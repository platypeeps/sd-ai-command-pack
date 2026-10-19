"""Status reads one shared projection and never invents a second attention policy."""

from __future__ import annotations

import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import sd_db
from sd_db import contributions
from sd_db.migrate import initialise

from tests.test_sd_status import status


class ContributionStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.database = sd_db.default_path(home=self.root)
        initialise(self.database)
        environment = patch.dict(os.environ, {"HOME": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        # The checkout is the home itself here, so its repository key is `~`
        # (sd:1439): that is the identity the projection is asked for.

    def test_exact_local_and_remote_identities_use_one_ordered_projection(self) -> None:
        rows = [{"key": "item:14", "lane": "newly_unblocked"},
                {"key": "github:https://github.com/example/project/pull/2", "lane": "awaiting_you"}]
        before = self.database.read_bytes()
        with patch.object(status.pr_state, "remote_slug", return_value="example/project"), \
                patch.object(contributions, "projection", return_value=rows) as projection, \
                patch.object(sd_db, "connect", wraps=sd_db.connect) as connect:
            result = status.contributions_section(self.root)
        self.assertEqual(result["rows"], rows)
        self.assertEqual(result["source"], "database")
        self.assertEqual(projection.call_count, 1)
        self.assertEqual(projection.call_args.kwargs, {"repo": ["~", "example/project"]})
        connect.assert_called_once_with(write=False)
        self.assertEqual(self.database.read_bytes(), before)

    def test_local_work_is_available_without_a_remote(self) -> None:
        with patch.object(status.pr_state, "remote_slug", return_value=None), \
                patch.object(contributions, "projection", return_value=[]) as projection:
            result = status.contributions_section(self.root)
        self.assertTrue(result["available"])
        self.assertEqual(projection.call_args.kwargs, {"repo": ["~"]})

    def test_missing_database_is_not_created_and_unreadable_data_is_not_empty_success(self) -> None:
        absent = self.root / "absent.db"
        with patch.object(sd_db, "default_path", return_value=absent):
            result = status.contributions_section(self.root)
        self.assertFalse(result["available"])
        self.assertFalse(absent.exists())
        with patch.object(status.pr_state, "remote_slug", return_value=None), \
                patch.object(contributions, "projection", side_effect=ValueError("incomplete checkpoint")):
            result = status.contributions_section(self.root)
        self.assertFalse(result["available"])
        self.assertIn("incomplete checkpoint", result["reason"])

    def test_text_is_one_table_row_per_contribution_in_projection_order_with_controls_escaped(self) -> None:
        """sd:5357: a row per contribution, as `sd today` prints a table; the fields beyond the
        columns are `sd task contribution show`'s and `--json`'s, named on a line under the table."""
        rows = [{"key": "item:14", "title": "Local\n\u001b[31mwork", "lane": "newly_unblocked", "item_id": 14,
                 "local_status": "planning", "local_branch": "fix/library",
                 "reasons": ["Dependency \u001b[2J merged"]},
                {"key": "github:closed", "title": "Closed without merge", "lane": "awaiting_you", "external_state": "CLOSED"},
                {"key": "github:waiting", "title": "Waiting for maintainer", "lane": "awaiting_them"},
                {"key": "github:merged", "title": "Merged upstream", "lane": "merged"}]
        output = io.StringIO()
        status._render_contributions({"available": True, "rows": rows}, output.write)
        text = output.getvalue()
        positions = [text.index(json.dumps(row["title"])) for row in rows]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("\u001b", text)
        self.assertIn("Local\\n\\u001b[31mwork", text)
        lines = text.splitlines()
        self.assertEqual("Contributions, this repo, shared database order (4)", lines[1])
        self.assertRegex(lines[2], r"^  Lane +Ref +Item +Local +External +Title$")
        self.assertRegex(lines[3], r"^  -+(  -+)*$")
        self.assertRegex(lines[4], r'^  newly_unblocked +item:14 +sd:14 +planning +- +"Local')
        self.assertRegex(lines[5], r'^  awaiting_you +github:closed +- +- +CLOSED +"Closed without merge"$')
        self.assertIn('  item:14 reasons: ["Dependency \\u001b[2J merged"]', lines)
        self.assertIn("  every field: `sd task contribution show <key> --json`, or `sd-status --json`", lines)
        self.assertNotIn("fix/library", text)

    def test_a_github_url_reads_as_its_short_reference(self) -> None:
        """A URL key is wider than a cell; the row names `<repo>#<number>` instead."""
        url = "https://github.com/example/project/pull/2"
        output = io.StringIO()
        status._render_contributions({"available": True, "rows": [
            {"key": f"github:{url}", "url": url, "lane": "merged", "title": "Merged"},
            {"key": "issue:https://github.com/example/project/issues/7", "lane": "closed", "title": "Bug"}]},
            output.write)
        self.assertRegex(output.getvalue(), r"\n  merged +project#2 +")
        self.assertRegex(output.getvalue(), r"\n  closed +project#7 +")

    def test_an_unread_projection_counts_unknown_and_says_why(self) -> None:
        output = io.StringIO()
        status._render_contributions({"available": False, "reason": "no database", "rows": []}, output.write)
        self.assertEqual('\nContributions, this repo, shared database order (unknown)\n  ! "no database"\n',
                         output.getvalue())

    def test_no_registration_never_invents_contributions_from_generic_tasks(self) -> None:
        connection = sd_db.connect(self.database)
        try:
            sd_db.create_item(connection, title="Ordinary local task", kind="task")
        finally:
            connection.close()
        with patch.object(status.pr_state, "remote_slug", return_value=None):
            result = status.contributions_section(self.root)
        self.assertEqual(result["rows"], [])

    def test_real_projection_retains_external_lifecycle_and_local_status(self) -> None:
        connection = sd_db.connect(self.database)
        try:
            url = "https://github.com/example/project/pull/14"
            item = contributions.capture(connection, title="Local patch", changes={"pull_url": url}, who="user")["item"]["id"]
            observation = {"complete": True, "observed_at": "2026-09-09T12:00:00Z",
                "operator": {"id": "1", "login": "author"}, "author": {"id": "1", "login": "author"},
                "repo": "example/project", "title": "Closed patch", "state": "closed", "head": "a" * 40,
                "base": "b" * 40, "draft": False, "mergeable": "mergeable", "ci": "success", "ci_head": "a" * 40,
                "ci_ids": ["check:1"], "why": ["author"], "blocking_labels": [], "labels": [], "reviews": [],
                "events": [{"id": "closed:1", "at": "2026-09-09T12:00:00Z", "actor_id": "2", "kind": "closed", "url": url}]}
            contributions.observe_pull(connection, url, observation,
                expected_revision=contributions.snapshot(connection, "github:" + url)["revision"])
            expected = contributions.projection(connection, repo=[str(self.root), "example/project"])
            before = tuple(connection.iterdump())
            with patch.object(status.pr_state, "remote_slug", return_value="example/project"):
                section = status.contributions_section(self.root)
            self.assertTrue(section["available"], section["reason"])
            self.assertEqual(section["rows"], expected)
            self.assertEqual(expected[0]["item_id"], item)
            self.assertEqual(expected[0]["external_state"], "closed")
            self.assertEqual(expected[0]["local_status"], "planning")
            self.assertEqual(expected[0]["lane"], "awaiting_you")
            self.assertEqual(tuple(connection.iterdump()), before)
        finally:
            connection.close()
