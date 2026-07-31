"""Single-source check for the supported Python floor.

``pyproject.toml``'s ``project.requires-python`` is the declared floor. The
copies that still have to be written out by hand — the CI matrix floor leg and
the toolchain interpreter probe — are checked against it here so a floor bump
cannot leave a stale copy behind. Ruff needs no copy (it infers its target
from ``requires-python``), and mypy's ``python_version`` is intentionally not
asserted here because mypy rejects unsupported values on its own.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
TESTS_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tests.yml"
TOOLCHAIN = REPO_ROOT / "scripts" / "sd-ai-command-pack-toolchain.sh"


def declared_floor() -> tuple[int, int]:
    # Parsed with a regex instead of tomllib: the suite itself must run on
    # the declared floor, and tomllib only exists on Python 3.11+.
    text = PYPROJECT.read_text(encoding="utf-8")
    matches = re.findall(r'(?m)^requires-python\s*=\s*"([^"]*)"$', text)
    if len(matches) != 1:
        raise AssertionError(
            "pyproject.toml must declare requires-python exactly once, "
            f"found {len(matches)} declarations"
        )
    match = re.fullmatch(r">=\s*(\d+)\.(\d+)", matches[0])
    if match is None:
        raise AssertionError(
            "project.requires-python must be a plain '>=X.Y' floor, "
            f"got {matches[0]!r}"
        )
    return int(match.group(1)), int(match.group(2))


class PythonFloorTests(unittest.TestCase):
    def test_ci_matrix_floor_leg_matches_requires_python(self) -> None:
        floor = declared_floor()
        workflow = TESTS_WORKFLOW.read_text(encoding="utf-8")
        versions = {
            (int(major), int(minor))
            for major, minor in re.findall(
                r'python-version:\s*"(\d+)\.(\d+)"', workflow
            )
        }
        self.assertTrue(versions, "no quoted python-version pins found in tests.yml")
        self.assertIn(
            floor,
            versions,
            "the CI matrix no longer exercises the declared floor "
            f"{floor[0]}.{floor[1]} from pyproject.toml",
        )
        below = sorted(version for version in versions if version < floor)
        self.assertFalse(
            below,
            f"CI pins Python versions below the declared floor: {below}",
        )

    def test_toolchain_probe_matches_requires_python(self) -> None:
        major, minor = declared_floor()
        toolchain = TOOLCHAIN.read_text(encoding="utf-8")
        self.assertIn(
            f"sys.version_info < ({major}, {minor})",
            toolchain,
            "the toolchain interpreter probe does not reject versions below "
            f"the declared floor {major}.{minor}",
        )


if __name__ == "__main__":
    unittest.main()
