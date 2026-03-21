#!/usr/bin/env python3
"""
Census Pipeline V4 — process 1926 Soviet census scans end-to-end.

Stages:
  0. Download images from TSDAVO e-resource (optional)
  1. Enumerate JPGs
  2. Dedup consecutive duplicates (SHA-256)
  3. Classify each image as first/second page via Gemini
  3.5. Verify classification — detect anomalies for Claude review
  4. Smart-pair first+second pages (tolerates missing backs)
  5. Extract nationality via Gemini (fast, simple task)
  6. Generate manifest for Claude FIO extraction (done in Cursor)
  7. Merge Claude FIO + Gemini nationality, mark Jewish, russify, write CSV

Usage:
    export GOOGLE_API_KEY=...

    # Download images for a new collection:
    python census_pipeline.py download --start 1411161 --end 1411566 --dest /path/to/582-1-1434

    # Process downloaded images:
    python census_pipeline.py process --source /path/to/582-1-1434

    # After Claude FIO extraction, rerun to finalize:
    python census_pipeline.py process --source /path/to/582-1-1434
"""

import argparse
import base64
import csv
import hashlib
import json
import os
import random
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image

# ── Stage 0: Download from TSDAVO ────────────────────────────────────

TSDAVO_URL = "https://e-resource.tsdavo.gov.ua/static/files/{prefix}/{file_id}.jpg"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def stage_download(start: int, end: int, dest: Path) -> int:
    """Download images from TSDAVO e-resource."""
    dest.mkdir(parents=True, exist_ok=True)
    prefix = str(start)[:3]
    total = end - start + 1
    downloaded = 0
    skipped = 0

    print(f"[0] Downloading {total} images ({start}..{end}) → {dest}")
    for file_id in range(start, end + 1):
        out_path = dest / f"{file_id}.jpg"
        if out_path.exists() and out_path.stat().st_size > 1000:
            skipped += 1
            continue

        url = TSDAVO_URL.format(prefix=prefix, file_id=file_id)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                out_path.write_bytes(resp.read())
            downloaded += 1
        except Exception as e:
            print(f"    FAIL {file_id}: {e}", file=sys.stderr)

        if downloaded % 50 == 0 and downloaded > 0:
            print(f"    [{downloaded + skipped}/{total}] downloaded={downloaded} skipped={skipped}")
        time.sleep(1 + random.random() * 3)

    print(f"    Done: {downloaded} new, {skipped} already existed")
    return downloaded


# ── Gemini client ────────────────────────────────────────────────────

MODEL_CLASSIFY = "gemini-3.1-flash-lite-preview"  # best at A/B page classification
MODEL_NATIONALITY = "gemini-2.0-flash"            # fast, simple nationality text

_client = None


def get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _client


def _gemini_raw(image_path: Path, prompt: str, model: str | None = None,
                retries: int = 3) -> str:
    """Send image + prompt to Gemini, return raw text response."""
    from google.genai import types

    raw = image_path.read_bytes()
    client = get_client()
    model = model or MODEL_CLASSIFY

    for attempt in range(retries):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[
                    types.Content(parts=[
                        types.Part.from_bytes(data=raw, mime_type="image/jpeg"),
                        types.Part.from_text(text=prompt),
                    ])
                ],
            )
            return resp.text.strip()
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    return ""


def call_gemini(image_path: Path, prompt: str, model: str | None = None,
                retries: int = 3) -> dict:
    """Send image + prompt to Gemini, parse JSON response."""
    try:
        text = _gemini_raw(image_path, prompt, model=model, retries=retries)
    except Exception as e:
        return {"error": str(e)}

    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {"raw": text, "error": "JSON parse failed"}


# ── Prompts ──────────────────────────────────────────────────────────

CLASSIFY_PROMPT = (
    "Classify this scanned document page. Is it:\n"
    "A) FRONT page — a census form (Сімейна картка) with printed questions "
    "and handwritten answers, starting with «ВСЕСОЮЗНИЙ ПЕРЕПИС НАСЕЛЕННЯ 1926 р.»\n"
    "B) BACK page — a rotated table/grid (Склад сім'ї) with numbered rows "
    "and columns for family members\n\n"
    "Answer with ONLY one letter: A or B"
)

