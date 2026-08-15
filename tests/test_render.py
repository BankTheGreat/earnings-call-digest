import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_digest import render, schema

import golden_input

GOLDEN_KB = golden_input.FIXTURES / "expected_kb.md"


def build_render() -> str:
    transcript = golden_input.golden_transcript()
    normalized, rep = schema.validate(
        golden_input.golden_analysis_raw(), transcript, 150
    )
    assert rep.ok, rep.errors
    return render.render_kb(golden_input.golden_front(), normalized, transcript)


class TestRender(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(build_render(), build_render())

    def test_golden_byte_identical(self):
        expected = GOLDEN_KB.read_text(encoding="utf-8")
        self.assertEqual(build_render(), expected)

    def test_transcript_section_is_last_and_verbatim(self):
        out = build_render()
        analysis_end = out.index("<!-- ANALYSIS:END -->")
        transcript_at = out.index("## Full Transcript")
        self.assertGreater(transcript_at, analysis_end)
        self.assertIn(golden_input.golden_transcript().strip(), out)
        self.assertIn(render.UNTRUSTED_BANNER, out)

    def test_pending_render_has_placeholder(self):
        front = golden_input.golden_front()
        front["analysis_status"] = "pending"
        out = render.render_kb(front, None, golden_input.golden_transcript())
        self.assertIn("_Analysis pending", out)

    def test_frontmatter_roundtrip_via_writer(self):
        from earnings_digest import writer
        import tempfile

        out = build_render()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.md"
            p.write_text(out, encoding="utf-8", newline="\n")
            fm = writer.read_frontmatter(p)
        front = golden_input.golden_front()
        self.assertEqual(fm["video_id"], front["video_id"])
        self.assertEqual(fm["tickers"], ["PTT.BK"])
        self.assertEqual(fm["published"], "2026-07-15")
        self.assertEqual(fm["is_verbatim_source"], True)
        self.assertEqual(fm["revision"], "1")  # scalars parse as strings by design


if __name__ == "__main__":
    unittest.main()
