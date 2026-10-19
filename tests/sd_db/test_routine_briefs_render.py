"""The vault copies of routine briefs: `routine_briefs.render` and `sd reports brief render` (sd:4041).

The render writes each row's text with a `mirror-hash` line (`hashed`), into
the folder the owning repository's `channels` setting names. Every vault and
database is a temp dir; `TempRootCase` fails a test whose copy lands outside it.
"""

import os
import subprocess
import sys
import threading
import time
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

from sd_db import connect, repos, routine_briefs, runner_journal
from sd_db.migrate import initialise
from sd_db.remote import HubOnly
from sd_db.routine_briefs import add, copies_state, hash_holds, hashed, render
from sd_db.testing.wire import hub_only
from sd_db.writes import record_state

from . import support

PACK = Path(__file__).resolve().parents[2]

DAILY = "2026-10-13 - Daily Intel Brief"
TEXT = "---\ntags:\n  - brief\n---\n\n# Daily Intel Brief\n\nThree things.\n"
FOLDER = "System/AI Generated/Briefs"


class Copies(support.TempRootCase):
    def setUp(self):
        super().setUp()
        initialise(self.root / "sd.db")
        self.db = connect(self.root / "sd.db")
        self.addCleanup(self.db.close)
        self.checkout = support.repository(self.root / "system")
        self.repo = repos.add(self.db, self.checkout, home=self.root / "home")
        self.vault = self.root / "vault"
        self.vault.mkdir()
        self.folder = self.vault / FOLDER
        self.channels({"obsidian": {"folder": FOLDER}})

    def channels(self, value):
        repos.set_channels(self.db, self.checkout, value)

    def add(self, text=TEXT, stem=DAILY, mode=None):
        return add(self.db, stem, text, repo=str(self.checkout), who="operator", mode=mode)

    def render(self):
        return render(self.db, self.vault)

    def copy(self, stem=DAILY, folder=None):
        return ((folder or self.folder) / f"{stem}.md").read_text(encoding="utf-8")

    def beat(self):
        found = copies_state(self.db)
        return None if found is None else found[1]

    def files(self):
        return sorted(path.relative_to(self.vault).as_posix() for path in self.vault.rglob("*") if path.is_file())


