"""The gate's `sd_db` pin carries the schema of the library this suite runs against.

sd:1381. `.sd-system-rev` names one `platypeeps/system` commit or release tag,
and the local gate installs `sd_db` from it
(`.github/scripts/provision-gate-env.py`), so the gate is reproducible: a change over there
cannot move this suite under it. The cost is that nothing advanced the pin. It
sat at schema 10 while every machine ran schema 13, and the retired CI was
green about a library nobody runs. `sd_db` refuses a database newer than
itself, so nothing crossed the versions there and nothing went red.

This test is the alarm for a library older than the pin. It reads the pin's
`SCHEMA_VERSION` through git and requires the installed library's to be at
least that. A newer installed library passes (sd:3013): the system checkout
moving ahead of the pin is normal, and an equality check forced a pin pull
request for each migration. In the local gate the library comes from the pin,
so the comparison holds by construction there.

Schema, not commit: a migration is what makes the two libraries disagree about
a database, and a commit count would fail on documentation changes.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import sd_install  # noqa: E402
import sd_library_guard  # noqa: E402

#: One line: the `platypeeps/system` ref the gate installs `sd_db` from.
PIN_FILE = ROOT / ".sd-system-rev"


#: What the pin may be (sd:1854): a full commit, or a release tag of the
#: library -- the same `sd-db-v*` pattern the installer prefers, so a tag cut
#: for another tool in that monorepo is not accepted as `sd_db`'s version.
#: Both are immutable; the tag is the readable name for the same promise.
TAG_PREFIX: str = sd_install.LIBRARY_TAGS.rstrip("*")
PIN_FORM = re.compile(r"^(?:[0-9a-f]{40}|" + re.escape(TAG_PREFIX) + r"\d+(?:\.\d+)*)$")


def pin() -> str:
    """The one ref `.sd-system-rev` holds."""
    return PIN_FILE.read_text(encoding="utf-8").strip()


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
    def test_the_pin_file_holds_one_full_commit_or_release_tag(self):
        lines = PIN_FILE.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1, f"expected one platypeeps/system ref in {PIN_FILE}: {lines}")
        self.assertRegex(lines[0], PIN_FORM,
                         "the pin is a full commit or an sd-db-v* release tag, not a branch")

    def test_a_release_tag_is_a_pin(self):
        for ref in ("sd-db-v0.1.0", "sd-db-v1.2", "sd-db-v10"):
            with self.subTest(ref=ref):
                self.assertRegex(ref, PIN_FORM)

    def test_a_branch_a_short_commit_or_another_tool_s_tag_is_not(self):
        for ref in ("main", "5fb29ef2", "sd-db-v", "sd-db-vnext", "sd-db-v1.2-rc1",
                    "local-ha-mcp-v1.0", "v0.1.0"):
            with self.subTest(ref=ref):
                self.assertNotRegex(ref, PIN_FORM)

    def test_a_tag_pin_reads_its_schema_through_git(self):
        """`pinned_schema` takes any ref git resolves, so a tag reads like a commit."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                   "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
            schema = repo / "local-sd-db" / "sd_db" / "schema.py"
            schema.parent.mkdir(parents=True)
            schema.write_text("SCHEMA_VERSION = 15\n", encoding="utf-8")
            for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "one"],
                         ["tag", "-a", "sd-db-v0.1.0", "-m", "sd-db 0.1.0"]):
                subprocess.run(["git", "-C", str(repo), *args], check=True, env=env,
                               capture_output=True)
            self.assertEqual(pinned_schema(repo, "sd-db-v0.1.0"), 15)


class TheOpencodePinIsWrittenOnce(unittest.TestCase):
    """sd:1557. The opencode version and checksum live in one script."""

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
    def test_installed_schema_is_not_older_than_the_pin(self):
        ref = pin()
        checkout = sd_install.system_checkout(dict(os.environ))
        installed = installed_schema()
        self.assertIsNotNone(installed, "no sd_db is installed here; run `make setup`")
        pinned = pinned_schema(checkout, ref)
        self.assertIsNotNone(
            pinned, f"cannot read SCHEMA_VERSION at {ref[:12]} in {checkout}; fetch that checkout")
        self.assertGreaterEqual(
            installed, pinned,
            f"The gate installs sd_db schema {pinned} (platypeeps/system {ref[:12]}), but this "
            f"suite runs against the older schema {installed}. Reinstall with `make setup`.")


class ANewerInstalledLibraryPasses(unittest.TestCase):
    """sd:3013. A system checkout that moved past the pin is no failure; a library older than the pin is."""

    def passes(self, offset: int) -> bool:
        pinned = pinned_schema(sd_install.system_checkout(dict(os.environ)), pin())
        self.assertIsNotNone(pinned, "cannot read the pin's SCHEMA_VERSION; fetch the system checkout")
        result = unittest.TestResult()
        with mock.patch.object(sys.modules[__name__], "installed_schema", return_value=pinned + offset):
            unittest.defaultTestLoader.loadTestsFromTestCase(ThePinCarriesTheInstalledSchema).run(result)
        return result.wasSuccessful()

    def test_a_newer_installed_schema_passes_and_an_older_one_fails(self):
        self.assertEqual((self.passes(1), self.passes(-1)), (True, False))


if __name__ == "__main__":
    unittest.main()
