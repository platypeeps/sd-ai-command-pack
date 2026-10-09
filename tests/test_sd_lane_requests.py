"""Lane requests (sd:2704, implement step 6): a satellite asks the hub's lane to merge.

The satellite writes `lane-request:v1:<slug>:<item>` with `sd-ship lane
request`; the hub's `lane run` takes it in before each claim (design.md,
"Intake").
A real workflow database in a temporary folder holds the rows; `sd-ship` is
the lane suite's recorder, so nothing reaches GitHub.
"""

from __future__ import annotations

import contextlib
import fcntl
import io
import json
import pathlib
import subprocess
import types
from unittest import mock

from sd_db import connect, initialise, upsert_repo
from sd_db import ship as receipts

from tests import test_sd_lane as lane_suite

sd_lane = lane_suite.sd_lane
git = lane_suite.git
SLUG = "fixture/repo"
URL = f"https://github.com/{SLUG}.git"
HUB = "hub.example.test:8769"
SATELLITE = {"hostname": "satellite.example.test", "login": "fixture@example.test", "address": "192.0.2.10"}


class Requests(lane_suite.Lane):
    """The lane suite's repository with a GitHub-named origin, a workflow database and a pushed `topic` branch."""

    def setUp(self) -> None:
        super().setUp()
        self.origin = self.tmp / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        # `origin` names GitHub, so the slug resolves; Git reaches the bare repository in its place.
        git(self.repo, "config", f"url.{self.origin}.insteadOf", URL)
        git(self.repo, "remote", "add", "origin", URL)
        git(self.repo, "push", "-q", "origin", "main")
        self.topic = self.worktree("topic")
        git(self.topic, "commit", "-q", "--allow-empty", "-m", "topic")
        git(self.topic, "push", "-q", "origin", "topic")
        self.head = git(self.topic, "rev-parse", "HEAD")
        self.database = self.tmp / "sd.db"
        initialise(self.database)
        self.connection = connect(self.database)
        self.addCleanup(self.connection.close)
        upsert_repo(self.connection, str(self.repo), remote=URL, ci="local", managed=1)
        self.hub = sd_lane.Hub(self.connection, receipts, SLUG, self.repo)
        self.path = sd_lane.queue_path(self.repo, self.environ)
        self.opt_in = "accept"
        self.gates: list[tuple] = []
        # The lane host is read from this database, never the machine's (sd:3003).
        for patcher in (mock.patch.object(sd_lane.sd_lib, "repo_satellite_gate", lambda connection, root: self.opt_in),
                        mock.patch("sd_db.database.default_path", lambda *args, **kwargs: self.database)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def gate(self, root: pathlib.Path, head: str, base: str) -> dict:
        self.gates.append((root, head, base))
        return {"status": "success"}

    def prepared(self, item: int = 7, branch: str = "topic", head: str | None = None, phase: str = "ready_to_send") -> None:
        """The `ship:` row a satellite's prepare leaves."""
        key = receipts.receipt_key(SLUG, branch, item)
        revision, row = receipts.read(self.connection, key)
        receipts.save(self.connection, key, revision, {**row, "repository": SLUG, "branch": branch, "item": item,
                                                      "phase": phase, "head": head or self.head, "base": "main",
                                                      "title": f"sd:{item} from the satellite"})

    def ask(self, item: int = 7, **fields) -> int:
        """A request row as `lane request` writes it; returns its revision."""
        key = sd_lane.request_key(SLUG, item)
        revision, _ = receipts.read(self.connection, key)
        return receipts.save(self.connection, key, revision, {
            "writer": sd_lane.REQUEST_WRITER, "repository": SLUG, "item": item, "branch": "topic", "head": self.head,
            "base": "main", "authority": "manual", "satellite": SATELLITE,
            "requested_at": sd_lane.stamp_now(), "status": "requested", **fields})

    def row(self, item: int = 7) -> dict:
        return receipts.read(self.connection, sd_lane.request_key(SLUG, item))[1]

    def intake(self, hub: sd_lane.Hub | None = None) -> list[dict]:
        return sd_lane.intake(hub or self.hub, self.path)


class Intake(Requests):
    def assert_refused(self, code: str) -> None:
        row = self.row()
        self.assertEqual((row["status"], row["code"]), ("refused", code))
        self.assertTrue(row["reason"])
        self.assertEqual(row["next_action"], sd_lane.REFUSAL_ACTIONS[code])
        self.assertEqual(self.entries(), [])

    def test_a_valid_request_is_queued_as_a_satellite_entry(self) -> None:
        self.prepared()
        revision = self.ask()
        [answer] = self.intake()
        [entry] = self.entries()
        self.assertEqual({key: entry[key] for key in ("worktree", "item", "gate", "branch", "base", "expected_head",
                                                      "authority", "request", "status")},
                         {"worktree": str(self.repo), "item": 7, "gate": "satellite", "branch": "topic", "base": "main",
                          "expected_head": self.head, "authority": "manual",
                          "request": {"key": sd_lane.request_key(SLUG, 7), "revision": revision}, "status": "pending"})
        row = self.row()
        self.assertEqual((answer["status"], row["status"], row["entry"]),
                         ("queued", "queued", {"enqueued_at": entry["enqueued_at"], "revision": revision}))
        self.assertEqual(self.intake(), [])  # a queued request is not taken in twice

    def test_a_repository_not_opted_in_is_refused(self) -> None:
        self.prepared()
        self.ask()
        self.opt_in = "off"
        self.intake()
        self.assert_refused("satellite_gate_off")

    def test_a_repository_that_does_not_gate_locally_is_refused(self) -> None:
        self.connection.execute("UPDATE repo SET ci = 'github'")
        self.connection.commit()
        self.prepared()
        self.ask()
        self.intake()
        self.assert_refused("satellite_gate_off")

    def test_a_malformed_request_is_refused_before_any_git_call_on_its_names(self) -> None:
        for fields in ({"branch": "--upload-pack=touch /tmp/x"}, {"branch": "a..b"}, {"base": "-main"},
                       {"head": self.head[:12]}, {"item": "7"}, {"authority": "everyone"}, {"writer": "sd-check"},
                       {"satellite": {"hostname": "satellite.example.test", "error": "TailnetError: not running"}},
                       {"satellite": None}):
            with self.subTest(fields=fields):
                self.prepared()
                self.ask(**fields)
                self.intake()
                self.assert_refused("invalid_request")

    def test_a_request_whose_base_is_not_the_ship_rows_is_refused(self) -> None:
        """sd:2782 L2: the merge checks the ship: row's base, so intake must not pre-check another one."""
        self.prepared()
        self.ask(base="release")
        self.intake()
        self.assert_refused("invalid_request")
        self.assertIn("release", self.row()["reason"])

    def test_a_request_whose_ship_row_is_not_ready_at_its_head_is_refused(self) -> None:
        for prepare in (lambda: None, lambda: self.prepared(phase="push_dispatch"),
                        lambda: self.prepared(head="0" * 40)):
            with self.subTest(prepare=prepare):
                prepare()
                self.ask()
                self.intake()
                self.assert_refused("satellite_not_prepared")

    def test_a_second_request_supersedes_the_pending_entry(self) -> None:
        self.prepared()
        first = self.ask()
        self.intake()
        second = self.ask()
        self.intake()
        old, new = self.entries()
        self.assertEqual((old["status"], old["superseded_by"]),
                         ("cancelled", {"key": sd_lane.request_key(SLUG, 7), "revision": second}))
        self.assertEqual((old["request"]["revision"], new["request"]["revision"], new["status"]),
                         (first, second, "pending"))
        self.assertEqual(self.row()["entry"]["revision"], second)

    def test_a_running_entry_leaves_the_request_requested(self) -> None:
        self.prepared()
        self.ask()
        self.intake()
        sd_lane.update(self.path, lambda rows: rows[0].update(status="running"))
        again = self.ask()
        [answer] = self.intake()
        self.assertEqual((answer["status"], [entry["status"] for entry in self.entries()]), ("requested", ["running"]))
        self.assertIn("is running", answer["reason"])
        self.assertEqual((self.row()["status"], receipts.read(self.connection, sd_lane.request_key(SLUG, 7))[0]),
                         ("requested", again))

    def test_a_crash_between_the_queue_write_and_the_row_write_takes_the_request_in_once(self) -> None:
        self.prepared()
        revision = self.ask()

        def crash_on_queued(connection, key, previous, value):
            if value.get("status") == "queued":
                raise RuntimeError("the hub stopped here")
            return receipts.save(connection, key, previous, value)
        crashing = types.SimpleNamespace(read=receipts.read, receipt_key=receipts.receipt_key, save=crash_on_queued)
        [answer] = self.intake(sd_lane.Hub(self.connection, crashing, SLUG, self.repo))
        self.assertIn("the hub stopped here", answer["error"])
        self.assertEqual((self.row()["status"], len(self.entries())), ("requested", 1))
        [answer] = self.intake()
        [entry] = self.entries()
        self.assertEqual((answer["status"], entry["status"], entry["request"]["revision"]), ("queued", "pending", revision))
        self.assertEqual((self.row()["status"], self.row()["entry"]["revision"]), ("queued", revision))

    def test_a_revision_conflict_on_the_row_is_retried_at_the_next_intake(self) -> None:
        self.prepared()
        self.ask()
        raced: list[int] = []

        def satellite_writes_first(connection, key, previous, value):
            if not raced:
                raced.append(self.ask())  # the satellite asks again while intake decides
            return receipts.save(connection, key, previous, value)
        racing = types.SimpleNamespace(read=receipts.read, receipt_key=receipts.receipt_key, save=satellite_writes_first)
        [answer] = self.intake(sd_lane.Hub(self.connection, racing, SLUG, self.repo))
        self.assertIn("changed concurrently", answer["error"])
        self.assertEqual(self.row()["status"], "requested")
        self.intake()
        old, new = self.entries()
        self.assertEqual((old["status"], new["status"], new["request"]["revision"]), ("cancelled", "pending", raced[0]))
        self.assertEqual((self.row()["status"], self.row()["entry"]["revision"]), ("queued", raced[0]))

    def test_a_database_that_will_not_answer_leaves_the_queue_alone(self) -> None:
        def refuse(*args):
            raise OSError("the database is locked")
        silent = sd_lane.Hub(types.SimpleNamespace(execute=refuse), receipts, SLUG, self.repo)
        [answer] = self.intake(silent)
        self.assertEqual((answer["status"], self.entries()), ("unread", []))
        self.assertIn("the database is locked", answer["error"])

    def test_another_repositorys_requests_are_not_read(self) -> None:
        self.prepared()
        key = sd_lane.request_key("fixture/other", 7)
        receipts.save(self.connection, key, 0, {"repository": "fixture/other", "item": 7, "status": "requested"})
        self.assertEqual(self.intake(), [])
        self.assertEqual(receipts.read(self.connection, key)[1]["status"], "requested")


class PlainRun(Requests):
    def test_a_plain_run_runs_hub_and_satellite_entries(self) -> None:
        hub_tree = self.worktree("hubitem")
        sd_lane.enqueue_entry(hub_tree, 3, "hub item", self.body, self.environ, manual=True, claim="deliver")
        self.prepared()
        self.ask()
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship, self.gate, hub=self.hub)
        self.assertEqual([(row["item"], row["status"]) for row in answer["ran"]], [(3, "merged"), (7, "merged")])

    def test_hosted_parses_and_satellite_only_stays_until_the_jobs_move(self) -> None:
        """sd:3003, review round 1: scheduled jobs still pass `--satellite-only`; the two flags do not combine."""
        self.assertTrue(sd_lane_parser().parse_args(["lane", "run", "--hosted"]).hosted)
        self.assertTrue(sd_lane_parser().parse_args(["lane", "run", "--satellite-only"]).satellite_only)
        with mock.patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
            sd_lane_parser().parse_args(["lane", "run", "--hosted", "--satellite-only"])


