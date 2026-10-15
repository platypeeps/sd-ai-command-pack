"""Replaying a cron report is a no-op on every path (sd:757).

`reporting._beat` promised that, and two replays broke it. A recovery tick
answered `nothing` the second time, because its own first heartbeat had already
made the job read healthy. An older run replayed after newer ticks appended its
heartbeat last, so `health` read the older tick as the current one, and the next
clean tick filed a recovery that never happened.
"""
import json
import tempfile
import unittest
from unittest import mock
from datetime import UTC, datetime
from pathlib import Path

from sd_db import reporting, retention, workflow
from sd_db.database import connect
from sd_db.migrate import initialise


#: The clock every tick here reads, injected: after every fixture stamp below
#: except the ones that are deliberately in the future.
NOW = datetime(2026, 9, 8, 1, 0, tzinfo=UTC)


class AReplayWritesNothing(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / "sd.db"; initialise(self.path)
        self.db = connect(self.path); self.addCleanup(self.db.close)

    def tick(self, run, minute, *, second=0, exit_code=0, text="ok\n", ended=None):
        """One run with its own log, so a replay reads exactly what the run did."""
        log = self.root / f"{run}.log"
        if not log.exists():
            log.write_text(text)
        return reporting.ingest_log(
            self.db, job="probe", run_id=run, started="2026-09-08T00:00:00Z",
            ended=ended or f"2026-09-08T00:{minute:02d}:{second:02d}Z", exit_code=exit_code,
            log_path=log, now=NOW)

    def items(self):
        return [row["id"] for row in self.db.execute("SELECT id FROM item WHERE kind='report' ORDER BY id")]

    def beats(self):
        return [json.loads(row["body"])["run_id"] for row in self.db.execute(
            "SELECT body FROM state WHERE kind='heartbeat' AND key=? ORDER BY id",
            (reporting.HEARTBEAT_KEY + "probe",))]

    def dump(self):
        return tuple(self.db.iterdump())

    def test_replaying_a_recovery_writes_nothing(self):
        self.tick("a", 1, exit_code=1, text="boom\n")
        first = self.tick("b", 16)
        self.assertEqual((first["recorded"], first["why"]), ("heartbeat", "the job recovered"))
        before = self.dump()
        again = self.tick("b", 16)
        self.assertEqual(again["recorded"], "nothing")
        self.assertEqual(before, self.dump())

    def test_replaying_a_recovery_report_an_older_version_filed_returns_it(self):
        """Before sd:3509 a recovery filed a clean report; its replay still answers with it."""
        self.tick("a", 1, exit_code=1, text="boom\n")
        self.tick("b", 16)
        old = reporting.ingest(self.db, job="probe", run_id="b", started="2026-09-08T00:00:00Z",
                               ended="2026-09-08T00:16:00Z", exit_code=0, text="ok\n",
                               source_path=str((self.root / "b.log").resolve()),
                               attention_basis="not supplied by the job")
        before = self.dump()
        again = self.tick("b", 16)
        self.assertEqual((again["recorded"], again["why"]), ("report", "the job recovered"))
        self.assertEqual(again["item"]["id"], old["item"]["id"])
        self.assertEqual(before, self.dump())

    def test_replaying_an_older_run_leaves_current_health_alone(self):
        failed = self.tick("a", 1, exit_code=1, text="boom\n")
        self.tick("b", 16)
        self.assertEqual(self.tick("c", 31)["recorded"], "heartbeat")
        before = self.dump()
        again = self.tick("a", 1, exit_code=1, text="boom\n")
        self.assertEqual(again["recorded"], "report")
        self.assertEqual(again["item"]["id"], failed["item"]["id"])
        self.assertEqual(before, self.dump())
        self.assertIs(reporting.health(self.db, "probe"), True)
        self.assertEqual(self.beats(), ["a", "b", "c"])
        # And the job is still quiet: no recovery from a failure that is not current.
        reports = self.items()
        self.assertEqual(self.tick("d", 46)["recorded"], "heartbeat")
        self.assertEqual(self.items(), reports)

    def test_a_replay_after_compaction_still_writes_nothing(self):
        """Retention keeps one heartbeat per key, so the replayed run's own row
        may be gone; the run is still older than the tick that replaced it."""
        self.tick("a", 1)
        self.tick("b", 16)
        retention.compact_heartbeats(self.db)
        self.assertEqual(self.beats(), ["b"])
        before = self.dump()
        self.assertEqual(self.tick("a", 1)["recorded"], "nothing")
        self.assertEqual(before, self.dump())

    def test_a_replay_of_the_older_of_two_same_second_runs_writes_nothing(self):
        """The run-id guard reads every row, not only the newest.

        Two runs of one job can end in the same second, and `stamp` keeps whole
        seconds, so the `ended` guard cannot tell the older one from the newer:
        only the older run's own heartbeat row says it was already recorded.
        """
        failed = self.tick("a", 1, second=5, exit_code=1, text="boom\n")
        self.assertEqual(self.tick("c", 1, second=5)["why"], "the job recovered")
        before = self.dump()
        again = self.tick("a", 1, second=5, exit_code=1, text="boom\n")
        self.assertEqual((again["recorded"], again["item"]["id"]), ("report", failed["item"]["id"]))
        self.assertEqual(before, self.dump())
        self.assertEqual(self.beats(), ["a", "c"])
        self.assertIs(reporting.health(self.db, "probe"), True)

    def test_a_replay_of_a_same_second_run_after_compaction_is_not_a_recovery(self):
        """The #326 review: compaction took the older run's own row, and its `ended`
        ties the newest, so only the newest row's `same_second` can say it was seen."""
        self.tick("a", 1, second=5)
        failed = self.tick("c", 1, second=5, exit_code=1, text="boom\n")
        self.assertEqual(failed["recorded"], "report")
        self.assertEqual(retention.compact_heartbeats(self.db), 1)
        self.assertEqual(self.beats(), ["c"])
        reports = self.items()
        before = self.dump()
        again = self.tick("a", 1, second=5)
        self.assertEqual(again["recorded"], "nothing")
        self.assertEqual(again["why"], "a replay of a run whose heartbeat is already recorded, so nothing was written")
        self.assertEqual(self.items(), reports)
        self.assertEqual(before, self.dump())
        self.assertIs(reporting.health(self.db, "probe"), False)

    def test_a_replayed_same_second_failure_after_compaction_leaves_health_alone(self):
        failed = self.tick("a", 1, second=5, exit_code=1, text="boom\n")
        self.assertEqual(self.tick("c", 1, second=5)["why"], "the job recovered")
        retention.compact_heartbeats(self.db)
        before = self.dump()
        again = self.tick("a", 1, second=5, exit_code=1, text="boom\n")
        self.assertEqual((again["recorded"], again["item"]["id"]), ("report", failed["item"]["id"]))
        self.assertEqual(before, self.dump())
        self.assertIs(reporting.health(self.db, "probe"), True)

    def test_a_new_run_in_the_same_second_is_still_ordered_by_arrival(self):
        """Two first arrivals in one second: the later one is the newer tick, and it says so."""
        self.tick("a", 1, second=5)
        tied = self.tick("b", 1, second=5)
        self.assertEqual(tied["recorded"], "heartbeat")
        self.assertIn("same second", tied["why"])
        self.assertEqual(self.beats(), ["a", "b"])

    def test_the_runs_one_second_remembers_are_bounded(self):
        for number in range(reporting.REMEMBERED_RUNS + 5):
            self.tick(f"r{number:02d}", 1, second=5)
        retention.compact_heartbeats(self.db)
        body = json.loads(self.db.execute("SELECT body FROM state WHERE kind='heartbeat' AND key=?",
                                          (reporting.HEARTBEAT_KEY + "probe",)).fetchone()["body"])
        self.assertEqual(body["run_id"], "r24")
        self.assertEqual(body["same_second"], [f"r{number:02d}" for number in range(4, 24)])
        self.assertEqual(self.tick("r04", 1, second=5)["recorded"], "nothing")

    def test_an_older_clean_run_is_not_a_recovery_from_a_newer_failure(self):
        self.tick("a", 1)
        self.tick("b", 16, exit_code=1, text="boom\n")
        retention.compact_heartbeats(self.db)
        reports = self.items()
        before = self.dump()
        self.assertEqual(self.tick("a", 1)["recorded"], "nothing")
        self.assertEqual(self.items(), reports)
        self.assertEqual(before, self.dump())
        self.assertIs(reporting.health(self.db, "probe"), False)

    def test_a_late_clean_run_says_why_it_wrote_no_heartbeat(self):
        """Not "the last tick was also clean": the last tick failed."""
        self.tick("b", 16, exit_code=1, text="boom\n")
        late = self.tick("a", 1)
        self.assertEqual(late["recorded"], "nothing")
        self.assertEqual(late["why"], "an older run than the job's newest recorded tick, so no heartbeat was written")
        self.assertIs(reporting.health(self.db, "probe"), False)

    def test_a_future_stamp_does_not_freeze_health(self):
        """One heartbeat stamped past the clock would otherwise outrank every real
        tick until the clock caught up: no heartbeat written, no recovery filed."""
        self.tick("typo", 0, ended="2027-09-08T00:01:00Z")
        failed = self.tick("b", 16, exit_code=1, text="boom\n")
        self.assertEqual(failed["recorded"], "report")
        self.assertIs(reporting.health(self.db, "probe"), False)
        recovered = self.tick("c", 31)
        self.assertEqual((recovered["recorded"], recovered["why"]), ("heartbeat", "the job recovered"))
        self.assertIs(reporting.health(self.db, "probe"), True)
        self.assertEqual(self.beats(), ["typo", "b", "c"])

    def test_a_stamp_within_the_allowance_still_counts_as_newest(self):
        """Five minutes past the clock is a slewing clock, not a typo: it still wins."""
        self.tick("ahead", 0, ended="2026-09-08T01:04:59Z")
        self.assertEqual(self.tick("b", 16, exit_code=1, text="boom\n")["recorded"], "report")
        self.assertIs(reporting.health(self.db, "probe"), True)
        self.assertEqual(self.beats(), ["ahead"])
        self.tick("beyond", 0, ended="2026-09-08T01:30:00Z")
        self.assertEqual(self.beats(), ["ahead", "beyond"])
        # The second `exit 1` folds into b's open report (sd:920); its
        # heartbeat is still this tick's own, and it still makes the job unhealthy.
        self.assertEqual(self.tick("c", 31, exit_code=1, text="boom\n")["recorded"], "folded")
        self.assertIs(reporting.health(self.db, "probe"), False)

    def test_a_late_failure_is_still_filed_but_does_not_become_current_health(self):
        """A run whose ingest never landed, recovered by hand after newer ticks:
        the failure is an event and gets its report, but it is not the last tick."""
        self.tick("b", 16)
        late = self.tick("a", 1, exit_code=1, text="boom\n")
        self.assertEqual(late["recorded"], "report")
        self.assertIs(reporting.health(self.db, "probe"), True)
        self.assertEqual(self.beats(), ["b"])
        self.assertEqual(self.tick("c", 31)["recorded"], "heartbeat")

    def test_the_shapes_a_replay_already_had_are_kept(self):
        quiet = self.tick("a", 1)
        self.assertEqual(quiet["recorded"], "heartbeat")
        self.assertEqual(self.tick("a", 1)["recorded"], "nothing")
        failed = self.tick("b", 16, exit_code=1, text="boom\n")
        before = self.dump()
        again = self.tick("b", 16, exit_code=1, text="boom\n")
        self.assertEqual((again["recorded"], again["item"]["id"]), ("report", failed["item"]["id"]))
        self.assertEqual(before, self.dump())

    def test_a_replayed_clean_run_whose_log_now_declares_a_finding_files_nothing(self):
        """The #315 review: the run id is the key. A clean run was recorded as a
        heartbeat, so its replay files no report, even when the log it reads has
        grown a later `SD_REPORT_ATTENTION` line or the exit code differs."""
        self.tick("a", 1)
        (self.root / "a.log").write_text("ok\nSD_REPORT_ATTENTION: a later run's finding\n")
        before = self.dump()
        for exit_code in (0, 1):
            with self.subTest(exit_code=exit_code):
                again = self.tick("a", 1, exit_code=exit_code)
                self.assertEqual((again["recorded"], again["healthy"]), ("nothing", False))
                self.assertEqual(again["why"], "a replay of a run whose heartbeat recorded it clean;"
                                               " the run id is the key, so its changed evidence was not written")
                self.assertEqual(self.items(), [])
                self.assertEqual(before, self.dump())
        self.assertIs(reporting.health(self.db, "probe"), True)


class TheQuietPathIsCheckedAndSaysWhatHappened(unittest.TestCase):
    """The #315 review: a clean run returns before `ingest`, so it must check the
    run the way `ingest` does, and its reason must be true of this run."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / "sd.db"; initialise(self.path)
        self.db = connect(self.path); self.addCleanup(self.db.close)
        self.log = self.root / "probe.log"; self.log.write_text("ok\n")

    def tick(self, **changes):
        arguments = {"job": "probe", "run_id": "one", "started": "2026-09-08T00:00:00Z",
                     "ended": "2026-09-08T00:01:00Z", "exit_code": 0, "log_path": self.log, "now": NOW, **changes}
        return reporting.ingest_log(self.db, **arguments)

    def test_a_bad_first_clean_run_is_refused_before_any_heartbeat(self):
        cases = {"job with a space": {"job": "bad name"}, "job not text": {"job": 7},
                 "empty run id": {"run_id": ""}, "long run id": {"run_id": "r" * 161},
                 "run id not text": {"run_id": 12},
                 "ends before it starts": {"started": "2026-09-08T00:02:00Z"},
                 "exit code as text": {"exit_code": "0"}, "exit code as bool": {"exit_code": False}}
        for name, change in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(workflow.WorkflowError):
                    self.tick(**change)
                self.assertEqual(self.db.execute("SELECT count(*) FROM state WHERE kind='heartbeat'").fetchone()[0], 0)

    def test_a_first_clean_run_says_it_is_a_baseline(self):
        first = self.tick()
        self.assertEqual((first["recorded"], first["why"]),
                         ("heartbeat", "the job's first recorded tick, a baseline and not an event"))
        second = self.tick(run_id="two", ended="2026-09-08T00:16:00Z")
        self.assertEqual((second["recorded"], second["why"]),
                         ("heartbeat", "a clean tick of a job whose last tick was also clean"))

    def test_a_replayed_clean_run_says_it_is_a_replay(self):
        self.tick()
        again = self.tick()
        self.assertEqual((again["recorded"], again["why"]),
                         ("nothing", "a replay of a run whose heartbeat is already recorded, so nothing was written"))


class ARepeatedFailureFoldsIntoTheOpenReport(unittest.TestCase):
    """A job that fails the same way on a schedule opens one report, not one per run (sd:920).

    sd:880's watchdog opened 51 `needs attention` rows in thirteen hours, one
    every fifteen minutes, each with its own followup. The fix that stopped
    that job did not bound the next one. So a run that needs attention, when
    an open attention report for the same job and the same `attention_basis`
    already exists, folds into it: `fields.repeats` carries the count and the
    last run's identity, no second row and no second followup are written.
    The single-failure case is untouched: one bad night still opens one
    report, and the failure after an acknowledge opens a fresh one; the same
    declared findings after an acknowledge count on the done report (sd:4629).
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / "sd.db"; initialise(self.path)
        self.db = connect(self.path); self.addCleanup(self.db.close)
        host = mock.patch("sd_db.ship.this_host", return_value="hosta"); host.start(); self.addCleanup(host.stop)

    def tick(self, run, minute, *, exit_code=1, text=None, job="probe"):
        log = self.root / f"{job}-{run}.log"
        if not log.exists():
            log.write_text(text if text is not None else f"boom at {minute}\n")
        return reporting.ingest_log(
            self.db, job=job, run_id=run, started="2026-09-08T00:00:00Z",
            ended=f"2026-09-08T00:{minute:02d}:00Z", exit_code=exit_code, log_path=log, now=NOW)

    def rows(self):
        return [dict(row) for row in self.db.execute(
            "SELECT id, title, status, external_id, fields, body FROM item WHERE kind='report' ORDER BY id")]

    def followups(self, item):
        return self.db.execute("SELECT COUNT(*) FROM note WHERE item=? AND kind='followup'", (item,)).fetchone()[0]

    def repeats(self, item):
        return json.loads(self.db.execute("SELECT fields FROM item WHERE id=?", (item,)).fetchone()["fields"]).get("repeats")

    def test_a_repeated_failure_folds_with_a_count_and_keeps_one_body(self):
        first = self.tick("a", 1)
        self.assertEqual(first["recorded"], "report")
        item = first["item"]["id"]
        second = self.tick("b", 16)
        self.assertEqual((second["recorded"], second["item"]["id"], second["count"]), ("folded", item, 2))
        self.assertEqual(second["why"], "job exited 1 on hosta")
        third = self.tick("c", 31)
        self.assertEqual((third["recorded"], third["item"]["id"], third["count"]), ("folded", item, 3))
        rows = self.rows()
        self.assertEqual([row["external_id"] for row in rows], ["probe:a"])
        self.assertEqual(rows[0]["title"], "probe: needs attention")
        self.assertEqual(json.loads(rows[0]["body"]), {"text": "boom at 31\n"})
        self.assertEqual(self.followups(item), 1)
        fields = json.loads(rows[0]["fields"])
        self.assertIs(fields["attention"], True)
        # The original run's own provenance is untouched by the folds.
        self.assertEqual((fields["report"]["run_id"], fields["report"]["ended"]), ("a", "2026-09-08T00:01:00+00:00"))
        self.assertEqual(fields["repeats"], {
            "count": 3, "first_ended": "2026-09-08T00:01:00+00:00", "last_run_id": "c",
            "last_ended": "2026-09-08T00:31:00+00:00", "run_ids": ["b", "c"]})

    def test_a_replay_of_a_folded_run_or_of_the_original_counts_nothing(self):
        item = self.tick("a", 1)["item"]["id"]
        self.tick("b", 16)
        before = tuple(self.db.iterdump())
        again = self.tick("b", 16)
        self.assertEqual((again["recorded"], again["item"]["id"], again["count"]), ("folded", item, 2))
        self.assertEqual(before, tuple(self.db.iterdump()))
        # The open report's own run, replayed after a fold changed its fields,
        # is still its own replay and not "different evidence".
        original = self.tick("a", 1)
        self.assertEqual((original["recorded"], original["item"]["id"]), ("report", item))
        self.assertEqual(before, tuple(self.db.iterdump()))

    def test_only_the_last_twenty_folded_runs_are_remembered(self):
        item = self.tick("a", 1)["item"]["id"]
        for index in range(1, 26):
            self.tick(f"r{index:02d}", 2 + index)
        repeats = self.repeats(item)
        self.assertEqual(repeats["count"], 26)
        self.assertEqual(repeats["run_ids"], [f"r{index:02d}" for index in range(6, 26)])
        self.assertEqual((repeats["last_run_id"], repeats["last_ended"]), ("r25", "2026-09-08T00:27:00+00:00"))
        # A folded run older than the twenty remembered is counted again on a
        # replay, and the docstring says so.
        self.assertEqual(self.tick("r01", 3)["count"], 27)

    def test_a_different_basis_opens_a_new_report(self):
        first = self.tick("a", 1, exit_code=1)["item"]["id"]
        second = self.tick("b", 16, exit_code=2)
        self.assertEqual(second["recorded"], "report")
        self.assertNotEqual(second["item"]["id"], first)
        self.assertEqual(len(self.rows()), 2)
        self.assertIsNone(self.repeats(first))
        self.assertIsNone(self.repeats(second["item"]["id"]))
        # And the same basis folds into the newest open one, not the oldest.
        third = self.tick("c", 31, exit_code=2)
        self.assertEqual((third["recorded"], third["item"]["id"]), ("folded", second["item"]["id"]))
        self.assertEqual(self.tick("d", 46, exit_code=1)["item"]["id"], first)

    def test_a_declared_finding_and_an_exit_code_are_two_bases(self):
        first = self.tick("a", 1, exit_code=0, text="SD_REPORT_ATTENTION: disk at 91%\n")["item"]["id"]
        self.assertEqual(self.tick("b", 16, exit_code=0, text="SD_REPORT_ATTENTION: disk at 91%\n")["item"]["id"], first)
        self.assertEqual(self.repeats(first)["count"], 2)
        other = self.tick("c", 31, exit_code=0, text="SD_REPORT_ATTENTION: disk at 95%\n")
        self.assertEqual(other["recorded"], "report")
        self.assertNotEqual(other["item"]["id"], first)

    def test_a_recovery_files_nothing_and_the_next_failure_folds(self):
        failed = self.tick("a", 1)["item"]["id"]
        recovered = self.tick("b", 16, exit_code=0, text="ok\n")
        self.assertEqual((recovered["recorded"], recovered["why"]), ("heartbeat", "the job recovered"))
        # The failure after a recovery folds into the still-open failure report.
        self.assertEqual(self.tick("c", 31)["item"]["id"], failed)
        again = self.tick("d", 46, exit_code=0, text="ok\n")
        self.assertEqual((again["recorded"], again["why"]), ("heartbeat", "the job recovered"))
        self.assertEqual([row["id"] for row in self.rows()], [failed])

    def test_another_job_with_the_same_basis_is_not_a_target(self):
        first = self.tick("a", 1)["item"]["id"]
        other = self.tick("a", 1, job="other")
        self.assertEqual(other["recorded"], "report")
        self.assertNotEqual(other["item"]["id"], first)
        self.assertIsNone(self.repeats(first))

    def test_the_run_after_an_acknowledge_opens_a_fresh_report(self):
        first = self.tick("a", 1)
        self.tick("b", 16)
        reporting.acknowledge(self.db, first["item"]["id"], who="fixture", resolve_ingest_followups=True,
                              expected_revision=workflow.item_state(self.db, first["item"]["id"])["revision"])
        fresh = self.tick("c", 31)
        self.assertEqual(fresh["recorded"], "report")
        self.assertNotEqual(fresh["item"]["id"], first["item"]["id"])
        self.assertNotIn("count", fresh)
        self.assertEqual(self.followups(fresh["item"]["id"]), 1)
        self.assertIsNone(self.repeats(fresh["item"]["id"]))
        self.assertEqual(self.repeats(first["item"]["id"])["count"], 2)
        # And the fresh one is the target from here on, not the acknowledged one.
        self.assertEqual(self.tick("d", 46)["item"]["id"], fresh["item"]["id"])

    def test_a_folded_run_replayed_after_the_acknowledge_answers_with_the_done_report(self):
        # An operator recovering a folded run by hand after the report was
        # acknowledged: the run's identity lives only in the done report's
        # `repeats.run_ids`, which is not a fold target. Before sd:955 the
        # replay found no report and opened a fresh one, with a followup.
        first = self.tick("a", 1)["item"]["id"]
        self.tick("b", 16)
        reporting.acknowledge(self.db, first, who="fixture", resolve_ingest_followups=True,
                              expected_revision=workflow.item_state(self.db, first)["revision"])
        before = tuple(self.db.iterdump())
        again = self.tick("b", 16)
        self.assertEqual((again["recorded"], again["item"]["id"], again["item"]["status"]), ("folded", first, "done"))
        self.assertEqual(again["count"], 2)
        self.assertEqual([row["external_id"] for row in self.rows()], ["probe:a"])
        self.assertEqual(self.followups(first), 1)
        self.assertEqual(before, tuple(self.db.iterdump()))
        # The done report's own run replays the same way it always did.
        original = self.tick("a", 1)
        self.assertEqual((original["recorded"], original["item"]["id"]), ("report", first))
        self.assertEqual(before, tuple(self.db.iterdump()))
        # A run id that was folded under another job is not this job's replay.
        self.assertEqual(self.tick("b", 16, job="other")["recorded"], "report")

    def test_the_folded_run_lookup_reads_one_job_through_the_identity_index(self):
        """The #401 review: every report-worthy ingest asks `_folded_into`, and it
        scanned every `item` row. It now seeks the job's own `job:` range of
        `item_by_external`, so a job's lookup costs that job's reports only."""
        first = self.tick("a", 1)["item"]["id"]
        self.tick("b", 16)
        self.tick("a", 1, job="prob")
        statements = []
        self.db.set_trace_callback(statements.append)
        try:
            self.assertEqual(reporting._folded_into(self.db, "probe", "b")["id"], first)
            self.assertIsNone(reporting._folded_into(self.db, "prob", "b"))
            self.assertIsNone(reporting._folded_into(self.db, "probe", "missing"))
        finally:
            self.db.set_trace_callback(None)
        lookups = [sql for sql in statements if "repeats.run_ids" in sql]
        self.assertEqual(len(lookups), 3)
        for sql in lookups:
            plan = [row[3] for row in self.db.execute("EXPLAIN QUERY PLAN " + sql)]
            self.assertTrue(any("USING INDEX item_by_external" in step for step in plan), plan)
            self.assertFalse(any(step.startswith("SCAN item") for step in plan), plan)

    def test_the_fold_target_reads_one_job_through_the_identity_index(self):
        """Acknowledged rows are never deleted, and since sd:4629 they are targets:
        the read seeks the job's `job:` range as `_folded_into` does."""
        statements: list[str] = []
        self.db.set_trace_callback(statements.append)
        try:
            reporting._fold_target(self.db, "probe", "disk low", chain=1)
        finally:
            self.db.set_trace_callback(None)
        [sql] = [sql for sql in statements if "attention_basis" in sql]
        plan = [row[3] for row in self.db.execute("EXPLAIN QUERY PLAN " + sql)]
        self.assertTrue(any("USING INDEX item_by_external" in step for step in plan), plan)

    def test_a_report_with_unreadable_fields_is_never_a_target(self):
        for index, value in enumerate((None, "", "{not json")):
            with self.subTest(fields=value):
                run = f"a-{index}"
                item = self.tick(run, 1)["item"]["id"]
                self.db.execute("UPDATE item SET fields=? WHERE id=?", (value, item))
                self.db.commit()
                fresh = self.tick(run + "-next", 16)
                self.assertEqual(fresh["recorded"], "report")
                self.assertNotEqual(fresh["item"]["id"], item)
                # The readable one is acknowledged so the next subtest starts
                # from no readable open target; the unreadable one stays open,
                # which is the property: open, and still never a target.
                reporting.acknowledge(self.db, fresh["item"]["id"], who="fixture", resolve_ingest_followups=True,
                                      expected_revision=workflow.item_state(self.db, fresh["item"]["id"])["revision"])

    def test_a_record_report_neither_folds_nor_is_a_target(self):
        kwargs = dict(started="2026-09-08T00:00:00Z", ended="2026-09-08T00:01:00Z", exit_code=1,
                      text="boom\n", source_path="/fixture", attention=True)
        marked = reporting.ingest(self.db, job="probe", run_id="record-one", record="probe", **kwargs)["item"]["id"]
        plain = reporting.ingest(self.db, job="probe", run_id="plain-one", **kwargs)["item"]["id"]
        self.assertNotEqual(plain, marked)
        marked_again = reporting.ingest(self.db, job="probe", run_id="record-two", record="probe", **kwargs)["item"]["id"]
        self.assertNotIn(marked_again, (marked, plain))
        self.assertEqual(reporting.ingest(self.db, job="probe", run_id="plain-two", **kwargs)["item"]["id"], plain)
        self.assertEqual(self.repeats(plain)["count"], 2)
        self.assertIsNone(self.repeats(marked))
        self.assertIsNone(self.repeats(marked_again))

    def test_a_fold_stores_the_latest_body(self):
        """sd:4629 (a): the sd:4042 ruling keeps one report "updated while its
        findings stay the same", so a fold replaces the body with the run's own."""
        item = self.tick("a", 1, exit_code=0, text="SD_REPORT_ATTENTION: disk low\nfree 9%\n")["item"]["id"]
        self.tick("b", 16, exit_code=0, text="SD_REPORT_ATTENTION: disk low\nfree 7%\n")
        body = json.loads(self.db.execute("SELECT body FROM item WHERE id=?", (item,)).fetchone()["body"])
        self.assertEqual(body, {"text": "SD_REPORT_ATTENTION: disk low\nfree 7%\n"})
        self.assertEqual(self.repeats(item)["last_run_id"], "b")

    def ack(self, item):
        reporting.acknowledge(self.db, item, who="fixture", resolve_ingest_followups=True,
                              expected_revision=workflow.item_state(self.db, item)["revision"])

    def test_an_acknowledged_findings_report_stays_closed_while_its_findings_repeat(self):
        """sd:4629 (b): the operator acknowledged these findings; the same
        findings the next night count on that report and do not open another."""
        finding = "SD_REPORT_ATTENTION: disk low [123]\n"
        first = self.tick("a", 1, exit_code=0, text=finding)["item"]["id"]
        self.ack(first)
        again = self.tick("b", 16, exit_code=0, text=finding + "night two\n")
        self.assertEqual((again["recorded"], again["item"]["id"], again["item"]["status"]), ("folded", first, "done"))
        self.assertEqual(again["count"], 2)
        self.assertEqual([row["id"] for row in self.rows()], [first])
        self.assertEqual(self.followups(first), 1)
        self.assertEqual(json.loads(again["item"]["body"]), {"text": finding + "night two\n"})
        # A changed finding is new: it opens its own report with a followup.
        changed = self.tick("c", 31, exit_code=0, text="SD_REPORT_ATTENTION: disk low [456]\n")
        self.assertEqual((changed["recorded"], changed["item"]["status"]), ("report", "planning"))
        self.assertEqual(self.followups(changed["item"]["id"]), 1)

    def test_a_carried_unseen_finding_does_not_fold_into_an_acknowledged_report(self):
        """A lost run's finding rides in ahead of an acknowledged one (sd:3537):
        folding the slice into the done report would close a finding nobody saw."""
        acked = self.tick("a", 1, exit_code=0, text="SD_REPORT_ATTENTION: disk low [123]\n")["item"]["id"]
        self.ack(acked)
        carried = self.tick("b", 16, exit_code=0, text="SD_REPORT_ATTENTION: swap high [7]\nnext run\n"
                                                        "SD_REPORT_ATTENTION: disk low [123]\n")
        self.assertEqual((carried["recorded"], carried["item"]["status"]), ("report", "planning"))
        self.assertEqual(self.followups(carried["item"]["id"]), 1)
        self.assertIsNone(self.repeats(acked))

    def test_a_carried_unseen_finding_opens_its_own_report_beside_an_open_one(self):
        """The same slice against an open report: a fold would keep the unseen
        finding only until the next body replaced it, or drop it as a late run."""
        disk = "SD_REPORT_ATTENTION: disk low [123]\n"
        open_ = self.tick("a", 1, exit_code=0, text=disk)["item"]["id"]
        carried = self.tick("b", 16, exit_code=0, text="SD_REPORT_ATTENTION: swap high [7]\nnext run\n" + disk)
        self.assertEqual(carried["recorded"], "report")
        self.assertIn("swap high", json.loads(carried["item"]["body"])["text"])
        self.assertIsNone(self.repeats(open_))
        # A job that prints the same two lines every run still folds.
        again = self.tick("c", 31, exit_code=0, text="SD_REPORT_ATTENTION: swap high [7]\n" + disk)
        self.assertEqual((again["recorded"], again["item"]["id"]), ("folded", carried["item"]["id"]))
        # A disk-only run never folds into the carried one. Since sd:4641 the
        # carried report superseded the disk report, and this one supersedes it.
        last = self.tick("d", 46, exit_code=0, text=disk)
        self.assertEqual((last["recorded"], last["why"]), ("report", "disk low [123]"))
        self.assertNotIn(last["item"]["id"], (open_, carried["item"]["id"]))

    def test_a_late_run_is_counted_but_keeps_the_newer_body(self):
        """A hand recovery of an older run counts, and the body stays the newest run's."""
        item = self.tick("a", 1)["item"]["id"]
        self.tick("c", 31)
        self.tick("b", 16)
        body = json.loads(self.db.execute("SELECT body FROM item WHERE id=?", (item,)).fetchone()["body"])
        self.assertEqual(body, {"text": "boom at 31\n"})
        repeats = self.repeats(item)
        self.assertEqual((repeats["count"], repeats["last_run_id"], repeats["last_ended"], repeats["run_ids"]),
                         (3, "c", "2026-09-08T00:31:00+00:00", ["c", "b"]))

    def test_an_open_report_wins_over_an_acknowledged_one_with_the_same_findings(self):
        """A reopened older report and a newer acknowledged one: the open one counts the run."""
        finding = "SD_REPORT_ATTENTION: disk low [123]\n"
        older = self.tick("a", 1, exit_code=0, text=finding)["item"]["id"]
        self.db.execute("UPDATE item SET fields=json_set(fields, '$.report.attention_basis', 'parked') WHERE id=?", (older,))
        self.db.commit()
        newer = self.tick("b", 16, exit_code=0, text=finding)["item"]["id"]
        self.assertNotEqual(newer, older)
        self.ack(newer)
        self.db.execute("UPDATE item SET fields=json_set(fields, '$.report.attention_basis', 'disk low [123]') WHERE id=?",
                        (older,))
        self.db.commit()
        self.assertEqual(self.tick("c", 31, exit_code=0, text=finding)["item"]["id"], older)

    def acked_disk(self):
        """An acknowledged `disk low` report, the fixture the chain tests start from."""
        first = self.tick("a", 1, exit_code=0, text=self.DISK)["item"]["id"]
        self.ack(first)
        return first

    DISK = "SD_REPORT_ATTENTION: disk low [123]\n"

    def assert_fresh(self, state, acked):
        self.assertEqual((state["recorded"], state["item"]["status"]), ("report", "planning"), state)
        self.assertNotEqual(state["item"]["id"], acked)
        self.assertEqual(self.followups(state["item"]["id"]), 1)

    def test_a_clean_run_ends_the_acknowledged_chain(self):
        """Lane review of sd:4629: acknowledged findings that recover and return
        months later are a new incident, not the one the operator closed."""
        acked = self.acked_disk()
        self.assertEqual(self.tick("b", 16, exit_code=0, text="ok\n")["recorded"], "heartbeat")
        self.assert_fresh(self.tick("c", 31, exit_code=0, text=self.DISK), acked)

    def test_other_findings_or_a_failure_end_the_acknowledged_chain(self):
        for index, (code, text) in enumerate(((0, "SD_REPORT_ATTENTION: swap high [7]\n"), (1, "boom\n"))):
            with self.subTest(exit_code=code):
                job = f"probe{index}"
                acked = self.tick("a", 1, exit_code=0, text=self.DISK, job=job)["item"]["id"]
                self.ack(acked)
                self.tick("b", 16, exit_code=code, text=text, job=job)
                self.assert_fresh(self.tick("c", 31, exit_code=0, text=self.DISK, job=job), acked)

    def test_another_hosts_run_neither_folds_into_nor_ends_the_chain(self):
        acked = self.acked_disk()
        with mock.patch("sd_db.ship.this_host", return_value="hostb"):
            self.tick("b", 16, exit_code=0, text="ok\n")
            other = self.tick("c", 31, exit_code=0, text=self.DISK)
        self.assert_fresh(other, acked)
        self.assertEqual(self.chain("hosta")["item"], acked)

    def chain(self, host, job="probe"):
        row = self.db.execute("SELECT body FROM state WHERE kind='heartbeat' AND key=? ORDER BY id DESC LIMIT 1",
                              (f"{reporting.CHAIN_KEY}{job}@{host}",)).fetchone()
        return json.loads(row["body"]) if row else None

    def test_a_clean_run_in_the_same_second_ends_the_chain(self):
        """Codex on the chain fix: a strict time comparison skipped a clean run
        that ended in the second of the last finding; arrival order ranks a tie."""
        acked = self.acked_disk()
        self.tick("b", 1, exit_code=0, text="ok\n")
        self.assert_fresh(self.tick("c", 16, exit_code=0, text=self.DISK), acked)

    def test_another_hosts_fold_does_not_hide_this_hosts_recovery(self):
        """Host B's repeat folds into host A's open report and moves its last run;
        host A's own clean run must still end A's chain."""
        first = self.tick("a", 1, exit_code=0, text=self.DISK)["item"]["id"]
        with mock.patch("sd_db.ship.this_host", return_value="hostb"):
            self.tick("b", 31, exit_code=0, text=self.DISK)
        self.tick("c", 16, exit_code=0, text="ok\n")
        self.ack(first)
        self.assert_fresh(self.tick("d", 46, exit_code=0, text=self.DISK), first)

    def test_a_replay_after_compaction_does_not_restore_a_broken_chain(self):
        """Codex on the chain row: once compaction took a run's heartbeat, its
        replay tied the chain's end and wrote the done report back into it."""
        for kind, run in (("original", "a"), ("folded", "a2")):
            with self.subTest(kind):
                job = f"probe-{kind}"
                first = self.tick("a", 1, exit_code=0, text=self.DISK, job=job)["item"]["id"]
                self.tick("a2", 1, exit_code=0, text=self.DISK, job=job)
                self.ack(first)
                self.tick("clean", 1, exit_code=0, text="ok\n", job=job)
                with mock.patch("sd_db.ship.this_host", return_value="hostb"):
                    self.tick("b", 16, exit_code=0, text="ok\n", job=job)
                retention.compact_heartbeats(self.db)
                self.assertEqual(self.tick(run, 1, exit_code=0, text=self.DISK, job=job)["item"]["id"], first)
                self.assert_fresh(self.tick("c", 31, exit_code=0, text=self.DISK, job=job), first)

    def test_a_future_stamped_finding_does_not_outrank_the_recovery(self):
        """Codex on the chain row: a bad future stamp held the chain the way
        `_beat`'s `FUTURE_ALLOWANCE` keeps it from holding health."""
        log = self.root / "ahead.log"; log.write_text(self.DISK)
        ahead = reporting.ingest_log(self.db, job="probe", run_id="ahead", started="2026-09-08T00:00:00Z",
                                     ended="2026-09-08T01:30:00Z", exit_code=0, log_path=log, now=NOW)["item"]["id"]
        self.ack(ahead)
        self.tick("clean", 16, exit_code=0, text="ok\n")
        log = self.root / "after.log"; log.write_text(self.DISK)
        after = reporting.ingest_log(self.db, job="probe", run_id="after", started="2026-09-08T01:00:00Z",
                                     ended="2026-09-08T01:31:00Z", exit_code=0, log_path=log,
                                     now=datetime(2026, 9, 8, 1, 32, tzinfo=UTC))
        self.assert_fresh(after, ahead)

    def test_a_future_stamped_fold_does_not_freeze_the_body(self):
        item = self.tick("a", 1)["item"]["id"]
        log = self.root / "ahead.log"; log.write_text("boom ahead\n")
        reporting.ingest_log(self.db, job="probe", run_id="ahead", started="2026-09-08T00:00:00Z",
                             ended="2026-09-08T01:30:00Z", exit_code=1, log_path=log, now=NOW)
        self.tick("c", 31)
        body = json.loads(self.db.execute("SELECT body FROM item WHERE id=?", (item,)).fetchone()["body"])
        self.assertEqual((body, self.repeats(item)["last_run_id"]), ({"text": "boom at 31\n"}, "c"))

    def test_a_late_report_after_a_clean_run_starts_no_chain(self):
        """A hand recovery of an older run with findings, filed after a newer clean run."""
        self.tick("b", 16, exit_code=0, text="ok\n")
        late = self.tick("a", 1, exit_code=0, text=self.DISK)["item"]["id"]
        self.ack(late)
        self.assert_fresh(self.tick("c", 31, exit_code=0, text=self.DISK), late)

    def test_a_late_clean_run_does_not_end_the_chain(self):
        acked = self.acked_disk()
        self.tick("b", 16, exit_code=0, text=self.DISK)
        self.tick("late", 10, exit_code=0, text="ok\n")
        self.assertEqual(self.tick("c", 31, exit_code=0, text=self.DISK)["item"]["id"], acked)

    def test_a_report_filed_before_the_chain_was_kept_is_never_a_done_target(self):
        """Older state: with no chain row for the host, nothing says no clean run came between."""
        acked = self.acked_disk()
        self.db.execute("DELETE FROM state WHERE key LIKE ?", (reporting.CHAIN_KEY + "%",))
        self.db.commit()
        self.assert_fresh(self.tick("b", 16, exit_code=0, text=self.DISK), acked)

    def test_the_original_run_replays_after_its_chain_ended(self):
        acked = self.acked_disk()
        self.tick("b", 16, exit_code=0, text="ok\n")
        before = tuple(self.db.iterdump())
        again = self.tick("a", 1, exit_code=0, text=self.DISK)
        self.assertEqual((again["recorded"], again["item"]["id"]), ("report", acked))
        self.assertEqual(before, tuple(self.db.iterdump()))

    def test_an_acknowledged_failure_does_not_hide_the_next_failure(self):
        """A non-zero exit is not a findings set: `job exited N` says nothing of
        what failed, so the failure after an acknowledge still opens a report."""
        first = self.tick("a", 1)["item"]["id"]
        self.ack(first)
        fresh = self.tick("b", 16)
        self.assertEqual((fresh["recorded"], fresh["item"]["status"]), ("report", "planning"))
        self.assertNotEqual(fresh["item"]["id"], first)

    def test_a_carried_slice_names_every_declared_line(self):
        """sd:4629 (c): a lost run's slice is carried into the next run's
        (`.unreported`, sd:3537); its first line made the basis, so the slice
        folded into the lost run's report and the new finding went unseen."""
        lost = self.tick("a", 1, exit_code=0, text="SD_REPORT_ATTENTION: disk low [123]\n")["item"]["id"]
        carried = self.tick("b", 16, exit_code=0,
                            text="SD_REPORT_ATTENTION: disk low [123]\nnext run\nSD_REPORT_ATTENTION: disk low [456]\n")
        self.assertEqual((carried["recorded"], carried["why"]), ("report", "disk low [123]\ndisk low [456]"))
        self.assertNotEqual(carried["item"]["id"], lost)
        # One line holding the separator is not the two lines.
        self.ack(carried["item"]["id"])
        one = self.tick("f", 55, exit_code=0, text="SD_REPORT_ATTENTION: disk low [123]; disk low [456]\n")
        self.assertEqual((one["recorded"], one["item"]["status"]), ("report", "planning"))
        # One line twice is one finding.
        twice = self.tick("c", 31, exit_code=0, text="SD_REPORT_ATTENTION: disk low [123]\nSD_REPORT_ATTENTION: disk low [123]\n")
        self.assertEqual(twice["why"], "disk low [123]")

    def test_a_basis_past_the_limit_still_files(self):
        """A carried slice grows a line per lost night; past `ingest`'s 2000
        characters the run was refused, and every later run carried it again."""
        lines = "".join(f"SD_REPORT_ATTENTION: finding {index} {'x' * 80}\n" for index in range(30))
        first = self.tick("a", 1, exit_code=0, text=lines)
        self.assertEqual(first["recorded"], "report")
        self.assertLessEqual(len(first["why"]), 2000)
        self.assertRegex(first["why"], r"\[sha256 [0-9a-f]{16}\]$")
        self.assertEqual(self.tick("b", 16, exit_code=0, text=lines)["item"]["id"], first["item"]["id"])

    def test_a_failure_names_its_host_and_its_declared_reason(self):
        """sd:4629 (d): `job exited N` folded one host's crash into another's
        report, and one cause into another's."""
        first = self.tick("a", 1)
        self.assertEqual(first["why"], "job exited 1 on hosta")
        with mock.patch("sd_db.ship.this_host", return_value="hostb"):
            other_host = self.tick("b", 16)
        self.assertEqual((other_host["recorded"], other_host["why"]), ("report", "job exited 1 on hostb"))
        declared = self.tick("c", 31, text="SD_REPORT_ATTENTION: upgrade failed [9]\n")
        self.assertEqual((declared["recorded"], declared["why"]), ("report", "job exited 1 on hosta: upgrade failed [9]"))
        self.assertEqual(self.tick("d", 46)["item"]["id"], first["item"]["id"])

    def test_a_record_that_reuses_a_folded_run_id_is_its_own_row(self):
        # A record report is never folded, and a folded run's identity is
        # not a record's replay either: `_folded_into` is asked only for a
        # cron run, so a record that reuses a folded `job`/`run_id` is filed
        # as a new row with its own `record` and `actor` fields, and the
        # report the run folded into is untouched.
        first = self.tick("a", 1)["item"]["id"]
        self.tick("b", 16)
        repeats = self.repeats(first)
        state = reporting.ingest(self.db, job="probe", run_id="b", record="probe", actor={"who": "fixture"},
                                 started="2026-09-08T00:00:00Z", ended="2026-09-08T00:17:00Z", exit_code=1,
                                 text="by hand\n", source_path="/fixture", attention=True)
        self.assertNotEqual(state["item"]["id"], first)
        rows = {row["external_id"]: row for row in self.rows()}
        self.assertEqual(sorted(rows), ["probe:a", "probe:b"])
        fields = json.loads(rows["probe:b"]["fields"])
        self.assertEqual((fields["record"], fields["report"]["actor"]), ("probe", {"who": "fixture"}))
        self.assertEqual(self.repeats(first), repeats)
        self.assertEqual(self.followups(first), 1)



class ANewFindingsReportSupersedesTheOlderOne(unittest.TestCase):
    """sd:4641, rule (e) of sd:4629: one open findings report per job and host.

    A shrinking or changed set of findings opened a second report beside the
    first. Now a new clean-exit findings report closes the older open one of
    the same job and host as superseded; a superseded report never counts as
    acknowledged; only reports that store a host take part.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / "sd.db"; initialise(self.path)
        self.db = connect(self.path); self.addCleanup(self.db.close)
        host = mock.patch("sd_db.ship.this_host", return_value="hosta"); host.start(); self.addCleanup(host.stop)

    def tick(self, run, minute, text, *, exit_code=0, job="probe"):
        log = self.root / f"{job}-{run}.log"
        if not log.exists():
            log.write_text(text)
        return reporting.ingest_log(
            self.db, job=job, run_id=run, started="2026-09-08T00:00:00Z",
            ended=f"2026-09-08T00:{minute:02d}:00Z", exit_code=exit_code, log_path=log, now=NOW)

    def row(self, item):
        return self.db.execute("SELECT * FROM item WHERE id=?", (item,)).fetchone()

    def status_notes(self, item):
        return [row["body"] for row in self.db.execute(
            "SELECT body FROM note WHERE item=? AND kind='status_change' ORDER BY id", (item,))]

    def open_followups(self, item):
        return self.db.execute("SELECT COUNT(*) FROM note WHERE item=? AND kind='followup' AND resolved_at IS NULL",
                               (item,)).fetchone()[0]

    TWO = "SD_REPORT_ATTENTION: 2 finding(s) [12]\n"
    ONE = "SD_REPORT_ATTENTION: 1 finding(s) [1]\n"

    def test_a_report_stores_its_host(self):
        item = self.tick("a", 1, self.TWO)["item"]["id"]
        self.assertEqual(json.loads(self.row(item)["fields"])["report"]["host"], "hosta")

    def test_a_shrinking_set_supersedes_the_open_report(self):
        older = self.tick("a", 1, self.TWO)["item"]["id"]
        newer = self.tick("b", 16, self.ONE)
        self.assertEqual((newer["recorded"], newer["item"]["status"]), ("report", "planning"))
        self.assertEqual(self.row(older)["status"], "done")
        self.assertRegex(self.status_notes(older)[-1],
                         rf"^planning -> done by cron: superseded by sd:{newer['item']['id']}")
        self.assertEqual(self.open_followups(older), 0)
        self.assertEqual(self.open_followups(newer["item"]["id"]), 1)

    def test_a_superseded_report_never_counts_as_acknowledged(self):
        """Even named by the host's chain row, it takes no repeat."""
        older = self.tick("a", 1, self.TWO)["item"]["id"]
        self.tick("b", 16, self.ONE)
        self.db.execute("UPDATE state SET body=json_set(body, '$.item', ?) WHERE key=?",
                        (older, reporting.CHAIN_KEY + "probe@hosta"))
        self.db.commit()
        again = self.tick("c", 31, self.TWO)
        self.assertEqual((again["recorded"], again["item"]["status"]), ("report", "planning"))
        self.assertNotEqual(again["item"]["id"], older)

    def test_another_hosts_report_is_not_superseded(self):
        with mock.patch("sd_db.ship.this_host", return_value="hostb"):
            other = self.tick("a", 1, self.TWO)["item"]["id"]
        self.tick("b", 16, self.ONE)
        self.assertEqual(self.row(other)["status"], "planning")

    def test_a_report_another_host_folded_into_stays_open(self):
        """Host B's run folded into host A's report: A's shrinking set must not hide B's finding."""
        shared = self.tick("a", 1, self.TWO)["item"]["id"]
        with mock.patch("sd_db.ship.this_host", return_value="hostb"):
            self.assertEqual(self.tick("b", 2, self.TWO)["item"]["id"], shared)
        self.tick("c", 16, self.ONE)
        self.assertEqual(self.row(shared)["status"], "planning")
        # Once B's newest run went elsewhere, A's next new set closes it.
        with mock.patch("sd_db.ship.this_host", return_value="hostb"):
            self.tick("d", 17, "clean\n")
        self.tick("e", 31, "SD_REPORT_ATTENTION: 3 finding(s) [123]\n")
        self.assertEqual(self.row(shared)["status"], "done")

    def test_a_report_without_a_stored_host_is_not_superseded(self):
        """No backfill: a row filed before the host was stored stays open."""
        older = self.tick("a", 1, self.TWO)["item"]["id"]
        self.db.execute("UPDATE item SET fields=json_remove(fields, '$.report.host') WHERE id=?", (older,))
        self.db.commit()
        self.tick("b", 16, self.ONE)
        self.assertEqual(self.row(older)["status"], "planning")

    def test_failures_neither_supersede_nor_are_superseded(self):
        failed = self.tick("a", 1, "boom\n", exit_code=1)["item"]["id"]
        findings = self.tick("b", 16, self.TWO)["item"]["id"]
        self.assertEqual(self.row(failed)["status"], "planning")
        self.tick("c", 31, "boom again\n", exit_code=2)
        self.assertEqual(self.row(findings)["status"], "planning")

    def test_a_late_report_supersedes_nothing(self):
        newer = self.tick("b", 16, self.TWO)["item"]["id"]
        self.tick("a", 1, self.ONE)
        self.assertEqual(self.row(newer)["status"], "planning")

    def test_a_report_a_person_owes_work_on_stays_open(self):
        older = self.tick("a", 1, self.TWO)["item"]["id"]
        workflow.add_item_note(self.db, older, kind="followup", body="Replace the disk.", who="operator")
        self.tick("b", 16, self.ONE)
        self.assertEqual(self.row(older)["status"], "planning")

    def test_a_row_filed_before_the_host_was_stored_still_replays(self):
        item = self.tick("a", 1, self.TWO)["item"]["id"]
        self.db.execute("UPDATE item SET fields=json_remove(fields, '$.report.host') WHERE id=?", (item,))
        self.db.commit()
        again = self.tick("a", 1, self.TWO)
        self.assertEqual((again["recorded"], again["item"]["id"]), ("report", item))

    def test_a_machine_with_no_host_name_still_files(self):
        with mock.patch("sd_db.ship.this_host", return_value=""):
            older = self.tick("a", 1, self.TWO)["item"]["id"]
            newer = self.tick("b", 16, self.ONE)["item"]["id"]
        self.assertNotIn("host", json.loads(self.row(newer)["fields"])["report"])
        self.assertEqual(self.row(older)["status"], "planning")

    def test_a_superseded_report_the_operator_then_acknowledges_counts(self):
        """The newest status change decides: reopened and acknowledged, it is acknowledged."""
        older = self.tick("a", 1, self.TWO)["item"]["id"]
        self.tick("b", 16, self.ONE)
        reporting.reopen(self.db, older, expected_revision=workflow.item_state(self.db, older)["revision"], who="fixture")
        reporting.acknowledge(self.db, older, expected_revision=workflow.item_state(self.db, older)["revision"],
                              who="fixture", resolve_ingest_followups=True)
        self.db.execute("UPDATE state SET body=json_set(body, '$.item', ?) WHERE key=?",
                        (older, reporting.CHAIN_KEY + "probe@hosta"))
        self.db.commit()
        again = self.tick("c", 31, self.TWO)
        self.assertEqual((again["recorded"], again["item"]["id"]), ("folded", older))

    PAD = "x" * 99 + "\n"

    def past_the_cut(self, head, tail):
        """A log whose `tail` lines sit past `MAX_REPORT`, where the body stops."""
        return head + self.PAD * (reporting.MAX_REPORT // len(self.PAD) + 1) + tail

    def test_a_truncated_log_supersedes_nothing(self):
        """Review round 1: the body stops at `MAX_REPORT`, so it is not the whole set."""
        older = self.tick("a", 1, self.TWO)["item"]["id"]
        newer = self.tick("b", 16, self.past_the_cut(self.ONE, "SD_REPORT_ATTENTION: 2 finding(s) [12]\n"))
        self.assertTrue(json.loads(newer["item"]["fields"])["report"]["truncated"])
        self.assertEqual(self.row(older)["status"], "planning")

    def test_a_finding_past_the_cut_still_names_the_basis(self):
        """The basis reads every declared line of the slice, not only the stored body's."""
        newer = self.tick("a", 1, self.past_the_cut(self.ONE, "SD_REPORT_ATTENTION: disk low [9]\n"))
        self.assertEqual(newer["why"], "1 finding(s) [1]\ndisk low [9]")

    def test_a_finding_past_the_cut_does_not_fold_into_an_acknowledged_report(self):
        acked = self.tick("a", 1, self.ONE)["item"]["id"]
        reporting.acknowledge(self.db, acked, expected_revision=workflow.item_state(self.db, acked)["revision"],
                              who="fixture", resolve_ingest_followups=True)
        again = self.tick("b", 16, self.past_the_cut(self.ONE, "SD_REPORT_ATTENTION: disk low [9]\n"))
        self.assertEqual((again["recorded"], again["item"]["status"]), ("report", "planning"))

    def test_a_clean_run_whose_only_finding_is_past_the_cut_files_a_report(self):
        run = self.tick("a", 1, self.past_the_cut("", "SD_REPORT_ATTENTION: disk low [9]\n"))
        self.assertEqual((run["recorded"], run["why"]), ("report", "disk low [9]"))

    def test_reopening_a_superseded_report_returns_it_to_planning(self):
        older = self.tick("a", 1, self.TWO)["item"]["id"]
        self.tick("b", 16, self.ONE)
        state = reporting.reopen(self.db, older, expected_revision=workflow.item_state(self.db, older)["revision"],
                                 who="fixture")
        self.assertEqual(state["item"]["status"], "planning")

if __name__ == "__main__": unittest.main()
