"""`sd-ship lane` (sd:2524): a serial ship queue per repository that outlives its session.

The acceptance test is the first: an entry one process enqueued is there for
the next process to read. The runner tests replace `sd-ship` with a recorder,
so nothing reaches GitHub or a review.
"""

from __future__ import annotations

import calendar
import contextlib
import fcntl
import importlib.util
import io
import json
import os
import pathlib
import signal
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

from tests.clean_env import clean_environment  # noqa: E402


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


#: An `sd-ship` that prints `sd_ship_workflow.failure` of prepare's incomplete-review `Refusal`, as `main` does,
#: and passes `--retry-review` (sd:3482).
FAKE_PREPARE = """import json, sys
sys.path.insert(0, {bin!r})
from sd_ship_remote import Refusal
from sd_ship_workflow import failure
if "--retry-review" in sys.argv:
    print(json.dumps({{"ok": True, "phase": "ready_to_send", "head": "head-1"}}))
    raise SystemExit(0)
refused = Refusal("the preceding review did not complete its requested depth; use --retry-review for a "
                  "full-branch retry", code="review_incomplete", boundary="review", state="operator_decision",
                  next_action="Prepare again with --retry-review; it spends one automatic pass.")
print(json.dumps(failure("prepare", refused), indent=2, sort_keys=True))
raise SystemExit(3)
"""


