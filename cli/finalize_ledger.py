"""
finalize_ledger.py — Clean, filter, and merge OCR data for DAZHO ledger 680-1-4.

Steps:
  1. Load rowmode.jsonl (Gemini + GPT-4o readings)
  2. Load claude_readings.json (manual Claude readings, pages 003-007)
  3. Load corrections.json (manual spot-check corrections) if exists
  4. Filter non-data rows (headers, Итого, binding, borders)
  5. Fix ditto surname propagation
  6. Identify suspect rows for spot-check
  7. Merge all sources into final.jsonl
  8. Generate final review HTML

Usage:
  python cli/finalize_ledger.py --case 680-1-4 --step suspects    # Step 6: identify suspects
  python cli/finalize_ledger.py --case 680-1-4 --step merge       # Step 7: merge final
  python cli/finalize_ledger.py --case 680-1-4 --step html --open # Step 8: generate HTML
  python cli/finalize_ledger.py --case 680-1-4 --step all --open  # All steps
"""

import json
import re
import argparse
import subprocess
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path("cli/dazho_downloads")


def load_rowmode(case_id: str) -> list[dict]:
    path = BASE_DIR / f"{case_id}_rowmode.jsonl"
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    return records


def load_claude_readings(case_id: str) -> dict[str, dict]:
    path = BASE_DIR / f"{case_id}_claude_readings.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {r["row_strip"]: r for r in data.get("readings", [])}


def load_corrections(case_id: str) -> dict[str, dict]:
    path = BASE_DIR / f"{case_id}_corrections.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {r["row_strip"]: r for r in data}


def is_skip_row(rec: dict, claude: dict | None, correction: dict | None = None) -> str | None:
    """Return skip reason or None if the row is data."""
    strip = rec.get("row_strip", "")
    gemini = rec.get("gemini", "") or ""

    if correction and correction.get("skip"):
        return correction.get("note", "correction_skip")

    if claude and claude.get("skip"):
        return claude.get("note", "skip")

    if rec.get("skipped"):
        return "skipped_in_source"

    row_num = 0
    m = re.search(r"row(\d+)", strip)
    if m:
        row_num = int(m.group(1))

    gemini_lower = gemini.lower()
    if "фамиліи" in gemini_lower and "имена" in gemini_lower:
        return "header"
    if "фамилии" in gemini_lower and "имена" in gemini_lower:
        return "header"

    skip_prefixes = ("Итого", "Подлежитъ", "АРКУШ", "Особливості", "Засвідчується",
                      "ERROR:", "избранными", "значитъ", "ditto")
    if any(gemini.startswith(p) for p in skip_prefixes):
        return "non_data_row"

    if row_num <= 3 and rec.get("seq_num") is None:
        return "likely_header_or_binding"
    if row_num <= 3 and isinstance(rec.get("seq_num"), int) and rec["seq_num"] > 500:
        return "likely_header_or_binding"

    return None


def modernize_name(name: str) -> str:
    """Normalize pre-revolutionary orthography to modern Russian.
    ъ before word boundary/punctuation → remove, і/i → и, ѣ → е."""
    name = re.sub(r"ъ(?=[-\s.,;:!?\"]|$)", "", name)
    name = name.replace("і", "и").replace("І", "И")
    name = name.replace("i", "и").replace("I", "И")
    name = name.replace("ѣ", "е").replace("Ѣ", "Е")
    name = name.replace("ѳ", "ф").replace("Ѳ", "Ф")
    return name


def extract_surname(name: str) -> str:
    """Extract surname (first word) from a full name string."""
    name = name.strip().strip("„").strip('"').strip()
    if not name:
        return ""
    parts = name.split()
    if parts:
        return parts[0]
    return ""


def propagate_ditto_surnames(records: list[dict]) -> list[dict]:
    """For rows where Gemini starts with 'Фамиліи' or ditto mark, 
    propagate the last known real surname."""
    last_real_surname = ""
    last_page = ""

    for rec in records:
        if rec.get("_skip"):
            continue

        page = rec.get("page", "")
        gemini = rec.get("gemini", "") or ""
        strip = rec.get("row_strip", "")

        row_num = 0
        m = re.search(r"row(\d+)", strip)
        if m:
            row_num = int(m.group(1))

        surname = extract_surname(gemini)

        surname_lower = surname.lower()
        is_ditto_prefix = surname_lower in ("фамиліи", "фамилии") or surname in ("„", '"')
        is_ditto_mark = gemini.startswith("„") or gemini.startswith('"')

        if is_ditto_prefix and last_real_surname:
            given = gemini.replace(surname, "", 1).strip()
            rec["_gemini_clean"] = f"{last_real_surname} {given}".strip()
            rec["_ditto_fixed"] = True
        elif is_ditto_mark and last_real_surname:
            given = gemini.lstrip("„").lstrip('"').strip()
            rec["_gemini_clean"] = f"{last_real_surname} {given}".strip()
            rec["_ditto_fixed"] = True
        else:
            rec["_gemini_clean"] = gemini
            skip_surnames = {"Итого", "Подлежитъ", "ФАМИЛІИ", "Фамиліи",
                             "Фамилии", "АРКУШ", "Особливості", "Засвідчується"}
            if surname and not any(surname.startswith(s) for s in skip_surnames):
                last_real_surname = surname

    return records


