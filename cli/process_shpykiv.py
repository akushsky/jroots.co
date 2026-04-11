"""
process_shpykiv.py — Extract alphabetical index from ДАКО 335-1-26
(Посімейний список євреїв м. Шпикова, 1902).

Steps:
  1. OCR alphabetical index pages (2-7) via Gemini
  2. Map family numbers to register pages
  3. Finalize into upload CSVs

Usage:
  python cli/process_shpykiv.py --step extract     # OCR index pages 2-7
  python cli/process_shpykiv.py --step map          # Build family_num → page mapping
  python cli/process_shpykiv.py --step finalize     # Generate final.jsonl + CSVs
  python cli/process_shpykiv.py --step all          # All steps
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

BASE_DIR = Path("cli/dazho_downloads")
CASE_ID = "335-1-26"
PAGES_DIR = BASE_DIR / f"{CASE_ID}_pages"
INDEX_PAGES = list(range(2, 8))  # pages 2-7

IMAGE_KEY = "Посімейний список євреїв м. Шпикова, 1902"
IMAGE_SOURCE_ID = 23  # ДАКО
IMAGE_PATH = CASE_ID

PROMPT_INDEX = """\
This is a page from the alphabetical index (Алфавитъ) of a 1902 Jewish family register
(Посімейний список) from the town of Shpykiv, Bratslav district, Podolia province.

The page is a two-page spread. Each side has a table with three columns:
1. Фамилія (Surname)
2. Имя (Given name, sometimes with patronymic or description like "сёстры", "братъ")
3. № (Family number in the register — a sequential number)

The entries are grouped by first letter of the surname (А, Б, В, etc.).

Instructions:
- Extract ALL entries from BOTH sides of the spread (left page and right page).
- For each entry return: {"surname": "...", "given_name": "...", "family_num": <int>}
- Transcribe exactly as written (pre-revolutionary orthography: ъ, і, ѣ, etc.)
- If a cell spans multiple lines, combine into one entry.
- If given_name says something like "сёстры Ароновъ" or "братъ его", include it as-is.
- Return ONLY a JSON array, no markdown, no explanations.
- If the page has no index table, return [].
"""


def modernize_name(name: str) -> str:
    """Normalize pre-revolutionary orthography."""
    name = re.sub(r"ъ(?=[-\s.,;:!?\"]|$)", "", name)
    name = name.replace("і", "и").replace("І", "И")
    name = name.replace("i", "и").replace("I", "И")
    name = name.replace("ѣ", "е").replace("Ѣ", "Е")
    name = name.replace("ѳ", "ф").replace("Ѳ", "Ф")
    return name


def find_page_file(page_num: int) -> Path | None:
    """Find the PNG file for a given page number (handles different naming patterns)."""
    for pattern in [f"page-{page_num:03d}.jpg", f"page-{page_num:03d}.png", f"page-{page_num:02d}.jpg", f"page-{page_num:02d}.png"]:
        p = PAGES_DIR / pattern
        if p.exists():
            return p
    return None


def step_extract():
    """OCR alphabetical index pages via Gemini."""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    output_file = BASE_DIR / f"{CASE_ID}_alphabet.jsonl"

    with open(output_file, "w", encoding="utf-8") as out:
        for page_num in INDEX_PAGES:
            page_path = find_page_file(page_num)
            if not page_path:
                print(f"  Page {page_num}: file not found, skipping")
                continue

            print(f"  Page {page_num} ({page_path.name}) ...", end=" ", flush=True)
            try:
                # Resize if too large for Gemini
                from PIL import Image
                import io
                img = Image.open(page_path)
                if max(img.size) > 6000:
                    img.thumbnail((6000, 6000))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=90)
                img_bytes = buf.getvalue()
                mime = "image/jpeg"

                resp = client.models.generate_content(
                    model="gemini-3.1-pro-preview",
                    contents=[
                        types.Content(parts=[
                            types.Part.from_bytes(data=img_bytes, mime_type=mime),
                            types.Part.from_text(text=PROMPT_INDEX),
                        ])
                    ],
                    config=types.GenerateContentConfig(max_output_tokens=8192),
                )
                text = (resp.text or "").strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

                entries = json.loads(text)
                record = {"page": page_path.name, "page_num": page_num, "data": entries}
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                print(f"{len(entries)} entries")
            except Exception as e:
                print(f"ERROR: {e}")
                record = {"page": page_path.name, "page_num": page_num, "data": [], "error": str(e)}
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()

            time.sleep(2)

    # Summary
    total = 0
    with open(output_file) as f:
        for line in f:
            r = json.loads(line)
            total += len(r.get("data", []))
    print(f"\nTotal: {total} entries → {output_file}")


def step_map():
    """Build family_num → register page mapping by scanning register pages for family numbers."""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    map_file = BASE_DIR / f"{CASE_ID}_page_map.json"

    # Register starts after index (page 8+)
    all_pages = sorted(list(PAGES_DIR.glob("page-*.jpg")) + list(PAGES_DIR.glob("page-*.png")))
    register_pages = [p for p in all_pages if int(re.search(r"(\d+)", p.stem).group()) >= 8]

    prompt = """\
This is a page from a 1902 Jewish family register (Посімейний список).
Each page contains 1-4 family entries. Each family has a sequential number
written in the left margin or top of the cell.

