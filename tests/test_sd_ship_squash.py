"""`sd_ship_squash.squashed_heads` against real git histories (sd:1409).

`tests/test_sd_ship.py` covers the warning end to end through `sd-ship
prepare`. These cases pin the path split itself: which paths `--ours` may
take is a claim about the merge that is about to happen, so each one builds
that merge's history and checks the claim against it.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import sd_lib  # noqa: E402
import sd_ship_squash  # noqa: E402


class SquashedHeadPaths(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.git("init", "-q", "--initial-branch=main", ".")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True,
                              text=True).stdout.strip()

    def commit(self, message: str, files: dict[str, str]) -> str:
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            self.git("add", "--", name)
        self.git("commit", "-q", "--no-verify", "-m", message)
        return self.git("rev-parse", "HEAD")

    def squash_merge(self, files: dict[str, str]) -> tuple[str, str]:
        """Branch `pr` off main, then squash it onto main. Returns (tip, squash);
        `feature` starts at the tip, carrying it."""
        self.git("checkout", "-q", "-b", "pr")
        tip = self.commit("pr", files)
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--squash", "pr")
        squash = self.commit("squash pr", {})
        self.git("checkout", "-q", "-b", "feature", tip)
        return tip, squash

    def split(self, tip: str, squash: str) -> dict:
        receipt = {"item": 1, "head": tip, "merge_commit": squash}
        found = sd_ship_squash.squashed_heads(self.root, "main", "feature", [receipt])
        self.assertEqual(len(found), 1, found)
        return found[0]

    def test_a_revert_on_main_after_a_shared_value_is_read_by_hand(self) -> None:
        """The squashed head set 1. Both sides then share 2 through a merge,
        main reverts to 1, and the feature moves to 3. Main's blob equals the
        squashed head's, yet `--ours` would discard main's revert: against the
        real merge base, which holds 2, main changed the path."""
        self.commit("base", {"f.txt": "0\n"})
        tip, squash = self.squash_merge({"f.txt": "1\n"})
        self.git("checkout", "-q", "main")
        self.commit("main moves to 2", {"f.txt": "2\n"})
        self.git("checkout", "-q", "feature")
        subprocess.run(["git", "merge", "-q", "--no-commit", "main"], cwd=self.root, capture_output=True)
        (self.root / "f.txt").write_text("2\n")
        self.git("add", "f.txt")
        self.git("commit", "-q", "--no-verify", "-m", "share 2")
        self.git("checkout", "-q", "main")
        self.commit("main reverts to 1", {"f.txt": "1\n"})
        self.git("checkout", "-q", "feature")
        self.commit("feature moves to 3", {"f.txt": "3\n"})
        entry = self.split(tip, squash)
        self.assertEqual(entry["ours"], [])
        self.assertEqual(entry["by_hand"], ["f.txt"])

    def test_the_squash_alone_is_safe_for_ours(self) -> None:
        """The positive case: main's only change to the path is the squash,
        which the feature carries, so `--ours` loses nothing."""
        self.commit("base", {"f.txt": "0\n"})
        tip, squash = self.squash_merge({"f.txt": "1\n"})
        self.git("checkout", "-q", "main")
        self.commit("unrelated main work", {"g.txt": "g\n"})
        self.git("checkout", "-q", "feature")
        self.commit("feature moves on", {"f.txt": "3\n"})
        entry = self.split(tip, squash)
        self.assertEqual(entry["ours"], ["f.txt"])
        self.assertEqual(entry["by_hand"], [])

    def test_a_path_with_a_space_is_one_path(self) -> None:
        self.commit("base", {"docs/my file.md": "0\n"})
        tip, squash = self.squash_merge({"docs/my file.md": "1\n"})
        self.git("checkout", "-q", "main")
        self.commit("unrelated main work", {"g.txt": "g\n"})
        entry = self.split(tip, squash)
        self.assertEqual(entry["ours"], ["docs/my file.md"])
        self.assertEqual(entry["by_hand"], [])

    def test_a_lookup_git_cannot_answer_is_read_by_hand(self) -> None:
        """Unknown is not absent: two failed lookups must not compare equal."""
        self.commit("base", {"f.txt": "0\n"})
        tip, squash = self.squash_merge({"f.txt": "1\n"})
        real = sd_lib.git_output

        def failing(args, root):
            if args[:1] in (["ls-tree"], ["rev-parse"]) and any(":" in a or a == "--" for a in args):
                return None
            return real(args, root)

        with patch.object(sd_ship_squash.sd_lib, "git_output", failing):
            entry = self.split(tip, squash)
        self.assertEqual(entry["ours"], [])
        self.assertEqual(entry["by_hand"], ["f.txt"])


if __name__ == "__main__":
    unittest.main()
