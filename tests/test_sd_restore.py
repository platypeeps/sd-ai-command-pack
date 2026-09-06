"""`sd restore` — the verb group a restored database is settled through.

The library it reads, `sd_db`, reaches this virtualenv through the pack's
installer, which lands after this. So two things are tested here and they are
different things: what the verbs do **when the library is absent**, which is
the state of every machine until the installer ships, and what they do
against a real database, which is exercised with `sd_db` put on `sys.path`
from the `system` checkout when that checkout is present beside this one.

Where the sibling checkout is absent that second class skips, with the reason
stated -- the only skip in this file, and one that says what it could not
reach rather than passing on nothing. On a machine with both checkouts, which
is every machine this is developed on, it runs.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_restore  # noqa: E402

#: The `system` checkout, if it sits beside this one. `sd_db` is not
#: installed here yet -- that is item A's criterion 13 -- so the tests that
#: need it import from the checkout rather than pretending it is installed.
SIBLING = REPO_ROOT.parent.parent / "system" / "local-sd-db"
LIBRARY = SIBLING if (SIBLING / "sd_db" / "__init__.py").exists() else None


def run(handler, **arguments):
    """Call a handler and capture what a person would see."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        status = handler(argparse.Namespace(**arguments))
    return status, out.getvalue(), err.getvalue()


class WithoutTheLibrary(unittest.TestCase):
    """Every machine, until the installer provisions `sd_db`."""

    def setUp(self) -> None:
        self.saved = dict(sys.modules)
        sys.modules.pop("sd_db", None)
        self.path = list(sys.path)
        sys.path = [entry for entry in sys.path if "local-sd-db" not in entry]

    def tearDown(self) -> None:
        sys.path = self.path
        sys.modules.clear()
        sys.modules.update(self.saved)

    def test_resume_refuses_with_the_remedy_and_not_a_traceback(self) -> None:
        with self.assertRaises(sd_restore.RestoreRefusal) as raised:
            sd_restore.resume(argparse.Namespace())
        message = str(raised.exception)
        self.assertIn("sd_db is not installed", message)
        self.assertIn("sd-install", message)

    def test_reimport_refuses_the_same_way(self) -> None:
        with self.assertRaises(sd_restore.RestoreRefusal):
            sd_restore.reimport(argparse.Namespace(repository="/repos/one"))


