"""Build runs as OTLP traces (pack sd:6943)."""
import http.server
import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from sd_db import build, telemetry
from sd_db.database import connect
from sd_db.jobs import cli
from sd_db.migrate import initialise
from sd_db.writes import create_item, record_cost, upsert_repo

REPO = "/fixture/repo"
SHA = "3d60d444699dfae13cbf9ad68a568c3172b0ab20"


class Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        initialise(self.root / "sd.db")
        self.db = connect(self.root / "sd.db")
        self.addCleanup(self.db.close)
        upsert_repo(self.db, REPO, remote="/fixture/remote", managed=1)

    def run_row(self, titles, *, outcome, detail, notes, start="2026-10-31T07:22:07+00:00",
                end="2026-10-31T09:02:06+00:00", review_round=None):
        items = [create_item(self.db, kind="task", title=title, repo=REPO, status="ready") for title in titles]
        build.queue(self.db, items, who="operator")
        run = build.claim(self.db, owner="fixture", load=1.0, load_cap=40.0, interactive=[],
                          root=self.root / "worktrees")
        assert run is not None
        ident = run["id"]
        self.db.execute("UPDATE runner_run SET created_at = ?, released_at = ?, outcome = ?, detail = ?, "
                        "review_round = ?, model = 'opus' WHERE id = ?",
                        (start, end, outcome, detail, review_round, ident))
        for stamp, body in notes:
            self.db.execute("INSERT INTO note (item, timestamp, kind, body) VALUES (?, ?, 'comment', ?)",
                            (items[0], stamp, body.format(run=ident)))
        self.db.commit()
        return ident, items

    def merged(self, review_round=None):
        return self.run_row(["Build me", "And me"], outcome="done", detail="worktree /Users/x removed",
                            review_round=review_round, notes=[
                                ("2026-10-31T07:34:11+00:00", "Build run {run} report:\nBuilt."),
                                ("2026-10-31T07:50:00+00:00", "Build run {run} report:\nFixed round 1."),
                                ("2026-10-31T08:26:35+00:00",
                                 "Build run {run} enqueued build/sd-1 in the lane as entry 20261031T082558Z-4791"),
                                ("2026-10-31T09:01:01+00:00",
                                 f"Code delivery https://github.com/o/r/pull/1722 at {SHA}")])


