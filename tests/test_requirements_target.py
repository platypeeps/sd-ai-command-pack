"""The hash-pinned requirements resolve for the Python the project requires.

sd:1391. Each `requirements-*.txt` records the `uv pip compile` line that made
it, and its `--python-version` decides which releases the resolver may pin.
Both files said 3.10 after `pyproject.toml` raised `requires-python` to 3.13.
A ruff, mypy, bandit or zizmor release that needs 3.11 or later was then never
a candidate: the resolve kept the last 3.10-compatible one, `--require-hashes`
installed it, and the lint and audit gates stayed green on an older analyzer.

Recompiling fixes it once; this test keeps it fixed the next time the floor
moves. It enumerates the tracked requirements files instead of naming them.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

COMPILE_TARGET = re.compile(r"^#\s+uv pip compile\b.*?--python-version[ =](\S+)", re.MULTILINE)
FLOOR = re.compile(r"^\s*>=\s*(\d+\.\d+)\s*$")


def compile_target(text: str) -> str | None:
    """The `--python-version` of the `uv pip compile` header, or None."""

    found = COMPILE_TARGET.search(text)
    return found.group(1) if found else None


def python_floor(pyproject: str) -> str:
    """The `X.Y` of a `requires-python = ">=X.Y"`; anything else is refused."""

    spec = tomllib.loads(pyproject)["project"]["requires-python"]
    found = FLOOR.match(spec)
    if not found:
        raise ValueError(f"requires-python {spec!r} is not a single >=X.Y floor")
    return found.group(1)


def mismatches(floor: str, files: dict[str, str]) -> list[str]:
    """Each requirements file whose compile target is not `floor`, explained."""

    wrong = []
    for name, text in sorted(files.items()):
        target = compile_target(text)
        if target != floor:
            wrong.append(f"{name}: compiled for {target or 'no --python-version'}, "
                         f"requires-python floor is {floor}")
    return wrong


def tracked_requirements() -> dict[str, str]:
    names = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--deduplicate", "--", "requirements-*.txt"],
        check=True, capture_output=True, text=True).stdout.split()
    return {name: (REPO_ROOT / name).read_text(encoding="utf-8") for name in names}


class RequirementsTarget(unittest.TestCase):
    def test_every_requirements_file_resolves_for_the_python_floor(self) -> None:
        files = tracked_requirements()
        self.assertTrue(files, "no tracked requirements-*.txt; the check would pass over nothing")
        floor = python_floor((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(mismatches(floor, files), [],
                         "recompile with `uv pip compile --universal --generate-hashes "
                         f"--python-version {floor} <file> -o <file>`")

    def test_a_stale_or_missing_target_is_named(self) -> None:
        header = "#    uv pip compile --universal --generate-hashes --python-version {} r.txt -o r.txt\n"
        files = {"a.txt": header.format("3.10"), "b.txt": header.format("3.13"), "c.txt": "ruff==1\n"}
        self.assertEqual(mismatches("3.13", files), [
            "a.txt: compiled for 3.10, requires-python floor is 3.13",
            "c.txt: compiled for no --python-version, requires-python floor is 3.13",
        ])

    def test_a_floor_that_is_not_one_lower_bound_is_refused(self) -> None:
        self.assertEqual(python_floor('[project]\nrequires-python = ">=3.13"\n'), "3.13")
        with self.assertRaisesRegex(ValueError, "not a single"):
            python_floor('[project]\nrequires-python = ">=3.12,<4"\n')


if __name__ == "__main__":
    unittest.main()
