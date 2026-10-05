"""How many subprocesses one `sd-status` run starts, counted rather than timed (sd:2677).

One run on a working checkout started 2,079 of them, and 1,750 repeated a
question already answered in the same run. Wall clock moves with the machine's
load; a count does not, so the budgets here are counts on a fixture repository.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import shutil
import subprocess
import sys
import unittest
from typing import Any, Iterator
from unittest import mock

from tests.test_sd_pr_state import BIN, SD_STATUS, ToolFixture

if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import sd_lib  # noqa: E402

ack = sd_lib.sibling("sd_review_ack_calls", "sd-review-ack")

#: A `gh` that answers the merged list with the pull requests in `$FAKE_GH`.
FAKE_GH = '''#!{python}
import json, os, sys
data = json.loads(os.environ["FAKE_GH"])
argv = sys.argv[1:]
if argv[:2] == ["auth", "status"]:
    sys.exit(0)
if argv[:1] == ["pr"]:
    print(json.dumps(data["merged"] if "merged" in argv else []))
elif argv[:1] == ["api"] and "comments" in argv[1]:
    print("[]")
elif argv[:1] == ["api"] and argv[1].endswith("/protection"):
    print(json.dumps(data["protection"]))
elif argv[:1] == ["api"] and "/rules/branches/" in argv[1]:
    print("[]")
elif argv[:1] == ["api"]:
    print(json.dumps(data["repo"]))
else:
    sys.exit(1)
'''

#: Every `git` the run starts, one argv per line, then the real `git`.
COUNTING_GIT = '''#!/bin/sh
printf '%s\\n' "$*" >> "{log}"
exec "{git}" "$@"
'''

#: origin/main measured 232 git calls for this fixture; the memo and the
#: per-ref ancestry read bring it to 38. Room for a few new questions, not
#: for asking the old ones twice.
GIT_BUDGET = 60


@contextlib.contextmanager
def counted() -> Iterator[list[list[str]]]:
    """Every `git` argv `sd_lib` starts inside the block."""
    calls: list[list[str]] = []
    real = subprocess.run

    def run(argv: list[str], *args: Any, **kwargs: Any) -> Any:
        calls.append(list(argv[1:]))
        return real(argv, *args, **kwargs)

    with mock.patch.object(sd_lib.subprocess, "run", run):
        yield calls


class Repository(ToolFixture):
    def commit(self, name: str) -> str:
        (self.repo / f"{name}.txt").write_text(name, encoding="utf-8")
        self.git("add", f"{name}.txt")
        self.git("commit", "-q", "-m", name)
        return self.git("rev-parse", "HEAD").strip()


class StatusRunBudgetTests(Repository):
    """The whole executable, the way an operator runs it, counted at `git`."""

    def test_a_run_over_merged_reviews_stays_inside_its_git_budget(self) -> None:
        stated = self.commit("stated")
        landed, merge = self.commit("fix"), self.commit("merge")
        self.git("checkout", "-q", "-b", "side")
        unlanded = self.commit("side")
        self.git("checkout", "-q", "main")
        self.git("update-ref", "refs/remotes/origin/main", "main")
        today = datetime.datetime.now(datetime.timezone.utc)
        merged = []
        for number in range(1, 9):
            body = "| File | Summary |\n|---|---|\n" + "".join(
                f"| `bin/f{number}{n}.py` | Moderate finding (1 vote): wrong {n}. |\n" for n in range(3))
            review = {"author": {"login": "bot"}, "commit_id": stated, "body": body}
            for row, fix in zip(ack.findings(number, [review], []), [landed, unlanded, stated], strict=True):
                ack.acknowledge(self.repo, row, "fixed", fix)
            when = (today - datetime.timedelta(days=number)).strftime("%Y-%m-%dT%H:%M:%SZ")
            merged.append({"number": number, "title": f"PR {number}", "url": f"https://example.test/{number}",
                           "mergedAt": when, "createdAt": when, "headRefOid": unlanded,
                           "mergeCommit": {"oid": merge}, "reviews": [review]})
        self.with_github(merged=merged)
        log = self.base / "git.log"
        (self.fake_bin / "git").unlink()
        (self.fake_bin / "git").write_text(
            COUNTING_GIT.format(log=log, git=shutil.which("git")), encoding="utf-8")
        (self.fake_bin / "git").chmod(0o755)
        self.install_gh()

        completed = self.run_tool(SD_STATUS)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("late: 8 review finding(s) on 8 pull request(s)", completed.stdout)
        calls = log.read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(calls), GIT_BUDGET, f"{len(calls)} git calls > budget {GIT_BUDGET}")

    def install_gh(self) -> None:
        script = self.fake_bin / "gh"
        script.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
        script.chmod(0o755)

    def env(self) -> dict[str, str]:
        return dict(super().env(), FAKE_GH=json.dumps(self.responses))


class ReadMemoTests(Repository):
    """`git_read_memo`: a repeated read starts nothing, and a write forgets."""

    def test_a_repeated_read_runs_once_and_a_write_empties_the_memo(self) -> None:
        first = self.git("rev-parse", "HEAD").strip()
        second = self.commit("second")
        self.git("update-ref", "refs/heads/main", first)
        with counted() as calls, sd_lib.git_read_memo():
            self.assertEqual(first, sd_lib.git_output(["rev-parse", "main"], self.repo))
            self.assertEqual(first, sd_lib.git_output(["rev-parse", "main"], self.repo))
            self.assertEqual(1, len(calls))
            sd_lib.git_output(["update-ref", "refs/heads/main", second], self.repo)
            self.assertEqual(second, sd_lib.git_output(["rev-parse", "main"], self.repo))
        self.assertEqual(3, len(calls))
        with counted() as calls:
            sd_lib.git_output(["rev-parse", "main"], self.repo)
            sd_lib.git_output(["rev-parse", "main"], self.repo)
        self.assertEqual(2, len(calls), "outside the block nothing is remembered")

    def test_only_reading_forms_are_remembered(self) -> None:
        for args in (["rev-parse", "HEAD"], ["-C", "x", "log"], ["--no-optional-locks", "status"],
                     ["config", "--get", "a.b"], ["remote"], ["symbolic-ref", "--short", "HEAD"]):
            self.assertTrue(sd_lib._reads_only(args), args)
        for args in (["fetch", "origin"], ["update-ref", "a", "b"], ["config", "a.b", "c"],
                     ["remote", "add", "o", "u"], ["symbolic-ref", "HEAD", "refs/heads/x"], []):
            self.assertFalse(sd_lib._reads_only(args), args)


class AncestryTests(Repository):
    """`_is_ancestor` answers from one `rev-list` per ref, and answers the same."""

    def test_every_answer_matches_merge_base_and_one_rev_list_serves_a_ref(self) -> None:
        root = self.git("rev-parse", "HEAD").strip()
        middle = self.commit("middle")
        tip = self.commit("tip")
        self.git("checkout", "-q", "-b", "side", middle)
        side = self.commit("side")
        self.git("checkout", "-q", "main")
        commits = [root, middle, tip, side, "f" * 40, middle[:12], ""]
        refs = ["main", "side", tip, "refs/heads/gone", "0" * 40]
        truth = {(c, r): bool(c) and subprocess.run(
            ["git", "merge-base", "--is-ancestor", c, r], cwd=self.repo, capture_output=True).returncode == 0
            for c in commits for r in refs}
        self.assertTrue(truth[(middle, "main")])
        self.assertFalse(truth[("f" * 40, "main")])
        for memo in (contextlib.nullcontext(), sd_lib.git_read_memo()):
            with memo:
                answers = {(c, r): ack._is_ancestor(self.repo, c, r) for c in commits for r in refs}
            self.assertEqual(truth, answers)
        with counted() as calls, sd_lib.git_read_memo():
            for commit in (root, middle, tip, side, "f" * 40):
                ack._is_ancestor(self.repo, commit, "main")
        self.assertEqual([["rev-list", "main"]], calls)


class DeliveredFetchTests(Repository):
    """`delivered` fetches each ref once per memo block, and answers as before."""

    def test_items_share_one_fetch_inside_the_block(self) -> None:
        remote = self.base / "remote.git"
        self.git("init", "-q", "--bare", str(remote))
        self.git("commit", "-q", "--allow-empty", "-m", "deliver\n\nDelivers: sd:1")
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-q", "origin", "main")
        self.git("remote", "set-head", "origin", "main")
        self.git("reset", "-q", "--hard", "HEAD~1")
        items = ["sd:1", "sd:2", "sd:3", "sd:4"]
        plain = [sd_lib.delivered(self.repo, item) for item in items]
        with counted() as calls, sd_lib.git_read_memo():
            memoized = [sd_lib.delivered(self.repo, item) for item in items]
        self.assertEqual(plain, memoized)
        self.assertEqual([sd_lib.YES, sd_lib.NO, sd_lib.NO, sd_lib.NO], [str(a) for a in memoized])
        self.assertEqual(1, sum(call[:1] == ["fetch"] for call in calls))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
