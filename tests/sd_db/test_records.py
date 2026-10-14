"""Base rows read and written through `sd_db.records` once the database is their source (sd:3973).

Rows come from the real vault import over a fixture vault, as the sitting
lands them; the rules come from a fixture `sd plugin list --json` entry that
carries the `rules` block the pack reports, with the driver flipped to `db`.
"""

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sd_db import connect, create_item
from sd_db.migrate import initialise
from sd_db.records import RecordRefused, add_row, edit_row, get_row, list_rows, render, rules_for
from sd_db.sources import MigrationRefused, run
from sd_db.sources.vault import Reader
from sd_db.workflow import MissingItem, StaleItem, item_state

from . import support

#: The writing manifest's `blog-idea` and `topic` rules, as the pack's `validate_kind` returns them.
RULES = {
    "blog-idea": {
        "fields": ["contexts", "content-type", "status", "score", "my-rating", "dateCreated",
                   "description", "tags"],
        "initial-status": "inbox", "protected-fields": ["my-rating"], "floor": {"score": 6},
        "transitions": {"inbox": ["accepted", "declined"], "accepted": ["drafting", "declined"],
                        "drafting": ["published", "declined"]},
        "human-only": {"accept": "accepted", "decline": "declined"},
    },
    "topic": {
        "fields": ["contexts", "content-type", "status", "slug", "dateCreated", "description", "tags"],
        "initial-status": "candidate", "unique-fields": ["slug"],
        "transitions": {"candidate": ["active", "parked", "retired"], "active": ["parked", "retired"],
                        "parked": ["active", "retired"]},
    },
}

META_BIND = "**Status:** `INPUT[inlineSelect(option(inbox), option(declined)):status]`"


def flipped(**extra):
    """The entry after the flip: the same kinds, `store.driver` `db`, and the pack's `rules`."""
    entry = support.plugin_entry(rules=json.loads(json.dumps(RULES)), **extra)
    entry["store"]["driver"] = "db"
    return entry


class RecordsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        initialise(root / "sd.db")
        self.db = connect(root / "sd.db")
        self.addCleanup(self.db.close)
        vault = support.vault(root / "vault", ideas={"first idea": "inbox", "second idea": "drafting"},
                              topics={"a topic": "active"})
        sitting = run(self.db, Reader.from_plugins([support.plugin_entry()],
                                                   environ={"OBSIDIAN_VAULT": str(vault)}))
        self.assertTrue(sitting.clean)
        self.home = root / "home"
        # Each write renders the mirror (sd:3976): into this vault, with these rules.
        for patcher in (patch.dict("os.environ", {"OBSIDIAN_VAULT": str(vault)}),
                        patch("sd_db.records.plugin_entries", return_value=[flipped()])):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.assertTrue(render(self.db, home=self.home, entries=[flipped()]).ok)
        self.idea = self.rules("blog-idea")
        self.topic = self.rules("topic")

    def rules(self, kind, entries=None):
        return rules_for(kind, home=self.home, entries=[flipped()] if entries is None else entries)

    def row(self, title, kind="blog-idea"):
        return get_row(self.db, kind=kind, title=title)

    def notes(self, item):
        return [(note["kind"], note["body"]) for note in item_state(self.db, item)["notes"]]

    def counts(self):
        return tuple(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("item", "note"))


class TheRules(RecordsCase):
    def test_the_rules_come_from_the_plugin_list_entry(self):
        self.assertEqual((self.idea.kind, self.idea.prefix, self.idea.driver, self.idea.base),
                         ("blog-idea", "sdw", "db", "System/Databases/Blog Ideas"))
        self.assertEqual(self.idea.stages, support.BLOG_IDEA)
        self.assertEqual((self.idea.initial, self.idea.floor, self.idea.protected),
                         ("inbox", {"score": 6}, ("my-rating",)))
        self.assertEqual(self.idea.human_only, {"accept": "accepted", "decline": "declined"})
        self.assertEqual(self.topic.unique, ("slug",))

    def test_a_pack_that_reports_no_rules_refuses_rather_than_reading_as_no_rules(self):
        entry = flipped()
        del entry["rules"]
        with self.assertRaisesRegex(RecordRefused, "reports no `rules` for kind 'blog-idea'"):
            self.rules("blog-idea", [entry])

    def test_an_unreadable_plugin_refuses_because_it_may_declare_the_kind(self):
        for broken in ({"root": "/plugins/other", "readable": False, "why": "no manifest"},
                       {**flipped(prefix="oth"), "workflow": {}, "manifestError": "bad kinds"}):
            with self.subTest(broken=broken.get("why") or broken.get("manifestError")), \
                    self.assertRaisesRegex(RecordRefused, "cannot be read"):
                self.rules("blog-idea", [flipped(), broken])

    def test_a_kind_needs_exactly_one_declaring_plugin(self):
        with self.assertRaisesRegex(RecordRefused, "0 registered plugins declare a `workflow` for kind 'market'"):
            self.rules("market")
        with self.assertRaisesRegex(RecordRefused, "2 registered plugins"):
            self.rules("topic", [flipped(), flipped(prefix="oth")])

    def test_a_pack_that_cannot_answer_refuses(self):
        with patch("sd_db.records.plugin_entries", side_effect=MigrationRefused("exited 1: boom")) as asked, \
                self.assertRaisesRegex(RecordRefused, "exited 1: boom"):
            rules_for("topic", home=self.home)
        asked.assert_called_once_with(home=self.home, environ=None)


