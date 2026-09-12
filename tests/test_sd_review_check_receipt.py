"""The review lane reads the runner's check instead of running it again.

sd:495. `sd-ship prepare` calls this lane, and step 1 re-runs the same
deterministic `sd-check --json` the runner has just run on the same clone at
the same head. The gate cannot answer differently, so a clean row pays for it
twice; on `system` that is the whole native suite, minutes each time.

The receipt these tests drive is the one the runner writes
(`sd_db.runner.record_check`, system #284), through the real writer and the
real schema rather than a hand-built row -- which is the point, because what
is being asserted is that the reader reads what that writer writes.

Every acceptance leg is asserted on its own, and each one failing is asserted
to fall through to the gate. A receipt that is trusted when the tree differs
is worse than no receipt at all: it would let a commit amended after the check
reach a push unchecked.
"""

from __future__ import annotations

import pathlib
import subprocess

from sd_db import connect, create_assignment, create_item, initialise, upsert_repo
from sd_db.runner import claim, record_check

from tests.test_sd_review import FakeRunner, ReviewFixture, namespace, sd_review


class TheRunnersCheckIsAReceiptTests(ReviewFixture):
    """`recorded_check` accepts only its own run, its own tree, and a pass."""

    def seed(self, root: pathlib.Path) -> tuple[pathlib.Path, str]:
        """A database carrying one live run for `root`, and that run's id."""

        database = self.tmp / "receipt.db"
        initialise(database)
        connection = connect(database)
        repo = str(root)
        upsert_repo(connection, repo, remote="git@github.com:fixture/repo.git")
        item = create_item(connection, kind="task", title="receipt", repo=repo, branch="main")
        assignment = create_assignment(connection, role="author", status="queued", item=item)
        run = claim(
            connection,
            assignment,
            owner="fixture",
            work_root=self.tmp / "work",
            retention_root=self.tmp / "retention",
        )
        self.connection = connection
        return database, run["run"]["id"]

    def tree(self, root: pathlib.Path) -> str:
        finished = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=str(root),
            check=True, capture_output=True, text=True,
        )
        return finished.stdout.strip()

    def reviewed(self, root: pathlib.Path, database: pathlib.Path | None, ident: str | None):
        """One real review, with a runner that fails loudly if the gate runs."""

        environment = dict(self.environment())
        if ident is not None:
            environment["SD_ASSIGNMENT"] = ident
        runner = FakeRunner({"sd-check": sd_review.Completed(0, '{"checks": [{"name": "gate"}]}', "")})
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        result = sd_review.review(
            root,
            namespace(database=database),
            runner,
            environment,
            self.chatgpt_home(),
        )
        ran = [call for call in runner.calls if "sd-check" in " ".join(str(p) for p in call["argv"])]
        return result, ran

    def test_a_receipt_for_this_tree_stands_in_for_the_gate(self) -> None:
        root = self.make_repo()
        database, ident = self.seed(root)
        record_check(
            self.connection, ident, head="0" * 40, tree=self.tree(root),
            exit_code=0, argv=["sd-check", "--json"], checks=[{"name": "gate"}],
        )
        result, ran = self.reviewed(root, database, ident)
        self.assertEqual(result["check"]["status"], "pass")
        self.assertEqual(result["check"]["source"], "runner")
        self.assertEqual(result["check"]["run"], ident)
        self.assertEqual(result["check"]["checks"], [{"name": "gate"}])
        self.assertEqual(ran, [], "the gate ran anyway; the receipt bought nothing")

    def test_a_tree_that_moved_is_checked_again(self) -> None:
        """The leg that carries the weight. A commit amended after the runner
        checked it has a different tree, and must not ride the old pass."""

        root = self.make_repo()
        database, ident = self.seed(root)
        record_check(
            self.connection, ident, head="0" * 40, tree="1" * 40,
            exit_code=0, argv=["sd-check", "--json"], checks=None,
        )
        result, ran = self.reviewed(root, database, ident)
        self.assertEqual(result["check"]["status"], "pass")
        self.assertNotIn("source", result["check"])
        self.assertEqual(len(ran), 1)

    def test_a_failing_record_is_not_a_pass(self) -> None:
        """The writer records whatever the runner handed over, a failure
        included, and says so in its own docstring. The reader decides."""

        root = self.make_repo()
        database, ident = self.seed(root)
        record_check(
            self.connection, ident, head="0" * 40, tree=self.tree(root),
            exit_code=1, argv=["sd-check", "--json"], checks=None,
        )
        result, ran = self.reviewed(root, database, ident)
        self.assertNotIn("source", result["check"])
        self.assertEqual(len(ran), 1)

    def test_a_run_that_recorded_nothing_is_checked(self) -> None:
        root = self.make_repo()
        database, ident = self.seed(root)
        result, ran = self.reviewed(root, database, ident)
        self.assertNotIn("source", result["check"])
        self.assertEqual(len(ran), 1)

    def test_a_persons_own_ship_has_no_run_and_is_checked(self) -> None:
        """Without `SD_ASSIGNMENT` there is no run and no row, so a review from
        a checkout behaves exactly as before this existed."""

        root = self.make_repo()
        database, ident = self.seed(root)
        record_check(
            self.connection, ident, head="0" * 40, tree=self.tree(root),
            exit_code=0, argv=["sd-check", "--json"], checks=None,
        )
        result, ran = self.reviewed(root, database, None)
        self.assertNotIn("source", result["check"])
        self.assertEqual(len(ran), 1)

    def test_no_database_is_checked(self) -> None:
        """`--database` is what makes this run one the lane already trusts for
        provider state. Without it there is nothing to read."""

        root = self.make_repo()
        _, ident = self.seed(root)
        record_check(
            self.connection, ident, head="0" * 40, tree=self.tree(root),
            exit_code=0, argv=["sd-check", "--json"], checks=None,
        )
        result, ran = self.reviewed(root, None, ident)
        self.assertNotIn("source", result["check"])
        self.assertEqual(len(ran), 1)

    def test_an_unreadable_database_falls_through_rather_than_raising(self) -> None:
        """A lane that cannot read the receipt runs the gate. It must not turn
        a reviewable change into a traceback."""

        root = self.make_repo()
        missing = self.tmp / "not-a-database.db"
        missing.write_text("this is not sqlite\n", encoding="utf-8")
        result, ran = self.reviewed(root, missing, "0" * 32)
        self.assertNotIn("source", result["check"])
        self.assertEqual(len(ran), 1)
