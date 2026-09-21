"""The optional prose scoring pass stays optional, private, and well formed.

`skills/_shared/references/prose-score-dimensions.md` defines a scoring pass
that `sd-prose-lint` and `sd-humanizer` may run over a draft. The pass reaches
a private companion command, `jev`, that a reader of this public repository
very likely does not have. Three properties have to hold, and none of them is
visible in a diff:

**The request has to be one the API accepts.** The reference ships the literal
JSON a caller hands to `jev ask`, so a typo in it is a runtime failure in an
installed skill rather than a review finding. This module parses that block
and checks it against the score primitive's own limits: an ordered `criteria`
array of at least two and at most ten level descriptions, each distinct,
because overlapping levels are what drives the model's confidence down.

**The levels have to be one length.** Normalization divides a raw score by the
highest level number. A dimension that grew a level while its neighbours did
not would outweigh them silently, and the composite would still look fine.

**The pass has to be skippable.** A reader without `jev` must read a complete
skill, not one with a hole in it. So every place either page names the command
is held to a conditional, and both pages have to say what happens when the
command cannot answer.

**Nothing private may leak.** The command lives in a private repository. Its
paths, that repository's name, and the key it reads are not this repository's
to publish, and the scored call itself must carry the draft and nothing else.

The dimension list is not typed here. It is read from the reference's JSON
block and checked against the reference's own table, so the two halves of that
file cannot drift apart without this module naming the difference.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The reference the two skills cite, at the path the installer fans out from.
REFERENCE = REPO_ROOT / "skills" / "_shared" / "references" / "prose-score-dimensions.md"

#: What a skill writes to pull the reference into its installed folder.
CITATION = "references/prose-score-dimensions.md"

#: The skills that may run the pass. Both cite the reference; nothing else does,
#: and `test_no_other_skill_cites_the_reference` is what holds that.
SCORING_SKILLS = ("sd-humanizer", "sd-prose-lint")

#: The score primitive's own bounds on an ordered level array.
MIN_LEVELS, MAX_LEVELS = 2, 10

JSON_BLOCK = re.compile(r"```json\n(.*?)\n```", re.DOTALL)

SH_BLOCK = re.compile(r"```sh\n(.*?)\n```", re.DOTALL)

#: Options the `ask` verb does not take. Each belongs to a single-question
#: verb: `--id` names the one question, `--json` and `--gate` shape the one
#: answer, and `--levels`, `--criteria` and `--unsure-below` define it. Under
#: `ask` the question ids are the keys of the request and the levels sit
#: inside it, so any of these is an invocation that exits non-zero having
#: printed nothing.
NOT_ON_ASK = ("--id", "--json", "--gate", "--levels", "--criteria",
              "--unsure-below")

#: Options `ask` does take, so a typo in the reference is caught rather than
#: read as an option this module has not heard of.
ON_ASK = ("--questions", "--state", "--state-format", "--model", "--fallback")

#: A row of the reference's dimension table: `| `name` | question |`.
TABLE_ROW = re.compile(r"^\|\s*`(\w+)`\s*\|", re.MULTILINE)

#: A paragraph that names the command has to carry one of these. Each says the
#: same thing in the voice of a different sentence: the pass may not run.
CONDITIONALS = (
    "optional", "only when", "when the user", "asks for", "asked for",
    "exits `0`", "is available", "cannot answer", "without", "absent",
    "skip", "never",
)

#: Strings that belong to the private companion and never to this repository.
#: Scanned over the reference and over the paragraphs that name the command,
#: not over a whole skill page: `sd-humanizer` records its own provenance as an
#: absolute path, which predates this pass and says nothing about the command.
PRIVATE = ("/Users/", "local-jev", "TYPESAFE_API_KEY", "repos/system",
           "jev.sh", "jev.py")


def skill_page(name: str) -> pathlib.Path:
    return REPO_ROOT / "skills" / name / "SKILL.md"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def questions() -> dict:
    """The `ask` request the reference ships, parsed."""

    match = JSON_BLOCK.search(read(REFERENCE))
    assert match is not None, f"{REFERENCE} carries no fenced json block"
    return json.loads(match.group(1))


def paragraphs(text: str) -> list[str]:
    return [block for block in re.split(r"\n\s*\n", text) if block.strip()]


#: The skill whose invocation modes decide whether the pass may run at all.
#: `sd-prose-lint` has no modes, so this half of the module is `sd-humanizer`
#: alone.
MODE_SKILL = "sd-humanizer"

#: A bold-led mode entry under `## Invocation Modes`, keyed by its own name.
MODE_ENTRY = re.compile(r"^\*\*(.+?)\.?\*\*(.*?)(?=^\*\*|\Z)", re.S | re.M)

#: A numbered step under `## Process and Output`, keyed by its number. It
#: stops at the next step or at the blank line after the list: a step that ran
#: to the end of the section would carry the paragraph below it, and a check
#: over the step would then pass on words that paragraph happened to use.
NUMBERED_STEP = re.compile(r"^(\d+)\. (.*?)(?=^\d+\. |^\s*$)", re.S | re.M)

#: The mode that outputs prose and nothing else, lowercased for matching.
SILENT_MODE = "embedded"

#: The modes that report scores, so the modes the pass may run in.
REPORTING_MODES = ("pasted", "file")

#: A sentence granting the pass on a user request. It is what the introduction
#: used to say before the mode condition reached it: a `when`, a user, and a
#: score, inside one sentence. Any paragraph shaped like this is a second
#: statement of the run rule and has to carry the mode condition or defer.
GRANT = re.compile(r"\b(when|once|if)\b[^.]*\b(user|caller)\b[^.]*\bscor", re.I)

#: A sentence end, for splitting a site into the sentence that states the rule
#: and the sentences that do not.
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def permission_sentences(body: str) -> str:
    """The sentences of a site that state the condition, joined.

    Most of a site is not the rule. The gate also says what to report, and the
    step also says what to do next, and both name a mode in passing while
    doing it. The condition is the sentence that names the probe, so that is
    the sentence the mode has to be in. A check over the whole block passes on
    a mode named in a neighbouring sentence, which is a check that cannot
    fail.
    """

    return " ".join(one for one in SENTENCE.split(body) if "jev enabled" in one)


def section(text: str, title: str) -> str:
    """The body of a `## <title>` section, without its heading."""

    match = re.search(r"^## " + re.escape(title) + r"\n(.*?)(?=^## |\Z)",
                      text, re.S | re.M)
    assert match is not None, f"{MODE_SKILL} has no '{title}' section"
    return match.group(1)


def modes(text: str) -> dict[str, str]:
    """The invocation modes the skill defines, keyed by name."""

    found = MODE_ENTRY.findall(section(text, "Invocation Modes"))
    return {name.split("(")[0].strip().lower(): body for name, body in found}


def run_condition_sites(text: str) -> dict[str, str]:
    """The three places that say whether the scoring pass runs.

    Each is located by what it is rather than by what it says: the gate is
    the paragraph of `## OPTIONAL SCORES` that names the probe, the step is
    the numbered step of `## Process and Output` that names it, and the mode
    entry is the one `## Invocation Modes` calls embedded.
    """

    found = {}
    for block in paragraphs(section(text, "OPTIONAL SCORES")):
        if "jev enabled" in block:
            found["the OPTIONAL SCORES gate"] = block
            break
    for number, body in NUMBERED_STEP.findall(section(text, "Process and Output")):
        if "jev enabled" in body:
            found[f"step {number}"] = body
            break
    for name, body in modes(text).items():
        if SILENT_MODE in name:
            found["the embedded mode entry"] = body
    return found


class TheRequest(unittest.TestCase):
    """The JSON block is a request the score primitive accepts."""

    def setUp(self) -> None:
        self.asked = questions()

    def test_the_block_is_an_object_of_questions(self) -> None:
        self.assertIsInstance(self.asked, dict)
        self.assertTrue(self.asked, "the request asks nothing")

    def test_every_question_is_a_score(self) -> None:
        wrong = {name: body.get("type") for name, body in self.asked.items()
                 if body.get("type") != "score"}
        self.assertEqual(wrong, {}, f"""
