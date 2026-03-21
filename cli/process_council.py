"""
process_council.py — Multi-LLM council OCR для ведомостей ДАЖО Ф.680.

Три модели независимо транскрибируют каждую страницу (Раунд 1).
По спорным строкам проводятся дебаты: каждая модель видит чужие прочтения
и объясняет своё (Раунд 2). Итог — голосование большинством.

Модели:
  - Gemini 2.5 Pro   (GOOGLE_API_KEY)
  - GPT-4o           (OPENAI_API_KEY)
  - Claude 3.5 Sonnet (ANTHROPIC_API_KEY, опционально)

Использование:
  python cli/process_council.py --case 680-1-4
  python cli/process_council.py --case 680-1-4 --no-resume
  python cli/process_council.py --case 680-1-4 --pages-only 3,4,5
"""

import os
import sys
import json
import time
import base64
import argparse
from pathlib import Path
from collections import Counter

# ── API clients ──────────────────────────────────────────────────────────────

def make_clients():
    clients = {}

    google_key = os.environ.get("GOOGLE_API_KEY")
    if google_key:
        from google import genai
        clients["gemini"] = genai.Client(api_key=google_key)
    else:
        print("WARNING: GOOGLE_API_KEY not set — Gemini disabled")

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        from openai import OpenAI
        clients["gpt4o"] = OpenAI(api_key=openai_key)
    else:
        print("WARNING: OPENAI_API_KEY not set — GPT-4o disabled")

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        import anthropic
        clients["claude"] = anthropic.Anthropic(api_key=anthropic_key)
    else:
        print("INFO: ANTHROPIC_API_KEY not set — Claude disabled (2-model council)")

    if len(clients) < 2:
        print("ERROR: Need at least 2 API keys to form a council.")
        sys.exit(1)

    return clients


# ── Prompts ───────────────────────────────────────────────────────────────────

PROMPT_ROUND1 = """\
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

Rules:
- Extract ONLY personal name rows. Skip summary rows (Итого, Итог).
- For ditto marks (", „, —//—) at the start of a page with no preceding surname,
  use the LAST SURNAME FROM PREVIOUS PAGE provided in the hint above.
- Transcribe names exactly as written. Do NOT normalise or guess.
  Common Jewish names: Шлема, Мойше, Янкель, Хаїм, Зельман, Юда-Лейб, Нухим,
  Пинхас, Гершко, Абрам, Ицко, Бейнеш, Нусим, Хана, Лейб, Гирш, Срул, Берко,
  Вольф, Эля, Рувим, Аврум, Давид, Рафуль, Фаліть, Нахман, Ізраіль.
- Common surname patterns: ending in -скій/-цкій/-бергъ/-штейнъ/-манъ/-овичъ.
- Return ONLY a JSON array, no markdown, no explanations.
- If page has no data table (cover, blank), return [].

JSON fields per row:
  seq_num (int), family_num (int|null), name (string),
  arrears_rub (num|null), arrears_kop (num|null),
  assessment_rub (num|null), assessment_kop (num|null),
  total_rub (num|null), total_kop (num|null),
  residence (string|null), payment_note (string|null),
  collected_rub (num|null), collected_kop (num|null), article_num (num|null)
"""

PROMPT_DEBATE = """\
You are reviewing a transcription of a pre-revolutionary handwritten Russian ledger
(Jewish craftsmen tax register, Berdychiv, ~1909-1912).

The image shows the original page. On row #{seq} the models disagreed:
{disagreements}

Please look very carefully at row #{seq} in the image.
Examine each letter individually. Consider:
- Pre-revolutionary Russian orthography (ъ, ять, і)
- Cursive letter shapes: Л vs Д, ф vs д, н vs и, п vs н, е vs с
- Jewish given names of the era (Рафуль, Файвуль, Нохем, Гершко, Ицко, Менаше...)
- Jewish surnames often derived from place names, occupations, or patronymics

Return ONLY valid JSON (no markdown):
{{"name": "Фамилия Имя", "reasoning": "brief explanation of each letter"}}
"""