class SatelliteOnly(Requests):
    """Ruling Q4: the scheduled run takes in and runs satellite entries; hub entries wait for an integrator.

    Kept until every scheduled job runs `--hosted` (review round 1); design.md, "What retires", row 2.
    """

    def queue_hub_then_satellite(self) -> None:
        hub_tree = self.worktree("hubitem")
        sd_lane.enqueue_entry(hub_tree, 3, "hub item", self.body, self.environ, manual=True, claim="deliver")
        self.prepared()
        self.ask()

    def test_a_hub_entry_ahead_stays_pending_in_place_and_nothing_is_prepared_or_gated(self) -> None:
        self.queue_hub_then_satellite()
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship, self.gate, satellite_only=True, hub=self.hub)
        hub_entry, satellite = self.entries()
        self.assertEqual((hub_entry["item"], hub_entry["status"]), (3, "pending"))
        self.assertNotIn("speculation", hub_entry)
        self.assertEqual((satellite["item"], satellite["status"], [row["item"] for row in answer["ran"]]),
                         (7, "merged", [7]))
        self.assertNotIn("prepare", [call[2] for call in self.calls])
        self.assertEqual(self.gates, [])
        self.assertEqual([row["status"] for row in answer["intake"]], ["queued"])

    def test_a_satellite_only_run_with_only_hub_entries_exits_at_once(self) -> None:
        sd_lane.enqueue_entry(self.worktree("hubitem"), 3, "hub item", self.body, self.environ, manual=True,
                              claim="deliver")
        answer = sd_lane.run_lane(self.repo, self.environ, self.ship, self.gate, satellite_only=True, hub=self.hub)
        self.assertEqual((answer["ran"], self.calls, self.entries()[0]["status"]), ([], [], "pending"))

    def test_the_cli_passes_satellite_only_to_the_run(self) -> None:
        seen = []
        with mock.patch.object(sd_lane, "run_lane", lambda root, environ, **kwargs: seen.append(kwargs) or {}), \
                mock.patch.object(sd_lane.sd_lib, "repo_root", lambda start: self.repo), \
                mock.patch.object(sd_lane, "refuse_elsewhere", lambda root: None), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            for argv, expected in ((["run", "--satellite-only"], True), (["run"], False)):
                self.assertEqual(sd_lane.lane_main(sd_lane_parser().parse_args(["lane", *argv])), 0)
                self.assertEqual(seen.pop(), {"satellite_only": expected})


