"""AC4 boundary gate: git subprocess invocation is consolidated in the shared lib.

Two sound static (AST) checks over the shipped ``scripts/*.py`` surface:

* Check 1 — no script builds its own direct ``subprocess.run``/``Popen`` call on
  a git-argv literal except the shared library.
* Check 2 — none of the migrated files carry a git-argv literal at all, which
  also closes any ``run(["git", ...])`` indirection (a ``run`` wrapper that
  calls ``subprocess.run(list(argv))`` on a *variable* is something Check 1
  alone would miss).

Residual limit (deferred to human review): a brand-new self-wrapping script that
feeds git through a variable, or fully dynamic argv, escapes a static lint. The
two generic shared-env runners (pr-eligibility, status) are intentionally
allowed: they run a variable argv through the shared
environment, so git is incidental, not a hand-built git-specific environment.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "templates/scripts"
LIB_NAME = "sd_ai_command_pack_lib.py"

# The files migrated off hand-built git subprocess environments in A-076
# (fleet-publish was migrated too and has since been deleted).
MIGRATED_FILES = (
    "sd-ai-command-pack-review-local.py",
    "sd-ai-command-pack-surface-check.py",
    "sd-ai-command-pack-install-audit.py",
    "sd-ai-command-pack-work-loop.py",
    "sd-ai-command-pack-fleet-controller.py",
)

# The generic shared-env runners that legitimately pass a variable argv
# (git incidental) through the shared environment. Printed on failure to explain
# why they are not migration targets.
GENERIC_RUNNERS = {
    "sd-ai-command-pack-pr-eligibility.py": (
        "generic shared-env runner: variable argv through build_tool_environment"
    ),
    "sd-ai-command-pack-status.py": (
        "generic shared-env runner: variable argv through build_tool_environment"
    ),
}


def _is_git_argv_literal(node: ast.AST) -> bool:
    """A git-argv literal: ``["git", ...]`` / ``("git", ...)`` or ``["git"] + x``.

    Matches a list/tuple whose first element is the constant ``"git"``, or an
    addition whose left operand is such a list/tuple.
    """

    if isinstance(node, (ast.List, ast.Tuple)):
        return (
            bool(node.elts)
            and isinstance(node.elts[0], ast.Constant)
            and node.elts[0].value == "git"
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_git_argv_literal(node.left)
    return False


def _is_subprocess_run_or_popen(func: ast.AST) -> bool:
    """True for ``subprocess.run`` / ``subprocess.Popen`` attribute calls."""

    return (
        isinstance(func, ast.Attribute)
        and func.attr in {"run", "Popen"}
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
    )


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _first_command_arg(node: ast.Call) -> ast.AST | None:
    """The subprocess command argument, positional (args[0]) or keyword (args=)."""

    if node.args:
        return node.args[0]
    for keyword in node.keywords:
        if keyword.arg == "args":
            return keyword.value
    return None


def _direct_git_subprocess_calls(tree: ast.Module) -> list[int]:
    """Line numbers of subprocess.run/Popen calls whose command arg is git-argv.

    Covers both the positional first argument and the ``args=`` keyword form so
    ``subprocess.run(args=["git", ...])`` cannot slip past the gate.
    """

    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_subprocess_run_or_popen(node.func):
            continue
        command = _first_command_arg(node)
        if command is not None and _is_git_argv_literal(command):
            hits.append(node.lineno)
    return hits


def _any_git_argv_literal(tree: ast.Module) -> list[int]:
    """Line numbers of every git-argv literal anywhere in the module."""

    hits: list[int] = []
    for node in ast.walk(tree):
        if _is_git_argv_literal(node):
            hits.append(node.lineno)
    return hits


class GitInvocationBoundaryTest(unittest.TestCase):
    def test_direct_git_subprocess_only_in_lib(self) -> None:
        """Check 1: only the shared lib builds a direct git subprocess call."""

        offenders: dict[str, list[int]] = {}
        for path in sorted(SCRIPTS_DIR.glob("*.py")):
            if path.name == LIB_NAME:
                continue
            hits = _direct_git_subprocess_calls(_tree(path))
            if hits:
                offenders[path.name] = hits
        self.assertEqual(
            offenders,
            {},
            "Direct git subprocess.run/Popen calls must live only in "
            f"{LIB_NAME}; migrate these through run_git_minimal / "
            f"run_git_cached. Generic runners (not offenders): {GENERIC_RUNNERS}. "
            f"Offenders: {offenders}",
        )

    def test_migrated_files_have_no_git_literal(self) -> None:
        """Check 2: the migrated files carry no git-argv literal at all."""

        offenders: dict[str, list[int]] = {}
        for name in MIGRATED_FILES:
            path = SCRIPTS_DIR / name
            self.assertTrue(path.is_file(), f"missing migrated file: {name}")
            hits = _any_git_argv_literal(_tree(path))
            if hits:
                offenders[name] = hits
        self.assertEqual(
            offenders,
            {},
            "Migrated files must not embed a git-argv literal (closes "
            "run([\"git\", ...]) indirection); route git through the shared lib "
            f"helpers instead. Offenders: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
