"""fetch chain — a caption-download failure (e.g. HTTP 429 on the timedtext
endpoint) must fall through to the youtube_transcript_api fallback instead of
aborting the whole fetch. Real incident 2025: timedtext 429'd while the API
fallback still returned the transcript."""
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_digest import fetch as F
from earnings_digest.fetch import FetchResult, Track, NetworkError


def _fake_yt_dlp(info):
    mod = types.ModuleType("yt_dlp")

    class YDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            return info

    mod.YoutubeDL = YDL
    mod.utils = types.SimpleNamespace(DownloadError=Exception)
    return mod


def _raise_429(url):
    raise NetworkError("caption download failed after 3 attempts: 429 Too Many Requests")


class TestCaptionDownloadFallthrough(unittest.TestCase):
    def test_yt_dlp_caption_429_returns_none_not_raises(self):
        info = {
            "title": "XO Oppday",
            "duration": 100,
            "subtitles": {"th": [{"ext": "vtt", "url": "http://x/cap.vtt"}]},
            "automatic_captions": {},
        }
        sys.modules["yt_dlp"] = _fake_yt_dlp(info)
        orig = F._download_url
        F._download_url = _raise_429
        try:
            res = F._fetch_via_yt_dlp("vid00000001", ["th"])
        finally:
            F._download_url = orig
            sys.modules.pop("yt_dlp", None)
        self.assertEqual(res.track.kind, "none")               # did NOT raise
        self.assertIn("caption download failed", res.error or "")
        self.assertEqual(res.meta.get("video_title"), "XO Oppday")  # metadata kept

    def test_fetch_video_falls_through_to_api(self):
        none_res = FetchResult(
            video_id="v", meta={"video_title": "X"}, track=Track(),
            acquisition_method="yt_dlp",
            error="caption download failed, falling back: 429",
        )
        yta_res = FetchResult(
            video_id="v", meta={"video_title": "X"},
            track=Track(kind="auto", lang="th", fmt="yta_json",
                        content='{"segments":[{"start":0,"text":"hi"}]}'),
            acquisition_method="youtube_transcript_api",
        )
        oa, ob = F._fetch_via_yt_dlp, F._fetch_via_yta
        F._fetch_via_yt_dlp = lambda vid, langs: none_res
        F._fetch_via_yta = lambda vid, langs, meta: yta_res
        try:
            out = F.fetch_video("v", ["th"])
        finally:
            F._fetch_via_yt_dlp, F._fetch_via_yta = oa, ob
        self.assertEqual(out.track.kind, "auto")
        self.assertEqual(out.acquisition_method, "youtube_transcript_api")
        self.assertIsNone(out.error)


if __name__ == "__main__":
    unittest.main()
