"""`restore --newest` and the prune of moved copies (sd:4011, hub failover slice 3).

The hourly job mirrors its snapshots to a share. A copy there records the
directory it was written in, so the owned-backup test refused it by path; these
hold that a copy is now judged by its manifest's hashes and its database's
checkpoint, wherever it sits, and that `restore --newest` takes the newest such
copy by the checkpoint time its own database records.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

from sd_db import connect, create_assignment, create_item, upsert_repo
from sd_db.backup import BACKUP_MANIFEST, prune_older, run
from sd_db.errors import BackupError
from sd_db.migrate import initialise
from sd_db.schema import SCHEMA_VERSION
from sd_db.testing import break_foreign_keys
from sd_db.testing.wire import hub_only
from sd_db.writes import unresolved_state

from . import support

#: The module, so a missing name fails one test, not the whole file.
backup = import_module("sd_db.backup")

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / "home"
        (self.home / ".local/share/sd").mkdir(parents=True)
        initialise(home=self.home)
        self.local = self.base / "local" / "sd-backups"
        self.nas = self.base / "nas" / "sd-backups-hourly"
        self.nas.mkdir(parents=True)

    def open(self, home=None):
        connection = connect(home=home or self.home)
        self.addCleanup(connection.close)
        return connection

    def snapshot(self, when, *, title=None):
        if title:
            create_item(self.open(), kind="work", title=title)
        return run(home=self.home, destination=self.local, when=when).directory

    def mirror(self, directory, name=None):
        """The copy rsync leaves on the share: same files, another path."""
        copy = self.nas / (name or directory.name)
        shutil.copytree(directory, copy, symlinks=True)
        return copy

    def fresh_home(self, name="promoted"):
        home = self.base / name
        (home / ".local/share/sd").mkdir(parents=True)
        return home

    def job(self, *argv):
        # SD_NOTIFY: a failing job mails through it, and no test sends a mail.
        return subprocess.run([sys.executable, str(support.SD_DB), "backup", *argv], capture_output=True,
                              text=True, check=False, input="",
                              env={**os.environ, "HOME": str(self.home), "SD_NOTIFY": "/usr/bin/true"})

    def items(self, home):
        return [row["title"] for row in self.open(home).execute("SELECT title FROM item ORDER BY id")]


class Refusals(Case):
    """Refused before any snapshot or hub-only path: these run the same over the wire."""

    def test_a_missing_root_is_a_failure_not_an_empty_prune(self):
        with self.assertRaisesRegex(BackupError, "existing unlinked directory"):
            prune_older(self.base / "unmounted", 7, now=NOW, moved=True)

    def test_the_job_refuses_a_prune_without_an_age(self):
        completed = self.job("--prune-only", "--destination", str(self.nas))
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("--prune-only needs --destination and --keep-days", completed.stdout + completed.stderr)


# Each test takes a snapshot, which `run` refuses off the hub.
@hub_only
class MovedCopies(Case):
    def test_a_copy_past_the_window_is_pruned_by_its_hashes_not_its_path(self):
        old = self.mirror(self.snapshot(datetime(2026, 10, 1, 9, 0, tzinfo=UTC)))
        young = self.mirror(self.snapshot(NOW))
        # The run's own prune still leaves a copy whose manifest names another directory.
        self.assertEqual(prune_older(self.nas, 7, now=NOW), [])

        removed = prune_older(self.nas, 7, now=NOW, moved=True)

        self.assertEqual(removed, [old])
        self.assertFalse(old.exists())
        self.assertTrue(young.exists())

    def test_a_copy_that_differs_from_its_manifest_stays(self):
        # A partial or edited copy is not the backup its manifest describes.
        old = self.mirror(self.snapshot(datetime(2026, 10, 1, 9, 0, tzinfo=UTC)))
        (old / "sd.db").write_bytes((old / "sd.db").read_bytes()[:4096])

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True), [])
        self.assertTrue(old.exists())

    def test_a_copy_named_for_an_old_day_but_taken_inside_the_window_stays(self):
        # Names restart on a promoted hub's empty root, so the name is not the age.
        young = self.mirror(self.snapshot(NOW), "2026-10-01")

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True), [])
        self.assertTrue(young.exists())

    def test_finder_metadata_does_not_keep_an_old_copy(self):
        old = self.mirror(self.snapshot(datetime(2026, 10, 1, 9, 0, tzinfo=UTC)))
        (old / ".DS_Store").write_bytes(b"\0Bud1")
        (old / "._sd.db").write_bytes(b"\0\5\26\7")

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True), [old])

    def test_the_job_prunes_copies_without_taking_a_snapshot(self):
        old = self.mirror(self.snapshot(datetime(2026, 10, 1, 9, 0, tzinfo=UTC)))
        taken = sorted(self.local.iterdir())
        completed = self.job("--prune-only", "--destination", str(self.nas), "--keep-days", "7")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn(f"1 copy older than 7 days removed under {self.nas}", completed.stdout)
        self.assertFalse(old.exists())
        self.assertEqual(sorted(self.local.iterdir()), taken)


@hub_only
class TheNewest(Case):
    def test_the_newest_checkpoint_wins_over_the_newest_name(self):
        self.mirror(self.snapshot(datetime(2026, 10, 12, 9, 0, tzinfo=UTC), title="first"))
        # Named for an earlier day than the first: the name is not the time.
        renamed = self.mirror(self.snapshot(NOW, title="second"), "2026-10-01")
        home = self.fresh_home()

        result = backup.restore_newest([self.base / "missing", self.nas], home=home)

        self.assertEqual(result.snapshot, renamed)
        self.assertEqual(result.taken_at, NOW)
        self.assertEqual(self.items(home), ["first", "second"])
        self.assertEqual(result.refused[0][0], self.base / "missing")
        row = unresolved_state(self.open(home), "restore")[0]
        self.assertEqual(json.loads(row["body"])["from"], str(renamed))

    def test_a_corrupt_newest_is_refused_and_the_next_restores(self):
        good = self.mirror(self.snapshot(datetime(2026, 10, 12, 9, 0, tzinfo=UTC), title="first"))
        bad = self.mirror(self.snapshot(NOW, title="second"))
        (bad / "runner-recovery-note").write_text("written on the share\n")
        lines: list[str] = []
        home = self.fresh_home()

        result = backup.restore_newest([self.nas], home=home, report=lines.append)

        self.assertEqual(result.snapshot, good)
        self.assertEqual(self.items(home), ["first"])
        self.assertEqual([path for path, _ in result.refused], [bad])
        self.assertIn("differ from its manifest", result.refused[0][1])
        self.assertEqual(len(lines), 1)
        self.assertIn(str(bad), lines[0])

    def test_a_newest_snapshot_restore_would_refuse_is_skipped(self):
        # `run` keeps a snapshot of a source with broken references as a forensic copy.
        self.mirror(self.snapshot(datetime(2026, 10, 12, 9, 0, tzinfo=UTC), title="first"))
        connection = self.open()
        create_item(connection, kind="work", title="second")
        break_foreign_keys(self.home / ".local/share/sd/sd.db")
        forensic = self.mirror(self.snapshot(NOW))
        home = self.fresh_home()

        result = backup.restore_newest([self.nas], home=home)

        self.assertEqual([path for path, _ in result.refused], [forensic])
        self.assertIn("restore refuses it", result.refused[0][1])
        self.assertEqual(self.items(home), ["first"])

    def test_when_every_candidate_is_refused_nothing_is_installed(self):
        for when in (datetime(2026, 10, 12, 9, 0, tzinfo=UTC), NOW):
            copy = self.mirror(self.snapshot(when))
            (copy / "sd.db").write_bytes((copy / "sd.db").read_bytes() + b"tail")
        home = self.fresh_home()

        with self.assertRaisesRegex(BackupError, r"no snapshot under .* restored \(2 refused\)"):
            backup.restore_newest([self.nas], home=home)
        self.assertFalse((home / ".local/share/sd/sd.db").exists())

    def test_a_newest_snapshot_newer_than_this_library_stops_the_run(self):
        self.mirror(self.snapshot(datetime(2026, 10, 12, 9, 0, tzinfo=UTC)))
        newest = self.mirror(self.snapshot(NOW))
        raw = sqlite3.connect(newest / "sd.db")
        raw.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        raw.execute("CREATE TABLE future (id INTEGER PRIMARY KEY)")
        raw.close()
        # A newer library counts its new table and writes a manifest that matches its own database.
        manifest = json.loads((newest / BACKUP_MANIFEST).read_text())
        manifest["counts"]["future"] = 0
        manifest["entries"]["sd.db"] = hashlib.sha256((newest / "sd.db").read_bytes()).hexdigest()
        (newest / BACKUP_MANIFEST).write_text(json.dumps(manifest))
        home = self.fresh_home()

        with self.assertRaisesRegex(BackupError, "newer than this library"):
            backup.restore_newest([self.nas], home=home)
        self.assertFalse((home / ".local/share/sd/sd.db").exists())

    def test_a_damaged_header_claiming_a_newer_schema_is_skipped(self):
        # Only a copy whose bytes match its manifest can stop the run for its schema.
        self.mirror(self.snapshot(datetime(2026, 10, 12, 9, 0, tzinfo=UTC), title="first"))
        damaged = self.mirror(self.snapshot(NOW, title="second"))
        data = bytearray((damaged / "sd.db").read_bytes())
        data[60:64] = (SCHEMA_VERSION + 1).to_bytes(4, "big")  # SQLite's user_version field
        (damaged / "sd.db").write_bytes(bytes(data))
        home = self.fresh_home()

        result = backup.restore_newest([self.nas], home=home)

        self.assertEqual([path for path, _ in result.refused], [damaged])
        self.assertIn("differ from its manifest", result.refused[0][1])
        self.assertEqual(self.items(home), ["first"])

    def test_open_leases_from_the_old_hub_are_released_and_noted(self):
        from sd_db import runner_journal as journal
        connection = self.open()
        upsert_repo(connection, "/fixture")
        item = create_item(connection, kind="work", title="leased", repo="/fixture")
        assignment = create_assignment(connection, role="worker", status="running", item=item)
        connection.execute(
            "INSERT INTO runner_run (id,assignment,run,repo,branch,owner,journal_version,work_path,retained_path,"
            "supervisor_pid,created_at,updated_at) VALUES (?,?,1,'/fixture','fixture','fixture',1,'/tmp/work',"
            "'/tmp/retained',4242,'fixture','fixture')", ("e" * 32, assignment))
        connection.execute("INSERT INTO runner_lease (run,repo,branch,exclusive,acquired_at) "
                           "VALUES (?,'/fixture','fixture',1,'fixture')", ("e" * 32,))
        journal.persist(self.home / ".local/share/sd/sd.db",
                        dict(connection.execute("SELECT * FROM runner_run").fetchone()))
        self.mirror(self.snapshot(NOW))
        home = self.fresh_home()

        result = backup.restore_newest([self.nas], home=home)

        self.assertEqual(result.released, ["e" * 32])
        restored = self.open(home)
        self.assertIsNotNone(restored.execute("SELECT released_at FROM runner_lease").fetchone()[0])
        notes = [row["body"] for row in restored.execute("SELECT body FROM note WHERE item=?", (item,))]
        self.assertTrue(any("abandoned at promotion" in body for body in notes), notes)
        # The run row and its journal still agree, so the promoted hub's first backup passes.
        self.assertEqual(restored.execute("SELECT journal_version FROM runner_run").fetchone()[0], 1)
        run(home=home, destination=self.base / "promoted-backups", when=NOW)

    def test_the_verb_restores_the_newest_and_names_it(self):
        copy = self.mirror(self.snapshot(NOW, title="only"))
        home = self.fresh_home()
        completed = subprocess.run(
            [sys.executable, str(support.SD_DB), "restore", "--newest", str(self.nas)],
            capture_output=True, text=True, check=False, input="",
            env={**os.environ, "HOME": str(home)})
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn(f"sd-db: restored {copy} (checkpoint {NOW.isoformat()})", completed.stdout)
        self.assertEqual(self.items(home), ["only"])


if __name__ == "__main__":
    unittest.main()
