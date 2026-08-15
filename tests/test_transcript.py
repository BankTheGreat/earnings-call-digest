import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_digest import transcript as t

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXPECTED = (FIXTURES / "expected_transcript.txt").read_text(encoding="utf-8")


class TestNormalize(unittest.TestCase):
    def _pipeline(self, fmt: str, payload: str) -> str:
        return t.render_transcript(t.dedupe(t.normalize(fmt, payload)))

    def test_json3_golden(self):
        payload = (FIXTURES / "sample.json3").read_text(encoding="utf-8")
        self.assertEqual(self._pipeline("json3", payload), EXPECTED)

    def test_vtt_golden(self):
        payload = (FIXTURES / "sample.vtt").read_text(encoding="utf-8")
        self.assertEqual(self._pipeline("vtt", payload), EXPECTED)

    def test_rolling_extension_dedupe(self):
        segs = [(0.0, "รายได้"), (1.0, "รายได้เพิ่มขึ้นสิบห้าเปอร์เซ็นต์")]
        out = t.dedupe(segs)
        # Short prefix (<12 chars) is NOT treated as a rolling extension.
        self.assertEqual(len(out), 2)
        segs2 = [(0.0, "the revenue grew by"), (1.0, "the revenue grew by fifteen percent")]
        out2 = t.dedupe(segs2)
        self.assertEqual(len(out2), 1)
        self.assertEqual(out2[0], (0.0, "the revenue grew by fifteen percent"))

    def test_ts_helpers(self):
        self.assertEqual(t.fmt_ts(65), "01:05")
        self.assertEqual(t.fmt_ts(3725), "1:02:05")
        self.assertEqual(t.parse_ts("01:05"), 65)
        self.assertEqual(t.parse_ts("1:02:05"), 3725)
        self.assertIsNone(t.parse_ts("abc"))
        self.assertIsNone(t.parse_ts("1:2:3:4"))

    def test_marker_timestamps(self):
        self.assertEqual(t.marker_timestamps(EXPECTED), [0, 65, 125])

    def test_sha_stable(self):
        self.assertEqual(t.transcript_sha256(EXPECTED), t.transcript_sha256(EXPECTED))

    def test_plain_text_fallback(self):
        segs = t.normalize("txt", "just plain notes ไทย")
        self.assertEqual(segs, [(0.0, "just plain notes ไทย")])


if __name__ == "__main__":
    unittest.main()
