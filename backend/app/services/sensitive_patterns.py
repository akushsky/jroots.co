"""Shared detectors for archive-sensitive strings (URLs and fund ciphers).

Single source of truth for what counts as leak-prone text, used by:

- record_filter — teaser/full paywall filtering of structured records;
- stream_redactor — real-time redaction of the outgoing LLM token stream
  for teaser-tier users.

Two pattern families live here:

- *_DETECT_RE — "does this value contain something sensitive" (record_filter);
- *_FULL_RE / *_TAIL_RE — full-match redaction and partial-tail hold-back
  for the streaming redactor.
"""

import re

# --- Presence detectors (record_filter) ---

# A URL starts here: scheme or bare www prefix.
URL_DETECT_RE = re.compile(r"https?://|www\.", re.IGNORECASE)

# A single archive-cipher component («ф. 585», «оп.1», «д. 23») at a word-ish
# boundary — start of string or after space/punctuation.
CIPHER_DETECT_RE = re.compile(r"(?:^|[\s(,.;])(?:ф|оп|д)\.\s*\d+", re.IGNORECASE)

# --- Full-match redaction patterns (stream_redactor) ---

# A whole URL token (URLs contain no whitespace).
URL_FULL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

# Replacement for a redacted bare URL (markdown italic).
URL_PLACEHOLDER = " 🔒 _доступно в полной версии_ "

# Replacement for a redacted markdown image: the whole construct (alt text
# included) is cut, the picture glyph marks what was hidden.
IMAGE_PLACEHOLDER = "🖼 🔒 _доступно в полной версии_ "

# A whole markdown image ![alt](https://...) — replaced as one unit. Must be
# matched BEFORE MD_LINK_FULL_RE: the image construct contains a link-shaped
# tail. The alt text is capped at 100 chars (same fallback as link labels).
MD_IMAGE_FULL_RE = re.compile(
    r"!\[[^\]]{0,100}\]\(https?://[^)\s]+\)",
    re.IGNORECASE,
)

# A whole markdown link [label](https://...) — replaced by «label 🔒».
# The label is capped at 100 chars: a longer label falls back to plain-URL
# redaction inside the parentheses (the URL itself still cannot leak).
MD_LINK_FULL_RE = re.compile(
    r"\[([^\]]{0,100})\]\(https?://[^)\s]+\)",
    re.IGNORECASE,
)

# Trailing partial markdown link or image, held back until it either
# completes (and gets redacted) or turns out to be innocent text: an open
# bracket with the label/alt in progress, or a finished label with the
# destination still typing. The optional «!» covers image constructs.
MD_LINK_OPEN_TAIL_RE = re.compile(r"!?\[[^\]\n]{0,100}$")
MD_LINK_DEST_TAIL_RE = re.compile(r"!?\[[^\]\n]{0,100}\]\(\S*$")

# A lone «!» at the very end of the buffer may be the start of an image
# construct whose «[» arrives with the next delta.
TRAILING_BANG_RE = re.compile(r"!$")

# Slash-notation archive cipher: «ЦДІАК/W/1164/1/423», «ГАБО/Р-585/1/12».
# Structure: archive code (letters) + optional single-letter series segment
# + at least two digit-bearing segments. Ukrainian letters included — these
# ciphers come from Ukrainian archives. No tail pattern needed: a slash
# cipher contains no whitespace, so the partial-token hold-back covers
# split deltas. Applied AFTER URL_FULL_RE so URL paths are never mangled.
SLASH_CIPHER_RE = re.compile(
    r"[A-Za-zА-Яа-яЁёІіЇїЄєҐґ][\w.-]*"
    r"(?:/[A-Za-zА-Яа-яЁёІіЇїЄєҐґ])?"
    r"(?:/[\w.-]*\d[\w.-]*){2,}"
)

# Archive word (all-caps acronym) + numbers in slash notation, with a space
# or slash separator: «ЦДІАК 1164/1», «ГАБО Р-585/1/12», «ЦДІАК/1164/1»,
# «фонд ЦДІАК 1164/1». Group 1 is the optional keyword (kept for
# readability), group 2 the archive code (also kept — it is not sensitive);
# only the numbers are masked. The all-caps requirement keeps Capitalized
# prose words («Всего 12/34») out of the match; the keyword is matched
# case-insensitively via an inline flag.
ARCHIVE_FOND_SLASH_RE = re.compile(
    r"((?i:фонд[ауе]?|опис[ьи])\s*\**\s*)?"
    r"([A-ZА-ЯЁІЇЄҐ][A-ZА-ЯЁІЇЄҐ0-9.-]*)"
    r"[ /][A-Za-zА-Яа-яЁёІіЇїЄєҐґ]?-?\d+"
    r"(?:/\d{1,3})+(?!\d)"
)

