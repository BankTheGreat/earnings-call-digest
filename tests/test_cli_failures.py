import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_digest import cli, config


class TestCliFailurePaths(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        base = Path(self._td.name)
        os.environ["ECD_KB_ROOT"] = str(base / "kb [x]")
        os.environ["ECD_CACHE_ROOT"] = str(base / "cache")
        os.environ["ECD_INDEX"] = str(base / "index.jsonl")

    def tearDown(self):
        for k in (
            "ECD_KB_ROOT",
            "ECD_CACHE_ROOT",
            "ECD_INDEX",
            "ECD_DISABLED",
        ):
            os.environ.pop(k, None)
        self._td.cleanup()

    def test_playlist_url_exit_4(self):
        code = cli.main(["run", "https://www.youtube.com/playlist?list=PLxyz"])
        self.assertEqual(code, config.EXIT_URL)

    def test_channel_url_exit_4(self):
        code = cli.main(["run", "https://www.youtube.com/@channelname"])
        self.assertEqual(code, config.EXIT_URL)

    def test_bare_ticker_headless_exit_3_before_any_network(self):
        code = cli.main(["run", "https://youtu.be/dQw4w9WgXcQ", "--ticker", "PTT"])
        self.assertEqual(code, config.EXIT_TICKER)

    def test_kill_switch_exit_2(self):
        os.environ["ECD_DISABLED"] = "1"
        code = cli.main(["run", "https://youtu.be/dQw4w9WgXcQ"])
        self.assertEqual(code, config.EXIT_KILL_SWITCH)

    def test_selftest_unicode(self):
        self.assertEqual(cli.main(["--selftest-unicode"]), config.EXIT_OK)

    def test_finalize_without_cache_exit_8(self):
        code = cli.main(
            ["finalize", "dQw4w9WgXcQ", "--analysis-json", "does-not-exist.json"]
        )
        self.assertEqual(code, config.EXIT_VALIDATION)


if __name__ == "__main__":
    unittest.main()
