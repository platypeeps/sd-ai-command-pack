"""sd:3647: `make post-merge` refreshes the hub's pack checkout, then checks service health.

The lane runs it after a pack merge, once its runner lock is released (sd:3566).
The dry run reads what `make` would do and changes nothing.
"""

from __future__ import annotations

import pathlib
import subprocess
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def dry_run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["make", "-n", "--no-print-directory", "post-merge", *arguments], cwd=REPO_ROOT,
                          capture_output=True, text=True, check=False)


class ThePostMergeTarget(unittest.TestCase):
    def test_it_refreshes_this_checkout_then_checks_health(self) -> None:
        done = dry_run("SYSTEM_REPO=/example/system")
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = [line for line in done.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 2, done.stdout)
        self.assertIn(f'/example/system/local-repo-sync/repo-sync.sh" refresh "{REPO_ROOT}"', lines[0])
        self.assertIn('/example/system/local-project-dashboard/dashboard.sh" health', lines[1])

    def test_the_system_checkout_defaults_to_the_home_folder(self) -> None:
        done = dry_run()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("/repos/system/local-repo-sync/repo-sync.sh", done.stdout)


if __name__ == "__main__":
    unittest.main()
