"""Streaming redactor for the outgoing LLM token stream (teaser tier).

Free-tier users must never see exact archive ciphers («ф. 585 оп. 1 д. 23»)
or record URLs, but the model itself iterates over full search results. The
redactor sits on the SSE boundary and rewrites those fragments in the deltas
before they reach the client:

- bare URL → URL_PLACEHOLDER (« 🔒 _доступно в полной версии_ »);
- markdown link [label](URL) → «label 🔒» (label capped at 100 chars);
- cipher sequence → cut out entirely.

The hard part is that sensitive patterns can split across token deltas
("https://arc" + "hive.ru/...", "[Catalog](https://" + "...", or
"ф. " + "58" + "5 оп. 1"). The redactor therefore holds back the tail of
the buffer that could still grow into a match — the trailing partial token
(URLs have no whitespace), the trailing cipher-ish fragment and the
trailing partial markdown link — and only emits text that is provably
final. The residual word-sized lag is released via flush() at the end of
each completion round.
"""

from app.services.sensitive_patterns import (
    CIPHER_SEQ_RE,
    CIPHER_TAIL_RE,
    IMAGE_PLACEHOLDER,
    MD_IMAGE_FULL_RE,
    MD_LINK_DEST_TAIL_RE,
    MD_LINK_FULL_RE,
    MD_LINK_OPEN_TAIL_RE,
    PARTIAL_TOKEN_TAIL_RE,
    TRAILING_BANG_RE,
    URL_FULL_RE,
    URL_PLACEHOLDER,
)


def _redact(text: str) -> str:
    """Rewrite complete markdown images/links, bare URLs and cipher sequences
    in a final text span. Order matters: the image construct contains a
    link-shaped tail, and the link pattern consumes its URL — so images
    first, links second, bare URLs last."""
    text = MD_IMAGE_FULL_RE.sub(IMAGE_PLACEHOLDER, text)
    text = MD_LINK_FULL_RE.sub(lambda m: f"{m.group(1)} 🔒", text)
    text = URL_FULL_RE.sub(URL_PLACEHOLDER, text)
    return CIPHER_SEQ_RE.sub("", text)


class StreamRedactor:
    """Incremental redactor: feed deltas, emit safe text, flush at the end."""

    def __init__(self) -> None:
        self._buf = ""

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
        return _redact(safe)

    def flush(self) -> str:
        """End of a completion round: redact and emit all that is buffered."""
        out = _redact(self._buf)
        self._buf = ""
        return out

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
        return hold
