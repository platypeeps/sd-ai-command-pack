"""`carried <item>`: the disposition whose verdict is a row rather than a claim.

sd:1004. `fixed` and `dismissed` both settle when they are written. A finding
that is real, that no commit in the pull request answers, and that has been
carried to a tracked item is neither: naming a commit produces `fix-missing`,
and writing a dismissal reason for a finding that stands puts a false sentence
in the store. The 2026-09-17 sweep left 177 findings on 80 pull requests open
for exactly that reason.

What makes the third word more than a bulk dismissal with better manners is
that it can be taken back without anybody editing the record. The verdict is
read from the named row's status every time it is asked, so an item somebody
cancels reopens every finding carried to it. `test_a_cancelled_item_reopens_the
_findings_it_was_holding` is that claim, written as one status change between
two reads of the same store.

The other half is the direction of failure. `id_verdict` is handed a repository
root and nothing that reaches a database, so resolving a carried item opens
one -- and an installation with no `sd_db`, or no store, cannot read the status
at all. That reads `carry-unreadable` and is UNSATISFIED, because the
alternative is a machine missing a library reporting every carried finding as
answered.
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from types import SimpleNamespace

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = REPO_ROOT / "bin"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sd-543-review-round.json"

sys.path.insert(0, str(BIN))
import sd_lib  # noqa: E402

#: Loaded under its own name, so this file's resolver cache is not the one
#: `tests/test_sd_review_ack.py` is holding.
ack = sd_lib.sibling("sd_review_ack_carried_under_test", "sd-review-ack")

import sd_db  # noqa: E402 - provisioned into this virtualenv by `make setup`

ROUND = json.loads(FIXTURE.read_text(encoding="utf-8"))["pull_requests"]

#: One finding, so `--check` on it is a statement about that finding alone.
ONE = 863

#: Eight findings, for the question of how many connections eight of them open.
MANY = 857

GIT_IDENTITY = (
    "-c", "user.email=carried@example.invalid",
    "-c", "user.name=Carried Fixture",
    "-c", "commit.gpgsign=false",
)


def findings_on(pull: int) -> list[dict]:
    key = str(pull)
    return ack.findings(pull, ROUND[key]["reviews"], ROUND[key]["comments"])


class CarriedCase(unittest.TestCase):
    """A scratch checkout, a scratch database, and nothing of the operator's.

    `HOME` is moved before any verdict is asked, because the resolver opens
    `sd_db.default_path()`, which reads `$HOME` at call time. A test that left
    it alone would read -- and a careless one would write -- the real store.
    """

    def setUp(self) -> None:
        self.stack = tempfile.TemporaryDirectory()
        self.addCleanup(self.stack.cleanup)
        base = pathlib.Path(self.stack.name)

        self.root = base / "repo"
        self.root.mkdir()
        self._git("init", "--initial-branch=main")
        (self.root / "README.md").write_text("landed\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("commit", "-m", "landed")
        # `main` exists and `origin/main` does not, so every run names the ref.
        self.ref = ("--landed-in", "main")

        self.home = base / "home"
        self.home.mkdir()
        sd_db.initialise(home=self.home)
        self.connection = sd_db.connect(sd_db.default_path(self.home), write=True)
        self.addCleanup(self.connection.close)
        was = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self.addCleanup(os.environ.__setitem__, "HOME", was or "")

        ack._forget_carried_rows()
        self.addCleanup(ack._forget_carried_rows)

    def _git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", *GIT_IDENTITY, *args], cwd=str(self.root),
            capture_output=True, text=True, check=True,
        )
        return done.stdout.strip()

    def item(self, *, kind: str = "followup", status: str = "planning") -> int:
        return sd_db.writes.create_item(
            self.connection, kind=kind, title=f"a {kind} row", status=status,
        )

    def cancel(self, number: int) -> None:
        """Cancel a row the way this database spells it, which is not a status.

        `item.status` admits six words and `cancelled` is not among them.
        `sd_db.progress.cancel_work` writes
        `fields.completion.outcome = "cancelled"` and moves the row to `done`,
        so a cancelled row and a delivered row share a status and only the
        completion record separates them. That library call is guarded to
        `work` rows, which `--carried` refuses, so the mark is written here
        directly -- the shape is the library's, not this test's invention.
        """
        sd_db.writes.set_item_fields(self.connection, number, fields={
            "completion": {"outcome": "cancelled", "item": number,
                           "who": "carried-test", "reason": "not doing this"},
        })
        sd_db.writes.transition(self.connection, number, "done",
                                who="carried-test", reason="cancelled: not doing this")

    def run_ack(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(BIN / "sd-review-ack"), "--from", str(FIXTURE), *args],
            cwd=str(self.root), capture_output=True, text=True, check=False,
        )

    def payload(self, *args: str) -> tuple[dict, int]:
        done = self.run_ack("--json", *args)
        return json.loads(done.stdout or "{}"), done.returncode

    def carry(self, pull: int, number: int | str, *ids: str) -> None:
        """Acknowledge findings on `pull` as carried to `number`, and check it took."""
        wanted = ids or tuple(row["id"] for row in findings_on(pull))
        for found in wanted:
            done = self.run_ack("--pr", str(pull), "--ack", found,
                                "--carried", str(number), *self.ref)
            self.assertEqual(done.returncode, 0, done.stderr)

    def verdicts(self, pull: int) -> list[str]:
        result, _ = self.payload("--pr", str(pull), *self.ref)
        return [row["verdict"] for row in result["findings"]]


class AnItemThatStillStandsHoldsTheFinding(CarriedCase):
    """The satisfying half: a row somebody could still work answers the gate."""

    def test_a_finding_carried_to_an_open_row_is_satisfied(self):
        """The whole point of the word: a true sentence that closes the gate."""
        number = self.item(status="planning")
        self.carry(ONE, number)
        result, code = self.payload("--pr", str(ONE), "--check", *self.ref)
        self.assertEqual(code, 0, "an item that holds the finding satisfies the gate")
        self.assertEqual([row["verdict"] for row in result["findings"]], ["carried"])
        self.assertEqual(result["unsatisfied"], [])

    def test_a_row_that_is_done_still_holds_it(self):
        """`done` is not `cancelled`. The work happened; nothing was dropped."""
        number = self.item(status="done")
        self.carry(ONE, number)
        result, code = self.payload("--pr", str(ONE), "--check", *self.ref)
        self.assertEqual([row["verdict"] for row in result["findings"]], ["carried"])
        self.assertEqual(code, 0)

    def test_the_stored_row_names_the_item_and_asserts_nothing_else(self):
        """No commit, no cited sha, no reason -- the record is the item id alone."""
        number = self.item()
        self.carry(ONE, number)
        stored = list(ack.read_store(self.root)[0].values())[0]
        self.assertEqual(
            {key: stored[key] for key in ("disposition", "item", "cited", "reason", "commit")},
            {"disposition": "carried", "item": number, "cited": "", "reason": "", "commit": None},
        )


class ACancelledItemReopensWhatItWasHolding(CarriedCase):
    """The central claim, and the reason this is not a bulk dismissal."""

    def test_the_same_record_reverses_when_the_item_is_cancelled(self):
        """One record, one status change, two reads, two different verdicts.

        Written as a change between two reads rather than as two fixtures on
        purpose. Two fixtures would prove only that the reader maps two
        statuses to two verdicts; what has to be true is that a record already
        written, and never touched again, stops satisfying the gate the moment
        the row behind it is cancelled.
        """
        number = self.item(status="in_progress")
        self.carry(ONE, number)
        before, code_before = self.payload("--pr", str(ONE), "--check", *self.ref)
        self.assertEqual([row["verdict"] for row in before["findings"]], ["carried"])
        self.assertEqual(code_before, 0)

        frozen = json.dumps(ack.read_store(self.root)[0], sort_keys=True)
        self.cancel(number)

        after, code_after = self.payload("--pr", str(ONE), "--check", *self.ref)
        self.assertEqual([row["verdict"] for row in after["findings"]], ["carry-dropped"])
        self.assertEqual(code_after, 1, "a cancelled item must reopen its findings")
        self.assertEqual(
            json.dumps(ack.read_store(self.root)[0], sort_keys=True), frozen,
            "the record must not have been rewritten; only the row moved",
        )

    def test_the_status_word_reopens_a_finding_too_if_a_schema_ever_writes_it(self):
        """The forward-compatible half of the same question.

        `cancelled` is not in this schema's `CHECK`, so no row here can carry
        it and no fixture can make one. The branch is still in the reader,
        because the vocabulary is the database's and a database that gains the
        word must reopen findings with nothing in `bin/` to edit. Asserted
        against a stubbed row for that reason, and only for that reason.
        """
        self.assertTrue(ack.cancelled_row({"status": "cancelled", "fields": None}))
        self.assertFalse(ack.cancelled_row({"status": "done", "fields": None}))
        self.assertFalse(ack.cancelled_row({"status": "done", "fields": "{not json"}))

    def test_an_item_id_naming_no_row_holds_nothing(self):
        """A row deleted, or an id typed wrong, is not a finding anybody answered."""
        number = self.item()
        self.carry(ONE, number)
        self.connection.execute("DELETE FROM item WHERE id = ?", (number,))
        self.connection.commit()
        result, code = self.payload("--pr", str(ONE), "--check", *self.ref)
        self.assertEqual([row["verdict"] for row in result["findings"]], ["carry-missing"])
        self.assertEqual(code, 1)


class AnUnreadableItemDecidesNothing(CarriedCase):
    """Fail closed: a library this machine does not have answers no questions."""

    def test_no_reader_is_unsatisfied_rather_than_satisfied(self):
        """An import error must not acknowledge 177 findings by accident."""
        number = self.item()
        self.carry(ONE, number)
        found = findings_on(ONE)[0]
        rows, _ = ack.read_store(self.root)
        absent = SimpleNamespace(module=None, problem="no sd_db here", provisioned=False)
        ack._forget_carried_rows()
        with unittest.mock.patch.object(ack.sd_lib, "import_sd_db", return_value=absent):
            state = ack.id_verdict(self.root, found["id"], rows, "main")
            standing = ack.unacknowledged(self.root, [found["id"]], "main")
        self.assertEqual(state, "carry-unreadable")
        self.assertEqual(standing, [found["id"]], "unreadable must leave the finding open")

    def test_a_store_that_will_not_open_reads_the_same_way(self):
        """The other fault with the same remedy: the library is here, the store is not."""
        number = self.item()
        self.carry(ONE, number)
        found = findings_on(ONE)[0]
        rows, _ = ack.read_store(self.root)
        ack._forget_carried_rows()
        with unittest.mock.patch.object(sd_db, "connect", side_effect=OSError("no store")):
            state = ack.id_verdict(self.root, found["id"], rows, "main")
        self.assertEqual(state, "carry-unreadable")


class AnUnimportableLibraryIsReportedAsItself(CarriedCase):
    """sd:1019. The verdict stays closed; the REPORT stops calling it content.

    `carry-unreadable` is one word over two worlds -- a store this machine has
    never written, and an interpreter with no `sd_db` on it at all. Read from
    a checkout with no `.venv`, the second produced that verdict for every
    carried finding in the store and 55 answered findings printed as
    unacknowledged backlog. Nothing in the output said an interpreter was
    missing, so an infrastructure failure arrived wearing a content verdict's
    clothes. These tests break the import and ask the report to say so.
    """

    #: What `sd_lib.import_sd_db` returns on a checkout with no `.venv` and no
    #: `sd_db` on the interpreter's path -- the environment this item is about.
    ABSENT = SimpleNamespace(
        module=None,
        problem="sd_db is not installed here: No module named 'sd_db'",
        provisioned="",
    )

    def test_the_report_names_the_missing_interpreter(self):
        """Its own line, beside the rows, in `unreadable-concern-row`'s shape."""
        self.carry(ONE, self.item())
        ack._forget_carried_rows()
        with unittest.mock.patch.object(ack.sd_lib, "import_sd_db", return_value=self.ABSENT):
            state = ack.review_state(self.root, {ONE: ROUND[str(ONE)]}, "main")
        out = io.StringIO()
        ack.render_findings(state, out)
        self.assertEqual(state["library_error"], self.ABSENT.problem)
        self.assertIn(f"carried items unreadable: {self.ABSENT.problem}", out.getvalue())
        self.assertIn("not an unanswered finding", out.getvalue())

    def test_a_library_that_imports_reports_nothing(self):
        """The control. A condition that is always reported is not a condition."""
        self.carry(ONE, self.item())
        ack._forget_carried_rows()
        state = ack.review_state(self.root, {ONE: ROUND[str(ONE)]}, "main")
        self.assertEqual(state["library_error"], "")
        self.assertEqual([row["verdict"] for row in state["findings"]], ["carried"])
        self.assertNotIn("carried items unreadable", _rendered(state))

    def test_a_round_with_nothing_carried_never_reaches_for_the_library(self):
        """An absent `sd_db` that changed no answer is not a fault to report."""
        ack._forget_carried_rows()
        with unittest.mock.patch.object(ack.sd_lib, "import_sd_db", return_value=self.ABSENT):
            state = ack.review_state(self.root, {ONE: ROUND[str(ONE)]}, "main")
        self.assertEqual([row["verdict"] for row in state["findings"]], ["unread"])
        self.assertEqual(state["library_error"], "")


