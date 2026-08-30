"""Fixtures for bin/sd-handoff: the writer half of the local handoff lane.

Every test runs the real executable in a subprocess against a real `git init`
repository under a temporary directory, with HOME redirected so no test can
reach the operator's `~/.local/state`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
HANDOFF = REPO_ROOT / "bin" / "sd-handoff"

GIT_IDENTITY = (
    "-c",
    "user.email=handoff@example.invalid",
    "-c",
    "user.name=Handoff Fixture",
    "-c",
    "commit.gpgsign=false",
)


def git(cwd: pathlib.Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *GIT_IDENTITY, *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
    )
    return completed.stdout


class HandoffFixture(unittest.TestCase):
    """A temp HOME, a temp repository, and a way to run the executable."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = pathlib.Path(os.path.realpath(self._temp.name))
        self.home = base / "home"
        self.home.mkdir()
        self.repo = base / "repo"
        self.repo.mkdir()
        self.init_repo(self.repo)

    def init_repo(self, path: pathlib.Path) -> None:
        git(path, "init", "-q", "-b", "main", ".")
        (path / "a.txt").write_text("one\n", encoding="utf-8")
        git(path, "add", "a.txt")
        git(path, "commit", "-qm", "first")

    def env(self, cwd: pathlib.Path, **extra: str) -> dict[str, str]:
        environment = dict(os.environ)
        for key in ("XDG_STATE_HOME", "CLAUDE_PROJECT_DIR", "SD_HANDOFF_RESTORE"):
            environment.pop(key, None)
        environment["HOME"] = str(self.home)
        environment["PWD"] = str(cwd)
        environment.update(extra)
        return environment

    def run_handoff(
        self, *args: str, cwd: pathlib.Path | None = None, **extra: str
    ) -> subprocess.CompletedProcess[str]:
        where = cwd or self.repo
        return subprocess.run(
            [str(HANDOFF), *args],
            cwd=str(where),
            env=self.env(where, **extra),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def packet_path(self, root: pathlib.Path) -> pathlib.Path:
        digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
        return (
            self.home
            / ".local"
            / "state"
            / "sd-ai-command-pack"
            / "handoff"
            / f"{digest}.json"
        )

    def packet(self, root: pathlib.Path | None = None) -> dict:
        path = self.packet_path(root or self.repo)
        return json.loads(path.read_text(encoding="utf-8"))


class WriteTests(HandoffFixture):
    def test_writes_one_packet_keyed_on_the_worktree_root(self) -> None:
        result = self.run_handoff("--summary", "halfway through the parser")
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.packet_path(self.repo)
        self.assertTrue(path.is_file(), result.stdout)
        packet = self.packet()
        self.assertEqual(packet["schema"], "sd-handoff/1")
        self.assertEqual(packet["repo"]["root"], str(self.repo))
        self.assertIsNone(packet["consumed"])
        self.assertEqual(packet["summary"], "halfway through the parser")

    def test_expiry_is_fourteen_days_after_creation(self) -> None:
        self.run_handoff("--summary", "s")
        packet = self.packet()
        created = dt.datetime.fromisoformat(packet["created"])
        expires = dt.datetime.fromisoformat(packet["expires"])
        self.assertEqual(expires - created, dt.timedelta(days=14))

    def test_a_subdirectory_normalizes_to_the_same_packet(self) -> None:
        nested = self.repo / "src" / "deep"
        nested.mkdir(parents=True)
        result = self.run_handoff("--summary", "from a subdirectory", cwd=nested)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.packet_path(self.repo).is_file())
        self.assertEqual(self.packet()["repo"]["cwd_raw"], str(nested))

    def test_item_may_be_absent(self) -> None:
        self.run_handoff("--summary", "no work item here")
        self.assertIsNone(self.packet()["item"])

    def test_item_is_recorded_when_given(self) -> None:
        self.run_handoff("--summary", "s", "--item", "docs/work/2026-08-29-thing")
        self.assertEqual(self.packet()["item"], "docs/work/2026-08-29-thing")

    def test_a_new_write_replaces_the_old_packet(self) -> None:
        self.run_handoff("--summary", "first attempt")
        self.run_handoff("--summary", "second attempt")
        packet = self.packet()
        self.assertEqual(packet["summary"], "second attempt")
        directory = self.packet_path(self.repo).parent
        self.assertEqual(len(list(directory.glob("*.json"))), 1)

    def test_files_are_derived_from_git_not_typed(self) -> None:
        (self.repo / "a.txt").write_text("changed\n", encoding="utf-8")
        (self.repo / "untracked.md").write_text("new\n", encoding="utf-8")
        staged = self.repo / "staged.py"
        staged.write_text("x = 1\n", encoding="utf-8")
        git(self.repo, "add", "staged.py")
        self.run_handoff("--summary", "s")
        self.assertEqual(
            self.packet()["files"], ["a.txt", "staged.py", "untracked.md"]
        )

    def test_a_clean_tree_lists_no_files(self) -> None:
        self.run_handoff("--summary", "s")
        self.assertEqual(self.packet()["files"], [])

    def test_stash_ref_is_recorded_outside_refs_heads(self) -> None:
        self.run_handoff("--summary", "s", "--stash-ref", "refs/sd-handoff/abc123")
        self.assertEqual(self.packet()["stash_ref"], "refs/sd-handoff/abc123")

    def test_remote_is_recorded_and_canonicalized(self) -> None:
        git(self.repo, "remote", "add", "origin", "git@github.com:o/r.git")
        self.run_handoff("--summary", "s")
        self.assertEqual(self.packet()["repo"]["remote"], "git@github.com:o/r")

    def test_a_directory_outside_any_repository_still_gets_a_packet(self) -> None:
        plain = pathlib.Path(os.path.realpath(self._temp.name)) / "plain"
        plain.mkdir()
        result = self.run_handoff("--summary", "notes, no repo", cwd=plain)
        self.assertEqual(result.returncode, 0, result.stderr)
        packet = self.packet(plain)
        self.assertEqual(packet["repo"]["root"], str(plain))
        self.assertIsNone(packet["repo"]["head_sha"])
        self.assertEqual(packet["files"], [])

    def test_two_worktrees_of_one_repository_get_distinct_packets(self) -> None:
        linked = pathlib.Path(os.path.realpath(self._temp.name)) / "linked"
        git(self.repo, "worktree", "add", "-q", "-b", "side", str(linked))
        self.run_handoff("--summary", "main checkout work")
        self.run_handoff("--summary", "worktree work", cwd=linked)
        self.assertNotEqual(
            self.packet_path(self.repo), self.packet_path(linked)
        )
        self.assertEqual(self.packet(self.repo)["summary"], "main checkout work")
        self.assertEqual(self.packet(linked)["summary"], "worktree work")

    def test_claude_project_dir_never_wins_over_the_working_directory(self) -> None:
        linked = pathlib.Path(os.path.realpath(self._temp.name)) / "linked"
        git(self.repo, "worktree", "add", "-q", "-b", "side", str(linked))
        result = self.run_handoff(
            "--summary",
            "written inside the worktree",
            cwd=linked,
            CLAUDE_PROJECT_DIR=str(self.repo),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.packet_path(linked).is_file())
        self.assertFalse(self.packet_path(self.repo).exists())

    def test_explicit_cwd_outranks_the_environment(self) -> None:
        other = pathlib.Path(os.path.realpath(self._temp.name)) / "other"
        other.mkdir()
        self.run_handoff("--summary", "s", "--cwd", str(other))
        self.assertTrue(self.packet_path(other).is_file())
        self.assertFalse(self.packet_path(self.repo).exists())


