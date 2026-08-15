# provenance: aerith-direct (acknowledged-bypass: self-contained reimplementation for the standalone distributable, per approved plan swift-mixing-stallman)
"""Ticker discipline — self-contained for the standalone distributable.

The AerithWorkspace build imports these primitives from one canonical
ticker_utils.py (§3.16 single-implementation rule). This public repo cannot
reach that file, so the five primitives (split_ticker / tickers_match /
ticker_dirname / ticker_from_dirname / canonical_set_ticker) are reimplemented
here with identical behavior. This is a deliberate, documented fork because the
package must ship independently.

Rules preserved:
  · bare-as-wildcard / qualified-must-match matching
  · unknown suffix -> the whole string is treated as a bare base (no misclassify)
  · Windows reserved device names (COM7, CON, ...) get a disk-safe escape
  · suffix synonyms (NVDA.NASDAQ vs NVDA.US) canonicalized before any path/match
"""
from __future__ import annotations

import re

from . import config


class TickerError(ValueError):
    pass


_QUALIFIED_RE = re.compile(r"^[A-Z0-9][A-Z0-9&-]{0,11}\.[A-Z]{1,8}$")

# Kept for compatibility with cli.py meta recording (no external shim here).
SHIM_SHA256 = "self-contained"

KNOWN_SUFFIXES = frozenset({
    "BK", "BKK", "SET", "NYSE", "NASDAQ", "HK", "HKG",
    "TO", "L", "SS", "SZ", "T", "KS", "KQ", "AX", "SI", "KL",
    "US", "PA", "DE", "MI", "SW", "TW", "JK", "VN",
})

# Windows reserved device stems: a file/folder whose pre-dot base equals one of
# these is creatable locally but some cloud-sync clients refuse it.
_WIN_RESERVED_STEMS = frozenset(
    {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


def split_ticker(raw):
    """Return (base_upper, suffix_or_None). Unknown suffix -> base absorbs it."""
    if not raw:
        return "", None
    s = raw.strip().upper()
    if "." not in s:
        return s, None
    base, suf = s.split(".", 1)
    if suf in KNOWN_SUFFIXES:
        return base, suf
    return s, None


def tickers_match(a, b) -> bool:
    """bare-as-wildcard / qualified-must-match."""
    if not a or not b:
        return False
    a_base, a_suf = split_ticker(a)
    b_base, b_suf = split_ticker(b)
    if a_base != b_base:
        return False
    if a_suf and b_suf:
        return a_suf == b_suf
    return True


def ticker_dirname(ticker: str) -> str:
    """ticker -> disk-safe folder/file name (escapes reserved device stems)."""
    t = ticker or ""
    stem = t.split(".", 1)[0]
    if stem.lower() not in _WIN_RESERVED_STEMS:
        return t
    if stem and stem[-1].isdigit():
        safe_stem = f"{stem[:-1]}-{stem[-1]}"   # COM7 -> COM-7
    else:
        safe_stem = f"{stem}-"                  # CON -> CON-
    return safe_stem + t[len(stem):]


def ticker_from_dirname(dirname: str) -> str:
    """Inverse of ticker_dirname; normal tickers returned unchanged."""
    t = dirname or ""
    stem = t.split(".", 1)[0]
    rest = t[len(stem):]
    if len(stem) >= 3 and stem[-1].isdigit() and stem[-2] == "-":
        candidate = stem[:-2] + stem[-1]        # COM-7 -> COM7
        if candidate.lower() in _WIN_RESERVED_STEMS:
            return candidate + rest
    if stem.endswith("-") and stem[:-1].lower() in _WIN_RESERVED_STEMS:
        return stem[:-1] + rest                 # CON- -> CON
    return t


def canonical_set_ticker(t: str) -> str:
    """A clean bare base is qualified to .BK; everything else unchanged (idempotent)."""
    if not t or not t.strip():
        return t or ""
    raw = t.strip()
    _, suf = split_ticker(raw)
    if suf is not None:
        return raw.upper()
    if "." in raw:
        return raw.upper()
    if ticker_from_dirname(raw) != raw:
        return raw.upper()
    return raw.upper() + ".BK"


# ── local helpers (already self-contained in the original) ────────────────────
def canonicalize(qualified: str) -> str:
    """Uppercase + map suffix synonyms to their canonical form."""
    base, suffix = split_ticker(qualified)
    if not suffix:
        raise TickerError(f"bare ticker {qualified!r} — qualified form required (e.g. PTT.BK)")
    suffix = config.SUFFIX_SYNONYMS.get(suffix.upper(), suffix.upper())
    return f"{base.upper()}.{suffix}"


def require_qualified(raw: str) -> str:
    """Validate + canonicalize a user-supplied ticker; raise TickerError if bare/bad."""
    t = (raw or "").strip().upper()
    if not t:
        raise TickerError("empty ticker")
    _, suffix = split_ticker(t)
    if not suffix:
        raise TickerError(
            f"bare ticker {t!r} is ambiguous — use the qualified form "
            "(PTT.BK, NVDA.US, 0700.HK)."
        )
    canon = canonicalize(t)
    if not _QUALIFIED_RE.match(canon):
        raise TickerError(f"ticker {canon!r} does not look like BASE.SUFFIX")
    return canon


def market_folder(qualified: str) -> str:
    _, suffix = split_ticker(canonicalize(qualified))
    return config.market_for_suffix(suffix or "")


def collisions(qualified: str, known: list[str]) -> list[str]:
    """Known qualified tickers whose BASE matches but whose canonical form differs."""
    canon = canonicalize(qualified)
    base, _ = split_ticker(canon)
    out = []
    for k in known:
        try:
            kc = canonicalize(k)
        except TickerError:
            continue
        kb, _ = split_ticker(kc)
        if kb == base and kc != canon:
            out.append(kc)
    return sorted(set(out))