class Lane(unittest.TestCase):
    #: `repo.runner_merge` for a suite with no database (sd:3132); None reads the suite's own database.
    runner_merge: str | None = "manual"
    #: Whether enqueue and retry read the item in the suite's database (sd:3473); most suites queue items it lacks.
    checks_item = False

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
        # The lane publishes and prepares a feature branch only; `self.repo` stays the main checkout on main.
        self.feature = self.worktree("feature")
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
        self.note_kinds: list[str] = []
        patcher = mock.patch.object(sd_lane, "default_note", self.note)
        patcher.start()
        self.addCleanup(patcher.stop)
        if self.runner_merge is not None:
            patcher = mock.patch.object(sd_lane, "default_runner_merge", lambda root: self.runner_merge)
            patcher.start()
            self.addCleanup(patcher.stop)
        if not self.checks_item:
            patcher = mock.patch.object(sd_lane, "check_item", lambda *args: None)
            patcher.start()
            self.addCleanup(patcher.stop)
        # And each runs as the hub would, which hosts every lane whose `repo.lane_host` is NULL (sd:3003).
        if importlib.util.find_spec("sd_db") is not None:
            patcher = mock.patch("sd_db.database.served_by", lambda target, home=None: None, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def register_items(self, count: int, remote: str = "https://github.com/example/pack.git") -> list[int]:
        """This checkout as a repository with `remote`, and `count` items of it, as prepare reads them (sd:3473)."""
        import sd_db
        connection = sd_db.connect(home=self.tmp)
        try:
            sd_db.upsert_repo(connection, str(self.repo), remote=remote, managed=1)
            return [sd_db.create_item(connection, kind="task", title=f"item {number}", status="in_progress",
                                      repo=str(self.repo)) for number in range(count)]
        finally:
            connection.close()

    def note(self, item: int, body: str, main: pathlib.Path, kind: str = "comment") -> str:
        self.notes.append((item, body, main))
        self.note_kinds.append(kind)
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
    checks_item = True  # the verbs run in a child process, which no patch here reaches

    def setUp(self) -> None:
        super().setUp()
        self.register_items(7)

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
        sd_lane.enqueue_entry(self.feature, 7, "Topic", self.body, self.environ, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        done = self.sd_ship(self.repo, "retry", "7", "--manual")
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        answer = json.loads(done.stdout)
        self.assertEqual((answer["ok"], answer["item"], answer["authority"], answer["status"]), (True, 7, "manual", "pending"))
        again = self.sd_ship(self.repo, "retry", "7")
        self.assertEqual((again.returncode, json.loads(again.stdout)["ok"]), (3, False))

    def test_retry_expected_head_refuses_another_head_and_names_both(self) -> None:
        """sd:3268. The Queue page sends the head it showed; another blocked head is refused with `stale_head`."""
        sd_lane.enqueue_entry(self.feature, 7, "Topic", self.body, self.environ, claim="deliver")
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

    def test_retry_takes_a_cancelled_entry_and_its_help_says_so(self) -> None:
        """sd:3389. The system Queue page re-queues a cancelled row; it reads `cancelled` in the help to offer it."""
        sd_lane.enqueue_entry(self.feature, 7, "Topic", self.body, self.environ, claim="deliver")
        sd_lane.cancel(self.repo, 7, self.environ)
        head = self.entries()[0]["expected_head"]
        done = self.sd_ship(self.repo, "retry", "7", "--expected-head", head)
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        self.assertEqual((json.loads(done.stdout)["status"], json.loads(done.stdout)["retried"]["status"]),
                         ("pending", "cancelled"))
        helped = self.sd_ship(self.repo, "retry", "--help")
        self.assertIn("cancelled", " ".join(helped.stdout.split()))

    def test_an_entry_without_a_delivery_claim_is_refused_with_exit_3(self) -> None:
        done = self.sd_ship(self.feature, "enqueue", "--item", "7", "--title", "Topic", "--body-file", str(self.body))
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
        sd_lane.enqueue_entry(self.feature, 3, "t", self.body, self.environ, claim="deliver")
        with self.assertRaisesRegex(sd_lane.LaneError, "already queued"):
            sd_lane.enqueue_entry(self.feature, 3, "t", self.body, self.environ, claim="deliver")

    def test_a_cancelled_entry_is_not_run(self) -> None:
        sd_lane.enqueue_entry(self.feature, 3, "t", self.body, self.environ, claim="deliver")
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
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
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
        sd_lane.enqueue_entry(self.feature, 1, "t", self.body, self.environ, claim="deliver", acceptance_file=acceptance)
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
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
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
        git(self.repo, "push", "-q", "origin", "main")  # prepare merges `origin/<default>`

        def catch_up_then_block(argv: list[str], log: pathlib.Path) -> dict:
            git(tree, "merge", "-q", "--no-ff", "-m", "Merge origin/main", "main")
            self.ship(argv, log)
            return {"ok": False, "phase": "review_blocked", "error": "a blocking finding"}
        sd_lane.run_lane(self.repo, self.environ, catch_up_then_block)
        self.assertEqual(sd_lane.retry(self.repo, 1, self.environ)["expected_head"], git(tree, "rev-parse", "HEAD"))

    def test_retry_refuses_what_it_cannot_retry(self) -> None:
        with self.assertRaisesRegex(sd_lane.LaneError, "no entry"):
            sd_lane.retry(self.repo, 1, self.environ)
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        with self.assertRaisesRegex(sd_lane.LaneError, "already queued"):
            sd_lane.retry(self.repo, 1, self.environ)
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        with self.assertRaisesRegex(sd_lane.LaneError, "last entry is merged"):
            sd_lane.retry(self.repo, 1, self.environ)
        sd_lane.enqueue_entry(self.feature, 2, "two", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.cancel(self.repo, 2, self.environ)
        with self.assertRaisesRegex(sd_lane.LaneError, "cancelled.*--expected-head"):
            sd_lane.retry(self.repo, 2, self.environ)
        # An entry that ended before its copy was kept has none to queue again.
        sd_lane.enqueue_entry(self.feature, 3, "three", self.body, self.environ, manual=True, claim="deliver")
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

    def moved_above(self, item: int) -> tuple[str, str]:
        """`item` fails at one head, then again at a newer one that `move top` put above it; both heads."""
        tree = self.worktree(f"topic{item}")
        heads = []
        for message in ("first", "second"):
            git(tree, "commit", "-q", "--allow-empty", "-m", message)
            heads.append(git(tree, "rev-parse", "HEAD"))
            sd_lane.enqueue_entry(tree, item, "t", self.body, self.environ, claim="deliver")
            if message == "second":
                sd_lane.move(self.repo, item, "top", self.environ)
            self.answers[(item, "prepare")] = {"ok": False, "error": f"{message} failure"}
            sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([row["expected_head"] for row in self.entries() if row["item"] == item], heads[::-1])
        return heads[0], heads[1]

    def test_retry_takes_the_newest_entry_when_a_move_put_it_above_older_ones(self) -> None:
        """sd:3412. After a hold and `move top`, the newest entry sits above an older finished one."""
        sd_lane.enqueue_entry(self.feature, 1, "held", self.body, self.environ, claim="deliver")
        sd_lane.set_hold(self.repo, 1, self.environ, held=True)
        old, new = self.moved_above(2)
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.retry(self.repo, 2, self.environ, expected_head=old)
        self.assertEqual(refused.exception.code, sd_lane.STALE_HEAD)
        self.assertEqual(sd_lane.retry(self.repo, 2, self.environ, expected_head=new)["expected_head"], new)
        _, new = self.moved_above(3)
        self.assertEqual(sd_lane.retry(self.repo, 3, self.environ)["expected_head"], new)

    def test_a_cancel_records_who_cancelled_it(self) -> None:
        """sd:3483. Thirteen cancelled entries carried an empty reason, while a release says who released it."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
        sd_lane.cancel(self.repo, 1, self.environ)
        self.assertEqual(self.entries()[0]["reason"], f"cancelled by the operator on {sd_lane.this_host()}")

    def test_lane_list_gives_each_entry_its_enqueue_order(self) -> None:
        """sd:3419. A reader of `lane list` takes an item's newest entry by `enqueue_seq`, not by its place after a move."""
        import argparse  # noqa: PLC0415
        sd_lane.enqueue_entry(self.feature, 1, "held", self.body, self.environ, claim="deliver")
        sd_lane.set_hold(self.repo, 1, self.environ, held=True)
        _, new = self.moved_above(2)
        parser = argparse.ArgumentParser()
        sd_lane.add_lane_verbs(parser.add_subparsers(dest="command"))
        with contextlib.chdir(self.repo), mock.patch.dict(os.environ, self.environ), \
                contextlib.redirect_stdout(io.StringIO()) as said:
            self.assertEqual(sd_lane.lane_main(parser.parse_args(["lane", "list"])), 0)
        listed = json.loads(said.getvalue())["entries"]
        self.assertTrue(all(type(row.get("enqueue_seq")) is int for row in listed), listed)
        self.assertEqual([row["item"] for row in sorted(listed, key=lambda row: row["enqueue_seq"])], [1, 2, 2])
        # sd:3483: each entry's round among its item's entries, so three blocking rounds need no counting by hand.
        self.assertEqual([(row["item"], row.get("round")) for row in sorted(listed, key=lambda row: row["enqueue_seq"])],
                         [(1, 1), (2, 1), (2, 2)])
        newest = max((row for row in listed if row["item"] == 2), key=lambda row: row["enqueue_seq"])
        self.assertEqual(newest["expected_head"], new)
        self.assertNotEqual([row for row in listed if row["item"] == 2][-1]["expected_head"], new)

    def test_retry_refuses_a_newer_entry_written_between_its_read_and_its_write(self) -> None:
        """sd:3412. With no expected head, the write still finds the entry it read is no longer the item's newest."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
        self.answers[(1, "prepare")] = {"ok": False, "error": "a failure"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        real = sd_lane.require_published

        def another_entry_ends_first(*args: Any) -> None:
            real(*args)
            sd_lane.update(self.store(), lambda rows: rows.insert(
                0, {**rows[0], "id": "later", "position": 0, "status": "skipped"}))
        with mock.patch.object(sd_lane, "require_published", another_entry_ends_first):
            with self.assertRaises(sd_lane.LaneError) as refused:
                sd_lane.retry(self.repo, 1, self.environ)
        self.assertEqual(refused.exception.code, sd_lane.SUPERSEDED)
        self.assertEqual([row["status"] for row in self.entries()], ["skipped", "failed"])

    def test_a_queue_write_that_fails_changes_nothing_and_says_hub_unavailable(self) -> None:
        """sd:3282: a write is one hub transaction; a fault in it leaves the entry as it was."""
        sd_lane.enqueue_entry(self.feature, 1, "t", self.body, self.environ, manual=True, claim="deliver")
        with mock.patch.object(sd_lane, "store", side_effect=sqlite3.OperationalError("disk I/O error")):
            with self.assertRaises(sd_lane.LaneError) as refused:
                sd_lane.cancel(self.repo, 1, self.environ)
        self.assertEqual((refused.exception.code, self.entries()[0]["status"]), (sd_lane.HUB_UNAVAILABLE, "pending"))

    def test_an_associate_only_entry_prepares_with_associate_only(self) -> None:
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="associate-only")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertIn("--associate-only", self.calls[0])
        self.assertNotIn("--deliver", self.calls[0])

    def test_an_acceptance_file_is_forwarded_to_prepare(self) -> None:
        acceptance = self.tmp / "acceptance.json"
        acceptance.write_text("{}", encoding="utf-8")
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver", acceptance_file=acceptance)
        acceptance.unlink()  # the entry holds the text (sd:3282)
        read: list[str] = []

        def ship(argv: list[str], log: pathlib.Path) -> dict:
            if argv[2] == "prepare":
                read.append(pathlib.Path(argv[argv.index("--acceptance-file") + 1]).read_text(encoding="utf-8"))
            return self.ship(argv, log)
        sd_lane.run_lane(self.repo, self.environ, ship)
        self.assertEqual((read, "--deliver" in self.calls[0]), (["{}"], True))

    def test_each_item_the_enqueue_names_reaches_prepare(self) -> None:
        """sd:3704: the enqueue's --item list is the closing set; prepare gets every one, the claimed item first."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver", closes=(2, 3, 1, 2))
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        items = [self.calls[0][index + 1] for index, part in enumerate(self.calls[0]) if part == "--item"]
        self.assertEqual(items, ["1", "2", "3"])

    def test_prepare_catches_up_with_the_base_inside_the_runner(self) -> None:
        """The catch-up merge runs under the lane lock, never before it."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertIn("--catch-up", self.calls[0])

    def test_the_merge_names_the_prepared_head(self) -> None:
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        merge = self.calls[1]
        self.assertEqual((merge[merge.index("--expected-head") + 1], "--manual" in merge), ("head-1", True))

    def test_without_manual_authority_the_runner_stops_at_a_prepared_head(self) -> None:
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
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
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.incomplete_review(retried=False))
        self.assertEqual([(c[2], "--retry-review" in c) for c in self.calls],
                         [("prepare", False), ("prepare", True), ("merge", False)])
        self.assertEqual(self.entries()[0]["status"], "merged")

    def test_sd_ships_own_review_incomplete_refusal_reaches_the_retry(self) -> None:
        """sd:3482. Two entries kept this refusal with no -retry.log; sd-ship's real refusal, printed, still retries.

        The fake `sd-ship` prints what `sd_ship_workflow.failure` makes of the
        `Refusal` prepare raises, exits 3 as `sd-ship` does, and runs under
        the runner's own `default_ship`.
        """
        fake = self.tmp / "fake-bin"
        fake.mkdir()
        (fake / "sd-ship").write_text(FAKE_PREPARE.format(bin=str(REPO_ROOT / "bin")), encoding="utf-8")
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
        with mock.patch.object(sd_lane, "BIN", fake), mock.patch.dict(os.environ, self.environ):
            sd_lane.run_lane(self.repo, self.environ)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry["head"]), ("prepared", "head-1"), entry.get("reason"))
        self.assertTrue(entry["prepare_log"].endswith("-retry.log"), entry["prepare_log"])
        self.assertIn("--retry-review", pathlib.Path(entry["prepare_log"]).read_text(encoding="utf-8"))

    def test_a_prepare_that_reconciles_a_landed_merge_records_it_merged(self) -> None:
        """sd:3482. A retry after a death at merge: prepare answered `merged`, and the entry failed 'not ready'."""
        head = sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")["expected_head"]
        self.answers[(1, "prepare")] = {"ok": True, "phase": "merged", "head": head, "merge_commit": "landed-1"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry.get("merge_commit"), entry.get("reconciled")),
                         ("merged", "landed-1", True), entry.get("reason"))
        self.assertEqual([c[2] for c in self.calls], ["prepare"])  # no second merge
        self.assertIn("Landed: merged at landed-1", self.notes[0][1])

    def caught_up_topic(self) -> tuple[pathlib.Path, str, str]:
        """A worktree whose branch has a commit, then prepare's catch-up merge of a moved `origin/main` on it."""
        tree = self.worktree("topic")
        git(tree, "commit", "-q", "--allow-empty", "-m", "work")
        work = git(tree, "rev-parse", "HEAD")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "base moved")
        git(self.repo, "push", "-q", "origin", "main")
        git(tree, "merge", "-q", "--no-ff", "-m", "Merge origin/main", "main")
        return tree, work, git(tree, "rev-parse", "HEAD")

    def test_a_reconciled_merge_of_the_entrys_catch_up_records_it_merged(self) -> None:
        """sd:3482: the merge that landed was of prepare's catch-up of the queued head."""
        tree, work, caught = self.caught_up_topic()
        git(tree, "reset", "-q", "--hard", work)
        sd_lane.enqueue_entry(tree, 1, "one", self.body, self.environ, claim="deliver")
        git(tree, "reset", "-q", "--hard", caught)
        self.answers[(1, "prepare")] = {"ok": True, "phase": "merged", "head": caught, "merge_commit": "landed-1"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual(self.entries()[0]["status"], "merged", self.entries()[0].get("reason"))

    def test_a_reconciled_merge_of_an_earlier_head_is_not_a_catch_up_of_it(self) -> None:
        """Codex round 1: the queued head is a catch-up of the merged one; that merge is not this entry's."""
        tree, work, caught = self.caught_up_topic()
        sd_lane.enqueue_entry(tree, 1, "one", self.body, self.environ, claim="deliver")
        self.answers[(1, "prepare")] = {"ok": True, "phase": "merged", "head": work, "merge_commit": "landed-0"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], self.notes), ("failed", []))
        self.assertIn(f"merge of {work}, not this entry's head {caught}", entry["reason"])

    def test_a_reconciled_merge_whose_claim_was_released_lands_nothing(self) -> None:
        """Codex round 1: the claim must still hold before the landing deletes the branch and notes the item."""
        head = sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")["expected_head"]

        def released_meanwhile(argv: list[str], log: pathlib.Path) -> dict:
            sd_lane.update(self.store(), lambda rows: rows[0]["holder"].update(token="released"))
            self.ship(argv, log)
            return {"ok": True, "phase": "merged", "head": head, "merge_commit": "landed-1"}
        answer = sd_lane.run_lane(self.repo, self.environ, released_meanwhile)
        self.assertEqual((self.notes, self.entries()[0]["status"]), ([], "running"))
        self.assertIn("reclaimed or released", answer["stopped"])

    def test_a_reconciled_merge_of_another_head_is_not_this_entrys(self) -> None:
        """sd:3482, evidence: the receipt's merge must be of the entry's head; an earlier pull request's is not."""
        tree = self.worktree("topic")
        git(tree, "commit", "-q", "--allow-empty", "-m", "follow-up")
        sd_lane.enqueue_entry(tree, 1, "one", self.body, self.environ, claim="deliver")
        earlier = git(self.repo, "rev-parse", "main")
        self.answers[(1, "prepare")] = {"ok": True, "phase": "merged", "head": earlier, "merge_commit": "landed-0"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry.get("merge_commit"), self.notes), ("failed", None, []))
        self.assertIn(f"merge of {earlier}, not this entry's head", entry["reason"])

    def test_the_lane_retries_an_incomplete_review_only_once(self) -> None:
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.incomplete_review(retried=True))
        self.assertEqual([(c[2], "--retry-review" in c) for c in self.calls], [("prepare", False), ("prepare", True)])
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry["step"]), ("failed", "prepare"))
        self.assertIn("did not complete", entry["reason"])

    #: `sd-ship`'s answer when the hub dropped its session or refused its build (sd:3239).
    HUB_FAULT = {"ok": False, "phase": "prepare", "error": "the sd hub at hub.example.test:8769 is unreachable: "
                 "[Errno 32] Broken pipe", "workflow": {"blocker": {"code": "hub_unavailable", "retryable": True}}}

    #: `sd-ship`'s answer to a prepare whose review planning failed before it reserved a pass (sd:3478).
    NO_PLAN = {"ok": False, "phase": "prepare", "passes_spent": 0,
               "error": "local review emitted no valid timing plan; no provider pass was reserved",
               "workflow": {"blocker": {"code": "timing_plan_invalid", "retryable": True}}}

    def test_a_retryable_refusal_that_spent_no_pass_is_put_back_and_the_next_run_ships_it(self) -> None:
        """sd:3478. Five entries failed on this refusal in 10 to 13 s each; seven retries by hand shipped them."""
        sd_lane.enqueue_entry(self.worktree("topic"), 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.enqueue_entry(self.worktree("second"), 2, "two", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(1, "prepare")] = self.NO_PLAN
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([(c[2], c[4]) for c in self.calls], [("prepare", "1")])
        self.assertIn("sd:1", answer["stopped"])
        one, two = self.entries()
        self.assertEqual((one["status"], one["retryable_retries"], one["retryable_fault"]["step"], two["status"]),
                         ("pending", 1, "prepare", "pending"))
        self.assertIn("timing plan", one["retryable_fault"]["reason"])
        self.assertNotIn("hub_retries", one)
        del self.answers[(1, "prepare")]
        self.calls.clear()
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([(c[2], c[4]) for c in self.calls],
                         [("prepare", "1"), ("merge", "1"), ("prepare", "2"), ("merge", "2")])
        self.assertEqual([entry["status"] for entry in self.entries()], ["merged", "merged"])

    def test_a_retryable_refusal_fails_the_entry_on_its_second_time(self) -> None:
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(1, "prepare")] = self.NO_PLAN
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry["step"], entry["retryable_retries"], len(self.calls)),
                         ("failed", "prepare", sd_lane.RETRYABLE_RETRIES, sd_lane.RETRYABLE_RETRIES + 1))
        self.assertIn("timing plan", entry["reason"])

    def test_a_refusal_that_spent_a_pass_or_does_not_say_or_is_not_retryable_fails_at_once(self) -> None:
        """sd:3478. An unknown spend is not "none"; a failed gate is not run again unasked."""
        blocker = self.NO_PLAN["workflow"]["blocker"]
        cases = {"spent": {"passes_spent": 1}, "unsaid": {"passes_spent": None}, "true": {"passes_spent": True},
                 "text": {"passes_spent": "0"},
                 "not retryable": {"workflow": {"blocker": {**blocker, "retryable": False}}},
                 "gate": {"workflow": {"blocker": {**blocker, "code": "gate_failed"}}}}
        for item, (case, change) in enumerate(cases.items(), start=1):
            with self.subTest(case=case):
                answer = {key: value for key, value in {**self.NO_PLAN, **change}.items() if value is not None}
                sd_lane.enqueue_entry(self.feature, item, "one", self.body, self.environ, manual=True, claim="deliver")
                self.answers[(item, "prepare")] = answer
                self.calls.clear()
                sd_lane.run_lane(self.repo, self.environ, self.ship)
                entry = self.entries()[-1]
                self.assertEqual((entry["status"], "retryable_retries" in entry, len(self.calls)), ("failed", False, 1))

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

    def test_a_failed_entry_keeps_the_failing_test_its_refusal_names(self) -> None:
        """sd:3476. The reason was cut at 600 characters, before the gate refusal's failing lines."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        error = ("the repository gate failed after the review cleared: sd-check fail (check fail: suite leg-shared)\n"
                 "check (exit 2): whole output: " + "/tmp/" + "o" * 700 + ".log\nfailing: FAIL: test_sd3476_marker")
        self.answers[(1, "prepare")] = {"ok": False, "phase": "reviewed", "error": error}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual(entry["status"], "failed")
        self.assertIn("failing: FAIL: test_sd3476_marker", entry["reason"])

    def test_a_database_older_than_the_library_stops_the_run_and_fails_nothing(self) -> None:
        """sd:3475. On 2026-10-10 a pack landing built the library for schema 25 over a database at 24,
        and the runner failed four entries in turn, each in no time, before anyone migrated."""
        from sd_db.errors import SchemaTooOld
        sd_lane.enqueue_entry(self.worktree("topic"), 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.enqueue_entry(self.worktree("second"), 2, "two", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(1, "prepare")] = sd_lane.sd_ship_workflow.failure("prepare", SchemaTooOld(24, 25))
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([(c[2], c[4]) for c in self.calls], [("prepare", "1")])
        self.assertIn("sd:1", answer["stopped"])
        one, two = self.entries()
        self.assertEqual((one["status"], one["hub_retries"], two["status"]), ("pending", 1, "pending"))
        self.assertIn("migrate", one["hub_fault"]["reason"])

    def test_a_hub_fault_in_the_merge_is_retried_too(self) -> None:
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(1, "merge")] = {**self.HUB_FAULT, "phase": "merge"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry["hub_fault"]["step"], entry["hub_retries"]), ("pending", "merge", 1))
        del self.answers[(1, "merge")]
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual((self.entries()[0]["status"], [c[2] for c in self.calls]),
                         ("merged", ["prepare", "merge", "prepare", "merge"]))

    def test_the_retry_starts_from_prepares_catch_up_merge_and_not_from_a_builder_commit(self) -> None:
        """The catch-up moved HEAD past the queued head; a commit of the builder's still skips the entry.

        Failure table, put-back (sd:3283): the catch-up is only in the worktree, so `expected_head` stays at
        the published head, and this host's worktree rule accepts the catch-up. Pushed, the entry moves to it.
        A retryable refusal's put-back takes the same path (sd:3478).
        """
        for builder, pushed, fault in ((False, False, "hub"), (True, False, "hub"), (False, True, "hub"),
                                       (False, False, "retryable"), (False, True, "retryable")):
            with self.subTest(builder=builder, pushed=pushed, fault=fault):
                name = f"topic-{builder}-{pushed}-{fault}"
                tree = self.worktree(name)
                queued = sd_lane.enqueue_entry(tree, 1, "one", self.body, self.environ, manual=True,
                                               claim="deliver")["expected_head"]
                git(self.repo, "commit", "-q", "--allow-empty", "-m", "base moved")
                git(self.repo, "push", "-q", "origin", "main")  # prepare merges `origin/<default>`

                def catch_up_then_fault(argv: list[str], log: pathlib.Path, tree: pathlib.Path = tree,
                                        name: str = name, pushed: bool = pushed, fault: str = fault) -> dict:
                    git(tree, "merge", "-q", "--no-ff", "-m", "Merge origin/main", "main")
                    if pushed:
                        git(tree, "push", "-q", "origin", f"HEAD:refs/heads/{name}")
                    self.ship(argv, log)
                    return self.HUB_FAULT if fault == "hub" else self.NO_PLAN
                sd_lane.run_lane(self.repo, self.environ, catch_up_then_fault)
                caught_up = git(tree, "rev-parse", "HEAD")
                self.assertEqual((self.entries()[-1]["status"], self.entries()[-1]["expected_head"]),
                                 ("pending", caught_up if pushed else queued))
                if builder:
                    git(tree, "commit", "-q", "--allow-empty", "-m", "the builder's")
                sd_lane.run_lane(self.repo, self.environ, self.ship)
                self.assertEqual(self.entries()[-1]["status"], "skipped" if builder else "merged")

    def test_a_hub_that_keeps_failing_fails_the_entry_after_its_retries(self) -> None:
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
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
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        log = pathlib.Path(self.entries()[0]["prepare_log"])
        self.assertEqual(log.read_text(encoding="utf-8"), "whole output " * 1000)
        self.assertEqual(log.parent, self.root / "pack/lane/logs")

    def test_a_second_runner_exits_at_once_instead_of_waiting(self) -> None:
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
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
            sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
            lock = sd_lane.queue_path(self.repo, self.environ).parent / "runner.lock"
            self.assertFalse(lock.exists(), "the lane already had a runner lock for the scan to find")
            started = time.monotonic()
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertLess(time.monotonic() - started, 5)
        self.assertIn("the tools this lane runs are moving", answer.get("busy", ""))
        self.assertEqual((self.calls, self.entries()[0]["status"]), ([], "pending"))
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual(([call[4] for call in self.calls], self.entries()[0]["status"]), (["1"], "prepared"))

    def test_a_run_past_its_budget_starts_no_new_entry_and_leaves_the_rest_pending(self) -> None:
        """sd:3287: the job limit TERMed a runner mid `make check`; an entry started in budget still finishes."""
        for item in (1, 2, 3):
            sd_lane.enqueue_entry(self.worktree(f"b{item}"), item, str(item), self.body, self.environ, claim="deliver")
        now = [0.0]

        def slow(argv: list[str], log: pathlib.Path) -> dict:
            now[0] += 30 * 60  # one entry on a busy lane
            return self.ship(argv, log)

        with mock.patch.object(sd_lane, "clock", lambda: now[0]):
            answer = sd_lane.run_lane(self.repo, self.environ, slow)
            self.assertEqual([call[4] for call in self.calls], ["1", "2"])
            self.assertEqual([row["status"] for row in self.entries()], ["prepared", "prepared", "pending"])
            self.assertIn("budget", answer["stopped"])
            spent = sd_lane.run_lane(self.repo, self.environ, slow, deadline=now[0])
        self.assertEqual((spent["ran"], len(self.calls)), ([], 2), "a hosted run's later lane started an entry")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([row["status"] for row in self.entries()], ["prepared"] * 3)

    def test_a_claim_leases_one_prepare_and_renews_it_before_the_retry(self) -> None:
        """sd:3481. A claim leased two prepares, 14 hours, so a dead satellite runner held its lane most of a day."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
        leases: list[float] = []

        def incomplete_once(argv: list[str], log: pathlib.Path) -> dict:
            [row] = self.entries()
            leases.append(calendar.timegm(time.strptime(row["lease_until"], "%Y-%m-%dT%H:%M:%SZ")) - time.time())
            sd_lane.update(self.store(), lambda rows: rows[0].update(lease_until="2020-01-01T00:00:00Z"))
            self.ship(argv, log)
            if "--retry-review" in argv:
                return {"ok": True, "phase": "ready_to_send", "head": "head-1"}
            return {"ok": False, "error": "incomplete", "workflow": {"blocker": {"code": "review_incomplete"}}}
        sd_lane.run_lane(self.repo, self.environ, incomplete_once)
        self.assertEqual(len(leases), 2)
        for lease in leases:  # the retry's prepare runs under a renewed lease, not the old one
            self.assertGreater(lease, sd_lane.sd_lib.GATE_SLOT_SECONDS)
            self.assertLess(lease, 8 * 3600)

    def test_a_claim_released_before_the_retry_starts_no_second_prepare(self) -> None:
        """sd:3481, the renew step: a claim lost before the --retry-review prepare stops the run there."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")

        def released_then_incomplete(argv: list[str], log: pathlib.Path) -> dict:
            sd_lane.update(self.store(), lambda rows: rows[0]["holder"].update(token="released"))
            self.ship(argv, log)
            return {"ok": False, "error": "incomplete", "workflow": {"blocker": {"code": "review_incomplete"}}}
        answer = sd_lane.run_lane(self.repo, self.environ, released_then_incomplete)
        self.assertEqual([("--retry-review" in call) for call in self.calls], [False])
        self.assertIn("reclaimed or released", answer["stopped"])

    def test_a_loaded_machine_claims_no_entry_until_load5_falls_below_the_gate_limit(self) -> None:
        """sd:3479. Six gates timed out at one hour under load, and a retry ran the same gate under the same load."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
        environ = {**self.environ, "SD_GATE_LOAD_MAX": "8"}
        with mock.patch.object(sd_lane.os, "getloadavg", lambda: (2.0, 9.5, 9.0)):
            answer = sd_lane.run_lane(self.repo, environ, self.ship)
        self.assertEqual((self.calls, [row["status"] for row in self.entries()]), ([], ["pending"]))
        self.assertIn("load5 9.5 is at or above 8", answer["stopped"])
        with mock.patch.object(sd_lane.os, "getloadavg", side_effect=OSError("no load")):
            answer = sd_lane.run_lane(self.repo, environ, self.ship)
        self.assertEqual((self.calls, answer["stopped"]), ([], "cannot read the load average (no load); "
                                                                 "the next run takes the pending entries"))
        with mock.patch.object(sd_lane.os, "getloadavg", lambda: (9.0, 7.9, 9.0)):
            sd_lane.run_lane(self.repo, environ, self.ship)
        self.assertEqual([row["status"] for row in self.entries()], ["prepared"])

    def test_no_gate_load_limit_claims_whatever_the_load(self) -> None:
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
        with mock.patch.object(sd_lane.os, "getloadavg", lambda: (99.0, 99.0, 99.0)):
            sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([row["status"] for row in self.entries()], ["prepared"])

    def left_running(self, pid: int | None, step: str = "prepare") -> None:
        """Item 1 claimed by the runner `pid` and never finished, as a killed runner leaves it (sd:2821)."""
        if not self.entries():
            sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")

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
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")  # no longer refused

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
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
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
            "enqueued_at": sd_lane.stamp_now(), "enqueued_on": sd_lane.this_host()}))
        sd_lane.enqueue_entry(self.second, 2, "two", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, super().ship, lambda root, head, base: {"status": "success"})
        self.assertEqual([(entry["item"], entry["status"]) for entry in self.entries()], [(1, "skipped"), (2, "merged")])
        self.assertEqual([call[call.index("--item") + 1] for call in self.calls], ["2", "2"])

    def test_a_stopped_run_cancels_its_speculative_gate_and_frees_its_lock(self) -> None:
        """sd:3361. A run that stopped on a build refusal waited in an unbounded join for the
        speculative gate's `sd-check` child, and held its runner lock the whole time. The stop
        now ends the gate's process group and waits a bounded time for it."""
        import sd_db.database
        from sd_db import remote
        self.queue_both()
        marker = self.tmp / "gate-child.pid"
        refusing: list[bool] = []
        connect = sd_db.database.connect

        def hub(*args: Any, **kwargs: Any) -> Any:
            if refusing:
                raise remote.BuildMismatch("build", "0000aaaa", "1111bbbb")
            return connect(*args, **kwargs)

        def endless(root: pathlib.Path, head: str, base: str) -> dict:
            """A gate whose child would outlive the run by far, run as the real gate runs its `sd-check`."""
            child = f"import os, pathlib, time; pathlib.Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(60)"
            code, _, _ = sd_lane.gate_run()([sys.executable, "-c", child], dict(os.environ), root, 120)
            return {"status": "failure", "summary": f"exit {code}"}

        def prepare_then_upgrade(argv: list[str], log: pathlib.Path) -> dict:
            for _ in range(200):  # the gate's child is running before the run stops
                if marker.exists() and marker.read_text():
                    break
                time.sleep(0.05)
            self.ship(argv, log)
            refusing.append(True)
            return Runner.HUB_FAULT

        started = time.monotonic()
        with mock.patch.object(sd_lane, "WRITE_RETRY_SECONDS", 600), mock.patch.object(sd_lane, "WRITE_PAUSE", 30), \
                mock.patch("sd_db.database.connect", hub):
            answer = sd_lane.run_lane(self.repo, self.environ, prepare_then_upgrade, endless)
        self.assertLess(time.monotonic() - started, 30)
        self.assertIn("BuildMismatch", answer["stopped"])
        self.assertEqual(answer["speculative_gate"], "cancelled")
        with open(self.store().lock_file, "a", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)  # free for `follow`
        with self.assertRaises(ProcessLookupError):
            os.kill(int(marker.read_text()), 0)


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
                               f"worktree {tree} and branch topic kept on {sd_lane.this_host()} for removal once the builder stops. "
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
        git(self.repo, "switch", "-q", "-c", "side")  # the lane refuses an entry on the default branch
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

    def test_a_branch_checkout_that_deploys_by_post_merge_is_not_moved(self) -> None:
        # REGRESSION sd:3647 review: the lane moved the code, then post-merge refused the install,
        # leaving new code on old dependencies; the refusal must come before the move.
        tree, head = self.topic()
        (self.repo / "Makefile").write_text("post-merge:\n\ttrue\n", encoding="utf-8")
        before = git(self.repo, "rev-parse", "HEAD")
        self.advance_origin_main()
        self.merge_lands(tree, 1, head)
        self.drain()
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        self.assertIn("switch --detach", self.entries()[0]["fast_forward"])

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

    def post_merge(self, *recipe: str) -> None:
        """A stub Makefile in the main checkout with a `post-merge` target, untracked, as an install step would be."""
        lines = ["VERSION := 1", "post-merge:", *(f"\t{line}" for line in recipe), "other:", "\t@echo other"]
        (self.repo / "Makefile").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_post_merge_runs_once_per_run_after_the_runner_lock_is_released(self) -> None:
        """sd:3566. The system target's `repo-sync.sh refresh` waits for every lane's runner lock; under this
        lane's own it waited out its 45-minute bound. So the target runs once the run released the lock."""
        first, first_head = self.topic()
        second, second_head = self.topic("second")
        self.advance_origin_main()
        git(self.repo, "switch", "-q", "--detach")  # a deploying checkout is pinned (sd:3647)
        lock = self.store().lock_file
        self.post_merge(f'"{sys.executable}" -c "import fcntl, sys; '
                        f'fcntl.flock(open(sys.argv[1], \'a\'), fcntl.LOCK_EX | fcntl.LOCK_NB)" "{lock}"',
                        "echo ran >> post-merge.out")
        self.merge_lands(first, 1, first_head)
        self.merge_lands(second, 2, second_head)
        answer = self.drain()
        self.assertEqual([row["status"] for row in self.entries()], ["merged", "merged"])
        self.assertEqual(answer["post_merge"], f"make post-merge passed in {self.repo}")
        self.assertEqual((self.repo / "post-merge.out").read_text(encoding="utf-8").splitlines(), ["ran"])
        self.assertEqual([(item, body) for item, body, _ in self.notes if body.startswith("Post-merge")],
                         [(1, f"Post-merge: make post-merge passed in {self.repo}"),
                          (2, f"Post-merge: make post-merge passed in {self.repo}")])
        self.assertEqual(self.note_kinds[-2:], ["comment", "comment"])

    def test_a_makefile_without_the_target_runs_nothing_and_notes_nothing(self) -> None:
        tree, head = self.topic()
        (self.repo / "Makefile").write_text("post-merge-later:\n\ttouch ran\npost-merge := 1\n", encoding="utf-8")
        self.merge_lands(tree, 1, head)
        answer = self.drain()
        self.assertEqual((self.entries()[0]["status"], "post_merge" in answer, len(self.notes)), ("merged", False, 1))
        self.assertFalse((self.repo / "ran").exists())

    def test_a_run_that_merged_nothing_runs_no_post_merge(self) -> None:
        tree, head = self.topic()
        self.post_merge("touch ran")
        self.merge_lands(tree, 1, head)
        self.answers[(1, "prepare")] = {"ok": False, "phase": "review_blocked", "error": "a blocking finding"}
        answer = self.drain()
        self.assertEqual((self.entries()[0]["status"], "post_merge" in answer), ("failed", False))
        self.assertFalse((self.repo / "ran").exists())

    def test_a_failing_or_slow_post_merge_never_fails_the_merged_entry_and_files_a_followup(self) -> None:
        tree, head = self.topic()
        git(self.repo, "switch", "-q", "--detach")  # a deploying checkout is pinned (sd:3647)
        self.post_merge("@echo the install broke >&2", "@exit 3")
        self.merge_lands(tree, 1, head)
        answer = self.drain()
        self.assertEqual(self.entries()[0]["status"], "merged")
        self.assertTrue(answer["post_merge"].startswith(f"make post-merge failed (exit 2) in {self.repo}:"), answer)
        self.assertIn("the install broke", answer["post_merge"])
        self.assertEqual((self.notes[-1][1], self.note_kinds[-1]), (f"Post-merge: {answer['post_merge']}", "followup"))
        tree, head = self.topic("slow")
        self.post_merge("sleep 60")
        self.merge_lands(tree, 2, head)
        started = time.monotonic()
        with mock.patch.object(sd_lane, "POST_MERGE_SECONDS", 1):
            answer = self.drain()
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual((self.entries()[-1]["status"], answer["post_merge"]),
                         ("merged", f"make post-merge timed out after 1s in {self.repo}"))
        self.assertEqual(self.note_kinds[-1], "followup")

    def test_a_checkout_that_did_not_fast_forward_skips_the_post_merge_and_says_why(self) -> None:
        tree, head = self.topic()
        git(self.repo, "switch", "-q", "-c", "elsewhere")
        self.post_merge("touch ran")
        self.merge_lands(tree, 1, head)
        answer = self.drain()
        self.assertFalse((self.repo / "ran").exists())
        self.assertEqual(self.entries()[0]["status"], "merged")
        self.assertTrue(answer["post_merge"].startswith("make post-merge skipped: the main checkout did not "
                                                        "fast-forward (fast-forward skipped: the main checkout is on "
                                                        "elsewhere"), answer["post_merge"])
        self.assertEqual((self.notes[-1][1], self.note_kinds[-1]), (f"Post-merge: {answer['post_merge']}", "followup"))

    def test_a_pinned_detached_checkout_runs_the_post_merge_that_refreshes_it(self) -> None:
        """sd:3647. The hub's main checkout is pinned (detached): the fast-forward skips it, and `repo-sync.sh
        refresh`, which the target runs, moves only a pinned checkout. So the target must run for it."""
        tree, head = self.topic()
        git(self.repo, "switch", "-q", "--detach")
        self.post_merge("touch ran")
        self.merge_lands(tree, 1, head)
        answer = self.drain()
        self.assertEqual(self.entries()[0]["status"], "merged")
        self.assertEqual(answer.get("post_merge"), f"make post-merge passed in {self.repo}")
        self.assertTrue((self.repo / "ran").exists())

    def pin_at_a_base_without_the_target(self) -> str:
        """The real bootstrap: origin/main tracks a Makefile with no `post-merge`; the main checkout is pinned there."""
        (self.repo / "Makefile").write_text("other:\n\t@echo other\n", encoding="utf-8")
        git(self.repo, "add", "Makefile")
        git(self.repo, "-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-q", "-m", "base")
        git(self.repo, "push", "-q", "origin", "main")
        git(self.repo, "switch", "-q", "--detach")
        return git(self.repo, "rev-parse", "HEAD")

    def land_a_makefile(self, text: str) -> str:
        upstream = self.tmp / "upstream"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(upstream)], check=True, env=clean_environment())
        (upstream / "Makefile").write_text(text, encoding="utf-8")
        git(upstream, "add", "Makefile")
        git(upstream, "-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-q", "-m", "target")
        git(upstream, "push", "-q", "origin", "main")
        return git(upstream, "rev-parse", "HEAD")

    def test_a_checkout_pinned_at_a_base_without_the_target_runs_origins_target_and_stays_put(self) -> None:
        """sd:3647. The first landing cannot rely on the old Makefile. The lane runs origin's, with the pin still
        checked out: the recipe's `repo-sync.sh refresh` stops the consumers, records the old SHA and moves it."""
        tree, head = self.topic()
        base = self.pin_at_a_base_without_the_target()
        landed = self.land_a_makefile("post-merge:\n\tgit rev-parse HEAD >> head.out\n")
        self.merge_lands(tree, 1, head)
        answer = self.drain()
        self.assertNotEqual(base, landed)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), base)
        self.assertEqual((self.repo / "Makefile").read_text(encoding="utf-8"), "other:\n\t@echo other\n")
        self.assertEqual((self.repo / "head.out").read_text(encoding="utf-8").split(), [base])
        self.assertEqual(answer.get("post_merge"), f"make post-merge passed in {self.repo}")

    def test_a_pinned_checkout_whose_origin_has_no_target_runs_nothing(self) -> None:
        tree, head = self.topic()
        base = self.pin_at_a_base_without_the_target()
        self.land_a_makefile("other:\n\t@echo other again\n")
        self.merge_lands(tree, 1, head)
        answer = self.drain()
        self.assertEqual((git(self.repo, "rev-parse", "HEAD"), "post_merge" in answer), (base, False))

    def test_a_pinned_checkout_that_cannot_fetch_origin_says_unknown_not_no_target(self) -> None:
        tree, head = self.topic()
        self.pin_at_a_base_without_the_target()
        self.merge_lands(tree, 1, head)
        self.origin.rename(self.origin.with_name("origin-moved"))
        answer = self.drain()
        self.assertTrue(answer["post_merge"].startswith("make post-merge unknown: git fetch failed"), answer)
        self.assertEqual(self.note_kinds[-1], "followup")

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

    def repo_row(self, host: str | None = None) -> None:
        import sd_db
        connection = sd_db.connect(home=self.tmp)
        try:
            sd_db.upsert_repo(connection, str(self.repo), remote="https://github.com/example/pack.git", managed=1)
            connection.execute("UPDATE repo SET lane_host = ?", (host,))
        finally:
            connection.close()

    def failing_store(self, when: Any) -> Any:
        real = sd_lane.store

        def store(connection: Any, repository: str, entry: dict) -> None:
            if when(entry):
                raise sqlite3.OperationalError("the hub went away")
            real(connection, repository, entry)
        return mock.patch.object(sd_lane, "store", store)

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

    def test_enqueue_from_the_default_branch_refuses_before_any_push(self) -> None:
        """Failure table, enqueue: a main checkout with a commit origin lacks; nothing is pushed or queued."""
        before = self.remote_tip("main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "unreviewed")
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.enqueue_entry(self.repo, 1, "t", self.body, self.environ, claim="deliver")
        self.assertEqual((refused.exception.code, self.rows(), self.remote_tip("main"), self.git_verbs),
                         (sd_lane.DEFAULT_BRANCH, [], before, ["ls-remote"]))
        head = git(self.repo, "rev-parse", "HEAD")
        self.assertEqual(sd_lane.publish_head(self.repo, "", head), sd_lane.DEFAULT_BRANCH)

    def test_with_no_local_origin_head_the_default_branch_is_origins_not_a_guess(self) -> None:
        """Failure table, enqueue: no local `origin/HEAD`, and origin's default is `trunk`, not the local `main`."""
        git(self.repo, "push", "-q", "origin", "main:refs/heads/trunk")
        git(self.origin, "symbolic-ref", "HEAD", "refs/heads/trunk")
        before = self.remote_tip("trunk")
        tree, _ = self.committed("trunk", "unreviewed")
        self.assertEqual(git(self.repo, "for-each-ref", "refs/remotes/origin/HEAD"), "")
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.enqueue_entry(tree, 1, "t", self.body, self.environ, claim="deliver")
        self.assertEqual((refused.exception.code, self.rows(), self.remote_tip("trunk"), "push" in self.git_verbs),
                         (sd_lane.DEFAULT_BRANCH, [], before, False))

    def test_a_stale_local_origin_head_does_not_hide_origins_default_branch(self) -> None:
        """Failure table, enqueue: the local `origin/HEAD` still names `old`; origin's HEAD is `main`."""
        git(self.repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/old")
        before = self.remote_tip("main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "unreviewed")
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.enqueue_entry(self.repo, 1, "t", self.body, self.environ, claim="deliver")
        self.assertEqual((refused.exception.code, self.rows(), self.remote_tip("main"), "push" in self.git_verbs),
                         (sd_lane.DEFAULT_BRANCH, [], before, False))

    def test_an_origin_that_names_no_default_branch_is_unknown_and_pushes_nothing(self) -> None:
        """Failure table, enqueue: origin advertises no HEAD symref; the lane does not guess one."""
        git(self.origin, "symbolic-ref", "HEAD", "refs/heads/unborn")
        tree, _ = self.committed("topic", "work")
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.enqueue_entry(tree, 1, "t", self.body, self.environ, claim="deliver")
        self.assertEqual((refused.exception.code, self.rows(), self.remote_tip("topic"), "push" in self.git_verbs),
                         (sd_lane.PUBLISH_UNKNOWN, [], None, False))

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
            before = self.rows()
            answer = real(queue, work)
            if self.rows() == before:  # a read, such as enqueue's check before it publishes (sd:3283)
                return answer
            raise sd_lane.LaneError("the session dropped", code=sd_lane.HUB_UNAVAILABLE)
        with mock.patch.object(sd_lane, "on_hub", landed_then_lost), self.assertRaises(sd_lane.LaneError) as lost:
            sd_lane.enqueue_entry(self.feature, 1, "t", self.body, self.environ, claim="deliver")
        self.assertEqual(lost.exception.code, sd_lane.HUB_UNAVAILABLE)
        with self.assertRaisesRegex(sd_lane.LaneError, "already queued"):
            sd_lane.enqueue_entry(self.feature, 1, "t", self.body, self.environ, claim="deliver")
        self.assertEqual(len(self.entries()), 1)


class ItemChecks(SharedQueue):
    """sd:3473. Enqueue refuses what prepare refuses on the item, before it pushes or queues anything.

    Eight system entries waited 3 to 32 minutes at the queue's head, then
    failed in seconds on an item of another repository, a `Closes:` item of
    another repository, or an item with no registered repository.
    """

    checks_item = True

    def setUp(self) -> None:
        super().setUp()
        [self.own] = self.register_items(1)
        import sd_db
        other = self.tmp / "other"
        other.mkdir()
        connection = sd_db.connect(home=self.tmp)
        try:
            sd_db.upsert_repo(connection, str(other), remote="https://github.com/example/other.git", managed=1)
            self.foreign = sd_db.create_item(connection, kind="task", title="theirs", status="in_progress", repo=str(other))
            self.unregistered = sd_db.create_item(connection, kind="task", title="nowhere", status="in_progress")
        finally:
            connection.close()
        self.tree, _ = self.committed("topic", "work")

    def refused(self, item: int, title: str = "t", body: str = "Words.\n", claim: str = "deliver") -> sd_lane.LaneError:
        self.body.write_text(body, encoding="utf-8")
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.enqueue_entry(self.tree, item, title, self.body, self.environ, claim=claim)
        self.assertEqual((self.rows(), "push" in self.git_verbs, self.remote_tip("topic")), ([], False, None))
        return refused.exception

    def test_an_item_of_another_repository_is_refused_before_any_push(self) -> None:
        refused = self.refused(self.foreign)
        self.assertEqual(refused.code, "item_repository_mismatch")
        self.assertIn(f"item sd:{self.foreign} belongs to example/other, not example/pack", str(refused))

    def test_an_item_with_no_registered_repository_is_refused_before_any_push(self) -> None:
        self.assertIn("requires an item with a registered repository", str(self.refused(self.unregistered)))

    def test_a_closes_line_naming_another_repositorys_item_is_refused(self) -> None:
        refused = self.refused(self.own, "t", f"Closes: sd:{self.foreign}\n")
        self.assertEqual(refused.code, "closes_item_foreign")
        self.assertIn(f"names sd:{self.foreign}, which belongs to another repository", str(refused))

    def test_a_second_item_of_another_repository_is_refused(self) -> None:
        """sd:3704: each later --item is checked as a `Closes:` item is."""
        self.body.write_text("Words.\n", encoding="utf-8")
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.enqueue_entry(self.tree, self.own, "t", self.body, self.environ, claim="deliver", closes=(self.foreign,))
        self.assertEqual(refused.exception.code, "closes_item_foreign")
        self.assertEqual(self.rows(), [])

    def test_a_title_naming_another_repositorys_item_is_queued(self) -> None:
        """sd:3704: a title closes nothing, so the item it names is context, not a refusal."""
        self.body.write_text("Words.\n", encoding="utf-8")
        entry = sd_lane.enqueue_entry(self.tree, self.own, f"Two fixes (sd:{self.own}, sd:{self.foreign})", self.body,
                                      self.environ, claim="deliver")
        self.assertEqual(entry["status"], "pending")

    def test_an_associate_only_claim_with_a_closes_line_is_refused(self) -> None:
        refused = self.refused(self.own, body=f"Closes: sd:{self.own + 99}\n", claim="associate-only")
        self.assertEqual(refused.code, "closes_need_delivery")

    def test_an_item_of_this_repository_is_queued(self) -> None:
        self.body.write_text(f"Closes: sd:{self.own}\n", encoding="utf-8")
        entry = sd_lane.enqueue_entry(self.tree, self.own, f"One fix (sd:{self.own})", self.body, self.environ,
                                      claim="deliver")
        self.assertEqual(([row["item"] for row in self.entries()], entry["status"]), ([self.own], "pending"))

    def test_retry_checks_the_item_again(self) -> None:
        """A retry queues the same item again; one moved to another repository since refuses as enqueue does."""
        sd_lane.enqueue_entry(self.tree, self.own, "t", self.body, self.environ, claim="deliver")
        sd_lane.update(self.store(), lambda rows: rows[0].update(status="failed"))
        import sd_db
        connection = sd_db.connect(home=self.tmp)
        try:
            connection.execute("UPDATE item SET repo = (SELECT repo FROM item WHERE id = ?) WHERE id = ?",
                               (self.foreign, self.own))
        finally:
            connection.close()
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.retry(self.repo, self.own, self.environ)
        self.assertEqual(refused.exception.code, "item_repository_mismatch")
        self.assertEqual([row["status"] for row in self.entries()], ["failed"])


class ClaimAndLease(SharedQueue):
    def test_a_claim_that_lands_with_its_answer_lost_is_put_back_by_the_next_run(self) -> None:
        """Failure table, claim: the hub fails after the claim landed; no step starts, and reclaim puts it back."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
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
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
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
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
        sd_lane.enqueue_entry(self.worktree("second"), 2, "two", self.body, self.environ, claim="deliver")
        first = sd_lane.claim_entry(self.store(), "hub-token")
        self.repo_row("build-2")
        with mock.patch("sd_db.ship.this_host", lambda: "build-2"), self.assertRaises(sd_lane.LaneError) as busy:
            sd_lane.claim_entry(self.store(), "satellite-token")
        self.assertEqual((first["item"], busy.exception.code), (1, "lane_busy"))
        self.assertEqual([row["status"] for row in self.entries()], ["running", "pending"])

    def test_another_hosts_entry_gets_no_speculative_gate_and_says_why(self) -> None:
        """Failure table, speculation (sd:3283): the next entry has no worktree on this host; nothing is gated."""
        self.repo_row()
        sd_lane.enqueue_entry(self.worktree("second"), 1, "one", self.body, self.environ, manual=True, claim="deliver")
        with mock.patch("sd_db.ship.this_host", lambda: "build-2"):
            sd_lane.enqueue_entry(self.feature, 2, "two", self.body, self.environ, claim="deliver")
        claimed = sd_lane.claim_entry(self.store(), "token")
        self.assertEqual((claimed or {}).get("item"), 1)
        gate = mock.Mock()
        self.assertIsNone(sd_lane.speculate(claimed, self.store(), gate))
        gate.assert_not_called()
        speculation = self.entries()[1]["speculation"]
        self.assertEqual((speculation["after"], speculation["status"]), (1, "skipped"))
        self.assertIn("no worktree on this host", speculation["reason"])

    def test_a_kill_mid_prepare_puts_the_entry_back_and_the_third_fails_it(self) -> None:
        """Failure table, prepare: the runner dies; pid gone, back to pending; the third reclaim fails it."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
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
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
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

    def elsewhere(self) -> None:
        """The running entry's holder is on another machine, so a release counts it stuck on the operator's word."""
        sd_lane.update(self.store(), lambda rows: [row["holder"].update(host="build-2") for row in rows
                                                   if row.get("status") == "running"])

    def test_a_bound_release_refuses_a_step_the_caller_did_not_see(self) -> None:
        """Failure table, release (sd:3330): prepare moved to merge between the read and the cancel."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        entry = sd_lane.claim_entry(self.store(), "seen")
        seen = f"{self.entries()[0]['holder']['token']}:{self.entries()[0]['step']}"
        sd_lane.advance(self.store(), entry, "seen")
        self.elsewhere()
        before = self.rows()
        with self.assertRaises(sd_lane.LaneError) as stale:
            sd_lane.cancel(self.repo, 1, self.environ, expected_claim=seen)
        self.assertEqual((stale.exception.code, self.rows()), (sd_lane.STALE_CLAIM, before))
        with self.assertRaisesRegex(sd_lane.LaneError, "<holder token>:<step>"):  # a token alone names no step
            sd_lane.cancel(self.repo, 1, self.environ, expected_claim="seen")
        released = sd_lane.cancel(self.repo, 1, self.environ, expected_claim="seen:merge")
        self.assertEqual((released["status"], released["released"]), ("failed", True))

    def test_a_bound_release_refuses_a_reclaimed_entry_at_the_same_revision(self) -> None:
        """Failure table, release (sd:3330): recovery put the entry back and a new runner claimed it again."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.enqueue_entry(self.worktree("second"), 2, "two", self.body, self.environ, claim="deliver")
        sd_lane.claim_entry(self.store(), "seen")
        self.elsewhere()
        revision = sd_lane.queue_revision(self.entries())
        sd_lane.update(self.store(), lambda rows: rows[0].update(lease_until="2020-01-01T00:00:00Z"))
        reclaimed: list[dict] = []
        again = sd_lane.claim_entry(self.store(), "new", reclaimed)
        self.elsewhere()
        self.assertEqual((reclaimed[0]["status"], again["item"], sd_lane.queue_revision(self.entries())),
                         ("pending", 1, revision))  # the revision alone cannot tell the two claims apart
        before = self.rows()
        with self.assertRaises(sd_lane.LaneError) as stale:
            sd_lane.cancel(self.repo, 1, self.environ, expected_revision=revision, expected_claim="seen:prepare")
        self.assertEqual((stale.exception.code, self.rows()), (sd_lane.STALE_CLAIM, before))
        self.assertEqual(self.entries()[0]["holder"]["token"], "new")

    def test_a_bound_release_refuses_a_finished_entry_and_another_items_entry(self) -> None:
        """Failure table, release (sd:3330): the claim ended before the cancel, and its item was queued again."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.enqueue_entry(self.worktree("second"), 2, "two", self.body, self.environ, claim="deliver")
        entry = sd_lane.claim_entry(self.store(), "seen")
        self.elsewhere()
        before = self.rows()
        with self.assertRaises(sd_lane.LaneError) as other:  # item 1's claim names no entry of item 2
            sd_lane.cancel(self.repo, 2, self.environ, expected_claim="seen:prepare")
        self.assertEqual((other.exception.code, self.rows()), (sd_lane.STALE_CLAIM, before))
        sd_lane.finish_entry(self.store(), entry, "seen", {"status": "failed", "step": "prepare", "reason": "red"})
        sd_lane.retry(self.repo, 1, self.environ)
        before = self.rows()
        with self.assertRaises(sd_lane.LaneError) as finished:
            sd_lane.cancel(self.repo, 1, self.environ, expected_claim="seen:prepare")
        self.assertEqual((finished.exception.code, self.rows()), (sd_lane.STALE_CLAIM, before))
        self.assertEqual([row["status"] for row in self.entries() if row["item"] == 1], ["failed", "pending"])

    def test_the_claim_is_compared_under_the_queue_lock(self) -> None:
        """A step write that lands while the cancel waits for the hub's write lock is caught (sd:3330)."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.claim_entry(self.store(), "seen")
        self.elsewhere()
        refused: list[str | None] = []

        def bound_cancel() -> None:
            try:
                sd_lane.cancel(self.repo, 1, self.environ, expected_claim="seen:prepare")
            except sd_lane.LaneError as error:
                refused.append(error.code)
        import sd_db
        writer = sd_db.connect(home=self.tmp)
        self.addCleanup(writer.close)
        with sd_db.database.transaction(writer):  # BEGIN IMMEDIATE: the cancel waits for it
            canceller = threading.Thread(target=bound_cancel)
            canceller.start()
            time.sleep(0.5)
            [row] = sd_lane.stored(writer, "example/pack")
            sd_lane.store(writer, "example/pack", {**row, "step": "merge"})
        canceller.join(30)
        self.assertEqual((refused, self.entries()[0]["status"], self.entries()[0]["step"]),
                         ([sd_lane.STALE_CLAIM], "running", "merge"))

    def test_cancel_takes_the_claim_list_prints_and_unbound_keeps_todays_behaviour(self) -> None:
        """`--expected-claim <holder.token>:<step>` from `lane list`; a stale one exits 3 with its code (sd:3330)."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.claim_entry(self.store(), "seen")
        self.elsewhere()

        def lane(*args: str) -> tuple[int, dict]:
            done = subprocess.run([sys.executable, str(REPO_ROOT / "bin/sd-ship"), "-C", str(self.repo), "lane", *args],
                                  env=clean_environment(**self.environ), capture_output=True, text=True, timeout=120)
            return done.returncode, json.loads(done.stdout)
        [row] = lane("list")[1]["entries"]
        code, refused = lane("cancel", "1", "--expected-claim", f"{row['holder']['token']}:merge")
        self.assertEqual((code, refused["code"]), (3, sd_lane.STALE_CLAIM))
        code, released = lane("cancel", "1", "--expected-claim", f"{row['holder']['token']}:{row['step']}")
        self.assertEqual((code, released["status"]), (0, "pending"))
        self.assertEqual(lane("cancel", "1")[1]["status"], "cancelled")  # unbound: a pending entry, as before

    def test_an_expired_lease_with_a_live_pid_on_this_host_keeps_the_entry_running(self) -> None:
        """Failure table, prepare: the lease passed while the holder slept; same host, live pid: no reclaim."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.claim_entry(self.store(), "sleeper")
        sd_lane.update(self.store(), lambda rows: rows[0].update(lease_until="2020-01-01T00:00:00Z"))
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertNotIn("reclaimed", answer)
        self.assertIn("one entry of a repository runs at a time", answer["stopped"])
        self.assertEqual((self.calls, self.entries()[0]["status"]), ([], "running"))

    def test_a_step_write_that_fails_stops_the_runner_and_reclaim_puts_it_back(self) -> None:
        """Failure table, before merge: the hub fails for the whole retry; no merge, and the rerun runs it."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        with self.failing_store(lambda entry: entry.get("step") == "merge"):
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertIn("the hub went away", answer["stopped"])
        self.assertEqual(([c[2] for c in self.calls], self.entries()[0]["step"]), (["prepare"], "prepare"))
        self.make_dead()
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual((answer["reclaimed"][0]["status"], self.entries()[0]["status"]), ("pending", "merged"))

    def test_a_retryable_put_back_that_fails_to_write_is_reclaimed_and_counts_nothing(self) -> None:
        """Failure table, sd:3478 put-back: the write of the count fails; the entry stays running, a reclaim
        puts it back with no count, and the next prepare still has its one retry."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(1, "prepare")] = Runner.NO_PLAN
        with self.failing_store(lambda entry: "retryable_retries" in entry):
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertIn("the hub went away", answer["stopped"])
        self.assertEqual((self.entries()[0]["status"], "retryable_retries" in self.entries()[0]), ("running", False))
        self.make_dead()
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((answer["reclaimed"][0]["status"], entry["status"], entry["retryable_retries"]),
                         ("pending", "pending", 1))
        del self.answers[(1, "prepare")]
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual((self.entries()[0]["status"], [c[2] for c in self.calls]),
                         ("merged", ["prepare", "prepare", "prepare", "merge"]))

    def test_a_runner_write_is_tried_again_until_the_hub_answers(self) -> None:
        """The 10-minute write retry: two faults, then the write lands and the entry merges."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        faults = [1, 1]
        with mock.patch.object(sd_lane, "WRITE_RETRY_SECONDS", 600), \
                self.failing_store(lambda entry: entry.get("step") == "merge" and faults and faults.pop()):
            sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual((faults, self.entries()[0]["status"]), ([], "merged"))

    def test_a_hub_that_refuses_this_build_stops_the_runner_at_once(self) -> None:
        """sd:3359. Prepare met a hub fault, and the hub then refused the satellite's build.

        The runner retried the put-back for 10 minutes under its lock. Only `repo-sync.sh follow` clears
        that refusal, and `follow` waits for every runner lock: each waited on the other. A process keeps
        the build it loaded, so no retry in it can pass. It stops without a sleep, the entry stays running
        under a holder that is gone, and the next run reclaims it.
        """
        import sd_db.database
        from sd_db import remote
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        refusing: list[bool] = []
        connect = sd_db.database.connect

        def hub(*args: Any, **kwargs: Any) -> Any:
            if refusing:
                raise remote.BuildMismatch("build", "0000aaaa", "1111bbbb")
            return connect(*args, **kwargs)

        def prepare_then_upgrade(argv: list[str], log: pathlib.Path) -> dict:
            self.ship(argv, log)
            refusing.append(True)
            return Runner.HUB_FAULT

        class Slept(BaseException):
            pass

        clock = mock.Mock(wraps=time)
        clock.sleep.side_effect = Slept
        with mock.patch.object(sd_lane, "WRITE_RETRY_SECONDS", 600), mock.patch.object(sd_lane, "WRITE_PAUSE", 30), \
                mock.patch.object(sd_lane, "time", clock), mock.patch("sd_db.database.connect", hub):
            answer = sd_lane.run_lane(self.repo, self.environ, prepare_then_upgrade)
        self.assertEqual(clock.sleep.call_count, 0)
        self.assertIn("BuildMismatch", answer["stopped"])
        self.assertIn("repo-sync.sh", answer["stopped"])
        with open(self.store().lock_file, "a", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)  # free for `follow`
        self.assertEqual((self.entries()[0]["status"], self.entries()[0]["step"]), ("running", "prepare"))
        self.make_dead()
        self.calls.clear()
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual((answer["reclaimed"][0]["status"], self.entries()[0]["status"]), ("pending", "merged"))
        self.assertEqual([c[2] for c in self.calls], ["prepare", "merge"])

    def test_a_finish_write_that_fails_after_a_merge_is_failed_by_reclaim(self) -> None:
        """Failure table, finish: the hub fails after a merge; the run stops, and reclaim fails the entry."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
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
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        entry = sd_lane.claim_entry(self.store(), "sleeper")
        self.make_dead()
        sd_lane.runner_write(self.store(), sd_lane.reclaim_dead)
        before = self.rows()
        with self.assertRaises(sd_lane.Stop) as lost:
            sd_lane.finish_entry(self.store(), entry, "sleeper", {"status": "merged"})
        self.assertEqual((lost.exception.code, self.rows()), (sd_lane.CLAIM_LOST, before))

    def test_a_double_finish_writes_one_outcome_row(self) -> None:
        """Failure table, finish: a retried outcome write finds its own outcome under its token."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        entry = sd_lane.claim_entry(self.store(), "mine")
        for _ in range(2):
            sd_lane.finish_entry(self.store(), entry, "mine", {"status": "merged", "merge_commit": "c0ffee"})
        merged = [body for _, body in self.rows() if body["status"] == "merged"]
        self.assertEqual(len(merged), 1)


class AnyHost(SharedQueue):
    """sd:3283, slice 2 of the sd:3174 design: the lane host runs any entry. One test per failure-table row."""

    def enqueued_elsewhere(self, item: int, name: str, *messages: str) -> list[str]:
        """`name`'s commits, enqueued by another host; this disk keeps neither its worktree nor its branch."""
        tree, heads = self.committed(name, *messages)
        with mock.patch("sd_db.ship.this_host", lambda: "build-2"):
            sd_lane.enqueue_entry(tree, item, name, self.body, self.environ, manual=True, claim="deliver")
        git(self.repo, "worktree", "remove", "--force", str(tree))
        git(self.repo, "branch", "-D", name)
        return heads

    def made(self, item: int = 1) -> pathlib.Path:
        return self.store().lane / "worktrees" / str(item)

    def pushed_on_top(self, branch: str) -> None:
        other = self.tmp / "other"
        git(self.tmp, "clone", "-q", "-b", branch, str(self.origin), str(other))
        git(other, "-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "more")
        git(other, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")

    def test_an_entry_another_host_enqueued_runs_here_from_origin(self) -> None:
        """Failure table, claim and mixed versions: the runner makes a lane worktree from origin, then removes it."""
        [head] = self.enqueued_elsewhere(1, "topic", "work")
        seen: list[tuple[str, str]] = []

        def ship(argv: list[str], log: pathlib.Path) -> dict:
            tree = pathlib.Path(argv[1])
            seen.append((git(tree, "rev-parse", "HEAD"), git(tree, "rev-parse", "--abbrev-ref", "@{upstream}")))
            return self.ship(argv, log)
        sd_lane.run_lane(self.repo, self.environ, ship)
        self.assertEqual([(c[2], c[1]) for c in self.calls], [("prepare", str(self.made())), ("merge", str(self.made()))])
        self.assertEqual((seen[0], self.entries()[0]["status"]), ((head, "origin/topic"), "merged"))
        self.assertEqual((self.made().exists(), git(self.repo, "branch", "--list", "topic")), (False, ""))

    def catch_ups(self, branch: str, head: str, count: int) -> list[str]:
        """`count` catch-up merges of a moving main onto `head`, each on the last, pushed to `origin/<branch>`."""
        scratch, merges = self.tmp / "scratch", []
        git(self.repo, "worktree", "add", "-q", "--detach", str(scratch), head)
        for number in range(count):
            git(self.repo, "commit", "-q", "--allow-empty", "-m", f"base {number}")
            git(self.repo, "push", "-q", "origin", "main")  # prepare merges `origin/<default>`
            git(scratch, "merge", "-q", "--no-ff", "-m", "Merge origin/main", "main")
            merges.append(git(scratch, "rev-parse", "HEAD"))
        git(scratch, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
        git(self.repo, "worktree", "remove", "--force", str(scratch))
        return merges

    def foreign_merge(self, tree: pathlib.Path, edited: bool = False) -> str:
        """A merge with a catch-up's message on `tree`'s HEAD that prepare did not make; the new HEAD.

        Plain, it merges a feature branch that is not on origin's default branch. `edited`, it merges
        `origin/main` but adds a file no merge makes.
        """
        if edited:
            git(self.repo, "commit", "-q", "--allow-empty", "-m", "base moved")
            git(self.repo, "push", "-q", "origin", "main")
            git(tree, "merge", "-q", "--no-ff", "--no-commit", "main")
            (tree / "unreviewed.txt").write_text("unreviewed\n", encoding="utf-8")
            git(tree, "add", "unreviewed.txt")
            git(tree, "commit", "-q", "-m", "Merge origin/main")
        else:
            other = self.tmp / f"other-{tree.name}"
            git(self.repo, "worktree", "add", "-q", "-b", other.name, str(other), "main")
            (other / "feature.txt").write_text("unreviewed\n", encoding="utf-8")
            git(other, "add", "feature.txt")
            git(other, "commit", "-q", "-m", "an unrelated feature")
            git(tree, "merge", "-q", "--no-ff", "-m", "Merge origin/main", other.name)
        return git(tree, "rev-parse", "HEAD")

    def test_a_merge_the_lane_did_not_make_is_not_a_catch_up(self) -> None:
        """Review round 1: a merge on the queued head is a catch-up only when it is prepare's own.

        That is a clean merge of a commit on origin's default branch; an unrelated feature, or an edit inside
        the merge, is scope no review saw.
        """
        tree = self.worktree("unit")
        queued = git(tree, "rev-parse", "HEAD")
        for edited in (False, True):
            with self.subTest(edited=edited):
                git(tree, "reset", "-q", "--hard", queued)
                merge = self.foreign_merge(tree, edited)
                self.assertEqual((sd_lane.catch_up_of(tree, merge, queued), sd_lane.at_head(tree, queued),
                                  sd_lane.caught_up(tree, queued)), (False, False, queued))
        git(tree, "reset", "-q", "--hard", queued)
        [merge] = self.catch_ups("unit", queued, 1)
        git(tree, "reset", "-q", "--hard", merge)
        self.assertEqual((sd_lane.at_head(tree, queued), sd_lane.caught_up(tree, queued)), (True, merge))

    def test_a_foreign_merge_on_origin_skips_head_moved(self) -> None:
        """Review round 1, remote validation: origin/<branch> holds a merge the lane did not make."""
        for edited in (False, True):
            with self.subTest(edited=edited):
                item = 1 + edited
                [head] = self.enqueued_elsewhere(item, f"topic{item}", "work")
                scratch = self.tmp / f"scratch{item}"
                git(self.repo, "worktree", "add", "-q", "--detach", str(scratch), head)
                self.foreign_merge(scratch, edited)
                git(scratch, "push", "-q", "origin", f"HEAD:refs/heads/topic{item}")
                git(self.repo, "worktree", "remove", "--force", str(scratch))
                sd_lane.run_lane(self.repo, self.environ, self.ship)
                entry = self.entries()[-1]
                self.assertEqual((entry["status"], entry.get("code"), self.calls), ("skipped", "head_moved", []))

    def test_a_foreign_merge_in_the_own_worktree_is_not_run(self) -> None:
        """Review round 1, own worktree and the head check: the entry's worktree holds a merge the lane did not make."""
        for edited in (False, True):
            with self.subTest(edited=edited):
                item = 1 + edited
                tree = self.worktree(f"own{item}")
                sd_lane.enqueue_entry(tree, item, "one", self.body, self.environ, manual=True, claim="deliver")
                self.foreign_merge(tree, edited)
                sd_lane.run_lane(self.repo, self.environ, self.ship)
                self.assertEqual((self.entries()[-1]["status"], self.calls), ("skipped", []))

    def test_a_put_back_never_adopts_a_foreign_merge_origin_holds(self) -> None:
        """Review round 1, put-back and the before-merge check: origin/<branch> gained a merge the lane did not make.

        A hub fault, a merge that answers `lane_elsewhere`, and a move seen by the before-merge write each put
        the entry back; `expected_head` stays the queued head.
        """
        for case in ("hub_fault", "merge_elsewhere", "moved"):
            with self.subTest(case=case):
                item = {"hub_fault": 1, "merge_elsewhere": 2, "moved": 3}[case]
                tree = self.worktree(f"back{item}")
                queued = sd_lane.enqueue_entry(tree, item, "one", self.body, self.environ, manual=True,
                                               claim="deliver")["expected_head"]
                self.answers[(item, "merge")] = {"ok": False, "phase": "merge", "error": "runs on build-2",
                                                 "workflow": {"blocker": {"code": "lane_elsewhere"}}}

                def prepare(argv: list[str], log: pathlib.Path, tree: pathlib.Path = tree, case: str = case,
                            item: int = item) -> dict:
                    if argv[2] == "prepare":
                        self.foreign_merge(tree)
                        git(tree, "push", "-q", "origin", f"HEAD:refs/heads/back{item}")
                        if case == "moved":
                            self.repo_row("build-2")
                    answer = self.ship(argv, log)
                    return Runner.HUB_FAULT if case == "hub_fault" and argv[2] == "prepare" else answer
                sd_lane.run_lane(self.repo, self.environ, prepare)
                entry = self.entries()[-1]
                self.repo_row(None)
                sd_lane.cancel(self.repo, item, self.environ)  # before the check, so a failure leaves no entry behind
                self.assertEqual((entry["item"], entry["status"], entry["expected_head"]), (item, "pending", queued))

    def test_an_own_worktree_that_moved_on_its_branch_skips_head_moved(self) -> None:
        """sd:3413. The builder committed or amended after enqueue; the run never advises removing its branch."""
        for amended in (False, True):
            with self.subTest(amended=amended):
                item = 1 + amended
                tree, _ = self.committed(f"moved{item}", "work")
                sd_lane.enqueue_entry(tree, item, "t", self.body, self.environ, manual=True, claim="deliver")
                git(tree, "commit", "-q", *(["--amend"] if amended else []), "--allow-empty", "-m", "more")
                sd_lane.run_lane(self.repo, self.environ, self.ship)
                entry = self.entries()[-1]
                self.assertEqual((entry["status"], entry.get("code"), self.calls), ("skipped", sd_lane.HEAD_MOVED, []))
                self.assertIn(str(tree), entry["reason"])
                self.assertFalse(self.made(item).exists())

    def test_a_failing_branch_read_of_a_moved_own_worktree_leaves_the_entry_pending(self) -> None:
        """sd:3413, unknown reads: the moved own worktree's branch read failed; not a skip, not a fall-through."""
        tree, _ = self.committed("moved", "work")
        sd_lane.enqueue_entry(tree, 1, "t", self.body, self.environ, manual=True, claim="deliver")
        git(tree, "commit", "-q", "--allow-empty", "-m", "more")
        with self.failing("branch"):
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], "holder" in entry, self.calls), ("pending", False, []))
        self.assertIn("not skipped", answer["stopped"])

    def test_an_entry_with_no_worktree_never_reads_the_runners_directory_as_its_own(self) -> None:
        """sd:3413, codex review: `Path("")` is the current directory, which may hold the branch at another head."""
        tree, [head] = self.committed("topic", "work")
        sd_lane.enqueue_entry(tree, 1, "t", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.update(self.store(), lambda rows: rows[0].update(worktree=""))
        git(self.repo, "worktree", "remove", "--force", str(tree))
        git(self.repo, "branch", "-D", "topic")
        decoy = self.tmp / "decoy"
        git(self.tmp, "clone", "-q", "-b", "topic", str(self.origin), str(decoy))
        git(decoy, "-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(decoy)
        heads: list[str] = []

        def ship(argv: list[str], log: pathlib.Path) -> dict:
            heads.append(git(pathlib.Path(argv[1]), "rev-parse", "HEAD"))
            return self.ship(argv, log)
        sd_lane.run_lane(self.repo, self.environ, ship)
        self.assertEqual((self.entries()[0]["status"], heads[:1]), ("merged", [head]))

    def test_a_retry_never_starts_from_a_foreign_merge(self) -> None:
        """Review round 1, retry: the worktree's HEAD is a merge the lane did not make; the retry keeps the head."""
        tree = self.worktree("again")
        queued = sd_lane.enqueue_entry(tree, 1, "one", self.body, self.environ, manual=True,
                                       claim="deliver")["expected_head"]

        def blocked(argv: list[str], log: pathlib.Path) -> dict:
            self.foreign_merge(tree)
            self.ship(argv, log)
            return {"ok": False, "phase": "review_blocked", "error": "a blocking finding"}
        sd_lane.run_lane(self.repo, self.environ, blocked)
        self.assertEqual(sd_lane.retry(self.repo, 1, self.environ)["expected_head"], queued)

    def test_a_chain_of_pushed_catch_ups_after_two_reclaims_still_runs(self) -> None:
        """Codex review: prepare pushed a catch-up, died, was reclaimed, caught up again; both merges are its own."""
        [head] = self.enqueued_elsewhere(1, "topic", "work")
        [_, second] = self.catch_ups("topic", head, 2)
        seen: list[str] = []

        def ship(argv: list[str], log: pathlib.Path) -> dict:
            seen.append(git(pathlib.Path(argv[1]), "rev-parse", "HEAD"))
            return self.ship(argv, log)
        sd_lane.run_lane(self.repo, self.environ, ship)
        self.assertEqual((self.entries()[0]["status"], seen[:1]), ("merged", [second]))

    def test_a_failed_read_of_a_catch_ups_parents_leaves_the_entry_pending(self) -> None:
        """Codex review: origin holds a valid catch-up, and the read of its parents fails; unknown, not head_moved."""
        [head] = self.enqueued_elsewhere(1, "topic", "work")
        [merge] = self.catch_ups("topic", head, 1)
        real_lane, real_publish = sd_lane.lane_git, sd_lane.publish_git

        def parents_read(args: tuple[str, ...]) -> bool:
            return any(merge in arg for arg in args) and args[0] in ("rev-parse", "rev-list", "cat-file", "log")

        def lane_git(worktree: pathlib.Path, *args: str) -> str | None:
            return None if parents_read(args) else real_lane(worktree, *args)

        def publish_git(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess | None:
            return None if parents_read(args) else real_publish(root, *args)
        with mock.patch.object(sd_lane, "lane_git", lane_git), mock.patch.object(sd_lane, "publish_git", publish_git):
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], "holder" in entry, self.calls), ("pending", False, []))
        self.assertIn("stopped", answer)

    def test_a_lane_worktree_landing_names_the_builders_worktree_and_host(self) -> None:
        """Codex review: the builder's worktree stays on the host that enqueued it; the note says where and how."""
        self.enqueued_elsewhere(1, "topic", "work")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        [(_, body, _)] = self.notes
        kept = self.tmp / "topic"
        self.assertIn(f"{kept} stays on build-2", body)
        self.assertTrue(body.endswith(f"Remove on build-2: git -C {kept} worktree remove {kept}"), body)

    def test_a_lane_worktree_is_removed_when_its_entry_fails(self) -> None:
        """Failure table, end: the runner removes the lane worktree and the branch it made, whatever the outcome."""
        self.enqueued_elsewhere(1, "topic", "work")
        self.answers[(1, "prepare")] = {"ok": False, "phase": "prepare", "error": "review blocked"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual(self.entries()[0]["status"], "failed")
        self.assertEqual((self.made().exists(), git(self.repo, "branch", "--list", "topic")), (False, ""))

    def test_a_remote_branch_that_moved_skips_head_moved(self) -> None:
        """Failure table, worktree: the fetched head is neither `expected_head` nor its catch-up merge."""
        self.enqueued_elsewhere(1, "topic", "work")
        self.pushed_on_top("topic")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry.get("code"), self.calls), ("skipped", "head_moved", []))

    def test_a_deleted_remote_branch_skips_head_gone(self) -> None:
        """Failure table, worktree: `origin/<branch>` was deleted after enqueue."""
        self.enqueued_elsewhere(1, "topic", "work")
        git(self.origin, "update-ref", "-d", "refs/heads/topic")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry.get("code"), self.calls), ("skipped", sd_lane.HEAD_GONE, []))
        self.assertIn("lane retry", entry["reason"])

    def test_a_failing_read_or_fetch_of_origin_leaves_the_entry_pending(self) -> None:
        """Failure table, worktree: an unknown answer is not a skip; back to pending at its place, the run stops."""
        self.enqueued_elsewhere(1, "topic", "work")
        for verb in ("ls-remote", "fetch"):
            with self.subTest(verb=verb):
                with self.failing(verb):
                    answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
                entry = self.entries()[0]
                self.assertEqual((entry["status"], "holder" in entry, self.calls), ("pending", False, []))
                self.assertIn("origin", answer["stopped"])
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual(self.entries()[0]["status"], "merged")

    def test_a_failing_local_read_leaves_the_entry_pending(self) -> None:
        """Codex class pass, unknown reads: a failed worktree list or local branch read is not a skip or a failure."""
        self.enqueued_elsewhere(1, "topic", "work")
        for verb in ("worktree", "rev-parse"):
            with self.subTest(verb=verb):
                with self.failing(verb):
                    answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
                entry = self.entries()[0]
                self.assertEqual((entry["status"], "holder" in entry, self.calls), ("pending", False, []))
                self.assertIn("not skipped", answer["stopped"])
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual(self.entries()[0]["status"], "merged")

    def test_a_head_check_with_no_answer_before_prepare_leaves_the_entry_pending(self) -> None:
        """Codex class pass, unknown reads: the head check before prepare has no answer; no skip, no failure."""
        self.enqueued_elsewhere(1, "topic", "work")

        def unknown(tree: pathlib.Path, expected: str) -> bool:
            raise sd_lane.LaneError("git rev-parse failed; the entry is not skipped.", code=sd_lane.PUBLISH_UNKNOWN)
        with mock.patch.object(sd_lane, "at_head", unknown):
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], "holder" in entry, self.calls), ("pending", False, []))
        self.assertIn("not skipped", answer["stopped"])
        self.assertFalse(self.made().exists())

    def test_a_local_branch_at_another_commit_skips_branch_busy(self) -> None:
        """Failure table, worktree: a local branch of that name at another commit, or checked out at another head."""
        for checked_out in (False, True):
            with self.subTest(checked_out=checked_out):
                item = 1 + checked_out
                self.enqueued_elsewhere(item, f"topic{item}", "work")
                if checked_out:
                    git(self.repo, "worktree", "add", "-q", "-b", f"topic{item}", str(self.tmp / "busy"), "main")
                else:
                    git(self.repo, "branch", f"topic{item}", "main")
                sd_lane.run_lane(self.repo, self.environ, self.ship)
                entry = self.entries()[-1]
                self.assertEqual((entry["status"], entry.get("code"), self.calls), ("skipped", "branch_busy", []))

    def test_a_leftover_lane_worktree_at_another_head_is_remade(self) -> None:
        """Failure table, worktree: a killed run left its lane worktree and branch at another head."""
        [head] = self.enqueued_elsewhere(1, "topic", "work")
        self.made().parent.mkdir(parents=True, exist_ok=True)
        git(self.repo, "worktree", "add", "-q", "-b", "topic", str(self.made()), "main")
        heads: list[str] = []

        def ship(argv: list[str], log: pathlib.Path) -> dict:
            heads.append(git(pathlib.Path(argv[1]), "rev-parse", "HEAD"))
            return self.ship(argv, log)
        sd_lane.run_lane(self.repo, self.environ, ship)
        self.assertEqual((heads[:1], self.entries()[0]["status"]), ([head], "merged"))
        self.assertFalse(self.made().exists())

    def test_a_leftover_lane_worktree_at_the_head_is_reused_and_its_branch_kept(self) -> None:
        """sd:3483: a killed run's lane worktree at the head runs the entry; this run did not make its branch."""
        [head] = self.enqueued_elsewhere(1, "topic", "work")
        self.made().parent.mkdir(parents=True, exist_ok=True)
        git(self.repo, "fetch", "-q", "origin", "topic")
        git(self.repo, "worktree", "add", "-q", "-b", "topic", str(self.made()), head)
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual(self.entries()[0]["status"], "merged")
        self.assertEqual((self.made().exists(), git(self.repo, "rev-parse", "refs/heads/topic")), (False, head))

    def test_a_leftover_lane_worktree_keeps_a_branch_origin_lacks(self) -> None:
        """sd:3483. A killed run's lane worktree went with `git branch -D`, though the lane may not have made the branch."""
        self.enqueued_elsewhere(1, "topic", "work")
        self.made().parent.mkdir(parents=True, exist_ok=True)
        git(self.repo, "worktree", "add", "-q", "-b", "topic", str(self.made()), "main")
        git(self.made(), "commit", "-q", "--allow-empty", "-m", "on no remote")
        unpushed = git(self.made(), "rev-parse", "HEAD")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry.get("code"), self.calls), ("skipped", sd_lane.BRANCH_BUSY, []))
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/topic"), unpushed)
        self.assertFalse(self.made().exists())

    def test_a_pending_entry_with_no_branch_fails_and_does_not_loop(self) -> None:
        """Failure table, worktree: an entry another host left with no branch has nothing to fetch; it fails once."""
        self.enqueued_elsewhere(1, "topic", "work")
        sd_lane.update(self.store(), lambda rows: rows[0].update(branch=None))
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry.get("code"), self.calls), ("failed", "no_branch", []))
        self.assertNotIn("stopped", answer)

    def test_a_leftover_lane_folder_git_no_longer_knows_is_replaced(self) -> None:
        """Failure table, worktree: the lane folder exists but is no registered worktree; the runner remakes it.

        Gate round 1: the stale folder is renamed aside, never deleted, so no new deletion path exists.
        """
        self.enqueued_elsewhere(1, "topic", "work")
        self.made().mkdir(parents=True)
        (self.made() / "stale.txt").write_text("left by a killed run\n", encoding="utf-8")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        [aside] = self.made().parent.glob(f"{self.made().name}.stale-*")
        self.assertEqual((self.entries()[0]["status"], (aside / "stale.txt").read_text(encoding="utf-8")),
                         ("merged", "left by a killed run\n"))

    def test_a_claim_whose_write_fails_reports_no_reclaim(self) -> None:
        """Failure table, claim: a cross-host reclaim inside a claim the hub never took is not reported."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.claim_entry(self.store(), "elsewhere")
        sd_lane.update(self.store(), lambda rows: rows[0]["holder"].update(host="build-2")
                       or rows[0].update(lease_until="2020-01-01T00:00:00Z"))
        reclaimed: list = []
        with self.failing_store(lambda entry: True), self.assertRaises(sd_lane.Stop):
            sd_lane.claim_entry(self.store(), "mine", reclaimed)
        self.assertEqual((reclaimed, self.entries()[0]["status"]), ([], "running"))

    def test_an_expired_lease_on_another_host_is_reclaimed_at_claim(self) -> None:
        """Failure table, claim: a holder on another host is dead once its lease passed; the lane host reclaims it."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.claim_entry(self.store(), "elsewhere")
        sd_lane.update(self.store(), lambda rows: rows[0]["holder"].update(host="build-2"))
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertIn("one entry of a repository runs at a time", answer["stopped"])
        self.assertEqual((self.calls, self.entries()[0]["status"]), ([], "running"))
        sd_lane.update(self.store(), lambda rows: rows[0].update(lease_until="2020-01-01T00:00:00Z"))
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([(row["item"], row["status"]) for row in answer["reclaimed"]], [(1, "pending")])
        self.assertEqual(self.entries()[0]["status"], "merged")

    def test_a_move_during_prepare_puts_the_entry_back_and_the_new_host_claims_it(self) -> None:
        """Failure table, before merge: the lane moved mid-prepare; no merge here, the entry keeps its place."""
        self.repo_row()
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.enqueue_entry(self.worktree("second"), 2, "two", self.body, self.environ, manual=True, claim="deliver")

        def prepared_then_moved(argv: list[str], log: pathlib.Path) -> dict:
            answer = self.ship(argv, log)
            self.repo_row("build-2")
            return answer
        answer = sd_lane.run_lane(self.repo, self.environ, prepared_then_moved)
        self.assertEqual([c[2] for c in self.calls], ["prepare"])
        self.assertIn("runs on build-2", answer["stopped"])
        one = self.entries()[0]
        self.assertEqual((one["status"], "holder" in one, one["moved_off"]["host"]), ("pending", False, sd_lane.this_host()))
        with mock.patch("sd_db.ship.this_host", lambda: "build-2"):
            self.assertEqual((sd_lane.claim_entry(self.store(), "new-host") or {}).get("item"), 1)

    def test_a_lane_host_that_cannot_be_read_before_the_merge_stops_with_no_merge(self) -> None:
        """Failure table, before merge: clones that disagree on the host; no merge starts and the run stops."""
        self.repo_row()
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")

        def prepared_then_unknown(argv: list[str], log: pathlib.Path) -> dict:
            import sd_db
            connection = sd_db.connect(home=self.tmp)
            try:
                sd_db.upsert_repo(connection, str(self.tmp / "clone-2"), remote="https://github.com/example/pack.git",
                                  managed=1)
                connection.execute("UPDATE repo SET lane_host = 'build-2' WHERE path = ?", (str(self.tmp / "clone-2"),))
            finally:
                connection.close()
            return self.ship(argv, log)
        answer = sd_lane.run_lane(self.repo, self.environ, prepared_then_unknown)
        self.assertEqual([c[2] for c in self.calls], ["prepare"])
        self.assertIn("Cannot read the lane host before the merge", answer["stopped"])
        self.assertEqual((self.entries()[0]["status"], self.entries()[0]["step"]), ("running", "prepare"))

    def test_a_merge_that_answers_lane_elsewhere_puts_the_entry_back(self) -> None:
        """Failure table, merge: `sd-ship merge` refused `lane_elsewhere`; the runner treats it as a move."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(1, "merge")] = {"ok": False, "phase": "merge", "error": "The lane for example/pack runs on build-2",
                                      "workflow": {"blocker": {"code": "lane_elsewhere"}}}
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship)
        entry = self.entries()[0]
        self.assertEqual((entry["status"], "holder" in entry, entry["moved_off"]["host"]),
                         ("pending", False, sd_lane.this_host()))
        self.assertIn("runs on build-2", answer["stopped"])

    def test_the_ship_locks_lane_elsewhere_reaches_the_runner_as_that_code(self) -> None:
        """Failure table, merge: the lock's `LaneElsewhere` is a `WorkflowError`; its JSON names `lane_elsewhere`."""
        from sd_db.ship import LaneElsewhere
        answer = sd_lane.sd_ship_workflow.failure("merge", LaneElsewhere("example/pack", "build-2", None))
        self.assertEqual(answer["workflow"]["blocker"]["code"], "lane_elsewhere")

    def test_every_verb_but_run_works_off_the_lane_host(self) -> None:
        """Failure table, verbs: with the lane on another host, the queue verbs work here; only `run` refuses."""
        import argparse
        self.repo_row("build-2")
        tree, _ = self.committed("topic", "work")
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
        sd_lane.update(self.store(), lambda rows: rows[0].update(status="failed"))
        parser = argparse.ArgumentParser()
        sd_lane.add_lane_verbs(parser.add_subparsers(dest="command"))
        verbs = (["enqueue", "--item", "2", "--title", "t", "--body-file", str(self.body), "--deliver"], ["list"],
                 ["move", "2", "top"], ["hold", "2"], ["release", "2"], ["cancel", "2"], ["retry", "1"], ["run"])
        codes = []
        for argv in verbs:
            with contextlib.chdir(tree), mock.patch.dict(os.environ, self.environ), \
                    contextlib.redirect_stdout(io.StringIO()) as said:
                code = sd_lane.lane_main(parser.parse_args(["lane", *argv]))
            codes.append((argv[0], code, json.loads(said.getvalue()).get("code")))
        self.assertEqual(codes, [(verb[0], 0, None) for verb in verbs[:-1]] + [("run", 3, "lane_elsewhere")])


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

    def test_retry_of_an_entry_on_the_default_branch_refuses_before_any_push(self) -> None:
        """Failure table, retry: an older version queued a main checkout; retry pushes nothing to main."""
        before = self.remote_tip("main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "unreviewed")
        self.imported_blocked(self.repo, git(self.repo, "rev-parse", "HEAD"))
        rows = self.rows()
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.retry(self.repo, 1, self.environ)
        remote = [verb for verb in self.git_verbs if verb != "rev-parse"]  # the local head read is not a publish step
        self.assertEqual((refused.exception.code, self.rows(), self.remote_tip("main"), remote),
                         (sd_lane.DEFAULT_BRANCH, rows, before, ["ls-remote"]))

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


class RetryCancelled(SharedQueue):
    """sd:3389. `lane retry` takes a cancelled entry, bound to the head the caller read; one test per failure-table row."""

    def cancelled(self, item: int = 1) -> tuple[pathlib.Path, str]:
        """Item `item` enqueued from its own worktree with one commit, then cancelled; the worktree and its head."""
        tree, [head] = self.committed(f"topic-{item}", "work")
        sd_lane.enqueue_entry(tree, item, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.cancel(self.repo, item, self.environ)
        self.git_verbs.clear()  # the enqueue's own publish
        return tree, head

    def test_a_cancelled_entry_joins_the_queue_last_at_its_head(self) -> None:
        """Failure table, write: the retried entry is a plain pending entry after every other one; it jumps nothing."""
        self.cancelled(1)
        for item in (2, 3):
            sd_lane.enqueue_entry(self.committed(f"topic-{item}", "work")[0], item, "t", self.body, self.environ,
                                  claim="deliver")
        head = self.entries()[0]["expected_head"]
        retried = sd_lane.retry(self.repo, 1, self.environ, expected_head=head)
        self.assertEqual((retried["status"], retried["expected_head"], retried["authority"], retried["retried"]["status"]),
                         ("pending", head, "manual", "cancelled"))
        pending = [row["item"] for row in self.entries() if row["status"] == "pending"]
        self.assertEqual(pending, [2, 3, 1])
        self.assertEqual([(row["item"], row["status"]) for row in self.entries() if row["item"] == 1],
                         [(1, "cancelled"), (1, "pending")])
        self.assertNotIn("held", retried)
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual([int(call[call.index("--item") + 1]) for call in self.calls if call[2] == "prepare"], [2, 3, 1])

    def test_a_cancelled_entry_needs_the_expected_head_and_a_stale_one_is_refused(self) -> None:
        """Failure table, read: without the head the caller showed, or with another one, nothing is pushed or written."""
        _, head = self.cancelled()
        before = self.rows()
        with self.assertRaisesRegex(sd_lane.LaneError, "--expected-head"):
            sd_lane.retry(self.repo, 1, self.environ)
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.retry(self.repo, 1, self.environ, expected_head="0" * 40)
        self.assertEqual(refused.exception.code, sd_lane.STALE_HEAD)
        self.assertEqual((self.rows(), [verb for verb in self.git_verbs if verb == "push"]), (before, []))

    def test_a_cancelled_entry_whose_branch_moved_on_origin_is_refused(self) -> None:
        """Failure table, read: the builder pushed past the cancelled head; a retry would ship scope nobody saw."""
        tree, head = self.cancelled()
        git(tree, "commit", "-q", "--allow-empty", "-m", "more")
        git(tree, "push", "-q", "origin", "topic-1")
        before = self.rows()
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.retry(self.repo, 1, self.environ, expected_head=head)
        self.assertEqual(refused.exception.code, sd_lane.HEAD_MOVED)
        self.assertIn(git(tree, "rev-parse", "HEAD"), str(refused.exception))
        self.assertEqual((self.rows(), self.remote_tip("topic-1"), "push" in self.git_verbs),
                         (before, git(tree, "rev-parse", "HEAD"), False))

    def test_a_cancelled_entry_whose_worktree_moved_is_refused(self) -> None:
        """Failure table, read: the builder committed past the cancelled head but has not pushed."""
        tree, head = self.cancelled()
        git(tree, "commit", "-q", "--allow-empty", "-m", "more")
        before = self.rows()
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.retry(self.repo, 1, self.environ, expected_head=head)
        self.assertEqual(refused.exception.code, sd_lane.HEAD_MOVED)
        self.assertEqual((self.rows(), self.remote_tip("topic-1")), (before, head))

    def merged_receipt(self, branch: str, item: int, head: str, phase: str = "merged") -> None:
        """The ship receipt `sd-ship merge` leaves for `branch` and `item`, in the lane or by hand."""
        import sd_db
        from sd_db import ship
        connection = sd_db.connect(home=self.tmp)
        try:
            key = ship.receipt_key("example/pack", branch, item)
            ship.save(connection, key, ship.read(connection, key)[0],
                      {"repository": "example/pack", "branch": branch, "item": item, "phase": phase, "head": head,
                       "merge_commit": "1" * 40})
        finally:
            connection.close()

    def test_a_cancelled_entry_whose_head_already_merged_is_refused(self) -> None:
        """Failure table, read: `sd-ship` merged a head that holds the cancelled one; a retry would ship it twice."""
        tree, head = self.cancelled()
        child = git(tree, "commit-tree", f"{head}^{{tree}}", "-p", head, "-m", "prepare's catch-up")
        for merged, phase in ((head, "merged"), (child, "merged"), (child, "merge_dispatch")):
            self.merged_receipt("topic-1", 1, merged, phase)
            before = self.rows()
            with self.assertRaises(sd_lane.LaneError) as refused:
                sd_lane.retry(self.repo, 1, self.environ, expected_head=head)
            self.assertEqual(refused.exception.code, sd_lane.ALREADY_MERGED, phase)
            self.assertIn("1" * 40, str(refused.exception))
            self.assertEqual((self.rows(), "push" in self.git_verbs), (before, False))
        # A merged head this checkout cannot read is unknown, not "not merged".
        self.merged_receipt("topic-1", 1, "2" * 40)
        with self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.retry(self.repo, 1, self.environ, expected_head=head)
        self.assertEqual(refused.exception.code, sd_lane.PUBLISH_UNKNOWN)
        # A later head on the same branch is a follow-up nobody merged yet; it is queued again.
        self.merged_receipt("topic-1", 1, head)
        git(tree, "commit", "-q", "--allow-empty", "-m", "follow-up")
        later = git(tree, "rev-parse", "HEAD")
        sd_lane.enqueue_entry(tree, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.cancel(self.repo, 1, self.environ)
        self.assertEqual(sd_lane.retry(self.repo, 1, self.environ, expected_head=later)["expected_head"], later)

    def test_a_branch_that_moves_after_the_check_is_skipped_by_the_runner(self) -> None:
        """Failure table, publish: the builder pushes between the branch read and the write; the run skips it."""
        tree, head = self.cancelled()
        real = sd_lane.require_published

        def builder_pushes_first(*args: Any) -> None:
            git(tree, "commit", "-q", "--allow-empty", "-m", "more")
            git(tree, "push", "-q", "origin", "topic-1")
            real(*args)
        with mock.patch.object(sd_lane, "require_published", builder_pushes_first):
            self.assertEqual(sd_lane.retry(self.repo, 1, self.environ, expected_head=head)["expected_head"], head)
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        self.assertEqual((self.entries()[-1]["status"], self.entries()[-1]["code"], self.calls),
                         ("skipped", sd_lane.HEAD_MOVED, []))

    def test_a_successor_moved_above_a_cancelled_entry_is_the_one_retried(self) -> None:
        """Failure table, read: a newer entry of the item ended at a position above the cancelled one.

        The retry takes that newer entry, the item's last by enqueue order (sd:3412), never the cancelled one.
        """
        sd_lane.enqueue_entry(self.committed("topic-2", "work")[0], 2, "t", self.body, self.environ, claim="deliver")
        _, head = self.cancelled(1)
        sd_lane.enqueue_entry(self.tmp / "topic-1", 1, "one", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.move(self.repo, 1, "top", self.environ)
        sd_lane.update(self.store(), lambda rows: [row.update(status="failed") for row in rows
                                                   if row["item"] == 1 and row["status"] == "pending"])
        self.assertEqual([(row["item"], row["status"]) for row in self.entries() if row["item"] == 1][-1],
                         (1, "cancelled"))
        retried = sd_lane.retry(self.repo, 1, self.environ, expected_head=head)
        self.assertEqual((retried["retried"]["status"], retried["expected_head"]), ("failed", head))
        self.assertEqual([row["status"] for row in self.entries() if row["item"] == 1],
                         ["failed", "cancelled", "pending"])

    def test_a_successor_written_between_the_read_and_the_write_is_refused(self) -> None:
        """Failure table, write: the transaction finds the item's entry it read is no longer its newest."""
        _, head = self.cancelled()
        real = sd_lane.require_published

        def another_entry_lands_first(*args: Any) -> None:
            real(*args)
            sd_lane.update(self.store(), lambda rows: rows.append(
                {**rows[0], "id": "later", "position": 9, "status": "merged", "merge_commit": "merged-1"}))
        with mock.patch.object(sd_lane, "require_published", another_entry_lands_first):
            with self.assertRaises(sd_lane.LaneError) as refused:
                sd_lane.retry(self.repo, 1, self.environ, expected_head=head)
        self.assertEqual(refused.exception.code, sd_lane.SUPERSEDED)
        self.assertEqual([row["status"] for row in self.entries()], ["cancelled", "merged"])

    def test_a_failed_branch_read_is_unknown_and_writes_nothing(self) -> None:
        """Failure table, read: `ls-remote` did not answer; that is not "the branch did not move"."""
        _, head = self.cancelled()
        before = self.rows()
        with self.failing("ls-remote"), self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.retry(self.repo, 1, self.environ, expected_head=head)
        self.assertEqual((refused.exception.code, self.rows(), "push" in self.git_verbs),
                         (sd_lane.PUBLISH_UNKNOWN, before, False))

    def test_a_rerun_after_a_kill_between_the_push_and_the_row_queues_one_entry(self) -> None:
        """Failure table, publish: origin lost the branch after the cancel; killed after the push, before the row."""
        tree, head = self.cancelled()
        git(tree, "push", "-q", "origin", "--delete", "topic-1")
        with mock.patch.object(sd_lane, "add_entry", side_effect=Killed), self.assertRaises(Killed):
            sd_lane.retry(self.repo, 1, self.environ, expected_head=head)
        self.assertEqual((self.remote_tip("topic-1"), [row["status"] for row in self.entries()]), (head, ["cancelled"]))
        self.git_verbs.clear()
        sd_lane.retry(self.repo, 1, self.environ, expected_head=head)
        self.assertNotIn("push", self.git_verbs)
        self.assertEqual([row["status"] for row in self.entries()], ["cancelled", "pending"])


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
        self.write_file(self.old(1, self.feature), self.old(2, self.repo, status="merged"))
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
        self.write_file(self.old(1, self.feature), self.old(2, self.repo, status="failed"))
        with mock.patch.object(pathlib.Path, "rename", side_effect=Killed), self.assertRaises(Killed):
            self.import_now()
        self.assertEqual((len(self.rows()), self.file.exists()), (2, True))
        self.import_now()
        self.assertEqual((len(self.rows()), self.file.exists(), len(self.imported_files())), (2, False, 1))
        self.assertTrue(all(row["id"].startswith("import-") for row in self.entries()))

    def test_leftover_named_bodies_go_and_an_unnamed_body_stays(self) -> None:
        """Failure table, import: killed before the named body files go; the next pass deletes only those."""
        self.write_file(self.old(1, self.feature), self.old(2, self.repo, status="failed"))
        unnamed = self.bodies / "3-y.md"
        unnamed.write_text("an older enqueue's copy\n", encoding="utf-8")
        with mock.patch.object(sd_lane, "drop_imported_bodies", side_effect=Killed), self.assertRaises(Killed):
            self.import_now()
        self.assertEqual(sorted(path.name for path in self.bodies.iterdir()), ["1-x.md", "2-x.md", "3-y.md"])
        self.import_now()
        self.assertEqual([path.name for path in self.bodies.iterdir()], ["3-y.md"])

    def test_a_body_an_older_enqueue_copied_before_its_queue_write_survives_and_imports(self) -> None:
        """Failure table, import: an older `sd-ship` copied a body, then appended a new file after the rename."""
        self.write_file(self.old(1, self.feature))
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

    def test_a_pending_entry_on_the_default_branch_imports_skipped_without_a_push(self) -> None:
        """Failure table, import publish: an older version queued a main checkout ahead of origin; nothing is pushed."""
        before = self.remote_tip("main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "unreviewed")
        live, [live_head] = self.committed("live", "work")
        self.write_file(self.old(1, self.repo), self.old(2, live, head=live_head))
        self.import_now()
        self.assertEqual(self.statuses(), [(1, "skipped"), (2, "pending")])
        self.assertEqual((self.entries()[0]["code"], self.remote_tip("main"), self.remote_tip("live")),
                         (sd_lane.DEFAULT_BRANCH, before, live_head))

    def test_a_blocked_entry_with_no_branch_or_commit_imports_without_a_push(self) -> None:
        """Failure table, import: a blocked entry's worktree and branch are gone; it is history, not published."""
        tree, [head] = self.committed("topic", "work")
        self.write_file(self.old(1, None, status="failed", head="1" * 40), self.old(2, tree, head=head))
        self.import_now()
        self.assertEqual(self.statuses(), [(1, "failed"), (2, "pending")])
        self.assertEqual((self.git_verbs.count("push"), self.entries()[0]["branch"]), (1, None))

    def test_an_append_after_the_rename_is_imported_once(self) -> None:
        """Failure table, import: an older `sd-ship` enqueues during the import; it lands in a new file."""
        self.write_file(self.old(1, self.feature))
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
        sd_lane.enqueue_entry(self.feature, 6, "queued here", self.body, self.environ, claim="deliver")
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
        original = self.write_file(self.old(1, self.feature), self.old(2, self.repo, status="merged"))
        self.import_now()
        [kept] = self.imported_files()
        self.assertEqual((kept.read_bytes(), self.file.exists()), (original, False))

    def test_a_busy_runner_lock_skips_the_import(self) -> None:
        """An older runner mid-entry holds the lock and keeps its file until the next pass."""
        self.write_file(self.old(1, self.feature))
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
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, claim="deliver")
        before = self.rows()
        self.git_verbs.clear()
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
        self.assertEqual((self.rows(), "push" in self.git_verbs), (before, False))


class ShipProcess(Lane):
    def test_the_answer_is_parsed_and_the_whole_output_kept(self) -> None:
        from unittest import mock

        log = self.tmp / "logs/step.log"
        with mock.patch.dict(os.environ, self.environ):
            answer = sd_lane.ship_process(["-C", str(self.repo), "lane", "list"], log, 120)
        self.assertEqual((answer["ok"], answer["entries"]), (True, []))
        self.assertTrue(log.read_text(encoding="utf-8").startswith(f"$ sd-ship -C {self.repo} lane list\n{{"))

    def test_the_timeout_ends_what_sd_ship_started(self) -> None:
        """sd:3480. The timeout killed `sd-ship` alone; its gate's children ran on and held the gate slot."""
        fake, child = self.tmp / "bin", self.tmp / "child.pid"
        fake.mkdir()
        (fake / "sd-ship").write_text(
            "import pathlib, subprocess, sys, time\n"
            "spawned = subprocess.Popen(['sleep', '60'])\n"
            f"pathlib.Path({str(child)!r}).write_text(str(spawned.pid))\n"
            "print('started', flush=True)\n"
            "time.sleep(60)\n", encoding="utf-8")
        log = self.tmp / "logs/step.log"
        with mock.patch.object(sd_lane, "BIN", fake):
            answer = sd_lane.ship_process(["prepare", "--json"], log, 2)
        pid = int(child.read_text(encoding="utf-8"))
        alive = True
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                alive = False
                break
            time.sleep(0.1)
        if alive:
            os.kill(pid, signal.SIGKILL)
        self.assertFalse(alive, "sd-ship's child outlived the step's timeout")
        self.assertEqual(answer["ok"], False)
        self.assertIn("timed out after 2", log.read_text(encoding="utf-8"))
        self.assertIn("started", log.read_text(encoding="utf-8"))


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

    def watch_items(self, cwd: pathlib.Path, *items: int) -> tuple[int, list[str]]:
        import argparse  # noqa: PLC0415
        parser = argparse.ArgumentParser()
        sd_lane.add_lane_verbs(parser.add_subparsers(dest="command"))
        argv = ["lane", "watch", *[word for item in items for word in ("--item", str(item))]]
        with contextlib.chdir(cwd), mock.patch.dict(os.environ, self.environ), \
                contextlib.redirect_stdout(io.StringIO()) as said:
            code = sd_lane.lane_main(parser.parse_args(argv))
        return code, said.getvalue().splitlines()

    def test_watch_item_waits_for_each_item_and_outlives_the_worktree_it_started_in(self) -> None:
        """sd:3565. A hand-run loop of `lane list` from a builder worktree broke once the merge removed it."""
        one, two = self.worktree("one"), self.worktree("two")
        sd_lane.enqueue_entry(one, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(1, "prepare")] = {"ok": False, "phase": "review_blocked", "error": "a blocking finding"}
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        del self.answers[(1, "prepare")]
        sd_lane.retry(self.repo, 1, self.environ)  # the failed entry is older: it ends nothing
        sd_lane.enqueue_entry(two, 2, "two", self.body, self.environ, manual=True, claim="deliver")
        self.answers[(2, "prepare")] = {"ok": False, "phase": "review_blocked", "error": "a blocking finding"}
        pauses: list[int] = []

        def pause() -> None:
            pauses.append(len(pauses))
            sd_lane.run_lane(self.repo, self.environ, self.ship)
            git(self.repo, "worktree", "remove", "--force", str(one))
        with mock.patch.object(sd_lane, "watch_pause", pause):
            code, lines = self.watch_items(one, 1, 2)
        self.assertEqual((code, pauses), (1, [0]))
        self.assertEqual(lines, ["sd:1 merged at merged-1", "sd:2 failed: a blocking finding"])
        self.assertEqual(self.watch_items(self.repo, 1), (0, ["sd:1 merged at merged-1"]))

    def test_watch_item_skips_cancelled_entries_and_ends_an_item_with_none_at_once(self) -> None:
        sd_lane.enqueue_entry(self.feature, 3, "three", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.run_lane(self.repo, self.environ, self.ship)
        sd_lane.enqueue_entry(self.feature, 3, "three", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.cancel(self.repo, 3, self.environ)
        sd_lane.enqueue_entry(self.feature, 4, "four", self.body, self.environ, manual=True, claim="deliver")
        sd_lane.cancel(self.repo, 4, self.environ)
        with mock.patch.object(sd_lane, "watch_pause", side_effect=AssertionError("waited")):
            code, lines = self.watch_items(self.repo, 3, 4, 5)
        self.assertEqual(code, 1)
        self.assertEqual(lines, ["sd:3 merged at merged-3", "sd:4 none: no lane entry that is not cancelled",
                                 "sd:5 none: no lane entry that is not cancelled"])

    def test_watch_item_reads_again_after_a_hub_fault(self) -> None:
        """A read the hub did not answer is unknown, not an end."""
        sd_lane.enqueue_entry(self.feature, 1, "one", self.body, self.environ, manual=True, claim="deliver")
        on_hub, faults = sd_lane.on_hub, [sd_lane.LaneError("down", code=sd_lane.HUB_UNAVAILABLE)]

        def flaky(queue: sd_lane.Queue, work: Any) -> Any:
            if faults:
                raise faults.pop()
            return on_hub(queue, work)
        with mock.patch.object(sd_lane, "on_hub", flaky), mock.patch.object(
                sd_lane, "watch_pause", lambda: sd_lane.run_lane(self.repo, self.environ, self.ship)):
            code, lines = self.watch_items(self.repo, 1)
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["hub unavailable: down; reading again", "sd:1 merged at merged-1"])


class HostedOrder(Lane):
    def test_the_lane_that_waited_longest_runs_first(self) -> None:
        """sd:3481. Lanes ran in path order; one that kept refilling held a later lane's entries for 90 minutes."""
        later = self.tmp / "zeta"
        later.mkdir()
        git(later, "init", "-q", "-b", "main")
        git(later, "remote", "add", "origin", "https://github.com/example/zeta.git")
        import sd_db
        connection = sd_db.connect(home=self.tmp)
        try:
            for path, remote in ((self.repo, "pack"), (later, "zeta")):
                sd_db.upsert_repo(connection, str(path), remote=f"https://github.com/example/{remote}.git", managed=1)
        finally:
            connection.close()
        for checkout, item, stamp in ((self.repo, 1, "2026-10-12T21:00:00Z"), (later, 2, "2026-10-12T20:35:00Z")):
            sd_lane.add_entry(sd_lane.queue_for(checkout, self.environ),
                              {"id": f"e{item}", "item": item, "status": "pending", "enqueued_at": stamp})
        order: list[pathlib.Path] = []

        def recorded(checkout: pathlib.Path, *args: Any) -> dict:
            order.append(checkout)
            return {"ran": []}
        with mock.patch.object(sd_lane, "run_lane", recorded):
            sd_lane.run_hosted(self.environ, self.ship)
        self.assertEqual(order, [later, self.repo])


class Bounds(unittest.TestCase):
    def test_an_entry_started_inside_the_budget_ends_before_the_job_limit(self) -> None:
        """sd:3481. The longest entry seen took 64.3 minutes; the lane-run job TERMs its runner at 120."""
        longest_seen, job_limit = 64.3 * 60, 120 * 60
        self.assertLess(sd_lane.RUN_BUDGET_SECONDS + longest_seen + sd_lane.POST_MERGE_SECONDS, job_limit)

    def test_prepare_and_merge_bounds_cover_a_gates_slot_wait(self) -> None:
        """sd:2611: the gate under them queues for up to `GATE_SLOT_SECONDS` before its check starts."""
        for bound in (sd_lane.PREPARE_SECONDS, sd_lane.MERGE_SECONDS):
            self.assertGreaterEqual(bound, 3 * 3600 + sd_lane.sd_lib.GATE_SLOT_SECONDS)

    def test_a_gate_child_that_starts_after_the_cancel_is_ended_at_once(self) -> None:
        """sd:3361, the step between the cancel and the gate's `sd-check` start: the late group is ended too."""
        go, answers = threading.Event(), []

        def target() -> None:
            go.wait(10)
            answers.append(sd_lane.gate_run()([sys.executable, "-c", "import time; time.sleep(60)"],
                                              dict(os.environ), pathlib.Path.cwd(), 120))
        gate = sd_lane.SpeculativeGate(target, "late")
        gate.start()
        cancelled: list[bool] = []
        canceller = threading.Thread(target=lambda: cancelled.append(gate.cancel_gate()))
        started = time.monotonic()
        canceller.start()
        for _ in range(1000):  # bounded: a cancel that never lands fails below rather than hangs
            if gate.cancelled:
                break
            time.sleep(0.01)
        go.set()
        canceller.join(60)
        self.assertEqual(cancelled, [True])
        self.assertLess(time.monotonic() - started, sd_lane.CANCEL_SECONDS)
        self.assertNotEqual(answers[0][0], 0)

    def test_a_gate_child_that_ignores_sigterm_is_killed(self) -> None:
        """sd:3361, the SIGKILL step: a child that ignores SIGTERM is killed one bound later."""
        child = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
        answers: list[Any] = []
        gate = sd_lane.SpeculativeGate(lambda: answers.append(sd_lane.gate_run()(
            [sys.executable, "-c", child], dict(os.environ), pathlib.Path.cwd(), 120)), "deaf")
        gate.start()
        for _ in range(500):  # bounded: the group is recorded once the child starts
            if gate.group is not None:
                break
            time.sleep(0.01)
        time.sleep(0.5)  # the child has installed its handler
        started = time.monotonic()
        with mock.patch.object(sd_lane, "CANCEL_SECONDS", 1):
            self.assertTrue(gate.cancel_gate())
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(answers[0][0], -signal.SIGKILL)

    def test_a_gate_that_outlives_both_signals_is_reported_and_left(self) -> None:
        """sd:3361, the last step: a gate still running after SIGKILL does not hold the run; the answer says so."""
        release = threading.Event()
        gate = sd_lane.SpeculativeGate(lambda: release.wait(60), "stuck")
        gate.start()
        try:
            with mock.patch.object(sd_lane, "CANCEL_SECONDS", 0.2):
                answer = sd_lane.finish_speculation(gate, {"stopped": "BuildMismatch"})
            self.assertEqual(answer["speculative_gate"], "still ending 0.4s after SIGKILL; the lock is freed anyway")
        finally:
            release.set()
            gate.join(10)


if __name__ == "__main__":
    unittest.main()
