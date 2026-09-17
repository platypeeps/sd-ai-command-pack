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
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
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

    A module already in `sys.modules` from that same file is handed back
    rather than executed again. Without the check this replaced
    `sys.modules["sd_lib"]` with a second module object on import, and every
    module that had already imported `sd_lib` the ordinary way was left
    holding functions equal to the live ones and identical to none of them.
    `unittest discover` imports this file and `test_sd_lib.py` into one
    process, which is how
    `SharedParserTests.test_docs_lint_imports_the_shared_parser` came to fail
    there while passing when its module was run alone.
    """
    path = str(REPO_ROOT / "bin" / (filename or f"{name}.py"))
    already = sys.modules.get(name)
    if already is not None and getattr(already, "__file__", None) == path:
        return already
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
        # `sd_db.default_path` reads `$HOME` from the process at call time, and
        # the reader opens its own connection rather than taking this one.
        # Both have to point at the scratch home or the read opens the
        # operator's real database.
        was = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self.addCleanup(os.environ.__setitem__, "HOME", was or "")

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
        """What the restore hook injects for this checkout: `note_brief`'s lines."""
        return sd_handoff_rows.brief_for(self.root)


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

    def test_the_last_one_named_comes_first(self):
        """Newest first, `sd_db.brief_notes`'s order and requirement 7's.

        The pack's own reader handed them back oldest first. The brief is read
        from the top by a session with eight kilobytes, so what was named last,
        nearest to where the dead session stopped, leads.
        """
        item = self.item()
        for body in ("first", "second", "third"):
            self.followup(item, body)
        bullets = [line for line in self.read() if line.startswith("- [")]
        self.assertEqual([line.split("] ", 1)[1] for line in bullets],
                         ["third", "second", "first"])


class WhatIsNotHandedOver(RowCase):
    def test_parked_followups_wait_until_the_piece_is_revived(self):
        from sd_db import writing

        path = self.root / "content/2026/paused/index.md"
        path.parent.mkdir(parents=True)
        path.write_text("---\ntitle: Paused piece\nstatus: drafting\n---\n## Draft\nText.\n")
        state = writing.import_piece(self.connection, str(self.root), "2026/paused", who="import")
        item = state["item"]["id"]
        self.followup(item, "resume the research")
        self.assertIn("resume the research", "\n".join(self.read()))
        writing.park_piece(self.connection, item, who="user")
        self.assertEqual(self.read(), [])
        writing.park_piece(self.connection, item, parked=False, who="user")
        self.assertIn("resume the research", "\n".join(self.read()))

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
    def test_two_items_each_name_their_item_on_the_line(self):
        first = self.item(name="alpha")
        second = self.item(name="beta")
        self.followup(first, "a thing")
        self.followup(second, "another thing")
        joined = "\n".join(self.read())
        self.assertIn(f"(alpha, sd:{first}) a thing", joined)
        self.assertIn(f"(beta, sd:{second}) another thing", joined)

    def test_every_bullet_carries_the_id_that_resolves_it(self):
        item = self.item()
        note = self.followup(item, "close me")
        bullets = [line for line in self.read() if line.startswith("- [")]
        self.assertEqual(len(bullets), 1, bullets)
        self.assertTrue(bullets[0].startswith(f"- [followup #{note} "), bullets)
        self.assertTrue(bullets[0].endswith("] close me"), bullets)


