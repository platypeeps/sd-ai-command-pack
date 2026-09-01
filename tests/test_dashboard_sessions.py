"""What the Sessions tab finds without anything having written it down.

The registrations here are the shape git actually writes: a `gitdir` file
naming the worktree's `.git`, and a `HEAD` naming its branch.
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from dashboard import sessions


class Worktrees(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def repo(self, name: str) -> pathlib.Path:
        repo = self.root / name
        (repo / ".git").mkdir(parents=True)
        return repo

    def register(self, repo: pathlib.Path, name: str, target: pathlib.Path,
                 head: str = "ref: refs/heads/task/x\n") -> None:
        entry = repo / ".git" / "worktrees" / name
        entry.mkdir(parents=True)
        (entry / "gitdir").write_text(f"{target}\n", encoding="utf-8")
        (entry / "HEAD").write_text(head, encoding="utf-8")

    def test_a_worktree_whose_directory_is_gone_is_the_whole_point(self) -> None:
        """A parallel run that ends badly leaves the registration holding a
        branch. Nothing else in the fleet reports it and nothing fails."""
        repo = self.repo("one")
        self.register(repo, "gone", self.root / "nowhere" / ".git")
        got = sessions.collect_sessions(self.root)
        self.assertEqual(got["abandoned"], 1)
        self.assertFalse(got["worktrees"][0]["live"])
        self.assertEqual(got["worktrees"][0]["branch"], "task/x")

    def test_a_live_worktree_is_not_reported_as_abandoned(self) -> None:
        repo = self.repo("one")
        live = self.root / "elsewhere"
        (live / ".git").mkdir(parents=True)
        self.register(repo, "here", live / ".git")
        got = sessions.collect_sessions(self.root)
        self.assertEqual(got["abandoned"], 0)
        self.assertTrue(got["worktrees"][0]["live"])
        self.assertEqual(got["worktrees"][0]["path"], str(live))

    def test_abandoned_worktrees_sort_to_the_top(self) -> None:
        """They are the reason to open the tab; a live one is just a fact."""
        repo = self.repo("one")
        live = self.root / "elsewhere"
        (live / ".git").mkdir(parents=True)
        self.register(repo, "a-live", live / ".git")
        self.register(repo, "b-gone", self.root / "nowhere" / ".git")
        got = sessions.collect_sessions(self.root)
        self.assertEqual([w["name"] for w in got["worktrees"]], ["b-gone", "a-live"])

    def test_an_unreadable_registration_is_still_a_registration(self) -> None:
        """It is the one most in need of pruning, so dropping it hides the
        worst case behind the handling of it."""
        repo = self.repo("one")
        (repo / ".git" / "worktrees" / "broken").mkdir(parents=True)
        got = sessions.collect_sessions(self.root)
        self.assertEqual(got["abandoned"], 1)
        self.assertEqual(got["worktrees"][0]["branch"], "?")
        self.assertEqual(got["worktrees"][0]["path"], "")

    def test_a_detached_head_says_so_rather_than_inventing_a_branch(self) -> None:
        repo = self.repo("one")
        self.register(repo, "d", self.root / "nowhere" / ".git", head="abc123\n")
        self.assertEqual(
            sessions.collect_sessions(self.root)["worktrees"][0]["branch"], "detached")

    def test_a_repo_with_no_worktrees_contributes_nothing(self) -> None:
        self.repo("one")
        self.assertEqual(sessions.collect_sessions(self.root)["worktrees"], [])


class Running(unittest.TestCase):
    def ps(self, text: str):
        return lambda: text

    def test_only_sd_commands_count(self) -> None:
        """Matched on the basename of argv[0], so a full path and a bare
        invocation both hit and a command that merely mentions one does not."""
        got = sessions.running(self.ps(
            "1 01:00 /usr/local/bin/sd-review --json\n"
            "2 00:10 sd-check\n"
            "3 05:00 vim /Users/x/bin/sd-status\n"
            "4 00:01 grep sd-review\n"
            "5 00:02 /Users/x/bin/sd plugin list\n"
        ))
        self.assertEqual([row["pid"] for row in got], ["1", "2", "5"])

    def test_ps_failing_costs_the_other_half_nothing(self) -> None:
        """A view, not a supervisor: `ps` not answering must not empty the
        worktree table beside it."""
        def boom():
            raise OSError("no ps")
        self.assertEqual(sessions.running(boom), [])

    def test_a_line_ps_did_not_shape_as_expected_is_skipped(self) -> None:
        self.assertEqual(sessions.running(self.ps("garbage\n\n")), [])


if __name__ == "__main__":
    unittest.main()
