"""The offload receipt, satellite side (sd:2704 step 3): a pass on a satellite writes a second row for the hub.

A satellite is a machine whose workflow database a hub serves over the wire.
Here the database is a local file and `served_by` is patched to name a hub for
it, as `SatellitePrepare` in `test_sd_ship_lane` does, so the rows land where
the test reads them. The pinned `sd_db` predates `repo.satellite_gate`, so the
opt-in is patched at its one reader, `sd_lib.repo_satellite_gate`, which has
its own tests below. No test starts `sd-check`: a stand-in run counts calls.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_gate_receipts  # noqa: E402
import sd_gate_run  # noqa: E402
import sd_lib  # noqa: E402

HUB = "hub.example.test:8769"
SLUG = "fixture/repo"


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


class SatelliteFixture(unittest.TestCase):
    """A repository whose origin is `fixture/repo`, a workflow database a hub serves, and a counted stand-in run."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name).resolve() / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        git(self.root, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
        (self.root / "Makefile").write_text("check:\n\ttrue\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "c")
        self.head = git(self.root, "rev-parse", "HEAD")
        from sd_db import initialise

        self.database = self.root.parent / "sd.db"
        initialise(self.database)
        self.runs = 0
        self.hub: str | None = HUB
        self.opted = "accept"
        for patcher in (mock.patch("sd_db.database.served_by", self.served_by, create=True),
                        mock.patch.object(sd_lib, "repo_satellite_gate", lambda connection, root: self.opted)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def served_by(self, target, home=None):  # type: ignore[no-untyped-def]
        return self.hub if str(target) == str(self.database) else None

    def passing(self, argv, env, tree, timeout):  # type: ignore[no-untyped-def]
        self.runs += 1
        return 0, json.dumps({"status": "pass", "scope": {"mode": "full"}, "checks": []}), ""

    def gate(self) -> dict:
        return sd_gate_run.check_in_worktree(self.root, self.head, database=self.database, run=self.passing)

    def row(self, key: str) -> dict:
        return sd_gate_receipts.read_offload(self.database, key)[1]

    def offload_row(self) -> dict:
        return self.row(sd_gate_receipts.offload_key(SLUG, self.head))

    def own_row(self) -> dict:
        return self.row(sd_gate_receipts.receipt_key(self.root, self.head))


class OffloadRows(SatelliteFixture):
    def test_a_satellite_pass_writes_its_own_receipt_and_the_offload_row(self) -> None:
        result = self.gate()
        self.assertEqual((result["status"], self.runs), ("success", 1))
        self.assertIn("receipt_revision", result)
        self.assertEqual((result["offload"]["hub"], result["offload"]["written"]), (HUB, True))
        row, own = self.offload_row(), self.own_row()
        self.assertEqual(row["writer"], "sd-satellite-gate")
        self.assertEqual((row["hub"], row["head"], row["reading"]["status"]), (HUB, self.head, "success"))
        self.assertTrue(row["satellite"]["hostname"])
        self.assertEqual(row["binding"], own["binding"])
        self.assertEqual(row["pack_bin"], sd_gate_receipts.pack_bin())
        self.assertEqual(row["local_block"], "absent")
        self.assertIn("make", row["offload_view"]["tools"])
        self.assertNotIn("receipt_revision", row["reading"])

    def test_the_offload_row_holds_no_variable_value(self) -> None:
        """A credential the gate environment keeps reaches the hub's database as a digest only."""
        with mock.patch.dict(os.environ, {"GH_TOKEN": "synthetic-secret-0001"}):
            self.gate()
        row = self.offload_row()
        self.assertIn("GH_TOKEN", row["offload_view"]["variables"])
        self.assertNotIn("synthetic-secret-0001", json.dumps(row))

    def test_a_hub_run_writes_no_offload_row(self) -> None:
        self.hub = None
        result = self.gate()
        self.assertIn("receipt_revision", result)
        self.assertFalse({"offload", "offload_error", "offload_skipped"} & set(result))
        self.assertEqual(self.offload_row(), {})

    def test_a_repository_that_did_not_opt_in_writes_no_offload_row(self) -> None:
        self.opted = "off"
        result = self.gate()
        self.assertEqual(result["offload_skipped"], "repo.satellite_gate is not accept for this repository")
        self.assertEqual(self.offload_row(), {})

    def test_a_reuse_writes_the_missing_row_with_the_original_time(self) -> None:
        self.opted = "off"
        self.gate()
        self.opted = "accept"
        reused = self.gate()
        self.assertEqual(self.runs, 1)
        self.assertIn("reused", reused)
        self.assertEqual(reused["offload"]["written"], True)
        row = self.offload_row()
        self.assertEqual(row["recorded_at"], self.own_row()["recorded_at"])
        self.assertEqual(row["reading"]["summary"], "sd-check pass ()")
        # The row now stands, so a later reuse leaves it alone.
        self.assertEqual(self.gate()["offload"]["written"], False)
        self.assertEqual(sd_gate_receipts.read_offload(self.database, reused["offload"]["key"])[0],
                         reused["offload"]["revision"])

    def test_a_reuse_replaces_a_row_another_pass_left(self) -> None:
        """A row the hub would refuse (another pass's time, inputs or pack, another writer, a failure, another view) does not stand: the reuse writes its own."""
        from contextlib import closing

        from sd_db import connect, ship

        self.gate()
        self.gate()  # the reuse's own row: the reused pass's binding and pack, at its receipt's time
        key, current = sd_gate_receipts.offload_key(SLUG, self.head), self.offload_row()
        for fields in ({"recorded_at": current["recorded_at"] - 60}, {"binding": {**current["binding"], "inputs": "0" * 12}},
                       {"pack_bin": "0" * 64}, {"writer": "sd-lane"}, {"reading": {**current["reading"], "status": "failure"}},
                       {"offload_view": {**current["offload_view"], "tools": {}}}):
            with self.subTest(fields=sorted(fields)):
                with closing(connect(self.database)) as connection:
                    ship.save(connection, key, ship.read(connection, key)[0], {**current, **fields})
                self.assertEqual(self.gate()["offload"]["written"], True)
                self.assertEqual({name: self.offload_row()[name] for name in fields}, {name: current[name] for name in fields})
        self.assertEqual((self.runs, self.gate()["offload"]["written"]), (1, False))

    def test_an_unreachable_hub_still_runs_the_check_and_reports_offload_error(self) -> None:
        with mock.patch.object(sd_gate_receipts, "_connect", side_effect=ConnectionError("HubUnreachable: no answer")):
            result = self.gate()
        self.assertEqual((result["status"], self.runs), ("success", 1))
        self.assertIn("HubUnreachable", result["offload_error"])
        self.assertIn("receipt_error", result)

    def test_a_differing_published_pack_digest_warns_before_the_run(self) -> None:
        from contextlib import closing

        from sd_db import connect, ship

        with closing(connect(self.database)) as connection:
            ship.save(connection, sd_gate_receipts.PACK_PREFIX + SLUG, 0,
                      {"writer": "sd-lane", "pack_bin": "0" * 64, "pack_rev": "1" * 40, "published_at": "now"})
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = self.gate()
        self.assertEqual(self.runs, 1)
        self.assertIn("satellite_pack_mismatch", result["pack_warning"])
        self.assertIn("is not the hub's 000000000000", stderr.getvalue())

    def test_an_equal_published_pack_digest_warns_of_nothing(self) -> None:
        from contextlib import closing

        from sd_db import connect, ship

        with closing(connect(self.database)) as connection:
            ship.save(connection, sd_gate_receipts.PACK_PREFIX + SLUG, 0,
                      {"writer": "sd-lane", "pack_bin": sd_gate_receipts.pack_bin(), "published_at": "now"})
        self.assertNotIn("pack_warning", self.gate())

    def test_a_publication_that_is_not_an_object_warns_of_nothing_and_the_check_runs(self) -> None:
        from sd_db import ship

        real = ship.read

        def read(connection, key):  # type: ignore[no-untyped-def]
            # `ship.save` writes objects only; a body written by other means can be anything.
            return (1, ["not", "an", "object"]) if key == sd_gate_receipts.PACK_PREFIX + SLUG else real(connection, key)

        with mock.patch.object(ship, "read", read):
            result = self.gate()
        self.assertEqual((result["status"], self.runs), ("success", 1))
        self.assertNotIn("pack_warning", result)


class PackDigest(unittest.TestCase):
    def test_pack_bin_hashes_the_files_gate_inputs_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            pack = pathlib.Path(folder)
            (pack / "sd-x").write_text("one\n", encoding="utf-8")
            (pack / "notes.txt").write_text("not a pack file\n", encoding="utf-8")
            with mock.patch.object(sd_gate_run, "BIN", pack):
                first = sd_gate_receipts.pack_bin()
                (pack / "notes.txt").write_text("still not\n", encoding="utf-8")
                self.assertEqual(sd_gate_receipts.pack_bin(), first)
                (pack / "sd-x").write_text("two\n", encoding="utf-8")
                self.assertNotEqual(sd_gate_receipts.pack_bin(), first)
        self.assertEqual(sd_gate_receipts.pack_bin(own=True), "tree")

    def test_the_offload_key_is_the_same_for_any_checkout_of_one_slug(self) -> None:
        keys = []
        with tempfile.TemporaryDirectory() as folder:
            for name, origin in (("https", f"https://github.com/{SLUG}.git"), ("ssh", "git@github.com:Fixture/Repo.git")):
                checkout = pathlib.Path(folder) / name
                checkout.mkdir()
                git(checkout, "init", "-q")
                git(checkout, "remote", "add", "origin", origin)
                keys.append(sd_gate_receipts.offload_key(sd_gate_receipts.repository_slug(checkout) or "", "a" * 40))
        self.assertEqual(keys, [sd_gate_receipts.offload_key(SLUG, "a" * 40)] * 2)
        self.assertNotEqual(sd_gate_receipts.offload_key(SLUG, "a" * 40), sd_gate_receipts.offload_key(SLUG, "b" * 40))
        self.assertNotEqual(sd_gate_receipts.offload_key(SLUG, "a" * 40, "c" * 40),
                            sd_gate_receipts.offload_key(SLUG, "a" * 40))


class LoginVariables(unittest.TestCase):
    """Decision 2026-10-05 10:02 MDT: `LOGNAME` and `TMPDIR` name the login, so a view leaves them out."""

    def view(self, **extra: str) -> dict:
        environment = {"HOME": "/Users/sat", "USER": "sat", "LOGNAME": "sat", "TMPDIR": "/var/folders/aa/T/",
                       "LANG": "C", "PATH": "/usr/bin", **extra}
        view = sd_gate_receipts.offload_view(environment)
        assert view is not None
        return view

    def test_another_logname_and_tmpdir_compare_equal(self) -> None:
        theirs = self.view()
        ours = self.view(HOME="/Users/hub", USER="hub", LOGNAME="hub", TMPDIR="/var/folders/bb/T/")
        self.assertIsNone(sd_gate_receipts.offload_miss(theirs, ours))
        self.assertFalse({"LOGNAME", "TMPDIR"} & set(theirs["variables"]))

    def test_any_other_differing_variable_still_misses(self) -> None:
        ours = self.view(LOGNAME="hub", TMPDIR="/var/folders/bb/T/", LANG="en_US.UTF-8")
        self.assertEqual(sd_gate_receipts.offload_miss(self.view(), ours), {"part": "variables", "name": "LANG"})


class BindingSplit(SatelliteFixture):
    """Step 4's split: `gate_binding` is the union of its tree part and its machine part, unchanged."""

    def test_gate_binding_is_its_tree_part_and_its_machine_part(self) -> None:
        tree = self.root
        env = sd_gate_run.gate_environment(self.root, dict(os.environ))
        whole = sd_gate_receipts.gate_binding(tree, self.head, "i" * 12, None, env)
        part = sd_gate_receipts.tree_binding(tree, self.head, "i" * 12, None)
        assert whole is not None and part is not None
        self.assertEqual(set(part), set(sd_gate_receipts.TREE_FIELDS))
        self.assertEqual(set(whole) - set(part), {"tools", "python", "environment_sha256", "threads"})
        self.assertEqual({name: whole[name] for name in part}, part)

    def test_the_tree_part_needs_no_tool_on_path(self) -> None:
        env = {"PATH": str(self.root.parent / "empty")}
        self.assertIsNone(sd_gate_receipts.gate_binding(self.root, self.head, "i" * 12, None, env))
        self.assertIsNotNone(sd_gate_receipts.tree_binding(self.root, self.head, "i" * 12, None))


class SatelliteGateReader(unittest.TestCase):
    """`sd_lib.repo_satellite_gate` answers `off` on every doubt, as `repo_ci` answers `github`."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = pathlib.Path(tmp.name).resolve()
        from sd_db import connect, initialise, upsert_repo

        database = home / "sd.db"
        initialise(database)
        self.connection = connect(database)
        self.addCleanup(self.connection.close)
        self.root = home / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        upsert_repo(self.connection, str(self.root), remote=None)

    def read(self, reader) -> str:  # type: ignore[no-untyped-def]
        import sd_db.repos

        with mock.patch.object(sd_db.repos, "repo_satellite_gate", reader, create=True):
            return sd_lib.repo_satellite_gate(self.connection, self.root)

    def test_the_librarys_accept_is_returned(self) -> None:
        self.assertEqual(self.read(lambda connection, path: "accept"), "accept")

    def test_an_unknown_value_or_a_failing_read_answers_off(self) -> None:
        def broken(connection, path):  # type: ignore[no-untyped-def]
            raise RuntimeError("no such column: satellite_gate")

        for reader in (lambda connection, path: "sometimes", broken):
            with self.subTest(reader=reader):
                self.assertEqual(self.read(reader), "off")

    def test_without_the_reader_the_column_is_read_when_present_and_off_when_absent(self) -> None:
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(repo)")}
        if "satellite_gate" in columns:  # a library newer than the pin
            self.connection.execute("ALTER TABLE repo DROP COLUMN satellite_gate")
        self.assertEqual(self.read(None), "off")
        self.connection.execute("ALTER TABLE repo ADD COLUMN satellite_gate TEXT NOT NULL DEFAULT 'off'")
        self.connection.execute("UPDATE repo SET satellite_gate = 'accept'")
        self.assertEqual(self.read(None), "accept")


if __name__ == "__main__":
    unittest.main()
