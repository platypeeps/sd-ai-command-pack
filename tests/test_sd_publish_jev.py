"""`sd-publish`'s Jev judgment stays optional, private, and non-publishing.

The step added to `skills/sd-publish/SKILL.md` asks an external, private
command for two numbers before the draft is shown. Three properties of it can
rot silently in prose, so they are read out of the file rather than
remembered.

**Off by default.** Jev is experimental and the command is private. A public
reader without it must get today's behaviour byte for byte, so the argument
has to default to `off` and the step has to name both gates: the user's
opt-in and `jev enabled` exiting 0. A later edit that drops the second gate
turns an unavailable command into a hard dependency, and nothing else here
would notice.

**Nothing private leaves.** The questions need the draft, the source span,
the destination name and the supplied constraints. A file path, a repository
name, a credential or a destination account detail in that state is a leak
out of a private workflow into a hosted model, and the step's refusal of each
is what this module holds in place.

**Neither number is permission.** A fit score and a faithfulness probability
change what the assistant writes, never what it sends. The skill does not
publish today and must not learn to, so the execution boundary is checked
alongside the judgment that could be mistaken for approval.

**A failed call does not read like a passing one.** `--fallback` exists so a
lane keeps moving, and it prints its answer and exits 0. An integration that
reported the questions it sent would print the same line whether Jev judged
the draft or answered nothing, and a dead check reads clean forever. So the
step has to count answers and report both numbers, and the flag has to sit
after the verb, where the dispatcher accepts it.

The checks read the live section text and match on meaning-bearing tokens,
not on whole sentences: rewording is expected and is not a failure, while
deleting the rule is.
"""

from __future__ import annotations

import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "skills/sd-publish/SKILL.md"

#: A numbered workflow step: its number, and its body up to the next number.
STEP = re.compile(r"^(\d+)\. (.*?)(?=^\d+\. |\Z)", re.S | re.M)

#: An argument bullet, keyed by the name left of its first `=`.
ARGUMENT = re.compile(r"^- `([a-z]+)=([^`]*)`(.*?)(?=^- `|\Z)", re.S | re.M)


def section(title: str) -> str:
    """The body of the `## <title>` section, without its heading."""

    text = SKILL.read_text(encoding="utf-8")
    match = re.search(r"^## " + re.escape(title) + r"\n(.*?)(?=^## |\Z)",
                      text, re.S | re.M)
    assert match, f"sd-publish has no '{title}' section"
    return match.group(1)


def steps() -> dict[int, str]:
    """The workflow steps, numbered as the file numbers them."""

    return {int(number): body for number, body in STEP.findall(section("Workflow"))}


def judgment_steps() -> str:
    """Every workflow step that names `jev`, joined."""

    return "\n".join(body for body in steps().values() if "jev" in body)


class JudgmentIsOptional(unittest.TestCase):
    def test_the_judge_argument_defaults_to_off(self):
        arguments = dict((name, values + rest)
                         for name, values, rest in ARGUMENT.findall(section("Arguments")))
        self.assertIn("judge", arguments, "sd-publish lost its `judge=` argument")
        judge = arguments["judge"]
        self.assertTrue(judge.startswith("off|"), f"`off` is not the first value: {judge!r}")
        self.assertIn("default `off`", judge)

    def test_the_step_names_both_gates_and_the_unavailable_exit(self):
        body = judgment_steps()
        self.assertTrue(body, "no workflow step names `jev`")
        self.assertIn("judge=jev", body, "the opt-in gate is missing")
        self.assertIn("jev enabled", body, "the availability probe is missing")
        self.assertRegex(body, r"[Ee]xit 3", "exit 3 is not named as unavailable")
        self.assertRegex(body, r"off by default")
        self.assertIn("`not checked`", body,
                      "an unrun probe must be recorded as `not checked`, not as "
                      "the `not run` that an unavailable command produces")

    def test_an_unavailable_command_changes_nothing(self):
        body = judgment_steps()
        self.assertRegex(body, r"continue unchanged",
                         "an unavailable command must leave the workflow unchanged")
        self.assertRegex(body, r"costs nothing",
                         "the probe must be stated as free")
        self.assertRegex(body, r"--fallback",
                         "the fallback answer is not described")
        self.assertRegex(body, r"[Nn]ever report it as a pass|not run",
                         "a fallback answer must not read as a pass")

    def test_a_public_reader_sees_the_command_as_available_or_not(self):
        body = judgment_steps()
        self.assertRegex(body, r"when `jev` is available",
                         "the step must read as conditional to a reader without `jev`")


class NothingPrivateLeaves(unittest.TestCase):
    def test_the_state_is_enumerated_and_closed(self):
        body = judgment_steps()
        for part in ("the exact draft", "source spans", "destination name"):
            self.assertIn(part, body, f"the state no longer names {part}")
        self.assertIn("Send\n    nothing else.", body.replace("\r\n", "\n"))

    def test_each_private_class_is_refused_by_name(self):
        body = judgment_steps()
        for forbidden in ("file paths", "repository names", "credentials",
                          "destination account details", "profile content"):
            with self.subTest(forbidden=forbidden):
                self.assertIn(forbidden, body,
                              f"the step stopped refusing {forbidden}")

    def test_a_confidential_source_is_not_sent_at_all(self):
        body = judgment_steps()
        self.assertRegex(body, r"confidential", "the confidential source case is gone")
        self.assertRegex(body, r"leave `judge=off`",
                         "a confidential source must not be sent at all")


