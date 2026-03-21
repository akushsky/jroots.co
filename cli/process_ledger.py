"""
process_ledger.py — извлечение данных из ведомостей ДАЖО Ф.680 через Gemini.

Поддерживает 4 дела:
  680-1-4  — раскладка налога с евреев-ремесленников, 1909
  680-1-8  — раскладка налога с евреев-ремесленников, 1912
  680-1-9  — раскладка ремесленного налога с евреев, 1912
  680-1-11 — посемейная книга мещан-евреев, 1912

Использование:
  python cli/process_ledger.py --case 680-1-8
  python cli/process_ledger.py --case 680-1-11
  python cli/process_ledger.py --case all          # обработать все (full-page mode)
  python cli/process_ledger.py --case 680-1-4 --row-crops   # нарезка по строкам
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from google import genai
from google.genai import types

BASE_DIR = Path("cli/dazho_downloads")

# Промпт для ведомостей раскладки налога (680-1-4, 680-1-8, 680-1-9)
PROMPT_RAKLADKA = """
This is a page from a pre-revolutionary ledger of Jewish craftsmen/tradesmen in Berdychiv,
recording the apportionment of communal taxes (Раскладка суспільного податку з євреїв ремісників).
Year: {year}.

{last_surname_hint}

The table has columns (left to right):
1. Sequential number (№ по порядку)
2. Family list number (№ по посемейному списку) — appears only at the start of a family group
3. Surnames and given names (Фамилии и Имена) — head of family on first line,
   relatives below (usually marked with " or „ ditto marks meaning same surname)
4. Arrears (Недоимка) — Rubles / Kopecks
5. Assessment (Оклад) — Rubles / Kopecks
6. Total due (Всего) — Rubles / Kopecks
7. Place of residence (Место жительства) — often a city name
8. When paid / payment notes (Когда уплочено)
9. Amount collected (Сколько взыскано) — Rubles / Kopecks
10. Article number (№ статьи)

Instructions:
- Extract ONLY personal name rows. Do NOT include summary/total rows (Итого, Итог).
- For rows with ditto marks (", „, —//—), reconstruct the full surname from the nearest
  family group head ABOVE on this page. If the very first rows of this page use ditto marks
  and no new surname appears above them, use the LAST SURNAME FROM PREVIOUS PAGE provided above.
- Pay close attention to handwritten Jewish names (e.g. Шлема, Мойше, Янкель, Хаїм, Зельман,
  Юда-Лейб, Нухим, Пинхас, Гершко, Абрам, Ицко, Бейнеш, Нусим, Хана, Лейб, Гирш, Срул,
  Ицко, Берко, Вольф, Эля, Рувим, Аврум, Давид).
- Transcribe names carefully — do not "normalize" or guess; write what you see.
- Return ONLY a JSON array, no markdown, no explanations.
- If the page has no data table (cover page, blank), return [].

JSON fields per row: seq_num, family_num, name, arrears_rub, arrears_kop,
  assessment_rub, assessment_kop, total_rub, total_kop, residence,
  payment_note, collected_rub, collected_kop, article_num
"""

# Промпт для посемейной книги (680-1-11)
PROMPT_POSEMEINAYA = """
This is a page from a 1912 communal tax ledger of Jewish townspeople (мещане) in Berdychiv:
"Податний зошит сплати суспільних зборів з Бердичівських міщан євреїв (посімейні списки)".

The page is a two-column spread. Each column has ~4 family cells.
Each cell contains:
- Family sequential number (top-left corner of cell)
- Head of household name + patronymic (Имя, отчество и фамилия хозяина)
- Names of adult male family members (неотдельных членов его семьи мужского пола 18+),
  each with their tax assessment (Оклад)
- Arrears (Недоимка прошлых лет) and current assessment (Оклад 1 г.)
- Payment columns (В счет недоимки / В счет оклада до 1910 года)

Instructions:
- Extract ALL family entries from both columns of the spread.
- For each family, capture the head's full name + all listed male members with their assessment.
- Family members may be listed as: "братъ", "сынъ", "племянникъ" etc. — include those labels.
- Assessments in Rubles and Kopecks columns.
- Return ONLY a JSON array, no markdown.
- If page is blank or a cover page, return [].

JSON fields per family entry:
  family_num (int), head_name (string),
  members: [{{name, relationship, assessment_rub, assessment_kop}}],
  arrears_rub, arrears_kop, assessment_rub, assessment_kop,
  paid_nedoimka_rub, paid_nedoimka_kop, paid_oklad_rub, paid_oklad_kop
"""

CASES = {
    "680-1-4": {
        "prompt_template": PROMPT_RAKLADKA,
        "prompt_kwargs": {"year": "1909"},
        "desc": "Раскладка суспільного податку з євреїв ремісників, 1909",
    },
    "680-1-8": {
        "prompt_template": PROMPT_RAKLADKA,
        "prompt_kwargs": {"year": "1912"},
        "desc": "Раскладка суспільного податку з євреїв ремісників, 1912",
    },
    "680-1-9": {
        "prompt_template": PROMPT_RAKLADKA,
        "prompt_kwargs": {"year": "1912"},
        "desc": "Раскладка ремісничого податку з євреїв ремісників, 1912",
    },
    "680-1-11": {
        "prompt_template": PROMPT_POSEMEINAYA,
        "prompt_kwargs": {},
        "desc": "Посімейна книга мещан-євреїв Бердичева, 1912",
    },
}


def extract_last_surname(rows: list) -> str | None:
    """Return the last non-empty surname seen in a list of extracted rows."""
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        name = row.get("name", "") or ""
        # Skip summary rows
        if "итог" in name.lower():
            continue
        parts = name.strip().split()
        if parts:
            return parts[0]
    return None


def process_case(client, case_id: str, resume: bool = True):
    cfg = CASES[case_id]
    pages_dir = BASE_DIR / f"{case_id}_pages"
    output_file = BASE_DIR / f"{case_id}_extracted.jsonl"

    if not pages_dir.exists():
        print(f"ERROR: pages dir not found: {pages_dir}")
        print(f"Run: pdftoppm -r 150 -png cli/dazho_downloads/{case_id}.pdf {pages_dir}/page")
        return

    images = sorted(pages_dir.glob("*.png"))
    if not images:
        print(f"No PNG images in {pages_dir}")
        return

    # Find already-processed images for resume; also recover last_surname from last done page
    done = {}  # image_name -> data (list of rows)
    last_surname = None
    if resume and output_file.exists():
        with open(output_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        obj = json.loads(line)
                        img = obj.get("image", "")
                        data = obj.get("data") or []
                        done[img] = data
                    except Exception:
                        pass
        # Recover last_surname from the last processed page that had data
        for img_path in images:
            if img_path.name in done:
                surname = extract_last_surname(done[img_path.name])
                if surname:
                    last_surname = surname
        print(f"Resuming {case_id}: {len(done)} pages already done, "
              f"{len(images) - len(done)} remaining. Last surname: {last_surname!r}")
    else:
        print(f"Starting fresh for {case_id}: {len(images)} pages.")

    is_rakladka = cfg["prompt_template"] is PROMPT_RAKLADKA

    processed = 0
    with open(output_file, "a", encoding="utf-8") as out:
        for img_path in images:
            if img_path.name in done:
                continue

            # Build prompt with last_surname hint for rakladka pages
            if is_rakladka:
                if last_surname:
                    hint = (f"IMPORTANT: The last surname on the PREVIOUS page was «{last_surname}». "
                            f"If the first rows of this page use ditto marks (\" or „) without "
                            f"a new surname above them, their surname is «{last_surname}».")
                else:
                    hint = "This is the first page — no previous surname context."
                prompt = cfg["prompt_template"].format(last_surname_hint=hint, **cfg["prompt_kwargs"])
            else:
                prompt = cfg["prompt_template"].format(**cfg["prompt_kwargs"])

            print(f"  [{case_id}] {img_path.name} (last_surname={last_surname!r}) ...", end=" ", flush=True)
            try:
                resp = client.models.generate_content(
                    model="gemini-3.1-pro-preview",
                    contents=[
                        types.Content(parts=[
                            types.Part.from_bytes(data=img_path.read_bytes(), mime_type="image/png"),
                            types.Part.from_text(text=prompt),
                        ])
                    ],
                    config=types.GenerateContentConfig(max_output_tokens=8192),
                )

                text = (resp.text or "").strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

                data = json.loads(text)

                # Update last_surname for next page
                surname = extract_last_surname(data)
                if surname:
                    last_surname = surname

                record = {"image": img_path.name, "last_surname_hint": last_surname, "data": data}
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                print(f"{len(data)} rows → last surname: {last_surname!r}")
                processed += 1
            except Exception as e:
                print(f"ERROR: {e}")
                record = {"image": img_path.name, "data": None, "error": str(e)}
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()

            time.sleep(3)

    print(f"Done {case_id}: processed {processed} new pages → {output_file}")


# ── Row-crop mode ──────────────────────────────────────────────────────────────

PROMPT_ROW_SINGLE = """\
This is a single row strip from a pre-revolutionary handwritten tax ledger
(Jewish craftsmen register, Berdychiv, ~{year}).

The row has columns: [seq#] [family#] [Surname Givenname] [rubles] [kop] [rubles] [kop] ...

{surname_hint}

{known_surnames_hint}

Your task: read ONLY the name in the 3rd column (Surname + Given name).
- Transcribe exactly what you see. Do NOT normalize or modernize spelling.
- If you see a ditto mark (" or „) instead of a surname, use the hint above.
- Pre-revolutionary Russian: ъ at end of words, ять (ѣ written as е), і instead of и.
- Common Jewish given names: Шлема, Мойше, Янкель, Хаім, Зельман, Юда-Лейб, Нухим,
  Пинхас, Гершко, Абрам, Ицко, Берко, Лейб, Гирш, Срул, Вольф, Эля, Рафуль, Аврум.
- Common surname endings: -скій/-цкій/-бергъ/-штейнъ/-манъ/-овичъ/-ерь/-инъ.

Return ONLY valid JSON (no markdown):
{{"seq_num": <int or null>, "name": "<Surname Givenname>"}}
"""


def _call_gemini_row(client, row_path: Path, prompt: str) -> dict:
    from google.genai import types
    resp = client.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents=[
            types.Content(parts=[
                types.Part.from_bytes(data=row_path.read_bytes(), mime_type="image/png"),
                types.Part.from_text(text=prompt),
            ])
        ],
        config=types.GenerateContentConfig(max_output_tokens=8192),
    )
    text = (resp.text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def _call_gpt4o_row(client, row_path: Path, prompt: str) -> dict:
    import base64
    b64 = base64.b64encode(row_path.read_bytes()).decode()
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}},
                {"type": "text", "text": prompt},
            ]
        }],
        max_tokens=256,
    )
    text = resp.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def _update_surname_dict(surname_dict: dict, name: str, weight: int = 1):
    """Add surname from name string to running frequency dict."""
    if not name:
        return
    parts = name.strip().split()
    if not parts:
        return
    surname = parts[0]
    # Skip ditto marks and very short tokens
    if len(surname) <= 1 or surname in {'"', '„', '"', '"', '»', '«'}:
        return
    surname_dict[surname] = surname_dict.get(surname, 0) + weight


def process_case_row_mode(gemini_client, openai_client, case_id: str, resume: bool = True):
    """
    Row-crop mode: посылает каждый стрип строки отдельно двум моделям.
    Выходной файл: {case_id}_rowmode.jsonl
    Каждая запись: {image, row_strip, seq_num, gemini, gpt4o, final, consensus}
    """
    cfg = CASES[case_id]
    rows_dir   = BASE_DIR / f"{case_id}_rows"
    manifest_f = BASE_DIR / f"{case_id}_rows_manifest.json"
    output_file = BASE_DIR / f"{case_id}_rowmode.jsonl"
    surname_dict_file = BASE_DIR / f"{case_id}_surname_dict.json"

    if not rows_dir.exists() or not manifest_f.exists():
        print(f"ERROR: rows not found. Run: python cli/detect_rows.py --case {case_id}")
        return

    manifest = json.loads(manifest_f.read_text())

    # Load surname dict
    surname_dict: dict = {}
    if surname_dict_file.exists():
        surname_dict = json.loads(surname_dict_file.read_text())

    # Find already-done strips
    done_strips: set = set()
    last_surname: str | None = None
    if resume and output_file.exists():
        with open(output_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    done_strips.add(obj.get("row_strip", ""))
                    if obj.get("final"):
                        parts = obj["final"].strip().split()
                        if parts and len(parts[0]) > 1:
                            last_surname = parts[0]
                except Exception:
                    pass
        print(f"Resuming: {len(done_strips)} strips done. last_surname={last_surname!r}")
    else:
        if output_file.exists():
            output_file.unlink()
        print(f"Fresh start.")

    year = cfg["prompt_kwargs"].get("year", "1909")
    total_processed = 0

    with open(output_file, "a", encoding="utf-8") as out:
        for page_name, strip_paths in sorted(manifest.items()):
            for strip_path_str in strip_paths:
                strip_path = Path(strip_path_str)
                strip_name = strip_path.name

                if strip_name in done_strips:
                    continue

                # Build hints
                if last_surname:
                    surname_hint = (
                        f"IMPORTANT: The previous row's surname was «{last_surname}». "
                        f"If this row starts with a ditto mark (\" or „), the surname is «{last_surname}»."
                    )
                else:
                    surname_hint = "No previous surname context (first data row)."

                top_surnames = sorted(surname_dict, key=surname_dict.get, reverse=True)[:25]
                if top_surnames:
                    known_surnames_hint = (
                        f"Known surnames seen so far in this document "
                        f"(use as reference, not as constraint): {', '.join(top_surnames)}"
                    )
                else:
                    known_surnames_hint = ""

                prompt = PROMPT_ROW_SINGLE.format(
                    year=year,
                    surname_hint=surname_hint,
                    known_surnames_hint=known_surnames_hint,
                )

                print(f"  {strip_name} ...", end=" ", flush=True)

                gemini_result = None
                gpt4o_result = None

                try:
                    gemini_result = _call_gemini_row(gemini_client, strip_path, prompt)
                except Exception as e:
                    gemini_result = {"seq_num": None, "name": f"ERROR:{e}"}

                time.sleep(1)

                if openai_client:
                    try:
                        gpt4o_result = _call_gpt4o_row(openai_client, strip_path, prompt)
                    except Exception as e:
                        gpt4o_result = {"seq_num": None, "name": f"ERROR:{e}"}
                    time.sleep(1)

                # Determine final name + consensus
                g_name = (gemini_result or {}).get("name", "") or ""
                o_name = (gpt4o_result or {}).get("name", "") or ""
                seq_num = (gemini_result or {}).get("seq_num") or (gpt4o_result or {}).get("seq_num")

                # Skip header/footer rows (no seq_num from either model)
                if seq_num is None and not g_name and not o_name:
                    print("(skip — no seq_num)")
                    record = {"page": page_name, "row_strip": strip_name, "skipped": True}
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out.flush()
                    continue

                consensus = (g_name == o_name) and bool(g_name)
                if consensus:
                    final = g_name
                    _update_surname_dict(surname_dict, final, weight=2)
                elif g_name and not o_name:
                    final = g_name
                    _update_surname_dict(surname_dict, final, weight=1)
                elif o_name and not g_name:
                    final = o_name
                    _update_surname_dict(surname_dict, final, weight=1)
                else:
                    # Both have names but disagree — take Gemini, flag for human
                    final = g_name
                    _update_surname_dict(surname_dict, g_name, weight=1)
                    _update_surname_dict(surname_dict, o_name, weight=1)

                # Update last surname
                if final:
                    parts = final.strip().split()
                    if parts and len(parts[0]) > 1 and parts[0] not in {'"', '„'}:
                        last_surname = parts[0]

                status = "✓" if consensus else "≠"
                print(f"{status} G={g_name!r} O={o_name!r} → {final!r}")

                record = {
                    "page": page_name,
                    "row_strip": strip_name,
                    "seq_num": seq_num,
                    "gemini": g_name,
                    "gpt4o": o_name,
                    "final": final,
                    "consensus": consensus,
                    "needs_human": not consensus and bool(g_name) and bool(o_name),
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                total_processed += 1

    # Save updated surname dict
    surname_dict_file.write_text(json.dumps(
        dict(sorted(surname_dict.items(), key=lambda x: x[1], reverse=True)),
        ensure_ascii=False, indent=2
    ))
    print(f"\nDone: {total_processed} strips. Surname dict: {len(surname_dict)} entries → {surname_dict_file}")


def fill_missing_gpt4o(openai_client, case_id: str):
    """
    Fill in gpt4o field for any rows in _rowmode.jsonl where gpt4o is empty.
    Reads the file, re-calls GPT-4o for missing rows, rewrites in place.
    """
    rows_dir     = BASE_DIR / f"{case_id}_rows"
    output_file  = BASE_DIR / f"{case_id}_rowmode.jsonl"
    surname_dict_file = BASE_DIR / f"{case_id}_surname_dict.json"

    if not output_file.exists():
        print(f"ERROR: {output_file} not found.")
        return

    records = []
    with open(output_file) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

    surname_dict: dict = {}
    if surname_dict_file.exists():
        surname_dict = json.loads(surname_dict_file.read_text())

    to_fill = [r for r in records if not r.get("skipped") and r.get("gpt4o", "") == ""]
    print(f"Records to fill with GPT-4o: {len(to_fill)} / {len(records)}")

    cfg = CASES[case_id]
    year = cfg["prompt_kwargs"].get("year", "1909")

    updated = 0
    # Build a lookup: strip_name → record index
    index = {r.get("row_strip", ""): i for i, r in enumerate(records)}

    for rec in to_fill:
        strip_name = rec.get("row_strip", "")
        strip_path = rows_dir / strip_name
        if not strip_path.exists():
            print(f"  {strip_name}: strip file not found, skipping")
            continue

        # Build context from surrounding records
        idx = index.get(strip_name)
        last_surname = None
        if idx and idx > 0:
            for prev in reversed(records[:idx]):
                if prev.get("final"):
                    parts = prev["final"].strip().split()
                    if parts and len(parts[0]) > 1:
                        last_surname = parts[0]
                        break

        if last_surname:
            surname_hint = (
                f"IMPORTANT: The previous row's surname was «{last_surname}». "
                f"If this row starts with a ditto mark (\" or „), the surname is «{last_surname}»."
            )
        else:
            surname_hint = "No previous surname context."

        top_surnames = sorted(surname_dict, key=surname_dict.get, reverse=True)[:25]
        known_surnames_hint = (
            f"Known surnames seen so far: {', '.join(top_surnames)}" if top_surnames else ""
        )

        prompt = PROMPT_ROW_SINGLE.format(
            year=year,
            surname_hint=surname_hint,
            known_surnames_hint=known_surnames_hint,
        )

        print(f"  {strip_name} ...", end=" ", flush=True)
        try:
            gpt4o_result = _call_gpt4o_row(openai_client, strip_path, prompt)
            o_name = (gpt4o_result or {}).get("name", "") or ""
        except Exception as e:
            print(f"ERROR: {e}")
            o_name = ""

        g_name = rec.get("gemini", "") or ""
        consensus = bool(g_name) and (g_name == o_name)
        needs_human = bool(g_name) and bool(o_name) and not consensus

        if consensus:
            final = g_name
            _update_surname_dict(surname_dict, final, weight=2)
        elif o_name and not g_name:
            final = o_name
        elif g_name:
            final = g_name
        else:
            final = ""

        rec["gpt4o"] = o_name
        rec["final"] = final
        rec["consensus"] = consensus
        rec["needs_human"] = needs_human

        status = "✓" if consensus else "≠"
        print(f"{status} G={g_name!r} O={o_name!r} → {final!r}")
        updated += 1
        time.sleep(1)

    # Rewrite the file
    with open(output_file, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    surname_dict_file.write_text(json.dumps(
        dict(sorted(surname_dict.items(), key=lambda x: x[1], reverse=True)),
        ensure_ascii=False, indent=2
    ))
    print(f"\nDone: filled {updated} GPT-4o values. File rewritten.")


def main():
    parser = argparse.ArgumentParser(description="Extract data from DAZHO fund 680 ledgers via Gemini.")
    parser.add_argument("--case", default="all",
                        help="Case ID to process: 680-1-4, 680-1-8, 680-1-9, 680-1-11, or 'all'")
    parser.add_argument("--no-resume", action="store_true",
                        help="Do not skip already-processed pages (start fresh)")
    parser.add_argument("--row-crops", action="store_true",
                        help="Use row-crop mode: send individual row strips instead of full pages")
    parser.add_argument("--fill-missing", action="store_true",
                        help="Fill in gpt4o values for rows where it is empty (patch existing _rowmode.jsonl)")
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set.")
        sys.exit(1)

    gemini_client = genai.Client(api_key=api_key)

    openai_client = None
    if args.row_crops or args.fill_missing:
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            from openai import OpenAI
            openai_client = OpenAI(api_key=openai_key)
            print("OpenAI client ready.")
        elif args.row_crops:
            print("WARNING: OPENAI_API_KEY not set — running single-model row mode (Gemini only)")

    cases_to_run = list(CASES.keys()) if args.case == "all" else [args.case]
    for case_id in cases_to_run:
        if case_id not in CASES:
            print(f"Unknown case: {case_id}. Choose from: {list(CASES.keys())}")
            continue
        print(f"\n=== {case_id}: {CASES[case_id]['desc']} ===")
        if args.fill_missing:
            if not openai_client:
                print("ERROR: OPENAI_API_KEY required for --fill-missing")
                continue
            fill_missing_gpt4o(openai_client, case_id)
        elif args.row_crops:
            process_case_row_mode(gemini_client, openai_client, case_id, resume=not args.no_resume)
        else:
            process_case(gemini_client, case_id, resume=not args.no_resume)


if __name__ == "__main__":
    main()
