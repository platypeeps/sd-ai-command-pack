"""Lane wait and gate times (pack sd:6006): what the Queue page shows per repository, and the question they file.

Each entry's history rows in the hub database say when it was enqueued, claimed, gated and ended. Over 7 days the page
shows the median wait and gate time and the slowest entry; a median wait past an hour files the parallel-lanes
question once (operator ruling, grill Q27).
"""

from __future__ import annotations

import calendar
import json
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lane  # noqa: E402

REPOSITORY = "example/pack"
NOW = calendar.timegm(time.strptime("2026-09-10T12:00:00", "%Y-%m-%dT%H:%M:%S"))


def at(minutes: float) -> str:
    """`minutes` before NOW as a lane stamp."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - minutes * 60))


class Times(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = pathlib.Path(tmp.name)
        import sd_db
        sd_db.initialise(home=self.home)
        self.connection = sd_db.connect(home=self.home)
        self.addCleanup(self.connection.close)

    def row(self, entry: str, minutes: float, **body) -> None:
        """One history row of `entry`, written `minutes` before NOW, as `sd_lane.store` writes it."""
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(NOW - minutes * 60))
        self.connection.execute("INSERT INTO state(kind, key, timestamp, body) VALUES ('checkpoint', ?, ?, ?)",
                                (f"{sd_lane.KEY_PREFIX}{REPOSITORY}:{entry}", stamp, json.dumps({"id": entry, **body})))

    def entry(self, entry: str, item: int, *, enqueued: float, claimed: float, merge: float | None, ended: float | None,
              speculated: tuple[float, float] | None = None, status: str = "merged") -> None:
        """An entry's history: enqueue, an optional speculative gate, the claim, the merge step and its end."""
        base = {"item": item, "title": f"item {item}", "enqueued_at": at(enqueued)}
        self.row(entry, enqueued, status="pending", **base)
        if speculated:
            self.row(entry, speculated[0], status="pending", speculation={"status": "running"}, **base)
            self.row(entry, speculated[1], status="pending", speculation={"status": "success"}, **base)
        running = {**base, "status": "running", "started_at": at(claimed)}
        self.row(entry, claimed, step="prepare", **running)
        if merge is not None:
            self.row(entry, merge, step="merge", **running)
        if ended is not None:
            self.row(entry, ended, **{**running, "status": status, "step": "merge", "finished_at": at(ended)})

    def test_each_entry_has_its_wait_gate_and_total(self):
        # Waited 30 min; a 20 min speculative gate, then 5 min of prepare; ended 2 min after the merge step.
        self.entry("e1", 1, enqueued=100, claimed=70, merge=65, ended=63, speculated=(95, 75))
        [found] = sd_lane.entry_times(self.connection, REPOSITORY, now=NOW)
        self.assertEqual((found["item"], found["wait"], found["gate"], found["total"]), (1, 1800, 1500, 2220))

    def test_a_running_entry_has_a_wait_but_no_gate_or_total_yet(self):
        self.entry("e1", 1, enqueued=50, claimed=10, merge=None, ended=None)
        [found] = sd_lane.entry_times(self.connection, REPOSITORY, now=NOW)
        self.assertEqual((found["wait"], found["gate"], found["total"]), (2400, None, None))

    def test_a_prepare_that_ended_short_of_the_merge_ends_its_gate(self):
        self.entry("e1", 1, enqueued=50, claimed=40, merge=None, ended=30, status="failed")
        [found] = sd_lane.entry_times(self.connection, REPOSITORY, now=NOW)
        self.assertEqual((found["gate"], found["total"]), (600, 1200))

    def test_a_reclaimed_entry_sums_the_prepare_of_each_claim(self):
        """pack sd:6281: a reclaim back to pending ended the gate at the first claim's 60 s."""
        base = {"item": 1, "title": "item 1", "enqueued_at": at(130)}
        self.row("e1", 130, status="pending", **base)
        self.row("e1", 125, status="running", step="prepare", started_at=at(125), **base)
        self.row("e1", 124, status="pending", **base)
        self.row("e1", 70, status="running", step="prepare", started_at=at(70), **base)
        self.row("e1", 10, status="running", step="merge", started_at=at(70), **base)
        self.row("e1", 9, status="merged", step="merge", started_at=at(70), finished_at=at(9), **base)
        [found] = sd_lane.entry_times(self.connection, REPOSITORY, now=NOW)
        self.assertEqual((found["wait"], found["gate"], found["total"]), (300, 3660, 7260))

    def test_a_reclaimed_entry_still_in_its_second_prepare_has_no_gate_yet(self):
        base = {"item": 1, "title": "item 1", "enqueued_at": at(130)}
        self.row("e1", 130, status="pending", **base)
        self.row("e1", 125, status="running", step="prepare", started_at=at(125), **base)
        self.row("e1", 124, status="pending", **base)
        self.row("e1", 70, status="running", step="prepare", started_at=at(70), **base)
        [found] = sd_lane.entry_times(self.connection, REPOSITORY, now=NOW)
        self.assertIsNone(found["gate"])

    def test_the_page_reads_medians_the_slowest_entry_and_seven_days_only(self):
        self.entry("e1", 1, enqueued=100, claimed=90, merge=80, ended=79)
        self.entry("e2", 2, enqueued=300, claimed=200, merge=190, ended=185)
        self.entry("e3", 3, enqueued=60, claimed=30, merge=10, ended=9)
        self.entry("old", 4, enqueued=8 * 1440 + 60, claimed=8 * 1440, merge=8 * 1440 - 10, ended=8 * 1440 - 11)
        times = sd_lane.lane_times(self.connection, REPOSITORY, now=NOW)
        self.assertEqual(times["entries"], 3)
        self.assertEqual((times["wait"], times["gate"]), (1800, 600))
        self.assertEqual(times["slowest"], {"item": 2, "title": "item 2", "total": 6900})
        self.assertFalse(times["over"])

    def test_no_entry_reads_no_median(self):
        self.assertEqual(sd_lane.lane_times(self.connection, REPOSITORY, now=NOW),
                         {"days": 7, "entries": 0, "wait": None, "gate": None, "slowest": None, "over": False})


