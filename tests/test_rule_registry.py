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

#: The runs a claim may occupy. sd:622 exists because these three were all
#: defensible readings of one corpus and none of them had ever been written
#: down as code, so "how many uncited claims are there" had no reproducible
#: answer. `prd.md` pinned 263. The delivery note for steps 1 to 3 offered 8,
#: 97 and 275 for the three shapes. Reconstructing those same three shapes
#: independently on `239ff624` produced a third set of figures again, because
#: each reconstruction had to invent the counting rule the original never
#: recorded.
#:
#: So no rival number is quoted here, and none should be quoted anywhere else.
#: The rejected readings are kept as code instead: `PARAGRAPH` and `DOCUMENT`
#: are runnable, their answer is whatever they return on the day you run them,
#: and `TheClaimPredicate` runs all three. The only figure this module records
#: is `UNCITED_SKILL_CLAIMS`, which is a PROJECTION of `claims_in` and not its
#: return value: `claims_in` yields every matching `(line, run, ids)` tuple, and
#: `uncited_skill_claims` filters those to the ones with empty `ids` and counts
#: them per document. Reading the dict as "what `claims_in` returns" is how the
#: next baseline update goes to the wrong value.
LINE = "line"
PARAGRAPH = "paragraph"
DOCUMENT = "document"
CLAIM_SCOPES = (LINE, PARAGRAPH, DOCUMENT)

#: **The reading in force, and the whole of it.** A claim is one line carrying
#: an enforcement verb *and* naming a pack tool or a test.
#:
#: Three properties of that sentence were load-bearing and unrecorded, and each
#: is now pinned by a test in `TheClaimPredicate` so that changing one is a
#: decision somebody makes rather than a number that moves:
#:
#: 1. **The scope is one line**, not a paragraph and not a document. A verb and
#:    a tool name in the same paragraph are not a claim about that tool.
#: 2. **The verbs are matched as written**, in lower case. `ENFORCEMENT` carries
#:    no `IGNORECASE`, so a bullet opening *"**Never accept a repo path**"* --
#:    this pack's most common way of writing a rule -- is invisible to leg b.
#:    Measured on `239ff624`, reading the verbs case-insensitively would find 12
#:    claims where the shipped predicate finds 8. That is a false negative worth
#:    naming and it is left standing: widening the predicate is a change to the
#:    rule, not a recording of it, and `design.md` accepted false negatives in
#:    writing because a ratchet with them still only moves one way.
#: 3. **The subject is enumerated, never listed** -- `pack_nouns` reads `bin/`
#:    and `tests/` off the index, so a tool built next month is covered the day
#:    it is written.
CLAIM_SCOPE = LINE

#: A definition of a rule id, as this repository has always written one: a run
#: of bold text opening with the id. There is no other form, because until now
#: there was no registry -- which is the finding, not an accident.
#:
#: Built from `sd_rules.RULE_ID` rather than restating it. A second copy of the
#: grammar is the second-list defect this module exists to end, and writing one
#: here -- inside the check that ends it -- is the shape review already caught
#: once in this branch. `test_the_rule_id_grammar_has_one_source` holds it.
DEFINITION = re.compile(r"\*\*(" + sd_rules.RULE_ID.pattern + r")")

#: A quoted run in a file no Python parser will read. Single and double quotes
#: stop at a newline; a backtick run does not, because a JavaScript template
#: literal spans lines and a reader that stopped at the first one would miss
#: every line but its opening.
QUOTED = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"|`[^`]*`", re.DOTALL)

#: A fence opening or closing a code block. A `#` line inside one is shell or
#: Python, never a heading.
FENCE = re.compile(r"^\s*(?:```|~~~)")

