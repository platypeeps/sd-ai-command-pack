"""Criterion 25: a trial is a row with an expiry, and use is what decides.

`sd skill try` writes the row and prints the date; the next install run after
expiry with no `skill_use` rows removes the skill and says so. Both against a
temporary database, which is what the criterion asks for.

This file is also where hand-off 7 lands: `sd_db.testing` has to be importable
from *this* repository's test suite, not only from the library's own, and the
assertion belongs beside the first tests that need the library.
"""

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


def load(name: str):
    """Import a `bin/` module by path -- `bin/` is not a package."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sd_install = load("sd_install")
sd_skill = load("sd_skill")

import sd_db  # noqa: E402 - after the path juggling above
import sd_db.testing  # noqa: E402,F401 - hand-off 7's assertion is the import


class TheHarnessIsImportableHere(unittest.TestCase):
    """Criterion 23's pack half, asserted from the pack.

    The library's own suite asserts the same import. Both are needed: the
    library's proves the module exists, this one proves the pack's virtualenv
    can reach it, which is the half the installer is responsible for and the
    half that silently fails when nobody provisions anything.
    """

    def test_the_library_resolves_to_a_copy_and_not_to_its_source(self):
        """B's criterion 1: the import resolves outside the library's checkout.

        The venv lives inside the pack, so "outside the pack" is the wrong
        test -- a correct install fails it. What must be true is that the
        import does not reach the `system` checkout's `local-sd-db`, which is
        exactly what an editable install would do and what a branch switch
        there would then change under the pack's feet.
        """
        resolved = Path(sd_db.__file__).resolve()
        source = sd_install.library_source(dict(os.environ)).resolve()
        self.assertFalse(
            resolved.is_relative_to(source),
            f"sd_db resolved to {resolved}, inside {source}; it is installed "
            "as a built copy, never as an editable checkout",
        )
        self.assertIn("site-packages", resolved.parts)

    def test_the_fixture_harness_is_reachable(self):
        self.assertTrue(hasattr(sd_db, "testing") or sd_db.testing is not None)


class TrialCase(unittest.TestCase):
    """A scratch home with a real database in it."""

    def setUp(self):
        self._scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self._scratch.cleanup)
        self.home = Path(self._scratch.name).resolve()
        sd_db.initialise(home=self.home)
        self.connection = sd_db.connect(sd_db.default_path(self.home))
        self.addCleanup(self.connection.close)


class TheTrialVerb(TrialCase):
    def run_try(self, name: str) -> tuple[int, str]:
        """`sd skill try <name>` through the CLI, against the scratch home."""
        done = subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "sd"), "skill", "try", name],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(self.home)},
            cwd=tempfile.gettempdir(),
        )
        return done.returncode, done.stdout + done.stderr

    def trial_rows(self) -> list:
        return sd_db.trials(self.connection)

    def test_a_trial_writes_one_row_and_prints_its_expiry(self):
        contrib = sorted(
            entry.name
            for entry in (REPO_ROOT / sd_skill.CONTRIB_DIR).iterdir()
            if entry.is_dir()
        )
        self.assertTrue(contrib, "contrib/ is empty; requirement 10 says it holds the rest")
        rc, output = self.run_try(contrib[0])
        self.assertEqual(rc, 0, output)
        rows = self.trial_rows()
        self.assertEqual([row["skill"] for row in rows], [contrib[0]])
        # The printed date is the row's expiry, not a second number computed
        # for the message. A test that only checked "some date appeared" would
        # pass against a message that lied about the row.
        self.assertIn(rows[0]["expires"][:10], output)

    def test_the_expiry_is_thirty_days_out(self):
        contrib = sorted(
            entry.name
            for entry in (REPO_ROOT / sd_skill.CONTRIB_DIR).iterdir()
            if entry.is_dir()
        )
        self.run_try(contrib[0])
        row = self.trial_rows()[0]
        started = row["started"]
        expires = row["expires"]
        self.assertEqual(
            (
                sd_skill.datetime.datetime.fromisoformat(expires)
                - sd_skill.datetime.datetime.fromisoformat(started)
            ).days,
            sd_skill.TRIAL_DAYS,
        )

    def test_a_skill_already_on_a_path_is_refused_rather_than_trialled(self):
        rc, output = self.run_try("sd-plan")
        self.assertEqual(rc, 1)
        self.assertIn("already on a path", output)
        self.assertEqual(self.trial_rows(), [])

    def test_a_name_in_neither_place_is_refused_and_says_what_there_is(self):
        rc, output = self.run_try("sd-not-a-skill")
        self.assertEqual(rc, 1)
        self.assertIn("available:", output)
        self.assertEqual(self.trial_rows(), [])


class TheExpiry(TrialCase):
    """The install run that removes a trial nobody used, and says so."""

    def context(self) -> "sd_install.Context":
        return sd_install.Context(
            checkout=REPO_ROOT,
            home=self.home,
            environ={
                "XDG_STATE_HOME": str(self.home / ".local" / "state"),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
            },
        )

    def test_an_expired_trial_with_no_use_is_removed_and_named(self):
        sd_db.start_trial(self.connection, "sd-grill", "2001-01-01T00:00:00Z")
        out = io.StringIO()
        removed = sd_install.expire_trials(self.connection, out)
        self.assertEqual(removed, ["sd-grill"])
        self.assertIn("sd-grill", out.getvalue())
        self.assertIn("no use", out.getvalue())
        self.assertEqual(sd_db.trials(self.connection), [])

    def test_an_expired_trial_that_earned_use_is_kept(self):
        sd_db.start_trial(self.connection, "sd-grill", "2001-01-01T00:00:00Z")
        row = sd_db.trials(self.connection)[0]
        sd_db.record_skill_use(self.connection, "sd-grill", timestamp=row["started"])
        out = io.StringIO()
        self.assertEqual(sd_install.expire_trials(self.connection, out), [])
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(len(sd_db.trials(self.connection)), 1)

    def test_use_from_before_the_trial_does_not_save_it(self):
        """The window is the trial's own, which is the whole point of the row.

        A skill somebody used last year and then put on trial has not earned
        the trial. Counting the old rows would keep it installed on the
        strength of the usage that made somebody curious in the first place.
        """
        sd_db.record_skill_use(self.connection, "sd-grill", timestamp="2000-01-01T00:00:00Z")
        sd_db.start_trial(self.connection, "sd-grill", "2001-01-01T00:00:00Z")
        out = io.StringIO()
        self.assertEqual(sd_install.expire_trials(self.connection, out), ["sd-grill"])

    def test_an_unexpired_trial_is_left_alone_however_unused(self):
        sd_db.start_trial(self.connection, "sd-grill", "2099-01-01T00:00:00Z")
        out = io.StringIO()
        self.assertEqual(sd_install.expire_trials(self.connection, out), [])
        self.assertEqual(len(sd_db.trials(self.connection)), 1)

    def test_the_whole_run_expires_removes_and_renders_in_one_pass(self):
        """`cmd_user` end to end, against this checkout and a real database.

        The pieces above are tested one at a time. This is the pass an
        operator actually gets: an expired unused trial goes, an active one
        stays and installs from `contrib/`, and the skills the paths name are
        rendered alongside it. Nothing here is mocked -- the database is the
        real schema, the checkout is this repository, and only `$HOME` is
        scratch.
        """
        sd_db.start_trial(self.connection, "sd-grill", "2099-01-01T00:00:00Z")
        sd_db.start_trial(self.connection, "sd-coherence-audit", "2001-01-01T00:00:00Z")
        self.connection.commit()

        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(self.context(), out), 0)
        report = out.getvalue()

        # No warning: the library imported and the database was there.
        self.assertNotIn("warning:", report)
        self.assertIn("sd-coherence-audit", report)
        self.assertIn("no use", report)

        claude = self.home / ".claude" / "skills"
        self.assertTrue((claude / "sd-grill" / sd_install.SKILL_FILE).is_file())
        self.assertFalse((claude / "sd-coherence-audit").exists())
        self.assertTrue((claude / "sd-plan" / sd_install.SKILL_FILE).is_file())

        remaining = {row["skill"] for row in sd_db.trials(self.connection)}
        self.assertEqual(remaining, {"sd-grill"})

    def test_the_install_run_renders_an_active_trial_from_contrib(self):
        sd_db.start_trial(self.connection, "sd-grill", "2099-01-01T00:00:00Z")
        names = [
            surface.name
            for surface in sd_install.discover_surfaces(
                REPO_ROOT, [row["skill"] for row in sd_db.active_trials(self.connection)]
            )
        ]
        self.assertIn("sd-grill", names)
        self.assertNotIn("sd-grill", sd_install.named_skills(REPO_ROOT))


class ProvisioningIsItsOwnRun(unittest.TestCase):
    """Rendering skills must not rebuild the virtualenv it renders from.

    Criterion 13 puts the path to the library's source in this installer and
    nowhere else. It does not say every render should reinstall, and the first
    version of this work did: `cmd_user` called `provision_library`, so each
    of the hundreds of fixture installs in this suite shelled out to `pip`.
    In a parallel run that replaced `sd_db` in site-packages while another
    shard was importing it, which surfaced as `No module named
    'sd_db.testing.home'` in a file that touches neither.

    The interpreter here is a script that records being called. If a render
    ever installs again, the marker appears and this fails at the cause.
    """

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name).resolve()
        self.checkout = self.home / "checkout"
        self.marker = self.home / "pip-was-run"

        # A checkout with one skill, one path naming it, and a virtualenv
        # whose interpreter is a recorder rather than a Python.
        skill = self.checkout / "skills" / "sd-probe"
        skill.mkdir(parents=True)
        (skill / sd_install.SKILL_FILE).write_text(
            "---\nname: sd-probe\n---\n\nprobe surface\n", encoding="utf-8"
        )
        (self.checkout / "skills" / sd_install.PATHS_FILE).write_text(
            json.dumps({"paths": {
                "research": {"summary": "sources to brief", "skills": ["sd-probe"]},
                "development": {"summary": "plan to ship", "skills": []},
                "act": {"summary": "brief to send", "skills": []},
            }}),
            encoding="utf-8",
        )
        interpreter = self.checkout / sd_install.VENV_RELATIVE
        interpreter.parent.mkdir(parents=True)
        interpreter.write_text(
            f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{self.marker}"\n', encoding="utf-8"
        )
        interpreter.chmod(0o755)

        # A library source the provisioner would accept, so a call would get
        # past the "nothing to install" guard rather than being turned back.
        # A git repository, because the provisioner installs from a ref.
        system = self.home / "system"
        source = sd_install.library_source({"SD_SYSTEM_CHECKOUT": str(system)})
        source.mkdir(parents=True)
        (source / "pyproject.toml").write_text("[project]\nname = 'sd-db'\n", encoding="utf-8")
        for args in (("init",), ("add", "-A"), ("commit", "-m", "fixture")):
            subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                cwd=system, capture_output=True, text=True, check=False,
            )

    def context(self) -> "sd_install.Context":
        return sd_install.Context(
            checkout=self.checkout,
            home=self.home,
            environ={
                "SD_SYSTEM_CHECKOUT": str(self.home / "system"),
                "XDG_STATE_HOME": str(self.home / ".local" / "state"),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
            },
        )

    def test_a_render_does_not_shell_out_to_pip(self) -> None:
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(self.context(), out), 0)
        self.assertFalse(
            self.marker.exists(),
            f"the render installed: {self.marker.read_text() if self.marker.exists() else ''}",
        )

    def test_the_provisioning_mode_does_shell_out(self) -> None:
        """The other half. Without it the test above passes on a broken path."""
        out = io.StringIO()
        installed, report = sd_install.provision_library(self.context(), out)
        self.assertTrue(installed, report)
        self.assertTrue(self.marker.exists(), report)
        self.assertIn("pip", self.marker.read_text(encoding="utf-8"))


class NoLibrary:
    """A `sys.meta_path` finder that refuses `sd_db` wherever it is installed."""

    def find_spec(self, name, path=None, target=None):
        if name == "sd_db" or name.startswith("sd_db."):
            raise ImportError("sd_db is not installed (blocked by the test)")
        return None


class TheLibraryDoor(unittest.TestCase):
    """Every way `open_library` and `provision_library` can answer.

    Each of these is a machine somebody actually has: no virtualenv yet, no
    `system` checkout, a `--dry-run`, a `pip` that is not there, a `pip` that
    fails, a library that will not import, a database that was never created.
    The installer answers all of them with a line and a working install of
    whatever it could still render, so none of them may raise.
    """

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name).resolve()
        self.checkout = self.home / "checkout"
        self.checkout.mkdir()
        self.system = self.home / "system"

    def context(self, **overrides) -> "sd_install.Context":
        fields = {
            "checkout": self.checkout,
            "home": self.home,
            "environ": {
                "SD_SYSTEM_CHECKOUT": str(self.system),
                "XDG_STATE_HOME": str(self.home / ".local" / "state"),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
            },
        }
        fields.update(overrides)
        return sd_install.Context(**fields)

    def interpreter(self, script: str) -> Path:
        path = self.checkout / sd_install.VENV_RELATIVE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(script, encoding="utf-8")
        path.chmod(0o755)
        return path

    def library(self, *, committed: bool = True, tag: str = "") -> Path:
        """A fixture system checkout, as a git repository.

        A repository and not a bare directory, because `provision_library`
        installs from an immutable ref now and a directory has none. The
        `committed=False` case is the machine that cloned nothing yet.
        """
        source = sd_install.library_source({"SD_SYSTEM_CHECKOUT": str(self.system)})
        source.mkdir(parents=True, exist_ok=True)
        (source / "pyproject.toml").write_text("[project]\nname = 'sd-db'\n", encoding="utf-8")
        if committed:
            self.git("init")
            self.git("add", "-A")
            self.git("commit", "-m", "fixture")
            if tag:
                self.git("tag", tag)
        return source

    def git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
            cwd=self.system, capture_output=True, text=True, check=False,
        )
        return done.stdout.strip()

    def test_no_virtualenv_names_the_remedy(self) -> None:
        installed, report = sd_install.provision_library(self.context(), io.StringIO())
        self.assertFalse(installed)
        self.assertIn("no virtualenv at", report)
        self.assertIn("make setup", report)

    def test_no_library_source_says_trials_are_unavailable(self) -> None:
        self.interpreter("#!/bin/sh\nexit 0\n")
        installed, report = sd_install.provision_library(self.context(), io.StringIO())
        self.assertFalse(installed)
        self.assertIn("no library at", report)
        self.assertIn("trials unavailable", report)

    def test_the_install_names_the_tag_the_checkout_stands_on(self) -> None:
        self.interpreter("#!/bin/sh\nexit 0\n")
        self.library(tag="sd-db-v9.9.9")
        installed, report = sd_install.provision_library(self.context(), io.StringIO())
        self.assertTrue(installed, report)
        self.assertIn("sd-db-v9.9.9", report)

    def test_a_tag_for_another_project_in_the_monorepo_is_not_the_library_version(
        self,
    ) -> None:
        """`system` holds four projects. A `local-ha-mcp` tag is not a version."""
        self.interpreter("#!/bin/sh\nexit 0\n")
        self.library(tag="ha-mcp-v2")
        head = self.git("rev-parse", "HEAD")
        installed, report = sd_install.provision_library(self.context(), io.StringIO())
        self.assertTrue(installed, report)
        self.assertNotIn("ha-mcp-v2", report)
        self.assertIn(head, report)

    def test_an_untagged_checkout_pins_to_its_commit_and_is_not_refused(self) -> None:
        """`system` carries no tags. Refusing here uninstalls sd_db everywhere."""
        self.interpreter("#!/bin/sh\nexit 0\n")
        self.library()
        head = self.git("rev-parse", "HEAD")
        installed, report = sd_install.provision_library(self.context(), io.StringIO())
        self.assertTrue(installed, report)
        self.assertIn(head, report)

    def test_the_working_tree_is_never_what_pip_is_pointed_at(self) -> None:
        """The whole point of the ref: an edit on disk is not a version."""
        seen = self.home / "argv"
        self.interpreter(f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{seen}"\n')
        source = self.library()
        (source / "pyproject.toml").write_text("[project]\nname = 'edited'\n", encoding="utf-8")
        installed, report = sd_install.provision_library(self.context(), io.StringIO())
        self.assertTrue(installed, report)
        argv = seen.read_text(encoding="utf-8")
        self.assertIn("git+file://", argv)
        self.assertNotIn(f"\n{source}\n", argv)

    def test_uncommitted_work_is_said_out_loud_and_not_refused(self) -> None:
        self.interpreter("#!/bin/sh\nexit 0\n")
        source = self.library()
        (source / "pyproject.toml").write_text("[project]\nname = 'edited'\n", encoding="utf-8")
        installed, report = sd_install.provision_library(self.context(), io.StringIO())
        self.assertTrue(installed, report)
        self.assertIn("uncommitted work", report)

    def test_a_system_directory_that_is_no_repository_is_refused_with_a_reason(self) -> None:
        self.interpreter("#!/bin/sh\nexit 0\n")
        self.library(committed=False)
        installed, report = sd_install.provision_library(self.context(), io.StringIO())
        self.assertFalse(installed)
        self.assertIn("nothing to pin to", report)

    def test_a_dry_run_says_what_it_would_do_and_does_not(self) -> None:
        marker = self.home / "ran"
        self.interpreter(f'#!/bin/sh\ntouch "{marker}"\n')
        self.library()
        installed, report = sd_install.provision_library(self.context(dry_run=True), io.StringIO())
        self.assertTrue(installed)
        self.assertIn("would install sd_db from", report)
        self.assertFalse(marker.exists())

    def test_provisioning_preserves_a_newer_installed_database_library(self) -> None:
        marker = self.home / "pip-ran"
        self.interpreter(f'#!/bin/sh\ntouch "{marker}"\n')
        source = self.library()
        schema = source / "sd_db/schema.py"
        schema.parent.mkdir()
        schema.write_text("SCHEMA_VERSION = 2\n")
        self.git("add", "-A")
        self.git("commit", "-m", "schema two")
        installed = self.checkout / ".venv/lib/python3.13/site-packages/sd_db/schema.py"
        installed.parent.mkdir(parents=True)
        installed.write_text("SCHEMA_VERSION = 3\n")
        ok, report = sd_install.provision_library(self.context(), io.StringIO())
        self.assertFalse(ok)
        self.assertIn("preserving installed sd_db schema 3", report)
        self.assertFalse(marker.exists())
        self.assertEqual(installed.read_text(), "SCHEMA_VERSION = 3\n")

    def test_an_interpreter_that_cannot_run_is_reported_not_raised(self) -> None:
        # Present and executable to the guard above, unrunnable to the kernel:
        # an interpreter line naming a program that does not exist.
        self.interpreter("#!/nonexistent/interpreter\n")
        self.library()
        installed, report = sd_install.provision_library(self.context(), io.StringIO())
        self.assertFalse(installed)
        self.assertIn("sd_db install failed", report)

    def test_a_failing_pip_is_reported_with_its_last_line(self) -> None:
        self.interpreter('#!/bin/sh\necho "the wheel would not build" >&2\nexit 1\n')
        self.library()
        installed, report = sd_install.provision_library(self.context(), io.StringIO())
        self.assertFalse(installed)
        self.assertIn("sd_db install failed", report)
        self.assertIn("the wheel would not build", report)

    def test_a_pip_that_says_nothing_still_reports_the_failure(self) -> None:
        """`[-1:] or ['no output']` -- a silent failure is still a failure."""
        self.interpreter("#!/bin/sh\nexit 1\n")
        self.library()
        installed, report = sd_install.provision_library(self.context(), io.StringIO())
        self.assertFalse(installed)
        self.assertIn("sd_db install failed", report)
        self.assertIn("no output", report)

    def test_a_library_that_will_not_import_leaves_the_render_working(self) -> None:
        blocker = NoLibrary()
        sys.meta_path.insert(0, blocker)
        self.addCleanup(sys.meta_path.remove, blocker)
        saved = dict(sys.modules)
        self.addCleanup(lambda: (sys.modules.clear(), sys.modules.update(saved)))
        for name in [n for n in sys.modules if n == "sd_db" or n.startswith("sd_db.")]:
            del sys.modules[name]
        connection, reason = sd_install.open_library(self.context())
        self.assertIsNone(connection)
        self.assertIn("sd_db not importable", reason)
        self.assertIn("trials unavailable", reason)

    def test_a_home_with_no_database_names_the_command_that_makes_one(self) -> None:
        connection, reason = sd_install.open_library(self.context())
        self.assertIsNone(connection)
        self.assertIn("no database at", reason)
        self.assertIn("sd-db.sh init", reason)


class TheProvisioningMode(unittest.TestCase):
    """`--provision-library`, the one door `make setup` goes through.

    What the dispatch does is turn a report into an exit code, and that is
    what these test. `main` derives the checkout from the module's own
    location and has no flag for it, so a test that went all the way to
    `pip` would be asserting facts about the machine it runs on: the first
    version did, and it passed here and failed on CI, where the checkout has
    no `.venv` and the refusal arrives before anything else can. The
    provisioning itself is covered by `TheLibraryDoor` against a fixture.
    """

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name).resolve()
        self.saved = sd_install.provision_library
        self.addCleanup(setattr, sd_install, "provision_library", self.saved)

    def answer(self, installed: bool, report: str) -> None:
        def stub(ctx, out):
            del ctx, out
            return installed, report

        sd_install.provision_library = stub

    def run_mode(self) -> tuple[int, str]:
        out = io.StringIO()
        code = sd_install.main(
            ["--provision-library", "--home", str(self.home)],
            environ={"SD_SYSTEM_CHECKOUT": str(self.home / "system")},
            out=out,
        )
        return code, out.getvalue()

    def test_a_machine_it_cannot_provision_exits_one_and_says_why(self) -> None:
        self.answer(False, "no library at /nowhere; sd_db is absent, trials unavailable")
        code, output = self.run_mode()
        self.assertEqual(code, 1)
        self.assertIn("sd_db is absent", output)

    def test_a_successful_provision_exits_zero_and_says_so(self) -> None:
        self.answer(True, "sd_db installed from /somewhere")
        code, output = self.run_mode()
        self.assertEqual(code, 0)
        self.assertIn("sd_db installed from", output)

    def test_the_exit_code_follows_the_flag_and_not_the_words(self) -> None:
        """The defect this replaced: the dispatch used to read its own prose.

        `"installed" in report` is true of "sd_db not installed", so the one
        machine the exit code exists for returned zero. A report whose words
        say the opposite of its flag pins that the words no longer decide.
        """
        self.answer(False, "sd_db installed from /somewhere")
        code, _ = self.run_mode()
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
