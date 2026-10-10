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
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from typing import Any
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
        # The queue is in the hub database (sd:3282): a scratch one under this `HOME`, never the operator's.
        # A lane needs a GitHub origin; Git resolves this one to a bare repository here.
        self.origin = self.tmp / "origin.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(self.repo, "remote", "add", "origin", "https://github.com/example/pack.git")
        git(self.repo, "config", f"url.{self.origin}.insteadOf", "https://github.com/example/pack.git")
        git(self.repo, "push", "-q", "origin", "main")
        import sd_db
        sd_db.initialise(home=self.tmp)
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

    def store(self) -> sd_lane.Queue:
        return sd_lane.queue_for(self.repo, self.environ)

    def entries(self) -> list[dict]:
        return sd_lane.read_queue(self.store())


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
        self.assertEqual({key: entry[key] for key in ("worktree", "item", "expected_head", "title", "status", "branch")},
                         {"worktree": str(tree), "item": 7, "expected_head": head, "title": "Topic", "status": "pending",
                          "branch": "topic"})
        # The entry holds the body's text, and `list` prints its size (sd:3282); nothing goes to `bodies/`.
        self.assertEqual((entry["body_bytes"], "body" in entry), (len(self.body.read_bytes()), False))
        self.assertFalse((self.root / "pack/lane/bodies").exists())

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
        self.assertEqual(text, "Item: sd:1\n")
        self.assertFalse(pathlib.Path(named).exists(), "the private body file outlived its prepare")

    def test_an_entry_holds_its_texts_and_enqueue_copies_no_file(self) -> None:
        """sd:3282: the body and acceptance texts live in the entry, so any host can run it and `retry` needs no file."""
        acceptance = self.tmp / "acceptance.md"
        acceptance.write_text("accepted\n", encoding="utf-8")
        sd_lane.enqueue_entry(self.repo, 1, "t", self.body, self.environ, claim="deliver", acceptance_file=acceptance)
        [entry] = self.entries()
        self.assertEqual((entry["body"], entry["acceptance"], "body_file" in entry), ("Item: sd:1\n", "accepted\n", False))
        self.assertFalse(sd_lane.lane_dir(self.repo, self.environ).joinpath("bodies").exists())

    def test_a_blocked_entry_is_retried_at_its_head_with_its_kept_body(self) -> None:
        """sd:3254. A failed entry could not be queued again without its body file; retry needs none."""
        tree, acceptance = self.worktree("topic"), self.tmp / "acceptance.md"
        acceptance.write_text("accepted\n", encoding="utf-8")
        sd_lane.enqueue_entry(tree, 1, "one", self.body, self.environ, manual=True, claim="deliver",
                              acceptance_file=acceptance)
        self.answers[(1, "prepare")] = {"ok": False, "phase": "review_blocked", "error": "a blocking finding"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        failed = self.entries()[0]
        self.body.unlink()
        retried = sd_lane.retry(self.repo, 1, self.environ)
        self.assertEqual({key: retried[key] for key in ("item", "expected_head", "title", "authority", "claim",
                                                        "acceptance", "body", "status")},
                         {"item": 1, "expected_head": failed["expected_head"], "title": "one", "authority": "manual",
                          "claim": "deliver", "acceptance": "accepted\n", "body": "Item: sd:1\n", "status": "pending"})
        self.assertEqual(retried["retried"], {"status": "failed", "finished_at": failed["finished_at"]})
        with self.assertRaisesRegex(sd_lane.LaneError, "already queued"):
            sd_lane.retry(self.repo, 1, self.environ)
        del self.answers[(1, "prepare")]
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([row["status"] for row in self.entries()], ["failed", "merged"])

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
        sd_lane.update(self.store(), lambda rows: rows[-1].update(body=None))
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
            sd_lane.update(self.store(), lambda entries: entries.append(
                {**entries[0], "id": "later", "position": 2, "expected_head": moved}))
            return caught_up(worktree, expected)
        with mock.patch.object(sd_lane, "caught_up", another_run_ends_first):
            with self.assertRaises(sd_lane.LaneError) as refused:
                sd_lane.retry(self.repo, 1, self.environ, manual=True, expected_head=shown)
        self.assertEqual(refused.exception.code, sd_lane.STALE_HEAD)
        self.assertIn(moved, str(refused.exception))
        self.assertEqual([(row["status"], row["expected_head"]) for row in self.entries()],
                         [("failed", shown), ("failed", moved)])
        self.assertEqual(sd_lane.retry(self.repo, 1, self.environ, expected_head=moved)["expected_head"], moved)

    def test_a_queue_write_that_fails_changes_nothing_and_says_hub_unavailable(self) -> None:
        """sd:3282: a write is one hub transaction; a fault in it leaves the entry as it was."""
        sd_lane.enqueue_entry(self.repo, 1, "t", self.body, self.environ, manual=True, claim="deliver")
        with mock.patch.object(sd_lane, "store", side_effect=sqlite3.OperationalError("disk I/O error")):
            with self.assertRaises(sd_lane.LaneError) as refused:
                sd_lane.cancel(self.repo, 1, self.environ)
        self.assertEqual((refused.exception.code, self.entries()[0]["status"]), (sd_lane.HUB_UNAVAILABLE, "pending"))

    def test_an_associate_only_entry_prepares_with_associate_only(self) -> None:
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="associate-only")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertIn("--associate-only", self.calls[0])
        self.assertNotIn("--deliver", self.calls[0])

    def test_an_acceptance_file_is_forwarded_to_prepare(self) -> None:
        acceptance = self.tmp / "acceptance.json"
        acceptance.write_text("{}", encoding="utf-8")
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver", acceptance_file=acceptance)
        acceptance.unlink()  # the entry holds the text (sd:3282)
        read: list[str] = []

        def ship(argv: list[str], log: pathlib.Path) -> dict:
            if argv[2] == "prepare":
                read.append(pathlib.Path(argv[argv.index("--acceptance-file") + 1]).read_text(encoding="utf-8"))
            return self.ship(argv, log)
        sd_lane.run_lane(self.repo, self.environ, ship)
        self.assertEqual((read, "--deliver" in self.calls[0]), (["{}"], True))

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
        self.assertNotIn("holder", one)
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
        lock = self.store().lock_file
        lock.parent.mkdir(parents=True, exist_ok=True)
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

    def left_running(self, pid: int | None, step: str = "prepare") -> None:
        """Item 1 claimed by the runner `pid` and never finished, as a killed runner leaves it (sd:2821)."""
        if not self.entries():
            sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver")

        def claimed(entries: list[dict]) -> None:
            entries[0].update(status="running", step=step, holder={"host": sd_lane.this_host(), "pid": pid, "token": "t"})
        sd_lane.update(self.store(), claimed)

    def dead_pid(self) -> int:
        runner = subprocess.Popen([sys.executable, "-c", ""])
        runner.wait()
        return runner.pid

    def test_a_running_entry_whose_runner_died_mid_merge_is_failed_and_the_queue_goes_on(self) -> None:
        """Failure table, merge: the runner dies mid-merge; a merge may have landed, so reclaim fails it (sd:3282)."""
        pid = self.dead_pid()
        self.left_running(pid, step="merge")
        sd_lane.enqueue_entry(self.worktree("second"), 2, "two", self.body, self.environ, claim="deliver")
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual(answer["reclaimed"], [{"item": 1, "runner_pid": pid, "step": "merge", "status": "failed"}])
        first, second = self.entries()
        self.assertEqual((first["status"], first["step"], first["reclaimed_by"]), ("failed", "runner", os.getpid()))
        self.assertIn(f"runner pid {pid} died", first["reason"])
        self.assertEqual(([call[4] for call in self.calls], second["status"]), (["2"], "prepared"))
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver")  # no longer refused

    def test_a_running_entry_whose_runner_may_live_is_kept(self) -> None:
        for pid in (os.getpid(), None, 1):  # alive, unreadable, and a pid this user may not signal
            with self.subTest(pid=pid):
                self.left_running(pid)
                answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
                self.assertNotIn("reclaimed", answer)
                self.assertEqual((self.calls, self.entries()[0]["status"]), ([], "running"))

    def test_a_running_entry_is_kept_while_another_runner_holds_the_lock(self) -> None:
        self.left_running(self.dead_pid())
        lock = self.store().lock_file
        lock.parent.mkdir(parents=True, exist_ok=True)
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
        sd_lane.update(self.store(), lambda rows: rows[0].update(status="running"))
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
        sd_lane.update(self.store(), lambda rows: rows[0].update(status="running"))
        followers: list[int] = []
        with mock.patch.object(sd_lane, "predict", lambda entry, following: followers.append(following["item"]) or
                               {"skipped": "recorded"}):
            sd_lane.speculate(self.entries()[0], self.store(), lambda *a: {})
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
        """A write that lands while the verb waits for the hub's write lock is caught; a check before it would miss it."""
        self.queue(1, 2)
        read = sd_lane.queue_revision(self.entries())
        refused: list[str | None] = []

        def stale_move() -> None:
            try:
                sd_lane.move(self.repo, 2, "top", self.environ, expected_revision=read)
            except sd_lane.LaneError as error:
                refused.append(error.code)
        import sd_db
        writer = sd_db.connect(home=self.tmp)
        self.addCleanup(writer.close)
        with sd_db.database.transaction(writer):  # BEGIN IMMEDIATE: the mover waits for it
            mover = threading.Thread(target=stale_move)
            mover.start()
            time.sleep(0.5)
            entries = sd_lane.stored(writer, "example/pack")
            entries[0]["position"], entries[1]["position"] = entries[1]["position"], entries[0]["position"]
            for row in entries:
                sd_lane.store(writer, "example/pack", row)
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
        self.commit_files(self.repo, {".github/sd-gate-reuse.json": json.dumps(
            {"schema_version": 1, "key": "tree", "reason": "the check reads no history"})}, "declare")
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
        sd_lane.update(self.store(), lambda rows: rows.append({
            "id": "older", "position": 0, "worktree": str(self.repo), "item": 1, "gate": "satellite", "branch": "sat", "base": "main",
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

class Killed(BaseException):
    """A process killed between two steps: nothing after the raise runs, and no `except Exception` catches it."""


class SharedQueue(Lane):
    """sd:3282, slice 1 of the sd:3174 design: the queue in the hub database. One test per failure-table row."""

    def setUp(self) -> None:
        super().setUp()
        for name, value in (("WRITE_RETRY_SECONDS", 0), ("WRITE_PAUSE", 0)):
            patcher = mock.patch.object(sd_lane, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.git_verbs: list[str] = []
        real = sd_lane.publish_git

        def recorded(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess | None:
            self.git_verbs.append(args[0])
            return real(root, *args)
        patcher = mock.patch.object(sd_lane, "publish_git", recorded)
        patcher.start()
        self.addCleanup(patcher.stop)

    def remote_tip(self, branch: str) -> str | None:
        return git(self.origin, "for-each-ref", "--format=%(objectname)", f"refs/heads/{branch}") or None

    def committed(self, name: str, *messages: str) -> tuple[pathlib.Path, list[str]]:
        tree = self.worktree(name)
        heads = []
        for message in messages:
            git(tree, "commit", "-q", "--allow-empty", "-m", message)
            heads.append(git(tree, "rev-parse", "HEAD"))
        return tree, heads

    def rows(self) -> list[tuple[str, dict]]:
        import sd_db
        connection = sd_db.connect(home=self.tmp, write=False)
        try:
            return [(row["key"], json.loads(row["body"])) for row in connection.execute(
                "SELECT key, body FROM state WHERE kind = 'checkpoint' AND key LIKE 'lane:v1:%' ORDER BY id")]
        finally:
            connection.close()

    def failing(self, verb: str) -> Any:
        """A `publish_git` whose `verb` fails as a refused push or a dropped network does."""
        real = sd_lane.publish_git

        def answer(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess | None:
            self.git_verbs.append(args[0])
            if args[0] == verb:
                return subprocess.CompletedProcess(["git", *args], 1, "", "remote: refused")
            return real(root, *args)
        return mock.patch.object(sd_lane, "publish_git", answer)

    def make_dead(self) -> None:
        """The runner that holds the running entry exits, as a stopped or killed one does."""
        runner = subprocess.Popen([sys.executable, "-c", ""])
        runner.wait()
        sd_lane.update(self.store(), lambda rows: [row["holder"].update(pid=runner.pid) for row in rows
                                                   if row.get("status") == "running"])


class Publishing(SharedQueue):
    def test_a_failing_push_leaves_no_row_and_a_diverged_remote_refuses(self) -> None:
        """Failure table, enqueue: push refused or fails, or branch_diverged; nothing queued."""
        tree, [head] = self.committed("topic", "work")
        with self.failing("push"), self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.enqueue_entry(tree, 1, "t", self.body, self.environ, claim="deliver")
        self.assertEqual((refused.exception.code, self.rows()), (sd_lane.PUBLISH_UNKNOWN, []))
        other = self.tmp / "other"
        git(self.tmp, "clone", "-q", str(self.origin), str(other))
        git(other, "-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
        git(other, "push", "-q", "origin", "HEAD:refs/heads/topic")
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.enqueue_entry(tree, 1, "t", self.body, self.environ, claim="deliver")
        self.assertEqual((refused.exception.code, self.rows()), (sd_lane.BRANCH_DIVERGED, []))
        self.assertNotEqual(self.remote_tip("topic"), head)

    def test_enqueue_publishes_the_expected_head_and_not_the_branch_tip(self) -> None:
        """Failure table, enqueue: the tip moved past `--expected-head`; the explicit refspec publishes that head."""
        tree, [older, tip] = self.committed("topic", "one", "two")
        entry = sd_lane.enqueue_entry(tree, 1, "t", self.body, self.environ, claim="deliver", expected_head=older)
        self.assertEqual((entry["expected_head"], self.remote_tip("topic")), (older, older))
        self.assertNotEqual(tip, older)

    def test_a_rerun_after_a_kill_between_push_and_row_writes_one_entry_and_pushes_nothing(self) -> None:
        """Failure table, enqueue: killed between the push and the row write."""
        tree, [head] = self.committed("topic", "work")
        with mock.patch.object(sd_lane, "add_entry", side_effect=Killed), self.assertRaises(Killed):
            sd_lane.enqueue_entry(tree, 1, "t", self.body, self.environ, claim="deliver")
        self.assertEqual((self.remote_tip("topic"), self.rows()), (head, []))
        self.git_verbs.clear()
        sd_lane.enqueue_entry(tree, 1, "t", self.body, self.environ, claim="deliver")
        self.assertNotIn("push", self.git_verbs)
        self.assertEqual([row["item"] for row in self.entries()], [1])

    def test_a_write_that_lands_but_reports_failure_gives_one_entry_on_rerun(self) -> None:
        """Failure table, enqueue: a hub fault after the write landed; the verb says hub_unavailable."""
        real = sd_lane.on_hub

        def landed_then_lost(queue: sd_lane.Queue, work: Any) -> Any:
            real(queue, work)
            raise sd_lane.LaneError("the session dropped", code=sd_lane.HUB_UNAVAILABLE)
        with mock.patch.object(sd_lane, "on_hub", landed_then_lost), self.assertRaises(sd_lane.LaneError) as lost:
            sd_lane.enqueue_entry(self.repo, 1, "t", self.body, self.environ, claim="deliver")
        self.assertEqual(lost.exception.code, sd_lane.HUB_UNAVAILABLE)
        with self.assertRaisesRegex(sd_lane.LaneError, "already queued"):
            sd_lane.enqueue_entry(self.repo, 1, "t", self.body, self.environ, claim="deliver")
        self.assertEqual(len(self.entries()), 1)


class ClaimAndLease(SharedQueue):
    def repo_row(self, host: str | None = None) -> None:
        import sd_db
        connection = sd_db.connect(home=self.tmp)
        try:
            sd_db.upsert_repo(connection, str(self.repo), remote="https://github.com/example/pack.git", managed=1)
            connection.execute("UPDATE repo SET lane_host = ?", (host,))
        finally:
            connection.close()

    def test_a_claim_that_lands_with_its_answer_lost_is_put_back_by_the_next_run(self) -> None:
        """Failure table, claim: the hub fails after the claim landed; no step starts, and reclaim puts it back."""
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        real = sd_lane.on_hub

        def claim_lands_then_hub_goes(queue: sd_lane.Queue, work: Any) -> Any:
            answer = real(queue, work)
            if any(body["status"] == "running" for _, body in self.rows()):
                raise sd_lane.LaneError("the session dropped", code=sd_lane.HUB_UNAVAILABLE)
            return answer
        with mock.patch.object(sd_lane, "on_hub", claim_lands_then_hub_goes):
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertIn("session dropped", answer["stopped"])
        self.assertEqual((self.calls, self.entries()[0]["status"]), ([], "running"))
        self.make_dead()
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([row["status"] for row in answer["reclaimed"]], ["pending"])
        self.assertEqual([(row["item"], row["status"]) for row in self.entries()], [(1, "merged")])

    def test_a_move_between_the_host_read_and_the_claim_claims_nothing(self) -> None:
        """Failure table, claim: the lane moved after the runner's last read; the claim reads the host itself."""
        self.repo_row()
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        settle = sd_lane.settle_checkout

        def then_moved(root: pathlib.Path, queue: sd_lane.Queue) -> dict:
            self.repo_row("build-2")
            return settle(root, queue)
        with mock.patch.object(sd_lane, "settle_checkout", then_moved):
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertIn("runs on build-2", answer["stopped"])
        self.assertEqual((self.calls, self.entries()[0]["status"]), ([], "pending"))

    def test_two_hosts_claim_and_one_wins(self) -> None:
        """Failure table, claim: old and new host claim at once; the second sees a running entry and stops."""
        self.repo_row()
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver")
        sd_lane.enqueue_entry(self.worktree("second"), 2, "two", self.body, self.environ, claim="deliver")
        first = sd_lane.claim_entry(self.store(), "hub-token")
        self.repo_row("build-2")
        with mock.patch("sd_db.ship.this_host", lambda: "build-2"), self.assertRaises(sd_lane.LaneError) as busy:
            sd_lane.claim_entry(self.store(), "satellite-token")
        self.assertEqual((first["item"], busy.exception.code), (1, "lane_busy"))
        self.assertEqual([row["status"] for row in self.entries()], ["running", "pending"])

    def test_a_kill_mid_prepare_puts_the_entry_back_and_the_third_fails_it(self) -> None:
        """Failure table, prepare: the runner dies; pid gone, back to pending; the third reclaim fails it."""
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        seen: list[Any] = []

        def killed_in_prepare(argv: list[str], log: pathlib.Path) -> dict:
            seen.append(self.entries()[0].get("reclaims"))
            raise Killed
        for _ in range(sd_lane.RECLAIMS):
            with self.assertRaises(Killed):
                sd_lane.run_lane(self.repo, self.environ, killed_in_prepare)
            self.make_dead()
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        [entry] = self.entries()
        self.assertEqual((seen, answer["reclaimed"][0]["status"], entry["status"], entry["reclaims"], self.calls),
                         ([None, 1, 2], "failed", "failed", sd_lane.RECLAIMS, []))
        self.assertIn("in prepare", entry["reason"])

    def test_release_voids_the_token_and_refuses_a_live_local_holder(self) -> None:
        """Failure table, release (D3): a released holder's writes are refused; a live pid here is not released."""
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        entry = sd_lane.claim_entry(self.store(), "mine")
        with self.assertRaises(sd_lane.LaneError) as alive:
            sd_lane.cancel(self.repo, 1, self.environ)
        self.assertEqual((alive.exception.code, self.entries()[0]["status"]), ("holder_alive", "running"))
        sd_lane.update(self.store(), lambda rows: rows[0]["holder"].update(host="build-2"))
        released = sd_lane.cancel(self.repo, 1, self.environ)
        self.assertEqual((released["status"], released["released"], "holder" in released), ("pending", True, False))
        before = self.rows()
        for write in (lambda: sd_lane.advance(self.store(), entry, "mine"),
                      lambda: sd_lane.finish_entry(self.store(), entry, "mine", {"status": "merged"})):
            with self.assertRaises(sd_lane.Stop) as lost:
                write()
            self.assertEqual(lost.exception.code, sd_lane.CLAIM_LOST)
        self.assertEqual(self.rows(), before)
        # At `step: merge` a release fails the entry: a merge may have landed.
        entry = sd_lane.claim_entry(self.store(), "again")
        sd_lane.advance(self.store(), entry, "again")
        sd_lane.update(self.store(), lambda rows: rows[0]["holder"].update(host="build-2"))
        released = sd_lane.cancel(self.repo, 1, self.environ)
        self.assertEqual(released["status"], "failed")
        self.assertIn("a merge may have landed", released["reason"])

    def test_an_expired_lease_with_a_live_pid_on_this_host_keeps_the_entry_running(self) -> None:
        """Failure table, prepare: the lease passed while the holder slept; same host, live pid: no reclaim."""
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.claim_entry(self.store(), "sleeper")
        sd_lane.update(self.store(), lambda rows: rows[0].update(lease_until="2020-01-01T00:00:00Z"))
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertNotIn("reclaimed", answer)
        self.assertIn("one entry of a repository runs at a time", answer["stopped"])
        self.assertEqual((self.calls, self.entries()[0]["status"]), ([], "running"))

    def failing_store(self, when: Any) -> Any:
        real = sd_lane.store

        def store(connection: Any, repository: str, entry: dict) -> None:
            if when(entry):
                raise sqlite3.OperationalError("the hub went away")
            real(connection, repository, entry)
        return mock.patch.object(sd_lane, "store", store)

    def test_a_step_write_that_fails_stops_the_runner_and_reclaim_puts_it_back(self) -> None:
        """Failure table, before merge: the hub fails for the whole retry; no merge, and the rerun runs it."""
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        with self.failing_store(lambda entry: entry.get("step") == "merge"):
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertIn("the hub went away", answer["stopped"])
        self.assertEqual(([c[2] for c in self.calls], self.entries()[0]["step"]), (["prepare"], "prepare"))
        self.make_dead()
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual((answer["reclaimed"][0]["status"], self.entries()[0]["status"]), ("pending", "merged"))

    def test_a_runner_write_is_tried_again_until_the_hub_answers(self) -> None:
        """The 10-minute write retry: two faults, then the write lands and the entry merges."""
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        faults = [1, 1]
        with mock.patch.object(sd_lane, "WRITE_RETRY_SECONDS", 600), \
                self.failing_store(lambda entry: entry.get("step") == "merge" and faults and faults.pop()):
            sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual((faults, self.entries()[0]["status"]), ([], "merged"))

    def test_a_finish_write_that_fails_after_a_merge_is_failed_by_reclaim(self) -> None:
        """Failure table, finish: the hub fails after a merge; the run stops, and reclaim fails the entry."""
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        with self.failing_store(lambda entry: entry.get("status") == "merged"):
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual((answer["ran"][0]["recorded"], self.entries()[0]["step"]), (False, "merge"))
        self.make_dead()
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        [entry] = self.entries()
        self.assertEqual(entry["status"], "failed")
        self.assertIn("a merge may have landed", entry["reason"])

    def test_a_late_finish_after_a_reclaim_writes_nothing(self) -> None:
        """Failure table, finish: the token was reclaimed while the holder slept; it reports claim_lost."""
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        entry = sd_lane.claim_entry(self.store(), "sleeper")
        self.make_dead()
        sd_lane.runner_write(self.store(), sd_lane.reclaim_dead)
        before = self.rows()
        with self.assertRaises(sd_lane.Stop) as lost:
            sd_lane.finish_entry(self.store(), entry, "sleeper", {"status": "merged"})
        self.assertEqual((lost.exception.code, self.rows()), (sd_lane.CLAIM_LOST, before))

    def test_a_double_finish_writes_one_outcome_row(self) -> None:
        """Failure table, finish: a retried outcome write finds its own outcome under its token."""
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        entry = sd_lane.claim_entry(self.store(), "mine")
        for _ in range(2):
            sd_lane.finish_entry(self.store(), entry, "mine", {"status": "merged", "merge_commit": "c0ffee"})
        merged = [body for _, body in self.rows() if body["status"] == "merged"]
        self.assertEqual(len(merged), 1)


class Retrying(SharedQueue):
    def imported_blocked(self, tree: pathlib.Path, head: str) -> None:
        """Item 1, failed in a file queue at `head`, imported; `retry` takes it from there."""
        path = sd_lane.queue_path(self.repo, self.environ)
        path.parent.mkdir(parents=True)
        body = path.parent.parent / "bodies" / "1-x.md"
        body.parent.mkdir()
        body.write_text("Item: sd:1\n", encoding="utf-8")
        path.write_text(json.dumps({"entries": [{
            "worktree": str(tree), "item": 1, "expected_head": head, "title": "t", "body_file": str(body),
            "authority": "manual", "claim": "deliver", "acceptance_file": None, "status": "failed",
            "enqueued_at": "2026-10-01T00:00:00Z", "finished_at": "2026-10-01T01:00:00Z"}]}), encoding="utf-8")
        sd_lane.import_file_queue(self.repo, self.store())

    def test_retry_of_an_imported_blocked_entry_publishes_its_head(self) -> None:
        """Failure table, retry: the commit is in this checkout, not on origin; retry publishes it, then queues."""
        tree, [head] = self.committed("topic", "work")
        self.imported_blocked(tree, head)
        self.assertEqual((self.remote_tip("topic"), self.git_verbs), (None, []))  # history is not published
        retried = sd_lane.retry(self.repo, 1, self.environ)
        self.assertEqual((retried["status"], retried["branch"], self.remote_tip("topic")), ("pending", "topic", head))

    def test_retry_after_the_branch_and_worktree_went_refuses_and_writes_no_row(self) -> None:
        """Failure table, retry: the commit is gone here and on origin; `head_gone` names where it was queued."""
        tree, [head] = self.committed("topic", "work")
        self.imported_blocked(tree, head)
        git(self.repo, "worktree", "remove", "--force", str(tree))
        git(self.repo, "branch", "-D", "topic")
        git(self.repo, "reflog", "expire", "--expire=now", "--all")
        git(self.repo, "gc", "-q", "--prune=now")
        before = self.rows()
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.retry(self.repo, 1, self.environ)
        self.assertEqual(refused.exception.code, sd_lane.HEAD_GONE)
        self.assertIn(f"run the retry on {sd_lane.this_host()}", str(refused.exception))
        self.assertEqual((self.rows(), self.entries()[0]["status"]), (before, "failed"))

    def test_a_rerun_after_a_kill_between_the_retry_push_and_its_row_queues_one_entry(self) -> None:
        """Failure table, retry: killed between the push and the row write."""
        tree, [head] = self.committed("topic", "work")
        self.imported_blocked(tree, head)
        with mock.patch.object(sd_lane, "add_entry", side_effect=Killed), self.assertRaises(Killed):
            sd_lane.retry(self.repo, 1, self.environ)
        self.assertEqual(self.remote_tip("topic"), head)
        self.git_verbs.clear()
        sd_lane.retry(self.repo, 1, self.environ)
        self.assertNotIn("push", self.git_verbs)
        self.assertEqual([row["status"] for row in self.entries()], ["failed", "pending"])


class Importing(SharedQueue):
    """The file queue an earlier version left on this host goes into the hub database once."""

    def setUp(self) -> None:
        super().setUp()
        self.file = sd_lane.queue_path(self.repo, self.environ)
        self.bodies = self.file.parent.parent / "bodies"
        self.bodies.mkdir(parents=True)

    def old(self, item: int, tree: pathlib.Path | None, *, status: str = "pending", head: str | None = None,
            body: bool = True, **extra: Any) -> dict:
        """An entry as the file queue held it, with a body copy under `bodies/` unless `body` is False."""
        copy = self.bodies / f"{item}-x.md"
        if body:
            copy.write_text(f"Item: sd:{item}\n", encoding="utf-8")
        return {"worktree": str(tree or self.tmp / "gone"), "item": item, "title": f"t{item}",
                "expected_head": head or git(tree or self.repo, "rev-parse", "HEAD"), "body_file": str(copy),
                "authority": "manual", "claim": "deliver", "acceptance_file": None, "status": status,
                "enqueued_at": f"2026-10-0{item}T00:00:00Z", **extra}

    def write_file(self, *entries: dict) -> bytes:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps({"entries": list(entries)}, indent=2), encoding="utf-8")
        return self.file.read_bytes()

    def imported_files(self) -> list[pathlib.Path]:
        return sorted(self.file.parent.glob("queue.json.imported-*"))

    def import_now(self) -> dict:
        return sd_lane.import_file_queue(self.repo, self.store())

    def statuses(self) -> list[tuple[int, str]]:
        return [(row["item"], row["status"]) for row in self.entries()]

    def test_a_fault_inside_the_transaction_leaves_no_row_and_the_file(self) -> None:
        """Failure table, import: killed mid-transaction; nothing written; the next pass imports."""
        self.write_file(self.old(1, self.repo), self.old(2, self.repo, status="merged"))
        writes = [1, 2]
        real = sd_lane.store

        def second_fails(connection: Any, repository: str, entry: dict) -> None:
            writes.pop(0)
            if not writes:
                raise sqlite3.OperationalError("the hub went away")
            real(connection, repository, entry)
        with mock.patch.object(sd_lane, "store", second_fails), self.assertRaises(sd_lane.LaneError):
            self.import_now()
        self.assertEqual((self.rows(), self.file.exists()), ([], True))
        self.import_now()
        self.assertEqual(self.statuses(), [(1, "pending"), (2, "merged")])

    def test_a_rerun_after_a_kill_before_the_rename_gives_one_row_per_entry(self) -> None:
        """Failure table, import: rows written, killed before the rename; the fixed ids are skipped."""
        self.write_file(self.old(1, self.repo), self.old(2, self.repo, status="failed"))
        with mock.patch.object(pathlib.Path, "rename", side_effect=Killed), self.assertRaises(Killed):
            self.import_now()
        self.assertEqual((len(self.rows()), self.file.exists()), (2, True))
        self.import_now()
        self.assertEqual((len(self.rows()), self.file.exists(), len(self.imported_files())), (2, False, 1))
        self.assertTrue(all(row["id"].startswith("import-") for row in self.entries()))

    def test_leftover_named_bodies_go_and_an_unnamed_body_stays(self) -> None:
        """Failure table, import: killed before the named body files go; the next pass deletes only those."""
        self.write_file(self.old(1, self.repo), self.old(2, self.repo, status="failed"))
        unnamed = self.bodies / "3-y.md"
        unnamed.write_text("an older enqueue's copy\n", encoding="utf-8")
        with mock.patch.object(sd_lane, "drop_imported_bodies", side_effect=Killed), self.assertRaises(Killed):
            self.import_now()
        self.assertEqual(sorted(path.name for path in self.bodies.iterdir()), ["1-x.md", "2-x.md", "3-y.md"])
        self.import_now()
        self.assertEqual([path.name for path in self.bodies.iterdir()], ["3-y.md"])

    def test_a_body_an_older_enqueue_copied_before_its_queue_write_survives_and_imports(self) -> None:
        """Failure table, import: an older `sd-ship` copied a body, then appended a new file after the rename."""
        self.write_file(self.old(1, self.repo))
        late = self.old(2, self.worktree("second"))  # its body copy lands before its queue write
        self.import_now()
        self.assertTrue(pathlib.Path(late["body_file"]).is_file())
        self.write_file(late)  # the old flock ordered it after the import: a new file
        self.import_now()
        self.import_now()  # once
        self.assertEqual(self.statuses(), [(1, "pending"), (2, "pending")])
        self.assertEqual((self.entries()[1]["body"], pathlib.Path(late["body_file"]).exists()), ("Item: sd:2\n", False))
        self.assertEqual(len(self.imported_files()), 2)

    def test_a_failing_import_push_leaves_the_file_and_writes_no_row(self) -> None:
        """Failure table, import publish: a push fails; unknown, so nothing is written and the file stays."""
        tree, [head] = self.committed("topic", "work")
        original = self.write_file(self.old(1, tree, head=head))
        with self.failing("push"):
            report = self.import_now()
        self.assertIn("sd:1", report["stopped"])
        self.assertEqual((self.rows(), self.file.read_bytes()), ([], original))

    def test_a_rerun_after_a_kill_between_import_push_and_write_gives_one_row_per_entry(self) -> None:
        """Failure table, import publish: branches pushed, killed before the transaction."""
        tree, [head] = self.committed("topic", "work")
        self.write_file(self.old(1, tree, head=head), self.old(2, self.repo, status="merged"))
        with mock.patch.object(sd_lane, "update", side_effect=Killed), self.assertRaises(Killed):
            self.import_now()
        self.assertEqual((self.remote_tip("topic"), self.rows()), (head, []))
        self.git_verbs.clear()
        self.import_now()
        self.assertNotIn("push", self.git_verbs)
        self.assertEqual(self.statuses(), [(1, "pending"), (2, "merged")])

    def test_a_pending_entry_behind_its_branch_tip_publishes_its_expected_head(self) -> None:
        """Failure table, import publish: the builder moved the branch after enqueue; origin gets the queued head."""
        tree, [queued, _tip] = self.committed("topic", "queued", "later")
        self.write_file(self.old(1, tree, head=queued))
        self.import_now()
        self.assertEqual((self.remote_tip("topic"), self.entries()[0]["branch"]), (queued, "topic"))

    def test_one_dead_pending_branch_among_live_ones_imports_skipped(self) -> None:
        """Failure table, import publish: a gone commit and a diverged remote are definite; the rest import."""
        gone, _ = self.committed("gone", "work")
        diverged, [head] = self.committed("diverged", "mine")
        git(self.repo, "push", "-q", "origin", "main:refs/heads/diverged")
        git(self.origin, "update-ref", "refs/heads/diverged",
            git(self.origin, "commit-tree", git(self.origin, "rev-parse", "main^{tree}"), "-p", "main", "-m", "theirs"))
        live, [live_head] = self.committed("live", "work")
        self.write_file(self.old(1, gone, head="0" * 40), self.old(2, diverged, head=head),
                        self.old(3, live, head=live_head))
        self.import_now()
        self.assertEqual(self.statuses(), [(1, "skipped"), (2, "skipped"), (3, "pending")])
        self.assertEqual([row.get("code") for row in self.entries()], [sd_lane.HEAD_GONE, sd_lane.BRANCH_DIVERGED, None])
        self.assertEqual((self.file.exists(), self.remote_tip("live")), (False, live_head))

    def test_a_blocked_entry_with_no_branch_or_commit_imports_without_a_push(self) -> None:
        """Failure table, import: a blocked entry's worktree and branch are gone; it is history, not published."""
        tree, [head] = self.committed("topic", "work")
        self.write_file(self.old(1, None, status="failed", head="1" * 40), self.old(2, tree, head=head))
        self.import_now()
        self.assertEqual(self.statuses(), [(1, "failed"), (2, "pending")])
        self.assertEqual((self.git_verbs.count("push"), self.entries()[0]["branch"]), (1, None))

    def test_an_append_after_the_rename_is_imported_once(self) -> None:
        """Failure table, import: an older `sd-ship` enqueues during the import; it lands in a new file."""
        self.write_file(self.old(1, self.repo))
        release = threading.Event()
        locked = threading.Event()

        def older_enqueue() -> None:
            locked.wait(10)
            with sd_lane.queue_lock(self.file):  # waits for the import, as an older `sd-ship` would
                entries = json.loads(self.file.read_text(encoding="utf-8"))["entries"] if self.file.exists() else []
                self.write_file(*entries, self.old(2, self.worktree("second")))
            release.set()
        real = sd_lane.import_locked

        def signalled(root: pathlib.Path, queue: sd_lane.Queue, path: pathlib.Path) -> dict:
            locked.set()
            time.sleep(0.3)
            return real(root, queue, path)
        appender = threading.Thread(target=older_enqueue)
        appender.start()
        with mock.patch.object(sd_lane, "import_locked", signalled):
            self.import_now()
        appender.join(30)
        self.assertTrue(release.is_set())
        self.import_now()
        self.import_now()
        self.assertEqual(self.statuses(), [(1, "pending"), (2, "pending")])

    def test_older_rows_import_by_the_migration_rules(self) -> None:
        """Failure table, import: running, no branch, no body, `handed_back` and a duplicate item, one each."""
        sd_lane.enqueue_entry(self.repo, 6, "queued here", self.body, self.environ, claim="deliver")
        tree = self.worktree("topic")
        self.write_file(
            self.old(1, tree, status="running", runner_pid=4242),
            self.old(2, None),  # pending, no worktree to read a branch from
            self.old(3, None, status="failed"),  # blocked, no branch: kept
            self.old(4, tree, body=False),  # pending, its body is gone
            self.old(5, tree, status="skipped", body=False),  # blocked, no body: kept
            self.old(7, tree, status="handed_back"),
            self.old(6, tree))  # already pending in the shared queue
        self.import_now()
        rows = {row["item"]: row for row in self.entries() if row.get("code") != "duplicate_on_import"}
        self.assertEqual({item: (row["status"], row.get("code")) for item, row in rows.items()},
                         {1: ("failed", None), 2: ("failed", "no_branch"), 3: ("failed", None), 4: ("failed", "no_body"),
                          5: ("skipped", None), 6: ("pending", None), 7: ("handed_back", None)})
        self.assertIn("runner pid 4242 died", rows[1]["reason"])
        duplicate = [row for row in self.entries() if row["item"] == 6 and row["id"].startswith("import-")]
        self.assertEqual([(row["status"], row["code"]) for row in duplicate], [("cancelled", "duplicate_on_import")])
        for item, words in ((3, "lane enqueue"), (5, "--body-file")):
            with self.subTest(item=item), self.assertRaisesRegex(sd_lane.LaneError, words):
                sd_lane.retry(self.repo, item, self.environ)

    def test_the_imported_file_holds_the_original_bytes(self) -> None:
        """Failure table, rollback: an earlier pack finds no queue file; renaming it back restores the queue."""
        original = self.write_file(self.old(1, self.repo), self.old(2, self.repo, status="merged"))
        self.import_now()
        [kept] = self.imported_files()
        self.assertEqual((kept.read_bytes(), self.file.exists()), (original, False))

    def test_a_busy_runner_lock_skips_the_import(self) -> None:
        """An older runner mid-entry holds the lock and keeps its file until the next pass."""
        self.write_file(self.old(1, self.repo))
        self.store().lock_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.store().lock_file, "a", encoding="utf-8") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            report = self.import_now()
        self.assertEqual((report["skipped"][:24], self.rows(), self.file.exists()), ("a runner holds the lock;", [], True))


class HubDown(SharedQueue):
    def test_every_verb_refuses_hub_unavailable_and_writes_nothing(self) -> None:
        """Failure table, hub down: an unreachable hub refuses each lane verb with `hub_unavailable`."""
        import argparse
        tree, _ = self.committed("topic", "work")
        sd_lane.enqueue_entry(self.repo, 1, "one", self.body, self.environ, claim="deliver")
        before = self.rows()
        parser = argparse.ArgumentParser()
        sd_lane.add_lane_verbs(parser.add_subparsers(dest="command"))
        verbs = (["enqueue", "--item", "2", "--title", "t", "--body-file", str(self.body), "--deliver"], ["list"],
                 ["retry", "1"], ["cancel", "1"], ["move", "1", "top"], ["hold", "1"], ["release", "1"], ["run"])
        for argv in verbs:
            with self.subTest(verb=argv[0]), contextlib.chdir(tree), mock.patch.dict(os.environ, self.environ), \
                    mock.patch("sd_db.database.connect", side_effect=OSError(61, "Connection refused")), \
                    contextlib.redirect_stdout(io.StringIO()) as said:
                code = sd_lane.lane_main(parser.parse_args(["lane", *argv]))
                answer = json.loads(said.getvalue())
            self.assertEqual((code, answer.get("code")), (3, sd_lane.HUB_UNAVAILABLE), answer)
        self.assertEqual(self.rows(), before)


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
