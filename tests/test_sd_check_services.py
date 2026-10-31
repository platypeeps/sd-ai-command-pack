"""`sd-check` refuses to run when a service its check needs is down (sd:1649).

A repository declares the services in its `CLAUDE.local.md` block. Before any
step runs, `sd-check` connects to each; one that does not answer fails every
check unrun, naming the service, its port and the declared start hint, so a
stopped database never reads as a code error. A loopback socket stands in for
an open service and a port just released by one for a closed service.
"""

from __future__ import annotations

import json
import pathlib
import shlex
import socket
import subprocess
import sys
import tempfile
import unittest
from typing import Any

from tests.clean_env import clean_environment
from tests.clean_env import home as clean_home
from tests.row_seed import seed_declaration

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SD_CHECK = REPO_ROOT / "bin" / "sd-check"
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lib  # noqa: E402

START = "docker compose up -d db"


def listening() -> socket.socket:
    """A loopback socket that accepts connections; the caller closes it."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen()
    return server


def closed_port() -> int:
    """A loopback port nothing listens on: bound once, then released."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class ServiceFixture(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name).resolve() / "repo"
        self.root.mkdir()
        self.witness = self.root / "ran"
        for args in (["init", "-q", "-b", "main"], ["config", "user.email", "test@example.test"],
                     ["config", "user.name", "Test"], ["config", "core.excludesFile", "/dev/null"]):
            self.git(*args)

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, env=clean_environment())

    def declare(self, **keys: str) -> None:
        """The local block with a check that records it ran, plus `keys`."""
        (self.root / "mark.py").write_text(f"open({str(self.witness)!r}, 'w').close()\n", encoding="utf-8")
        check = f"{shlex.quote(sys.executable)} mark.py"
        body = "".join(f"{key}: {value}\n" for key, value in {"check": check, **keys}.items())
        (self.root / sd_lib.LOCAL_FILE_NAME).write_text(
            f"{sd_lib.LOCAL_BLOCK_START}\n{body}{sd_lib.LOCAL_BLOCK_END}\n", encoding="utf-8")

    def run_check(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(SD_CHECK), *args], cwd=self.root, capture_output=True, text=True,
                              timeout=120, env=clean_environment(SD_GATE_SLOTS="0"))

    def report(self, *args: str, expect: int) -> dict[str, Any]:
        completed = self.run_check("--json", *args)
        self.assertEqual(completed.returncode, expect, completed.stdout + completed.stderr)
        loaded = json.loads(completed.stdout)
        assert isinstance(loaded, dict)
        return loaded