NATIONALITY_PROMPT = """\
This is a scanned front page of a 1926 Soviet census family card \
(Сімейна картка, Форма №2, Всесоюзний перепис населення 1926 р.).

Find the nationality annotation (національність): a handwritten note, often in \
pencil or coloured ink, near the top or side of the form. Common values: "євр." \
(еврей/Jewish), "укр." (украинец), "рус." (русский), "пол." (поляк).

Return ONLY the nationality text you see, or "null" if not found. \
Do not return JSON, just the raw text."""

EXTRACT_PROMPT = """\
This is a scanned front page of a 1926 Soviet census family card \
(Сімейна картка, Форма №2, Всесоюзний перепис населення 1926 р.).

Extract two pieces of information from this handwritten document:

1. **Nationality annotation** (національність): a handwritten note, often in \
pencil or coloured ink, near the top of the form. Common values: "євр." \
(еврей/Jewish), "укр." (украинец), "рус." (русский), "пол." (поляк). \
Return null if not found.

2. **Head of family full name**: from field 3 "Прізвище, ім'я та по батькові". \
Extract as "Фамилия Имя Отчество".

Important:
- Read carefully, letter by letter if needed.
- These are Jewish/Ukrainian/Russian families from the Berdychiv area.
- Patronymics often end in -ович/-евич/-ич.

Return ONLY a JSON object (no markdown):
{
  "nationality": "text or null",
  "name": "Фамилия Имя Отчество",
  "confidence": "high/medium/low",
  "notes": "any observations"
}"""


# ── Helpers ──────────────────────────────────────────────────────────

def enumerate_images(source_dir: Path) -> list[Path]:
    return sorted(source_dir.glob("*.jpg"), key=lambda p: int(p.stem))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_cover_page(path: Path) -> bool:
    with Image.open(path) as img:
        w, h = img.size
    return h / w > 1.3


JEWISH_MARKERS = frozenset(
    {"євр", "евр", "єврей", "еврей", "єврейка", "еврейка", "єв", "ев",
     "жид", "жок", "евреи"}
)

CHAR_MAP = {"І": "И", "і": "и", "Ї": "И", "ї": "и",
            "Є": "Е", "є": "е", "Ґ": "Г", "ґ": "г"}
SUFFIX_MAP = [
    ("ський", "ский"), ("зький", "зкий"), ("цький", "цкий"),
    ("ській", "ский"), ("зькій", "зкий"), ("цькій", "цкий"),
    ("ська", "ская"), ("зька", "зкая"), ("цька", "цкая"),
    ("ське", "ское"),
]


def is_jewish_nationality(nat: str | None) -> bool:
    if not nat:
        return False
    low = nat.lower().strip().rstrip(".")
    return any(m in low for m in JEWISH_MARKERS)


def to_russian(name: str) -> str:
    if not name:
        return name
    for ua, ru in SUFFIX_MAP:
        name = name.replace(ua, ru)
    for ua, ru in CHAR_MAP.items():
        name = name.replace(ua, ru)
    return name


def load_json(path: Path) -> dict | list:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Stage 1-2: Enumerate & Dedup ─────────────────────────────────────

def stage_enumerate_and_dedup(source_dir: Path, output_dir: Path) -> list[Path]:
    images = enumerate_images(source_dir)
    print(f"[1] Found {len(images)} images in {source_dir}")

    if not images:
        print("    No images found — aborting.", file=sys.stderr)
        sys.exit(1)

    print("[2] Deduplicating by SHA-256...")
    hashes = [(img, sha256_file(img)) for img in images]

    clean = [hashes[0][0]]
    dups = []
    for i in range(1, len(hashes)):
        if hashes[i][1] == hashes[i - 1][1]:
            dups.append((hashes[i][0].name, hashes[i - 1][0].name))
        else:
            clean.append(hashes[i][0])

    if dups:
        log = output_dir / "duplicates.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(
            "\n".join(f"DUPLICATE: {a} == {b}" for a, b in dups),
            encoding="utf-8",
        )
        print(f"    Removed {len(dups)} duplicates (see {log})")

    # Strip cover pages
    start = 1 if is_cover_page(clean[0]) else 0
    end = len(clean)
    for i in range(len(clean) - 1, max(len(clean) - 4, start) - 1, -1):
        if is_cover_page(clean[i]):
            end = i
            break
    clean = clean[start:end]

    print(f"    Clean data images: {len(clean)}")
    return clean


