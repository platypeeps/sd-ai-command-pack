"""A merge that touches `local-sd-db` re-provisions `sd_db` at the merge commit (sd:2108).

The dashboard refuses to start when the pack's installed `sd_db` lacks the
system checkout's last library commit, and nothing installed one between the
merge and the next restart: the restart failed until somebody ran
`make setup` in the pack. The operator ruled on 2026-09-30 that `sd-ship`
re-provisions after merging a pull request that touches `local-sd-db`.

`provision_library` is the installer's one install path; these tests replace
it with a recorder, so nothing reaches pip.
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

BIN = pathlib.Path(__file__).resolve().parent.parent / "bin"
sys.path.insert(0, str(BIN))

import sd_install  # noqa: E402

SCHEMA = "local-sd-db/sd_db/schema.py"


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


class ReprovisionAfterMerge(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.system = pathlib.Path(temp.name).resolve() / "system"
        self.system.mkdir()
        git(self.system, "init", "-q", "-b", "main")
        git(self.system, "config", "user.email", "test@example.test")
        git(self.system, "config", "user.name", "Test")
        self.commit("README.md")
        self.commit(SCHEMA, "SCHEMA_VERSION = 3\n")
        # The database the schema check reads lives under the test's own home, at schema 3.
        self.home = self.system.parent / "home"
        self.database = sd_install.sibling("sd_lib").import_sd_db().module.default_path(self.home)
        self.database_at(3)
        home = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        home.start()
        self.addCleanup(home.stop)
        # The provisioning lock lives under the state home: the test's own.
        self.environ = {sd_install.SYSTEM_CHECKOUT_ENV: str(self.system),
                        "XDG_STATE_HOME": str(self.system.parent / "state")}
        # A pack of the test's own, so the developer's virtualenv is never read.
        self.pack = self.system.parent / "pack"
        self.calls: list[str | None] = []

        def provision(ctx, out, ref=None):
            self.calls.append(ref)
            return True, f"sd_db installed at {ref}"
        patcher = mock.patch.object(sd_install, "provision_library", provision)
        patcher.start()
        self.addCleanup(patcher.stop)

    def commit(self, name: str, text: str | None = None) -> str:
        path = self.system / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text is not None else f"{name}\n", encoding="utf-8")
        git(self.system, "add", name)
        git(self.system, "commit", "-q", "-m", f"touch {name}")
        return git(self.system, "rev-parse", "HEAD")

    def database_at(self, version: int) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database)
        try:
            connection.execute(f"PRAGMA user_version = {int(version)}")
        finally:
            connection.close()

    def test_a_merge_touching_the_library_installs_the_merge_commit(self) -> None:
        merged = self.commit("local-sd-db/sd_db/writing.py")
        result = sd_install.reprovision_after_merge(self.system, merged, self.environ, pack=self.pack)
        self.assertEqual(self.calls, [merged])
        self.assertEqual(result, {"ref": merged, "installed": True, "report": f"sd_db installed at {merged}"})

    def test_a_merge_elsewhere_in_the_system_repository_installs_nothing(self) -> None:
        merged = self.commit("local-redis/redis.sh")
        self.assertIsNone(sd_install.reprovision_after_merge(self.system, merged, self.environ, pack=self.pack))
        self.assertEqual(self.calls, [])

    def test_another_repository_installs_nothing(self) -> None:
        merged = self.commit("local-sd-db/sd_db/writing.py")
        other = {sd_install.SYSTEM_CHECKOUT_ENV: str(self.system.parent / "elsewhere")}
        self.assertIsNone(sd_install.reprovision_after_merge(self.system, merged, other, pack=self.pack))
        self.assertEqual(self.calls, [])

    def test_a_worktree_of_the_system_checkout_counts_as_the_system_repository(self) -> None:
        worktree = self.system.parent / "system-topic"
        git(self.system, "worktree", "add", "-q", "-b", "topic", str(worktree))
        merged = self.commit("local-sd-db/pyproject.toml")
        sd_install.reprovision_after_merge(worktree, merged, self.environ, pack=self.pack)
        self.assertEqual(self.calls, [merged])


class SchemaChangeWaitsForMigrate(ReprovisionAfterMerge):
    """A merge that changes `SCHEMA_VERSION` installs nothing until the database is migrated (sd:3249).

    Installing it left the database one version behind the library, and every
    database command refused until somebody stopped the services and migrated
    by hand. A schema that cannot be read on either side is unknown, not a match.
    """

    def test_a_merge_that_bumps_the_schema_installs_nothing_and_names_the_migrate_steps(self) -> None:
        merged = self.commit(SCHEMA, "SCHEMA_VERSION = 4\n")
        result = sd_install.reprovision_after_merge(self.system, merged, self.environ, pack=self.pack)
        self.assertEqual((self.calls, result["installed"]), ([], False))
        self.assertIn(f"{merged} builds schema 4 and the database is at schema 3", result["report"])
        for step in ("repo-sync.sh refresh", "sd-serve", "sd-db.sh backup", "sd-db.sh migrate"):
            self.assertIn(step, result["report"])

    def test_a_library_merge_that_keeps_the_schema_still_installs(self) -> None:
        merged = self.commit(SCHEMA, "SCHEMA_VERSION = 3\nTABLES = ()\n")
        result = sd_install.reprovision_after_merge(self.system, merged, self.environ, pack=self.pack)
        self.assertEqual((self.calls, result["installed"]), ([merged], True))

    def test_a_merge_older_than_the_database_installs_nothing(self) -> None:
        self.database_at(4)
        merged = self.commit("local-sd-db/sd_db/writing.py")
        result = sd_install.reprovision_after_merge(self.system, merged, self.environ, pack=self.pack)
        self.assertEqual((self.calls, result["installed"]), ([], False))
        self.assertIn(f"{merged} builds schema 3, older than the database's schema 4", result["report"])

    def test_an_unreadable_schema_at_the_merge_installs_nothing(self) -> None:
        merged = self.commit(SCHEMA, "SCHEMA_VERSION = next\n")
        result = sd_install.reprovision_after_merge(self.system, merged, self.environ, pack=self.pack)
        self.assertEqual((self.calls, result["installed"]), ([], False))
        self.assertIn(f"cannot read SCHEMA_VERSION at {merged}", result["report"])

    def test_an_unreadable_database_installs_nothing(self) -> None:
        self.database.unlink()
        merged = self.commit("local-sd-db/sd_db/writing.py")
        result = sd_install.reprovision_after_merge(self.system, merged, self.environ, pack=self.pack)
        self.assertEqual((self.calls, result["installed"]), ([], False))
        self.assertIn("cannot read the database's schema version", result["report"])

    def test_a_database_newer_than_the_installed_library_is_still_read(self) -> None:
        """The installed copy refuses the open with `SchemaTooNew`, which names the version it found."""
        newer = sd_install.sibling("sd_lib").import_sd_db().module.SCHEMA_VERSION + 1
        self.database_at(newer)
        merged = self.commit(SCHEMA, f"SCHEMA_VERSION = {newer}\n")
        sd_install.reprovision_after_merge(self.system, merged, self.environ, pack=self.pack)
        self.assertEqual(self.calls, [merged])

    def test_a_pack_without_sd_db_reports_why_it_cannot_read_the_schema(self) -> None:
        missing = mock.Mock(module=None, problem="sd_db is not installed")
        with mock.patch.object(sd_install, "sibling", return_value=mock.Mock(import_sd_db=lambda: missing)):
            self.assertEqual(sd_install.database_schema(self.home), (None, "sd_db is not installed"))

    def test_a_schema_read_that_fails_after_the_open_reports_why(self) -> None:
        sd_db = sd_install.sibling("sd_lib").import_sd_db().module
        with mock.patch.object(sd_db, "schema_version", side_effect=sqlite3.DatabaseError("disk I/O error")):
            self.assertEqual(sd_install.database_schema(self.home), (None, "disk I/O error"))


class NoAncestryDowngrade(ReprovisionAfterMerge):
    """A late reconcile must not replace a newer installed `sd_db` (sd:2108 review).

    The downgrade guard compares schema numbers only, so two library merges
    under one schema pass it in either order. Reconciling the older merge after
    the newer one was installed would put the older code back.
    """

    def install_record(self, commit: str) -> pathlib.Path:
        """A pack whose virtualenv holds `sd_db` installed from `commit`, as pip records a VCS install."""
        pack = self.pack
        info = pack / ".venv/lib/python3.14/site-packages/sd_db-0.1.dist-info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "direct_url.json").write_text(
            json.dumps({"url": f"file://{self.system}", "vcs_info": {"vcs": "git", "commit_id": commit}}),
            encoding="utf-8")
        return pack

    def test_an_older_merge_after_a_newer_install_is_skipped(self) -> None:
        older = self.commit("local-sd-db/sd_db/a.py")
        newer = self.commit("local-sd-db/sd_db/b.py")
        pack = self.install_record(newer)
        result = sd_install.reprovision_after_merge(self.system, older, self.environ, pack=pack)
        self.assertEqual(self.calls, [])
        self.assertFalse(result["installed"])
        self.assertIn(f"installed sd_db {newer} is not an ancestor of {older}", result["report"])

    def test_the_commit_already_installed_is_not_installed_again(self) -> None:
        merged = self.commit("local-sd-db/sd_db/a.py")
        result = sd_install.reprovision_after_merge(self.system, merged, self.environ, pack=self.install_record(merged))
        self.assertEqual((self.calls, result["installed"]), ([], False))
        self.assertIn("already installed", result["report"])

    def test_a_newer_merge_over_an_older_install_installs(self) -> None:
        older = self.commit("local-sd-db/sd_db/a.py")
        newer = self.commit("local-sd-db/sd_db/b.py")
        sd_install.reprovision_after_merge(self.system, newer, self.environ, pack=self.install_record(older))
        self.assertEqual(self.calls, [newer])

    def test_two_reconciles_at_once_cannot_land_the_older_install_last(self) -> None:
        """Each read the same installed ancestor and passed the ancestry check;
        the newer install finished first, and the older one then replaced it."""
        base = self.commit("local-sd-db/sd_db/base.py")
        older = self.commit("local-sd-db/sd_db/a.py")
        newer = self.commit("local-sd-db/sd_db/b.py")
        pack = self.install_record(base)
        older_installing, newer_installed = threading.Event(), threading.Event()

        def provision(ctx, out, ref=None):
            self.calls.append(ref)
            if ref == older:
                # The older install is slow: it records only after the newer
                # one has finished, or after a bound when the newer one waits.
                older_installing.set()
                newer_installed.wait(2)
            self.install_record(ref)
            if ref == newer:
                newer_installed.set()
            return True, f"sd_db installed at {ref}"

        def reconcile(commit: str) -> None:
            sd_install.reprovision_after_merge(self.system, commit, self.environ, pack=pack)
        with mock.patch.object(sd_install, "provision_library", provision):
            first = threading.Thread(target=reconcile, args=(older,))
            first.start()
            self.assertTrue(older_installing.wait(10))
            second = threading.Thread(target=reconcile, args=(newer,))
            second.start()
            first.join(30)
            second.join(30)
        self.assertEqual(sd_install.installed_library_commit(pack / ".venv"), newer)
        self.assertEqual(self.calls, [older, newer])


class DirectProvisioningAfterANewerReconcile(ReprovisionAfterMerge):
    """`make setup` from a stale system checkout must not undo a reconcile (sd:2108 review).

    A reconcile installed a newer library merge; the system checkout still
    stands on an older commit with the same schema. Direct provisioning took
    the lock but not the ancestry check, so it put the older code back.
    """

    def make_setup(self, installed: str) -> tuple[int, str]:
        out = io.StringIO()
        home = self.system.parent / "home"
        with mock.patch.object(sd_install, "installed_library_commit", return_value=installed):
            code = sd_install.main(["--provision-library", "--home", str(home)],
                                   environ=dict(self.environ), out=out)
        return code, out.getvalue()

    def test_an_older_checkout_does_not_replace_the_newer_install(self) -> None:
        older = self.commit("local-sd-db/sd_db/a.py")
        newer = self.commit("local-sd-db/sd_db/b.py")
        git(self.system, "checkout", "-q", older)
        code, output = self.make_setup(newer)
        self.assertEqual(self.calls, [])
        self.assertEqual(code, 1)
        self.assertIn(f"preserving installed sd_db {newer}", output)
        self.assertIn(older, output)

    def test_a_newer_checkout_installs_its_pin(self) -> None:
        older = self.commit("local-sd-db/sd_db/a.py")
        newer = self.commit("local-sd-db/sd_db/b.py")
        code, _ = self.make_setup(older)
        self.assertEqual((code, self.calls), (0, [newer]))

    def test_a_diverged_checkout_still_installs_its_pin(self) -> None:
        """Only a reconcile keeps an unrelated install; `make setup` on a topic branch is the operator's call."""
        base = self.commit("local-sd-db/sd_db/base.py")
        installed = self.commit("local-sd-db/sd_db/a.py")
        git(self.system, "checkout", "-q", "-b", "topic", base)
        topic = self.commit("local-sd-db/sd_db/b.py")
        code, _ = self.make_setup(installed)
        self.assertEqual((code, self.calls), (0, [topic]))