def compute_suspect_score(rec: dict) -> tuple[int, list[str]]:
    """Return (score, reasons) for how suspect a row is. Higher = more suspect."""
    score = 0
    reasons = []
    gemini = rec.get("gemini", "") or ""
    gpt4o = rec.get("gpt4o", "") or ""
    gemini_clean = rec.get("_gemini_clean", gemini)
    seq = rec.get("seq_num")

    gemini_surname = extract_surname(gemini_clean)
    gpt4o_surname = extract_surname(gpt4o)

    if rec.get("_ditto_fixed"):
        score += 3
        reasons.append("ditto_fixed")

    if gemini_surname.startswith("Фамиліи") or gemini_surname.startswith("Фамилии"):
        score += 5
        reasons.append("header_fragment_in_surname")

    if gpt4o_surname and gemini_surname and gpt4o_surname != gemini_surname:
        if gpt4o_surname[:3] != gemini_surname[:3]:
            score += 4
            reasons.append("surname_completely_different")
        else:
            score += 1
            reasons.append("surname_variant")

    if isinstance(seq, int) and seq > 300:
        score += 3
        reasons.append(f"seq_out_of_range={seq}")

    if seq is None:
        score += 1
        reasons.append("no_seq_num")

    if not gpt4o:
        score += 1
        reasons.append("gpt4o_empty")

    non_cyrillic = sum(1 for c in gemini if c.isalpha() and not ('\u0400' <= c <= '\u04ff'))
    if non_cyrillic > 2:
        score += 2
        reasons.append("non_cyrillic_chars")

    return score, reasons


def identify_suspects(records: list[dict], top_n: int = 60) -> list[dict]:
    """Identify the most suspect rows from filtered data records."""
    scored = []
    for rec in records:
        if rec.get("_skip"):
            continue
        if rec.get("consensus"):
            continue
        score, reasons = compute_suspect_score(rec)
        if score > 0:
            scored.append({
                "row_strip": rec["row_strip"],
                "page": rec.get("page", ""),
                "seq_num": rec.get("seq_num"),
                "gemini": rec.get("gemini", ""),
                "gemini_clean": rec.get("_gemini_clean", ""),
                "gpt4o": rec.get("gpt4o", ""),
                "score": score,
                "reasons": reasons,
            })

    scored.sort(key=lambda x: -x["score"])
    return scored[:top_n]


def merge_final(records: list[dict], claude_map: dict, corrections: dict) -> list[dict]:
    """Merge all sources into final records."""
    final = []
    seq_counter = 0
    last_seen_surname = ""

    for rec in records:
        if rec.get("_skip"):
            continue

        strip = rec.get("row_strip", "")
        page = rec.get("page", "")
        claude = claude_map.get(strip)
        correction = corrections.get(strip)

        gemini_clean = rec.get("_gemini_clean", rec.get("gemini", ""))

        entry = {
            "row_strip": strip,
            "page": page,
            "seq_num": rec.get("seq_num"),
            "gemini": rec.get("gemini", ""),
            "gemini_clean": gemini_clean,
            "gpt4o": rec.get("gpt4o", ""),
            "consensus": rec.get("consensus", False),
            "final_name": modernize_name(gemini_clean),
            "source": "gemini",
            "ditto_fixed": bool(rec.get("_ditto_fixed")),
        }

        if correction and correction.get("final_name"):
            entry["prev_correction"] = correction["final_name"]
        if claude and claude.get("claude_name") and not claude.get("skip"):
            entry["prev_claude"] = claude["claude_name"]

        surname = extract_surname(entry["final_name"])
        given = entry["final_name"].replace(surname, "", 1).strip() if surname else ""
        entry["surname"] = surname
        entry["given"] = given

        is_new_family = (surname != last_seen_surname) if surname else False
        entry["new_family"] = is_new_family
        if surname:
            last_seen_surname = surname

        seq_counter += 1
        entry["row_order"] = seq_counter

        final.append(entry)

    return final


