"""Fixtures for `bin/sd_fleet.py`: `sd fleet stamp` over throwaway repositories.

Every repository here is a temporary git checkout with a github.com origin
URL that is never contacted: `origin/HEAD` is a local ref the fixture sets,
and nothing fetches. The repository rows are handed in, so no test reads the
workflow database.
"""

from __future__ import annotations

import argparse
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_fleet  # noqa: E402
import sd_install  # noqa: E402
import sd_lib  # noqa: E402
import sd_setup_github  # noqa: E402

PIN = "1" * 40
CI = "name: ci\non:\n  pull_request:\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def args(**overrides) -> argparse.Namespace:
    values = {"dry_run": True, "only": [], "pin": PIN, "json": False}
    values.update(overrides)
    return argparse.Namespace(**values)


def remote(*, admin: bool = True, fork: bool = False, others: tuple[str, ...] = ()):
    """An `ask` seam answering the three ownership questions; nothing reaches the network."""
    people = [{"login": "me", "permissions": {"push": True}}]
    people += [{"login": who, "permissions": {"push": True}} for who in others]
    answers = {sd_lib.VIEWER_QUERY: {"login": "me"},
               sd_lib.REPOSITORY_QUERY: {"full_name": "o/r", "fork": fork, "permissions": {"admin": admin}},
               sd_lib.COLLABORATOR_QUERY: people}
    return lambda endpoint, root: (answers[endpoint], "")


def snapshot(root: pathlib.Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and ".git" not in p.relative_to(root).parts}


class Fleet(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name).resolve()

    def repo(self, name: str, files: dict[str, str] | None = None, *, owner: str = "platypeeps",
             local: str | None = None) -> tuple[pathlib.Path, str]:
        root = self.tmp / name
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "t")
        git(root, "config", "maintenance.auto", "false")
        remote = f"https://github.com/{owner}/{name}"
        git(root, "remote", "add", "origin", remote)
        for rel, text in {"README.md": "x\n", **(files or {})}.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "init")
        git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        if local is not None:
            (root / "CLAUDE.local.md").write_text(local, encoding="utf-8")
        return root, remote

    def run_stamp(self, rows, cwd=None, ask=None, **overrides) -> tuple[int, str]:
        out = io.StringIO()
        code = sd_fleet.fleet_stamp(args(**overrides), rows=lambda: rows, stream=out, cwd=cwd,
                                    ask=ask or remote())
        return code, out.getvalue()

    def plan(self, rows, cwd=None, ask=None, **overrides) -> list[dict]:
        code, text = self.run_stamp(rows, cwd, ask, json=True, **overrides)
        return json.loads(text)["repos"]


