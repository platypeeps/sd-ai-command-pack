"""Gate mode (sd:1918): under `SD_LOCAL_GATE=1` the Makefile provisions, never borrows.

`bin/sd_local_gate.py` exports the variable; `.github/scripts/provision-gate-env.py`
builds the in-tree environment, with `sd_db` from the worktree's own `lib/` (sd:3278). The dry runs here read what `make`
would do and build nothing; the script is driven only down its refusals.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "provision-gate-env.py"

spec = importlib.util.spec_from_file_location("provision_gate_env", SCRIPT)
assert spec and spec.loader
provision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provision)


def dry_run(target: str, **env: str) -> str:
    environ = {key: value for key, value in os.environ.items() if key not in ("SD_LOCAL_GATE", "VENV")}
    done = subprocess.run(["make", "-n", "--no-print-directory", target], cwd=REPO_ROOT, capture_output=True,
                          text=True, check=True, env={**environ, **env})
    return done.stdout


class TheMakefile(unittest.TestCase):
    def test_gate_mode_provisions_first_and_uses_the_worktrees_own_venv(self) -> None:
        lines = dry_run("lint", SD_LOCAL_GATE="1", VENV="/elsewhere/.venv").splitlines()
        self.assertIn("provision-gate-env.py", lines[0])
        self.assertTrue(lines[1].startswith('".venv/bin/python" -m ruff check'), lines[1])

    def test_every_lane_waits_for_the_environment(self) -> None:
        for lane in ("lint", "audit", "docs-lint", "test"):
            with self.subTest(lane=lane):
                self.assertIn("provision-gate-env.py", dry_run(lane, SD_LOCAL_GATE="1").splitlines()[0])

    def test_outside_the_gate_nothing_is_provisioned(self) -> None:
        self.assertNotIn("provision-gate-env.py", dry_run("lint", VENV="/elsewhere/.venv"))
        self.assertIn('"/elsewhere/.venv/bin/python" -m ruff', dry_run("lint", VENV="/elsewhere/.venv"))


class TheLibrary(unittest.TestCase):
    """sd:3278. The gate tests the worktree's own `lib/`; no system checkout, no pin file."""

    def test_the_gate_installs_sd_db_from_the_worktrees_own_lib(self) -> None:
        seen: list[list[str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            venv = pathlib.Path(tmp) / ".venv"
            venv.mkdir()
            with mock.patch.object(provision, "VENV", venv), \
                    mock.patch.object(provision, "require_opencode", return_value="opencode"), \
                    mock.patch.object(provision, "clear_venv"), \
                    mock.patch.object(provision, "run", side_effect=seen.append), \
                    mock.patch("sys.stdout"):
                self.assertEqual(provision.main(["provision-gate-env.py", sys.executable]), 0)
            marker = (venv / provision.MARKER).read_text(encoding="utf-8")
        self.assertEqual(seen[-1][-1], str(REPO_ROOT / "lib"))
        self.assertEqual([argv for argv in seen if "local-sd-db" in " ".join(argv)], [])
        self.assertTrue(marker.startswith("sd_db lib/"), marker)

    def test_the_pin_file_is_gone(self) -> None:
        self.assertFalse((REPO_ROOT / ".sd-system-rev").exists())


class TheOpencodePinIsWrittenOnce(unittest.TestCase):
    """sd:1557. The opencode version and checksum live in one script."""

    def test_the_opencode_version_and_checksum_are_written_once(self) -> None:
        definitions = re.compile(r"(?m)^\s*(OPENCODE_VERSION|OPENCODE_SHA256)\s*[:=]")
        found = sorted(
            (str(path.relative_to(REPO_ROOT)), name)
            for path in (REPO_ROOT / ".github").rglob("*")
            if path.is_file()
            for name in definitions.findall(path.read_text(encoding="utf-8", errors="replace")))
        self.assertEqual(found, [(".github/scripts/install-opencode.sh", "OPENCODE_SHA256"),
                                 (".github/scripts/install-opencode.sh", "OPENCODE_VERSION")])


class TheRefusals(unittest.TestCase):
    def test_without_opencode_the_gate_fails_naming_the_installer(self) -> None:
        done = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False,
                              env={**os.environ, "PATH": "/nonexistent"})
        self.assertEqual(done.returncode, 1)
        self.assertIn("install-opencode.sh", done.stderr)

    def test_a_linked_or_foreign_venv_is_refused_and_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "real").mkdir()
            (root / "real" / "keep").write_text("operator's\n", encoding="utf-8")
            (root / "link").symlink_to(root / "real")
            for name, words in (("link", "is a link"), ("real", "not a gate environment")):
                with self.subTest(name=name), mock.patch.object(provision, "VENV", root / name):
                    with self.assertRaisesRegex(provision.GateError, words):
                        provision.clear_venv()
            self.assertTrue((root / "real" / "keep").is_file())

    def test_a_gate_environment_is_rebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            venv = pathlib.Path(tmp) / ".venv"
            venv.mkdir()
            # The marker an older gate wrote, naming a system ref: still a gate environment.
            (venv / provision.MARKER).write_text("sd_db sd-db-v0.1.0\n", encoding="utf-8")
            with mock.patch.object(provision, "VENV", venv):
                provision.clear_venv()
            self.assertFalse(venv.exists())


if __name__ == "__main__":
    unittest.main()