class HeldLock(Requests):
    """sd:2861: another ship operation's repository lock passes, so the merge waits for the next run."""

    def setUp(self) -> None:
        super().setUp()
        self.prepared()
        self.ask()
        self.answers[(7, "merge")] = {
            "ok": False, "error": f"{receipts.HELD} (pid 25080, sd-ship prepare --item 2816, held 110s); "
                                  "retry after it finishes", "workflow": {"blocker": {"code": "prerequisite_failed"}}}

    def run_once(self) -> dict:
        return sd_lane.run_lane(self.repo, self.environ, self.ship, self.gate, hub=self.hub)

    def test_a_held_lock_leaves_the_request_queued_for_the_next_run(self) -> None:
        self.run_once()
        [entry] = self.entries()
        self.assertEqual((entry["status"], entry["lock_retries"], self.row()["status"]), ("pending", 1, "queued"))
        self.assertIn(receipts.HELD, entry["reason"])
        self.assertEqual([call[2] for call in self.calls], ["merge"])  # once a run, not a spin
        del self.answers[(7, "merge")]
        self.run_once()
        self.assertEqual((self.entries()[0]["status"], self.row()["status"]), ("merged", "merged"))

    def test_a_lock_held_past_the_cap_fails_with_the_reason(self) -> None:
        sd_lane.intake(self.hub, self.path)

        def waited(entries: list[dict]) -> None:
            entries[0]["lock_retries"] = sd_lane.LOCK_RETRIES
        sd_lane.update(self.path, waited)
        self.run_once()
        [entry], row = self.entries(), self.row()
        self.assertEqual((entry["status"], row["status"], row["code"]), ("failed", "failed", "prerequisite_failed"))
        self.assertIn(f"still held after {sd_lane.LOCK_RETRIES} runs", row["reason"])


