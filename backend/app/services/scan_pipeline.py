"""Scan pipeline for chat uploads: validation, normalization, vision extraction.

Flow (POST /api/chat/sessions/{id}/scans):
1. Size + magic-bytes validation (413/415) — before any DB or LLM work.
2. Credit pre-check (402 no_scans_left) — never burn vision tokens for free.
3. Pillow normalization: TIFF/PNG → JPEG, downscale to 2000 px on the long
   side, decompression-bomb guard.
4. Vision transcription + metadata via the Moonshot client (main model,
   one escalation retry on unparseable/low-confidence output).
5. Free-tier scans get the JRoots watermark baked into the stored copy.
6. One scan credit is charged AFTER successful extraction; technical vision
   failures leave status='error' and are never charged.

Context hygiene (TZ 2.6): only the extracted text + metadata enter the chat
context — the image itself never does.
"""

import asyncio
import base64
import json
import logging
import os
import re
from io import BytesIO
from typing import Any

from PIL import Image as PILImage, ImageOps
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import ChatMessage, Scan
from app.services import credits as credits_service
from app.services import image as image_service
from app.services import llm_router
from app.services.credits import InsufficientCredits

logger = logging.getLogger("jroots")

MAX_SCAN_BYTES = 10 * 1024 * 1024
MAX_SCAN_DIMENSION = 2000
# Decompression-bomb guard: a small file can still decode to gigapixels.
MAX_SCAN_PIXELS = 50_000_000
JPEG_QUALITY = 90
VISION_TIMEOUT_SECONDS = 55.0

VISION_PROMPT = (
    "Ты — палеограф, эксперт по еврейским генеалогическим документам. "
    "Внимательно прочитай документ на изображении (старорусская скоропись, "
    "идиш, иврит — старайся изо всех сил) и верни СТРОГО один JSON-объект "
    "без пояснений и markdown-разметки:\n"
    '{"transcription": string, "doc_type": string|null, "names": string[], '
    '"dates": string[], "place": string|null, "confidence": "high"|"low"}\n'
    "transcription — полная транскрипция читаемого текста; нечитаемые места "
    "помечай [неразборчиво]. doc_type — тип документа (метрическая запись, "
    "ревизская сказка, домовая книга и т.п.). names — все имена/фамилии из "
    "документа. dates — все даты. place — место составления. "
    'confidence="low", если текст в основном не читается.'
)


class ScanTooLargeError(Exception):
    pass


class UnsupportedMediaError(Exception):
    pass


class NoScansLeftError(Exception):
    pass


class VisionExtractionError(Exception):
    pass


class ForeignScanError(Exception):
    pass


def _sniff_format(data: bytes) -> str | None:
    """Detect the real image format from magic bytes, never the extension."""
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "TIFF"
    return None


def _normalize_sync(data: bytes) -> bytes:
    """Decode (with a pixel cap against bombs), downscale, re-encode as JPEG.

    The pixel cap is enforced EXPLICITLY right after open(): the size is
    known from the header, so an oversized image is rejected before a single
    pixel is decoded. PIL's own MAX_IMAGE_PIXELS is not relied upon — it
    only warns at 1x and raises at 2x, letting a 64Mpx PNG decode ~200 MB.
    """
    with PILImage.open(BytesIO(data)) as img:
        if img.width * img.height > MAX_SCAN_PIXELS:
            raise UnsupportedMediaError(
                f"image is {img.width}x{img.height} px "
                f"({img.width * img.height} px > {MAX_SCAN_PIXELS} px limit)"
            )
        img = ImageOps.exif_transpose(img)
        img.load()
        if max(img.size) > MAX_SCAN_DIMENSION:
            resample = PILImage.Resampling.LANCZOS
            img.thumbnail((MAX_SCAN_DIMENSION, MAX_SCAN_DIMENSION), resample=resample)
        rgb = img.convert("RGB")
        buffer = BytesIO()
        rgb.save(buffer, format="JPEG", quality=JPEG_QUALITY)
        return buffer.getvalue()