# Bare long slash notation with no labels at all: «1164/1», «1164/1/534»,
# «1893/196». Segment lengths (3+ then 1-3 digits) deliberately exclude
# year ranges like «1889/1890». In the stream redactor this only applies on
# lines with archive context (see ARCHIVE_CONTEXT_* below); the final
# persist pass and tool-result sanitation apply it unconditionally.
BARE_SLASH_SEQ_RE = re.compile(r"(?<!\d)\d{3,}(?:/\d{1,3})+(?!\d)")

# Archive context markers for BARE_SLASH_SEQ_RE in prose: a keyword or an
# all-caps archive acronym (3+ letters) on the same line.
ARCHIVE_CONTEXT_WORD_RE = re.compile(
    r"фонд|опис|дел[ао]\b|запис|шифр|лист|могил|квадрат", re.IGNORECASE
)
ARCHIVE_ACRONYM_RE = re.compile(r"[A-ZА-ЯЁІЇЄҐ]{3,}")

# A cipher sequence: one or more «ф./оп./д./л. <num>» components with their
# trailing separators, e.g. «ф. 585 оп. 1 д. 23» or «оп.1, д.5». «л.» (лист)
# is included on top of the detector set — a sheet number without fond/opis
# is harmless on its own, but it rides inside cipher sequences.
CIPHER_SEQ_RE = re.compile(
    r"(?:(?:ф|оп|д|л)\.?\s*\d+(?:[-–—]\d+)?[\s,;]*)+",
    re.IGNORECASE,
)

# Trailing buffer fragment that may still grow into a cipher sequence when
# more stream deltas arrive: cipher-ish components (digits optional — they
# may be split into the next delta) anchored at the end of the buffer.
CIPHER_TAIL_RE = re.compile(
    r"(?:(?:ф|оп|д|л)\.?\s*\d*[\s,;]*)+$",
    re.IGNORECASE,
)

# Trailing partial token (no whitespace yet) — URLs are single tokens, so a
# split URL always ends the buffer as a partial token.
PARTIAL_TOKEN_TAIL_RE = re.compile(r"\S+$")

# Trailing fragment that may grow into a long-form cipher or case list once
# more deltas arrive: an archive keyword followed only by cipher-ish
# characters (letters, digits, №, separators) to the end of the buffer.
# «запись в журнале» contains a space-separated non-digit word right after
# the keyword, but digits never start — the digit requirement keeps it from
# holding prose indefinitely.
LONG_CIPHER_TAIL_RE = re.compile(
    r"(?:фонд[ыауе]?|опис[ьиея]|дел[аое]?|запис[ьиея]|записей|микрофильм[ыа]?|"
    r"ед\.?\s*хранения)"
    r"[\w\s№.,;()*/–—-]{0,60}\d[\w\s№.,;()*/–—-]*$",
    re.IGNORECASE,
)

# Loose keyword-at-tail candidate: keyword followed by up to 60 cipher-ish
# characters to the buffer end, NO digit required — catches the keyword split
# from its digits across deltas («номер » + «21166950»). Used via
# long_cipher_tail_len, which rejects prose tails.
_LOOSE_CIPHER_TAIL_RE = re.compile(
    r"(?:фонд[ыауе]?|опис[ьиея]|дел[аое]?|запис[ьиея]|записей|микрофильм[ыа]?|"
    r"номер|id|№|ед\.?\s*хранения)"
    r"[\w\s№.,;()*/–—-]{0,60}$",
    re.IGNORECASE,
)

# A 3+ lowercase-letter word after the keyword means the tail is ordinary
# prose («запись в журнале», «дело было») — do not hold it back.
_TAIL_PROSE_WORD_RE = re.compile(r"[a-zа-яёіїєґ]{3,}")


