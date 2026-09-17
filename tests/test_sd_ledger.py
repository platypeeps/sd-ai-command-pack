"""The ledger, with the write sites that fed it gone.

The point of these tests is not that records get written -- that is the easy
half. It is that a record is *never* a precondition for serving (D-6), and that
the three states the criterion distinguishes stay distinguishable: an absent
ledger, a ledger with starts and no demand, and a ledger with demand. The
classes that drove `dashboard/server.py` -- the bounded tailnet reprobe, the
mutation-row guard in `do_POST`, the Host parser and the ack endpoint's 503 --
retired with that file at sd:719 step 6; what is left reads the ledger alone.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import threading
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

_spec = importlib.util.spec_from_file_location(
    "sd_ledger", REPO_ROOT / "bin" / "sd_ledger.py"
)
ledger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ledger)


class LedgerPath(unittest.TestCase):
    def test_it_is_under_the_state_root_not_the_cache_root(self) -> None:
        """D-1. The cache root is swept for rebuildable things; this is not one."""
        found = ledger.path({"XDG_STATE_HOME": "/s"})
        self.assertEqual(found, pathlib.Path("/s/sd-ai-command-pack/dashboard/ledger.jsonl"))

    def test_an_unset_state_home_falls_back_to_the_documented_default(self) -> None:
        found = ledger.path({})
        self.assertEqual(
            found.parts[-5:],
            (".local", "state", "sd-ai-command-pack", "dashboard", "ledger.jsonl"),
        )


class LedgerAppend(unittest.TestCase):
    def target(self) -> pathlib.Path:
        import tempfile
        directory = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, directory, True)
        return pathlib.Path(directory) / "nested" / "ledger.jsonl"

    def read(self, target: pathlib.Path) -> list[dict]:
        return [json.loads(line) for line in target.read_text().splitlines()]

    def test_a_record_carries_its_kind_and_a_stamp(self) -> None:
        target = self.target()
        ledger.append("bind", target=target, requested=3, bound=1)
        (record,) = self.read(target)
        self.assertEqual(record["kind"], "bind")
        self.assertEqual((record["requested"], record["bound"]), (3, 1))
        self.assertIn("T", record["at"])

    def test_an_unwritable_destination_is_silent(self) -> None:
        """D-6, and the whole reason this function exists in this shape.

        A ledger write is a byproduct of serving. If this raises, a counter
        added to measure the write path has instead added a failure mode to
        it -- which requirement 2 forbids in as many words.
        """
        ledger.append("mutation", target=pathlib.Path("/proc/nope/ledger.jsonl"))

    def test_concurrent_writers_do_not_tear_a_line(self) -> None:
        target = self.target()
        threads = [
            threading.Thread(target=ledger.append, args=("mutation",),
                             kwargs={"target": target, "n": n})
            for n in range(40)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        # Every line parses, and all forty arrived. A torn line raises here
        # rather than being skipped, which is the failure the lock prevents.
        self.assertEqual(sorted(r["n"] for r in self.read(target)), list(range(40)))


class LedgerAcked(unittest.TestCase):
    def target(self) -> pathlib.Path:
        import tempfile
        directory = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, directory, True)
        return pathlib.Path(directory) / "ledger.jsonl"

    def test_only_ack_records_contribute_ids(self) -> None:
        target = self.target()
        ledger.append("ack", target=target, id="dirty:repo:2")
        ledger.append("mutation", target=target, action="index")
        ledger.append("bind", target=target, requested=1, bound=1)
        self.assertEqual(ledger.acked(target), frozenset({"dirty:repo:2"}))

    def test_an_absent_ledger_is_no_acks_rather_than_an_error(self) -> None:
        """The page renders without acks rather than not at all."""
        self.assertEqual(ledger.acked(pathlib.Path("/nope/ledger.jsonl")), frozenset())

    def test_a_damaged_line_is_skipped_and_the_rest_survive(self) -> None:
        target = self.target()
        ledger.append("ack", target=target, id="a")
        with target.open("a") as handle:
            handle.write("{not json\n")
        ledger.append("ack", target=target, id="b")
        self.assertEqual(ledger.acked(target), frozenset({"a", "b"}))


class TheCriterionHasThreeStates(unittest.TestCase):
    """D-6's table, which is the whole reason `bind` rows are written.

    A zero that means "nobody used it" and a zero that means "nothing ever
    ran" select the same branch of R11-D10 and must not be read the same way.
    """

    def target(self) -> pathlib.Path:
        import tempfile
        directory = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, directory, True)
        return pathlib.Path(directory) / "ledger.jsonl"

    def counts(self, target: pathlib.Path) -> tuple[int, int]:
        records = []
        if target.exists():
            for line in target.read_text().splitlines():
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue
        starts = sum(1 for r in records if r.get("kind") == "bind")
        demand = sum(1 for r in records
                     if r.get("kind") == "mutation" and r.get("tailnet_host"))
        return starts, demand

    def test_an_absent_ledger_is_no_evidence(self) -> None:
        starts, demand = self.counts(self.target())
        self.assertEqual((starts, demand), (0, 0))
        self.assertEqual(starts, 0, "no start recorded means the count is not evidence")

    def test_starts_without_mutations_is_genuine_zero_demand(self) -> None:
        target = self.target()
        for _ in range(5):
            ledger.append("bind", target=target, requested=2, bound=2)
        starts, demand = self.counts(target)
        self.assertEqual((starts, demand), (5, 0))

    def test_a_loopback_only_start_is_visible_in_the_denominator(self) -> None:
        """Gap 3 is gap 2's denominator: a zero from a server nothing could
        reach is not evidence about the write path."""
        target = self.target()
        ledger.append("bind", target=target, requested=3, bound=1)
        (record,) = [json.loads(line) for line in target.read_text().splitlines()]
        self.assertLess(record["bound"], record["requested"])


class AcksExpireWithTheDay(unittest.TestCase):
    """D-2 reversed: an ack holds for its day, because count ids recur.

    Review's case: dismiss `dirty:repo:1`, the repo goes clean, and a different
    single dirty file tomorrow mints the identical id. Permanent acks hide it
    forever; the day bound closes that without the ledger having to know which
    ids are count-keyed.
    """

    def target(self) -> pathlib.Path:
        import tempfile
        directory = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, directory, True)
        return pathlib.Path(directory) / "ledger.jsonl"

    def write(self, target: pathlib.Path, stamp: str, identifier: str) -> None:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(
                {"kind": "ack", "id": identifier, "at": stamp}) + "\n")

    def test_todays_ack_holds(self) -> None:
        target = self.target()
        ledger.append("ack", target=target, id="dirty:repo:1")
        self.assertEqual(ledger.acked(target), frozenset({"dirty:repo:1"}))

    def test_yesterdays_ack_does_not(self) -> None:
        import datetime as dt
        target = self.target()
        # Derived from the same clock `acked` reads, so the case cannot drift
        # across a midnight between the two calls. Review found the first
        # version racing it.
        stamp = dt.datetime.now().astimezone() - dt.timedelta(days=1)
        self.write(target, stamp.isoformat(timespec="seconds"), "dirty:repo:1")
        self.assertEqual(ledger.acked(target), frozenset())

    def test_the_stamp_is_the_operators_day_not_utcs(self) -> None:
        """Review's case: 19:00 in America/Denver is tomorrow in UTC, so a
        UTC-stamped ack expired at 18:00 the following afternoon."""
        import datetime as dt
        target = self.target()
        ledger.append("ack", target=target, id="x")
        stamp = json.loads(target.read_text().splitlines()[0])["at"]
        self.assertEqual(stamp[:10], dt.datetime.now().astimezone().date().isoformat())
        self.assertRegex(stamp, r"[+-]\d\d:\d\d$", "the offset keeps it an instant")

    def test_a_stampless_ack_is_not_honoured(self) -> None:
        """Rather than honoured forever, which is the failure being removed."""
        target = self.target()
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"kind": "ack", "id": "x"}) + "\n")
        self.assertEqual(ledger.acked(target), frozenset())


class DamagedLedgerStillRenders(unittest.TestCase):
    def test_a_non_utf8_byte_is_not_an_error(self) -> None:
        """`UnicodeDecodeError` is a ValueError, so the OSError guard missed
        it and the Now endpoint 500'd on a damaged file. Found in review."""
        import tempfile
        directory = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, directory, True)
        target = pathlib.Path(directory) / "ledger.jsonl"
        ledger.append("ack", target=target, id="a")
        with target.open("ab") as handle:
            handle.write(b"\xff\xfe not utf-8\n")
        self.assertEqual(ledger.acked(target), frozenset({"a"}))


class AppendReportsWhatHappened(unittest.TestCase):
    """`append` returns whether the record landed, and never raises doing it.

    Both halves are review findings. Four statements sat above the `try` --
    `json.dumps` among them -- so an unserializable field raised `TypeError`
    into `do_POST` between `actions.run` and `send_body`, turning a mutation
    that had already happened into a 500. And the ack endpoint answered 200 to
    a write that never landed, so the row vanished and came back on the next
    poll with nothing said.
    """

    def target(self) -> pathlib.Path:
        import tempfile
        directory = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, directory, True)
        return pathlib.Path(directory) / "ledger.jsonl"

    def test_a_field_json_cannot_encode_returns_false_and_does_not_raise(self) -> None:
        self.assertIs(ledger.append("mutation", target=self.target(), x=object()), False)

    def test_an_unwritable_destination_returns_false(self) -> None:
        self.assertIs(
            ledger.append("ack", target=pathlib.Path("/proc/nope/l.jsonl"), id="a"),
            False)

    def test_a_landed_record_returns_true(self) -> None:
        self.assertIs(ledger.append("ack", target=self.target(), id="a"), True)


if __name__ == "__main__":
    unittest.main()