#: An ATX heading, and the only form this repository's skills use.
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")


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
#: 26 of them on `cddd3b98`. More than half the rule ids in live prose point
#: only into the archive -- into pages this pack's own citation gate treats as
#: historical records rather than as current statements.
#:
#: This is the backfill's meter. Each id moved into a registry row takes one
#: entry out, and the assertion below proves it went.
#:
#: A set, not a count, for the reason `DANGLING_RULE_IDS` already gives: no
#: arithmetic can hide one behind another being fixed. Held as a count, this
#: baseline passed unchanged when one stranded id was resolved and a different
#: one was newly stranded in the same change -- two baselines in one file
#: keeping two different standards, which review caught.
#:
#: **25 on this branch, down from the 26 measured on `cddd3b98`.** `R10-D5` is
#: a row in `bin/sd_rules.py` now.
#:
#: `R10-D6` is NOT, and the reason is worth keeping because it is a gap in the
#: registry rather than in the rule. Its enforcement exists and is good --
#: `tests/test_verb_inventory.py::test_no_command_accepts_a_repository_path`
#: enumerates `bin/` with `iterdir()`, parses each file, and asserts no command
#: declares a repo-path option. But that is a TEST, and `Rule.checker` holds a
#: function object imported by `bin/sd_rules.py`, which cannot import `tests/`.
#: `R10-D5`'s checker is runtime code carrying its own refusal; `R10-D6`'s is a
#: test over the tree. The field means two different things and the registry has
#: no way to name the second. Registering `sd_lib.repo_root` papered over that:
#: it is the resolver the rule CONSTRAINS, not a guard -- it accepts a `start`
#: path, so it is the mechanism by which the rule would be broken. Settle what
#: `checker` names before this row returns.
#:
#: The other twenty-four were each looked at and each has a recorded reason it
#: is not a row yet, in the backfill section of this item's `implement.md`,
#: rather than left for the next reader to rediscover.
STRANDED_RULE_IDS = frozenset({
    "R10-D1", "R10-D2", "R10-D3", "R10-D4", "R10-D6", "R10-D7",
    "R11-D10", "R11-D12", "R11-D13", "R11-D14", "R11-D15", "R11-D16",
    "R11-D17", "R11-D18", "R11-D19", "R11-D20", "R11-D21", "R11-D23",
    "R11-D24", "R11-D25", "R11-D27", "R11-D29", "R11-D4", "R11-D5", "R11-D6",
})

#: Tool-behaviour claims in skills that cite no rule id, per document.
#: Measured on `cddd3b98`, and unchanged on `239ff624`, by `uncited_skill_claims`
#: below -- which is to say by `claims_in`, and by nothing else. `CLAIM_SCOPE`
#: says what that predicate is and which properties of it are load-bearing;
#: this is only where its answer is written down.
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


#: Tracked files the walk could not read, or that resolve outside the
#: repository. Never silently dropped: `test_the_corpus_is_whole` names them.
UNREADABLE: list[str] = []


def read_corpus(*pathspecs: str) -> list[tuple[str, str]]:
    """Every tracked file matching `pathspecs`, as `(path, text)`, minus this one.

    Read with `errors="replace"` rather than filtered by suffix: a rule id
    cited from a shell script, a JSON schema or a workflow is still a citation,
    and picking suffixes by hand would be the listed-roster mistake one layer
    down.

    **Never `continue` without recording.** The first draft swallowed `OSError`
    so that "a permission accident should not silently empty a baseline" -- and
    silently emptying a baseline is exactly what it did. A tracked file that
    cannot be read drops out of leg b's measured set, the count falls, and an
    equality baseline that only ever fires upward reports success on a smaller
    corpus. `tests/test_code_health.py` states the rule this now follows: *"The
    measurement must fail loudly rather than pass on a smaller corpus."*

    **Resolved and contained before it is opened.** `git ls-files` lists a
    symlink as readily as a regular file and `read_text` follows it, so a
    tracked `skills/x.md -> /etc/passwd` would read a file of the tree's
    choosing into the census. `contained` in `tests/test_doc_citations.py`
    already guards its corpus this way, for the same reason and against the
    same hole.
    """

    corpus = []
    inside = REPO_ROOT.resolve()
    for path in tracked_paths(*pathspecs):
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative == SELF:
            continue
        try:
            resolved = path.resolve(strict=True)
        except OSError as failure:
            UNREADABLE.append(f"{relative}: will not resolve ({failure})")
            continue
        if not resolved.is_relative_to(inside):
            UNREADABLE.append(f"{relative}: resolves outside the repository, "
                              f"to {resolved}")
            continue
        try:
            corpus.append((relative, path.read_text(encoding="utf-8",
                                                    errors="replace")))
        except OSError as failure:
            UNREADABLE.append(f"{relative}: will not read ({failure})")
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