class TheReads(RecordsCase):
    def test_list_rows_reads_base_rows_by_kind_and_stage_only(self):
        create_item(self.db, kind="task", title="not a base row")
        self.assertEqual([row["title"] for row in list_rows(self.db)], ["first idea", "second idea", "a topic"])
        self.assertEqual([row["title"] for row in list_rows(self.db, "blog-idea", stage="drafting")],
                         ["second idea"])
        [topic] = list_rows(self.db, "topic")
        self.assertEqual(topic["fields"]["kind"], "topic")
        self.assertIn("the topic body of a topic.", topic["body"])

    def test_get_row_by_id_or_title_carries_the_revision(self):
        row = self.row("first idea")
        self.assertEqual(row["stage"], "inbox")
        self.assertEqual(row["revision"], item_state(self.db, row["id"])["revision"])
        self.assertEqual(get_row(self.db, row["id"])["external_id"],
                         "blog-idea:System/Databases/Blog Ideas/first idea.md")
        with self.assertRaises(MissingItem):
            self.row("no such idea")
        with self.assertRaisesRegex(RecordRefused, "not a base row"):
            get_row(self.db, create_item(self.db, kind="task", title="a task"))


class TheStageMove(RecordsCase):
    def test_a_stage_move_sets_the_mapped_status_and_writes_both_notes(self):
        row = self.row("first idea")
        moved = edit_row(self.db, row["id"], self.idea, revision=row["revision"], who="operator", stage="accepted")
        self.assertEqual((moved["stage"], moved["status"]), ("accepted", "ready"))
        self.assertEqual(self.notes(row["id"])[-2:], [
            ("comment", "Stage inbox -> accepted by operator"),
            ("status_change", "planning -> ready by operator: stage inbox -> accepted")])

    def test_a_move_that_keeps_the_status_writes_the_comment_only(self):
        row = self.row("first idea")
        rules = dataclasses.replace(self.idea, stages={**self.idea.stages, "accepted": "planning"})
        edit_row(self.db, row["id"], rules, revision=row["revision"], who="operator", stage="accepted")
        self.assertEqual(self.notes(row["id"])[1:], [("comment", "Stage inbox -> accepted by operator")])

    def test_a_move_the_graph_or_the_map_does_not_allow_refuses_and_writes_nothing(self):
        row, before = self.row("first idea"), self.counts()
        for stage, refusal in (("drafting", "allows 'inbox' -> accepted, declined"),
                               ("someday", "names no stage 'someday'")):
            with self.subTest(stage=stage), self.assertRaisesRegex(RecordRefused, refusal):
                edit_row(self.db, row["id"], self.idea, revision=row["revision"], who="operator", stage=stage)
        self.assertEqual((self.counts(), self.row("first idea")["revision"]), (before, row["revision"]))

    def test_a_stale_revision_refuses(self):
        row = self.row("first idea")
        edit_row(self.db, row["id"], self.idea, revision=row["revision"], who="operator", stage="accepted")
        with self.assertRaises(StaleItem):
            edit_row(self.db, row["id"], self.idea, revision=row["revision"], who="operator", stage="declined")
        with self.assertRaisesRegex(RecordRefused, "names the revision"):
            edit_row(self.db, row["id"], self.idea, revision=None, who="operator", stage="declined")  # type: ignore[arg-type]

    def test_rules_of_another_kind_refuse(self):
        row = self.row("first idea")
        with self.assertRaisesRegex(RecordRefused, "is not a topic row from the vault"):
            edit_row(self.db, row["id"], self.topic, revision=row["revision"], who="operator", stage="active")

    def test_a_failure_after_the_row_write_leaves_the_row_and_its_notes_as_they_were(self):
        row, before = self.row("first idea"), self.counts()
        with patch("sd_db.records._transition", side_effect=RuntimeError("stopped")), \
                self.assertRaisesRegex(RuntimeError, "stopped"):
            edit_row(self.db, row["id"], self.idea, revision=row["revision"], who="operator", stage="accepted")
        self.assertEqual((self.counts(), self.row("first idea")["revision"]), (before, row["revision"]))


