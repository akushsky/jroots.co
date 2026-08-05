from app.services.records_stream import RecordsBlockStream

BLOCK = (
    '[{"type": "metric_book", "place": "Клинцы", "period": "1890-1895", '
    '"names": ["Шмуил Фалькович"], "archive": "ГАБО", '
    '"cipher": "ф.585 оп.1 д.12", "url": "https://archive.example/r/1"}]'
)


def _run(tier, deltas):
    stream = RecordsBlockStream(tier)
    events = []
    for delta in deltas:
        events.extend(stream.feed(delta))
    events.extend(stream.flush())
    return events


def _prose(events):
    return "".join(text for kind, text in events if kind == "prose")


def _records(events):
    return "".join(text for kind, text in events if kind == "records")


def test_plain_text_passes_through():
    events = _run("teaser", ["Просто ", "текст без блоков."])
    assert _prose(events) == "Просто текст без блоков."
    assert _records(events) == ""


def test_block_split_across_deltas_teaser():
    deltas = [
        "Смотри:\n",
        "```rec",
        "ords\n",
        BLOCK[:30],
        BLOCK[30:],
        "\n```",
        "\nГотово.",
    ]
    events = _run("teaser", deltas)
    assert _prose(events) == "Смотри:\n\nГотово."
    table = _records(events)
    # Server-rendered teaser table: masked name, lock, no cipher/URL/JSON.
    assert "| Тип | Место | Период | Имена | Запись |" in table
    assert "Шмуи…" in table
    assert "Фалькович" not in table
    assert "585" not in table
    assert "archive.example" not in table
    assert "```" not in table


def test_block_full_tier_renders_everything():
    events = _run("full", ["```records\n", BLOCK, "\n```"])
    table = _records(events)
    assert "Шмуил Фалькович" in table
    assert "ф.585 оп.1 д.12" in table
    assert "[открыть](https://archive.example/r/1)" in table


def test_broken_json_dropped_silently_in_teaser():
    events = _run("teaser", ["До.\n", "```records\n", "[{не json", "\n```", "\nПосле."])
    assert _records(events) == ""
    assert "не json" not in _prose(events)
    assert "```" not in _prose(events)
    assert _prose(events) == "До.\n\nПосле."


def test_broken_json_passes_raw_in_full():
    events = _run("full", ["```records\n", "[{не json", "\n```"])
    raw = _records(events)
    assert "[{не json" in raw
    assert "```records" in raw


def test_unterminated_block_dropped_in_teaser():
    events = _run("teaser", ["Текст.\n", "```records\n", BLOCK[:40]])
    assert _records(events) == ""
    assert "585" not in _prose(events)
    assert _prose(events) == "Текст.\n"


def test_unterminated_block_raw_in_full():
    events = _run("full", ["```records\n", BLOCK[:40]])
    assert BLOCK[:40] in _records(events)


def test_other_fences_pass_through():
    text = "```json\n{}\n```"
    events = _run("teaser", [text])
    assert _prose(events) == text
    assert _records(events) == ""


def test_partial_opener_held_until_resolved():
    # "```" alone could become the records fence — held back, then resolved.
    events = _run("teaser", ["код: ``", "`", "json\nx```"])
    assert _prose(events) == "код: ```json\nx```"


def test_multiple_blocks_in_one_stream():
    deltas = [
        "A",
        "```records\n",
        BLOCK,
        "\n```",
        "B",
        "```records\n",
        "[]",
        "```",
        "C",
    ]
    events = _run("full", deltas)
    assert _prose(events) == "ABC"
    records = _records(events)
    assert "Шмуил Фалькович" in records  # first block rendered
    # second block was an empty array — renders nothing