class PackDigest(Requests):
    def pack_row(self) -> dict:
        return receipts.read(self.connection, sd_lane_receipts().PACK_PREFIX + SLUG)[1]

    def test_a_run_publishes_the_hubs_pack_digest_at_its_start(self) -> None:
        with mock.patch.object(sd_lane_receipts(), "pack_bin", lambda own=False: "tree" if own else "f" * 64):
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship, self.gate, hub=self.hub)
        self.assertEqual(answer["pack"], "published")
        row = self.pack_row()
        self.assertEqual((row["writer"], row["pack_bin"]), ("sd-lane", "f" * 64))
        self.assertEqual(row["pack_rev"], git(sd_lane.BIN.parent, "rev-parse", "HEAD"))

    def test_a_pack_gating_itself_publishes_tree_as_its_receipts_bind(self) -> None:
        with mock.patch.object(sd_lane_receipts(), "gates_itself", lambda root, tree, pack: True):
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship, self.gate, hub=self.hub)
        self.assertEqual((answer["pack"], self.pack_row()["pack_bin"]), ("published", "tree"))

    def test_a_failed_digest_publishes_nothing_and_the_run_goes_on(self) -> None:
        with mock.patch.object(sd_lane_receipts(), "pack_bin", mock.Mock(side_effect=OSError("bin/ unreadable"))):
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship, self.gate, hub=self.hub)
        self.assertEqual(answer["pack"], "failed: OSError: bin/ unreadable")
        self.assertEqual(self.pack_row(), {})


