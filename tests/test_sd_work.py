"""The real CLI operates on a scratch database, without repository ceremony."""

import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

import sd_db  # noqa: E402
import sd_db.repos  # noqa: E402
import sd_work  # noqa: E402
from sd_db.workflow import NOTE_KINDS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class TaskCLI(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name)
        sd_db.initialise(home=self.home)
        self.environment = {**os.environ, "HOME": str(self.home)}

    def call(self, *arguments, code=0, cwd=None):
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "sd"), *map(str, arguments)],
            cwd=str(cwd or self.home), env=self.environment,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def test_task_lifecycle_outside_checkout_and_stale_edit(self):
        state = json.loads(self.call("task", "add", "Check the workflow", "--json").stdout)
        item = state["item"]["id"]
        edited = json.loads(self.call(
            "task", "edit", item, "--priority", 1, "--due", "2026-09-08",
            "--if-revision", state["revision"], "--json").stdout)
        refused = self.call("task", "status", item, "done", "--if-revision",
                            state["revision"], code=1)
        self.assertIn("changed", refused.stderr)
        readback = json.loads(self.call("store", "item", item, "--json").stdout)
        self.assertEqual(readback, edited)
        noted = json.loads(self.call("task", "note", item, "--body", "Verify on iPad",
                                     "--json").stdout)
        resolved = json.loads(self.call("task", "resolve", noted["note"]["id"],
                                        "--json").stdout)
        self.assertTrue(resolved["note"]["resolved_at"])
        completed = json.loads(self.call("task", "status", item, "done", "--json").stdout)
        self.assertEqual(completed["item"]["status"], "done")
        self.assertEqual(json.loads(self.call("store", "items", "--open", "--json").stdout), [])
        self.assertFalse((self.home / "docs").exists())
        self.assertFalse((self.home / ".git").exists())

    def test_cli_and_today_query_agree(self):
        for title in ("One", "Two"):
            state = json.loads(self.call("task", "add", title, "--json").stdout)
            self.call("task", "status", state["item"]["id"], "in_progress")
        with sd_db.connect(sd_db.default_path(self.home), write=False) as connection:
            expected = [dict(row) for row in sd_db.reads.today_items(connection)]
        self.assertEqual(json.loads(self.call("today", "--json").stdout), expected)

    def test_note_defaults_to_comment_without_creating_a_followup(self):
        state = json.loads(self.call("task", "add", "Parent task", "--json").stdout)
        item = state["item"]["id"]
        result = json.loads(self.call("task", "note", item, "--body", "A useful observation",
                                      "--json").stdout)
        self.assertEqual(result["note"]["kind"], "comment")
        self.assertEqual((result["item"]["kind"], result["item"]["status"]), ("task", "planning"))
        readback = json.loads(self.call("store", "item", item, "--json").stdout)
        self.assertEqual(readback["notes"], result["notes"])
        with sd_db.connect(sd_db.default_path(self.home), write=False) as connection:
            self.assertEqual(sd_db.reads.open_followups(connection), [])

    def test_all_public_note_kinds_parse_and_persist_without_internal_kinds(self):
        self.assertEqual(set(NOTE_KINDS), {"comment", "followup", "question", "decision", "proposal"})
        state = json.loads(self.call("task", "add", "Parent task", "--json").stdout)
        item = state["item"]["id"]
        initial_notes = state["notes"]
        initial_ids = {note["id"] for note in initial_notes}
        for kind in NOTE_KINDS:
            with self.subTest(kind=kind):
                state = json.loads(self.call("task", "note", item, "--kind", kind,
                    "--body", f"Recorded {kind}", "--if-revision", state["revision"], "--json").stdout)
                self.assertEqual(state["note"]["kind"], kind)
                self.assertEqual(state["note"]["body"], f"Recorded {kind}")
        before = json.loads(self.call("store", "item", item, "--json").stdout)
        self.assertEqual([note["kind"] for note in before["notes"] if note["id"] not in initial_ids], list(NOTE_KINDS))
        self.assertEqual([note for note in before["notes"] if note["id"] in initial_ids], initial_notes)
        self.call("task", "note", item, "--body", "Forged history", "--kind", "status_change", code=2)
        self.assertEqual(json.loads(self.call("store", "item", item, "--json").stdout), before)
        help_text = self.call("task", "note", "--help").stdout
        self.assertIn("{" + ",".join(NOTE_KINDS) + "}", help_text)
        self.assertIn("default: comment", help_text)

    def test_task_add_remains_task_only(self):
        state = json.loads(self.call("task", "add", "Standalone work", "--json").stdout)
        self.assertEqual(state["item"]["kind"], "task")
        self.call("task", "add", "Not another task", "--kind", "proposal", code=2)
        rows = json.loads(self.call("store", "items", "--json").stdout)
        self.assertEqual([row["id"] for row in rows], [state["item"]["id"]])

    def _checkout(self, name):
        """A real checkout, because the repository is resolved by asking git."""
        root = self.home / name
        root.mkdir()
        def run(*args):
            return subprocess.run(["git", *args], cwd=str(root), check=True,
                                  capture_output=True, text=True)

        run("init", "-q", "-b", "main")
        run("config", "user.email", "t@example.com")
        run("config", "user.name", "T")
        (root / "README.md").write_text("x\n")
        run("add", "README.md")
        run("commit", "-qm", "first")
        return root

    def test_a_new_task_takes_the_repository_it_was_filed_from(self):
        """The default is cwd's registered checkout, and never a refusal.

        Two cases carry the design. A linked worktree resolves to its main
        checkout, because `--show-toplevel` names the temporary worktree,
        which is deleted long before anyone reads the row back. An
        unregistered checkout falls back to no repository: `capture_task`
        rejects an unregistered path, so a default that passed cwd through
        would make the verb fail everywhere it used to work.
        """
        root = self._checkout("project")

        unregistered = json.loads(
            self.call("task", "add", "Before registering", "--json", cwd=root).stdout)
        self.assertIsNone(unregistered["item"]["repo"])
        self.assertIn("not a registered repository",
                      self.call("task", "add", "Insisting", "--here", cwd=root, code=1).stderr)

        with sd_db.connect(sd_db.default_path(self.home), write=True) as connection:
            sd_db.repos.add(connection, root, home=self.home)

        filed = json.loads(self.call("task", "add", "Inside", "--json", cwd=root).stdout)
        self.assertEqual(filed["item"]["repo"], str(root.resolve()))

        linked = self.home / "linked"
        subprocess.run(["git", "worktree", "add", "-q", "-b", "side", str(linked)],
                       cwd=str(root), check=True, capture_output=True, text=True)
        from_worktree = json.loads(
            self.call("task", "add", "From a worktree", "--json", cwd=linked).stdout)
        self.assertEqual(from_worktree["item"]["repo"], str(root.resolve()))

        opted_out = json.loads(
            self.call("task", "add", "Neither", "--no-repo", "--json", cwd=root).stdout)
        self.assertIsNone(opted_out["item"]["repo"])

        outside = json.loads(self.call("task", "add", "Outside", "--json").stdout)
        self.assertIsNone(outside["item"]["repo"])

        self.call("task", "add", "Both", "--here", "--no-repo", cwd=root, code=2)

    def test_a_filed_task_can_be_moved_between_repositories_and_off_them(self):
        """The move a hand-written `UPDATE item.repo` used to be (sd:507, sd:452).

        `repo` was the one capture-time field `edit` could not change, so a row
        filed from the wrong directory stayed mis-attributed. The rule it has
        to obey is the same one `add` obeys -- the `repo` table decides what a
        repository is -- and the note the library already writes for every
        edited field is what records the move, so nothing here re-implements
        either half.
        """
        first, second = self._checkout("first"), self._checkout("second")
        with sd_db.connect(sd_db.default_path(self.home), write=True) as connection:
            sd_db.repos.add(connection, first, home=self.home)
            sd_db.repos.add(connection, second, home=self.home)

        state = json.loads(self.call("task", "add", "Filed nowhere", "--json").stdout)
        item = state["item"]["id"]
        self.assertIsNone(state["item"]["repo"])

        moved = json.loads(self.call("task", "edit", item, "--belongs-to", first, "--json").stdout)
        self.assertEqual(moved["item"]["repo"], str(first.resolve()))

        # The path is read the way `add` reads cwd, so `.` inside a checkout
        # names that checkout rather than a directory the `repo` table has
        # never heard of. The flag is `--belongs-to` and not `--repo` because
        # R10-D6 refuses that option name anywhere under `bin/`, and `add`
        # answered the same question without it one verb earlier.
        again = json.loads(
            self.call("task", "edit", item, "--belongs-to", ".", "--json", cwd=second).stdout)
        self.assertEqual(again["item"]["repo"], str(second.resolve()))

        cleared = json.loads(self.call("task", "edit", item, "--no-repo", "--json").stdout)
        self.assertIsNone(cleared["item"]["repo"])

    def test_the_move_is_recorded_on_the_item_rather_than_happening_silently(self):
        root = self._checkout("recorded")
        with sd_db.connect(sd_db.default_path(self.home), write=True) as connection:
            sd_db.repos.add(connection, root, home=self.home)
        state = json.loads(self.call("task", "add", "Mis-filed", "--json").stdout)
        item = state["item"]["id"]
        before = {note["id"] for note in state["notes"]}
        moved = json.loads(self.call("task", "edit", item, "--belongs-to", root, "--json").stdout)
        added = [note for note in moved["notes"] if note["id"] not in before]
        self.assertEqual([note["kind"] for note in added], ["comment"])
        self.assertIn("repo", added[0]["body"])

    def test_the_move_is_visible_without_asking_for_json(self):
        """The other half of sd:452: `repo` was the field no output showed.

        `--belongs-to` wrote the database and printed the same five words back,
        so the only way to see the move was `--json`. It prints now -- but only
        where it says something, because a path on every row of every listing
        is a field nobody reads.
        """
        root = self._checkout("visible")
        with sd_db.connect(sd_db.default_path(self.home), write=True) as connection:
            sd_db.repos.add(connection, root, home=self.home)
        item = json.loads(self.call("task", "add", "Mis-filed", "--json").stdout)["item"]["id"]

        # The move, made from inside the destination, where "which repository"
        # is otherwise answered by where the caller is standing.
        moved = self.call("task", "edit", item, "--belongs-to", ".", cwd=root)
        self.assertIn(f"repo: {root.resolve()}", moved.stdout)

        # Read back from outside every checkout: nothing else answers it.
        self.assertIn(f"repo: {root.resolve()}",
                      self.call("store", "item", item).stdout)

        # The control. Standing in the row's own checkout, an ordinary listing
        # does not grow a repo line.
        listed = self.call("store", "items", cwd=root)
        self.assertIn("Mis-filed", listed.stdout)
        self.assertNotIn("repo:", listed.stdout)

        # And a linked worktree of it is still standing in it: the row carries
        # the main checkout, which is the spelling `add` resolved it to.
        linked = self.home / "visible-linked"
        subprocess.run(["git", "worktree", "add", "-q", "-b", "side", str(linked)],
                       cwd=str(root), check=True, capture_output=True, text=True)
        self.assertNotIn("repo:", self.call("store", "items", cwd=linked).stdout)

        # Clearing it is a move too, and says so rather than printing a blank.
        cleared = self.call("task", "edit", item, "--no-repo", cwd=root)
        self.assertIn(f"repo: {sd_work.NO_CHECKOUT}", cleared.stdout)
        # ...and afterwards there is no path to name, so nothing is named.
        self.assertNotIn("repo:", self.call("store", "item", item).stdout)

    def test_an_unregistered_repository_is_refused_without_moving_the_row(self):
        """The `repo` table is the authority, and a refusal changes nothing."""
        stranger = self._checkout("stranger")
        state = json.loads(self.call("task", "add", "Stays put", "--json").stdout)
        item = state["item"]["id"]
        refused = self.call("task", "edit", item, "--belongs-to", stranger, code=1)
        self.assertIn("not registered", refused.stderr)
        readback = json.loads(self.call("store", "item", item, "--json").stdout)
        self.assertIsNone(readback["item"]["repo"])
        self.assertEqual(readback["revision"], state["revision"])

    def test_belongs_to_and_no_repo_are_the_same_field_and_cannot_both_be_given(self):
        state = json.loads(self.call("task", "add", "One or the other", "--json").stdout)
        self.call("task", "edit", state["item"]["id"], "--belongs-to", self.home,
                  "--no-repo", code=2)
        self.assertIn("requires a field",
                      self.call("task", "edit", state["item"]["id"], code=1).stderr)

    def test_refusals_and_usage_have_distinct_exit_codes(self):
        self.assertIn("no item", self.call("store", "item", 9999, code=1).stderr)
        self.call("task", "add", "Task", "--priority", 9, code=2)
        self.assertIn("Git checkout", self.call("task", "add", "Task", "--here", code=1).stderr)
        self.call("task", "add", "Task", "--due", "tomorrow", code=1)


