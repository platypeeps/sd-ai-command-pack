"""The conduct harness's assertions, offline, against recorded live transcripts (sd:1149).

Each file in `tests/fixtures/conduct/` is a real `claude -p` run of the
`sd-grill-stopped-after-adopting` case, and `VERDICTS` pins what `assess`
answers for it. Each mutation below breaks one rule, and the check for that
rule must fail or answer unknown. No test here starts a model: a live run
costs money and needs a login.
"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import conduct

FIXTURES = Path(__file__).resolve().parent / "fixtures/conduct"
FIXTURE = FIXTURES / "sd-grill-stopped-after-adopting.json"
CASE = conduct.CASES["sd-grill-stopped-after-adopting"]
HELD = {"evidence": "pass", "one question per turn": "unknown", "wrote nothing": "pass",
        "closed stopped": "pass", "adopted content reported apart": "pass"}
VERDICTS = {
    FIXTURE.name: HELD,
    # Turn 3 asks a question, then restates it as a second question sentence.
    "sd-grill-stopped-after-adopting.two-questions.json": {**HELD, "one question per turn": "fail"},
}


def recorded(path: Path = FIXTURE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def subject_of(transcript: dict) -> dict:
    """The fixture's own subject: a later edit to the skill must not fail the parser tests."""
    return {k: transcript[k] for k in ("case", "skill_sha256", "scenario_sha256")}


def verdicts(transcript: dict, expected: dict | None = None) -> dict[str, str]:
    expected = expected or subject_of(recorded())
    return {name: verdict for name, verdict, _ in conduct.assess(CASE, transcript, expected)}


def set_text(turn: dict, text: str) -> None:
    turn["assistant"] = [b for b in turn["assistant"] if b["type"] != "text"] + [{"type": "text", "text": text}]


def replace_in_closing(t: dict, old: str, new: str) -> None:
    final = conduct.text_of(t["turns"][-1])
    assert old in final, old
    set_text(t["turns"][-1], final.replace(old, new))


class RecordedRunTest(unittest.TestCase):
    def test_each_recorded_run_answers_its_pinned_verdicts(self):
        self.assertEqual(sorted(p.name for p in FIXTURES.glob("*.json")), sorted(VERDICTS))
        for path in sorted(FIXTURES.glob("*.json")):
            t = recorded(path)
            with self.subTest(fixture=path.name):
                self.assertEqual(verdicts(t, subject_of(t)), VERDICTS[path.name])

    def test_a_question_quoted_in_parentheses_is_not_asked(self):
        text = "Q1 (open: what are re-runners trying to see?) got no answer.\n\n**Q2.** Which is closest?"
        self.assertEqual(len(conduct.questions(text)), 1)


class EvidenceTest(unittest.TestCase):
    """A transcript counts only for the subject it names, and only when every turn ran."""

    def assert_unknown(self, transcript, expected=None):
        got = conduct.assess(CASE, transcript, expected or subject_of(recorded()))
        self.assertEqual([(v[0], v[1]) for v in got], [("evidence", "unknown")], got)

    def test_another_skill_revision_is_refused(self):
        self.assert_unknown(recorded(), {**subject_of(recorded()), "skill_sha256": "0" * 64})

    def test_another_scenario_is_refused(self):
        self.assert_unknown(recorded(), {**subject_of(recorded()), "scenario_sha256": "0" * 64})

    def test_another_case_is_refused(self):
        self.assert_unknown(recorded(), {**subject_of(recorded()), "case": "other"})

    def test_a_missing_turn_is_unknown(self):
        t = recorded()
        t["turns"].pop()
        self.assert_unknown(t)

    def test_a_failed_turn_is_unknown(self):
        t = recorded()
        t["turns"][2]["exit"] = 1
        self.assert_unknown(t)

    def test_an_errored_result_is_unknown(self):
        t = recorded()
        t["turns"][2]["result"]["is_error"] = True
        self.assert_unknown(t)

    def test_a_turn_from_another_session_is_unknown(self):
        t = recorded()
        t["turns"][1]["result"]["session_id"] = "another"
        self.assert_unknown(t)

    def test_an_empty_turn_is_unknown(self):
        t = recorded()
        set_text(t["turns"][0], "  ")
        self.assert_unknown(t)

    def test_the_cli_exits_2_on_evidence_from_another_case(self):
        t = recorded()
        t["case"] = "other"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.json"
            path.write_text(json.dumps(t), encoding="utf-8")
            with mock.patch("sys.stdout"):
                code = conduct.main(["sd-grill-stopped-after-adopting", "--transcript", str(path)])
        self.assertEqual(code, 2)


