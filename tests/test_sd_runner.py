"""The pack forwards the finite command CLI and preserves its durable evidence."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sd_db import connect, initialise
from sd_db.writes import create_item, upsert_repo

ROOT = Path(__file__).resolve().parents[1]


class RunnerCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "catalog-home"
        self.process_home = self.root / "process-home"
        self.process_home.mkdir()
        self.database = self.root / "custom" / "commands.db"
        initialise(self.database)
        self.connection = connect(self.database)
        self.addCleanup(self.connection.close)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        upsert_repo(self.connection, str(self.repo))
        self.item = create_item(
            self.connection, kind="task", title="CLI fixture", repo=str(self.repo)
        )
        self.program = self.root / "registered-inspection"
        self.program.write_text(
            f"#!{sys.executable}\nimport sys\nprint('item=' + sys.argv[1])\n"
        )
        self.program.chmod(0o700)
        catalog = self.home / ".local/share/sd/commands.yaml"
        catalog.parent.mkdir(parents=True)
        entry = {
            "argv": [str(self.program), "{item}"],
            "screens": ["item"],
            "mutates": False,
            "scope": "worktree",
            "placeholders": {"item": "item"},
        }
        catalog.write_text("version: 1\ncommands:\n  inspect: " + json.dumps(entry))
        self.options = [
            "--database", str(self.database), "--home", str(self.home)
        ]

    def invoke(self, *args, shared=False):
        command = (
            [sys.executable, "-m", "sd_db.runner_palette"]
            if shared else [sys.executable, str(ROOT / "bin/sd"), "runner", "commands"]
        )
        return subprocess.run(
            [*command, *args],
            env={**os.environ, "HOME": str(self.process_home)},
            capture_output=True, text=True, check=False, timeout=10,
        )

    def json_result(self, *args):
        result = self.invoke(*self.options, *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def snapshot(self):
        return tuple(self.connection.iterdump())

    def prepare_args(self, **changes):
        current = self.json_result("catalog", "--item", str(self.item))
        options = {
            "--item": str(self.item), "--command": "inspect",
            "--if-revision": current["revision"], "--catalog": current["sha256"],
            "--value": f"item={self.item}",
        }
        options.update(changes)
        return ["prepare", *(value for pair in options.items() for value in pair)]

    def test_help_and_usage_match_shared_cli_without_default_home_writes(self):
        before = self.snapshot()
        for args in (
            (), ("--help",), ("prepare", "--help"), ("unknown",),
            ("--database",), ("--unregistered",),
            (*self.options, "prepare", "--item", str(self.item)),
        ):
            with self.subTest(args=args):
                actual = self.invoke(*args)
                expected = self.invoke(*args, shared=True)
                self.assertEqual(
                    (actual.returncode, actual.stdout, actual.stderr),
                    (expected.returncode, expected.stdout, expected.stderr),
                )
                self.assertNotIn("Traceback", actual.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.process_home.iterdir()), [])
        self.assertFalse((self.home / ".local/share/sd/sd.db").exists())

    def test_catalog_forwards_explicit_database_home_and_item(self):
        before = self.snapshot()
        args = (*self.options, "catalog", "--item", str(self.item))
        actual = self.invoke(*args)
        expected = self.invoke(*args, shared=True)
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected.stdout)
        current = json.loads(actual.stdout)
        self.assertTrue(current["configured"])
        self.assertEqual(current["item"], self.item)
        self.assertEqual([entry["name"] for entry in current["entries"]], ["inspect"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.process_home.iterdir()), [])

    def test_prepare_execute_and_output_keep_one_durable_note(self):
        prepared = self.json_result(*self.prepare_args())
        execution = prepared["execution"]
        self.assertEqual(prepared["assignments"], [])
        self.assertFalse(Path(execution["output_path"]).exists())
        result = self.json_result("execute", str(execution["note"]))
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["output"], f"item={self.item}\n")
        output = self.json_result("output", str(execution["note"]), "--offset", "5")
        self.assertEqual(output["output"], f"item={self.item}\n"[5:])
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM note WHERE kind='exec'").fetchone()[0],
            1,
        )
        self.assertEqual(list(self.repo.iterdir()), [])
        self.assertEqual(list(self.process_home.iterdir()), [])
        replay = self.invoke(*self.options, "execute", str(execution["note"]))
        self.assertEqual(replay.returncode, 1)
        self.assertIn("already ended", replay.stderr)

    def test_invalid_requests_refuse_without_recording_or_executing(self):
        before = self.snapshot()
        for changes, message in (
            ({"--command": "absent"}, "not registered"),
            ({"--value": "item=1;touch bad"}, "invalid literal"),
            ({"--value": f"argv={self.program}"}, "registered placeholder"),
            ({"--catalog": "0" * 64}, "catalog changed"),
        ):
            with self.subTest(changes=changes):
                result = self.invoke(*self.options, *self.prepare_args(**changes))
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.repo.iterdir()), [])
        self.assertFalse((self.database.parent / "executions").exists())

    def test_existing_queue_list_still_returns_an_object(self):
        initialise(home=self.process_home)
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin/sd"), "runner", "list", "--json"],
            env={**os.environ, "HOME": str(self.process_home)},
            capture_output=True, text=True, check=False, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"queued": [], "active": []})


class RunnerPreparation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        self.env = {
            **os.environ, "HOME": str(self.home),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        }
        initialise(home=self.home)
        self.connection = connect(home=self.home)
        self.addCleanup(self.connection.close)
        self.item = create_item(self.connection, kind="task", title="Prepare here")
        self.remote = self.root / "upstream.git"
        self.repo = self.root / "repo"
        self.git("init", "--bare", "--initial-branch=main", str(self.remote))
        self.git("clone", str(self.remote), str(self.repo))
        self.git(
            "-C", str(self.repo), "-c", "user.name=Fixture",
            "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty",
            "-m", "Fixture seed",
        )
        self.git("-C", str(self.repo), "push", "origin", "main")

    def git(self, *args):
        return subprocess.run(
            ["git", *args], env=self.env, capture_output=True, text=True,
            check=True, timeout=10,
        )

    def prepare(self, cwd, *extra):
        return subprocess.run(
            [sys.executable, str(ROOT / "bin/sd"), "runner", "prepare",
             str(self.item), "--branch", "item/fixture", "--json", *extra],
            cwd=cwd, env=self.env, capture_output=True, text=True,
            check=False, timeout=10,
        )

    def test_prepare_resolves_registered_repository_from_nested_cwd(self):
        upsert_repo(self.connection, str(self.repo), remote=str(self.remote))
        nested = self.repo / "nested"
        nested.mkdir()
        result = self.prepare(nested)
        self.assertEqual(result.returncode, 0, result.stderr)
        item = json.loads(result.stdout)["item"]
        self.assertEqual(item["repo"], str(self.repo))
        self.assertEqual(item["branch"], "item/fixture")
        self.assertEqual(self.git("-C", str(self.repo), "branch", "--show-current").stdout.strip(), "main")

    def test_prepare_refuses_unregistered_cwd_and_repository_override(self):
        before = tuple(self.connection.iterdump())
        for cwd, extra, message in (
            (self.repo, (), "registered repository"),
            (self.root, (), "requires a Git checkout"),
            (self.repo, ("--repo", str(self.repo)), "unrecognized arguments"),
        ):
            with self.subTest(cwd=cwd, extra=extra):
                result = self.prepare(cwd, *extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(tuple(self.connection.iterdump()), before)


if __name__ == "__main__":
    unittest.main()