class LimitTests(HandoffFixture):
    """The field limits are the packet's shape, so they are table-driven."""

    CASES = (
        ("next", "--next", 5),
        ("dont", "--dont", 5),
        ("questions", "--question", 3),
    )

    def test_repeatable_fields_keep_only_their_limit(self) -> None:
        args: list[str] = ["--summary", "s"]
        for _, flag, limit in self.CASES:
            for index in range(limit + 3):
                args.extend([flag, f"entry {index}"])
        result = self.run_handoff(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        packet = self.packet()
        for field, flag, limit in self.CASES:
            with self.subTest(field=field):
                self.assertEqual(len(packet[field]), limit)
                self.assertEqual(packet[field][0], "entry 0")
                self.assertEqual(packet[field][-1], f"entry {limit - 1}")
                self.assertIn(f"--{flag.lstrip('-')}", result.stderr)

    def test_summary_is_truncated_at_six_hundred_characters(self) -> None:
        self.run_handoff("--summary", "x" * 900)
        self.assertEqual(len(self.packet()["summary"]), 600)

    def test_a_short_summary_is_left_alone(self) -> None:
        self.run_handoff("--summary", "y" * 600)
        self.assertEqual(len(self.packet()["summary"]), 600)


class CapTests(HandoffFixture):
    def test_an_oversized_packet_is_refused_with_something_to_cut(self) -> None:
        result = self.run_handoff("--summary", "s", "--next", "z" * 9000)
        self.assertEqual(result.returncode, 1)
        self.assertIn("over the 8192-byte cap", result.stderr)
        self.assertIn("--next", result.stderr)
        self.assertFalse(self.packet_path(self.repo).exists())

    def test_a_refused_write_leaves_the_previous_packet_alone(self) -> None:
        self.run_handoff("--summary", "the good packet")
        result = self.run_handoff("--summary", "s", "--dont", "z" * 9000)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.packet()["summary"], "the good packet")

    def test_a_dirty_tree_trims_the_derived_file_list_instead_of_refusing(self) -> None:
        for index in range(400):
            name = f"a-rather-long-generated-filename-number-{index:04d}.txt"
            (self.repo / name).write_text("x\n", encoding="utf-8")
        result = self.run_handoff("--summary", "four hundred dirty paths")
        self.assertEqual(result.returncode, 0, result.stderr)
        body = self.packet_path(self.repo).read_bytes()
        self.assertLessEqual(len(body), 8192)
        packet = self.packet()
        self.assertEqual(packet["summary"], "four hundred dirty paths")
        self.assertTrue(packet["files"][-1].startswith("... "))
        self.assertIn("more changed files", packet["files"][-1])

    def test_every_written_packet_fits_the_cap(self) -> None:
        self.run_handoff(
            "--summary",
            "s" * 600,
            *[part for index in range(5) for part in ("--next", f"n{index}" * 40)],
            *[part for index in range(5) for part in ("--dont", f"d{index}" * 40)],
            *[part for index in range(3) for part in ("--question", f"q{index}" * 40)],
        )
        self.assertLessEqual(len(self.packet_path(self.repo).read_bytes()), 8192)