class TheCommandLine(unittest.TestCase):
    def test_the_group_is_registered_with_both_verbs(self) -> None:
        completed = subprocess.run(
            [str(REPO_ROOT / "bin" / "sd"), "restore", "--help"],
            capture_output=True, text=True, input="",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("reimport", completed.stdout)
        self.assertIn("resume", completed.stdout)

    def test_a_refusal_exits_one_and_says_why(self) -> None:
        completed = subprocess.run(
            [str(REPO_ROOT / "bin" / "sd"), "restore", "resume"],
            capture_output=True, text=True, input="",
            env={**os.environ, "PYTHONPATH": ""},
        )
        self.assertEqual(completed.returncode, 1)
        self.assertTrue(completed.stderr.startswith("sd: "), completed.stderr)

    def test_a_missing_verb_is_a_usage_error(self) -> None:
        completed = subprocess.run(
            [str(REPO_ROOT / "bin" / "sd"), "restore"],
            capture_output=True, text=True, input="",
        )
        self.assertEqual(completed.returncode, 2)


class AgainstADatabase(unittest.TestCase):
    """The verbs against real rows, with `sd_db` from the sibling checkout."""

    @classmethod
    def setUpClass(cls) -> None:
        if LIBRARY is None:
            raise unittest.SkipTest(
                "the `system` checkout is not beside this one; `sd_db` cannot "
                "be imported and these tests would assert nothing"
            )
        sys.path.insert(0, str(LIBRARY))
        cls.sd_db = importlib.import_module("sd_db")

    @classmethod
    def tearDownClass(cls) -> None:
        if LIBRARY is not None and str(LIBRARY) in sys.path:
            sys.path.remove(str(LIBRARY))

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name)
        (self.home / ".local/share/sd").mkdir(parents=True)
        self.saved_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self.addCleanup(self._restore_home)
        self.sd_db.initialise(home=self.home)
        self.connection = self.sd_db.connect(home=self.home)
        self.addCleanup(self.connection.close)

    def _restore_home(self) -> None:
        if self.saved_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.saved_home

    def open_restore(self, key: str = "2026-09-06") -> int:
        return self.sd_db.record_state(self.connection, "restore", key=key)

    def test_resume_with_no_restore_says_there_is_nothing_to_clear(self) -> None:
        with self.assertRaises(sd_restore.RestoreRefusal) as raised:
            sd_restore.resume(argparse.Namespace())
        self.assertIn("no unresolved restore", str(raised.exception))

    def test_resume_names_what_is_blocked_and_what_is_frozen(self) -> None:
        self.sd_db.upsert_repo(self.connection, "/repos/one")
        item = self.sd_db.create_item(self.connection, kind="work", title="A thing")
        assignment = self.sd_db.create_assignment(
            self.connection, role="reviewer", status="queued", item=item)
        self.sd_db.update_assignment(self.connection, assignment, status="blocked")
        self.connection.execute(
            "INSERT INTO bill (name, cost_basis, cap_usd_month) VALUES ('baseten', 'company', 50)")
        row = self.open_restore()

        status, out, _err = run(sd_restore.resume)

        self.assertEqual(status, 0)
        self.assertIn(f"assignment {assignment} (reviewer)", out)
        self.assertIn("baseten", out)
        self.assertIn("Dispatch resumes", out)
        self.assertEqual(self.sd_db.unresolved_state(self.connection, "restore"), [])
        del row

    def test_resume_refuses_while_a_repository_is_still_retiring(self) -> None:
        self.sd_db.upsert_repo(self.connection, "/repos/one", status_source="retiring")
        self.open_restore()
        with self.assertRaises(sd_restore.RestoreRefusal) as raised:
            sd_restore.resume(argparse.Namespace())
        message = str(raised.exception)
        self.assertIn("/repos/one (status_source)", message)
        self.assertIn("sd restore reimport", message)
        self.assertEqual(len(self.sd_db.unresolved_state(self.connection, "restore")), 1)

    def test_a_verified_row_in_the_snapshot_proves_the_repository(self) -> None:
        self.sd_db.upsert_repo(self.connection, "/repos/one", status_source="retiring")
        self.sd_db.record_state(
            self.connection, "verified", key="/repos/one:status_source", body="hash")
        self.open_restore()
        status, out, _err = run(sd_restore.resume)
        self.assertEqual(status, 0)
        self.assertIn("Dispatch resumes", out)

    def test_two_unresolved_restores_are_not_this_command_s_call(self) -> None:
        self.open_restore("2026-09-05")
        self.open_restore("2026-09-06")
        with self.assertRaises(sd_restore.RestoreRefusal) as raised:
            sd_restore.resume(argparse.Namespace())
        self.assertIn("2 unresolved restores", str(raised.exception))

    def test_reimport_refuses_an_unregistered_repository(self) -> None:
        self.open_restore()
        with self.assertRaises(sd_restore.RestoreRefusal) as raised:
            sd_restore.reimport(argparse.Namespace(repository="/repos/absent"))
        self.assertIn("not a registered repository", str(raised.exception))

    def test_reimport_refuses_a_repository_that_is_not_awaiting_one(self) -> None:
        self.sd_db.upsert_repo(self.connection, "/repos/one", status_source="row")
        self.open_restore()
        with self.assertRaises(sd_restore.RestoreRefusal) as raised:
            sd_restore.reimport(argparse.Namespace(repository="/repos/one"))
        self.assertIn("not awaiting a reimport", str(raised.exception))

    def test_reimport_reports_what_is_held_and_says_the_import_is_not_here(self) -> None:
        """The verb group lands now; the per-kind import lands with the
        migration that wrote the rows, and says so rather than pretending."""
        self.sd_db.upsert_repo(self.connection, "/repos/one", status_source="retiring")
        self.open_restore()
        status, out, _err = run(sd_restore.reimport, repository="/repos/one")
        self.assertEqual(status, 1)
        self.assertIn("retiring for status_source", out)
        self.assertIn("rehearsal rows", out)
        self.assertIn("rerun the sitting", out)


if __name__ == "__main__":
    unittest.main()
