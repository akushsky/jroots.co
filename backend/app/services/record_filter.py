"""Server-side record filtering for the teaser/full paywall matrix.

Free users see a "teaser": enough to judge whether a record is relevant, but
never the exact archive cipher or links. Safe-by-default: only whitelisted
presentation fields survive at the top level; their values are then cleaned
recursively (cipher keys — English and Russian — links, file paths, name
masking), plus a defense-in-depth value scan that drops URL-looking strings
and masks cipher-looking strings wherever they hide.
"""

import re
from typing import Any, Literal

# Top-level fields allowed into a teaser (safe-by-default whitelist).
KEEP_FIELDS = frozenset(
    {
        "type",
        "record_type",
        "place",
        "period",
        "date",
        "year",
        "archive_region",
        "match_count",
        "names",
        "notes",
        "summary",
        "description",
    }
)

# String values under these keys are masked (recursively) in a teaser.
NAME_FIELDS = frozenset(
    {
        "name",
        "names",
        "surname",
        "first_name",
        "last_name",
        "patronymic",
        "middle_name",
        "maiden_name",
        "fio",
        "person",
        "people",
        "full_name",
        "фамилия",
        "имя",
        "отчество",
        "фамилия_лат",
    }
)

# Removed from a teaser completely, at any nesting depth (exact ciphers,
# links, file paths, ordering hints) — English and Russian keys.
DROP_FIELDS = frozenset(
    {
        "cipher",
        "fond",
        "opis",
        "delo",
        "case_number",
        "fund_number",
        "inventory_number",
        "record_url",
        "source_url",
        "scan_url",
        "scan_links",
        "download_url",
        "image_url",
        "file_path",
        "link",
        "url",
        "archive_reference",
        "archive_ref",
        "instructions",
        "related",
        "фонд",
        "опись",
        "дело",
        "шифр",
        "лист",
        "ссылка",
        "скан",
    }
)

MASK_SUFFIX = "…"
# Names shorter than this are masked completely — a 2-4 char prefix would
# leak the whole name.
_MIN_UNMASKED_LEN = 5

# Defense-in-depth value detection.
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_CIPHER_RE = re.compile(r"(?:^|[\s(,.;])(?:ф|оп|д)\.\s*\d+", re.IGNORECASE)


def _is_url_like(value: str) -> bool:
    return bool(_URL_RE.search(value))


def _is_cipher_like(value: str) -> bool:
    return bool(_CIPHER_RE.search(value))


def _mask(value: Any) -> Any:
    """Mask strings (first 4 chars + ellipsis; short names fully), recursing
    into lists/dicts and still dropping DROP_FIELDS keys inside."""
    if isinstance(value, str):
        if len(value) >= _MIN_UNMASKED_LEN:
            return value[:4] + MASK_SUFFIX
        return MASK_SUFFIX
    if isinstance(value, list):
        return [_mask(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _mask(item) for key, item in value.items() if key not in DROP_FIELDS
        }
    return value


def _clean(value: Any) -> Any:
    """Recursively copy a kept value: DROP_FIELDS keys out at any depth,
    NAME_FIELDS values masked, URL-looking strings dropped (dict key or list
    item), cipher-looking strings masked."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in DROP_FIELDS:
                continue
            if key in NAME_FIELDS:
                result[key] = _mask(item)
            elif isinstance(item, str) and _is_url_like(item):
                continue
            else:
                result[key] = _clean(item)
        return result
    if isinstance(value, list):
        cleaned_items = []
        for item in value:
            if isinstance(item, str) and _is_url_like(item):
                continue
            cleaned_items.append(_clean(item))
        return cleaned_items
    if isinstance(value, str) and _is_cipher_like(value):
        return MASK_SUFFIX
    return value


def filter_record(record: dict, tier: Literal["teaser", "full"]) -> dict:
    """Return the record payload for the given tier.

    - full: the record as-is.
    - teaser: only KEEP_FIELDS/NAME_FIELDS survive at the top level (names
      masked); values are cleaned recursively — no ciphers, no links, no
      file paths, at any depth.
    """
    if tier == "full":
        return record
    if tier != "teaser":
        raise ValueError(f"Unknown record tier: {tier!r}")

    teaser: dict[str, Any] = {}
    for key, value in record.items():
        if key in DROP_FIELDS:
            continue
        if key in NAME_FIELDS:
            teaser[key] = _mask(value)
        elif key in KEEP_FIELDS:
            if isinstance(value, str) and _is_url_like(value):
                continue
            teaser[key] = _clean(value)
    return teaser