class TheBriefIsTheLibrarys(RowCase):
    """sd:234 PR 10: the hook injects `sd_db.note_brief`'s text and nothing else.

    `bin/sd_handoff_rows.py` used to query and render the same rows itself,
    which is the second reader the brief was written to retire. Each test here
    fails against a hook that renders its own.
    """

    def injected(self, cwd: Path | None = None) -> str:
        out = io.StringIO()
        payload = json.dumps({"cwd": str(cwd or self.root)})
        self.assertEqual(restore.run(payload, {"HOME": str(self.home)}, out), 0)
        if not out.getvalue():
            return ""
        return json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]

    def test_the_hook_injects_the_brief_verbatim(self):
        item = self.item()
        self.followup(item, "rebase onto main")
        sd_db.add_note(self.connection, item, "question", "which tag?\nthe pin or HEAD")
        sd_db.add_note(self.connection, item, "decision", "we chose sqlite")
        self.followup(item, "answer the review")
        brief = sd_db.note_brief(self.connection, str(self.root), branch="")
        self.assertEqual(brief.shown, 3)
        self.assertEqual(self.injected(), brief.text.rstrip("\n"))

    def test_a_question_is_handed_over_as_well(self):
        """The one difference in what is handed over, and the library's call.

        The pack's reader read `followup` alone; requirement 7's brief is open
        `followup` and `question` notes, so an open question now reaches the
        next session too.
        """
        item = self.item()
        note = sd_db.add_note(self.connection, item, "question", "which tag?")
        self.assertIn(f"#{note} ", self.injected())

    def test_the_cut_names_the_list_verb(self):
        """Past the bound the trailer names `sd note list <item>`, which is
        why `bin/sd-note` grew `list` in the same change."""
        item = self.item()
        for index in range(12):
            self.followup(item, f"{index:02d} " + "x" * 900)
        context = self.injected()
        self.assertLessEqual(len((context + "\n").encode("utf-8")), 8 * 1024)
        self.assertIn(f"`sd note list {item}`", context)

    def test_the_command_the_trailer_names_runs(self):
        """The trailer is an instruction, so it has to be one `bin/sd` obeys.

        Asserting the string alone passed while `sd note list` was an
        argparse "invalid choice": every session past the bound was told to
        run a command that did not exist.
        """
        item = self.item()
        for index in range(12):
            self.followup(item, f"{index:02d} " + "x" * 900)
        command = self.injected().rsplit("`sd note list ", 1)[1].split("`", 1)[0]
        code, out, err = run_sd(["note", "list", command])
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.startswith(f"sd:{item} an-item (in_progress): 13 notes"), out)

    def test_a_body_with_other_line_breaks_is_injected_verbatim(self):
        """`\\r`, form feed and U+2028 are not line ends to the brief.

        `str.splitlines` splits on all of them and the hook joins on `\\n`,
        so a body carrying one reached the session changed.
        """
        item = self.item()
        self.followup(item, "a \r b \x0c c   d \x85 e")
        brief = sd_db.note_brief(self.connection, str(self.root), branch="")
        self.assertEqual(self.injected(), brief.text.rstrip("\n"))

    def test_a_detached_linked_worktree_is_briefed_repository_wide(self):
        """A detached HEAD reaches `note_brief` as `""`, never as None.

        None tells the library to read the branch itself, at the main root,
        and the main root here is on a branch that has an item -- so the
        detached session would be briefed on another checkout's work alone.
        """
        branch = subprocess.run(["git", "-C", str(self.root), "branch", "--show-current"],
                                check=True, capture_output=True, text=True).stdout.strip()
        on_main = sd_db.writes.create_item(
            self.connection, kind="work", title="main-roots-branch", status="in_progress",
            repo=str(self.root), branch=branch, source=sd_lib.ITEM_ROW_SOURCE,
            external_id=f"{self.root}::{branch}/prd.md")
        other = self.item(name="unbranched")
        self.followup(on_main, "the main root's work")
        self.followup(other, "the repository's other work")
        linked = self.home / "detached"
        subprocess.run(["git", "-C", str(self.root), "worktree", "add", "-q", "--detach",
                        str(linked)], check=True, capture_output=True)
        context = self.injected(linked.resolve())
        self.assertIn("the main root's work", context)
        self.assertIn("the repository's other work", context)
        self.assertNotIn(f"branch {branch}", context)

    def test_a_linked_worktree_is_briefed_on_its_own_branch(self):
        """Rows are keyed by the main checkout; the branch is the session's.

        Left to read the branch itself, `note_brief` would read it at the
        main root -- whatever is checked out there -- and brief the wrong item.
        """
        mine = sd_db.writes.create_item(
            self.connection, kind="work", title="on-the-branch", status="in_progress",
            repo=str(self.root), branch="feature-x", source=sd_lib.ITEM_ROW_SOURCE,
            external_id=f"{self.root}::feature-x/prd.md")
        other = self.item(name="elsewhere-on-main")
        self.followup(mine, "the branch's own work")
        self.followup(other, "not this worktree's")
        linked = self.home / "linked"
        subprocess.run(["git", "-C", str(self.root), "worktree", "add", "-q", "-b",
                        "feature-x", str(linked)], check=True, capture_output=True)
        context = self.injected(linked.resolve())
        self.assertIn("the branch's own work", context)
        self.assertIn("branch feature-x", context)
        self.assertNotIn("not this worktree's", context)


