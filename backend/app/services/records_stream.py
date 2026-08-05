"""Stream interceptor for the model's ```records fenced block.

The system prompt obliges the model to put structured records into a
```records fence (JSON array) in the final answer. The raw JSON must never
reach the user: while streaming, the block is buffered invisibly and, once
the closing fence arrives, replaced by the server-rendered tier-aware
markdown table (record_render).

Tier policy for a broken/unterminated block: teaser drops it silently (the
raw JSON may carry names, ciphers and URLs); full passes it through raw.

The fence opener can split across token deltas ("``" + "`reco" + "rds\n"),
so in prose state the handler holds back a trailing partial opener —
`` ` ``, `` `` ``, `` ``` ``, `` ```r `` … `` ```records `` — the same
hold-back mechanics as the stream redactor.

feed() returns a list of (kind, text) events:
- ("prose", text)   — ordinary answer text, to pass through the redactor;
- ("records", text) — a rendered records table (or the raw block for the
                      full tier), safe to emit as-is.
"""

import re
from typing import Literal

from app.services.record_render import render_records

# Block opener: ```records followed by an optional newline.
_FENCE_OPEN_RE = re.compile(r"```records[ \t]*\n?")

# Block closer: the next triple backtick inside the block.
_FENCE_CLOSE_RE = re.compile(r"```")

# Trailing buffer fragment that may still grow into a records-fence opener.
_PARTIAL_FENCE_TAIL_RE = re.compile(r"`{1,3}(?:r|re|rec|reco|recor|record|records)?$")


class RecordsBlockStream:
    """Splits a raw model stream into prose and rendered records blocks."""

    def __init__(self, tier: Literal["teaser", "full"]) -> None:
        self._tier = tier
        self._in_block = False
        self._buf = ""

    def feed(self, delta: str) -> list[tuple[str, str]]:
        if not delta:
            return []
        self._buf += delta
        out: list[tuple[str, str]] = []
        while self._buf:
            if not self._in_block:
                fence = _FENCE_OPEN_RE.search(self._buf)
                if fence is None:
                    hold = self._partial_fence_hold()
                    if hold:
                        safe, self._buf = self._buf[:-hold], self._buf[-hold:]
                    else:
                        safe, self._buf = self._buf, ""
                    if safe:
                        out.append(("prose", safe))
                    break
                before = self._buf[: fence.start()]
                if before:
                    out.append(("prose", before))
                self._buf = self._buf[fence.end() :]
                self._in_block = True
            else:
                closing = _FENCE_CLOSE_RE.search(self._buf)
                if closing is None:
                    break  # keep buffering — the block streams out of sight
                block_text = self._buf[: closing.start()]
                self._buf = self._buf[closing.end() :]
                self._in_block = False
                rendered = self._render_block(block_text)
                if rendered is not None:
                    out.append(("records", rendered))
        return out

    def flush(self) -> list[tuple[str, str]]:
        """End of a completion round: release whatever is still buffered."""
        out: list[tuple[str, str]] = []
        if self._in_block:
            # Unterminated fence = broken block (same policy as bad JSON).
            rendered = self._render_block(self._buf)
            if rendered is not None:
                out.append(("records", rendered))
        elif self._buf:
            out.append(("prose", self._buf))
        self._buf = ""
        self._in_block = False
        return out

    def _render_block(self, block_text: str) -> str | None:
        rendered = render_records(block_text, self._tier)
        if rendered is not None:
            return rendered
        if self._tier == "teaser":
            return None  # safe default: broken JSON never leaves the server
        return f"```records\n{block_text}\n```"

    def _partial_fence_hold(self) -> int:
        match = _PARTIAL_FENCE_TAIL_RE.search(self._buf)
        return len(self._buf) - match.start() if match else 0