Extract ONLY the family numbers (sequential integers) visible on this page.
Return a JSON array of integers, e.g. [15, 16, 17].
If no family numbers are visible (blank page, cover, etc.), return [].
"""

    page_map = {}  # family_num -> page_filename
    resume_map = {}
    if map_file.exists():
        resume_map = json.loads(map_file.read_text())
        # Invert to see which pages are done
        done_pages = set(resume_map.values()) if isinstance(resume_map, dict) else set()
        page_map = resume_map if isinstance(resume_map, dict) else {}

    for page_path in register_pages:
        if page_path.name in set(page_map.values()):
            continue

        print(f"  {page_path.name} ...", end=" ", flush=True)
        try:
            from PIL import Image as PILImage
            import io as _io
            _img = PILImage.open(page_path)
            if max(_img.size) > 4000:
                _img.thumbnail((4000, 4000))
            _buf = _io.BytesIO()
            _img.save(_buf, format="JPEG", quality=90)
            _img_bytes = _buf.getvalue()

            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Content(parts=[
                        types.Part.from_bytes(data=_img_bytes, mime_type="image/jpeg"),
                        types.Part.from_text(text=prompt),
                    ])
                ],
                config=types.GenerateContentConfig(max_output_tokens=256),
            )
            text = (resp.text or "").strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            nums = json.loads(text)
            for n in nums:
                if isinstance(n, int) and str(n) not in page_map:
                    page_map[str(n)] = page_path.name
            print(f"families: {nums}")
        except Exception as e:
            print(f"ERROR: {e}")

        # Save incrementally
        map_file.write_text(json.dumps(page_map, ensure_ascii=False, indent=2))
        time.sleep(1)

    print(f"\nMapped {len(page_map)} families → {map_file}")


def step_finalize():
    """Generate final.jsonl + upload CSVs."""
    alphabet_file = BASE_DIR / f"{CASE_ID}_alphabet.jsonl"
    map_file = BASE_DIR / f"{CASE_ID}_page_map.json"

    if not alphabet_file.exists():
        print(f"ERROR: {alphabet_file} not found. Run --step extract first.")
        sys.exit(1)

    # Load alphabet
    entries = []
    with open(alphabet_file) as f:
        for line in f:
            r = json.loads(line)
            for entry in r.get("data", []):
                entry["_index_page"] = r["page"]
                entries.append(entry)

    print(f"Loaded {len(entries)} index entries")

    # Load page map
    page_map = {}
    if map_file.exists():
        page_map = json.loads(map_file.read_text())
        print(f"Loaded page map: {len(page_map)} families")
    else:
        print("WARNING: No page map found. Entries will link to index pages.")

    # Build final records
    final = []
    unmapped = 0
    for entry in entries:
        surname_raw = (entry.get("surname") or "").strip()
        given_raw = (entry.get("given_name") or "").strip()
        family_num = entry.get("family_num")

        if not surname_raw:
            continue

        surname = modernize_name(surname_raw)
        given = modernize_name(given_raw)
        final_name = f"{surname} {given}".strip() if given else surname

        # Determine which page to link to
        register_page = page_map.get(str(family_num)) if family_num else None
        if register_page:
            page = register_page
        else:
            page = entry["_index_page"]  # fallback to index page
            unmapped += 1

        final.append({
            "page": page,
            "family_num": family_num,
            "role": "head",
            "raw_name": f"{surname_raw} {given_raw}".strip(),
            "final_name": final_name,
            "surname": surname,
            "given": given,
            "key": f"{entry['_index_page']}:{family_num}:head",
        })

    print(f"Finalized: {len(final)} records ({unmapped} unmapped to register pages)")

    # Save final.jsonl
    final_path = BASE_DIR / f"{CASE_ID}_final.jsonl"
    with open(final_path, "w", encoding="utf-8") as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Saved {final_path}")

    # Generate CSVs
    pages_with_data = sorted(set(r["page"] for r in final))

    images_path = BASE_DIR / f"{CASE_ID}_images.csv"
    with open(images_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "image_key", "image_source_id", "image_path"])
        for page in pages_with_data:
            full_path = str((PAGES_DIR / page).resolve())
            w.writerow([full_path, IMAGE_KEY, IMAGE_SOURCE_ID, IMAGE_PATH])
    print(f"images.csv: {len(pages_with_data)} pages → {images_path}")

    objects_path = BASE_DIR / f"{CASE_ID}_objects.csv"
    count = 0
    with open(objects_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "text_content", "price"])
        for r in final:
            name = r["final_name"].strip()
            if not name:
                continue
            full_path = str((PAGES_DIR / r["page"]).resolve())
            w.writerow([full_path, name, 5000])
            count += 1
    print(f"objects.csv: {count} records → {objects_path}")


def main():
    parser = argparse.ArgumentParser(description="Process ДАКО 335-1-26 Shpykiv family register")
    parser.add_argument("--step", choices=["extract", "map", "finalize", "all"], default="all")
    args = parser.parse_args()

    if args.step in ("extract", "all"):
        print("=== Step 1: Extract alphabetical index ===")
        step_extract()

    if args.step in ("map", "all"):
        print("\n=== Step 2: Map family numbers to pages ===")
        step_map()

    if args.step in ("finalize", "all"):
        print("\n=== Step 3: Finalize ===")
        step_finalize()


if __name__ == "__main__":
    main()
