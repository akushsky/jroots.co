"""
benchmark_qwen.py — Test Qwen VL Plus on DAZHO ledger row strips.

Sends a sample of row strips to Qwen VL Plus via DashScope's OpenAI-compatible API
and compares against existing Gemini, GPT-4o, and Claude/correction readings.

Usage:
  export DASHSCOPE_API_KEY=sk-...
  python cli/benchmark_qwen.py --case 680-1-4 --sample 30
  python cli/benchmark_qwen.py --case 680-1-4 --all
  python cli/benchmark_qwen.py --case 680-1-4 --sample 30 --model qwen3-vl-plus
"""

import os
import sys
import json
import time
import base64
import argparse
from pathlib import Path
from openai import OpenAI

BASE_DIR = Path("cli/dazho_downloads")

SYSTEM_MSG = """\
Ты — эксперт-палеограф, специализирующийся на чтении рукописных документов \
Российской империи XIX — начала XX века. Ты свободно читаешь дореволюционный \
русский и украинский рукописный текст, включая еврейские имена и фамилии."""

PROMPT = """\
Перед тобой одна строка из рукописной ведомости «Раскладка суспільного податку \
з євреїв ремісників м. Бердичева» (~1909 г.).

Документ написан на смеси дореволюционного русского и украинского языков. \
Орфография дореволюционная: ъ на конце слов, ять (ѣ), і вместо и, ій вместо ый.

Строка имеет колонки слева направо:
1. № по порядку (число)
2. № по посемейному списку (может быть пусто)
3. Фамилия и Имя (рукописный текст)
4-10. Суммы в рублях и копейках, место жительства и т.д.

{surname_hint}

Твоя задача: прочитать ТОЛЬКО имя в 3-й колонке (Фамилия + Имя).

Правила:
- Транскрибируй ТОЧНО то, что видишь в рукописи. НЕ модернизируй написание.
- Если вместо фамилии стоит знак повтора (" или „ или —), подставь фамилию из подсказки.
- Типичные еврейские имена в этом документе: Шлема, Мойше, Янкель, Хаімъ, \
Зельманъ, Юда-Лейбъ, Нухімъ, Пінхасъ, Гершко, Абрамъ, Ицко, Берко, Лейбъ, \
Гіршъ, Сруль, Вольфъ, Эля, Рафуль, Аврумъ, Мееръ, Давидъ, Перецъ, Нисанель.
- Типичные окончания фамилий: -скій, -цкій, -бергъ, -штейнъ, -манъ, -овичъ, -ерь, -інъ.

Верни ТОЛЬКО валидный JSON (без markdown, без ```):
{{"seq_num": <число или null>, "name": "<Фамилия Имя>"}}
"""


def call_qwen(client: OpenAI, model: str, image_path: Path, prompt: str) -> dict:
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    messages = [
        {"role": "system", "content": SYSTEM_MSG},
        {"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}},
            {"type": "text", "text": prompt},
        ]},
    ]
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=300,
        temperature=0.1,
        top_p=0.9,
    )
    text = resp.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    if text.startswith("<think>"):
        text = text.split("</think>")[-1].strip()
    return json.loads(text)


def load_final(case_id: str) -> dict[str, dict]:
    path = BASE_DIR / f"{case_id}_final.jsonl"
    result = {}
    if path.exists():
        with open(path) as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    result[rec["row_strip"]] = rec
    return result


def select_sample(final_records: dict, n: int) -> list[str]:
    """Pick a balanced sample: some easy (consensus), some hard (corrections), some gemini-only."""
    corrections = [k for k, v in final_records.items() if v.get("source") == "correction"]
    claude = [k for k, v in final_records.items() if v.get("source") == "claude"]
    consensus = [k for k, v in final_records.items() if v.get("source") == "consensus"]
    gemini = [k for k, v in final_records.items() if v.get("source") == "gemini"]

    import random
    random.seed(42)

    sample = []
    for pool, share in [(corrections, 0.35), (claude, 0.20), (consensus, 0.15), (gemini, 0.30)]:
        count = max(1, int(n * share))
        sample.extend(random.sample(pool, min(count, len(pool))))

    random.shuffle(sample)
    return sample[:n]


def surname_match(name_a: str, name_b: str) -> bool:
    """Check if two names share the same surname (first word, case-insensitive)."""
    a = (name_a or "").strip().split()
    b = (name_b or "").strip().split()
    if not a or not b:
        return False
    return a[0].lower() == b[0].lower()


