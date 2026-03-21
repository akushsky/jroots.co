#!/usr/bin/env python3
"""
Process 1926 Soviet census images: detect duplicates, extract nationality
and names from BOTH first and second pages, cross-verify, filter Jewish families.

Usage:
    # Sample batch (first 10 cards, both pages):
    python process_census.py --source /path/to/582-1-1433 --sample 10

    # Full run:
    python process_census.py --source /path/to/582-1-1433

    # Generate review CSV from existing JSON:
    python process_census.py --review-only

Environment variables:
    GOOGLE_API_KEY  - for Gemini Vision
"""

import argparse
import base64
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from PIL import Image
from tqdm import tqdm

FIRST_PAGE_PROMPT = """This is a scanned front page of a 1926 Soviet census family card (Сімейна картка, Форма №2, Всесоюзний перепис населення 1926 р.).

Your task: extract two pieces of information from this handwritten document.

1. **Nationality annotation** (національність): Look for a handwritten annotation, often in pencil or red/blue ink, typically near the top of the form or near the head-of-family section. Common values: "євр." (еврей/Jewish), "укр." (украинец), "рус." (русский), "пол." (поляк). It may also say "еврей", "евр", "єврей" etc. If you cannot find any nationality annotation, return null.

2. **Head of family full name**: From field 3 "Прізвище, ім'я та по батькові" (Surname, first name and patronymic) of the head of family ("Голова сім'ї або одинець"). This is handwritten text after the printed label. Extract the full name in the format "Фамилия Имя Отчество".

Return ONLY a JSON object (no markdown, no code fences) with this exact structure:
{
  "nationality": "the nationality annotation text or null if not found",
  "name": "Фамилия Имя Отчество",
  "confidence": "high/medium/low",
  "notes": "any relevant observations, e.g. illegible parts, uncertain readings"
}"""

SECOND_PAGE_PROMPT = """This is the back side of a 1926 Soviet census family card (Сімейна картка, Форма №2). It contains a table "Склад сім'ї" (family composition) listing family members.

IMPORTANT: The image may be rotated 90 degrees clockwise. If so, mentally rotate it to read the table correctly.

The table has numbered rows (1, 2, 3...) and columns. Row 1 is always the head of family.

Column 2 contains "Прізвище, ім'я та по батькові" (Surname, first name and patronymic).

Your task: Extract the name from ROW 1, COLUMN 2 — this is the head of family's surname, first name, and patronymic. Sometimes only the surname and initials are written.

Also look at the top-right area of the page for questions 19-21, where additional information may be written.

Return ONLY a JSON object (no markdown, no code fences):
{
  "name": "Фамилия Имя Отчество (or whatever is written)",
  "confidence": "high/medium/low",
  "notes": "any observations about legibility or the table content"
}"""

OUTPUT_DIR = Path(__file__).parent / "census_output"
RESULTS_FILE = OUTPUT_DIR / "extracted_data.json"
REVIEW_CSV = OUTPUT_DIR / "review.csv"
DEDUP_LOG = OUTPUT_DIR / "duplicates.log"


def load_image_base64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_image_dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.size


def enumerate_images(source_dir: Path) -> list[Path]:
    return sorted(source_dir.glob("*.jpg"), key=lambda p: int(p.stem))


def is_cover_page(path: Path) -> bool:
    w, h = get_image_dimensions(path)
    return h / w > 1.3


# ── Gemini API ──────────────────────────────────────────────────────

_gemini_model = None

def get_gemini_model():
    global _gemini_model
    if _gemini_model is None:
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
        _gemini_model = genai.GenerativeModel("gemini-2.0-flash")
    return _gemini_model


def call_gemini(image_b64: str, prompt: str) -> dict:
    model = get_gemini_model()
    image_bytes = base64.standard_b64decode(image_b64)
    response = model.generate_content([
        {"mime_type": "image/jpeg", "data": image_bytes},
        prompt,
    ])
    text = response.text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return {"raw": text, "error": "Failed to parse JSON"}


def extract_first_page(image_b64: str) -> dict:
    try:
        return call_gemini(image_b64, FIRST_PAGE_PROMPT)
    except Exception as e:
        return {"error": str(e)}


def extract_second_page(image_b64: str) -> dict:
    try:
        return call_gemini(image_b64, SECOND_PAGE_PROMPT)
    except Exception as e:
        return {"error": str(e)}


# ── Dedup & Pairing ────────────────────────────────────────────────