class TheRefusalNamesTheFault(unittest.TestCase):
    """Two ways `sd_db` can be unreachable, and two things to tell the reader.

    `bin/sd-note` and `bin/sd` print a `RowsRefusal` verbatim to a human, so
    the sentence this module chooses is the whole of what that person gets.
    `NOT_INSTALLED` is right for one of the two faults and misleading for the
    other: a virtualenv holding an `sd_db` that raises on import is not a
    machine without the library, and telling its owner to run the installer
    sends them to provision a package already sitting there while discarding
    the error that says what is wrong with it.

    Run out of process against a built pack, for the reason
    `tests/test_status_source.py` gives: the run that reaches this test
    necessarily has a working `sd_db`, and `-S` with a copied tree is the only
    honest way to describe a machine that does not. Binding the name to `None`
    in `sys.modules` cannot express it -- that defeats the retry as well as
    the first try, and the retry is the thing under test.
    """

    def refusal(self, provisioned: str | None) -> str:
        """`library()`'s sentence on a pack whose provisioned copy is `provisioned`.

        `None` builds the virtualenv and leaves it empty, which is the machine
        before `make setup`. A string is written as the copy's `__init__.py`.
        """
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        pack = Path(directory) / "pack"
        (pack / "bin").mkdir(parents=True)
        for name in ("sd_lib.py", "sd_handoff_rows.py"):
            (pack / "bin" / name).write_bytes((REPO_ROOT / "bin" / name).read_bytes())
        version = f"python{sys.version_info.major}.{sys.version_info.minor}"
        site = pack / ".venv" / "lib" / version / "site-packages"
        site.mkdir(parents=True)
        if provisioned is not None:
            (site / "sd_db").mkdir()
            (site / "sd_db" / "__init__.py").write_text(provisioned, encoding="utf-8")
        script = (
            "import sd_handoff_rows as rows\n"
            "try:\n"
            "    rows.library()\n"
            "except rows.RowsRefusal as refusal:\n"
            "    print(refusal)\n"
            "else:\n"
            "    print('no refusal at all')\n"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", script], capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(pack / "bin")},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_a_provisioned_copy_that_will_not_import_is_not_called_absent(self):
        """The error is the only thing that can be acted on, and it was dropped."""
        said = self.refusal("raise ImportError('the provisioned copy is broken')")
        self.assertIn("the provisioned copy is broken", said)
        self.assertIn("will not import", said)
        self.assertNotIn("is not installed in this virtualenv", said)
        self.assertNotIn("sd-install", said)

    def test_a_library_absent_everywhere_still_gets_the_installer(self):
        """The other half, and the reason the fix is a choice and not a swap.

        Nothing provisioned means nothing to inspect, and the remedy really is
        to install. Pinned so that naming the second fault does not quietly
        take the first fault's answer away with it.
        """
        said = self.refusal(None)
        self.assertIn("sd-install", said)
        self.assertNotIn("will not import", said)


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
        original = sd_handoff_rows.brief_for

        def explode(root):
            raise OSError("disk is gone")

        sd_handoff_rows.brief_for = explode
        self.addCleanup(setattr, sd_handoff_rows, "brief_for", original)
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


class TheRowIsFoundFromAClone(RowCase):
    """sd:981. `item_for` keyed the row by the checkout it ran in.

    `sd work register` resolves a checkout to the registered repository by
    its origin, so a runner clone can register a folder; `item_for` keyed by
    `main_worktree_root` and could not read the row that clone had made.
    Both now go through `sd_lib.registered_base`.
    """

    def git(self, root: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    def test_item_for_from_a_clone_returns_the_row_the_original_registered(self):
        bare = self.home / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)],
                       check=True, capture_output=True)
        self.git(self.root, "remote", "add", "origin", str(bare))
        self.git(self.root, "push", "-q", "origin", "HEAD:main")
        sd_db.writes.upsert_repo(self.connection, str(self.root), remote=str(bare))
        row = self.item()
        clone = self.home / "clone"
        subprocess.run(["git", "clone", "-q", str(bare), str(clone)],
                       check=True, capture_output=True)
        found = sd_handoff_rows.item_for(
            self.connection, sd_db, clone, clone / sd_lib.WORK_DIR / "an-item")
        self.assertIsNotNone(found, "the clone read no row")
        self.assertEqual(found["id"], row)
        self.assertEqual(found["external_id"], sd_lib.external_id(self.root, self.root / sd_lib.WORK_DIR / "an-item"))

    def test_item_for_from_a_clone_of_another_remote_reads_nothing(self):
        other = self.home / "other.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(other)],
                       check=True, capture_output=True)
        self.git(self.root, "remote", "add", "other", str(other))
        self.git(self.root, "push", "-q", "other", "HEAD:main")
        self.item()
        clone = self.home / "foreign"
        subprocess.run(["git", "clone", "-q", str(other), str(clone)],
                       check=True, capture_output=True)
        self.assertIsNone(sd_handoff_rows.item_for(
            self.connection, sd_db, clone, clone / sd_lib.WORK_DIR / "an-item"))


