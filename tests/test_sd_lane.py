"""`sd-ship lane` (sd:2524): a serial ship queue per repository that outlives its session.

The acceptance test is the first: an entry one process enqueued is there for
the next process to read. The runner tests replace `sd-ship` with a recorder,
so nothing reaches GitHub or a review.
"""

from __future__ import annotations

import contextlib
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
        # Nor does a run read requests from one (sd:2704): a suite passes its own `hub`.
        for name, double in (("default_note", self.note), ("default_hub", lambda root: contextlib.nullcontext())):
            patcher = mock.patch.object(sd_lane, name, double)
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


class Reorder(Lane):
    """sd:2584: the runner reads the queue's top before each item, and the verbs reorder it."""

    def queue(self, *items: int, manual: bool = False) -> None:
        for item in items:
            sd_lane.enqueue_entry(self.worktree(f"t{item}"), item, f"t{item}", self.body, self.environ,
                                  manual=manual, claim="deliver")

    def items_run(self) -> list[int]:
        return [int(c[c.index("--item") + 1]) for c in self.calls if c[2] == "prepare"]

    def pending(self) -> list[int]:
        return [row["item"] for row in self.entries() if row["status"] == "pending"]

    def test_a_move_while_the_first_merges_runs_the_moved_item_second_and_a_hold_skips(self) -> None:
        self.queue(1, 2, 3, 4, manual=True)
        sd_lane.set_hold(self.repo, 2, self.environ, held=True)
        ship = self.ship

        def move_during_the_first_merge(argv: list[str], log: pathlib.Path) -> dict:
            if argv[2] == "merge" and argv[argv.index("--item") + 1] == "1":
                sd_lane.move(self.repo, 4, "top", self.environ)
            return ship(argv, log)
        sd_lane.run_lane(self.repo, self.environ, move_during_the_first_merge)
        self.assertEqual((self.items_run(), self.pending()), ([1, 4, 3], [2]))
        sd_lane.set_hold(self.repo, 2, self.environ, held=False)
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual(self.items_run(), [1, 4, 3, 2])

    def test_up_down_and_a_position_move_among_pending_entries_only(self) -> None:
        self.queue(1, 2, 3, 4)
        sd_lane.cancel(self.repo, 1, self.environ)
        self.assertEqual(sd_lane.move(self.repo, 4, "up", self.environ)["pending"], [2, 4, 3])
        self.assertEqual(sd_lane.move(self.repo, 2, "down", self.environ)["pending"], [4, 2, 3])
        self.assertEqual(sd_lane.move(self.repo, 3, "1", self.environ)["pending"], [3, 4, 2])
        self.assertEqual(sd_lane.move(self.repo, 3, "9", self.environ)["pending"], [4, 2, 3])
        self.assertEqual(sd_lane.move(self.repo, 4, "up", self.environ)["pending"], [4, 2, 3])
        # The cancelled entry keeps its place in the history at the front.
        self.assertEqual([row["item"] for row in self.entries()], [1, 4, 2, 3])

    def test_a_running_entry_is_not_edited_and_an_absent_or_unheld_one_is_refused(self) -> None:
        self.queue(1)
        sd_lane.update(sd_lane.queue_path(self.repo, self.environ), lambda rows: rows[0].update(status="running"))
        for verb in (lambda: sd_lane.move(self.repo, 1, "top", self.environ),
                     lambda: sd_lane.set_hold(self.repo, 1, self.environ, held=True)):
            with self.assertRaisesRegex(sd_lane.LaneError, "between items"):
                verb()
        with self.assertRaisesRegex(sd_lane.LaneError, "no pending entry"):
            sd_lane.move(self.repo, 5, "top", self.environ)
        self.queue(2)
        with self.assertRaisesRegex(sd_lane.LaneError, "not held"):
            sd_lane.set_hold(self.repo, 2, self.environ, held=False)

    def test_a_position_must_be_up_down_top_or_a_positive_number(self) -> None:
        for where in ("0", "-1", "sideways"):
            with self.assertRaises(ValueError):
                sd_lane.position(where)

    def test_the_speculative_gate_skips_a_held_entry(self) -> None:
        self.queue(1, 2, 3, manual=True)
        sd_lane.set_hold(self.repo, 2, self.environ, held=True)
        sd_lane.update(sd_lane.queue_path(self.repo, self.environ), lambda rows: rows[0].update(status="running"))
        followers: list[int] = []
        with mock.patch.object(sd_lane, "predict", lambda entry, following: followers.append(following["item"]) or
                               {"skipped": "recorded"}):
            sd_lane.speculate(self.entries()[0], sd_lane.queue_path(self.repo, self.environ), lambda *a: {})
        self.assertEqual(followers, [3])

    def test_the_verbs_reorder_through_sd_ship(self) -> None:
        self.queue(1, 2)
        env = {**os.environ, **self.environ}

        def lane(*args: str) -> dict:
            done = subprocess.run([sys.executable, str(REPO_ROOT / "bin/sd-ship"), "-C", str(self.repo), "lane", *args],
                                  env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
            return json.loads(done.stdout)
        self.assertEqual(lane("move", "2", "top")["pending"], [2, 1])
        self.assertTrue(lane("hold", "1")["held"])
        self.assertEqual([(row["item"], bool(row.get("held"))) for row in lane("list")["entries"]], [(2, False), (1, True)])
        self.assertFalse(lane("release", "1")["held"])

    def test_an_expected_revision_refuses_a_queue_that_changed_and_writes_nothing(self) -> None:
        """sd:2717. A caller that read the queue names its revision; a move between its read and its edit is caught."""
        self.queue(1, 2, 3)
        read = sd_lane.queue_revision(self.entries())
        self.assertEqual(sd_lane.move(self.repo, 3, "top", self.environ, expected_revision=read)["pending"], [3, 1, 2])
        before = self.entries()
        for verb in (lambda: sd_lane.move(self.repo, 2, "top", self.environ, expected_revision=read),
                     lambda: sd_lane.set_hold(self.repo, 2, self.environ, held=True, expected_revision=read)):
            with self.assertRaises(sd_lane.LaneError) as caught:
                verb()
            self.assertEqual(caught.exception.code, sd_lane.STALE_REVISION)
        self.assertEqual(self.entries(), before)
        held = sd_lane.set_hold(self.repo, 2, self.environ, held=True, expected_revision=sd_lane.queue_revision(before))
        self.assertTrue(held["held"])
        with self.assertRaises(sd_lane.LaneError) as caught:
            sd_lane.set_hold(self.repo, 2, self.environ, held=False, expected_revision=sd_lane.queue_revision(before))
        self.assertEqual((caught.exception.code, self.pending()), (sd_lane.STALE_REVISION, [3, 1, 2]))

    def test_the_revision_is_compared_under_the_queue_lock(self) -> None:
        """A write that lands while the verb waits for the lock is caught; a check before the lock would miss it."""
        self.queue(1, 2)
        path = sd_lane.queue_path(self.repo, self.environ)
        read = sd_lane.queue_revision(self.entries())
        refused: list[str | None] = []

        def stale_move() -> None:
            try:
                sd_lane.move(self.repo, 2, "top", self.environ, expected_revision=read)
            except sd_lane.LaneError as error:
                refused.append(error.code)
        with sd_lane.queue_lock(path):
            mover = threading.Thread(target=stale_move)
            mover.start()
            time.sleep(0.5)  # the mover reaches the lock; this writer holds it
            entries = sd_lane.read_queue(path)
            entries.reverse()
            sd_lane.write_queue(path, entries)
        mover.join(30)
        self.assertEqual((refused, self.pending()), ([sd_lane.STALE_REVISION], [2, 1]))

    def test_list_prints_the_revision_and_a_stale_one_exits_3_with_its_code(self) -> None:
        self.queue(1, 2)
        env = {**os.environ, **self.environ}

        def lane(*args: str) -> tuple[int, dict]:
            done = subprocess.run([sys.executable, str(REPO_ROOT / "bin/sd-ship"), "-C", str(self.repo), "lane", *args],
                                  env=env, capture_output=True, text=True, timeout=120)
            return done.returncode, json.loads(done.stdout)
        _, listed = lane("list")
        self.assertEqual(listed["revision"], sd_lane.queue_revision(listed["entries"]))
        self.assertEqual(lane("hold", "2", "--expected-revision", listed["revision"])[0], 0)
        code, refused = lane("release", "2", "--expected-revision", listed["revision"])
        self.assertEqual((code, refused["code"]), (3, sd_lane.STALE_REVISION))
        self.assertEqual(lane("move", "2", "top")[1]["pending"], [2, 1])  # unset keeps today's behaviour


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

    def test_a_satellite_entry_ahead_is_predicted_from_its_branch_on_origin(self) -> None:
        """sd:2704. Its worktree is the main checkout, whose HEAD is not its head; the branch on origin is."""
        git(self.first, "push", "-q", "origin", "first")
        sd_lane.update(sd_lane.queue_path(self.repo, self.environ), lambda rows: rows.append({
            "worktree": str(self.repo), "item": 1, "gate": "satellite", "branch": "first", "base": "main",
            "expected_head": git(self.first, "rev-parse", "HEAD"), "authority": "manual", "status": "pending",
            "enqueued_at": sd_lane.stamp_now()}))
        sd_lane.enqueue_entry(self.second, 2, "two", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, super().ship, lambda root, head, base: self.gates.append(
            (root, head, base)) or {"status": "success"})
        [(root, _, _)] = self.gates
        self.assertEqual((root, self.entries()[1]["speculation"]["status"]), (self.second, "success"))


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

    def merge_lands(self, tree: pathlib.Path, item: int, head: str) -> None:
        sd_lane.enqueue_entry(tree, item, "t", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(item, "prepare")] = {"ok": True, "phase": "ready_to_send", "head": head}
        self.answers[(item, "merge")] = {"ok": True, "phase": "merged", "merge_commit": "c0ffee" * 6 + "c0ff"}

    def drain(self, ship=None) -> dict:
        return sd_lane.run_lane(self.repo, self.environ, ship or self.ship)

    def remote_branches(self) -> list[str]:
        return git(self.origin, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()

    def advance_origin_main(self) -> str:
        upstream = self.tmp / "upstream"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(upstream)], check=True)
        git(upstream, "-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "landed")
        git(upstream, "push", "-q", "origin", "main")
        return git(upstream, "rev-parse", "HEAD")

    def test_a_merged_worktree_stays_and_the_note_names_its_removal_command(self) -> None:
        """The review's race (sd:2568): removal can race a live builder, so the runner never removes the worktree."""
        tree, head = self.topic()
        self.merge_lands(tree, 1, head)
        self.drain()
        self.assertEqual((tree / "pkg/mod/a.py").read_text(encoding="utf-8"), "A = 1\n")
        self.assertEqual(os.readlink(tree / "link"), "README.md")
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/topic"), head)
        self.assertEqual(self.remote_branches(), ["main"])
        remove = f"git -C {self.repo} worktree remove {tree} && git -C {self.repo} update-ref -d refs/heads/topic {head}"
        [(item, body, main)] = self.notes
        self.assertEqual((item, main), (1, self.repo))
        self.assertEqual(body, f"Landed: merged at c0ffeec0ffee (head {head[:12]}). Cleanup: removed origin/topic, "
                               f"worktree {tree} and branch topic kept for removal once the builder stops. "
                               f"Recover: git branch topic {head}. Remove: {remove}")
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry["remove"]), ("merged", remove))
        subprocess.run(remove, shell=True, check=True, capture_output=True)  # the printed command works as printed
        self.assertFalse(tree.exists())
        self.assertEqual(git(self.repo, "branch", "--list", "topic"), "")

    def test_a_builder_write_through_an_open_handle_survives_the_landing(self) -> None:
        """The second review's case: a handle opened before the landing, written after it."""
        tree, head = self.topic()
        self.merge_lands(tree, 1, head)
        with open(tree / "README.md", "a", encoding="utf-8") as handle:
            self.drain()
            handle.write("late\n")
        self.assertEqual((tree / "README.md").read_text(encoding="utf-8"), "readme\nlate\n")

    def test_the_runner_notes_through_default_note_when_given_none(self) -> None:
        """The fixture replaces `default_note`; `run_lane` must read it at the call, or a suite writes real notes."""
        tree, head = self.topic()
        self.merge_lands(tree, 1, head)
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([item for item, _, _ in self.notes], [1])
        self.assertEqual(self.entries()[0]["note"], "written")

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

    def test_a_remote_branch_that_moved_is_not_deleted(self) -> None:
        tree, head = self.topic()
        other = self.tmp / "other"
        subprocess.run(["git", "clone", "-q", "-b", "topic", str(self.origin), str(other)], check=True)
        git(other, "-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
        git(other, "push", "-q", "origin", "topic")
        self.merge_lands(tree, 1, head)
        self.drain()
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
