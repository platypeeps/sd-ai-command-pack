"""The pre-commit tier of sd:431: `hooks/pre-commit`, installed by `make hooks`.

The hook is the tier that fires while the author is still in the file. Its
argument, from the item's design page, is that a hook slow enough to be
bypassed is an advisory rule in the costume of an enforced one, so the hook
carries a wall-time budget in its header and prints its own wall time on
exit. Three things are held here: the file is what git will run (tracked,
executable, its budget stated once and agreed with the design page), it
refuses a staged Python file Ruff rejects and names the file, and the named
escape hatch `SD_SKIP_HOOKS=1` skips it with a notice rather than in silence.

The layout is `hooks/pre-commit` linked from `.git/hooks/pre-commit`, never
`.githooks/` and never `core.hooksPath`: those two are the retired gate
stack's signatures, and `bin/sd-status` reports both as residue with a
removal command. A pack whose own hook matched its own residue detector would
be telling the operator to delete it. The residue case below runs that
detector over a checkout laid out this way and requires silence from both
rows; the install cases run `make hooks` there and require the relative
link `../../hooks/pre-commit` under the clone's common hooks directory (one
hook per clone, read from the main checkout, shared by every linked
worktree), a refusal when something else already holds the path, and a
`git commit` that fails through the link.

sd:1020 adds the fourth thing: an interpreter that cannot run the gates is its
own condition, `unchecked`, and not a verdict on the staged code. The cases
below hold the word, the refusal that still stands behind it, the linked
worktree that reaches the clone's provisioned `.venv` rather than a bare
`python3`, and the `.gitignore` pattern that hides the symlink such a worktree
used to be given by hand.

The behavioural cases run the hook by path inside a throwaway repository, not
in this checkout: staging a file here would edit the index the developer is
working in, and the hook's two whole-tree test passes take five seconds each
run. The throwaway repository carries the two passes as one-test stubs, so
the hook runs them in milliseconds; a named pass that is absent is a
failure, because a commit that deletes or renames one would otherwise pass
in silence, and the deletion case holds that.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / "hooks" / "pre-commit"
LINK_TARGET = "../../hooks/pre-commit"
POLICY = REPO_ROOT / "docs/current-architecture.md"
BUDGET_LINE = re.compile(r"^# Budget: (\d+) s wall on a one-file diff\.$", re.MULTILINE)
CONSTANT_LINE = re.compile(r"^BUDGET_SECONDS = (\d+)$", re.MULTILINE)
SKIP_VARIABLE = "SD_SKIP_HOOKS"


def git(*args: str, cwd: pathlib.Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


class TheHookFile(unittest.TestCase):
    def test_the_hook_is_tracked_executable_and_states_its_budget_once(self):
        self.assertTrue(HOOK.is_file(), f"{HOOK} is missing")
        mode = git("ls-files", "-s", "--", "hooks/pre-commit", cwd=REPO_ROOT)
        self.assertTrue(mode.startswith("100755 "), f"not tracked as executable: {mode!r}")
        self.assertTrue(os.access(HOOK, os.X_OK), "the hook is not executable on disk")
        text = HOOK.read_text(encoding="utf-8")
        stated = BUDGET_LINE.findall(text)
        self.assertEqual(
            len(stated), 1,
            f"the header must state `# Budget: N s wall on a one-file diff.` once, found {stated}",
        )
        constant = CONSTANT_LINE.findall(text)
        self.assertEqual(len(constant), 1, f"BUDGET_SECONDS must be defined once, found {constant}")
        self.assertEqual(constant[0], stated[0], "the header's budget and BUDGET_SECONDS disagree")
        self.assertIn(
            f"has an {stated[0]}-second wall-time budget",
            POLICY.read_text(encoding="utf-8"),
            f"current architecture does not budget the hook at {stated[0]} s",
        )

    def test_both_whole_tree_passes_the_hook_names_exist_here(self):
        """The `not run` notice is for a checkout without them, never this one."""
        self.assertTrue(HOOK.is_file(), f"{HOOK} is missing")
        text = HOOK.read_text(encoding="utf-8")
        found = re.search(r"^WHOLE_TREE_PASSES = \((.*)\)$", text, re.MULTILINE)
        self.assertIsNotNone(found, "the hook does not define WHOLE_TREE_PASSES")
        assert found is not None
        names = re.findall(r'"([\w.]+)"', found.group(1))
        self.assertTrue(names, "WHOLE_TREE_PASSES names nothing")
        for name in names:
            with self.subTest(module=name):
                self.assertTrue((REPO_ROOT / (name.replace(".", "/") + ".py")).is_file())


class TheHookRun(unittest.TestCase):
    """The hook by path in a throwaway repository, staged files under it."""

    def setUp(self):
        self.assertTrue(HOOK.is_file(), f"{HOOK} is missing")
        self.assertTrue(os.access(HOOK, os.X_OK), "the hook is not executable on disk")
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="sd-431-hook-"))
        self.addCleanup(self._remove)
        git("init", "-q", cwd=self.root)
        git("config", "user.email", "hook@example.invalid", cwd=self.root)
        git("config", "user.name", "hook", cwd=self.root)
        # The hook prefers `.venv/bin/python`; point it at the interpreter
        # running this suite, which is the one that has Ruff installed.
        (self.root / ".venv").symlink_to(pathlib.Path(sys.prefix))
        self.stub_passes()

    def _remove(self):
        subprocess.run(["rm", "-rf", str(self.root)], check=False)

    def stage(self, name: str, text: str) -> None:
        (self.root / name).write_text(text, encoding="utf-8")
        git("add", "--", name, cwd=self.root)

    def run_hook(self, **extra_env: str) -> subprocess.CompletedProcess[str]:
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("GIT_") and key != SKIP_VARIABLE}
        env.update(extra_env)
        env.setdefault("PATH", "")
        return subprocess.run(
            [str(HOOK)], cwd=self.root, env=env, capture_output=True, text=True, check=False
        )

    def test_a_staged_python_file_ruff_rejects_fails_the_commit_by_name(self):
        self.stage("bad.py", "import os\n")
        result = self.run_hook()
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("bad.py", output)
        self.assertIn("pre-commit: failed", output)

    def test_the_named_escape_hatch_skips_the_hook_with_a_notice(self):
        self.stage("bad.py", "import os\n")
        result = self.run_hook(**{SKIP_VARIABLE: "1"})
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn(f"pre-commit: skipped, {SKIP_VARIABLE}=1", output)

    def test_a_clean_staged_change_passes_and_reports_its_wall_time(self):
        self.stage("ok.py", "x = 1\n")
        result = self.run_hook()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertRegex(output, r"pre-commit: ok in \d+\.\d\d s \(budget \d+ s\)")
        self.assertIn("Ran 2 tests", output)

    def test_a_staged_path_fixed_in_the_working_tree_but_not_restaged_is_refused(self):
        """The gates read the working tree; the commit holds the index (#1014 review).

        Staging a bad file and then fixing it without `git add` would pass a
        hook that reads the working tree while the commit still carried the
        bad blob. The hook refuses the state by name instead.
        """
        self.stage("bad.py", "import os\n")
        (self.root / "bad.py").write_text("x = 1\n", encoding="utf-8")
        result = self.run_hook()
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("1 staged path(s) differ from the working tree", output)
        self.assertIn("bad.py", output)
        self.assertNotIn("F401", output, "Ruff ran on the working-tree copy")

    def stub_passes(self, failing: str | None = None) -> None:
        """The two whole-tree modules the hook names, as stubs, one failing if asked."""
        (self.root / "tests").mkdir(exist_ok=True)
        for name in ("test_code_health", "test_doc_citations"):
            verdict = "self.fail('stub red')" if name == failing else "pass"
            (self.root / "tests" / f"{name}.py").write_text(
                "import unittest\n\n\nclass Stub(unittest.TestCase):\n"
                f"    def test_stub(self):\n        {verdict}\n",
                encoding="utf-8",
            )

    def test_the_whole_tree_passes_run_when_their_modules_exist(self):
        self.stage("ok.py", "x = 1\n")
        result = self.run_hook()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("Ran 2 tests", output)
        self.assertNotIn("missing", output)

    def test_a_commit_that_deletes_a_whole_tree_pass_is_refused_by_name(self):
        """Deleted paths are not in `staged_paths()`, so only the module check sees this."""
        git("add", "--", "tests", cwd=self.root)
        git("commit", "-q", "-m", "stubs", cwd=self.root)
        git("rm", "-q", "--", "tests/test_doc_citations.py", cwd=self.root)
        result = self.run_hook()
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("tests.test_doc_citations", output)
        self.assertIn("missing", output)
        self.assertNotIn("Ran ", output, "a pass ran with one of the two missing")
        self.assertIn("pre-commit: failed, status 1", output)

    def test_a_python_shebang_past_128_bytes_still_names_python(self):
        """The same bound as `tests/test_code_health.py`: the whole first line, up to 4096."""
        shebang = "#!/usr/bin/env -S " + " " * 200 + "python3\n"
        self.stage("tool", shebang + "import os\n")
        result = self.run_hook()
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("F401", output)
        self.assertIn("tool", output)

    def test_a_long_shell_shebang_within_the_bound_is_not_sent_to_ruff(self):
        """A 128-byte window would cap this line and, failing closed, lint shell as Python."""
        self.stage("tool", "#!/bin/sh -" + " " * 200 + "\necho hi\n")
        result = self.run_hook()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn("tool", output, "the shell script was handed to Ruff")

    def test_a_capped_unterminated_shebang_is_treated_as_python(self):
        """4096 bytes with no newline is a prefix, not the line; fail closed as code health does."""
        self.stage("tool", "#!/usr/bin/env -S " + "x" * 5000 + "\nimport os\n")
        result = self.run_hook()
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("tool", output)

    def test_without_a_venv_the_hook_runs_ruff_and_the_passes_under_python3(self):
        """`interpreter()`'s fallback: `python3` first on PATH, a shim that execs this suite's."""
        (self.root / ".venv").unlink()
        shims = self.root / "shims"
        shims.mkdir()
        shim = shims / "python3"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
        shim.chmod(0o755)
        path = f"{shims}{os.pathsep}{os.environ.get('PATH', '')}"
        self.stage("bad.py", "import os\n")
        result = self.run_hook(PATH=path)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("F401", output, "Ruff did not run under the python3 fallback")
        self.stage("bad.py", "x = 1\n")
        result = self.run_hook(PATH=path)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("Ran 2 tests", output, "the passes did not run under the python3 fallback")

    def barren_venv(self) -> None:
        """Replace setUp's borrowed `.venv` with one that has no dev requirements.

        A real interpreter with an empty site-packages, which is what a clone
        nobody has run `make setup` in actually has; `--without-pip` keeps it
        to a fraction of a second.
        """
        (self.root / ".venv").unlink()
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(self.root / ".venv")],
            capture_output=True, text=True, check=True,
        )

    def test_an_unprovisioned_interpreter_is_unchecked_not_a_lint_verdict(self):
        """sd:1020. The staged file is clean, so a provisioned run says `ok`.

        Before this, an interpreter without Ruff reached the reader as
        `pre-commit: failed, status 1`, which is what Ruff rejecting the staged
        code looks like; on 2026-09-18 that read cost an `sd-review` pass and a
        commit that was rejected and then pushed as an empty branch. The word
        is `unchecked`, which is what `bin/sd-status` calls a class whose check
        could not run.
        """
        self.barren_venv()
        self.stage("ok.py", "x = 1\n")
        result = self.run_hook()
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, "the hook failed open: " + output)
        self.assertRegex(output, r"pre-commit: unchecked, status 1 in \d+\.\d\d s \(budget \d+ s\)")
        self.assertIn("cannot import ruff", output)
        self.assertIn("make setup", output)
        self.assertNotIn("pre-commit: failed", output, "an environment fault read as a verdict")
        self.assertNotIn("Ran ", output, "a whole-tree pass ran under an interpreter without Ruff")

    def test_a_red_whole_tree_pass_fails_the_commit_with_its_status(self):
        self.stub_passes(failing="test_doc_citations")  # overwrites setUp's green stubs
        self.stage("ok.py", "x = 1\n")
        result = self.run_hook()
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("stub red", output)
        self.assertIn("pre-commit: failed, status 1", output)


def scratch_checkout(prefix: str) -> pathlib.Path:
    """A repository laid out as this one is for hooks: `hooks/pre-commit` tracked."""
    root = pathlib.Path(tempfile.mkdtemp(prefix=prefix))
    git("init", "-q", cwd=root)
    git("config", "user.email", "hook@example.invalid", cwd=root)
    git("config", "user.name", "hook", cwd=root)
    (root / "hooks").mkdir()
    shutil.copy2(HOOK, root / "hooks" / "pre-commit")
    git("add", "--", "hooks/pre-commit", cwd=root)
    return root


def load_sd_status():
    """`bin/sd-status` as a module; it has no suffix, so by loader."""
    path = REPO_ROOT / "bin" / "sd-status"
    loader = importlib.machinery.SourceFileLoader("sd_status_for_hooks", str(path))
    spec = importlib.util.spec_from_file_location("sd_status_for_hooks", str(path), loader=loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sd_status_for_hooks"] = module
    loader.exec_module(module)
    return module


class TheLayout(unittest.TestCase):
    """`hooks/` plus a link under `.git/hooks`, which the residue detector ignores."""

    def setUp(self):
        self.assertTrue(HOOK.is_file(), f"{HOOK} is missing")
        self.root = scratch_checkout("sd-431-layout-")
        self.addCleanup(subprocess.run, ["rm", "-rf", str(self.root)], check=False)
        shutil.copy2(REPO_ROOT / "Makefile", self.root / "Makefile")

    def make_hooks(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["make", "hooks"], cwd=self.root, capture_output=True, text=True, check=False
        )

    def test_make_hooks_links_the_tracked_hook_relatively_and_says_where(self):
        result = self.make_hooks()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        link = self.root / ".git" / "hooks" / "pre-commit"
        self.assertTrue(link.is_symlink(), f"{link} is not a symlink")
        self.assertEqual(os.readlink(link), LINK_TARGET)
        self.assertTrue(link.resolve().samefile(self.root / "hooks" / "pre-commit"))
        self.assertIn(f"pre-commit -> {LINK_TARGET}", result.stdout)
        again = self.make_hooks()
        self.assertEqual(again.returncode, 0, "a second run over its own link must pass")

    def test_make_hooks_from_a_linked_worktree_installs_the_clone_wide_link(self):
        """One hook per clone: the link sits in the common `.git/hooks` and reads the main checkout's file."""
        git("add", "--", "Makefile", cwd=self.root)
        git("commit", "-q", "-m", "layout", cwd=self.root)
        worktree = self.root.parent / (self.root.name + "-wt")
        self.addCleanup(subprocess.run, ["rm", "-rf", str(worktree)], check=False)
        git("worktree", "add", "-q", "-b", "wt", str(worktree), cwd=self.root)
        result = subprocess.run(
            ["make", "hooks"], cwd=worktree, capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        link = self.root / ".git" / "hooks" / "pre-commit"
        self.assertTrue(link.is_symlink(), f"{link} is not under the main .git/hooks")
        self.assertEqual(os.readlink(link), LINK_TARGET)
        self.assertTrue(link.resolve().samefile(self.root / "hooks" / "pre-commit"),
                        "the link does not read the main checkout's hook")
        self.assertFalse((self.root / ".git" / "worktrees" / worktree.name / "hooks").exists(),
                         "a per-worktree hooks dir appeared")

    def test_a_commit_runs_the_hook_through_the_link(self):
        self.assertEqual(self.make_hooks().returncode, 0)
        (self.root / ".venv").symlink_to(pathlib.Path(sys.prefix))
        (self.root / "bad.py").write_text("import os\n", encoding="utf-8")
        git("add", "--", "bad.py", cwd=self.root)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("GIT_") and key != SKIP_VARIABLE}
        result = subprocess.run(
            ["git", "commit", "-q", "-m", "x"], cwd=self.root, env=env,
            capture_output=True, text=True, check=False,
        )
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, "the commit went through: " + output)
        self.assertIn("bad.py", output)
        self.assertIn("F401", output)
        self.assertEqual(git("log", "--oneline", "--all", cwd=self.root), "", "a commit landed")
        self.assertFalse((self.root / ".githooks").exists())

    def test_a_commit_from_a_linked_worktree_leaves_the_main_repository_a_work_tree(self):
        """sd:993. Git runs a linked worktree's hook with `GIT_DIR` and
        `GIT_INDEX_FILE` exported, and a whole-tree pass whose fixture runs
        `git init .` in a temporary directory then re-initialises the repository
        at `GIT_DIR`, which git guesses bare for a path not named `.git`
        (measured 2026-09-17 18:28Z on the pack checkout: `core.bare = true`,
        `sd-status` "not inside a git repository").
        The hook hands the passes an environment without git's per-invocation
        variables, so a fixture's git acts on the fixture."""
        self.assertEqual(self.make_hooks().returncode, 0)
        (self.root / ".venv").symlink_to(pathlib.Path(sys.prefix))
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_doc_citations.py").write_text(
            "import unittest\n\n\nclass Stub(unittest.TestCase):\n"
            "    def test_stub(self):\n        pass\n",
            encoding="utf-8",
        )
        (self.root / "tests" / "test_code_health.py").write_text(
            "import subprocess\nimport tempfile\nimport unittest\n\n\n"
            "class Fixture(unittest.TestCase):\n"
            "    def test_a_fixture_repository(self):\n"
            "        subprocess.run(['git', 'init', '-q', '-b', 'main', '.'], cwd=tempfile.mkdtemp(), check=True)\n",
            encoding="utf-8",
        )
        git("add", "--", "tests", cwd=self.root)
        git("commit", "-q", "-m", "layout", cwd=self.root)
        worktree = self.root.parent / (self.root.name + "-wt")
        self.addCleanup(subprocess.run, ["rm", "-rf", str(worktree)], check=False)
        git("worktree", "add", "-q", "-b", "wt", str(worktree), cwd=self.root)
        (worktree / ".venv").symlink_to(pathlib.Path(sys.prefix))
        (worktree / "ok.py").write_text("x = 1\n", encoding="utf-8")
        git("add", "--", "ok.py", cwd=worktree)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("GIT_") and key != SKIP_VARIABLE}
        result = subprocess.run(
            ["git", "commit", "-q", "-m", "from the worktree"], cwd=worktree, env=env,
            capture_output=True, text=True, check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("Ran 2 tests", output)
        self.assertEqual(git("config", "--get", "core.bare", cwd=self.root).strip(), "false",
                         "the pass's fixture re-initialised the main repository as bare")
        self.assertEqual(git("rev-parse", "--is-inside-work-tree", cwd=self.root).strip(), "true")
        self.assertEqual(git("log", "--oneline", "wt", cwd=self.root).count("\n"), 2)

    def test_a_linked_worktree_runs_the_gates_under_the_clones_provisioned_venv(self):
        """sd:1020. One `.venv` per clone, in the main checkout, as with the hook.

        The worktree gets none of its own. `python3` on PATH is shadowed here by
        an interpreter with an empty site-packages -- the hook's own shebang
        resolves through it, so it has to start, it just has no Ruff -- and a
        run that reaches Ruff at all reached it through
        `git rev-parse --git-common-dir` and the main checkout's `.venv`.
        """
        (self.root / ".venv").symlink_to(pathlib.Path(sys.prefix))
        (self.root / "tests").mkdir()
        for name in ("test_code_health", "test_doc_citations"):
            (self.root / "tests" / f"{name}.py").write_text(
                "import unittest\n\n\nclass Stub(unittest.TestCase):\n"
                "    def test_stub(self):\n        pass\n",
                encoding="utf-8",
            )
        git("add", "--", "tests", cwd=self.root)
        git("commit", "-q", "-m", "layout", cwd=self.root)
        worktree = self.root.parent / (self.root.name + "-wt")
        self.addCleanup(subprocess.run, ["rm", "-rf", str(worktree)], check=False)
        git("worktree", "add", "-q", "-b", "wt", str(worktree), cwd=self.root)
        self.assertFalse((worktree / ".venv").exists(), "the worktree was given a venv")
        barren = self.root / "barren"
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(barren)],
            capture_output=True, text=True, check=True,
        )
        shims = self.root / "shims"
        shims.mkdir()
        (shims / "python3").write_text(
            f'#!/bin/sh\nexec "{barren / "bin" / "python"}" "$@"\n', encoding="utf-8")
        (shims / "python3").chmod(0o755)
        (worktree / "bad.py").write_text("import os\n", encoding="utf-8")
        git("add", "--", "bad.py", cwd=worktree)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("GIT_") and key != SKIP_VARIABLE}
        env["PATH"] = f"{shims}{os.pathsep}{os.environ.get('PATH', '')}"
        result = subprocess.run(
            [str(HOOK)], cwd=worktree, env=env, capture_output=True, text=True, check=False,
        )
        output = result.stdout + result.stderr
        self.assertNotIn("unchecked", output, "the worktree fell back to a bare python3")
        self.assertIn("F401", output, "Ruff did not run from the clone's provisioned venv")
        self.assertIn("bad.py", output)

    def test_make_hooks_refuses_to_replace_a_file_that_is_not_its_link(self):
        link = self.root / ".git" / "hooks" / "pre-commit"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        result = self.make_hooks()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(".git/hooks/pre-commit exists and is not the link", result.stderr)
        self.assertFalse(link.is_symlink(), "the stranger was replaced")
        self.assertEqual(link.read_text(encoding="utf-8"), "#!/bin/sh\nexit 0\n")

    def test_make_hooks_refuses_while_core_hooks_path_is_set(self):
        git("config", "core.hooksPath", ".githooks", cwd=self.root)
        result = self.make_hooks()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("core.hooksPath is set to .githooks", result.stderr)
        self.assertIn("git config --unset core.hooksPath", result.stderr)
        self.assertFalse((self.root / ".git" / "hooks" / "pre-commit").exists(), "a link was made")
        self.assertFalse((self.root / ".githooks").exists(), "a link was made under the stale path")

    def test_the_residue_detector_reports_neither_githooks_nor_hooks_path(self):
        self.assertEqual(self.make_hooks().returncode, 0)
        status = load_sd_status()
        found = {entry["id"] for entry in status.residue_section(self.root)}
        self.assertNotIn("githooks", found, "the pack's own hook reads as the retired stack's")
        self.assertNotIn("hooks-path", found, "the install set core.hooksPath")
        probe = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"], cwd=self.root,
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(probe.returncode, 1, f"core.hooksPath is set: {probe.stdout!r}")


class TheBorrowedVenvIsIgnored(unittest.TestCase):
    """The clone's `.venv` reaches a worktree as a symlink, which `.venv/` missed.

    `.venv/` is directory-only, so the symlink a worktree gets showed as an
    untracked path and dirtied `git status` for everyone working there
    (sd:1020). The pattern is `.venv`, which covers both.
    """

    def test_a_venv_symlink_is_ignored_the_way_a_venv_directory_is(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="sd-1020-ignore-"))
        self.addCleanup(subprocess.run, ["rm", "-rf", str(root)], check=False)
        git("init", "-q", cwd=root)
        shutil.copy2(REPO_ROOT / ".gitignore", root / ".gitignore")
        (root / "provisioned").mkdir()
        (root / ".venv").symlink_to(root / "provisioned")
        untracked = git("status", "--porcelain", "--untracked-files=all", cwd=root)
        self.assertNotIn(".venv", untracked, f"a .venv symlink is not ignored: {untracked!r}")


if __name__ == "__main__":
    unittest.main()
