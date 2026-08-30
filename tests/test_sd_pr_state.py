"""Fixtures for bin/sd-pr-state: live GitHub reads, and every way they fail.

The tool talks to GitHub through `gh`, so these tests give it a `gh` of their
own: a fixed-response script on a PATH that contains nothing else the tool
could reach. No test here makes a network call, and no test depends on the
operator's `gh` being installed or authenticated -- including the tests for
what happens when it is neither.

`tests/test_sd_status.py` imports this module's fixture rather than growing a
second copy of it.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = REPO_ROOT / "bin"
SD_PR_STATE = BIN / "sd-pr-state"
SD_STATUS = BIN / "sd-status"

GIT_IDENTITY = (
    "-c",
    "user.email=pr-state@example.invalid",
    "-c",
    "user.name=PR State Fixture",
    "-c",
    "commit.gpgsign=false",
)

FAKE_GH = '''#!{python}
"""A `gh` with fixed answers, so the tests never leave the machine."""
import json
import os
import sys

data = json.loads(os.environ.get("FAKE_GH", "{{}}"))
argv = sys.argv[1:]
log = os.environ.get("FAKE_GH_LOG")
if log:
    with open(log, "a", encoding="utf-8") as stream:
        stream.write(" ".join(argv) + "\\n")

if argv[:2] == ["auth", "status"]:
    sys.exit(0 if data.get("auth", True) else 1)
if argv[:1] == ["pr"]:
    print(json.dumps(data.get("pulls", [])))
    sys.exit(0)
if argv[:1] == ["api"]:
    path = argv[1]
    if path.endswith("/protection"):
        if data.get("protection") is None:
            print("gh: Not Found (HTTP 404)", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(data["protection"]))
        sys.exit(0)
    if "/compare/" in path:
        print(json.dumps({{"behind_by": data.get("behind_by", 0)}}))
        sys.exit(0)
    print(json.dumps(data.get("repo", {{}})))
    sys.exit(0)
print("unexpected: " + " ".join(argv), file=sys.stderr)
sys.exit(1)
'''

PROTECTED = {
    "required_status_checks": {"strict": True, "contexts": ["build"]},
    "required_pull_request_reviews": {"required_approving_review_count": 1},
    "enforce_admins": {"enabled": True},
}

REPO_SETTINGS = {
    "default_branch": "main",
    "squash_merge_commit_title": "PR_TITLE",
    "squash_merge_commit_message": "PR_BODY",
    "allow_rebase_merge": False,
}


def tree_digest(root: pathlib.Path) -> dict[str, str]:
    """Content hash of every file under `root`, so a write cannot hide."""
    found = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            found[str(path.relative_to(root))] = "link:" + os.readlink(path)
        elif path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            found[str(path.relative_to(root))] = digest
        elif path.is_dir():
            found[str(path.relative_to(root)) + "/"] = "dir"
    return found


class ToolFixture(unittest.TestCase):
    """A temp HOME, a temp repository, a fake `gh`, and a way to run the tools."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.base = pathlib.Path(os.path.realpath(self._temp.name))
        self.home = self.base / "home"
        self.home.mkdir()
        self.state = self.base / "state"
        self.fake_bin = self.base / "bin"
        self.fake_bin.mkdir()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.init_repo(self.repo)
        self.responses: dict[str, Any] = {}
        self.gh_installed = True
        self.link_real("git")

    # -- fixture plumbing ---------------------------------------------------

    def git(self, *args: str, cwd: pathlib.Path | None = None) -> str:
        completed = subprocess.run(
            ["git", *GIT_IDENTITY, *args],
            cwd=str(cwd or self.repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=True,
        )
        return completed.stdout

    def init_repo(self, path: pathlib.Path) -> None:
        self.git("init", "-q", "-b", "main", ".", cwd=path)
        (path / "a.txt").write_text("one\n", encoding="utf-8")
        self.git("add", "a.txt", cwd=path)
        self.git("commit", "-q", "-m", "init", cwd=path)

    def link_real(self, name: str) -> None:
        """Put one real executable on the fixture PATH, and nothing else."""
        found = shutil.which(name)
        assert found, f"{name} is required to run this suite"
        os.symlink(found, self.fake_bin / name)

    def install_gh(self) -> None:
        script = self.fake_bin / "gh"
        script.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
        script.chmod(0o755)

    def set_origin(self, url: str) -> None:
        existing = self.git("remote").split()
        self.git("remote", "set-url" if "origin" in existing else "add", "origin", url)

    def with_github(self, **responses: Any) -> None:
        """Give the repo a GitHub origin and a `gh` that answers about it."""
        self.set_origin("https://github.com/acme/widget.git")
        self.responses = {"repo": dict(REPO_SETTINGS), "protection": dict(PROTECTED)}
        self.responses.update(responses)
        self.install_gh()

    def env(self) -> dict[str, str]:
        return {
            "PATH": str(self.fake_bin),
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.state),
            "PWD": str(self.repo),
            "FAKE_GH": json.dumps(self.responses),
        }

    def run_tool(
        self, tool: pathlib.Path, *args: str, cwd: pathlib.Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        if self.gh_installed and self.responses:
            self.install_gh()
        return subprocess.run(
            [sys.executable, str(tool), *args],
            cwd=str(cwd or self.repo),
            env=self.env(),
            capture_output=True,
            text=True,
        )

    def run_json(self, tool: pathlib.Path, *args: str) -> dict[str, Any]:
        completed = self.run_tool(tool, "--json", *args)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        loaded = json.loads(completed.stdout)
        assert isinstance(loaded, dict)
        return loaded


class RepoResolutionTests(ToolFixture):
    """R10-D6: the repository is cwd's, and there is no way to say otherwise."""

    def test_no_repo_path_argument_exists(self) -> None:
        for tool in (SD_PR_STATE, SD_STATUS):
            with self.subTest(tool=tool.name):
                text = self.run_tool(tool, "--help").stdout
                for spelling in (
                    "--repo",
                    "--repo-path",
                    "--path",
                    "--root",
                    "--dir",
                    "--directory",
                    "--checkout",
                    "--worktree",
                    "--cwd",
                    "--fleet",
                    "--all-repos",
                ):
                    self.assertNotIn(spelling, text)

    def test_positional_repository_is_refused(self) -> None:
        for tool in (SD_PR_STATE, SD_STATUS):
            with self.subTest(tool=tool.name):
                completed = self.run_tool(tool, str(self.base))
                self.assertEqual(completed.returncode, 2, completed.stdout)

    def test_reports_the_enclosing_repository_from_a_subdirectory(self) -> None:
        self.with_github(pulls=[])
        nested = self.repo / "src" / "deep"
        nested.mkdir(parents=True)
        completed = self.run_tool(SD_PR_STATE, "--json", cwd=nested)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["root"], str(self.repo))
        self.assertEqual(result["repo"], "acme/widget")

    def test_outside_a_git_repository_is_a_usage_error(self) -> None:
        completed = self.run_tool(SD_PR_STATE, cwd=self.base / "home")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("not inside a git repository", completed.stderr)