def long_cipher_tail_len(text: str) -> int:
    """Length of a trailing keyword-started fragment worth holding back.

    Covers the keyword-split-from-digits case («номер » + «21166950») while
    not holding plain prose: if the fragment after the keyword contains a
    3+ lowercase-letter word, it is prose and the hold is refused.
    """
    match = _LOOSE_CIPHER_TAIL_RE.search(text)
    if not match:
        return 0
    tail = match.group(0)
    # Skip the keyword itself (up to the first space).
    after = tail.split(None, 1)
    if len(after) > 1 and _TAIL_PROSE_WORD_RE.search(after[1]):
        return 0
    return len(tail)


# Long-form cipher sequences: «фонд Р-585 опись 1», «дело 415, запись № 12»,
# «запись 1893/196». The abbreviated CIPHER_SEQ_RE only knows «ф./оп./д.» —
# models also write the long form. Keyword + optional №/series + digits;
# digit required right after the keyword, so «опись магазина» and «запись в
# журнале» stay untouched.
LONG_CIPHER_SEQ_RE = re.compile(
    r"(?:(?:фонд|опись|дело|деле|запись|ед\.?\s*хранения)\s*№?\s*"
    r"[A-Za-zА-Яа-яЁёІіЇїЄєҐґ-]*\s*\d+(?!\d)[A-Za-zА-Яа-я]?(?!\s*год[ау]?)"
    r"(?:[-–—/]\d+[A-Za-zА-Яа-я]?)?[\s,;]*)+",
    re.IGNORECASE,
)

# Case-number enumerations: «(дела 149, 171, 172)», «дела 12, 15–18», with
# optional letter-suffixed numbers (428А) and markdown bold markers.
CASE_LIST_RE = re.compile(
    r"\(?\**(?:дела|дело)\s+\**\s*"
    r"(?:\d+[A-Za-zА-Яа-я]?(?:[-–—]\d+[A-Za-zА-Яа-я]?)?[\s,;]*)+\**\)?",
    re.IGNORECASE,
)

# Bare source domains without a scheme. The URL pattern only catches
# http(s):// and www. — a domain dropped into prose («проверьте
# online.archives.ru») guides the free user straight to the source, which
# defeats the teaser. Maintained list of source domains we actually proxy.
SOURCE_DOMAIN_RE = re.compile(
    r"\b(?:"
    r"toldot\.com|jewishgen\.org|pamyat-naroda\.ru|pamyat-naroda\.com|"
    r"obd-memorial\.ru|yadvashem\.org|pomnim\.online|mitzvatemet\.com|"
    r"cgamos\.ru|online\.archives\.ru|archives\.gov\.pl|"
    r"szukajwarchiwach\.gov\.pl|szukajwarchiwach\.pl|genealodzy\.pl|"
    r"jri-poland\.org|geni\.com|familio\.org|gravlov\.com|"
    r"jewishgen\.org|babynyar\.org|goskatalog\.ru|gwar\.mil\.ru|"
    r"spbarchives\.ru|fgurgia\.ru|duckarchive\.com|openlist\.wiki"
    r")\b",
    re.IGNORECASE,
)

# Identifier keywords that turn a number into a product leak: «фонды
# 2234548, 2255342», «микрофильмы 2373292, 2375369», «записей 91952313».
# Plurals and the record-id variants («записи», «записей») included; plain
# «запись 1894 года» (a year, not an id) is excluded by the negative
# lookahead for год-words and by requiring ≥3 digits or a slash.
IDENT_LIST_RE = re.compile(
    r"(?:фонд[ыауе]?|опис[ьиея]|дел[ао]?|запис[ьи]|записей|микрофильм[ыа]?|"
    r"плёнк[иа]|пленк[иа])\s*№?\s*\**"
    r"(?:[A-Za-zА-Яа-яЁёІіЇїЄєҐґ-]*\d+(?!\d)[A-Za-zА-Яа-я]?(?!\s*год[ау]?)"
    r"(?:[-–—/]\d+)?[\s,;]*)+",
    re.IGNORECASE,
)

# Bare numeric record ids: 5+ digits after an id-ish marker («id 91952313»,
# «№ 21166950», «номер записи 20801411»). Years (4 digits) never match.
NUMERIC_ID_RE = re.compile(
    r"(?:id|ID|№|номер(?:\s+записи)?)\s*[:№]?\s*\d{5,}\b",
    re.IGNORECASE,
)
