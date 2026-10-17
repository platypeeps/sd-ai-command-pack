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
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from unittest import mock

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

    def pre_json(self, copy):
        """What a build before c9ceaf7bb left: a bare-timestamp checkpoint body, no `checkpoint` key."""
        manifest = json.loads((copy / BACKUP_MANIFEST).read_text())
        raw = sqlite3.connect(copy / "sd.db")
        with raw:
            raw.execute("UPDATE state SET body = json_extract(body, '$.at') WHERE kind='checkpoint' AND key=?",
                        (manifest["run_id"],))
        raw.close()
        del manifest["checkpoint"]
        manifest["entries"]["sd.db"] = hashlib.sha256((copy / "sd.db").read_bytes()).hexdigest()
        (copy / BACKUP_MANIFEST).write_text(json.dumps(manifest))
        return copy

    def uncheckpointed(self, copy, *, read_only=True):
        """A copy whose database holds no row for its run. `read_only` is what a snapshot taken
        before `migrate` writes: the manifest says `checkpoint: false` and no row was ever written."""
        manifest = json.loads((copy / BACKUP_MANIFEST).read_text())
        raw = sqlite3.connect(copy / "sd.db")
        with raw:
            raw.execute("DELETE FROM state WHERE kind='checkpoint' AND key=?", (manifest["run_id"],))
        raw.close()
        manifest["checkpoint"] = not read_only
        manifest["entries"]["sd.db"] = hashlib.sha256((copy / "sd.db").read_bytes()).hexdigest()
        (copy / BACKUP_MANIFEST).write_text(json.dumps(manifest))
        return copy

    def stopped(self, copy):
        """What a run that failed before `_record_backup` leaves: everything but the manifest."""
        (copy / BACKUP_MANIFEST).unlink()
        return copy

    def leftover(self, name):
        """A dated folder no manifest describes, such as a copy stopped partway (sd:4917)."""
        folder = self.nas / name
        (folder / "executions").mkdir(parents=True, exist_ok=True)
        (folder / "sd.db").write_bytes(b"half a copy")
        return folder

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

    def test_the_dry_run_needs_the_prune_only_mode(self):
        completed = self.job("--dry-run", "--destination", str(self.nas))
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("--dry-run needs --prune-only", completed.stderr)
        self.assertEqual(list(self.nas.iterdir()), [])

    def test_the_unmanifested_prune_needs_the_prune_only_mode(self):
        folder = self.leftover("2026-09-01")
        completed = self.job("--prune-unmanifested", "--destination", str(self.nas), "--keep-days", "7")
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("--prune-unmanifested needs --prune-only", completed.stderr)
        self.assertTrue((folder / "sd.db").exists())

    def test_the_unmanifested_prune_needs_an_age(self):
        folder = self.leftover("2026-09-01")
        completed = self.job("--prune-only", "--prune-unmanifested", "--destination", str(self.nas))
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("--prune-only needs --destination and --keep-days", completed.stderr)
        self.assertTrue((folder / "sd.db").exists())

    def test_the_unmanifested_prune_needs_a_moved_root(self):
        folder = self.leftover("2026-09-01")
        with self.assertRaisesRegex(BackupError, "only a moved root"):
            prune_older(self.nas, 7, now=NOW, unmanifested=True)
        self.assertTrue((folder / "sd.db").exists())

    def test_a_leftover_that_is_itself_a_mount_point_is_kept(self):
        leftover = self.nas / ".2026-10-01.removing"
        leftover.mkdir()
        (leftover / "sd.db").write_bytes(b"on another volume")
        real = Path.lstat

        def mounted(path, *args, **kwargs):
            details = real(path, *args, **kwargs)
            if path == leftover:
                fields = list(details)
                fields[stat.ST_DEV] += 1
                return os.stat_result(fields)
            return details

        lines: list[str] = []
        with mock.patch.object(Path, "lstat", mounted):
            self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True, report=lines.append), [])

        self.assertTrue((leftover / "sd.db").exists())
        self.assertEqual(lines, [f"kept {leftover}: it holds a linked, mounted or special entry"])

    def test_a_leftover_with_an_unreadable_folder_is_kept_and_listed(self):
        # `rglob` skips a folder it cannot list; the walk must not, or `rmtree` stops halfway.
        leftover = self.nas / ".2026-10-01.removing"
        (leftover / "executions" / "inner").mkdir(parents=True)
        (leftover / "executions").chmod(0)
        self.addCleanup((leftover / "executions").chmod, 0o700)
        lines: list[str] = []

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True, report=lines.append), [])

        self.assertTrue(leftover.exists())
        self.assertEqual(len(lines), 1, lines)
        self.assertIn(f"kept {leftover}: it could not be read", lines[0])


