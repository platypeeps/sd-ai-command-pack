"""Provider/report CLI round trips through the same shared domain as HTTP."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sd_db import initialise

ROOT = Path(__file__).resolve().parents[1]
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


if __name__ == "__main__":
    unittest.main()
