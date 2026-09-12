"""sd:405 -- the guest-mode artifact refusal, performed rather than described.

`WORKFLOW.md` stated the refusal as a mechanical property: "every writing skill
refuses the upstream tree". Nothing refused anything. The rule existed once, as
a bullet in `skills/sd-plan/SKILL.md` addressed to an agent, and no code path
consulted `sd_lib.mode()` before a planning artifact was written -- which is how
two checkouts that resolve to `guest` came to carry 162 committed `prd.md` files
between them with nothing objecting on any of those occasions.

These tests are that refusal. The unit half asserts the sentence `sd_lib` hands
back through the injected `ask` seam, so no case here reaches the network. The
end-to-end half runs `bin/sd-review --scope planning` -- the one command
`sd-plan`'s sequence puts between writing the triad and promoting it -- as a
real process against a real repository holding a real `prd.md`, with a `gh` stub
on `PATH` answering for the remote, and asserts exit 2 and one sentence rather
than a traceback.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lib  # noqa: E402

VIEWER = ({"login": "sven"}, "")

#: A `gh api` that answers from a fixture: the transport is real, the network
#: is not. `__REPO__` is replaced per case so one stub covers fork and not.
GH_STUB = """#!/bin/sh
case "$2" in
  user) printf '%s' '{"login": "sven"}' ;;
  */collaborators) printf '%s' '[{"login": "sven", "permissions": {"push": true}}]' ;;
  *) printf '%s' '__REPO__' ;;
