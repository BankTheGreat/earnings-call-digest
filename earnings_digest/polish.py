"""REQ-012 polished-transcript guards (Phase-1 of the legacy analyst template).

A polished transcript is an LLM PARAPHRASE — it structurally cannot be
quote-anchored (killer F-v3-1), so it is admitted only through mechanical
gates, renders under an [AI-EDITED] label, and the verbatim raw stays the
sole citation-grade surface at the tail of every KB file. Polish failure
DEGRADES (polish_status: failed) — it never blocks analysis or the KB render.

Gates:
  G1 number preservation — the multiset of numeric tokens (timestamps
     excluded, Thai digits normalized, thousand-commas stripped) must be
     IDENTICAL between raw and polished. Any lost/altered figure rejects.
  G2 chronological sanctity — [MM:SS] markers in the polish must form a
     monotonic subsequence of the raw markers (no reordering, no invention).
  G3 anti-summarization — a polish under MIN_LENGTH_RATIO of the raw
     dialogue length is a covert summary, rejected.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

MIN_LENGTH_RATIO = 0.40

_MARKER = re.compile(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]")
_NUM_TOKEN = re.compile(r"\d[\d,\.]*")
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


@dataclass
class PolishReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    raw_numbers: int = 0
    polished_numbers: int = 0
    raw_markers: int = 0
    polished_markers: int = 0


def _strip_markers(text: str) -> str:
    return _MARKER.sub(" ", text or "")


def _number_multiset(text: str) -> Counter:
    """Numeric tokens with timestamps removed first; commas stripped and a
    trailing dot dropped so pure formatting shifts do not false-alarm, while
    a changed or missing figure still breaks multiset equality."""
    cleaned = _strip_markers(text).translate(_THAI_DIGITS)
    toks = []
    for t in _NUM_TOKEN.findall(cleaned):
        t = t.replace(",", "").rstrip(".")
        if t:
            toks.append(t)
    return Counter(toks)


def _markers(text: str) -> list[str]:
    return _MARKER.findall(text or "")


def _is_subsequence(needle: list[str], hay: list[str]) -> bool:
    it = iter(hay)
    return all(any(h == n for h in it) for n in needle)


def validate_polish(raw: str, polished: str) -> PolishReport:
    """Admit `polished` only if every gate passes. Empty/None polish fails."""
    rep = PolishReport()
    if not (polished or "").strip():
        rep.ok = False
        rep.errors.append("polish: empty")
        return rep

    raw_nums = _number_multiset(raw)
    pol_nums = _number_multiset(polished)
    rep.raw_numbers = sum(raw_nums.values())
    rep.polished_numbers = sum(pol_nums.values())
    if raw_nums != pol_nums:
        missing = raw_nums - pol_nums
        added = pol_nums - raw_nums
        if missing:
            sample = ", ".join(list(missing.elements())[:5])
            rep.errors.append(f"polish G1: number(s) lost/changed — missing from polish: {sample}")
        if added:
            sample = ", ".join(list(added.elements())[:5])
            rep.errors.append(f"polish G1: number(s) not present in raw: {sample}")

    raw_marks = _markers(raw)
    pol_marks = _markers(polished)
    rep.raw_markers = len(raw_marks)
    rep.polished_markers = len(pol_marks)
    if pol_marks and not _is_subsequence(pol_marks, raw_marks):
        rep.errors.append(
            "polish G2: [MM:SS] markers are not a monotonic subsequence of the raw markers"
        )

    raw_len = len(_strip_markers(raw).strip())
    pol_len = len(_strip_markers(polished).strip())
    if raw_len and pol_len < MIN_LENGTH_RATIO * raw_len:
        rep.errors.append(
            f"polish G3: too short ({pol_len} vs raw {raw_len} chars, "
            f"< {int(MIN_LENGTH_RATIO * 100)}%) — looks like a summary, not a polish"
        )

    rep.ok = not rep.errors
    return rep