def dedup_images(images: list[Path]) -> tuple[list[Path], list[tuple[Path, Path]]]:
    """Remove consecutive duplicate images by SHA-256. Returns (clean list, duplicate pairs)."""
    if not images:
        return [], []

    hashes: list[tuple[Path, str]] = []
    print("Computing image hashes for duplicate detection...")
    for img in tqdm(images, desc="Hashing"):
        hashes.append((img, sha256_file(img)))

    clean = [hashes[0][0]]
    duplicates = []

    for i in range(1, len(hashes)):
        if hashes[i][1] == hashes[i - 1][1]:
            duplicates.append((hashes[i][0], hashes[i - 1][0]))
        else:
            clean.append(hashes[i][0])

    return clean, duplicates


def pair_pages(images: list[Path]) -> list[dict]:
    """
    Pair images into (first_page, second_page) after removing covers.
    Expects images are already deduped.
    """
    if len(images) < 3:
        return []

    start_idx = 1 if is_cover_page(images[0]) else 0

    end_idx = len(images)
    for i in range(len(images) - 1, max(len(images) - 4, start_idx) - 1, -1):
        if is_cover_page(images[i]):
            end_idx = i
            break

    data_images = images[start_idx:end_idx]
    pairs = []
    for i in range(0, len(data_images) - 1, 2):
        pairs.append({
            "first_page": data_images[i],
            "second_page": data_images[i + 1],
        })

    if len(data_images) % 2 == 1:
        pairs.append({
            "first_page": data_images[-1],
            "second_page": None,
        })

    return pairs


# ── Cross-verification ──────────────────────────────────────────────

def extract_surname(full_name: str | None) -> str | None:
    if not full_name:
        return None
    parts = full_name.strip().split()
    return parts[0].lower().rstrip(".,") if parts else None


def names_match(name1: str | None, name2: str | None) -> bool | None:
    s1 = extract_surname(name1)
    s2 = extract_surname(name2)
    if not s1 or not s2:
        return None
    # Fuzzy: check if one surname starts with the other (handles abbreviations)
    shorter, longer = sorted([s1, s2], key=len)
    return longer.startswith(shorter) or shorter.startswith(longer)


def merge_names(first_page_data: dict, second_page_data: dict) -> str:
    """Pick the best combined name from first and second page extractions."""
    name1 = first_page_data.get("name")
    name2 = second_page_data.get("name")

    if not name1 and not name2:
        return ""
    if not name1:
        return name2 or ""
    if not name2:
        return name1 or ""

    conf1 = first_page_data.get("confidence", "low")
    conf2 = second_page_data.get("confidence", "low")

    conf_order = {"high": 3, "medium": 2, "low": 1}
    c1 = conf_order.get(conf1, 0)
    c2 = conf_order.get(conf2, 0)

    # If both have names, prefer the one with more parts (more complete)
    parts1 = len((name1 or "").split())
    parts2 = len((name2 or "").split())

    if parts1 >= 3 and parts2 < 3:
        return name1
    if parts2 >= 3 and parts1 < 3:
        return name2
    if c1 >= c2:
        return name1
    return name2


# ── Main pipeline ───────────────────────────────────────────────────

def load_results() -> list[dict]:
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_results(results: list[dict]):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def is_fully_processed(entry: dict) -> bool:
    return "gemini_first" in entry and "gemini_second" in entry