def generate_final_html(case_id: str, final_records: list[dict], open_browser: bool = False):
    """Generate a clean final review HTML."""
    rows_dir = BASE_DIR / f"{case_id}_rows"
    pages_dir = BASE_DIR / f"{case_id}_pages"
    out_path = BASE_DIR / f"{case_id}_final_review.html"

    pages_dict = defaultdict(list)
    for rec in final_records:
        pages_dict[rec.get("page", "?")].append(rec)

    source_colors = {
        "correction": "#28a745",
        "claude": "#007bff",
        "consensus": "#6c757d",
        "gemini": "#fd7e14",
    }

    parts = [f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<title>{case_id} Final Review</title>
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:Arial,sans-serif; font-size:13px; background:#f0f0f0; }}
h1 {{ padding:10px 16px; background:#1a1a2e; color:#e0e0ff; font-size:16px; }}
h1 small {{ font-weight:normal; font-size:12px; opacity:0.7; }}
.legend {{ display:flex; gap:16px; padding:8px 16px; background:#fff; border-bottom:1px solid #ddd; font-size:11px; flex-wrap:wrap; }}
.legend span {{ display:flex; align-items:center; gap:4px; }}
.swatch {{ width:14px; height:14px; border-radius:2px; display:inline-block; }}
.page-block {{ display:flex; gap:10px; margin:12px; padding:10px; background:#fff; border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,.1); }}
.page-img {{ flex:0 0 320px; }}
.page-img img {{ width:100%; border:1px solid #ccc; cursor:zoom-in; border-radius:4px; }}
.page-img img:hover {{ box-shadow:0 0 0 2px #007bff; }}
.page-label {{ font-weight:bold; font-size:12px; margin-bottom:4px; color:#555; }}
.page-tables {{ flex:1; overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:12px; }}
th {{ background:#2c2c54; color:#fff; padding:4px 6px; text-align:left; font-size:11px; white-space:nowrap; }}
td {{ padding:3px 6px; border-bottom:1px solid #eee; vertical-align:top; }}
.col-seq {{ width:28px; color:#888; text-align:center; }}
.col-strip {{ width:300px; }}
.col-strip img {{ width:100%; border:1px solid #ccc; cursor:zoom-in; border-radius:3px; }}
.col-strip img:hover {{ box-shadow:0 0 0 2px #007bff; }}
.col-final {{ font-weight:bold; }}
.src-badge {{ font-size:9px; padding:1px 4px; border-radius:2px; color:#fff; margin-left:4px; vertical-align:middle; }}
#lb {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.88); z-index:9999; align-items:center; justify-content:center; cursor:zoom-out; }}
#lb.open {{ display:flex; }}
#lb img {{ max-width:96vw; max-height:96vh; object-fit:contain; box-shadow:0 0 50px rgba(0,0,0,.9); border:2px solid #fff; }}
#lb-close {{ position:fixed; top:12px; right:18px; font-size:34px; color:#fff; cursor:pointer; line-height:1; z-index:10000; }}
#lb-cap {{ position:fixed; bottom:14px; color:#ccc; font-size:12px; text-align:center; width:100%; pointer-events:none; }}
</style></head><body>
<h1>{case_id} · Final Review <small>({len(final_records)} records across {len(pages_dict)} pages)</small></h1>
<div class="legend">
  <span><span class="swatch" style="background:#28a745"></span> Correction (manual)</span>
  <span><span class="swatch" style="background:#007bff"></span> Claude reading</span>
  <span><span class="swatch" style="background:#6c757d"></span> Consensus (Gemini=GPT)</span>
  <span><span class="swatch" style="background:#fd7e14"></span> Gemini (primary)</span>
</div>
<div id="lb"><span id="lb-close">&#10005;</span><img id="lb-img" src="" alt=""><div id="lb-cap"></div></div>
"""]

    for page_name in sorted(pages_dict.keys()):
        page_records = pages_dict[page_name]
        img_path = pages_dir / page_name
        if img_path.exists():
            rel = img_path.relative_to(out_path.parent)
            page_img_html = f'<img src="{rel}" alt="{page_name}">'
        else:
            page_img_html = f'<span style="color:#999">no image</span>'

        parts.append(f"""
<div class="page-block" id="{page_name}">
  <div class="page-img">
    <div class="page-label">{page_name}</div>
    {page_img_html}
  </div>
  <div class="page-tables">
    <table>
      <tr>
        <th class="col-strip">Strip</th>
        <th class="col-seq">#</th>
        <th>Gemini</th>
        <th>GPT-4o</th>
        <th class="col-final">Final name</th>
      </tr>
""")

        for rec in page_records:
            strip_name = rec.get("row_strip", "")
            strip_path = rows_dir / strip_name
            if strip_path.exists():
                rel = strip_path.relative_to(out_path.parent)
                strip_html = f'<img src="{rel}" alt="{strip_name}">'
            else:
                strip_html = strip_name

            src = rec.get("source", "gemini")
            color = source_colors.get(src, "#999")
            badge = f'<span class="src-badge" style="background:{color}">{src}</span>'

            parts.append(
                f'<tr>'
                f'<td class="col-strip">{strip_html}</td>'
                f'<td class="col-seq">{rec.get("seq_num") or ""}</td>'
                f'<td>{rec.get("gemini", "")}</td>'
                f'<td>{rec.get("gpt4o", "")}</td>'
                f'<td class="col-final">{rec.get("final_name", "")}{badge}</td>'
                f'</tr>\n'
            )

        parts.append("</table></div></div>\n")

    parts.append("""<script>
const lb=document.getElementById('lb'),lbI=document.getElementById('lb-img'),lbC=document.getElementById('lb-cap');
document.querySelectorAll('.page-img img, .col-strip img').forEach(i=>{
  i.addEventListener('click',()=>{lbI.src=i.src;lbC.textContent=i.alt;lb.classList.add('open');});
});
lb.addEventListener('click',e=>{if(e.target!==lbI)lb.classList.remove('open');});
document.getElementById('lb-close').addEventListener('click',()=>lb.classList.remove('open'));
document.addEventListener('keydown',e=>{if(e.key==='Escape')lb.classList.remove('open');});
</script></body></html>""")

    out_path.write_text("".join(parts), encoding="utf-8")
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"Written: {out_path}  ({size_mb:.1f} MB)")
    if open_browser:
        subprocess.run(["open", str(out_path)])


def main():
    parser = argparse.ArgumentParser(description="Finalize DAZHO ledger OCR data")
    parser.add_argument("--case", default="680-1-4")
    parser.add_argument("--step", choices=["suspects", "merge", "html", "all"], default="all")
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--top-suspects", type=int, default=60)
    args = parser.parse_args()

    print(f"Loading {args.case} data...")
    records = load_rowmode(args.case)
    claude_map = load_claude_readings(args.case)
    corrections = load_corrections(args.case)
    print(f"  {len(records)} rowmode records, {len(claude_map)} claude readings, {len(corrections)} corrections")

    for rec in records:
        strip = rec.get("row_strip", "")
        claude = claude_map.get(strip)
        correction = corrections.get(strip)
        skip_reason = is_skip_row(rec, claude, correction)
        if skip_reason:
            rec["_skip"] = skip_reason

    records = propagate_ditto_surnames(records)

    data_rows = [r for r in records if not r.get("_skip")]
    skip_rows = [r for r in records if r.get("_skip")]
    print(f"  {len(data_rows)} data rows, {len(skip_rows)} filtered out")

    if args.step in ("suspects", "all"):
        suspects = identify_suspects(records, top_n=args.top_suspects)
        suspect_path = BASE_DIR / f"{args.case}_suspects.json"
        suspect_path.write_text(json.dumps(suspects, ensure_ascii=False, indent=2))
        print(f"\n=== Top {len(suspects)} suspect rows ===")
        for i, s in enumerate(suspects[:20], 1):
            print(f"  {i:2d}. [{s['score']:2d}] {s['row_strip']}: "
                  f"G={s['gemini']!r} → clean={s['gemini_clean']!r} "
                  f"| reasons={', '.join(s['reasons'])}")
        if len(suspects) > 20:
            print(f"  ... and {len(suspects) - 20} more (see {suspect_path})")
        print(f"\nSaved to {suspect_path}")

    if args.step in ("merge", "all"):
        final = merge_final(records, claude_map, corrections)
        final_path = BASE_DIR / f"{args.case}_final.jsonl"
        with open(final_path, "w") as f:
            for entry in final:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        source_counts = defaultdict(int)
        for e in final:
            source_counts[e.get("source", "?")] += 1
        print(f"\n=== Final merge: {len(final)} records ===")
        for src, cnt in sorted(source_counts.items()):
            print(f"  {src}: {cnt}")
        print(f"Saved to {final_path}")

    if args.step in ("html", "all"):
        final_path = BASE_DIR / f"{args.case}_final.jsonl"
        if final_path.exists():
            final = []
            with open(final_path) as f:
                for line in f:
                    if line.strip():
                        final.append(json.loads(line))
            generate_final_html(args.case, final, open_browser=args.open)
        else:
            print(f"ERROR: {final_path} not found. Run --step merge first.")


if __name__ == "__main__":
    main()
