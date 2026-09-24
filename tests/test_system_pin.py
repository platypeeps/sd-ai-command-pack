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


def pins(text: str) -> list[str]:
    return PIN.findall(text)


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

    def test_comments_between_repository_and_ref_are_skipped(self):
        text = ("          repository: platypeeps/system\n"
                "          # why\n"
                "          ref: " + "a" * 40 + "\n")
        self.assertEqual(pins(text), ["a" * 40])


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