def claim_spans(text: str, scope: str) -> list[tuple[int, str]]:
    """The runs of `text` one claim may occupy, as `(first line, run)`.

    The three readings of `CLAIM_SCOPE`, side by side and executable, so the
    rejected ones stay reproducible instead of surviving as numbers in a
    document. `TheClaimPredicate` runs all three over the live corpus.
    """

    if scope == LINE:
        return list(enumerate(text.splitlines(), 1))
    if scope == DOCUMENT:
        return [(1, text)]
    if scope != PARAGRAPH:
        raise ValueError(f"{scope!r} is not one of {CLAIM_SCOPES}")
    spans, start, block = [], 1, []
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip():
            if not block:
                start = number
            block.append(line)
        elif block:
            spans.append((start, "\n".join(block)))
            block = []
    if block:
        spans.append((start, "\n".join(block)))
    return spans


def claims_in(text: str, subject: re.Pattern[str], *,
              scope: str = CLAIM_SCOPE) -> list[tuple[int, str, list[str]]]:
    """Every tool-behaviour claim in one document, as `(line, run, rule ids)`.

    **This function is the definition.** Nothing else decides what a claim is:
    `skill_claims` walks the corpus and hands each document here, and the
    baseline is whatever this returns. See `CLAIM_SCOPE` for why that mattered
    enough to be said out loud.
    """

    return [(number, run, sd_rules.RULE_ID.findall(run))
            for number, run in claim_spans(text, scope)
            if ENFORCEMENT.search(run) and subject.search(run)]


def skill_claims(scope: str = CLAIM_SCOPE) -> list[tuple[str, int, str, list[str]]]:
    """Every tool-behaviour claim in a skill, as `(path, line, text, rule ids)`.

    The predicate is deliberately narrow and will have false negatives, which
    the design accepted in writing: this is a ratchet on new claims, not an
    audit of old ones, and a ratchet with false negatives still only moves one
    way. A predicate wide enough to catch every claim reddens thousands of
    lines on its first run, and a check that does that is not adopted, it is
    disabled.
    """

    subject = names_a_pack_noun()
    return [(relative, number, run.strip(), ids)
            for relative, text in read_corpus(f"{SKILLS}*.md", f"{SKILLS}**/*.md")
            for number, run, ids in claims_in(text, subject, scope=scope)]


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


def consumer_sources() -> list[tuple[str, str]]:
    """Every tracked file under `bin/` and `dashboard/`, Python or not.

    Not "every file that parses as Python", which is what this was and which
    made `dashboard/app.js` invisible -- the one tracked file here that is not
    Python, and the same file an independent sd:525 pass named as the blind
    spot of this repository's other AST-only locator. A scope that silently
    drops the only file it cannot parse is the defect this module exists to
    end, committed inside the check built to end it.
    """

    return [(relative, text) for relative, text in read_corpus("bin", "dashboard")
            if relative != "bin/sd_rules.py"]


def second_list_entries() -> list[tuple[str, int, str]]:
    """Registry rule ids written as data outside the registry module.

    A rule id in a *comment or a docstring* is a citation, and citing a rule is
    the point. A rule id in any other string is data: a consumer restating what
    the table already says, which is the second list `CLASSES` in
    `bin/sd-status` was shaped to make impossible.

    Two readers, because the corpus has two kinds of file. Python goes through
    `ast`, which tells a docstring from a string constant exactly. Everything
    else has no parser here and goes through `QUOTED`, which reads quoted runs
    only -- so `// see R11-D20` in `dashboard/app.js` stays a citation while
    `["R11-D20"]` does not. What neither reader sees is stated on the test.

    Empty while the table is empty, which is what lets the table land first.
    The first row for a rule some consumer already names in a string fails
    here on the spot -- and `bin/sd-status` carries `R10-D1` in a `CLASSES`
    row today, so that is not a hypothetical.
    """

    registered = registered_rule_ids()
    offenders = []
    for relative, text in consumer_sources():
        for number, identifier in _data_rule_ids(text):
            if identifier in registered:
                offenders.append((relative, number, identifier))
    return offenders


def _data_rule_ids(text: str) -> list[tuple[int, str]]:
    """Rule ids written as data, as `(line, id)`, by whichever reader fits."""

    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return _quoted_rule_ids(text)
    return [(node.lineno, identifier)
            for node in _data_strings(tree)
            for identifier in sd_rules.RULE_ID.findall(node.value)]


def _quoted_rule_ids(text: str) -> list[tuple[int, str]]:
    """Rule ids inside quoted runs of a file no Python parser will read."""

    found = []
    for run in QUOTED.finditer(text):
        for match in sd_rules.RULE_ID.finditer(run.group()):
            offset = run.start() + match.start()
            found.append((text.count("\n", 0, offset) + 1, match.group()))
    return found


