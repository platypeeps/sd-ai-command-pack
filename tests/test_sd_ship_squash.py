"""`sd_ship_squash.squashed_heads` against real git histories (sd:1409).

`tests/test_sd_ship.py` covers the warning end to end through `sd-ship
prepare`. These cases pin the path list itself: which paths `--ours` may
take is a claim about the merge that is about to happen, and no entry comparison
can prove it, so every case here asserts the path is left to a reader.
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

    def merge_main_resolving(self, text: str) -> None:
        """Merge main into `feature`, settling f.txt to `text`."""
        self.git("checkout", "-q", "feature")
        subprocess.run(["git", "merge", "-q", "--no-commit", "main"], cwd=self.root, capture_output=True)
        (self.root / "f.txt").write_text(text)
        self.git("add", "f.txt")
        self.git("commit", "-q", "--no-verify", "-m", "merge main")

    def assert_read_by_hand(self, entry: dict, paths: list[str]) -> None:
        self.assertEqual(entry["by_hand"], paths)
        self.assertNotIn("ours", entry)
        text = sd_ship_squash.warning(entry, "main")
        self.assertIn("No path is proven safe for `git checkout --ours`", text)
        self.assertNotIn("safe for:", text)

    def test_a_revert_on_main_after_a_shared_value_is_read_by_hand(self) -> None:
        """The squashed head set 1. Both sides then share 2 through a merge,
        main reverts to 1, and the feature moves to 3. Main's entry equals the
        squashed head's, yet `--ours` would discard main's revert."""
        self.commit("base", {"f.txt": "0\n"})
        tip, squash = self.squash_merge({"f.txt": "1\n"})
        self.git("checkout", "-q", "main")
        self.commit("main moves to 2", {"f.txt": "2\n"})
        self.merge_main_resolving("2\n")
        self.git("checkout", "-q", "main")
        self.commit("main reverts to 1", {"f.txt": "1\n"})
        self.git("checkout", "-q", "feature")
        self.commit("feature moves to 3", {"f.txt": "3\n"})
        self.assert_read_by_hand(self.split(tip, squash), ["f.txt"])

    def test_a_restore_on_main_after_returning_to_the_squash_parent_is_read_by_hand(self) -> None:
        """Main starts at 0, the squash makes it 1, main returns to 0 and is
        merged into the feature, then main restores 1 while the feature moves
        to 3. The merge base holds the squash parent's 0, yet `--ours` would
        discard main's restoration."""
        self.commit("base", {"f.txt": "0\n"})
        tip, squash = self.squash_merge({"f.txt": "1\n"})
        self.git("checkout", "-q", "main")
        self.commit("main returns to 0", {"f.txt": "0\n"})
        self.merge_main_resolving("0\n")
        self.git("checkout", "-q", "main")
        self.commit("main restores 1", {"f.txt": "1\n"})
        self.git("checkout", "-q", "feature")
        self.commit("feature moves to 3", {"f.txt": "3\n"})
        self.assert_read_by_hand(self.split(tip, squash), ["f.txt"])

    def test_names_keep_their_spaces(self) -> None:
        """NUL-delimited and unstripped: an inner space and a leading one."""
        self.commit("base", {"docs/my file.md": "0\n", " leading.txt": "0\n"})
        tip, squash = self.squash_merge({"docs/my file.md": "1\n", " leading.txt": "1\n"})
        entry = self.split(tip, squash)
        self.assertEqual(sorted(entry["by_hand"]), [" leading.txt", "docs/my file.md"])

    def test_a_squash_git_cannot_list_is_still_reported(self) -> None:
        self.commit("base", {"f.txt": "0\n"})
        tip, squash = self.squash_merge({"f.txt": "1\n"})

        def failing(root, args):
            raise ValueError("cannot read the complete review subject")

        with patch.object(sd_ship_squash.sd_review_material, "read_git_material", failing):
            entry = self.split(tip, squash)
        self.assertIsNone(entry["by_hand"])
        self.assertIn("git could not list them", sd_ship_squash.warning(entry, "main"))


if __name__ == "__main__":
    unittest.main()
