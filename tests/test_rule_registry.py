"""The rule registry and the three-legged meta-check that keeps it honest.

`bin/sd_rules.py` answers "which rules exist". This module is what stops that
answer and the repository drifting apart, and it is the deliverable: legs a, b
and c below are worth more than any number of rules, because rules with no
meta-check start drifting the day they land.

The three legs fail independently, and each one catches a different way the
sentence and the machinery come apart:

    a. a registry rule no skill teaches -- a rule authors meet only as a CI
       failure, never while they are writing;
    b. a skill claiming a tool behaviour with no rule id behind it -- prose
       asserting an enforcement nothing performs, which is the defect that
       let `WORKFLOW.md` claim for weeks that every writing skill refuses the
       upstream tree while nothing refused;
    c. a rule id cited in live prose that the registry does not carry -- a
       deleted checker leaving live prose behind.

**Every population here is enumerated, never listed.** The pack nouns come
from `bin/` and `tests/` as they are on disk, the corpus comes from the git
index, and the skills come from `skills/`. A roster written down by hand is
the thing this whole item exists to stop: two items closed the same week were
a generated list of twenty skills of which fourteen did not exist, and a pair
of hand-written field tuples that silently dropped keys.

**This module is excluded from the corpus it measures**, the same exclusion
`_references()` in `tests/test_code_health.py` makes and for the same reason:
the baselines below name rule ids, and naming an id in a baseline must not be
evidence about that id. Without the exclusion, adding `R11-D1` to
`DANGLING_RULE_IDS` would be a live-prose citation of `R11-D1`, so the act of
recording a violation would also be an instance of it.
"""

from __future__ import annotations

import ast
import collections
import pathlib
import re
import subprocess
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_rules  # noqa: E402 - the table under test, imported for its own sake

#: Where the historical record lives. Archived planning documents are read for
#: *definitions*, because a rule defined there still answers a live citation,
#: but their own citations are not held to leg c: the ruling everywhere else in
#: this repository is to take the coverage and not buy it by editing history.
ARCHIVE = "docs/work/archive/"

#: This file, as the index names it. See the module docstring.
SELF = "tests/test_rule_registry.py"

#: Where the skills live, and the only scope leg b reads.
SKILLS = "skills/"

#: The four verbs that turn a sentence into an enforcement claim. Narrowed
#: from every occurrence of them -- 4,652 lines of tracked markdown on
#: `cddd3b98` carry one
#: -- by requiring a pack tool or a test on the same line, because *"never
#: write into a shared checkout"* is an instruction to a reader rather than a
#: claim about machinery, and it cites nothing because there is nothing to
#: cite.
ENFORCEMENT = re.compile(r"\b(refuses|never|always|cannot)\b")

#: A definition of a rule id, as this repository has always written one: a run
#: of bold text opening with the id. There is no other form, because until now
#: there was no registry -- which is the finding, not an accident.
DEFINITION = re.compile(r"\*\*(R\d+-D\d+)\b")


# --------------------------------------------------------------------------
# The baselines. Every number below was measured, not chosen.
# --------------------------------------------------------------------------

#: Rule ids cited in live prose that are defined nowhere at all -- not in the
#: registry, not in a live document, not even in the archive. Measured on
#: `cddd3b98`, and the same four the planning pass found on `e6c2cb20`.
#:
#: Held as a set rather than a count, because with four entries the set is the
#: better record: a new dangling id fails by name on the line that invented it,
#: and no arithmetic can hide one behind another being fixed.
#:
#: Resolving one means either registering it or repointing the prose that cites
#: it, and then removing it here in the same change.
DANGLING_RULE_IDS = frozenset({"R11-D1", "R11-D30", "R11-D46", "R5-D1"})

#: Live prose citations whose only definition sits inside `docs/work/archive`.
#: Measured at 26 on `cddd3b98`. More than half the rule ids in live prose
#: point only into the archive -- into pages this pack's own citation gate
#: treats as historical records rather than as current statements.
#:
#: This is the backfill's meter. Each id moved into a registry row takes this
#: number down by one, and the assertion below proves it fell.
ARCHIVE_ONLY_CITATIONS = 26

