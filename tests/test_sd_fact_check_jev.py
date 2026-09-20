"""The optional typed verdict pass in `sd-fact-check`, asserted from the page.

The pass is additive and off by default: it runs only when the invocation
passes `jev=on` and the command reports itself available. `jev` ships from a
private companion repository and is absent on most machines that install this
pack, so the interesting failure is not the pass going wrong -- it is the skill
quietly acquiring a hole where a reader without the command finds an
instruction they cannot follow, or a report shape that assumes an answer they
never got.

Nothing here runs `jev`. These are structural checks over the markdown, which
is what the skill is.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

from tests.test_sd_agents import skill_verdicts

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "skills" / "sd-fact-check" / "SKILL.md"

#: The heading the whole opt-in lives under. Named once here so a rename fails
#: in one place instead of in every assertion below.
SECTION = "## Optional typed verdicts"

#: The no-match option, which is not one of step 6's verdicts. The `choice`
#: guidance is to carry one so the model never forces a listed name onto an
#: input none of them describes.
NO_MATCH = "not_a_factual_claim"

#: What the command prints when it reached no judgment at all. It is the
#: `--fallback` answer, and it may not be the word `--unsure-below` prints.
NOT_ASKED = "not_asked"

#: The word `--unsure-below` prints for a real answer under the threshold.
UNSURE = "unsure"

#: Every option the `choice` verb accepts, read off its usage line. A copy,
#: which is the only offline form available: the command ships from a private
#: companion repository, so its parser cannot be imported here. What the copy
#: buys is the failure it catches -- a flag misspelled in the page is an
#: instruction that exits 2 and prints nothing for the reader who runs it.
CHOICE_OPTIONS = frozenset({
    "--criteria", "--unsure-below", "--state", "--state-format",
    "--model", "--id", "--json", "--fallback",
})

FENCE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


def page() -> str:
    return SKILL.read_text(encoding="utf-8")


def heading_body(text: str, heading: str) -> str:
    """Everything under `heading`, up to the next `## ` heading.

    Anchored to the start of a line. The argument list names this section in
    running prose, and an unanchored search found that mention first and
    returned a two-line window that every assertion below then passed over.
    """

    match = re.search(rf"^{re.escape(heading)}$", text, re.MULTILINE)
    assert match, f"{heading} is not a heading in the page"
    end = re.compile(r"^## ", re.MULTILINE).search(text, match.end())
    return text[match.start():end.start() if end else len(text)]


def section_body(text: str) -> str:
    return heading_body(text, SECTION)


def fenced(text: str, language: str) -> list[str]:
    return [body for tag, body in FENCE.findall(text) if tag == language]


def criteria() -> dict[str, str]:
    """The criteria object the section tells the reader to write to a file.

    Found by its content rather than by its position: the section carries a
    second JSON block for the state, and a test that picked the first block
    would start asserting about the wrong one the day their order changes.
    """

    blocks = [json.loads(body) for body in fenced(section_body(page()), "json")]
    matching = [block for block in blocks if "supported" in block]
    assert len(matching) == 1, f"{len(matching)} criteria blocks in {SECTION}"
    return matching[0]


class TheSectionIsReachable(unittest.TestCase):
    """The bound. Every assertion below reads the section, so its absence
    must fail loudly here rather than making the rest pass over nothing."""

    def test_the_skill_carries_the_section(self) -> None:
        self.assertIn(f"\n{SECTION}\n", page())

    def test_the_section_has_a_criteria_block(self) -> None:
        self.assertIn("supported", criteria())


class TheCriteriaCarryTheVerdictVocabulary(unittest.TestCase):
    """The criteria names are step 6's verdicts, plus the no-match option.

    Read from the page on both sides. The verdict definitions come from
    `skill_verdicts`, which parses the same ladder `sd-claim-verifier` is
    compared against, so a verdict renamed in step 6 cannot leave a criterion
    behind under the old name -- which is exactly how a typed answer starts
    meaning something the ledger has no column for.
    """

    def test_the_names_are_the_verdicts_plus_the_no_match_option(self) -> None:
        expected = {name.replace(" ", "_") for name in skill_verdicts()}
        self.assertEqual(set(criteria()), expected | {NO_MATCH})

    def test_the_no_match_option_is_not_one_of_the_verdicts(self) -> None:
        """Otherwise the line above passes with the option folded into the
        ladder, and a claim the five verdicts cannot describe gets one."""

        self.assertNotIn(NO_MATCH.replace("_", " "), skill_verdicts())

    def test_every_criterion_describes_a_situation(self) -> None:
        """A name with no description is a name the model has to guess at."""

        for name, description in criteria().items():
            with self.subTest(criterion=name):
                self.assertGreater(len(description.split()), 8, description)
                self.assertTrue(description.endswith("."), description)

    def test_no_criterion_leans_on_another_to_be_understood(self) -> None:
        """Each description is sent on its own and read on its own.

        A description saying "unlike the option above" arrives in a request
        whose option order this page does not control, and a description
        naming a sibling makes two criteria one. Both read as separation on
        the page and neither separates anything in the request.

        Both spellings of a sibling are rejected. The ledger spells the names
        with underscores, and prose naming one spells it with spaces: a check
        that read the underscored form alone let "partially supported" name a
        sibling in plain English and pass. The name is what a reader reads,
        not the punctuation it is stored under.
        """

        names = set(criteria())
        for name, description in criteria().items():
            with self.subTest(criterion=name):
                lowered = description.lower()
                for phrase in ("above", "below", "the previous", "same as",
                               "step 6", "this skill"):
                    self.assertNotIn(phrase, lowered, description)
                for sibling in names - {name}:
                    for spelling in {sibling, sibling.replace("_", " ")}:
                        self.assertNotIn(spelling, lowered, description)


class ThePassIsOffByDefault(unittest.TestCase):
    """Both halves of the opt-in, stated where a reader acts on them.

    The contract is that today's behaviour is unchanged unless the invocation
    asks for the pass and the command reports itself available. A section that
    named only one of the two would leave the other to be remembered.
    """

    def test_the_argument_is_documented_and_defaults_off(self) -> None:
        arguments = heading_body(page(), "## Arguments")
        self.assertIn("`jev=on|off`", arguments)
        self.assertIn("default `off`", arguments)

    def test_the_section_requires_the_argument_and_the_probe(self) -> None:
        body = section_body(page())
        self.assertIn("`jev=on`", body)
        self.assertIn("`jev enabled`", body)
        self.assertIn("exits `0`", body)

    def test_the_section_takes_a_fallback_so_a_failure_is_not_a_stall(self) -> None:
        """A failed call has to land on the branch that changes nothing."""

        body = section_body(page())
        self.assertIn(f"--fallback {NOT_ASKED}", body)
        self.assertIn("`unsure`", body)


class TheSkillStandsAloneWithoutTheCommand(unittest.TestCase):
    """The reader without `jev` must not be reading a skill with a hole.

    The command ships from a private companion repository, so its absence is
    the normal case for a reader of this pack. Every instruction that mentions
    it therefore lives inside the optional section or in the one argument that
    switches the section on -- nowhere a reader following the workflow, the
    safety rules, or the report contract has to step over it.
    """

    #: The headings a reader must be able to follow with no `jev` at all.
    LOAD_BEARING = ("## When to use", "## Workflow", "## Sub-agent dispatch",
                    "## Safety rules", "## Final report")

    def test_the_load_bearing_sections_never_mention_it(self) -> None:
        text = page()
        for heading in self.LOAD_BEARING:
            with self.subTest(heading=heading):
                self.assertNotIn("jev", heading_body(text, heading).lower(),
                                 heading)

    def test_the_headings_are_really_in_the_page(self) -> None:
        """The control: a heading renamed would make the scan above read
        nothing and pass, which is the failure it exists to catch."""

        for heading in self.LOAD_BEARING:
            with self.subTest(heading=heading):
                self.assertIn(heading, page())

    def test_the_report_contract_is_unconditional(self) -> None:
        """The pass may not add, remove, or qualify a reported element."""

        body = section_body(page())
        self.assertIn("never cite this", body)
        self.assertIn("`## Final report` contract", body)


class NothingPrivateLeavesThePage(unittest.TestCase):
    """This is a public repository and the command is private.

    Two different leaks are possible and both are cheap to check: naming a
    machine or a checkout in the page, and telling the reader to put one in
    the request. The state the question needs is the claim and its span.
    """

    #: Substrings that would name a machine, a checkout, or a secret.
    FORBIDDEN = ("/Users/", "$HOME/", "local-jev", "TYPESAFE_API_KEY",
                 "~/.config/", "api.typesafe.ai")

    def test_the_section_names_no_path_machine_or_key(self) -> None:
        body = section_body(page())
        for needle in self.FORBIDDEN:
            with self.subTest(needle=needle):
                self.assertNotIn(needle, body)

    def test_the_state_is_only_the_claim_and_its_evidence(self) -> None:
        blocks = [json.loads(body) for body in fenced(section_body(page()), "json")]
        state = [block for block in blocks if "claim" in block]
        self.assertEqual(len(state), 1, "no single state block")
        self.assertEqual(set(state[0]), {"claim", "as_of", "evidence"})

    def test_the_section_says_the_call_leaves_the_machine(self) -> None:
        """A reader deciding whether to switch the pass on needs that said."""

        body = section_body(page())
        self.assertIn("leave the machine", body)
        self.assertIn("third party", body)


class ANotAnsweredCallDoesNotReadAsAnAnswer(unittest.TestCase):
    """`not_asked` and `unsure` are two different things and must stay so.

    `--fallback` prints whatever answer it was given and exits `0`, and
    `--unsure-below` prints the literal word `unsure` and exits `0` too. Give
    the fallback the word `unsure` and a pass that judged nothing prints
    exactly what a pass that judged every claim and was uncertain prints. The
    check would then read clean forever while answering nothing, which is the
    shape of a dead gate.
    """

    def test_the_fallback_answer_is_not_the_low_confidence_word(self) -> None:
        body = section_body(page())
        self.assertNotIn(f"--fallback {UNSURE}", body)
        self.assertIn(f"--fallback {NOT_ASKED}", body)

    def test_both_outcomes_have_their_own_instruction(self) -> None:
        """A reader has to be told what each of the two means, separately."""

        body = section_body(page())
        self.assertIn(f"Answer `{NOT_ASKED}`:", body)
        self.assertIn(f"Answer `{UNSURE}`:", body)

    def test_the_section_says_exit_zero_settles_nothing(self) -> None:
        """The fallback exits `0`, so the status cannot be read as a judgment."""

        self.assertIn("Exit `0` does not mean", section_body(page()))

    def test_the_section_requires_the_sent_and_answered_counts(self) -> None:
        """Otherwise a silently dead pass is invisible to everyone."""

        body = section_body(page())
        self.assertIn("Count the claims sent and the claims answered", body)
        self.assertIn("stop the pass", body)


class TheCallIsSpelledAsTheCommandAcceptsIt(unittest.TestCase):
    """A flag the verb does not take is an instruction that fails on use.

    The page is read by someone who will paste the command. `choice` exits 2
    on an unrecognised option and prints nothing, so a typo here costs the
    reader the whole pass with no usable error.
    """

    def command(self) -> str:
        blocks = fenced(section_body(page()), "sh")
        self.assertEqual(len(blocks), 1, "no single shell block in the section")
        return blocks[0].replace("\\\n", " ")

    def test_the_verb_is_choice_with_its_instructions_first(self) -> None:
        words = self.command().split()
        self.assertEqual(words[:2], ["jev", "choice"])
        self.assertFalse(words[2].startswith("-"), "instructions are positional")

    def test_every_option_is_one_the_verb_accepts(self) -> None:
        used = {word for word in self.command().split() if word.startswith("--")}
        self.assertEqual(sorted(used - CHOICE_OPTIONS), [], sorted(used))

    def test_the_required_option_is_there(self) -> None:
        """`--criteria` is not optional for `choice`."""

        self.assertIn("--criteria", self.command())


if __name__ == "__main__":
    unittest.main()