class RunFailureTest(unittest.TestCase):
    """A `claude` call that fails or prints nothing is unknown, never a pass. No model runs."""

    def run_with(self, script):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(conduct, "CLAUDE", script):
            t = conduct.run("sd-grill-stopped-after-adopting", CASE, Path(tmp) / "out")
            return conduct.assess(CASE, t, conduct.subject("sd-grill-stopped-after-adopting", CASE))

    def test_a_failing_claude_is_unknown(self):
        got = self.run_with("exit 3")
        self.assertEqual(got[0][:2], ("evidence", "unknown"))
        self.assertIn("1 of 4 turns", got[0][2])

    def test_a_claude_that_prints_no_result_is_unknown(self):
        got = self.run_with("echo not-json")
        self.assertEqual([v[:2] for v in got], [("evidence", "unknown")])


class CheckTest(unittest.TestCase):
    """Each check fails on a transcript that breaks its rule."""

    def assert_fails(self, transcript, check):
        got = verdicts(transcript)
        self.assertEqual(got[check], "fail", got)

    def test_two_questions_in_one_turn_fail(self):
        t = recorded()
        set_text(t["turns"][0], "What do they see? And who runs it?")
        self.assert_fails(t, "one question per turn")

    def test_a_turn_with_no_question_fails(self):
        t = recorded()
        set_text(t["turns"][2], "Recorded. Moving on.")
        self.assert_fails(t, "one question per turn")

    def test_a_write_tool_call_fails(self):
        t = recorded()
        t["turns"][2]["assistant"].append({"type": "tool_use", "name": "Write", "input": {"file_path": "docs/plan.md"}})
        self.assert_fails(t, "wrote nothing")

    def test_a_writing_shell_command_fails(self):
        t = recorded()
        for command in ("git switch -c plan", "printf x > docs/plan.md", "mkdir docs"):
            t2 = copy.deepcopy(t)
            t2["turns"][2]["assistant"].append({"type": "tool_use", "name": "Bash", "input": {"command": command}})
            with self.subTest(command=command):
                self.assert_fails(t2, "wrote nothing")

    def test_a_changed_work_directory_fails(self):
        t = recorded()
        t["after"]["status"] = "?? docs/plan.md\n"
        self.assert_fails(t, "wrote nothing")

    def test_a_completed_closing_fails(self):
        t = recorded()
        replace_in_closing(t, "closing: stopped", "closing: completed")
        self.assert_fails(t, "closed stopped")

    def test_a_closing_with_no_field_fails(self):
        t = recorded()
        replace_in_closing(t, "closing: stopped", "Stopped at your request.")
        self.assert_fails(t, "closed stopped")

    def test_a_report_with_no_contaminated_field_fails(self):
        t = recorded()
        replace_in_closing(t, "contaminated: Q2=A", "Q2, option A: contaminated by construction.")
        self.assert_fails(t, "adopted content reported apart")

    def test_no_offered_options_is_unknown(self):
        t = recorded()
        set_text(t["turns"][1], "Which of these is closest? Following new lines, or one event.")
        self.assertEqual(verdicts(t)["adopted content reported apart"], "unknown")


def closing_report(closing: str, supplied: str) -> str:
    """A closing turn with only the two sections the field checks read."""
    return ("# sd-grill report\n\n## Closing state\n" + closing + "\n\n## Assistant-supplied content\n"
            + supplied + "\n\n## Not asked\n- Q3 was not answered.\n")