#: Tool-behaviour claims in skills that cite no rule id, per document.
#: Measured on `cddd3b98` by `uncited_skill_claims` below.
#:
#: Per document rather than as one total, so a new uncited claim in `sd-ship`
#: fails even in a change that cleaned two out of `sd-plan`. One number for the
#: whole tree would net them off and say nothing.
UNCITED_SKILL_CLAIMS = {
    "skills/sd-handoff/SKILL.md": 1,
    "skills/sd-plan/SKILL.md": 2,
    "skills/sd-research-repo/templates/CLAUDE.md": 1,
    "skills/sd-ship/SKILL.md": 3,
    "skills/sd-suggest/SKILL.md": 1,
}


# --------------------------------------------------------------------------
# Enumeration
# --------------------------------------------------------------------------


def tracked_paths(*pathspecs: str) -> list[pathlib.Path]:
    """Tracked files matching `pathspecs`, as the index reports them.

    The index rather than a directory walk, so a scratch file or a stale
    `__pycache__` entry cannot join the measurement. `--deduplicate` because a
    conflicted index holds one entry per merge stage, and every count here
    would otherwise triple on the one file a writer is resolving.
    """

    output = subprocess.run(
        ["git", "ls-files", "-z", "--deduplicate", "--", *pathspecs],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
    return [REPO_ROOT / name for name in output.split("\0") if name]


def read_corpus(*pathspecs: str) -> list[tuple[str, str]]:
    """Every tracked file matching `pathspecs`, as `(path, text)`, minus this one.

    Read with `errors="replace"` rather than filtered by suffix: a rule id
    cited from a shell script, a JSON schema or a workflow is still a citation,
    and picking suffixes by hand would be the listed-roster mistake one layer
    down. A file the process cannot open is skipped rather than fatal, because
    a permission accident should not silently empty a baseline.
    """

    corpus = []
    for path in tracked_paths(*pathspecs):
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative == SELF:
            continue
        try:
            corpus.append((relative, path.read_text(encoding="utf-8",
                                                    errors="replace")))
        except OSError:
            continue
    return corpus


def pack_nouns() -> frozenset[str]:
    """Every name that could be the subject of a claim about this pack.

    Enumerated from `bin/` and `tests/` on disk. A tool built next month is
    covered the day it is written, with nobody updating anything -- which is
    the property a hand-kept list does not have, and the property this whole
    registry is about.
    """

    tools = {path.name for path in tracked_paths("bin")}
    suites = {path.stem for path in tracked_paths("tests/test_*.py")}
    return frozenset(tools | suites)


def names_a_pack_noun() -> re.Pattern[str]:
    """The pack-noun matcher, longest name first so `sd` cannot shadow `sd-plan`.

    The boundaries are `[\\w-]` rather than `\\b`, because tool names carry
    hyphens: plain `\\bsd-plan\\b` would also match inside `sd-planning`, and a
    leading `\\b` would refuse to match `sd-status` written as `bin/sd-status`.
    """

    names = sorted(pack_nouns(), key=len, reverse=True)
    alternation = "|".join(re.escape(name) for name in names)
    return re.compile(rf"(?<![\w-])({alternation})(?![\w-])")


def skill_claims() -> list[tuple[str, int, str, list[str]]]:
    """Every tool-behaviour claim in a skill, as `(path, line, text, rule ids)`.

    A claim is a line carrying an enforcement verb *and* naming a pack tool or
    a test. That predicate is deliberately narrow and will have false
    negatives, which the design accepted in writing: this is a ratchet on new
    claims, not an audit of old ones, and a ratchet with false negatives still
    only moves one way. A predicate wide enough to catch every claim reddens
    thousands of lines on its first run, and a check that does that is not
    adopted, it is disabled.
    """

    subject = names_a_pack_noun()
    found = []
    for relative, text in read_corpus(f"{SKILLS}*.md", f"{SKILLS}**/*.md"):
        for number, line in enumerate(text.splitlines(), 1):
            if ENFORCEMENT.search(line) and subject.search(line):
                found.append((relative, number, line.strip(),
                              sd_rules.RULE_ID.findall(line)))
    return found


def uncited_skill_claims() -> dict[str, int]:
    """Tool-behaviour claims citing no rule id at all, counted per document."""

    counts: collections.Counter = collections.Counter()
    for relative, _, _, ids in skill_claims():
        if not ids:
            counts[relative] += 1
    return dict(counts)


def cited_rule_ids(*, live_only: bool) -> set[str]:
    """Every rule id written anywhere in the corpus.

    `live_only` drops `docs/work/archive`, which is what separates a statement
    the pack still makes from a record of one it used to.
    """

    found: set[str] = set()
    for relative, text in read_corpus():
        if live_only and relative.startswith(ARCHIVE):
            continue
        found.update(sd_rules.RULE_ID.findall(text))
    return found


def defined_rule_ids(*, live_only: bool) -> set[str]:
    """Every rule id a document defines, by the bold-run form."""

    found: set[str] = set()
    for relative, text in read_corpus():
        if live_only and relative.startswith(ARCHIVE):
            continue
        found.update(DEFINITION.findall(text))
    return found


def registered_rule_ids() -> set[str]:
    """The registry's own answer, live rows and repealed rows alike.

    A repealed row still resolves a citation. That is the whole reason the
    state exists: prose citing a withdrawn rule must be answered, and the id
    must never be handed to a different rule later.
    """

    return {rule.id for rule in sd_rules.RULES}


def python_sources() -> list[tuple[str, str]]:
    """Tracked `bin/` and `dashboard/` files that parse as Python.

    Parsed rather than selected by suffix, because half of `bin/` is
    extensionless scripts with a shebang. A file that will not parse is not
    Python and drops out on its own.
    """

    return [(relative, text) for relative, text in read_corpus("bin", "dashboard")
            if _parses(text)]


def _parses(text: str) -> bool:
    try:
        ast.parse(text)
    except (SyntaxError, ValueError):
        return False
    return True


def second_list_entries() -> list[tuple[str, int, str]]:
    """Registry rule ids written as data outside the registry module.

    A rule id in a *comment or a docstring* is a citation, and citing a rule is
    the point. A rule id in any other string constant is data: a consumer
    restating what the table already says, which is the second list `CLASSES`
    in `bin/sd-status` was shaped to make impossible. So docstrings and bare
    string statements are dropped and every other string constant is read.

    Empty while the table is empty, which is what lets the table land first.
    The first row for a rule some consumer already names in a string fails
    here on the spot -- and `bin/sd-status` carries `R10-D1` in a `CLASSES`
    row today, so that is not a hypothetical.
    """

    registered = registered_rule_ids()
    offenders = []
    for relative, text in python_sources():
        if relative == "bin/sd_rules.py":
            continue
        for node in _data_strings(ast.parse(text)):
            for identifier in sd_rules.RULE_ID.findall(node.value):
                if identifier in registered:
                    offenders.append((relative, node.lineno, identifier))
    return offenders


def _data_strings(tree: ast.AST) -> list[ast.Constant]:
    """Every string constant that is not documentation."""

    prose = {id(node.value) for node in ast.walk(tree)
             if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in prose]


def skill_documents() -> list[tuple[str, str]]:
    """Every authored markdown file under `skills/`, walked from the index."""

    return read_corpus(f"{SKILLS}*.md", f"{SKILLS}**/*.md")


def _lines(rows) -> str:
    return "\n".join(f"  {row}" for row in rows)


# --------------------------------------------------------------------------
# Step 1 -- the table keeps its own shape
# --------------------------------------------------------------------------


class Registry(unittest.TestCase):
    """The table's own tests. Zero rows passes every one of them."""

    def test_every_live_rule_names_a_checker_that_exists(self):
        """A row whose checker is missing is a failure, never a comment.

        The checker is held as the function object, so a row naming something
        that does not exist raises at import. This asserts the weaker thing the
        import cannot: that the object a row does hold is callable, and that a
        repealed row holds nothing, because a withdrawn rule has nothing left
        to run.
        """

        wrong = [rule.id for rule in sd_rules.RULES
                 if (rule.state == sd_rules.LIVE) != callable(rule.checker)]
        self.assertEqual(wrong, [], f"""
A registry row's checker does not match its state.

{_lines(wrong)}

A `live` row must hold a callable. A `repealed` row must hold `None`.""")

    def test_every_rule_id_is_unique_and_well_formed(self):
        """Two rows sharing an id make the lookup silently drop one.

        Reuse is the sharper half. A repealed id must never be handed to a new
        rule: live prose citing `R5-D1` would start resolving to a rule its
        author never read, and nothing would say so.
        """

        identifiers = [rule.id for rule in sd_rules.RULES]
        duplicated = sorted({identifier for identifier in identifiers
                             if identifiers.count(identifier) > 1})
        self.assertEqual(duplicated, [], f"ids used twice:\n{_lines(duplicated)}")
        malformed = [identifier for identifier in identifiers
                     if not sd_rules.RULE_ID.fullmatch(identifier)]
        self.assertEqual(malformed, [],
                         f"ids not of the form R<n>-D<n>:\n{_lines(malformed)}")
        self.assertEqual(len(sd_rules.BY_RULE_ID), len(sd_rules.RULES),
                         "BY_RULE_ID dropped a row; two rows share an id")

    def test_every_rule_declares_a_known_scope_and_state(self):
        """`scope` and `state` are read by consumers, so a typo must fail here."""

        wrong = [f"{rule.id}: scope={rule.scope!r} state={rule.state!r}"
                 for rule in sd_rules.RULES
                 if rule.scope not in sd_rules.SCOPES
                 or rule.state not in sd_rules.STATES]
        self.assertEqual(wrong, [], f"""
A row declares a scope or a state nothing recognises.

{_lines(wrong)}

Scopes are {sd_rules.SCOPES}. States are {sd_rules.STATES}.""")

    def test_no_consumer_carries_a_second_list(self):
        """A rule id written as data outside the registry is a second list.

        This is requirement 1's only mechanical check, and it is the one that
        would have caught the drift `CLASSES` was built to prevent: a consumer
        that names a rule in a string has taken a copy of the table, and a copy
        is a thing that can disagree.
        """

        offenders = second_list_entries()
        self.assertEqual(offenders, [], f"""
A registry rule id appears as data outside `bin/sd_rules.py`.

{_lines(f"{path}:{line} carries {identifier}" for path, line, identifier in offenders)}

Read the id off `sd_rules.RULES` or `sd_rules.BY_RULE_ID` instead. A rule id in
a comment or a docstring is a citation and is fine; one in any other string is
a copy of the table.""")


# --------------------------------------------------------------------------
# Leg a -- every rule is taught
# --------------------------------------------------------------------------


class LegA(unittest.TestCase):
    """A rule nobody teaches is a rule authors meet only as a CI failure."""

    def test_every_live_rule_is_cited_by_a_skill(self):
        """The rule id appears in at least one skill document.

        Citation is what is checked. *Not restating the rule* is the other half
        of the convention and it has no mechanical check -- judging whether two
        English sentences say the same thing is not a test -- so it is left as
        a review habit and recorded as an accepted gap, rather than asserted
        here as an enforcement with no enforcer. Committing that defect inside
        the check built to end it would be absurd.
        """

        taught = set()
        for _, text in skill_documents():
            taught.update(sd_rules.RULE_ID.findall(text))
        untaught = sorted(rule.id for rule in sd_rules.RULES
                          if rule.state == sd_rules.LIVE and rule.id not in taught)
        self.assertEqual(untaught, [], f"""
A live registry rule is taught by no skill.

{_lines(untaught)}

Cite the id from the skill section named in the row's `teaches` field.""")

    def test_every_live_rule_points_at_a_skill_section_that_exists(self):
        """`teaches` is `path#heading`, and both halves have to resolve.

        A row pointing at a deleted skill, or at a heading somebody renamed, is
        the registry's own version of the drift it exists to catch.
        """

        documents = dict(skill_documents())
        broken = []
        for rule in sd_rules.RULES:
            if rule.state != sd_rules.LIVE:
                continue
            path, _, heading = rule.teaches.partition("#")
            if path not in documents:
                broken.append(f"{rule.id}: no skill document at {path!r}")
            elif heading and heading not in documents[path]:
                broken.append(f"{rule.id}: {path} carries no heading {heading!r}")
        self.assertEqual(broken, [], f"""
A registry row teaches from a section that does not exist.

{_lines(broken)}""")


# --------------------------------------------------------------------------
# Leg b -- every enforcement claim in a skill cites a rule
# --------------------------------------------------------------------------


class LegB(unittest.TestCase):
    """Prose asserting an enforcement, with nothing linking it to the code."""

    def test_no_skill_claim_cites_an_unknown_rule_id(self):
        """A claim naming an id the registry does not carry fails at once.

        No baseline, because no skill claim cites any id today. That is the
        finding, not the exemption: of the tool-behaviour claims in `skills/`,
        every single one asserts a behaviour with no rule id behind it.
        """

        registered = registered_rule_ids()
        unknown = [f"{path}:{line} cites {identifier} -- {text}"
                   for path, line, text, ids in skill_claims()
                   for identifier in ids if identifier not in registered]
        self.assertEqual(unknown, [], f"""
A skill claims a tool behaviour and cites a rule id the registry does not carry.

{_lines(unknown)}

Add the rule to `bin/sd_rules.py`, or cite the id that already covers it.""")

    def test_uncited_tool_behaviour_claims_match_their_baseline(self):
        """The ratchet on claims with no rule id behind them.

        Exactly, not at most, and the repository has already argued this out:
        `test_the_shared_name_blind_spot_only_shrinks` uses equality because
        `assertLessEqual` lets a record go stale -- a cleanup shrinks the
        population while the constant stays at its old value forever. Equality
        makes the record move with the thing it records, in the same change.

        The count is of *violations*, never of the population. A new claim that
        correctly cites a rule id does not appear here at all, which is what
        separates a ratchet from a census: on a census, doing the right thing
        would redden the build.
        """

        self.assertEqual(uncited_skill_claims(), UNCITED_SKILL_CLAIMS, """
The uncited tool-behaviour claims in `skills/` no longer match their baseline.

Above: measured first, baseline second. A count that rose is a new claim
asserting a behaviour with nothing linking it to the code that performs it --
cite a registry rule id on the line. A count that fell is the ordinary good
case: lower the entry in `UNCITED_SKILL_CLAIMS` in the same change, and delete
the entry outright when it reaches zero.""")


# --------------------------------------------------------------------------
# Leg c -- every rule id cited in live prose resolves
# --------------------------------------------------------------------------


class LegC(unittest.TestCase):
    """A deleted checker leaving live prose behind."""

    def test_live_citations_that_resolve_to_nothing_match_their_baseline(self):
        """Ids cited in live prose and defined nowhere at all.

        These are the sharpest case: not a rule whose definition moved into the
        archive, but a rule id with no definition anywhere in the repository.
        Four of them, and the pack has been citing them as though they were
        rules the whole time.
        """

        cited = cited_rule_ids(live_only=True)
        resolved = defined_rule_ids(live_only=False) | registered_rule_ids()
        self.assertEqual(cited - resolved, DANGLING_RULE_IDS, """
The rule ids cited in live prose that resolve to nothing changed.

Above: measured first, baseline second. A new id means live prose cites a rule
no document defines and the registry does not carry -- register it in
`bin/sd_rules.py`, or repoint the prose. One fewer is the good case: drop it
from `DANGLING_RULE_IDS` in the same change.""")

    def test_live_citations_resolving_only_into_the_archive_match_their_baseline(self):
        """The backfill's meter.

        A live document citing a rule whose only definition is an archived
        planning page is citing a source the pack has stopped maintaining. Each
        id moved into a registry row takes this number down by one, and this
        assertion is what proves it fell rather than being asserted to have.
        """

        cited = cited_rule_ids(live_only=True)
        archive_only = defined_rule_ids(live_only=False) - defined_rule_ids(live_only=True)
        stranded = sorted((cited & archive_only) - registered_rule_ids())
        self.assertEqual(len(stranded), ARCHIVE_ONLY_CITATIONS, f"""
Live prose citations resolving only into `docs/work/archive` changed.

{_lines(stranded)}

Measured {len(stranded)} against a baseline of {ARCHIVE_ONLY_CITATIONS}. Moving
one into a registry row lowers it; lower `ARCHIVE_ONLY_CITATIONS` in the same
change. A rise means a new live document started citing an archived ruling.""")

    def test_every_dangling_baseline_entry_still_earns_its_place(self):
        """A baseline entry for an id nobody cites any more is a stale record.

        The same rule `tests/test_code_health.py` applies to its own baselines:
        an exemption that outlives the thing it exempts is a sentence nobody
        will ever re-read, and it makes the count look like work remaining when
        the work is done.
        """

        cited = cited_rule_ids(live_only=True)
        dead = sorted(DANGLING_RULE_IDS - cited)
        self.assertEqual(dead, [], f"""
`DANGLING_RULE_IDS` names ids no live document cites any more.

{_lines(dead)}

Delete these entries.""")


if __name__ == "__main__":  # pragma: no cover - the suite runs this by module
    unittest.main()