class LaneHosts(Requests):
    """The request suite's fixture with `repo.lane_host` to set (sd:3003); it holds no test."""

    def lane_host(self, host: str | None) -> None:
        self.connection.execute("UPDATE repo SET lane_host = ?", (host,))
        self.connection.commit()

    def satellite(self) -> contextlib.ExitStack:
        """`served_by` names a hub for the database, wherever `sd_db` reads it."""
        stack = contextlib.ExitStack()
        for target in ("sd_db.database.served_by", "sd_db.ship.served_by"):
            stack.enter_context(mock.patch(target, lambda target, home=None: HUB, create=True))
        return stack

    def machines(self):
        """`(name, context factory, host the refusal names)` for each machine off the host."""
        self.lane_host("build-2")
        yield "the hub", contextlib.nullcontext, "build-2"
        self.lane_host(None)
        yield "a satellite", self.satellite, "the hub"

    def lane(self, *argv: str) -> tuple[int, dict]:
        with mock.patch.dict(sd_lane.os.environ, self.environ), \
                mock.patch.object(sd_lane.sd_lib, "repo_root", lambda start: self.topic), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as printed:
            code = sd_lane.lane_main(sd_lane_parser().parse_args(["lane", *argv]))
        return code, json.loads(printed.getvalue())


class OffTheLaneHost(LaneHosts):
    """sd:3003, acceptance 11: off the lane host `lane run` and the host verbs refuse `lane_elsewhere`.

    Two machines are off the host: the hub when `repo.lane_host` names
    another machine, and a satellite when it is NULL.
    """

    def test_a_run_off_the_host_refuses_before_intake_or_publication(self) -> None:
        self.prepared()
        revision = self.ask()
        pack = receipts.read(self.connection, sd_lane_receipts().PACK_PREFIX + SLUG)
        for machine, context, host in self.machines():
            with self.subTest(machine=machine), context():
                with self.assertRaises(sd_lane.LaneError) as refused:
                    sd_lane.run_lane(self.repo, self.environ, self.ship, self.gate, hub=self.hub)
                self.assertEqual(refused.exception.code, "lane_elsewhere")
                self.assertIn(f"The lane for {SLUG} runs on {host}, not on this machine.", str(refused.exception))
                self.assertIn("dashboard, Management", str(refused.exception))
        key = sd_lane.request_key(SLUG, 7)
        self.assertEqual((receipts.read(self.connection, key)[0], self.row()["status"]), (revision, "requested"))
        self.assertEqual(receipts.read(self.connection, sd_lane_receipts().PACK_PREFIX + SLUG), pack)
        self.assertEqual((self.entries(), self.calls), ([], []))

    def test_enqueue_and_the_reorder_verbs_refuse_and_run_refuses_from_the_cli(self) -> None:
        for machine, context, host in self.machines():
            for argv in (["enqueue", "--item", "7", "--title", "t", "--body-file", str(self.body), "--deliver"],
                         ["move", "7", "top"], ["hold", "7"], ["release", "7"], ["run"]):
                with self.subTest(machine=machine, verb=argv[0]), context():
                    code, answer = self.lane(*argv)
                    self.assertEqual((code, answer["ok"], answer.get("code")), (3, False, "lane_elsewhere"))
                    self.assertIn(f"runs on {host}, not on this machine", answer["error"])
        self.assertFalse(self.path.exists())

    def test_the_old_host_still_lists_and_cancels_after_a_move(self) -> None:
        """design.md, "Moving a lane", step 3: cancel each pending entry on the old host."""
        sd_lane.enqueue_entry(self.topic, 7, "t", self.body, self.environ, manual=True, claim="deliver")
        self.lane_host("build-2")
        code, listed = self.lane("list")
        self.assertEqual((code, [row["status"] for row in listed["entries"]]), (0, ["pending"]))
        code, cancelled = self.lane("cancel", "7")
        self.assertEqual((code, cancelled["status"]), (0, "cancelled"))

    def test_clones_that_disagree_refuse_lane_unknown_and_never_run_as_the_hub(self) -> None:
        sd_lane.enqueue_entry(self.topic, 7, "t", self.body, self.environ, manual=True, claim="deliver")
        clone = self.tmp / "clone"
        upsert_repo(self.connection, str(clone), remote=URL, managed=1)
        self.connection.execute("UPDATE repo SET lane_host = 'build-2' WHERE path = ?", (str(clone),))
        self.connection.commit()
        for argv in (["run"], ["enqueue", "--item", "8", "--title", "t", "--body-file", str(self.body), "--deliver"]):
            with self.subTest(verb=argv[0]):
                code, answer = self.lane(*argv)
                self.assertEqual((code, answer.get("code")), (3, "lane_unknown"))
                self.assertIn("name different lane hosts", answer["error"])
        self.assertEqual(([row["status"] for row in self.entries()], self.calls), (["pending"], []))

    def test_a_database_that_does_not_answer_refuses_lane_unknown(self) -> None:
        with mock.patch("sd_db.database.default_path", lambda *args, **kwargs: self.tmp / "absent" / "sd.db"):
            code, answer = self.lane("run")
        self.assertEqual((code, answer.get("code")), (3, "lane_unknown"))
        self.assertEqual(self.calls, [])

    def test_a_satellite_that_hosts_the_lane_runs_it_and_reads_no_request(self) -> None:
        """Acceptance 9's lane half: the host's run is the hub's run, without the hub's request rows."""
        self.prepared()
        revision = self.ask()
        sd_lane.enqueue_entry(self.worktree("hubitem"), 3, "hub item", self.body, self.environ, manual=True,
                              claim="deliver")
        self.lane_host("build-2")
        with self.satellite(), mock.patch.object(receipts, "this_host", lambda: "build-2"), \
                mock.patch.object(sd_lane, "default_hub", sd_lane_default_hub()):
            answer = sd_lane.run_lane(self.repo, self.environ, self.ship, self.gate)
        self.assertEqual([(row["item"], row["status"]) for row in answer["ran"]], [(3, "merged")])
        self.assertNotIn("intake", answer)
        self.assertEqual(receipts.read(self.connection, sd_lane.request_key(SLUG, 7))[0], revision)