def process_images(source_dir: Path, sample_size: int | None = None):
    images = enumerate_images(source_dir)
    print(f"Found {len(images)} images in {source_dir}")

    clean_images, duplicates = dedup_images(images)
    if duplicates:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(DEDUP_LOG, "w", encoding="utf-8") as f:
            for dup, original in duplicates:
                f.write(f"DUPLICATE: {dup.name} == {original.name}\n")
        print(f"Removed {len(duplicates)} duplicate images (logged to {DEDUP_LOG})")
    else:
        print("No duplicates found")
    print(f"Clean images: {len(clean_images)}")

    pairs = pair_pages(clean_images)
    print(f"Paired into {len(pairs)} family cards (after removing covers)")

    if sample_size:
        pairs = pairs[:sample_size]
        print(f"Sample mode: processing first {sample_size} cards")

    results = load_results()
    processed_map = {r["filename"]: r for r in results}

    new_count = 0
    for pair in tqdm(pairs, desc="Processing family cards"):
        first_page: Path = pair["first_page"]
        fname = first_page.name
        second_page = pair["second_page"]

        existing = processed_map.get(fname)
        if existing and is_fully_processed(existing):
            continue

        if existing:
            entry = existing
        else:
            entry = {
                "filename": fname,
                "pair_filename": second_page.name if second_page else None,
            }

        # First page
        if "gemini_first" not in entry:
            tqdm.write(f"  first:  {fname}")
            b64 = load_image_base64(first_page)
            entry["gemini_first"] = extract_first_page(b64)
            time.sleep(0.5)

        # Second page
        if "gemini_second" not in entry and second_page:
            tqdm.write(f"  second: {second_page.name}")
            b64 = load_image_base64(second_page)
            entry["gemini_second"] = extract_second_page(b64)
            time.sleep(0.5)
        elif "gemini_second" not in entry:
            entry["gemini_second"] = {"name": None, "confidence": "low", "notes": "no second page"}

        # Cross-verify
        name_first = entry.get("gemini_first", {}).get("name")
        name_second = entry.get("gemini_second", {}).get("name")
        entry["names_match"] = names_match(name_first, name_second)
        entry["merged_name"] = merge_names(
            entry.get("gemini_first", {}),
            entry.get("gemini_second", {}),
        )
        entry["is_jewish"] = None
        entry["final_name"] = None

        if existing:
            pass  # already in results list
        else:
            results.append(entry)
            processed_map[fname] = entry

        new_count += 1
        if new_count % 5 == 0:
            save_results(results)

    save_results(results)
    print(f"\nProcessed {len(results)} cards total. Results saved to {RESULTS_FILE}")
    return results


JEWISH_MARKERS = {"євр", "евр", "еврей", "єврей", "єв", "ев", "jewish", "jew", "еврейк"}


def auto_detect_jewish(results: list[dict]) -> list[dict]:
    for entry in results:
        if entry.get("is_jewish") is not None:
            continue

        nat = (entry.get("gemini_first", {}).get("nationality") or "").lower().strip().rstrip(".")
        entry["is_jewish"] = any(marker in nat for marker in JEWISH_MARKERS) if nat else False

    return results


def generate_review_csv(results: list[dict]):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = auto_detect_jewish(results)
    save_results(results)

    fieldnames = [
        "filename", "pair_filename",
        "nationality", "name_first_page", "confidence_first",
        "name_second_page", "confidence_second",
        "names_match", "merged_name",
        "is_jewish", "final_name",
        "notes_first", "notes_second",
    ]

    with open(REVIEW_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for entry in results:
            gf = entry.get("gemini_first", {})
            gs = entry.get("gemini_second", {})
            writer.writerow({
                "filename": entry["filename"],
                "pair_filename": entry.get("pair_filename", ""),
                "nationality": gf.get("nationality", ""),
                "name_first_page": gf.get("name", ""),
                "confidence_first": gf.get("confidence", ""),
                "name_second_page": gs.get("name", ""),
                "confidence_second": gs.get("confidence", ""),
                "names_match": entry.get("names_match", ""),
                "merged_name": entry.get("merged_name", ""),
                "is_jewish": entry.get("is_jewish", ""),
                "final_name": entry.get("final_name", ""),
                "notes_first": gf.get("notes", ""),
                "notes_second": gs.get("notes", ""),
            })

    jewish_count = sum(1 for r in results if r.get("is_jewish"))
    match_count = sum(1 for r in results if r.get("names_match") is True)
    mismatch_count = sum(1 for r in results if r.get("names_match") is False)
    print(f"\nReview CSV: {REVIEW_CSV}")
    print(f"Total cards: {len(results)}")
    print(f"Auto-detected Jewish: {jewish_count}")
    print(f"Name cross-check: {match_count} match, {mismatch_count} mismatch, "
          f"{len(results) - match_count - mismatch_count} unknown")


def main():
    parser = argparse.ArgumentParser(description="Process 1926 census images")
    parser.add_argument("--source", type=Path, help="Source directory with JPG images")
    parser.add_argument("--sample", type=int, default=None,
                        help="Process only first N family cards (for testing)")
    parser.add_argument("--review-only", action="store_true",
                        help="Only generate review CSV from existing results")
    args = parser.parse_args()

    if args.review_only:
        results = load_results()
        if not results:
            print("No results found. Run processing first.", file=sys.stderr)
            sys.exit(1)
        generate_review_csv(results)
        return

    if not args.source:
        parser.error("--source is required unless using --review-only")
    if not args.source.is_dir():
        parser.error(f"Source directory not found: {args.source}")
    if not os.environ.get("GOOGLE_API_KEY"):
        parser.error("GOOGLE_API_KEY environment variable required")

    results = process_images(args.source, args.sample)
    generate_review_csv(results)


if __name__ == "__main__":
    main()
