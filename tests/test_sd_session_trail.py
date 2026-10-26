"""The compact hook prints the session's own trail, read back by its id (sd:6023).

Every test runs the hook as Claude Code does, a process fed the SessionStart
payload, against a real `sd_db` under a `HOME` nothing else shares: the claim
is about which rows come back, and a double would only say a query ran.
"""

from __future__ import annotations

import json
import pathlib
import subprocess  # nosec B404 - fixed argv, running the hook
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "bin" / "sd-session-trail"
sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_db  # noqa: E402 - the checkout's lib/, through tests/__init__
import sd_db.workflow as workflow  # noqa: E402
import sd_install  # noqa: E402 - bin/ is on sys.path above

from tests.clean_env import clean_environment  # noqa: E402

LIMIT = 10


class SessionTrail(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = pathlib.Path(scratch.name)
        sd_db.initialise(home=self.home)
        self.connection = sd_db.connect(sd_db.default_path(self.home), write=True)
        self.addCleanup(self.connection.close)

    def hook(self, payload: dict, home: pathlib.Path | None = None, **env: str) -> str:
        """The `additionalContext` the hook printed, or "" when it printed nothing."""
        result = subprocess.run(  # nosec B603 - fixed argv, a scratch HOME
            [sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
            env=clean_environment(HOME=str(home or self.home), **env), check=False)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        if not result.stdout:
            return ""
        printed = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(printed["hookEventName"], "SessionStart")
        return printed["additionalContext"]

    def file(self, title: str, session: str) -> int:
        return workflow.capture_task(self.connection, title=title, who="operator", session=session)["item"]["id"]

    def note(self, item: int, body: str, kind: str, session: str) -> None:
        workflow.add_item_note(self.connection, item, body=body, kind=kind, who="operator", session=session)

    def test_the_trail_is_this_sessions_filed_items_decisions_and_questions_newest_first(self):
        mine = self.file("Filed by this session", "session-a")
        self.note(mine, "Which way?\nSecond line stays out", "question", "session-a")
        self.note(mine, "A comment is not trail", "comment", "session-a")
        other = self.file("Filed by another session", "session-b")
        self.note(other, "Another session's ruling", "decision", "session-b")
        self.note(other, "This way", "decision", "session-a")
        text = self.hook({"hook_event_name": "SessionStart", "source": "compact", "session_id": "session-a"})
        lines = text.splitlines()
        self.assertIn("session session-a", lines[0])
        self.assertEqual([entry.split(" ", 2)[1] for entry in lines[1:]], ["decision", "question", "filed"])
        self.assertIn(f"sd:{other}", lines[1])
        self.assertTrue(lines[2].endswith(": Which way?"), lines[2])
        self.assertTrue(lines[3].endswith(": Filed by this session"), lines[3])
        self.assertNotIn("another session", text.lower())
        self.assertNotIn("comment", text)

    def test_the_environment_names_the_session_when_the_payload_does_not(self):
        self.file("Filed by this session", "session-a")
        self.assertIn("Filed by this session", self.hook({"source": "compact"}, CLAUDE_CODE_SESSION_ID="session-a"))
        self.assertEqual(self.hook({"source": "compact"}, CLAUDE_CODE_SESSION_ID=""), "")

    def test_a_ruling_that_keeps_the_user_shows_by_its_harness_session(self):
        """pack sd:6046: a CLI ruling records the user as `session`, the Review page's "ruled by"."""
        item = self.file("Someone else's batch", "fixture")
        workflow.add_item_note(self.connection, item, body="Ruling on note #1: Approve", kind="decision",
                               who="operator", harness_session="session-a")
        workflow.add_item_note(self.connection, item, body="Ruling on note #2: Reject", kind="decision",
                               who="operator")
        lines = self.hook({"session_id": "session-a"}).splitlines()
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(lines[1].endswith(": Ruling on note #1: Approve"), lines[1])

    def test_a_teammate_reads_its_own_marked_trail_and_the_lead_its_own(self):
        """pack sd:6046: a teammate shares its lead's session id; its notes carry `:<agent_id>`."""
        self.file("Filed by the lead", "session-a")
        self.file("Filed by a teammate", "session-a:agent-1")
        lead = self.hook({"session_id": "session-a"})
        mate = self.hook({"session_id": "session-a", "agent_id": "agent-1"})
        self.assertIn("Filed by the lead", lead)
        self.assertNotIn("Filed by a teammate", lead)
        self.assertIn("Filed by a teammate", mate)
        self.assertNotIn("Filed by the lead", mate)

    def test_the_trail_is_capped_and_says_so(self):
        item = self.file("Busy", "session-a")
        for number in range(LIMIT + 2):
            self.note(item, f"Ruling {number}", "decision", "session-a")
        lines = self.hook({"session_id": "session-a"}).splitlines()
        self.assertEqual(len(lines), 1 + LIMIT + 1)
        self.assertTrue(lines[1].endswith(f": Ruling {LIMIT + 1}"), lines[1])
        self.assertIn("Older entries not shown", lines[-1])

    def test_a_long_or_multiline_title_keeps_one_bounded_line(self):
        """pack sd:6046: a filed item's title skipped the first-line cut and the `WIDTH` bound notes get."""
        workflow.capture_task(self.connection, title="Short head", who="operator", session="session-a")
        self.connection.execute("UPDATE item SET title = ?", ("First line\nsecond line " + "x" * 400,))
        self.connection.commit()
        lines = self.hook({"session_id": "session-a"}).splitlines()
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(lines[1].endswith(": First line"), lines[1])
        self.connection.execute("UPDATE item SET title = ?", ("y" * 400,))
        self.connection.commit()
        entry = self.hook({"session_id": "session-a"}).splitlines()[1]
        self.assertTrue(entry.endswith("y" * 157 + "..."), entry)

    def test_a_session_with_no_trail_prints_nothing(self):
        self.file("Someone else's", "session-b")
        self.assertEqual(self.hook({"session_id": "session-a"}), "")

    def test_a_failed_read_is_named_not_shown_as_an_empty_trail(self):
        empty = pathlib.Path(tempfile.mkdtemp(dir=self.home))
        text = self.hook({"session_id": "session-a"}, home=empty)
        self.assertIn("could not read this session's trail", text)

    def test_garbage_input_prints_nothing(self):
        for stdin in ("", "not json", "[1, 2]"):
            result = subprocess.run(  # nosec B603 - fixed argv, a scratch HOME
                [sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True,
                env=clean_environment(HOME=str(self.home)), check=False)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_the_installer_registers_it_on_compact_only(self):
        self.assertIn(("bin/sd-session-trail", "SessionStart", ("compact",)), sd_install.HOOK_SPECS)


if __name__ == "__main__":
    unittest.main()
