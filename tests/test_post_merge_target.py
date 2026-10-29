"""sd:3647: `make post-merge` refreshes the hub's pack checkout, then checks service health.

The lane runs it after a pack merge, once its runner lock is released (sd:3566).
The dry run reads what `make` would do and changes nothing.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

from tests.clean_env import clean_environment

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def dry_run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["make", "-n", "--no-print-directory", "post-merge", *arguments], cwd=REPO_ROOT,
                          capture_output=True, text=True, check=False, env=clean_environment())


class ThePostMergeTarget(unittest.TestCase):
    def test_it_refreshes_this_checkout_then_checks_health(self) -> None:
        done = dry_run("SYSTEM_REPO=/example/system")
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = [line for line in done.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 3, done.stdout)
        self.assertIn("git symbolic-ref", lines[0])
        self.assertIn(f'/example/system/local-repo-sync/repo-sync.sh" refresh "{REPO_ROOT}"', lines[1])
        self.assertIn(f'"{REPO_ROOT}/dashboard/dashboard.sh" health', lines[2])

    def test_every_script_it_runs_from_this_checkout_exists(self) -> None:
        # REGRESSION sd:6631: the health step named the system checkout's retired dashboard.sh,
        # so every pack merge's post-merge exited 127 after a good refresh.
        done = dry_run("SYSTEM_REPO=/example/system")
        scripts = re.findall(r'^sh "([^"]+)"', done.stdout, re.MULTILINE)
        local = [path for path in scripts if not path.startswith("/example/system/")]
        self.assertTrue(local, done.stdout)
        for path in local:
            self.assertTrue(pathlib.Path(path).is_file(), path)

    def test_the_system_checkout_defaults_to_the_home_folder(self) -> None:
        done = dry_run()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("/repos/system/local-repo-sync/repo-sync.sh", done.stdout)


class ThePostMergeTargetRuns(unittest.TestCase):
    """The lane's two checkout states, executed against stub tools: a dry run cannot tell them apart."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        system = self.tmp / "system"
        self.checkout = self.tmp / "pack"
        for tool in (system / "local-repo-sync/repo-sync.sh", self.checkout / "dashboard/dashboard.sh"):
            tool.parent.mkdir(parents=True)
            tool.write_text(f'echo "{tool.name} $*" >> "{self.tmp}/calls"\n', encoding="utf-8")
        shutil.copy(REPO_ROOT / "Makefile", self.checkout / "Makefile")
        self.git("init", "-q", "-b", "main")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-q", "--allow-empty", "-m", "x")

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.checkout), *args], check=True, capture_output=True,
                       env=clean_environment())

    def post_merge(self, code: int = 0) -> list[str]:
        env = {key: value for key, value in clean_environment().items() if key not in ("SD_LOCAL_GATE", "VENV")}
        done = subprocess.run(["make", "--no-print-directory", "post-merge", f"SYSTEM_REPO={self.tmp / 'system'}"], cwd=self.checkout, env=env,
                              capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, code, done.stderr)
        self.stderr = done.stderr
        calls = self.tmp / "calls"
        return calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []

    def test_a_branch_checkout_is_refused_with_the_step_that_pins_it(self) -> None:
        # REGRESSION sd:3647 review: setup on a branch checkout ran outside refresh's protection, and
        # no setup left it running new code on old dependencies; refusing it leaves neither.
        self.assertEqual(self.post_merge(code=2), [])
        self.assertIn("switch --detach && make post-merge", self.stderr)

    def test_a_pinned_checkout_is_installed_by_refresh_alone(self) -> None:
        self.git("switch", "-q", "--detach")
        self.assertEqual(self.post_merge(), [f"repo-sync.sh refresh {self.checkout}", "dashboard.sh health"])


if __name__ == "__main__":
    unittest.main()