# ── Stage 3: Classify pages ──────────────────────────────────────────

def stage_classify(images: list[Path], output_dir: Path) -> dict[str, str]:
    cache_file = output_dir / "page_types.json"
    cache: dict[str, str] = load_json(cache_file) if cache_file.exists() else {}

    remaining = [img for img in images if img.name not in cache]
    if not remaining:
        first_n = sum(1 for v in cache.values() if v == "first")
        print(f"[3] Classification cached: {first_n} first, {len(cache) - first_n} second")
        return cache

    print(f"[3] Classifying {len(remaining)} images (cached: {len(cache)})...")
    for i, img in enumerate(remaining):
        try:
            answer = _gemini_raw(img, CLASSIFY_PROMPT, model=MODEL_CLASSIFY).upper()
        except Exception:
            answer = "B"

        page_type = "first" if "A" in answer else "second"
        cache[img.name] = page_type

        if (i + 1) % 50 == 0 or i == len(remaining) - 1:
            save_json(cache_file, cache)
            f_n = sum(1 for v in cache.values() if v == "first")
            print(f"    [{len(cache)}/{len(images)}] first={f_n} second={len(cache) - f_n}")

        time.sleep(0.3)

    save_json(cache_file, cache)
    first_n = sum(1 for v in cache.values() if v == "first")
    print(f"    Done: {first_n} first, {len(cache) - first_n} second")
    return cache


# ── Stage 3.5: Detect sequence anomalies for Claude review ───────────

def stage_verify_classification(
    images: list[Path], page_types: dict[str, str], output_dir: Path,
) -> dict[str, str]:
    """
    Detect anomalies in first/second page sequence and write them for review.
    Returns the (possibly corrected) page_types dict.
    """
    corrections_file = output_dir / "classification_corrections.json"
    corrections: dict[str, str] = load_json(corrections_file) if corrections_file.exists() else {}

    if corrections:
        for fn, new_type in corrections.items():
            if fn in page_types:
                page_types[fn] = new_type
        print(f"[3.5] Applied {len(corrections)} classification corrections")

    seq = [(img, page_types.get(img.name, "second")) for img in images]
    anomalies = []

    for i in range(1, len(seq)):
        prev_img, prev_t = seq[i - 1]
        curr_img, curr_t = seq[i]
        if prev_t == curr_t:
            anomalies.append({
                "type": f"2x{curr_t}",
                "files": [prev_img.name, curr_img.name],
                "index": i,
            })

    anomaly_file = output_dir / "anomalies.json"
    save_json(anomaly_file, anomalies)

    if anomalies:
        first_n = sum(1 for _, t in seq if t == "first")
        second_n = sum(1 for _, t in seq if t == "second")
        print(f"[3.5] Classification: {first_n} first, {second_n} second")
        print(f"      Anomalies: {len(anomalies)} (review in {anomaly_file})")
        for a in anomalies:
            print(f"        {a['type']}: {a['files'][0]} / {a['files'][1]}")
        if not corrections:
            print(f"      >>> Ask Claude to visually verify these in Cursor,")
            print(f"          then save corrections to {corrections_file}")
    else:
        print(f"[3.5] Classification verified — no anomalies")

    return page_types


# ── Stage 4: Smart pairing ──────────────────────────────────────────

def stage_pair(images: list[Path], page_types: dict[str, str]) -> list[dict]:
    pairs = []
    pending_first: Path | None = None

    for img in images:
        pt = page_types.get(img.name, "second")
        if pt == "exclude":
            continue
        if pt == "first":
            if pending_first is not None:
                pairs.append({"first": pending_first, "second": None})
            pending_first = img
        else:  # second
            if pending_first is not None:
                pairs.append({"first": pending_first, "second": img})
                pending_first = None
            # else: orphan second page — skip

    if pending_first is not None:
        pairs.append({"first": pending_first, "second": None})

    print(f"[4] Paired into {len(pairs)} family cards")
    with_back = sum(1 for p in pairs if p["second"])
    print(f"    {with_back} with back page, {len(pairs) - with_back} without")
    return pairs