class SchemaGuardReadsTheEnvironmentItProtects(unittest.TestCase):
    """Review round 18: `--venv` names what the schema guard reads, not the checkout's `.venv`."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = pathlib.Path(temp.name).resolve()
        self.system = self.root / "system"
        (self.system / "local-sd-db/sd_db").mkdir(parents=True)
        (self.system / "local-sd-db/pyproject.toml").write_text("", encoding="utf-8")
        (self.system / "local-sd-db/sd_db/schema.py").write_text("SCHEMA_VERSION = 3\n", encoding="utf-8")
        git(self.system, "init", "-q", "-b", "main")
        git(self.system, "add", "-A")
        git(self.system, "-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-qm", "schema 3")
        self.ref = git(self.system, "rev-parse", "HEAD")

    def env(self, name: str, schema: int | None = None) -> pathlib.Path:
        venv = self.root / name
        (venv / "bin").mkdir(parents=True)
        (venv / "bin/python").write_text("", encoding="utf-8")
        if schema is not None:
            package = venv / "lib/python3.14/site-packages/sd_db"
            package.mkdir(parents=True)
            (package / "schema.py").write_text(f"SCHEMA_VERSION = {schema}\n", encoding="utf-8")
        return venv

    def provision(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        environ = {sd_install.SYSTEM_CHECKOUT_ENV: str(self.system), "XDG_STATE_HOME": str(self.root / "state")}
        with mock.patch.object(sd_install, "library_pin", return_value=(self.ref, "")):
            code = sd_install.main(["--provision-library", "--home", str(self.root / "home"), *args],
                                   environ=environ, out=out)
        return code, out.getvalue()

    def test_a_custom_venv_with_a_newer_schema_is_preserved(self) -> None:
        code, output = self.provision("--venv", str(self.env("custom", schema=4)))
        self.assertEqual(code, 1)
        self.assertIn("preserving installed sd_db schema 4", output)


class ProvisioningLock(unittest.TestCase):
    def test_a_dry_run_takes_no_lock_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = pathlib.Path(temp)
            ctx = sd_install.Context(checkout=home / "pack", home=home, environ={}, dry_run=True)
            with sd_install.provisioning_lock(ctx):
                pass
            self.assertEqual(list(home.iterdir()), [])


class InstalledLibraryCommit(unittest.TestCase):
    """What pip recorded, read without trusting it: a bad record names no commit."""

    def record(self, pack: pathlib.Path, python: str, text: str) -> None:
        info = pack / f".venv/lib/{python}/site-packages/sd_db-0.1.dist-info"
        info.mkdir(parents=True)
        (info / "direct_url.json").write_text(text, encoding="utf-8")

    def test_an_unreadable_or_path_install_record_names_no_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pack = pathlib.Path(temp)
            self.record(pack, "python3.12", "{not json")
            self.record(pack, "python3.13", json.dumps({"url": "file:///x", "dir_info": {}}))
            self.assertIsNone(sd_install.installed_library_commit(pack / ".venv"))
            self.record(pack, "python3.14", json.dumps({"vcs_info": {"commit_id": "abc123"}}))
            self.assertEqual(sd_install.installed_library_commit(pack / ".venv"), "abc123")


class ProvisionAtARef(unittest.TestCase):
    """`provision_library` installs the ref it is handed instead of the checkout's pin."""

    def test_the_given_ref_is_the_one_installed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp).resolve()
            checkout, system = root / "pack", root / "system"
            (checkout / ".venv/bin").mkdir(parents=True)
            (checkout / ".venv/bin/python").write_text("", encoding="utf-8")
            (system / "local-sd-db").mkdir(parents=True)
            (system / "local-sd-db/pyproject.toml").write_text("", encoding="utf-8")
            ctx = sd_install.Context(checkout=checkout, home=root / "home",
                                     environ={sd_install.SYSTEM_CHECKOUT_ENV: str(system)})
            seen = []

            def pip(argv, **kwargs):
                seen.append(argv)
                return subprocess.CompletedProcess(argv, 0, "", "")
            with mock.patch.object(sd_install, "library_pin", return_value=("pinned", "")), \
                    mock.patch.object(sd_install.subprocess, "run", pip):
                installed, report = sd_install.provision_library(ctx, None, ref="abc123")
            self.assertTrue(installed, report)
            # The git reads around the install share the mock; the pip call is the one asked about.
            installs = [argv for argv in seen if "pip" in argv]
            self.assertEqual(installs[0][-1], f"git+file://{system}@abc123#subdirectory=local-sd-db")


if __name__ == "__main__":
    unittest.main()