class RequiredServices(ServiceFixture):
    def test_an_open_service_lets_the_check_run(self) -> None:
        with listening() as server:
            self.declare(services=f"db=127.0.0.1:{server.getsockname()[1]}", services_start=START)
            report = self.report(expect=0)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(self.witness.exists(), "the check did not run")

    def test_a_closed_service_refuses_the_run_and_names_it(self) -> None:
        port = closed_port()
        self.declare(services=f"db=127.0.0.1:{port}", services_start=START)
        report = self.report(expect=1)
        check = next(row for row in report["checks"] if row["name"] == "check")
        self.assertEqual((check["status"], check["exit_code"]), ("fail", None))
        self.assertIn(f"db (127.0.0.1:{port})", check["reason"])
        self.assertIn(START, check["reason"])
        self.assertEqual(check["failed_steps"], [f"check: {check['reason']}"])
        self.assertNotIn("gate_slot", report, "a refused run waits for no slot")
        self.assertFalse(self.witness.exists(), "the check ran though its service was down")

    def test_every_closed_service_is_named_and_an_open_one_is_not(self) -> None:
        port = closed_port()
        with listening() as server:
            open_port = server.getsockname()[1]
            self.declare(services=f"127.0.0.1:{open_port} cache=127.0.0.1:{port}")
            completed = self.run_check()
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn(f"so this did not run: cache (127.0.0.1:{port})\n", completed.stdout)
        self.assertNotIn(f"127.0.0.1:{open_port}", completed.stdout)
        self.assertFalse(self.witness.exists())

    def test_a_dry_run_probes_nothing(self) -> None:
        self.declare(services=f"db=127.0.0.1:{closed_port()}")
        self.assertEqual(self.report("--dry-run", expect=0)["status"], "skipped")

    def test_a_malformed_entry_is_a_configuration_error(self) -> None:
        for entry in ("db=127.0.0.1", "127.0.0.1:0", ":5433", "db=127.0.0.1:port"):
            with self.subTest(entry=entry):
                self.declare(services=entry)
                completed = self.run_check()
                self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                self.assertIn(f"services: '{entry}'", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)
                self.assertFalse(self.witness.exists())

    def test_a_docs_only_scope_probes_nothing(self) -> None:
        # The scope is the repo row's `check_scope` declaration (sd:5109), under the clean HOME the run reads.
        seed_declaration(pathlib.Path(clean_home()), self.root, "check_scope",
                         {"schema_version": 1, "docs_paths": ["docs/**"], "docs_command": [sys.executable, "-c", "pass"]})
        (self.root / "base.txt").write_text("b\n")
        self.git("add", "base.txt")
        self.git("commit", "-q", "-m", "base")
        self.git("checkout", "-q", "-b", "topic")
        (self.root / "docs").mkdir()
        (self.root / "docs/guide.md").write_text("# Guide\n")
        self.git("add", "docs")
        self.git("commit", "-q", "-m", "docs")
        self.declare(services=f"db=127.0.0.1:{closed_port()}")
        report = self.report("--base", "main", expect=0)
        self.assertEqual((report["scope"]["mode"], report["status"]), ("docs-only", "pass"))


class TestRecipe(ServiceFixture):
    """sd:6882. The policy's `test` recipe: env names that must be set, a setup before the checks, a teardown after."""

    def recipe(self, check: str = "check", **test: object) -> pathlib.Path:
        """Declare `test` on the row and a local check that logs `check`; the log each step appends to."""
        log = self.root / "log"
        seed_declaration(pathlib.Path(clean_home()), self.root, "policy", {"test": test})
        ending = "raise SystemExit(3)\n" if check == "fail" else ""
        (self.root / "step.py").write_text(f"open({str(log)!r}, 'a').write({check + chr(10)!r})\n{ending}")
        self.declare(check=f"{shlex.quote(sys.executable)} step.py")
        return log

    def test_setup_runs_before_the_checks_and_teardown_after(self) -> None:
        log = self.recipe(setup="echo setup >> log", teardown="echo teardown >> log")
        report = self.report(expect=0)
        self.assertEqual(log.read_text().split(), ["setup", "check", "teardown"])
        self.assertEqual([(row["name"], row["status"]) for row in report["recipe"]],
                         [("setup", "pass"), ("teardown", "pass")])

    def test_a_missing_env_name_fails_every_check_unrun(self) -> None:
        log = self.recipe(env=["SD_TEST_RECIPE_TOKEN"], setup="echo setup >> log")
        report = self.report(expect=1)
        check = next(row for row in report["checks"] if row["name"] == "check")
        self.assertEqual((check["status"], check["exit_code"]), ("fail", None))
        self.assertIn("needs SD_TEST_RECIPE_TOKEN set", check["reason"])
        self.assertFalse(log.exists(), "a step ran though the recipe's env was missing")

    def test_a_failed_setup_fails_the_checks_unrun_and_still_tears_down(self) -> None:
        log = self.recipe(setup="exit 4", teardown="echo teardown >> log")
        report = self.report(expect=1)
        check = next(row for row in report["checks"] if row["name"] == "check")
        self.assertIn("setup failed", check["reason"])
        self.assertEqual(log.read_text().split(), ["teardown"])

    def test_a_failed_check_still_tears_down(self) -> None:
        log = self.recipe("fail", teardown="echo teardown >> log")
        self.assertEqual(self.report(expect=1)["status"], "fail")
        self.assertEqual(log.read_text().split(), ["fail", "teardown"])


if __name__ == "__main__":
    unittest.main()
