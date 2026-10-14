"""The vault mirror of base rows: `records.render` and the render after each write (sd:3976).

Rows come from the real vault import over a fixture vault, as the sitting
lands them; the rules come from a fixture `sd plugin list --json` entry with
the driver flipped to `db`, as in `test_records`. Every vault is a temp dir.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sd_db import connect, record_state
from sd_db.jobs import cli
from sd_db.migrate import initialise
from sd_db.records import MIRROR_KEY, add_row, edit_row, get_row, render, rules_for
from sd_db.remote import HubOnly
from sd_db.sources import run, verify
from sd_db.sources.vault import Reader
from sd_db.testing.wire import hub_only

from . import support
from .test_records import flipped

IDEAS = "System/Databases/Blog Ideas"
TOPICS = "System/Databases/Topics"

STATUS_CONTROL = "**Status:** `INPUT[inlineSelect(option(inbox), option(accepted), option(declined)):status]`"
RATING_CONTROL = "**My rating:** `INPUT[inlineSelect(option(1), option(2), option(3)):my-rating]`"

#: A note body with every shape the HTML mirror redraws, and one code fence it must leave alone.
RICH = f"""---
contexts:
  - Personal
content-type: blog-idea
status: inbox
my-rating: 7
dateCreated: 2026-06-15
description: "a rich idea"
tags:
  - blog-idea
---

# rich idea

{STATUS_CONTROL}
{RATING_CONTROL}

Seen in [[2026-10-07 - Daily Intel Brief]] and [[Agents|the agents note]].

