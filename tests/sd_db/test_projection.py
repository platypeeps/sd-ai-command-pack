"""`sd_db.projection`: the experiments designation, its maps, and `record_row` (sd:3982).

Nothing here reaches Notion: the designation is a field on the item row, and
`record_row` is the drain's last step, handed a URL.
"""

import json
import tempfile
import unittest
from pathlib import Path

from sd_db import connect
from sd_db.migrate import initialise
from sd_db.projection import (
    ProjectionRefusal,
    designate,
    priority_value,
    record_row,
    row_id,
    stage_value,
    status_value,
    validate,
)
from sd_db.workflow import StaleItem, item_state
from sd_db.writes import create_item, record_state

ROW = "3c9f52b1-5782-81a7-a466-fb0e2df4d928"
OTHER_ROW = "3cff52b1-5782-806a-acb0-ca0c8f41524b"
URL = "https://example.test/" + ROW.replace("-", "")
SINCE = "2026-10-14T20:30:00+00:00"


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / "sd.db"
        initialise(path)
        self.connection = connect(path)
        self.addCleanup(self.connection.close)

    def item(self, title="An experiment", **columns):
        return create_item(self.connection, kind=columns.pop("kind", "task"), title=title, **columns)

    def held(self, item):
        row = self.connection.execute("SELECT fields FROM item WHERE id = ?", (item,)).fetchone()
        return json.loads(row["fields"] or "{}").get("experiments")

    def put(self, item, value):
        self.connection.execute("UPDATE item SET fields = ? WHERE id = ?",
                                (json.dumps({"experiments": value}), item))

    def comments(self, item):
        return [row["body"] for row in self.connection.execute(
            "SELECT body FROM note WHERE item = ? AND kind = 'comment' ORDER BY id", (item,))]


class Shapes(unittest.TestCase):
    def test_the_two_designations_validate(self):
        self.assertEqual(validate({"as": "experiment", "since": SINCE})["as"], "experiment")
        self.assertEqual(validate({"as": "task", "of": 4021, "since": SINCE})["of"], 4021)
        self.assertEqual(validate({"as": "off", "row": ROW, "since": SINCE})["row"], ROW)

    def test_each_bad_shape_refuses_naming_the_key(self):
        for value, named in (
                ([], "object"),
                ({"as": "page", "since": SINCE}, "experiments.as"),
                ({"as": "task", "since": SINCE}, "experiments.of"),
                ({"as": "task", "of": "4021", "since": SINCE}, "experiments.of"),
                ({"as": "experiment", "of": 4021, "since": SINCE}, "experiments.of"),
                ({"as": "experiment"}, "experiments.since"),
                ({"as": "experiment", "since": SINCE, "row": "Experiments"}, "experiments.row"),
                ({"as": "experiment", "since": SINCE, "colour": "red"}, "colour"),
                ({"as": "experiment", "since": SINCE, "writing": {"values": {}}}, "experiments.writing"),
                ({"as": "experiment", "since": SINCE, "yielded": "Status"}, "experiments.yielded")):
            with self.subTest(value=value), self.assertRaisesRegex(ProjectionRefusal, named):
                validate(value)

    def test_a_row_id_reads_from_every_spelling(self):
        for spelling in (ROW, ROW.replace("-", ""), ROW.upper(), URL, URL + "?pvs=4#block", "Title-" + ROW):
            with self.subTest(spelling=spelling):
                self.assertEqual(row_id(spelling), ROW)
        self.assertEqual(row_id("Experiments"), "")
        self.assertEqual(row_id(None), "")


class Maps(unittest.TestCase):
    def test_status_both_databases(self):
        self.assertEqual([status_value(s) for s in ("planning", "ready", "in_progress", "ready_to_send",
                                                    "blocked", "done")],
                         ["Todo", "Todo", "In Progress", "In Progress", "Blocked", "Done"])

    def test_stage_is_idea_for_a_work_idea_whatever_its_status(self):
        self.assertEqual(stage_value("work-idea", "in_progress"), "Idea")
        self.assertEqual([stage_value("task", s) for s in ("planning", "ready", "in_progress", "ready_to_send",
                                                           "blocked", "done")],
                         ["Scoping", "Scoping", "Running", "Running", "Running", "Evaluating"])

    def test_priority(self):
        self.assertEqual([priority_value(p) for p in (1, 2, 3, 4, None)], ["High", "Medium", "Low", "Low", None])