def _rendered(state: dict) -> str:
    out = io.StringIO()
    ack.render_findings(state, out)
    return out.getvalue()


class AWorkRowIsRefusedBeforeItIsWritten(CarriedCase):
    """The refusal happens at the write, where a person can still fix it."""

    def test_a_work_row_is_named_and_the_record_is_not_written(self):
        """A work row closes on a delivery, so its status answers a different question."""
        number = self.item(kind="work")
        found = findings_on(ONE)[0]["id"]
        done = self.run_ack("--pr", str(ONE), "--ack", found, "--carried", str(number), *self.ref)
        self.assertEqual(done.returncode, 2)
        self.assertIn(f"--carried {number} names a work row", done.stderr)
        self.assertIn("closes on a delivery", done.stderr)
        self.assertEqual(ack.read_store(self.root)[0], {})


class TheValueHasToBeAnItemId(CarriedCase):
    """Three ways to hand `--carried` something that is not a row id."""

    def test_zero_a_negative_and_a_word_are_each_refused(self):
        found = findings_on(ONE)[0]["id"]
        for value in ("0", "-1", "abc"):
            with self.subTest(value=value):
                done = self.run_ack("--pr", str(ONE), "--ack", found,
                                    "--carried", value, *self.ref)
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertIn("names no item", done.stderr)
                self.assertEqual(ack.read_store(self.root)[0], {})


