"""`sd-ship lane` (sd:2524): a serial ship queue per repository that outlives its session.

The acceptance test is the first: an entry one process enqueued is there for
the next process to read. The runner tests replace `sd-ship` with a recorder,
so nothing reaches GitHub or a review.
"""

from __future__ import annotations

import fcntl
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from typing import Any, Callable
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lane  # noqa: E402


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


class Lane(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name).resolve()
        self.repo = self.tmp / "pack"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@example.test")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "a")
        self.root = self.tmp / "lanes"
        self.environ = {sd_lane.ROOT_VARIABLE: str(self.root), "HOME": str(self.tmp)}
        self.body = self.tmp / "body.md"
        self.body.write_text("Item: sd:1\n", encoding="utf-8")
        self.calls: list[list[str]] = []
        self.answers: dict[tuple[int, str], dict] = {}
        # A landing notes its item (sd:2568); no test writes to a real workflow database.
        self.notes: list[tuple[int, str, pathlib.Path]] = []
        patcher = mock.patch.object(sd_lane, "default_note", self.note)
        patcher.start()
        self.addCleanup(patcher.stop)

    def note(self, item: int, body: str, main: pathlib.Path) -> str:
        self.notes.append((item, body, main))
        return "written"

    def worktree(self, name: str) -> pathlib.Path:
        path = self.tmp / name
        git(self.repo, "worktree", "add", "-q", "-b", name, str(path))
        return path

    def ship(self, argv: list[str], log: pathlib.Path) -> dict:
        """The recorder: `(item, verb)` answers, ready and merged by default."""
        self.calls.append(argv)
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("whole output " * 1000, encoding="utf-8")
        verb, item = argv[2], int(argv[argv.index("--item") + 1])
        default = ({"ok": True, "phase": "ready_to_send", "head": f"head-{item}"} if verb == "prepare"
                   else {"ok": True, "phase": "merged", "merge_commit": f"merged-{item}"})
        return self.answers.get((item, verb), default)

    def entries(self) -> list[dict]:
        return sd_lane.read_queue(sd_lane.queue_path(self.repo, self.environ))


class QueueOutlivesTheProcess(Lane):
    def sd_ship(self, cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, **self.environ}
        return subprocess.run([sys.executable, str(REPO_ROOT / "bin/sd-ship"), "lane", *args], cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=120)

    def test_an_entry_one_process_enqueued_is_read_by_the_next(self) -> None:
        tree = self.worktree("topic")
        head = git(tree, "rev-parse", "HEAD")
        done = self.sd_ship(tree, "enqueue", "--item", "7", "--title", "Topic", "--body-file", str(self.body), "--deliver")
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        listed = self.sd_ship(self.repo, "list")
        self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
        answer = json.loads(listed.stdout)
        self.assertEqual(answer["queue"], str(self.root / "pack/lane/queue/queue.json"))
        [entry] = answer["entries"]
        self.assertEqual({key: entry[key] for key in ("worktree", "item", "expected_head", "title", "body_file", "status")},
                         {"worktree": str(tree), "item": 7, "expected_head": head, "title": "Topic",
                          "body_file": str(self.body), "status": "pending"})

    def test_an_entry_without_a_delivery_claim_is_refused_with_exit_3(self) -> None:
        done = self.sd_ship(self.repo, "enqueue", "--item", "7", "--title", "Topic", "--body-file", str(self.body))
        self.assertEqual(done.returncode, 3, done.stderr + done.stdout)
        self.assertIn("--associate-only", json.loads(done.stdout)["error"])
        self.assertEqual(self.entries(), [])


class Enqueue(Lane):
    def test_the_lane_root_comes_from_the_setting_when_no_variable_names_it(self) -> None:
        config = self.tmp / "config"
        (config / "sd-ai-command-pack").mkdir(parents=True)
        (config / "sd-ai-command-pack/config.json").write_text(
            json.dumps({"config": {"sd": {"lane_root": str(self.tmp / "storage")}}}), encoding="utf-8")
        environ = {"XDG_CONFIG_HOME": str(config), "HOME": str(self.tmp)}
        self.assertEqual(sd_lane.queue_path(self.repo, environ), self.tmp / "storage/pack/lane/queue/queue.json")

    def test_an_item_already_queued_is_refused(self) -> None:
        sd_lane.enqueue_entry(self.repo, 3, "t", self.body, self.environ, claim="deliver")
        with self.assertRaisesRegex(sd_lane.LaneError, "already queued"):
            sd_lane.enqueue_entry(self.repo, 3, "t", self.body, self.environ, claim="deliver")

    def test_a_cancelled_entry_is_not_run(self) -> None:
        sd_lane.enqueue_entry(self.repo, 3, "t", self.body, self.environ, claim="deliver")
        sd_lane.cancel(self.repo, 3, self.environ)
        self.assertEqual(sd_lane.run_lane(self.repo, self.environ, self.ship), {"ran": []})
        self.assertEqual(self.calls, [])


