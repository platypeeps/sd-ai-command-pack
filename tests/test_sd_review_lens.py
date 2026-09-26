"""`sd-review --lens`: a research brief is attacked as an argument, by whoever the chain picks.

#1194. `sd-research-kit review` used to print a fixed `codex exec` line as the
research repo's second reader, so the registry's reviewer order was skipped and
a Codex outage blocked the pass outright. The checklist now routes through this
lane, and a lens is what keeps the research framing on the way: the prompt the
chain's provider is handed says "a markdown research brief, not code".

Three properties are pinned, each against the fixture registry rather than the
shipped one: the lens text reaches the prompt of every provider the chain
plans, a failed or disabled first reviewer hands the lensed review to the next
one, and a markdown-only change -- which the default policy routes to tier
`skip` -- is still read when a lens asks for it.
"""

from __future__ import annotations

import pathlib
import subprocess
import unittest
from typing import Any

from tests.test_sd_review import FakeRunner, sd_review
from tests.test_sd_review_fallbacks import ReviewRunFixture

LENS = "research-brief"
MARKER = "Lens: research-brief."


def planned_prompts(result: dict[str, Any]) -> list[str]:
    return [row["stdin"] for row in result["planned_invocations"] if row["would_run"]]


def session_prompt(runner: FakeRunner, program: str) -> str:
    calls = [call for call in runner.calls if call["argv"][0] == program and call["argv"][1:3] != ["debug", "prompt-input"]]
    return " ".join((call["stdin"] or "") + " ".join(call["argv"]) for call in calls)


class TheLensReachesTheProviderPromptTests(ReviewRunFixture):
    def test_every_planned_provider_is_handed_the_lens(self) -> None:
        root = self.prepare()
        result = self.run_review(root, FakeRunner(), dry_run=True, lens=LENS)
        prompts = planned_prompts(result)
        self.assertTrue(prompts, result["planned_invocations"])
        for prompt in prompts:
            self.assertIn(MARKER, prompt)
            self.assertIn("not code", prompt)
        self.assertEqual(result["lens"], LENS)

    def test_no_lens_leaves_the_code_review_prompt_alone(self) -> None:
        root = self.prepare()
        result = self.run_review(root, FakeRunner(), dry_run=True)
        for prompt in planned_prompts(result):
            self.assertNotIn(MARKER, prompt)
        self.assertIsNone(result["lens"])

    def test_the_parser_takes_the_lens_and_refuses_an_unknown_one(self) -> None:
        parser = sd_review.build_parser()
        self.assertEqual(parser.parse_args(["--lens", LENS]).lens, LENS)
        self.assertIsNone(parser.parse_args([]).lens)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--lens", "no-such-lens"])


class TheChainStillChoosesTests(ReviewRunFixture):
    def test_a_failing_first_reviewer_hands_the_lensed_review_to_the_next(self) -> None:
        root = self.prepare()
        runner = FakeRunner({"codex": sd_review.Completed(1, "", "401 Unauthorized")})
        result = self.run_review(root, runner, lens=LENS)
        self.assertEqual(result["status"], "clean")
        self.assertEqual([row["backend"] for row in result["outcomes"]], ["codex", "second"])
        self.assertEqual(result["reviewed_by"], ["second"])
        self.assertIn(MARKER, session_prompt(runner, "second"))

    def test_a_disabled_first_reviewer_is_passed_over(self) -> None:
        root = self.prepare()
        registry = self.registry_home / ".local/share/sd/providers.yaml"
        # With codex off, `second` would lead both lists and the registry
        # would refuse a review by the author, so it gives up the author role.
        text = registry.read_text().replace(
            "vendor: openai, bill: first,", 'vendor: openai, bill: first, enabled: false, reason: "fixture outage",')
        registry.write_text(text.replace("roles: [author, reviewer]", "roles: [reviewer]").replace("author: [second]", "author: []"))
        runner = FakeRunner()
        result = self.run_review(root, runner, lens=LENS)
        self.assertEqual(result["status"], "clean")
        self.assertEqual(result["reviewed_by"], ["second"])
        self.assertEqual(session_prompt(runner, "codex"), "")
        self.assertIn(MARKER, session_prompt(runner, "second"))


class ALensedMarkdownChangeIsReadTests(ReviewRunFixture):
    def brief(self) -> pathlib.Path:
        # No `.github/sd-review.json`: the built-in policy, whose `docs_skip`
        # routes a change of only `*.md` to tier `skip` and asks nobody.
        root = self.make_repo()
        (root / "brief.md").write_text("# A brief\n\nThe rate doubled.\n")
        return root

    def test_without_a_lens_a_markdown_change_is_skipped(self) -> None:
        root = self.brief()
        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", "")})
        result = self.run_review(root, runner)
        self.assertEqual(result["route"]["tier"], "skip")
        self.assertEqual(result["reviewed_by"], [])

    def test_with_the_lens_the_brief_is_read_by_the_chain(self) -> None:
        root = self.brief()
        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", "")})
        result = self.run_review(root, runner, lens=LENS)
        self.assertEqual(result["route"]["tier"], "skip")
        self.assertEqual(result["requested_reviews"], 1)
        self.assertEqual(result["reviewed_by"], ["codex"])
        self.assertIn(MARKER, session_prompt(runner, "codex"))

    def test_the_brief_is_committed_on_a_branch_too(self) -> None:
        root = self.brief()
        for argv in (["checkout", "-b", "brief"], ["add", "."], ["commit", "-m", "brief\n\nAuthored-with: human"]):
            subprocess.run(["git", *argv], cwd=root, check=True, capture_output=True)
        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", "")})
        result = self.run_review(root, runner, scope="branch", lens=LENS)
        self.assertEqual(result["requested_reviews"], 1)
        self.assertEqual(result["reviewed_by"], ["codex"])


if __name__ == "__main__":
    unittest.main()
