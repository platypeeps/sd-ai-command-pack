"""Layout-independent helper resolution for every shipped pack script.

Two halves, matching the two ways the contract can break:

* A static gate over ``templates/scripts/**`` (the canonical payload) that
  enumerates every repository-root ``scripts/sd-ai-command-pack-*`` literal and
  compares it against an explicit allowlist. Everything on the allowlist is
  *data* — consumer-layout globs, changed-path classification, pack-source-only
  gates, generated-file provenance, a lint directive — never a path a script
  builds to reach a sibling helper. A new functional site therefore fails here
  until it is either converted to own-location resolution or justified.
* Behavioral tests for ``sd-ai-command-pack-toolchain.sh``: a pack-script
  operand resolves against the toolchain's own directory (bare or
  ``scripts/``-prefixed), never against the working directory, so a consumer
  repository cannot shadow a pack helper. Non-pack operands pass through.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:  # pragma: no cover - import shim
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase
TEMPLATE_SCRIPTS = PACK_ROOT / "templates/scripts"
TOOLCHAIN = TEMPLATE_SCRIPTS / "sd-ai-command-pack-toolchain.sh"

PACK_PATH_LITERAL = re.compile(r"scripts/sd[-_]ai[-_]command[-_]pack[A-Za-z0-9_.*-]*")

# filename -> (justification, literals that may appear in it).
#
# Every entry is semantic data about some *other* filesystem: a consumer
# repository being audited, a changed-path set being classified, the pack source
# repository's own tree, or a comment consumed by a linter. None of them
# resolves a helper this script then runs.
ALLOWED_LITERALS: dict[str, tuple[str, frozenset[str]]] = {
    "sd-ai-command-pack-check.py": (
        "remediation prose: the one remaining literal is the command text a "
        "human is told to run, printed in a row's remediation field. Resolution "
        "itself is converted and goes through shipped_helper_path(), which "
        "reads the consumer's own thin pin and leaves the repository only for "
        "a converted install",
        frozenset({"scripts/sd-ai-command-pack-update-spec-kb.py"}),
    ),
    "sd-ai-command-pack-full-check.sh": (
        "pack-source-only release gate: the fleet candidate checker has no "
        "manifest row and only ever runs inside the pack source repository, "
        "whose own tree is the correct anchor",
        frozenset({"scripts/sd-ai-command-pack-fleet-candidate-check.py"}),
    ),
    "sd-ai-command-pack-housekeeping.sh": (
        "shellcheck source= directive: a static-analysis annotation, not a "
        "runtime path (the runtime load uses $SCRIPT_DIR)",
        frozenset({"scripts/sd-ai-command-pack-shell-lib.sh"}),
    ),
    "sd-ai-command-pack-install-audit.py": (
        "consumer-layout data: the audit describes where a vendored install "
        "puts payload files in the repository it inspects",
        frozenset(
            {
                "scripts/sd-ai-command-pack-",
                "scripts/sd-ai-command-pack-*",
                "scripts/sd-ai-command-pack-fleet-candidate-check.py",
                "scripts/sd-ai-command-pack-fleet-controller.py",
                "scripts/sd-ai-command-pack-fleet-finding-classify.py",
                "scripts/sd-ai-command-pack-fleet-preflight.py",
                "scripts/sd-ai-command-pack-fleet-publish.py",
                "scripts/sd-ai-command-pack-fleet-review-classify.py",
                "scripts/sd-ai-command-pack-fleet-timing.py",
                "scripts/sd-ai-command-pack-fleet-wave-plan.py",
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/sd-ai-command-pack-housekeeping.sh",
                "scripts/sd-ai-command-pack-thin-resweep.py",
                "scripts/sd_ai_command_pack_fleet_lib.py",
                "scripts/sd_ai_command_pack_lib.py",
            }
        ),
    ),
    "sd-ai-command-pack-pr-body-scope.py": (
        "consumer-layout data: region globs classify changed paths in the "
        "repository whose PR body is being scoped",
        frozenset(
            {
                "scripts/sd-ai-command-pack-*.mjs",
                "scripts/sd-ai-command-pack-*.py",
                "scripts/sd-ai-command-pack-*.sh",
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/sd-ai-command-pack-housekeeping.sh",
                "scripts/sd-ai-command-pack-install-audit.py",
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "scripts/sd-ai-command-pack-review-learnings.py",
                "scripts/sd-ai-command-pack-review-scope.sh",
                "scripts/sd-ai-command-pack-shell-lib.sh",
                "scripts/sd_ai_command_pack_*.py",
                "scripts/sd_ai_command_pack_lib.py",
            }
        ),
    ),
    "sd-ai-command-pack-review-learnings.py": (
        "changed-path classification: payload prefixes used to recognize pack "
        "files in a diff",
        frozenset(
            {"scripts/sd-ai-command-pack-", "scripts/sd_ai_command_pack_"}
        ),
    ),
    "sd-ai-command-pack-review-preflight.mjs": (
        "changed-path classification: copiedTemplateKind recognizes vendored "
        "payload paths in a diff",
        frozenset(
            {
                "scripts/sd-ai-command-pack-",
                "scripts/sd-ai-command-pack-review-scope.sh",
            }
        ),
    ),
    "sd-ai-command-pack-surface-check.py": (
        "pack-source-only validator: every path names the pack source "
        "repository's own tree, which is always a full checkout",
        frozenset(
            {
                "scripts/sd-ai-command-pack-fleet-candidate-check.py",
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/sd-ai-command-pack-surface-check.py",
            }
        ),
    ),
    "sd-ai-command-pack-toolchain.sh": (
        "repository-state report: doctor tells the operator whether the "
        "repository it inspects carries a vendored full-check",
        frozenset({"scripts/sd-ai-command-pack-full-check.sh"}),
    ),
    "sd-ai-command-pack-update-spec-kb.py": (
        "generated-file provenance: the banner written into generated KB files "
        "names the generator by its canonical repository path",
        frozenset({"scripts/sd-ai-command-pack-update-spec-kb.py"}),
    ),
    "sd_ai_command_pack_fleet_lib.py": (
        "release-evidence layout data: CANDIDATE_VALIDATOR_SOURCES names the "
        "candidate validator's path in the pack source repository's own tree, "
        "the one tree a candidate ledger is ever recorded against. It is never "
        "resolved against this file's location -- the digest takes a "
        "caller-supplied loader so the same names can be read from a working "
        "tree or from a git commit's blobs",
        frozenset({"scripts/sd-ai-command-pack-fleet-candidate-check.py"}),
    ),
}

# Scripts whose sibling resolution this change converted, with the own-location
# idiom each one must keep.
OWN_LOCATION_IDIOMS = {
    "sd-ai-command-pack-toolchain.sh": '"$SCRIPT_DIR/$name"',
    "sd-ai-command-pack-full-check.sh": '"$SCRIPT_DIR/$name"',
    "sd-ai-command-pack-review-full-check.sh": '"$SCRIPT_DIR/sd-ai-command-pack-toolchain.sh"',
    "sd-ai-command-pack-review.py": 'Path(__file__).resolve().with_name(',
    "sd-ai-command-pack-review-preflight.mjs": "dirname(fileURLToPath(import.meta.url))",
}


def _matches(text: str) -> set[str]:
    # A literal ending a sentence keeps its period out of the match.
    return {match.rstrip(".") for match in PACK_PATH_LITERAL.findall(text)}


def _python_literals(path: Path) -> set[str]:
    """Every pack path literal reachable as a Python string constant."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.update(_matches(node.value))
    return found