These questions are not score questions: {wrong}.

The pass exists to produce a position on ordered levels that a caller can
threshold and compare across revisions. A noul or a choice answers something
else and does not normalize the same way.
""")

    def test_every_question_asks_one_question(self) -> None:
        bad = [name for name, body in self.asked.items()
               if not str(body.get("instructions", "")).strip().endswith("?")]
        self.assertEqual(bad, [], f"""
These instructions do not read as a question: {bad}.

A level array answers one question. Instructions that state two put the
answer between them, and the score then means neither.
""")

    def test_level_counts_are_within_the_primitive_bounds(self) -> None:
        sizes = {name: len(body["criteria"]) for name, body in self.asked.items()}
        outside = {name: size for name, size in sizes.items()
                   if not MIN_LEVELS <= size <= MAX_LEVELS}
        self.assertEqual(outside, {}, f"""
These dimensions carry a level count the primitive refuses: {outside}.
It takes at least {MIN_LEVELS} levels and at most {MAX_LEVELS}.
""")

    def test_all_dimensions_share_one_level_count(self) -> None:
        sizes = {name: len(body["criteria"]) for name, body in self.asked.items()}
        self.assertEqual(len(set(sizes.values())), 1, f"""
The dimensions do not agree on a level count: {sizes}.

Normalization divides a raw score by the highest level number. With two
different counts in one request, the dimension with more levels quietly
outweighs the others and the composite still looks reasonable.
""")

    def test_levels_are_distinct_and_described(self) -> None:
        for name, body in self.asked.items():
            levels = body["criteria"]
            with self.subTest(dimension=name):
                self.assertTrue(all(isinstance(one, str) and one.strip()
                                    for one in levels))
                self.assertEqual(len(set(levels)), len(levels), f"""
