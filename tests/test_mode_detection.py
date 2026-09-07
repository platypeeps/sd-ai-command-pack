"""Criterion 11: with no `mode:` line the remote is asked, and a no lowers.

`README.md:64` has promised detection since before anything detected. What
`sd_lib.mode` actually did was return `full` -- the most permissive mode --
for every repository with no line, which is the answer detection exists to
avoid in exactly the two situations it exists for: a fork, and a repository
the operator cannot administer. These tests are the criterion, case by case.

Nothing here reaches the network, and nothing here is skipped when a tool is
absent. The six cases and the unanswerable ones go through the injected
`ask` seam. The end-to-end gate goes through a `gh` stub on `PATH`, so the
real transport, the real JSON decode and the real refusal all run against a
process that answers from a fixture instead of from GitHub.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lib  # noqa: E402
import sd_setup_github  # noqa: E402

VIEWER = ({"login": "sven"}, "")


def repo_payload(
    full_name: str = "sven/thing",
    *,
    admin: bool = True,
    fork: bool = False,
    parent: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "full_name": full_name,
        "fork": fork,
        "permissions": {"admin": admin, "push": True, "pull": True},
    }
    if parent is not None:
        body["parent"] = {"full_name": parent}
    return body


def collaborators(*logins: str) -> list[dict[str, Any]]:
    return [{"login": name, "permissions": {"push": True}} for name in logins]


def table(
    repo: Any = None,
    people: Any = None,
    *,
    viewer: tuple[Any, str] = VIEWER,
) -> dict[str, tuple[Any, str]]:
    """The three answers, all affirmative unless a case overrides one."""

    return {
        sd_lib.VIEWER_QUERY: viewer,
        sd_lib.REPOSITORY_QUERY: (repo if repo is not None else repo_payload(), ""),
        sd_lib.COLLABORATOR_QUERY: (
            people if people is not None else collaborators("sven"),
            "",
        ),
    }


class Asker:
    """An `ask` that answers from a fixture and records what it was asked.

    A question with no fixture is an error rather than a default. A default
    would let a case pass because the code asked nothing, which is the exact
    failure mode -- resolving `full` without putting the question -- that this
    file exists to catch.
    """

    def __init__(self, answers: dict[str, tuple[Any, str]]) -> None:
        self.answers = answers
        self.asked: list[str] = []

    def __call__(self, endpoint: str, root: pathlib.Path) -> tuple[Any, str]:
        self.asked.append(endpoint)
        if endpoint not in self.answers:
            raise AssertionError(f"the code asked {endpoint}, which this case does not answer")
        return self.answers[endpoint]


class Fixture(unittest.TestCase):
    """Real git repositories in a throwaway tree; no git call is mocked."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()

    def git(self, cwd: pathlib.Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)

    def make_repo(self, name: str = "repo", origin: str | None = None) -> pathlib.Path:
        root = self.tmp / name
        root.mkdir(parents=True)
        self.git(root, "init", "-b", "main")
        self.git(root, "config", "user.email", "test@example.com")
        self.git(root, "config", "user.name", "Test User")
        (root / "README.md").write_text("seed\n", encoding="utf-8")
        self.git(root, "add", "README.md")
        self.git(root, "commit", "-m", "seed")
        if origin is not None:
            # Added, never fetched: the URL is what the questions are about.
            self.git(root, "remote", "add", "origin", origin)
        return root

    def write_mode(self, root: pathlib.Path, value: str) -> None:
        (root / sd_lib.LOCAL_FILE_NAME).write_text(
            f"{sd_lib.LOCAL_BLOCK_START}\nmode: {value}\n{sd_lib.LOCAL_BLOCK_END}\n",
            encoding="utf-8",
        )

    def path_holding(self, *tools: str) -> str:
        """A `PATH` with exactly these tools on it, by symlink to the real ones."""

        bindir = self.tmp / ("path-" + ("-".join(tools) or "nothing"))
        bindir.mkdir(exist_ok=True)
        for tool in tools:
            found = shutil.which(tool)
            self.assertIsNotNone(found, f"{tool} must be installed to run this test")
            (bindir / tool).symlink_to(str(found))
        return str(bindir)


