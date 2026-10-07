"""The Jev shadow stages: review triage (sd:2092) and the duplicate hint (sd:2093).

A shadow stage records Jev's answer and never reads it back, and it sends text
about a repository, so it may run for a public repository only. Every case
puts a `jev` and a `gh` stub on the only `PATH` the run is handed, so the suite
stays offline and neither real command is reached.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import unittest.mock

import sd_db
import sd_db.repos

from tests.test_sd_review import FakeRunner, ReviewFixture, namespace, sd_review

sd_jev = sd_review.sd_jev
ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Logs each call as one JSON line. `enabled` exits with the case's code;
#: `choice` exits with the case's code and prints the `--shadow` answer, as
#: the real `jev` does in shadow mode.
JEV_STUB = """#!/usr/bin/env python3
import json, sys
argv = sys.argv[1:]
stdin = "" if argv[:1] == ["enabled"] else sys.stdin.read()
with open({log!r}, "a") as log:
    log.write(json.dumps({{"argv": argv, "state": stdin}}) + "\\n")
if argv[:1] == ["enabled"]:
    raise SystemExit({gate})
if {code}:
    raise SystemExit({code})
print(argv[argv.index("--shadow") + 1])
"""

#: Answers `gh api repos/<owner>/<repo> --jq .private` with the case's word.
GH_STUB = """#!/usr/bin/env python3
import json, sys
with open({log!r}, "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
print({private!r})
"""

FINDING = {"path": "src.py", "line": 1, "severity": "high", "summary": "bad, really", "family": "correctness"}


class Stubs:
    """The two stubs in `bin_dir`, and what each was asked."""

    def __init__(self, bin_dir: pathlib.Path, *, gate: int = 0, code: int = 0, private: str = "false") -> None:
        self.jev_log, self.gh_log = bin_dir / "jev.log", bin_dir / "gh.log"
        for name, text in (("jev", JEV_STUB.format(log=str(self.jev_log), gate=gate, code=code)),
                           ("gh", GH_STUB.format(log=str(self.gh_log), private=private))):
            (bin_dir / name).write_text(text)
            (bin_dir / name).chmod(0o700)

    def jev(self) -> list[dict]:
        return [json.loads(line) for line in self.jev_log.read_text().splitlines()] if self.jev_log.exists() else []

    def choices(self) -> list[dict]:
        return [call for call in self.jev() if call["argv"][:1] == ["choice"]]

    def gh(self) -> list[list[str]]:
        return [json.loads(line) for line in self.gh_log.read_text().splitlines()] if self.gh_log.exists() else []


def flag(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


class TriageTests(ReviewFixture):
    def repo(self) -> pathlib.Path:
        root = self.make_repo()
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/example/demo.git"],
                       cwd=str(root), check=True)
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        return root

    def triage(self, findings, **env: str) -> str:
        noise = io.StringIO()
        sd_jev.jev_triage(findings, self.environment(**env), self.repo(), noise)
        return noise.getvalue()

    def review(self, root: pathlib.Path, findings) -> tuple[str, str]:
        """One review, its tier reading off, as its JSON bytes and its stderr."""
        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", ""),
                             "codex": sd_review.Completed(0, json.dumps({"findings": findings}), "")})
        self.codex_home = getattr(self, "codex_home", None) or self.chatgpt_home()
        noise = io.StringIO()
        with contextlib.redirect_stderr(noise):
            result = sd_review.review(root, namespace(), runner, self.environment(JEV_SD_REVIEW="0"),
                                      self.codex_home)
        return json.dumps(result, sort_keys=True), noise.getvalue()

    def test_a_review_with_findings_records_a_triage_and_changes_nothing(self):
        root = self.repo()
        without, _ = self.review(root, [FINDING])
        stubs = Stubs(self.tool_bin)
        with_jev, said = self.review(root, [FINDING])
        self.assertEqual(with_jev, without)
        self.assertEqual(said, "")
        [call] = stubs.choices()
        argv = call["argv"]
        self.assertEqual((flag(argv, "--stage"), flag(argv, "--shadow"), flag(argv, "--caller")),
                         (sd_jev.TRIAGE_STAGE, sd_jev.UNTRIAGED, "sd-review"))
        self.assertEqual(set(sd_jev.TRIAGE_CRITERIA),
                         {part.split("=", 1)[0] for part in flag(argv, "--criteria").split(",")})
        self.assertEqual(json.loads(call["state"]), {
            "severity": "high", "disposition": "blocking", "family": "correctness",
            "path": "src.py", "summary": "bad, really"})
        self.assertEqual(stubs.gh(), [["api", "repos/example/demo", "--jq", ".private"]])

    def test_a_clean_review_asks_nothing(self):
        stubs = Stubs(self.tool_bin)
        self.review(self.repo(), [])
        self.assertEqual((stubs.jev(), stubs.gh()), ([], []))

    def test_a_private_repository_sends_nothing(self):
        stubs = Stubs(self.tool_bin, private="true")
        self.assertEqual(self.triage([FINDING]), "")
        self.assertEqual(stubs.choices(), [])
        self.assertEqual(len(stubs.gh()), 1)

    def test_a_failing_visibility_answer_reads_as_private(self):
        stubs = Stubs(self.tool_bin, private="")
        self.assertEqual(self.triage([FINDING]), "")
        self.assertEqual(stubs.choices(), [])

    def test_no_github_origin_asks_nobody(self):
        stubs = Stubs(self.tool_bin)
        root = self.repo()
        subprocess.run(["git", "remote", "remove", "origin"], cwd=str(root), check=True)
        sd_jev.jev_triage([FINDING], self.environment(), root, io.StringIO())
        self.assertEqual((stubs.jev(), stubs.gh()), ([], []))

    def test_the_stage_switched_off_asks_nobody(self):
        stubs = Stubs(self.tool_bin)
        self.assertEqual(self.triage([FINDING], JEV_SD_REVIEW_TRIAGE="0"), "")
        self.assertEqual((stubs.jev(), stubs.gh()), ([], []))

    def test_a_jev_that_cannot_answer_asks_github_nothing(self):
        stubs = Stubs(self.tool_bin, gate=3)
        self.assertEqual(self.triage([FINDING]), "")
        self.assertEqual(stubs.gh(), [])
        self.assertEqual([call["argv"][:2] for call in stubs.jev()], [["enabled", sd_jev.TRIAGE_STAGE]])

    def test_a_failing_jev_is_loud_and_stops(self):
        stubs = Stubs(self.tool_bin, code=2)
        said = self.triage([FINDING, FINDING])
        self.assertIn("the Jev shadow reading stopped: `jev` exited 2", said)
        self.assertIn("JEV_SD_REVIEW_TRIAGE=0", said)
        self.assertEqual(len(stubs.choices()), 1)

    def test_one_review_triages_at_most_the_cap(self):
        stubs = Stubs(self.tool_bin)
        self.triage([dict(FINDING, line=n) for n in range(sd_jev.MAX_TRIAGE + 3)])
        subjects = [flag(call["argv"], "--subject") for call in stubs.choices()]
        self.assertEqual(len(subjects), sd_jev.MAX_TRIAGE)
        self.assertTrue(subjects[0].startswith("sd-review-triage:example.demo:"), subjects[0])


class DedupeTests(ReviewFixture):
    """`sd task add` through the real CLI, on a scratch database."""

    def setUp(self) -> None:
        super().setUp()
        self.home = self.tmp / "home"
        self.home.mkdir()
        sd_db.initialise(home=self.home)
        self.root = self.home / "demo"
        self.root.mkdir()
        for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@example.com"],
                     ["config", "user.name", "T"], ["commit", "-q", "--allow-empty", "-m", "first"],
                     ["remote", "add", "origin", "git@github.com:example/demo.git"]):
            subprocess.run(["git", *args], cwd=str(self.root), check=True, capture_output=True)
        # The library keys a checkout under `$HOME` as `~/...` (sd:1439), so
        # this row and the CLI's agree only when both read the scratch home.
        with unittest.mock.patch.dict(os.environ, {"HOME": str(self.home)}), \
                sd_db.connect(sd_db.default_path(self.home), write=True) as connection:
            sd_db.repos.add(connection, self.root, home=self.home)

    def add(self, title: str, **env: str) -> subprocess.CompletedProcess[str]:
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith("JEV_")}
        environment.update(HOME=str(self.home), PATH=str(self.tool_bin) + os.pathsep + os.defpath, **env)
        return subprocess.run([sys.executable, str(ROOT / "bin" / "sd"), "task", "add", title, "--json"],
                              cwd=str(self.root), env=environment, capture_output=True, text=True, check=True)

    def test_a_new_item_records_a_duplicate_pick_and_prints_the_same(self):
        first = json.loads(self.add("Fix the lane, again").stdout)["item"]["id"]
        stubs = Stubs(self.tool_bin)
        added = self.add("Fix the lane")
        state = json.loads(added.stdout)
        self.assertEqual(set(state), {"item", "notes", "revision"})
        self.assertEqual(added.stderr, "")
        [call] = stubs.choices()
        argv = call["argv"]
        self.assertEqual((flag(argv, "--stage"), flag(argv, "--shadow"), flag(argv, "--subject")),
                         ("JEV_SD_TASK_DEDUPE", "none", f"sd-task-dedupe:sd-{state['item']['id']}"))
        self.assertEqual(flag(argv, "--criteria"),
                         f"none=no listed item tracks the same work,sd-{first}=Fix the lane; again")
        self.assertEqual(json.loads(call["state"]), {"new_item_title": "Fix the lane"})

    def test_a_private_repository_sends_no_title(self):
        self.add("Fix the lane")
        stubs = Stubs(self.tool_bin, private="true")
        self.add("Fix the lane too")
        self.assertEqual(stubs.choices(), [])

    def test_the_stage_switched_off_asks_nobody(self):
        self.add("Fix the lane")
        stubs = Stubs(self.tool_bin)
        self.add("Fix the lane too", JEV_SD_TASK_DEDUPE="off")
        self.assertEqual((stubs.jev(), stubs.gh()), ([], []))

    def test_the_first_item_of_a_repository_asks_nobody(self):
        stubs = Stubs(self.tool_bin)
        self.add("Fix the lane")
        self.assertEqual((stubs.jev(), stubs.gh()), ([], []))

