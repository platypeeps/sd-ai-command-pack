"""The developer identity file must stay out of version control.

Everything this repository does about developer identity in linked worktrees
rests on one fact: `.trellis/.developer` is gitignored, so a fresh worktree never
receives it. The resolution behavior itself belongs to vendored Trellis code and
is asserted by the staged suite under
`.trellis/tasks/08-08-developer-identity-not-in-worktrees/research/`, which skips
until an upstream release lands and therefore cannot live under this gate
(`Makefile:49` fails on any skip).
"""

from __future__ import annotations

import subprocess
import unittest

import install


class IdentityStaysIgnoredTests(unittest.TestCase):
    def test_the_identity_stays_ignored(self) -> None:
        completed = subprocess.run(
            ["git", "check-ignore", "-v", ".trellis/.developer"],
            cwd=install.ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(".developer", completed.stdout)


if __name__ == "__main__":
    unittest.main()
