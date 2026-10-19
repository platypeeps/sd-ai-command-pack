"""sd-action-inbox keeps a waiting-on-others section that cannot send (sd:5156).

The section lists mail the user sent that asks something of someone else and
has had no reply for two weeks, each with a nudge drafted as text. The skill
is prose run by a model, so these checks read the file, and they aim at what
a rewrite must keep rather than at the sentences around it.

**Absence carries the weight.** The skill is read-only; a nudge that a run
could send, or park as a draft in the mail client, is a write to a source.
So the section must say never to send, and the file must name no mail tool
that sends or saves a draft. A thread the run could not read in full is an
unknown result, not "no reply", so the section routes it to `unclear`.

**One threshold.** Two weeks is stated once, as `14 days`. A second day
count in the section would be a second threshold for a reader to pick from.

Nothing here reaches a mail endpoint: the file is the subject.
"""

from __future__ import annotations

import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "contrib/sd-action-inbox/SKILL.md"

#: The heading the workflow's section carries and the final-report field.
SECTION = "## Waiting on others"
FIELD = "**Waiting on others**"

#: Mail connector verbs that send or store a message. Draft nudges stay in
#: the report, so the skill names none of them.
SENDING_TOOLS = re.compile(
    r"\b(send_gmail_message|draft_gmail_message|create_draft|send_message|"
    r"send_email|gmail_send|messages\.send|drafts\.create)\b"
)


def section(text: str, heading: str) -> str:
    """The body under `heading`, up to the next heading of the same level."""

    start = text.find(heading + "\n")
    if start < 0:
        return ""
    body = text[start + len(heading) + 1:]
    end = re.search(r"^## ", body, flags=re.MULTILINE)
    return body[: end.start()] if end else body


class WaitingOnOthers(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SKILL.read_text(encoding="utf-8")
        self.waiting = section(self.text, SECTION)

    def test_the_section_and_its_report_field_exist(self) -> None:
        self.assertTrue(self.waiting, f"{SKILL.name} has no `{SECTION}` section")
        report = section(self.text, "## Final report")
        self.assertIn(FIELD, report)

    def test_the_threshold_is_fourteen_days_and_only_that(self) -> None:
        counts = re.findall(r"\b(\d+)\s+days?\b", self.waiting)
        self.assertEqual(["14"], sorted(set(counts)), counts)

    def test_a_nudge_is_never_sent_or_saved(self) -> None:
        self.assertRegex(self.waiting, r"(?i)\bnever send\b")
        self.assertRegex(self.waiting, r"(?i)\bdraft\b")
        self.assertIsNone(SENDING_TOOLS.search(self.text),
                          "the skill names a mail tool that sends or saves")

    def test_an_unread_thread_is_unclear_not_waiting(self) -> None:
        self.assertIn("`unclear`", self.waiting)

    def test_the_safety_rules_keep_nudges_read_only(self) -> None:
        rules = section(self.text, "## Safety rules")
        self.assertRegex(rules, r"(?i)nudge")


if __name__ == "__main__":
    unittest.main()
