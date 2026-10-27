"""The 'why' search (pack sd:6019): a file path or a rule's text leads to the items that explain it.

A path reads `git log` in each managed checkout that holds it and lists the items each commit's trailer block cites, or
whose `Code delivery` note names the commit; rule text lists the `sd:N` each matching rule line cites. The search keeps
no store of its own; these tests build a real git checkout and rule files under a temporary folder.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest import mock

from sd_dashboard import why_search
from sd_db import upsert_repo
from support import ScreenCase
from test_workflow_actions import BrowserSession


def git(folder: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(folder), "-c", "user.name=Example", "-c", "user.email=dev@example.test",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True).stdout.strip()


class Checkout:
    """A managed checkout with two commits on `dashboard/page.py`, a rule file, and the items they cite.

    The first commit cites by trailer and names sd:999 in body prose, which cites nothing; the second cites by its
    subject and is delivered by a `Code delivery` note.
    """

    def build(self) -> None:
        self.folder = Path(self.tmp.name) / "pack"
        (self.folder / "dashboard").mkdir(parents=True)
        (self.folder / ".claude" / "rules").mkdir(parents=True)
        git(self.folder, "init", "-q")
        upsert_repo(self.connection, str(self.folder), remote="https://github.com/example/pack.git", managed=1)
        self.cited, self.delivered, self.ruled = (self.item("Queue times", repo=str(self.folder)), self.item("Rulings by session"),
                                                  self.item("Lane order"))
        page = self.folder / "dashboard" / "page.py"
        page.write_text("one\n")
        git(self.folder, "add", "-A")
        git(self.folder, "commit", "-q", "-m",
            f"feat: first (#1)\n\nBody naming sd:999 in prose.\n\nItem: sd:{self.cited}\nDelivers: sd:{self.cited}")
        page.write_text("two\n")
        (self.folder / "CLAUDE.md").write_text(
            f"# Rules\n\nNever auto-retry a ship on a locked repo:  it jumps the lane (sd:{self.ruled}).\n"
            "Keep it simple: delete before you add.\n")
        git(self.folder, "add", "-A")
        git(self.folder, "commit", "-q", "-m", f"fix: second, as sd:{self.ruled} ruled (#2)")
        sha = git(self.folder, "rev-parse", "HEAD")
        self.note(self.delivered, f"Code delivery https://github.com/example/pack/pull/2 at {sha}", kind="comment")
        self.connection.commit()
        self.home = Path(self.tmp.name) / "home"
        (self.home / ".claude").mkdir(parents=True)
        (self.home / ".claude" / "CLAUDE.md").write_text("Run the lane in order, never jump it (sd:999).\n")


class ThePath(Checkout, ScreenCase):
    def setUp(self) -> None:
        super().setUp()
        self.build()

    def test_a_path_leads_to_the_items_its_commits_cite_and_deliver(self):
        found = why_search.search(self.connection, "dashboard/page.py", home=self.home)
        self.assertEqual(found["kind"], "path")
        self.assertEqual([row["item"] for row in found["items"]], [self.ruled, self.delivered, self.cited])
        first = found["items"][2]
        self.assertEqual((first["title"], first["repo"]), ("Queue times", "pack"))
        self.assertIn("commit", first["why"])
        self.assertIn("feat: first (#1)", first["why"])
        self.assertIn("as sd:", found["items"][0]["why"])
        self.assertIn("pull/2", found["items"][1]["why"])
        # Prose in a body cites nothing: only the trailer block does, as pack sd:5999 reads it.
        self.assertNotIn(999, [row["item"] for row in found["items"]])

    def test_an_absolute_path_inside_the_checkout_reads_the_same(self):
        found = why_search.search(self.connection, str(self.folder / "dashboard" / "page.py"), home=self.home)
        self.assertEqual([row["item"] for row in found["items"]], [self.ruled, self.delivered, self.cited])

    def test_a_failed_git_log_is_named_not_read_as_no_item(self):
        with mock.patch.object(why_search, "_commits", side_effect=OSError("fatal: not a git repository")):
            found = why_search.search(self.connection, "dashboard/page.py", home=self.home)
        self.assertEqual(found["items"], [])
        self.assertEqual(found["errors"], ["git log in pack failed: fatal: not a git repository"])

    def test_a_path_no_checkout_holds_finds_nothing_and_says_no_error(self):
        found = why_search.search(self.connection, "no/such/file.py", home=self.home)
        self.assertEqual((found["items"], found["errors"]), ([], []))


class TheRuleText(Checkout, ScreenCase):
    def setUp(self) -> None:
        super().setUp()
        self.build()

    def test_rule_text_leads_to_the_item_its_line_cites(self):
        found = why_search.search(self.connection, "auto-retry a ship on a  LOCKED repo", home=self.home)
        self.assertEqual(found["kind"], "text")
        [row] = found["items"]
        self.assertEqual((row["item"], row["title"]), (self.ruled, "Lane order"))
        self.assertTrue(row["why"].startswith("pack/CLAUDE.md:3: Never auto-retry"))

    def test_the_operators_own_rules_count_and_an_unknown_item_still_shows(self):
        found = why_search.search(self.connection, "never jump it", home=self.home)
        self.assertEqual([(row["item"], row["title"]) for row in found["items"]], [(999, None)])
        self.assertTrue(found["items"][0]["why"].startswith("~/.claude/CLAUDE.md:1:"))

    def test_a_rule_that_cites_nothing_is_counted(self):
        found = why_search.search(self.connection, "delete before you add", home=self.home)
        self.assertEqual((found["items"], found["uncited"]), ([], ["pack/CLAUDE.md:4"]))

    def test_a_short_query_searches_nothing(self):
        self.assertEqual(why_search.search(self.connection, "ne", home=self.home)["items"], [])


class TheRoute(Checkout, BrowserSession):
    def test_the_search_answers_at_api_why(self):
        self.build()
        with mock.patch.object(Path, "home", return_value=self.home):
            status, _, body = self.request("/api/why?q=dashboard%2Fpage.py", headers={"Cookie": self.cookie})
        self.assertEqual(status, 200, body)
        self.assertEqual([row["item"] for row in json.loads(body)["items"]], [self.ruled, self.delivered, self.cited])
        status, _, body = self.request("/api/why?q=a&q=b", headers={"Cookie": self.cookie})
        self.assertEqual(status, 400, body)
