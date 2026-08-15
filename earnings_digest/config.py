# provenance: aerith-direct (acknowledged-bypass: standalone extraction of Master-Bank-owned engine per approved plan swift-mixing-stallman; original authored this session)
"""Configuration for earnings-call-digest.

Standalone: every path defaults to the current working directory, so the tool
runs anywhere with no folder structure to set up. Each default is overridable
by an ECD_* environment variable. Templates ship inside the package.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent


def pin_utf8() -> None:
    """UTF-8 stdio reconfigure (Windows consoles often default to a cp codepage)."""
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdin.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass


def _out_root() -> Path:
    return Path(os.environ.get("ECD_OUT_DIR", "out"))


def kb_root() -> Path:
    """Where the human-readable .md + .html renders are written (default ./out)."""
    return Path(os.environ.get("ECD_KB_ROOT", str(_out_root())))


def cache_root() -> Path:
    """Machine cache (transcript + analysis per video_id); default ./.cache/videos."""
    return Path(os.environ.get("ECD_CACHE_ROOT", str(Path(".cache") / "videos")))


def index_path() -> Path:
    """Append-only JSONL index (rebuildable); default ./out/index.jsonl."""
    return Path(os.environ.get("ECD_INDEX", str(_out_root() / "index.jsonl")))


def log_dir() -> Path:
    return Path(os.environ.get("ECD_LOG_DIR", str(Path(".cache") / "logs")))


# Templates ship inside the package — works from source and pip-installed.
TEMPLATE_PATH = _PKG_DIR / "templates" / "analyst_prompt.md"
POLISH_TEMPLATE_PATH = _PKG_DIR / "templates" / "polish_prompt.md"

# Subtitle language priority (manual tracks first, then auto captions).
SUB_LANG_PRIORITY = ["en", "en-US", "en-GB", "th"]

# Coarse [MM:SS] marker interval in the normalized transcript (quote anchoring).
MARKER_INTERVAL_S = 60

# Contract versions — part of the run key; bump on any breaking change.
PROMPT_VERSION = "stock-video-v1.2"
SCHEMA_VERSION = 1

# BYO-key API-mode defaults. The vendor's key comes from its own env var
# (GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY) — never bundled.
DEFAULT_VENDOR = os.environ.get("ECD_VENDOR", "gemini")
DEFAULT_MODEL = os.environ.get("ECD_MODEL", "gemini-2.5-flash")
MAX_OUTPUT_TOKENS = 16384
DEFAULT_MAX_SPEND_USD = float(os.environ.get("ECD_MAX_SPEND", "0.50"))

# Suffix synonyms canonicalized BEFORE any path/match is built.
SUFFIX_SYNONYMS = {
    "NASDAQ": "US", "NYSE": "US", "AMEX": "US", "ARCA": "US",
    "BKK": "BK", "SET": "BK", "HKEX": "HK", "HKG": "HK",
}

# Market folder per canonical suffix; unknown suffix -> OTHER-<SUFFIX>.
MARKET_MAP = {
    "BK": "TH-SET", "US": "US", "HK": "HK-HKEX", "T": "JP-TSE",
    "L": "UK-LSE", "SI": "SG-SGX", "AX": "AU-ASX", "SS": "CN-SSE",
    "SZ": "CN-SZSE", "VN": "VN-HOSE",
}

UNRESOLVED_DIRNAME = "_unresolved"
SOURCE_SHELF = "YouTube"
TITLE_SLUG_MAX = 40

# Exit codes (stable CLI contract).
EXIT_OK = 0
EXIT_KILL_SWITCH = 2
EXIT_TICKER = 3
EXIT_URL = 4
EXIT_LIVE = 5
EXIT_NETWORK = 6
EXIT_COST_GATE = 7
EXIT_VALIDATION = 8


def kill_switch_reason() -> str | None:
    if os.environ.get("ECD_DISABLED") == "1":
        return "ECD_DISABLED=1"
    return None


def market_for_suffix(suffix: str) -> str:
    s = (suffix or "").upper()
    return MARKET_MAP.get(s, f"OTHER-{s}" if s else "OTHER")
