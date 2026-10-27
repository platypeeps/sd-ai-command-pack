"""The test process opens no live workflow database (sd:6403).

On the work satellite a hub refresh mid-run failed 356 pack tests: each opened
the default database, which on a satellite is the hub's over the tailnet, and
the hub's new build refused the old client. Each case starts a child the way a
shard starts, with a `HOME` that names a hub nobody serves, and the package's
`__init__` must move `HOME` away before any test resolves the database.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from tests.clean_env import clean_environment

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
REVIEW = "tests.test_sd_review.TheWorkstationLaneIsNotPrintedWhereItCannotBeReached"
#: Prints where the default database and `hub.json` resolve once the package is imported, and whether the hub is one.
PROBE = ("import importlib, json, os, sys; importlib.import_module(sys.argv[1]); "
         "sys.path.insert(0, sys.argv[2]); from sd_db import database, hub; "
         "print(json.dumps([os.environ['HOME'], str(database.local_path()), hub.configured()]))")
#: Imports the package, then runs the body's privacy check in the environment it leaves.
LINT = ("import importlib, subprocess, sys; importlib.import_module(sys.argv[1]); "
        "sys.exit(subprocess.run([sys.executable, sys.argv[2], '--body-only', '--pr-body', sys.argv[3]]).returncode)")


class HomeIsolation(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="sd-home-isolation-")
        self.addCleanup(temporary.cleanup)
        self.home = pathlib.Path(temporary.name).resolve()
        (self.home / ".config/sd").mkdir(parents=True)
        (self.home / ".config/sd/hub.json").write_text(json.dumps({"hub": "127.0.0.1", "port": 1}))

    def environment(self) -> dict[str, str]:
        """A satellite shard's environment: its home names a hub that refuses every connection."""

        return clean_environment(HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / ".config"))

    def test_review_tests_pass_on_a_satellite_whose_hub_is_unreachable(self) -> None:
        done = subprocess.run([sys.executable, "-m", "unittest", REVIEW], cwd=REPO_ROOT, capture_output=True,
                              text=True, env=self.environment(), timeout=300, check=False)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])

    def test_each_test_package_moves_home_off_the_live_database(self) -> None:
        for package in ("tests", "tests.sd_db", "dashboard.tests"):
            with self.subTest(package=package):
                done = subprocess.run([sys.executable, "-c", PROBE, package, str(REPO_ROOT / "lib")], cwd=REPO_ROOT,
                                      capture_output=True, text=True, env=self.environment(), timeout=60, check=True)
                home, database, satellite = json.loads(done.stdout)
                self.assertNotEqual(pathlib.Path(home).resolve(), self.home, f"{package} kept the live HOME")
                self.assertFalse(pathlib.Path(database).resolve().is_relative_to(self.home),
                                 f"{package} resolves the database to {database}")
                self.assertFalse(satellite, f"{package} still reads the live hub.json")

    def test_each_test_package_checks_bodies_against_synthetic_privacy_patterns(self) -> None:
        """sd:6432. The temp `HOME` hid `<config>/privacy-patterns` where `SYSTEM_TOOLS_CONFIG` is unset, and five
        tests failed on the satellite; where it is set, tests read the operator's real patterns. Each package holds a
        synthetic file of its own in both cases: the live one here matches the body, so reading it fails."""
        live = self.home / ".config/system"
        live.mkdir(parents=True)
        (live / "privacy-patterns").write_text("live-only-secret\n", encoding="utf-8")
        body = self.home / "body.md"
        body.write_text("## Summary\n\nNames live-only-secret.\n", encoding="utf-8")
        # Empty reads as unset, in `sd-docs-lint` and in `dashboard.sh` alike.
        for config in ("", str(live)):
            for package in ("tests", "tests.sd_db", "dashboard.tests"):
                with self.subTest(package=package, set=bool(config)):
                    done = subprocess.run([sys.executable, "-c", LINT, package, str(REPO_ROOT / "bin/sd-docs-lint"),
                                           str(body)], cwd=REPO_ROOT, capture_output=True, text=True,
                                          env=clean_environment(HOME=str(self.home),
                                                                XDG_CONFIG_HOME=str(self.home / ".config"),
                                                                SYSTEM_TOOLS_CONFIG=config),
                                          timeout=120, check=False)
                    self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
                    self.assertIn("PR privacy: 1 pattern(s) from", done.stdout)


if __name__ == "__main__":
    unittest.main()