class SixCases(Fixture):
    """The six cases `prd.md:1376-1384` enumerates, each asserted by name."""

    def test_case_1_a_personal_remote_only_you_can_push_to_is_full(self) -> None:
        root = self.make_repo(origin="https://github.com/sven/thing.git")
        answer = sd_lib.remote_permits_full(root, ask=Asker(table(repo_payload("sven/thing"))))
        self.assertEqual(answer, sd_lib.RemoteAnswer(True, True, ""))

    def test_case_2_an_organisation_remote_only_you_can_push_to_is_full(self) -> None:
        root = self.make_repo(origin="git@github.com:acme/thing.git")
        answer = sd_lib.remote_permits_full(root, ask=Asker(table(repo_payload("acme/thing"))))
        self.assertEqual(answer, sd_lib.RemoteAnswer(True, True, ""))

    def test_case_3_a_remote_you_cannot_administer_is_guest(self) -> None:
        root = self.make_repo(origin="https://github.com/acme/thing.git")
        ask = Asker(table(repo_payload("acme/thing", admin=False)))
        answer = sd_lib.remote_permits_full(root, ask=ask)
        self.assertFalse(answer.full)
        self.assertTrue(answer.answered, "a plain no is an answer, not a failure to ask")
        self.assertIn("do not administer acme/thing", answer.reason)
        self.assertNotIn(sd_lib.COLLABORATOR_QUERY, ask.asked)

    def test_case_4_a_personal_fork_of_a_shared_upstream_is_guest(self) -> None:
        root = self.make_repo(origin="https://github.com/sven/thing.git")
        ask = Asker(table(repo_payload("sven/thing", fork=True, parent="acme/thing")))
        answer = sd_lib.remote_permits_full(root, ask=ask)
        self.assertFalse(answer.full)
        self.assertTrue(answer.answered)
        self.assertEqual(answer.reason, "sven/thing is a fork of acme/thing")

    def test_case_5_an_owned_remote_with_a_second_collaborator_is_guest(self) -> None:
        root = self.make_repo(origin="https://github.com/sven/thing.git")
        ask = Asker(table(people=collaborators("sven", "mallory")))
        answer = sd_lib.remote_permits_full(root, ask=ask)
        self.assertFalse(answer.full)
        self.assertTrue(answer.answered)
        self.assertIn("mallory", answer.reason)
        self.assertNotIn("sven, mallory", answer.reason, "you are not your own collaborator")

    def test_case_6_no_remote_and_no_git_are_full_each_on_its_own_branch(self) -> None:
        ask = Asker({})

        no_remote = self.make_repo("scratch-repo")
        self.assertEqual(
            sd_lib.remote_permits_full(no_remote, ask=ask), sd_lib.RemoteAnswer(True, True, "")
        )

        no_git = self.tmp / "not-a-repo"
        no_git.mkdir()
        self.assertFalse((no_git / ".git").exists())
        self.assertEqual(
            sd_lib.remote_permits_full(no_git, ask=ask), sd_lib.RemoteAnswer(True, True, "")
        )

        # The point of the branch: neither is reached by catching what the
        # remote lookup raised, because no remote lookup was attempted.
        self.assertEqual(ask.asked, [])