class DegradationTests(ToolFixture):
    """Missing gh, unauthenticated gh, no GitHub remote: reported, not raised."""

    def test_no_github_remote_exits_zero(self) -> None:
        self.install_gh()
        completed = self.run_tool(SD_PR_STATE)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("no GitHub remote", completed.stdout)

    def test_missing_gh_exits_zero_and_says_so(self) -> None:
        self.set_origin("https://github.com/acme/widget.git")
        completed = self.run_tool(SD_PR_STATE)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("gh is not installed", completed.stdout)

    def test_unauthenticated_gh_exits_zero_and_says_so(self) -> None:
        self.with_github(auth=False)
        completed = self.run_tool(SD_PR_STATE)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("gh auth login", completed.stdout)

    def test_a_non_github_remote_is_not_github(self) -> None:
        self.set_origin("git@gitlab.com:acme/widget.git")
        self.install_gh()
        result = self.run_json(SD_PR_STATE)
        self.assertFalse(result["available"])
        self.assertIsNone(result["repo"])

    def test_limit_must_be_positive(self) -> None:
        completed = self.run_tool(SD_PR_STATE, "--limit", "0")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("positive", completed.stderr)


class SlugTests(ToolFixture):
    """Every remote spelling the tool is expected to recognise, and one it is not."""

    def test_remote_spellings(self) -> None:
        cases = {
            "https://github.com/acme/widget.git": "acme/widget",
            "https://github.com/acme/widget": "acme/widget",
            "git@github.com:acme/widget.git": "acme/widget",
            "ssh://git@github.com/acme/widget.git": "acme/widget",
            "https://github.com/acme/widget/": "acme/widget",
            "https://gitlab.com/acme/widget.git": None,
            "/srv/mirrors/widget.git": None,
        }
        self.install_gh()
        self.responses = {"auth": True, "pulls": []}
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.set_origin(url)
                result = self.run_json(SD_PR_STATE)
                self.assertEqual(result["repo"], expected)


