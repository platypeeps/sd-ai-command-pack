"""Pull requests that need the operator, filed as report alerts after a shadow sync (sd:6712)."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sd_db import connect, initialise, pr_attention
from sd_db.shadow_sync import _sync
from sd_db.writes import add_note, resolve_note

NOW = datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc)


def pull(number, *, decision=None, mergeable="MERGEABLE", rollup="SUCCESS", repo="example/widget"):
    return {"url": f"https://github.com/{repo}/pull/{number}", "number": number, "title": f"Pull {number}",
            "repository": {"nameWithOwner": repo}, "reviewDecision": decision, "mergeable": mergeable,
            "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": rollup} if rollup else None}}]}}


class Gh:
    """`gh`: the two attention searches answer `author` and `requested`; every other search answers nothing."""

    def __init__(self, author=(), requested=(), fail=None, count=None):
        self.author, self.requested, self.fail, self.count = list(author), list(requested), fail, count

    def __call__(self, argv):
        if argv[:2] == ["gh", "auth"]:
            return 0, "", ""
        query = next(value[2:] for value in argv if value.startswith("q="))
        nodes = self.author if "author:@me" in query and "is:pr is:open" in query else \
            self.requested if "user-review-requested:@me" in query else []
        if self.fail and nodes is self.requested:
            return 1, "", self.fail
        block = {"issueCount": self.count or len(nodes), "pageInfo": {"hasNextPage": False, "endCursor": None},
                 "nodes": nodes}
        return 0, json.dumps({"data": {"search": block}}), ""


class Alerts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        initialise(Path(self.tmp.name) / "sd.db")
        self.db = connect(Path(self.tmp.name) / "sd.db")
        self.addCleanup(self.db.close)

    def run_(self, gh, now=NOW):
        found, complete, reason = pr_attention.read(gh)
        return pr_attention.alert(self.db, found, complete, now=now), reason

    def reports(self):
        rows = self.db.execute("SELECT title, status, fields FROM item WHERE kind = 'report' ORDER BY id").fetchall()
        return [(row["title"], row["status"], json.loads(row["fields"])["report"]["attention_basis"]) for row in rows]

    def test_a_review_request_alerts_once_and_its_clearing_acknowledges_it(self):
        url = "https://github.com/example/widget/pull/7"
        done, _ = self.run_(Gh(requested=[pull(7)]))
        self.assertEqual(done["filed"], [f"review_requested {url}"])
        self.assertEqual(self.reports(), [("pr-attention: example/widget#7: review requested of you", "planning",
                                           f"review_requested {url}")])
        done, _ = self.run_(Gh(requested=[pull(7)]))
        self.assertEqual((done["filed"], done["cleared"]), ([], []))
        self.assertEqual(len(self.reports()), 1)
        done, _ = self.run_(Gh())
        self.assertEqual(done["cleared"], [f"review_requested {url}"])
        self.assertEqual(self.reports()[0][1], "done")

    def test_a_cleared_state_keeps_an_alert_with_an_operator_followup_open(self):
        url = "https://github.com/example/widget/pull/7"
        self.run_(Gh(author=[pull(7, rollup="FAILURE")]))
        item = self.db.execute("SELECT id FROM item WHERE kind = 'report'").fetchone()["id"]
        mine = add_note(self.db, item, "followup", "find why checks flake", session="operator")
        done, _ = self.run_(Gh())
        self.assertEqual(done["cleared"], [], "checks turning green is not the operator's work done")
        self.assertEqual(self.reports()[0][1], "planning")
        open_ = {row["id"]: row["session"] for row in self.db.execute(
            "SELECT id, session FROM note WHERE item = ? AND kind = 'followup' AND resolved_at IS NULL", (item,))}
        self.assertEqual(open_, {mine: "operator"}, "the alert's own followup closes; the operator's stays open")
        resolve_note(self.db, mine)
        done, _ = self.run_(Gh())
        self.assertEqual(done["cleared"], [f"checks_failing {url}"])
        self.assertEqual(self.reports()[0][1], "done")

    def test_a_scheduled_agents_cron_followup_survives_a_cleared_state(self):
        """Session `cron` alone is no proof ingest wrote a followup: its text must match too, as reporting.py rules."""
        url = "https://github.com/example/widget/pull/7"
        self.run_(Gh(author=[pull(7, rollup="FAILURE")]))
        item = self.db.execute("SELECT id FROM item WHERE kind = 'report'").fetchone()["id"]
        agents = add_note(self.db, item, "followup", "rerun the flaky check by hand", session="cron")
        done, _ = self.run_(Gh())
        self.assertEqual(done["cleared"], [])
        self.assertEqual(self.reports()[0][1], "planning")
        open_ = [row["id"] for row in self.db.execute(
            "SELECT id FROM note WHERE item = ? AND kind = 'followup' AND resolved_at IS NULL", (item,))]
        self.assertEqual(open_, [agents], "the alert's own followup closes; the scheduled agent's stays open")
        resolve_note(self.db, agents)
        done, _ = self.run_(Gh())
        self.assertEqual(done["cleared"], [f"checks_failing {url}"])

    def test_an_acknowledged_state_that_persists_files_nothing_new(self):
        self.run_(Gh(author=[pull(3, rollup="FAILURE")]))
        self.db.execute("UPDATE item SET status = 'done' WHERE kind = 'report'")
        done, _ = self.run_(Gh(author=[pull(3, rollup="FAILURE")]))
        self.assertEqual(done["filed"], [])
        done, _ = self.run_(Gh())
        done, _ = self.run_(Gh(author=[pull(3, rollup="FAILURE")]))
        self.assertEqual(len(done["filed"]), 1, "a state that cleared and came back is new")

    def test_your_pulls_light_by_review_checks_and_mergeability(self):
        cases = {1: pull(1, decision="CHANGES_REQUESTED"), 2: pull(2, rollup="ERROR"), 3: pull(3, mergeable="CONFLICTING"),
                 4: pull(4, decision="APPROVED"), 5: pull(5, decision="APPROVED", rollup=None),
                 6: pull(6, decision="APPROVED", rollup="PENDING"), 7: pull(7, decision="REVIEW_REQUIRED"),
                 8: pull(8, decision="APPROVED", mergeable="UNKNOWN")}
        self.assertEqual({n: pr_attention.states(node, "author") for n, node in cases.items()}, {
            1: ["changes_requested"], 2: ["checks_failing"], 3: ["conflict"], 4: ["ready"], 5: ["ready"],
            6: [], 7: [], 8: []})

    def test_a_failed_or_cut_read_files_what_it_read_and_clears_nothing(self):
        self.run_(Gh(requested=[pull(7)]))
        done, reason = self.run_(Gh(author=[pull(4, decision="APPROVED")], fail="HTTP 502"))
        self.assertEqual((len(done["filed"]), done["cleared"]), (1, []))
        self.assertEqual(reason, "requested: HTTP 502")
        done, reason = self.run_(Gh(author=[pull(4, decision="APPROVED")], count=150))
        self.assertEqual((done["filed"], done["cleared"]), ([], []))
        self.assertIn("more than 100 open pulls", reason)
        self.assertEqual([status for _, status, _ in self.reports()], ["planning", "planning"])

    def test_a_malformed_search_is_cut_and_keeps_every_alert(self):
        """A search block or node of the wrong shape is no read: it neither raises nor clears an open alert."""
        self.run_(Gh(requested=[pull(7)]))
        bad_nodes = [{**pull(4), "repository": "example/widget"}, {**pull(4), "commits": []},
                     {**pull(4), "commits": {"nodes": [None, "x"]}}, {**pull(4), "url": 4}, {"number": 4}, "x"]
        blocks = [{}, {"issueCount": 0}, {"nodes": []}, {"issueCount": "1", "nodes": []},
                  {"issueCount": True, "nodes": []}, {"issueCount": 0, "nodes": {}},
                  *({"issueCount": 1, "nodes": [node]} for node in bad_nodes)]
        for block in blocks:
            with self.subTest(block=block):
                def gh(argv, block=block):
                    return 0, json.dumps({"data": {"search": block}}), ""
                done, reason = self.run_(gh)
                self.assertEqual(done["cleared"], [])
                self.assertIn("malformed", reason)
        self.assertEqual([status for _, status, _ in self.reports()], ["planning"])

    def test_a_node_missing_a_queried_field_is_no_evidence_a_state_cleared(self):
        """Absence is not null: a node short of a field the query asks for clears no alert (sd:6712)."""
        self.run_(Gh(author=[pull(7, rollup="FAILURE", mergeable="CONFLICTING")]))
        url = "https://github.com/example/widget/pull/7"
        bare = pull(7)
        shorts = [{"url": url}, *({k: v for k, v in bare.items() if k != key} for key in bare if key != "url"),
                  {**bare, "repository": {}}, {**bare, "commits": {}}, {**bare, "commits": {"nodes": []}},
                  {**bare, "commits": {"nodes": [None]}}, {**bare, "commits": {"nodes": [{}]}},
                  {**bare, "commits": {"nodes": [{"commit": {}}]}},
                  {**bare, "commits": {"nodes": [{"commit": {"statusCheckRollup": {}}}]}},
                  {**bare, "repository": None}, {**bare, "mergeable": None}, {**bare, "commits": None}]
        for node in shorts:
            with self.subTest(node=node):
                done, reason = self.run_(Gh(author=[node]))
                self.assertEqual(done["cleared"], [])
                self.assertIn("malformed", reason)
        self.assertEqual([status for _, status, _ in self.reports()], ["planning", "planning"])
        done, reason = self.run_(Gh(author=[pull(7, rollup=None)]))
        self.assertEqual((sorted(done["cleared"]), reason), ([f"checks_failing {url}", f"conflict {url}"], ""),
                         "a present commit with no rollup is a read: its checks cleared")

    def test_the_sync_reports_its_alerts_and_an_alert_failure_never_fails_it(self):
        result = _sync(self.db, now=NOW, runner=Gh(requested=[pull(7)]), alerts=True)
        self.assertTrue(result.ok, result.reason)
        self.assertIn("shadow sync: pull request alerts: 1 filed, 0 cleared, 1 state(s) open", result.report())
        quiet = _sync(self.db, now=NOW, runner=Gh(requested=[pull(7)]))
        self.assertEqual(quiet.attention, [], "a run that does not ask files nothing")
        self.db.execute("CREATE TRIGGER refuse BEFORE INSERT ON state WHEN NEW.key = 'pr-attention:seen' "
                        "BEGIN SELECT RAISE(ABORT, 'disk full'); END")
        result = _sync(self.db, now=NOW, runner=Gh(requested=[pull(8)]), alerts=True)
        self.assertTrue(result.ok, result.reason)
        self.assertEqual(result.attention, ["pull request alerts not filed: disk full"])


if __name__ == "__main__":
    unittest.main()
