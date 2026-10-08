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
import sd_ship_body  # noqa: E402

TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"


def normalize(body: str, item: int | None = 7, **flags) -> tuple[str, tuple[str, ...]]:
    return sd_ship_body.normalize(body, item, **flags)


class NormalizeTests(unittest.TestCase):
    def test_lines_that_agree_are_stripped_and_named(self) -> None:
        body = "Summary.\n\nItem: sd:7\nWork: sd:7\nDelivers: sd:7\nRefs: sd:8\n"
        text, stripped = normalize(body)
        self.assertEqual("Summary.\n\nRefs: sd:8", text)
        self.assertEqual(("Item: sd:7", "Work: sd:7", "Delivers: sd:7"), stripped)

    def test_an_authored_with_line_is_prose_the_body_keeps(self) -> None:
        """sd:3014: sd-ship owns no attribution line, so the body keeps it unread."""
        self.assertEqual(("Summary.\n\nAuthored-with: nobody", ()), normalize("Summary.\n\nAuthored-with: nobody\n"))

    def test_a_stray_item_work_or_delivers_line_is_stripped_not_refused(self) -> None:
        """sd:2999: sd-ship writes the links itself, so another item's line is dropped."""
        body = "Summary.\n\nItem: sd:9\nWork: sd:70\nDelivers: sd:7\nDelivers: sd:8\n"
        self.assertEqual(("Summary.", ("Item: sd:9", "Work: sd:70", "Delivers: sd:7", "Delivers: sd:8")),
                         normalize(body))

    def test_a_closes_line_naming_the_claimed_item_is_refused(self) -> None:
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

    def test_a_closes_line_in_a_fence_or_a_comment_is_an_example_and_never_closes(self) -> None:
        """A quoted `Closes:` closed sd:8 on merge, even with --associate-only (late-reviews review)."""
        bodies = {
            "backtick fence": "Example only:\n```text\nCloses: sd:8\n```\n",
            "tilde fence": "Example only:\n~~~~\nCloses: sd:8\n~~~\n~~~~\n",
            "unclosed fence": "Example only:\n```\nCloses: sd:8\n",
            "comment": "Summary.\n<!-- for example\nCloses: sd:8\n-->\n",
            "comment opened mid-line": "Summary. <!--\nCloses: sd:8 -->\n",
        }
        for name, body in bodies.items():
            with self.subTest(name):
                self.assertEqual((), sd_ship_body.closes_named(body, 7))
                self.assertEqual(body, sd_ship_body.strip_closes(body))
                with self.assertRaisesRegex(ship.Refusal, r"`Closes: sd:8[^`]*`; a code block or comment holds it"):
                    normalize(body)
                indented = body.replace("\nCloses: sd:8", "\n    Closes: sd:8")
                self.assertEqual((indented.rstrip(), ()), normalize(indented))

    def test_a_column_zero_closes_line_outside_fences_and_comments_still_counts(self) -> None:
        body = ("Summary.\n```sh\necho done\n```\n<!-- a note -->\n<!--\nRefs: sd:3\n-->\n"
                "Closes: sd:8\n~~~\n    Closes: sd:9\n~~~\n")
        kept, stripped = normalize(body)
        self.assertEqual((body.rstrip(), ()), (kept, stripped))
        self.assertEqual((8,), sd_ship_body.closes_named(kept, 7))
        self.assertNotIn("\nCloses: sd:8\n", sd_ship_body.strip_closes(kept))
        self.assertIn("    Closes: sd:9", sd_ship_body.strip_closes(kept))

    def test_quoted_lines_follow_commonmark_fences(self) -> None:
        body = "a\n````md\n```\nb\n```\n````\nc\n```x`y\nd\n"
        # The four-backtick fence holds lines 2-6; three backticks do not close
        # it, and a backtick fence's info string cannot hold a backtick.
        self.assertEqual({2, 3, 4, 5, 6}, sd_ship_body.quoted_lines(body))

    def test_a_stripped_line_between_blank_lines_leaves_one_gap(self) -> None:
        self.assertEqual("A\n\nB", normalize("A\n\nWork: sd:7\n\nB\n")[0])
        self.assertEqual("A\n\n\nB", normalize("A\n\n\nB\n")[0])

    def test_every_problem_is_named_in_one_refusal(self) -> None:
        with self.assertRaises(ship.Refusal) as caught:
            normalize("Closes: sd:7\nx\nCloses: #12\n")
        self.assertIn("line 1:", str(caught.exception))
        self.assertIn("line 3:", str(caught.exception))

    def test_an_indented_line_is_prose_and_stays_with_an_item(self) -> None:
        body = "Example:\n\n    Item: sd:9\n"
        self.assertEqual(("Example:\n\n    Item: sd:9", ()), normalize(body))

    def test_with_no_item_every_column_zero_owned_line_is_stripped(self) -> None:
        """sd:2999: a no-item body owns nothing, so its stray links are dropped, not refused."""
        for line in ("Work: sd:9", "Item: sd:9", "Delivers: sd:9", "Closes: sd:9"):
            with self.subTest(line=line):
                self.assertEqual(("Proposed change", (line,)), normalize(f"Proposed change\n\n{line}\n", None))
        self.assertEqual(("Proposed change\n\n Work : sd:9\n", ()), normalize("Proposed change\n\n Work : sd:9\n", None))
        self.assertEqual(("Plain.\n", ()), normalize("Plain.\n", None))

    def test_normalize_is_a_fixpoint_and_the_published_body_round_trips(self) -> None:
        bodies = ("Summary.", "Summary.\n", "Summary.\n\nWork: sd:7\n", "A\n\nItem: sd:7\n\nB\n\n\n",
                  "Summary.\r\n\r\nWork: sd:7\r\n", "Work: sd:7", "", "Refs: sd:8\nItem: sd:7",
                  "Summary.\n\nCloses: sd:8\nItem: sd:7\n")
        for body in bodies:
            with self.subTest(body=body):
                once, _ = normalize(body)
                self.assertEqual(once, normalize(once)[0])
                published = sd_ship_body.published(once, 7)
                self.assertEqual(once, normalize(published)[0])
                self.assertEqual(published, sd_ship_body.published(normalize(published)[0], 7))

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

    def test_a_different_item_in_the_body_file_is_dropped_and_the_own_link_written(self) -> None:
        body = self.directory / "body.md"
        body.write_text(f"A slice.\n\nWork: sd:{self.item + 1}\n")
        result = self.prepare("--body-file", str(body))
        self.assertEqual(("ready_to_send", [f"Work: sd:{self.item + 1}"]), (result["phase"], result["normalized"]))
        self.assertEqual(f"A slice.\n\nWork: sd:{self.item}\n", self.live().body)


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

    def pull_request(self, body: str) -> int:
        """A pull request opened by hand on another branch."""
        self.remote.commit_on("elsewhere", "a hand-opened change\n\nAuthored-with: human")
        return self.remote.open_pull_request("elsewhere", title="by hand", body=body).number

    def test_the_verb_prints_the_published_body_and_its_lint(self) -> None:
        before = self.database.read_bytes()
        code, result = self.body("A slice.\n\nWork: sd:7\n")
        self.assertEqual(0, code, result)
        self.assertEqual("A slice.\n\nWork: sd:7\n", result["body"])
        self.assertEqual(["Work: sd:7"], result["normalized"])
        self.assertEqual(0, result["lint"]["exit"])
        self.assertIn("sd-docs-lint: clean", result["lint"]["output"])
        self.assertEqual(before, self.database.read_bytes())
        self.assertEqual([], self.remote.calls)

    def test_the_verb_exits_nonzero_on_a_refusal(self) -> None:
        code, result = self.body("A slice.\n\nCloses: sd:7\n")
        self.assertEqual(3, code)
        self.assertIn("line 3: `Closes: sd:7`; expected", result["error"])

    def test_a_ci_diff_with_no_scope_line_passes_the_verb(self) -> None:
        self.policy()
        (self.root / ".github/workflows").mkdir(parents=True, exist_ok=True)
        (self.root / ".github/workflows/ci.yml").write_text("on: push\n")
        _git(self.root, "add", ".github/workflows")
        _git(self.root, "commit", "-m", "touch the CI surface\n\nAuthored-with: human")
        code, result = self.body("A slice.\n")
        self.assertEqual(0, code, result)  # sd:2999: no scope line is required
        self.assertNotIn("CI/review scope:", result["lint"]["output"])  # rule 8 is retired
        self.assertNotIn("scope", result)  # nothing reads the demanded scope lines any more

    def test_a_given_pull_request_is_linted_on_its_live_body_alone(self) -> None:
        # sd:1877: the live body is the one read; sd:2999: its file listing is not.
        number = self.pull_request("Opened by hand.\r\n")
        code, result = self.run_verb("--pr", str(number))
        self.assertEqual(0, code, result)
        self.assertEqual(("live_pr", "Opened by hand.\n\nWork: sd:7\n"), (result["body_source"], result["body"]))
        self.assertNotIn("scope", result)
        self.assertFalse([call for call in self.remote.calls if call.path.split("?")[0].endswith("/files")])

    def test_a_pull_request_github_does_not_have_is_a_refusal(self) -> None:
        code, result = self.run_verb("--pr", "99")
        self.assertEqual(3, code)
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