class Unmanifested(Case):
    """`--prune-unmanifested` (sd:4917): a folder with no manifest goes once its name is past twice the window."""

    def setUp(self):
        super().setUp()
        # The newest copy's manifest names where `run` wrote it, outside this root: the proof the root is a mirror.
        self.copy = self.provenance({"directory": str(self.local / "2026-10-12")})

    def provenance(self, value, name="2026-10-12"):
        """A copy inside the window whose manifest holds only `value`; the scan never opens it."""
        folder = self.nas / name
        folder.mkdir(exist_ok=True)
        (folder / BACKUP_MANIFEST).write_text(value if isinstance(value, str) else json.dumps(value))
        return folder

    def refused(self, pattern):
        folder = self.leftover("2026-09-01")
        with self.assertRaisesRegex(BackupError, pattern):
            prune_older(self.nas, 7, now=NOW, moved=True, unmanifested=True)
        self.assertTrue((folder / "sd.db").exists())

    def test_a_root_with_no_manifest_at_all_is_refused(self):
        shutil.rmtree(self.copy)
        self.refused("no folder under .* has a manifest")

    def test_a_manifest_naming_no_directory_refuses_the_root(self):
        for value in ({}, {"directory": None}, {"directory": 12}, {"directory": ""},
                      {"directory": "sd-backups/2026-10-12"}, [1, 2]):
            with self.subTest(value=value):
                self.provenance(value)
                self.refused("names no directory it was written in|could not be read")

    def test_a_manifest_naming_a_folder_of_this_root_refuses_it(self):
        # Copied or renamed inside the root: written here, so `run` may write here too.
        self.provenance({"directory": str(self.nas / "2026-10-11")})
        self.refused("written in place")

    def test_a_linked_manifest_refuses_the_root(self):
        target = self.base / "elsewhere.json"
        target.write_text(json.dumps({"directory": str(self.local / "2026-10-12")}))
        (self.copy / BACKUP_MANIFEST).unlink()
        (self.copy / BACKUP_MANIFEST).symlink_to(target)
        self.refused("is a link")

    def test_a_manifest_that_cannot_be_looked_up_refuses_the_root(self):
        self.copy.chmod(0o644)  # listable, but no entry in it can be looked up
        self.addCleanup(self.copy.chmod, 0o755)
        self.refused("could not tell whether")

    def test_a_folder_whose_entries_cannot_be_looked_up_is_kept_not_read_as_unmanifested(self):
        # `exists()` reads EACCES as absent, which made a folder nobody can inspect look manifest-less.
        folder = self.leftover("2026-09-01")
        other = self.leftover("2026-09-02")
        folder.chmod(0o644)
        self.addCleanup(folder.chmod, 0o755)
        lines: list[str] = []

        removed = prune_older(self.nas, 7, now=NOW, moved=True, unmanifested=True, report=lines.append)

        self.assertEqual(removed, [other])
        folder.chmod(0o755)
        self.assertTrue((folder / "sd.db").exists())
        self.assertEqual(len([line for line in lines if line.startswith(f"kept {folder}: ")]), 1, lines)
        self.assertIn("could not be read", lines[0])

    def test_a_window_whose_cutoff_reaches_before_year_one_is_refused(self):
        folder = self.leftover("2026-09-01")
        for flag in (False, True):
            with self.subTest(unmanifested=flag), self.assertRaisesRegex(BackupError, "before the calendar"):
                prune_older(self.nas, 999999999, now=NOW, moved=True, unmanifested=flag)
        self.assertTrue((folder / "sd.db").exists())

    def test_only_a_dated_folder_named_past_twice_the_window_goes(self):
        # NOW less 14 days is 2026-09-29: that day stays, the day before goes.
        gone = [self.leftover("2026-09-28"), self.leftover("2026-09-28.2")]
        boundary = self.leftover("2026-09-29")
        inside = self.leftover("2026-10-01")
        foreign = [self.leftover("2026-09-01-by-hand"), self.leftover("old")]
        outside = self.base / "outside" / "2026-09-01"
        outside.mkdir(parents=True)
        (outside / "sd.db").write_bytes(b"not under the root")
        link = self.nas / "2026-09-20"
        link.symlink_to(outside, target_is_directory=True)
        lines: list[str] = []

        removed = prune_older(self.nas, 7, now=NOW, moved=True, unmanifested=True, report=lines.append)

        self.assertEqual(removed, gone)
        self.assertEqual(sorted(self.nas.iterdir()), sorted([link, boundary, inside, *foreign, self.copy]))
        for folder in (boundary, inside, *foreign):
            self.assertTrue((folder / "sd.db").exists())
        self.assertTrue(link.is_symlink())
        self.assertTrue((outside / "sd.db").exists())
        self.assertEqual(lines, [f"kept {link}: it is a link or not a directory",
                                 f"kept {boundary}: no manifest (stopped run?)",
                                 f"kept {inside}: no manifest (stopped run?)",
                                 f"removed {gone[0]}", f"removed {gone[1]}"])

    def test_without_the_flag_the_same_folder_stays(self):
        folder = self.leftover("2026-09-01")

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True), [])
        self.assertTrue((folder / "sd.db").exists())

    def test_a_window_whose_double_reaches_before_year_one_removes_no_folder(self):
        # 400000 days back is the year 931; twice that is before the calendar starts.
        folder = self.leftover("0001-01-01")

        self.assertEqual(prune_older(self.nas, 400000, now=NOW, moved=True, unmanifested=True), [])
        self.assertTrue((folder / "sd.db").exists())

    def test_an_unreadable_newest_manifest_refuses_the_root(self):
        # It cannot say where it was written, so the root may be one `run` writes in.
        folder = self.leftover("2026-09-01")
        (self.leftover("2026-10-12") / BACKUP_MANIFEST).write_text("{")

        with self.assertRaisesRegex(BackupError, "could not tell whether"):
            prune_older(self.nas, 7, now=NOW, moved=True, unmanifested=True)
        self.assertTrue((folder / "sd.db").exists())

    def test_a_folder_holding_a_link_is_kept(self):
        folder = self.leftover("2026-09-01")
        target = self.base / "elsewhere.db"
        target.write_bytes(b"keep me")
        (folder / "executions" / "link").symlink_to(target)
        lines: list[str] = []

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True, unmanifested=True, report=lines.append), [])

        self.assertEqual(target.read_bytes(), b"keep me")
        self.assertTrue((folder / "sd.db").exists())
        self.assertEqual(lines, [f"kept {folder}: it holds a linked, mounted or special entry"])

    def test_a_manifest_written_before_the_removal_keeps_the_folder(self):
        folder = self.leftover("2026-09-01")
        real = backup._contained

        def copy_finishes(path):
            real(path)
            (path / BACKUP_MANIFEST).write_text("{}")  # between the scan and the removal

        with (mock.patch.object(backup, "_contained", copy_finishes),
              self.assertRaisesRegex(BackupError, "changed before retention")):
            prune_older(self.nas, 7, now=NOW, moved=True, unmanifested=True)
        self.assertTrue((folder / "sd.db").exists())

    def test_the_dry_run_lists_what_would_go_and_deletes_nothing(self):
        folder = self.leftover("2026-09-01")

        completed = self.job("--prune-only", "--prune-unmanifested", "--dry-run", "--destination", str(self.nas),
                             "--keep-days", "7")

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn(f"would remove {folder}\n", completed.stdout)
        self.assertIn("dry run: 1 copy older than 7 days, or with no manifest older than 14 days, would be removed",
                      completed.stdout)
        self.assertTrue((folder / "sd.db").exists())

    def test_the_job_removes_and_names_each_folder(self):
        folder = self.leftover("2026-09-01")

        completed = self.job("--prune-only", "--prune-unmanifested", "--destination", str(self.nas),
                             "--keep-days", "7")

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn(f"sd-db backup: removed {folder}\n", completed.stdout)
        self.assertIn(f"1 copy older than 7 days, or with no manifest older than 14 days, removed under {self.nas}",
                      completed.stdout)
        self.assertEqual(list(self.nas.iterdir()), [self.copy])


