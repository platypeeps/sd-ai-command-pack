"""Provisioning must preserve a newer or uninspectable installed library."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sd_library_guard", ROOT / "bin/sd_library_guard.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class LibraryDowngradeGuard(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.package = self.root / ".venv/lib/python3.13/site-packages/sd_db"
        self.schema = self.package / "schema.py"

    def installed(self, source="SCHEMA_VERSION = 3\n"):
        self.package.mkdir(parents=True, exist_ok=True)
        self.schema.write_text(source, encoding="utf-8")

    def check(self, candidate):
        calls = []

        def read_git(args, cwd):
            calls.append((args, cwd))
            return candidate

        refusal = guard.downgrade_refusal(self.root, self.root / "system", "abc123", read_git)
        for args, cwd in calls:
            self.assertEqual(args, ["show", "abc123:local-sd-db/sd_db/schema.py"])
            self.assertEqual(cwd, self.root / "system")
        return refusal

    def test_single_literal_versions_allow_equal_or_newer_but_refuse_downgrade(self):
        self.installed()
        self.assertIn("schema 3", self.check("SCHEMA_VERSION = 2\n"))
        self.assertEqual(self.check("SCHEMA_VERSION = 3\n"), "")
        self.assertEqual(self.check("SCHEMA_VERSION = 4\n"), "")

    def test_ambiguous_version_reassignment_cannot_hide_a_downgrade(self):
        self.installed()
        for source in ("SCHEMA_VERSION = 3\nSCHEMA_VERSION = 2\n",
                       "SCHEMA_VERSION = 3\nif True:\n    SCHEMA_VERSION = 2\n",
                       "SCHEMA_VERSION = 3\nSCHEMA_VERSION -= 1\n"):
            with self.subTest(source=source):
                self.assertTrue(self.check(source))

    def test_missing_candidate_and_malformed_or_nonliteral_versions_fail_closed(self):
        self.installed()
        for source in ("", "SCHEMA_VERSION =", "SCHEMA_VERSION = True\n",
                       "SCHEMA_VERSION = '3'\n", "SCHEMA_VERSION = 0\n",
                       "SCHEMA_VERSION = make_version()\n"):
            with self.subTest(source=source):
                self.assertTrue(self.check(source))

    def test_git_read_failure_returns_a_refusal_and_preserves_installed_schema(self):
        self.installed()
        before = self.schema.read_bytes()
        self.assertIn("cannot verify", self.check(None))
        self.assertEqual(self.schema.read_bytes(), before)

    def test_existing_package_without_schema_is_preserved_not_treated_as_first_install(self):
        self.package.mkdir(parents=True)
        (self.package / "__init__.py").write_text("# Installed package with damaged metadata\n")
        self.assertTrue(self.check("SCHEMA_VERSION = 2\n"))

    def test_invalid_utf8_installed_metadata_returns_a_refusal_without_raising(self):
        self.installed()
        self.schema.write_bytes(b"\xff\xfe")
        self.assertTrue(self.check("SCHEMA_VERSION = 2\n"))
        self.assertEqual(self.schema.read_bytes(), b"\xff\xfe")

    def test_malformed_installed_source_is_preserved(self):
        self.installed("SCHEMA_VERSION = nope(\n")
        self.assertTrue(self.check("SCHEMA_VERSION = 3\n"))

    def test_first_install_with_no_package_remains_available(self):
        self.assertEqual(self.check("SCHEMA_VERSION = 3\n"), "")

    def test_multiple_installed_python_versions_use_highest_and_refuse_partial_metadata(self):
        self.installed("SCHEMA_VERSION = 2\n")
        second = self.root / ".venv/lib/python3.14/site-packages/sd_db"
        second.mkdir(parents=True)
        (second / "schema.py").write_text("SCHEMA_VERSION = 4\n")
        self.assertIn("schema 4", self.check("SCHEMA_VERSION = 3\n"))
        (second / "schema.py").unlink()
        self.assertTrue(self.check("SCHEMA_VERSION = 3\n"))


if __name__ == "__main__":
    unittest.main()
