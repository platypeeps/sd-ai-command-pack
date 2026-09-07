"""Criterion 29: a killed session restarts from the followups it had named.

The criterion's own test is `TheCriterion` below: three followups written
through the library, a session that ends without calling `sd-handoff`, a new
session, and all three in the injected context. The rest of the file is what
that one assertion rests on -- which rows are read, which are not, and what
happens when the database is not there at all.

`bin/sd-handoff-restore` is a hook, so every failure here has to be silent.
That makes the negative tests the load-bearing ones: a hook that raised on a
missing library would break every session start on a machine that has not run
`make setup`, and nothing in the criterion would catch it.
"""

import ast
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load(name: str, filename: str | None = None):
    """Import a `bin/` module by path -- `bin/` is not a package.

    The loader is named explicitly because two of the three modules here have
    no `.py` suffix, and `spec_from_file_location` infers no loader for those.
    """
    path = str(REPO_ROOT / "bin" / (filename or f"{name}.py"))
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sd_lib = load("sd_lib")
sd_handoff_rows = load("sd_handoff_rows")
restore = load("sd_handoff_restore", "sd-handoff-restore")

import sd_db  # noqa: E402 - after the path juggling above


class RowCase(unittest.TestCase):
    """A scratch home with a real database, and a real git checkout beside it."""

    def setUp(self):
        self._scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self._scratch.cleanup)
        self.home = Path(self._scratch.name).resolve()
        sd_db.initialise(home=self.home)
        self.connection = sd_db.connect(sd_db.default_path(self.home), write=True)
        self.addCleanup(self.connection.close)

        self.root = self.home / "checkout"
        item_dir = self.root / sd_lib.WORK_DIR / "an-item"
        item_dir.mkdir(parents=True)
        # git records no empty directory, and a checkout with no commit has no
        # HEAD for `main_worktree_root` to resolve against.
        (item_dir / "prd.md").write_text("# an item\n", encoding="utf-8")
        for args in (["init", "-q"], ["config", "user.email", "t@example.com"],
                     ["config", "user.name", "T"], ["add", "-A"],
                     ["commit", "-qm", "first"]):
            subprocess.run(["git", "-C", str(self.root), *args], check=True,
                           capture_output=True)
        self.root = self.root.resolve()
        sd_db.writes.upsert_repo(self.connection, str(self.root))

    def item(self, name: str = "an-item", status: str = "in_progress") -> int:
        """One work item, keyed the way `sd_lib` keys it."""
        item_dir = self.root / sd_lib.WORK_DIR / name
        item_dir.mkdir(parents=True, exist_ok=True)
        return sd_db.writes.create_item(
            self.connection,
            kind="work",
            title=name,
            status=status,
            repo=str(self.root),
            source=sd_lib.ITEM_ROW_SOURCE,
            external_id=sd_lib.external_id(self.root, item_dir),
        )

    def followup(self, item: int, body: str) -> int:
        return sd_db.add_note(self.connection, item, "followup", body)

    def read(self) -> list[str]:
        return sd_handoff_rows.render(
            sd_handoff_rows.open_followups(self.connection, str(self.root)))


class TheCriterion(RowCase):
    """Three followups, a session that dies, and all three back."""

    def test_three_followups_survive_a_session_that_wrote_no_packet(self):
        item = self.item()
        named = ["rebase onto main", "answer the review on sd-note", "delete the pyc"]
        for body in named:
            self.followup(item, body)

        # The session ends. Nothing calls `sd-handoff`, so no packet is
        # written -- which is the whole point: the rows are all there is.
        packet = restore.packet_path(str(self.root), {"HOME": str(self.home)})
        self.assertFalse(packet.is_file())

        lines = self.read()
        for body in named:
            self.assertTrue(any(body in line for line in lines),
                            f"{body!r} is not in {lines}")

    def test_the_order_is_the_order_they_were_named_in(self):
        item = self.item()
        for body in ("first", "second", "third"):
            self.followup(item, body)
        bullets = [line for line in self.read() if line.startswith("- [")]
        self.assertEqual([line.split("] ", 1)[1] for line in bullets],
                         ["first", "second", "third"])


