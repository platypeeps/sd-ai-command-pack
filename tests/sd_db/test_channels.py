"""`sd_db.channels`: the one check on a repository's publish channels (sd:3462, design sd:3471).

The setting is a JSON object on the `repo` row. `validate` is the closed
vocabulary every write passes through; `repos.repo_channels` reads it back,
and a value it cannot read raises rather than reading as "no setting".
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sd_db import connect
from sd_db import schema as schema_module
from sd_db.channels import ChannelRefusal, dumps, outbound, validate
from sd_db.errors import SchemaTooOld
from sd_db.migrate import initialise, migrate
from sd_db.repos import RepoRefusal, repo_channels


class TheValidator(unittest.TestCase):
    def test_the_designs_example_passes_and_comes_back_the_same(self):
        value = {"obsidian": {"folder": "Briefs/example-research"}, "notion": {"folder": "Example"}, "drive": {}}
        self.assertEqual(validate(value), value)

    def test_one_channel_with_its_default_folder_is_a_setting(self):
        self.assertEqual(validate({"drive": {}}), {"drive": {}})

    def test_a_refusal_is_a_repo_refusal(self):
        self.assertTrue(issubclass(ChannelRefusal, RepoRefusal))

    def test_an_empty_object_refuses_because_clearing_is_null(self):
        with self.assertRaisesRegex(ChannelRefusal, "none"):
            validate({})

    def test_a_value_that_is_not_an_object_refuses(self):
        for value in ([], "obsidian", None, 3, ["obsidian"]):
            with self.subTest(value=value), self.assertRaisesRegex(ChannelRefusal, "an object"):
                validate(value)

    def test_each_key_outside_the_vocabulary_refuses_by_name(self):
        for key in ("slack", "email", "jira", "github", "Obsidian", ""):
            with self.subTest(key=key), self.assertRaises(ChannelRefusal) as caught:
                validate({"obsidian": {}, key: {}})
            self.assertIn(repr(key), str(caught.exception))
            self.assertIn("obsidian, notion or drive", str(caught.exception))

    def test_a_channel_that_is_not_an_object_refuses_naming_it(self):
        for value in ("Briefs/x", True, None, ["Briefs/x"]):
            with self.subTest(value=value), self.assertRaises(ChannelRefusal) as caught:
                validate({"drive": value})
            self.assertIn("drive", str(caught.exception))

    def test_a_key_inside_a_channel_other_than_folder_refuses_naming_both(self):
        # Ids stay per machine or per document: `space=`, `page=`, `file=`.
        for key in ("space", "page", "file", "id", "team"):
            with self.subTest(key=key), self.assertRaises(ChannelRefusal) as caught:
                validate({"notion": {"folder": "Example", key: "x"}})
            self.assertIn("notion", str(caught.exception))
            self.assertIn(repr(key), str(caught.exception))

    def test_a_folder_that_is_not_a_non_empty_string_refuses(self):
        for folder in ("", 3, None, ["a"], {"a": 1}):
            with self.subTest(folder=folder), self.assertRaises(ChannelRefusal) as caught:
                validate({"obsidian": {"folder": folder}})
            self.assertIn("obsidian", str(caught.exception))

    def test_a_relative_path_is_a_folder_for_obsidian_and_drive(self):
        for channel in ("obsidian", "drive"):
            for folder in ("Briefs/x", "Research/Example", "Notes: 2026", "a b/c.d"):
                with self.subTest(channel=channel, folder=folder):
                    self.assertEqual(validate({channel: {"folder": folder}}), {channel: {"folder": folder}})

    def test_names_never_paths_out_ids_or_urls(self):
        refused = {
            "/Briefs/x": "leading /",
            "Briefs/../x": "..",
            "..": "..",
            "Briefs/./x": ".",
            "Briefs//x": "empty",
            "Briefs/x/": "empty",
            "Briefs/ /x": "empty",
            "Briefs\nx": "control",
            "Briefs\x7fx": "control",
            "Briefs‮x": "control",
            "https://example.test/x": "URL",
            "obsidian://open?vault=v": "URL",
        }
        for channel in ("obsidian", "drive", "notion"):
            for folder, reason in refused.items():
                with self.subTest(channel=channel, folder=folder), self.assertRaises(ChannelRefusal) as caught:
                    validate({channel: {"folder": folder}})
                self.assertIn(channel, str(caught.exception))
                self.assertIn(reason, str(caught.exception))

    def test_a_notion_folder_is_one_page_name_with_no_slash(self):
        self.assertEqual(validate({"notion": {"folder": "Example"}}), {"notion": {"folder": "Example"}})
        with self.assertRaises(ChannelRefusal) as caught:
            validate({"notion": {"folder": "A/B"}})
        self.assertIn("notion", str(caught.exception))
        self.assertIn("one page name", str(caught.exception))

    def test_a_notion_page_id_is_refused_as_a_folder_in_either_spelling(self):
        """Ids stay per machine or per document; a folder is a name (codex review, C1)."""
        for folder in ("12345678-1234-1234-1234-123456789abc", "12345678123412341234123456789ABC"):
            for channel in ("notion", "drive", "obsidian"):
                with self.subTest(channel=channel, folder=folder), self.assertRaises(ChannelRefusal) as caught:
                    validate({channel: {"folder": folder}})
                self.assertIn("an id", str(caught.exception))
        # A name that only holds hex digits among other words stays a name.
        self.assertEqual(validate({"notion": {"folder": "Q3 deadbeef"}}), {"notion": {"folder": "Q3 deadbeef"}})

    def test_the_canonical_text_is_sorted_and_compact(self):
        value = {"obsidian": {"folder": "Briefs/x"}, "drive": {}}
        self.assertEqual(dumps(value), '{"drive":{},"obsidian":{"folder":"Briefs/x"}}')
        self.assertEqual(dumps(None), "none")


class TheFeed(unittest.TestCase):
    """sd:3980: a repo's one RSS/Atom subscription, the inbound `feed` key.

    `sd-watchlist` reads it; it is not an outbound channel, so it neither
    turns publishing on nor leaves the outbound channels off."""

    FEED = "https://example.test/feed.xml"

    def test_a_feed_url_is_a_setting_beside_the_outbound_channels(self):
        value = {"feed": {"url": self.FEED}, "notion": {}}
        self.assertEqual(validate(value), value)
        self.assertEqual(validate({"feed": {"url": "http://example.test/r/x/.rss?sort=new"}}),
                         {"feed": {"url": "http://example.test/r/x/.rss?sort=new"}})

    def test_a_feed_needs_one_http_url_and_nothing_else(self):
        for entry in ({}, {"url": ""}, {"url": 3}, {"url": "example.test/feed"}, {"url": "ftp://example.test/f"},
                      {"url": "file:///etc/passwd"}, {"url": "https://"}, {"url": "https://user:pw@example.test/f"},
                      {"url": "https://example.test/f\n"}, {"url": "https://example.test/ f"},
                      {"url": self.FEED, "folder": "x"}, {"folder": "x"}):
            with self.subTest(entry=entry), self.assertRaises(ChannelRefusal) as caught:
                validate({"feed": entry})
            self.assertIn("feed", str(caught.exception))

    def test_publishing_reads_only_the_outbound_channels(self):
        """A setting that names only a feed says nothing about publishing:
        it publishes as no setting. Beside an outbound channel, the feed is
        dropped and the outbound rule stands: a channel left out is off."""
        self.assertIsNone(outbound({"feed": {"url": self.FEED}}))
        self.assertEqual(outbound({"feed": {"url": self.FEED}, "drive": {}}), {"drive": {}})
        self.assertIsNone(outbound(None))
        self.assertEqual(outbound({"obsidian": {"folder": "Notes"}}), {"obsidian": {"folder": "Notes"}})


class TheReader(unittest.TestCase):
    """`repo_channels`: the validated setting, `None` for no setting, and a
    raise for anything it cannot read. Unknown is never "no setting"."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "sd.db"

    def _current(self):
        initialise(self.path)
        connection = connect(self.path)
        self.addCleanup(connection.close)
        connection.execute(
            "INSERT INTO repo (path, created_at, updated_at) VALUES ('/srv/one', 't', 't'), ('/srv/two', 't', 't')")
        return connection

    def test_a_null_row_and_an_absent_row_read_none(self):
        connection = self._current()
        self.assertIsNone(repo_channels(connection, "/srv/one"))
        self.assertIsNone(repo_channels(connection, "/srv/absent"))

    def test_a_stored_setting_reads_back_validated(self):
        connection = self._current()
        connection.execute("UPDATE repo SET channels = ? WHERE path = '/srv/one'",
                           ('{"notion": {"folder": "Example"}, "drive": {}}',))
        self.assertEqual(repo_channels(connection, "/srv/one"), {"notion": {"folder": "Example"}, "drive": {}})
        self.assertIsNone(repo_channels(connection, "/srv/two"))

    def test_a_stored_value_the_validator_refuses_raises_naming_the_repository(self):
        connection = self._current()
        for stored in ('{"slack": {}}', '{}', '[]', '{"notion": {"folder": "A/B"}}'):
            connection.execute("UPDATE repo SET channels = ? WHERE path = '/srv/one'", (stored,))
            with self.subTest(stored=stored), self.assertRaises(ChannelRefusal) as caught:
                repo_channels(connection, "/srv/one")
            self.assertIn("/srv/one", str(caught.exception))

    def test_the_column_refuses_text_that_is_not_json(self):
        connection = self._current()
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("UPDATE repo SET channels = 'obsidian' WHERE path = '/srv/one'")

    def test_a_database_not_yet_at_twenty_nine_reads_unknown_not_none(self):
        """Failure table, row "library at 29, database at 28": a read of the
        missing column raises `SchemaTooOld`, which names `migrate`."""
        through = [m for m in schema_module.migrations() if m[0] <= 28]
        with mock.patch("sd_db.migrate.migrations", return_value=through):
            migrate(self.path)
        raw = sqlite3.connect(self.path)
        raw.execute("INSERT INTO repo (path, created_at, updated_at) VALUES ('/srv/one', 't', 't')")
        raw.commit()
        raw.close()
        connection = connect(self.path, write=False)
        self.addCleanup(connection.close)
        with self.assertRaises(SchemaTooOld) as caught:
            repo_channels(connection, "/srv/one")
        self.assertIn("bin/sd-db migrate", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
