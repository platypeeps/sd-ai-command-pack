"""`sd-ship lane` (sd:2524): a serial ship queue per repository that outlives its session.

The acceptance test is the first: an entry one process enqueued is there for
the next process to read. The runner tests replace `sd-ship` with a recorder,
so nothing reaches GitHub or a review.
"""

from __future__ import annotations

import contextlib
import fcntl
import importlib.util
import io
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
    #: `repo.runner_merge` for a suite with no database (sd:3132); None reads the suite's own database.
    runner_merge: str | None = "manual"

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
        if self.runner_merge is not None:
            patcher = mock.patch.object(sd_lane, "default_runner_merge", lambda root: self.runner_merge)
            patcher.start()
            self.addCleanup(patcher.stop)
        # And each runs as the hub would, which hosts every lane whose `repo.lane_host` is NULL (sd:3003).
        if importlib.util.find_spec("sd_db") is not None:
            patcher = mock.patch("sd_db.database.served_by", lambda target, home=None: None, create=True)
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
        self.assertEqual({key: entry[key] for key in ("worktree", "item", "expected_head", "title", "status")},
                         {"worktree": str(tree), "item": 7, "expected_head": head, "title": "Topic", "status": "pending"})
        body = pathlib.Path(entry["body_file"])
        self.assertEqual((body.parent, body.read_text(encoding="utf-8")),
                         (self.root / "pack/lane/bodies", self.body.read_text(encoding="utf-8")))

    def test_retry_prints_json_as_the_other_verbs_do(self) -> None:
        """sd:3254. The system Queue page calls `lane retry`; it reads the same JSON shape."""
        sd_lane.enqueue_entry(self.repo, 7, "Topic", self.body, self.environ, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        done = self.sd_ship(self.repo, "retry", "7", "--manual")
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        answer = json.loads(done.stdout)
        self.assertEqual((answer["ok"], answer["item"], answer["authority"], answer["status"]), (True, 7, "manual", "pending"))
        again = self.sd_ship(self.repo, "retry", "7")
        self.assertEqual((again.returncode, json.loads(again.stdout)["ok"]), (3, False))

    def test_retry_expected_head_refuses_another_head_and_names_both(self) -> None:
        """sd:3268. The Queue page sends the head it showed; another blocked head is refused with `stale_head`."""
        sd_lane.enqueue_entry(self.repo, 7, "Topic", self.body, self.environ, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        head = self.entries()[0]["expected_head"]
        done = self.sd_ship(self.repo, "retry", "7", "--expected-head", "0" * 40)
        answer = json.loads(done.stdout)
        self.assertEqual((done.returncode, answer["ok"], answer["code"]), (3, False, sd_lane.STALE_HEAD), done.stdout)
        self.assertIn(head, answer["error"])
        self.assertIn("0" * 40, answer["error"])
        self.assertEqual([row["status"] for row in self.entries()], ["prepared"])
        done = self.sd_ship(self.repo, "retry", "7", "--manual", "--expected-head", head)
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        self.assertEqual(json.loads(done.stdout)["expected_head"], head)

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

    def test_prepare_reads_the_lanes_copy_of_the_body_once_the_original_is_gone(self) -> None:
        """sd:3170: a reboot that clears /tmp left entries naming a lost body; the lane keeps its own copy."""
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        self.body.unlink()
        read: list[tuple[str, str]] = []

        def ship(argv: list[str], log: pathlib.Path) -> dict:
            if argv[2] == "prepare":
                named = argv[argv.index("--body-file") + 1]
                read.append((named, pathlib.Path(named).read_text(encoding="utf-8")))
            return self.ship(argv, log)

        sd_lane.run_lane(self.repo, self.environ, ship)
        [entry] = self.entries()
        self.assertEqual(entry["status"], "merged", entry.get("reason"))
        [(named, text)] = read
        lane = sd_lane.lane_dir(self.repo, self.environ)
        self.assertEqual((pathlib.Path(named).parent, text), (lane / "bodies", "Item: sd:1\n"))

    def test_the_body_copy_is_private_and_goes_when_its_entry_ends(self) -> None:
        """sd:3170: merged and cancelled entries drop their copy; an older entry's own file stays.

        sd:3254: a failed entry keeps its copy, for `lane retry`, until the item's next entry ends.
        """
        first, second = self.worktree("first"), self.worktree("second")
        for tree, item in ((first, 1), (second, 2), (self.repo, 3)):
            sd_lane.enqueue_entry(tree, item, "t", self.body, self.environ, manual=True, claim="deliver")
        copies = {row["item"]: pathlib.Path(row["body_file"]) for row in self.entries()}
        self.assertEqual(len(set(copies.values())), 3)
        self.assertEqual({oct(path.stat().st_mode & 0o777) for path in copies.values()}, {"0o600"})
        self.assertEqual(oct(copies[1].parent.stat().st_mode & 0o777), "0o700")
        sd_lane.cancel(self.repo, 3, self.environ)
        self.assertFalse(copies[3].exists(), "the cancelled entry's copy stayed")
        self.answers[(2, "prepare")] = {"ok": False, "phase": "review_blocked", "error": "a blocking finding"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([row["status"] for row in self.entries()], ["merged", "failed", "cancelled"])
        self.assertEqual({item: path.exists() for item, path in copies.items()}, {1: False, 2: True, 3: False})
        self.assertTrue(self.body.is_file(), "the caller's own body file went with the copies")
        # An entry an earlier version queued names the caller's file, which stays when the entry ends.
        older = self.tmp / "older.md"
        older.write_text("Item: sd:4\n", encoding="utf-8")

        def as_before(entries: list[dict]) -> None:
            entries.append({"worktree": str(self.repo), "item": 4, "expected_head": git(self.repo, "rev-parse", "HEAD"),
                            "title": "t", "body_file": str(older), "authority": "manual", "claim": "deliver",
                            "acceptance_file": None, "status": "pending", "enqueued_at": sd_lane.stamp_now()})
        sd_lane.update(sd_lane.queue_path(self.repo, self.environ), as_before)
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual(self.entries()[-1]["status"], "merged")
        self.assertTrue(older.is_file(), "an older entry's body file was removed")

    def test_a_blocked_entry_is_retried_at_its_head_with_its_kept_body(self) -> None:
        """sd:3254. A failed entry could not be queued again without its body file; retry needs none."""
        tree, acceptance = self.worktree("topic"), self.tmp / "acceptance.md"
        acceptance.write_text("accepted\n", encoding="utf-8")
        sd_lane.enqueue_entry(tree, 1, "one", self.body, self.environ, manual=True, claim="deliver",
                              acceptance_file=acceptance)
        self.answers[(1, "prepare")] = {"ok": False, "phase": "review_blocked", "error": "a blocking finding"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        failed = self.entries()[0]
        kept = pathlib.Path(failed["body_file"])
        self.assertTrue(kept.is_file(), "the failed entry's body copy went")
        self.body.unlink()
        retried = sd_lane.retry(self.repo, 1, self.environ)
        self.assertEqual({key: retried[key] for key in ("item", "expected_head", "title", "authority", "claim",
                                                        "acceptance_file", "status")},
                         {"item": 1, "expected_head": failed["expected_head"], "title": "one", "authority": "manual",
                          "claim": "deliver", "acceptance_file": failed["acceptance_file"], "status": "pending"})
        self.assertEqual(retried["retried"], {"status": "failed", "finished_at": failed["finished_at"]})
        fresh = pathlib.Path(retried["body_file"])
        self.assertEqual(fresh.read_text(encoding="utf-8"), "Item: sd:1\n")
        with self.assertRaisesRegex(sd_lane.LaneError, "already queued"):
            sd_lane.retry(self.repo, 1, self.environ)
        del self.answers[(1, "prepare")]
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([row["status"] for row in self.entries()], ["failed", "merged"])
        # The next entry ended, so the earlier copy goes, and a merged entry keeps none.
        self.assertEqual((kept.exists(), fresh.exists()), (False, False))

    def test_retry_manual_approves_an_entry_that_stopped_prepared(self) -> None:
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual(self.entries()[0]["code"], sd_lane.RUNNER_MERGE_MANUAL)
        self.assertEqual(sd_lane.retry(self.repo, 1, self.environ, manual=True)["authority"], "manual")
        self.calls.clear()
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual(([c[2] for c in self.calls], self.entries()[-1]["status"]), (["prepare", "merge"], "merged"))

    def test_retry_starts_from_prepares_catch_up_merge(self) -> None:
        tree = self.worktree("topic")
        sd_lane.enqueue_entry(tree, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "base moved")

        def catch_up_then_block(argv: list[str], log: pathlib.Path) -> dict:
            git(tree, "merge", "-q", "--no-ff", "-m", "Merge origin/main", "main")
            self.ship(argv, log)
            return {"ok": False, "phase": "review_blocked", "error": "a blocking finding"}
        sd_lane.run_lane(self.repo, self.environ, catch_up_then_block)
        self.assertEqual(sd_lane.retry(self.repo, 1, self.environ)["expected_head"], git(tree, "rev-parse", "HEAD"))

    def test_retry_refuses_what_it_cannot_retry(self) -> None:
        with self.assertRaisesRegex(sd_lane.LaneError, "no entry"):
            sd_lane.retry(self.repo, 1, self.environ)
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        with self.assertRaisesRegex(sd_lane.LaneError, "already queued"):
            sd_lane.retry(self.repo, 1, self.environ)
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        with self.assertRaisesRegex(sd_lane.LaneError, "last entry is merged"):
            sd_lane.retry(self.repo, 1, self.environ)
        sd_lane.enqueue_entry(self.repo, 2, "two", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.cancel(self.repo, 2, self.environ)
        with self.assertRaisesRegex(sd_lane.LaneError, "last entry is cancelled"):
            sd_lane.retry(self.repo, 2, self.environ)
        # An entry that ended before its copy was kept has none to queue again.
        sd_lane.enqueue_entry(self.repo, 3, "three", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(3, "prepare")] = {"ok": False, "phase": "review_blocked", "error": "a blocking finding"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        pathlib.Path(self.entries()[-1]["body_file"]).unlink()
        with self.assertRaisesRegex(sd_lane.LaneError, "--body-file"):
            sd_lane.retry(self.repo, 3, self.environ)
        self.assertEqual([row["status"] for row in self.entries()], ["merged", "cancelled", "failed"])

    def test_retry_expected_head_is_checked_under_the_queue_lock(self) -> None:
        """sd:3268. An entry that ends at another head between retry's read and its write is refused, not retried."""
        tree = self.worktree("topic")
        sd_lane.enqueue_entry(tree, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(1, "prepare")] = {"ok": False, "phase": "review_blocked", "error": "a blocking finding"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        shown = self.entries()[0]["expected_head"]
        git(tree, "commit", "-q", "--allow-empty", "-m", "fix")
        moved = git(tree, "rev-parse", "HEAD")
        caught_up = sd_lane.caught_up

        def another_run_ends_first(worktree: pathlib.Path, expected: str) -> str:
            sd_lane.update(sd_lane.queue_path(self.repo, self.environ),
                           lambda entries: entries.append({**entries[0], "expected_head": moved}))
            return caught_up(worktree, expected)
        with mock.patch.object(sd_lane, "caught_up", another_run_ends_first):
            with self.assertRaises(sd_lane.LaneError) as refused:
                sd_lane.retry(self.repo, 1, self.environ, manual=True, expected_head=shown)
        self.assertEqual(refused.exception.code, sd_lane.STALE_HEAD)
        self.assertIn(moved, str(refused.exception))
        self.assertEqual([(row["status"], row["expected_head"]) for row in self.entries()],
                         [("failed", shown), ("failed", moved)])
        self.assertEqual(sd_lane.retry(self.repo, 1, self.environ, expected_head=moved)["expected_head"], moved)

    def test_a_queue_write_that_fails_keeps_the_entry_and_its_body(self) -> None:
        """sd:3170 review: the copy goes only once the queue records the end; a failed write leaves both."""
        real = sd_lane.write_queue

        def fails_on_an_end(path: pathlib.Path, entries: list[dict]) -> None:
            if any(row.get("status") in ("cancelled", "merged") for row in entries):
                raise OSError(28, "No space left on device")
            real(path, entries)

        sd_lane.enqueue_entry(self.repo, 1, "t", self.body, self.environ, manual=True, claim="deliver")
        [entry] = self.entries()
        body = pathlib.Path(entry["body_file"])
        with mock.patch.object(sd_lane, "write_queue", side_effect=fails_on_an_end):
            with self.assertRaises(OSError):
                sd_lane.cancel(self.repo, 1, self.environ)
            self.assertEqual((self.entries()[0]["status"], body.is_file()), ("pending", True), "cancel")
            with self.assertRaises(OSError):
                sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual((self.entries()[0]["status"], body.is_file()), ("running", True), "run")

    def test_a_refused_enqueue_leaves_no_copy(self) -> None:
        """sd:3170: the copy is made before the queue write; a refusal there takes it back."""
        sd_lane.enqueue_entry(self.repo, 3, "t", self.body, self.environ, claim="deliver")
        bodies = sd_lane.lane_dir(self.repo, self.environ) / "bodies"
        before = sorted(bodies.iterdir())
        with self.assertRaisesRegex(sd_lane.LaneError, "already queued"):
            sd_lane.enqueue_entry(self.repo, 3, "t", self.body, self.environ, claim="deliver")
        self.assertEqual(sorted(bodies.iterdir()), before)

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

    def incomplete_review(self, retried: bool):
        """A recorder whose prepare refuses for an incomplete review, also on its retry when `retried`."""
        refused = {"ok": False, "phase": "prepare",
                   "error": "the preceding review did not complete its requested depth; use --retry-review",
                   "workflow": {"blocker": {"code": "review_incomplete"}}}
        def ship(argv: list[str], log: pathlib.Path) -> dict:
            answer = self.ship(argv, log)
            return refused if argv[2] == "prepare" and (retried or "--retry-review" not in argv) else answer
        return ship

    def test_an_incomplete_review_spends_the_one_automatic_retry(self) -> None:
        """sd:3037. The lane retries as an operator would, with prepare --retry-review."""
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.incomplete_review(retried=False))
        self.assertEqual([(c[2], "--retry-review" in c) for c in self.calls],
                         [("prepare", False), ("prepare", True), ("merge", False)])
        self.assertEqual(self.entries()[0]["status"], "merged")

    def test_the_lane_retries_an_incomplete_review_only_once(self) -> None:
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.incomplete_review(retried=True))
        self.assertEqual([(c[2], "--retry-review" in c) for c in self.calls], [("prepare", False), ("prepare", True)])
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry["step"]), ("failed", "prepare"))
        self.assertIn("did not complete", entry["reason"])

    #: `sd-ship`'s answer when the hub dropped its session or refused its build (sd:3239).
    HUB_FAULT = {"ok": False, "phase": "prepare", "error": "the sd hub at hub.example.test:8769 is unreachable: "
                 "[Errno 32] Broken pipe", "workflow": {"blocker": {"code": "hub_unavailable", "retryable": True}}}

    def test_a_hub_fault_puts_the_entry_back_and_the_next_run_ships_it(self) -> None:
        """sd:3239. A hub upgrade broke prepare's session; the entry failed as a policy block and was lost."""
        tree = self.worktree("topic")
        sd_lane.enqueue_entry(tree, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.enqueue_entry(self.worktree("second"), 2, "two", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(1, "prepare")] = self.HUB_FAULT
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        # The run stops: the hub is mid-upgrade, and the next entry would meet it too.
        self.assertEqual([(c[2], c[4]) for c in self.calls], [("prepare", "1")])
        self.assertIn("sd:1", answer["stopped"])
        one, two = self.entries()
        self.assertEqual((one["status"], one["hub_retries"], one["hub_fault"]["step"], two["status"]),
                         ("pending", 1, "prepare", "pending"))
        self.assertIn("Broken pipe", one["hub_fault"]["reason"])
        self.assertNotIn("step", one)
        self.assertNotIn("runner_pid", one)
        self.assertTrue(pathlib.Path(one["body_file"]).is_file())
        del self.answers[(1, "prepare")]
        self.calls.clear()
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        # No --retry-review: a review that cleared before the fault is the receipt prepare reuses at this head.
        self.assertEqual([(c[2], c[4], "--retry-review" in c) for c in self.calls],
                         [("prepare", "1", False), ("merge", "1", False), ("prepare", "2", False), ("merge", "2", False)])
        self.assertEqual([entry["status"] for entry in self.entries()], ["merged", "merged"])

    def test_a_hub_fault_in_the_merge_is_retried_too(self) -> None:
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(1, "merge")] = {**self.HUB_FAULT, "phase": "merge"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry["hub_fault"]["step"], entry["hub_retries"]), ("pending", "merge", 1))
        del self.answers[(1, "merge")]
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual((self.entries()[0]["status"], [c[2] for c in self.calls]),
                         ("merged", ["prepare", "merge", "prepare", "merge"]))

    def test_the_retry_starts_from_prepares_catch_up_merge_and_not_from_a_builder_commit(self) -> None:
        """The catch-up moved HEAD past the queued head; a commit of the builder's still skips the entry."""
        for builder in (False, True):
            with self.subTest(builder=builder):
                tree = self.worktree(f"topic-{builder}")
                sd_lane.enqueue_entry(tree, 1, "one", self.body, self.environ, manual=True, claim="deliver")
                git(self.repo, "commit", "-q", "--allow-empty", "-m", "base moved")

                def catch_up_then_fault(argv: list[str], log: pathlib.Path, tree: pathlib.Path = tree) -> dict:
                    git(tree, "merge", "-q", "--no-ff", "-m", "Merge origin/main", "main")
                    self.ship(argv, log)
                    return self.HUB_FAULT
                sd_lane.run_lane(self.repo, self.environ, catch_up_then_fault)
                caught_up = git(tree, "rev-parse", "HEAD")
                self.assertEqual(self.entries()[-1]["expected_head"], caught_up)
                if builder:
                    git(tree, "commit", "-q", "--allow-empty", "-m", "the builder's")
                sd_lane.run_lane(self.repo, self.environ, self.ship)
                self.assertEqual(self.entries()[-1]["status"], "skipped" if builder else "merged")

    def test_a_hub_that_keeps_failing_fails_the_entry_after_its_retries(self) -> None:
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(1, "prepare")] = self.HUB_FAULT
        for _ in range(sd_lane.HUB_RETRIES):
            sd_lane.run_lane(self.repo, self.environ, self.ship)
            self.assertEqual(self.entries()[0]["status"], "pending")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry["hub_retries"], len(self.calls)),
                         ("failed", sd_lane.HUB_RETRIES, sd_lane.HUB_RETRIES + 1))
        self.assertIn("Broken pipe", entry["reason"])

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

    def test_a_lane_that_starts_after_the_scan_runs_nothing_until_the_move_ends(self) -> None:
        """sd:3273 review 1: a lane queued after `other_lanes_idle` scanned, with no runner lock yet, waits."""
        with sd_lane.other_lanes_idle(self.root) as busy:
            self.assertIsNone(busy)
            sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver")
            lock = sd_lane.queue_path(self.repo, self.environ).parent / "runner.lock"
            self.assertFalse(lock.exists(), "the lane already had a runner lock for the scan to find")
            started = time.monotonic()
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertLess(time.monotonic() - started, 5)
        self.assertIn("the tools this lane runs are moving", answer.get("busy", ""))
        self.assertEqual((self.calls, self.entries()[0]["status"]), ([], "pending"))
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual(([call[4] for call in self.calls], self.entries()[0]["status"]), (["1"], "prepared"))

    def left_running(self, pid: int | None) -> None:
        """Item 1 claimed by the runner `pid` and never finished, as a killed runner leaves it (sd:2821)."""
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver")

        def claimed(entries: list[dict]) -> None:
            entries[0].update(status="running", runner_pid=pid)
        sd_lane.update(sd_lane.queue_path(self.repo, self.environ), claimed)

    def dead_pid(self) -> int:
        runner = subprocess.Popen([sys.executable, "-c", ""])
        runner.wait()
        return runner.pid

    def test_a_running_entry_whose_runner_died_is_failed_and_the_queue_goes_on(self) -> None:
        pid = self.dead_pid()
        self.left_running(pid)
        sd_lane.enqueue_entry(self.worktree("second"), 2, "two", self.body, self.environ, claim="deliver")
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual(answer["reclaimed"], [{"item": 1, "runner_pid": pid}])
        first, second = self.entries()
        self.assertEqual((first["status"], first["step"], first["reclaimed_by"]), ("failed", "runner", os.getpid()))
        self.assertIn(f"runner pid {pid} died", first["reason"])
        self.assertEqual(([call[4] for call in self.calls], second["status"]), (["2"], "prepared"))
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver")  # no longer refused

    def test_a_running_entry_whose_runner_may_live_is_kept(self) -> None:
        for pid in (os.getpid(), None, 1):  # alive, unreadable, and a pid this user may not signal
            with self.subTest(pid=pid):
                sd_lane.update(sd_lane.queue_path(self.repo, self.environ), list.clear)
                self.left_running(pid)
                answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
                self.assertNotIn("reclaimed", answer)
                self.assertEqual((self.calls, self.entries()[0]["status"]), ([], "running"))

    def test_a_running_entry_is_kept_while_another_runner_holds_the_lock(self) -> None:
        self.left_running(self.dead_pid())
        lock = sd_lane.queue_path(self.repo, self.environ).parent / "runner.lock"
        with open(lock, "a", encoding="utf-8") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertIn("another runner holds", answer["busy"])
        self.assertEqual(self.entries()[0]["status"], "running")

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

    def test_cancel_takes_an_expected_revision_as_the_other_editors_do(self) -> None:
        """sd:3137. A cancel against a queue that changed since its read is refused with the same code."""
        self.queue(1, 2, 3)
        read = sd_lane.queue_revision(self.entries())
        sd_lane.move(self.repo, 3, "top", self.environ)
        before = self.entries()
        with self.assertRaises(sd_lane.LaneError) as caught:
            sd_lane.cancel(self.repo, 2, self.environ, expected_revision=read)
        self.assertEqual((caught.exception.code, self.entries()), (sd_lane.STALE_REVISION, before))
        cancelled = sd_lane.cancel(self.repo, 2, self.environ, expected_revision=sd_lane.queue_revision(before))
        self.assertEqual((cancelled["status"], self.pending()), ("cancelled", [3, 1]))

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
        code, refused = lane("cancel", "1", "--expected-revision", listed["revision"])
        self.assertEqual((code, refused["code"]), (3, sd_lane.STALE_REVISION))
        self.assertEqual(lane("cancel", "1")[1]["status"], "cancelled")  # unset keeps today's behaviour


