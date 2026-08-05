from app.services.sensitive_patterns import IMAGE_PLACEHOLDER, URL_PLACEHOLDER
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


def test_url_replaced_with_placeholder():
    out = _run(["запись https://archive.example/record/1 найдена"])
    assert "archive.example" not in out
    assert URL_PLACEHOLDER in out
    assert "найдена" in out


def test_url_split_across_deltas():
    out = _run(["ссылка: https://arc", "hive.exam", "ple/r/1 готово"])
    assert "hive.example" not in out
    assert "ссылка: " in out
    assert URL_PLACEHOLDER in out
    assert "готово" in out


def test_www_url_replaced_case_insensitive():
    out = _run(["см. WWW.ARCHIVE.RU/x далее"])
    assert "archive" not in out.lower()
    assert URL_PLACEHOLDER in out
    assert "далее" in out


def test_markdown_link_becomes_label_with_lock():
    out = _run(["см. [Catalog URL](https://archive.example/r/1) далее"])
    assert "archive.example" not in out
    assert out == "см. Catalog URL 🔒 далее"


def test_markdown_link_split_across_deltas():
    deltas = ["см. [Cat", "alog](htt", "ps://arc", "hive.ru/x) готово"]
    out = _run(deltas)
    assert "hive.ru" not in out
    assert out == "см. Catalog 🔒 готово"


def test_multiple_markdown_links_in_a_row():
    out = _run(["[A](https://a.ru/x) и [B](https://b.ru/y) конец"])
    assert "a.ru" not in out
    assert "b.ru" not in out
    assert out == "A 🔒 и B 🔒 конец"


def test_markdown_link_split_inside_url():
    deltas = ["фото: [скан](https://toldot", ".ru/gr", "ave/7), запись"]
    out = _run(deltas)
    assert "toldot" not in out
    assert out == "фото: скан 🔒, запись"


def test_non_link_brackets_survive():
    out = _run(["см. [1] и [два](не-ссылка) текст"])
    assert out == "см. [1] и [два](не-ссылка) текст"


def test_markdown_image_replaced_with_picture_placeholder():
    out = _run(["фото: ![могила деда](https://toldot.ru/x.jpg) запись"])
    assert "toldot" not in out
    assert "могила деда" not in out  # the alt text is cut with the construct
    assert out == f"фото: {IMAGE_PLACEHOLDER} запись"


def test_markdown_image_split_across_deltas():
    deltas = ["фото: ![мо", "гила](https://tol", "dot.ru/x.jp", "g) конец"]
    out = _run(deltas)
    assert "toldot" not in out
    assert "гила" not in out
    assert out == f"фото: {IMAGE_PLACEHOLDER} конец"


def test_markdown_image_bang_split_from_bracket():
    deltas = ["смотри !", "[скан](https://t.ru/1) далее"]
    out = _run(deltas)
    assert "t.ru" not in out
    assert out == f"смотри {IMAGE_PLACEHOLDER} далее"


def test_exclamation_in_prose_survives():
    out = _run(["Нашлось! И это не все: вторая запись!"])
    assert out == "Нашлось! И это не все: вторая запись!"


def test_image_and_link_side_by_side():
    out = _run(["![фото](https://img.ru/1) и [текст](https://a.ru/2) конец"])
    assert "img.ru" not in out
    assert "a.ru" not in out
    assert out == f"{IMAGE_PLACEHOLDER} и текст 🔒 конец"


def test_slash_cipher_removed():
    out = _run(["запись ЦДІАК/W/1164/1/423 найдена"])
    assert "1164" not in out
    assert "ЦДІАК" not in out
    assert "найдена" in out


def test_slash_cipher_with_dashed_series_removed():
    out = _run(["дело ГАБО/Р-585/1/12 ок"])
    assert "Р-585" not in out
    assert "ок" in out


def test_slash_cipher_split_across_deltas():
    out = _run(["шифр ЦДІА", "К/W/116", "4/1/423 конец"])
    assert "1164" not in out
    assert "конец" in out


def test_slash_false_positives_survive():
    out = _run(["см. и/или далее, здание 12/корпус/3, год 1890/1891"])
    assert "и/или" in out
    assert "12/корпус/3" in out  # starts with a digit — not a cipher


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