class UnanswerableQueries(Fixture):
    """No answer is `guest`, never `full`. One test per way of not answering."""

    def remote_repo(self) -> pathlib.Path:
        return self.make_repo(origin="https://github.com/sven/thing.git")

    def test_a_remote_that_refuses_is_guest_and_unanswered(self) -> None:
        answers = table()
        answers[sd_lib.REPOSITORY_QUERY] = (None, "HTTP 403: Resource not accessible")
        answer = sd_lib.remote_permits_full(self.remote_repo(), ask=Asker(answers))
        self.assertEqual((answer.full, answer.answered), (False, False))
        self.assertIn("403", answer.reason)

    def test_an_absent_network_is_guest_and_unanswered(self) -> None:
        answers = table()
        answers[sd_lib.VIEWER_QUERY] = (None, "dial tcp: lookup api.github.com: no such host")
        answer = sd_lib.remote_permits_full(self.remote_repo(), ask=Asker(answers))
        self.assertEqual((answer.full, answer.answered), (False, False))
        self.assertIn("no such host", answer.reason)

    def test_two_yeses_then_no_collaborator_list_is_still_guest(self) -> None:
        """The dangerous one: most of the way to `full` is not `full`."""

        answers = table()
        answers[sd_lib.COLLABORATOR_QUERY] = (None, "HTTP 502: Bad gateway")
        answer = sd_lib.remote_permits_full(self.remote_repo(), ask=Asker(answers))
        self.assertEqual((answer.full, answer.answered), (False, False))
        self.assertIn("who may push", answer.reason)

    def test_an_answer_in_the_wrong_shape_is_guest_and_unanswered(self) -> None:
        answers = table(repo={"full_name": "sven/thing", "fork": False})
        answer = sd_lib.remote_permits_full(self.remote_repo(), ask=Asker(answers))
        self.assertEqual((answer.full, answer.answered), (False, False))

    def test_a_missing_gh_is_guest_and_unanswered(self) -> None:
        """The real transport, with the tool absent rather than stubbed away."""

        root = self.remote_repo()
        with mock.patch.dict(os.environ, {"PATH": self.path_holding("git")}):
            self.assertEqual(sd_lib.git_output(["rev-parse", "--is-inside-work-tree"], root), "true")
            self.assertIsNone(shutil.which("gh"))
            answer = sd_lib.remote_permits_full(root)
        self.assertEqual((answer.full, answer.answered), (False, False))
        self.assertIn("gh could not be run", answer.reason)

    def test_a_git_that_cannot_run_is_guest_and_not_mistaken_for_no_git(self) -> None:
        root = self.remote_repo()
        with mock.patch.dict(os.environ, {"PATH": self.path_holding()}):
            answer = sd_lib.remote_permits_full(root)
        self.assertEqual((answer.full, answer.answered), (False, False))
        self.assertIn("git could not be asked", answer.reason)

    def test_no_unanswerable_condition_anywhere_resolves_to_full(self) -> None:
        """The sweep, so a new failure mode cannot land as `full` unnoticed.

        `[]` is deliberately not in the payloads: an empty collaborator list is
        a real answer -- nobody else may push -- and asserting `guest` for it
        would be asserting the wrong thing.
        """

        root = self.remote_repo()
        for endpoint in (sd_lib.VIEWER_QUERY, sd_lib.REPOSITORY_QUERY, sd_lib.COLLABORATOR_QUERY):
            for payload in (None, "", {}, 0, "not json", {"unexpected": True}):
                with self.subTest(endpoint=endpoint, payload=payload):
                    answers = table()
                    answers[endpoint] = (payload, "the remote said nothing usable")
                    answer = sd_lib.remote_permits_full(root, ask=Asker(answers))
                    self.assertFalse(answer.full)
                    self.assertFalse(answer.answered)
                    self.assertTrue(answer.reason)


