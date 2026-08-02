import pytest

from app.services.record_filter import filter_record


def _record():
    return {
        "type": "metric_book",
        "place": "Клинцы",
        "period": "1890-1895",
        "archive_region": "Черниговская губерния",
        "match_count": 3,
        "surname": "Фалькович",
        "first_name": "Шмуил",
        "names": ["Шмуил", "Гитля"],
        "person": {"full_name": "Шмуил Фалькович", "patronymic": "Гершевич"},
        "cipher": "ф.585 оп.1 д.12",
        "fond": "585",
        "opis": "1",
        "delo": "12",
        "record_url": "https://archive.example/record/1",
        "source_url": "https://archive.example",
        "instructions": "Закажите копию",
        "related": [{"cipher": "ф.585 оп.1 д.13"}],
    }


def test_full_tier_returns_record_as_is():
    record = _record()
    assert filter_record(record, "full") is record


def test_teaser_keeps_base_fields():
    teaser = filter_record(_record(), "teaser")
    assert teaser["type"] == "metric_book"
    assert teaser["place"] == "Клинцы"
    assert teaser["period"] == "1890-1895"
    assert teaser["archive_region"] == "Черниговская губерния"
    assert teaser["match_count"] == 3


def test_teaser_masks_names():
    teaser = filter_record(_record(), "teaser")
    assert teaser["surname"] == "Фаль…"
    assert teaser["first_name"] == "Шмуи…"
    assert teaser["names"] == ["Шмуи…", "Гитл…"]
    assert teaser["person"]["full_name"] == "Шмуи…"
    assert teaser["person"]["patronymic"] == "Герш…"


def test_teaser_drops_cipher_and_links_completely():
    teaser = filter_record(_record(), "teaser")
    for field in (
        "cipher",
        "fond",
        "opis",
        "delo",
        "record_url",
        "source_url",
        "instructions",
        "related",
    ):
        assert field not in teaser


def test_teaser_does_not_mutate_source():
    record = _record()
    filter_record(record, "teaser")
    assert record["surname"] == "Фалькович"
    assert record["names"] == ["Шмуил", "Гитля"]


def test_teaser_drops_cipher_fields_in_nested_structures():
    record = {
        "place": {
            "name": "Бердичев",
            "record_url": "https://leak/r/1",
            "fond": "228",
            "details": {"opis": "2", "delo": "45", "town": "Бердичев"},
        },
        "notes": {
            "matches": [
                {"name": "Мендель", "cipher": "ф.228 оп.2 д.45", "year": 1890},
                {"name": "Сура", "record_url": "https://leak/r/2", "year": 1892},
            ]
        },
    }
    teaser = filter_record(record, "teaser")

    assert "record_url" not in teaser["place"]
    assert "fond" not in teaser["place"]
    assert "opis" not in teaser["place"]["details"]
    assert "delo" not in teaser["place"]["details"]
    assert teaser["place"]["details"]["town"] == "Бердичев"
    # place.name is a NAME_FIELDS key — masked even when nested.
    assert teaser["place"]["name"] == "Берд…"

    matches = teaser["notes"]["matches"]
    assert "cipher" not in matches[0]
    assert matches[0]["name"] == "Менд…"
    assert matches[0]["year"] == 1890
    assert "record_url" not in matches[1]
    assert matches[1]["name"] == "…"  # 4 chars — masked fully


def test_teaser_masks_short_names_completely():
    teaser = filter_record({"first_name": "Аб", "surname": "Кац", "name": ""}, "teaser")
    assert teaser["first_name"] == "…"
    assert teaser["surname"] == "…"
    assert teaser["name"] == "…"


def test_teaser_drops_unlisted_top_level_fields():
    record = {
        "type": "census",
        "year": 1897,
        "notes": "стр. 12",
        "internal_id": "rec-123",
        "score": 0.87,
    }
    teaser = filter_record(record, "teaser")
    assert teaser == {"type": "census", "year": 1897, "notes": "стр. 12"}


def test_teaser_value_detection_urls_and_ciphers():
    record = {
        "notes": "Найдена запись ф.585 оп.1 д.12, стр. 3",
        "summary": "см. https://archive.example/record/1",
        "description": {
            "comment": "www.archive.example/scan",
            "plain": "без ссылок",
            "list": ["https://leak/1", "текст"],
        },
    }
    teaser = filter_record(record, "teaser")
    # Cipher-looking string is masked wholesale.
    assert teaser["notes"] == "…"
    # URL-looking values drop the key/item entirely, at any depth.
    assert "summary" not in teaser
    assert "comment" not in teaser["description"]
    assert teaser["description"]["plain"] == "без ссылок"
    assert teaser["description"]["list"] == ["текст"]


def test_teaser_producer_realistic_record():
    """Record shape close to what real MCP producers return: Russian cipher
    keys, archive_reference, scan_links, bare url — none may survive."""
    record = {
        "type": "metric_book",
        "place": "Бердичев",
        "period": "1890-1895",
        "archive_region": "Киевская губерния",
        "match_count": 2,
        "фамилия": "Гольдберг",
        "имя": "Мендель",
        "отчество": "Шмуйлович",
        "фамилия_лат": "Goldberg",
        "archive_reference": "ЦДІАК ф.228 оп.2 д.45",
        "scan_links": ["https://scan/1", "https://scan/2"],
        "url": "https://archive/record/1",
        "notes": "Запись ф.228 оп.2 д.45, лист 12",
        "фонд": "228",
        "опись": "2",
        "дело": "45",
        "шифр": "ф.228 оп.2 д.45",
        "лист": "12",
        "ссылка": "https://archive/record/1",
        "скан": "https://scan/1",
        "names": ["Мендель Гольдберг"],
    }
    teaser = filter_record(record, "teaser")

    for field in (
        "archive_reference",
        "scan_links",
        "url",
        "фонд",
        "опись",
        "дело",
        "шифр",
        "лист",
        "ссылка",
        "скан",
    ):
        assert field not in teaser, field

    assert teaser["фамилия"] == "Голь…"
    assert teaser["имя"] == "Менд…"
    assert teaser["отчество"] == "Шмуй…"
    assert teaser["фамилия_лат"] == "Gold…"
    assert teaser["names"] == ["Менд…"]
    # notes mentions the exact cipher — masked by value detection.
    assert teaser["notes"] == "…"

    assert teaser["type"] == "metric_book"
    assert teaser["place"] == "Бердичев"
    assert teaser["period"] == "1890-1895"
    assert teaser["archive_region"] == "Киевская губерния"
    assert teaser["match_count"] == 2

    # No URL or cipher strings survive anywhere in the payload.
    assert "http" not in str(teaser)
    assert "ф.228" not in str(teaser)


def test_unknown_tier_raises():
    with pytest.raises(ValueError):
        filter_record(_record(), "partial")
