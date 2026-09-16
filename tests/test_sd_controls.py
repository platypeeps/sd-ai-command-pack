"""Provider/report CLI round trips through the same shared domain as HTTP."""

import argparse
import contextlib
import getpass
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sd_db import initialise

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import sd_controls  # noqa: E402
import sd_work  # noqa: E402

PROVIDERS = """bills:
  a: {cost: subscription}
  b: {cost: subscription}
providers:
  claude: {start: "claude -p", vendor: anthropic, bill: a, roles: [author, reviewer], reader: claude-json}
  codex: {start: "codex exec", vendor: openai, bill: b, roles: [author, reviewer], reader: codex-json}
roles:
  author: [claude, codex]
  reviewer: [codex, claude]
"""


class Controls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        initialise(home=self.home)
        (self.home / ".local/share/sd/providers.yaml").write_text(PROVIDERS)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "bin/sd"), *args],
            env={**os.environ, "HOME": str(self.home)},
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )

    def test_provider_complete_proposal_and_invalid_disable(self):
        result = self.cli("providers", "list", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(result.stdout)
        proposal = self.home / "proposal.json"
        payload = {
            "revision": state["revision"],
            "enabled": {"claude": True, "codex": False},
            "orders": state["orders"],
        }
        proposal.write_text(json.dumps(payload))
        refused = self.cli("providers", "configure", "--file", str(proposal), "--json")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("first in both", refused.stderr)
        self.assertEqual(
            json.loads(self.cli("providers", "list", "--json").stdout), state
        )
        proposal.write_text("[]")
        refused = self.cli("providers", "configure", "--file", str(proposal))
        self.assertEqual(refused.returncode, 1)
        self.assertNotIn("Traceback", refused.stderr)

    def ingest(self, run_id, exit_code, text):
        log = self.home / f"{run_id}.log"
        log.write_text(text)
        return (
            "reports",
            "ingest",
            "fixture",
            "--run-id",
            run_id,
            "--started",
            "2026-09-08T00:00:00Z",
            "--ended",
            "2026-09-08T00:01:00Z",
            "--exit-code",
            str(exit_code),
            "--log",
            str(log),
            "--json",
        )

    def reports(self):
        listed = self.cli("reports", "list", "--json")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        return json.loads(listed.stdout)

    def test_report_ingestion_is_replayable_and_acknowledged(self):
        # A clean tick is not an event: the library records a heartbeat and
        # files no report (system sd:739), and replaying the same run records
        # nothing more.
        quiet = self.ingest("quiet", 0, "A completed observation.\n")
        clean = self.cli(*quiet)
        self.assertEqual(clean.returncode, 0, clean.stderr)
        beat = json.loads(clean.stdout)
        self.assertEqual(beat["recorded"], "heartbeat")
        self.assertNotIn("item", beat)
        replay = self.cli(*quiet)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        replayed = json.loads(replay.stdout)
        self.assertEqual(replayed["recorded"], "nothing")
        self.assertNotIn("item", replayed)
        self.assertEqual(self.reports(), [])

        # A tick with findings is the one that files a report, so it is the one
        # the acknowledge verb has to be proved against.
        findings = self.ingest(
            "findings", 0, "Observed drift.\nSD_REPORT_ATTENTION: two stale rows\n"
        )
        first = self.cli(*findings)
        self.assertEqual(first.returncode, 0, first.stderr)
        state = json.loads(first.stdout)
        self.assertEqual(state["recorded"], "report")
        self.assertEqual(state["item"]["kind"], "report")
        self.assertIs(json.loads(state["item"]["fields"])["attention"], True)
        replay = self.cli(*findings)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        again = json.loads(replay.stdout)
        self.assertEqual(state["item"]["id"], again["item"]["id"])
        report = str(state["item"]["id"])

        # Its followup is open, so acknowledging it now is refused and changes
        # nothing.
        refused = self.cli(
            "reports", "acknowledge", report, "--if-revision", state["revision"], "--json"
        )
        self.assertEqual(refused.returncode, 1)
        self.assertIn("resolve the report's followups", refused.stderr)
        self.assertNotIn("Traceback", refused.stderr)
        [followup] = [note for note in state["notes"] if note["kind"] == "followup"]
        resolved = self.cli(
            "task", "resolve", str(followup["id"]), "--if-revision", state["revision"], "--json"
        )
        self.assertEqual(resolved.returncode, 0, resolved.stderr)

        result = self.cli(
            "reports",
            "acknowledge",
            report,
            "--if-revision",
            json.loads(resolved.stdout)["revision"],
            "--json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["item"]["status"], "done")
        self.assertEqual([row["id"] for row in self.reports()], [state["item"]["id"]])

    def failed_run(self):
        """One failed run as the ingest files it: a report born with the ingest's own followup."""
        failed = self.cli(*self.ingest("failed", 1, "boom\n"))
        self.assertEqual(failed.returncode, 0, failed.stderr)
        state = json.loads(failed.stdout)
        [followup] = [note for note in state["notes"] if note["kind"] == "followup"]
        self.assertEqual((followup["session"], followup["resolved_at"]), ("cron", None))
        return str(state["item"]["id"]), state["revision"], followup["id"]

    def followups(self, report):
        shown = self.cli("store", "item", report, "--json")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        state = json.loads(shown.stdout)
        return state["item"]["status"], [(note["id"], note["session"], note["resolved_at"] is not None)
                                         for note in state["notes"] if note["kind"] == "followup"]

    def test_the_flag_resolves_the_ingests_own_followup_and_is_off_by_default(self):
        # Every failure report is born with the followup the ingest wrote, so
        # without the flag the verb refuses it and names the note (sd:941).
        report, revision, note = self.failed_run()
        refused = self.cli("reports", "acknowledge", report, "--if-revision", revision, "--json")
        self.assertEqual(refused.returncode, 1)
        self.assertIn(
            f"resolve the report's followups before acknowledging it: sd note resolve {note}",
            refused.stderr,
        )
        self.assertNotIn("Traceback", refused.stderr)
        self.assertEqual(self.followups(report), ("planning", [(note, "cron", False)]))

        # With the flag, one call resolves that note and finishes the report,
        # and the status note says which note it resolved.
        result = self.cli(
            "reports", "acknowledge", report, "--if-revision", revision, "--resolve-ingest-followups", "--json"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(result.stdout)
        self.assertEqual(state["item"]["status"], "done")
        self.assertEqual(self.followups(report), ("done", [(note, "cron", True)]))
        self.assertIn(
            f"planning -> done by {getpass.getuser()}: resolved the ingest's followup {note}",
            [entry["body"] for entry in state["notes"] if entry["kind"] == "status_change"],
        )

    def test_a_followup_a_person_wrote_still_blocks_with_the_flag_on(self):
        report, revision, cron = self.failed_run()
        noted = self.cli(
            "task", "note", report, "--kind", "followup", "--body", "check the disk too",
            "--if-revision", revision, "--json",
        )
        self.assertEqual(noted.returncode, 0, noted.stderr)
        owed = json.loads(noted.stdout)["note"]["id"]
        refused = self.cli("reports", "acknowledge", report, "--resolve-ingest-followups", "--json")
        self.assertEqual(refused.returncode, 1)
        self.assertIn(f"sd note resolve {owed}", refused.stderr)
        self.assertNotIn(f"sd note resolve {cron}", refused.stderr)
        self.assertNotIn("Traceback", refused.stderr)
        status, notes = self.followups(report)
        self.assertEqual(status, "planning")
        self.assertEqual(sorted(notes), sorted([(cron, "cron", False), (owed, getpass.getuser(), False)]))

    def test_the_flag_refuses_a_library_without_the_keyword_naming_the_provisioner(self):
        # A library that predates system #394 takes no
        # `resolve_ingest_followups`; the flag must not reach it as a
        # TypeError. The verb runs in-process here so the library function can
        # be replaced by one with the old signature.
        report, revision, note = self.failed_run()

        def old_acknowledge(connection, item, *, expected_revision, who):
            raise AssertionError("the old library must not be called with the flag on")

        args = argparse.Namespace(
            control_group="reports", control_action="acknowledge", item=int(report),
            if_revision=revision, resolve_ingest_followups=True, json=True,
        )
        from sd_db import reporting

        with patch.dict(os.environ, {"HOME": str(self.home)}), \
                patch.object(reporting, "acknowledge", old_acknowledge), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(sd_work.WorkRefusal) as raised:
                sd_controls.run(args)
        self.assertEqual(
            str(raised.exception),
            "the installed sd_db takes no --resolve-ingest-followups; "
            "run bin/sd_install.py --provision-library",
        )
        self.assertEqual(self.followups(report), ("planning", [(note, "cron", False)]))


if __name__ == "__main__":
    unittest.main()