class DryRun(Fleet):
    def test_bare_repository_gets_every_file(self) -> None:
        root, remote = self.repo("bare")
        [plan] = self.plan([(root, remote)])
        paths = [change["path"] for change in plan["changes"]]
        self.assertEqual(paths, [".github/workflows/sd-review-route.yml", ".github/dependabot.yml",
                                 ".github/workflows/sd-check.yml", ".github/sd-status.json", ".gitignore",
                                 "CLAUDE.local.md", "docs/dashboard"])
        self.assertIn(f"review-route@{PIN}", plan["changes"][0]["diff"])
        self.assertEqual(plan["refused"], [])

    def test_dry_run_writes_nothing(self) -> None:
        root, remote = self.repo("quiet")
        before = snapshot(root)
        code, text = self.run_stamp([(root, remote)])
        self.assertEqual(code, sd_fleet.EXIT_OK)
        self.assertEqual(snapshot(root), before)
        self.assertFalse((root / "docs" / "dashboard").exists())
        self.assertIn("dry run: nothing was written", text)

    def test_diff_is_against_origin_head_not_the_checkout(self) -> None:
        root, remote = self.repo("stale", {".gitignore": "docs/dashboard/\n"})
        (root / ".gitignore").write_text("", encoding="utf-8")  # the working tree says otherwise
        [plan] = self.plan([(root, remote)])
        self.assertNotIn(".gitignore", [change["path"] for change in plan["changes"]])

    def test_existing_pull_request_workflow_is_kept_and_no_check_is_laid(self) -> None:
        root, remote = self.repo("ci", {".github/workflows/ci.yml": CI})
        [plan] = self.plan([(root, remote)])
        self.assertNotIn(sd_fleet.CHECK_PATH, [change["path"] for change in plan["changes"]])
        self.assertTrue(any(line.startswith(sd_fleet.CHECK_PATH) for line in plan["adapted"]))

    def test_employer_repository_gets_no_unprotected_declaration(self) -> None:
        root, remote = self.repo("work", owner="answerbook")
        [plan] = self.plan([(root, remote)])
        self.assertNotIn(sd_fleet.STATUS_PATH, [change["path"] for change in plan["changes"]])
        self.assertTrue(any("protection stands" in line for line in plan["adapted"]))

    def test_co_owned_repository_gets_files_but_no_declaration(self) -> None:
        root, remote_url = self.repo("shared")
        [plan] = self.plan([(root, remote_url)], ask=remote(others=("colleague",)))
        paths = [change["path"] for change in plan["changes"]]
        self.assertIn(sd_fleet.ROUTE_PATH, paths)
        self.assertNotIn(sd_fleet.STATUS_PATH, paths)

    def test_fork_or_unadministered_remote_gets_no_tracked_file(self) -> None:
        for name, ask in (("fork", remote(fork=True)), ("visitor", remote(admin=False))):
            root, remote_url = self.repo(name)
            [plan] = self.plan([(root, remote_url)], ask=ask)
            self.assertEqual({change["where"] for change in plan["changes"]}, {"local"}, name)
            self.assertTrue(plan["refused"][0].startswith("tracked files:"), name)

    def test_status_keeps_other_entries_and_rewrites_unprotected(self) -> None:
        other = {"id": "reviews", "state": {"required_pull_request_reviews": False},
                 "because": "b", "since": "2026-01-01", "until": "u"}
        old = {"id": "unprotected", "state": {"branch_protection": False},
               "because": "cites ruleset 17617253", "since": "2026-09-12", "until": "u"}
        current = json.dumps({"$schema": "./s.json", "accepted_gaps": [other, old]}, indent=2) + "\n"
        written = json.loads(sd_fleet.status_text(current))
        self.assertEqual(written["$schema"], "./s.json")
        self.assertEqual(written["accepted_gaps"], [other, sd_fleet.UNPROTECTED_ENTRY])
        self.assertEqual(sd_fleet.status_text(sd_fleet.status_text(current)), sd_fleet.status_text(current))

    def test_malformed_status_is_refused(self) -> None:
        root, remote = self.repo("broken", {".github/sd-status.json": "{nope"})
        code, _ = self.run_stamp([(root, remote)])
        [plan] = self.plan([(root, remote)])
        self.assertEqual(code, sd_fleet.EXIT_REFUSED)
        self.assertTrue(plan["refused"][0].startswith(sd_fleet.STATUS_PATH))

    def test_settled_modes_get_no_tracked_file(self) -> None:
        for mode in ("guest", "minimal"):
            local = f"{sd_install.BLOCK_BEGIN}\n    mode: {mode}\n{sd_install.BLOCK_END}\n"
            root, remote = self.repo(mode, local=local)
            [plan] = self.plan([(root, remote)])
            self.assertEqual({change["where"] for change in plan["changes"]}, {"local"}, mode)
            self.assertIn(f"mode {mode}", plan["refused"][0])

    def test_the_pack_itself_names_no_pin_and_gets_no_guard(self) -> None:
        root, _ = self.repo("sd-ai-command-pack")
        [plan] = self.plan([(root, "git@github.com:platypeeps/sd-ai-command-pack.git")])
        paths = [change["path"] for change in plan["changes"]]
        self.assertNotIn(sd_fleet.DEPENDABOT_PATH, paths)
        self.assertIn(f"$/{sd_setup_github.ACTION_SUBPATH}", plan["changes"][0]["diff"])

    def test_local_block_keeps_the_operators_answers(self) -> None:
        local = f"mine\n\n{sd_install.BLOCK_BEGIN}\n    test: make unit\n{sd_install.BLOCK_END}\n"
        root, remote = self.repo("answers", local=local)
        [plan] = self.plan([(root, remote)])
        [change] = [c for c in plan["changes"] if c["path"] == "CLAUDE.local.md"]
        self.assertIn(" mine\n", change["diff"])
        self.assertIn(" " * 5 + "test: make unit", change["diff"])
        self.assertIn("+# Parallel work follows", change["diff"])

    def test_only_selects_by_name_and_refuses_a_repository_outside_the_rows(self) -> None:
        one, remote_one = self.repo("one")
        two, remote_two = self.repo("two")
        [plan] = self.plan([(one, remote_one), (two, remote_two)], only=["platypeeps/two"])
        self.assertEqual(plan["repo"], str(two))
        with self.assertRaises(sd_fleet.FleetRefusal):
            self.run_stamp([(one, remote_one)], only=["platypeeps/manual"])

    def test_template_block_names_parallel_work_and_the_dashboard(self) -> None:
        self.assertIn('"Parallel work" section: one writer per checkout', sd_install.DEFAULT_BLOCK_BODY)
        self.assertIn("docs/dashboard/", sd_install.DEFAULT_BLOCK_BODY)