class WhatIsNotHandedOver(RowCase):
    def test_a_resolved_followup_is_gone(self):
        item = self.item()
        note = self.followup(item, "already done")
        self.followup(item, "still open")
        sd_db.resolve_note(self.connection, note)
        self.assertNotIn("already done", "\n".join(self.read()))
        self.assertIn("still open", "\n".join(self.read()))

    def test_a_followup_on_a_finished_item_is_gone(self):
        item = self.item(name="finished", status="done")
        self.followup(item, "left open on a done item")
        self.assertEqual(self.read(), [])

    def test_another_checkouts_followups_are_not_handed_over(self):
        item = self.item()
        self.followup(item, "mine")
        other = self.home / "elsewhere"
        other.mkdir()
        sd_db.writes.upsert_repo(self.connection, str(other))
        theirs = sd_db.writes.create_item(
            self.connection, kind="work", title="theirs", status="in_progress",
            repo=str(other), source=sd_lib.ITEM_ROW_SOURCE,
            external_id=f"{other}::x/prd.md")
        self.followup(theirs, "not mine")
        joined = "\n".join(self.read())
        self.assertIn("mine", joined)
        self.assertNotIn("not mine", joined)

    def test_a_note_of_another_kind_is_not_a_followup(self):
        item = self.item()
        sd_db.add_note(self.connection, item, "decision", "we chose sqlite")
        self.assertEqual(self.read(), [])

    def test_no_followups_renders_nothing_at_all(self):
        self.item()
        self.assertEqual(self.read(), [])


class TheRenderedShape(RowCase):
    def test_two_items_are_grouped_under_their_titles(self):
        first = self.item(name="alpha")
        second = self.item(name="beta")
        self.followup(first, "a thing")
        self.followup(second, "another thing")
        lines = self.read()
        self.assertIn("alpha:", lines)
        self.assertIn("beta:", lines)

    def test_every_bullet_carries_the_id_that_resolves_it(self):
        item = self.item()
        note = self.followup(item, "close me")
        self.assertIn(f"- [{note}] close me", self.read())


class TheHookStaysSilent(unittest.TestCase):
    """Every way the read can fail, and the silence each one owes."""

    def test_a_missing_library_returns_no_lines_and_does_not_raise(self):
        original = sd_handoff_rows.library

        def refuse():
            raise sd_handoff_rows.RowsRefusal(sd_handoff_rows.NOT_INSTALLED)

        sd_handoff_rows.library = refuse
        self.addCleanup(setattr, sd_handoff_rows, "library", original)
        self.assertEqual(restore.followup_lines("/nowhere"), [])

    def test_an_unopenable_database_returns_no_lines(self):
        original = sd_handoff_rows.followups_for

        def explode(root):
            raise OSError("disk is gone")

        sd_handoff_rows.followups_for = explode
        self.addCleanup(setattr, sd_handoff_rows, "followups_for", original)
        self.assertEqual(restore.followup_lines("/nowhere"), [])

    def test_the_reader_never_writes(self):
        """A read that claimed would hand the second session nothing.

        The packet is claimed by rename because it describes one moment. Rows
        are not: they stay open until the work is done. Asserted on the source
        because there is no other way to prove a negative about every path.
        """
        tree = ast.parse((REPO_ROOT / "bin" / "sd_handoff_rows.py").read_text("utf-8"))
        for node in ast.walk(tree):
            # Docstrings say "add_note" and must keep saying it; what may not
            # appear is a call to one or a write in a SQL literal.
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                self.assertNotIn(name, ("add_note", "resolve_note", "record_state"),
                                 f"{name} is called by a module that must only read")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for verb in ("INSERT ", "UPDATE ", "DELETE "):
                    self.assertNotIn(verb, node.value.upper(),
                                     f"{verb.strip()} appears in a SQL literal here")


