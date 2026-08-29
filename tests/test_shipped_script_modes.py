"""The shipped-script executable bit, observed on the real tree.

``tests/test_script_sibling_resolution.py`` builds its helpers and chmods them
``0o755`` before exercising ``run --``, so it asserts the *resolver* and can
never observe the mode of the thing resolved. This module covers the other
half:

* every shipped helper is actually reachable through
  ``sd-ai-command-pack-toolchain.sh run --`` in this checkout, enumerated from
  ``git ls-files templates/scripts`` rather than from a list written here;
* ``.github/scripts/check-shipped-script-modes.py`` fails in *both* directions
  when a synthetic index violates the invariant -- a gate that never fires
  looks exactly like a gate that passes, because the invariant holds.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path, PurePosixPath

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:  # pragma: no cover - import shim
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

PACK_ROOT = _support.PACK_ROOT
GATE = PACK_ROOT / ".github/scripts/check-shipped-script-modes.py"
TOOLCHAIN = PACK_ROOT / "templates/scripts/sd-ai-command-pack-toolchain.sh"

if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

# Imported, not restated, for the same reason the gate imports it: a second
# literal is a second place the rule can drift from the generators that
# actually derive the mode from it.
from installer.machinepayload import LIBRARY_PREFIX  # noqa: E402

# Every shipped helper rejects this and exits before doing any work, so the
# sweep observes reachability without running 25 tools for real.
BOGUS_FLAG = "--sd-bogus-flag"

UNREACHABLE = (
    "Permission denied",
    "pack helper is missing",
    "No such file or directory",
)


def git(*args: str, cwd: Path = PACK_ROOT) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


class ShippedHelpersAreReachableTest(unittest.TestCase):
    """`run --` reaches every shipped helper from this repository's own tree."""

    def test_every_shipped_helper_runs_through_the_toolchain(self) -> None:
        tracked = [
            PurePosixPath(line)
            for line in git("ls-files", "templates/scripts").splitlines()
            if line
        ]
        names = [
            path.name
            for path in tracked
            if not path.name.startswith(LIBRARY_PREFIX)
        ]
        self.assertTrue(names, "no shipped helpers enumerated from the index")

        # `run --` takes a helper *name*, not a path, so the sweep must operate
        # on basenames. That makes basename uniqueness load-bearing: two
        # tracked files sharing one would silently sweep the same helper twice
        # and never exercise the other. Assert it rather than assume it.
        counts = Counter(path.name for path in tracked)
        duplicates = sorted(name for name, n in counts.items() if n > 1)
        self.assertEqual(
            [], duplicates, "shipped helper basenames must be unique for `run --`"
        )

        unreachable: list[str] = []
        for name in names:
            result = subprocess.run(
                ["bash", str(TOOLCHAIN), "run", "--", name, BOGUS_FLAG],
                cwd=PACK_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            # A non-zero exit from a helper rejecting the flag is expected and
            # is not a failure; only a failure to *reach* the helper is.
            if any(marker in result.stderr for marker in UNREACHABLE):
                unreachable.append(f"{name}: {result.stderr.strip().splitlines()[-1]}")
        self.assertEqual([], unreachable)


class ShippedScriptModeGateTest(unittest.TestCase):
    """The gate fails on a violating index, in both directions."""

    def _repo(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="sd-modes-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        git("init", "-q", str(root), cwd=Path(tempfile.gettempdir()))
        (root / "templates/scripts").mkdir(parents=True)
        (root / ".github/scripts").mkdir(parents=True)
        shutil.copy2(GATE, root / ".github/scripts" / GATE.name)
        return root

    def _write(self, root: Path, name: str, mode: int) -> None:
        path = root / "templates/scripts" / name
        path.write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
        path.chmod(mode)
        git("add", "--chmod=" + ("+x" if mode & 0o111 else "-x"), str(path), cwd=root)

    def _run_gate(self, root: Path) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        # The gate imports LIBRARY_PREFIX from `installer.machinepayload`; the
        # synthetic repository has no installer package, so the real one is
        # reached through PYTHONPATH after the gate's own sys.path insert of
        # the synthetic root falls through.
        env["PYTHONPATH"] = os.pathsep.join(
            [str(PACK_ROOT), env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        return subprocess.run(
            [sys.executable, str(root / ".github/scripts" / GATE.name)],
            cwd=root,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_a_clean_tree_passes(self) -> None:
        root = self._repo()
        self._write(root, "sd-ai-command-pack-probe.sh", 0o755)
        self._write(root, f"{LIBRARY_PREFIX}probe.py", 0o644)

        result = self._run_gate(root)

        self.assertEqual(0, result.returncode, result.stderr)

    def test_a_non_executable_helper_fails(self) -> None:
        root = self._repo()
        self._write(root, "sd-ai-command-pack-probe.sh", 0o644)

        result = self._run_gate(root)

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("NOT-EXEC", result.stderr)
        self.assertIn("templates/scripts/sd-ai-command-pack-probe.sh", result.stderr)

    def test_an_executable_library_module_fails(self) -> None:
        root = self._repo()
        self._write(root, f"{LIBRARY_PREFIX}probe.py", 0o755)

        result = self._run_gate(root)

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("LIB-EXEC", result.stderr)
        self.assertIn(f"templates/scripts/{LIBRARY_PREFIX}probe.py", result.stderr)

    def test_a_file_without_a_shebang_is_ignored(self) -> None:
        root = self._repo()
        plain = root / "templates/scripts" / "notes.txt"
        plain.write_text("no shebang here\n", encoding="utf-8")
        git("add", str(plain), cwd=root)

        result = self._run_gate(root)

        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