class ShowTests(HandoffFixture):
    def test_show_prints_the_packet_and_consumes_it(self) -> None:
        self.run_handoff(
            "--summary", "the parser is half converted", "--next", "finish tokenize"
        )
        shown = self.run_handoff("--show")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("the parser is half converted", shown.stdout)
        self.assertIn("finish tokenize", shown.stdout)
        self.assertIsNotNone(self.packet()["consumed"])

    def test_show_json_emits_the_packet_as_json(self) -> None:
        self.run_handoff("--summary", "machine readable")
        shown = self.run_handoff("--show", "--json")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        payload = json.loads(shown.stdout)
        self.assertEqual(payload["summary"], "machine readable")
        self.assertIsNotNone(payload["consumed"])

    def test_a_packet_loads_exactly_once(self) -> None:
        self.run_handoff("--summary", "only once")
        self.assertEqual(self.run_handoff("--show").returncode, 0)
        second = self.run_handoff("--show")
        self.assertEqual(second.returncode, 1)
        self.assertIn("already consumed", second.stderr)

    def test_show_without_a_packet_is_a_stated_refusal(self) -> None:
        result = self.run_handoff("--show")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no handoff packet is pending", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_show_reports_an_unreadable_packet_without_a_traceback(self) -> None:
        self.run_handoff("--summary", "s")
        self.packet_path(self.repo).write_text("{ not json", encoding="utf-8")
        result = self.run_handoff("--show")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not readable JSON", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class UsageTests(HandoffFixture):
    def test_an_unknown_flag_is_a_controlled_usage_error(self) -> None:
        result = self.run_handoff("--nonsense")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_help_exits_zero(self) -> None:
        result = self.run_handoff("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--dont", result.stdout)

    def test_the_writer_is_executable_and_self_contained(self) -> None:
        self.assertTrue(os.access(HANDOFF, os.X_OK))
        source = HANDOFF.read_text(encoding="utf-8")
        self.assertTrue(source.startswith("#!/usr/bin/env python3\n"))
        for forbidden in ("sd_lib", "import requests", "from installer"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