class Runner(Lane):
    def test_entries_run_in_order_and_a_failure_does_not_stop_the_next(self) -> None:
        first, second = self.worktree("first"), self.worktree("second")
        sd_lane.enqueue_entry(first, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.enqueue_entry(second, 2, "two", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(1, "prepare")] = {"ok": False, "phase": "review_blocked", "error": "a blocking finding"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([(int(c[c.index("--item") + 1]), c[2]) for c in self.calls],
                         [(1, "prepare"), (2, "prepare"), (2, "merge")])
        one, two = self.entries()
        self.assertEqual((one["status"], one["step"], one["reason"]), ("failed", "prepare", "a blocking finding"))
        self.assertEqual((two["status"], two["merge_commit"]), ("merged", "merged-2"))

    def test_an_associate_only_entry_prepares_with_associate_only(self) -> None:
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="associate-only")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertIn("--associate-only", self.calls[0])
        self.assertNotIn("--deliver", self.calls[0])

    def test_an_acceptance_file_is_forwarded_to_prepare(self) -> None:
        acceptance = self.tmp / "acceptance.json"
        acceptance.write_text("{}", encoding="utf-8")
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver", acceptance_file=acceptance)
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        prepare = self.calls[0]
        self.assertEqual((prepare[prepare.index("--acceptance-file") + 1], "--deliver" in prepare), (str(acceptance), True))

    def test_prepare_catches_up_with_the_base_inside_the_runner(self) -> None:
        """The catch-up merge runs under the lane lock, never before it."""
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertIn("--catch-up", self.calls[0])

    def test_the_merge_names_the_prepared_head(self) -> None:
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        merge = self.calls[1]
        self.assertEqual((merge[merge.index("--expected-head") + 1], "--manual" in merge), ("head-1", True))

    def test_without_manual_authority_the_runner_stops_at_a_prepared_head(self) -> None:
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([c[2] for c in self.calls], ["prepare"])
        self.assertEqual(self.entries()[0]["status"], "prepared")

    def test_a_worktree_that_moved_is_skipped_without_a_prepare(self) -> None:
        tree = self.worktree("topic")
        sd_lane.enqueue_entry(tree, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        git(tree, "commit", "-q", "--allow-empty", "-m", "moved")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual((self.calls, self.entries()[0]["status"]), ([], "skipped"))

    def test_the_whole_prepare_output_is_kept(self) -> None:
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        log = pathlib.Path(self.entries()[0]["prepare_log"])
        self.assertEqual(log.read_text(encoding="utf-8"), "whole output " * 1000)
        self.assertEqual(log.parent, self.root / "pack/lane/logs")

    def test_a_second_runner_exits_at_once_instead_of_waiting(self) -> None:
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver")
        lock = sd_lane.queue_path(self.repo, self.environ).parent / "runner.lock"
        with open(lock, "a", encoding="utf-8") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            started = time.monotonic()
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertLess(time.monotonic() - started, 5)
        self.assertIn("another runner holds", answer["busy"])
        self.assertEqual((self.calls, self.entries()[0]["status"]), ([], "pending"))

    def test_an_entry_queued_while_the_runner_works_is_run_too(self) -> None:
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver")
        second = self.worktree("second")
        ship = self.ship

        def enqueue_during(argv: list[str], log: pathlib.Path) -> dict:
            if not any(entry["item"] == 2 for entry in self.entries()):
                sd_lane.enqueue_entry(second, 2, "two", self.body, self.environ, claim="deliver")
            return ship(argv, log)
        sd_lane.run_lane(self.repo, self.environ, enqueue_during)
        self.assertEqual([entry["status"] for entry in self.entries()], ["prepared", "prepared"])


class Speculation(Lane):
    """sd:2586: while one entry ships, the next one's gate runs on the predicted landing.

    A bare `origin` holds main; two worktrees each add a file and a CHANGELOG
    entry, and main moves after they fork. The recorder lands entry 1 as
    GitHub's squash would: its catch-up tree as a new commit on main.
    """

    def setUp(self) -> None:
        super().setUp()
        self.origin = self.tmp / "origin.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.commit_files(self.repo, {".github/sd-gate-reuse.json": json.dumps(
            {"schema_version": 1, "key": "tree", "reason": "the check reads no history"}),
            "CHANGELOG.md": "# Changelog\n\n## Unreleased\n\n- base\n"}, "declare")
        git(self.repo, "remote", "add", "origin", str(self.origin))
        git(self.repo, "push", "-q", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        self.first = self.branch("first", {"one.txt": "1\n"}, "- one\n")
        self.second = self.branch("second", {"two.txt": "2\n"}, "- two\n")
        self.commit_files(self.repo, {"base.txt": "b\n"}, "main moved")
        git(self.repo, "push", "-q", "origin", "main")
        self.gates: list[tuple[pathlib.Path, str, str]] = []
        self.events = {name: threading.Event() for name in ("landed", "gated")}
        self.seen: dict[str, bool] = {}

    def commit_files(self, tree: pathlib.Path, files: dict[str, str], message: str) -> None:
        for name, text in files.items():
            (tree / name).parent.mkdir(parents=True, exist_ok=True)
            (tree / name).write_text(text, encoding="utf-8")
        git(tree, "add", "-A")
        git(tree, "commit", "-q", "-m", message)

    def branch(self, name: str, files: dict[str, str], entry: str) -> pathlib.Path:
        path = self.tmp / name
        git(self.repo, "worktree", "add", "-q", "-b", name, str(path), "origin/main")
        changelog = (path / "CHANGELOG.md").read_text(encoding="utf-8").replace("## Unreleased\n\n", f"## Unreleased\n\n{entry}")
        self.commit_files(path, {**files, "CHANGELOG.md": changelog}, name)
        return path

    def caught_up(self, head: str, ref: str) -> str:
        """The tree `sd-ship prepare --catch-up` makes at `head` against `ref`, built apart from the lane's code."""
        import sd_changelog_merge

        scratch = self.tmp / f"scratch-{len(list(self.tmp.iterdir()))}"
        git(self.repo, "worktree", "add", "-q", "--detach", str(scratch), head)
        try:
            merged = subprocess.run(["git", "-C", str(scratch), "merge", "--no-ff", "--no-edit", "-m", "catch up", ref],
                                    capture_output=True, text=True, check=False)
            if merged.returncode:
                self.assertTrue(sd_changelog_merge.resolve_keep_both(scratch))
                git(scratch, "commit", "-q", "--no-verify", "-m", "catch up")
            return git(scratch, "rev-parse", "HEAD^{tree}")
        finally:
            git(self.repo, "worktree", "remove", "--force", str(scratch))

    def ship(self, argv: list[str], log: pathlib.Path) -> dict:
        verb, item = argv[2], int(argv[argv.index("--item") + 1])
        if (item, verb) == (1, "merge"):
            git(self.repo, "fetch", "-q", "origin")
            tree = self.caught_up(git(self.first, "rev-parse", "HEAD"), "origin/main")
            landed = git(self.repo, "commit-tree", tree, "-p", "origin/main", "-m", "one (#1)")
            git(self.repo, "push", "-q", "origin", f"{landed}:refs/heads/main")
            self.events["landed"].set()
        if (item, verb) == (2, "prepare"):
            self.seen["gate done before prepare 2"] = self.events["gated"].is_set()
        return super().ship(argv, log)

    def gate(self, root: pathlib.Path, head: str, base: str) -> dict:
        """Still running when entry 1 lands, and ends half a second after."""
        self.gates.append((root, head, base))
        self.seen["gate ran while entry 1 shipped"] = self.events["landed"].wait(10)
        time.sleep(0.5)
        self.events["gated"].set()
        return {"status": "success", "summary": "sd-check pass (check pass)", "receipt_revision": 1}

    def queue_both(self, *, manual: bool = True) -> None:
        sd_lane.enqueue_entry(self.first, 1, "one", self.body, self.environ, manual=manual, claim="deliver")
        sd_lane.enqueue_entry(self.second, 2, "two", self.body, self.environ, manual=True, claim="deliver")

    def test_the_next_entry_is_gated_on_the_predicted_landing_while_this_one_ships(self) -> None:
        self.queue_both()
        fork = git(self.repo, "rev-parse", "origin/main")
        sd_lane.run_lane(self.repo, self.environ, self.ship, self.gate)
        [(root, head, base)] = self.gates
        self.assertEqual(root, self.second)
        git(self.repo, "fetch", "-q", "origin")
        landed = git(self.repo, "rev-parse", "origin/main")
        # The predicted landing is another commit than the real one, on the same base, with the same tree.
        self.assertNotEqual(base, landed)
        self.assertEqual(git(self.repo, "rev-parse", f"{base}^"), fork)
        self.assertEqual(git(self.repo, "rev-parse", f"{base}^{{tree}}"), git(self.repo, "rev-parse", "origin/main^{tree}"))
        # The gated tree is the one entry 2's catch-up makes after the real landing, CHANGELOG resolved.
        self.assertEqual(git(self.repo, "rev-parse", f"{head}^{{tree}}"),
                         self.caught_up(git(self.second, "rev-parse", "HEAD"), "origin/main"))
        self.assertTrue(self.seen["gate ran while entry 1 shipped"])

    def test_the_next_prepare_starts_after_the_speculative_gate_ends(self) -> None:
        self.queue_both()
        sd_lane.run_lane(self.repo, self.environ, self.ship, self.gate)
        self.assertTrue(self.seen["gate done before prepare 2"])

    def test_the_next_entry_records_the_speculation(self) -> None:
        self.queue_both()
        sd_lane.run_lane(self.repo, self.environ, self.ship, self.gate)
        [(_, head, base)] = self.gates
        speculation = self.entries()[1]["speculation"]
        self.assertEqual({key: speculation[key] for key in ("after", "head", "base", "status", "receipt")},
                         {"after": 1, "head": head, "base": base, "status": "success", "receipt": "recorded"})
        self.assertIn('"status": "success"', pathlib.Path(speculation["log"]).read_text(encoding="utf-8"))

    def test_an_entry_queued_without_manual_is_not_predicted(self) -> None:
        """It stops prepared and never lands, so the next entry's gate would name a tree no prepare makes."""
        self.queue_both(manual=False)
        sd_lane.run_lane(self.repo, self.environ, super().ship, self.gate)
        self.assertEqual(self.gates, [])
        self.assertNotIn("speculation", self.entries()[1])

    def test_without_the_tree_key_nothing_is_gated(self) -> None:
        for tree in (self.first, self.second):
            git(tree, "rm", "-q", ".github/sd-gate-reuse.json")
            git(tree, "commit", "-q", "-m", "no tree key")
        self.queue_both()
        sd_lane.run_lane(self.repo, self.environ, super().ship, self.gate)
        self.assertEqual(self.gates, [])
        self.assertEqual(self.entries()[1]["speculation"]["status"], "skipped")
        self.assertIn("no tree key", self.entries()[1]["speculation"]["reason"])

    def test_a_conflict_with_the_predicted_landing_gates_nothing_and_both_entries_still_run(self) -> None:
        self.commit_files(self.second, {"one.txt": "not 1\n"}, "conflicts with first")
        worktrees = git(self.repo, "worktree", "list", "--porcelain").count("worktree ")
        self.queue_both()
        sd_lane.run_lane(self.repo, self.environ, super().ship, self.gate)
        self.assertEqual(self.gates, [])
        self.assertEqual([entry["status"] for entry in self.entries()], ["merged", "merged"])
        self.assertIn("conflicts with sd:1", self.entries()[1]["speculation"]["reason"])
        self.assertEqual(git(self.repo, "worktree", "list", "--porcelain").count("worktree "), worktrees)

    def test_a_gate_that_raises_does_not_stop_the_lane(self) -> None:
        def broken(root: pathlib.Path, head: str, base: str) -> dict:
            raise RuntimeError("the gate broke")
        self.queue_both()
        sd_lane.run_lane(self.repo, self.environ, super().ship, broken)
        self.assertEqual([entry["status"] for entry in self.entries()], ["merged", "merged"])
        self.assertEqual(self.entries()[1]["speculation"]["status"], "error")


class Landing(Lane):
    """sd:2568: after a merge, clean up, note the item and fast-forward the main checkout."""

    def setUp(self) -> None:
        super().setUp()
        self.origin = self.tmp / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        git(self.repo, "remote", "add", "origin", str(self.origin))
        git(self.repo, "push", "-q", "-u", "origin", "main")

    def topic(self, name: str = "topic") -> tuple[pathlib.Path, str]:
        """A pushed worktree whose commit tracks a file, a nested file and a symlink, as a real one does."""
        tree = self.worktree(name)
        (tree / "pkg/mod").mkdir(parents=True)
        (tree / "README.md").write_text("readme\n", encoding="utf-8")
        (tree / "pkg/mod/a.py").write_text("A = 1\n", encoding="utf-8")
        (tree / "link").symlink_to("README.md")
        git(tree, "add", "-A")
        git(tree, "commit", "-q", "-m", name)
        git(tree, "push", "-q", "origin", name)
        return tree, git(tree, "rev-parse", "HEAD")

    def merge_lands(self, tree: pathlib.Path, item: int, head: str, **options) -> None:
        sd_lane.enqueue_entry(tree, item, "t", self.body, self.environ, manual=True, claim="deliver", **options)
        self.answers[(item, "prepare")] = {"ok": True, "phase": "ready_to_send", "head": head}
        self.answers[(item, "merge")] = {"ok": True, "phase": "merged", "merge_commit": "c0ffee" * 6 + "c0ff"}

    def drain(self, ship=None) -> dict:
        return sd_lane.run_lane(self.repo, self.environ, ship or self.ship)

    def remote_branches(self) -> list[str]:
        return git(self.origin, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()

    def ignore(self, *patterns: str) -> None:
        """Ignore `patterns` in every worktree of the fixture repository, as a `.gitignore` would."""
        exclude = pathlib.Path(git(self.repo, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "info/exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text("".join(f"{pattern}\n" for pattern in patterns), encoding="utf-8")

    def advance_origin_main(self) -> str:
        upstream = self.tmp / "upstream"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(upstream)], check=True)
        git(upstream, "-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "landed")
        git(upstream, "push", "-q", "origin", "main")
        return git(upstream, "rev-parse", "HEAD")

    def test_a_clean_merged_worktree_is_removed_and_the_item_noted(self) -> None:
        tree, head = self.topic()
        self.merge_lands(tree, 1, head)
        self.drain()
        self.assertFalse(tree.exists())
        self.assertEqual(git(self.repo, "branch", "--list", "topic"), "")
        self.assertEqual(self.remote_branches(), ["main"])
        [(item, body, main)] = self.notes
        self.assertEqual((item, main), (1, self.repo))
        self.assertEqual(body, f"Landed: merged at c0ffeec0ffee (head {head[:12]}). Cleanup: removed worktree {tree}, "
                               f"removed branch topic, removed origin/topic. Recover: git branch topic {head}.")
        self.assertEqual(self.entries()[0]["status"], "merged")

    def test_the_runner_notes_through_default_note_when_given_none(self) -> None:
        """The fixture replaces `default_note`; `run_lane` must read it at the call, or a suite writes real notes."""
        tree, head = self.topic()
        self.merge_lands(tree, 1, head)
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([item for item, _, _ in self.notes], [1])
        self.assertEqual(self.entries()[0]["note"], "written")

    def test_a_dirty_worktree_is_kept_and_the_note_says_why(self) -> None:
        tree, head = self.topic()
        (tree / "work.txt").write_text("uncommitted\n", encoding="utf-8")
        self.merge_lands(tree, 1, head)
        self.drain()
        self.assertTrue(tree.exists())
        self.assertEqual(self.remote_branches(), ["main", "topic"])
        self.assertIn("Cleanup skipped: the worktree has uncommitted changes", self.notes[0][1])
        self.assertIn(f"Recover: git branch topic {head}", self.notes[0][1])

    def test_an_untracked_file_hidden_by_the_status_setting_still_keeps_the_worktree(self) -> None:
        tree, head = self.topic()
        git(self.repo, "config", "status.showUntrackedFiles", "no")
        (tree / "notes.txt").write_text("scratch\n", encoding="utf-8")
        self.merge_lands(tree, 1, head)
        self.drain()
        self.assertTrue((tree / "notes.txt").exists())
        self.assertIn("uncommitted", self.entries()[0]["cleanup"])

    def test_a_tip_past_the_merged_head_is_kept(self) -> None:
        tree, head = self.topic()
        self.merge_lands(tree, 1, head)
        ship = self.ship

        def commit_after_prepare(argv: list[str], log: pathlib.Path) -> dict:
            if argv[2] == "merge":
                git(tree, "commit", "-q", "--allow-empty", "-m", "later")
            return ship(argv, log)
        self.drain(commit_after_prepare)
        self.assertTrue(tree.exists())
        self.assertEqual(self.remote_branches(), ["main", "topic"])
        self.assertIn("is not the merged head", self.entries()[0]["cleanup"])

    def test_a_commit_after_the_tip_check_keeps_the_branch_at_the_newer_tip(self) -> None:
        tree, head = self.topic()
        self.merge_lands(tree, 1, head)
        checked = sd_lane.lane_git

        def builder_commits_during_ls_remote(root: pathlib.Path, *args: str) -> str | None:
            if args[:1] == ("ls-remote",):
                git(tree, "commit", "-q", "--allow-empty", "-m", "newer")
            return checked(root, *args)
        with mock.patch.object(sd_lane, "lane_git", builder_commits_during_ls_remote):
            self.drain()
        newer = git(self.repo, "for-each-ref", "--format=%(objectname)", "refs/heads/topic")
        self.assertNotIn(newer, ("", head))
        self.assertIn(f"Cleanup stopped: branch topic moved to {newer}", self.entries()[0]["cleanup"])
        self.assertEqual(self.remote_branches(), ["main", "topic"])

    def test_any_ignored_entry_keeps_the_worktree_and_its_branch(self) -> None:
        """Operator ruling (sd:2584 option a): removal deletes ignored files, build output included."""
        for files in ({".env": "TOKEN=change-me\n"}, {"pkg/__pycache__/m.cpython-314.pyc": ""},
                      {"build/credentials.env": "x\n"}):
            with self.subTest(files=sorted(files)):
                self.setUp()
                tree, head = self.topic()
                self.ignore(".env", "__pycache__/", "build/")
                for name, text in files.items():
                    (tree / name).parent.mkdir(parents=True, exist_ok=True)
                    (tree / name).write_text(text, encoding="utf-8")
                self.merge_lands(tree, 1, head)
                self.drain()
                self.assertTrue(all((tree / name).exists() for name in files))
                self.assertEqual(git(self.repo, "rev-parse", "refs/heads/topic"), head)
                cleanup = self.entries()[0]["cleanup"]
                self.assertIn("worktree kept: holds ignored entries: ", cleanup)
                self.assertIn(next(iter(files)).split("/")[0], cleanup)
                self.assertEqual(self.remote_branches(), ["main"])

    def after_git(self, matches: Callable[[tuple[str, ...]], bool], act: Callable[[], None]) -> Any:
        """Run `act` once, as a builder would, right after the first `lane_git` call whose arguments match returns."""
        checked, done = sd_lane.lane_git, []

        def acting(root: pathlib.Path, *args: str) -> str | None:
            answer = checked(root, *args)
            if not done and matches(args):
                done.append(act())
            return answer
        return mock.patch.object(sd_lane, "lane_git", acting)

    def test_an_ignored_file_written_after_the_last_status_check_survives(self) -> None:
        """The sd:2568 review's race: no lock excludes the builder, so a file can appear after the check."""
        tree, head = self.topic()
        self.ignore("build/")
        late = tree / "build/late.o"

        def builder_writes() -> None:
            late.parent.mkdir()
            late.write_text("object\n", encoding="utf-8")
        self.merge_lands(tree, 1, head)
        with self.after_git(lambda args: "--ignored=matching" in args, builder_writes):
            self.drain()
        self.assertEqual(late.read_text(encoding="utf-8"), "object\n")
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/topic"), head)
        self.assertEqual(self.remote_branches(), ["main", "topic"])
        cleanup = self.entries()[0]["cleanup"]
        self.assertIn("Cleanup stopped: build/late.o appeared or changed during removal", cleanup)
        git(tree, "checkout", "--", ".")  # the note's restore: the tracked files come back from the index
        self.assertEqual((tree / "pkg/mod/a.py").read_text(encoding="utf-8"), "A = 1\n")

    def test_a_tracked_file_rewritten_after_the_last_status_check_is_put_back(self) -> None:
        """Same size, same inode: only the modification time tells the rewrite apart, and it must."""
        tree, head = self.topic()

        def builder_rewrites() -> None:
            with open(tree / "README.md", "r+", encoding="utf-8") as handle:
                handle.write("REA")
        self.merge_lands(tree, 1, head)
        with self.after_git(lambda args: "--ignored=matching" in args, builder_rewrites):
            self.drain()
        self.assertEqual((tree / "README.md").read_text(encoding="utf-8"), "REAdme\n")
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/topic"), head)
        self.assertIn("Cleanup stopped: README.md appeared or changed during removal", self.entries()[0]["cleanup"])

    def test_a_tracked_file_rewritten_after_the_uncommitted_check_keeps_the_worktree(self) -> None:
        """The check that vouches for each file runs after its snapshot, so it sees every kind of change."""
        tree, head = self.topic()

        def builder_rewrites() -> None:
            (tree / "README.md").write_text("rewritten\n", encoding="utf-8")
        self.merge_lands(tree, 1, head)
        with self.after_git(lambda args: args == ("status", "--porcelain", "--untracked-files=all"), builder_rewrites):
            self.drain()
        self.assertEqual((tree / "README.md").read_text(encoding="utf-8"), "rewritten\n")
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/topic"), head)
        self.assertIn("worktree kept: changed after the status check: README.md", self.entries()[0]["cleanup"])

    def test_a_locked_worktree_is_kept(self) -> None:
        tree, head = self.topic()
        git(self.repo, "worktree", "lock", str(tree))
        self.merge_lands(tree, 1, head)
        self.drain()
        self.assertTrue((tree / "README.md").exists())
        self.assertIn("worktree kept: git worktree lock holds it", self.entries()[0]["cleanup"])

    def test_the_kept_note_names_three_ignored_entries_then_elides(self) -> None:
        tree, head = self.topic()
        self.ignore("*.local")
        for name in ("a", "b", "c", "my d"):
            (tree / f"{name}.local").write_text("x\n", encoding="utf-8")
        self.merge_lands(tree, 1, head)
        self.drain()
        self.assertIn("holds ignored entries: a.local, b.local, c.local…", self.entries()[0]["cleanup"])

    def test_a_worktree_queued_to_keep_keeps_it_and_its_branch_and_drops_the_remote(self) -> None:
        tree, head = self.topic()
        self.merge_lands(tree, 1, head, keep_worktree=True)
        self.drain()
        self.assertTrue(tree.exists())
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/topic"), head)
        self.assertEqual(self.remote_branches(), ["main"])
        self.assertEqual(self.entries()[0]["cleanup"],
                         "Cleanup: worktree and branch kept: queued with --keep-worktree, removed origin/topic")

    def test_a_worktree_that_holds_the_running_tools_is_kept(self) -> None:
        tree, head = self.topic()
        self.merge_lands(tree, 1, head)
        with mock.patch.object(sd_lane, "BIN", tree / "bin"):
            self.drain()
        self.assertTrue(tree.exists())
        self.assertIn("worktree kept: holds the running lane tools", self.entries()[0]["cleanup"])

    def test_a_remote_branch_that_moved_is_not_deleted(self) -> None:
        tree, head = self.topic()
        other = self.tmp / "other"
        subprocess.run(["git", "clone", "-q", "-b", "topic", str(self.origin), str(other)], check=True)
        git(other, "-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
        git(other, "push", "-q", "origin", "topic")
        self.merge_lands(tree, 1, head)
        self.drain()
        self.assertFalse(tree.exists())
        self.assertEqual(self.remote_branches(), ["main", "topic"])
        self.assertIn("origin/topic kept: it is at", self.entries()[0]["cleanup"])

    def test_the_main_checkout_is_never_removed(self) -> None:
        head = git(self.repo, "rev-parse", "HEAD")
        self.merge_lands(self.repo, 1, head)
        self.drain()
        self.assertTrue((self.repo / ".git").exists())
        self.assertIn("is the main checkout", self.entries()[0]["cleanup"])

    def test_the_main_checkout_fast_forwards_to_the_merged_base(self) -> None:
        tree, head = self.topic()
        landed = self.advance_origin_main()
        self.merge_lands(tree, 1, head)
        self.drain()
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), landed)
        self.assertIn("fast-forwarded", self.entries()[0]["fast_forward"])

    def test_a_checkout_off_the_default_branch_is_not_moved(self) -> None:
        tree, head = self.topic()
        git(self.repo, "switch", "-q", "-c", "elsewhere")
        before = git(self.repo, "rev-parse", "HEAD")
        self.advance_origin_main()
        self.merge_lands(tree, 1, head)
        self.drain()
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        self.assertIn("on elsewhere, not the default branch", self.entries()[0]["fast_forward"])

    def test_origin_head_names_the_default_branch_over_the_usual_names(self) -> None:
        tree, head = self.topic()
        git(self.repo, "remote", "set-head", "origin", "main")
        git(self.repo, "switch", "-q", "-c", "master")
        before = git(self.repo, "rev-parse", "HEAD")
        self.advance_origin_main()
        self.merge_lands(tree, 1, head)
        self.drain()
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        self.assertIn("on master, not the default branch", self.entries()[0]["fast_forward"])

    def test_the_tools_checkout_tries_another_lanes_lock_once_and_never_waits(self) -> None:
        """The pack checkout runs every lane's `sd-ship`; move it only while no other lane runs."""
        tree, head = self.topic()
        before = git(self.repo, "rev-parse", "HEAD")
        self.advance_origin_main()
        self.merge_lands(tree, 1, head)
        other = self.root / "system/lane/queue/runner.lock"
        other.parent.mkdir(parents=True)
        with open(other, "a", encoding="utf-8") as held, mock.patch.object(sd_lane, "BIN", self.repo / "bin"):
            fcntl.flock(held, fcntl.LOCK_EX)
            started = time.monotonic()
            self.drain()
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        self.assertIn("the system lane is running from this checkout", self.entries()[0]["fast_forward"])
        tree, head = self.topic("later")
        self.merge_lands(tree, 2, head)
        with mock.patch.object(sd_lane, "BIN", self.repo / "bin"):
            self.drain()  # the other lane is idle now: the next landing catches up
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), git(self.origin, "rev-parse", "main"))

    def test_a_failing_note_does_not_undo_the_merge(self) -> None:
        tree, head = self.topic()
        self.merge_lands(tree, 1, head)

        def broken(item: int, body: str, main: pathlib.Path) -> str:
            raise OSError("the store is locked")
        sd_lane.run_lane(self.repo, self.environ, self.ship, note=broken)
        entry = self.entries()[0]
        self.assertEqual(entry["status"], "merged")
        self.assertIn("the store is locked", entry["note"])
        self.assertIn("fast-forward", entry["fast_forward"])

    def test_keep_worktree_reaches_the_queue_through_sd_ship(self) -> None:
        tree, _ = self.topic()
        env = {**os.environ, **self.environ}
        done = subprocess.run([sys.executable, str(REPO_ROOT / "bin/sd-ship"), "lane", "enqueue", "--item", "3",
                               "--title", "t", "--body-file", str(self.body), "--deliver", "--keep-worktree"],
                              cwd=tree, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        self.assertIs(self.entries()[0]["keep_worktree"], True)


class ShipProcess(Lane):
    def test_the_answer_is_parsed_and_the_whole_output_kept(self) -> None:
        from unittest import mock

        log = self.tmp / "logs/step.log"
        with mock.patch.dict(os.environ, self.environ):
            answer = sd_lane.ship_process(["-C", str(self.repo), "lane", "list"], log, 120)
        self.assertEqual((answer["ok"], answer["entries"]), (True, []))
        self.assertTrue(log.read_text(encoding="utf-8").startswith(f"$ sd-ship -C {self.repo} lane list\n{{"))


class Watch(Lane):
    def test_each_gate_end_is_printed_once(self) -> None:
        log = self.root / "pack/lane/make-check.log"
        log.parent.mkdir(parents=True)
        log.write_text("run-tests: start head=abc\nrun-tests: end head=abc exit=0\n", encoding="utf-8")
        seen: set[str] = set()
        self.assertEqual(sd_lane.gate_ends(self.root, seen), ["GATE-END lane/make-check.log: run-tests: end head=abc exit=0"])
        self.assertEqual(sd_lane.gate_ends(self.root, seen), [])
        with log.open("a", encoding="utf-8") as handle:
            handle.write("make: *** [test] Error 1\n")
        self.assertEqual(sd_lane.gate_ends(self.root, seen), ["GATE-END lane/make-check.log: make: *** [test] Error 1"])


class Bounds(unittest.TestCase):
    def test_prepare_and_merge_bounds_cover_a_gates_slot_wait(self) -> None:
        """sd:2611: the gate under them queues for up to `GATE_SLOT_SECONDS` before its check starts."""
        for bound in (sd_lane.PREPARE_SECONDS, sd_lane.MERGE_SECONDS):
            self.assertGreaterEqual(bound, 3 * 3600 + sd_lane.sd_lib.GATE_SLOT_SECONDS)


if __name__ == "__main__":
    unittest.main()
