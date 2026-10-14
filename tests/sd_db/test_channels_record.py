"""`sd_db.channels.record_url`: the published URL reaches the item row (sd:3979, design sd:3471).

One field, `fields.published`, keyed by repository and document, and one
`comment` note per change. A refusal writes nothing: a restore still open, or
an item that is not there.
"""

import json
import tempfile
import unittest
from pathlib import Path

from sd_db import connect
from sd_db.channels import UrlRefusal, record_url
from sd_db.migrate import initialise
from sd_db.writes import create_item, record_state

URL = "https://example.test/p"


class RecordUrl(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / "sd.db"
        initialise(path)
        self.connection = connect(path)
        self.addCleanup(self.connection.close)
        self.item = create_item(self.connection, kind="task", title="Publish the brief")
        self.repo = str(Path(self.tmp.name) / "research" / "example-research")

    def published(self, item=None):
        row = self.connection.execute("SELECT fields FROM item WHERE id = ?", (item or self.item,)).fetchone()
        return json.loads(row["fields"] or "{}").get("published")

    def notes(self):
        return [row["body"] for row in self.connection.execute(
            "SELECT body FROM note WHERE item = ? AND kind = 'comment' ORDER BY id", (self.item,))]

    def record(self, **changes):
        given = dict(item=self.item, repo=self.repo, document="a", title="A", channel="notion", url=URL,
                     who="sd-research-kit")
        given.update(changes)
        return record_url(self.connection, **given)

    def test_the_url_lands_on_the_item_with_one_note(self):
        self.assertEqual(self.record(), "recorded")
        self.assertEqual(self.published(), {f"{self.repo}::a": {"title": "A", "notion": URL}})
        self.assertEqual(self.notes(), [f"Published notion a: {URL}"])

    def test_the_same_url_again_is_unchanged_and_adds_no_note(self):
        self.record()
        self.assertEqual(self.record(), "unchanged")
        self.assertEqual(self.notes(), [f"Published notion a: {URL}"])

    def test_a_second_channel_joins_the_same_document(self):
        self.record()
        self.record(channel="drive", url="https://example.test/d")
        self.assertEqual(self.published()[f"{self.repo}::a"],
                         {"title": "A", "notion": URL, "drive": "https://example.test/d"})
        self.assertEqual(len(self.notes()), 2)

    def test_two_repositories_with_one_basename_get_two_keys(self):
        other = str(Path(self.tmp.name) / "elsewhere" / "example-research")
        self.record()
        self.record(repo=other, url="https://example.test/q")
        self.assertEqual(sorted(self.published()), sorted([f"{self.repo}::a", f"{other}::a"]))

    def test_an_unknown_item_refuses_and_writes_nothing(self):
        with self.assertRaisesRegex(UrlRefusal, "sd:999"):
            self.record(item=999)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM note WHERE kind = 'comment'").fetchone()[0], 0)

    def test_an_open_restore_refuses_and_writes_nothing(self):
        record_state(self.connection, "restore", key="example", body={})
        with self.assertRaisesRegex(UrlRefusal, "restore"):
            self.record()
        self.assertIsNone(self.published())
        self.assertEqual(self.notes(), [])

    def test_a_channel_outside_the_vocabulary_refuses(self):
        with self.assertRaisesRegex(UrlRefusal, "slack"):
            self.record(channel="slack")
        self.assertIsNone(self.published())

    def test_other_fields_on_the_item_are_kept(self):
        self.connection.execute("UPDATE item SET fields = ? WHERE id = ?",
                                (json.dumps({"writing": {"published_urls": ["https://example.test/w"]}}), self.item))
        self.record()
        row = self.connection.execute("SELECT fields FROM item WHERE id = ?", (self.item,)).fetchone()
        self.assertEqual(json.loads(row["fields"])["writing"], {"published_urls": ["https://example.test/w"]})


if __name__ == "__main__":
    unittest.main()
