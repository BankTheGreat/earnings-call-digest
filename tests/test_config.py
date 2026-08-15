"""config — standalone cwd defaults + ECD_* env overrides. No workspace paths,
no OneDrive, templates ship inside the package."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_digest import config


class TestDefaults(unittest.TestCase):
    def setUp(self):
        import os
        self._saved = {k: os.environ.pop(k, None)
                       for k in ("ECD_OUT_DIR", "ECD_KB_ROOT", "ECD_CACHE_ROOT",
                                 "ECD_INDEX", "ECD_LOG_DIR", "ECD_DISABLED")}

    def tearDown(self):
        import os
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_cwd_relative_defaults(self):
        self.assertEqual(config.kb_root(), Path("out"))
        self.assertEqual(config.index_path(), Path("out") / "index.jsonl")
        self.assertEqual(config.cache_root(), Path(".cache") / "videos")

    def test_out_dir_repoints_kb_and_index(self):
        import os
        os.environ["ECD_OUT_DIR"] = "renders"
        self.assertEqual(config.kb_root(), Path("renders"))
        self.assertEqual(config.index_path(), Path("renders") / "index.jsonl")
        # cache is independent of --out
        self.assertEqual(config.cache_root(), Path(".cache") / "videos")

    def test_explicit_overrides_win(self):
        import os
        os.environ["ECD_KB_ROOT"] = "K"
        os.environ["ECD_INDEX"] = "K/i.jsonl"
        self.assertEqual(config.kb_root(), Path("K"))
        self.assertEqual(config.index_path(), Path("K/i.jsonl"))

    def test_templates_ship_in_package(self):
        self.assertTrue(config.TEMPLATE_PATH.is_file())
        self.assertTrue(config.POLISH_TEMPLATE_PATH.is_file())
        self.assertEqual(config.TEMPLATE_PATH.parent.name, "templates")

    def test_kill_switch(self):
        import os
        self.assertIsNone(config.kill_switch_reason())
        os.environ["ECD_DISABLED"] = "1"
        self.assertEqual(config.kill_switch_reason(), "ECD_DISABLED=1")


if __name__ == "__main__":
    unittest.main()
