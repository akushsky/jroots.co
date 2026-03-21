#!/usr/bin/env python3
"""Run Gemini 3 Flash on all 184 Jewish cards for FIO extraction."""

import base64
import json
import os
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

SOURCE_DIR = Path("/Users/michaelak/Documents/Харьков 1926/582-1-1433")
JEWISH_LIST = Path(__file__).parent / "census_output" / "jewish_cards_list.json"
OUTPUT_FILE = Path(__file__).parent / "census_output" / "gemini3_readings.json"
EXTRACTED = Path(__file__).parent / "census_output" / "extracted_data.json"

MODEL = "gemini-3-flash-preview"

PROMPT = """This is a scanned front page of a 1926 Soviet census family card (Сімейна картка, Форма №2, Всесоюзний перепис населення 1926 р.).

Your task: extract the **Head of family full name** from field 3 "Прізвище, ім'я та по батькові" (Surname, first name and patronymic) of the head of family ("Голова сім'ї або одинець"). This is handwritten text after the printed label. Extract the full name in the format "Фамилия Имя Отчество".

Important notes:
- The text is handwritten in Ukrainian/Russian cursive from the 1920s
- These are Jewish families, so expect names like: Шехтман, Фурман, Кройтман, Лернер, Штейн, Новик, Аксман, Крель, etc.
- Patronymics often end in -ович/-евич/-ич
- Read carefully, letter by letter if needed
- If parts are illegible, write what you can read and mark uncertain parts

Return ONLY a JSON object (no markdown, no code fences):
{
  "name": "Фамилия Имя Отчество",
  "confidence": "high/medium/low",
  "notes": "any observations"
}"""


def load_image_b64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def call_gemini3(client: genai.Client, image_b64: str) -> dict:
    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Content(
                parts=[
                    types.Part.from_bytes(
                        data=base64.b64decode(image_b64),
                        mime_type="image/jpeg",
                    ),
                    types.Part.from_text(text=PROMPT),
                ]
            )
        ],
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"name": text, "confidence": "low", "notes": "JSON parse failed", "raw": text}


def main():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Set GOOGLE_API_KEY")
        return

    client = genai.Client(api_key=api_key)

    cards = json.loads(JEWISH_LIST.read_text())
    print(f"Total Jewish cards: {len(cards)}")

    # Load old gemini readings for comparison
    extracted = json.loads(EXTRACTED.read_text())
    old_names = {}
    for entry in extracted:
        if entry.get("is_jewish"):
            fn = entry.get("filename", "")
            old_names[fn] = entry.get("gemini_first", {}).get("name", "")

    results = {}
    if OUTPUT_FILE.exists():
        results = json.loads(OUTPUT_FILE.read_text())

    done = set(results.keys())
    remaining = [c for c in cards if c not in done]
    print(f"Already done: {len(done)}, remaining: {len(remaining)}")

    for i, fn in enumerate(remaining):
        img_path = SOURCE_DIR / fn
        if not img_path.exists():
            print(f"  [{i+1}/{len(remaining)}] SKIP {fn} (not found)")
            continue

        print(f"  [{len(done)+i+1}/{len(cards)}] {fn}...", end=" ", flush=True)
        b64 = load_image_b64(img_path)

        retries = 0
        while retries < 3:
            try:
                result = call_gemini3(client, b64)
                break
            except Exception as e:
                retries += 1
                print(f"retry {retries}: {e}", end=" ", flush=True)
                time.sleep(5 * retries)
        else:
            result = {"name": None, "confidence": "low", "notes": "Failed after 3 retries"}

        old_name = old_names.get(fn, "")
        new_name = result.get("name", "") or ""
        conf = result.get("confidence", "low")

        results[fn] = {
            "name_gemini3": new_name,
            "name_gemini2": old_name,
            "confidence": conf,
            "notes": result.get("notes", ""),
        }

        same = "SAME" if new_name == old_name else "DIFF"
        print(f"[{conf}] {same}  \"{new_name}\"  (old: \"{old_name}\")")

        # Save incrementally
        if (len(done) + i + 1) % 5 == 0 or i == len(remaining) - 1:
            OUTPUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2))

        time.sleep(0.5)

    # Final save
    OUTPUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2))

    # Stats
    total = len(results)
    high = sum(1 for r in results.values() if r["confidence"] == "high")
    med = sum(1 for r in results.values() if r["confidence"] == "medium")
    low = sum(1 for r in results.values() if r["confidence"] == "low")
    diff = sum(1 for r in results.values() if r["name_gemini3"] != r["name_gemini2"])

    print(f"\n{'='*60}")
    print(f"DONE: {total} cards processed")
    print(f"Confidence: {high} high, {med} medium, {low} low")
    print(f"Different from old Gemini 2.0: {diff}/{total}")
    print(f"Results saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
