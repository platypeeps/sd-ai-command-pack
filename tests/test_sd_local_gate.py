"""The local CI gate (sd:1843): `sd-check` at the exact head, posted as `sd/local-gate`.

Real git and a real `sd-check` child against a throwaway repository; the
GitHub side is a recorder, so nothing leaves the machine.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lib  # noqa: E402
import sd_local_gate  # noqa: E402
from sd_ship_remote import Refusal  # noqa: E402


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


class Recorder:
    """The `GitHub` calls the gate makes, answered from memory; posts land as `me`'s statuses."""

    prefix = "repos/o/r"

    def __init__(self, statuses: list | None = None) -> None:
        self.statuses = statuses or []
        self.posts: list[tuple[str, dict]] = []

    def viewer_login(self) -> str:
        return "Me"

    def pages(self, path: str, field: str | None = None) -> list:
        return list(self.statuses)

    def api(self, path: str, *, method: str = "GET", body: dict | None = None) -> dict:
        assert method == "POST", method
        self.posts.append((path, body or {}))
        self.statuses.insert(0, {**(body or {}), "sha": path.rsplit("/", 1)[1], "creator": {"login": "Me"}})
        return {"state": (body or {}).get("state")}


class Repository(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name).resolve() / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")

    def commit(self, makefile: str) -> str:
        (self.root / "Makefile").write_text(makefile, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "c")
        return git(self.root, "rev-parse", "HEAD")

    def worktrees(self) -> int:
        return git(self.root, "worktree", "list", "--porcelain").count("worktree ")


class RunCheck(Repository):
    def test_a_passing_check_is_a_success_at_the_head_it_ran_on(self) -> None:
        head = self.commit("check:\n\t@echo ok\n")
        result = sd_local_gate.check_in_worktree(self.root, head)
        self.assertEqual((result["head"], result["status"]), (head, "success"))
        self.assertIn("check pass", result["summary"])

    def test_a_failing_check_is_a_failure(self) -> None:
        head = self.commit("check:\n\t@false\n")
        result = sd_local_gate.check_in_worktree(self.root, head)
        self.assertEqual(result["status"], "failure")
        self.assertIn("check fail", result["summary"])

    def test_the_check_runs_in_a_clean_worktree_not_the_operators_checkout(self) -> None:
        """An untracked file in the checkout that would fail the check is not seen."""
        head = self.commit("check:\n\t@test ! -e dirty.txt\n")
        (self.root / "dirty.txt").write_text("operator's uncommitted state\n", encoding="utf-8")
        self.assertEqual(sd_local_gate.check_in_worktree(self.root, head)["status"], "success")

    def test_the_named_commit_is_checked_not_the_checkouts_head(self) -> None:
        first = self.commit("check:\n\t@false\n")
        self.commit("check:\n\t@echo ok\n")
        result = sd_local_gate.check_in_worktree(self.root, first)
        self.assertEqual((result["head"], result["status"]), (first, "failure"))

    def test_a_pythonpath_at_the_root_does_not_reach_the_child(self) -> None:
        """An editable install pointed at the dirty checkout must not be importable in the gate."""
        head = self.commit('check:\n\t@test -z "$$PYTHONPATH" && test -z "$$VIRTUAL_ENV"\n')
        with mock.patch.dict(os.environ, {"PYTHONPATH": str(self.root), "VIRTUAL_ENV": str(self.root / ".venv")}):
            self.assertEqual(sd_local_gate.check_in_worktree(self.root, head)["status"], "success")

    def test_the_environment_drops_package_selectors_and_path_entries_in_the_checkout(self) -> None:
        inside, outside = str(self.root / ".venv/bin"), "/usr/bin"
        env = sd_local_gate.gate_environment(self.root, {
            "PATH": os.pathsep.join([inside, outside, "relative/bin"]), "PYTHONPATH": str(self.root),
            "PYTHONHOME": "/x", "VIRTUAL_ENV": inside, "CONDA_PREFIX": "/c", "__PYVENV_LAUNCHER__": "/l", "HOME": "/h"})
        self.assertEqual(env, {"PATH": outside, "HOME": "/h"})

    def test_a_virtualenv_bin_outside_the_checkout_is_dropped_from_path(self) -> None:
        """A venv's `bin` is found by the `pyvenv.cfg` beside it, wherever it lives."""
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        venv, plain = pathlib.Path(outside.name) / "venv", pathlib.Path(outside.name) / "tools"
        (venv / "bin").mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
        plain.mkdir()
        env = sd_local_gate.gate_environment(self.root, {"PATH": os.pathsep.join([str(venv / "bin"), str(plain)])})
        self.assertEqual(env["PATH"], str(plain))

    def test_the_worktree_is_removed_after_the_run(self) -> None:
        head = self.commit("check:\n\t@echo ok\n")
        before = self.worktrees()
        sd_local_gate.check_in_worktree(self.root, head)
        self.assertEqual(self.worktrees(), before)


class Reading(unittest.TestCase):
    def test_only_an_exit_zero_pass_is_a_success(self) -> None:
        passed = '{"status": "pass", "checks": [{"name": "check", "status": "pass"}]}'
        self.assertEqual(sd_local_gate.check_reading(0, passed)["status"], "success")
        for code, output in ((0, '{"status": "absent", "checks": []}'), (0, '{"status": "skipped"}'),
                             (1, '{"status": "fail"}'), (2, ""), (None, "timed out"), (0, "not json")):
            with self.subTest(code=code, output=output):
                self.assertEqual(sd_local_gate.check_reading(code, output)["status"], "failure")