# ── Stage 5: Extract nationality via Gemini ──────────────────────────

def stage_nationality(pairs: list[dict], output_dir: Path) -> dict[str, str]:
    """Fast nationality extraction using Gemini (simple task it handles well)."""
    cache_file = output_dir / "nationalities.json"
    cache: dict[str, str] = load_json(cache_file) if cache_file.exists() else {}

    remaining = [(i, p) for i, p in enumerate(pairs) if p["first"].name not in cache]
    if not remaining:
        jewish_n = sum(1 for v in cache.values() if is_jewish_nationality(v))
        print(f"[5] Nationality cached for all {len(pairs)} pages ({jewish_n} Jewish)")
        return cache

    print(f"[5] Extracting nationality from {len(remaining)} first pages (cached: {len(cache)})...")
    for seq, (_, pair) in enumerate(remaining):
        fp = pair["first"]
        try:
            raw = _gemini_raw(fp, NATIONALITY_PROMPT, model=MODEL_NATIONALITY)
            nat = raw.strip().strip('"').strip("'")
            if nat.lower() == "null":
                nat = ""
        except Exception:
            nat = ""
        cache[fp.name] = nat

        if (seq + 1) % 50 == 0 or seq == len(remaining) - 1:
            save_json(cache_file, cache)
            jewish_n = sum(1 for v in cache.values() if is_jewish_nationality(v))
            print(f"    [{len(cache)}/{len(pairs)}] Jewish so far: {jewish_n}")

        time.sleep(0.3)

    save_json(cache_file, cache)
    jewish_n = sum(1 for v in cache.values() if is_jewish_nationality(v))
    print(f"    Done: {jewish_n} Jewish out of {len(cache)}")
    return cache


# ── Stage 6: Claude FIO manifest ─────────────────────────────────────
# NOTE: When processing FIO via Claude agents, ALWAYS provide both the first
# page AND its paired second page (back). The second page contains a family
# composition table with surname/initials that helps verify the FIO reading.
# Without cross-referencing, agents misread surnames (e.g. "Маронкній" vs "Аронкін").

def stage_claude_manifest(
    pairs: list[dict],
    nationalities: dict[str, str],
    output_dir: Path,
) -> tuple[Path, dict[str, dict], bool]:
    """
    Check for Claude FIO results; if missing, write manifest for processing.
    Returns (manifest_path, claude_data, is_complete).
    """
    claude_file = output_dir / "claude_fio.json"
    claude_data: dict[str, dict] = load_json(claude_file) if claude_file.exists() else {}

    first_pages = [p["first"].name for p in pairs]
    missing = [fn for fn in first_pages if fn not in claude_data]

    manifest_path = output_dir / "claude_manifest.json"
    manifest = {
        "source_dir": str(pairs[0]["first"].parent) if pairs else "",
        "total": len(first_pages),
        "done": len(first_pages) - len(missing),
        "remaining": missing,
    }
    save_json(manifest_path, manifest)

    if not missing:
        print(f"[6] Claude FIO complete for all {len(first_pages)} pages")
        return manifest_path, claude_data, True

    print(f"[6] Claude FIO: {len(first_pages) - len(missing)}/{len(first_pages)} done, "
          f"{len(missing)} remaining")
    print(f"    Manifest written to: {manifest_path}")
    print(f"    Claude data file:    {claude_file}")
    return manifest_path, claude_data, False


# ── Stage 7: Finalize — merge, russify, write CSV ────────────────────

