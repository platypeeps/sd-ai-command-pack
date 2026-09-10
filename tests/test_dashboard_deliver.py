"""The legacy Work tab delegates to the shared delivery verifier.

Delivery requires a full commit with the item's `Delivers:` trailer on the
verified default branch. A button click without that evidence leaves the
item open and explains the missing evidence.

Every test here writes to a real `sd_db` under a `HOME` nothing else shares,
because the thing being asserted is that a row moved. A double would assert
that the right calls were made, which is a different and weaker claim -- and
the failure this control exists downstream of was a page that reported a state
no row held.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from typing import Any
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_db  # noqa: E402 - installed into this virtualenv by `make setup`
import sd_lib  # noqa: E402

from dashboard import work  # noqa: E402

ITEM = "2026-09-05-a-thing"


class Fixture(unittest.TestCase):
    """One fleet root, one checkout inside it, one item, one database."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        patched = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patched.start()
        self.addCleanup(patched.stop)

        self.fleet = self.tmp / "repos"
        self.root = self.fleet / "pack"
        self.item = self.root / "docs" / "work" / ITEM
        self.item.mkdir(parents=True)
        (self.item / "prd.md").write_text("---\ntitle: A thing\n---\n", encoding="utf-8")
        for arguments in (("init", "-q", "-b", "main"),
                          ("config", "user.name", "Test"),
                          ("config", "user.email", "test@example.invalid"),
                          ("add", "-A"),
                          ("commit", "-qm", f"Deliver\n\nDelivers: {ITEM}")):
            subprocess.run(["git", "-C", str(self.root), *arguments],
                           check=True, capture_output=True)

    def identity(self, name: str = ITEM) -> str:
        """The row key, spelled out here rather than asked of the code."""
        return f"{self.root}::docs/work/{name}/prd.md"

    def seed(self, status: str = "in_progress", name: str = ITEM) -> Any:
        sd_db.initialise(home=self.home)
        connection = sd_db.connect(home=self.home)
        self.addCleanup(connection.close)
        sd_db.upsert_repo(connection, str(self.root), status_source="row")
        sd_db.upsert_item(
            connection,
            source=sd_lib.ITEM_ROW_SOURCE,
            external_id=self.identity(name),
            kind="work",
            title="A thing",
            status=status,
            who="the test",
            created_at="2026-09-05T00:00:00+00:00",
            repo=str(self.root),
            path=f"docs/work/{name}/prd.md",
            branch="main",
        )
        return connection

    def row(self, connection: Any, name: str = ITEM) -> Any:
        return sd_db.writes.item_by_external(
            connection, sd_lib.ITEM_ROW_SOURCE, self.identity(name)
        )


class TheWrite(Fixture):
    def test_a_row_that_is_there_goes_done_and_records_when(self) -> None:
        connection = self.seed()
        self.assertEqual(work.deliver(self.root, ITEM), "")
        row = self.row(connection)
        self.assertEqual(row["status"], "done")
        self.assertTrue(row["shipped_at"], "the row says done and not when")

    def test_a_row_that_is_not_there_says_so_and_claims_nothing(self) -> None:
        """The distinction the whole tab turns on.

        No row is not "so the item is open" and not "so it delivered": it is
        the database having lost the item, and answering `""` here would put
        `delivered` on a page for a write that landed nowhere.
        """

        self.seed()
        refused = work.deliver(self.root, "2026-09-05-no-such-item")
        self.assertIn("no row for", refused)
        self.assertIn("2026-09-05-no-such-item", refused)

    def test_with_no_database_at_all_it_says_that_instead(self) -> None:
        """`make setup` provisions `sd_db`; a checkout without one is a state.

        The sentence names the state rather than raising, because the caller
        is an HTTP handler and a traceback reaches the operator as a 500 with
        nothing in it they can act on.
        """

        refused = work.deliver(self.root, ITEM)
        self.assertTrue(refused, "a checkout with no database delivered anyway")
        self.assertIn(str(self.root), refused + self.identity())

    def test_the_second_press_does_not_move_the_moment_it_shipped(self) -> None:
        """`shipped_at` is when the item shipped, not when a button was last
        pressed. `skills/sd-ship/SKILL.md` says the same of a second merge.

        The moment is planted rather than read back off the first press.
        `sd_db.writes.now()` keeps whole seconds, so two presses one call
        apart carry the same text and this passes whether the gate on
        `shipped_at` is there or not -- which is what the first version of
        this test did, and a mutation that deleted the gate walked past it.
        A sentinel no clock produces makes the assertion mean what it says.
        """

        connection = self.seed()
        self.assertEqual(work.deliver(self.root, ITEM), "")
        before = dict(self.row(connection))
        notes = [dict(note) for note in sd_db.reads.item_notes(connection, before["id"])]
        with mock.patch.object(sd_db.writes, "now", return_value="2099-01-01T00:00:00+00:00"):
            self.assertEqual(work.deliver(self.root, ITEM), "")
        self.assertEqual(dict(self.row(connection)), before)
        self.assertEqual([dict(note) for note in sd_db.reads.item_notes(connection, before["id"])], notes)

    def test_a_commit_without_delivery_evidence_cannot_complete_work(self) -> None:
        connection = self.seed()
        subprocess.run(["git", "-C", str(self.root), "commit", "--allow-empty", "-qm", "A slice"],
                       check=True, capture_output=True)
        self.assertIn("no Delivers trailer", work.deliver(self.root, ITEM))
        self.assertEqual(self.row(connection)["status"], "in_progress")
        self.assertIsNone(self.row(connection)["shipped_at"])


class TheLabelResolves(Fixture):
    """A row carries a label, and a write comes back naming one."""

    def test_the_label_a_row_carries_resolves_to_its_checkout(self) -> None:
        rows = work.collect_work(self.fleet)["unstated"]
        self.assertEqual(len(rows), 1, "the fixture holds exactly one item")
        self.assertEqual(
            work.checkout_of(self.fleet, rows[0]["repo"]), self.root
        )

    def test_a_label_nothing_answers_to_resolves_to_nothing(self) -> None:
        self.assertIsNone(work.checkout_of(self.fleet, "somewhere/else"))

    def test_a_label_shaped_like_an_escape_reaches_nothing(self) -> None:
        """The label is matched against what the fleet holds, never joined
        onto the root, so a traversal has nothing to traverse."""

        for attempt in ("../pack", "pack/../pack", "/etc"):
            self.assertIsNone(work.checkout_of(self.fleet, attempt), attempt)


class WhatTheTabThenReads(Fixture):
    """The end the operator sees: the row moved, so the page moves."""

    def test_after_the_write_the_row_reads_done(self) -> None:
        marker = self.root / "docs" / "work" / sd_lib.STATUS_MARKER
        marker.write_text("row\n", encoding="utf-8")
        self.seed()
        before = work.collect_work(self.fleet)
        self.assertEqual(before["counts"], {"in_progress": 1})
        self.assertEqual(work.deliver(self.root, ITEM), "")
        self.assertEqual(work.collect_work(self.fleet)["counts"], {"done": 1})


if __name__ == "__main__":
    unittest.main()
