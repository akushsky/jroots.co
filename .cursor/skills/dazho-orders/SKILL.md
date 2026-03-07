---
name: dazho-orders
description: Order archival document copies from ДАЖО (Державний архів Житомирської області). Fills the PDF order form, manages order lifecycle in Plane, tracks receipt. Use when ordering documents from ДАЖО, filling Замовлення на копіювання, or managing Zhytomyr archive requests.
---

# ДАЖО Document Orders

## Overview

Workflow for ordering digital copies of archival cases from ДАЖО (Zhytomyr State Archive). Covers the full lifecycle: identify cases, fill the order form, submit, track in Plane, receive and process.

## Tools

| File | Purpose |
|------|---------|
| `cli/dazho_order_template.pdf` | Blank order form (Замовлення на копіювання) |
| `cli/fill_dazho_order.py` | Fills the form by overlaying text on the template |
| `cli/dazho_603_cases_to_order.md` | Example: prioritized case list for fond 603 |

## Order Form Script

```bash
python cli/fill_dazho_order.py \
  --fond 603 --opis 1 \
  --cases '100:69, 249:59, 250:40, 12, 20, 37' \
  --date '{day} {місяць_укр} {year}' \
  -o ~/Downloads/order.pdf
```

- `--date`: always use today's date in Ukrainian genitive: `7 березня 2026`, `15 квітня 2026`, etc.
- Cases format: `case_num[:sheets]` — omit sheets if unknown
- Auto-paginates: 10 data rows per page, totals on last page
- Applicant info hardcoded in script (APPLICANT, ADDRESS, EMAIL constants)
- Requires: `pip install reportlab pypdf`

## Workflow

### 1. Identify cases to order

Source: archival inventory (опис) PDFs, or `cli/dazho_*_cases_to_order.md` files.
Each case needs: fond, opis, case number, sheet count (if known).

### 2. Generate order form

Run `fill_dazho_order.py` with the case list. Open the output PDF and verify text alignment.

### 3. Create Plane tracking

Project: **Генеалогія: клиенти** (`bbed6e2c-30c8-4091-bf00-308bb7e5f2b6`)

Structure:
```
Parent: "ДАЖО ф.{fond} оп.{opis} — {description}"          state: In Progress
  └─ Child: "Замовлення від {date} ({N} справ)"             state: In Progress
       ├─ "Справа {num} — {title} (~{year}, {sheets} арк.)" state: Todo
       └─ ...
```

States:
| State | ID | Use |
|-------|----|-----|
| Backlog | `bdd5fdee-...` | Not yet planned |
| Todo | `2f477e54-...` | Planned, not sent |
| In Progress | `c7e8af0a-...` | Order sent, awaiting response |
| Received | `13ccb71e-...` | Files received from archive |
| Done | `d9cfd04d-...` | Processed and uploaded to jroots.co |

When order is sent:
- Set order work item to **In Progress**, `start_date` = send date
- Add comment: "Замовлення відправлено до ДАЖО {date} електронною поштою"

### 4. Receive and process

When files arrive:
- Update individual case items to **Received**
- Upload scans to jroots.co using `cli/upload.py`
- After upload, set items to **Done**

## Applicant Details

```
Name:    Michael Akushsky
Address: 4035522, Israel, Kfar Yona, Motskin str., 22b
Email:   michael.akushsky@gmail.com
```

Director (addressee): І.М. Слобожану

## Form Layout Notes

The template PDF has a 7-column table with 10 data rows per page. Column grid positions (in pt, extracted via pdfplumber) are hardcoded in `fill_dazho_order.py`. If the blank form changes, re-extract positions using:

```python
import pdfplumber
with pdfplumber.open("template.pdf") as pdf:
    page = pdf.pages[0]
    for r in sorted(page.rects, key=lambda r: r['top']):
        print(f"x0={r['x0']:.1f} y0={r['top']:.1f} x1={r['x1']:.1f} y1={r['bottom']:.1f}")
```
