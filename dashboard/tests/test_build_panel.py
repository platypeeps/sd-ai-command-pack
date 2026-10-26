"""The Build press on Tasks and the Builds panel on Queue (pack sd:6095), over real HTTP on a disposable store.

`builds.kickstart` is replaced, so nothing reaches launchctl; the room's gate and sessions are seams of `plan`.
"""

from pathlib import Path
from unittest.mock import patch

from sd_db import build, ship, upsert_repo
from sd_db.writes import now as clock
from sd_db.workflow import item_state
from sd_dashboard import builds

from support import NOW
from test_workflow_actions import BrowserSession

REPO = "/fixture/repos/alpha"
IDLE = {"load": 1.0, "load_cap": 40.0, "interactive": []}


class Fixture(BrowserSession):
    def setUp(self):
        super().setUp()
        upsert_repo(self.connection, REPO, remote="/fixture/remote-alpha", managed=1)
        self.kicks = []
        kick = patch.object(builds, "kickstart", lambda: self.kicks.append(1) or {"ok": True, "service": "x", "why": ""})
        kick.start()
        self.addCleanup(kick.stop)

    def ready(self, status="ready", **columns):
        return self.item("Build me", kind="task", status=status, repo=REPO, **columns)

    def revision(self, item):
        return item_state(self.connection, item)["revision"]

    def builds_of(self, item):
        return self.connection.execute("SELECT COUNT(*) FROM assignment WHERE item = ? AND scope = 'build'",
                                       (item,)).fetchone()[0]



class BuildRoutes(Fixture):
    def test_build_refuses_a_non_ready_item_with_409_and_writes_nothing(self):
        """Slice 4's fail-first: a press with a planning item is a 409, and no item of the selection is queued."""
        ready, planning = self.ready(), self.ready(status="planning")
        status, _, body = self.post("/api/tasks/build", {"items": [ready, planning], "revisions": {
            str(ready): self.revision(ready), str(planning): self.revision(planning)}})
        self.assertEqual(status, 409, body)
        self.assertIn(f"item {planning} is planning", body["error"])
        self.assertEqual((self.builds_of(ready), self.builds_of(planning), self.kicks), (0, 0, []))

    def test_build_refuses_a_stale_revision_with_409(self):
        item = self.ready()
        before = self.revision(item)
        self.connection.execute("UPDATE item SET title = 'moved' WHERE id = ?", (item,))
        status, _, body = self.post("/api/tasks/build", {"items": [item], "revisions": {str(item): before}})
        self.assertEqual((status, self.builds_of(item)), (409, 0), body)

    def test_build_queues_each_item_and_kickstarts_the_dispatcher(self):
        first, second = self.ready(), self.ready()
        status, _, body = self.post("/api/tasks/build", {"items": [first, second], "revisions": {
            str(first): self.revision(first), str(second): self.revision(second)}})
        self.assertEqual(status, 200, body)
        self.assertEqual([(row["item"], row["status"]) for row in body["queued"]], [(first, "queued"), (second, "queued")])
        self.assertEqual((body["kickstart"]["ok"], len(self.kicks)), (True, 1))
        self.assertEqual((self.builds_of(first), self.builds_of(second)), (1, 1))

    def test_build_refuses_a_malformed_body_with_400(self):
        item = self.ready()
        for payload in ({"items": [item]}, {"items": [], "revisions": {}}, {"items": [item, item], "revisions": {}},
                        {"items": ["1"], "revisions": {}}):
            status, _, body = self.post("/api/tasks/build", payload)
            self.assertEqual(status, 400, (payload, body))
        self.assertEqual(self.builds_of(item), 0)

    def test_the_plan_bundles_by_repository_and_names_each_refusal(self):
        items = [self.ready() for _ in range(4)]
        planning = self.ready(status="planning")
        out = builds.plan(self.connection, items + [planning], now=NOW,
                          sessions=lambda connection, *, now: {"sessions": [], "builders": {"running": 0, "why": ""}},
                          gate=lambda: {"load": [1.0, 1.0, 1.0], "load_max": 40.0})
        self.assertEqual([[row["id"] for row in bundle["items"]] for bundle in out["bundles"]], [items[:3], items[3:]])
        self.assertEqual({bundle["model"] for bundle in out["bundles"]}, {"opus"})
        self.assertEqual([row["id"] for row in out["refused"]], [planning])
        self.assertEqual((out["room"]["machine"], out["room"]["why"], out["bundles"][0]["room"]), (6, "", 3))

    def test_the_plan_shows_no_room_when_the_load_was_not_read(self):
        out = builds.plan(self.connection, [self.ready()], now=NOW,
                          sessions=lambda connection, *, now: {"sessions": [], "builders": {"running": 0, "why": ""}},
                          gate=lambda: {})
        self.assertEqual((out["room"]["machine"], out["room"]["why"], out["bundles"][0]["room"]),
                         (0, "the load was not read", 0))

    def test_the_plan_route_reads_its_items(self):
        item = self.ready()
        with patch.object(builds, "_room", lambda connection, **_: {"machine": 6, "used": {}, "held": [], "why": ""}):
            status, _, body = self.request(f"/api/tasks/build/plan?items={item}", headers={"Cookie": self.cookie})
        self.assertEqual(status, 200, body)
        self.assertIn('"bundles"', body)
        status, _, _ = self.request("/api/tasks/build/plan?items=abc", headers={"Cookie": self.cookie})
        self.assertEqual(status, 400)


