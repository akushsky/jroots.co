from app.services.record_render import TEASER_LOCK, render_records

BLOCK = """
[
  {
    "type": "metric_book",
    "place": "Клинцы",
    "period": "1890-1895",
    "names": ["Шмуил Фалькович", "Гитля"],
    "archive_region": "Черниговская губ.",
    "archive": "ГАБО",
    "cipher": "ф.585 оп.1 д.12",
    "url": "https://archive.example/r/1",
    "record_id": "rec-1",
    "notes": "брак"
  }
]
"""


def test_teaser_masks_names_and_locks_cipher_and_url():
    out = render_records(BLOCK, "teaser")
    assert out is not None
    # Masked names (first 4 chars + ellipsis), no full names anywhere.
    assert "Шмуи…" in out
    assert "Гитл…" in out
    assert "Фалькович" not in out
    # Place and period stay; cipher and URL are gone behind the lock.
    assert "Клинцы" in out
    assert "1890-1895" in out
    assert "metric_book" in out
    assert "585" not in out
    assert "archive.example" not in out
    assert TEASER_LOCK in out


def test_full_renders_everything_with_clickable_url():
    out = render_records(BLOCK, "full")
    assert out is not None
    assert "Шмуил Фалькович" in out
    assert "Гитля" in out
    assert "ф.585 оп.1 д.12" in out
    assert "ГАБО" in out
    assert "[открыть](https://archive.example/r/1)" in out


def test_broken_json_returns_none():
    assert render_records("[{не json", "teaser") is None
    assert render_records("[{не json", "full") is None


def test_non_array_json_returns_none():
    assert render_records('{"a": 1}', "teaser") is None
    assert render_records('"просто строка"', "full") is None


def test_empty_array_renders_nothing():
    assert render_records("[]", "teaser") == ""
    assert render_records("[]", "full") == ""


def test_pipes_and_newlines_in_values_are_sanitized():
    block = '[{"type": "a|b", "place": "Киев\\nЦентр", "names": ["Абрам"]}]'
    out = render_records(block, "full")
    assert out is not None
    assert "a|b" not in out
    assert "a/b" in out
    assert "\nЦентр" not in out
