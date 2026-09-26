"""CI's `sd_db` pin carries the schema of the library this suite runs against.

sd:1381. `.github/workflows/tests.yml` checks out `platypeeps/system` at one
commit and installs `sd_db` from it, so CI is reproducible: a change over there
cannot move this suite under it. The cost is that nothing advanced the pin. It
sat at schema 10 while every machine ran schema 13, and CI was green about a
library nobody runs. `sd_db` refuses a database newer than itself, so nothing
crossed the versions inside CI and nothing went red.

This test is the alarm. It reads the pin's `SCHEMA_VERSION` through git and
compares it with the installed library's. Locally the venv is installed from
the system checkout (`make setup`), so a migration landed there and not in the
pin fails here, on the next `make check`. In CI the library comes from the pin,
so the comparison holds by construction; CI stays reproducible, and the
local gate carries the check.

Schema, not commit: a migration is what makes the two libraries disagree about
a database, and a commit count would fail on documentation changes.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import sd_install  # noqa: E402
import sd_library_guard  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
#: The `ref:` of the checkout step for `platypeeps/system`, comments allowed between.
PIN = re.compile(r"repository: platypeeps/system\n(?:[ \t]+(?:#.*|\w+: .*)\n)*?[ \t]+ref: (\S+)")


#: The one other system ref (sd:1542): the `sd-db-main-canary` job runs the
#: suite against system `main`, never as a gate, so a removed `sd_db` name
#: shows before the pin moves.
CANARY_REF = "main"


def pins(text: str) -> list[str]:
    """The pinned system refs: every checkout of it except the canary's."""
    return [ref for ref in PIN.findall(text) if ref != CANARY_REF]


def job_block(text: str, name: str) -> str:
    match = re.search(rf"^  {re.escape(name)}:\n((?:(?:    .*|[ \t]*)\n)*)", text, re.MULTILINE)
    return match.group(1) if match else ""


def pinned_schema(checkout: Path, ref: str) -> int | None:
    shown = subprocess.run(
        ["git", "-C", str(checkout), "show", f"{ref}:local-sd-db/sd_db/schema.py"],
        capture_output=True, text=True, check=False)
    return sd_library_guard.schema_version(shown.stdout) if shown.returncode == 0 else None


def installed_schema() -> int | None:
    spec = importlib.util.find_spec("sd_db")
    if spec is None or not spec.submodule_search_locations:
        return None
    schema = Path(next(iter(spec.submodule_search_locations))) / "schema.py"
    return sd_library_guard.schema_version(schema.read_text(encoding="utf-8"))


class ThePinIsReadable(unittest.TestCase):
    def test_the_workflow_names_one_full_commit(self):
        found = pins(WORKFLOW.read_text(encoding="utf-8"))
        self.assertEqual(len(found), 1, f"expected one platypeeps/system ref in {WORKFLOW}: {found}")
        self.assertRegex(found[0], r"^[0-9a-f]{40}$", "the pin is a full commit, not a branch or tag")

    def test_the_only_unpinned_system_ref_is_the_non_blocking_canary(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(PIN.findall(text).count(CANARY_REF), 1)
        canary = job_block(text, "sd-db-main-canary")
        self.assertIn(f"ref: {CANARY_REF}\n", canary)
        self.assertRegex(canary, r"(?m)^    continue-on-error: true$",
                         "a red canary must not block a merge")
        self.assertIn("bash .github/scripts/run-tests.sh", canary)

    def test_comments_between_repository_and_ref_are_skipped(self):
        text = ("          repository: platypeeps/system\n"
                "          # why\n"
                "          ref: " + "a" * 40 + "\n")
        self.assertEqual(pins(text), ["a" * 40])


class TheCanarySkipsNothing(unittest.TestCase):
    """sd:1557. The canary fails on a skipped test, as the unittest job does.

    Without the gate, a system `main` that loses a capability a test skips on
    leaves the canary green. Both jobs install opencode from one script, so its
    live test runs in each, and its version and checksum are written once.
    """

    INSTALL = "run: bash .github/scripts/install-opencode.sh\n"
    RUN = "run: bash .github/scripts/run-tests.sh\n"
    GATE = "- name: Fail on skipped tests\n"
    SKIPS = "grep -Eq 'skipped=[1-9][0-9]*' unittest-output.log"

    def test_each_suite_job_installs_opencode_runs_then_fails_on_skips(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for name in ("unittest", "sd-db-main-canary"):
            with self.subTest(job=name):
                job = job_block(text, name)
                self.assertEqual(job.count(self.INSTALL), 1, job)
                self.assertEqual(job.count(self.RUN), 1, job)
                self.assertEqual(job.count(self.GATE), 1, job)
                self.assertIn(self.SKIPS, job[job.index(self.GATE):])
                self.assertLess(job.index(self.INSTALL), job.index(self.RUN))
                self.assertLess(job.index(self.RUN), job.index(self.GATE))

    def test_the_opencode_version_and_checksum_are_written_once(self):
        definitions = re.compile(r"(?m)^\s*(OPENCODE_VERSION|OPENCODE_SHA256)\s*[:=]")
        found = sorted(
            (str(path.relative_to(ROOT)), name)
            for path in (ROOT / ".github").rglob("*")
            if path.is_file()
            for name in definitions.findall(path.read_text(encoding="utf-8", errors="replace")))
        self.assertEqual(found, [(".github/scripts/install-opencode.sh", "OPENCODE_SHA256"),
                                 (".github/scripts/install-opencode.sh", "OPENCODE_VERSION")])


class ThePinCarriesTheInstalledSchema(unittest.TestCase):
    def test_pin_schema_equals_installed_schema(self):
        ref = pins(WORKFLOW.read_text(encoding="utf-8"))[0]
        checkout = sd_install.system_checkout(dict(os.environ))
        installed = installed_schema()
        self.assertIsNotNone(installed, "no sd_db is installed here; run `make setup`")
        pinned = pinned_schema(checkout, ref)
        self.assertIsNotNone(
            pinned, f"cannot read SCHEMA_VERSION at {ref[:12]} in {checkout}; fetch that checkout")
        self.assertEqual(
            pinned, installed,
            f"CI installs sd_db schema {pinned} (platypeeps/system {ref[:12]}), but this suite "
            f"runs against schema {installed}. Move the ref in {WORKFLOW.relative_to(ROOT)} to "
            "the system commit this library came from, and record the move in the comment "
            "above it; or, if the pin is the newer one, reinstall with `make setup`.")


if __name__ == "__main__":
    unittest.main()