class TheLister(RowCase):
    """`sd-note list <item>`: one item's whole history, through `sd_db.item_notes`."""

    def note(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        module = load("sd_note", "sd-note")
        code = module.main(argv, out, err, cwd=str(self.root))
        return code, out.getvalue(), err.getvalue()

    def test_every_note_is_listed_oldest_first_with_kind_id_and_resolution(self):
        item = self.item()
        first = self.followup(item, "wire the hook")
        question = sd_db.add_note(self.connection, item, "question", "which tag?\nthe pin or HEAD")
        decision = sd_db.add_note(self.connection, item, "decision", "we chose sqlite")
        sd_db.resolve_note(self.connection, first)
        code, out, err = self.note(["list", str(item)])
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[0], f"sd:{item} an-item (in_progress): 4 notes, oldest first")
        # The opening `status_change` `create_item` writes is history too.
        self.assertTrue(lines[1].startswith("- [status_change #"), lines)
        self.assertRegex(lines[2], rf"^- \[followup #{first} \d{{4}}-\d\d-\d\d, "
                                   rf"resolved \d{{4}}-\d\d-\d\d\] wire the hook$")
        self.assertRegex(lines[3], rf"^- \[question #{question} [0-9-]+\] which tag\?$")
        self.assertEqual(lines[4], "  the pin or HEAD")
        self.assertRegex(lines[5], rf"^- \[decision #{decision} [0-9-]+\] we chose sqlite$")
        self.assertEqual(len(lines), 6, lines)

    def test_an_item_with_no_notes_says_so(self):
        item = self.item()
        self.connection.execute("DELETE FROM note WHERE item = ?", (item,))
        self.connection.commit()
        code, out, err = self.note(["list", f"sd:{item}"])
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, f"sd:{item} an-item (in_progress): no notes\n")

    def test_an_unknown_item_refuses_and_prints_nothing_on_stdout(self):
        code, out, err = self.note(["list", "4242"])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no item sd:4242 in the database", err)

    def test_an_id_past_sqlites_integers_is_a_usage_error_not_a_traceback(self):
        """SQLite raised OverflowError on the bind, which reached the operator raw."""
        for argv in (["list", "99999999999999999999"], ["resolve", "99999999999999999999"]):
            with self.subTest(argv=argv):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as exited:
                    self.note(argv)
                self.assertEqual(exited.exception.code, 2)
                self.assertIn("99999999999999999999", err.getvalue())
                self.assertNotIn("Traceback", err.getvalue())


def run_sd(argv: list[str]) -> tuple[int, str, str]:
    """`bin/sd`'s own `main`, with what it printed."""
    module = load("sd_cli", "sd")
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main(argv)
    return code, out.getvalue(), err.getvalue()


