"""Pack tools stay out of repositories the sd database does not mark managed (sd:1620).

The operator sets `repo.managed` by hand on their own repositories (sd:1619);
the rest must not use any pack capability. A fleet walk skips an unmanaged
row, and a direct call in an unmanaged checkout refuses, naming the flag. Not
knowing -- no library, no database, no row -- is no reason to deny.

A real database, as `test_sd_issue_guard` uses: the claim is about which row
decides, and a double would only restate the answer.
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import subprocess  # nosec B404 - fixed argv, running git
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_ci  # noqa: E402
import sd_db  # noqa: E402 - installed into this virtualenv by `make setup`
import sd_fleet  # noqa: E402
import sd_lib  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = pathlib.Path(tmp.name).resolve()
        patched = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patched.start()
        self.addCleanup(patched.stop)

    def checkout(self, name: str) -> pathlib.Path:
        root = self.home / name
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)  # nosec B603 B607
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin",  # nosec B603 B607
                        f"https://github.com/example/{name}"], check=True)
        return root

    def register(self, root: pathlib.Path, **columns: object) -> None:
        sd_db.initialise(home=self.home)
        connection = sd_db.connect(home=self.home)
        try:
            key = sd_db.add_repo(connection, root, home=self.home)
            sd_db.writes.upsert_repo(connection, key, remote=f"https://github.com/example/{root.name}", **columns)
            connection.commit()
        finally:
            connection.close()


class ADirectCall(Fixture):
    def test_an_unmanaged_checkout_refuses_naming_the_flag(self) -> None:
        root = self.checkout("theirs")
        self.register(root, managed=0)
        said = sd_lib.unmanaged(root)
        self.assertIsNotNone(said, "an unmanaged checkout was let through")
        self.assertIn("repo.managed = no", said)
        self.assertIn("sd-db.sh repo managed ~/theirs yes", said)

    def test_a_managed_checkout_proceeds(self) -> None:
        root = self.checkout("mine")
        self.register(root, managed=1)
        self.assertIsNone(sd_lib.unmanaged(root))

    def test_no_database_proceeds_in_silence(self) -> None:
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            self.assertIsNone(sd_lib.unmanaged(self.checkout("unregistered")))
        self.assertEqual(said.getvalue(), "")

    def test_no_row_proceeds_with_one_warning_naming_the_flag(self) -> None:
        root = self.checkout("unregistered")
        self.register(self.checkout("other"), managed=0)
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            self.assertIsNone(sd_lib.unmanaged(root))
        self.assertEqual(said.getvalue().count("\n"), 1, said.getvalue())
        self.assertIn("(repo.managed); proceeding", said.getvalue())
        self.assertIn("sd-db.sh repo managed ", said.getvalue())


class SdCiLocal(Fixture):
    def test_an_unmanaged_checkout_refuses_before_any_github_write(self) -> None:
        theirs = self.checkout("theirs")
        self.register(theirs, managed=0)
        with self.assertRaises(sd_ci.CiRefusal) as refused:
            sd_ci.ci_step(theirs, None)
        self.assertIn("repo.managed = no", str(refused.exception))

    def test_a_managed_checkout_reads_its_ci_row(self) -> None:
        mine = self.checkout("mine")
        self.register(mine, managed=1)
        self.assertEqual(sd_ci.ci_step(mine, None).subject, "repo.ci")


class AFleetWalk(Fixture):
    def test_the_stamp_skips_an_unmanaged_auto_row(self) -> None:
        mine, theirs = self.checkout("mine"), self.checkout("theirs")
        self.register(mine, managed=1, runner_merge="auto")
        self.register(theirs, managed=0, runner_merge="auto")
        self.assertEqual([checkout.name for checkout, _ in sd_fleet.auto_rows()], ["mine"])

    def test_a_write_in_an_unmanaged_checkout_refuses_naming_the_flag(self) -> None:
        theirs = self.checkout("theirs")
        self.register(theirs, managed=0, runner_merge="auto")
        with self.assertRaises(sd_fleet.FleetRefusal) as refused:
            sd_fleet.here(sd_fleet.auto_rows(), theirs)
        self.assertIn("repo.managed = no", str(refused.exception))

    def test_a_row_without_the_column_stays_in(self) -> None:
        class Row(dict):
            keys = dict.keys

        self.assertEqual(sd_lib.managed_rows([Row(path="old"), Row(path="no", managed=0)]), [{"path": "old"}])


if __name__ == "__main__":
    unittest.main()