class Write(Fleet):
    def worktree(self, root: pathlib.Path, branch: str) -> pathlib.Path:
        into = self.tmp / f"{root.name}-wt"
        git(root, "worktree", "add", "-q", "-b", branch, str(into), "origin/main")
        return into

    def test_write_then_rerun_changes_nothing(self) -> None:
        root, remote = self.repo("stamped")
        into = self.worktree(root, "chore/stamp")
        code, _ = self.run_stamp([(root, remote)], cwd=into, dry_run=False)
        self.assertEqual(code, sd_fleet.EXIT_OK)
        self.assertTrue((into / sd_fleet.CHECK_PATH).is_file())
        self.assertTrue((into / "docs" / "dashboard").is_dir())
        self.assertIn(sd_install.BLOCK_BEGIN, (into / "CLAUDE.local.md").read_text(encoding="utf-8"))
        self.assertFalse((root / sd_fleet.CHECK_PATH).exists())  # only the checkout the caller stands in
        [again] = self.plan([(root, remote)], cwd=into, dry_run=False)
        self.assertEqual(again["changes"], [])

    def test_default_branch_gets_the_untracked_files_only(self) -> None:
        root, remote = self.repo("main-only")
        before = git(root, "status", "--porcelain", "--untracked-files=no")
        [plan] = self.plan([(root, remote)], cwd=root, dry_run=False)
        self.assertEqual({change["where"] for change in plan["changes"]}, {"local"})
        self.assertTrue(any("default branch" in line for line in plan["adapted"]))
        self.assertFalse((root / sd_fleet.CHECK_PATH).exists())
        self.assertTrue((root / "CLAUDE.local.md").is_file())
        self.assertEqual(git(root, "status", "--porcelain", "--untracked-files=no"), before)

    def test_master_without_origin_head_is_a_default_branch(self) -> None:
        root, remote_url = self.repo("old")
        git(root, "branch", "-m", "main", "master")
        git(root, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
        [plan] = self.plan([(root, remote_url)], cwd=root, dry_run=False)
        self.assertEqual({change["where"] for change in plan["changes"]}, {"local"})

    def test_write_refuses_a_checkout_outside_the_auto_rows(self) -> None:
        root, remote = self.repo("one")
        other, _ = self.repo("two")
        with self.assertRaisesRegex(sd_fleet.FleetRefusal, "not a checkout of a runner_merge=auto"):
            self.run_stamp([(root, remote)], cwd=other, dry_run=False)

    def test_write_takes_no_selection(self) -> None:
        root, remote = self.repo("unnamed")
        with self.assertRaisesRegex(sd_fleet.FleetRefusal, "--only"):
            self.run_stamp([(root, remote)], cwd=root, dry_run=False, only=["platypeeps/unnamed"])


class Wiring(unittest.TestCase):
    def test_sd_exposes_the_verb(self) -> None:
        done = subprocess.run([sys.executable, str(REPO_ROOT / "bin" / "sd"), "fleet", "stamp", "--help"],
                              capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("--dry-run", done.stdout)


if __name__ == "__main__":
    unittest.main()
