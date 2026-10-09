"""How many subprocesses one `sd-status` run starts, counted rather than timed (sd:2677).

One run on a working checkout started 2,079 of them, and 1,750 repeated a
question already answered in the same run. Wall clock moves with the machine's
load; a count does not, so the budgets here are counts on a fixture repository.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import unittest
from typing import Any, Iterator
from unittest import mock

from tests.test_sd_pr_state import BIN, ToolFixture

if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import sd_lib  # noqa: E402


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
