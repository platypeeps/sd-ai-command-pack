"""The body `sd-ship` publishes is a body it accepts back (sd:1870).

`prepare` appended `Work: sd:<item>` to the body it published and refused a
`--body-file` carrying that same line, so the live body of #1236 and #1238,
fed back, was refused. `sd_ship_body.normalize` strips an owned line that
says what `sd-ship` would write and refuses the rest by line number. The
cases below run the unit, `prepare` on the shared fixture, the `body` verb
as a process, and the pull-request template.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import unittest

from sd_db.testing.remote import _git

from tests import test_sd_ship as ship_fixture
from tests import test_sd_ship_scope_lint as scope_fixture

ship = ship_fixture.ship
ROOT = pathlib.Path(__file__).resolve().parents[1]

import sd_lib  # noqa: E402 - bin/ is on sys.path once the fixture module loads
import sd_registry  # noqa: E402
import sd_ship_body  # noqa: E402

READERS = [sd_registry.read_file(ROOT / "providers.yaml")]
TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"


def normalize(body: str, item: int | None = 7, **flags) -> tuple[str, tuple[str, ...]]:
    return sd_ship_body.normalize(body, item, readers=READERS, **flags)


class NormalizeTests(unittest.TestCase):
    def test_lines_that_agree_are_stripped_and_named(self) -> None:
        body = ("Summary.\n\nItem: sd:7\nWork: sd:7\nDelivers: sd:7\n"
                "Authored-with: claude/anthropic\nAuthored-with: human\nRefs: sd:8\n")
        text, stripped = normalize(body, deliver=True)
        self.assertEqual("Summary.\n\nRefs: sd:8", text)
        self.assertEqual(("Item: sd:7", "Work: sd:7", "Delivers: sd:7",
                          "Authored-with: claude/anthropic", "Authored-with: human"), stripped)

    def test_another_item_is_refused_by_line_with_the_expected_value(self) -> None:
        with self.assertRaisesRegex(ship.Refusal, re.escape("line 3: `Item: sd:9`; expected `Item: sd:7`")):
            normalize("Summary.\n\nItem: sd:9\n")
        with self.assertRaisesRegex(ship.Refusal, re.escape("line 1: `Work: sd:70`; expected `Work: sd:7`")):
            normalize("Work: sd:70\n")

    def test_delivers_needs_the_delivery_claim(self) -> None:
        with self.assertRaisesRegex(ship.Refusal, r"line 2: `Delivers: sd:7`; expected no line: delivery is claimed with --deliver"):
            normalize("Summary.\nDelivers: sd:7\n")
        self.assertEqual(("Delivers: sd:7",), normalize("Summary.\nDelivers: sd:7\n", deliver=True)[1])

    def test_an_author_no_registry_resolves_is_refused(self) -> None:
        for value in ("nobody/anthropic", "claude/openai", "claude"):
            with self.subTest(value=value), self.assertRaisesRegex(ship.Refusal, r"line 1: .*registry resolves"):
                normalize(f"Authored-with: {value}\n")

    def test_attributes_and_a_closes_line_naming_the_claimed_item_are_refused(self) -> None:
        with self.assertRaisesRegex(ship.Refusal, r"line 1: `Attributes: 0123456 claude/anthropic`; expected no line: it names a pre-squash sha"):
            normalize("Attributes: 0123456 claude/anthropic\n")
        with self.assertRaisesRegex(ship.Refusal, r"line 1: `Closes: sd:7`; expected `Closes: sd:<n>\[, sd:<m>\]` naming co-delivered items other than sd:7"):
            normalize("Closes: sd:7\n")
        for value in ("sd:8, sd:7", "#12", "sd:08", ""):
            with self.subTest(value=value), self.assertRaisesRegex(ship.Refusal, r"line 1: `Closes:"):
                normalize(f"Closes: {value}\n")

    def test_a_closes_line_naming_other_items_stays_in_the_body(self) -> None:
        """sd:1481: the merge reads `Closes:` from the body, so normalize keeps it."""
        body = "Summary.\n\nCloses: sd:8, sd:9\nCloses: sd:9,sd:10\n    Closes: sd:11\nRefs: sd:12\n"
        kept, stripped = normalize(body)
        self.assertEqual(body.rstrip(), kept)
        self.assertEqual((), stripped)
        self.assertEqual((8, 9, 10), sd_ship_body.closes_named(kept, 7))
        self.assertEqual((), sd_ship_body.closes_named(kept, None))
        self.assertEqual("Summary.\n\n    Closes: sd:11\nRefs: sd:12", sd_ship_body.strip_closes(kept))

    def test_a_stripped_line_between_blank_lines_leaves_one_gap(self) -> None:
        self.assertEqual("A\n\nB", normalize("A\n\nWork: sd:7\n\nB\n")[0])
        self.assertEqual("A\n\n\nB", normalize("A\n\n\nB\n")[0])

    def test_every_problem_is_named_in_one_refusal(self) -> None:
        with self.assertRaises(ship.Refusal) as caught:
            normalize("Item: sd:1\nx\nWork: sd:2\n")
        self.assertIn("line 1:", str(caught.exception))
        self.assertIn("line 3:", str(caught.exception))

    def test_an_indented_line_is_prose_and_stays_with_an_item(self) -> None:
        body = "Example:\n\n    Item: sd:9\n"
        self.assertEqual(("Example:\n\n    Item: sd:9", ()), normalize(body))

    def test_with_no_item_every_owned_line_refuses_and_nothing_is_stripped(self) -> None:
        for line in ("Work: sd:9", "Item: sd:9", " Work : sd:9", "authored-with: human", "Closes: sd:9"):
            with self.subTest(line=line), self.assertRaisesRegex(ship.Refusal, r"no-item publication .*line 3:"):
                normalize(f"Proposed change\n\n{line}\n", None)
        self.assertEqual(("Plain.\n", ()), normalize("Plain.\n", None))

    def test_normalize_is_a_fixpoint_and_the_published_body_round_trips(self) -> None:
        bodies = ("Summary.", "Summary.\n", "Summary.\n\nWork: sd:7\n", "A\n\nItem: sd:7\n\nB\n\n\n",
                  "Summary.\r\n\r\nWork: sd:7\r\n", "Work: sd:7", "", "Refs: sd:8\nItem: sd:7",
                  "Summary.\n\nCloses: sd:8\nItem: sd:7\n")
        for body in bodies:
            with self.subTest(body=body):
                once, _ = normalize(body, deliver=True)
                self.assertEqual(once, normalize(once, deliver=True)[0])
                published = sd_ship_body.published(once, 7)
                self.assertEqual(once, normalize(published)[0])
                self.assertEqual(published, sd_ship_body.published(normalize(published)[0], 7))

    def test_a_pull_request_rename_names_both_of_its_paths(self) -> None:
        files = [{"filename": "ci/ci.yml", "previous_filename": ".github/workflows/ci.yml"},
                 {"filename": "src.py"}, {"filename": "src.py"}, "not a row"]
        self.assertEqual([".github/workflows/ci.yml", "ci/ci.yml", "src.py"], sd_ship_body.pull_paths(files))

    def test_the_parser_reads_the_one_constant(self) -> None:
        body = "".join(f"{key} sd:7\n" for key in sd_lib.OWNED_TRAILERS)
        self.assertEqual(list(sd_lib.OWNED_TRAILERS), [line.key for line in sd_ship_body.owned_lines(body)])


class TemplateTests(unittest.TestCase):
    def test_the_template_writes_no_owned_trailer_outside_a_comment(self) -> None:
        text = re.sub(r"<!--.*?-->", "", TEMPLATE.read_text(encoding="utf-8"), flags=re.DOTALL)
        self.assertEqual([], [line.text for line in sd_ship_body.owned_lines(text)])
        self.assertIn("Refs: sd:<other>", text)


class PrepareTests(unittest.TestCase):
    setUp = ship_fixture.ShipCase.setUp
    args = ship_fixture.ShipCase.args
    operation = ship_fixture.ShipCase.operation
    prepare = ship_fixture.ShipCase.prepare

    def live(self):
        number = self.operation().state["pull_request"]["number"]
        return self.remote.pull_requests[number]

    def again(self, *extra):
        _git(self.root, "commit", "--allow-empty", "-m", "another slice\n\nAuthored-with: human")
        return self.prepare(*extra)

    def test_the_live_body_fed_back_as_a_body_file_prepares(self) -> None:
        body = self.directory / "body.md"
        body.write_text("A slice.\n")
        first = self.prepare("--body-file", str(body))
        published = self.live().body
        self.assertIn(f"\nWork: sd:{self.item}\n", published)
        body.write_text(published)
        second = self.again("--body-file", str(body))
        self.assertEqual("ready_to_send", second["phase"])
        self.assertEqual(published, self.operation().state["body"])
        self.assertEqual(("file", []), (first["body_source"], first["normalized"]))
        self.assertEqual([f"Work: sd:{self.item}"], second["normalized"])

    def test_an_edit_made_on_github_is_prepared_from_the_live_body(self) -> None:
        self.prepare()
        self.live().body = f"Edited on GitHub.\r\n\r\nCI/review scope: none.\r\n\r\nWork: sd:{self.item}\r\n"
        result = self.again()
        self.assertEqual(f"Edited on GitHub.\n\nCI/review scope: none.\n\nWork: sd:{self.item}\n",
                         self.operation().state["body"])
        self.assertEqual("live_pr", result["body_source"])

    def test_a_hand_opened_pull_request_without_a_receipt_is_prepared_from_its_live_body(self) -> None:
        # sd:1878: no receipt names the pull request, so before this the
        # default body was reviewed and squashed while GitHub showed another.
        _git(self.root, "push", "-q", "origin", "HEAD:refs/heads/topic")
        written = f"Opened by hand.\r\n\r\nCI/review scope: none.\r\n\r\nWork: sd:{self.item}\r\n"
        pull = self.remote.open_pull_request("topic", title="by hand", body=written)
        self.remote.commit_on("elsewhere", "another branch\n\nAuthored-with: human")
        self.remote.open_pull_request("elsewhere", title="another branch", body="Not this one.\n")
        result = self.prepare()
        self.assertEqual(("live_pr", [f"Work: sd:{self.item}"]), (result["body_source"], result["normalized"]))
        self.assertEqual(f"Opened by hand.\n\nCI/review scope: none.\n\nWork: sd:{self.item}\n",
                         self.operation().state["body"])
        self.assertEqual(pull.number, self.operation().state["pull_request"]["number"])

    def test_a_blank_hand_opened_body_falls_back_to_the_default(self) -> None:
        _git(self.root, "push", "-q", "origin", "HEAD:refs/heads/topic")
        self.remote.open_pull_request("topic", title="by hand", body="  \n")
        self.assertEqual("default", self.prepare()["body_source"])

    def test_a_different_item_in_the_body_file_is_refused_before_anything_is_pushed(self) -> None:
        body = self.directory / "body.md"
        body.write_text(f"A slice.\n\nWork: sd:{self.item + 1}\n")
        with self.assertRaisesRegex(ship.Refusal, rf"line 3: `Work: sd:{self.item + 1}`; expected `Work: sd:{self.item}`"):
            self.prepare("--body-file", str(body))
        self.assertEqual({}, self.remote.pull_requests)


class BodyVerbTests(unittest.TestCase):
    setUp = ship_fixture.ShipCase.setUp

    def run_verb(self, *extra: str) -> tuple[int, dict]:
        done = subprocess.run([sys.executable, str(ROOT / "bin/sd-ship"), "body", "--item", "7", "--json", *extra],
                              cwd=self.root, env=self.environment, capture_output=True, text=True,
                              timeout=ship_fixture.CLI_TIMEOUT, check=False)
        return done.returncode, json.loads(done.stdout)

    def body(self, text: str, *extra: str) -> tuple[int, dict]:
        path = self.directory / "body.md"
        path.write_text(text)
        return self.run_verb("--body-file", str(path), *extra)

    def policy(self) -> None:
        """The scope policy in the working tree only, so the checkout's own diff stays empty."""
        policy = self.root / ".github/copilot-instructions.md"
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text(scope_fixture.SCOPE_POLICY)

    def pull_request(self, body: str, files: list[dict]) -> int:
        """A pull request opened by hand on another branch, and the files GitHub lists for it."""
        self.remote.commit_on("elsewhere", "a hand-opened change\n\nAuthored-with: human")
        number = self.remote.open_pull_request("elsewhere", title="by hand", body=body).number
        route = self.double._route

        def files_route(method, path, payload):
            if method == "GET" and path.split("?")[0] == f"/repos/{self.remote.slug}/pulls/{number}/files":
                return 200, files
            return route(method, path, payload)
        self.double._route = files_route
        return number

    def test_the_verb_prints_the_published_body_and_its_lint(self) -> None:
        before = self.database.read_bytes()
        code, result = self.body("A slice.\n\nWork: sd:7\nAuthored-with: author/firstvendor\n")
        self.assertEqual(0, code, result)
        self.assertEqual("A slice.\n\nWork: sd:7\n", result["body"])
        self.assertEqual(["Work: sd:7", "Authored-with: author/firstvendor"], result["normalized"])
        self.assertEqual(0, result["lint"]["exit"])
        self.assertIn("rule 5 PR link: database association sd:7", result["lint"]["output"])
        self.assertEqual(before, self.database.read_bytes())
        self.assertEqual([], self.remote.calls)

    def test_the_verb_exits_nonzero_on_a_refusal(self) -> None:
        code, result = self.body("A slice.\n\nItem: sd:8\n")
        self.assertEqual(3, code)
        self.assertIn("line 3: `Item: sd:8`; expected `Item: sd:7`", result["error"])

    def test_the_verb_exits_nonzero_when_the_body_lint_fails(self) -> None:
        self.policy()
        (self.root / ".github/workflows").mkdir(parents=True, exist_ok=True)
        (self.root / ".github/workflows/ci.yml").write_text("on: push\n")
        _git(self.root, "add", ".github/workflows")
        _git(self.root, "commit", "-m", "touch the CI surface\n\nAuthored-with: human")
        code, result = self.body("A slice.\n")
        self.assertEqual(3, code, result)
        self.assertIn('carries no "CI/review scope:" line', result["lint"]["output"])
        self.assertEqual([{"line": "CI/review scope:", "path": ".github/workflows/ci.yml", "present": False}],
                         result["scope"]["demanded"])
        self.assertEqual("origin/HEAD...HEAD", result["scope"]["changed_from"])
        code, result = self.body("A slice.\n\nCI/review scope: one workflow.\n")
        self.assertEqual(0, code, result)
        self.assertEqual([{"line": "CI/review scope:", "path": ".github/workflows/ci.yml", "present": True}],
                         result["scope"]["demanded"])

    def test_a_given_pull_request_is_linted_against_its_own_files_and_live_body(self) -> None:
        # sd:1877: the pull request's diff, not the checkout's, is the one
        # read, and the answer comes before prepare refuses.
        self.policy()
        number = self.pull_request("Opened by hand.\r\n", [
            {"filename": "ci/ci.yml", "previous_filename": ".github/workflows/ci.yml", "status": "renamed"}])
        code, result = self.run_verb("--pr", str(number))
        self.assertEqual(3, code, result)
        self.assertEqual(("live_pr", "Opened by hand.\n\nWork: sd:7\n"), (result["body_source"], result["body"]))
        self.assertEqual({"changed_from": f"pull request #{number}", "changed": 2,
                          "demanded": [{"line": "CI/review scope:", "path": ".github/workflows/ci.yml",
                                        "present": False}]}, result["scope"])
        self.assertIn("touches .github/workflows/ci.yml", result["lint"]["output"])
        self.assertNotIn(".github/workflows/ci.yml", str(self.run_verb()[1]["scope"]))
        code, result = self.body("Opened by hand.\n\nCI/review scope: the workflow moves out.\n", "--pr", str(number))
        self.assertEqual((0, "file", True), (code, result["body_source"], result["scope"]["demanded"][0]["present"]))

    def test_a_pull_request_github_does_not_have_is_a_refusal(self) -> None:
        code, result = self.run_verb("--pr", "99")
        self.assertEqual(3, code)
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