class TheDeltaToTheRestoreHook(RowCase):
    """The hook's own path, not the reader's."""

    def setUp(self):
        super().setUp()
        # `sd_db.default_path` reads `$HOME` from the process at call time, and
        # the reader is called by the hook rather than handed the environment
        # dict `run` gets. Both have to point at the scratch home or the hook
        # opens the operator's real database.
        was = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self.addCleanup(os.environ.__setitem__, "HOME", was or "")

    def env(self) -> dict:
        return {"HOME": str(self.home), "PWD": str(self.root)}

    def test_rows_are_injected_when_there_is_no_packet(self):
        item = self.item()
        self.followup(item, "survive the kill")
        out = io.StringIO()
        payload = json.dumps({"cwd": str(self.root)})
        self.assertEqual(restore.run(payload, self.env(), out), 0)
        self.assertIn("survive the kill", out.getvalue())

    def test_nothing_is_emitted_when_there_is_neither_packet_nor_row(self):
        self.item()
        out = io.StringIO()
        payload = json.dumps({"cwd": str(self.root)})
        self.assertEqual(restore.run(payload, self.env(), out), 0)
        self.assertEqual(out.getvalue(), "")

    def test_the_opt_out_silences_the_rows_too(self):
        item = self.item()
        self.followup(item, "should not appear")
        out = io.StringIO()
        environ = {**self.env(), "SD_HANDOFF_RESTORE": "0"}
        self.assertEqual(restore.run(json.dumps({"cwd": str(self.root)}), environ, out), 0)
        self.assertEqual(out.getvalue(), "")

    def test_a_bad_packet_does_not_take_the_rows_with_it(self):
        """The bug the split into `packet_section` was written to stop.

        Every packet refusal used to return straight out of `run`, so a packet
        written for a different project silently dropped followups that had
        nothing to do with it.
        """
        item = self.item()
        self.followup(item, "unrelated to any packet")
        path = restore.packet_path(str(self.root), self.env())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "created": "2026-09-07T00:00:00+00:00",
            "repo": {"root": "/no/such/directory", "head_sha": "", "remote": None},
        }), encoding="utf-8")
        out = io.StringIO()
        self.assertEqual(restore.run(json.dumps({"cwd": str(self.root)}), self.env(), out), 0)
        self.assertIn("no longer exists", out.getvalue())
        self.assertIn("unrelated to any packet", out.getvalue())


class TheWriter(RowCase):
    """`bin/sd-note`, end to end, through its own `main`."""

    def note(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        environ = dict(os.environ)
        os.environ["HOME"] = str(self.home)
        self.addCleanup(os.environ.update, {"HOME": environ.get("HOME", "")})
        module = load("sd_note", "sd-note")
        code = module.main(argv, out, err, cwd=str(self.root))
        return code, out.getvalue(), err.getvalue()

    def test_a_written_followup_comes_back_from_the_reader(self):
        self.item()
        code, out, err = self.note(["add", "wire the hook", "--item", "an-item"])
        self.assertEqual(code, 0, err)
        self.assertIn("followup [", out)
        self.assertIn("wire the hook", "\n".join(self.read()))

    def test_an_unknown_item_directory_refuses_and_writes_nothing(self):
        code, _, err = self.note(["add", "x", "--item", "no-such-item"])
        self.assertEqual(code, 1)
        self.assertIn("no work item at", err)
        self.assertEqual(self.read(), [])

    def test_an_item_with_no_row_refuses_and_names_the_remedy(self):
        (self.root / sd_lib.WORK_DIR / "rowless").mkdir(parents=True)
        code, _, err = self.note(["add", "x", "--item", "rowless"])
        self.assertEqual(code, 1)
        self.assertIn("sd-status", err)

    def test_resolve_closes_the_followup_the_write_printed(self):
        self.item()
        _, out, _ = self.note(["add", "close me", "--item", "an-item"])
        note = int(out.split("[", 1)[1].split("]", 1)[0])
        code, _, err = self.note(["resolve", str(note)])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read(), [])


if __name__ == "__main__":
    unittest.main()