class BuildsPanel(Fixture):
    def claimed(self, items):
        build.queue(self.connection, items, who="fixture")
        return build.claim(self.connection, owner="fixture", root=self.path.parent / "worktrees", **IDLE)

    def blocked(self, items):
        """A run lost twice at one step: blocked, released, its items blocked (the reap's second loss)."""
        run = self.claimed(items)
        build.write(self.connection, run["id"], step="building")
        retry = build.reap(self.connection, now="2099-01-01T00:00:00Z")[0]["retry"]
        build.reap(self.connection, now="2099-01-02T00:00:00Z")
        return build.run(self.connection, retry)

    def panel(self, now="2099-01-02T01:00:00Z"):
        return builds.panel(self.connection, now=now)

    def test_an_open_run_is_a_row_with_its_items_step_state_and_cancel(self):
        items = [self.ready(), self.ready()]
        run = self.claimed(items)
        out = builds.panel(self.connection, now=run["created_at"])
        self.assertEqual(out["error"], "")
        row = out["runs"][0]
        self.assertEqual((row["run"], [m["item"] for m in row["items"]], row["step"], row["state"]),
                         (run["id"], items, "claimed", "working"))
        self.assertEqual((row["cancel"]["assignment"], row["cancel"]["allowed"]), (run["assignment"], True))
        status, _, body = self.post(f"/api/assignments/{run['assignment']}/cancel",
                                    {"revision": row["cancel"]["revision"]})
        self.assertEqual(status, 200, body)
        self.assertIsNotNone(build.run(self.connection, run["id"])["cancel_requested"])
        again = builds.panel(self.connection, now=run["created_at"])["runs"][0]["cancel"]
        self.assertFalse(again["allowed"])

    def test_a_silent_supervisor_is_lost_and_a_quiet_builder_log_is_stalled(self):
        run = self.claimed([self.ready()])
        self.assertEqual(self.panel()["runs"][0]["state"], "lost")
        log = self.path.parent / "run.jsonl"
        log.write_text("{}\n")
        build.write(self.connection, run["id"], step="building", log_path=str(log),
                    heartbeat_at="2099-01-02T00:59:30Z")
        import os
        os.utime(log, (0, 0))
        self.assertEqual(self.panel()["runs"][0]["state"], "stalled")

    def test_an_open_question_makes_a_run_wait_on_the_operator(self):
        item = self.ready()
        run = self.claimed([item])
        build.write(self.connection, run["id"], heartbeat_at="2099-01-02T00:59:30Z")
        self.note(item, "Which option?", kind="question")
        row = self.panel()["runs"][0]
        self.assertEqual(row["state"], "waiting")
        self.assertIn("question note", row["why"])

    def test_a_run_whose_branch_shipped_carries_its_pull_request_from_the_ship_receipt(self):
        """Pack sd:6020 ruling #31553: the row's Open PR reads `sd-ship`'s receipt for the branch; nothing asks GitHub."""
        items = [self.ready(), self.ready()]
        run = self.claimed(items)
        self.assertEqual(self.panel(run["created_at"])["runs"][0]["pull"], "")  # a remote that is not GitHub's
        upsert_repo(self.connection, REPO, remote="https://github.com/example/alpha.git", managed=1)
        self.assertEqual(self.panel(run["created_at"])["runs"][0]["pull"], "")  # never shipped
        url = "https://github.com/example/alpha/pull/7"
        # The lane names an entry by the first member the branch delivers, which need not be the lead.
        ship.save(self.connection, ship.receipt_key("example/alpha", run["branch"], items[1]), 0, {
            "repository": "example/alpha", "branch": run["branch"], "item": items[1],
            "pull_request": {"number": 7, "repository": "example/alpha", "base": "main", "url": url}})
        self.assertEqual(self.panel(run["created_at"])["runs"][0]["pull"], url)
        build.end(self.connection, run["id"], "done", "landed")
        self.assertEqual(self.panel(clock())["recent"][0]["pull"], url)

    def test_the_pull_request_lookup_matches_every_stored_form_of_the_repository(self):
        """A repository registered by its `~/` key still finds its remote from the absolute form a run may hold."""
        absolute = str(Path.home() / "repos" / "example-beta")
        upsert_repo(self.connection, "~/repos/example-beta", remote="https://github.com/example/beta.git", managed=1)
        url = "https://github.com/example/beta/pull/9"
        ship.save(self.connection, ship.receipt_key("example/beta", "build-1", 1), 0, {
            "repository": "example/beta", "branch": "build-1", "item": 1,
            "pull_request": {"number": 9, "repository": "example/beta", "base": "main", "url": url}})
        self.assertEqual(build.pull_url(self.connection, absolute, "build-1", [1]), url)

    def test_retry_on_a_blocked_run_queues_its_items_again(self):
        items = [self.ready(), self.ready()]
        run = self.blocked(items)
        self.assertEqual([item_state(self.connection, i)["item"]["status"] for i in items], ["blocked", "blocked"])
        recent = self.panel(clock())["recent"]
        self.assertEqual((recent[0]["outcome"], recent[0]["retry"]["allowed"]), ("interrupted", True))
        status, _, body = self.post("/api/queue/builds/retry", {"assignment": run["assignment"],
                                                               "revision": recent[0]["retry"]["revision"]})
        self.assertEqual(status, 200, body)
        self.assertEqual(sorted(row["item"] for row in body["queued"]), items)
        self.assertEqual([item_state(self.connection, i)["item"]["status"] for i in items], ["ready", "ready"])
        queued = self.connection.execute("SELECT COUNT(*) FROM assignment WHERE scope = 'build' AND status = 'queued'")
        self.assertEqual(queued.fetchone()[0], 2)
        self.assertEqual(len(self.kicks), 1)
        status, _, body = self.post("/api/queue/builds/retry", {"assignment": run["assignment"],
                                                               "revision": recent[0]["retry"]["revision"]})
        self.assertEqual(status, 409, body)

    def test_retry_refuses_a_run_that_did_not_block(self):
        run = self.claimed([self.ready()])
        build.end(self.connection, run["id"], "done", "landed")
        recent = self.panel(clock())["recent"][0]
        self.assertEqual((recent["outcome"], recent["retry"]["allowed"]), ("done", False))
        status, _, body = self.post("/api/queue/builds/retry", {"assignment": run["assignment"],
                                                               "revision": recent["retry"]["revision"]})
        self.assertEqual(status, 400, body)
        self.assertIn("Retry takes a blocked or cancelled one", body["error"])

    def test_retry_with_a_stale_revision_is_a_409_and_writes_nothing(self):
        items = [self.ready()]
        run = self.blocked(items)
        status, _, body = self.post("/api/queue/builds/retry", {"assignment": run["assignment"], "revision": "0" * 64})
        self.assertEqual(status, 409, body)
        self.assertEqual(item_state(self.connection, items[0])["item"]["status"], "blocked")
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM assignment WHERE scope = 'build' AND status = 'queued'").fetchone()[0], 0)


