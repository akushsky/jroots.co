#!/usr/bin/env python3
"""Audit FIO from fio_export.csv using LLM to flag suspicious names."""

import csv
import json
import os
import sys
import time
from pathlib import Path

from openai import OpenAI

OUTPUT_DIR = Path(__file__).parent
BATCH_SIZE = 200

SYSTEM_PROMPT = """\
You are an expert in Eastern European Jewish/Russian/Ukrainian personal names \
from archival documents of the late 19th – early 20th century (Russian Empire, \
Soviet Union, shtetl communities). You will receive a numbered list of names \
(ФИО) extracted from such documents.

Your task: find entries where the text is CLEARLY GARBLED — i.e. it cannot \
possibly be a real surname or given name in any plausible reading. Think of \
broken OCR output, random letter soup, impossible consonant clusters that \
don't exist in any Slavic or Yiddish name.

DO NOT flag any of the following — they are ALL normal:
- Yiddish names however unusual: Стера, Груня, Песя, Итка, Эска, Фало, \
  Устурка, Дыся, Идка, Неух, Нуто, Тевель, Хонон, Ципа, Сося, Двойра, \
  Гитля, Церлия, Овший, Овшия, Гейнах, Ноях, Нусин, Файвель, Зиндель, \
  Сруль, Гершко, Шмуль, Фроим, Ента, Геся, etc.
- Jewish surnames however rare: Пинхасик, Подоксик, Фундылер, Крейндель, \
  Эбех, Талесмахер, Гермизо, Тугер, Блинчик, Эленбоген, Месенгисер, \
  Кнопов, Глейзер, Бранспис, Бык, Ройтбур, Шамис, Лейбельс, Нысензон, \
  Ярмульник, Юхт, Блех, Биленкин, etc.
- Surnames from place names: Иерусалимская, Запишковецкая, Ходоровская, etc.
- Surnames from adjectives/nouns: Безсмертная, Короткая, Спокойная, \
  Мурованный, Письменный, Горбонос, etc.
- Single-word entries (surname only)
- Names with (?) or (??) — intentional uncertainty markers
- Names with initials: "Коренфельд Х. М.", "Бродская Р. Д.", etc.
- Names abbreviated with dot: "Бор.", "Абр.", "Ср."
- Hyphenated names: Сося-Бейла, Хаим-Меер, Файвель-Ицхок, etc.

ONLY flag entries where the text is IMPOSSIBLE as a name — garbled beyond \
recognition, random letters, clearly broken OCR. Be very conservative. \
When in doubt, do NOT flag.

Return JSON: {"flagged": [{"id": N, "name": "...", "reason": "..."}]}
If nothing is suspicious, return: {"flagged": []}"""


def audit_batch(client: OpenAI, batch: list[dict]) -> list[dict]:
    names_text = "\n".join(f"{obj['id']}: {obj['text_content']}" for obj in batch)

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Check these names:\n\n{names_text}\n\nReturn JSON: {{\"flagged\": [...]}}"},
        ],
    )

    raw = resp.choices[0].message.content
    try:
        data = json.loads(raw)
        return data.get("flagged", data if isinstance(data, list) else [])
    except json.JSONDecodeError:
        print(f"  WARNING: failed to parse LLM response", file=sys.stderr)
        return []


def main():
    export_path = OUTPUT_DIR / "fio_export.csv"
    audit_path = OUTPUT_DIR / "fio_audit.csv"

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        env_local = OUTPUT_DIR.parent / ".env.local"
        if env_local.exists():
            for line in env_local.read_text().splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    objects = []
    with open(export_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            objects.append({"id": int(row["id"]), "text_content": row["text_content"]})
    print(f"Loaded {len(objects)} records from {export_path}")

    all_flagged = []
    total_batches = (len(objects) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(objects), BATCH_SIZE):
        batch = objects[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} names)...", end=" ", flush=True)

        flagged = audit_batch(client, batch)
        all_flagged.extend(flagged)
        print(f"{len(flagged)} flagged")

        if batch_num < total_batches:
            time.sleep(0.5)

    with open(audit_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "reason"])
        for item in all_flagged:
            w.writerow([item.get("id", ""), item.get("name", ""), item.get("reason", "")])

    print(f"\n{'='*60}")
    print(f"AI audit: {len(all_flagged)} suspicious out of {len(objects)} total")
    print(f"{'='*60}")
    for item in all_flagged:
        print(f"  #{item.get('id','?'):>5}  {item.get('name',''):40s}  {item.get('reason','')}")
    print(f"\nSaved to {audit_path}")


if __name__ == "__main__":
    main()
