"""Server-side rendering of the model's ```records JSON block.

The model is instructed to return records as a fenced JSON array in the
final answer. The raw JSON never reaches the user: the server renders a
markdown table appropriate for the tier — teaser gets masked names (via
record_filter) and a lock glyph instead of ciphers/links, full gets
everything including a clickable URL.
"""

import json
import logging
from typing import Any, Literal

from app.services.record_filter import filter_record

logger = logging.getLogger("jroots")

TEASER_LOCK = "🔒 доступно в полной версии"

_TEASER_HEADER = (
    "| Тип | Место | Период | Имена | Запись |",
    "|---|---|---|---|---|",
)
_FULL_HEADER = (
    "| Тип | Место | Период | Имена | Архив | Шифр | Ссылка |",
    "|---|---|---|---|---|---|---|",
)


def render_records(block_text: str, tier: Literal["teaser", "full"]) -> str | None:
    """Parse the fenced-block JSON and render the records table.

    Returns None when the payload is not a JSON array (caller decides:
    teaser drops the block silently, full passes it through raw).
    """
    try:
        payload = json.loads(block_text)
    except (json.JSONDecodeError, ValueError):
        logger.info("records block did not parse (tier=%s)", tier)
        return None
    if not isinstance(payload, list):
        return None
    records = [rec for rec in payload if isinstance(rec, dict)]
    if tier == "teaser":
        records = [filter_record(rec, "teaser") for rec in records]
    return _render_table(records, tier)


def _cell(value: Any) -> str:
    """Markdown-table cell: scalar or list joined; pipes and newlines out."""
    if value is None:
        return ""
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value)
    return str(value).replace("|", "/").replace("\n", " ").strip()


def _period(rec: dict) -> str:
    return _cell(rec.get("period") or rec.get("date") or rec.get("year"))


def _render_table(records: list[dict], tier: str) -> str:
    if not records:
        return ""
    if tier == "teaser":
        lines = [*_TEASER_HEADER]
        for rec in records:
            lines.append(
                "| {} | {} | {} | {} | {} |".format(
                    _cell(rec.get("type")),
                    _cell(rec.get("place")),
                    _period(rec),
                    _cell(rec.get("names")),
                    TEASER_LOCK,
                )
            )
        return "\n".join(lines)

    lines = [*_FULL_HEADER]
    for rec in records:
        url = rec.get("url")
        link = f"[открыть]({_cell(url)})" if url else ""
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                _cell(rec.get("type")),
                _cell(rec.get("place")),
                _period(rec),
                _cell(rec.get("names")),
                _cell(rec.get("archive") or rec.get("archive_region")),
                _cell(rec.get("cipher")),
                link,
            )
        )
    return "\n".join(lines)
