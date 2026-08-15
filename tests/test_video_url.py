import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_digest.video_url import UrlError, canonical_url, parse_video_id

VID = "dQw4w9WgXcQ"


class TestParseVideoId(unittest.TestCase):
    def test_accepts_all_video_url_shapes(self):
        accepted = [
            f"https://www.youtube.com/watch?v={VID}",
            f"https://youtube.com/watch?v={VID}",
            f"http://m.youtube.com/watch?v={VID}",
            f"https://music.youtube.com/watch?v={VID}",
            f"https://www.youtube.com/watch?v={VID}&t=42s&list=PLxyz&index=3",
            f"https://youtu.be/{VID}",
            f"https://youtu.be/{VID}?si=abc123&t=10",
            f"youtu.be/{VID}",
            f"https://www.youtube.com/shorts/{VID}",
            f"https://www.youtube.com/live/{VID}",
            f"https://www.youtube.com/embed/{VID}",
            f"https://www.youtube.com/v/{VID}",
            f"www.youtube.com/watch?v={VID}",
            VID,  # bare id convenience
        ]
        for url in accepted:
            with self.subTest(url=url):
                self.assertEqual(parse_video_id(url), VID)

    def test_rejections(self):
        cases = [
            ("https://www.youtube.com/playlist?list=PLxyz", "playlist"),
            ("https://www.youtube.com/@somechannel", "channel"),
            ("https://www.youtube.com/channel/UCabc", "channel"),
            ("https://www.youtube.com/c/somename", "channel"),
            ("https://vimeo.com/12345", "host"),
            ("https://notyoutube.com/watch?v=" + VID, "host"),
            ("https://evil.com/youtube.com/watch?v=" + VID, "host"),
            ("https://www.youtube.com/watch", "shape"),
            ("https://www.youtube.com/watch?v=shortid", "id"),
            ("https://www.youtube.com/watch?v=toolongvideoid99", "id"),
            ("https://youtu.be/", "shape"),
            ("", "shape"),
            ("https://www.youtube.com/watch?v=bad*chars!!", "id"),
        ]
        for url, kind in cases:
            with self.subTest(url=url):
                with self.assertRaises(UrlError) as ctx:
                    parse_video_id(url)
                self.assertEqual(ctx.exception.kind, kind)

    def test_canonical_url(self):
        self.assertEqual(canonical_url(VID), f"https://www.youtube.com/watch?v={VID}")


if __name__ == "__main__":
    unittest.main()
