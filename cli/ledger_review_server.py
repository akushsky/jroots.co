#!/usr/bin/env python3
"""
ledger_review_server.py — Interactive review server for DAZHO ledger OCR results.

Serves the final.jsonl data with inline editing, strip/page images,
and saves corrections back to disk.

Usage:
  python cli/ledger_review_server.py --case 680-1-4
  python cli/ledger_review_server.py --case 680-1-4 --port 8090
"""

import argparse
import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BASE_DIR = Path("cli/dazho_downloads")
CASE_ID = "680-1-4"
PORT = 8090


def load_final():
    path = BASE_DIR / f"{CASE_ID}_final.jsonl"
    records = []
    if path.exists():
        with open(path) as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
    return records


def save_final(records):
    path = BASE_DIR / f"{CASE_ID}_final.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_corrections():
    path = BASE_DIR / f"{CASE_ID}_corrections.json"
    if path.exists():
        return json.loads(path.read_text())
    return []


def save_corrections(corrections):
    path = BASE_DIR / f"{CASE_ID}_corrections.json"
    path.write_text(json.dumps(corrections, ensure_ascii=False, indent=2))


class LedgerHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(build_html().encode("utf-8"))

        elif parsed.path == "/api/data":
            records = load_final()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(records, ensure_ascii=False).encode("utf-8"))

        elif parsed.path.startswith("/img/rows/"):
            filename = parsed.path[len("/img/rows/"):]
            img_path = BASE_DIR / f"{CASE_ID}_rows" / filename
            self._serve_image(img_path)

        elif parsed.path.startswith("/img/pages/"):
            filename = parsed.path[len("/img/pages/"):]
            img_path = BASE_DIR / f"{CASE_ID}_pages" / filename
            self._serve_image(img_path)

        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/save":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            edits = json.loads(body)

            records = load_final()
            rec_map = {r["row_strip"]: r for r in records}
            corrections = load_corrections()
            corr_map = {c["row_strip"]: c for c in corrections}

            changed = 0
            for edit in edits:
                strip = edit["row_strip"]
                new_name = edit["final_name"].strip()
                if strip in rec_map:
                    old_name = rec_map[strip].get("final_name", "")
                    if new_name != old_name:
                        rec_map[strip]["final_name"] = new_name
                        rec_map[strip]["source"] = "correction"
                        parts = new_name.split()
                        rec_map[strip]["surname"] = parts[0] if parts else ""
                        rec_map[strip]["given"] = " ".join(parts[1:]) if len(parts) > 1 else ""

                        corr_map[strip] = {
                            "row_strip": strip,
                            "final_name": new_name,
                            "note": f"edited from: {old_name}",
                        }
                        changed += 1

            save_final(list(rec_map.values()))
            save_corrections(list(corr_map.values()))

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "changed": changed}).encode("utf-8"))

        elif self.path == "/api/skip":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
            strip = data.get("row_strip", "")

            records = load_final()
            records = [r for r in records if r.get("row_strip") != strip]
            save_final(records)

            corrections = load_corrections()
            corr_map = {c["row_strip"]: c for c in corrections}
            corr_map[strip] = {"row_strip": strip, "skip": True, "note": "marked_skip_in_review"}
            save_corrections(list(corr_map.values()))

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "skipped": strip}).encode("utf-8"))
        else:
            self.send_error(404)

    def _serve_image(self, img_path: Path):
        if img_path.exists() and img_path.suffix.lower() in (".jpg", ".jpeg", ".png"):
            mime = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(img_path.read_bytes())
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        status = args[1] if len(args) > 1 else ""
        if str(status).startswith("4") or str(status).startswith("5"):
            SimpleHTTPRequestHandler.log_message(self, fmt, *args)