`{name}` repeats a level description. The model evaluates each level
independently, so two identical or overlapping descriptions split the
probability between them and drive confidence down for no reason.
""")

    def test_levels_describe_a_situation_rather_than_a_degree(self) -> None:
        """A level is a sentence about the draft, not an adverb."""

        thin = {}
        for name, body in self.asked.items():
            for index, level in enumerate(body["criteria"]):
                if len(level.split()) < 6:
                    thin[f"{name}[{index}]"] = level
        self.assertEqual(thin, {}, f"""
These levels are too short to describe a situation: {thin}.

"Moderately hedged" is not something two readers agree on. "Qualifiers stack
inside single sentences" is. A level has to stand on its own without reading
its neighbours.
""")


class TheInvocation(unittest.TestCase):
    """The shell example is a command the verb accepts.

    A wrong flag in a shipped skill is an instruction that fails for its
    reader, and `ask` answers a rejected option by exiting non-zero with
    nothing on stdout: the reader sees no scores and no reason.
    """

    def command(self) -> str:
        match = SH_BLOCK.search(read(REFERENCE))
        self.assertIsNotNone(match, f"{REFERENCE} shows no shell invocation")
        assert match is not None
        return " ".join(match.group(1).split())

    def test_the_example_calls_the_batching_verb(self) -> None:
        self.assertTrue(self.command().startswith("jev ask "), f"""
The shell example does not call `ask`: {self.command()!r}.

The dimensions are independent questions over one draft. One `ask` runs them
in parallel over a shared state; a verb per dimension pays for the state
again each time.
""")

    def test_the_example_uses_no_option_the_verb_rejects(self) -> None:
        words = self.command().split()
        wrong = [word for word in words if word in NOT_ON_ASK]
        self.assertEqual(wrong, [], f"""
The shell example passes options `ask` does not take: {wrong}.

Each of these belongs to a single-question verb. Passed to `ask` the parser
rejects the call, so the reader gets a non-zero exit and no output.
""")

    def test_every_option_in_the_example_is_one_the_verb_takes(self) -> None:
        unknown = [word for word in self.command().split()
                   if word.startswith("--") and word not in ON_ASK]
        self.assertEqual(unknown, [], f"""
The shell example passes options this module does not recognise: {unknown}.

Either the option is a typo, or `ask` gained one and `ON_ASK` has not caught
up. Check it against the command's own help before widening the list.
""")

    def test_at_most_one_source_reads_stdin(self) -> None:
        words = self.command().split()
        piped = [flag for flag in ("--questions", "--state")
                 if flag in words and words[words.index(flag) + 1] == "-"]
        self.assertLessEqual(len(piped), 1, f"""