class TheFieldsAndBody(RecordsCase):
    def test_fields_and_a_verbatim_body_are_set_with_a_comment(self):
        row = self.row("first idea")
        body = f"\n# first idea\n\n{META_BIND}\n\n## Score\n\n7, because.\n"
        edited = edit_row(self.db, row["id"], self.idea, revision=row["revision"], who="operator",
                          fields={"score": "7", "my-rating": None}, body=body)
        self.assertEqual(edited["body"], body)
        self.assertEqual((edited["fields"]["score"], edited["fields"]["my-rating"], edited["fields"]["kind"]),
                         ("7", None, "blog-idea"))
        self.assertEqual(edited["stage"], "inbox")
        self.assertEqual(self.notes(row["id"])[-1], ("comment", "Set my-rating, score, body by operator"))

    def test_an_edit_that_changes_nothing_writes_nothing(self):
        row, before = self.row("first idea"), self.counts()
        same = edit_row(self.db, row["id"], self.idea, revision=row["revision"], who="operator",
                        stage="inbox", fields={"content-type": "blog-idea"}, body=row["body"])
        self.assertEqual((self.counts(), same["revision"]), (before, row["revision"]))

    def test_an_undeclared_or_reserved_field_refuses(self):
        row = self.row("first idea")
        for fields, refusal in (({"colour": "red"}, "declares no field 'colour'"),
                                ({"kind": "topic"}, "declares no field 'kind'"),
                                ({"mirror-hash": "abc"}, "declares no field 'mirror-hash'"),
                                ({"status": "accepted"}, "status field is its stage"),
                                ({"description": "two\nlines"}, "one line of text"),
                                ({"tags": [{"nested": 1}]}, "one line of text")):
            with self.subTest(fields=fields), self.assertRaisesRegex(RecordRefused, refusal):
                edit_row(self.db, row["id"], self.idea, revision=row["revision"], who="operator", fields=fields)

    def test_a_floored_field_under_its_floor_refuses(self):
        row = self.row("first idea")
        for value in ("5", "nan", "high", None):
            with self.subTest(value=value), self.assertRaisesRegex(RecordRefused, "`floor`"):
                edit_row(self.db, row["id"], self.idea, revision=row["revision"], who="operator",
                         fields={"score": value})

    def test_a_unique_field_refuses_a_value_another_row_holds(self):
        topic = self.row("a topic", "topic")
        edit_row(self.db, topic["id"], self.topic, revision=topic["revision"], who="operator",
                 fields={"slug": "agents"})
        again = self.row("a topic", "topic")
        edit_row(self.db, topic["id"], self.topic, revision=again["revision"], who="operator",
                 fields={"slug": "agents", "description": "its own slug again"})
        with self.assertRaisesRegex(RecordRefused, "`unique-fields` declares 'slug' unique"):
            add_row(self.db, self.topic, title="another topic", who="operator", fields={"slug": "agents"})


