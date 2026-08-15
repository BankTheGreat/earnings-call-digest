"""Strict YouTube URL -> 11-char video id parsing.

Accepts: watch?v=, youtu.be/, /shorts/, /live/, /embed/, m./www./music.
Rejects: playlist-only URLs, channel/handle URLs, non-YouTube hosts, bad ids.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
    "youtu.be",
}
_PATH_PREFIXES = ("/shorts/", "/live/", "/embed/", "/v/")


class UrlError(ValueError):
    """Typed URL error; .kind in {playlist, channel, host, id, shape}."""

    def __init__(self, kind: str, msg: str):
        super().__init__(msg)
        self.kind = kind


def _validate_id(candidate: str, source: str) -> str:
    candidate = candidate.strip()
    if not _ID_RE.match(candidate):
        raise UrlError("id", f"not a valid 11-char YouTube video id ({source}): {candidate!r}")
    return candidate


def parse_video_id(url: str) -> str:
    """Extract the video id or raise UrlError. Bare 11-char ids are accepted."""
    raw = (url or "").strip().strip('"').strip("'")
    if not raw:
        raise UrlError("shape", "empty URL")

    # Bare video id convenience (e.g. from the index or cache).
    if _ID_RE.match(raw) and "/" not in raw and "." not in raw:
        return raw

    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        raise UrlError("host", f"not a YouTube host: {host or '(none)'}")

    path = parsed.path or "/"
    query = parse_qs(parsed.query or "")

    if host == "youtu.be":
        seg = path.strip("/").split("/")[0]
        if not seg:
            raise UrlError("shape", "youtu.be URL without a video id")
        return _validate_id(seg, "youtu.be path")

    # Channel / handle URLs are not videos.
    if path.startswith(("/@", "/channel/", "/c/", "/user/")):
        raise UrlError("channel", "channel/handle URL — paste a single video URL")

    if path.startswith("/playlist"):
        raise UrlError(
            "playlist",
            "playlist URLs are not supported — paste a single video URL "
            "(watch / youtu.be / shorts / live)",
        )

    for prefix in _PATH_PREFIXES:
        if path.startswith(prefix):
            seg = path[len(prefix):].split("/")[0]
            return _validate_id(seg, f"{prefix} path")

    if path.startswith("/watch"):
        vals = query.get("v", [])
        if not vals:
            raise UrlError("shape", "watch URL without v= parameter")
        # list=/index=/t=/si= params are simply ignored (video proceeds alone).
        return _validate_id(vals[0], "v= parameter")

    raise UrlError("shape", f"unrecognized YouTube URL shape: {path}")


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"