The example asks two options to read stdin: {piped}.

`-` means stdin for both `--questions` and `--state`, and there is one stdin.
One of them has to be a file.
""")

    def test_the_reference_says_why_it_branches_instead_of_falling_back(self) -> None:
        text = read(REFERENCE).lower()
        self.assertIn("--fallback", text)
        self.assertIn("jev enabled", text)


class TheDimensionTable(unittest.TestCase):
    """The reference's prose table and its JSON name the same dimensions."""

    def test_the_table_matches_the_request(self) -> None:
        listed = set(TABLE_ROW.findall(read(REFERENCE)))
        asked = set(questions())
        self.assertEqual(listed, asked, f"""
The dimension table and the JSON request disagree.

In the table only: {sorted(listed - asked)}
In the request only: {sorted(asked - listed)}

A reader reads the table and a caller runs the JSON. A dimension in one and
not the other is documented and never scored, or scored and never explained.
""")


class TheSkillsCiteIt(unittest.TestCase):
    """The installer copies the reference into a skill that cites it."""

    def test_both_scoring_skills_carry_the_citation(self) -> None:
        missing = [name for name in SCORING_SKILLS
                   if CITATION not in read(skill_page(name))]
        self.assertEqual(missing, [], f"""
These skills describe the scoring pass without citing it: {missing}.

The installer fans a shared reference out to the skills that write
`{CITATION}`. A skill that only describes the pass installs
without the file and points its reader at nothing.
""")

    def test_no_other_skill_cites_the_reference(self) -> None:
        others = sorted(
            path.parent.name
            for path in REPO_ROOT.glob("skills/*/SKILL.md")
            if path.parent.name not in SCORING_SKILLS and CITATION in read(path)
        )
        self.assertEqual(others, [], f"""
These skills also cite the scoring reference: {others}.

Add them to `SCORING_SKILLS` so the optionality and privacy checks below cover
them too. The checks are the reason the citation is worth having.
""")


class ItStaysOptional(unittest.TestCase):
    """A reader without the command reads a whole skill."""

    def test_every_paragraph_naming_the_command_carries_a_conditional(self) -> None:
        unguarded = {}
        for name in SCORING_SKILLS:
            for block in paragraphs(read(skill_page(name))):
                lowered = block.lower()
                if "jev" not in lowered:
                    continue
                if not any(word in lowered for word in CONDITIONALS):
                    unguarded.setdefault(name, []).append(block.strip()[:120])
        self.assertEqual(unguarded, {}, f"""
These paragraphs name the command with nothing making it optional:
{unguarded}

The command is experimental and private, and most readers of this repository
do not have it. Every mention has to read as a branch the reader may not take.
""")

    def test_both_skills_gate_on_the_no_cost_probe(self) -> None:
        missing = [name for name in SCORING_SKILLS
                   if "jev enabled" not in read(skill_page(name))]
        self.assertEqual(missing, [], f"""
These skills do not name the probe that decides whether to score: {missing}.

`jev enabled` calls nothing and costs nothing, and it is the one way to ask
whether scoring can happen here without spending a request to find out.
""")

    def test_both_skills_say_what_happens_when_it_cannot_answer(self) -> None:
        for name in SCORING_SKILLS:
            page = read(skill_page(name)).lower()
            with self.subTest(skill=name):
                self.assertTrue(
                    "cannot answer here" in page or "could not answer here" in page,
                    f"{name} does not say what it does when scoring is unavailable; "
                    "a pass that goes quiet is the failure the fallback shape exists "
                    "to prevent",
                )


class TheSplitIsStated(unittest.TestCase):
    """The countable stays in code, and the pages say so."""

    def test_the_reference_assigns_counting_to_code(self) -> None:
        text = read(REFERENCE)
        for token in ("wc -w", "grep", "Code counts", "The model judges"):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_each_skill_names_a_counting_tool(self) -> None:
        missing = [name for name in SCORING_SKILLS
                   if "grep" not in read(skill_page(name)).lower()]
        self.assertEqual(missing, [], f"""
These skills describe the scoring pass without saying what code still counts:
{missing}.

Handing the model a literal match spends tokens to learn what a pipe already
knows, and answers it less reliably. The division is the point of the pass.
""")


