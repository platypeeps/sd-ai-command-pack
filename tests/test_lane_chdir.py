"""`-C <dir>` on the five lane commands (sd:1910), R10-D6's one named exception.

Each command changes its working directory once, before anything resolves the
repository, as `git -C` does. Everything after still reads cwd, so a bad `-C`
fails the same way a bad cwd does: an empty directory is "not inside a git
repository", named; a missing path is "not a directory", named. The tests run
each command as a subprocess from a temporary directory that is not a
repository, so `-C` is the only thing that can point them at one.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = REPO_ROOT / "bin"

# (command, the cheapest arguments that reach repository resolution)
LANE_COMMANDS = {
    "sd-check": ["--dry-run", "--json"],
    "sd-review": ["--explain", "--json"],
    "sd-review-ack": ["--check", "--json"],
    "sd-pr-state": ["--json"],
}


def run(command: str, *arguments: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BIN / command), *arguments],
        cwd=cwd, capture_output=True, text=True, timeout=120, check=False,
    )


class LaneChdirTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = tempfile.TemporaryDirectory(prefix="sd-lane-chdir-")
        self.addCleanup(self.scratch.cleanup)
        self.outside = pathlib.Path(self.scratch.name) / "outside"
        self.outside.mkdir()
        self.empty = pathlib.Path(self.scratch.name) / "empty"
        self.empty.mkdir()
        self.missing = pathlib.Path(self.scratch.name) / "missing"

    def test_an_empty_directory_is_not_a_repository_and_is_named(self) -> None:
        for command, arguments in LANE_COMMANDS.items():
            with self.subTest(command=command):
                result = run(command, "-C", str(self.empty), *arguments, cwd=self.outside)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("is not inside a git repository", result.stderr)
                self.assertIn(str(self.empty.resolve()), result.stderr, "the named cwd is the -C one")
                self.assertNotIn(str(self.outside.resolve()), result.stderr)

    def test_a_missing_path_is_refused_by_name(self) -> None:
        for command, arguments in LANE_COMMANDS.items():
            with self.subTest(command=command):
                result = run(command, "-C", str(self.missing), *arguments, cwd=self.outside)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(f"-C {self.missing}: not a directory", result.stderr)

    def test_sd_ship_refuses_a_missing_path_as_a_failure_object(self) -> None:
        result = run("sd-ship", "-C", str(self.missing), "body", "--item", "1", "--json", cwd=self.outside)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report.get("ok", True))
        self.assertIn(f"-C {self.missing}: not a directory", json.dumps(report))

    def test_sd_ship_refuses_an_empty_directory_as_a_failure_object(self) -> None:
        # sd:1911. LANE_COMMANDS exit 2 on stderr; sd-ship answers with its
        # exit-3 refusal object. The cwd is a repository where `body` passes,
        # so a `-C` that went unread would pass too rather than refuse.
        subprocess.run(["git", "init", "-q", str(self.outside)], check=True)
        control = run("sd-ship", "body", "--item", "1", "--json", cwd=self.outside)
        self.assertEqual(control.returncode, 0, "the control: in the cwd repository, body passes")
        result = run("sd-ship", "-C", str(self.empty), "body", "--item", "1", "--json", cwd=self.outside)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report.get("ok", True))
        self.assertIn("not inside a git repository", report["error"].lower())

    def test_sd_ship_body_resolves_the_repository_from_the_c_directory(self) -> None:
        # `body` is the one sd-ship verb with no database and no GitHub; it
        # still refuses outside a repository, so it observes where -C went.
        # A fresh repository, not this checkout: `body` lints the scope line
        # this checkout's own branch demands, so a branch touching
        # `.github/**` failed here for a reason that has nothing to do with -C.
        without = run("sd-ship", "body", "--item", "1", "--json", cwd=self.outside)
        self.assertNotEqual(without.returncode, 0, "the control: outside a repository, body refuses")
        subprocess.run(["git", "init", "-q", str(self.empty)], check=True)
        result = run("sd-ship", "-C", str(self.empty), "body", "--item", "1", "--json", cwd=self.outside)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_sd_check_reports_the_c_repository_not_the_cwd(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.empty)], check=True)
        # An initialised, buildfile-less repository has every entrypoint absent;
        # the pack has `make check`. The dry run says which one it looked at.
        result = run("sd-check", "-C", str(self.empty), "--dry-run", "--json", cwd=REPO_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        statuses = {check["name"]: check["status"] for check in json.loads(result.stdout)["checks"]}
        self.assertEqual(statuses, {"check": "absent", "test": "absent", "lint": "absent"}, statuses)

    def test_a_repeated_c_is_refused_rather_than_last_wins(self) -> None:
        # Pass 2 of sd:1910: an allow rule that names the directory is a prefix
        # match on the command line, so `-C /approved -C /unrelated` must not
        # select /unrelated. argparse would let the last value win; the shared
        # action refuses the second, and sd-review's pre-parser refuses it too.
        # Pass 3: the attached spelling `-C/unrelated` is a second `-C` too.
        for command, arguments in {**LANE_COMMANDS, "sd-ship": ["body", "--item", "1", "--json"]}.items():
            for second in (["-C", str(self.empty)], [f"-C{self.empty}"]):
                with self.subTest(command=command, second=second):
                    result = run(command, "-C", str(REPO_ROOT), *second, *arguments, cwd=self.outside)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn("-C given twice", result.stderr)
                    self.assertNotIn("is not inside a git repository", result.stderr)

    def test_a_parent_component_is_refused(self) -> None:
        # The same prefix match: `-C /approved/../unrelated` keeps the approved
        # prefix and leaves the directory. `..` is refused; name the directory.
        dodge = str(REPO_ROOT / ".." / REPO_ROOT.name)
        for command, arguments in {**LANE_COMMANDS, "sd-ship": ["body", "--item", "1", "--json"]}.items():
            with self.subTest(command=command):
                result = run(command, "-C", dodge, *arguments, cwd=self.outside)
                self.assertEqual(result.returncode, 3 if command == "sd-ship" else 2, result.stdout + result.stderr)
                self.assertIn("'..' is not allowed", result.stdout + result.stderr)

    def test_sd_review_refuses_a_c_without_an_operand(self) -> None:
        # The pre-parser in front of `setup-github` runs before argparse, so a
        # bare `-C` used to become `.` and fall through to a default review in
        # whatever checkout the caller stood in (pass 1 of sd:1910). From a
        # non-repository cwd a fall-through says "not inside a git repository",
        # which is the wrong message, so the assertion is on the message.
        for arguments in (["-C"], ["-C", "setup-github"], ["-C", "", "--explain"]):
            with self.subTest(arguments=arguments):
                result = run("sd-review", *arguments, cwd=self.outside)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertRegex(result.stderr, r"-C(: expected a directory|: expected one argument| setup-github: not a directory)")
                self.assertNotIn("is not inside a git repository", result.stderr)

    def test_sd_review_setup_github_honours_a_leading_c(self) -> None:
        result = run("sd-review", "-C", str(self.missing), "setup-github", "--help", cwd=self.outside)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(f"-C {self.missing}: not a directory", result.stderr)


if __name__ == "__main__":
    unittest.main()
