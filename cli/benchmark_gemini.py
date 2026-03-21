"""
benchmark_gemini.py — Benchmark Gemini models on DAZHO ledger row strips.

Sends the same sample of row strips to different Gemini model versions
and compares against the reference (final) readings.

Usage:
  python cli/benchmark_gemini.py --case 680-1-4 --sample 30 --model gemini-2.5-pro
  python cli/benchmark_gemini.py --case 680-1-4 --sample 30 --model gemini-3.1-pro-preview
  python cli/benchmark_gemini.py --case 680-1-4 --sample 30 --model gemini-3-flash-preview
  python cli/benchmark_gemini.py --case 680-1-4 --all --model gemini-3.1-pro-preview
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


def extract_text(resp) -> str:
    """Extract text from Gemini response, handling thinking models that may split parts."""
    if resp.text:
        return resp.text.strip()
    if resp.candidates:
        for part in (resp.candidates[0].content.parts or []):
            if part.text and not getattr(part, "thought", False):
                return part.text.strip()
        for part in (resp.candidates[0].content.parts or []):
            if part.text:
                return part.text.strip()
    raise ValueError(f"Empty response: finish_reason={getattr(resp.candidates[0], 'finish_reason', '?')}")


THINKING_MODELS = {
    "gemini-2.5-pro", "gemini-2.5-flash",
    "gemini-3.1-pro-preview", "gemini-3-flash-preview",
}


def call_gemini(client: genai.Client, model: str, image_path: Path, prompt: str) -> dict:
    if model in THINKING_MODELS:
        config_kwargs = {"max_output_tokens": 8192}
    else:
        config_kwargs = {"max_output_tokens": 300, "temperature": 0.1, "top_p": 0.9}

    resp = client.models.generate_content(
        model=model,
        contents=[
            types.Content(parts=[
                types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/png"),
                types.Part.from_text(text=prompt),
            ])
        ],
        config=types.GenerateContentConfig(**config_kwargs),
    )
    text = extract_text(resp)
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
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
    """Same sample as Qwen benchmark (seed=42) for fair comparison."""
    corrections = [k for k, v in final_records.items() if v.get("source") == "correction"]
    claude = [k for k, v in final_records.items() if v.get("source") == "claude"]
    consensus = [k for k, v in final_records.items() if v.get("source") == "consensus"]
    gemini_only = [k for k, v in final_records.items() if v.get("source") == "gemini"]

    import random
    random.seed(42)

    sample = []
    for pool, share in [(corrections, 0.35), (claude, 0.20), (consensus, 0.15), (gemini_only, 0.30)]:
        count = max(1, int(n * share))
        sample.extend(random.sample(pool, min(count, len(pool))))

    random.shuffle(sample)
    return sample[:n]


def surname_match(name_a: str, name_b: str) -> bool:
    a = (name_a or "").strip().split()
    b = (name_b or "").strip().split()
    if not a or not b:
        return False
    return a[0].lower() == b[0].lower()


def main():
    parser = argparse.ArgumentParser(description="Benchmark Gemini models on DAZHO ledger strips")
    parser.add_argument("--case", default="680-1-4")
    parser.add_argument("--sample", type=int, default=30, help="Number of strips to test")
    parser.add_argument("--all", action="store_true", help="Test all strips")
    parser.add_argument("--model", default="gemini-2.5-pro",
                        help="Gemini model (e.g. gemini-2.5-pro, gemini-3.1-pro-preview, gemini-3-flash-preview)")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between API calls (seconds)")
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

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
    timings = []

    for i, strip_name in enumerate(strips, 1):
        strip_path = rows_dir / strip_name
        if not strip_path.exists():
            print(f"  {i:3d}. {strip_name}: FILE NOT FOUND")
            stats["error"] += 1
            continue

        ref = final_records[strip_name]
        ref_name = ref.get("final_name", "")
        orig_gemini = ref.get("gemini", "")

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
            t0 = time.time()
            result = call_gemini(client, args.model, strip_path, prompt)
            elapsed = time.time() - t0
            timings.append(elapsed)
            model_name = (result or {}).get("name", "") or ""
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"strip": strip_name, "model_name": "", "ref": ref_name, "error": str(e)})
            stats["error"] += 1
            time.sleep(args.delay)
            continue

        if model_name == ref_name:
            match_type = "exact"
            stats["exact_match"] += 1
            icon = "✓"
        elif surname_match(model_name, ref_name):
            match_type = "surname_ok"
            stats["surname_match"] += 1
            icon = "~"
        else:
            match_type = "different"
            stats["different"] += 1
            icon = "✗"

        print(f"{icon} ({elapsed:.1f}s) M={model_name!r}  ref={ref_name!r}  old_G={orig_gemini!r}")

        results.append({
            "strip": strip_name,
            "model_name": model_name,
            "ref": ref_name,
            "orig_gemini": orig_gemini,
            "source": ref.get("source", ""),
            "match_type": match_type,
            "time_s": round(elapsed, 2),
        })

        time.sleep(args.delay)

    total = len(results)
    avg_time = sum(timings) / len(timings) if timings else 0
    print(f"\n{'='*60}")
    print(f"RESULTS: {total} strips tested with {args.model}")
    print(f"  Exact match:   {stats['exact_match']:3d} ({100*stats['exact_match']/max(total,1):.0f}%)")
    print(f"  Surname match: {stats['surname_match']:3d} ({100*stats['surname_match']/max(total,1):.0f}%)")
    print(f"  Different:     {stats['different']:3d} ({100*stats['different']/max(total,1):.0f}%)")
    print(f"  Errors:        {stats['error']:3d}")
    print(f"  Avg time/strip: {avg_time:.1f}s")
    print(f"{'='*60}")

    safe_model = args.model.replace("/", "_")
    out_path = BASE_DIR / f"{args.case}_gemini_bench_{safe_model}.json"
    out_path.write_text(json.dumps({
        "model": args.model,
        "total": total,
        "stats": stats,
        "avg_time_s": round(avg_time, 2),
        "results": results,
    }, ensure_ascii=False, indent=2))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
