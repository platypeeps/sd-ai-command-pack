"""The optional Jev tier reading, which must be invisible until it is asked for.

Every case here compares a whole result object against the same run without the
opt-in, serialised the way `sd-review --json` serialises it. That is the
contract worth testing: not that some field survived, but that the bytes a
caller reads are the bytes it read before `bin/sd_jev.py` existed. The exit code
comes with them, being a pure function of `status` and the flags.

`jev` is not installed on the machines that run this suite and is not expected
to be. Each case that needs one writes a stub into the fixture's own tool
directory, which is already the only entry on the fixture `PATH`, so the suite
stays offline and the real command is never reached.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import subprocess

from tests.test_sd_review import (
    FakeClient,
    FakeRunner,
    ReviewFixture,
    namespace,
    sd_review,
)

#: Reached through the module under test, which put `bin/` on `sys.path` when it
#: was imported; a bare `import sd_jev` up here would run before that happened.
sd_jev = sd_review.sd_jev

#: A stand-in for the private command. `enabled` answers with the exit code the
#: case is about and reaches nothing; the judgment records the argv and the
#: state it was handed, so a case can assert exactly what would have left the
#: machine. `{answer}` is substituted verbatim, so a case can hand back the
#: fallback token the real `jev` prints when it judged nothing.
STUB = """#!/usr/bin/env python3
import json, pathlib, sys

argv = sys.argv[1:]
if argv[:1] == ["enabled"]:
    pathlib.Path({record!r} + ".gate").write_text(json.dumps(argv))
    raise SystemExit({gate})
