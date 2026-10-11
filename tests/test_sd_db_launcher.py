"""`bin/sd-db` runs the database verbs from this checkout's `lib/` (sd:3285).

Two halves. A fixture tree holds a copy of the launcher beside a fake `lib/`,
so each test can say what the library answered and with which exit code, and
a decoy `sd_db` on `PYTHONPATH` proves `lib/` answers first. One real run
drives the copied library end to end against a database under a temporary
`HOME`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.clean_env import clean_environment

REPO_ROOT = Path(__file__).resolve().parents[1]
SD_DB = REPO_ROOT / "bin" / "sd-db"

FAKE_CLI = """\
import sys
def main(argv):
    print("lib cli", argv)
    return 7
"""

FAKE_BACKUP = """\
import os, sys
BROKEN_SOURCE = 3
def main(argv):
    print("lib backup", argv, flush=True)
    print("to stderr", file=sys.stderr)
    return int(os.environ["FAKE_BACKUP_EXIT"])
if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
"""

FAKE_SERVE = """\
def main(argv):
    print("lib serve", argv)
    return 0
"""


class TheLauncher(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="sd-db-launcher-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / "bin").mkdir()
        shutil.copy2(SD_DB, self.root / "bin" / "sd-db")
        self.write("lib/sd_db/__init__.py", "")
        self.write("lib/sd_db/jobs/__init__.py", "")
        self.write("lib/sd_db/jobs/cli.py", FAKE_CLI)
        self.write("lib/sd_db/jobs/backup.py", FAKE_BACKUP)
        self.write("lib/sd_db/serve.py", FAKE_SERVE)
        self.write("decoy/sd_db/__init__.py", "raise SystemExit('the decoy answered')\n")
        self.mail = self.root / "mail.txt"
        notify = self.write("notify", f"#!{sys.executable}\nimport sys\n"
                            f"open({str(self.mail)!r}, 'a').write(repr(sys.argv[1:]) + '\\n')\n")
        notify.chmod(0o755)
        self.notify = notify

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_sd_db(self, *argv: str, **extra: str) -> subprocess.CompletedProcess[str]:
        steer = {"PYTHONPATH": str(self.root / "decoy"), "SD_NOTIFY": str(self.notify), **extra}
        return subprocess.run([sys.executable, str(self.root / "bin" / "sd-db"), *argv],
                              capture_output=True, text=True, env=clean_environment(**steer), timeout=60)

    def mails(self) -> list[str]:
        return self.mail.read_text(encoding="utf-8").splitlines() if self.mail.exists() else []

    def test_a_cli_verb_runs_lib_with_its_arguments_and_exit_code(self) -> None:
        run = self.run_sd_db("repo", "list", "--managed")
        self.assertEqual(run.returncode, 7, run.stderr)
        self.assertEqual(run.stdout, "lib cli ['repo', 'list', '--managed']\n")

    def test_every_verb_sd_db_sh_hands_the_cli_reaches_it(self) -> None:
        for verb in ("init", "migrate", "status", "restore", "repo", "item", "work",
                     "import", "verify", "usage", "judgments", "credentials"):
            with self.subTest(verb=verb):
                run = self.run_sd_db(verb, "x")
                self.assertEqual((run.returncode, run.stdout), (7, f"lib cli [{verb!r}, 'x']\n"), run.stderr)

    def test_help_anywhere_on_a_cli_verb_prints_usage_and_runs_nothing(self) -> None:
        for argv in (("init", "--help"), ("repo", "list", "-h")):
            with self.subTest(argv=argv):
                run = self.run_sd_db(*argv)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout, "")
                self.assertIn("Usage: sd-db <verb>", run.stderr)

    def test_help_exits_zero_and_no_verb_or_an_unknown_one_exits_one(self) -> None:
        for argv, code in (((), 1), (("help",), 0), (("-h",), 0), (("--help",), 0), (("nope",), 1),
                           (("release",), 1), (("library",), 1)):
            with self.subTest(argv=argv):
                run = self.run_sd_db(*argv)
                self.assertEqual(run.returncode, code, run.stderr)
                self.assertIn("Usage: sd-db <verb>", run.stderr)

    def test_serve_runs_lib_with_its_arguments(self) -> None:
        run = self.run_sd_db("serve", "--loopback", "--port", "0")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "lib serve ['--loopback', '--port', '0']\n")

    def test_a_passing_backup_prints_its_output_and_sends_no_mail(self) -> None:
        run = self.run_sd_db("backup", "--keep", "3", FAKE_BACKUP_EXIT="0")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "lib backup ['--keep', '3']\nto stderr\n")
        self.assertEqual(self.mails(), [])

    def test_a_failed_backup_mails_its_output_and_exits_one(self) -> None:
        run = self.run_sd_db("backup", FAKE_BACKUP_EXIT="5")
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, "")
        self.assertIn("lib backup []\nto stderr", run.stderr)
        self.assertEqual(self.mails(), [repr(["-t", "sd-db backup FAILED", "-k", "status", "-F", "-c", "email",
                                              "-b", "lib backup []\nto stderr"])])

    def test_a_broken_source_mails_its_own_title_and_keeps_exit_three(self) -> None:
        run = self.run_sd_db("backup", FAKE_BACKUP_EXIT="3")
        self.assertEqual(run.returncode, 3)
        self.assertEqual(self.mails()[0].split(", ")[1], "'sd-db backup: the source is referentially broken'")

    def test_a_mail_that_cannot_leave_is_said_and_the_failure_stays(self) -> None:
        run = self.run_sd_db("backup", FAKE_BACKUP_EXIT="5", SD_NOTIFY=str(self.root / "absent"))
        self.assertEqual(run.returncode, 1)
        self.assertIn("sd-db backup: the failure mail did not leave", run.stderr)


class TheRealLibrary(unittest.TestCase):
    def test_init_status_and_an_empty_repo_list_answer_from_the_copied_library(self) -> None:
        home = tempfile.mkdtemp(prefix="sd-db-home-")
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)

        def sd_db(*argv: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([sys.executable, str(SD_DB), *argv], capture_output=True, text=True,
                                  env=clean_environment(HOME=home, XDG_CONFIG_HOME=home), timeout=120)

        self.assertEqual(sd_db("init").returncode, 0)
        listed = sd_db("repo", "list")
        self.assertEqual((listed.returncode, listed.stdout),
                         (1, "sd-db: the `repo` table is empty; run `sd-db.sh repo seed`\n"))
        status = sd_db("status")
        self.assertEqual(status.returncode, 0, status.stderr)
        schema = (REPO_ROOT / "lib" / "sd_db" / "schema.py").read_text(encoding="utf-8")
        version = next(line.split("=")[1].strip() for line in schema.splitlines()
                       if line.startswith("SCHEMA_VERSION ="))
        self.assertIn(version, status.stdout)
        self.assertIn(str(Path(home) / ".local" / "share" / "sd" / "sd.db"), status.stdout)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
