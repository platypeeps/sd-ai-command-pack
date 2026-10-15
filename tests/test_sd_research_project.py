"""`sd-research-kit project`, its `--plan` guard, and `delivered` for a row (sd:3982).

The failure table of `docs/work/2026-10-14-experiments-projection/design.md`
names three suites; they are the three classes here: `ProjectTests`
(`test_projection`), `PlanTests` (`test_projection_plan`) and
`DeliveredRowTests` (`test_delivered`). Nothing reaches Notion: the drain's
fetch is a JSON file each test writes, the stub of what the connector answers.
"""

from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import unittest
import unittest.mock
from pathlib import Path
from typing import Any

from tests import test_sd_research_publish as base

PUBLISH = base.PUBLISH

EXPERIMENTS = "1a2b3c4d-0000-4000-8000-00000000e001"
TASKS = "1a2b3c4d-0000-4000-8000-00000000e002"
ROW = "3c9f52b1-5782-81a7-a466-fb0e2df4d928"
TASK_ROW = "3c9f52b1-5782-81a7-a466-fb0e2df4d929"
OTHER = "3cff52b1-5782-806a-acb0-ca0c8f41524b"
CONTRACT = base.REPO_ROOT / "skills" / "_shared" / "references" / "publication-contract.md"


def url(row: str) -> str:
    return "https://example.test/" + row.replace("-", "")


def day(start: str, end: str | None = None, time_zone: str | None = None) -> dict[str, Any]:
    """A date property as the drain hands it: the whole value, never its start alone."""
    return {"start": start, "end": end, "time_zone": time_zone}


def linked(*pages: str, more: bool = False) -> dict[str, Any]:
    """A relation as the drain hands it: every page id, and Notion's word that none is left out."""
    return {"ids": list(pages), "has_more": more}


def schema(target: str) -> dict[str, Any]:
    """The live schema of a database as the drain hands it over, matching the mapping."""
    status = {"type": "select", "options": ["Todo", "In Progress", "Blocked", "Done"]}
    if target == "experiments":
        return {"Experiment": {"type": "title"}, "Status": status, "Decision": {"type": "select", "options": []},
                "Stage": {"type": "select", "options": ["Idea", "Scoping", "Running", "Evaluating", "Decided"]}}
    return {"Task": {"type": "title"}, "Status": status, "Experiment": {"type": "relation"},
            "Due": {"type": "date"}, "Priority": {"type": "select", "options": ["High", "Medium", "Low"]},
            "Type": {"type": "select", "options": ["Build"]}}