esac
"""

FORK_JSON = (
    '{"full_name": "sven/thing", "fork": true, '
    '"parent": {"full_name": "acme/thing"}, '
    '"permissions": {"admin": true, "push": true}}'
)
OWN_JSON = (
    '{"full_name": "sven/thing", "fork": false, '
    '"permissions": {"admin": true, "push": true}}'
)


def answers(*, full: bool) -> dict:
    """The three answers `remote_permits_full` asks for, yes or a plain no."""

    repo = {
        "full_name": "sven/thing",
        "fork": not full,
        "permissions": {"admin": True, "push": True, "pull": True},
    }
    if not full:
        repo["parent"] = {"full_name": "acme/thing"}
    return {
        sd_lib.VIEWER_QUERY: VIEWER,
        sd_lib.REPOSITORY_QUERY: (repo, ""),
        sd_lib.COLLABORATOR_QUERY: ([{"login": "sven", "permissions": {"push": True}}], ""),
    }


class Asker:
    """Answers from a fixture and records what it was asked."""

    def __init__(self, table: dict) -> None:
        self.table = table
        self.asked: list[str] = []

    def __call__(self, endpoint: str, root: pathlib.Path):
        self.asked.append(endpoint)
        if endpoint not in self.table:
            raise AssertionError(f"the code asked {endpoint}, which this case does not answer")
        return self.table[endpoint]


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()

    def git(self, cwd: pathlib.Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)

    def make_repo(self, origin: str = "https://github.com/sven/thing.git") -> pathlib.Path:
        root = self.tmp / "repo"
        root.mkdir(parents=True)
        self.git(root, "init", "-b", "main")
        self.git(root, "config", "user.email", "test@example.com")
        self.git(root, "config", "user.name", "Test User")
        (root / "README.md").write_text("seed\n", encoding="utf-8")
        self.git(root, "add", "README.md")
        self.git(root, "commit", "-m", "seed")
        self.git(root, "remote", "add", "origin", origin)
        return root

    def write_mode(self, root: pathlib.Path, value: str) -> None:
        (root / sd_lib.LOCAL_FILE_NAME).write_text(
            f"{sd_lib.LOCAL_BLOCK_START}\nmode: {value}\n{sd_lib.LOCAL_BLOCK_END}\n",
            encoding="utf-8",
        )

    def write_item(self, root: pathlib.Path, slug: str = "2026-01-01-a-thing") -> pathlib.Path:
        """A real planning artifact on disk, the shape `sd-plan` step 2 writes."""

        item = root / sd_lib.WORK_DIR / slug
        item.mkdir(parents=True)
        (item / "prd.md").write_text(
            "---\n"
            "title: A thing\n"
            "status: planning\n"
            "created: 2026-01-01\n"
            "branch: topic\n"
            "---\n"
            "\n## Requirements\n\n- [ ] one\n",
            encoding="utf-8",
        )
        return item


class TheRule(Fixture):
    """`sd_lib.guest_artifact_refusal`: the one place the rule lives in code."""

    def test_a_planning_artifact_in_guest_mode_is_refused_by_name(self) -> None:
        root = self.make_repo()
        self.write_mode(root, "guest")
        sentence = sd_lib.guest_artifact_refusal(
            root, ["docs/work/2026-01-01-a-thing/prd.md"], ask=Asker(answers(full=True))
        )
        self.assertIn("guest mode", sentence)
        self.assertIn("docs/work/2026-01-01-a-thing/prd.md", sentence)
        self.assertIn("fork's integration branch", sentence)

    def test_all_three_refused_trees_are_named(self) -> None:
        self.assertEqual(
            sd_lib.GUEST_REFUSED_DIRS, ("docs/work", "docs/spec", "docs/decisions"),
            "the three trees WORKFLOW.md and bin/sd-ship already spell",
        )
        root = self.make_repo()
        self.write_mode(root, "guest")
        for path in ("docs/work/i/prd.md", "docs/spec/a.md", "docs/decisions/d.md"):
            with self.subTest(path=path):
                self.assertTrue(
                    sd_lib.guest_artifact_refusal(root, [path], ask=Asker(answers(full=True)))
                )

    def test_an_unrelated_path_is_not_refused_and_asks_nothing(self) -> None:
        """The pure half runs first, so nothing to refuse never costs a call."""

        root = self.make_repo()
        self.write_mode(root, "guest")
        ask = Asker({})
        self.assertEqual(sd_lib.guest_artifact_refusal(root, ["bin/sd_lib.py"], ask=ask), "")
        self.assertEqual(ask.asked, [])

    def test_a_full_mode_repository_writes_where_it_always_did(self) -> None:
        root = self.make_repo()
        self.assertEqual(
            sd_lib.guest_artifact_refusal(
                root, ["docs/work/i/prd.md"], ask=Asker(answers(full=True))
            ),
            "",
        )

    def test_a_written_full_the_remote_lowers_is_still_refused(self) -> None:
        """Detection is a ceiling: `mode: full` on a fork resolves guest here."""

        root = self.make_repo()
        self.write_mode(root, "full")
        self.assertIn(
            "guest mode",
            sd_lib.guest_artifact_refusal(
                root, ["docs/work/i/prd.md"], ask=Asker(answers(full=False))
            ),
        )

    def test_prefixes_that_only_look_like_the_refused_trees_pass(self) -> None:
        root = self.make_repo()
        self.write_mode(root, "guest")
        for path in ("docs/workbook/a.md", "docs/specification.md", "adocs/work/i/prd.md"):
            with self.subTest(path=path):
                self.assertEqual(
                    sd_lib.guest_artifact_refusal(root, [path], ask=Asker({})), ""
                )


class TheReviewGate(Fixture):
    """End to end: the write path `sd-plan` mandates, refused as a process.

    `sd-plan` step 4 runs `sd-review --scope planning` over the triad in the
    working tree and step 5 gates `planning -> ready` on that lane, so this is
    where a guest-mode checkout finds out before the artifact is promoted or
    committed. Red against `origin/main`, where `sd-review` consulted no mode.
    """

    def path_holding(self, *tools: str) -> pathlib.Path:
        bindir = self.tmp / "path"
        bindir.mkdir(exist_ok=True)
        for tool in tools:
            found = shutil.which(tool)
            self.assertIsNotNone(found, f"{tool} must be installed to run this test")
            link = bindir / tool
            if not link.exists():
                link.symlink_to(str(found))
        return bindir

    def run_review(self, root: pathlib.Path, repo_json: str) -> subprocess.CompletedProcess:
        bindir = self.path_holding("git", "python3")
        stub = bindir / "gh"
        stub.write_text(GH_STUB.replace("__REPO__", repo_json), encoding="utf-8")
        stub.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = str(bindir)
        env["HOME"] = str(self.tmp / "home")
        (self.tmp / "home").mkdir(exist_ok=True)
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "sd-review"), "--scope", "planning", "--explain"],
            cwd=str(root), env=env, capture_output=True, text=True, timeout=300,
        )

    def test_guest_mode_refuses_the_active_items_planning_documents(self) -> None:
        root = self.make_repo()
        self.write_item(root)
        done = self.run_review(root, FORK_JSON)
        self.assertEqual(done.returncode, 2, f"stdout={done.stdout}\nstderr={done.stderr}")
        self.assertIn("guest mode", done.stderr)
        self.assertIn("docs/work/2026-01-01-a-thing/prd.md", done.stderr)
        self.assertIn("fork's integration branch", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_the_same_repository_unforked_reaches_the_reviewer(self) -> None:
        """The control: the refusal is about the mode, not about the fixture.

        The success is asserted positively, because absence is not evidence.
        Written as two `assertNotIn`s alone this passed on any failure that did
        not happen to use the guest wording -- a usage error, a missing `gh`, an
        `--explain` that fell over for its own reasons -- so the one thing its
        name claims, that the reviewer was reached, was the one thing nothing in
        it established. The exit code says the run succeeded and the explanation
        naming the scope says it was this review that produced it.
        """

        root = self.make_repo()
        self.write_item(root)
        done = self.run_review(root, OWN_JSON)
        self.assertEqual(done.returncode, 0,
                         f"stdout={done.stdout}\nstderr={done.stderr}")
        self.assertIn("planning", done.stdout + done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assertNotIn("guest mode", done.stderr)
        self.assertNotIn("fork's integration branch", done.stderr)


if __name__ == "__main__":
    unittest.main()
