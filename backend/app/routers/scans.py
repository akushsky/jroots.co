"""Chat scan endpoints: upload (synchronous vision pipeline) and image fetch."""

import logging
import os

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Scan, User
from app.rate_limit import limiter
from app.routers.chat import _get_owned_session
from app.services import scan_pipeline
from app.services.auth import get_current_user

logger = logging.getLogger("jroots")

router = APIRouter(prefix="/api/chat", tags=["scans"])


def _scan_payload(scan: Scan) -> dict:
    metadata = scan.metadata_json or {}
    return {
        "scan_id": scan.id,
        "status": scan.status,
        "extracted_text": scan.extracted_text,
        "metadata": {
            "doc_type": metadata.get("doc_type"),
            "names": metadata.get("names") or [],
            "dates": metadata.get("dates") or [],
            "place": metadata.get("place"),
        },
        "model_used": scan.model_used,
        "watermarked": bool(scan.watermarked),
    }


@router.post("/sessions/{session_id}/scans", status_code=201)
@limiter.limit("5/minute")
async def upload_scan(
    session_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await _get_owned_session(db, session_id, current_user.id)
    # Read at most limit+1 so an oversized body is rejected without loading
    # the whole payload into memory.
    data = await file.read(scan_pipeline.MAX_SCAN_BYTES + 1)
    try:
        scan = await scan_pipeline.process_upload(
            db,
            user_id=current_user.id,
            session_id=session.id,
            data=data,
        )
    except scan_pipeline.ScanTooLargeError:
        raise HTTPException(
            status_code=413,
            detail="Файл больше 10 МБ — сожмите или обрежьте скан",
        )
    except scan_pipeline.UnsupportedMediaError:
        raise HTTPException(
            status_code=415, detail="Поддерживаются только JPEG, PNG и TIFF"
        )
    except scan_pipeline.NoScansLeftError:
        raise HTTPException(status_code=402, detail="no_scans_left")
    return _scan_payload(scan)


@router.get("/scans/{scan_id}/image")
async def get_scan_image(
    scan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Serve the stored scan copy (watermarked for free-tier uploads)."""
    scan = await db.get(Scan, scan_id)
    if scan is None or scan.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Скан не найден")
    if not scan.file_path or not os.path.exists(scan.file_path):
        raise HTTPException(status_code=404, detail="Файл скана не найден")
    return FileResponse(scan.file_path, media_type="image/jpeg")
