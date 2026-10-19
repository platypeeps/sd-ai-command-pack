"""The HTML page of each base: `records.render` and the render after each write (sd:3976, sd:5133).

Rows come from the real vault import over a fixture vault, as the sitting
lands them; the rules come from a fixture `sd plugin list --json` entry with
the driver flipped to `db`, as in `test_records`. Every vault is a temp dir.
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sd_db import connect, records
from sd_db.jobs import cli
from sd_db.migrate import initialise
from sd_db.records import (
    MIRROR_KEY,
    add_row,
    edit_row,
    get_row,
    mirror_state,
    render,
    rules_for,
)
from sd_db.remote import HubOnly
from sd_db.testing.wire import hub_only

from . import support
from .test_records import flipped

IDEAS = "System/Databases/Blog Ideas"

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
class MirrorCase(support.TempRootCase):
    def setUp(self):
        super().setUp()
        root = self.root
        initialise(root / "sd.db")
        self.db = connect(root / "sd.db")
        self.addCleanup(self.db.close)
        self.vault = support.vault(root / "vault", ideas={"first idea": "inbox", "dropped idea": "declined"},
                                   topics={"a topic": "active"})
        (self.vault / IDEAS / "rich idea.md").write_text(RICH, encoding="utf-8")
        self.env = {"OBSIDIAN_VAULT": str(self.vault)}
        support.land_vault(self.db, self.vault)
        self.home = root / "home"

    def render(self, **extra):
        return render(self.db, home=self.home, environ=self.env, entries=[flipped()], **extra)

    def shown(self, title, stage):
        """Whether the blog-idea page's table shows the row at `stage`."""
        return f">{title}</a></td><td>{stage}</td>" in self.page()

    def page(self, kind="blog-idea"):
        return (self.vault / "docs" / "dashboard" / f"base-{kind}.html").read_text(encoding="utf-8")

    def beat(self):
        row = self.db.execute("SELECT body FROM state WHERE kind = 'heartbeat' AND key = ? ORDER BY id DESC LIMIT 1",
                              (MIRROR_KEY,)).fetchone()
        return None if row is None else json.loads(row["body"])

    def move(self, title, stage, kind="blog-idea", **changes):
        row = get_row(self.db, kind=kind, title=title)
        rules = rules_for(kind, home=self.home, environ=self.env, entries=[flipped()])
        with patch("sd_db.records.plugin_entries", return_value=[flipped()]):
            return edit_row(self.db, row["id"], rules, revision=row["revision"], who="operator", stage=stage,
                            **changes)


class TheRefusals(MirrorCase):
    def files(self):
        return sorted(str(path.relative_to(self.vault)) for path in self.vault.rglob("*") if path.is_file())

    def test_a_vault_root_that_is_not_a_directory_refuses_and_creates_nothing(self):
        missing = Path(self.tmp.name) / "not the vault"
        mirror = render(self.db, home=self.home, environ={"OBSIDIAN_VAULT": str(missing)}, entries=[flipped()])
        self.assertIn("is not a directory", str(mirror.reason))
        self.assertFalse(missing.exists())

    def test_a_write_whose_rules_name_no_vault_renders_nowhere(self):
        # support.TempRootCase points $OBSIDIAN_VAULT at a folder that does not exist.
        self.render()
        row = get_row(self.db, kind="blog-idea", title="first idea")
        said = io.StringIO()
        with patch("sd_db.records.plugin_entries", return_value=[flipped()]), contextlib.redirect_stderr(said):
            edit_row(self.db, row["id"], rules_for("blog-idea", home=self.home, entries=[flipped()]),
                     revision=row["revision"], who="operator", stage="accepted")
        self.assertIn("is not a directory", said.getvalue())
        self.assertFalse(Path(os.environ["OBSIDIAN_VAULT"]).exists())

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
        self.assertIn("which was removed", str(mirror.reason))
        self.assertEqual(self.files(), before)

    def test_mirror_state_is_the_last_heartbeat_and_none_before_any_render(self):
        # The dashboard's Health reads it (sd:3977); it issues no SQL of its own.
        self.assertIsNone(mirror_state(self.db))
        self.render()
        stamp, body = mirror_state(self.db) or ("", None)
        self.assertEqual(body, self.beat())
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T")

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
        self.assertTrue(self.shown("first idea", "accepted"))
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
        self.assertTrue(self.shown("first idea", "inbox"))
        self.move("a topic", "parked", kind="topic")
        self.assertTrue(self.shown("first idea", "accepted"))
        self.assertEqual((self.beat()["ok"], sorted(self.beat()["kinds"])), (True, ["blog-idea", "topic"]))

    def test_a_process_stopped_after_the_commit_leaves_a_failed_heartbeat_the_next_write_catches_up(self):
        self.render()
        with patch("sd_db.records._mirror_after"):
            self.move("first idea", "accepted")
        self.assertEqual((self.beat()["ok"], self.beat()["reason"]),
                         (False, "a blog-idea write is committed and not yet rendered"))
        self.move("a topic", "parked", kind="topic")
        self.assertTrue(self.shown("first idea", "accepted"))
        self.assertTrue(self.beat()["ok"])

    def test_a_write_renders_the_vault_its_rules_name_not_the_one_in_the_environment(self):
        self.render()
        elsewhere = support.vault(self.root / "the environment's vault", ideas={"first idea": "inbox"}, topics={})
        before = {path: path.read_bytes() for path in elsewhere.rglob("*") if path.is_file()}
        with patch.dict(os.environ, {"OBSIDIAN_VAULT": str(elsewhere)}):
            self.move("first idea", "accepted")
            self.move("a topic", "parked", kind="topic")
        self.assertEqual({path: path.read_bytes() for path in elsewhere.rglob("*") if path.is_file()}, before)
        self.assertTrue(self.shown("first idea", "accepted"))
        self.assertTrue(self.beat()["ok"], self.beat())

    def test_a_write_from_a_satellite_commits_and_leaves_the_render_to_the_hub(self):
        self.render()
        said = io.StringIO()
        with patch("sd_db.database.served_by", return_value="hub.example.test:8765"), \
                contextlib.redirect_stderr(said):
            moved = self.move("first idea", "accepted")
        self.assertEqual(moved["stage"], "accepted")
        self.assertIn("mirror not updated", said.getvalue())
        self.assertEqual(self.beat()["ok"], False)
        self.assertTrue(self.shown("first idea", "inbox"))


