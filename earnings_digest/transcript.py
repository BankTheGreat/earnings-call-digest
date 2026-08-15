"""Normalize caption payloads (json3 / VTT / SRT / yta) into plain text with
coarse [MM:SS] markers every MARKER_INTERVAL_S seconds (quote anchoring).

Rolling auto-captions repeat lines across cues — consecutive duplicates are
collapsed. Raw source payloads are never modified; this module produces the
canonical normalized transcript that everything downstream hashes and reads.
"""
from __future__ import annotations

import hashlib
import json
import re

from . import config

Segment = tuple[float, str]  # (start_seconds, text)


def fmt_ts(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def parse_ts(ts: str) -> float | None:
    parts = (ts or "").strip().split(":")
    if not (2 <= len(parts) <= 3):
        return None
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if any(n < 0 for n in nums):
        return None
    if len(parts) == 2:
        return nums[0] * 60 + nums[1]
    return nums[0] * 3600 + nums[1] * 60 + nums[2]


def _clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)          # inline cue tags
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def segments_from_json3(payload: str) -> list[Segment]:
    data = json.loads(payload)
    out: list[Segment] = []
    for ev in data.get("events") or []:
        segs = ev.get("segs")
        if not segs:
            continue
        start = float(ev.get("tStartMs") or 0) / 1000.0
        text = _clean_text("".join(s.get("utf8", "") for s in segs))
        if text:
            out.append((start, text))
    return out


_VTT_TS = re.compile(
    r"(?P<h>\d{1,2}:)?(?P<m>\d{2}):(?P<s>\d{2})[.,]\d{3}\s*-->"
)


def segments_from_vtt(payload: str) -> list[Segment]:
    """Works for WEBVTT and (tolerantly) SRT — both use HH:MM:SS timelines."""
    out: list[Segment] = []
    current: float | None = None
    buf: list[str] = []

    def flush():
        nonlocal buf, current
        if current is not None and buf:
            text = _clean_text(" ".join(buf))
            if text:
                out.append((current, text))
        buf = []

    for line in payload.splitlines():
        line = line.strip("﻿").rstrip()
        m = _VTT_TS.search(line)
        if m:
            flush()
            h = int((m.group("h") or "0:").rstrip(":") or 0)
            current = h * 3600 + int(m.group("m")) * 60 + int(m.group("s"))
            continue
        if not line or line == "WEBVTT" or line.isdigit() or line.startswith(("NOTE", "STYLE", "Kind:", "Language:")):
            continue
        if current is not None:
            buf.append(line)
    flush()
    return out


def segments_from_yta(payload: str) -> list[Segment]:
    data = json.loads(payload)
    out: list[Segment] = []
    for seg in data.get("segments") or []:
        text = _clean_text(str(seg.get("text", "")))
        if text:
            out.append((float(seg.get("start", 0.0)), text))
    return out


def segments_from_plain(payload: str) -> list[Segment]:
    """User-supplied .txt/.md with no timeline — one pseudo-segment at t=0."""
    text = payload.strip()
    return [(0.0, text)] if text else []


def normalize(fmt: str | None, payload: str) -> list[Segment]:
    fmt = (fmt or "").lower()
    if fmt in ("json3", "srv3"):
        return segments_from_json3(payload)
    if fmt in ("vtt", "srt"):
        return segments_from_vtt(payload)
    if fmt == "yta_json":
        return segments_from_yta(payload)
    if payload.lstrip().startswith("WEBVTT"):
        return segments_from_vtt(payload)
    return segments_from_plain(payload)


def dedupe(segments: list[Segment]) -> list[Segment]:
    """Collapse consecutive repeats (rolling auto-captions) and mid-roll overlap
    where a cue begins with the previous cue's text."""
    out: list[Segment] = []
    for start, text in segments:
        if out:
            _, prev = out[-1]
            if text == prev:
                continue
            if text.startswith(prev) and len(prev) > 12:
                out[-1] = (out[-1][0], text)  # rolling extension — keep earliest ts
                continue
        out.append((start, text))
    return out


def render_transcript(segments: list[Segment], interval: int | None = None) -> str:
    """Emit normalized text with a [MM:SS] marker at the first segment crossing
    each interval boundary. Marker cost ≈ 0.5% of tokens; anchors Key Claims."""
    interval = interval or config.MARKER_INTERVAL_S
    lines: list[str] = []
    next_marker = 0.0
    for start, text in segments:
        if start >= next_marker:
            lines.append(f"\n[{fmt_ts(start)}]")
            next_marker = (int(start // interval) + 1) * interval
        lines.append(text)
    return " ".join(lines).replace(" \n", "\n").strip() + "\n"


def transcript_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def marker_timestamps(text: str) -> list[float]:
    """All [MM:SS]/[H:MM:SS] marker values present in a normalized transcript."""
    out = []
    for m in re.finditer(r"\[(\d{1,2}:)?(\d{2}):(\d{2})\]", text):
        h = int((m.group(1) or "0:").rstrip(":") or 0)
        out.append(h * 3600 + int(m.group(2)) * 60 + int(m.group(3)))
    return out
