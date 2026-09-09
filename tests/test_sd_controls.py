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

    def test_report_ingestion_is_replayable_and_acknowledged(self):
        log = self.home / "report.log"
        log.write_text("A completed observation.\n")
        args = (
            "reports",
            "ingest",
            "fixture",
            "--run-id",
            "one",
            "--started",
            "2026-09-08T00:00:00Z",
            "--ended",
            "2026-09-08T00:01:00Z",
            "--exit-code",
            "0",
            "--log",
            str(log),
            "--json",
        )
        first = self.cli(*args)
        self.assertEqual(first.returncode, 0, first.stderr)
        state = json.loads(first.stdout)
        again = json.loads(self.cli(*args).stdout)
        self.assertEqual(state["item"]["id"], again["item"]["id"])
        result = self.cli(
            "reports",
            "acknowledge",
            str(state["item"]["id"]),
            "--if-revision",
            state["revision"],
            "--json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["item"]["status"], "done")
        self.assertEqual(
            len(json.loads(self.cli("reports", "list", "--json").stdout)), 1
        )


if __name__ == "__main__":
    unittest.main()
