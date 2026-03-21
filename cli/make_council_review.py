"""
make_council_review.py — генератор HTML-обзора для council и row-mode JSONL.

Использование:
  python cli/make_council_review.py --case 680-1-4            # council mode
  python cli/make_council_review.py --case 680-1-4 --row-mode # row-crops mode
  python cli/make_council_review.py --case 680-1-4 --open
"""

import json
import base64
import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path("cli/dazho_downloads")

STYLE = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: Arial, sans-serif; font-size: 13px; background: #f0f0f0; }
h1 { padding: 10px 16px; background: #1a1a2e; color: #e0e0ff; font-size: 16px; }
h1 small { font-weight: normal; font-size: 12px; opacity: 0.7; }

.legend { display:flex; gap:16px; padding:8px 16px; background:#fff;
          border-bottom:1px solid #ddd; font-size:11px; flex-wrap:wrap; }
.legend span { display:flex; align-items:center; gap:4px; }
.swatch { width:14px; height:14px; border-radius:2px; display:inline-block; }
.sw-ok     { background:#d4edda; border:1px solid #b8dfc4; }
.sw-debate { background:#fff3cd; border:1px solid #ffc107; }
.sw-human  { background:#f8d7da; border:1px solid #f5c6cb; }

.page-block { display:flex; gap:10px; margin:12px; padding:10px;
              background:#fff; border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,.1); }
.page-img { flex:0 0 360px; }
.page-img img { width:100%; border:1px solid #ccc; cursor:zoom-in;
                border-radius:4px; transition:box-shadow .15s; }
.page-img img:hover { box-shadow:0 0 0 2px #007bff; }
.page-label { font-weight:bold; font-size:12px; margin-bottom:4px; color:#555; }
.page-tables { flex:1; overflow-x:auto; }

.summary { padding:4px 8px; margin-bottom:6px; border-left:3px solid #007bff;
           background:#f0f6ff; font-size:11px; display:flex; gap:12px; }
.badge { display:inline-block; border-radius:3px; padding:1px 6px; font-size:11px; font-weight:bold; }
.badge-ok    { background:#28a745; color:#fff; }
.badge-warn  { background:#fd7e14; color:#fff; }
.badge-err   { background:#dc3545; color:#fff; }

table { border-collapse:collapse; width:100%; font-size:12px; }
th { background:#2c2c54; color:#fff; padding:4px 6px; text-align:left; font-size:11px; white-space:nowrap; }
td { padding:3px 6px; border-bottom:1px solid #eee; vertical-align:top; }

tr.row-ok   td { background:#d4edda; }
tr.row-debate td { background:#fff3cd; }
tr.row-human  td { background:#f8d7da; }

.col-seq  { width:28px; color:#888; text-align:center; }
.col-name { min-width:140px; }
.col-r1   { min-width:120px; color:#555; font-size:11px; }
.col-final { font-weight:bold; }
.col-strip { width:320px; }
.col-strip img { width:100%; border:1px solid #ccc; cursor:zoom-in; border-radius:3px; }
.col-strip img:hover { box-shadow:0 0 0 2px #007bff; }

details { margin-top:3px; }
summary { cursor:pointer; color:#666; font-size:11px; user-select:none; }
summary:hover { color:#333; }
.debate-box { background:#fffbf0; border:1px solid #ffc107; border-radius:4px;
              padding:6px 8px; margin-top:4px; font-size:11px; }
.debate-model { font-weight:bold; color:#333; margin-top:5px; }
.debate-r1  { color:#666; }
.debate-r2  { color:#1a1a2e; }
.debate-why { color:#555; font-style:italic; margin-left:8px; }

/* Lightbox */
#lb { display:none; position:fixed; inset:0; background:rgba(0,0,0,.88);
      z-index:9999; align-items:center; justify-content:center; cursor:zoom-out; }
#lb.open { display:flex; }
#lb img { max-width:96vw; max-height:96vh; object-fit:contain;
          box-shadow:0 0 50px rgba(0,0,0,.9); border:2px solid #fff; }
#lb-close { position:fixed; top:12px; right:18px; font-size:34px; color:#fff;
            cursor:pointer; line-height:1; z-index:10000; user-select:none; }
#lb-cap { position:fixed; bottom:14px; color:#ccc; font-size:12px;
          text-align:center; width:100%; pointer-events:none; }
"""

JS = """
const lb = document.getElementById('lb');
const lbI = document.getElementById('lb-img');
const lbC = document.getElementById('lb-cap');

document.querySelectorAll('.page-img img, .col-strip img').forEach(img => {
  img.addEventListener('click', () => {
    lbI.src = img.src;
    lbC.textContent = img.alt;
    lb.classList.add('open');
  });
});
lb.addEventListener('click', e => { if (e.target !== lbI) lb.classList.remove('open'); });
document.getElementById('lb-close').addEventListener('click', () => lb.classList.remove('open'));
document.addEventListener('keydown', e => { if (e.key === 'Escape') lb.classList.remove('open'); });
"""


def make_review(case_id: str, open_browser: bool = False):
    council_file = BASE_DIR / f"{case_id}_council.jsonl"
    pages_dir = BASE_DIR / f"{case_id}_pages"
    out_path = BASE_DIR / f"{case_id}_council_review.html"

    if not council_file.exists():
        print(f"ERROR: {council_file} not found. Run process_council.py first.")
        return

    pages = []
    with open(council_file) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    pages.append(json.loads(line))
                except Exception as e:
                    print(f"  Skipping bad line: {e}")

    # Collect model names from first page with debate data
    model_names = []
    for pg in pages:
        for row in pg.get("data", []):
            r1 = row.get("_r1", {})
            if r1:
                model_names = list(r1.keys())
                break
        if model_names:
            break

    total_rows = sum(len(pg.get("data", [])) for pg in pages)
    total_contested = sum(
        sum(1 for r in pg.get("data", []) if r.get("_contested")) for pg in pages
    )
    total_human = sum(
        sum(1 for r in pg.get("data", []) if r.get("_needs_human")) for pg in pages
    )

    parts = [f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{case_id} Council Review</title>
<style>{STYLE}</style>
</head><body>
<h1>{case_id} · Council Review
  <small>({len(pages)} pages, {total_rows} rows,
  {total_contested} debated, {total_human} need human review)
  &nbsp;·&nbsp; Click scan to enlarge</small>
</h1>

<div class="legend">
  <span><span class="swatch sw-ok"></span> Consensus (2/2+)</span>
  <span><span class="swatch sw-debate"></span> Debated &amp; resolved</span>
  <span><span class="swatch sw-human"></span> Needs human review</span>
</div>

<div id="lb">
  <span id="lb-close">&#10005;</span>
  <img id="lb-img" src="" alt="">
  <div id="lb-cap"></div>
</div>
"""]

    for pg in pages:
        img_name = pg.get("image", "?")
        rows = pg.get("data", [])
        img_path = pages_dir / img_name
        if not img_path.exists():
            img_b64 = ""
        else:
            img_b64 = base64.b64encode(img_path.read_bytes()).decode()

        n_ok = sum(1 for r in rows if not r.get("_contested"))
        n_debate = sum(1 for r in rows if r.get("_contested") and not r.get("_needs_human"))
        n_human = sum(1 for r in rows if r.get("_needs_human"))

        # Header columns for R1 per model
        r1_headers = "".join(f'<th class="col-r1">{m}</th>' for m in model_names)

        parts.append(f"""
<div class="page-block" id="{img_name}">
  <div class="page-img">
    <div class="page-label">{img_name}</div>
    <img src="data:image/png;base64,{img_b64}" alt="{img_name}">
  </div>
  <div class="page-tables">
    <div class="summary">
      <span>Rows: <b>{len(rows)}</b></span>
      <span class="badge badge-ok">✓ {n_ok} consensus</span>
      <span class="badge badge-warn">⚡ {n_debate} debated</span>
      <span class="badge badge-err">⚠ {n_human} human</span>
    </div>
    <table>
      <tr>
        <th class="col-seq">#</th>
        {r1_headers}
        <th class="col-final">Council result</th>
        <th>Residence</th>
      </tr>
""")

        for row in rows:
            seq = row.get("seq_num", "")
            final_name = row.get("name", "")
            residence = row.get("residence") or ""
            contested = row.get("_contested", False)
            needs_human = row.get("_needs_human", False)
            r1 = row.get("_r1", {})
            debate = row.get("_debate", {})

            if needs_human:
                css = "row-human"
            elif contested:
                css = "row-debate"
            else:
                css = "row-ok"

            r1_cells = "".join(
                f'<td class="col-r1">{r1.get(m, "")}</td>' for m in model_names
            )

            # Build debate details block
            debate_html = ""
            if contested and debate:
                entries = []
                for mname, entry in debate.items():
                    r1_n = entry.get("round1", "")
                    r2_n = entry.get("round2", "")
                    why = entry.get("reasoning", "")
                    changed = " → " + r2_n if r2_n and r2_n != r1_n else ""
                    entries.append(
                        f'<div class="debate-model">{mname}</div>'
                        f'<div class="debate-r1">R1: {r1_n}{changed}</div>'
                        + (f'<div class="debate-why">{why[:200]}</div>' if why else "")
                    )
                debate_html = (
                    "<details><summary>debate log</summary>"
                    f'<div class="debate-box">{"".join(entries)}</div>'
                    "</details>"
                )

            icon = "⚠ " if needs_human else ("⚡ " if contested else "")
            parts.append(
                f'<tr class="{css}">'
                f'<td class="col-seq">{seq}</td>'
                f'{r1_cells}'
                f'<td class="col-name col-final">{icon}{final_name}{debate_html}</td>'
                f'<td>{residence}</td>'
                f'</tr>\n'
            )

        parts.append("</table></div></div>\n")

    parts.append(f"<script>{JS}</script></body></html>")

    out_path.write_text("".join(parts), encoding="utf-8")
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"Written: {out_path}  ({size_mb:.1f} MB)")

    if open_browser:
        subprocess.run(["open", str(out_path)])


def make_rowmode_review(case_id: str, open_browser: bool = False):
    """Generate HTML review for row-crop mode (_rowmode.jsonl)."""
    rowmode_file = BASE_DIR / f"{case_id}_rowmode.jsonl"
    rows_dir     = BASE_DIR / f"{case_id}_rows"
    pages_dir    = BASE_DIR / f"{case_id}_pages"
    out_path     = BASE_DIR / f"{case_id}_rowmode_review.html"

    if not rowmode_file.exists():
        print(f"ERROR: {rowmode_file} not found. Run: python cli/process_ledger.py --case {case_id} --row-crops")
        return

    # Load all records
    records = []
    with open(rowmode_file) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

    # Group by page
    from collections import defaultdict
    pages_dict = defaultdict(list)
    for rec in records:
        if not rec.get("skipped"):
            pages_dict[rec.get("page", "?")].append(rec)

    total_rows = sum(len(v) for v in pages_dict.values())
    total_consensus = sum(sum(1 for r in v if r.get("consensus")) for v in pages_dict.values())
    total_human = sum(sum(1 for r in v if r.get("needs_human")) for v in pages_dict.values())
    total_single = total_rows - total_consensus - total_human

    parts = [f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{case_id} Row-Mode Review</title>
<style>{STYLE}</style>
</head><body>
<h1>{case_id} · Row-Crop OCR Review
  <small>({len(pages_dict)} pages, {total_rows} data rows,
  ✓ {total_consensus} consensus, ≠ {total_human} contested, ∅ {total_single} single-model)
  &nbsp;·&nbsp; Click image to enlarge</small>
</h1>

<div class="legend">
  <span><span class="swatch sw-ok"></span> Consensus (both models agree)</span>
  <span><span class="swatch sw-human"></span> Contested (models disagree)</span>
  <span><span class="swatch sw-debate"></span> Single model only</span>
</div>

<div id="lb">
  <span id="lb-close">&#10005;</span>
  <img id="lb-img" src="" alt="">
  <div id="lb-cap"></div>
</div>
"""]

    for page_name in sorted(pages_dict.keys()):
        page_records = pages_dict[page_name]
        img_path = pages_dir / page_name
        if img_path.exists():
            rel = img_path.relative_to(out_path.parent)
            page_img_html = f'<img src="{rel}" alt="{page_name}">'
        else:
            page_img_html = f'<span style="color:#999">no image</span>'

        n_ok    = sum(1 for r in page_records if r.get("consensus"))
        n_human = sum(1 for r in page_records if r.get("needs_human"))
        n_single = len(page_records) - n_ok - n_human

        parts.append(f"""
<div class="page-block" id="{page_name}">
  <div class="page-img">
    <div class="page-label">{page_name}</div>
    {page_img_html}
  </div>
  <div class="page-tables">
    <div class="summary">
      <span>Rows: <b>{len(page_records)}</b></span>
      <span class="badge badge-ok">✓ {n_ok} consensus</span>
      <span class="badge badge-warn">∅ {n_single} single</span>
      <span class="badge badge-err">≠ {n_human} contested</span>
    </div>
    <table>
      <tr>
        <th class="col-strip">Row strip</th>
        <th class="col-seq">#</th>
        <th class="col-r1">Gemini</th>
        <th class="col-r1">GPT-4o</th>
        <th class="col-final">Final</th>
      </tr>
""")

        for rec in page_records:
            seq        = rec.get("seq_num") or ""
            gemini_n   = rec.get("gemini", "") or ""
            gpt4o_n    = rec.get("gpt4o", "") or ""
            final_n    = rec.get("final", "") or ""
            consensus  = rec.get("consensus", False)
            needs_human= rec.get("needs_human", False)
            strip_name = rec.get("row_strip", "")

            if needs_human:
                css = "row-human"
            elif consensus:
                css = "row-ok"
            else:
                css = "row-debate"

            # Row strip thumbnail — use relative file path (no base64 for strips)
            strip_path = rows_dir / strip_name
            if strip_path.exists():
                rel = strip_path.relative_to(out_path.parent)
                strip_html = f'<img src="{rel}" alt="{strip_name}">'
            else:
                strip_html = strip_name

            icon = "≠ " if needs_human else ("" if consensus else "∅ ")
            parts.append(
                f'<tr class="{css}">'
                f'<td class="col-strip">{strip_html}</td>'
                f'<td class="col-seq">{seq}</td>'
                f'<td class="col-r1">{gemini_n}</td>'
                f'<td class="col-r1">{gpt4o_n}</td>'
                f'<td class="col-name col-final">{icon}{final_n}</td>'
                f'</tr>\n'
            )

        parts.append("</table></div></div>\n")

    parts.append(f"<script>{JS}</script></body></html>")
    out_path.write_text("".join(parts), encoding="utf-8")
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"Written: {out_path}  ({size_mb:.1f} MB)")

    if open_browser:
        subprocess.run(["open", str(out_path)])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="680-1-4")
    parser.add_argument("--open", action="store_true", help="Open in browser after generating")
    parser.add_argument("--row-mode", action="store_true",
                        help="Generate row-mode review from _rowmode.jsonl instead of _council.jsonl")
    args = parser.parse_args()
    if args.row_mode:
        make_rowmode_review(args.case, open_browser=args.open)
    else:
        make_review(args.case, open_browser=args.open)


if __name__ == "__main__":
    main()
