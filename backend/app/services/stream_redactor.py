"""Streaming redactor for the outgoing LLM token stream (teaser tier).

Free-tier users must never see exact archive ciphers («ф. 585 оп. 1 д. 23»,
«ЦДІАК/W/1164/1/423», «фонд ЦДІАК 1164/1») or record URLs. The model-facing
tool results are sanitized upstream (mcp_client), so this redactor is the
second line of defense for the prose the model writes itself:

- bare URL → URL_PLACEHOLDER (« 🔒 _доступно в полной версии_ »);
- markdown link [label](URL) → «label 🔒» (label capped at 100 chars);
- markdown image ![alt](URL) → picture placeholder, alt included;
- cipher families (ф./оп./д. sequences, long keyword forms, slash notations,
  case lists) → lock glyphs / cut out;
- bare long slash numbers («1164/1/534») — only on lines with archive
  context (a keyword or an all-caps acronym), so «1889/1890» and «123/45»
  in ordinary prose survive; the line context is tracked across deltas.

The hard part is that sensitive patterns can split across token deltas
("https://arc" + "hive.ru/...", "[Catalog](https://" + "...", or
"ф. " + "58" + "5 оп. 1"). The redactor therefore holds back the tail of
the buffer that could still grow into a match — the trailing partial token
(URLs have no whitespace), the trailing cipher-ish fragment and the
trailing partial markdown link — and only emits text that is provably
final. The residual word-sized lag is released via flush() at the end of
each completion round.

redact_text() is the non-streaming whole-text variant used as the final
safety pass before persisting teaser-tier content: there the bare slash
pattern applies unconditionally (a persist-bound text has no excuse to
carry bare cipher fragments).
"""

from app.services.sensitive_patterns import (
    ARCHIVE_ACRONYM_RE,
    ARCHIVE_CONTEXT_WORD_RE,
    ARCHIVE_FOND_SLASH_RE,
    BARE_SLASH_SEQ_RE,
    CASE_LIST_RE,
    CIPHER_SEQ_RE,
    CIPHER_TAIL_RE,
    IDENT_LIST_RE,
    IMAGE_PLACEHOLDER,
    LONG_CIPHER_SEQ_RE,
    MD_IMAGE_FULL_RE,
    MD_LINK_DEST_TAIL_RE,
    MD_LINK_FULL_RE,
    MD_LINK_OPEN_TAIL_RE,
    NUMERIC_ID_RE,
    PARTIAL_TOKEN_TAIL_RE,
    SLASH_CIPHER_RE,
    SOURCE_DOMAIN_RE,
    TRAILING_BANG_RE,
    URL_FULL_RE,
    URL_PLACEHOLDER,
    long_cipher_tail_len,
)


def _redact(text: str) -> str:
    """Rewrite the context-free sensitive families in a final text span.
    Order matters: the image construct contains a link-shaped tail, the link
    pattern consumes its URL, and slash ciphers must run after URLs so URL
    paths are never mangled — so: images, links, bare URLs, then ciphers."""
    text = MD_IMAGE_FULL_RE.sub(IMAGE_PLACEHOLDER, text)
    text = MD_LINK_FULL_RE.sub(lambda m: f"{m.group(1)} 🔒", text)
    text = URL_FULL_RE.sub(URL_PLACEHOLDER, text)
    text = SOURCE_DOMAIN_RE.sub(" 🔒 ", text)
    text = SLASH_CIPHER_RE.sub("", text)
    text = ARCHIVE_FOND_SLASH_RE.sub(
        lambda m: f"{m.group(1) or ''}{m.group(2)} 🔒", text
    )
    text = CASE_LIST_RE.sub(" 🔒 ", text)
    text = IDENT_LIST_RE.sub(" 🔒 ", text)
    text = NUMERIC_ID_RE.sub(" 🔒 ", text)
    text = LONG_CIPHER_SEQ_RE.sub(" 🔒 ", text)
    return CIPHER_SEQ_RE.sub("", text)


def _has_archive_context(line: str) -> bool:
    """An archive keyword or an all-caps acronym on the line."""
    return bool(ARCHIVE_CONTEXT_WORD_RE.search(line) or ARCHIVE_ACRONYM_RE.search(line))


def redact_text(text: str) -> str:
    """Whole-text redaction for the final persist pass: everything _redact
    covers, plus the bare slash pattern unconditionally (a persist-bound
    text must not carry bare cipher fragments)."""
    return BARE_SLASH_SEQ_RE.sub(" 🔒 ", _redact(text))


class StreamRedactor:
    """Incremental redactor: feed deltas, emit safe text, flush at the end."""

    def __init__(self) -> None:
        self._buf = ""
        # The tail of the line emitted so far — bare slash numbers are
        # masked only on lines with archive context, and the context word
        # may have been emitted deltas ago.
        self._line_tail = ""

    def feed(self, delta: str) -> str:
        """Consume one token delta; return the redacted text safe to emit."""
        if not delta:
            return ""
        self._buf += delta
        hold = self._holdback()
        if hold:
            safe, self._buf = self._buf[:-hold], self._buf[-hold:]
        else:
            safe, self._buf = self._buf, ""
        return self._redact_safe(safe)

    def flush(self) -> str:
        """End of a completion round: redact and emit all that is buffered."""
        out = self._redact_safe(self._buf)
        self._buf = ""
        self._line_tail = ""
        return out

    def _redact_safe(self, text: str) -> str:
        if not text:
            return text
        out = _redact(text)
        lines = out.split("\n")
        masked = []
        for index, line in enumerate(lines):
            context = (self._line_tail + line) if index == 0 else line
            if _has_archive_context(context):
                line = BARE_SLASH_SEQ_RE.sub(" 🔒 ", line)
            masked.append(line)
        self._line_tail = masked[-1][-120:]
        return "\n".join(masked)

    def _holdback(self) -> int:
        """Length of the buffer tail that may still grow into a pattern."""
        hold = 0
        for pattern in (
            PARTIAL_TOKEN_TAIL_RE,
            CIPHER_TAIL_RE,
            MD_LINK_OPEN_TAIL_RE,
            MD_LINK_DEST_TAIL_RE,
            TRAILING_BANG_RE,
        ):
            match = pattern.search(self._buf)
            if match:
                hold = max(hold, len(self._buf) - match.start())
        hold = max(hold, long_cipher_tail_len(self._buf))
        return hold