class Projection(base.Fixture):
    """A workflow database, both variables set, and helpers for the drain's steps."""

    def setUp(self) -> None:
        super().setUp()
        PUBLISH.ENVIRON = dict(PUBLISH.ENVIRON, SD_NOTION_EXPERIMENTS=EXPERIMENTS.replace("-", ""),
                               SD_NOTION_EXPERIMENT_TASKS="collection://" + TASKS)
        self.experiment, self.task = self.database("An experiment", "A task")
        from sd_db import projection  # noqa: PLC0415
        self.projection = projection

    def add(self, title: str) -> int:
        from sd_db.writes import create_item  # noqa: PLC0415
        return create_item(self.connection, kind="task", title=title)

    def designate(self, item: int, *specs: str) -> None:
        self.projection.designate(self.connection, item, list(specs), who="tester")

    def held(self, item: int) -> dict[str, Any]:
        row = self.connection.execute("SELECT fields FROM item WHERE id = ?", (item,)).fetchone()
        return json.loads(row["fields"] or "{}").get("experiments")

    def status(self, item: int, status: str) -> None:
        self.connection.execute("UPDATE item SET status = ? WHERE id = ?", (status, item))

    def name(self, item: int) -> str:
        return PUBLISH.row_request_name(item)

    def path(self, item: int) -> Path:
        return PUBLISH.QUEUE / self.name(item)

    def request(self, item: int) -> dict[str, Any]:
        return json.loads(self.path(item).read_text())

    def queue(self) -> dict[str, bytes]:
        return {path.name: path.read_bytes() for path in sorted(PUBLISH.QUEUE.glob("*"))} \
            if PUBLISH.QUEUE.is_dir() else {}

    def project(self) -> tuple[int, list[str]]:
        return PUBLISH.project()

    def live(self, target: str = "experiments", row: str | None = None, candidates: list | None = None,
             **properties: Any) -> dict[str, Any]:
        database = EXPERIMENTS if target == "experiments" else TASKS
        fetched: dict[str, Any] = {"database": database, "schema": schema(target)}
        properties = {**{name: None for name in self.projection.OWNED[target]},
                      **({"Experiment": linked()} if target == "tasks" else {}), **properties}
        if row is not None:
            fetched["row"] = {"id": url(row), "parent": database, "properties": properties}
        if candidates is not None:
            fetched["candidates"] = [{"id": entry, "parent": database, "properties": properties}
                                     for entry in candidates]
        return fetched

    def plan(self, item: int, live: dict[str, Any] | None) -> tuple[int, str]:
        path = None
        if live is not None:
            path = self.root / ("live-%d.json" % item)
            path.write_text(json.dumps(live))
        return PUBLISH.plan_request(self.path(item), path)

    def planned(self, item: int, live: dict[str, Any] | None) -> dict[str, Any]:
        status, said = self.plan(item, live)
        self.assertEqual(status, 0, said)
        return json.loads(said)

    def mark(self, item: int, path: Path | None = None) -> tuple[int, str]:
        """The drain's mark just before its create call: `project --writing <request>`."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            status = PUBLISH.project_main(["--writing", str(path or self.path(item))])
        return status, out.getvalue()

    def deliver(self, item: int, fingerprint: str | None = None, row: str = ROW, *extra: str) -> tuple[int, str]:
        given = fingerprint or self.request(item)["fingerprint"]
        out = io.StringIO()
        arguments = [self.name(item), given, *(extra or ("--url", url(row)))]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            status = PUBLISH.delivered_main(arguments)
        return status, out.getvalue()

    def created(self, item: int = 0, row: str = ROW) -> None:
        """A first drain of an experiment: project, plan a create, write it, `delivered`, then the no-op
        generation the recorded row starts."""
        item = item or self.experiment
        self.designate(item, "yes")
        self.project()
        self.assertEqual(self.planned(item, self.live())["action"], "create")
        self.assertEqual(self.deliver(item, row=row)[0], 0)
        self.project()
        self.planned(item, self.live(row=row, Status="Todo"))
        self.assertEqual(self.deliver(item, row=row)[0], 0)


class ProjectTests(Projection):
    """`project`: what reaches the queue, and what a failure leaves there."""

    def test_two_designated_items_queue_two_requests_and_a_second_run_none(self) -> None:
        self.designate(self.experiment, "yes")
        self.designate(self.task, "of:%d" % self.experiment)
        status, said = self.project()
        self.assertEqual(status, 0, said)
        self.assertEqual(sorted(self.queue()), [self.name(self.experiment), self.name(self.task)])
        request = self.request(self.task)
        self.assertEqual((request["destination"], request["target"], request["database"], request["of"]),
                         ("notion-row", "tasks", TASKS, self.experiment))
        self.assertEqual(request["values"], {"Status": "Todo", "Experiment": None, "Due": None})
        before = self.queue()
        status, said = self.project()
        self.assertEqual(status, 0, said)
        self.assertEqual(self.queue(), before)
        self.assertEqual(sum("already queued" in line for line in said), 2, said)

    def test_no_designation_queues_nothing(self) -> None:
        self.assertEqual(self.project(), (0, []))
        self.assertEqual([path for path in PUBLISH.QUEUE.glob("*.json")], [])

    def test_an_unset_or_name_valued_variable_refuses_naming_it(self) -> None:
        self.designate(self.experiment, "yes")
        for setting, value in (("SD_NOTION_EXPERIMENTS", ""), ("SD_NOTION_EXPERIMENT_TASKS", "Experiment Tasks")):
            with self.subTest(setting=setting):
                environ = dict(PUBLISH.ENVIRON, **{setting: value})
                with unittest.mock.patch.object(PUBLISH, "ENVIRON", environ):
                    status, said = self.project()
                self.assertEqual(status, 1)
                self.assertIn(setting, said[0])
                self.assertEqual(self.queue(), {})

    def test_each_read_failure_leaves_the_queue_byte_for_byte(self) -> None:
        self.designate(self.experiment, "yes")
        self.project()
        before = self.queue()
        self.status(self.experiment, "in_progress")
        from sd_db.remote import RemoteError  # noqa: PLC0415
        from sd_db.writes import record_state  # noqa: PLC0415
        cases = {
            "no database": lambda: unittest.mock.patch.object(PUBLISH, "DATABASE_HOME", self.root / "no-home"),
            "build mismatch": lambda: unittest.mock.patch(
                "sd_db.connect", side_effect=RemoteError("build mismatch: hub 1.2, this 1.3")),
            "designated items": lambda: unittest.mock.patch(
                "sd_db.projection.designated_rows", side_effect=sqlite3.OperationalError("disk I/O error")),
        }
        for cause, patcher in cases.items():
            with self.subTest(cause=cause), patcher():
                status, said = self.project()
                self.assertEqual(status, 1, said)
                self.assertIn("nothing queued", said[0])
                self.assertEqual(self.queue(), before)
        record_state(self.connection, "restore", key="example", body={})
        status, said = self.project()
        self.assertEqual(status, 1, said)
        self.assertIn("restore", said[0])
        self.assertEqual(self.queue(), before)

    def test_a_truncated_request_is_rewritten_on_the_next_run(self) -> None:
        self.designate(self.experiment, "yes")
        self.project()
        whole = self.path(self.experiment).read_text()
        self.path(self.experiment).write_text(whole[:20])
        status, said = self.project()
        self.assertEqual(status, 0, said)
        self.assertEqual(self.path(self.experiment).read_text(), whole)

    def test_a_dropped_designations_request_is_reported_and_left(self) -> None:
        self.designate(self.experiment, "yes")
        self.project()
        before = self.queue()
        self.designate(self.experiment, "off")
        status, said = self.project()
        self.assertEqual(status, 0, said)
        self.assertTrue(any(str(self.path(self.experiment)) in line and "no longer designated" in line
                            for line in said), said)
        self.assertEqual(self.queue(), before)
        status, said = self.plan(self.experiment, self.live())
        self.assertEqual(status, 1)
        self.assertIn("stale", said)

    def test_a_task_of_an_experiment_set_off_is_not_queued_and_says_why(self) -> None:
        self.designate(self.experiment, "yes")
        self.designate(self.task, "of:%d" % self.experiment)
        self.designate(self.experiment, "off")
        status, said = self.project()
        self.assertEqual(status, 1)
        self.assertTrue(any("parent sd:%d is not designated experiment" % self.experiment in line
                            for line in said), said)
        self.assertEqual(self.queue(), {})

    def test_a_rerun_during_a_drain_keeps_the_drained_generation_recordable(self) -> None:
        self.designate(self.experiment, "yes")
        self.project()
        drained = self.request(self.experiment)["fingerprint"]
        self.planned(self.experiment, self.live())
        self.status(self.experiment, "in_progress")
        self.project()
        newer = self.path(self.experiment).read_bytes()
        self.assertNotEqual(json.loads(newer)["fingerprint"], drained)
        status, said = self.deliver(self.experiment, drained)
        self.assertEqual(status, 0, said)
        held = self.held(self.experiment)
        self.assertEqual((held["row"], held["written"]), (ROW, {"Status": "Todo"}))
        self.assertEqual(self.path(self.experiment).read_bytes(), newer)
        self.assertEqual(PUBLISH.load_record(PUBLISH.receipts() / self.name(self.experiment))["delivered"], drained)

    def test_sd_status_reads_the_request_on_its_repo(self) -> None:
        self.designate(self.experiment, "yes")
        self.project()
        request = self.request(self.experiment)
        self.assertEqual((request["document"], request["target"]), ("sd:%d" % self.experiment, "experiments"))


class PlanTests(Projection):
    """`project --plan`: the guard, given the row the drain fetched."""

    def queued(self) -> None:
        self.designate(self.experiment, "yes")
        self.project()

    def test_a_create_prints_the_seeds_the_owned_fields_and_the_pointer(self) -> None:
        self.connection.execute("UPDATE item SET kind = 'work-idea' WHERE id = ?", (self.experiment,))
        self.queued()
        planned = self.planned(self.experiment, self.live())
        self.assertEqual(planned["action"], "create")
        self.assertEqual(planned["properties"], {"Experiment": "An experiment", "Status": "Todo", "Stage": "Idea"})
        self.assertEqual(planned["body"], "Projected from sd:%d. sd keeps Status current; edit anything else."
                         % self.experiment)
        held = self.held(self.experiment)
        self.assertEqual(held["creating"]["generation"], self.request(self.experiment)["fingerprint"])
        self.assertEqual(held["creating"]["database"], EXPERIMENTS)

    def test_a_task_create_links_its_experiment_and_seeds_priority(self) -> None:
        self.created()
        self.connection.execute("UPDATE item SET priority = 1, due = '2026-11-02' WHERE id = ?", (self.task,))
        self.designate(self.task, "of:%d" % self.experiment)
        self.project()
        planned = self.planned(self.task, self.live("tasks"))
        self.assertEqual(planned["properties"], {"Task": "A task", "Status": "Todo", "Experiment": [ROW],
                                                 "Due": "2026-11-02", "Priority": "High"})

    def test_each_change_after_project_refuses_as_stale(self) -> None:
        self.created()
        self.designate(self.task, "of:%d" % self.experiment)
        self.project()
        third = self.add("Another experiment")
        self.designate(third, "yes")
        changes = {
            "status": lambda: self.status(self.task, "blocked"),
            "designation": lambda: self.designate(self.task, "off"),
            "of": lambda: self.designate(self.task, "of:%d" % third),
            "config": lambda: PUBLISH.ENVIRON.update(SD_NOTION_EXPERIMENT_TASKS=OTHER),
        }
        for change, apply in changes.items():
            with self.subTest(change=change):
                saved = (self.connection.execute("SELECT status, fields FROM item WHERE id = ?",
                                                 (self.task,)).fetchone(), dict(PUBLISH.ENVIRON))
                apply()
                status, said = self.plan(self.task, self.live("tasks"))
                self.assertEqual(status, 1, said)
                self.assertIn("stale", said)
                self.connection.execute("UPDATE item SET status = ?, fields = ? WHERE id = ?",
                                        (saved[0]["status"], saved[0]["fields"], self.task))
                PUBLISH.ENVIRON = saved[1]

    def test_no_database_and_an_open_restore_refuse(self) -> None:
        self.queued()
        with unittest.mock.patch.object(PUBLISH, "DATABASE_HOME", self.root / "no-home"):
            self.assertEqual(self.plan(self.experiment, self.live())[0], 1)
        from sd_db.writes import record_state  # noqa: PLC0415
        record_state(self.connection, "restore", key="example", body={})
        status, said = self.plan(self.experiment, self.live())
        self.assertEqual(status, 1)
        self.assertIn("restore", said)
        self.assertNotIn("creating", self.held(self.experiment))

    def test_a_channels_setting_without_notion_or_unreadable_refuses(self) -> None:
        from sd_db.repos import set_channels  # noqa: PLC0415
        from sd_db.writes import upsert_repo  # noqa: PLC0415
        repo = self.root / "example-repo"
        repo.mkdir()
        repo = repo.resolve()
        upsert_repo(self.connection, str(repo))
        self.connection.execute("UPDATE item SET repo = ? WHERE id = ?", (str(repo), self.experiment))
        set_channels(self.connection, str(repo), {"obsidian": {}})
        self.queued()
        status, said = self.plan(self.experiment, self.live())
        self.assertEqual(status, 1)
        self.assertIn("leaves out notion", said)
        self.connection.execute("UPDATE repo SET channels = '{\"slack\": {}}' WHERE path = ?", (str(repo),))
        status, said = self.plan(self.experiment, self.live())
        self.assertEqual(status, 1)
        self.assertIn("cannot be read", said)
        # The operator replaces the value they read (sd:4191): with no `before`, a set over a value this build cannot read
        # refuses rather than lose the keys it does not name.
        set_channels(self.connection, str(repo), {"notion": {}}, before='{"slack": {}}')
        self.assertEqual(self.plan(self.experiment, self.live())[0], 0)

    def test_missing_refuses_and_prints_no_create(self) -> None:
        self.created()
        self.status(self.experiment, "in_progress")
        self.project()
        before = self.held(self.experiment)
        status, said = self.plan(self.experiment, None)
        self.assertEqual(status, 1)
        self.assertNotIn('"action"', said)
        self.assertIn("Option: stop projecting it", said)
        self.assertIn("--experiment new", said)
        self.assertEqual(self.held(self.experiment), before)

    def test_each_schema_change_refuses_naming_the_property(self) -> None:
        self.created()
        self.status(self.experiment, "in_progress")
        self.project()
        cases = {
            "removed": lambda live: live["schema"].pop("Status"),
            "retyped": lambda live: live["schema"].update(Status={"type": "rich_text"}),
            "option removed": lambda live: live["schema"]["Status"]["options"].remove("Blocked"),
        }
        for case, change in cases.items():
            with self.subTest(case=case):
                live = self.live(row=ROW, Status="Todo")
                change(live)
                status, said = self.plan(self.experiment, live)
                self.assertEqual(status, 1, said)
                self.assertIn("Status", said)
        live = self.live(row=ROW, Status="Todo")
        live["row"]["parent"] = TASKS
        status, said = self.plan(self.experiment, live)
        self.assertEqual(status, 1)
        self.assertIn("never written across databases", said)
        self.assertNotIn("writing", self.held(self.experiment))

    def test_a_hand_set_status_is_refused_and_one_note_names_it(self) -> None:
        self.created()
        self.status(self.experiment, "in_progress")
        self.project()
        planned = self.planned(self.experiment, self.live(row=ROW, Status="Blocked"))
        self.assertEqual((planned["properties"], planned["yielded"]), ({}, ["Status"]))
        self.assertEqual(self.held(self.experiment)["yielded"], ["Status"])
        self.assertEqual(self.comments(self.experiment)[-1],
                         "Status on the experiments row is not sd's (Blocked; sd last wrote Todo; set it to Todo "
                         "to hand it back)")

    def test_a_select_name_is_compared_exactly(self) -> None:
        self.created()
        self.status(self.experiment, "in_progress")
        self.project()
        live = self.live(row=ROW, Status=" Todo ")
        live["schema"]["Status"]["options"].append(" Todo ")
        planned = self.planned(self.experiment, live)
        self.assertEqual((planned["properties"], planned["yielded"]), ({}, ["Status"]))

    def test_a_value_equal_to_the_wanted_one_is_not_claimed(self) -> None:
        self.created()
        self.status(self.experiment, "in_progress")
        self.project()
        planned = self.planned(self.experiment, self.live(row=ROW, Status="In Progress"))
        self.assertEqual(planned["yielded"], ["Status"])
        self.status(self.experiment, "done")
        self.project()
        self.assertNotIn("Status", self.planned(self.experiment, self.live(row=ROW, Status="In Progress"))
                         ["properties"])

    def test_a_hand_back_is_picked_up_by_the_next_project_and_confirmed(self) -> None:
        self.created()
        self.status(self.experiment, "in_progress")
        self.project()
        self.planned(self.experiment, self.live(row=ROW, Status="Blocked"))
        self.assertEqual(self.deliver(self.experiment)[0], 0)
        self.assertEqual(self.queue(), {})
        status, said = self.project()
        self.assertTrue(any("queued sd:%d" % self.experiment in line for line in said), said)
        planned = self.planned(self.experiment, self.live(row=ROW, Status="Todo"))
        self.assertEqual((planned["properties"], planned["yielded"]), ({"Status": "In Progress"}, []))
        self.assertEqual(self.deliver(self.experiment)[0], 0)
        held = self.held(self.experiment)
        self.assertEqual((held["written"], held.get("yielded")), ({"Status": "In Progress"}, None))
        self.assertEqual(self.project()[1], ["project: sd:%d: unchanged since it was last projected; not queued "
                                              "again" % self.experiment])

    def test_two_episodes_give_two_notes_each_naming_its_own_written(self) -> None:
        self.created()
        self.status(self.experiment, "in_progress")
        self.project()
        self.planned(self.experiment, self.live(row=ROW, Status="Blocked"))
        self.planned(self.experiment, self.live(row=ROW, Status="Blocked"))
        self.planned(self.experiment, self.live(row=ROW, Status="Todo"))
        self.deliver(self.experiment)
        self.status(self.experiment, "done")
        self.project()
        self.planned(self.experiment, self.live(row=ROW, Status="Blocked"))
        notes = [note for note in self.comments(self.experiment) if "is not sd's" in note]
        self.assertEqual(len(notes), 2, notes)
        self.assertIn("sd last wrote Todo", notes[0])
        self.assertIn("sd last wrote In Progress", notes[1])

    def test_a_task_before_its_experiments_row_refuses(self) -> None:
        self.designate(self.experiment, "yes")
        self.designate(self.task, "of:%d" % self.experiment)
        self.project()
        status, said = self.plan(self.task, self.live("tasks"))
        self.assertEqual(status, 1)
        self.assertIn("parent sd:%d has no row yet" % self.experiment, said)

    def test_a_failed_intent_write_prints_no_plan(self) -> None:
        self.queued()
        with unittest.mock.patch("sd_db.projection._store", side_effect=sqlite3.OperationalError("disk full")):
            status, said = self.plan(self.experiment, self.live())
        self.assertEqual(status, 1)
        self.assertNotIn('"action"', said)
        self.assertNotIn("creating", self.held(self.experiment))

    def test_an_interrupted_create_never_creates_twice(self) -> None:
        # sd:4742: the drain marks the intent `writing` just before its create call; a stop after that leaves
        # the mark, and the next plan searches. None found asks (the create may have landed and search can
        # lag); two ask; never a create.
        self.queued()
        self.planned(self.experiment, self.live())
        status, said = self.mark(self.experiment)
        self.assertEqual(status, 0, said)
        self.assertEqual(self.held(self.experiment)["creating"]["state"], "writing")
        status, said = self.plan(self.experiment, self.live())
        self.assertEqual(status, 1)
        self.assertIn("search: an earlier create of sd:%d may have landed" % self.experiment, said)
        self.assertIn("`Projected from sd:%d.`" % self.experiment, said)
        self.assertNotIn("Option:", said)
        for found in ([], [ROW, OTHER]):
            with self.subTest(found=found):
                status, said = self.plan(self.experiment, self.live(candidates=found, Status="Todo"))
                self.assertEqual(status, 1)
                self.assertNotIn('"action"', said)
                self.assertIn("may have landed", said)
                self.assertIn("Option: no row exists, create it, `sd task edit %d --experiment new`"
                              % self.experiment, said)
                self.assertEqual(self.held(self.experiment)["creating"]["state"], "writing")

    def test_a_planned_create_intent_prints_the_same_create_again_without_a_search(self) -> None:
        # sd:4742 (a): a plan-only run (a dry run, or a drain stopped before its mark) leaves the intent in
        # state `planned`: nothing was written, so the next plan prints the same create again, asks for no
        # search and never for `--experiment new`.
        self.queued()
        first = self.planned(self.experiment, self.live())
        self.assertEqual(self.held(self.experiment)["creating"]["state"], "planned")
        status, said = self.plan(self.experiment, self.live())
        self.assertEqual(status, 0, said)
        self.assertNotIn("Option:", said)
        self.assertEqual(json.loads(said), first)
        held = self.held(self.experiment)
        self.assertEqual((held["creating"]["state"], held["creating"]["generation"]),
                         ("planned", self.request(self.experiment)["fingerprint"]))
        self.assertEqual(self.mark(self.experiment)[0], 0)
        self.assertEqual(self.deliver(self.experiment)[0], 0)
        self.assertEqual(self.held(self.experiment)["row"], ROW)

    def test_a_create_intent_without_a_state_reads_as_writing(self) -> None:
        # A `creating` intent an older pack recorded has no state: the safe reading is that its write may
        # have landed, so an empty search asks rather than creates.
        self.queued()
        self.planned(self.experiment, self.live())
        row = self.connection.execute("SELECT fields FROM item WHERE id = ?", (self.experiment,)).fetchone()
        fields = json.loads(row["fields"])
        fields["experiments"]["creating"].pop("state")
        self.connection.execute("UPDATE item SET fields = ? WHERE id = ?", (json.dumps(fields), self.experiment))
        status, said = self.plan(self.experiment, self.live(candidates=[]))
        self.assertEqual(status, 1)
        self.assertNotIn('"action"', said)
        self.assertIn("Option: no row exists, create it", said)
        self.assertNotIn("state", self.held(self.experiment)["creating"])

    def test_the_writing_mark_is_bound_to_the_planned_generation_and_made_once(self) -> None:
        self.queued()
        status, said = self.mark(self.experiment)
        self.assertEqual(status, 1)
        self.assertIn("no create planned", said)
        self.assertNotIn("creating", self.held(self.experiment))
        self.planned(self.experiment, self.live())
        held = self.held(self.experiment)
        other = self.root / self.name(self.task)
        other.write_bytes(self.path(self.experiment).read_bytes())
        self.assertEqual(self.mark(self.experiment, other)[0], 1)
        self.status(self.experiment, "in_progress")
        self.project()  # a newer generation: the planned one is not this request's
        status, said = self.mark(self.experiment)
        self.assertEqual(status, 1)
        self.assertIn("no create planned", said)
        self.status(self.experiment, "planning")
        self.project()
        self.designate(self.experiment, "off")
        self.designate(self.experiment, "yes")  # `since` moved since the plan
        status, said = self.mark(self.experiment)
        self.assertEqual(status, 1)
        self.assertIn("moved since the plan", said)
        self.assertEqual(self.held(self.experiment)["creating"], held["creating"])
        self.project()
        self.planned(self.experiment, self.live())
        self.assertEqual(self.mark(self.experiment)[0], 0)
        status, said = self.mark(self.experiment)
        self.assertEqual(status, 1)
        self.assertIn("already marked writing", said)
        self.assertEqual(self.held(self.experiment)["creating"]["state"], "writing")

    def test_a_create_plan_repeated_before_its_write_is_the_same_create(self) -> None:
        # sd:4742 (b): anything between a plan and its write means plan again. Before the mark that plan is
        # the same create under the same intent, however often; after the mark it answers `search:`. The plan
        # the write follows is the one that counts.
        self.queued()
        first = self.planned(self.experiment, self.live())
        held = self.held(self.experiment)
        notes = self.comments(self.experiment)
        for _ in range(2):
            self.assertEqual(self.planned(self.experiment, self.live()), first)
            self.assertEqual(self.held(self.experiment), held)
        self.assertEqual(self.comments(self.experiment), notes)
        self.assertEqual(self.mark(self.experiment)[0], 0)
        status, said = self.plan(self.experiment, self.live())
        self.assertEqual(status, 1)
        self.assertIn("search:", said)
        text = " ".join(CONTRACT.read_text(encoding="utf-8").split())
        self.assertIn("The plan the write follows is the one that counts", text)
        self.assertIn("sd-research-kit project --writing", text)

    def test_one_candidate_is_adopted_and_its_fields_wait_for_a_hand_back(self) -> None:
        self.queued()
        self.planned(self.experiment, self.live())
        self.assertEqual(self.mark(self.experiment)[0], 0)
        planned = self.planned(self.experiment, self.live(candidates=[ROW], Status="Todo"))
        self.assertEqual((planned["action"], planned["row"], planned["yielded"]), ("update", ROW, ["Status"]))
        held = self.held(self.experiment)
        self.assertEqual(held["row"], ROW)
        self.assertNotIn("creating", held)
        self.assertEqual(self.comments(self.experiment)[-1],
                         "Status on the experiments row is not sd's (Todo; sd last wrote nothing; clear it to hand "
                         "it back); this may be sd's own unconfirmed write")
        self.assertEqual(self.deliver(self.experiment)[0], 0)
        self.project()
        planned = self.planned(self.experiment, self.live(row=ROW))
        self.assertEqual((planned["properties"], planned["yielded"]), ({"Status": "Todo"}, []))

    def test_creating_in_another_database_refuses_naming_both(self) -> None:
        self.queued()
        self.planned(self.experiment, self.live())
        PUBLISH.ENVIRON["SD_NOTION_EXPERIMENTS"] = OTHER
        self.project()
        live = self.live()
        live["database"] = OTHER
        status, said = self.plan(self.experiment, live)
        self.assertEqual(status, 1)
        self.assertIn(EXPERIMENTS, said)
        self.assertIn(OTHER, said)

    def test_a_partly_written_update_waits_for_a_hand_back(self) -> None:
        self.created()
        self.designate(self.task, "of:%d" % self.experiment)
        self.project()
        self.planned(self.task, self.live("tasks"))
        self.deliver(self.task, row=TASK_ROW)
        self.connection.execute("UPDATE item SET due = '2026-11-02', status = 'in_progress' WHERE id = ?",
                                (self.task,))
        self.project()
        self.project()
        live = dict(Status="Todo", Experiment=linked(url(ROW)))
        self.planned(self.task, self.live("tasks", row=TASK_ROW, **live))
        # Notion took Due, then the drain stopped before `delivered`.
        self.project()
        planned = self.planned(self.task, self.live("tasks", row=TASK_ROW, Due=day("2026-11-02"), **live))
        self.assertEqual((planned["properties"], planned["yielded"]), ({"Status": "In Progress"}, ["Due"]))
        self.assertIn("this may be sd's own unconfirmed write", self.comments(self.task)[-1])
        self.deliver(self.task, row=TASK_ROW)
        self.project()
        planned = self.planned(self.task, self.live("tasks", row=TASK_ROW, **dict(live, Status="In Progress")))
        self.assertEqual((planned["properties"], planned["yielded"]), ({"Due": "2026-11-02"}, []))

    def test_a_row_read_without_an_owned_property_refuses_and_records_nothing(self) -> None:
        self.queued()
        self.planned(self.experiment, self.live())
        self.assertEqual(self.mark(self.experiment)[0], 0)
        live = self.live(candidates=[ROW], Status="Blocked")
        del live["candidates"][0]["properties"]["Status"]
        before = self.held(self.experiment)
        status, said = self.plan(self.experiment, live)
        self.assertEqual(status, 1, said)
        self.assertIn("Status: the live row does not carry it", said)
        self.assertEqual(self.held(self.experiment), before)
        self.created(self.task, TASK_ROW)
        self.status(self.task, "in_progress")
        self.project()
        live = self.live(row=TASK_ROW, Status="Blocked")
        del live["row"]["properties"]["Status"]
        status, said = self.plan(self.task, live)
        self.assertEqual(status, 1, said)
        self.assertIn("Status: the live row does not carry it", said)

    def test_a_date_range_or_time_on_the_written_start_is_yielded_and_a_bare_date_refused(self) -> None:
        self.created()
        self.connection.execute("UPDATE item SET due = '2026-11-02' WHERE id = ?", (self.task,))
        self.designate(self.task, "of:%d" % self.experiment)
        self.project()
        self.planned(self.task, self.live("tasks"))
        self.deliver(self.task, row=TASK_ROW)
        self.connection.execute("UPDATE item SET due = '2026-11-09' WHERE id = ?", (self.task,))
        self.project()
        live = dict(Status="Todo", Experiment=linked(url(ROW)))
        for held in (day("2026-11-02", "2026-11-05"), day("2026-11-02T09:00:00.000-06:00"),
                     day("2026-11-02", time_zone="America/New_York")):
            with self.subTest(held=held):
                planned = self.planned(self.task, self.live("tasks", row=TASK_ROW, Due=held, **live))
                self.assertEqual((planned["properties"], planned["yielded"]), ({}, ["Due"]))
        self.assertIn("Due on the tasks row is not sd's (2026-11-02 to 2026-11-05; sd last wrote 2026-11-02",
                      self.comments(self.task)[-1])
        before = self.held(self.task)
        for cut in ("2026-11-02", {"start": "2026-11-02"}, {"start": "2026-11-02", "end": None},
                    {"start": "2026-11-02", "end": 5, "time_zone": None}):
            with self.subTest(cut=cut):
                status, said = self.plan(self.task, self.live("tasks", row=TASK_ROW, Due=cut, **live))
                self.assertEqual(status, 1, said)
                self.assertIn("Due: hand the whole date", said)
                self.assertEqual(self.held(self.task), before)
        planned = self.planned(self.task, self.live("tasks", row=TASK_ROW, Due=day("2026-11-02"), **live))
        self.assertEqual(planned["properties"], {"Due": "2026-11-09"})

    def test_a_relation_without_proof_it_is_whole_is_refused(self) -> None:
        self.created()
        self.designate(self.task, "of:%d" % self.experiment)
        self.project()
        self.planned(self.task, self.live("tasks"))
        self.deliver(self.task, row=TASK_ROW)
        self.status(self.task, "in_progress")
        self.project()
        before = self.held(self.task)
        for cut in ([url(ROW)], [], None, {"ids": [url(ROW)]}, linked(url(ROW), more=True),
                    {"ids": url(ROW), "has_more": False}):
            with self.subTest(cut=cut):
                live = self.live("tasks", row=TASK_ROW, Status="Todo", Experiment=cut)
                status, said = self.plan(self.task, live)
                self.assertEqual(status, 1, said)
                self.assertIn("Experiment: hand the whole relation", said)
                self.assertEqual(self.held(self.task), before)
        planned = self.planned(self.task, self.live("tasks", row=TASK_ROW, Status="Todo",
                                                    Experiment=linked(url(ROW), url(OTHER))))
        self.assertEqual(planned["yielded"], ["Experiment"])

    def test_a_live_row_lacking_status_names_it(self) -> None:
        self.created()
        self.status(self.experiment, "done")
        self.project()
        live = self.live(row=ROW, Status="Todo")
        del live["schema"]["Status"]
        status, said = self.plan(self.experiment, live)
        self.assertEqual(status, 1)
        self.assertIn("Status:", said)

    def test_a_request_under_another_items_name_refuses(self) -> None:
        self.queued()
        moved = PUBLISH.QUEUE / self.name(self.task)
        self.path(self.experiment).rename(moved)
        status, said = PUBLISH.plan_request(moved, None)
        self.assertEqual(status, 1)
        self.assertIn("whose request is", said)


class DeliveredRowTests(Projection):
    """`delivered` for a `notion-row` request: `record_row`, then the receipt and the removal."""

    def setUp(self) -> None:
        super().setUp()
        self.designate(self.experiment, "yes")
        self.project()
        self.planned(self.experiment, self.live())

    def state(self) -> tuple[bytes, dict, Any]:
        return (self.path(self.experiment).read_bytes(),
                PUBLISH.load_record(PUBLISH.receipts() / self.name(self.experiment)), self.held(self.experiment))

    def test_a_row_url_records_the_row_and_a_second_run_adds_no_note(self) -> None:
        fingerprint = self.request(self.experiment)["fingerprint"]
        status, said = self.deliver(self.experiment)
        self.assertEqual(status, 0, said)
        self.assertEqual(self.held(self.experiment)["row"], ROW)
        self.assertFalse(self.path(self.experiment).exists())
        self.path(self.experiment).write_text(json.dumps({"destination": "notion-row", "item": self.experiment,
                                                          "fingerprint": fingerprint}))
        status, said = self.deliver(self.experiment, fingerprint)
        self.assertEqual(status, 0, said)
        self.assertEqual(self.comments(self.experiment), ["Updated experiments by tester",
                                                          "Projected to experiments: " + url(ROW)])

    def test_no_url_exits_2_and_writes_nothing(self) -> None:
        before = self.state()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            status = PUBLISH.delivered_main([self.name(self.experiment), self.request(self.experiment)["fingerprint"]])
        self.assertEqual(status, 2, out.getvalue())
        self.assertIn("--url", out.getvalue())
        self.assertEqual(self.state(), before)

    def test_each_refusal_leaves_request_receipt_and_item(self) -> None:
        from sd_db.writes import record_state  # noqa: PLC0415
        before = self.state()
        cases = {
            "no intent": lambda: self.deliver(self.experiment, "0" * 64),
            "row mismatch": lambda: self.deliver(self.experiment, None, OTHER),
            "hub down": self.down,
            "item unknown": self.unknown,
        }
        for cause, run in cases.items():
            with self.subTest(cause=cause):
                if cause == "row mismatch":
                    self.pin()
                status, said = run()
                self.assertEqual(status, 1, said)
                self.assertIn("left in place", said)
                if cause == "row mismatch":
                    self.assertIn("names row", said)
                self.restore_held(before[2])
                self.assertEqual(self.state(), before)
        record_state(self.connection, "restore", key="example", body={})
        status, said = self.deliver(self.experiment)
        self.assertEqual(status, 1)
        self.assertIn("restore", said)
        self.assertEqual(self.state(), before)

    def pin(self) -> None:
        held = self.held(self.experiment)
        held["row"] = ROW
        held["writing"]["designation"]["row"] = ROW
        held.pop("creating")
        self.restore_held(held)

    def restore_held(self, held: dict[str, Any]) -> None:
        self.connection.execute("UPDATE item SET fields = ? WHERE id = ?",
                                (json.dumps({"experiments": held}), self.experiment))

    def down(self) -> tuple[int, str]:
        with unittest.mock.patch.object(PUBLISH, "DATABASE_HOME", self.root / "no-home"):
            return self.deliver(self.experiment)

    def unknown(self) -> tuple[int, str]:
        request = self.request(self.experiment)
        saved = self.path(self.experiment).read_bytes()
        self.path(self.experiment).write_text(json.dumps(dict(request, item=999)))
        try:
            return self.deliver(self.experiment, request["fingerprint"])
        finally:
            self.path(self.experiment).write_bytes(saved)

    def test_each_designation_change_after_the_plan_refuses_even_after_a_rewrite(self) -> None:
        drained = self.request(self.experiment)["fingerprint"]
        third = self.add("Another")
        self.designate(third, "yes")
        for change in ("off", "of:%d" % third, "row:" + OTHER):
            with self.subTest(change=change):
                saved = self.held(self.experiment)
                self.designate(self.experiment, change)
                self.project()
                status, said = self.deliver(self.experiment, drained)
                self.assertEqual(status, 1, said)
                self.assertIn("left in place", said)
                self.restore_held(saved)
        self.designate(self.experiment, "off")
        self.designate(self.experiment, "yes")
        self.project()
        status, said = self.deliver(self.experiment, drained)
        self.assertEqual(status, 1, said)
        self.assertIn("moved since the plan (since)", said)

    def test_a_stop_after_record_row_reruns_to_unchanged_and_removes_the_request(self) -> None:
        receipt = PUBLISH.receipts() / self.name(self.experiment)
        held = receipt.read_text()
        receipt.unlink()
        receipt.mkdir()
        status, said = self.deliver(self.experiment)
        self.assertEqual(status, 1, said)
        self.assertIn("cannot write receipt", said)
        receipt.rmdir()
        receipt.write_text(held)
        status, said = self.deliver(self.experiment)
        self.assertEqual(status, 0, said)
        self.assertFalse(self.path(self.experiment).exists())
        self.assertEqual(self.comments(self.experiment).count("Projected to experiments: " + url(ROW)), 1)

    def test_a_newer_generation_still_confirms_the_drained_plan(self) -> None:
        drained = self.request(self.experiment)["fingerprint"]
        self.status(self.experiment, "in_progress")
        self.project()
        status, said = self.deliver(self.experiment, drained)
        self.assertEqual(status, 0, said)
        self.assertIn("newer request is pending", said)
        self.project()
        planned = self.planned(self.experiment, self.live(row=ROW, Status="Todo"))
        self.assertEqual((planned["properties"], planned["yielded"]), ({"Status": "In Progress"}, []))

    def test_an_older_record_url_refuses_the_row_channel(self) -> None:
        """Rollback: an older `delivered` calls `record_url`, which refuses `notion-row` and exits 1."""
        from sd_db.channels import UrlRefusal, record_url  # noqa: PLC0415
        with self.assertRaisesRegex(UrlRefusal, "notion-row"):
            record_url(self.connection, self.experiment, "/repos/example", "sd:1", "A", "notion-row",
                       url(ROW), "sd-research-kit")


class ContractTests(unittest.TestCase):
    """The drain is prose: the contract names its `notion-row` steps."""

    def test_the_contract_names_the_row_drain(self) -> None:
        text = " ".join(CONTRACT.read_text(encoding="utf-8").split())
        for phrase in ("`notion-row`", "sd-research-kit project --plan", "--missing",
                       "a failed read is unknown, not missing", "experiments before tasks",
                       "a `notion-row` request reads the channel `notion`",
                       "fetch and plan again", "Steps 4 and 5 do not apply to a row",
                       "a date's whole value, never its start alone",
                       "a relation's whole value, never a page of it"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