def build_html():
    return """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>""" + CASE_ID + """ — Ledger Review</title>
<style>
:root {
  --bg: #f5f5f5; --card: #fff; --border: #e0e0e0;
  --green: #28a745; --blue: #007bff; --gray: #6c757d; --orange: #fd7e14;
  --red: #dc3545; --dark: #1a1a2e;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; font-size: 13px; background: var(--bg); color: #333; }

header {
  position: sticky; top: 0; z-index: 100;
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  padding: 10px 16px; background: var(--dark); color: #e0e0ff;
}
header h1 { font-size: 15px; font-weight: 600; }
header .stats { font-size: 11px; opacity: 0.7; }
header .actions { margin-left: auto; display: flex; gap: 8px; }
header button {
  padding: 5px 14px; border: none; border-radius: 4px; font-size: 12px;
  cursor: pointer; font-weight: 600; transition: opacity .15s;
}
header button:hover { opacity: 0.85; }
.btn-save { background: var(--green); color: #fff; }
.btn-export { background: var(--blue); color: #fff; }
.btn-save:disabled { background: #999; cursor: default; }
.save-status { font-size: 11px; color: #8f8; padding: 4px 8px; }

.legend {
  display: flex; gap: 14px; padding: 6px 16px; background: #fff;
  border-bottom: 1px solid var(--border); font-size: 11px; flex-wrap: wrap;
}
.legend span { display: flex; align-items: center; gap: 4px; }
.swatch { width: 12px; height: 12px; border-radius: 2px; display: inline-block; }

.filter-bar {
  display: flex; gap: 12px; padding: 8px 16px; background: #fafafa;
  border-bottom: 1px solid var(--border); font-size: 12px; align-items: center;
}
.filter-bar label { display: flex; align-items: center; gap: 4px; cursor: pointer; }
.filter-bar input[type=text] {
  padding: 3px 8px; border: 1px solid #ccc; border-radius: 3px; width: 200px;
}

.page-block {
  display: flex; gap: 10px; margin: 10px 12px; padding: 10px;
  background: var(--card); border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,.08);
}
.page-img { flex: 0 0 280px; }
.page-img img { width: 100%; border: 1px solid #ddd; border-radius: 4px; cursor: zoom-in; }
.page-label { font-weight: 600; font-size: 11px; color: #666; margin-bottom: 4px; }
.page-tables { flex: 1; overflow-x: auto; }

table { border-collapse: collapse; width: 100%; font-size: 12px; }
th { background: #2c2c54; color: #fff; padding: 4px 6px; text-align: left; font-size: 11px; white-space: nowrap; position: sticky; top: 0; }
td { padding: 3px 6px; border-bottom: 1px solid #eee; vertical-align: middle; }
.col-seq { width: 30px; text-align: center; color: #888; }
.col-strip { width: 320px; }
.col-strip img { width: 100%; border: 1px solid #ddd; border-radius: 3px; cursor: zoom-in; }
.col-strip img:hover { box-shadow: 0 0 0 2px var(--blue); }
.col-models { color: #666; font-size: 11px; min-width: 120px; }

.name-input {
  width: 100%; padding: 3px 6px; border: 1px solid #ddd; border-radius: 3px;
  font-size: 13px; font-weight: 600; font-family: inherit;
  transition: border-color .15s, background .15s;
}
.name-input:focus { outline: none; border-color: var(--blue); background: #f0f6ff; }
.name-input.edited { border-color: var(--orange); background: #fff8f0; }

.src-badge {
  display: inline-block; font-size: 9px; padding: 1px 5px; border-radius: 2px;
  color: #fff; vertical-align: middle; margin-left: 4px;
}
.btn-skip {
  background: none; border: 1px solid #ddd; border-radius: 3px;
  padding: 1px 6px; font-size: 10px; cursor: pointer; color: #999;
}
.btn-skip:hover { border-color: var(--red); color: var(--red); }

tr.row-edited td { background: #fff8f0; }
tr.row-surname td { border-left: 4px solid var(--green); }
tr.row-ditto td { border-left: 4px solid #e0e0e0; }
.ditto-badge { display:inline-block; font-size:9px; padding:1px 5px; border-radius:2px; background:#e0e0e0; color:#666; vertical-align:middle; margin-left:4px; }
.surname-badge { display:inline-block; font-size:9px; padding:1px 5px; border-radius:2px; background:var(--green); color:#fff; vertical-align:middle; margin-left:4px; }

#lb { display:none; position:fixed; inset:0; background:rgba(0,0,0,.88);
      z-index:9999; align-items:center; justify-content:center; cursor:zoom-out; }
#lb.open { display:flex; }
#lb img { max-width:96vw; max-height:96vh; object-fit:contain;
          box-shadow:0 0 50px rgba(0,0,0,.9); border:2px solid #fff; }
#lb-close { position:fixed; top:12px; right:18px; font-size:34px; color:#fff;
            cursor:pointer; line-height:1; z-index:10000; }
#lb-cap { position:fixed; bottom:14px; color:#ccc; font-size:12px;
          text-align:center; width:100%; pointer-events:none; }

.kbd { background: #eee; border: 1px solid #ccc; border-radius: 3px; padding: 0 4px; font-size: 10px; }
</style>
</head>
<body>

<header>
  <h1>""" + CASE_ID + """ · Ledger Review</h1>
  <span class="stats" id="stats"></span>
  <div class="actions">
    <span class="save-status" id="save-status"></span>
    <button class="btn-save" id="btn-save" disabled>Save (Ctrl+S)</button>
    <button class="btn-export" id="btn-export">Export JSON</button>
  </div>
</header>

<div class="legend">
  <span><span class="swatch" style="background:var(--green)"></span> Correction</span>
  <span><span class="swatch" style="background:var(--blue)"></span> Claude</span>
  <span><span class="swatch" style="background:var(--gray)"></span> Consensus</span>
  <span><span class="swatch" style="background:var(--orange)"></span> Gemini</span>
  <span style="margin-left:auto; color:#888;">
    <span class="kbd">Tab</span> next field &nbsp;
    <span class="kbd">Shift+Tab</span> prev &nbsp;
    <span class="kbd">Ctrl+S</span> save
  </span>
</div>

<div class="filter-bar">
  <label><input type="checkbox" id="filter-edited"> Show only edited</label>
  <label><input type="checkbox" id="filter-gemini-only"> Gemini-only (no consensus)</label>
  <label><input type="checkbox" id="filter-ditto"> Ditto (members) only</label>
  <label><input type="checkbox" id="filter-heads"> Heads only</label>
  <input type="text" id="filter-search" placeholder="Search name...">
</div>

<div id="content"></div>

<div id="lb"><span id="lb-close">&#10005;</span><img id="lb-img" src="" alt=""><div id="lb-cap"></div></div>

<script>
const SRC_COLORS = {correction:'#28a745', claude:'#007bff', consensus:'#6c757d', gemini:'#fd7e14'};
let DATA = [];
let EDITS = {};

async function loadData() {
  const resp = await fetch('/api/data');
  DATA = await resp.json();
  render();
  updateStats();
}

function updateStats() {
  const total = DATA.length;
  const edited = Object.keys(EDITS).length;
  const bySrc = {};
  DATA.forEach(r => { bySrc[r.source] = (bySrc[r.source]||0)+1; });
  const parts = Object.entries(bySrc).map(([s,c]) => `${s}: ${c}`).join(' · ');
  document.getElementById('stats').textContent = `${total} records · ${parts}` + (edited ? ` · ${edited} edited` : '');
  document.getElementById('btn-save').disabled = edited === 0;
}

function render() {
  const filterEdited = document.getElementById('filter-edited').checked;
  const filterGemini = document.getElementById('filter-gemini-only').checked;
  const filterDitto = document.getElementById('filter-ditto').checked;
  const filterHeads = document.getElementById('filter-heads').checked;
  const searchTerm = document.getElementById('filter-search').value.toLowerCase();

  const pages = {};
  DATA.forEach(r => {
    if (filterEdited && !EDITS[r.row_strip]) return;
    if (filterGemini && r.source !== 'gemini') return;
    if (filterDitto && r.new_family) return;
    if (filterHeads && !r.new_family) return;
    if (searchTerm && !(r.final_name||'').toLowerCase().includes(searchTerm)
        && !(r.gemini||'').toLowerCase().includes(searchTerm)
        && !(r.gpt4o||'').toLowerCase().includes(searchTerm)) return;
    const p = r.page || '?';
    if (!pages[p]) pages[p] = [];
    pages[p].push(r);
  });

  let html = '';
  Object.keys(pages).sort().forEach(pageName => {
    const recs = pages[pageName];
    html += `<div class="page-block" id="${pageName}">
      <div class="page-img">
        <div class="page-label">${pageName}</div>
        <img src="/img/pages/${pageName}" alt="${pageName}" class="zoomable">
      </div>
      <div class="page-tables"><table>
        <tr><th class="col-strip">Strip</th><th class="col-seq">#</th>
        <th class="col-models">Gemini (raw)</th>
        <th style="min-width:240px">Final name (editable)</th><th style="width:30px"></th></tr>`;

    recs.forEach(r => {
      const edited = !!EDITS[r.row_strip];
      const val = EDITS[r.row_strip] || r.final_name || '';
      const isNewFamily = r.new_family;
      const rowCls = [edited ? 'row-edited' : '', isNewFamily ? 'row-surname' : 'row-ditto'].filter(Boolean).join(' ');
      const typeBadge = isNewFamily ? '<span class="surname-badge">new</span>' : '';
      html += `<tr class="${rowCls}" data-strip="${r.row_strip}">
        <td class="col-strip"><img src="/img/rows/${r.row_strip}" alt="${r.row_strip}" class="zoomable"></td>
        <td class="col-seq">${r.seq_num || ''}</td>
        <td class="col-models">${r.gemini || ''}</td>
        <td><input class="name-input ${edited?'edited':''}" value="${esc(val)}"
            data-strip="${r.row_strip}" data-orig="${esc(r.final_name||'')}">${typeBadge}${edited ? '<span class="src-badge" style="background:#fd7e14">edited</span>' : ''}</td>
        <td><button class="btn-skip" data-strip="${r.row_strip}" title="Remove row">&#10005;</button></td>
      </tr>`;
    });
    html += '</table></div></div>';
  });

  document.getElementById('content').innerHTML = html;
  bindEvents();
}

function esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;'); }

function bindEvents() {
  document.querySelectorAll('.name-input').forEach(inp => {
    inp.addEventListener('input', () => {
      const strip = inp.dataset.strip;
      const orig = inp.dataset.orig;
      const newVal = inp.value.trim();
      if (newVal !== orig) {
        EDITS[strip] = newVal;
        inp.classList.add('edited');
        inp.closest('tr').classList.add('row-edited');
      } else {
        delete EDITS[strip];
        inp.classList.remove('edited');
        inp.closest('tr').classList.remove('row-edited');
      }

      const rec = DATA.find(r => r.row_strip === strip);
      if (rec && rec.new_family) {
        const oldSurname = (orig || '').split(' ')[0];
        const newSurname = newVal.split(' ')[0];
        if (oldSurname && newSurname && oldSurname !== newSurname) {
          const idx = DATA.indexOf(rec);
          for (let i = idx + 1; i < DATA.length; i++) {
            const m = DATA[i];
            if (m.new_family) break;
            const mOrig = m.final_name || '';
            const mSurname = mOrig.split(' ')[0];
            if (mSurname === oldSurname) {
              const mNew = newSurname + mOrig.slice(oldSurname.length);
              EDITS[m.row_strip] = mNew;
              const mInp = document.querySelector(`input[data-strip="${m.row_strip}"]`);
              if (mInp) {
                mInp.value = mNew;
                mInp.classList.add('edited');
                mInp.closest('tr').classList.add('row-edited');
              }
            }
          }
        }
      }

      updateStats();
    });
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const tr = inp.closest('tr');
        const next = tr.nextElementSibling;
        if (next) next.querySelector('.name-input')?.focus();
      }
    });
  });

  document.querySelectorAll('.btn-skip').forEach(btn => {
    btn.addEventListener('click', async () => {
      const strip = btn.dataset.strip;
      if (!confirm(`Remove ${strip}?`)) return;
      await fetch('/api/skip', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({row_strip: strip}),
      });
      btn.closest('tr').remove();
      DATA = DATA.filter(r => r.row_strip !== strip);
      delete EDITS[strip];
      updateStats();
    });
  });

  document.querySelectorAll('.zoomable').forEach(img => {
    img.addEventListener('click', () => {
      document.getElementById('lb-img').src = img.src;
      document.getElementById('lb-cap').textContent = img.alt;
      document.getElementById('lb').classList.add('open');
    });
  });
}

async function saveEdits() {
  const edits = Object.entries(EDITS).map(([strip, name]) => ({row_strip: strip, final_name: name}));
  if (!edits.length) return;

  const status = document.getElementById('save-status');
  status.textContent = 'Saving...';

  const resp = await fetch('/api/save', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(edits),
  });
  const result = await resp.json();

  if (result.ok) {
    status.textContent = `Saved ${result.changed} changes`;
    DATA.forEach(r => {
      if (EDITS[r.row_strip]) {
        r.final_name = EDITS[r.row_strip];
        r.source = 'correction';
      }
    });
    EDITS = {};
    render();
    updateStats();
    setTimeout(() => { status.textContent = ''; }, 3000);
  }
}

function exportJSON() {
  const blob = new Blob([JSON.stringify(DATA, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = '""" + CASE_ID + """_final_export.json';
  a.click();
}

document.getElementById('btn-save').addEventListener('click', saveEdits);
document.getElementById('btn-export').addEventListener('click', exportJSON);
document.getElementById('filter-edited').addEventListener('change', render);
document.getElementById('filter-gemini-only').addEventListener('change', render);
document.getElementById('filter-ditto').addEventListener('change', render);
document.getElementById('filter-heads').addEventListener('change', render);
document.getElementById('filter-search').addEventListener('input', render);

const lb = document.getElementById('lb');
lb.addEventListener('click', e => { if (e.target !== document.getElementById('lb-img')) lb.classList.remove('open'); });
document.getElementById('lb-close').addEventListener('click', () => lb.classList.remove('open'));
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') lb.classList.remove('open');
  if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); saveEdits(); }
});

loadData();
</script>
</body>
</html>"""


def main():
    global CASE_ID, PORT

    parser = argparse.ArgumentParser(description="Ledger review server with inline editing")
    parser.add_argument("--case", default="680-1-4", help="Case ID")
    parser.add_argument("--port", type=int, default=8090, help="Server port")
    args = parser.parse_args()

    CASE_ID = args.case
    PORT = args.port

    final_path = BASE_DIR / f"{CASE_ID}_final.jsonl"
    rows_dir = BASE_DIR / f"{CASE_ID}_rows"

    if not final_path.exists():
        print(f"ERROR: {final_path} not found. Run finalize_ledger.py first.")
        return
    if not rows_dir.exists():
        print(f"ERROR: {rows_dir} not found.")
        return

    records = load_final()
    print(f"Ledger Review Server")
    print(f"  Case:    {CASE_ID}")
    print(f"  Records: {len(records)}")
    print(f"  Rows:    {rows_dir}")
    print(f"  URL:     http://localhost:{PORT}")
    print(f"\n  Ctrl+S in browser = save edits to disk")
    print(f"  Press Ctrl+C to stop\n")

    server = HTTPServer(("", PORT), LedgerHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