class Speculation(Lane):
    """sd:2586: while one entry ships, the next one's gate runs on the predicted landing.

    A bare `origin` holds main; two worktrees each add a file, and main moves
    after they fork. The recorder lands entry 1 as
    GitHub's squash would: its catch-up tree as a new commit on main.
    """

    def setUp(self) -> None:
        super().setUp()
        self.origin = self.tmp / "origin.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.commit_files(self.repo, {".github/sd-gate-reuse.json": json.dumps(
            {"schema_version": 1, "key": "tree", "reason": "the check reads no history"})}, "declare")
        git(self.repo, "remote", "add", "origin", str(self.origin))
        git(self.repo, "push", "-q", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        self.first = self.branch("first", {"one.txt": "1\n"})
        self.second = self.branch("second", {"two.txt": "2\n"})
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

    def branch(self, name: str, files: dict[str, str]) -> pathlib.Path:
        path = self.tmp / name
        git(self.repo, "worktree", "add", "-q", "-b", name, str(path), "origin/main")
        self.commit_files(path, files, name)
        return path

    def caught_up(self, head: str, ref: str) -> str:
        """The tree `sd-ship prepare --catch-up` makes at `head` against `ref`, built apart from the lane's code."""
        scratch = self.tmp / f"scratch-{len(list(self.tmp.iterdir()))}"
        git(self.repo, "worktree", "add", "-q", "--detach", str(scratch), head)
        try:
            git(scratch, "merge", "--no-ff", "--no-edit", "-m", "catch up", ref)
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
        # The gated tree is the one entry 2's catch-up makes after the real landing.
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

    def test_a_satellite_entry_an_older_version_queued_is_skipped_and_never_shipped(self) -> None:
        """sd:3003. A `gate: satellite` entry the retired hand-off left names the main checkout, not its head."""
        satellite = self.tmp / "satellite"
        git(self.tmp, "clone", "-q", str(self.origin), str(satellite))
        self.commit_files(satellite, {"sat.txt": "s\n"}, "satellite")
        git(satellite, "push", "-q", "origin", "HEAD:refs/heads/sat")
        sd_lane.update(sd_lane.queue_path(self.repo, self.environ), lambda rows: rows.append({
            "worktree": str(self.repo), "item": 1, "gate": "satellite", "branch": "sat", "base": "main",
            "expected_head": git(satellite, "rev-parse", "HEAD"), "authority": "manual", "status": "pending",
            "enqueued_at": sd_lane.stamp_now()}))
        sd_lane.enqueue_entry(self.second, 2, "two", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, super().ship, lambda root, head, base: {"status": "success"})
        self.assertEqual([(entry["item"], entry["status"]) for entry in self.entries()], [(1, "skipped"), (2, "merged")])
        self.assertEqual([call[call.index("--item") + 1] for call in self.calls], ["2", "2"])


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

    def test_a_worktree_the_merge_removed_is_landed_from_the_lane_root(self) -> None:
        """sd:3096. `sd-ship merge` removes a clean worktree (sd:3006); git cannot name the main
        checkout from a directory that is gone, so the landing used to read the dead path as the main
        checkout, note from it (FileNotFoundError) and see a detached HEAD."""
        tree, head = self.topic()
        landed = self.advance_origin_main()
        self.merge_lands(tree, 1, head)
        ship = self.ship

        def remove_after_merge(argv: list[str], log: pathlib.Path) -> dict:
            answer = ship(argv, log)
            if argv[2] == "merge":
                git(self.repo, "worktree", "remove", "--force", str(tree))
            return answer
        self.drain(remove_after_merge)
        entry = self.entries()[0]
        self.assertEqual(entry["note"], "written")
        [(item, body, main)] = self.notes
        self.assertEqual((item, main), (1, self.repo))
        self.assertIn("was already removed by the merge", body)
        self.assertIn("was already removed by the merge", entry["cleanup"])
        self.assertIsNone(entry["remove"])
        self.assertIn("fast-forwarded", entry["fast_forward"])
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), landed)

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


class Resolution(unittest.TestCase):
    def test_a_git_that_gave_no_answer_is_reported_as_itself(self) -> None:
        """sd:2986: a satellite lane run under load reported a git timeout as 'cwd is not inside a Git repository'."""
        import argparse  # noqa: PLC0415
        out = io.StringIO()
        stalled = subprocess.TimeoutExpired(["git"], sd_lane.sd_lib.GIT_TIMEOUT_SECONDS)
        with mock.patch.object(sd_lane.sd_lib.subprocess, "run", side_effect=stalled), contextlib.redirect_stdout(out):
            code = sd_lane.lane_main(argparse.Namespace(lane_command="list"))
        error = json.loads(out.getvalue())["error"]
        self.assertEqual(code, 3)
        self.assertIn("git rev-parse --show-toplevel did not finish within", error)


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