class TheNoteGroup(RowCase):
    """`sd note list <item>` and `sd note resolve <id>`, the verbs the brief and
    the dashboard name, through `bin/sd` rather than `bin/sd-note`."""

    def test_sd_note_list_prints_the_items_history(self):
        item = self.item()
        self.followup(item, "wire the hook")
        code, out, err = run_sd(["note", "list", f"sd:{item}"])
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(lines[0], f"sd:{item} an-item (in_progress): 2 notes, oldest first")
        self.assertTrue(lines[2].endswith("] wire the hook"), lines)

    def test_sd_note_resolve_closes_the_note(self):
        item = self.item()
        note = self.followup(item, "close me")
        code, out, err = run_sd(["note", "resolve", str(note)])
        self.assertEqual((code, out, err), (0, f"resolved note {note}\n", ""))
        self.assertEqual(self.read(), [])

    def test_an_unknown_item_refuses_through_sd(self):
        code, out, err = run_sd(["note", "list", "4242"])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no item sd:4242 in the database", err)

    def test_an_overflowing_id_is_a_usage_error_through_sd(self):
        code, _, err = run_sd(["note", "list", "99999999999999999999"])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)


class TheModuleLoader(unittest.TestCase):
    """`load` returns what `sys.modules` holds rather than a second copy.

    Asserted here rather than left to the module that noticed: the failure
    lands in `test_sd_lib.py`, which does nothing wrong, and only under
    `unittest discover`, which is the one way CI never runs the suite --
    `.github/scripts/run-tests.sh` gives each shard its own process. A
    defect no gate can see needs its check next to its cause.
    """

    def test_a_module_already_imported_is_not_executed_again(self) -> None:
        self.assertIs(load("sd_lib"), sys.modules["sd_lib"])
        self.assertIs(load("sd_lib"), sd_lib)

    def test_it_still_executes_a_module_that_is_not_imported_yet(self) -> None:
        """The control: a guard returning early for everything would pass the
        test above while loading nothing at all."""

        name = "sd_lib_under_another_name"
        sys.modules.pop(name, None)
        self.addCleanup(sys.modules.pop, name, None)
        fresh = load(name, "sd_lib.py")
        self.assertIs(sys.modules[name], fresh)
        self.assertIsNot(fresh, sd_lib)
        self.assertTrue(callable(fresh.parse_frontmatter))


if __name__ == "__main__":
    unittest.main()


class TheRowIsFoundFromItsKey(RowCase):
    """sd:994. `item_for` takes the `item: sd:<id>` fallback `sd_lib.Rows` takes.

    The dashboard and `sd-status` read the same folder; a fallback in one
    reader and not the other would have them disagree on which row it is.
    """

    def prd(self, value: str, name: str = "an-item") -> Path:
        item_dir = self.root / sd_lib.WORK_DIR / name
        item_dir.mkdir(parents=True, exist_ok=True)
        (item_dir / "prd.md").write_text(
            f"---\ntitle: {name}\ncreated: 2026-09-12\nitem: {value}\n---\n\n# {name}\n",
            encoding="utf-8",
        )
        return item_dir

    def row(self, kind: str = "followup") -> int:
        return sd_db.writes.create_item(
            self.connection, kind=kind, title="a row", status="planning",
            repo=str(self.root),
        )

    def test_item_for_reads_the_followup_row_the_frontmatter_names(self):
        number = self.row("followup")
        item_dir = self.prd(f"sd:{number}")
        found = sd_handoff_rows.item_for(self.connection, sd_db, self.root, item_dir)
        self.assertIsNotNone(found, "the key read no row")
        self.assertEqual(found["id"], number)

    def test_item_for_refuses_a_work_row_through_the_key(self):
        number = self.item("another-item")
        item_dir = self.prd(f"sd:{number}")
        self.assertIsNone(
            sd_handoff_rows.item_for(self.connection, sd_db, self.root, item_dir))

    def test_item_for_reads_nothing_for_a_row_that_is_not_there(self):
        item_dir = self.prd("sd:424242")
        self.assertIsNone(
            sd_handoff_rows.item_for(self.connection, sd_db, self.root, item_dir))

    def test_the_path_row_wins_over_the_key(self):
        number = self.item("an-item")
        other = self.row("followup")
        item_dir = self.prd(f"sd:{other}")
        found = sd_handoff_rows.item_for(self.connection, sd_db, self.root, item_dir)
        self.assertEqual(found["id"], number)