class AMoveStopsTheRunner(LaneHosts):
    """sd:3003, acceptance 13: the runner reads the host before each claim, so a move lands between items."""

    def test_the_running_entry_finishes_and_no_next_entry_is_claimed(self) -> None:
        for item in (3, 4):
            sd_lane.enqueue_entry(self.worktree(f"item{item}"), item, "t", self.body, self.environ, manual=True,
                                  claim="deliver")
        recorder = self.ship

        def moved_mid_merge(argv: list[str], log: pathlib.Path) -> dict:
            if argv[2] == "merge":
                self.lane_host("build-2")  # the operator moves the lane while item 3 merges
            return recorder(argv, log)

        answer = sd_lane.run_lane(self.repo, self.environ, moved_mid_merge, self.gate, hub=self.hub)
        self.assertEqual([(row["item"], row["status"]) for row in answer["ran"]], [(3, "merged")])
        self.assertEqual([(row["item"], row["status"]) for row in self.entries()], [(3, "merged"), (4, "pending")])
        self.assertIn(f"The lane for {SLUG} runs on build-2", answer["stopped"])
        self.assertEqual([call[2] for call in self.calls], ["prepare", "merge"])


class HostedRun(LaneHosts):
    """sd:3003, acceptance 12: `lane run --hosted` runs only hosted lanes, in path order, past a busy one."""

    def lane_repo(self, name: str, item: int | None, host: str | None = None) -> pathlib.Path:
        """A managed repository with a GitHub origin and, with `item`, one queued entry."""
        root = self.tmp / name
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        git(root, "-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "a")
        url = f"https://github.com/example/{name}.git"
        git(root, "remote", "add", "origin", url)
        upsert_repo(self.connection, str(root), remote=url, managed=1)
        self.connection.execute("UPDATE repo SET lane_host = ? WHERE path = ?", (host, str(root)))
        self.connection.commit()
        if item is not None:
            sd_lane.enqueue_entry(root, item, name, self.body, self.environ, manual=True, claim="deliver")
        return root

    def test_only_hosted_lanes_run_in_path_order_and_a_busy_one_is_skipped(self) -> None:
        self.lane_repo("alpha", 11)
        self.lane_repo("bravo", 12, host="build-2")
        busy = self.lane_repo("charlie", 13)
        self.lane_repo("delta", None)
        self.lane_repo("echo", 15)
        with open(sd_lane.queue_path(busy, self.environ).parent / "runner.lock", "a", encoding="utf-8") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)  # another runner drains charlie's lane
            answer = sd_lane.run_hosted(self.environ, self.ship, self.gate)
        self.assertEqual([int(call[call.index("--item") + 1]) for call in self.calls], [11, 11, 15, 15])
        lanes = {pathlib.Path(lane["path"]).name: lane for lane in answer["lanes"]}
        self.assertEqual(sorted(lanes), ["alpha", "charlie", "delta", "echo", self.repo.name])
        self.assertEqual((lanes["delta"]["ran"], lanes[self.repo.name]["ran"]), ([], []))  # no queue file: still runs
        self.assertEqual([row["item"] for row in lanes["alpha"]["ran"]], [11])
        self.assertIn("another runner holds", lanes["charlie"]["busy"])
        self.assertEqual(sd_lane.read_queue(sd_lane.queue_path(self.tmp / "bravo", self.environ))[0]["status"], "pending")

    def test_a_hosted_lane_with_no_queue_file_takes_a_satellite_request_in(self) -> None:
        """Review round 1: `lane request` writes only a row, so a hosted lane that never queued here still runs."""
        self.prepared()
        self.ask()
        self.assertFalse(self.path.exists())
        with mock.patch.object(sd_lane, "default_hub", sd_lane_default_hub()):
            answer = sd_lane.run_hosted(self.environ, self.ship, self.gate)
        [lane] = answer["lanes"]
        self.assertEqual((lane["path"], [(row["item"], row["status"]) for row in lane["ran"]]),
                         (str(self.repo), [(7, "merged")]))
        self.assertEqual(self.row()["status"], "merged")

    def test_a_lane_whose_host_cannot_be_read_is_skipped_and_the_rest_run(self) -> None:
        self.lane_repo("alpha", 11)
        clone = self.tmp / "alpha-clone"
        upsert_repo(self.connection, str(clone), remote="https://github.com/example/alpha.git", managed=1)
        self.connection.execute("UPDATE repo SET lane_host = 'build-2' WHERE path = ?", (str(clone),))
        self.connection.commit()
        self.lane_repo("bravo", 12)
        answer = sd_lane.run_hosted(self.environ, self.ship, self.gate)
        skipped, ran, _ = answer["lanes"]  # the suite's own repository runs last, with nothing queued
        self.assertEqual((pathlib.Path(skipped["path"]).name, skipped["code"]), ("alpha", "lane_unknown"))
        self.assertEqual((pathlib.Path(ran["path"]).name, [row["item"] for row in ran["ran"]]), ("bravo", [12]))

    def test_a_repo_table_that_does_not_answer_runs_nothing(self) -> None:
        self.lane_repo("alpha", 11)
        with mock.patch("sd_db.database.default_path", lambda *args, **kwargs: self.tmp / "absent" / "sd.db"), \
                self.assertRaises(sd_lane.LaneError) as refused:
            sd_lane.run_hosted(self.environ, self.ship, self.gate)
        self.assertEqual((refused.exception.code, self.calls), ("lane_unknown", []))

    def test_the_cli_runs_from_any_folder(self) -> None:
        with mock.patch.object(sd_lane, "run_hosted", lambda environ: {"lanes": []}), \
                mock.patch.object(sd_lane.sd_lib, "repo_root", side_effect=AssertionError("read the cwd")), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as printed:
            code = sd_lane.lane_main(sd_lane_parser().parse_args(["lane", "run", "--hosted"]))
        self.assertEqual((code, json.loads(printed.getvalue())), (0, {"ok": True, "lanes": []}))