@hub_only  # a render in this process takes the lock beside the database
class TheCopies(Copies):
    def test_with_no_rows_a_render_writes_nothing(self):
        copies = self.render()
        self.assertEqual((copies["state"], copies["written"], self.files()), ("ok", [], []))

    def test_a_row_is_written_once_with_its_mirror_hash_and_the_heartbeat_says_so(self):
        self.add()
        self.assertEqual(self.render()["written"], [DAILY])
        self.assertEqual(self.copy(), hashed(TEXT))
        self.assertTrue(hash_holds(self.copy()))
        self.assertEqual(self.render()["written"], [])
        beat = self.beat()
        self.assertEqual({key: beat[key] for key in ("ok", "state", "folder", "previous_folder", "written",
                                                      "refused", "reason")},
                         {"ok": True, "state": "ok", "folder": {self.repo: FOLDER}, "previous_folder": {},
                          "written": 0, "refused": [], "reason": None})

    def test_an_imported_note_with_no_hash_that_equals_its_row_takes_the_hash_only(self):
        self.folder.mkdir(parents=True)
        (self.folder / f"{DAILY}.md").write_text(TEXT, encoding="utf-8")
        self.add()
        self.assertEqual(self.render()["written"], [DAILY])
        self.assertEqual(self.copy(), hashed(TEXT))

    def test_a_replaced_row_overwrites_its_rendered_copy(self):
        self.add()
        self.render()
        self.add("---\na: b\n---\nnew\n", mode="replace")
        self.assertEqual(self.render()["written"], [DAILY])
        self.assertEqual(self.copy(), hashed("---\na: b\n---\nnew\n"))

    def test_a_hand_edit_to_a_copy_is_kept_and_refused(self):
        self.add()
        self.render()
        edited = self.copy().replace("Three", "Four")
        (self.folder / f"{DAILY}.md").write_text(edited, encoding="utf-8")
        self.add(TEXT + "more\n", mode="extend")
        copies = self.render()
        self.assertEqual(([stem for stem, _ in copies["refused"]], copies["ok"]), ([DAILY], False))
        self.assertIn("a hand edit, kept", copies["refused"][0][1])
        self.assertEqual(self.copy(), edited)
        self.assertEqual((self.beat()["state"], self.beat()["refused"]), ("failed", [DAILY]))

    def test_a_note_with_no_hash_that_differs_from_its_row_is_kept_and_refused(self):
        self.folder.mkdir(parents=True)
        (self.folder / f"{DAILY}.md").write_text(TEXT + "an edit\n", encoding="utf-8")
        self.add()
        copies = self.render()
        self.assertIn("no mirror-hash and differs", copies["refused"][0][1])
        self.assertEqual(self.copy(), TEXT + "an edit\n")

    def test_a_brief_file_with_no_row_is_reported_and_kept_and_another_note_is_left_alone(self):
        self.add()
        self.folder.mkdir(parents=True)
        (self.folder / "2026-10-01 - Daily Intel Brief.md").write_text(TEXT, encoding="utf-8")
        (self.folder / "Index.md").write_text("# index\n", encoding="utf-8")
        copies = self.render()
        self.assertEqual([stem for stem, _ in copies["refused"]], ["2026-10-01 - Daily Intel Brief"])
        self.assertEqual(self.copy("2026-10-01 - Daily Intel Brief"), TEXT)
        self.assertTrue((self.folder / "Index.md").exists())

    def test_rows_whose_stems_name_one_file_on_macos_are_refused_and_none_is_written(self):
        self.add()
        self.render()
        other = self.add("---\na: b\n---\nother text\n", stem="2026-10-12 - Other")["item"]
        # A pack before the add refusal (sd:4040) could file this second spelling.
        self.db.execute("UPDATE item SET title = ?, external_id = ? WHERE id = ?", (DAILY.lower(), DAILY.lower(), other))
        copies = self.render()
        self.assertEqual(sorted(stem for stem, _ in copies["refused"]), sorted([DAILY, DAILY.lower()]))
        self.assertIn(f"also the file of {DAILY.lower()}", dict(copies["refused"])[DAILY])
        self.assertEqual((copies["written"], copies["state"]), ([], "failed"))
        self.assertEqual(self.copy(), hashed(TEXT))

    def test_a_copy_named_in_another_unicode_form_is_its_rows_copy_not_a_stray(self):
        cafe = unicodedata.normalize("NFC", "2026-10-13 - Café")
        self.add(stem=cafe)
        self.folder.mkdir(parents=True)
        (self.folder / f"{unicodedata.normalize('NFD', cafe)}.md").write_text(hashed(TEXT), encoding="utf-8")
        copies = self.render()
        self.assertEqual((copies["refused"], copies["state"]), ([], "ok"))

    def test_two_repositories_in_one_folder_are_not_each_others_strays(self):
        other = support.repository(self.root / "other")
        repos.add(self.db, other, home=self.root / "home")
        repos.set_channels(self.db, other, {"obsidian": {"folder": FOLDER.lower()}})
        self.add()
        add(self.db, "2026-10-12 - Other", TEXT, repo=str(other), who="operator")
        copies = self.render()
        self.assertEqual((copies["refused"], copies["state"]), ([], "ok"))
        self.assertEqual(sorted(copies["written"]), ["2026-10-12 - Other", DAILY])

    def test_the_heartbeat_lists_at_most_50_refused_stems(self):
        self.add()
        self.folder.mkdir(parents=True)
        for day in range(1, 61):
            (self.folder / f"2026-{day // 28 + 1:02d}-{day % 28 + 1:02d} - Old.md").write_text(TEXT, encoding="utf-8")
        copies = self.render()
        self.assertEqual((len(copies["refused"]), len(self.beat()["refused"])), (60, 50))


@hub_only  # a render in this process takes the lock beside the database
class TheRefusals(Copies):
    def test_a_satellite_refuses_by_name_and_writes_nothing(self):
        self.add()
        with patch("sd_db.database.served_by", return_value="hub.example.test:8765"), \
                self.assertRaisesRegex(HubOnly, "brief render"):
            self.render()
        self.assertEqual((self.files(), self.beat()), ([], None))

    def test_an_open_restore_refuses_before_any_file(self):
        self.add()
        record_state(self.db, "restore", key="2026-10-13")
        copies = self.render()
        self.assertIn("restore", copies["reason"])
        self.assertEqual((self.files(), self.beat()["state"]), ([], "failed"))

    def test_no_vault_or_a_missing_one_writes_nothing_and_creates_no_vault(self):
        self.add()
        self.assertIn("OBSIDIAN_VAULT", render(self.db, None)["reason"])
        missing = self.root / "elsewhere"
        self.assertIn("not a directory", render(self.db, missing)["reason"])
        self.assertFalse(missing.exists())

    def test_a_folder_that_links_outside_the_vault_is_refused_and_nothing_written_there(self):
        self.add()
        outside = self.root / "outside"
        outside.mkdir()
        self.folder.parent.mkdir(parents=True)
        self.folder.symlink_to(outside)
        copies = self.render()
        self.assertIn("outside the vault", copies["reason"])
        self.assertEqual((list(outside.iterdir()), self.beat()["state"]), ([], "failed"))

    def test_a_setting_it_cannot_read_writes_nothing_and_never_the_default_folder(self):
        self.add()
        self.db.execute("UPDATE repo SET channels = ? WHERE path = ?", ('{"obsidian": {"folder": "/abs"}}', self.repo))
        copies = self.render()
        self.assertIn("cannot be used", copies["reason"])
        self.assertEqual((self.files(), self.beat()["state"]), ([], "failed"))

    def test_a_store_too_old_for_the_setting_writes_nothing(self):
        from sd_db.errors import SchemaTooOld

        self.add()
        with patch("sd_db.repos.repo_channels", side_effect=SchemaTooOld(28, 29)):
            copies = self.render()
        self.assertIsNotNone(copies["reason"])
        self.assertEqual(self.files(), [])