class SendToBuilder(Fixture):
    claimed, panel = BuildsPanel.claimed, BuildsPanel.panel

    def cancelled(self, items):
        run = self.claimed(items)
        build.end(self.connection, run["id"], "cancelled", "cancelled by the operator")
        return run

    def test_send_to_builder_notes_the_finding_and_queues_the_bundle_for_its_worktree(self):
        """Pack sd:6020: a cancelled bundle takes a finding; each item gets the note, the bundle queues again under
        its lead, and the next claim names the same branch and worktree."""
        items = [self.ready(), self.ready()]
        run = self.cancelled(items)
        recent = self.panel(clock())["recent"][0]
        self.assertEqual((recent["outcome"], recent["retry"]["allowed"]), ("cancelled", True))
        status, _, body = self.post("/api/queue/builds/retry", {"assignment": run["assignment"],
                                                               "revision": recent["retry"]["revision"],
                                                               "finding": "  The label reads wrong on phones "})
        self.assertEqual(status, 200, body)
        for item in items:
            notes = [row["body"] for row in self.connection.execute("SELECT body FROM note WHERE item = ?", (item,))]
            self.assertIn("Send to builder: The label reads wrong on phones", notes)
        again = build.claim(self.connection, owner="fixture", root=self.path.parent / "worktrees", **IDLE)
        self.assertEqual((again["assignment"], again["branch"], again["work_path"]),
                         (run["assignment"], run["branch"], run["work_path"]))
        self.assertEqual(len(self.kicks), 1)

    def test_send_to_builder_refuses_an_empty_or_long_finding_and_writes_nothing(self):
        run = self.cancelled([self.ready()])
        revision = self.panel(clock())["recent"][0]["retry"]["revision"]
        for finding in ("", "   ", 7, "x" * (builds.FINDING_MAX + 1)):
            status, _, body = self.post("/api/queue/builds/retry", {"assignment": run["assignment"],
                                                                   "revision": revision, "finding": finding})
            self.assertEqual(status, 400, (finding, body))
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM assignment WHERE scope = 'build' AND status = 'queued'").fetchone()[0], 0)
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM note WHERE body LIKE 'Send to builder:%'").fetchone()[0], 0)
