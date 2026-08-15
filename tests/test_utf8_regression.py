"""cp874 regression (INVERTER-verified live trap): the CLI must print Thai and
Unicode arrows even when the parent environment does NOT force UTF-8 — the
in-script reconfigure must carry it alone."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "earnings_digest" / "cli.py"


class TestUtf8Pin(unittest.TestCase):
    def test_selftest_survives_hostile_console_env(self):
        env = dict(os.environ)
        env.pop("PYTHONUTF8", None)
        env.pop("PYTHONIOENCODING", None)
        proc = subprocess.run(
            [sys.executable, str(CLI), "--selftest-unicode"],
            capture_output=True,
            env=env,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        out = proc.stdout.decode("utf-8", "replace")
        self.assertIn("ไทย", out)
        self.assertIn("→", out)


if __name__ == "__main__":
    unittest.main()