class TheAnswersAreCounted(unittest.TestCase):
    """A summary counting what was sent survives the pass going dead."""

    def pages(self) -> dict[str, str]:
        found = {str(REFERENCE.relative_to(REPO_ROOT)): read(REFERENCE)}
        for name in SCORING_SKILLS:
            path = skill_page(name)
            found[str(path.relative_to(REPO_ROOT))] = read(path)
        return found

    def test_every_page_says_to_count_what_came_back(self) -> None:
        for where, text in self.pages().items():
            lowered = text.lower()
            with self.subTest(page=where):
                self.assertIn("answered", lowered, f"""
{where} does not say to count the dimensions that answered.

A count of the questions sent prints the same line whether every dimension
answered or the call returned nothing, so a pass that has stopped working goes
on reading clean.
""")
                self.assertIn("asked", lowered,
                              f"{where} reports one number where two are needed")

    def test_every_page_refuses_to_read_a_missing_answer_as_zero(self) -> None:
        for where, text in self.pages().items():
            lowered = text.lower()
            with self.subTest(page=where):
                self.assertIn("missing", lowered, f"""
{where} does not say what a dimension that did not answer means.

It is missing, not zero. Zero is a real position on the scale: on `hedging` it
says the draft hedges nothing, which is the opposite of an absent answer.
""")


class NothingPrivateLeaks(unittest.TestCase):
    """This repository is public and the command it reaches is not."""

    def pages(self) -> dict[str, str]:
        found = {str(REFERENCE.relative_to(REPO_ROOT)): read(REFERENCE)}
        for name in SCORING_SKILLS:
            path = skill_page(name)
            found[str(path.relative_to(REPO_ROOT))] = read(path)
        return found

    def scoring_prose(self) -> dict[str, str]:
        """The reference, plus each skill's paragraphs that name the command."""

        found = {str(REFERENCE.relative_to(REPO_ROOT)): read(REFERENCE)}
        for name in SCORING_SKILLS:
            blocks = [block for block in paragraphs(read(skill_page(name)))
                      if "jev" in block.lower()]
            found[str(skill_page(name).relative_to(REPO_ROOT))] = "\n\n".join(blocks)
        return found

    def test_no_private_identifier_appears(self) -> None:
        hits = {}
        for where, text in self.scoring_prose().items():
            for token in PRIVATE:
                if token in text:
                    hits.setdefault(where, []).append(token)
        self.assertEqual(hits, {}, f"""
These pages name something that belongs to the private companion: {hits}.

A public reader learns the command's name and nothing else. Its checkout, its
entrypoints and the key it reads are not this repository's to publish.
""")

    def test_every_page_says_a_confidential_draft_is_not_sent(self) -> None:
        for where, text in self.pages().items():
            with self.subTest(page=where):
                self.assertIn("confidential draft", text.lower(), f"""
{where} describes a call that posts the draft to a third party without saying
which drafts must never go. The rule has to sit beside the instruction that
would otherwise send them.
""")

    def test_every_page_scopes_the_payload_to_the_draft(self) -> None:
        for where, text in self.pages().items():
            lowered = text.lower()
            with self.subTest(page=where):
                missing = [token for token in ("file path", "repository name")
                           if token not in lowered]
                self.assertEqual(missing, [], f"""
{where} does not name what a scoring request must leave out: {missing}.

The draft text is what the question needs. A path or a repository name adds
nothing to the judgment and is the part that cannot be taken back.
""")


class PolicyStaysSeparate(unittest.TestCase):
    """Raw scores are recorded; thresholds and weights are not baked in."""

    def test_the_reference_keeps_weights_out_of_the_scores(self) -> None:
        text = read(REFERENCE).lower()
        for token in ("normalize", "raw", "confidence", "weight", "threshold"):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_each_skill_reports_the_raw_numbers(self) -> None:
        missing = [name for name in SCORING_SKILLS
                   if "raw" not in read(skill_page(name)).lower()]
        self.assertEqual(missing, [], f"""
These skills do not say to report the raw per-dimension numbers: {missing}.

Inference is the expensive part. Recording it lets a reader change a weight or
a threshold and re-read the same numbers instead of paying again.
""")


