#!/usr/bin/env python3
"""Sync ~/.jroots/cases/ and reports to Outline Wiki.

For cases WITH a professional report (~/.jroots/reports/{stem}-report.md):
  converts custom ::: directives to clean Markdown + appends JSON.

For cases WITHOUT a report: minimal metadata card + JSON only.
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

API_URL = "https://wiki.jroots.co/api"
API_TOKEN = "ol_api_QXvjG7fQTA9Nsu3YlW0v2c5Nm1ExRvC3lVkWB4"
COLLECTION_ID = "af878370-f689-4398-8495-1c3bd9c1beef"
CASES_DIR = Path.home() / ".jroots" / "cases"
REPORTS_DIR = Path.home() / ".jroots" / "reports"


def api(endpoint, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{API_URL}/{endpoint}", data=data,
        headers={"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def find_report(case_stem):
    path = REPORTS_DIR / f"{case_stem}-report.md"
    return path.read_text() if path.exists() else None


# --------------- mermaid tree from JSON relationships ---------------

def _sanitize_mermaid(text):
    return text.replace('"', "'").replace("\n", " ").replace("(", "").replace(")", "")


def _get_person_name(persons, pid):
    if isinstance(persons, dict):
        p = persons.get(pid, {})
    elif isinstance(persons, list):
        p = next((x for x in persons if x.get("id") == pid), {})
    else:
        return pid
    name = (p.get("name") or p.get("name_ru") or p.get("full_name")
            or p.get("canonical_name", pid))
    parts = name.split()
    if len(parts) >= 2:
        name = f"{parts[0]} {parts[1]}"
    birth = p.get("birth_year") or p.get("birth_date") or p.get("birth_year_approx", "")
    if birth:
        return f"{name}, {str(birth)[:4]}"
    return name


def _normalize_rel(r):
    rtype = r.get("type", "").lower().strip()
    p1 = r.get("from") or r.get("person1") or r.get("parent", "")
    p2 = r.get("to") or r.get("person2") or r.get("child", "")
    if not p1 and r.get("grandparent"):
        p1, p2 = r["grandparent"], r.get("grandchild", "")

    spouse_kw = {"spouse", "marriage", "partner", "супруг", "супруги", "брак",
                 "connected (marriage)", "second_marriage_1901"}
    if any(s in rtype for s in spouse_kw) or rtype.startswith("брак"):
        return ("spouse", p1, p2)

    parent_kw = {"parent", "parent-child", "parent_child", "father", "mother",
                 "отец", "мать", "отец-сын", "отец-дочь", "мать-сын", "мать-дочь"}
    if rtype in parent_kw or rtype.startswith("отец") or rtype.startswith("мать"):
        return ("parent", p1, p2)
    if rtype == "child_of":
        return ("parent", p2, p1)
    if rtype in {"son", "daughter", "grandparent"}:
        return ("parent", p1, p2)
    return None


def build_family_tree(persons, relationships):
    if not relationships:
        return ""
    parent_edges, spouse_edges, seen = [], [], set()
    for r in relationships:
        norm = _normalize_rel(r)
        if not norm:
            continue
        if norm[0] == "spouse":
            _, a, b = norm
            if a and b:
                spouse_edges.append((a, b))
                seen.update([a, b])
        elif norm[0] == "parent":
            _, par, ch = norm
            if par and ch:
                parent_edges.append((par, ch))
                seen.update([par, ch])
    if not seen:
        return ""
    lines = ["```mermaidjs", "flowchart TD"]
    for pid in sorted(seen):
        label = _sanitize_mermaid(_get_person_name(persons, pid))
        lines.append(f'    {pid}["{label}"]')
    for a, b in spouse_edges:
        lines.append(f"    {a} --- {b}")
    for par, ch in parent_edges:
        lines.append(f"    {par} --> {ch}")
    lines.append("```")
    return "\n".join(lines)


# --------------- directive → clean Markdown converter ---------------

def convert_directives(text, case):
    """Convert custom ::: directives to clean Markdown for Outline Wiki."""
    lines = text.split("\n")
    out = []
    i = 0

    while i < len(lines):
        s = lines[i].strip()

        if re.match(r"^:::\s*personcard", s):
            i = _copy_until_close(lines, i + 1, out)
            continue

        if re.match(r"^:::\s*timeline", s):
            i = _copy_until_close(lines, i + 1, out)
            continue

        if re.match(r"^:::\s*tree", s):
            i = _skip_block(lines, i + 1)
            tree = build_family_tree(case.get("persons"), case.get("relationships"))
            if tree:
                out += ["", tree, ""]
            continue

        if re.match(r"^:::\s*discovery", s):
            i = _convert_discovery(lines, i + 1, out)
            continue

        if re.match(r"^:::\s*info", s):
            i = _convert_callout(lines, i + 1, out, prefix="*", suffix="*")
            continue

        if re.match(r"^:::\s*warning", s):
            i = _convert_callout(lines, i + 1, out, prefix="**Внимание:** ")
            continue

        if s == ":::":
            i += 1
            continue

        out.append(lines[i])
        i += 1

    return "\n".join(out)


def _copy_until_close(lines, i, out):
    """Copy lines verbatim until a standalone :::."""
    while i < len(lines) and lines[i].strip() != ":::":
        out.append(lines[i])
        i += 1
    return i + 1


def _skip_block(lines, i):
    """Skip lines until the matching ::: close (handles nesting)."""
    depth = 1
    while i < len(lines) and depth > 0:
        s = lines[i].strip()
        if s == ":::":
            depth -= 1
        elif re.match(r"^:::\s*\w", s):
            depth += 1
        i += 1
    return i


def _convert_discovery(lines, i, out):
    """Convert ::: discovery block to blockquote, handling nested info/warning."""
    buf = []
    depth = 1
    while i < len(lines) and depth > 0:
        s = lines[i].strip()

        if s == ":::":
            depth -= 1
            if depth == 0:
                i += 1
                break
            i += 1
            continue

        if re.match(r"^:::\s*info", s):
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                t = lines[i].strip()
                buf.append(f"*{t}*" if t else "")
                i += 1
            i += 1
            continue

        if re.match(r"^:::\s*warning", s):
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                t = lines[i].strip()
                buf.append(f"**Внимание:** {t}" if t else "")
                i += 1
            i += 1
            continue

        buf.append(lines[i])
        i += 1

    for line in buf:
        out.append(f"> {line}" if line.strip() else ">")
    out.append("")
    return i


def _convert_callout(lines, i, out, prefix="", suffix=""):
    """Convert standalone ::: info / ::: warning to blockquote."""
    while i < len(lines) and lines[i].strip() != ":::":
        t = lines[i].strip()
        if t:
            out.append(f"> {prefix}{t}{suffix}")
        else:
            out.append(">")
        i += 1
    out.append("")
    return i + 1


# --------------- document assembly ---------------

def _json_block(case):
    raw = json.dumps(case, indent=2, ensure_ascii=False)
    return f"\n---\n\n<details><summary>JSON кейса</summary>\n\n```json\n{raw}\n```\n\n</details>"


def doc_with_report(report_text, case):
    return convert_directives(report_text, case) + _json_block(case)


def doc_without_report(case, filename):
    meta = case.get("metadata", {})
    title = meta.get("title", filename.replace(".json", "").replace("-", " ").title())
    parts = [f"# {title}\n"]

    rows = []
    for key, label in [
        ("goal", "Цель"), ("client", "Клиент"), ("status", "Статус"),
        ("research_status", "Статус исследования"),
        ("regions", "Регионы"), ("time_period", "Период"),
        ("conclusion", "Вывод"), ("key_finding", "Ключевая находка"),
        ("created", "Создан"), ("updated", "Обновлён"),
    ]:
        val = meta.get(key)
        if val:
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            rows.append(f"| {label} | {str(val).replace('|', '/')} |")

    if rows:
        parts.append("| Параметр | Значение |")
        parts.append("|----------|----------|")
        parts.extend(rows)
        parts.append("")

    return "\n".join(parts) + _json_block(case)


# --------------- main ---------------

def delete_all_docs_in_collection():
    result = api("documents.list", {"collectionId": COLLECTION_ID, "limit": 100})
    docs = result.get("data", [])
    for d in docs:
        api("documents.delete", {"id": d["id"]})
    if docs:
        print(f"Deleted {len(docs)} existing documents")


def main():
    cases = sorted(CASES_DIR.glob("*.json"))
    if not cases:
        print(f"No cases found in {CASES_DIR}")
        sys.exit(1)

    print(f"Found {len(cases)} cases in {CASES_DIR}")

    if "--replace" in sys.argv:
        delete_all_docs_in_collection()

    reports_found = 0
    for path in cases:
        with open(path) as f:
            case = json.load(f)

        report = find_report(path.stem)
        title = case.get("metadata", {}).get("title", path.stem.replace("-", " ").title())

        if report:
            md = doc_with_report(report, case)
            tag = "report"
            reports_found += 1
        else:
            md = doc_without_report(case, path.name)
            tag = "json-only"

        result = api("documents.create", {
            "title": title,
            "collectionId": COLLECTION_ID,
            "text": md,
            "publish": True,
        })
        doc_id = result["data"]["id"]
        print(f"  [{tag}] {path.name} -> {doc_id} ({title})")

    print(f"\nDone! {len(cases)} cases ({reports_found} with reports) -> collection {COLLECTION_ID}")


if __name__ == "__main__":
    main()