def _data_strings(tree: ast.AST) -> list[ast.Constant]:
    """Every string constant that is not documentation."""

    prose = {id(node.value) for node in ast.walk(tree)
             if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in prose]


def markdown_headings(text: str) -> set[str]:
    """Every real heading in a document, with fenced blocks excluded.

    The fence tracking is the half that is easy to skip and wrong to skip: a
    `# install the thing` line inside a ```sh block is a shell comment, and a
    registry row naming it would point at a section that does not exist while
    passing a check that said it did.
    """

    headings: set[str] = set()
    fenced = False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = HEADING.match(line)
        if match:
            headings.add(match.group(1).strip())
    return headings


def section_body(text: str, heading: str) -> str:
    """The lines under `heading`, to the next heading of the same or higher level.

    Leg a's guarantee is that the rule is taught *where the row says it is
    taught*. Aggregating ids across every skill document, which is what this
    replaced, satisfied that sentence with a citation in an unrelated skill --
    the row could point at a real heading whose section never mentions the id,
    and both leg a and the section check passed.
    """

    body: list[str] = []
    depth = None
    fenced = False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            if depth is not None:
                body.append(line)
            continue
        match = None if fenced else HEADING.match(line)
        level = len(line) - len(line.lstrip("#")) if match else 0
        if match and match.group(1).strip() == heading and depth is None:
            depth = level
            continue
        if depth is not None:
            if match and level <= depth:
                break
            body.append(line)
    return "\n".join(body)


def teaching_section_errors() -> list[str]:
    """Every live row whose `teaches` does not resolve to a real section.

    `teaches` is `path#heading` and both halves have to be there. The first
    draft of this used `str.partition`, which returns an empty heading for a
    `teaches` carrying no `#` at all, and then skipped the check on exactly
    that case -- so the malformed value was the one value that passed. The
    second half matched the heading as a *substring of the whole document*,
    which any phrase in any paragraph satisfies.
    """

    documents = dict(skill_documents())
    broken = []
    for rule in sd_rules.RULES:
        if rule.state != sd_rules.LIVE:
            continue
        path, separator, heading = rule.teaches.partition("#")
        heading = heading.strip()
        if not (separator and path and heading):
            broken.append(
                f"{rule.id}: teaches={rule.teaches!r} is not `path#heading`")
        elif path not in documents:
            broken.append(f"{rule.id}: no skill document at {path!r}")
        elif heading not in markdown_headings(documents[path]):
            broken.append(f"{rule.id}: {path} carries no heading {heading!r}")
    return broken


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
        that does not exist raises at import. This asserts the two things the
        import cannot: that a live row's checker is callable, and that a
        repealed row holds `None` exactly -- a withdrawn rule has nothing left
        to run, and a stale name left in its place is a tombstone that still
        looks like a checker.
        """

        wrong = []
        for rule in sd_rules.RULES:
            if rule.state == sd_rules.LIVE and not callable(rule.checker):
                wrong.append(f"{rule.id}: live, but its checker "
                             f"{rule.checker!r} is not callable")
            elif rule.state == sd_rules.REPEALED and rule.checker is not None:
                wrong.append(f"{rule.id}: repealed, but still holds "
                             f"{rule.checker!r}")
        self.assertEqual(wrong, [], f"""
A registry row's checker does not match its state.

{_lines(wrong)}

A `live` row must hold a callable. A `repealed` row must hold `None` -- not a
leftover name, which the first form of this check accepted: `(state == LIVE)
!= callable(checker)` is False for a repealed row holding the *string*
"stale_name", because neither side is true.""")

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

    def test_every_row_is_completely_filled_in(self):
        """Every field a consumer reads is present and recognised.

        `scope` and `state` are read by consumers, so a typo must fail here.
        `subject` -- what the rule checks, in words -- was checked by nothing,
        so a row with `subject=""` passed every test and the registry could
        carry a rule nobody could describe. `tests/test_sd_status.py` holds
        `CLASSES` to the same standard, asserting `kind.source and kind.what`
        on the table this one is modelled on.
        """

        wrong = []
        for rule in sd_rules.RULES:
            if not rule.subject.strip():
                wrong.append(f"{rule.id}: no subject -- say what it checks")
            if not rule.teaches.strip():
                wrong.append(f"{rule.id}: no teaches -- say where it is taught")
            if rule.scope not in sd_rules.SCOPES:
                wrong.append(f"{rule.id}: scope={rule.scope!r} is not one of "
                             f"{sd_rules.SCOPES}")
            if rule.state not in sd_rules.STATES:
                wrong.append(f"{rule.id}: state={rule.state!r} is not one of "
                             f"{sd_rules.STATES}")
        self.assertEqual(wrong, [], f"""