class Composition(Fixture):
    """A written line is a ceiling. Detection lowers it and never raises it."""

    def test_written_full_with_a_detected_no_resolves_to_guest(self) -> None:
        root = self.make_repo(origin="https://github.com/sven/thing.git")
        self.write_mode(root, "full")
        ask = Asker(table(people=collaborators("sven", "mallory")))
        self.assertEqual(sd_lib.mode(root, ask=ask), "guest")

    def test_written_guest_with_a_detected_yes_stays_guest(self) -> None:
        root = self.make_repo(origin="https://github.com/sven/thing.git")
        self.write_mode(root, "guest")
        ask = Asker(table())
        self.assertEqual(sd_lib.mode(root, ask=ask), "guest")
        self.assertEqual(ask.asked, [], "a written guest has nothing left to lower")

    def test_written_minimal_is_left_alone_by_detection(self) -> None:
        """`minimal` writes no artifacts at all, so `guest` would raise exposure.

        Detection's six cases never produce `minimal`; it is set by hand. And
        `guest` is not below it -- `guest` puts the triad on a fork's
        integration branch, where `minimal` puts nothing anywhere -- so
        rewriting `minimal` to `guest` would be detection raising exposure,
        the one move `WORKFLOW.md:187-189` forbids.
        """

        root = self.make_repo(origin="https://github.com/sven/thing.git")
        self.write_mode(root, "minimal")
        ask = Asker(table(people=collaborators("sven", "mallory")))
        self.assertEqual(sd_lib.mode(root, ask=ask), "minimal")
        self.assertEqual(ask.asked, [])

    def test_no_line_with_three_yeses_resolves_to_full(self) -> None:
        root = self.make_repo(origin="https://github.com/sven/thing.git")
        self.assertEqual(sd_lib.mode(root, ask=Asker(table())), "full")

    def test_the_answer_is_not_cached_between_two_calls(self) -> None:
        """Asked again before every write and every push, per `WORKFLOW.md:185`."""

        root = self.make_repo(origin="https://github.com/sven/thing.git")
        first = Asker(table())
        self.assertEqual(sd_lib.mode(root, ask=first), "full")
        gained = Asker(table(people=collaborators("sven", "mallory")))
        self.assertEqual(sd_lib.mode(root, ask=gained), "guest")
        self.assertIn(sd_lib.COLLABORATOR_QUERY, gained.asked)


GH_STUB = """#!/bin/sh
# `gh api <endpoint>`: $1 is `api`, $2 is the endpoint. Answers from a fixture,
# so the transport is real and the network is not.
case "$2" in
  user) printf '%s' '{"login": "sven"}' ;;
  */collaborators) printf '%s' '[{"login": "sven", "permissions": {"push": true}}]' ;;
  *) printf '%s' '__REPO__' ;;
esac
"""


class TheInstallerGate(Fixture):
    """End to end: `bin/sd_setup_github.py`'s R10-D5 refusal, on a real fork.

    The gate reads `sd_lib.mode(root)` and refuses anything but `full`. Before
    detection existed, a fork with no `mode:` line read `full` and this
    installed the routing lane -- the one thing R10-D5 restricts to full-mode
    repositories. Asserted through the real `gh_api`, against a `gh` on `PATH`.
    """

    def gate(self, root: pathlib.Path, repo_json: str) -> dict[str, Any]:
        bindir = pathlib.Path(self.path_holding("git"))
        stub = bindir / "gh"
        stub.write_text(GH_STUB.replace("__REPO__", repo_json), encoding="utf-8")
        stub.chmod(0o755)
        args = argparse.Namespace(
            dry_run=True, json=False, force=False, remove_legacy=False, pin="deadbeef"
        )
        policy = ({"authors": ["sven"]}, "built-in default")
        with mock.patch.dict(os.environ, {"PATH": str(bindir)}):
            return sd_setup_github.setup_github(root, args, load_policy=lambda _root: policy)

    def test_a_fork_with_no_mode_line_is_refused(self) -> None:
        root = self.make_repo(origin="https://github.com/sven/thing.git")
        self.assertEqual(sd_lib.local_block(root), {}, "the fixture writes no mode: line")
        with self.assertRaises(sd_setup_github.Refusal) as caught:
            self.gate(
                root,
                '{"full_name": "sven/thing", "fork": true, '
                '"parent": {"full_name": "acme/thing"}, '
                '"permissions": {"admin": true, "push": true}}',
            )
        self.assertIn("guest mode", str(caught.exception))
        self.assertFalse((root / sd_setup_github.WORKFLOW_RELATIVE_PATH).exists())

    def test_the_same_repository_unforked_installs(self) -> None:
        """The control: the refusal is about the fork, not about the stub."""

        root = self.make_repo(origin="https://github.com/sven/thing.git")
        result = self.gate(
            root,
            '{"full_name": "sven/thing", "fork": false, '
            '"permissions": {"admin": true, "push": true}}',
        )
        self.assertEqual(result["mode"], "full")
        self.assertEqual(result["status"], "dry_run")


if __name__ == "__main__":
    unittest.main()
