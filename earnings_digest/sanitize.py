"""Injection scrub for untrusted transcript text, implemented once for
this engine.

CONTRACT (INVERTER F4 of the REQ register): the RAW transcript is never
modified — it is preserved verbatim in the cache and the KB render (lossless
standing rule). This module produces a SEPARATE sanitized buffer that is the
ONLY text an analyzer (in-session or API) ever sees. Hits are counted, logged,
and surfaced in frontmatter.
"""
from __future__ import annotations

import json
import os
import re
import time

from . import config

# Canon pattern list (transcribe_and_extract.md Layer 0.25). Whitespace-flexible,
# case-insensitive. English-based by design limitation — defense in depth
# (data fencing, tool-less analyzer path, structural validation) carries the rest.
_CANON = [
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"you\s+are\s+now\s+",
    r"developer\s+mode",
    r"\bsudo\b",
    r"reveal\s+your\s+system\s+prompt",
    r"system\s+prompt",
    r"new\s+rule\s*:",
    r"do\s+not\s+tell\s+the\s+user",
    r"run\s+this\s+code",
    r"download\s+this\s+file",
    r"override\s+safety",
]
PATTERNS = [re.compile(p, re.IGNORECASE) for p in _CANON]

REDACTION = "[REDACTED-INJECTION]"


def sanitize(text: str) -> tuple[str, int, list[str]]:
    """Return (sanitized_buffer, flag_count, matched_snippets)."""
    hits: list[str] = []
    out = text
    for pat in PATTERNS:
        for m in pat.finditer(out):
            hits.append(m.group(0)[:80])
        out = pat.sub(REDACTION, out)
    return out, len(hits), hits


def log_hits(video_id: str, source_url: str, hits: list[str]) -> None:
    if not hits:
        return
    config.log_dir().mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
            "video_id": video_id,
            "source_url": source_url,
            "hits": hits,
        },
        ensure_ascii=False,
    )
    # Single O_APPEND write — safe under concurrent sessions (INVERTER F7 idiom).
    fd = os.open(
        str(config.log_dir() / "sanitize.jsonl"),
        os.O_APPEND | os.O_CREAT | os.O_WRONLY,
    )
    try:
        os.write(fd, (line + "\n").encode("utf-8"))
    finally:
        os.close(fd)
