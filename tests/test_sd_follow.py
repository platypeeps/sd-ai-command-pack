"""`bin/sd` on a satellite whose build the hub refuses: follow once, run the command again (sd:4748).

The hub is a loopback `sd_db.serve` on this checkout's `lib/`. The satellite
is a copy of `bin/` and `lib/` with one library file changed, so its first
`sd task show` is refused for the build. The follow is a script under a
registered plugin root at `local-repo-sync/repo-sync.sh`; the one that
"moves the pack to the hub's pin" copies the changed file back, so the
re-run, a fresh process, loads the hub's build and is admitted. A fake hub
that refuses once then accepts would hide the fact these tests exist for:
the retry has to be a new process (sd:3359).
"""

from __future__ import annotations

import json
import pathlib
import shutil
import stat
import subprocess
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from sd_db import create_item, database, initialise  # noqa: E402

from tests.clean_env import clean_environment  # noqa: E402
from tests.sd_db.test_wire import Served  # noqa: E402

TITLE = "a note the satellite reads"


class SatelliteFixture(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name).resolve()
        # The hub, on this checkout's build, with one item.
        path = self.root / "hub.db"
        initialise(path)
        connection = database.connect(path)
        self.item = create_item(connection, kind="work", title=TITLE)
        connection.close()
        self.served = Served(self.root, "hub.db")
        self.addCleanup(self.served.stop)
        # The satellite's pack: a copy whose library differs by one file.
        self.pack = self.root / "pack"
        ignore = shutil.ignore_patterns("__pycache__", ".venv", "*.egg-info")
        shutil.copytree(REPO_ROOT / "bin", self.pack / "bin", ignore=ignore)
        shutil.copytree(REPO_ROOT / "lib", self.pack / "lib", ignore=ignore)
        self.changed = self.pack / "lib" / "sd_db" / "reads.py"
        with open(self.changed, "a") as changed:
            changed.write("\n# the satellite's older build\n")
        self.home = self.root / "satellite"
        config = self.home / ".config"
        (config / "sd").mkdir(parents=True)
        (config / "sd" / "hub.json").write_text(json.dumps(
            {"hub": "127.0.0.1", "port": self.served.port, "token_file": str(self.served.token_file)}))
        self.system = self.root / "system"
        (config / "sd-ai-command-pack").mkdir()
        (config / "sd-ai-command-pack" / "config.json").write_text(json.dumps({"plugins": [str(self.system)]}))
        self.log = self.root / "follow.log"

    def follow(self, body: str) -> None:
        """The registered system checkout's follow: logs its call, then runs `body`."""
        script = self.system / "local-repo-sync" / "repo-sync.sh"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text('#!/bin/sh\necho "args=$* marker=${SD_FOLLOWED:-unset} wait=${REPO_SYNC_DRAIN_WAIT:-unset}"'
                          f' >> "{self.log}"\n{body}\n')
        script.chmod(script.stat().st_mode | stat.S_IXUSR)

    def moves_to_the_hubs_pin(self) -> str:
        return f'cp "{REPO_ROOT / "lib" / "sd_db" / "reads.py"}" "{self.changed}"\necho "follow  : done"\nexit 0'

    def sd(self, *args: str, env: dict[str, str] | None = None,
           stdin: int = subprocess.DEVNULL, input: str | None = None) -> subprocess.CompletedProcess[str]:
        # stdin is `/dev/null` unless a test feeds one: the follow's re-run rule reads it.
        return subprocess.run(
            [sys.executable, str(self.pack / "bin" / "sd"), *args], capture_output=True, text=True, timeout=120,
            cwd=self.root, **({"input": input} if input is not None else {"stdin": stdin}),
            env=clean_environment(PATH="/usr/bin:/bin", HOME=str(self.home),
                                  XDG_CONFIG_HOME=str(self.home / ".config"), **(env or {})))

    def logged(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []


class TheRefusedCommand(SatelliteFixture):
    def test_follows_once_and_the_rerun_is_admitted(self):
        self.follow(self.moves_to_the_hubs_pin())
        done = self.sd("task", "show", str(self.item))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(TITLE, done.stdout)
        self.assertEqual(self.logged(), ["args=follow marker=1 wait=120"])
        lines = done.stderr.splitlines()
        self.assertRegex(lines[0], r"^sd: sd_db build [0-9a-f]{16} here, [0-9a-f]{16} on the hub: following the hub's pins")
        self.assertRegex(lines[1], r"^sd: sd_db build [0-9a-f]{16} here, [0-9a-f]{16} on the hub: follow exited 0 after \d+ s; "
                                   r"running the command again$")
        self.assertEqual(len(lines), 2, done.stderr)

    def test_a_failed_follow_surfaces_the_refusal_with_its_text(self):
        self.follow('echo "follow  : refused, nothing moved"\nexit 1')
        done = self.sd("task", "show", str(self.item))
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.logged(), ["args=follow marker=1 wait=120"])
        self.assertIn("follow exited 1", done.stderr)
        self.assertIn("  follow: follow  : refused, nothing moved", done.stderr)
        self.assertIn("sd_db build mismatch: build digest", done.stderr)
        self.assertIn("then `repo-sync.sh follow` on this satellite. The hub ran no statement", done.stderr)
        self.assertEqual(done.stdout, "")

    def test_a_follow_that_moves_nothing_surfaces_the_refusal_once_and_follows_no_second_time(self):
        self.follow('echo "follow: pack already at the hub\'s pin"\nexit 0')
        done = self.sd("task", "show", str(self.item))
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.logged(), ["args=follow marker=1 wait=120"])
        self.assertIn("running the command again", done.stderr)
        self.assertIn("still refused after a follow in this process chain; the refusal stands", done.stderr)
        self.assertIn("sd_db build mismatch: build digest", done.stderr)

    def test_a_pipe_fed_command_is_not_followed_and_the_refusal_names_the_hand_run(self):
        self.follow(self.moves_to_the_hubs_pin())
        done = self.sd("task", "show", str(self.item), input="piped body\n")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.logged(), [], "a pipe-fed command must not follow")
        self.assertIn("stdin is a pipe, which a re-run cannot read again; the refusal stands, "
                      "run the command again after `repo-sync.sh follow`", done.stderr)
        self.assertIn("sd_db build mismatch: build digest", done.stderr)

    def test_no_registered_follow_surfaces_the_refusal(self):
        done = self.sd("task", "show", str(self.item))
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.logged(), [])
        self.assertIn("no registered plugin holds local-repo-sync/repo-sync.sh", done.stderr)
        self.assertIn("sd_db build mismatch: build digest", done.stderr)

    def test_a_follow_that_calls_sd_does_not_follow_again(self):
        self.follow(f'"{sys.executable}" "{self.pack / "bin" / "sd"}" task show {self.item} >> "{self.log}" 2>&1; '
                    'echo "inner=$?" >> "' + str(self.log) + '"\n' + self.moves_to_the_hubs_pin())
        done = self.sd("task", "show", str(self.item))
        self.assertEqual(done.returncode, 0, done.stderr)
        logged = self.logged()
        self.assertEqual(logged.count("args=follow marker=1 wait=120"), 1)
        self.assertIn("inner=1", logged)
        self.assertTrue(any("still refused after a follow in this process chain" in line for line in logged), logged)

    def test_the_hub_itself_never_follows(self):
        # No hub.json: the command opens the local file, and the follow is never looked for.
        self.follow(self.moves_to_the_hubs_pin())
        (self.home / ".config" / "sd" / "hub.json").unlink()
        done = self.sd("task", "show", str(self.item), env={"XDG_DATA_HOME": str(self.root / "nowhere")})
        self.assertEqual(self.logged(), [])
        self.assertNotIn("following the hub's pins", done.stderr)


if __name__ == "__main__":
    unittest.main()
