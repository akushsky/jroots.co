#!/usr/bin/env python3
"""
Fill the ДАЖО archival copy-order form (Замовлення на копіювання) by overlaying
text onto the blank PDF template.

Usage:
    python fill_dazho_order.py --fond 603 --opis 1 \
        --cases '100:69, 249:59, 250:40, 332:31, 385:44, 12, 20, 37, 58, 59, 60, 132' \
        --date '7 березня 2026' \
        -o ~/Downloads/order.pdf

Each case is  case_num[:sheets].  Omit sheets if unknown.

Requires: pip install reportlab pypdf
Template:  cli/dazho_order_template.pdf  (blank form from ДАЖО)
"""

import argparse
import os
import re
from io import BytesIO
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE   = SCRIPT_DIR / "dazho_order_template.pdf"
FONT_PATH  = "/Library/Fonts/Arial Unicode.ttf"

pdfmetrics.registerFont(TTFont("AU", FONT_PATH))

# ── Applicant info ──
APPLICANT = "Michael Akushsky"
ADDRESS   = ["4035522", "Israel, Kfar Yona, Motskin str., 22b"]
EMAIL     = "michael.akushsky@gmail.com"
DIRECTOR  = "І.М. Слобожану"

PAGE_H = 841.92  # A4 in pt

# Table grid extracted from the blank form with pdfplumber (pt, top-left origin)
COL_CENTERS = [74.05, 114.65, 195.65, 282.6, 358.55, 443.9, 524.6]
COL_WIDTHS  = [40.1, 40.1, 121.1, 51.8, 99.3, 70.4, 90.0]
ROW_TOP_TL  = [296.3, 315.9, 335.4, 355.0, 374.6, 394.0, 413.6, 433.1, 452.7, 472.3]
ROW_BOT_TL  = [315.4, 335.0, 354.5, 374.1, 393.5, 413.1, 432.7, 452.2, 471.8, 491.3]
MAX_ROWS    = len(ROW_TOP_TL)  # 10


def row_center_bl(i):
    mid_tl = (ROW_TOP_TL[i] + ROW_BOT_TL[i]) / 2
    return PAGE_H - mid_tl


def draw_centered(c, text, x_center, y_baseline, max_w=None, font_size=9):
    c.setFont("AU", font_size)
    tw = c.stringWidth(text, "AU", font_size)
    if max_w and tw > max_w - 4:
        while tw > max_w - 4 and font_size > 5:
            font_size -= 0.5
            c.setFont("AU", font_size)
            tw = c.stringWidth(text, "AU", font_size)
    c.drawCentredString(x_center, y_baseline, text)


def parse_date(date_str):
    """Parse '7 березня 2026' → ('7', 'березня', '26')."""
    parts = date_str.strip().split()
    if len(parts) != 3:
        raise ValueError(f"Date must be 'day month year', got: {date_str}")
    day, month, year = parts
    if len(year) == 4:
        year = year[2:]
    return day, month, year


def parse_cases(cases_str):
    """Parse '100:69, 249:59, 12' → [('100','69'), ('249','59'), ('12','—')]."""
    result = []
    for item in re.split(r'[,;\s]+', cases_str.strip()):
        if not item:
            continue
        if ':' in item:
            num, sheets = item.split(':', 1)
            result.append((num.strip(), sheets.strip()))
        else:
            result.append((item.strip(), "—"))
    return result


def make_overlay(cases, all_cases, fond, opis, page_num, total_pages, date_parts):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(595.32, PAGE_H))

    # ── Header fields ──
    c.setFont("AU", 11)
    c.drawString(374, 750, APPLICANT)

    c.setFont("AU", 10)
    c.drawString(478, 735, ADDRESS[0])
    c.drawString(349, 722, ADDRESS[1])

    c.setFont("AU", 11)
    c.drawString(390, 680, EMAIL)
    c.drawString(170, 648, APPLICANT)

    # ── Table rows ──
    for i, (case_num, sheets) in enumerate(cases):
        y = row_center_bl(i) - 3
        vals = [
            fond, opis, case_num,
            "Усі арк. та зв.",
            "цифр. копія, ел. пошта",
            sheets, "",
        ]
        for text, cx, cw in zip(vals, COL_CENTERS, COL_WIDTHS):
            draw_centered(c, text, cx, y, max_w=cw, font_size=9)

    # ── Totals (last page) ──
    if page_num == total_pages:
        total_idx = len(cases)
        if total_idx < MAX_ROWS:
            y = row_center_bl(total_idx) - 3
            total_known = sum(int(s) for _, s in all_cases if s != "—")
            has_unknown = any(s == "—" for _, s in all_cases)
            neg_text = f"{total_known}+" if has_unknown else str(total_known)

            c.setFont("AU", 9)
            c.drawRightString(408.2 - 4, y, f"Разом: {len(all_cases)} справ")
            draw_centered(c, neg_text, COL_CENTERS[5], y, max_w=COL_WIDTHS[5])

    # ── Date & signature ──
    day, month, year = date_parts
    c.setFont("AU", 11)
    c.drawCentredString(80, 319, day)
    c.drawString(108, 319, month)
    c.drawString(172, 319, year)
    c.drawCentredString((298 + 540) / 2, 299, f"M. {APPLICANT.split()[-1]}")

    c.save()
    buf.seek(0)
    return buf


def build_pdf(fond, opis, cases, date_parts, output_path):
    writer = PdfWriter()
    template = str(TEMPLATE)

    chunks = []
    remaining = list(cases)
    while remaining:
        if len(remaining) <= MAX_ROWS - 1:
            chunks.append(remaining)
            remaining = []
        else:
            chunks.append(remaining[:MAX_ROWS])
            remaining = remaining[MAX_ROWS:]

    total_pages = len(chunks)

    for page_num, chunk in enumerate(chunks, 1):
        print(f"  Page {page_num}: cases {[c[0] for c in chunk]}")
        overlay_buf = make_overlay(chunk, cases, fond, opis, page_num, total_pages, date_parts)
        overlay_reader = PdfReader(overlay_buf)

        fresh = PdfReader(template)
        page = fresh.pages[0]
        page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)
    print(f"Saved → {output_path}  ({total_pages} page(s), {len(cases)} cases)")


def main():
    parser = argparse.ArgumentParser(description="Fill ДАЖО copy-order form")
    parser.add_argument("--fond", required=True, help="Fond number, e.g. 603")
    parser.add_argument("--opis", required=True, help="Opis number, e.g. 1")
    parser.add_argument("--cases", required=True,
                        help="Comma-separated case_num[:sheets], e.g. '100:69, 249:59, 12'")
    parser.add_argument("--date", required=True,
                        help="Order date, e.g. '7 березня 2026'")
    parser.add_argument("-o", "--output", required=True, help="Output PDF path")
    args = parser.parse_args()

    cases = parse_cases(args.cases)
    date_parts = parse_date(args.date)
    output = os.path.expanduser(args.output)

    build_pdf(args.fond, args.opis, cases, date_parts, output)


if __name__ == "__main__":
    main()
