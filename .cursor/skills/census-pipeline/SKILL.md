---
name: census-pipeline
description: Process 1926 Soviet census scans from TSDAVO — download images, classify pages, extract nationality and FIO, review results. Use when working with census data, Kharkiv/Berdychiv 1926 archives, TSDAVO images, or cli/census_pipeline.py.
---

# Census Pipeline V4

Process 1926 Soviet census family cards (Сімейна картка, Форма №2) from TSDAVO digital archive. Goal: identify Jewish families and extract head-of-family FIO.

## Scripts

| Script | Purpose |
|--------|---------|
| `cli/census_pipeline.py` | Main pipeline: download, classify, extract, finalize |
| `cli/review_server.py` | Local web UI for reviewing/editing extracted data |
| `cli/review.html` | HTML template for the review UI |

## Quick Start

### 1. Download images from TSDAVO

```bash
python cli/census_pipeline.py download \
  --start <first_file_id> --end <last_file_id> \
  --dest /path/to/582-1-NNNN
```

URL pattern: `https://e-resource.tsdavo.gov.ua/static/files/{prefix}/{file_id}.jpg`
where `prefix` = first 3 digits of file_id. Throttled 1-4s between requests.

### 2. Run automated stages (Gemini)

```bash
export GOOGLE_API_KEY=...
python cli/census_pipeline.py process --source /path/to/582-1-NNNN
```

This runs stages 1-6. If Claude FIO data is missing, it stops and prints a manifest path.

### 3. Extract FIO via main Claude agent