A registry row is missing a field a consumer reads.

{_lines(wrong)}""")

    def test_no_consumer_carries_a_second_list(self):
        """A rule id written as data outside the registry is a second list.

        This is requirement 1's only mechanical check, and it is the one that
        would have caught the drift `CLASSES` was built to prevent: a consumer
        that names a rule in a string has taken a copy of the table, and a copy
        is a thing that can disagree.

        **What it reads.** Every tracked file under `bin/` and `dashboard/`,
        including the ones that are not Python. `dashboard/app.js` is the only
        such file today and it was invisible until review said so.

        **What it cannot see, which is stated rather than left to be found.**

        1. In a non-Python file there is no parser, only quoted runs. A rule id
           inside a quoted run *in a comment* reads as data, and one built by
           concatenation -- `"R11-" + "D20"` -- reads as neither.
        2. In Python, a string constant holding embedded CSS or JavaScript
           reads as data throughout, including where the id sits in that
           embedded language's own comment. `dashboard/server.py` carries
           `R11-D20` exactly that way today, so registering `R11-D20` would
           report it.

        Both are over-reports rather than misses, which is the safe direction
        for this check: the failure names a line, and a reader can see at once
        whether it is a copy of the table or a citation that needs rephrasing.
        """

        offenders = second_list_entries()
        self.assertEqual(offenders, [], f"""
A registry rule id appears as data outside `bin/sd_rules.py`.

{_lines(f"{path}:{line} carries {identifier}" for path, line, identifier in offenders)}

Read the id off `sd_rules.RULES` or `sd_rules.BY_RULE_ID` instead. A rule id in
a comment or a docstring is a citation and is fine; one in any other string is
a copy of the table.

Two shapes are reported that are citations rather than copies, because neither
reader can tell: a rule id inside a quoted run in a non-Python comment, and one
inside embedded CSS or JavaScript held in a Python string. Rephrase the
citation so it sits outside the quotes.""")


    def test_the_rule_id_grammar_has_one_source(self):
        """`DEFINITION` is built from `sd_rules.RULE_ID`, never beside it.

        Two regular expressions describing one grammar are two things that can
        disagree, which is the defect the registry exists to end. This holds
        the derivation structurally -- the id pattern is *inside* the
        definition pattern -- and behaviourally, so a derivation that compiled
        but matched differently still fails.
        """

        self.assertIn(sd_rules.RULE_ID.pattern, DEFINITION.pattern,
                      "DEFINITION restates the rule-id grammar instead of "
                      "building on sd_rules.RULE_ID")
        for sample in ("R1-D1", "R11-D46", "R123-D7"):
            self.assertTrue(sd_rules.RULE_ID.fullmatch(sample), sample)
            self.assertEqual(DEFINITION.findall(f"**{sample}**, a rule."),
                             [sample], sample)
        for reject in ("Q1-D1", "R1-E1", "RD1"):
            self.assertIsNone(sd_rules.RULE_ID.fullmatch(reject), reject)
            self.assertEqual(DEFINITION.findall(f"**{reject}**, not a rule."),
                             [], reject)

    def test_the_corpus_is_whole(self):
        """Every tracked file was read, and every one of them is in the tree.

        The measurement must fail loudly rather than pass on a smaller corpus,
        which is the rule `tests/test_code_health.py` states for its own walk.
        A tracked file that cannot be read drops out of leg b's measured set
        and the count falls, and an equality baseline reports success on the
        smaller corpus. A tracked symlink pointing out of the repository is the
        same hole from the other side: it reads a file of the tree's choosing
        into the census.
        """

        UNREADABLE.clear()
        read_corpus()
        self.assertEqual(UNREADABLE, [], f"""
A tracked file could not be read, or resolves outside the repository.

{_lines(UNREADABLE)}