# ── Model call wrappers ───────────────────────────────────────────────────────

def img_to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def call_gemini(client, img_path: Path, prompt: str) -> str:
    from google.genai import types
    resp = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=[
            types.Content(parts=[
                types.Part.from_bytes(data=img_path.read_bytes(), mime_type="image/png"),
                types.Part.from_text(text=prompt),
            ])
        ],
    )
    return resp.text.strip()


def call_gpt4o(client, img_path: Path, prompt: str) -> str:
    b64 = img_to_b64(img_path)
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
        max_tokens=4096,
    )
    return resp.choices[0].message.content.strip()


def call_claude(client, img_path: Path, prompt: str) -> str:
    b64 = img_to_b64(img_path)
    resp = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": prompt},
            ]
        }],
    )
    return resp.content[0].text.strip()


def call_model(name: str, client, img_path: Path, prompt: str) -> str:
    if name == "gemini":
        return call_gemini(client, img_path, prompt)
    elif name == "gpt4o":
        return call_gpt4o(client, img_path, prompt)
    elif name == "claude":
        return call_claude(client, img_path, prompt)
    raise ValueError(f"Unknown model: {name}")


def parse_json_response(text: str):
    """Strip markdown fences and parse JSON."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(t)


# ── Comparison & voting ───────────────────────────────────────────────────────

def names_agree(names: list[str]) -> bool:
    """True if at least 2 out of N names are identical."""
    if len(names) < 2:
        return True
    c = Counter(names)
    return c.most_common(1)[0][1] >= 2


def majority_name(names: list[str]) -> tuple[str, bool]:
    """Return (winning_name, is_majority). If all different, first name wins with flag."""
    c = Counter(n for n in names if n)
    if not c:
        return ("", False)
    top_name, top_count = c.most_common(1)[0]
    is_majority = top_count >= 2
    return (top_name, is_majority)


DITTO_CHARS = {'"', '„', '"', '»', '«', '–', '—', '"', "'", "//"}

def extract_last_surname(rows: list) -> str | None:
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        name = (row.get("name") or "").strip()
        if not name:
            continue
        if "итог" in name.lower():
            continue
        parts = name.split()
        if not parts:
            continue
        first = parts[0]
        # Skip ditto marks and short non-surname tokens
        if first in DITTO_CHARS or first.strip('"„"\'') == "" or len(first) <= 1:
            continue
        return first
    return None


# ── Core per-page processing ──────────────────────────────────────────────────

MODEL_LABELS = {"gemini": "Gemini 2.5 Pro", "gpt4o": "GPT-4o", "claude": "Claude 3.5"}


def process_page(clients: dict, img_path: Path, prompt_r1: str, verbose: bool = True) -> dict:
    """
    Run council on a single page. Returns:
    {
      "image": filename,
      "data": [final rows with debate metadata],
      "round1": {model: [rows]},
      "last_surname": str|None,
    }
    """
    model_names = list(clients.keys())

    # ── Round 1: independent transcription ──────────────────────────────────
    r1_results = {}
    for mname, mclient in clients.items():
        if verbose:
            print(f"    [{MODEL_LABELS[mname]}] R1 ...", end=" ", flush=True)
        try:
            raw = call_model(mname, mclient, img_path, prompt_r1)
            rows = parse_json_response(raw)
            if not isinstance(rows, list):
                rows = []
            r1_results[mname] = rows
            if verbose:
                print(f"{len(rows)} rows")
        except Exception as e:
            if verbose:
                print(f"ERROR: {e}")
            r1_results[mname] = []
        time.sleep(2)

    # ── Find max seq range across all models ────────────────────────────────
    all_seqs = set()
    for rows in r1_results.values():
        for r in rows:
            if isinstance(r, dict) and r.get("seq_num"):
                all_seqs.add(r["seq_num"])

    # ── Build per-seq comparison ─────────────────────────────────────────────
    r1_by_seq = {}   # seq -> {model: row}
    for mname, rows in r1_results.items():
        for r in rows:
            if not isinstance(r, dict):
                continue
            seq = r.get("seq_num")
            if seq is None:
                continue
            if seq not in r1_by_seq:
                r1_by_seq[seq] = {}
            r1_by_seq[seq][mname] = r

    # ── Identify contested rows ───────────────────────────────────────────────
    contested_seqs = []
    for seq, model_rows in r1_by_seq.items():
        names = [mr.get("name", "") for mr in model_rows.values()]
        if len(names) >= 2 and not names_agree(names):
            contested_seqs.append(seq)

    # ── Round 2: debate on contested rows ────────────────────────────────────
    r2_results = {}  # seq -> {model: {name, reasoning}}

    if contested_seqs and verbose:
        print(f"    Debating {len(contested_seqs)} contested rows: {contested_seqs}")

    for seq in contested_seqs:
        model_rows = r1_by_seq.get(seq, {})
        disagreements_text = "\n".join(
            f"  {MODEL_LABELS.get(mn, mn)}: «{mr.get('name', '(empty)')}»"
            for mn, mr in model_rows.items()
        )
        debate_prompt = PROMPT_DEBATE.format(seq=seq, disagreements=disagreements_text)

        r2_results[seq] = {}
        for mname, mclient in clients.items():
            if verbose:
                print(f"    [{MODEL_LABELS[mname]}] R2 seq={seq} ...", end=" ", flush=True)
            try:
                raw = call_model(mname, mclient, img_path, debate_prompt)
                result = parse_json_response(raw)
                if isinstance(result, dict) and "name" in result:
                    r2_results[seq][mname] = result
                    if verbose:
                        print(f"«{result['name']}»")
                else:
                    r2_results[seq][mname] = {"name": model_rows.get(mname, {}).get("name", ""), "reasoning": "parse error"}
                    if verbose:
                        print("parse error, keeping R1")
            except Exception as e:
                if verbose:
                    print(f"ERROR: {e}")
                r2_results[seq][mname] = {"name": model_rows.get(mname, {}).get("name", ""), "reasoning": str(e)}
            time.sleep(2)

    # ── Build final rows ──────────────────────────────────────────────────────
    final_rows = []
    for seq in sorted(r1_by_seq.keys()):
        model_rows = r1_by_seq[seq]

        # Use the most complete row as base (prefer gemini for non-name fields)
        base_row = {}
        for preferred in ("gemini", "gpt4o", "claude"):
            if preferred in model_rows:
                base_row = dict(model_rows[preferred])
                break
        if not base_row and model_rows:
            base_row = dict(next(iter(model_rows.values())))

        if seq in contested_seqs:
            # Use Round 2 results for name
            r2 = r2_results.get(seq, {})
            r2_names = [v.get("name", "") for v in r2.values()]
            final_name, is_majority = majority_name(r2_names)
            needs_human = not is_majority

            debate_log = {}
            # Include both R1 and R2 positions
            for mname in clients:
                r1_name = model_rows.get(mname, {}).get("name", "(no data)")
                r2_entry = r2.get(mname, {})
                debate_log[MODEL_LABELS.get(mname, mname)] = {
                    "round1": r1_name,
                    "round2": r2_entry.get("name", r1_name),
                    "reasoning": r2_entry.get("reasoning", ""),
                }
        else:
            # Consensus in Round 1
            names = [mr.get("name", "") for mr in model_rows.values()]
            final_name, is_majority = majority_name(names)
            needs_human = False
            debate_log = {}

        base_row["name"] = final_name
        base_row["_contested"] = seq in contested_seqs
        base_row["_needs_human"] = needs_human
        base_row["_debate"] = debate_log
        base_row["_r1"] = {
            MODEL_LABELS.get(mn, mn): mr.get("name", "")
            for mn, mr in model_rows.items()
        }
        final_rows.append(base_row)

    last_surname = extract_last_surname(final_rows)

    return {
        "image": img_path.name,
        "data": final_rows,
        "round1": {mn: rows for mn, rows in r1_results.items()},
        "last_surname": last_surname,
    }


# ── Case config ───────────────────────────────────────────────────────────────

BASE_DIR = Path("cli/dazho_downloads")

CASES = {
    "680-1-4":  {"year": "1909", "desc": "Раскладка суспільного податку, 1909"},
    "680-1-8":  {"year": "1912", "desc": "Раскладка суспільного податку, 1912"},
    "680-1-9":  {"year": "1912", "desc": "Раскладка ремісничого податку, 1912"},
}

SKIP_IMAGES = {"page_001.png", "page_002.png"}  # covers / index pages


def process_case(clients: dict, case_id: str, resume: bool = True, pages_filter: set = None):
    cfg = CASES[case_id]
    pages_dir = BASE_DIR / f"{case_id}_pages"
    output_file = BASE_DIR / f"{case_id}_council.jsonl"

    if not pages_dir.exists():
        print(f"ERROR: pages dir not found: {pages_dir}")
        return

    images = sorted(p for p in pages_dir.glob("*.png") if p.name not in SKIP_IMAGES)
    if pages_filter:
        images = [p for p in images if p.stem.split("_")[-1].lstrip("0") in pages_filter
                  or p.stem.split("_")[-1] in pages_filter]

    if not images:
        print("No images to process.")
        return

    # Resume: find already-done pages and last surname
    done = {}
    last_surname = None
    if resume and output_file.exists():
        with open(output_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    img = obj.get("image", "")
                    done[img] = obj
                except Exception:
                    pass
        # Recover last surname from last done page in image order
        for img_path in images:
            if img_path.name in done:
                ls = done[img_path.name].get("last_surname")
                if ls:
                    last_surname = ls
        print(f"Resuming: {len(done)} done, {len(images)-len(done)} remaining. "
              f"Last surname: {last_surname!r}")
    else:
        if output_file.exists():
            output_file.unlink()
        print(f"Fresh start: {len(images)} pages.")

    processed = 0
    with open(output_file, "a", encoding="utf-8") as out:
        for img_path in images:
            if img_path.name in done:
                continue

            print(f"\n  [{case_id}] {img_path.name}  (last_surname={last_surname!r})")

            if last_surname:
                hint = (f"IMPORTANT: The last surname on the PREVIOUS page was «{last_surname}». "
                        f"If the first rows of this page use ditto marks without a new surname "
                        f"above them, their surname is «{last_surname}».")
            else:
                hint = "This is the first data page — no previous surname context."

            prompt = PROMPT_ROUND1.format(year=cfg["year"], last_surname_hint=hint)

            result = process_page(clients, img_path, prompt, verbose=True)
            result["image"] = img_path.name

            last_surname = result.get("last_surname") or last_surname

            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            out.flush()
            processed += 1
            print(f"  → {len(result['data'])} rows, last_surname={last_surname!r}")

    print(f"\nDone {case_id}: {processed} new pages → {output_file}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="680-1-4",
                        choices=list(CASES.keys()),
                        help="Case ID to process")
    parser.add_argument("--no-resume", action="store_true",
                        help="Start fresh, ignore previous results")
    parser.add_argument("--pages-only", default="",
                        help="Comma-separated page numbers to process, e.g. 3,4,5")
    args = parser.parse_args()

    clients = make_clients()
    print(f"Council members: {[MODEL_LABELS[m] for m in clients]}")

    pages_filter = None
    if args.pages_only:
        pages_filter = set(args.pages_only.split(","))

    print(f"\n=== {args.case}: {CASES[args.case]['desc']} ===")
    process_case(clients, args.case, resume=not args.no_resume, pages_filter=pages_filter)


if __name__ == "__main__":
    main()