class NoNotes(MirrorCase):
    """pack sd:5133: the vault holds no base notes; only the HTML page is written."""

    def test_a_write_and_a_render_leave_no_note_and_write_the_page(self):
        for note in self.vault.rglob("*.md"):
            note.unlink()
        rules = rules_for("blog-idea", home=self.home, environ=self.env, entries=[flipped()])
        add_row(self.db, rules, title="added idea", who="operator", fields={"score": "7"}, body="# added\n")
        mirror = self.render()
        self.assertEqual(sorted(path.relative_to(self.vault).as_posix() for path in self.vault.rglob("*.md")), [])
        self.assertTrue(mirror.ok, mirror.why() if not mirror.ok else "")
        self.assertIn(">added idea</a></td>", self.page())

    def test_a_vault_with_no_base_folders_still_gets_its_pages(self):
        shutil.rmtree(self.vault / "System")
        mirror = self.render()
        self.assertTrue(mirror.ok, mirror.reason)
        self.assertIn(">first idea</a></td>", self.page())
        self.assertFalse((self.vault / "System").exists())


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

    def test_the_page_obeys_the_documents_policy(self):
        self.render()
        page = self.page()
        for banned in ("<script", "<link", 'src="http', "url(http", "@import"):
            self.assertNotIn(banned, page)
        # A body link to `javascript:` stays a dead link, even opened from disk with no served policy.
        self.assertIn('<meta http-equiv="Content-Security-Policy" content="script-src \'none\'; '
                      'object-src \'none\'">', page)
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

    def test_records_render_exits_zero_then_one_on_a_render_that_stopped(self):
        code, out, err = self.sd_db("render")
        self.assertEqual(code, 0, err)
        self.assertIn("sd-db:   wrote docs/dashboard/base-blog-idea.html", out)
        shutil.rmtree(self.vault)
        code, out, err = self.sd_db("render", "blog-idea")
        self.assertEqual(code, 1)
        self.assertIn("blog-idea: wrote 0 file(s)", out)
        self.assertIn("records render stopped:", err)



class TheVerbsArguments(unittest.TestCase):
    def test_anything_but_render_and_kinds_exits_one_before_the_store_opens(self):
        for argv in ([], ["draw"], ["render", "--all"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()) as said:
                self.assertEqual(cli.main(["records", *argv]), 1)
            self.assertIn("expected render [KIND ...]", said.getvalue())


if __name__ == "__main__":
    unittest.main()


class TheTempRootGuard(unittest.TestCase):
    def test_a_mirror_write_outside_the_temp_root_fails_the_test_and_writes_nothing(self):
        outside = Path(tempfile.gettempdir()) / "sd-db-tests-never-write-here.md"

        class Writes(support.TempRootCase):
            def test_it(self):
                with contextlib.suppress(AssertionError):  # as the render swallows it into a heartbeat
                    records._replace(outside, b"a fixture\n")

        result = unittest.TestResult()
        Writes("test_it").run(result)
        self.assertEqual((result.wasSuccessful(), outside.exists()), (False, False))
        self.assertIn("a mirror write left the test's temp root", "".join(trace for _, trace in result.errors + result.failures))