Every baseline in this module is measured over that corpus, so none of them
means anything until this is clear.""")


# --------------------------------------------------------------------------
# Leg a -- every rule is taught
# --------------------------------------------------------------------------


class LegA(unittest.TestCase):
    """A rule nobody teaches is a rule authors meet only as a CI failure."""

    def test_every_live_rule_is_cited_by_the_section_that_teaches_it(self):
        """The rule id appears in the body of the section the row names.

        Not "somewhere in `skills/`", which is what this asked first. A row can
        point at a real heading whose section never mentions the id while an
        unrelated skill happens to cite it, and the aggregate form passed on
        exactly that -- so leg a's stated guarantee, that the rule is taught
        where the row says it is taught, was not what it checked.

        Citation is what is checked. *Not restating the rule* is the other half
        of the convention and it has no mechanical check -- judging whether two
        English sentences say the same thing is not a test -- so it is left as
        a review habit and recorded as an accepted gap, rather than asserted
        here as an enforcement with no enforcer. Committing that defect inside
        the check built to end it would be absurd.
        """

        documents = dict(skill_documents())
        untaught = []
        for rule in sd_rules.RULES:
            if rule.state != sd_rules.LIVE:
                continue
            path, _, heading = rule.teaches.partition("#")
            if path not in documents:
                # Reported by the section check, which owns that failure.
                continue
            body = section_body(documents[path], heading.strip())
            if rule.id not in body:
                untaught.append(f"{rule.id}: {rule.teaches} does not cite it")
        self.assertEqual(untaught, [], f"""
A live registry rule is not cited by the section that teaches it.

{_lines(untaught)}

Cite the id inside that section. A citation elsewhere in `skills/` does not
count: the row names where the rule is taught, and that is where a reader who
follows the row will look.""")

    def test_every_live_rule_points_at_a_skill_section_that_exists(self):
        """`teaches` is `path#heading`, and every part of that has to resolve.

        A row pointing at a deleted skill, at a heading somebody renamed, or at
        a phrase that is only body prose is the registry's own version of the
        drift it exists to catch. The heading is matched against the document's
        real headings, fenced blocks excluded -- not as a substring of the
        whole document, which any paragraph would satisfy.

        Fires on nothing while `RULES` is empty. The first row added is what it
        would otherwise wrongly accept, which is the whole point of the leg.
        """

        broken = teaching_section_errors()
        self.assertEqual(broken, [], f"""
A registry row teaches from a section that does not exist.

{_lines(broken)}