class ExactlyOneDispositionPerAcknowledgement(CarriedCase):
    """Three words, one of them, and the refusal names all three."""

    def test_fixed_and_carried_together_is_a_usage_error(self):
        found = findings_on(ONE)[0]["id"]
        done = self.run_ack("--pr", str(ONE), "--ack", found,
                            "--fixed", "HEAD", "--carried", "1", *self.ref)
        self.assertEqual(done.returncode, 2)
        # The tool's own refusal, not argparse's. `--fixed` and `--dismiss`
        # appear in the usage banner of any argparse failure, so a test that
        # only looked for the three names would pass against a parser that
        # had never heard of `--carried`.
        self.assertIn("exactly one of", done.stderr)
        for flag in ("--fixed", "--dismiss", "--carried"):
            self.assertIn(flag, done.stderr)
        self.assertEqual(ack.read_store(self.root)[0], {})


class AReplayReachesTheLiveVerdict(CarriedCase):
    """`--from FILE` freezes the round, never the row the round is judged against."""

    def test_the_replay_agrees_with_the_direct_read_in_every_state(self):
        """The capture holds findings. The verdict is the database's, not the file's."""
        number = self.item(status="ready")
        self.carry(ONE, number)
        found = findings_on(ONE)[0]
        for stage in ("open", "cancelled", "deleted"):
            with self.subTest(stage=stage):
                if stage == "cancelled":
                    self.cancel(number)
                if stage == "deleted":
                    self.connection.execute("DELETE FROM item WHERE id = ?", (number,))
                    self.connection.commit()
                ack._forget_carried_rows()
                direct = ack.id_verdict(self.root, found["id"],
                                        ack.read_store(self.root)[0], "main")
                self.assertEqual(self.verdicts(ONE), [direct])