def _text_literals(path: Path) -> set[str]:
    return _matches(path.read_text(encoding="utf-8"))


class ShippedScriptSiblingBoundaryTest(unittest.TestCase):
    def test_no_shipped_script_builds_siblings_from_repo_root_literals(self) -> None:
        """Every remaining repo-root pack literal is allowlisted data."""

        offenders: dict[str, list[str]] = {}
        # Recursive on purpose: the payload is flat today, but a future
        # subdirectory must not silently escape the gate.
        for path in sorted(TEMPLATE_SCRIPTS.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix == ".py":
                found = _python_literals(path)
            else:
                found = _text_literals(path)
            if not found:
                continue
            allowed = ALLOWED_LITERALS.get(path.name, ("", frozenset()))[1]
            unexpected = sorted(found - allowed)
            if unexpected:
                offenders[path.name] = unexpected

        self.assertEqual(
            offenders,
            {},
            "shipped scripts must resolve pack helpers against their own file "
            "location (Path(__file__), $SCRIPT_DIR from BASH_SOURCE, "
            "import.meta.url), not a repository-root scripts/ literal. Convert "
            "the site, or add it to ALLOWED_LITERALS with a written "
            f"justification if it is layout data. Offenders: {offenders}",
        )

    def test_allowlist_has_no_stale_entries(self) -> None:
        """A converted site must leave the allowlist, or the gate rots."""

        stale: dict[str, list[str]] = {}
        for name, (_justification, allowed) in ALLOWED_LITERALS.items():
            path = TEMPLATE_SCRIPTS / name
            self.assertTrue(path.is_file(), f"allowlisted script is missing: {name}")
            found = _python_literals(path) if path.suffix == ".py" else _text_literals(path)
            unused = sorted(allowed - found)
            if unused:
                stale[name] = unused
        self.assertEqual(stale, {}, f"remove converted literals from the allowlist: {stale}")

    def test_every_allowlist_entry_carries_a_justification(self) -> None:
        for name, (justification, _allowed) in ALLOWED_LITERALS.items():
            with self.subTest(script=name):
                self.assertGreater(len(justification.split()), 5, name)

    def test_converted_scripts_keep_their_own_location_idiom(self) -> None:
        for name, idiom in OWN_LOCATION_IDIOMS.items():
            with self.subTest(script=name):
                source = (TEMPLATE_SCRIPTS / name).read_text(encoding="utf-8")
                self.assertIn(idiom, source)

    def test_root_mirrors_match_the_canonical_templates(self) -> None:
        """The gate covers the shipped payload only if the mirrors agree."""

        for name in sorted(OWN_LOCATION_IDIOMS):
            with self.subTest(script=name):
                self.assertEqual(
                    (PACK_ROOT / "scripts" / name).read_bytes(),
                    (TEMPLATE_SCRIPTS / name).read_bytes(),
                )


class ToolchainOperandResolutionTest(InstallTestCase):
    """`run`/`run-python` resolve pack operands next to the toolchain only."""

    def setUp(self) -> None:
        super().setUp()
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

    def _layout(self) -> tuple[Path, Path, Path]:
        """A pack directory, a decoy repository, and the copied toolchain."""

        temporary = tempfile.TemporaryDirectory(prefix="sd-sibling-resolution-")
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        pack = base / "pack"
        pack.mkdir()
        toolchain = pack / TOOLCHAIN.name
        toolchain.write_bytes(TOOLCHAIN.read_bytes())
        toolchain.chmod(0o755)
        # The toolchain loads its cache helper from its own directory already;
        # the fixture has to satisfy that to reach operand resolution.
        lib = TEMPLATE_SCRIPTS / "sd_ai_command_pack_lib.py"
        (pack / lib.name).write_bytes(lib.read_bytes())

        repo = base / "repo"
        (repo / "scripts").mkdir(parents=True)
        return pack, repo, toolchain

    def _run(
        self, toolchain: Path, repo: Path, *args: str
    ) -> subprocess.CompletedProcess[str]:
        cache = repo.parent / "cache"
        cache.mkdir(mode=0o700, exist_ok=True)
        return subprocess.run(
            [self._bash_path, str(toolchain), *args],
            cwd=repo,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "SD_AI_COMMAND_PACK_PYTHON": sys.executable,
                "SD_AI_COMMAND_PACK_CACHE_ROOT": str(cache),
                "SD_AI_COMMAND_PACK_REPO_ROOT": str(repo),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _plant(self, pack: Path, repo: Path, name: str) -> None:
        """The real helper next to the toolchain, a decoy in the repository."""

        (pack / name).write_text("print('pack helper')\n", encoding="utf-8")
        (repo / "scripts" / name).write_text("print('repo decoy')\n", encoding="utf-8")

    def test_bare_pack_name_resolves_next_to_the_toolchain(self) -> None:
        pack, repo, toolchain = self._layout()
        self._plant(pack, repo, "sd-ai-command-pack-probe.py")

        result = self._run(
            toolchain, repo, "run-python", "--", "sd-ai-command-pack-probe.py"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "pack helper")

    def test_scripts_prefixed_pack_path_ignores_the_working_directory(self) -> None:
        """The decoy under the repository's scripts/ must never win."""

        pack, repo, toolchain = self._layout()
        self._plant(pack, repo, "sd-ai-command-pack-probe.py")

        result = self._run(
            toolchain,
            repo,
            "run-python",
            "--",
            "scripts/sd-ai-command-pack-probe.py",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "pack helper")

    def test_underscore_library_names_resolve_the_same_way(self) -> None:
        pack, repo, toolchain = self._layout()
        self._plant(pack, repo, "sd_ai_command_pack_probe.py")

        result = self._run(
            toolchain, repo, "run-python", "--", "sd_ai_command_pack_probe.py"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "pack helper")

    def test_non_pack_operands_pass_through_unchanged(self) -> None:
        pack, repo, toolchain = self._layout()
        (repo / "scripts" / "workload.py").write_text(
            "print('repo workload')\n", encoding="utf-8"
        )
        (pack / "workload.py").write_text("print('pack workload')\n", encoding="utf-8")

        relative = self._run(toolchain, repo, "run-python", "--", "scripts/workload.py")
        self.assertEqual(relative.returncode, 0, relative.stderr)
        self.assertEqual(relative.stdout.strip(), "repo workload")

        absolute = self._run(
            toolchain, repo, "run-python", "--", str(pack / "workload.py")
        )
        self.assertEqual(absolute.returncode, 0, absolute.stderr)
        self.assertEqual(absolute.stdout.strip(), "pack workload")

        stdin = subprocess.run(
            [
                self._bash_path,
                str(toolchain),
                "run-python",
                "--",
                "-",
            ],
            cwd=repo,
            input="print('stdin workload')\n",
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "SD_AI_COMMAND_PACK_PYTHON": sys.executable,
                "SD_AI_COMMAND_PACK_CACHE_ROOT": str(repo.parent / "cache"),
                "SD_AI_COMMAND_PACK_REPO_ROOT": str(repo),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(stdin.returncode, 0, stdin.stderr)
        self.assertEqual(stdin.stdout.strip(), "stdin workload")

    def test_missing_pack_helper_fails_with_a_resolved_diagnostic(self) -> None:
        pack, repo, toolchain = self._layout()
        # Only the repository decoy exists: resolution must still fail closed.
        (repo / "scripts" / "sd-ai-command-pack-probe.py").write_text(
            "print('repo decoy')\n", encoding="utf-8"
        )

        result = self._run(
            toolchain,
            repo,
            "run-python",
            "--",
            "scripts/sd-ai-command-pack-probe.py",
        )

        self.assertEqual(result.returncode, 127, result.stdout)
        self.assertIn("pack helper is missing next to the toolchain", result.stderr)
        self.assertIn(str(pack / "sd-ai-command-pack-probe.py"), result.stderr)
        self.assertNotIn("repo decoy", result.stdout)

    def test_run_resolves_a_pack_command_next_to_the_toolchain(self) -> None:
        pack, repo, toolchain = self._layout()
        helper = pack / "sd-ai-command-pack-probe.sh"
        helper.write_text("#!/usr/bin/env bash\nprintf 'pack helper\\n'\n", encoding="utf-8")
        helper.chmod(0o755)
        decoy = repo / "scripts" / "sd-ai-command-pack-probe.sh"
        decoy.write_text("#!/usr/bin/env bash\nprintf 'repo decoy\\n'\n", encoding="utf-8")
        decoy.chmod(0o755)

        result = self._run(toolchain, repo, "run", "--", "sd-ai-command-pack-probe.sh")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "pack helper")

    def test_run_leaves_ordinary_tools_alone(self) -> None:
        pack, repo, toolchain = self._layout()

        result = self._run(toolchain, repo, "run", "--", "printf", "%s", "plain tool")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "plain tool")


if __name__ == "__main__":
    unittest.main()