pathlib.Path({record!r}).write_text(json.dumps({{"argv": argv, "state": sys.stdin.read()}}))
sys.stderr.write("stub: no key on this machine\\n")
sys.stdout.write({answer!r} + "\\n")
raise SystemExit({code})
"""


class JevTierTests(ReviewFixture):
    def prepare(self) -> pathlib.Path:
        root = self.make_repo("privatename")
        (root / ".github").mkdir()
        (root / ".github/sd-review.json").write_text(json.dumps({"default_tier": "standard"}))
        self.commit(root)
        subprocess.run(["git", "checkout", "-qb", "work"], cwd=str(root), check=True)
        (root / "src.py").write_text("value = 1\n" * 20)
        self.commit(root)
        return root

    def commit(self, root: pathlib.Path) -> None:
        subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(["git", "commit", "--quiet", "-m", "fixture"], cwd=str(root),
                       check=True, capture_output=True)

    def install_stub(self, *, gate: int = 0, answer: str = "deep", code: int = 0) -> pathlib.Path:
        record = self.tmp / "jev-argv.json"
        stub = self.tool_bin / sd_jev.COMMAND
        stub.write_text(STUB.format(gate=gate, answer=answer, code=code, record=str(record)))
        stub.chmod(0o700)
        return record

    def run_review(self, root: pathlib.Path, **extra: str) -> tuple[str, str]:
        """One explain-only review, as its JSON bytes and whatever it said on stderr."""

        args = namespace(scope="branch", explain=True)
        noise = io.StringIO()
        with contextlib.redirect_stderr(noise):
            result = sd_review.review(root, args, FakeRunner(), self.environment(**extra),
                                      self.chatgpt_home(), FakeClient())
        return json.dumps(result, indent=2, sort_keys=True), noise.getvalue()

    def test_a_present_jev_is_reached_with_nothing_set(self):
        """Unset means on. This is the flip, and it inverts the case that was
        here before: the same fixture used to assert jev was never called."""

        root = self.prepare()
        baseline, quiet = self.run_review(root)
        record = self.install_stub(answer="standard")
        _, still_quiet = self.run_review(root)
        self.assertEqual((quiet, still_quiet), ("", ""))
        self.assertNotIn("jev", json.loads(baseline))
        self.assertTrue(record.exists(), "an unset switch did not reach jev")

    def test_no_jev_on_path_changes_nothing_and_says_nothing(self):
        """Silence is the point. `jev` ships in a private companion repository
        and most machines do not have it, so announcing its absence would put
        a line in every review on every one of them, forever."""

        root = self.prepare()
        baseline, _ = self.run_review(root)
        same, said = self.run_review(root)
        self.assertEqual(same, baseline)
        self.assertEqual(said, "")

    def test_a_jev_that_cannot_answer_is_silent_too(self):
        """Exit 3 is `cannot answer on this machine` -- unkeyed, or `jev off`.
        That is the same not-configured case as an absent binary, and it is
        the ordinary state of a machine that merely cloned the companion."""

        root = self.prepare()
        baseline, _ = self.run_review(root)
        record = self.install_stub(gate=3)
        same, said = self.run_review(root)
        self.assertEqual(same, baseline)
        self.assertEqual(said, "")
        self.assertFalse(record.exists(), "the judgment ran although the gate refused")

    def test_a_gate_that_fails_some_other_way_is_loud(self):
        """The other side of the rule above. 3 is not configured; anything
        else is broken, and a lane that quietly stops running is the defect
        this repository has already been bitten by."""

        root = self.prepare()
        baseline, _ = self.run_review(root)
        record = self.install_stub(gate=2)
        same, said = self.run_review(root)
        self.assertEqual(same, baseline)
        self.assertIn("exited 2", said)
        self.assertIn("keeping the routed tier standard", said)
        self.assertFalse(record.exists())

    def test_a_failing_judgment_leaves_the_review_where_it_was(self):
        root = self.prepare()
        baseline, _ = self.run_review(root)
        self.install_stub(answer="deep", code=1)
        same, said = self.run_review(root)
        self.assertEqual(same, baseline)
        self.assertIn("exited 1", said)

    def test_an_answer_outside_the_policy_tiers_is_not_a_tier(self):
        root = self.prepare()
        baseline, _ = self.run_review(root)
        self.install_stub(answer="thorough")
        same, said = self.run_review(root)
        self.assertEqual(same, baseline)
        self.assertIn("'thorough' is not one of", said)

    def test_every_off_word_switches_the_stage_off(self):
        root = self.prepare()
        baseline, _ = self.run_review(root)
        record = self.install_stub()
        for word in sd_jev.sd_lib.JEV_FLAG_OFF:
            for value in (word, word.upper(), f"  {word} "):
                with self.subTest(value=value):
                    same, said = self.run_review(root, **{sd_jev.STAGE: value})
                    self.assertEqual(same, baseline,
                                     f"{sd_jev.STAGE}={value!r} took a reading")
                    self.assertEqual(said, "")
        self.assertFalse(record.exists())

    def test_a_word_that_is_not_an_off_word_leaves_the_stage_on(self):
        """Including the `1` this gate used to require: a typo is not an
        outage. `read_flag`'s rule in `jev.py`, which `JEV_FLAG_OFF` is
        copied from, and the reason the copy is pinned word for word below."""

        root = self.prepare()
        self.install_stub(answer="deep")
        for value in ("1", "true", "yes", "", "of", "offf"):
            with self.subTest(value=value):
                moved = json.loads(self.run_review(root, **{sd_jev.STAGE: value})[0])
                self.assertEqual(moved["route"]["tier"], "deep",
                                 f"{sd_jev.STAGE}={value!r} switched the stage off")

    def test_the_off_word_vocabulary_matches_the_one_it_was_copied_from(self):
        """`jev` is private and this repository is public, so `JEV_FLAG_OFF`
        is a copy and not an import. Two copies drift; this pins the words so
        the drift is a failure here rather than a stage that stops running
        there. One definition serves both gates in this repository, in
        `sd_lib`, which is why this pins it there and not per caller.
        """

        self.assertEqual(sd_jev.sd_lib.JEV_FLAG_OFF,
                         ("0", "off", "false", "no", "disabled"))
        self.assertFalse(sd_jev.sd_lib.jev_stage_off(None), "unset must mean on")

    def test_an_answered_reading_moves_the_tier_and_records_that_it_did(self):
        root = self.prepare()
        baseline = json.loads(self.run_review(root)[0])
        self.install_stub(answer="deep")
        moved = json.loads(self.run_review(root)[0])
        self.assertEqual(baseline["route"]["tier"], "standard")
        self.assertEqual(moved["route"]["tier"], "deep")
        self.assertEqual(moved["jev"], {"routed_tier": "standard", "tier": "deep",
                                        "moved": True, "source": "judged"})
        self.assertIn(baseline["route"]["reason"], moved["route"]["reason"])
        self.assertTrue(moved["route"]["reason"].endswith("Jev read the diff and chose tier deep"))
        # The tier is the only input to the Copilot line, so moving one moves it.
        self.assertEqual(baseline["remote_reviews"]["copilot"]["tier"], "standard")
        self.assertEqual(moved["remote_reviews"]["copilot"]["tier"], "deep")
        self.assertEqual(moved["status"], baseline["status"])

    def test_an_answer_that_agrees_with_the_routing_still_records_the_reading(self):
        root = self.prepare()
        self.install_stub(answer="standard")
        held = json.loads(self.run_review(root)[0])
        self.assertEqual(held["route"]["tier"], "standard")
        self.assertEqual(held["jev"]["moved"], False)

    def test_the_fallback_token_is_not_an_answer_although_it_exits_zero(self):
        """The case `--fallback` exists for, and the one an exit code cannot see."""

        root = self.prepare()
        baseline, _ = self.run_review(root)
        self.install_stub(answer=sd_jev.FALLBACK, code=0)
        same, said = self.run_review(root)
        self.assertEqual(same, baseline)
        self.assertIn("Jev judged nothing", said)
        self.assertIn("no key on this machine", said)

    def test_a_fallback_token_can_never_collide_with_a_declared_tier(self):
        self.assertEqual(sd_jev._jev_fallback(["cheap", "deep"]), sd_jev.FALLBACK)
        crowded = [sd_jev.FALLBACK, sd_jev.FALLBACK + "-x"]
        self.assertNotIn(sd_jev._jev_fallback(crowded), crowded)

    def test_an_unsure_judgment_keeps_the_routed_tier(self):
        root = self.prepare()
        baseline, _ = self.run_review(root)
        self.install_stub(answer=sd_jev.UNSURE)
        same, said = self.run_review(root)
        self.assertEqual(same, baseline)
        self.assertIn(f"unsure below {sd_jev.UNSURE_BELOW}", said)

    def test_the_call_carries_the_diff_shape_and_nothing_private(self):
        root = self.prepare()
        record = self.install_stub()
        self.run_review(root)
        sent = json.loads(record.read_text())
        argv, state = sent["argv"], sent["state"]
        self.assertEqual(argv[0], "choice")
        self.assertEqual(argv[1], "How deeply should this code change be reviewed?")
        self.assertEqual(argv[2:4], ["--criteria", sd_jev._jev_criteria(
            ["skip", "cheap", "standard", "deep"])])
        self.assertEqual(argv[4:], ["--unsure-below", sd_jev.UNSURE_BELOW, "--state", "-",
                                    "--state-format", "json", "--caller", "sd-review",
                                    "--id", "sd-review-tier", "--stage", sd_jev.STAGE,
                                    "--fallback", sd_jev.FALLBACK])
        self.assertEqual(json.loads(state), {
            "changed_paths": ["src.py"], "changed_paths_omitted": 0, "path_count": 1,
            "lines_moved": 20,
            "deterministic_routing_said": "no category matched; default tier standard"})
        for private in (str(root), str(self.tmp), "privatename", "work", "Fixture",
                        "fixture@example.invalid", "value = 1"):
            self.assertNotIn(private, state + " ".join(argv), f"{private!r} left the machine")

    def test_both_calls_name_themselves_for_the_judgment_ledger(self):
        """sd:1253. Without `--caller` and `--stage` the judgment lands under
        `unknown`, and without `--record` a declining gate leaves no row, so
        the busiest Jev caller on the machine was the one the ledger missed."""

        root = self.prepare()
        for gate in (0, 3):
            with self.subTest(gate=gate):
                record = self.install_stub(gate=gate)
                self.run_review(root)
                sent = json.loads(pathlib.Path(str(record) + ".gate").read_text())
                self.assertEqual(sent, ["enabled", sd_jev.STAGE, "--record",
                                        "--caller", "sd-review"])

    def test_no_criterion_carries_a_separator_that_would_split_it(self):
        criteria = sd_jev._jev_criteria(sorted(sd_jev.TIER_CRITERIA))
        self.assertEqual(len(criteria.split(",")), len(sd_jev.TIER_CRITERIA))
        for pair in criteria.split(","):
            self.assertEqual(len(pair.split("=")), 2)

    def test_a_tier_this_file_cannot_describe_is_sent_bare(self):
        self.assertEqual(sd_jev._jev_criteria(["forensic"]), "forensic")

    def test_a_long_change_sends_a_count_instead_of_every_path(self):
        paths = [f"dir{index}/file.py" for index in range(sd_jev.MAX_PATHS + 5)]
        state = json.loads(sd_jev._jev_state(paths, 900, "because"))
        self.assertEqual(len(state["changed_paths"]), sd_jev.MAX_PATHS)
        self.assertEqual(state["changed_paths_omitted"], 5)
        self.assertEqual((state["path_count"], state["lines_moved"]), (len(paths), 900))

    def test_a_command_that_cannot_be_executed_is_a_declined_reading(self):
        note = io.StringIO()
        env = {"PATH": str(self.tool_bin)}
        broken = self.tool_bin / sd_jev.COMMAND
        broken.write_text("not an executable\n")
        broken.chmod(0o700)
        tier, record = sd_jev.jev_tier("cheap", ["cheap", "deep"], ["a.py"], 3, "why", env, note)
        self.assertEqual((tier, record), ("cheap", None))
        self.assertIn("keeping the routed tier cheap", note.getvalue())