class Designate(Store):
    def setUp(self):
        super().setUp()
        self.experiment = self.item()
        self.task = self.item("A task")

    def test_yes_designates_an_experiment_with_a_since_and_a_note(self):
        designate(self.connection, self.experiment, ["yes"], who="tester")
        held = self.held(self.experiment)
        self.assertEqual(held["as"], "experiment")
        self.assertTrue(held["since"])
        self.assertEqual(self.comments(self.experiment), ["Updated experiments by tester"])

    def test_of_designates_a_task_of_an_experiment(self):
        designate(self.connection, self.experiment, ["yes"], who="tester")
        designate(self.connection, self.task, ["of:%d" % self.experiment], who="tester")
        self.assertEqual(self.held(self.task)["of"], self.experiment)

    def test_a_task_of_itself_refuses(self):
        with self.assertRaisesRegex(ProjectionRefusal, "task of itself"):
            designate(self.connection, self.task, ["of:%d" % self.task], who="tester")
        self.assertIsNone(self.held(self.task))

    def test_of_an_item_not_designated_experiment_refuses(self):
        with self.assertRaisesRegex(ProjectionRefusal, "sd:%d is not designated experiment" % self.experiment):
            designate(self.connection, self.task, ["of:%d" % self.experiment], who="tester")
        with self.assertRaisesRegex(ProjectionRefusal, "sd:999"):
            designate(self.connection, self.task, ["of:999"], who="tester")
        self.assertIsNone(self.held(self.task))

    def test_a_task_of_a_task_refuses(self):
        designate(self.connection, self.experiment, ["yes"], who="tester")
        designate(self.connection, self.task, ["of:%d" % self.experiment], who="tester")
        third = self.item("A third")
        with self.assertRaisesRegex(ProjectionRefusal, "not designated experiment"):
            designate(self.connection, third, ["of:%d" % self.task], who="tester")
        designate(self.connection, third, ["yes"], who="tester")
        with self.assertRaisesRegex(ProjectionRefusal, "one level"):
            designate(self.connection, self.experiment, ["of:%d" % third], who="tester")

    def test_off_keeps_the_row_and_yes_resumes_on_it(self):
        self.put(self.experiment, {"as": "experiment", "since": SINCE, "row": ROW, "written": {"Status": "Todo"}})
        designate(self.connection, self.experiment, ["off"], who="tester")
        self.assertEqual((self.held(self.experiment)["as"], self.held(self.experiment)["row"]), ("off", ROW))
        designate(self.connection, self.experiment, ["yes"], who="tester")
        held = self.held(self.experiment)
        self.assertEqual((held["as"], held["row"], held["written"]), ("experiment", ROW, {"Status": "Todo"}))

    def test_row_pins_a_row_and_drops_the_old_rows_state(self):
        self.put(self.experiment, {"as": "experiment", "since": SINCE, "row": OTHER_ROW, "url": "https://example.test/x",
                                   "written": {"Status": "Todo"}, "yielded": ["Status"], "confirmed": "f1"})
        designate(self.connection, self.experiment, ["row:%s" % URL], who="tester")
        held = self.held(self.experiment)
        self.assertEqual(held["row"], ROW)
        for key in ("url", "written", "yielded", "confirmed"):
            self.assertNotIn(key, held)

    def test_yes_with_row_adopts_from_the_start(self):
        designate(self.connection, self.experiment, ["yes", "row:" + ROW], who="tester")
        self.assertEqual(self.held(self.experiment)["row"], ROW)

    def test_new_drops_the_row_and_its_state(self):
        self.put(self.experiment, {"as": "experiment", "since": SINCE, "row": ROW, "written": {"Status": "Todo"},
                                   "creating": {"generation": "f1", "designation": {}, "database": ROW}})
        designate(self.connection, self.experiment, ["new"], who="tester")
        held = self.held(self.experiment)
        self.assertNotIn("row", held)
        self.assertNotIn("creating", held)
        self.assertNotIn("written", held)

    def test_an_equal_designation_writes_nothing(self):
        designate(self.connection, self.experiment, ["yes"], who="tester")
        before = self.held(self.experiment)
        designate(self.connection, self.experiment, ["yes"], who="tester")
        self.assertEqual(self.held(self.experiment), before)
        self.assertEqual(len(self.comments(self.experiment)), 1)

    def test_a_change_moves_since(self):
        self.put(self.experiment, {"as": "experiment", "since": SINCE})
        designate(self.connection, self.experiment, ["off"], who="tester")
        self.assertNotEqual(self.held(self.experiment)["since"], SINCE)

    def test_bad_values_refuse_and_write_nothing(self):
        for specs, said in ((["maybe"], "takes yes"), (["yes", "off"], "one of yes"), (["row:x"], "Notion page id"),
                            (["new", "row:" + ROW], "one of row"), (["of:x"], "item number"), ([], "needs a value"),
                            (["new"], "not designated")):
            with self.subTest(specs=specs), self.assertRaisesRegex(ProjectionRefusal, said):
                designate(self.connection, self.experiment, specs, who="tester")
        self.assertIsNone(self.held(self.experiment))

    def test_a_stale_revision_refuses(self):
        revision = item_state(self.connection, self.experiment)["revision"]
        designate(self.connection, self.experiment, ["yes"], who="tester")
        with self.assertRaises(StaleItem):
            designate(self.connection, self.experiment, ["off"], who="tester", expected_revision=revision)

    def test_an_open_restore_refuses(self):
        record_state(self.connection, "restore", key="example", body={})
        with self.assertRaisesRegex(ProjectionRefusal, "restore"):
            designate(self.connection, self.experiment, ["yes"], who="tester")
        self.assertIsNone(self.held(self.experiment))