@hub_only  # a render in this process takes the lock beside the database
class TheSetting(Copies):
    def test_no_setting_or_an_empty_obsidian_is_the_default_folder(self):
        self.add()
        # sd:3980: a feed alone is no outbound setting, so it keeps the default.
        values: tuple[dict | None, ...] = (None, {"obsidian": {}}, {"feed": {"url": "https://example.test/f"}})
        for value in values:
            with self.subTest(value=value):
                self.channels(value)
                self.render()
                self.assertEqual(self.copy(folder=self.vault / "Briefs" / "system"), hashed(TEXT))

    def test_a_setting_without_obsidian_is_off_and_keeps_the_copies(self):
        self.add()
        self.render()
        self.channels({"notion": {}})
        self.add(TEXT + "more\n", mode="extend")
        copies = self.render()
        self.assertEqual((copies["state"], copies["written"], self.beat()["folder"]), ("off", [], {self.repo: None}))
        self.assertEqual(self.copy(), hashed(TEXT))

    def test_a_folder_change_names_the_copies_left_behind_and_deletes_none(self):
        self.add()
        self.render()
        self.channels({"obsidian": {"folder": "Briefs/moved"}})
        copies = self.render()
        self.assertEqual(copies["left"], [f"{FOLDER}/{DAILY}.md"])
        self.assertEqual(self.beat()["previous_folder"], {self.repo: FOLDER})
        self.assertEqual(self.copy(folder=self.vault / "Briefs/moved"), hashed(TEXT))
        self.assertEqual(self.copy(), hashed(TEXT))
        self.assertEqual(self.render()["left"], [f"{FOLDER}/{DAILY}.md"])  # until the operator deletes it
        (self.folder / f"{DAILY}.md").unlink()
        self.assertEqual((self.render()["left"], self.beat()["previous_folder"]), ([], {}))

    def test_a_folder_renamed_only_in_case_leaves_no_copies_behind(self):
        self.add()
        self.render()
        self.channels({"obsidian": {"folder": FOLDER.lower()}})
        copies = self.render()
        self.assertEqual((copies["left"], copies["refused"], self.beat()["previous_folder"]), ([], [], {}))


@hub_only  # a render in this process takes the lock beside the database
class TheSteps(Copies):
    def test_a_write_error_after_one_file_leaves_whole_files_and_a_rerun_finishes(self):
        self.add()
        self.add(stem="2026-10-12 - Daily Intel Brief")
        real, calls = os.replace, []

        def fail_second(source, target):
            calls.append(target)
            if len(calls) == 2:
                raise PermissionError("Documents access denied")
            real(source, target)

        with patch("sd_db.records.os.replace", side_effect=fail_second):
            copies = self.render()
        self.assertIn("Documents access denied", copies["reason"])
        self.assertEqual(self.beat()["state"], "failed")
        self.assertEqual(len(self.files()), 1)
        self.assertEqual(list(self.vault.rglob(".*.tmp")), [])
        rerun = self.render()
        self.assertEqual((rerun["ok"], len(rerun["written"]), len(self.files())), (True, 1, 2))

    def test_a_render_waiting_on_the_lock_reads_the_rows_committed_while_it_waited(self):
        self.add()
        lock = self.root / routine_briefs.LOCK_NAME
        waiting, result = threading.Event(), {}
        real_sleep = time.sleep

        def polled(seconds):
            waiting.set()
            real_sleep(min(seconds, 0.05))

        def second():
            other = connect(self.root / "sd.db")
            try:
                result["copies"] = render(other, self.vault)
            finally:
                other.close()

        with patch("sd_db.runner_journal.time.sleep", side_effect=polled):
            with runner_journal.lock(lock, blocking=False):
                thread = threading.Thread(target=second)
                thread.start()
                self.assertTrue(waiting.wait(10))
                self.add("---\na: b\n---\nnewer\n", mode="replace")
            thread.join(30)
        self.assertEqual(result["copies"]["written"], [DAILY])
        self.assertEqual(self.copy(), hashed("---\na: b\n---\nnewer\n"))

    def test_a_lock_wait_that_runs_out_is_a_failed_render(self):
        self.add()
        with patch.object(routine_briefs, "LOCK_WAIT", 0.1), \
                runner_journal.lock(self.root / routine_briefs.LOCK_NAME, blocking=False):
            copies = self.render()
        self.assertIn("another brief render held the lock", copies["reason"])
        self.assertEqual((self.files(), self.beat()["state"]), ([], "failed"))


