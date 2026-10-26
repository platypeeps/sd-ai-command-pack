"""The longest `--help` texts hold usage, flags and exit codes only (sd:5996).

The pack's bin tools are an agent API (operator ruling, grill Q14): agents and
the dashboard run them, so a help text answers what to type and what the exit
status means, not why the tool exists. Each module docstring keeps the why.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from tests.clean_env import clean_environment

BIN = Path(__file__).resolve().parents[1] / "bin"
#: The five tools the ruling named, the longest helps when it was made.
TOOLS = ("sd-research-kit", "sd-review", "sd-note", "sd", "sd-ship")
#: Lines one help may take at 80 columns.
LIMIT = 40


class TrimmedHelp(unittest.TestCase):
    def test_each_help_is_short_and_names_its_exit_codes(self) -> None:
        for tool in TOOLS:
            with self.subTest(tool=tool):
                done = subprocess.run([sys.executable, str(BIN / tool), "--help"], capture_output=True, text=True,
                                      env=clean_environment(COLUMNS="80"), timeout=60, check=False)
                self.assertEqual(done.returncode, 0, done.stderr)
                lines = done.stdout.splitlines()
                self.assertLessEqual(len(lines), LIMIT, done.stdout)
                self.assertIn("Exit codes: 0 ", done.stdout)


if __name__ == "__main__":
    unittest.main()