![chart](https://example.test/chart.png)

```
[[not a link inside code]]
```
"""


@hub_only
class MirrorCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        initialise(root / "sd.db")
        self.db = connect(root / "sd.db")
        self.addCleanup(self.db.close)
        self.vault = support.vault(root / "vault", ideas={"first idea": "inbox", "dropped idea": "declined"},
                                   topics={"a topic": "active"})
        (self.vault / IDEAS / "rich idea.md").write_text(RICH, encoding="utf-8")
        self.env = {"OBSIDIAN_VAULT": str(self.vault)}
        sitting = run(self.db, Reader.from_plugins([support.plugin_entry()], environ=self.env))
        self.assertTrue(sitting.clean)
        self.home = root / "home"

    def render(self, **extra):
        return render(self.db, home=self.home, environ=self.env, entries=[flipped()], **extra)

    def note(self, title, base=IDEAS):
        return (self.vault / base / f"{title}.md").read_text(encoding="utf-8")

    def page(self, kind="blog-idea"):
        return (self.vault / "docs" / "dashboard" / f"base-{kind}.html").read_text(encoding="utf-8")

    def beat(self):
        row = self.db.execute("SELECT body FROM state WHERE kind = 'heartbeat' AND key = ? ORDER BY id DESC LIMIT 1",
                              (MIRROR_KEY,)).fetchone()
        return None if row is None else json.loads(row["body"])

    def move(self, title, stage, kind="blog-idea", **changes):
        row = get_row(self.db, kind=kind, title=title)
        rules = rules_for(kind, home=self.home, entries=[flipped()])
        with patch.dict(os.environ, self.env), patch("sd_db.records.plugin_entries", return_value=[flipped()]):
            return edit_row(self.db, row["id"], rules, revision=row["revision"], who="operator", stage=stage,
                            **changes)


class TheMarkdownMirror(MirrorCase):
    def test_the_first_render_takes_over_imported_notes_and_a_second_writes_nothing(self):
        mirror = self.render()
        self.assertTrue(mirror.ok, mirror.refused)
        self.assertEqual(sorted(mirror.kinds), ["blog-idea", "topic"])
        self.assertIn(f"{IDEAS}/first idea.md", mirror.written)
        self.assertIn("docs/dashboard/base-topic.html", mirror.written)
        self.assertRegex(self.note("first idea"), r"\nmirror-hash: [0-9a-f]{64}\n---\n")
        self.assertEqual(self.beat()["ok"], True)
        again = self.render()
        self.assertEqual((again.ok, again.written), (True, []))

    def test_the_body_stays_verbatim_and_status_comes_from_the_stage(self):
        self.render()
        self.move("rich idea", "accepted")
        text = self.note("rich idea")
        self.assertIn("\nstatus: accepted\n", text)
        self.assertTrue(text.endswith(RICH.split("---\n", 2)[2]), text)

    def test_render_then_freeze_round_trips_every_kind(self):
        self.render()
        self.move("first idea", "accepted", fields={"description": "  padded: and \"quoted\"  ", "my-rating": None})
        self.move("a topic", "parked", kind="topic", body="new body\n\nwith  spaces \n")
        self.assertTrue(self.render().ok)
        reader = Reader.from_plugins([support.plugin_entry()], environ=self.env)
        self.assertEqual(verify(self.db, reader, reader.freeze()), [])

    def test_an_added_row_carries_its_date_so_its_note_reads_back(self):
        self.render()
        rules = rules_for("blog-idea", home=self.home, entries=[flipped()])
        with patch.dict(os.environ, self.env):
            add_row(self.db, rules, title="added idea", who="operator", fields={"score": "7"}, body="# added\n")
        self.assertTrue(self.beat()["ok"], self.beat())
        reader = Reader.from_plugins([support.plugin_entry()], environ=self.env)
        self.assertEqual(verify(self.db, reader, reader.freeze()), [])

    def test_a_row_whose_created_date_its_fields_do_not_give_is_refused(self):
        self.render()
        before = self.note("first idea")
        with contextlib.redirect_stderr(io.StringIO()):
            self.move("first idea", None, fields={"dateCreated": None})
        mirror = self.render()
        self.assertEqual([path for path, _ in mirror.refused], [f"{IDEAS}/first idea.md"])
        self.assertIn("title, created date or due date", mirror.refused[0][1])
        self.assertEqual(self.note("first idea"), before)

    def test_a_row_that_would_not_read_back_is_refused_and_its_file_kept(self):
        self.render()
        before = self.note("first idea")
        with contextlib.redirect_stderr(io.StringIO()):
            self.move("first idea", None, fields={"tags": []})
        mirror = self.render()
        self.assertEqual([path for path, _ in mirror.refused], [f"{IDEAS}/first idea.md"])
        self.assertIn("would not read back", mirror.refused[0][1])
        self.assertEqual(self.note("first idea"), before)


class TheOverwriteRule(MirrorCase):
    def test_a_changed_note_with_no_mirror_hash_is_refused_and_kept(self):
        path = self.vault / IDEAS / "first idea.md"
        edited = path.read_text(encoding="utf-8").replace("status: inbox", "status: accepted")
        path.write_text(edited, encoding="utf-8")
        mirror = self.render()
        self.assertEqual([path for path, _ in mirror.refused], [f"{IDEAS}/first idea.md"])
        self.assertIn("no mirror-hash", mirror.refused[0][1])
        self.assertEqual(self.note("first idea"), edited)
        self.assertIn(f"{IDEAS}/rich idea.md", mirror.written)
        self.assertEqual((mirror.ok, self.beat()["ok"], self.beat()["refused"][0]["path"]),
                         (False, False, f"{IDEAS}/first idea.md"))

    def test_a_hand_edit_to_a_mirror_file_is_refused_and_kept(self):
        self.render()
        path = self.vault / IDEAS / "first idea.md"
        edited = path.read_text(encoding="utf-8").replace("the blog-idea body", "a phone edit of the body")
        path.write_text(edited, encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            self.move("first idea", "accepted")
        mirror = self.render()
        self.assertEqual([path for path, _ in mirror.refused], [f"{IDEAS}/first idea.md"])
        self.assertIn("differs from its mirror-hash", mirror.refused[0][1])
        self.assertEqual(self.note("first idea"), edited)

    def test_an_edit_that_lands_while_the_render_runs_is_kept(self):
        self.render()
        path = self.vault / IDEAS / "first idea.md"
        real = os.chmod

        def phone_edit(target, mode):
            real(target, mode)
            if Path(target).name.startswith(".first idea.md."):
                path.write_text("a phone edit\n", encoding="utf-8")

        # A row change the next render writes out, with no render of its own.
        row = get_row(self.db, kind="blog-idea", title="first idea")
        self.db.execute("UPDATE item SET stage = 'declined' WHERE id = ?", (row["id"],))
        with patch("sd_db.records.os.chmod", side_effect=phone_edit):
            mirror = self.render()
        self.assertEqual(mirror.refused, [(f"{IDEAS}/first idea.md",
                                           "it changed while the render ran: a hand edit, kept")])
        self.assertEqual(path.read_text(encoding="utf-8"), "a phone edit\n")
        self.assertEqual([found.name for found in self.vault.rglob(".*.tmp")], [])

    def test_a_file_with_no_row_is_reported_and_kept(self):
        stray = self.vault / IDEAS / "nested" / "Stray.md"
        stray.parent.mkdir()
        stray.write_text("---\nstatus: inbox\n---\nwritten by a satellite\n", encoding="utf-8")
        mirror = self.render()
        self.assertEqual(mirror.refused, [(f"{IDEAS}/nested/Stray.md",
                                           "no row holds this file; kept: add it as a row or delete it")])
        self.assertEqual(stray.read_text(encoding="utf-8"), "---\nstatus: inbox\n---\nwritten by a satellite\n")


class TheRefusals(MirrorCase):
    def files(self):
        return sorted(str(path.relative_to(self.vault)) for path in self.vault.rglob("*") if path.is_file())

    def test_a_row_path_outside_its_base_is_refused_and_nothing_written_there(self):
        self.render()
        row = get_row(self.db, kind="blog-idea", title="first idea")
        self.db.execute("UPDATE item SET path = ? WHERE id = ?", (f"{IDEAS}/../../escaped.md", row["id"]))
        self.db.commit()
        mirror = self.render()
        self.assertIn("is not a note under", dict(mirror.refused)[f"{IDEAS}/../../escaped.md"])
        self.assertFalse((self.vault / "escaped.md").exists())

    def test_an_open_restore_refuses_before_any_file(self):
        before = self.files()
        record_state(self.db, "restore", key="2026-10-13")
        mirror = self.render()
        self.assertIn("restore", str(mirror.reason))
        self.assertEqual((mirror.written, self.files(), self.beat()["ok"]), ([], before, False))

    def test_a_vault_root_with_no_base_folder_refuses_and_creates_nothing(self):
        missing = Path(self.tmp.name) / "not the vault"
        mirror = render(self.db, home=self.home, environ={"OBSIDIAN_VAULT": str(missing)}, entries=[flipped()])
        self.assertIn("is not a directory", str(mirror.reason))
        self.assertFalse(missing.exists())

    def test_a_write_in_a_suite_that_names_no_vault_renders_nowhere(self):
        # tests/sd_db/__init__.py points $OBSIDIAN_VAULT at a folder that does not exist.
        self.render()
        row = get_row(self.db, kind="blog-idea", title="first idea")
        said = io.StringIO()
        with patch("sd_db.records.plugin_entries", return_value=[flipped()]), contextlib.redirect_stderr(said):
            edit_row(self.db, row["id"], rules_for("blog-idea", home=self.home, entries=[flipped()]),
                     revision=row["revision"], who="operator", stage="accepted")
        self.assertIn("is not a directory", said.getvalue())
        self.assertFalse(Path(os.environ["OBSIDIAN_VAULT"]).exists())
        self.assertIn("\nstatus: inbox\n", self.note("first idea"))

    def test_an_unreadable_plugin_is_an_unknown_not_an_empty_render(self):
        broken = {"root": "/plugins/other", "readable": False, "why": "no manifest"}
        # Only the unreadable plugin could hold a `db` kind, so no kind's rules are ever asked for.
        mirror = render(self.db, home=self.home, environ=self.env, entries=[support.plugin_entry(), broken])
        self.assertIn("cannot be read", str(mirror.reason))
        self.assertEqual((mirror.ok, self.beat()["ok"]), (False, False))

    def test_a_kind_whose_plugin_is_still_on_the_vault_driver_refuses(self):
        entry = flipped()
        entry["store"]["driver"] = "vault"
        before = self.files()
        self.assertEqual(render(self.db, home=self.home, environ=self.env, entries=[entry]).kinds, [])
        mirror = render(self.db, home=self.home, environ=self.env, entries=[entry], kinds=["topic"])
        self.assertIn("still the source", str(mirror.reason))
        self.assertEqual(self.files(), before)

    def test_a_satellite_refuses_by_name_and_writes_nothing(self):
        before = self.files()
        with patch("sd_db.database.served_by", return_value="hub.example.test:8765"), \
                self.assertRaisesRegex(HubOnly, "records render"):
            self.render()
        self.assertEqual((self.files(), self.beat()), (before, None))

    def test_a_write_error_after_one_file_leaves_whole_files_and_a_rerun_finishes(self):
        real, calls = os.replace, []

        def fail_second(source, target):
            calls.append(target)
            if len(calls) == 2:
                raise PermissionError("Documents access denied")
            real(source, target)

        with patch("sd_db.records.os.replace", side_effect=fail_second):
            mirror = self.render()
        self.assertIn("Documents access denied", str(mirror.reason))
        self.assertEqual((len(mirror.written), self.beat()["ok"]), (1, False))
        self.assertEqual([path.name for path in self.vault.rglob(".*.tmp")], [])
        again = self.render()
        self.assertTrue(again.ok, again.reason)
        self.assertNotIn(mirror.written[0], again.written)
        self.assertEqual(self.render().written, [])


class TheRenderAfterAWrite(MirrorCase):
    def test_a_write_renders_its_kind(self):
        self.render()
        self.move("first idea", "accepted")
        self.assertIn("\nstatus: accepted\n", self.note("first idea"))
        self.assertTrue(self.beat()["ok"])
        self.assertEqual(self.beat()["kinds"], ["blog-idea"])

    def test_a_failed_render_leaves_the_row_and_a_failed_heartbeat_and_the_next_write_catches_up(self):
        self.render()
        said = io.StringIO()
        with patch("sd_db.records._render", side_effect=OSError("disk full")), contextlib.redirect_stderr(said):
            moved = self.move("first idea", "accepted")
        self.assertEqual(moved["stage"], "accepted")
        self.assertIn("mirror not updated: disk full", said.getvalue())
        self.assertEqual((self.beat()["ok"], self.beat()["reason"]), (False, "disk full"))
        self.assertIn("\nstatus: inbox\n", self.note("first idea"))
        self.move("a topic", "parked", kind="topic")
        self.assertIn("\nstatus: accepted\n", self.note("first idea"))
        self.assertEqual((self.beat()["ok"], sorted(self.beat()["kinds"])), (True, ["blog-idea", "topic"]))

    def test_a_process_stopped_after_the_commit_leaves_a_failed_heartbeat_the_next_write_catches_up(self):
        self.render()
        with patch("sd_db.records._mirror_after"):
            self.move("first idea", "accepted")
        self.assertEqual((self.beat()["ok"], self.beat()["reason"]),
                         (False, "a blog-idea write is committed and not yet rendered"))
        self.move("a topic", "parked", kind="topic")
        self.assertIn("\nstatus: accepted\n", self.note("first idea"))
        self.assertTrue(self.beat()["ok"])

    def test_a_write_from_a_satellite_commits_and_leaves_the_render_to_the_hub(self):
        self.render()
        said = io.StringIO()
        with patch("sd_db.database.served_by", return_value="hub.example.test:8765"), \
                contextlib.redirect_stderr(said):
            moved = self.move("first idea", "accepted")
        self.assertEqual(moved["stage"], "accepted")
        self.assertIn("mirror not updated", said.getvalue())
        self.assertEqual(self.beat()["ok"], False)
        self.assertIn("\nstatus: inbox\n", self.note("first idea"))


class TheHtmlMirror(MirrorCase):
    def test_one_page_per_base_with_every_row_in_the_table_and_open_rows_as_sections(self):
        self.render()
        page = self.page()
        for title in ("first idea", "rich idea", "dropped idea"):
            self.assertIn(f"<td>{title}</td>" if title == "dropped idea" else f">{title}</a></td>", page)
        self.assertEqual(page.count('<section class="row"'), 2)

    def test_controls_are_hidden_or_drawn_as_text_and_links_render_as_text(self):
        self.render()
        section = self.page().split(">rich idea</h2>", 1)[1]
        self.assertNotIn("INPUT[", section)
        self.assertNotIn("Status:", section)
        self.assertIn("<strong>My rating:</strong> 7", section)
        self.assertIn("Seen in 2026-10-07 - Daily Intel Brief and the agents note.", section)
        self.assertIn('<a href="https://example.test/chart.png">chart</a>', section)
        self.assertIn("[[not a link inside code]]", section)
        self.assertIn(STATUS_CONTROL, self.note("rich idea"))

    def test_the_page_obeys_the_documents_policy(self):
        self.render()
        page = self.page()
        for banned in ("<script", "<link", 'src="http', "url(http", "@import"):
            self.assertNotIn(banned, page)
        self.assertIn("<style>", page)
        self.assertIn("--color-paper", page)

    def test_an_unclosed_fence_renders_as_preformatted_text(self):
        self.render()
        self.move("first idea", None, body="# first idea\n\n```\nnever closed <b>\n")
        self.assertIn("<pre>", self.page().split(">first idea</h2>", 1)[1])
        self.assertIn("never closed &lt;b&gt;", self.page())


class TheVerb(MirrorCase):
    def sd_db(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        database = self.home / ".local/share/sd/sd.db"
        database.parent.mkdir(parents=True, exist_ok=True)
        if not database.exists():
            database.symlink_to(Path(self.tmp.name) / "sd.db")
        with patch.dict(os.environ, {**self.env, "HOME": str(self.home)}), \
                patch("sd_db.records.plugin_entries", return_value=[flipped()]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["records", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_records_render_exits_zero_then_one_on_a_refusal(self):
        code, out, err = self.sd_db("render")
        self.assertEqual(code, 0, err)
        self.assertIn("refused 0", out)
        (self.vault / IDEAS / "stray.md").write_text("---\nstatus: inbox\n---\n", encoding="utf-8")
        code, out, err = self.sd_db("render", "blog-idea")
        self.assertEqual(code, 1)
        self.assertIn("blog-idea: wrote 0 file(s), refused 1", out)
        self.assertIn(f"refused {IDEAS}/stray.md", err)



class TheVerbsArguments(unittest.TestCase):
    def test_anything_but_render_and_kinds_exits_one_before_the_store_opens(self):
        for argv in ([], ["draw"], ["render", "--all"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()) as said:
                self.assertEqual(cli.main(["records", *argv]), 1)
            self.assertIn("expected render [KIND ...]", said.getvalue())


if __name__ == "__main__":
    unittest.main()