def _scan_file_path(user_id: int, scan_id: int) -> str:
    return os.path.join(
        get_settings().media_path, "scans", str(user_id), f"{scan_id}.jpg"
    )


def _write_file_sync(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


async def _watermark(jpeg_bytes: bytes) -> bytes:
    """Bake the JRoots watermark into the stored copy (free tier)."""
    watermarked = await image_service.apply_watermark(jpeg_bytes)
    buffer = BytesIO()
    watermarked.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


def _parse_vision_payload(raw: str) -> dict[str, Any] | None:
    """Extract the strict JSON object from a vision response, tolerating
    markdown fences and leading/trailing prose."""
    text = re.sub(r"```(?:json)?", "", raw).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "transcription" not in payload:
        return None
    return payload


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


async def extract_scan_content(jpeg_bytes: bytes) -> tuple[str, dict[str, Any], str]:
    """Transcribe the scan and extract metadata via the vision model.

    Returns (extracted_text, metadata, model_used). The main model is tried
    first; an unparseable or low-confidence answer escalates once to the
    escalation model. Raises VisionExtractionError when both attempts fail.
    """
    settings = get_settings()
    client = llm_router.get_llm_client()
    data_uri = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_PROMPT},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }
    ]

    attempts = [settings.llm_model_main]
    if settings.llm_model_escalation != settings.llm_model_main:
        attempts.append(settings.llm_model_escalation)

    last_error: Exception | None = None
    for model in attempts:
        try:
            response = await client.chat.completions.create(
                model=model, messages=messages, timeout=VISION_TIMEOUT_SECONDS
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:  # provider/network failure on this model
            last_error = exc
            logger.warning("Vision call failed on model %s: %s", model, exc)
            continue
        payload = _parse_vision_payload(raw)
        if payload is not None and payload.get("confidence") != "low":
            metadata = {
                "doc_type": payload.get("doc_type"),
                "names": _string_list(payload.get("names")),
                "dates": _string_list(payload.get("dates")),
                "place": payload.get("place"),
            }
            return str(payload["transcription"]), metadata, model
        logger.info(
            "Vision output on %s is unparseable or low-confidence, escalating",
            model,
        )

    raise VisionExtractionError(
        f"Vision extraction failed on all models (last error: {last_error})"
    )


async def process_upload(
    db: AsyncSession,
    *,
    user_id: int,
    session_id: int,
    data: bytes,
) -> Scan:
    """Full upload pipeline. Raises ScanTooLargeError, UnsupportedMediaError
    or NoScansLeftError before a Scan row exists; a vision failure is
    reported on the returned scan as status='error' (never charged)."""
    if len(data) > MAX_SCAN_BYTES:
        raise ScanTooLargeError(f"{len(data)} bytes > {MAX_SCAN_BYTES}")
    if _sniff_format(data) is None:
        raise UnsupportedMediaError("not a JPEG/PNG/TIFF payload")

    # 402 before any heavy work: no free vision burns without credits.
    balance = await credits_service.get_balance(db, user_id)
    if balance["scans_left"] < 1:
        raise NoScansLeftError(f"user {user_id} has no scan credits")

    try:
        jpeg_bytes = await asyncio.to_thread(_normalize_sync, data)
    except UnsupportedMediaError:
        raise
    except Exception as exc:
        raise UnsupportedMediaError(f"undecodable image: {exc}") from exc

    is_free = await llm_router.is_free_user(db, user_id)

    scan = Scan(user_id=user_id, session_id=session_id, status="processing")
    db.add(scan)
    await db.flush()

    try:
        extracted_text, metadata, model_used = await extract_scan_content(jpeg_bytes)
    except VisionExtractionError:
        scan.status = "error"
        await db.commit()
        await db.refresh(scan)
        logger.warning(
            "Vision extraction failed for scan %d (user %d) — not charged",
            scan.id,
            user_id,
        )
        return scan

    stored_bytes = jpeg_bytes
    if is_free:
        stored_bytes = await _watermark(jpeg_bytes)
        scan.watermarked = True

    file_path = _scan_file_path(user_id, scan.id)
    await asyncio.to_thread(_write_file_sync, file_path, stored_bytes)

    scan.file_path = file_path
    scan.extracted_text = extracted_text
    scan.metadata_json = metadata
    scan.model_used = model_used
    scan.status = "done"

    try:
        await credits_service.charge(
            db, user_id, scans=1, reason="usage", ref_id=f"scan:{scan.id}"
        )
    except InsufficientCredits:
        # The balance raced to zero after the pre-check; the processed scan
        # stays delivered, the charge is dropped (mirrors the agent cycle).
        logger.warning(
            "Scan charge raced to zero for user %d (scan %d) — not charged",
            user_id,
            scan.id,
        )

    await db.commit()
    await db.refresh(scan)
    logger.info(
        "Scan %d processed for user %d (model=%s, watermarked=%s)",
        scan.id,
        user_id,
        scan.model_used,
        scan.watermarked,
    )
    return scan


def build_scan_context(scans: list[Scan]) -> str:
    """The «[Приложены сканы #N: …]» block injected into the LLM context —
    extracted text + metadata only, never the image."""
    blocks: list[str] = []
    for scan in scans:
        metadata = scan.metadata_json or {}
        fields: list[str] = []
        if metadata.get("doc_type"):
            fields.append(f"документ: {metadata['doc_type']}")
        if metadata.get("names"):
            fields.append("имена: " + ", ".join(metadata["names"]))
        if metadata.get("dates"):
            fields.append("даты: " + ", ".join(metadata["dates"]))
        if metadata.get("place"):
            fields.append(f"место: {metadata['place']}")
        header = f"Скан #{scan.id}"
        if fields:
            header += " (" + "; ".join(fields) + ")"
        blocks.append(f"{header}:\n{scan.extracted_text or ''}")
    ids = ", ".join(f"#{scan.id}" for scan in scans)
    return f"[Приложены сканы {ids}:\n" + "\n---\n".join(blocks) + "]"


async def load_owned_scans(
    db: AsyncSession, user_id: int, scan_ids: list[int]
) -> list[Scan]:
    """Fetch scans by ids, requiring every one to exist and belong to the
    user. Raises ForeignScanError otherwise."""
    result = await db.execute(
        select(Scan).where(Scan.id.in_(scan_ids)).order_by(Scan.id)
    )
    scans = list(result.scalars().all())
    if len(scans) != len(set(scan_ids)) or any(
        scan.user_id != user_id for scan in scans
    ):
        raise ForeignScanError(f"user {user_id} cannot reference scans {scan_ids}")
    return scans


async def augment_history_with_scans(
    db: AsyncSession, rows: list[ChatMessage]
) -> list[dict[str, str]]:
    """Serialize chat rows into LLM messages, appending the scan context
    block (from the DB, server-side) to user messages carrying scan_ids."""
    all_ids = {scan_id for row in rows for scan_id in (row.scan_ids or [])}
    scans_by_id: dict[int, Scan] = {}
    if all_ids:
        result = await db.execute(select(Scan).where(Scan.id.in_(all_ids)))
        scans_by_id = {scan.id: scan for scan in result.scalars().all()}

    messages: list[dict[str, str]] = []
    for row in rows:
        content = row.content
        attached = [
            scans_by_id[scan_id]
            for scan_id in (row.scan_ids or [])
            if scan_id in scans_by_id and scans_by_id[scan_id].status == "done"
        ]
        if attached:
            content = f"{content}\n\n{build_scan_context(attached)}"
        messages.append({"role": row.role, "content": content})
    return messages