class WorkRegister(unittest.TestCase):
    """`sd work register` makes the row that owns a folder already on disk.

    The folder is the input. Retirement handed status to the database and took
    the importer away with it, so a `docs/work` folder created after the
    cutover has no row and therefore no readable status at all -- which is what
    `sd-status` reports as `status-unreadable`. This is the missing step.
    """

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name)
        sd_db.initialise(home=self.home)
        self.environment = {**os.environ, "HOME": str(self.home)}
        # Resolved, because that is the spelling the repo row carries: `add`
        # resolves what it is given, and on macOS the scratch directory is a
        # symlink, so the unresolved path matches no row at all.
        self.root = (self.home / "project").resolve()
        self.root.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "T")
        with sd_db.connect(sd_db.default_path(self.home), write=True) as connection:
            registered = sd_db.repos.add(connection, self.root, home=self.home)
            connection.execute(
                "UPDATE repo SET status_source = 'row' WHERE path = ?",
                (registered,))
            connection.commit()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=str(self.root), check=True,
                       capture_output=True, text=True)

    def call(self, *arguments, code=0):
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "sd"), *map(str, arguments)],
            cwd=str(self.root), env=self.environment,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def item(self, name="a-thing", *, title="A thing to do", created="2026-09-11",
             commit=True):
        folder = self.root / "docs" / "work" / f"2026-09-11-{name}"
        folder.mkdir(parents=True)
        prd = folder / "prd.md"
        prd.write_text(f"---\ntitle: {title}\ncreated: {created}\n---\n\nBody.\n")
        if commit:
            self.git("add", "-A")
            self.git("commit", "-qm", f"plan {name}")
        return prd.relative_to(self.root).as_posix()

    def test_a_folder_on_disk_becomes_the_row_that_owns_it(self):
        path = self.item()
        state = json.loads(self.call("work", "register", path, "--json").stdout)
        row = state["item"]
        self.assertTrue(state["created"])
        self.assertEqual(row["title"], "A thing to do")
        self.assertEqual(row["status"], "planning")
        self.assertEqual(row["repo"], str(self.root))
        self.assertEqual(row["path"], path)
        # On the default branch there is no working branch to name yet.
        self.assertIsNone(row["branch"])
        # The commit is read from git, not asserted by the caller.
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.root),
                              capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(row["source_commit"], head)

    def test_registering_twice_is_safe_and_says_so(self):
        """Not an error: the unique index makes the second call a no-op.

        But a caller who cannot tell the calls apart reads "here is the row" as
        "I just made it", so the second one has to say which it was.
        """

        path = self.item()
        first = json.loads(self.call("work", "register", path, "--json").stdout)
        again = json.loads(self.call("work", "register", path, "--json").stdout)
        self.assertTrue(first["created"])
        self.assertFalse(again["created"])
        self.assertEqual(first["item"]["id"], again["item"]["id"])
        self.assertIn("already registered", self.call("work", "register", path).stdout)

    def test_the_row_records_a_local_working_branch_or_none(self):
        """`item.branch` is the branch the work happens ON, so it is a local head.

        A runner clone standing on `plan/<slug>` names that branch. The
        default branch and a detached HEAD name nothing, because neither is a
        branch anyone is going to do the work on, and a row whose branch is
        the remote-tracking `origin/main` passes the runner's shape check,
        names no local head and fails only inside the clone -- which is the
        whole of system sd:462 and the reason this column may never carry one.
        """

        # `main` has to exist as a ref before anything can come back to it.
        self.git("commit", "-q", "--allow-empty", "-m", "root")
        self.git("checkout", "-q", "-b", "plan/a-thing")
        state = json.loads(self.call("work", "register", self.item(), "--json").stdout)
        self.assertEqual(state["item"]["branch"], "plan/a-thing")
        self.git("checkout", "-q", "main")
        default = json.loads(
            self.call("work", "register", self.item("second"), "--json").stdout)
        self.assertIsNone(default["item"]["branch"])
        self.git("checkout", "-q", "--detach")
        detached = json.loads(
            self.call("work", "register", self.item("third"), "--json").stdout)
        self.assertIsNone(detached["item"]["branch"])

    def test_the_branch_column_never_carries_a_remote_tracking_name(self):
        """The defect stated as the thing it produced, not as an implementation.

        `master` is the second name the fleet's defaults go by, and a checkout
        with no `origin/HEAD` to read is exactly the one where `default_branch`
        guesses `origin/main`; registering from it used to write that guess
        into the column verbatim.
        """

        self.git("checkout", "-q", "-b", "master")
        on_master = json.loads(
            self.call("work", "register", self.item(), "--json").stdout)
        self.assertIsNone(on_master["item"]["branch"])
        self.git("checkout", "-q", "-b", "fix/late")
        on_work = json.loads(
            self.call("work", "register", self.item("second"), "--json").stdout)
        self.assertEqual(on_work["item"]["branch"], "fix/late")
        # Read back through the surface anyone else would use, because the
        # column is what the runner and `sd-plan` consume, not the return.
        row = json.loads(
            self.call("store", "item", on_work["item"]["id"], "--json").stdout)["item"]
        self.assertEqual(row["branch"], "fix/late")
        self.assertNotIn("origin/", row["branch"])

    def test_a_local_main_is_a_working_branch_when_the_default_is_dev(self):
        """sd:639. The `{main, master}` pair belongs inside the no-remote guess.

        Every other fixture here has `main` as its default, so none of them
        can see the difference between "not the default" and "not named main
        or master". This one reads `origin/HEAD` as `dev`, stands on a local
        `main`, and expects `main` back -- and stands on `dev` for the control.
        """

        self.git("commit", "-q", "--allow-empty", "-m", "root")
        upstream = self.root.parent / "upstream.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "dev", str(upstream)],
                       check=True, capture_output=True, text=True)
        self.git("remote", "add", "origin", str(upstream))
        self.git("push", "-q", "origin", "main:dev")
        self.git("remote", "set-head", "origin", "dev")
        on_main = json.loads(
            self.call("work", "register", self.item(), "--json").stdout)
        self.assertEqual(on_main["item"]["branch"], "main")
        self.git("checkout", "-q", "-b", "dev", "origin/dev")
        on_dev = json.loads(
            self.call("work", "register", self.item("second"), "--json").stdout)
        self.assertIsNone(on_dev["item"]["branch"])

    def test_a_path_that_is_not_a_prd_is_refused_by_the_rule_it_breaks(self):
        """The shape is the library's rule; this proves the sentence arrives.

        `docs/work/<item>/prd.md` is what every reader keys on, so a row
        pointing anywhere else is a row nothing finds. The check lives in
        `register_work_item`; what this pins is that it reaches the caller as
        a refusal and an exit code rather than as a traceback.
        """

        stray = self.root / "docs" / "work" / "2026-09-11-a-thing"
        stray.mkdir(parents=True)
        (stray / "design.md").write_text(
            "---\ntitle: A thing to do\ncreated: 2026-09-11\n---\n\nBody.\n")
        refused = self.call(
            "work", "register", "docs/work/2026-09-11-a-thing/design.md", code=1)
        self.assertIn("docs/work/<item>/prd.md", refused.stderr)
        self.assertNotIn("Traceback", refused.stderr)

    def test_an_uncommitted_folder_registers_with_no_source_commit(self):
        """Planning writes the folder before anybody commits it."""

        path = self.item(commit=False)
        state = json.loads(self.call("work", "register", path, "--json").stdout)
        self.assertTrue(state["created"])
        self.assertIsNone(state["item"]["source_commit"])

    def test_frontmatter_without_a_title_or_date_is_refused(self):
        """Both halves, because the row takes both from the file.

        A date is not decoration here: `created_at` is what the item is aged
        by, and `register_work_item` refuses one that is not a real date.
        """

        cases = {
            "no-title": "---\ncreated: 2026-09-11\n---\n\nBody.\n",
            "no-date": "---\ntitle: A thing to do\n---\n\nBody.\n",
            "neither": "---\nowner: someone\n---\n\nBody.\n",
        }
        for name, text in cases.items():
            with self.subTest(missing=name):
                folder = self.root / "docs" / "work" / f"2026-09-11-{name}"
                folder.mkdir(parents=True)
                (folder / "prd.md").write_text(text)
                refused = self.call(
                    "work", "register", f"docs/work/2026-09-11-{name}/prd.md",
                    code=1)
                self.assertIn("title:", refused.stderr)
                self.assertIn("created:", refused.stderr)
                self.assertNotIn("Traceback", refused.stderr)

    def test_a_path_outside_the_repository_is_refused(self):
        refused = self.call("work", "register", "../escape/prd.md", code=1)
        self.assertIn("outside", refused.stderr)
        self.assertNotIn("Traceback", refused.stderr)

    def test_a_missing_file_is_refused_by_name(self):
        refused = self.call("work", "register", "docs/work/nope/prd.md", code=1)
        self.assertIn("no file at", refused.stderr)

    def test_a_repository_whose_files_still_own_status_is_refused(self):
        """Two answers to one question is the state this must never create."""

        with sd_db.connect(sd_db.default_path(self.home), write=True) as connection:
            connection.execute(
                "UPDATE repo SET status_source = 'file' WHERE path = ?",
                (str(self.root),))
            connection.commit()
        path = self.item()
        refused = self.call("work", "register", path, code=1)
        self.assertIn("second answer", refused.stderr)
        self.assertNotIn("Traceback", refused.stderr)

    def test_a_stale_library_refuses_by_name_instead_of_raising(self):
        """The import cannot stand in for the attribute.

        `sd_db.workflow` imports cleanly on a build that predates
        `register_work_item`, so checking the module alone would turn a stale
        library into an AttributeError from inside an open write.
        """

        self.assertEqual(
            sd_work.REGISTER_NEEDS,
            (("workflow", "register_work_item"), ("repos", "registered_for"),
             ("sources.docs_work", "default_branch")))
        for module_name, attribute in sd_work.REGISTER_NEEDS:
            module = importlib.import_module(f"sd_db.{module_name}")
            with self.subTest(missing=attribute):
                with unittest.mock.patch.object(module, attribute, create=False):
                    delattr(module, attribute)
                    with self.assertRaises(sd_work.WorkRefusal) as refusal:
                        sd_work._register_library(sd_db)
                self.assertIn(attribute, str(refusal.exception))
                self.assertIn("sd-install", str(refusal.exception))

    def test_the_stale_library_refusal_reaches_the_command_line(self):
        """The helper exception is not the contract; the exit code is.

        `bin/sd` maps `WorkRefusal` to 1 and reserves 2 for usage, so a
        machine carrying an old build gets the same "this is a refusal"
        signal as a bad path -- a sentence on stderr, and no traceback.
        The attribute is removed in the child, before `sd_work` looks for it.
        """

        shim = self.home / "shim"
        shim.mkdir()
        (shim / "sitecustomize.py").write_text(
            "import sd_db.workflow\n"
            "del sd_db.workflow.register_work_item\n")
        environment = {**self.environment,
                       "PYTHONPATH": f"{shim}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
        path = self.item()
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "sd"), "work", "register", path],
            cwd=str(self.root), env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("register_work_item", result.stderr)
        self.assertIn("sd-install", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