`teaches` is `path#heading`. Both halves are required, and the heading must be
a real markdown heading in that document.""")


# --------------------------------------------------------------------------
# Leg b's predicate -- one recorded definition, not three readings
# --------------------------------------------------------------------------


class TheClaimPredicate(unittest.TestCase):
    """sd:622. What counts as a claim, pinned instead of remembered.

    Leg b's baseline was argued three ways before it landed and no reading of
    it was ever written as code, so the number it produced could not be
    reproduced from the repository -- which made it a claim about the
    repository with nothing linking it to the machinery, the exact defect the
    registry exists to end, committed by the registry.

    These tests do not judge the predicate. They record it, so that widening it
    is a change somebody signs rather than a baseline that moves.
    """

    #: A verb and a tool name, split across two lines. The only property that
    #: matters is that neither line carries both, which is what separates the
    #: line reading from the two wider ones.
    SPLIT = "The report from sd-status is the one to read.\nIt refuses a second.\n"

    #: The same two facts on one line.
    JOINED = "The report from sd-status refuses a second.\n"

    def test_a_claim_is_one_line_and_the_wider_readings_are_not_in_force(self):
        """The scope in force is the line, and the fixture proves which.

        `CLAIM_SCOPE == LINE` on its own is a constant asserting itself. The
        fixture is what makes it evidence: the same two sentences are one claim
        when they share a line and no claim when they do not, and a predicate
        that had quietly become paragraph-scoped would say one both times.
        """

        subject = names_a_pack_noun()
        self.assertEqual(CLAIM_SCOPE, LINE, "the shipped reading is the line")
        self.assertEqual(claims_in(self.SPLIT, subject), [])
        self.assertEqual(len(claims_in(self.JOINED, subject)), 1)
        self.assertEqual(len(claims_in(self.SPLIT, subject, scope=PARAGRAPH)), 1)
        self.assertEqual(len(claims_in(self.SPLIT, subject, scope=DOCUMENT)), 1)

    def test_the_rejected_readings_stay_reproducible_and_stay_wider(self):
        """All three readings run over the live corpus, and the shipped one is least.

        The rejected readings are kept executable rather than remembered as
        numbers. A number in a document is what sd:622 is about: 263, 97, 275,
        63 and 176 were all offered for this corpus by predicates nobody wrote
        down, and not one of them can be checked today. These can, on whatever
        the corpus is at the time.

        The assertion is containment, not a count, because a count here would
        be a second baseline restating `UNCITED_SKILL_CLAIMS` -- and because
        counts do not order across these scopes at all: a document read whole
        is one span, so the widest reading yields the fewest *spans* while
        reaching the most documents. That asymmetry is itself worth pinning,
        since it is how two people measuring "the same thing" three ways got
        three numbers and each believed the others had miscounted.
        """

        reached = {scope: {path for path, *_ in skill_claims(scope)}
                   for scope in CLAIM_SCOPES}
        self.assertLessEqual(reached[LINE], reached[PARAGRAPH], reached)
        self.assertLessEqual(reached[PARAGRAPH], reached[DOCUMENT], reached)
        self.assertEqual(reached[CLAIM_SCOPE], reached[LINE], reached)
        self.assertTrue(reached[LINE], "the corpus carries no claims at all")

    def test_an_enforcement_verb_is_matched_as_written(self):
        """Lower case only, and the cost of that is named rather than found later.

        `ENFORCEMENT` carries no `IGNORECASE`. A bullet opening *"**Never accept
        a repo path**"* is therefore not a claim, and that shape is how this
        pack most often writes a rule. The property is pinned here so that
        widening it reads as a decision; the measured cost of leaving it is in
        `CLAIM_SCOPE`.
        """

        self.assertIsNone(ENFORCEMENT.search("Never accept a repo path"))
        self.assertIsNotNone(ENFORCEMENT.search("it never accepts a repo path"))
        self.assertFalse(ENFORCEMENT.flags & re.IGNORECASE)

    def test_the_subject_of_a_claim_is_enumerated_and_not_listed(self):
        """`pack_nouns` reads the tree, so a new tool needs nobody to remember it.

        A hand-kept roster of tool names is the listed-roster defect one layer
        down, and it would make leg b quietly stop covering everything written
        after the day the list was typed.

        **The matcher is exercised, not just the enumeration.** The first form
        of this test asserted only that `pack_nouns` reads the index, and
        mutation caught it: hard-coding the roster inside `names_a_pack_noun`
        -- the function that actually feeds the predicate -- left this test
        green and reddened only the baseline, which is the wrong test failing
        and sends the reader to a count instead of to the roster.
        """

        nouns = pack_nouns()
        self.assertIn("sd-status", nouns)
        self.assertIn("test_rule_registry", nouns)
        self.assertEqual(nouns, frozenset(
            {path.name for path in tracked_paths("bin")}
            | {path.stem for path in tracked_paths("tests/test_*.py")}))
        subject = names_a_pack_noun()
        missed = sorted(name for name in nouns
                        if not subject.search(f"the {name} tool"))
        self.assertEqual(missed, [], f"""
The claim subject does not match every name enumerated from the tree.

{_lines(missed)}

`names_a_pack_noun` builds its alternation from `pack_nouns`. A name the
enumeration carries and the matcher misses means the matcher has a roster of
its own.""")

    def test_an_unknown_scope_is_refused_rather_than_silently_read(self):
        """A typo must not fall through to whichever branch is last."""

        with self.assertRaises(ValueError):
            claim_spans("anything", "sentence")


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
        """The backfill's meter, held as a set rather than as a count.

        A live document citing a rule whose only definition is an archived
        planning page is citing a source the pack has stopped maintaining. Each
        id moved into a registry row takes one entry out, and this assertion is
        what proves it went rather than being asserted to have.

        The count form of this passed a change that resolved one stranded id
        and stranded a different one, because 26 is 26. `DANGLING_RULE_IDS` was
        already a set, and its reason applies here word for word: no arithmetic
        can hide one behind another being fixed.
        """

        cited = cited_rule_ids(live_only=True)
        archive_only = defined_rule_ids(live_only=False) - defined_rule_ids(live_only=True)
        stranded = (cited & archive_only) - registered_rule_ids()
        self.assertEqual(stranded, STRANDED_RULE_IDS, """
Live prose citations resolving only into `docs/work/archive` changed.

Above: measured first, baseline second. An id that appeared is a live document
newly citing an archived ruling. An id that went is the good case -- moved into
a registry row, or its prose repointed -- so drop it from `STRANDED_RULE_IDS`
in the same change.""")

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