class Post(unittest.TestCase):
    HEAD = "a" * 40

    def test_success_is_posted_to_the_checked_head_under_the_context(self) -> None:
        api = Recorder()
        sd_local_gate.post_gate_status(api, self.HEAD, {"head": self.HEAD, "status": "success", "summary": "sd-check pass"},
                                       "0123456789ab")
        [(path, body)] = api.posts
        self.assertEqual(path, f"repos/o/r/statuses/{self.HEAD}")
        self.assertEqual((body["state"], body["context"]), ("success", "sd/local-gate"))
        self.assertTrue(body["description"].startswith(f"{self.HEAD[:12]} inputs 0123456789ab: "))
        self.assertLessEqual(len(body["description"]), 140)

    def test_a_result_for_another_sha_is_refused_and_nothing_is_posted(self) -> None:
        api = Recorder()
        with self.assertRaisesRegex(Refusal, "no status is posted for a commit that was not checked"):
            sd_local_gate.post_gate_status(api, self.HEAD, {"head": "b" * 40, "status": "success"}, "0" * 12)
        self.assertEqual(api.posts, [])

    def test_a_failure_posts_failure(self) -> None:
        api = Recorder()
        sd_local_gate.post_gate_status(api, self.HEAD, {"head": self.HEAD, "status": "failure", "summary": "x" * 300},
                                       "0" * 12)
        self.assertEqual(api.posts[0][1]["state"], "failure")
        self.assertEqual(len(api.posts[0][1]["description"]), 140)


class Gate(Repository):
    """Every merge attempt runs `sd-check` and posts a fresh status; nothing is reused."""

    def test_a_prior_matching_success_at_the_head_still_runs_the_check(self) -> None:
        head = self.commit("check:\n\t@false\n")
        inputs = sd_local_gate.gate_inputs(self.root, head)
        api = Recorder([{"context": "sd/local-gate", "state": "success", "sha": head, "creator": {"login": "Me"},
                         "description": f"{head[:12]} inputs {inputs}: sd-check pass (check pass)"}])
        result = sd_local_gate.local_gate(api, self.root, head)
        self.assertEqual((result["status"], [body["state"] for _, body in api.posts]), ("failure", ["failure"]))

    def test_each_attempt_posts_its_own_status_carrying_the_inputs_digest(self) -> None:
        head = self.commit("check:\n\t@echo ok\n")
        api = Recorder()
        sd_local_gate.local_gate(api, self.root, head)
        sd_local_gate.local_gate(api, self.root, head)
        inputs = sd_local_gate.gate_inputs(self.root, head)
        self.assertEqual([body["state"] for _, body in api.posts], ["success", "success"])
        self.assertTrue(api.posts[1][1]["description"].startswith(f"{head[:12]} inputs {inputs}: "))

    def test_the_digest_follows_the_local_block(self) -> None:
        head = self.commit("check:\n\t@echo ok\n")
        before = sd_local_gate.gate_inputs(self.root, head)
        (self.root / "CLAUDE.local.md").write_text("check: make other\n", encoding="utf-8")
        self.assertNotEqual(sd_local_gate.gate_inputs(self.root, head), before)


class CiMode(unittest.TestCase):
    """`sd_lib.repo_ci` answers `github` on every doubt, so ci=github is unchanged."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = pathlib.Path(tmp.name).resolve()
        from sd_db import connect, initialise, upsert_repo

        self.database = self.home / ".local/share/sd/sd.db"
        initialise(self.database)
        self.connection = connect(self.database)
        self.addCleanup(self.connection.close)
        self.root = self.home / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        upsert_repo(self.connection, str(self.root), remote=None)

    def columns(self) -> set[str]:
        return {row[1] for row in self.connection.execute("PRAGMA table_info(repo)")}

    def test_a_library_without_the_reader_answers_github(self) -> None:
        import sd_db.repos

        # A schema-15 database: the pinned library creates repo.ci, so drop it.
        if "ci" in self.columns():
            self.connection.execute("ALTER TABLE repo DROP COLUMN ci")
        self.assertNotIn("ci", self.columns())
        with mock.patch.object(sd_db.repos, "repo_ci", None, create=True):
            self.assertEqual(sd_lib.repo_ci(self.connection, self.root), "github")

    def test_the_librarys_local_answer_is_returned(self) -> None:
        import sd_db.repos

        with mock.patch.object(sd_db.repos, "repo_ci", lambda connection, path: "local", create=True):
            self.assertEqual(sd_lib.repo_ci(self.connection, self.root), "local")

    def test_without_the_reader_the_column_is_read_when_present(self) -> None:
        import sd_db.repos

        if "ci" not in self.columns():  # a library older than schema 16
            self.connection.execute("ALTER TABLE repo ADD COLUMN ci TEXT NOT NULL DEFAULT 'github'")
        self.connection.execute("UPDATE repo SET ci = 'local'")
        with mock.patch.object(sd_db.repos, "repo_ci", None, create=True):
            self.assertEqual(sd_lib.repo_ci(self.connection, self.root), "local")

    def test_an_unknown_value_or_a_failing_read_answers_github(self) -> None:
        import sd_db.repos

        def broken(connection, path):
            raise RuntimeError("no such column: ci")

        for reader in (lambda connection, path: "sometimes", broken):
            with self.subTest(reader=reader), mock.patch.object(sd_db.repos, "repo_ci", reader, create=True):
                self.assertEqual(sd_lib.repo_ci(self.connection, self.root), "github")

    def test_ci_mode_with_no_database_answers_github(self) -> None:
        with mock.patch.dict(os.environ, {"HOME": str(self.home / "elsewhere")}):
            self.assertEqual(sd_lib.ci_mode(self.root), "github")


if __name__ == "__main__":
    unittest.main()
