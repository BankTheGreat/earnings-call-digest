"""Transcript + metadata acquisition with an explicit fallback chain (REQ-003).

Chain: user-supplied file -> yt_dlp (metadata + manual/auto subs, primary)
       -> youtube_transcript_api (fallback, transcript only) -> stub.

Every result carries provenance (acquisition_method, track kind) so a caption
is never confused with a model reconstruction (killer F1 of the REQ register).
Imports of yt_dlp / youtube_transcript_api / httpx are lazy so unit tests run
offline without them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .video_url import canonical_url


class LiveVideoError(RuntimeError):
    """Video is live/upcoming — transcript is not final."""


class NetworkError(RuntimeError):
    pass


@dataclass
class Track:
    kind: str = "none"          # manual | auto | user | none
    lang: str | None = None
    fmt: str | None = None      # json3 | vtt | srt | txt
    content: str | None = None  # raw track payload (not yet normalized)


@dataclass
class FetchResult:
    video_id: str
    meta: dict = field(default_factory=dict)
    track: Track = field(default_factory=Track)
    acquisition_method: str = "none"
    error: str | None = None    # human-readable reason when track.kind == "none"


def _published_from_info(info: dict) -> str | None:
    up = info.get("upload_date") or info.get("release_date")
    if isinstance(up, str) and len(up) == 8 and up.isdigit():
        return f"{up[0:4]}-{up[4:6]}-{up[6:8]}"
    return None


def _meta_from_info(info: dict) -> dict:
    return {
        "video_title": info.get("title") or "",
        "channel": info.get("channel") or info.get("uploader") or "",
        "published": _published_from_info(info),
        "duration_s": int(info.get("duration") or 0),
        "webpage_url": info.get("webpage_url") or "",
    }


def select_track(info: dict, langs: list[str]) -> tuple[str, str, dict] | None:
    """Pick (kind, lang, entry) from yt_dlp info. Manual subtitles win over auto."""
    for kind, key in (("manual", "subtitles"), ("auto", "automatic_captions")):
        tracks = info.get(key) or {}
        for lang in langs:
            # Exact first, then prefix match (th matches th-TH).
            candidates = [lang] + [k for k in tracks if k.lower().startswith(lang.lower() + "-")]
            for cand in candidates:
                entries = tracks.get(cand)
                if not entries:
                    continue
                by_ext = {e.get("ext"): e for e in entries if isinstance(e, dict)}
                for ext in ("json3", "vtt", "srv3", "srt"):
                    if ext in by_ext and by_ext[ext].get("url"):
                        return kind, cand, by_ext[ext]
    return None


def _download_url(url: str) -> str:
    import httpx  # lazy

    last = None
    for _ in range(3):
        try:
            resp = httpx.get(url, timeout=30.0, follow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:  # noqa: BLE001 — retried, then surfaced typed
            last = exc
    raise NetworkError(f"caption download failed after 3 attempts: {last}")


def _fetch_via_yt_dlp(video_id: str, langs: list[str]) -> FetchResult:
    import yt_dlp  # lazy

    opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(canonical_url(video_id), download=False)
    except yt_dlp.utils.DownloadError as exc:
        return FetchResult(
            video_id=video_id,
            meta={},
            track=Track(),
            acquisition_method="yt_dlp",
            error=f"yt_dlp: {str(exc).splitlines()[0][:300]}",
        )

    if info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
        raise LiveVideoError(
            f"live_status={info.get('live_status')} — transcript is not final; "
            "retry after the stream ends and processing completes"
        )

    meta = _meta_from_info(info)
    picked = select_track(info, langs)
    if picked is None:
        return FetchResult(
            video_id=video_id,
            meta=meta,
            track=Track(),
            acquisition_method="yt_dlp",
            error="no captions available in requested languages "
                  f"({','.join(langs)}) — neither manual nor auto",
        )
    kind, lang, entry = picked
    try:
        content = _download_url(entry["url"])
    except NetworkError as exc:
        # A caption-endpoint failure (e.g. HTTP 429) must NOT abort the chain:
        # return metadata + no track so fetch_video falls through to the
        # youtube_transcript_api fallback (real incident 2025 — timedtext 429'd
        # while the API fallback still returned the transcript).
        return FetchResult(
            video_id=video_id,
            meta=meta,
            track=Track(),
            acquisition_method="yt_dlp",
            error=f"caption download failed, falling back: {str(exc)[:200]}",
        )
    return FetchResult(
        video_id=video_id,
        meta=meta,
        track=Track(kind=kind, lang=lang, fmt=entry.get("ext"), content=content),
        acquisition_method="yt_dlp",
    )


def _fetch_via_yta(video_id: str, langs: list[str], meta: dict) -> FetchResult | None:
    """Fallback adapter: youtube_transcript_api (transcript only, no metadata)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # lazy
    except ImportError:
        return None
    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=langs)
    except Exception:  # noqa: BLE001 — fallback is best-effort by contract
        return None
    segments = [
        {"start": float(getattr(s, "start", 0.0)), "text": str(getattr(s, "text", ""))}
        for s in fetched
    ]
    if not segments:
        return None
    import json

    return FetchResult(
        video_id=video_id,
        meta=meta,
        track=Track(
            kind="auto",  # yta cannot reliably distinguish; label conservatively
            lang=getattr(fetched, "language_code", None) or (langs[0] if langs else None),
            fmt="yta_json",
            content=json.dumps({"segments": segments}, ensure_ascii=False),
        ),
        acquisition_method="youtube_transcript_api",
    )


def fetch_video(
    video_id: str,
    langs: list[str] | None = None,
    transcript_file: str | None = None,
) -> FetchResult:
    """Run the acquisition chain. Raises LiveVideoError / NetworkError; every
    other failure returns a stub-able FetchResult with .error set."""
    langs = langs or config.SUB_LANG_PRIORITY

    if transcript_file:
        p = Path(transcript_file)
        text = p.read_text(encoding="utf-8", errors="replace")
        fmt = p.suffix.lstrip(".").lower() or "txt"
        return FetchResult(
            video_id=video_id,
            meta={},
            track=Track(kind="user", lang=None, fmt=fmt, content=text),
            acquisition_method="user_supplied",
        )

    result = _fetch_via_yt_dlp(video_id, langs)
    if result.track.kind != "none":
        return result

    yta = _fetch_via_yta(video_id, langs, result.meta)
    if yta is not None:
        yta.error = None
        return yta
    return result  # stub-able: meta (maybe partial) + error reason
