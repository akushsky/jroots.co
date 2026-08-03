from app.services.stream_redactor import StreamRedactor


def _run(deltas: list[str]) -> str:
    redactor = StreamRedactor()
    parts = [redactor.feed(delta) for delta in deltas]
    parts.append(redactor.flush())
    return "".join(parts)


def test_plain_text_passes_through():
    text = "Привет! Ищем метрики семьи Кацнельсон в Клинцах, т. д. и т. п."
    assert _run([text]) == text


def test_plain_text_split_across_deltas_is_lossless():
    deltas = ["При", "вет, и", "щем ", "Кацнельсона ", "в Клин", "цах."]
    assert _run(deltas) == "Привет, ищем Кацнельсона в Клинцах."


def test_town_and_year_are_not_ciphers():
    text = "Ревизская сказка г. Клинцы, 1858 год, д. Каменка."
    assert _run([text]) == text


def test_url_removed_single_delta():
    out = _run(["запись https://archive.example/record/1 найдена"])
    assert "https" not in out
    assert "archive.example" not in out
    assert "найдена" in out


def test_url_split_across_deltas():
    out = _run(["ссылка: https://arc", "hive.exam", "ple/r/1 готово"])
    assert "https" not in out
    assert "hive.example" not in out
    assert "ссылка: " in out
    assert "готово" in out


def test_www_url_removed_case_insensitive():
    out = _run(["см. WWW.ARCHIVE.RU/x далее"])
    assert "archive" not in out.lower()
    assert "далее" in out


def test_cipher_removed_single_delta():
    out = _run(["метрика ф. 585 оп. 1 д. 23 найдена"])
    assert "585" not in out
    assert "оп." not in out
    assert out == "метрика найдена"


def test_cipher_split_across_deltas():
    deltas = ["дело ф. ", "58", "5 оп", ". 1 ", "д. 2", "3, л. 15 ", "нашли"]
    out = _run(deltas)
    for fragment in ("585", "оп. 1", "д. 23", "л. 15"):
        assert fragment not in out
    assert "дело " in out
    assert "нашли" in out


def test_uppercase_cipher_removed():
    out = _run(["шифр Ф. 12 ОП. 3 Д. 4 ок"])
    assert "12" not in out
    assert "ОП." not in out
    assert "ок" in out


def test_trailing_cipher_at_stream_end_removed():
    assert _run(["смотри ф. 585 оп. 1"]) == "смотри "


def test_lone_abbreviation_without_digits_survives():
    # «ф.» without digits is not a cipher — must not be eaten.
    assert _run(["письмо ф. говорили"]) == "письмо ф. говорили"
