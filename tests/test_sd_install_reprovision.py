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

import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

BIN = pathlib.Path(__file__).resolve().parent.parent / "bin"
sys.path.insert(0, str(BIN))

import sd_install  # noqa: E402


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
        self.environ = {sd_install.SYSTEM_CHECKOUT_ENV: str(self.system)}
        self.calls: list[str | None] = []

        def provision(ctx, out, ref=None):
            self.calls.append(ref)
            return True, f"sd_db installed at {ref}"
        patcher = mock.patch.object(sd_install, "provision_library", provision)
        patcher.start()
        self.addCleanup(patcher.stop)

    def commit(self, name: str) -> str:
        path = self.system / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{name}\n", encoding="utf-8")
        git(self.system, "add", name)
        git(self.system, "commit", "-q", "-m", f"touch {name}")
        return git(self.system, "rev-parse", "HEAD")

    def test_a_merge_touching_the_library_installs_the_merge_commit(self) -> None:
        merged = self.commit("local-sd-db/sd_db/writing.py")
        result = sd_install.reprovision_after_merge(self.system, merged, self.environ)
        self.assertEqual(self.calls, [merged])
        self.assertEqual(result, {"ref": merged, "installed": True, "report": f"sd_db installed at {merged}"})

    def test_a_merge_elsewhere_in_the_system_repository_installs_nothing(self) -> None:
        merged = self.commit("local-redis/redis.sh")
        self.assertIsNone(sd_install.reprovision_after_merge(self.system, merged, self.environ))
        self.assertEqual(self.calls, [])

    def test_another_repository_installs_nothing(self) -> None:
        merged = self.commit("local-sd-db/sd_db/writing.py")
        other = {sd_install.SYSTEM_CHECKOUT_ENV: str(self.system.parent / "elsewhere")}
        self.assertIsNone(sd_install.reprovision_after_merge(self.system, merged, other))
        self.assertEqual(self.calls, [])

    def test_a_worktree_of_the_system_checkout_counts_as_the_system_repository(self) -> None:
        worktree = self.system.parent / "system-topic"
        git(self.system, "worktree", "add", "-q", "-b", "topic", str(worktree))
        merged = self.commit("local-sd-db/pyproject.toml")
        sd_install.reprovision_after_merge(worktree, merged, self.environ)
        self.assertEqual(self.calls, [merged])


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
            self.assertEqual(seen[0][-1], f"git+file://{system}@abc123#subdirectory=local-sd-db")


if __name__ == "__main__":
    unittest.main()
