"""watcher discovery — pure matching logic + NEVER-GUESS resolution. The
network (_raw_search) is monkeypatched so these run fully offline."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_digest import watcher


class TestQuarterParse(unittest.TestCase):
    def test_accepts_forms(self):
        self.assertEqual(watcher.parse_quarter("Q2/2026"), (2, 2026))
        self.assertEqual(watcher.parse_quarter("2/2026"), (2, 2026))
        self.assertEqual(watcher.parse_quarter("Q2 2026"), (2, 2026))

    def test_rejects_bad(self):
        for bad in ("2026", "Q5/2026", "", "Q2/26", "junk"):
            with self.assertRaises(ValueError):
                watcher.parse_quarter(bad)


class TestMatching(unittest.TestCase):
    def test_thai_buddhist_era_year(self):
        # 2026 Gregorian == 2569 Buddhist Era; Thai OppDay titles use พ.ศ.
        self.assertTrue(watcher._title_has_quarter("TU งบ ไตรมาส 2/2569", 2, 2026))
        self.assertTrue(watcher._title_has_quarter("2Q2569 results", 2, 2026))

    def test_gregorian_year(self):
        self.assertTrue(watcher._title_has_quarter("Thai Union Q2/2026", 2, 2026))

    def test_wrong_quarter(self):
        self.assertFalse(watcher._title_has_quarter("TU Q1/2026", 2, 2026))

    def test_base_is_whole_word(self):
        self.assertTrue(watcher._title_has_base("TU Opportunity Day", "TU"))
        self.assertFalse(watcher._title_has_base("FUTURE studio", "TU"))


def _fake_entries(titles):
    return [{"id": f"vid{i:08d}xyz"[:11], "title": t, "duration": 3600}
            for i, t in enumerate(titles)]


class TestDiscoverNeverGuess(unittest.TestCase):
    def _patch(self, titles):
        watcher._raw_search = lambda q, n: _fake_entries(titles)  # type: ignore

    def tearDown(self):
        import importlib
        importlib.reload(watcher)

    def test_single_confident_returns_it(self):
        self._patch(["TU Opportunity Day Q2/2569", "unrelated clip", "TU teaser"])
        cand = watcher.discover("TU", "Q2/2026")
        self.assertTrue(cand.confident)
        self.assertIn("Q2/2569", cand.title)

    def test_zero_confident_raises_ambiguous(self):
        self._patch(["random clip", "TU Q1/2026 (wrong quarter)"])
        with self.assertRaises(watcher.AmbiguousError) as ctx:
            watcher.discover("TU", "Q2/2026")
        self.assertTrue(len(ctx.exception.candidates) >= 1)

    def test_many_confident_raises_ambiguous(self):
        self._patch(["TU Opportunity Day Q2/2569 part 1",
                     "TU OppDay Q2/2026 reupload"])
        with self.assertRaises(watcher.AmbiguousError):
            watcher.discover("TU", "Q2/2026")

    def test_search_failure_becomes_discovery_error(self):
        def boom(q, n):
            raise RuntimeError("network down\nsecond line")
        watcher._raw_search = boom  # type: ignore
        with self.assertRaises(watcher.DiscoveryError):
            watcher.search_candidates("TU", "Q2/2026")


if __name__ == "__main__":
    unittest.main()