class RecordRow(Store):
    """`record_row`: confirm the plan bound to a generation, or refuse and write nothing."""

    def setUp(self):
        super().setUp()
        self.experiment = self.item()

    def plan(self, generation="f1", row=None, values=None, creating=True, **extra):
        planned = {"as": "experiment", "of": None, "since": SINCE, "row": row}
        value = {"as": "experiment", "since": SINCE,
                 "writing": {"generation": generation, "designation": planned, "target": "experiments",
                             "values": values if values is not None else {"Status": "Todo"}}, **extra}
        if row is not None:
            value["row"] = row
        elif creating:
            value["creating"] = {"generation": generation, "designation": planned, "database": OTHER_ROW}
        self.put(self.experiment, value)

    def test_a_create_records_the_row_written_and_one_note(self):
        self.plan()
        self.assertEqual(record_row(self.connection, self.experiment, "f1", URL, "tester"), "recorded")
        held = self.held(self.experiment)
        self.assertEqual((held["row"], held["url"], held["written"], held["confirmed"]),
                         (ROW, URL, {"Status": "Todo"}, "f1"))
        self.assertNotIn("writing", held)
        self.assertNotIn("creating", held)
        self.assertEqual(self.comments(self.experiment), ["Projected to experiments: " + URL])

    def test_a_rerun_answers_unchanged_and_adds_no_note(self):
        self.plan()
        record_row(self.connection, self.experiment, "f1", URL, "tester")
        self.assertEqual(record_row(self.connection, self.experiment, "f1", URL, "tester"), "unchanged")
        self.assertEqual(len(self.comments(self.experiment)), 1)

    def test_an_update_merges_written(self):
        self.plan(row=ROW, values={"Status": "Done"}, written={"Status": "Todo", "Due": None}, url=URL)
        self.assertEqual(record_row(self.connection, self.experiment, "f1", URL, "tester"), "recorded")
        self.assertEqual(self.held(self.experiment)["written"], {"Status": "Done", "Due": None})
        self.assertEqual(self.comments(self.experiment), [])

    def test_each_refusal_writes_nothing(self):
        self.plan(row=ROW)
        before = self.held(self.experiment)
        for fingerprint, url, said in (("f2", URL, "no plan outstanding"),
                                       ("f1", "https://example.test/" + OTHER_ROW, "names row"),
                                       ("f1", "https://example.test/no-id", "no Notion page id"),
                                       ("", URL, "fingerprint")):
            with self.subTest(fingerprint=fingerprint, url=url), self.assertRaisesRegex(ProjectionRefusal, said):
                record_row(self.connection, self.experiment, fingerprint, url, "tester")
        self.assertEqual(self.held(self.experiment), before)

    def test_a_designation_moved_since_the_plan_refuses_for_each_key(self):
        for key, value in (("as", "off"), ("since", "2026-10-15T00:00:00+00:00"), ("row", OTHER_ROW)):
            with self.subTest(key=key):
                self.plan()
                held = self.held(self.experiment)
                held[key] = value
                self.put(self.experiment, held)
                with self.assertRaisesRegex(ProjectionRefusal, "moved since the plan"):
                    record_row(self.connection, self.experiment, "f1", URL, "tester")
                self.assertEqual(self.held(self.experiment), held)

    def test_unknown_item_restore_and_no_designation_refuse(self):
        with self.assertRaisesRegex(ProjectionRefusal, "sd:999"):
            record_row(self.connection, 999, "f1", URL, "tester")
        with self.assertRaisesRegex(ProjectionRefusal, "not designated"):
            record_row(self.connection, self.experiment, "f1", URL, "tester")
        self.plan()
        record_state(self.connection, "restore", key="example", body={})
        with self.assertRaisesRegex(ProjectionRefusal, "restore"):
            record_row(self.connection, self.experiment, "f1", URL, "tester")
        self.assertIn("writing", self.held(self.experiment))

    def test_unreadable_fields_refuse(self):
        self.connection.execute("UPDATE item SET fields = '{' WHERE id = ?", (self.experiment,))
        with self.assertRaisesRegex(ProjectionRefusal, "not JSON"):
            record_row(self.connection, self.experiment, "f1", URL, "tester")


if __name__ == "__main__":
    unittest.main()
