"""Grounding (standalone explicit-path API): locate() takes user-supplied
--slide / --mda paths, never scans a private corpus. extract_text() reads a
PDF text layer with honest failure states; cross_check() confirms numbers by
digit-presence only (no rescaling, no guessing)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_digest import grounding
from earnings_digest.grounding import DocHit


class TestLocateExplicit(unittest.TestCase):
    def test_no_paths_reports_no_document_supplied(self):
        slide, mda = grounding.locate(None, None)
        self.assertEqual(slide.status, "absent")
        self.assertEqual(mda.status, "absent")
        self.assertIn("no document supplied", slide.detail)
        self.assertIsNone(slide.path)

    def test_missing_file_is_absent_not_a_guess(self):
        slide, _ = grounding.locate("C:/nope/does-not-exist.pdf", None)
        self.assertEqual(slide.status, "absent")
        self.assertIn("file not found", slide.detail)

    def test_existing_file_is_found(self):
        # Any real file on disk resolves to found (extract_text judges usability).
        here = str(Path(__file__).resolve())
        slide, mda = grounding.locate(here, None)
        self.assertEqual(slide.status, "found")
        self.assertEqual(slide.path, Path(here))
        self.assertEqual(mda.status, "absent")


class TestCrossCheck(unittest.TestCase):
    def _doc(self, text):
        return DocHit("slide", Path("x.pdf"), "found", text=text)

    def test_presence_confirm_and_unmatched(self):
        slide = self._doc("Revenue was 100,000 million baht this quarter.")
        mda = DocHit("mda", None, "absent")
        numbers = [
            {"value_text": "100,000 ล้านบาท"},   # digits present in slide
            {"value_text": "42.5%"},              # not present anywhere
        ]
        rep = grounding.cross_check(numbers, slide, mda)
        self.assertEqual(rep.checked_total, 2)
        self.assertEqual(rep.confirmed_total, 1)
        self.assertEqual(rep.per_number[0], "slide")
        self.assertEqual(rep.per_number[1], "none")

    def test_no_usable_docs_keeps_checked_none(self):
        slide = DocHit("slide", None, "absent")
        mda = DocHit("mda", None, "absent")
        rep = grounding.cross_check([{"value_text": "5"}], slide, mda)
        self.assertIsNone(rep.checked_total)   # None != 0 (nothing usable)
        self.assertIsNone(rep.confirmed_total)

    def test_both_when_present_in_slide_and_mda(self):
        slide = self._doc("total 100,000")
        mda = DocHit("mda", Path("m.pdf"), "found", text="figure 100,000 confirmed")
        rep = grounding.cross_check([{"value_text": "100,000"}], slide, mda)
        self.assertEqual(rep.per_number[0], "both")
        self.assertEqual(rep.confirmed_total, 1)


if __name__ == "__main__":
    unittest.main()


class TestFrontFields(unittest.TestCase):
    """Honesty fields: *_status must tell WHY the name field is null —
    a located-but-scanned PDF is NOT an absent PDF."""

    def _rep(self):
        from earnings_digest.grounding import GroundingReport
        r = GroundingReport()
        r.checked_total, r.confirmed_total = 5, 3
        return r

    def test_found_doc_keeps_name_and_status(self):
        f = grounding.front_fields(
            DocHit("slide", Path("A Opp Day 2026Q2.pdf"), "found"),
            DocHit("mda", Path("A MDA 2026Q2.pdf"), "found"), self._rep())
        self.assertEqual(f["grounding_slide"], "A Opp Day 2026Q2.pdf")
        self.assertEqual(f["grounding_slide_status"], "found")
        self.assertIsNone(f["grounding_slide_detail"])

    def test_scanned_doc_is_not_absent(self):
        f = grounding.front_fields(
            DocHit("slide", Path("XO Opp Day 2026Q2.pdf"), "no_text_layer",
                   "45 pages, no extractable text (scan?)"),
            DocHit("mda", None, "absent", "no document supplied"), self._rep())
        self.assertIsNone(f["grounding_slide"])
        self.assertEqual(f["grounding_slide_status"], "no_text_layer")
        self.assertIn("XO Opp Day 2026Q2.pdf", f["grounding_slide_detail"])
        self.assertEqual(f["grounding_mda_status"], "absent")
        self.assertNotIn(".pdf", f["grounding_mda_detail"] or "")
