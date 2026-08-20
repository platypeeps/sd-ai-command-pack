"""Staged acceptance tests for developer-identity resolution in worktrees.

**Staged, not collected.** This file deliberately sits in the task's
``research/`` rather than ``tests/``: the behavior it asserts lives in vendored
Trellis code (``.trellis/scripts/``) that this repository does not edit, the fix
is implemented in the Trellis fork but carries no release, so every behavioral
test here skips against the vendored copy — and ``Makefile:49`` fails the repo
gate on *any* skip. Weakening that gate to house a suite waiting on someone
else's release is the wrong trade, so the suite waits outside it.

Run it by hand, from the repository root:

    .venv/bin/python .trellis/tasks/08-08-developer-identity-not-in-worktrees/\
      research/staged_test_worktree_identity.py -v

    SD_DEVELOPER_IDENTITY_SCRIPTS=/tmp/upstream/scripts \
      .venv/bin/python <same path> -v

Two rules keep it honest:

* The skip gate probes the **behavior** through a throwaway fixture, never a
  symbol name. Upstream is free to implement this under any helper it likes.
* ``SD_DEVELOPER_IDENTITY_SCRIPTS`` points the suite at a scripts directory
  where the behavior exists — a copy of upstream's tree, or a patched one. That
  is the run that proves anything.

At uptake — a vendored refresh carrying the fallback — move this file to
``tests/test_developer_identity.py`` and confirm it runs with zero skips. Only
then does it belong to the gate. The permanent, never-skipping half of the
original suite already lives there.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

# repo/.trellis/tasks/<task>/research/<this file>
ROOT = Path(__file__).resolve().parents[4]
VENDORED_SCRIPTS = ROOT / ".trellis/scripts"
SCRIPTS = Path(os.environ.get("SD_DEVELOPER_IDENTITY_SCRIPTS") or VENDORED_SCRIPTS)

GIT_ENV = {
    "GIT_AUTHOR_NAME": "sd-ai-command-pack tests",
    "GIT_AUTHOR_EMAIL": "tests@example.invalid",
    "GIT_COMMITTER_NAME": "sd-ai-command-pack tests",
    "GIT_COMMITTER_EMAIL": "tests@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}

# The resolver consults TRELLIS_DEVELOPER ahead of every file, so an operator who
# has it exported would make the behavioral gate resolve their own name and skip
# the whole suite for a reason unrelated to the fallback. Scrub it once, here, and
# let only the test that is about the override put it back.
BASE_ENV = {k: v for k, v in os.environ.items() if k != "TRELLIS_DEVELOPER"}


def child_env(*overrides: dict[str, str]) -> dict[str, str]:
    env = {**BASE_ENV, **GIT_ENV}
    for override in overrides:
        env.update(override)
    return env


def git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        env=child_env(),
    )


def git_supports_relative_paths() -> bool:
    helped = subprocess.run(
        ["git", "worktree", "add", "-h"], capture_output=True, text=True, check=False
    )
    # Git prints the negatable spelling, `--[no-]relative-paths`, so match the
    # option name rather than a leading `--`.
    return "relative-paths" in (helped.stdout + helped.stderr)


class DeveloperIdentityFixture(unittest.TestCase):
    """A throwaway primary checkout plus linked worktrees, and nothing else.

    The developer's real ``.trellis/.developer`` is never read and never
    written: every path here lives under one temporary directory.
    """

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="sd-developer-identity-")
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name).resolve()

    # -- fixture construction ------------------------------------------------

    def make_primary(self, name: str | None = "primary-dev", *, slug: str = "primary") -> Path:
        primary = self.root / slug
        (primary / ".trellis").mkdir(parents=True, exist_ok=True)
        git("init", "--quiet", str(primary), cwd=self.root)
        # The real repository gitignores the identity, which is the whole reason
        # a worktree never receives it. A fixture that commits the file would
        # make every test below pass for the wrong reason.
        (primary / ".trellis/.gitignore").write_text(".developer\n", encoding="utf-8")
        (primary / "seed.txt").write_text("seed\n", encoding="utf-8")
        git("add", "--all", cwd=primary)
        git("commit", "--quiet", "--message", "seed", cwd=primary)
        if name is not None:
            self.write_identity(primary, f"name={name}\n")
            self.assertEqual(
                git("check-ignore", "--verbose", ".trellis/.developer", cwd=primary).returncode,
                0,
            )
        return primary

    def add_worktree(self, primary: Path, slug: str, *, relative: bool = False) -> Path:
        worktree = self.root / slug
        args = ["worktree", "add", "--quiet"]
        if relative:
            args.append("--relative-paths")
        args += [str(worktree), "--detach", "HEAD"]
        git(*args, cwd=primary)
        self.addCleanup(
            lambda: git("worktree", "remove", "--force", str(worktree), cwd=primary, check=False)
        )
        return worktree

    def make_primary_and_worktree(
        self, *, name: str = "primary-dev", slug: str = "primary"
    ) -> tuple[Path, Path]:
        primary = self.make_primary(name, slug=slug)
        return primary, self.add_worktree(primary, f"{slug}-worktree")

    def write_identity(self, root: Path, contents: str) -> Path:
        path = root / ".trellis/.developer"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        return path

    # -- running the vendored (or overridden) scripts -------------------------

    def run_python(self, source: str, *, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", "-c", textwrap.dedent(source)],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=child_env({"PYTHONPATH": str(SCRIPTS)}),
        )

    def run_script(self, script: str, *args: str, cwd: Path, env: dict[str, str] | None = None):
        return subprocess.run(
            ["python3", str(SCRIPTS / script), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=child_env(env or {}),
        )

    def resolved_developer(self, root: Path, *, env: dict[str, str] | None = None):
        """``get_developer(root)`` as the resolver itself answers it."""
        completed = subprocess.run(
            [
                "python3",
                "-c",
                "import json,sys;from common.paths import get_developer;"
                "print(json.dumps(get_developer(__import__('pathlib').Path(sys.argv[1]))))",
                str(root),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env=child_env({"PYTHONPATH": str(SCRIPTS)}, env or {}),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    # -- the behavior gate ---------------------------------------------------

    def require_worktree_fallback(self) -> None:
        """Skip while the resolved scripts still cannot see the main checkout.

        Behavioral on purpose: a symbol probe would keep skipping forever if
        upstream implemented the fallback inside ``get_developer`` itself, or
        named its helper something else. The failure mode here is a skip, never
        a pass.
        """
        _, worktree = self.make_primary_and_worktree(name="probe-dev", slug="probe")
        if self.resolved_developer(worktree) != "probe-dev":
            self.skipTest(
                "resolved Trellis scripts do not fall back to the main working "
                f"tree ({SCRIPTS}); upstream handoff pending"
            )


class WorktreeResolutionTests(DeveloperIdentityFixture):
    def test_a_fresh_worktree_resolves_the_primary_identity(self) -> None:
        self.require_worktree_fallback()
        primary, worktree = self.make_primary_and_worktree(name="fresh-dev")
        self.assertFalse((worktree / ".trellis/.developer").exists())

        completed = self.run_script("get_developer.py", cwd=worktree)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "fresh-dev")
        self.assertEqual(
            self.run_script("get_developer.py", cwd=primary).stdout.strip(), "fresh-dev"
        )

    def test_a_fresh_worktree_emits_no_diagnostic(self) -> None:
        self.require_worktree_fallback()
        _, worktree = self.make_primary_and_worktree(name="quiet-dev")

        completed = self.run_script("get_developer.py", cwd=worktree)

        self.assertEqual(completed.stderr, "")

    def test_a_local_identity_takes_precedence(self) -> None:
        self.require_worktree_fallback()
        _, worktree = self.make_primary_and_worktree(name="primary-dev")
        self.write_identity(worktree, "name=local-dev\n")

        self.assertEqual(self.resolved_developer(worktree), "local-dev")

    def test_an_unusable_local_file_falls_back(self) -> None:
        self.require_worktree_fallback()
        _, worktree = self.make_primary_and_worktree(name="primary-dev")

        self.write_identity(worktree, "nothing here resembles a name field\n")
        self.assertEqual(self.resolved_developer(worktree), "primary-dev")

        unreadable = self.write_identity(worktree, "name=unreadable\n")
        unreadable.chmod(0o000)
        self.addCleanup(unreadable.chmod, 0o600)
        if os.access(unreadable, os.R_OK):  # root, or a filesystem without modes
            self.skipTest("cannot make a file unreadable in this environment")
        self.assertEqual(self.resolved_developer(worktree), "primary-dev")

    def test_an_empty_name_is_unusable(self) -> None:
        self.require_worktree_fallback()
        _, worktree = self.make_primary_and_worktree(name="primary-dev")

        for contents in ("name=\n", "name=   \n"):
            with self.subTest(contents=contents):
                self.write_identity(worktree, contents)
                self.assertEqual(self.resolved_developer(worktree), "primary-dev")

        lonely = self.make_primary(None, slug="lonely")
        self.write_identity(lonely, "name=\n")
        self.assertIsNone(self.resolved_developer(lonely))
        checked = self.run_python(
            """
            import pathlib, sys
            from common.paths import check_developer
            print(check_developer(pathlib.Path(sys.argv[0]).parent))
            """,
            cwd=lonely,
        )
        self.assertEqual(checked.stdout.strip(), "False", checked.stderr)

    def test_the_environment_override_outranks_both_files(self) -> None:
        self.require_worktree_fallback()
        primary, worktree = self.make_primary_and_worktree(name="primary-dev")
        self.write_identity(worktree, "name=local-dev\n")

        env = {"TRELLIS_DEVELOPER": "env-dev"}
        if self.resolved_developer(primary, env=env) != "env-dev":
            self.skipTest(
                "resolved Trellis scripts ignore TRELLIS_DEVELOPER; the override "
                "arrived with the same upstream work as the fallback"
            )

        self.assertEqual(self.resolved_developer(worktree, env=env), "env-dev")

        # Value equality alone cannot show the files went unread, and neither can
        # unreadability: `_read_developer_file` swallows OSError and returns None,
        # so a resolver that read both files and then preferred the environment
        # would pass either check. What this asserts is the observable part —
        # the answer does not depend on the files' contents or even on their
        # being readable, and no diagnostic leaks out. Proving non-consultation
        # itself needs syscall tracing, which this suite deliberately does not do.
        for root in (worktree, primary):
            unreadable = root / ".trellis/.developer"
            unreadable.chmod(0o000)
            self.addCleanup(unreadable.chmod, 0o600)
        if os.access(worktree / ".trellis/.developer", os.R_OK):
            self.skipTest("cannot make a file unreadable in this environment")

        self.assertEqual(self.resolved_developer(worktree, env=env), "env-dev")
        quiet = self.run_script("get_developer.py", cwd=worktree, env=env)
        self.assertEqual(quiet.stdout.strip(), "env-dev")
        self.assertEqual(quiet.stderr, "")

    def test_get_developer_itself_resolves_through_the_fallback(self) -> None:
        self.require_worktree_fallback()
        _, worktree = self.make_primary_and_worktree(name="api-dev")

        self.assertEqual(self.resolved_developer(worktree), "api-dev")

    def test_moved_and_relative_worktrees_still_resolve(self) -> None:
        self.require_worktree_fallback()
        primary = self.make_primary("moved-dev")

        moved_from = self.add_worktree(primary, "before-move")
        moved_to = self.root / "after-move"
        git("worktree", "move", str(moved_from), str(moved_to), cwd=primary)
        self.assertEqual(self.resolved_developer(moved_to), "moved-dev")

        if not git_supports_relative_paths():
            self.skipTest("git worktree add has no --relative-paths (pre-2.48)")
        relative = self.add_worktree(primary, "relative", relative=True)
        self.assertEqual(self.resolved_developer(relative), "moved-dev")

    def test_add_session_runs_in_a_fresh_worktree(self) -> None:
        self.require_worktree_fallback()
        primary = self.make_primary(None, slug="session")
        shutil.copytree(SCRIPTS, primary / ".trellis/scripts", dirs_exist_ok=True)
        # Real repositories reach a worktree with the workspace tracked and the
        # identity ignored, so init the identity for real and commit what Git
        # would carry: the journal travels, `.developer` does not.
        initialized = self.run_script("init_developer.py", "session-dev", cwd=primary)
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
        git("add", "--all", cwd=primary)
        git("commit", "--quiet", "--message", "vendor scripts and workspace", cwd=primary)
        worktree = self.add_worktree(primary, "session-worktree")
        self.assertFalse((worktree / ".trellis/.developer").exists())

        completed = self.run_script(
            "add_session.py",
            "--title",
            "staged acceptance run",
            "--summary",
            "records a session from a linked worktree",
            "--no-commit",
            cwd=worktree,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        journals = sorted((worktree / ".trellis/workspace/session-dev").glob("journal-*.md"))
        self.assertTrue(journals, "no journal was written for the resolved identity")
        self.assertIn(
            "staged acceptance run",
            "".join(path.read_text(encoding="utf-8") for path in journals),
        )


if __name__ == "__main__":
    unittest.main()
