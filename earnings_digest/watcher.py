"""Ticker + quarter -> YouTube OppDay video discovery (best-effort, NEVER-GUESS).

The killer failure of this feature is auto-filing the WRONG company's video
(silent poisoning of the knowledge base). So discovery is deliberately timid:

  · A candidate is CONFIDENT only if its title contains BOTH the ticker base
    AND the requested quarter (Gregorian OR Thai Buddhist-Era year, since Thai
    OppDay titles use พ.ศ. — 2026 -> 2569).
  · Exactly ONE confident candidate  -> return it (the auto path).
  · Zero, or two-or-more confident    -> raise Ambiguous: the caller prints the
    candidate list and requires the user to pass an explicit --url. A wrong
    guess is worse than asking.

yt_dlp is imported lazily (as in fetch.py) so the unit tests run offline; the
network path is exercised only by the live smoke test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .video_url import canonical_url


@dataclass
class Candidate:
    video_id: str
    title: str
    channel: str
    duration_s: int
    url: str
    confident: bool = False


class DiscoveryError(RuntimeError):
    """No usable candidate could be resolved."""


class AmbiguousError(DiscoveryError):
    """Zero or several confident candidates — the caller must let the user pick."""

    def __init__(self, message: str, candidates: list[Candidate]):
        super().__init__(message)
        self.candidates = candidates


_QUARTER_RE = re.compile(r"^\s*Q?([1-4])\s*[/\- ]\s*(\d{4})\s*$", re.IGNORECASE)


def parse_quarter(quarter: str) -> tuple[int, int]:
    """'Q2/2026' | '2/2026' | 'Q2 2026' -> (2, 2026). Raises ValueError."""
    m = _QUARTER_RE.match(quarter or "")
    if not m:
        raise ValueError(
            f"quarter {quarter!r} is not Q<n>/<yyyy> (e.g. Q2/2026)"
        )
    q, year = int(m.group(1)), int(m.group(2))
    if year < 1900 or year > 2999:
        raise ValueError(f"quarter {quarter!r}: implausible year {year}")
    return q, year


def _quarter_tokens(q: int, year: int) -> list[str]:
    """Substrings any of which, present in a title, confirms the quarter.
    Includes the Thai Buddhist-Era year (Gregorian + 543) — Thai OppDay
    titles overwhelmingly use พ.ศ."""
    be = year + 543
    toks: list[str] = []
    for y in (year, be):
        toks += [
            f"q{q}/{y}", f"q{q} {y}", f"q{q}-{y}", f"q{q}{y}",
            f"{q}q{y}", f"{q}q/{y}", f"{q}q {y}",
            f"ไตรมาส {q}/{y}", f"ไตรมาส {q} {y}", f"ไตรมาส{q}/{y}",
        ]
    return toks


def _title_has_quarter(title: str, q: int, year: int) -> bool:
    low = re.sub(r"\s+", " ", (title or "").lower())
    compact = low.replace(" ", "")
    for tok in _quarter_tokens(q, year):
        t = tok.lower()
        if t in low or t.replace(" ", "") in compact:
            return True
    return False


def _title_has_base(title: str, base: str) -> bool:
    """Whole-word base match (avoids TU matching 'STUDIO'/'FUTURE')."""
    if not base:
        return False
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(base)}(?![A-Za-z0-9])",
                     title or "", re.IGNORECASE) is not None


def _search_queries(base: str, q: int, year: int) -> list[str]:
    # "OppDay" and "Earnings Call" are INTERCHANGEABLE — SET renamed the format
    # from 2026, so a video may be titled either way; search BOTH or 2026+ videos
    # are missed. YouTube search returns a narrow, unstable slice from any single
    # query, so we run several focused ANGLES (both terms, broad + quarter-focused)
    # and merge. (Over-stuffing ONE query with every term returns zero results.)
    return [
        f"{base} oppday โอกาสเดย์",
        f"{base} earnings call oppday",
        f"{base} oppday Q{q}/{year}",
        f"{base} earnings call Q{q}/{year}",
    ]


def _raw_search(query: str, n: int) -> list[dict]:
    import yt_dlp  # lazy, matches fetch.py

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,      # search page only — no per-video extraction
        "socket_timeout": 30,
        "retries": 3,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    return [e for e in (info.get("entries") or []) if e]


def _search_all(base: str, q: int, year: int, n: int) -> list[dict]:
    """Run every broad query and merge, deduping by video id (one query alone
    is an unreliable narrow slice of YouTube search)."""
    seen: set[str] = set()
    out: list[dict] = []
    for query in _search_queries(base, q, year):
        for e in _raw_search(query, n):
            vid = e.get("id")
            if vid and vid not in seen:
                seen.add(vid)
                out.append(e)
    return out


def _to_candidate(entry: dict, base: str, q: int, year: int) -> Candidate:
    vid = entry.get("id") or ""
    title = entry.get("title") or ""
    return Candidate(
        video_id=vid,
        title=title,
        channel=entry.get("channel") or entry.get("uploader") or "",
        duration_s=int(entry.get("duration") or 0),
        url=entry.get("url") or canonical_url(vid),
        confident=_title_has_base(title, base) and _title_has_quarter(title, q, year),
    )


def search_candidates(base: str, quarter: str, n: int = 12) -> list[Candidate]:
    """Return ranked candidates (confident first). Raises ValueError on a bad
    quarter; propagates yt_dlp/network errors to the caller (mapped by cli)."""
    q, year = parse_quarter(quarter)
    try:
        entries = _search_all(base, q, year, n)
    except Exception as exc:  # noqa: BLE001 — surfaced as a typed, truncated error
        raise DiscoveryError(
            f"YouTube search failed ({type(exc).__name__}): {str(exc).splitlines()[0][:200]}"
        ) from None
    cands = [_to_candidate(e, base, q, year) for e in entries if e.get("id")]
    cands.sort(key=lambda c: (not c.confident,))  # confident first, stable otherwise
    return cands


def discover(base: str, quarter: str, n: int = 12) -> Candidate:
    """NEVER-GUESS resolution. Returns the single confident candidate, or raises
    AmbiguousError carrying the candidate list for the caller to display."""
    cands = search_candidates(base, quarter, n)
    confident = [c for c in cands if c.confident]
    if len(confident) == 1:
        return confident[0]
    if not confident:
        raise AmbiguousError(
            f"no video whose title contains both {base!r} and quarter {quarter} "
            f"(searched {len(cands)} result(s)) — pass the exact --url instead",
            cands,
        )
    raise AmbiguousError(
        f"{len(confident)} videos match {base!r} + {quarter} — pass the exact "
        "--url of the right one (never auto-file an ambiguous match)",
        confident,
    )