class TheAdd(RecordsCase):
    def test_a_new_row_takes_the_import_shape_from_its_base_and_title(self):
        added = add_row(self.db, self.idea, title="third idea", who="operator",
                        fields={"score": "8", "tags": ["blog-idea"]}, body="# third idea\n")
        self.assertEqual((added["kind"], added["source"], added["external_id"], added["path"]),
                         ("idea", "vault", "blog-idea:System/Databases/Blog Ideas/third idea.md",
                          "System/Databases/Blog Ideas/third idea.md"))
        self.assertEqual((added["stage"], added["status"], added["body"]), ("inbox", "planning", "# third idea\n"))
        self.assertEqual(added["fields"], {"score": "8", "tags": ["blog-idea"], "kind": "blog-idea"})
        self.assertEqual(self.notes(added["id"]), [("status_change", "opened as planning")])
        self.assertEqual(self.row("third idea")["id"], added["id"])

    def test_a_stage_other_than_the_initial_one_must_be_a_move_from_it(self):
        accepted = add_row(self.db, self.idea, title="third idea", who="operator", fields={"score": "6"},
                           stage="accepted")
        self.assertEqual((accepted["stage"], accepted["status"]), ("accepted", "ready"))
        with self.assertRaisesRegex(RecordRefused, "'drafting' is not among them"):
            add_row(self.db, self.idea, title="fourth idea", who="operator", fields={"score": "6"},
                    stage="drafting")

    def test_every_floored_field_must_be_given(self):
        before = self.counts()
        with self.assertRaisesRegex(RecordRefused, "`floor` bounds 'score'"):
            add_row(self.db, self.idea, title="third idea", who="operator")
        self.assertEqual(self.counts(), before)

    def test_a_title_must_name_one_new_file_in_the_vault(self):
        before = self.counts()
        for title, refusal in (("A Topic", "already has the file name 'A Topic.md'"),
                               ("first idea", "already has the file name"),
                               ("../escaped", "must name one file"),
                               (".hidden", "must name one file"),
                               ("two\nlines", "must name one file")):
            with self.subTest(title=title), self.assertRaisesRegex(RecordRefused, refusal):
                add_row(self.db, self.idea, title=title, who="operator", fields={"score": "7"})
        self.assertEqual(self.counts(), before)


    def test_a_title_equal_once_unicode_normalized_is_taken(self):
        # macOS keeps one file for `Café.md` composed (NFC) and decomposed (NFD).
        composed, decomposed = "Caf\u00e9", "Cafe\u0301"
        added = add_row(self.db, self.idea, title=composed, who="operator", fields={"score": "7"})
        before = self.counts()
        for title in (decomposed, decomposed.upper()):
            with self.subTest(title=ascii(title)), self.assertRaisesRegex(RecordRefused, "already has the file name"):
                add_row(self.db, self.topic, title=title, who="operator")
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.row(decomposed)["id"], added["id"])
        self.assertEqual(self.row("FIRST IDEA")["title"], "first idea")

class TheImportShape(RecordsCase):
    """A written row holds what the import would land from the same note."""

    def dated(self):
        entry = flipped()
        entry["workflow"]["blog-idea"]["due-field"] = "deadline"
        entry["rules"]["blog-idea"]["fields"].append("deadline")
        return self.rules("blog-idea", [entry])

    def test_the_declared_due_field_sets_due_and_must_be_a_date(self):
        rules = self.dated()
        added = add_row(self.db, rules, title="third idea", who="operator",
                        fields={"score": "7", "deadline": "2026-12-01"})
        self.assertEqual(added["due"], "2026-12-01")
        moved = edit_row(self.db, added["id"], rules, revision=added["revision"], who="operator",
                         fields={"deadline": ""})
        self.assertIsNone(moved["due"])
        for value in ("next week", "2026-02-30", ["2026-12-01"]):
            with self.subTest(value=value), self.assertRaisesRegex(RecordRefused, "YYYY-MM-DD"):
                edit_row(self.db, added["id"], rules, revision=moved["revision"], who="operator",
                         fields={"deadline": value})

    def test_date_created_sets_created_at_as_the_import_does(self):
        added = add_row(self.db, self.idea, title="third idea", who="operator",
                        fields={"score": "7", "dateCreated": "2020-01-01"})
        self.assertEqual(added["created_at"], "2020-01-01")
        row = self.row("first idea")
        self.assertEqual(row["created_at"], "2026-06-15")
        edited = edit_row(self.db, row["id"], self.idea, revision=row["revision"], who="operator",
                          fields={"dateCreated": "2021-01-01"})
        self.assertEqual((edited["created_at"], edited["fields"]["dateCreated"]), ("2021-01-01", "2021-01-01"))


class BeforeTheFlip(RecordsCase):
    def test_both_writers_refuse_while_the_vault_is_the_source(self):
        entry = flipped()
        entry["store"]["driver"] = "vault"
        rules, row, before = self.rules("blog-idea", [entry]), self.row("first idea"), self.counts()
        with self.assertRaisesRegex(RecordRefused, "next import would overwrite"):
            edit_row(self.db, row["id"], rules, revision=row["revision"], who="operator", stage="accepted")
        with self.assertRaisesRegex(RecordRefused, "next import would overwrite"):
            add_row(self.db, rules, title="third idea", who="operator", fields={"score": "7"})
        self.assertEqual(self.counts(), before)


if __name__ == "__main__":
    unittest.main()
