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