class TheModeGate(unittest.TestCase):
    """Embedded mode never sends the draft, and three sites say so.

    The pass posts the draft to a third party. Embedded mode outputs prose
    and nothing else, so a scored embedded run would transmit the text for
    numbers it then throws away. That is the defect this class exists to
    catch, and it got in because the rule was written four times and one copy
    was missed. So the check is not that some sentence is present: it is that
    every place stating when the pass runs carries the mode condition, and
    that no fourth place quietly grants it again.
    """

    def setUp(self) -> None:
        self.page = read(skill_page(MODE_SKILL))
        self.sites = run_condition_sites(self.page)

    def test_all_three_sites_are_there(self) -> None:
        missing = [name for name in
                   ("the OPTIONAL SCORES gate", "step 5",
                    "the embedded mode entry")
                   if name not in self.sites]
        self.assertEqual(missing, [], f"""
These statements of the scoring rule are gone from {MODE_SKILL}: {missing}.

They are found by structure, not by wording, so a rename does not hide one.
A site that disappeared took its half of the rule with it.
""")

    def test_the_modes_are_the_ones_this_module_knows(self) -> None:
        named = set(modes(self.page))
        self.assertEqual(named, {"pasted text", "file mode", "embedded mode"}, f"""
{MODE_SKILL} defines these invocation modes: {sorted(named)}.

A new mode has to state whether the scoring pass may run in it, because the
pass transmits the draft. Decide that, then widen this test.
""")

    def test_each_permitting_site_names_the_modes_it_permits(self) -> None:
        """A permission that names no mode is the bug that was shipped."""

        thin = {}
        for name, body in self.sites.items():
            if name == "the embedded mode entry":
                continue
            stated = permission_sentences(body)
            self.assertTrue(stated, f"{name} states no condition at all")
            lowered = stated.lower()
            absent = [mode for mode in REPORTING_MODES if mode not in lowered]
            if absent:
                thin[name] = {"missing": absent, "sentence": stated.strip()[:160]}
        self.assertEqual(thin, {}, f"""
These sites let the pass run without naming the modes it may run in: {thin}.

Both reporting modes have to be named. A permission stated without them reads
as permission in embedded mode too, and that is the draft leaving the machine.
""")

    def test_each_permitting_site_excludes_the_silent_mode(self) -> None:
        silent = {}
        for name, body in self.sites.items():
            if name == "the embedded mode entry":
                continue
            if SILENT_MODE not in body.lower():
                silent[name] = body.strip()[:120]
        self.assertEqual(silent, {}, f"""
These sites never mention embedded mode: {silent}.

A reader who enters here has to be told the pass does not run there. Leaving
it unsaid is how the rule was missed the first time.
""")

    def test_the_silent_mode_refuses_the_pass_itself(self) -> None:
        body = self.sites["the embedded mode entry"]
        self.assertRegex(body.lower(), r"never scor", f"""
The embedded mode entry no longer refuses the pass:

{body.strip()[:200]}

A reader arriving at the mode description must be told there, not only in
OPTIONAL SCORES. The rule has to sit where the mode is defined.
""")

    def test_no_fourth_site_grants_the_pass_on_a_user_request_alone(self) -> None:
        """The introduction is where this leaked, and it named no mode."""

        known = set(self.sites.values())
        unguarded = {}
        for block in paragraphs(self.page):
            if block in known or "jev enabled" in block:
                continue
            if not GRANT.search(block):
                continue
            lowered = block.lower()
            if any(mode in lowered for mode in REPORTING_MODES):
                continue
            if "optional scores" in lowered:
                continue
            unguarded[block.strip()[:160]] = "names no mode and defers to nothing"
        self.assertEqual(unguarded, {}, f"""
These paragraphs grant the scoring pass on a user request without a mode:
{unguarded}

A user request and an available command both hold for an embedded run, so a
paragraph stating only those two sends the draft. Name the modes, or say the
paragraph states no condition and point at OPTIONAL SCORES.
""")


if __name__ == "__main__":
    unittest.main()