class PullRequestTests(ToolFixture):
    """The reported fields, and the buckets the check rollup collapses into."""

    def pull(self, **overrides: Any) -> dict[str, Any]:
        record = {
            "number": 7,
            "title": "Teach the widget to fold",
            "url": "https://github.com/acme/widget/pull/7",
            "headRefName": "task/fold",
            "baseRefName": "main",
            "isDraft": False,
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
            "reviewDecision": "APPROVED",
            "headRepositoryOwner": {"login": "acme"},
            "statusCheckRollup": [
                {"name": "build", "conclusion": "SUCCESS"},
                {"name": "lint", "conclusion": "FAILURE"},
                {"name": "slow", "status": "IN_PROGRESS", "conclusion": None},
                {"context": "legacy", "state": "PENDING"},
                {"name": "docs", "conclusion": "SKIPPED"},
                {"name": "odd", "conclusion": "WHAT"},
            ],
        }
        record.update(overrides)
        return record

    def test_every_reported_field(self) -> None:
        self.with_github(pulls=[self.pull()], behind_by=3)
        result = self.run_json(SD_PR_STATE)
        record = result["pull_requests"][0]
        self.assertEqual(record["number"], 7)
        self.assertEqual(record["head"], "task/fold")
        self.assertEqual(record["base"], "main")
        self.assertFalse(record["draft"])
        self.assertEqual(record["mergeable"], "MERGEABLE")
        self.assertEqual(record["merge_state"], "CLEAN")
        self.assertEqual(record["review_decision"], "APPROVED")
        self.assertEqual(record["behind_by"], 3)
        self.assertEqual(
            record["checks"],
            {"success": 1, "failure": 1, "pending": 2, "skipped": 1, "other": 1},
        )
        self.assertEqual(record["failing"], ["lint"])

    def test_behind_base_is_reported_in_the_human_output(self) -> None:
        self.with_github(pulls=[self.pull()], behind_by=4)
        completed = self.run_tool(SD_PR_STATE)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("behind base by 4", completed.stdout)

    def test_draft_and_conflict_are_flagged(self) -> None:
        self.with_github(
            pulls=[self.pull(isDraft=True, mergeable="CONFLICTING")], behind_by=0
        )
        completed = self.run_tool(SD_PR_STATE)
        self.assertIn("draft", completed.stdout)
        self.assertIn("conflicting", completed.stdout)

    def test_a_fork_head_is_compared_as_owner_colon_branch(self) -> None:
        log = self.base / "gh.log"
        self.with_github(
            pulls=[self.pull(headRepositoryOwner={"login": "contributor"})]
        )
        environ = self.env()
        environ["FAKE_GH_LOG"] = str(log)
        subprocess.run(
            [sys.executable, str(SD_PR_STATE), "--json"],
            cwd=str(self.repo),
            env=environ,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("main...contributor:task/fold", log.read_text(encoding="utf-8"))

    def test_no_open_pull_requests(self) -> None:
        self.with_github(pulls=[])
        completed = self.run_tool(SD_PR_STATE)
        self.assertEqual(completed.returncode, 0)
        self.assertIn("no open pull requests", completed.stdout)

    def test_a_red_pull_request_still_exits_zero(self) -> None:
        self.with_github(pulls=[self.pull()])
        self.assertEqual(self.run_tool(SD_PR_STATE).returncode, 0)


class ReadOnlyTests(ToolFixture):
    """The tool writes nothing, anywhere. Not the repo, not the state dir."""

    def test_nothing_under_the_temp_root_changes(self) -> None:
        self.with_github(pulls=[])
        before = tree_digest(self.base)
        completed = self.run_tool(SD_PR_STATE)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(tree_digest(self.base), before)

    def test_the_state_directory_is_never_created(self) -> None:
        self.with_github(pulls=[])
        self.run_tool(SD_PR_STATE)
        self.assertFalse(self.state.exists())

    def test_the_working_tree_stays_clean(self) -> None:
        self.with_github(pulls=[])
        self.run_tool(SD_PR_STATE)
        self.assertEqual(self.git("status", "--porcelain").strip(), "")


if __name__ == "__main__":
    unittest.main()