def stage_finalize(
    pairs: list[dict],
    nationalities: dict[str, str],
    claude_data: dict[str, dict],
    output_dir: Path,
) -> Path:
    rows = []
    for pair in pairs:
        fn = pair["first"].name
        nat = nationalities.get(fn, "")
        jewish = is_jewish_nationality(nat)
        cd = claude_data.get(fn, {})
        name_raw = cd.get("name", "")
        conf = cd.get("confidence", "")
        notes = cd.get("notes", "")
        name_ru = to_russian(name_raw)

        rows.append({
            "filename": fn,
            "name": name_ru,
            "confidence": conf,
            "nationality": nat,
            "notes": notes,
            "not_jewish": "true" if not jewish else "",
        })

    rows.sort(key=lambda r: int(r["filename"].replace(".jpg", "")))

    csv_path = output_dir / "review.csv"
    fields = ["filename", "name", "confidence", "nationality", "notes", "not_jewish"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    total = len(rows)
    jewish_n = sum(1 for r in rows if not r["not_jewish"])
    named_n = sum(1 for r in rows if r["name"])

    print(f"\n{'=' * 60}")
    print(f"[7] Pipeline complete")
    print(f"  Total first pages : {total}")
    print(f"  Jewish            : {jewish_n}")
    print(f"  Not Jewish        : {total - jewish_n}")
    print(f"  Names extracted   : {named_n}")
    print(f"\n  CSV: {csv_path}")
    print(f"{'=' * 60}")
    return csv_path


# ── Main ─────────────────────────────────────────────────────────────

def cmd_download(args):
    dest = args.dest.resolve()
    stage_download(args.start, args.end, dest)
    print(f"\nTo process, run:")
    print(f"  python cli/census_pipeline.py process --source {dest}")


def cmd_process(args):
    source: Path = args.source.resolve()
    if not source.is_dir():
        print(f"Source directory not found: {source}", file=sys.stderr)
        sys.exit(1)
    if not os.environ.get("GOOGLE_API_KEY"):
        print("Set GOOGLE_API_KEY environment variable", file=sys.stderr)
        sys.exit(1)

    output: Path = args.output or (Path(__file__).parent / "census_output" / source.name)
    output.mkdir(parents=True, exist_ok=True)

    print(f"Census Pipeline V4")
    print(f"  Source : {source}")
    print(f"  Output : {output}")
    print(f"  Classify: {MODEL_CLASSIFY}")
    print(f"  National: {MODEL_NATIONALITY}")
    print(f"  FIO     : Claude (via Cursor)")
    print()

    # Stages 1-2: Enumerate & dedup
    clean_images = stage_enumerate_and_dedup(source, output)

    # Stage 3: Classify pages via Gemini
    page_types = stage_classify(clean_images, output)

    # Stage 3.5: Verify classification — detect anomalies for Claude review
    page_types = stage_verify_classification(clean_images, page_types, output)

    # Stage 4: Smart-pair
    pairs = stage_pair(clean_images, page_types)

    # Stage 5: Nationality via Gemini
    nationalities = stage_nationality(pairs, output)

    # Stage 6: Check Claude FIO status
    manifest_path, claude_data, is_complete = stage_claude_manifest(pairs, nationalities, output)

    if not is_complete:
        print(f"\n>>> Claude FIO extraction needed.")
        print(f"    In Cursor, ask Claude to process images from: {manifest_path}")
        print(f"    After Claude finishes, rerun this command to generate review.csv")
        return

    # Stage 7: Finalize
    csv_path = stage_finalize(pairs, nationalities, claude_data, output)

    print(f"\nTo review, run:")
    print(f"  python cli/review_server.py --source {source} --csv {csv_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Census Pipeline V4 — download, classify, extract",
    )
    sub = parser.add_subparsers(dest="command")

    dl = sub.add_parser("download", help="Download images from TSDAVO e-resource")
    dl.add_argument("--start", type=int, required=True, help="First file ID")
    dl.add_argument("--end", type=int, required=True, help="Last file ID")
    dl.add_argument("--dest", type=Path, required=True, help="Destination directory")

    proc = sub.add_parser("process", help="Process downloaded images")
    proc.add_argument("--source", type=Path, required=True, help="Source image directory")
    proc.add_argument("--output", type=Path, default=None, help="Output directory")

    args = parser.parse_args()
    if args.command == "download":
        cmd_download(args)
    elif args.command == "process":
        cmd_process(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