def main():
    parser = argparse.ArgumentParser(description="Benchmark Qwen VL Plus on DAZHO ledger strips")
    parser.add_argument("--case", default="680-1-4")
    parser.add_argument("--sample", type=int, default=30, help="Number of strips to test")
    parser.add_argument("--all", action="store_true", help="Test all strips (overrides --sample)")
    parser.add_argument("--model", default="qwen-vl-plus-latest",
                        help="Qwen model name (default: qwen-vl-plus-latest)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between API calls (seconds)")
    args = parser.parse_args()

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("ERROR: DASHSCOPE_API_KEY not set.")
        sys.exit(1)

    base_url = os.environ.get(
        "DASHSCOPE_BASE_URL",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )
    client = OpenAI(api_key=api_key, base_url=base_url)

    rows_dir = BASE_DIR / f"{args.case}_rows"
    if not rows_dir.exists():
        print(f"ERROR: {rows_dir} not found.")
        sys.exit(1)

    final_records = load_final(args.case)
    if not final_records:
        print(f"ERROR: no final records for {args.case}. Run finalize_ledger.py first.")
        sys.exit(1)

    print(f"Loaded {len(final_records)} final records for {args.case}")
    print(f"Model: {args.model}")

    if args.all:
        strips = sorted(final_records.keys())
    else:
        strips = select_sample(final_records, args.sample)

    print(f"Testing {len(strips)} strips\n")

    results = []
    stats = {"exact_match": 0, "surname_match": 0, "different": 0, "error": 0}

    for i, strip_name in enumerate(strips, 1):
        strip_path = rows_dir / strip_name
        if not strip_path.exists():
            print(f"  {i:3d}. {strip_name}: FILE NOT FOUND")
            stats["error"] += 1
            continue

        ref = final_records[strip_name]
        ref_name = ref.get("final_name", "")
        gemini_name = ref.get("gemini", "")

        prev_strip = None
        prev_surname = ""
        for s in sorted(final_records.keys()):
            if s == strip_name:
                break
            prev_strip = s
        if prev_strip and prev_strip in final_records:
            pn = final_records[prev_strip].get("final_name", "")
            parts = pn.split()
            if parts:
                prev_surname = parts[0]

        if prev_surname:
            surname_hint = (
                f"ПОДСКАЗКА: Фамилия предыдущей строки — «{prev_surname}». "
                f"Если эта строка начинается со знака повтора (\" или „), фамилия = «{prev_surname}»."
            )
        else:
            surname_hint = "Нет контекста предыдущей фамилии (первая строка)."

        prompt = PROMPT.format(surname_hint=surname_hint)

        print(f"  {i:3d}. {strip_name} [{ref.get('source', '?')}]", end=" ", flush=True)

        try:
            result = call_qwen(client, args.model, strip_path, prompt)
            qwen_name = (result or {}).get("name", "") or ""
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"strip": strip_name, "qwen": "", "ref": ref_name, "error": str(e)})
            stats["error"] += 1
            time.sleep(args.delay)
            continue

        if qwen_name == ref_name:
            match_type = "exact"
            stats["exact_match"] += 1
            icon = "✓"
        elif surname_match(qwen_name, ref_name):
            match_type = "surname_ok"
            stats["surname_match"] += 1
            icon = "~"
        else:
            match_type = "different"
            stats["different"] += 1
            icon = "✗"

        print(f"{icon} Q={qwen_name!r}  ref={ref_name!r}  G={gemini_name!r}")

        results.append({
            "strip": strip_name,
            "qwen": qwen_name,
            "ref": ref_name,
            "gemini": gemini_name,
            "source": ref.get("source", ""),
            "match_type": match_type,
        })

        time.sleep(args.delay)

    total = len(results)
    print(f"\n{'='*60}")
    print(f"RESULTS: {total} strips tested with {args.model}")
    print(f"  Exact match:   {stats['exact_match']:3d} ({100*stats['exact_match']/max(total,1):.0f}%)")
    print(f"  Surname match: {stats['surname_match']:3d} ({100*stats['surname_match']/max(total,1):.0f}%)")
    print(f"  Different:     {stats['different']:3d} ({100*stats['different']/max(total,1):.0f}%)")
    print(f"  Errors:        {stats['error']:3d}")
    print(f"{'='*60}")

    out_path = BASE_DIR / f"{args.case}_qwen_benchmark.json"
    out_path.write_text(json.dumps({
        "model": args.model,
        "total": total,
        "stats": stats,
        "results": results,
    }, ensure_ascii=False, indent=2))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
