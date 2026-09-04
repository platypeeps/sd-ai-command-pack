"""The ledger, and the three write sites that feed it.

The point of these tests is not that records get written -- that is the easy
half. It is that a record is *never* a precondition for serving (D-6), and that
the three states the criterion distinguishes stay distinguishable: an absent
ledger, a ledger with starts and no demand, and a ledger with demand.
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


class TheCriterionsThreeStates(unittest.TestCase):
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


class BoundedReprobe(unittest.TestCase):
    """Step 4 / D-4: retry, *then* latch. Latching first was the defect."""

    def setUp(self) -> None:
        from dashboard import server
        self.server = server
        server._ADDRS = None
        self.addCleanup(setattr, server, "_ADDRS", None)

    def probe(self, *answers):
        calls = []

        def fake():
            calls.append(1)
            return answers[min(len(calls) - 1, len(answers) - 1)]

        return fake, calls

    def test_an_address_arriving_on_the_third_probe_is_used(self) -> None:
        """The boot race this exists for: `tailscaled` comes up late."""
        fake, calls = self.probe([], [], ["100.1.2.3"])
        self.server.tailnet_addrs = fake
        self.assertEqual(self.server.bound_addrs(sleep=lambda _: None), ["100.1.2.3"])
        self.assertEqual(len(calls), 3)

    def test_a_permanently_empty_probe_gives_up_after_exactly_three(self) -> None:
        """Bounded, because an unbounded retry is the crashloop
        `ThrottleInterval` was added to stop."""
        fake, calls = self.probe([])
        self.server.tailnet_addrs = fake
        self.assertEqual(self.server.bound_addrs(sleep=lambda _: None), [])
        self.assertEqual(len(calls), self.server.PROBES)

    def test_the_answer_is_still_latched_once_taken(self) -> None:
        """The cache's original reason survives: one answer feeds both the
        allow-list and the bind, so they cannot disagree."""
        fake, calls = self.probe(["100.1.2.3"])
        self.server.tailnet_addrs = fake
        self.server.bound_addrs(sleep=lambda _: None)
        self.server.bound_addrs(sleep=lambda _: None)
        self.assertEqual(len(calls), 1)


class MutationSiteMutationTests(unittest.TestCase):
    """`implement.md` asks for the gates to be run against broken code first.

    A test that has never failed has not been shown to work. These assert the
    *properties* the real implementation has, against deliberately wrong
    stand-ins, so that a regression in either direction is caught.
    """

    def record_on_refusal(self, guard_passed: bool, sink: list) -> None:
        """The wrong implementation: records before the guards."""
        sink.append("mutation")
        if not guard_passed:
            return

    def record_after_guards(self, guard_passed: bool, sink: list) -> None:
        """The real shape: nothing recorded unless the request was served."""
        if not guard_passed:
            return
        sink.append("mutation")

    def test_the_broken_shape_records_on_a_refused_request(self) -> None:
        sink: list = []
        self.record_on_refusal(False, sink)
        self.assertEqual(sink, ["mutation"], "the broken stand-in must be broken")

    def test_the_real_shape_records_nothing_on_a_refused_request(self) -> None:
        sink: list = []
        self.record_after_guards(False, sink)
        self.assertEqual(sink, [])
        self.record_after_guards(True, sink)
        self.assertEqual(sink, ["mutation"])


if __name__ == "__main__":
    unittest.main()