When the pipeline stops at stage 6, process images using the main Claude agent directly (NEVER subagents). See [FIO Extraction](#fio-extraction-via-main-claude-agent) below.

### 4. Finalize and review

```bash
# Rerun to generate review.csv (stage 7)
python cli/census_pipeline.py process --source /path/to/582-1-NNNN

# Start review UI
python cli/review_server.py \
  --source /path/to/582-1-NNNN \
  --csv cli/census_output/582-1-NNNN/review.csv \
  --port 8080
```

Open `http://localhost:8080` to review, edit names, and mark non-Jewish entries.

## Pipeline Stages

| # | Stage | Tool | Output file |
|---|-------|------|-------------|
| 0 | Download from TSDAVO | urllib | JPG files in source dir |
| 1 | Enumerate JPGs | — | — |
| 2 | Dedup consecutive (SHA-256) | hashlib | `duplicates.log` |
| 3 | Classify first/second page | Gemini (`gemini-3.1-flash-lite-preview`) | `page_types.json` |
| 3.5 | Verify classification anomalies | manual | `anomalies.json`, `classification_corrections.json` |
| 4 | Smart-pair first+second pages | — | — |
| 5 | Extract nationality | Gemini (`gemini-2.0-flash`) | `nationalities.json` |
| 6 | Generate Claude FIO manifest | — | `claude_manifest.json`, `claude_fio.json` |
| 7 | Merge, russify, write CSV | — | `review.csv` |

## Output Directory Structure

```
cli/census_output/582-1-NNNN/
├── page_types.json                  # {filename: "first"|"second"}
├── classification_corrections.json  # manual overrides: {filename: "first"|"second"|"exclude"}
├── anomalies.json                   # sequence anomalies detected in stage 3.5
├── nationalities.json               # {filename: "євр."|"укр."|...}
├── claude_manifest.json             # list of images pending FIO extraction
├── claude_fio.json                  # {filename: {name, confidence, notes}}
├── review.csv                       # final CSV for UI review
└── duplicates.log                   # dedup log
```

## FIO Extraction via Main Claude Agent

After stage 6 produces `claude_manifest.json`, the main Claude agent (NOT subagents!) reads each image pair directly in conversation.

**WARNING: NEVER delegate FIO/nationality extraction to subagents or Task tools. Subagents use weaker models that produce catastrophic errors on handwritten text.**

### Process

1. Load `claude_manifest.json` to get the list of images needing FIO extraction
2. For each card, read BOTH the first page AND its paired second page
3. Extract FIO from field 3, cross-reference with the family table on the back
4. Process in batches of ~5 image pairs at a time (model context limits)

### Instructions for reading each card

```
Read field 3 (Прізвище, ім'я та по батькові) on the first page.
Cross-reference with the surname/initials in the family table on the second page.

Rules:
- Read letter by letter for difficult handwriting
- These are mostly Jewish/Ukrainian/Russian families from Berdychiv area
- Patronymics end in -ович/-евич/-ич (male) or -овна/-евна/-івна (female)
- If patronymic is abbreviated, write the FULL form
- Common Jewish names: Мойсей, Шмуль, Хаїм, Лейзер, Янкель, Герш, Бейла, Рівка, Хана, Сара, Малка, Тайба
- Nationality is in colored ink (red/blue/purple) in margins near field 3
```

### Saving results

Write to `claude_fio.json` (Ukrainian form) and `review.csv` (Russian form via `to_russian()`).

## Manual Corrections

### Single entry correction (without rerunning pipeline)

Update BOTH files to avoid losing edits:

```python
import json, csv

# 1. Update claude_fio.json (Ukrainian form)
fio_path = 'cli/census_output/582-1-NNNN/claude_fio.json'
with open(fio_path) as f:
    data = json.load(f)
data['FILENAME.jpg'] = {
    'name': 'Прізвище Ім\'я По-батькові',
    'confidence': 'high',
    'notes': 'Corrected manually; verified with second page'
}
with open(fio_path, 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# 2. Update review.csv (Russian form)
review_path = 'cli/census_output/582-1-NNNN/review.csv'
with open(review_path, newline='') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)
for r in rows:
    if r['filename'] == 'FILENAME.jpg':
        r['name'] = 'Фамилия Имя Отчество'  # russified
        r['confidence'] = 'high'
        r['notes'] = 'correction note'
        break
with open(review_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
```

### Classification corrections

Save to `classification_corrections.json` to override Gemini classification:

```json
{
  "1411367.jpg": "exclude",
  "1411428.jpg": "second"
}
```

Valid values: `"first"`, `"second"`, `"exclude"` (skip entirely).

## Critical Gotchas

1. **NEVER use subagents for FIO or nationality extraction.** Subagents use weaker models (e.g. composer-1.5) that produce unacceptable error rates on handwritten census data. ALL visual inspection of images — FIO reading, nationality verification, cross-referencing with second pages — MUST be performed by the main Claude agent (Claude 4.6 Opus or higher) directly in the conversation. This is NON-NEGOTIABLE. Do not delegate image reading to Task/subagent tools under any circumstances.

2. **Always cross-reference FIO with second page.** The back of each card has a family composition table with surname/initials. Without this, agents misread surnames (e.g. "Маронкній" vs "Аронкін", "Плис Товбуз Сюзерів" vs "Хасін Рівка Лейзерівна").

3. **Never rerun stage 7 after manual UI edits.** `stage_finalize` regenerates `review.csv` from scratch, overwriting all user edits. For corrections, update both `claude_fio.json` and `review.csv` directly.

4. **Gemini is unreliable for nationality and FIO.** Use Gemini only for page classification (stage 3). All FIO and nationality extraction should go through Claude main agent directly.

5. **Name russification.** `claude_fio.json` stores Ukrainian forms. `review.csv` stores Russian forms (via `to_russian()`). When correcting manually, update both.

6. **Patronymic completion.** If the source shows an abbreviated patronymic (e.g. "Борис.", "Лейзер."), always write the full form: "Борисович/Борисовна", "Лейзерович/Лейзеровна".

7. **Jewish nationality markers.** The pipeline recognizes: євр, евр, єврей, еврей, єврейка, еврейка, єв, ев, жид, жок, евреи.

8. **Nationality is written in colored ink (red/blue/purple).** It appears to the left of or above field 3 on the first page. Always look for colored ink annotations in the margins — not the printed form text.

## Document Structure

Each census family card consists of two pages:
- **First page (front):** Printed form "Сімейна картка" with handwritten answers. Contains nationality annotation (margins), head-of-family FIO (field 3), gender (field 4), occupation (field 5), family size (field 6).
- **Second page (back):** Rotated table "Склад сім'ї" with numbered rows for each family member — surname, name, relationship, gender, age, occupation.

Images alternate: first, second, first, second... with occasional anomalies (missing backs, duplicates, cover pages).