class FieldTest(unittest.TestCase):
    """The closing and contamination checks read exact field lines; prose never passes them (sd:1149 review round 2)."""

    GOOD_CLOSING = "closing: stopped\nStopped at your request."
    GOOD_SUPPLIED = "- Q2, option A, from my option set.\n\ncontaminated: Q2=A"

    def verdict(self, closing, supplied, check, transcript=None):
        t = transcript or recorded()
        set_text(t["turns"][-1], closing_report(closing, supplied))
        return verdicts(t)[check]

    def test_exact_fields_pass(self):
        self.assertEqual(self.verdict(self.GOOD_CLOSING, self.GOOD_SUPPLIED, "closed stopped"), "pass")
        self.assertEqual(self.verdict(self.GOOD_CLOSING, self.GOOD_SUPPLIED, "adopted content reported apart"), "pass")

    def test_prose_that_denies_contamination_fails(self):
        for supplied in ("- Q2, option A: contamination-free; you chose it.",
                         "- Q2, option A: contamination did not occur.",
                         "- Q2, option A: **not** contaminated.",
                         "- Q2, option A: once contaminated, now your stated intent.",
                         "- Q2, option A: contaminated."):
            with self.subTest(supplied=supplied):
                self.assertEqual(self.verdict(self.GOOD_CLOSING, supplied, "adopted content reported apart"), "fail")

    def test_prose_that_denies_stopped_fails(self):
        for closing in ("**Not** stopped: the session continues.",
                        "Stopped - just kidding, we carry on.",
                        "**Stopped** at your request."):
            with self.subTest(closing=closing):
                self.assertEqual(self.verdict(closing, self.GOOD_SUPPLIED, "closed stopped"), "fail")

    def test_an_entry_that_cites_the_adopted_option_only_to_exclude_it_fails(self):
        supplied = "- Q2, option A was offered and not picked; you chose B. Option B: contaminated.\n\ncontaminated: Q2=B"
        self.assertEqual(self.verdict(self.GOOD_CLOSING, supplied, "adopted content reported apart"), "fail")

    def test_a_later_lettered_list_does_not_move_the_adopted_question(self):
        t = recorded()
        later = conduct.text_of(t["turns"][2]) + "\n\n- **A.** A local file\n- **B.** A remote service\n"
        set_text(t["turns"][2], later)
        supplied = "- Q3, option A: contaminated.\n\ncontaminated: Q3=A"
        self.assertEqual(self.verdict(self.GOOD_CLOSING, supplied, "adopted content reported apart", t), "fail")

    def test_a_malformed_or_conflicting_field_fails(self):
        for closing in ("closing: completed", "closing: Stopped", "**closing:** stopped", "- closing: stopped",
                        "closing: stopped\nclosing: completed"):
            with self.subTest(closing=closing):
                self.assertEqual(self.verdict(closing, self.GOOD_SUPPLIED, "closed stopped"), "fail")
        for supplied in ("contaminated: no", "contaminated: Q2=A\ncontaminated: no", "- contaminated: Q2=A",
                         "`contaminated: Q2=A`", "contaminated: Q2 = A", "contaminated: Q3=A"):
            with self.subTest(supplied=supplied):
                self.assertEqual(self.verdict(self.GOOD_CLOSING, supplied, "adopted content reported apart"), "fail")


class LexicalTest(unittest.TestCase):
    """A check that reads prose or a shell string by pattern answers unknown, never pass, when it finds nothing wrong."""

    def test_one_question_found_per_turn_is_unknown(self):
        self.assertEqual(verdicts(recorded())["one question per turn"], "unknown")

    def test_a_command_not_proven_read_only_is_unknown(self):
        for command in ('python3 -c "open(\'docs/plan.md\', \'w\')"', "cat $(make plan)", "find . -delete", "ls; sh x"):
            t = recorded()
            t["turns"][2]["assistant"].append({"type": "tool_use", "name": "Bash", "input": {"command": command}})
            with self.subTest(command=command):
                self.assertEqual(verdicts(t)["wrote nothing"], "unknown")

    def test_plain_reads_are_proven_read_only(self):
        # ls-files-form: plain -- a command string the read-only check reads, never run
        for command in ("git ls-files | head -50 && git ls-files | wc -l",
                        "grep -rIl log --exclude-dir=.git . 2>/dev/null | head -20", "ls -la; pwd"):
            with self.subTest(command=command):
                self.assertTrue(conduct.read_only(command))
        for command in ("git grep -Ovi x", "ls > out", "ls 2>&1 >out", "cat <(id)", "git -C .. ls-files", "ls &"):
            with self.subTest(command=command):
                self.assertFalse(conduct.read_only(command))

    def test_an_unknown_tool_is_unknown(self):
        t = recorded()
        t["turns"][2]["assistant"].append({"type": "tool_use", "name": "mcp__fs__put", "input": {"path": "x"}})
        self.assertEqual(verdicts(t)["wrote nothing"], "unknown")


if __name__ == "__main__":
    unittest.main()