class TheVerbs(Copies):
    """`sd reports brief` through `bin/sd`, with a temp HOME whose default database is the fixture's.

    Not `hub_only`: the render runs in the child, which opens its database locally."""

    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        store = self.home / ".local/share/sd/sd.db"
        store.parent.mkdir(parents=True)
        self.db.close()
        (self.root / "sd.db").rename(store)
        self.db = connect(store)
        self.addCleanup(self.db.close)

    def sd(self, *args, vault=None):
        return subprocess.run([sys.executable, str(PACK / "bin/sd"), "reports", "brief", *args],
                              env={**os.environ, "HOME": str(self.home), "PYTHONPATH": str(PACK / "lib"),
                                   "OBSIDIAN_VAULT": str(vault or self.vault),
                                   "SD_MIRROR_QUEUE": str(self.root / "queue")},
                              capture_output=True, text=True, check=False, timeout=60)

    def draft(self, text=TEXT):
        path = self.root / f"{DAILY}.md"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_a_hub_add_writes_the_copy_after_its_commit(self):
        filed = self.sd("add", self.draft(), "--belongs-to", str(self.checkout))
        self.assertEqual((filed.returncode, filed.stdout, filed.stderr), (0, f"filed {DAILY}\n", ""))
        self.assertEqual(self.copy(), hashed(TEXT))

    def test_a_failed_render_after_add_keeps_the_row_and_exits_0(self):
        filed = self.sd("add", self.draft(), "--belongs-to", str(self.checkout), vault=self.root / "gone")
        self.assertEqual(filed.returncode, 0, filed.stderr)
        self.assertIn("vault copy not written: ", filed.stderr)
        self.assertEqual(self.db.execute("SELECT count(*) FROM item WHERE source = 'brief'").fetchone()[0], 1)
        self.assertEqual(self.beat()["state"], "failed")

    def test_render_exits_1_on_a_refused_copy_and_0_once_clear(self):
        self.sd("add", self.draft(), "--belongs-to", str(self.checkout))
        (self.folder / f"{DAILY}.md").write_text(hashed(TEXT).replace("Three", "Four"), encoding="utf-8")
        self.sd("add", self.draft(TEXT + "more\n"), "--belongs-to", str(self.checkout), "--extend")
        refused = self.sd("render")
        self.assertEqual(refused.returncode, 1)
        self.assertIn(f"refused {DAILY}: it differs from its mirror-hash", refused.stdout)
        (self.folder / f"{DAILY}.md").unlink()
        clear = self.sd("render")
        self.assertEqual((clear.returncode, clear.stdout), (0, "ok: written 1, refused 0\n"), clear.stderr)
        self.assertEqual(self.sd("render").stdout, "ok: written 0, refused 0\n")

    def test_a_render_queues_the_briefs_their_items_designate(self):
        """sd:5102: `fields.publish` designates a brief; each render queues it, as a render queues a document."""
        self.sd("add", self.draft(), "--belongs-to", str(self.checkout))
        self.channels({"obsidian": {"folder": FOLDER}, "drive": {}})
        self.db.execute("UPDATE item SET fields = json_set(COALESCE(fields, '{}'), '$.publish', json('{\"drive\": {}}')) "
                        "WHERE source = 'brief'")
        self.db.commit()
        rendered = self.sd("render")
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertIn(f"mirror: queued {DAILY} ", rendered.stdout)
        request = self.root / "queue" / f"system.{DAILY}.drive.json"
        self.assertIn("Three things.", request.read_text(encoding="utf-8"))
        self.assertIn(f"mirror: {DAILY}: already queued", self.sd("render").stdout)


if __name__ == "__main__":
    unittest.main()
