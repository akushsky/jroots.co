"""Streaming redactor for the outgoing LLM token stream (teaser tier).

Free-tier users must never see exact archive ciphers («ф. 585 оп. 1 д. 23»)
or record URLs, but the model itself iterates over full search results. The
redactor sits on the SSE boundary and cuts those fragments out of the
deltas before they reach the client.

The hard part is that sensitive patterns can split across token deltas
("https://arc" + "hive.ru/..." or "ф. " + "58" + "5 оп. 1"). The redactor
therefore holds back the tail of the buffer that could still grow into a
match — the trailing partial token (URLs have no whitespace) and the
trailing cipher-ish fragment — and only emits text that is provably final.
The residual word-sized lag is flushed at the end of the stream via
flush().
"""

from app.services.sensitive_patterns import (
    CIPHER_SEQ_RE,
    CIPHER_TAIL_RE,
    PARTIAL_TOKEN_TAIL_RE,
    URL_FULL_RE,
)


def _redact(text: str) -> str:
    """Remove complete URLs and cipher sequences from a final text span."""
    text = URL_FULL_RE.sub("", text)
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
        """End of stream: redact and emit everything still buffered."""
        out = _redact(self._buf)
        self._buf = ""
        return out

    def _holdback(self) -> int:
        """Length of the buffer tail that may still grow into a pattern."""
        hold = 0
        token = PARTIAL_TOKEN_TAIL_RE.search(self._buf)
        if token:
            hold = len(self._buf) - token.start()
        cipher = CIPHER_TAIL_RE.search(self._buf)
        if cipher:
            hold = max(hold, len(self._buf) - cipher.start())
        return hold