# Each test takes a snapshot, which `run` refuses off the hub.
@hub_only
class MovedCopies(Case):
    def test_the_unmanifested_prune_still_judges_a_copy_by_its_manifest(self):
        old = self.mirror(self.snapshot(datetime(2026, 9, 1, 9, 0, tzinfo=UTC)))
        partial = self.mirror(self.snapshot(datetime(2026, 9, 2, 9, 0, tzinfo=UTC)))
        (partial / "sd.db").write_bytes((partial / "sd.db").read_bytes()[:4096])

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True, unmanifested=True), [old])
        self.assertTrue((partial / "sd.db").exists())

    def test_the_unmanifested_prune_refuses_a_root_backups_were_written_in(self):
        self.snapshot(datetime(2026, 9, 1, 9, 0, tzinfo=UTC))
        stopped = self.local / "2026-09-02"
        stopped.mkdir()
        (stopped / "sd.db").write_bytes(b"half a snapshot")

        with self.assertRaisesRegex(BackupError, "written in place"):
            prune_older(self.local, 7, now=NOW, moved=True, unmanifested=True)
        self.assertTrue((stopped / "sd.db").exists())

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

    def test_a_pre_json_copy_past_the_window_is_pruned(self):
        # sd:4694: a bare-timestamp checkpoint was unreadable, so these copies never aged out.
        old = self.pre_json(self.mirror(self.snapshot(datetime(2026, 10, 1, 9, 0, tzinfo=UTC))))

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True), [old])
        self.assertFalse(old.exists())

    def test_a_stopped_run_past_the_window_is_kept_and_listed(self):
        # A run that stopped before its manifest proves nothing about what is in the folder.
        old = self.stopped(self.mirror(self.snapshot(datetime(2026, 10, 1, 9, 0, tzinfo=UTC))))
        lines: list[str] = []

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True, report=lines.append), [])

        self.assertTrue((old / "sd.db").exists())
        self.assertEqual(lines, [f"kept {old}: no manifest (stopped run?)"])

    def test_a_dated_folder_holding_a_copied_store_is_kept(self):
        # A hand-kept copy of the live store holds earlier backup checkpoints too (sd:4694 lane review).
        self.snapshot(datetime(2026, 9, 30, 9, 0, tzinfo=UTC))
        kept = self.nas / "2026-10-01"
        kept.mkdir()
        shutil.copy2(self.home / ".local/share/sd/sd.db", kept / "sd.db")
        lines: list[str] = []

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True, report=lines.append), [])

        self.assertTrue((kept / "sd.db").exists())
        self.assertEqual(lines, [f"kept {kept}: no manifest (stopped run?)"])

    def test_a_copy_taken_before_migrate_is_kept_with_its_reason(self):
        # sd:4700: four NAS copies read `'NoneType' object is not subscriptable` here.
        read_only = self.uncheckpointed(self.mirror(self.snapshot(datetime(2026, 10, 1, 9, 0, tzinfo=UTC))))
        missing = self.uncheckpointed(self.mirror(self.snapshot(datetime(2026, 10, 2, 9, 0, tzinfo=UTC))),
                                      read_only=False)
        lines: list[str] = []

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True, report=lines.append), [])

        self.assertTrue((read_only / "sd.db").exists())
        self.assertTrue((missing / "sd.db").exists())
        self.assertEqual(lines, [
            f"kept {read_only}: it was taken read-only before `migrate`, so no checkpoint row dates it",
            f"kept {missing}: its database holds no checkpoint row for its run"])

    def test_a_pre_json_copy_inside_the_window_stays(self):
        young = self.pre_json(self.mirror(self.snapshot(datetime(2026, 10, 10, 9, 0, tzinfo=UTC))))
        lines: list[str] = []

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True, report=lines.append), [])
        self.assertTrue(young.exists())
        self.assertEqual(lines, [])

    def test_the_dry_run_lists_what_would_go_and_deletes_nothing(self):
        pre = self.pre_json(self.mirror(self.snapshot(datetime(2026, 10, 1, 9, 0, tzinfo=UTC))))
        halted = self.stopped(self.mirror(self.snapshot(datetime(2026, 10, 2, 9, 0, tzinfo=UTC))))

        completed = self.job("--prune-only", "--dry-run", "--destination", str(self.nas), "--keep-days", "7")

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn(f"would remove {pre}\n", completed.stdout)
        self.assertIn(f"kept {halted}: no manifest (stopped run?)\n", completed.stdout)
        self.assertIn("dry run: 1 copy older than 7 days would be removed", completed.stdout)
        self.assertTrue(pre.exists())
        self.assertTrue(halted.exists())

    def test_a_removal_stopped_halfway_is_finished_by_the_next_prune(self):
        old = self.mirror(self.snapshot(datetime(2026, 10, 1, 9, 0, tzinfo=UTC)))
        doomed = self.nas / ".2026-10-01.removing"

        def stop_after_one_file(path):
            (path / "sd.db").unlink()
            raise KeyboardInterrupt  # the job's time bound, between two unlinks

        with mock.patch.object(backup.shutil, "rmtree", stop_after_one_file), self.assertRaises(KeyboardInterrupt):
            prune_older(self.nas, 7, now=NOW, moved=True)
        self.assertEqual(sorted(self.nas.iterdir()), [doomed])
        # Not a dated name: restore never reads the half left behind.
        with self.assertRaisesRegex(BackupError, r"\(0 refused\)"):
            backup.restore_newest([self.nas], home=self.fresh_home())
        dry: list[str] = []
        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True, dry_run=True, report=dry.append), [])
        self.assertTrue(doomed.exists())
        lines: list[str] = []

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True, report=lines.append), [])

        self.assertFalse(old.exists())
        self.assertEqual(list(self.nas.iterdir()), [])
        self.assertEqual(dry, [f"would finish removing {doomed}, which an earlier prune stopped inside"])
        self.assertEqual(lines, [f"finished removing {doomed}, which an earlier prune stopped inside"])

    def test_a_leftover_holding_a_special_entry_is_kept_and_listed(self):
        leftover = self.nas / ".2026-10-01.removing"
        leftover.mkdir()
        os.mkfifo(leftover / "pipe")
        young = self.mirror(self.snapshot(NOW))
        lines: list[str] = []

        self.assertEqual(prune_older(self.nas, 7, now=NOW, moved=True, report=lines.append), [])

        self.assertEqual(sorted(self.nas.iterdir()), [leftover, young])
        self.assertEqual(lines, [f"kept {leftover}: it holds a linked, mounted or special entry"])

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

    def test_stopped_runs_are_one_line_and_a_real_refusal_keeps_its_own(self):
        good = self.mirror(self.snapshot(datetime(2026, 10, 9, 9, 0, tzinfo=UTC), title="first"))
        for when in (datetime(2026, 10, 10, 9, 0, tzinfo=UTC), datetime(2026, 10, 11, 9, 30, tzinfo=UTC)):
            self.stopped(self.mirror(self.snapshot(when)))
        bad = self.mirror(self.snapshot(NOW, title="second"))
        (bad / "runner-recovery-note").write_text("written on the share\n")
        lines: list[str] = []
        home = self.fresh_home()

        result = backup.restore_newest([self.nas], home=home, report=lines.append)

        self.assertEqual(result.snapshot, good)
        self.assertEqual(len(result.refused), 3)
        self.assertEqual(len(lines), 2, lines)
        self.assertEqual(lines[0], f"refused 2 snapshot(s) under {self.nas} with no manifest (stopped runs?), "
                                   "named 2026-10-10 to 2026-10-11")
        self.assertIn(f"refused {bad}: ", lines[1])

    def test_a_pre_json_snapshot_restores(self):
        old = self.pre_json(self.mirror(self.snapshot(datetime(2026, 10, 1, 9, 0, tzinfo=UTC), title="first")))
        home = self.fresh_home()

        result = backup.restore_newest([self.nas], home=home)

        self.assertEqual((result.snapshot, result.refused), (old, []))
        self.assertEqual(result.taken_at, datetime(2026, 10, 1, 9, 0, tzinfo=UTC))
        self.assertEqual(self.items(home), ["first"])

    def test_a_copy_taken_before_migrate_is_refused_by_name_and_the_next_restores(self):
        good = self.mirror(self.snapshot(datetime(2026, 10, 12, 9, 0, tzinfo=UTC), title="first"))
        read_only = self.uncheckpointed(self.mirror(self.snapshot(NOW, title="second")))
        home = self.fresh_home()

        result = backup.restore_newest([self.nas], home=home)

        self.assertEqual(result.snapshot, good)
        self.assertEqual(result.refused, [
            (read_only, "it was taken read-only before `migrate`, so no checkpoint row dates it")])

    def test_a_tie_goes_to_the_new_format_snapshot(self):
        when = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
        new = self.mirror(self.snapshot(when, title="first"))
        # Same checkpoint time, a later name, the old body: the name must not win the tie.
        old = self.pre_json(self.mirror(self.snapshot(when, title="second")))
        self.assertGreater(old.name, new.name)
        home = self.fresh_home()

        result = backup.restore_newest([self.nas], home=home)

        self.assertEqual(result.snapshot, new)
        self.assertEqual(self.items(home), ["first"])

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
