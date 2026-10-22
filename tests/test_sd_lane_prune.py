"""sd:5700. The lane deletes local branches proven landed, after a merge and through `lane prune`.

A branch goes only when no worktree holds it and merging it into origin's
default branch changes nothing, or each of its commits is in a merged lane
head by id or by patch: a squashed bundle lands its builders' commits under
other ids. Temporary repositories; nothing reaches GitHub.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import pathlib
import subprocess
from unittest import mock

from tests import test_sd_lane as lane_suite
from tests.clean_env import clean_environment

sd_lane = lane_suite.sd_lane
git = lane_suite.git
#: The reason a branch with work on it stays (sd:5700).
NOT_HELD = "not on origin/main, and no merged lane head holds its changes"


class Prune(lane_suite.Lane):
    topic = lane_suite.Landing.topic
    merge_lands = lane_suite.Landing.merge_lands
    drain = lane_suite.Landing.drain

    def setUp(self) -> None:
        super().setUp()
        git(self.repo, "push", "-q", "-u", "origin", "main")

    def commit(self, tree: pathlib.Path, name: str, text: str) -> str:
        (tree / name).write_text(text, encoding="utf-8")
        git(tree, "add", name)
        git(tree, "commit", "-q", "-m", name)
        return git(tree, "rev-parse", "HEAD")

    def builder(self, name: str, *files: str) -> list[str]:
        """A builder branch off main with one commit per file, its worktree removed as a lead does."""
        tree = self.worktree(name)
        made = [self.commit(tree, file, f"{file}\n") for file in files]
        git(self.repo, "worktree", "remove", str(tree))
        return made

    def bundle(self, *commits: str) -> str:
        """An integrator's bundle branch: the builders' commits picked with `-x`, so their ids differ."""
        tree = self.worktree("bundle")
        git(tree, "cherry-pick", "-x", *commits)
        head = git(tree, "rev-parse", "HEAD")
        git(self.repo, "worktree", "remove", str(tree))
        return head

    def squash_lands(self, head: str) -> None:
        """origin/main gets `head` squashed, then a later commit edits a landed file, so no branch merges as a no-op."""
        git(self.repo, "merge", "-q", "--squash", head)
        git(self.repo, "commit", "-q", "-m", "squashed bundle")
        (self.repo / "one").write_text("changed later\n", encoding="utf-8")
        git(self.repo, "commit", "-q", "-am", "later edit")
        git(self.repo, "push", "-q", "origin", "main")

    def branches(self) -> list[str]:
        return git(self.repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()

    def landed_bundle(self) -> tuple[list[str], str]:
        made = self.builder("b1", "one", "two")
        head = self.bundle(*made)
        self.squash_lands(head)
        return made, head

    def test_a_squashed_bundles_builder_branch_goes_by_content(self) -> None:
        made, head = self.landed_bundle()
        self.assertNotEqual(git(self.repo, "rev-parse", "bundle~1"), made[0])  # other ids, the same patches
        result = sd_lane.prune_landed(self.repo, [head])
        self.assertEqual([row["branch"] for row in result["deleted"]], ["b1", "bundle"])
        self.assertEqual(self.branches(), ["feature", "main"])

    def test_without_the_merged_head_the_builder_branch_is_not_proven(self) -> None:
        made, _ = self.landed_bundle()
        result = sd_lane.prune_landed(self.repo, [])
        kept = {row["branch"]: row["reason"] for row in result["kept"]}
        self.assertEqual(kept["b1"], f"2 commits {NOT_HELD}")
        self.assertIn("b1", self.branches())

    def lands_one_then_writes_another(self, landed: bytes, other: bytes) -> tuple[str, str]:
        """`b1` adds `one` as `landed` and lands in a squashed bundle; `other` adds it as `other`, off main."""
        tree = self.worktree("b1")
        (tree / "one").write_bytes(landed)
        git(tree, "add", "one")
        git(tree, "commit", "-q", "-m", "one")
        git(self.repo, "worktree", "remove", str(tree))
        head = self.bundle(git(self.repo, "rev-parse", "b1"))
        tree = self.worktree("other")
        (tree / "one").write_bytes(other)
        git(tree, "add", "one")
        git(tree, "commit", "-q", "-m", "one")
        git(self.repo, "worktree", "remove", str(tree))
        self.squash_lands(head)
        return head, git(self.repo, "rev-parse", "other")

    def test_a_commit_that_differs_only_in_whitespace_is_not_the_same_patch(self) -> None:
        """Codex review: `git cherry` ignores whitespace, so `"ab"` read as the landed `"a b"` and was deleted."""
        head, other = self.lands_one_then_writes_another(b'value = "a b"\n', b'value = "ab"\n')
        result = sd_lane.prune_landed(self.repo, [head])
        kept = {row["branch"]: row["reason"] for row in result["kept"]}
        self.assertEqual(kept.get("other"), f"1 commit {NOT_HELD}")
        self.assertEqual([row["branch"] for row in result["deleted"]], ["b1", "bundle"])

    def test_a_commit_with_other_binary_content_is_not_the_same_patch(self) -> None:
        head, other = self.lands_one_then_writes_another(b"\x00landed", b"\x00other")
        result = sd_lane.prune_landed(self.repo, [head])
        kept = {row["branch"]: row["reason"] for row in result["kept"]}
        self.assertEqual(kept.get("other"), f"1 commit {NOT_HELD}")

    def reverted_bundle(self, start: str, *picks: str) -> str:
        """A bundle off `start` that picks `picks`, reverts its last commit and adds an unrelated `two`; it lands."""
        tree = self.tmp / "bundle"
        git(self.repo, "worktree", "add", "-q", "-b", "bundle", str(tree), start)
        if picks:
            git(tree, "cherry-pick", "-x", *picks)
        git(tree, "revert", "--no-edit", "HEAD")
        self.commit(tree, "two", "two\n")
        head = git(tree, "rev-parse", "HEAD")
        git(self.repo, "worktree", "remove", str(tree))
        git(self.repo, "merge", "-q", "--squash", head)
        git(self.repo, "commit", "-q", "-m", "squashed bundle")
        git(self.repo, "push", "-q", "origin", "main")
        return head

    def test_a_commit_the_bundle_picked_then_reverted_is_not_landed(self) -> None:
        """Lane review round 1: the pick's patch is in the bundle's history, but the squash never landed it."""
        [one] = self.builder("b1", "one")
        head = self.reverted_bundle("main", one)
        self.assertFalse((self.repo / "one").exists())
        result = sd_lane.prune_landed(self.repo, [head])
        self.assertIn("b1", {row["branch"] for row in result["kept"]})
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/b1"), one)

    def test_a_commit_the_bundle_holds_by_ancestry_then_reverted_is_not_landed(self) -> None:
        """Lane review round 1: the builder commit is the bundle's ancestor, but the squash never landed it."""
        [one] = self.builder("b1", "one")
        head = self.reverted_bundle("b1")
        self.assertFalse((self.repo / "one").exists())
        result = sd_lane.prune_landed(self.repo, [head])
        self.assertIn("b1", {row["branch"] for row in result["kept"]})
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/b1"), one)

    def test_a_git_that_cannot_merge_from_a_base_proves_only_by_a_no_op_merge(self) -> None:
        """Before git 2.40 `merge-tree` has no `--merge-base`: a squashed builder branch stays, a merged one goes."""
        _, head = self.landed_bundle()
        git(self.repo, "branch", "merged-by-fast-forward", "main")
        with mock.patch.object(sd_lane, "merges_from_a_base", lambda main, commit: False):
            result = sd_lane.prune_landed(self.repo, [head])
        kept = {row["branch"]: row["reason"] for row in result["kept"]}
        self.assertEqual(kept["b1"], f"2 commits {NOT_HELD}; this git has no merge-tree --merge-base, so only a "
                                     "no-op merge proves it")
        self.assertEqual([row["branch"] for row in result["deleted"]], ["merged-by-fast-forward"])

    def test_a_branch_with_a_commit_past_the_merged_head_stays_with_its_reason(self) -> None:
        made = self.builder("b1", "one", "two")
        tree = self.worktree("b2")
        git(tree, "cherry-pick", *made)
        extra = self.commit(tree, "three", "three\n")
        git(self.repo, "worktree", "remove", str(tree))
        head = self.bundle(*made)
        self.squash_lands(head)
        result = sd_lane.prune_landed(self.repo, [head])
        kept = {row["branch"]: row for row in result["kept"]}
        self.assertEqual(kept["b2"]["reason"], f"3 commits {NOT_HELD}")
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/b2"), extra)

    def test_a_merge_with_an_edit_of_its_own_stays(self) -> None:
        """Its own commits are proven, but the merge carries a change no lane head holds."""
        made = self.builder("b1", "one")
        head = self.bundle(*made)
        git(self.repo, "merge", "-q", "--squash", head)
        git(self.repo, "commit", "-q", "-m", "squashed bundle")
        git(self.repo, "push", "-q", "origin", "main")
        tree = self.tmp / "b1-again"
        git(self.repo, "worktree", "add", "-q", str(tree), "b1")
        git(tree, "merge", "-q", "--no-commit", "--no-ff", "main")
        (tree / "evil").write_text("an edit in the merge\n", encoding="utf-8")
        git(tree, "add", "evil")
        git(tree, "commit", "-q", "-m", "merge main")
        git(self.repo, "worktree", "remove", str(tree))
        result = sd_lane.prune_landed(self.repo, [head])
        kept = {row["branch"]: row["reason"] for row in result["kept"]}
        self.assertEqual(kept["b1"], f"2 commits {NOT_HELD}")

    def test_a_branch_a_worktree_has_checked_out_stays(self) -> None:
        made, head = self.landed_bundle()
        tree = self.tmp / "b1-live"
        git(self.repo, "worktree", "add", "-q", str(tree), "b1")
        result = sd_lane.prune_landed(self.repo, [head])
        kept = {row["branch"]: row["reason"] for row in result["kept"]}
        self.assertEqual(kept["b1"], f"checked out in {tree}")
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/b1"), made[-1])

    def test_a_branch_being_rebased_in_a_worktree_stays(self) -> None:
        """`git worktree list` shows a rebase as a detached HEAD; `git branch -D` still refuses the branch."""
        made, head = self.landed_bundle()
        tree = self.tmp / "b1-rebasing"
        git(self.repo, "worktree", "add", "-q", str(tree), "b1")
        subprocess.run(["git", "-C", str(tree), "-c", "sequence.editor=true", "rebase", "-q", "-i", "--exec", "false",
                        "HEAD~1"], capture_output=True, check=False, env=clean_environment())
        self.assertIn("detached", git(self.repo, "worktree", "list", "--porcelain"))
        result = sd_lane.prune_landed(self.repo, [head])
        kept = {row["branch"]: row["reason"] for row in result["kept"]}
        self.assertTrue(kept["b1"].startswith("being rebased or bisected in "), kept["b1"])
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/b1"), made[-1])

    def test_a_branch_that_moved_after_the_check_stays(self) -> None:
        made, head = self.landed_bundle()
        held, reads = sd_lane.held_branches, []

        def move_b1_then_read(main: pathlib.Path) -> dict[str, str]:
            reads.append(main)
            if len(reads) == 2:  # the fresh read before the first delete: b1 gets new work meanwhile
                later = git(self.repo, "commit-tree", "-p", made[-1], "-m", "new work",
                            git(self.repo, "rev-parse", f"{made[-1]}^{{tree}}"))
                git(self.repo, "update-ref", "refs/heads/b1", later)
            return held(main)
        with mock.patch.object(sd_lane, "held_branches", move_b1_then_read):
            result = sd_lane.prune_landed(self.repo, [head])
        kept = {row["branch"]: row["reason"] for row in result["kept"]}
        self.assertTrue(kept["b1"].startswith("the delete failed"), kept["b1"])
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/b1~1"), made[-1])
        self.assertEqual([row["branch"] for row in result["deleted"]], ["bundle"])

    def test_a_branch_checked_out_after_the_check_stays(self) -> None:
        _, head = self.landed_bundle()
        held, reads = sd_lane.held_branches, []

        def check_out_b1_then_read(main: pathlib.Path) -> dict[str, str]:
            reads.append(main)
            return {**held(main), **({"b1": "checked out in elsewhere"} if len(reads) == 2 else {})}
        with mock.patch.object(sd_lane, "held_branches", check_out_b1_then_read):
            result = sd_lane.prune_landed(self.repo, [head])
        self.assertEqual({row["branch"]: row["reason"] for row in result["kept"]}["b1"], "checked out in elsewhere")
        self.assertIn("b1", self.branches())

    def test_a_failed_read_keeps_that_branch_as_unknown(self) -> None:
        _, head = self.landed_bundle()
        read = sd_lane.read_git

        def merge_tree_fails_for_b1(tree: pathlib.Path, *args: str, **options: object) -> object:
            if args[0] == "merge-tree" and args[-1] == git(self.repo, "rev-parse", "b1"):
                raise sd_lane.LaneError("no answer", code=sd_lane.PUBLISH_UNKNOWN)
            return read(tree, *args, **options)
        with mock.patch.object(sd_lane, "read_git", merge_tree_fails_for_b1):
            result = sd_lane.prune_landed(self.repo, [head])
        self.assertEqual({row["branch"]: row["reason"] for row in result["kept"]}["b1"], "unknown: no answer")
        self.assertEqual([row["branch"] for row in result["deleted"]], ["bundle"])

    def test_a_run_killed_between_deletes_is_finished_by_the_next(self) -> None:
        _, head = self.landed_bundle()
        delete, calls = sd_lane.delete_branch, []

        class Killed(BaseException):
            pass

        def killed_at_the_second(main: pathlib.Path, branch: str, tip: str) -> str | None:
            calls.append(branch)
            if len(calls) == 2:
                raise Killed
            return delete(main, branch, tip)
        with mock.patch.object(sd_lane, "delete_branch", killed_at_the_second), self.assertRaises(Killed):
            sd_lane.prune_landed(self.repo, [head])
        self.assertEqual(self.branches(), ["bundle", "feature", "main"])
        result = sd_lane.prune_landed(self.repo, [head])
        self.assertEqual([row["branch"] for row in result["deleted"]], ["bundle"])
        self.assertEqual(self.branches(), ["feature", "main"])

    def test_a_dry_run_deletes_nothing(self) -> None:
        _, head = self.landed_bundle()
        result = sd_lane.prune_landed(self.repo, [head], dry_run=True)
        self.assertEqual(([row["branch"] for row in result["landed"]], result["deleted"]), (["b1", "bundle"], []))
        self.assertEqual(self.branches(), ["b1", "bundle", "feature", "main"])

    def test_the_default_branch_is_never_touched(self) -> None:
        git(self.repo, "switch", "-q", "--detach")  # main is now held by no worktree, and at origin/main
        git(self.repo, "branch", "merged-by-fast-forward", "main")
        result = sd_lane.prune_landed(self.repo, [])
        self.assertEqual([row["branch"] for row in result["deleted"]], ["merged-by-fast-forward"])
        self.assertNotIn("main", [row["branch"] for row in result["kept"]])
        self.assertEqual(self.branches(), ["feature", "main"])

    def test_an_origin_that_does_not_answer_deletes_nothing(self) -> None:
        self.landed_bundle()
        git(self.repo, "config", "url.%s.insteadOf" % (self.tmp / "gone.git"), "https://github.com/example/pack.git")
        git(self.repo, "config", "--unset", f"url.{self.origin}.insteadOf")
        with self.assertRaises(sd_lane.LaneError) as caught:
            sd_lane.prune_landed(self.repo, [])
        self.assertEqual(caught.exception.code, sd_lane.PUBLISH_UNKNOWN)
        self.assertEqual(self.branches(), ["b1", "bundle", "feature", "main"])

    def test_the_landing_deletes_a_landed_branch_and_keeps_the_checked_out_one(self) -> None:
        tree, head = self.topic()
        git(self.repo, "branch", "leftover", head)
        self.merge_lands(tree, 1, head)
        self.drain()
        self.assertEqual(self.branches(), ["feature", "main", "topic"])
        entry = self.entries()[0]
        self.assertIn(f"; deleted the landed local branches leftover at {head}", entry["cleanup"])
        [(_, body, _)] = self.notes
        self.assertIn(f"deleted the landed local branches leftover at {head}", body)

    def test_lane_prune_reads_every_merged_head_of_the_repository(self) -> None:
        made, head = self.landed_bundle()
        sd_lane.add_entry(self.store(), {"id": sd_lane.entry_id(), "item": 7, "status": "merged",
                                         "expected_head": made[-1], "head": head})
        unlanded = self.commit(self.feature, "four", "four\n")
        git(self.repo, "branch", "-f", "unlanded", unlanded)
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            self.assertEqual(sd_lane.lane_prune(self.repo, self.environ, dry_run=False, as_json=True), 0)
        result = json.loads(said.getvalue())
        self.assertEqual([row["branch"] for row in result["deleted"]], ["b1", "bundle"])
        kept = {row["branch"]: row["reason"] for row in result["kept"]}
        self.assertEqual(kept["unlanded"], f"1 commit {NOT_HELD}")
        self.assertEqual(kept["feature"], f"checked out in {self.feature}")
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            sd_lane.lane_prune(self.repo, self.environ, dry_run=True, as_json=False)
        self.assertEqual(said.getvalue().splitlines(),
                         [f"kept feature: checked out in {self.feature}",
                          f"kept unlanded: 1 commit {NOT_HELD}"])

    def test_the_verb_parses(self) -> None:
        parser = argparse.ArgumentParser()
        sd_lane.add_lane_verbs(parser.add_subparsers(dest="command"))
        args = parser.parse_args(["lane", "prune", "--dry-run", "--json"])
        self.assertEqual((args.lane_command, args.dry_run, args.json), ("prune", True, True))


if __name__ == "__main__":
    import unittest
    unittest.main()