class Spans(Case):
    def test_a_merged_run_is_one_trace_with_its_steps(self):
        ident, items = self.merged(review_round=1)
        record_cost(self.db, source="run", role="author", repo=REPO, pass_=ident, tokens_in=100, tokens_out=7,
                    usd=1.25)
        spans = telemetry.run_spans(self.db, telemetry.ended_runs(self.db)[0])
        self.assertEqual([span["name"] for span in spans],
                         ["build_run", "claim", "build", "review_round", "enqueue", "lane", "merge"])
        self.assertEqual({span["traceId"] for span in spans}, {ident})
        root = spans[0]
        self.assertNotIn("parentSpanId", root)
        self.assertEqual({span["parentSpanId"] for span in spans[1:]}, {root["spanId"]})
        attributes = {row["key"]: row["value"] for row in root["attributes"]}
        self.assertEqual(attributes["sd.items"], {"stringValue": f"{items[0]},{items[1]}"})
        self.assertEqual(attributes["sd.item_titles"], {"stringValue": "Build me | And me"})
        self.assertEqual(attributes["sd.cost_usd"], {"doubleValue": 1.25})
        self.assertEqual(attributes["sd.tokens_in"], {"intValue": "100"})
        self.assertEqual(root["status"], {"code": 1})
        self.assertNotIn("sd.failure_class", attributes)
        merge = {row["key"]: row["value"] for row in spans[-1]["attributes"]}
        self.assertEqual((merge["sd.pr"], merge["sd.commit"]), ({"intValue": "1722"}, {"stringValue": SHA}))

    def test_ids_are_stable_so_a_second_export_repeats_the_spans(self):
        self.merged()
        first = telemetry.run_spans(self.db, telemetry.ended_runs(self.db)[0])
        again = telemetry.run_spans(self.db, telemetry.ended_runs(self.db)[0])
        self.assertEqual(first, again)
        self.assertEqual(len({span["spanId"] for span in first}), len(first))

    def test_no_detail_or_note_body_leaves_the_store(self):
        self.merged()
        text = json.dumps(telemetry.payload(telemetry.run_spans(self.db, telemetry.ended_runs(self.db)[0])))
        for secret in ("/Users/x", "Fixed round 1", "Built."):
            self.assertNotIn(secret, text)
        self.assertIn('"openinference.project.name"', text)

    def test_a_failed_run_carries_its_class_and_an_error_status(self):
        self.run_row(["Fail me"], outcome="lane_failed",
                     detail="lane entry 1 failed: merging origin/main into build/sd-1 conflicts", notes=[
                         ("2026-10-31T08:26:35+00:00", "Build run {run} enqueued build/sd-1 in the lane as entry 1")])
        spans = telemetry.run_spans(self.db, telemetry.ended_runs(self.db)[0])
        self.assertEqual(spans[0]["status"], {"code": 2, "message": "conflict"})
        self.assertEqual(spans[-1]["name"], "lane")
        self.assertEqual(spans[-1]["status"], {"code": 2, "message": "conflict"})

    def test_failure_classes(self):
        cases = {
            "supervisor lost at step reviewing: no live beat for 180 s": "lost_run",
            "a child ran past 3600 s; its group was ended": "timed_out",
            "sd-ship lane enqueue refused: The hub database did not answer: database is locked": "db_locked",
            "sd-ship lane enqueue refused: lines too long: body line 31 is 149 characters (limit 72)":
                "line_too_long",
            "git push failed (leak-guard: 1 line(s) match a pattern": "leak_guard",
            "the ship adapter owns association and delivery trailers: line 15: `Closes: sd:1`":
                "no_closes_trailer",
            "ended at step building: permission denied: Bash": "denied_tool",
            "3 review rounds left blockers: a.py:1 merge conflict handling": "review_blockers",
            "the review gave no answer twice at d67de91c0b40": "review_no_answer",
            "the repository gate failed after the review cleared": "gate_failed",
            "the builder left no commit on build/sd-1": "no_commit",
            "gh: Server Error (HTTP 502)": "other",
        }
        for detail, expected in cases.items():
            with self.subTest(detail=detail):
                self.assertEqual(telemetry.failure_class("blocked", detail), expected)
        self.assertIsNone(telemetry.failure_class("done", "anything"))
        self.assertEqual(telemetry.failure_class("cancelled", "cancelled by operator"), "cancelled")

    def test_an_open_run_is_not_exported(self):
        self.run_row(["Open"], outcome=None, detail=None, end=None, notes=[])
        self.assertEqual(telemetry.ended_runs(self.db), [])


class Export(Case):
    def test_a_missing_collector_is_a_skip(self):
        self.merged()
        with mock.patch.object(telemetry, "ENDPOINT", "http://127.0.0.1:9/v1/traces"), \
                mock.patch.object(cli, "_open_for_read", return_value=connect(self.root / "sd.db", write=False)), \
                mock.patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": ""}), \
                redirect_stdout(io.StringIO()) as out:
            code = cli.main(["telemetry", "export"])
        self.assertEqual(code, 0)
        self.assertIn("sd-db telemetry: skip: no collector at http://127.0.0.1:9/v1/traces", out.getvalue())

    def test_the_spans_reach_a_collector_as_otlp_json(self):
        ident, _ = self.merged()
        received = []

        class Collector(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, self.headers["Content-Type"],
                                 json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Collector)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        result = telemetry.export(self.db, f"http://127.0.0.1:{server.server_port}/v1/traces")
        self.assertEqual(result, {"runs": 1, "spans": 7, "skipped": None})
        path, kind, body = received[0]
        self.assertEqual((path, kind), ("/v1/traces", "application/json"))
        spans = body["resourceSpans"][0]["scopeSpans"][0]["spans"]
        self.assertEqual(spans[0]["traceId"], ident)


if __name__ == "__main__":
    unittest.main()
