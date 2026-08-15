import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_digest import tickers
from earnings_digest.tickers import TickerError


class TestTickers(unittest.TestCase):
    def test_self_contained_fork(self):
        # The standalone reimplements the 5 primitives locally (no canonical
        # ticker_utils to load); the compat marker records that fork.
        self.assertEqual(tickers.SHIM_SHA256, "self-contained")
        self.assertEqual(tickers.split_ticker("PTT.BK"), ("PTT", "BK"))
        self.assertEqual(tickers.split_ticker("PTT"), ("PTT", None))
        self.assertTrue(tickers.tickers_match("PTT", "PTT.BK"))      # bare wildcard
        self.assertFalse(tickers.tickers_match("PTT.BK", "PTT.HK"))  # qualified must match
        self.assertEqual(tickers.canonical_set_ticker("ptt"), "PTT.BK")

    def test_require_qualified_rejects_bare(self):
        for bad in ("PTT", "nvda", "", "  "):
            with self.subTest(bad=bad):
                with self.assertRaises(TickerError):
                    tickers.require_qualified(bad)

    def test_require_qualified_accepts_and_canonicalizes(self):
        self.assertEqual(tickers.require_qualified("ptt.bk"), "PTT.BK")
        self.assertEqual(tickers.require_qualified("NVDA.US"), "NVDA.US")
        self.assertEqual(tickers.require_qualified("0700.HK"), "0700.HK")

    def test_suffix_synonyms_canonicalized(self):
        self.assertEqual(tickers.canonicalize("NVDA.NASDAQ"), "NVDA.US")
        self.assertEqual(tickers.canonicalize("JPM.NYSE"), "JPM.US")
        self.assertEqual(tickers.canonicalize("PTT.BKK"), "PTT.BK")
        self.assertEqual(tickers.canonicalize("PTT.SET"), "PTT.BK")

    def test_market_folder(self):
        self.assertEqual(tickers.market_folder("PTT.BK"), "TH-SET")
        self.assertEqual(tickers.market_folder("NVDA.US"), "US")
        self.assertEqual(tickers.market_folder("0700.HK"), "HK-HKEX")
        self.assertEqual(tickers.market_folder("SAP.DE"), "OTHER-DE")

    def test_com7_dirname_roundtrip(self):
        d = tickers.ticker_dirname("COM7.BK")
        self.assertNotEqual(d.split(".")[0].upper(), "COM7")  # reserved name escaped
        self.assertEqual(tickers.ticker_from_dirname(d), "COM7.BK")

    def test_collisions(self):
        known = ["PTT.BK", "NVDA.US", "ABC.HK"]
        self.assertEqual(tickers.collisions("ABC.BK", known), ["ABC.HK"])
        self.assertEqual(tickers.collisions("PTT.BK", known), [])
        # Synonym suffix does NOT count as a collision with itself (F5).
        self.assertEqual(tickers.collisions("NVDA.NASDAQ", known), [])


if __name__ == "__main__":
    unittest.main()
