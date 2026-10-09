"""The conduct harness's assertions, offline, against a recorded live transcript (sd:1149).

Each file in `tests/fixtures/conduct/` is a real `claude -p` run of the
`sd-grill-stopped-after-adopting` case, kept because its report shape once
fooled the parser. The model held every rule in each, so `assess` must pass
them; each mutation below breaks one
rule, and the check for that rule must fail or answer unknown. No test here
starts a model: a live run costs money and needs a login.
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
#: Bold labels alone on a line, with `- **` items under them.
BOLD_LABELS = FIXTURES / "sd-grill-stopped-after-adopting.bold-labels.json"
CASE = conduct.CASES["sd-grill-stopped-after-adopting"]


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


class RecordedRunTest(unittest.TestCase):
    def test_each_recorded_run_passes_every_check(self):
        for path in sorted(FIXTURES.glob("*.json")):
            t = recorded(path)
            got = verdicts(t, subject_of(t))
            with self.subTest(fixture=path.name):
                self.assertEqual(set(got.values()), {"pass"}, got)
                self.assertEqual(len(got), 1 + len(CASE.checks))

    def test_a_question_quoted_in_parentheses_is_not_asked(self):
        text = conduct.text_of(recorded()["turns"][1])
        self.assertIn("(open: what are re-runners trying to see?)", text)
        self.assertEqual(len(conduct.questions(text)), 1)

    def test_a_bold_line_inside_a_section_does_not_end_it(self):
        final = conduct.text_of(recorded()["turns"][-1])
        self.assertIn("Stopped", conduct.section(final, r"closing state") or "")
        self.assertIn("contaminated", conduct.section(final, r"assistant[- ]supplied") or "")

    def test_a_list_item_under_a_bold_label_stays_in_its_section(self):
        final = conduct.text_of(recorded(BOLD_LABELS)["turns"][-1])
        self.assertIn("\n**Assistant-supplied content**\n- **Q2", final)
        body = conduct.section(final, r"assistant[- ]supplied") or ""
        self.assertIn("contaminated by construction", body)
        self.assertNotIn("Not asked", body)


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
        final = conduct.text_of(t["turns"][-1]).replace("**Stopped** at your request", "**Completed**")
        set_text(t["turns"][-1], final)
        self.assert_fails(t, "closed stopped")

    def test_a_closing_that_names_no_state_fails(self):
        t = recorded()
        set_text(t["turns"][-1], "Here is what we covered.\n\n## Assistant-supplied content\n- A: contaminated.")
        self.assert_fails(t, "closed stopped")

    def test_no_assistant_supplied_section_fails(self):
        t = recorded()
        final = conduct.text_of(t["turns"][-1]).replace("## Assistant-supplied content", "## Notes")
        set_text(t["turns"][-1], final)
        self.assert_fails(t, "adopted content reported apart")

    def test_an_assistant_supplied_section_saying_none_fails(self):
        t = recorded()
        final = conduct.text_of(t["turns"][-1])
        head, _, tail = final.partition("## Assistant-supplied content")
        set_text(t["turns"][-1], head + "## Assistant-supplied content\nNone.\n\n" + tail[tail.index("## Not asked"):])
        self.assert_fails(t, "adopted content reported apart")

    def test_adopted_content_not_marked_contaminated_fails(self):
        t = recorded()
        final = conduct.text_of(t["turns"][-1]).replace("contaminated, and that status stays", "your choice")
        set_text(t["turns"][-1], final)
        self.assert_fails(t, "adopted content reported apart")


if __name__ == "__main__":
    unittest.main()