class TheQuestion(Times):
    """A median wait past an hour files the parallel-lanes question once (grill Q27)."""

    def setUp(self) -> None:
        super().setUp()
        import sd_db
        sd_db.upsert_repo(self.connection, "/repos/pack", remote="https://github.com/example/pack.git", managed=1)

    def slow(self) -> None:
        self.entry("e1", 1, enqueued=200, claimed=100, merge=90, ended=89)

    def questions(self) -> list:
        return self.connection.execute(
            "SELECT note.body, item.title, item.repo FROM note JOIN item ON item.id = note.item "
            "WHERE note.kind = 'question'").fetchall()

    def test_a_median_wait_past_an_hour_files_one_question(self):
        self.slow()
        note = sd_lane.wait_question(self.connection, REPOSITORY, "/repos/pack", now=NOW)
        [found] = self.questions()
        self.assertIsNotNone(note)
        self.assertEqual(found["title"], "Decide: parallel lanes for example/pack")
        self.assertIn("median lane wait in example/pack was 100 min", found["body"])
        self.assertTrue(found["body"].endswith("\nOption: Plan parallel lanes (Recommended)\nOption: Not now"))
        # The next run asks nothing while that question is open.
        self.assertIsNone(sd_lane.wait_question(self.connection, REPOSITORY, "/repos/pack", now=NOW + 600))
        self.assertEqual(len(self.questions()), 1)

    def test_an_answered_question_is_not_asked_again_within_the_week(self):
        self.slow()
        sd_lane.wait_question(self.connection, REPOSITORY, "/repos/pack", now=NOW)
        self.connection.execute("UPDATE note SET resolved_at = timestamp WHERE kind = 'question'")
        self.assertIsNone(sd_lane.wait_question(self.connection, REPOSITORY, "/repos/pack", now=NOW + 3600))

    def test_a_done_item_files_nothing(self):
        self.slow()
        sd_lane.wait_question(self.connection, REPOSITORY, "/repos/pack", now=NOW)
        self.connection.execute("UPDATE item SET status = 'done'")
        self.connection.execute("UPDATE note SET resolved_at = '2000-01-01T00:00:00+00:00', "
                                "timestamp = '2000-01-01T00:00:00+00:00' WHERE kind = 'question'")
        self.assertIsNone(sd_lane.wait_question(self.connection, REPOSITORY, "/repos/pack", now=NOW))

    def test_a_short_wait_files_nothing(self):
        self.entry("e1", 1, enqueued=30, claimed=20, merge=10, ended=9)
        self.assertIsNone(sd_lane.wait_question(self.connection, REPOSITORY, "/repos/pack", now=NOW))
        self.assertEqual(self.questions(), [])

    def test_a_hub_that_does_not_answer_is_named_and_stops_nothing(self):
        refused = sd_lane.LaneError("The hub database did not answer", code=sd_lane.HUB_UNAVAILABLE)
        with mock.patch.object(sd_lane, "queue_for", return_value=mock.Mock(repository=REPOSITORY)), \
                mock.patch.object(sd_lane, "on_hub", side_effect=refused):
            asked = sd_lane.ask_wait(pathlib.Path("/repos/pack"), "/repos/pack", {})
        self.assertEqual(asked, {"path": "/repos/pack", "wait_question": None,
                                 "error": "The hub database did not answer"})


if __name__ == "__main__":
    unittest.main()
