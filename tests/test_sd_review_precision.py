"""`sd providers precision`: each reviewer's findings by outcome, read from ship receipts (sd:1832, sd:1788)."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sd_db import initialise

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

from sd_ship_dispositions import digest  # noqa: E402


def finding(backend, severity, summary, disposition="blocking"):
    return {"backend": backend, "severity": severity, "family": "correctness", "disposition": disposition,
            "path": "bin/x.py", "line": 1, "summary": summary}


def run(head, *findings, started="2026-10-01T00:00:00+00:00"):
    return {"head": head, "started_at": started, "report": {"findings": list(findings)}}


class Precision(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        initialise(home=self.home)
        self.database = self.home / ".local/share/sd/sd.db"

    def put(self, key, body):
        with sqlite3.connect(self.database) as connection:
            connection.execute("INSERT INTO state(kind,key,timestamp,body) VALUES ('checkpoint',?,?,?)",
                               (key, "2026-10-01T00:00:00+00:00", json.dumps({**body, "protocol": 1})))

    def adjudicate(self, key, *decisions):
        self.put(key, {"decision": "accepted", "proposal": {"findings": [
            {"finding_digest": digest(raw), "response_disposition": verdict, "reason": f"{verdict} because"}
            for raw, verdict in decisions]}})

    def cli(self, *args):
        result = subprocess.run([sys.executable, str(ROOT / "bin/sd"), "providers", "precision", *args],
                                env={**os.environ, "HOME": str(self.home)}, capture_output=True, text=True,
                                check=False, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def report(self, *args):
        return json.loads(self.cli("--json", *args))

    def outcomes(self, *args):
        return {row["summary"]: row["outcome"] for row in self.report(*args)["findings"]}

    def test_each_outcome_is_read_from_the_receipt_and_its_adjudication(self):
        fixed, parked, rebutted = finding("codex", "high", "fixed"), finding("codex", "high", "parked"), \
            finding("codex", "high", "rebutted")
        replaced, last = finding("minimax", "high", "replaced"), finding("minimax", "medium", "last")
        self.put("ship:a", {"repository": "o/r", "item": 7, "branch": "b", "pull_request": {"number": 12},
                            "passes": [run("h1", fixed, finding("codex", "low", "advisory", "advisory")),
                                       run("h2", replaced), run("h2", parked, rebutted, last)]})
        self.adjudicate("ship-adjudication:a", (parked, "parked"), (rebutted, "rebutted"))
        self.assertEqual(self.outcomes(), {"fixed": "fixed", "advisory": "advisory", "replaced": "undecided",
                                           "parked": "parked", "rebutted": "rebutted", "last": "undecided"})
        row = next(row for row in self.report()["findings"] if row["summary"] == "rebutted")
        self.assertEqual((row["provider"], row["pull_request"], row["item"], row["reason"], row["receipt"]),
                         ("codex", 12, 7, "rebutted because", "ship:a"))

    def test_no_item_records_read_their_own_adjudication_key(self):
        rebutted = finding("kimi", "medium", "no-item rebutted")
        self.put("ship-review-no-item:n", {"repository": "o/r", "review_id": "r1", "passes": [run("h1", rebutted)]})
        self.adjudicate("ship-adjudication-no-item:n", (rebutted, "rebutted"))
        # The same suffix under the item prefix is another receipt's adjudication.
        self.adjudicate("ship-adjudication:n", (rebutted, "parked"))
        # Only an accepted adjudication decides.
        self.put("ship-adjudication-no-item:n", {"decision": "proposed", "proposal": {"findings": [
            {"finding_digest": digest(rebutted), "response_disposition": "parked", "reason": "unaccepted"}]}})
        self.assertEqual(self.outcomes(), {"no-item rebutted": "rebutted"})

    def test_newest_receipt_revision_counts_with_set_aside_passes_and_without_imported_ones(self):
        self.put("ship:a", {"passes": [run("h0", finding("codex", "high", "stale revision"))]})
        self.put("ship:a", {"passes": [run("h3", finding("codex", "high", "current"))],
                            "superseded_reviews": [{"passes": [run("h1", finding("codex", "high", "set aside"))]}]})
        self.put("ship-review-no-item:n", {"historical_passes": [run("h1", finding("codex", "high", "imported"))],
                                           "passes": []})
        self.assertEqual(self.outcomes(), {"set aside": "fixed", "current": "undecided"})

    def test_precision_is_held_over_decided_per_provider_and_severity(self):
        raised = [finding("minimax", "high", name) for name in ("f", "p", "r1", "r2", "u")]
        self.put("ship:a", {"passes": [run("h1", raised[0]), run("h2", *raised[1:]),
                                       run("h2", finding("minimax", "low", "a", "advisory"))]})
        self.adjudicate("ship-adjudication:a", (raised[1], "parked"), (raised[2], "rebutted"), (raised[3], "rebutted"))
        table = {(row["provider"], row["severity"]): row for row in self.report()["summary"]}
        self.assertEqual(list(table), [("minimax", "high"), ("minimax", "low"), ("minimax", "all")])
        self.assertEqual({name: table["minimax", "high"][name] for name in
                          ("raised", "fixed", "parked", "rebutted", "undecided", "advisory", "precision")},
                         {"raised": 5, "fixed": 1, "parked": 1, "rebutted": 2, "undecided": 1, "advisory": 0,
                          "precision": 0.5})
        self.assertIsNone(table["minimax", "low"]["precision"])
        self.assertEqual((table["minimax", "all"]["raised"], table["minimax", "all"]["precision"]), (6, 0.5))
        text = self.cli()
        self.assertIn("6 finding(s) in 1 ship receipt(s)", text)
        self.assertRegex(text, r"minimax\s+high\s+5\s+1\s+1\s+2\s+1\s+0\s+50%")

    def test_repository_and_since_select_rows_before_the_summary(self):
        self.put("ship:a", {"repository": "o/a", "passes": [run("h1", finding("codex", "high", "old"))]})
        self.put("ship:b", {"repository": "o/b", "passes": [
            run("h1", finding("codex", "high", "new"), started="2026-10-05T00:00:00+00:00")]})
        self.assertEqual(self.outcomes("--repository", "o/a"), {"old": "undecided"})
        self.assertEqual(self.outcomes("--since", "2026-10-02"), {"new": "undecided"})
        self.assertEqual(self.report("--since", "2026-10-02")["summary"][0]["raised"], 1)


if __name__ == "__main__":
    unittest.main()