class NeitherNumberIsPermission(unittest.TestCase):
    def test_a_low_fit_score_is_a_rewrite(self):
        body = judgment_steps()
        self.assertRegex(body, r"low fit score is a rewrite",
                         "a low fit score must change the draft, not the report")
        self.assertRegex(body, r"judge the new draft",
                         "a rewrite must be judged again before the preview")

    def test_a_low_faithfulness_probability_is_a_stop(self):
        body = judgment_steps()
        self.assertRegex(body, r"stop-and-ask",
                         "a low faithfulness probability must stop the workflow")
        self.assertRegex(body, r"near the middle",
                         "a mid probability must not read as half faithful")

    def test_a_high_number_authorises_nothing(self):
        body = judgment_steps()
        self.assertRegex(body, r"neither as permission to publish",
                         "the step must deny that the numbers are permission")
        self.assertRegex(body, r"does not send, publish, or schedule",
                         "the step must restate the execution boundary")

    def test_the_safety_rules_bound_the_judgment(self):
        rules = section("Safety rules")
        self.assertRegex(rules, r"`jev` judgment is optional, additive, and off by default")
        self.assertRegex(rules, r"writes nothing")
        self.assertRegex(rules, r"high\s+number is not approval")

    def test_the_skill_still_publishes_nothing(self):
        rules = section("Safety rules")
        self.assertRegex(rules, r"This skill is read-only\.")
        self.assertRegex(rules, r"It does not send, publish, schedule, post")
        report = section("Final report")
        self.assertRegex(report, r"\*\*Execution boundary\*\*")
        self.assertRegex(report, r"media production marked `not run`")


class TheJudgmentIsReported(unittest.TestCase):
    def test_the_final_report_carries_the_judgment(self):
        report = section("Final report")
        self.assertRegex(report, r"\*\*Destination-fit judgment\*\*",
                         "the report lost its judgment bullet")
        for part in ("judge mode", "fit score", "faithfulness probability",
                     "`not run`", "`not checked`"):
            with self.subTest(part=part):
                self.assertIn(part, report)

    def test_both_questions_travel_in_one_request(self):
        body = judgment_steps()
        self.assertRegex(body, r"one `ask` request",
                         "the questions must share a request")
        self.assertIn("`score`", body, "the fit question is not a score")
        self.assertIn("`noul`", body, "the faithfulness question is not a noul")

    def test_the_faithfulness_question_names_both_failure_shapes(self):
        body = judgment_steps()
        self.assertRegex(body, r"contradicts\s+the\s+source",
                         "a contradiction must be a failure of the condition")
        self.assertRegex(body, r"adds or strengthens a claim",
                         "an added claim must be a failure of the condition")


class TheWorkflowStillReads(unittest.TestCase):
    def test_the_steps_are_numbered_consecutively_from_one(self):
        numbers = sorted(steps())
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)),
                         f"the workflow numbering is broken: {numbers}")

    def test_the_judgment_precedes_the_preview(self):
        found = steps()
        preview = [number for number, body in found.items()
                   if "Produce a preview" in body]
        self.assertEqual(len(preview), 1, "the preview step is not unique")
        judging = [number for number, body in found.items() if "jev" in body]
        self.assertTrue(judging, "no step names `jev`")
        self.assertLess(max(judging), preview[0],
                        "the judgment must run before the draft is shown")


class TheCallIsWrittenAsItRuns(unittest.TestCase):
    """The invocation in the prose has to be one `jev` actually accepts."""

    def test_the_fallback_flag_follows_the_verb(self):
        body = judgment_steps()
        self.assertRegex(body, r"jev ask\b[^`]*--fallback",
                         "the fallback must be shown after the `ask` verb")
        self.assertNotRegex(body, r"`jev --fallback",
                            "a leading `--fallback` is rejected by the dispatcher")
        self.assertRegex(body, r"after the verb",
                         "the step must say where the flag goes")

    def test_the_step_invents_no_flags_that_ask_refuses(self):
        body = judgment_steps()
        self.assertIn("--questions", body, "`ask` needs its questions file")
        self.assertIn("--state", body, "`ask` needs its shared state")
        for refused in ("--id", "--json", "--gate"):
            with self.subTest(refused=refused):
                self.assertNotIn(refused, body,
                                 f"`ask` does not take {refused}")

    def test_one_state_is_shared_and_referenced_by_path(self):
        body = judgment_steps()
        self.assertRegex(body, r"share one state",
                         "both questions must run over one state")
        self.assertRegex(body, r"backticked paths",
                         "nested state is referenced by backticked path")


class AFailedCallCannotReadAsAPass(unittest.TestCase):
    def test_answers_are_counted_not_questions(self):
        body = judgment_steps()
        self.assertRegex(body, r"[Cc]ount the answers",
                         "the step must count answers")
        self.assertRegex(body, r"not the questions you sent",
                         "counting the questions sent is the bug this prevents")
        self.assertRegex(body, r"report\s+both numbers",
                         "both numbers must reach the report")

    def test_exit_zero_is_not_read_as_a_judgment(self):
        body = judgment_steps()
        self.assertRegex(body, r"Exit 0 says the call returned",
                         "exit 0 must not be read as a judgment")
        self.assertRegex(body, r"fallback answers nothing and exits 0",
                         "the fallback's exit code must be called out")
        self.assertRegex(body, r"missing either answer is not run",
                         "a partial answer set must not pass")

    def test_the_report_separates_the_two_counts(self):
        report = section("Final report")
        self.assertRegex(report, r"questions sent and answers returned",
                         "the report must carry both counts")
        self.assertRegex(report, r"separate numbers",
                         "one combined number hides a fallback")


if __name__ == "__main__":
    unittest.main()
