"""The test process reads no global or system git config (sd:6386).

A work satellite's global `fetch.prune=true` failed the fetch in
`test_an_empty_commit_on_merged_work_allocates_its_own_record` on every run:
"cannot lock ref 'refs/remotes/origin/main'". Each case starts a child the way
a shard starts, with a hostile global and system config, and the package's
`__init__` must shut both out before any test reads git.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

from tests.clean_env import clean_environment

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
NO_ITEM = "tests.test_sd_ship_no_item.NoItemContracts.test_an_empty_commit_on_merged_work_allocates_its_own_record"
#: Prints `fetch.prune` as the test process's git reads it, after the package is imported.
PROBE = ("import importlib, subprocess, sys; importlib.import_module(sys.argv[1]); "
         "print(subprocess.run(['git', 'config', '--get', 'fetch.prune'], capture_output=True, text=True).stdout)")


class GitConfigIsolation(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="sd-git-isolation-")
        self.addCleanup(temporary.cleanup)
        self.config = pathlib.Path(temporary.name) / "gitconfig"
        self.config.write_text("[fetch]\n\tprune = true\n")

    def environment(self, scope: str) -> dict[str, str]:
        """A shard's environment whose `scope` config sets `fetch.prune=true`."""

        environment = clean_environment(**{f"GIT_CONFIG_{scope.upper()}": str(self.config)})
        environment.pop("GIT_CONFIG_NOSYSTEM", None)
        return environment

    def test_a_global_fetch_prune_leaves_the_no_item_fetch_fixture_passing(self) -> None:
        done = subprocess.run([sys.executable, "-m", "unittest", NO_ITEM], cwd=REPO_ROOT, capture_output=True,
                              text=True, env=self.environment("global"), timeout=300, check=False)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])

    def test_each_test_package_shuts_out_the_global_and_system_config(self) -> None:
        for package in ("tests", "tests.sd_db", "dashboard.tests"):
            for scope in ("global", "system"):
                with self.subTest(package=package, scope=scope):
                    done = subprocess.run([sys.executable, "-c", PROBE, package], cwd=REPO_ROOT, capture_output=True,
                                          text=True, env=self.environment(scope), timeout=60, check=True)
                    self.assertEqual(done.stdout.strip(), "", f"{package} let the {scope} config through")


if __name__ == "__main__":
    unittest.main()
