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
rows; the install case runs `make hooks` there and requires the relative
link, and a refusal when something else already holds the path.

The behavioural cases run the hook by path inside a throwaway repository, not
in this checkout: staging a file here would edit the index the developer is
working in, and the hook's two whole-tree test passes take five seconds each
run. The throwaway repository carries no `tests/`, so the hook reports those
passes as not run and the case asserts that line, which is the only place the
notice is exercised -- in this checkout both modules exist, and the first case
below pins that.
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
DESIGN = REPO_ROOT / "docs/work/2026-09-12-every-rule-is-a-row-and-a-checker/design.md"
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
        stated = BUDGET_LINE.search(text)
        self.assertIsNotNone(stated, "the header does not state `# Budget: N s wall on a one-file diff.`")
        assert stated is not None
        constant = CONSTANT_LINE.search(text)
        self.assertIsNotNone(constant, "the hook does not define BUDGET_SECONDS")
        assert constant is not None
        self.assertEqual(
            constant.group(1), stated.group(1),
            "the header's budget and BUDGET_SECONDS disagree",
        )
        self.assertIn(
            f"budgeted at {stated.group(1)} s",
            DESIGN.read_text(encoding="utf-8"),
            f"design.md does not budget the hook at {stated.group(1)} s",
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

    def _remove(self):
        subprocess.run(["rm", "-rf", str(self.root)], check=False)

    def stage(self, name: str, text: str) -> None:
        (self.root / name).write_text(text, encoding="utf-8")
        git("add", "--", name, cwd=self.root)

    def run_hook(self, **extra_env: str) -> subprocess.CompletedProcess[str]:
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("GIT_") and key != SKIP_VARIABLE}
        env.update(extra_env)
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
        self.assertIn("in this checkout; not run", output)


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
        self.assertIn(f"{link} -> {LINK_TARGET}", result.stdout)
        again = self.make_hooks()
        self.assertEqual(again.returncode, 0, "a second run over its own link must pass")

    def test_make_hooks_refuses_to_replace_a_file_that_is_not_its_link(self):
        link = self.root / ".git" / "hooks" / "pre-commit"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        result = self.make_hooks()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(str(link), result.stderr)
        self.assertFalse(link.is_symlink(), "the stranger was replaced")
        self.assertEqual(link.read_text(encoding="utf-8"), "#!/bin/sh\nexit 0\n")

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


if __name__ == "__main__":
    unittest.main()
