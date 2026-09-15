"""The persona enumeration reads zizmor, and a stale decision cannot survive it.

`.github/scripts/check-zizmor-personas.py` is the answer to a list that could
go stale: the three findings zizmor's default persona drops were written down
in one sentence in a tracked-work note and nowhere that runs, so a fourth one
would have arrived in silence and a fixed one would have left its description
behind (item 876).

The reconciliation itself runs against real zizmor, in `make audit` and in the
`lint` job -- not here. A recorded copy of a real run committed under
`tests/fixtures/` would be a second list of the same three, ageing the same
way, which is the thing being removed. What is asserted here is the machinery
that list-free answer depends on:

* `gated()` keeps exactly the findings whose persona is not the default one,
  because that set is the definition of "what the gate drops";
* `primary()` picks the one location a finding points at and refuses a shape it
  has not been read against, rather than guessing and keying on the wrong text;
* `reconcile()` reports both directions, since a decision with no finding is
  the failure that lets the next reader believe a reason that no longer applies;
* `render_route()` makes the key a route rather than a line number, so editing
  anything above a finding does not fail the run;
* and every entry of `DECIDED` is distinct, reasoned, and about a workflow that
  is in this checkout.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import pathlib
import sys
import unittest
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".github/scripts/check-zizmor-personas.py"


def load() -> Any:
    """The script as a module. Its name has a hyphen, so it is loaded by path.

    Registered in `sys.modules` before it runs, as the `bin/` tools are: the
    script's dataclasses resolve their own annotations through the module they
    were declared in, and an unregistered one is not there to resolve.
    """

    name = "check_zizmor_personas"
    loader = importlib.machinery.SourceFileLoader(name, str(SCRIPT))
    spec = importlib.util.spec_from_file_location(name, str(SCRIPT), loader=loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


personas = load()


def finding(ident: str, persona: str, *, route: str = "unittest", feature: str = "unittest",
            severity: str = "Informational", row: int = 16,
            extra_locations: tuple[dict, ...] = ()) -> dict:
    """One finding in the shape `zizmor --format=json-v1` emits."""

    def location(kind: str, feature_text: str) -> dict:
        return {
            "symbolic": {
                "key": {"Local": {"verbatim_path": ".github/workflows/tests.yml"}},
                "route": {"route": [{"Key": "jobs"}, {"Key": route}]},
                "kind": kind,
            },
            "concrete": {
                "feature": feature_text,
                "location": {"start_point": {"row": row, "column": 2}},
            },
        }

    return {
        "ident": ident,
        "determinations": {"confidence": "High", "severity": severity, "persona": persona},
        "locations": [*extra_locations, location("Primary", feature)],
    }


class TheRoute(unittest.TestCase):
    def test_a_route_of_keys_reads_as_a_path(self) -> None:
        self.assertEqual(
            personas.render_route([{"Key": "jobs"}, {"Key": "lint"}]), "/jobs/lint")

    def test_an_index_in_the_route_keeps_its_position(self) -> None:
        # A step is addressed by number, and a finding on one must key on which
        # step it was, not on the first step of the job.
        self.assertEqual(
            personas.render_route([{"Key": "jobs"}, {"Key": "lint"}, {"Key": "steps"},
                                   {"Index": 4}]),
            "/jobs/lint/steps/4")

    def test_a_route_that_is_not_a_list_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            personas.render_route({"Key": "jobs"})

    def test_a_component_with_two_keys_is_refused(self) -> None:
        # Guessing which of the two names the position would key findings on
        # whichever one `dict` happened to yield first.
        with self.assertRaises(ValueError):
            personas.render_route([{"Key": "jobs", "Index": 1}])


class ThePrimaryLocation(unittest.TestCase):
    def setUp(self) -> None:
        self.related = {
            "symbolic": {
                "key": {"Local": {"verbatim_path": ".github/workflows/tests.yml"}},
                "route": {"route": [{"Key": "jobs"}, {"Key": "unittest"}]},
                "kind": "Related",
            },
            "concrete": {"feature": "unittest", "location": {"start_point": {"row": 16}}},
        }
        self.hidden = dict(self.related,
                           symbolic=dict(self.related["symbolic"], kind="Hidden"))

    def test_the_related_and_hidden_locations_are_not_the_key(self) -> None:
        # `secrets-outside-env` hands back the whole job as a Hidden location,
        # whose text is every line of it. Keying on that would make the finding
        # a different finding after any edit anywhere inside the job.
        found = personas.key_of(finding(
            "secrets-outside-env", "Auditor", feature="secrets.SYSTEM_REPO_TOKEN",
            extra_locations=(self.hidden, self.related)))
        self.assertEqual(found.feature, "secrets.SYSTEM_REPO_TOKEN")

    def test_a_finding_with_no_primary_location_stops_the_run(self) -> None:
        with self.assertRaises(ValueError) as caught:
            personas.primary({"ident": "made-up", "locations": [self.related]})
        self.assertIn("0 primary locations", str(caught.exception))

    def test_a_finding_with_two_primary_locations_stops_the_run(self) -> None:
        # The stop is the point: a zizmor whose output has grown a second
        # primary is one this script has not been read against, and picking
        # either would key half the findings on the wrong text without saying so.
        doubled = finding("made-up", "Auditor")
        doubled["locations"] = [*doubled["locations"], *doubled["locations"]]
        with self.assertRaises(ValueError) as caught:
            personas.primary(doubled)
        self.assertIn("2 primary locations", str(caught.exception))


class TheGatedSet(unittest.TestCase):
    def test_a_finding_the_default_persona_reports_is_not_gated(self) -> None:
        # This is the whole definition. A `Regular` finding reddens the plain
        # gate beside this one, so it is not something to hold a reason for.
        self.assertEqual(
            personas.gated([finding("template-injection", personas.DEFAULT_PERSONA)]), [])

    def test_a_finding_above_the_default_persona_is_gated(self) -> None:
        found = personas.gated([finding("anonymous-definition", "Pedantic")])
        self.assertEqual([item.key.ident for item in found], ["anonymous-definition"])
        self.assertEqual(found[0].persona, "Pedantic")

    def test_both_personas_above_the_default_are_gated(self) -> None:
        # Pedantic and Auditor are two different personas and the gate drops
        # both; a check that knew only the one it was written against would
        # pass on a finding it had never seen.
        found = personas.gated([finding("anonymous-definition", "Pedantic"),
                                finding("secrets-outside-env", "Auditor")])
        self.assertEqual([item.persona for item in found], ["Pedantic", "Auditor"])

    def test_the_reported_line_is_the_one_a_reader_would_open(self) -> None:
        # zizmor counts rows from zero and prints them from one. Off by one,
        # every line this prints points at the line above the finding.
        found = personas.gated([finding("anonymous-definition", "Pedantic", row=16)])
        self.assertEqual(found[0].line, 17)
        self.assertEqual(found[0].path_line, ".github/workflows/tests.yml:17")


class TheReconciliation(unittest.TestCase):
    def setUp(self) -> None:
        self.found = personas.gated([finding("anonymous-definition", "Pedantic")])
        self.decision = personas.Decision(key=self.found[0].key, reason="because")

    def test_a_finding_and_its_decision_agree(self) -> None:
        self.assertEqual(personas.reconcile(self.found, (self.decision,)), ([], []))

    def test_a_finding_nobody_decided_is_reported(self) -> None:
        undecided, unfound = personas.reconcile(self.found, ())
        self.assertEqual(undecided, self.found)
        self.assertEqual(unfound, [])

    def test_a_decision_nothing_found_is_reported(self) -> None:
        # The direction that would otherwise rot quietly: the finding is fixed
        # or the audit is retired, and a reason for it sits here being read.
        undecided, unfound = personas.reconcile([], (self.decision,))
        self.assertEqual(undecided, [])
        self.assertEqual(unfound, [self.decision])

    def test_a_decision_for_the_wrong_job_does_not_cover_the_finding(self) -> None:
        # Two `anonymous-definition` findings differ only by route, so a key
        # that dropped the route would let one decision answer for both.
        elsewhere = personas.Decision(
            key=personas.Key(ident="anonymous-definition",
                             path=".github/workflows/tests.yml",
                             route="/jobs/lint", feature="lint"),
            reason="because")
        undecided, unfound = personas.reconcile(self.found, (elsewhere,))
        self.assertEqual(undecided, self.found)
        self.assertEqual(unfound, [elsewhere])


class TheDecisionTable(unittest.TestCase):
    def test_the_table_is_not_empty(self) -> None:
        # An empty table passes reconciliation against an empty run, so the
        # day zizmor's output stops parsing this would be green and silent.
        self.assertTrue(personas.DECIDED)

    def test_every_key_is_distinct(self) -> None:
        keys = [decision.key for decision in personas.DECIDED]
        self.assertEqual(len(set(keys)), len(keys))

    def test_every_decision_gives_a_reason(self) -> None:
        for decision in personas.DECIDED:
            with self.subTest(key=str(decision.key)):
                # A word or two is an entry made to clear the check. The
                # shortest real one here names what the audit wants and what
                # stands in for it.
                self.assertGreater(len(decision.reason.split()), 20)

    def test_every_decision_is_about_a_workflow_in_this_checkout(self) -> None:
        for decision in personas.DECIDED:
            with self.subTest(key=str(decision.key)):
                self.assertTrue((REPO_ROOT / decision.key.path).is_file(),
                                f"{decision.key.path} is not a file here")

    def test_every_decision_names_a_job_this_workflow_defines(self) -> None:
        # The route's second component is the job key. A decision naming a job
        # that was renamed or deleted is answering for nothing, and would be
        # caught by the live run -- but only on a machine that has zizmor.
        for decision in personas.DECIDED:
            job = decision.key.route.split("/")[2]
            text = (REPO_ROOT / decision.key.path).read_text(encoding="utf-8")
            with self.subTest(key=str(decision.key)):
                self.assertIn(f"\n  {job}:\n", text)


class TheBinaryItRuns(unittest.TestCase):
    def test_a_path_to_a_file_is_taken_as_given(self) -> None:
        # `make audit` hands over the pinned copy in the virtualenv by path.
        self.assertEqual(personas.locate(str(SCRIPT)), str(SCRIPT))

    def test_a_name_on_path_is_taken(self) -> None:
        # The `lint` job hands over a bare name, because the pinned copy is
        # what PATH resolves there.
        self.assertEqual(personas.locate("sh"), "sh")

    def test_a_name_that_is_neither_is_not_invented(self) -> None:
        self.assertIsNone(personas.locate("zizmor-that-is-not-installed-anywhere"))

    def test_a_missing_binary_is_an_error_and_never_a_green_skip(self) -> None:
        # Both callers reach the script only down an arm that already found
        # zizmor, so a miss means the binary moved between the gate and this.
        # Reporting zero here would certify an enumeration of nothing.
        with contextlib.redirect_stderr(io.StringIO()) as said:
            code = personas.main(["check-zizmor-personas.py", "--zizmor",
                                  "zizmor-that-is-not-installed-anywhere"])
        self.assertEqual(code, 2)
        self.assertIn("cannot run", said.getvalue())


class TheLanesThatRunIt(unittest.TestCase):
    """Nothing above this reaches real zizmor, so the two lanes that do are pinned.

    Deleting either call is a change with no other symptom: every test in this
    file still passes, the plain gate still says "3 suppressed", and the
    enumeration simply stops happening. A `run:` line and a recipe line are all
    there is to assert, and asserting them is cheaper than losing the check to
    a tidy-up.
    """

    def run_lines(self, path: str) -> list[str]:
        return [line.strip() for line in
                (REPO_ROOT / path).read_text(encoding="utf-8").splitlines()
                if SCRIPT.name in line and not line.lstrip().startswith("#")]

    def test_the_ci_lint_job_runs_it(self) -> None:
        lines = self.run_lines(".github/workflows/tests.yml")
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(lines[0].startswith("run: "), lines[0])

    def test_make_audit_runs_it(self) -> None:
        # Once per arm of the zizmor lookup: the pinned copy in the virtualenv
        # and the unpinned one on PATH. An arm that runs the gate without the
        # enumeration is a machine where this silently does not happen.
        self.assertEqual(len(self.run_lines("Makefile")), 2)


if __name__ == "__main__":
    unittest.main()