class RequestVerb(Requests):
    """`sd-ship lane request`, on the satellite's worktree of the item."""

    def request(self, served_by: str | None = HUB) -> dict:
        """`served_by` names the hub wherever `sd_db` reads it, `hosts_lane` included."""
        with mock.patch("sd_db.database.served_by", lambda target, home=None: served_by, create=True), \
                mock.patch("sd_db.ship.served_by", lambda target, home=None: served_by, create=True), \
                mock.patch.object(sd_lane_receipts(), "satellite_identity", lambda: SATELLITE):
            return sd_lane.request(self.topic, 7, manual=True, database=self.database)

    def test_a_prepared_item_writes_its_request_row(self) -> None:
        self.prepared()
        answer = self.request()
        row = self.row()
        self.assertEqual(answer["revision"], receipts.read(self.connection, sd_lane.request_key(SLUG, 7))[0])
        self.assertEqual({key: row[key] for key in ("writer", "repository", "item", "branch", "head", "base",
                                                    "authority", "status", "satellite")},
                         {"writer": "sd-lane-request", "repository": SLUG, "item": 7, "branch": "topic",
                          "head": self.head, "base": "main", "authority": "manual", "status": "requested",
                          "satellite": SATELLITE})
        [taken] = self.intake()
        self.assertEqual(taken["status"], "queued")

    def test_the_hub_is_refused_and_named_to_enqueue(self) -> None:
        self.prepared()
        with self.assertRaises(sd_lane.LaneError) as refused:
            self.request(served_by=None)
        self.assertEqual(refused.exception.code, "hub_request")
        self.assertIn("sd-ship lane enqueue", str(refused.exception))
        self.assertEqual(self.row(), {})

    def test_a_lane_the_hub_does_not_host_is_refused_and_writes_no_row(self) -> None:
        """Review round 1 class pass: only the hub's run takes requests in, so no other host drains the row."""
        self.prepared()
        self.connection.execute("UPDATE repo SET lane_host = 'build-2'")
        self.connection.commit()
        for here, says in (("build-2", "runs on this machine"), ("build-3", "runs on build-2, not on this machine")):
            with self.subTest(here=here), mock.patch.object(receipts, "this_host", lambda here=here: here):
                with self.assertRaises(sd_lane.LaneError) as refused:
                    self.request()
                self.assertEqual(refused.exception.code, "lane_elsewhere")
                self.assertIn(says, str(refused.exception))
        self.assertIn("sd-ship lane enqueue", str(refused.exception))
        self.assertEqual(self.row(), {})

    def test_an_item_not_ready_at_the_pushed_head_is_refused(self) -> None:
        git(self.topic, "commit", "-q", "--allow-empty", "-m", "pushed past the prepared head")
        git(self.topic, "push", "-q", "origin", "topic")
        for prepare in (lambda: None, lambda: self.prepared()):
            with self.subTest(prepare=prepare):
                prepare()
                with self.assertRaises(sd_lane.LaneError) as refused:
                    self.request()
                self.assertEqual(refused.exception.code, "satellite_not_prepared")
                self.assertEqual(self.row(), {})


def sd_lane_parser():
    import argparse

    parser = argparse.ArgumentParser()
    sd_lane.add_lane_verbs(parser.add_subparsers(dest="command"))
    return parser


def sd_lane_default_hub():
    """The real `default_hub`, which the lane suite replaces for every test."""
    return sd_lane_default_hub.real


sd_lane_default_hub.real = sd_lane.default_hub


def sd_lane_receipts():
    import sd_gate_receipts

    return sd_gate_receipts
