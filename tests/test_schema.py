import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_digest import schema

import golden_input

TRANSCRIPT = golden_input.golden_transcript()
DURATION = 150


class TestValidate(unittest.TestCase):
    def test_golden_analysis_passes_with_verified_quotes(self):
        norm, rep = schema.validate(golden_input.golden_analysis_raw(), TRANSCRIPT, DURATION)
        self.assertTrue(rep.ok, rep.errors)
        self.assertEqual(rep.quote_fail_count, 0)
        self.assertEqual(norm["claims"][0]["verification"], "quote_verified")
        self.assertEqual(norm["numbers"][0]["verification"], "quote_verified")

    def test_fact_without_quote_rejected(self):
        analysis = {
            "summary": ["x"],
            "claims": [{"text": "Revenue doubled", "type": "fact", "ts": "01:05"}],
        }
        _, rep = schema.validate(analysis, TRANSCRIPT, DURATION)
        self.assertFalse(rep.ok)
        self.assertTrue(any("requires a short verbatim quote" in e for e in rep.errors))

    def test_fabrication_tripwire(self):
        analysis = {
            "summary": ["x"],
            "claims": [
                {"text": "a", "type": "opinion", "quote": "this text is nowhere"},
                {"text": "b", "type": "opinion", "quote": "also fabricated entirely"},
            ],
        }
        _, rep = schema.validate(analysis, TRANSCRIPT, DURATION)
        self.assertFalse(rep.ok)
        self.assertTrue(any("fabrication suspicion" in e for e in rep.errors))
        self.assertEqual(rep.quote_fail_count, 2)

    def test_minor_quote_failure_marks_but_passes(self):
        analysis = golden_input.golden_analysis_raw()
        # 1 bad quote out of 3 anchored items (2 claims + 1 number) = 33%... make it 1/4.
        analysis["claims"].append(
            {"text": "extra", "type": "opinion", "quote": "รายได้ 100,000 ล้านบาท"}
        )
        analysis["claims"][1]["quote"] = "not present anywhere at all"
        norm, rep = schema.validate(analysis, TRANSCRIPT, DURATION)
        self.assertTrue(rep.ok, rep.errors)
        self.assertEqual(rep.quote_fail_count, 1)
        self.assertEqual(norm["claims"][1]["verification"], "quote_not_found")

    def test_bad_timestamp_rejected(self):
        analysis = {
            "summary": ["x"],
            "claims": [{"text": "a", "type": "opinion", "ts": "99:99", "quote": ""}],
        }
        _, rep = schema.validate(analysis, TRANSCRIPT, DURATION)
        self.assertFalse(rep.ok)
        self.assertTrue(any("exceeds video duration" in e for e in rep.errors))

    def test_unparseable_timestamp_rejected(self):
        analysis = {"summary": ["x"], "numbers": [{"value_text": "15", "ts": "noon"}]}
        _, rep = schema.validate(analysis, TRANSCRIPT, DURATION)
        self.assertFalse(rep.ok)

    def test_confidence_out_of_range_rejected(self):
        analysis = {
            "summary": ["x"],
            "entities": [{"company": "PTT", "confidence": 1.5}],
        }
        _, rep = schema.validate(analysis, TRANSCRIPT, DURATION)
        self.assertFalse(rep.ok)

    def test_bare_ticker_demoted_to_hint(self):
        analysis = {
            "summary": ["x"],
            "entities": [{"company": "PTT", "ticker": "PTT", "confidence": 0.9}],
        }
        norm, rep = schema.validate(analysis, TRANSCRIPT, DURATION)
        self.assertTrue(rep.ok, rep.errors)
        self.assertIsNone(norm["entities"][0]["ticker"])
        self.assertEqual(norm["entities"][0]["ticker_hint_rejected"], "PTT")

    def test_unknown_claim_type_rejected(self):
        analysis = {
            "summary": ["x"],
            "claims": [{"text": "a", "type": "prophecy", "quote": ""}],
        }
        _, rep = schema.validate(analysis, TRANSCRIPT, DURATION)
        self.assertFalse(rep.ok)

    def test_empty_summary_rejected(self):
        _, rep = schema.validate({"summary": []}, TRANSCRIPT, DURATION)
        self.assertFalse(rep.ok)

    def test_not_a_dict_rejected(self):
        _, rep = schema.validate(["not", "a", "dict"], TRANSCRIPT, DURATION)
        self.assertFalse(rep.ok)


if __name__ == "__main__":
    unittest.main()