class OneConnectionForTheWholeRun(CarriedCase):
    """1299 findings held by five items is five reads, not 1299 connections."""

    def test_eight_findings_on_two_items_open_one_connection_and_read_twice(self):
        """Counted, not timed: a timing assertion measures the machine instead."""
        alpha = self.item()
        beta = self.item()
        found = findings_on(MANY)
        self.assertEqual(len(found), 8, "the fixture must still carry eight findings here")
        half = [row["id"] for row in found[:4]]
        rest = [row["id"] for row in found[4:]]
        self.carry(MANY, alpha, *half)
        self.carry(MANY, beta, *rest)

        opened: list[int] = []
        read_for: list[int] = []
        real = ack._open_carry_reader

        def counting() -> tuple[object, object] | None:
            opened.append(1)
            reader = real()
            assert reader is not None
            connection, read = reader

            def counted(handle: object, number: int) -> object:
                read_for.append(number)
                return read(handle, number)

            return connection, counted

        ack._forget_carried_rows()
        with unittest.mock.patch.object(ack, "_open_carry_reader", counting):
            standing = ack.unacknowledged(self.root, half + rest, "main")
        self.assertEqual(standing, [])
        self.assertEqual(len(opened), 1, "one connection for the whole run")
        self.assertEqual(sorted(read_for), sorted([alpha, beta]),
                         "one status read per item, not one per finding")


if __name__ == "__main__":
    unittest.main()
