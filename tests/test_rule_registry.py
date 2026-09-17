"""The rule registry and the four-legged meta-check that keeps it honest.

`bin/sd_rules.py` answers "which rules exist". This module is what stops that
answer and the repository drifting apart, and it is the deliverable: legs a to d
below are worth more than any number of rules, because rules with no meta-check
start drifting the day they land.

The four legs fail independently, and each one catches a different way the
sentence and the machinery come apart:

    a. a registry rule no skill teaches -- a rule authors meet only as a CI
       failure, never while they are writing;
    b. a skill claiming a tool behaviour with no rule id behind it -- prose
       asserting an enforcement nothing performs, which is the defect that
       let `WORKFLOW.md` claim for weeks that every writing skill refuses the
       upstream tree while nothing refused;
    c. a rule id cited in live prose that the registry does not carry -- a
       deleted checker leaving live prose behind;
    d. a row whose named checker does not redden when its rule is violated --
       a checker that exists and enforces nothing.

**Leg d is why the other three are worth anything.** Legs a to c landed first
and each asserted a *link*: a row is taught, a claim cites a row, a citation
resolves to a row. None of them looks at what the checker does. A row naming
`sd_lib.repo_root` -- the resolver by which its own rule would be violated --
passed every one of them, and the only reason it is not in the table today is
that a human reviewer read it. Leg d is that reader made mechanical: the row
states the mutation, and this module executes it.

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
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from typing import Iterable, NamedTuple
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_rules  # noqa: E402 - the table under test, imported for its own sake

# The module the code rules' checkers live in, imported for its constants and
# nothing else: the `R12-D*` subjects state a ceiling by value, and the value
# is read back off this module rather than trusted. The four mutations leg d
# runs against those checkers are built from the same constants, so a raised
# ceiling moves the violation with it instead of leaving a fixture green.
from tests import test_code_health as code_health  # noqa: E402

# The resolver for a `path::symbol` location, borrowed rather than rebuilt. It is
# the same function that resolves the `source:path::symbol` citations in this
# pack's documentation, which is the whole reason `Rule.checker` could stop being
# a callable: one resolver for both, so the registry did not bring a second
# source of truth about which declarations exist. A second AST walk here would be
# the defect this module exists to end.
from tests.test_doc_citations import source_declaration_error  # noqa: E402

#: Where the historical record lives. Archived planning documents are read for
#: *definitions*, because a rule defined there still answers a live citation,
#: but their own citations are not held to leg c: the ruling everywhere else in
#: this repository is to take the coverage and not buy it by editing history.
ARCHIVE = "docs/work/archive/"

#: This file, as the index names it. See the module docstring.
SELF = "tests/test_rule_registry.py"

#: Where the skills live, and the only scope leg b reads.
SKILLS = "skills/"

#: The module the code rules' checkers are declared in, as the index names
#: it. `test_a_code_health_subject_states_the_current_ceiling` selects rows by
#: this prefix rather than by a list of ids, so a fifth code-health row is
#: held to the same agreement the day it lands.
CODE_HEALTH = "tests/test_code_health.py"

#: How a subject states a ceiling: the constant's name in a code span, then
#: its value, `` `LENGTH_CEILING`, 50 ``. A name alone sends the reader to
#: look; a number alone is a number nothing can check.
STATED_CEILING = re.compile(r"`([A-Z][A-Z_]*)`, (\d+)\b")


def ceilings_read_by(checker: str) -> set[str]:
    """The integer constants of `tests/test_code_health.py` that `checker` reads.

    Off the checker's own body, so a subject is bound to the threshold its
    checker enforces rather than to any threshold that happens to exist. A
    name counts when the module holds an integer under it: `COMPLEX`, the
    baseline set the complexity test also reads, is not one.
    """

    tree = ast.parse((REPO_ROOT / CODE_HEALTH).read_text(encoding="utf-8"))
    bodies = [node for node in ast.walk(tree)
              if isinstance(node, ast.FunctionDef) and node.name == checker]
    return {node.id for body in bodies for node in ast.walk(body)
            if isinstance(node, ast.Name)
            and isinstance(getattr(code_health, node.id, None), int)
            and not isinstance(getattr(code_health, node.id), bool)}

#: Where the suites live. A checker declared under here *is* the enforcement,
#: rather than the code an enforcement reads, and leg d binds the two shapes to
#: their mutation differently. See
#: `test_every_mutation_touches_what_its_rows_checker_names`.
TESTS = "tests/"

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

#: A definition of a rule id, in every form this repository has written one.
#: Until sd:431 slice S2 the grammar was one form -- a bold run *opening* with
#: the id -- and three of the four ids leg c reported as defined nowhere were
#: defined in a form that grammar could not see. `TheDefinitionGrammar` holds
#: each form against a fixture, and the step-4 slice paragraph of this item's
#: `implement.md` names the archive lines they were read off.
#:
#: Two inline forms, read in every tracked file, because `tests/test_loc_caps.py`
#: defines three rules in its docstring and its comments and a suffix filter
#: would make them dangling:
#:
#: 1. a bold run that *contains* the id, anywhere in the run -- team-lead
#:    decision 2026-09-16, reversible by the owner, taken so that the one id
#:    defined in no other form, `R11-D46`, counts by the bold sentence that
#:    re-derives it rather than needing a separate answer;
#: 2. a bold run, opened and closed, and then on the same line the id opening
#:    a parenthesis, `**...** (id`. Paired, so that `x** (id)` in a comment is
#:    an exponent and not a run; same line, so that a bold sentence and a
#:    parenthesised id in the next paragraph are two things and not one.
#:
#: Two block forms, in `MARKDOWN_DEFINITION` below, read in Markdown only.
#:
#: Built from `sd_rules.RULE_ID` rather than restating it. A second copy of the
#: grammar is the second-list defect this module exists to end, and writing one
#: here -- inside the check that ends it -- is the shape review already caught
#: once in this branch. `test_the_rule_id_grammar_has_one_source` holds it.
#:
#: The bold run is delimited, not approximated. `BOLD_OPEN` is a `**` with
#: nothing word-like on its left and no whitespace on its right; `BOLD_CLOSE`
#: is a `**` with no whitespace on its left. The `**` that closes `**foo**` is
#: followed by a space or punctuation, so it never opens a run, and the plain
#: text between two bold runs stays plain. That matters here because this
#: item's own `implement.md` cites stranded ids in exactly that position,
#: between one bold slice heading and the next; `TheDefinitionGrammar` holds
#: it with a control. `BOLD_BODY` stops at the next `**` and at a blank line,
#: because a run does not cross a paragraph.
BOLD_OPEN = r"(?<![\w*])\*\*(?=\S)"
BOLD_CLOSE = r"(?<=\S)\*\*"
BOLD_BODY = r"(?:[^*\n]|\n(?![ \t]*\n)|\*(?!\*))*?"
DEFINITION = re.compile(
    "(?:"
    + BOLD_OPEN + BOLD_BODY
    + "(?=" + sd_rules.RULE_ID.pattern + BOLD_BODY + BOLD_CLOSE + ")"
    + "|" + BOLD_OPEN + BOLD_BODY + BOLD_CLOSE + r"[ \t]*\("
    + ")(" + sd_rules.RULE_ID.pattern + ")")

#: The two block forms, and why they read Markdown only: a `#` line in any
#: other file is a comment, and a comment cites -- `tests/test_loc_caps.py`
#: carries `# R11-D24's clause`, which is not where `R11-D24` is defined.
#: Measured on `2eafa78b`, reading `#` lines in every file moved six stranded
#: ids out of their baseline on the strength of code comments.
#:
#: 3. an ATX heading that contains the id;
#: 4. a table cell in which the id opens a parenthesis, `| label (id` -- any
#:    parenthesis in the cell, not the first, because a cell may carry a
#:    parenthesised aside before the one that names the rule.
#:
#: Both read after `prose_of` has blanked the fenced blocks, for the reason
#: `markdown_headings` tracks `FENCE`: a `## id` line or a `| label (id) |`
#: row inside a fenced example is an example, and reading it would let a
#: code sample move a baseline.
MARKDOWN_DEFINITION = re.compile(
    r"(?:^#{1,6}[ \t]+[^\n]*?|\|[^|\n]*\()(" + sd_rules.RULE_ID.pattern + ")",
    re.MULTILINE)

#: A code span. Blanked before a definition is read, because text inside one
#: is quoted rather than stated: on `2eafa78b` this item's own `implement.md`
#: quotes the archived `**...** (R5-D1)` line inside backticks, and read as
#: prose that quotation would have "defined" `R5-D1` live and moved it out of
#: both baselines at once. Not stopped at a newline, for the reason `QUOTED`
#: gives: the quotation spans one. Under the one-form grammar this blanking
#: changed nothing -- 51 defined ids, 18 live, with and without it.
#:
#: Replaced by `CODE_SPAN_STANDIN` rather than by a space, because a bold run
#: may open with a code span -- `**\`mode: minimal\` and ... refuse it**` in
#: `skills/sd-review/SKILL.md` does -- and `BOLD_OPEN` wants a non-space on
#: its right. The stand-in is neither whitespace nor a word character, so it
#: neither closes a run nor glues to one.
CODE_SPAN = re.compile(r"`[^`]*`")
CODE_SPAN_STANDIN = "~"

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
#: registry, not in a live document, not even in the archive. Four on
#: `cddd3b98`, the same four the planning pass found on `e6c2cb20`, and
#: **empty since sd:431 slice S2**, which widened `DEFINITION` rather than
#: repointing them: three of the four were defined in the archive in a form
#: the one-form grammar could not see and are stranded now, and the fourth is
#: defined by the bold sentence that re-derives it, under the decision
#: recorded on `DEFINITION`. Nothing was registered and no prose moved.
#:
#: Held as a set rather than a count, because the set is the better record: a
#: new dangling id fails by name on the line that invented it, and no
#: arithmetic can hide one behind another being fixed.
#:
#: Resolving one means either registering it or repointing the prose that cites
#: it, and then removing it here in the same change.
DANGLING_RULE_IDS: frozenset[str] = frozenset()

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
#: **20 before slice D and 19 since, down from the 26 measured on `cddd3b98`.** `R10-D5`,
#: `R10-D6` and `R10-D4` are rows in `bin/sd_rules.py` now. Three more went the
#: other way out: sd:719 step 3 deleted the only live files that cited them --
#: `dashboard/plugins.py`, `dashboard/markup.py` and
#: `tests/test_dashboard_plugins.py` -- and nothing was registered for them. They
#: are named in that commit's message and not here, because a live comment
#: naming them is a live citation, and this set would measure them back in.
#:
#: `R10-D6` took two slices to land, and what held it is worth keeping. Its
#: enforcement was never in doubt --
#: `tests/test_verb_inventory.py::test_no_command_accepts_a_repository_path`
#: enumerates `bin/` with `iterdir()`, parses each file, and asserts no command
#: declares a repo-path option. The obstacle was the registry: `Rule.checker`
#: held a function object imported by `bin/sd_rules.py`, which cannot import a
#: test module, so the field could not name a test at all. The first attempt
#: papered over that with `sd_lib.repo_root`, which is the resolver the rule
#: CONSTRAINS rather than a guard on it -- it accepts a `start` path, so the row
#: named the mechanism by which the rule would be broken as its enforcement, and
#: the meta-check passed it. `checker` is a `path::symbol` location now, so a
#: test is nameable, and leg d is what makes naming one mean something.
#:
#: **Still 20 after sd:431 slice S2, and a different 20.** Widening
#: `DEFINITION` moved six ids in one change, three in and three out, which a
#: count would have reported as nothing happening. In: `R5-D1`, `R11-D1` and
#: `R11-D30`, out of `DANGLING_RULE_IDS`, because the archive defines each of
#: them in a form the grammar now reads. Out: `R10-D2`, `R11-D4` and
#: `R11-D20`, because a *live* file defines each of them in the same
#: closed-bold-then-parenthesis form as the archived `R5-D1` --
#: `skills/sd-handoff/SKILL.md` for `R10-D2`, `CONTRIBUTING.md` for `R11-D4`,
#: the module docstring of `dashboard/now.py` for `R11-D20` -- and a grammar
#: that reads the archive reads the live tree the same way. None of the three
#: was registered by S2; each became an id with a live definition and no row,
#: which is not what this set measures. `R10-D2` in particular no longer had
#: a meter entry for the repeal Dec-4 decided, so when that repeal landed as
#: the first `REPEALED` row, on 2026-09-16, this set did not move for it.
#: `R11-D4` and `R11-D20` are still rowless, and `R11-D20` came back in at
#: sd:719 step 6: `dashboard/now.py`, the one live file that defined it,
#: retired, so its definition is archive-only again while this file's own
#: prose still cites it.
#:
#: **18 after sd:719 step 6, 2026-09-16.** One in, `R11-D20`, as above. Two
#: went the way step 3's three did: step 6's module deletions under
#: `dashboard/` (the package marker stays until step 7) took the only live
#: files that cited them, and nothing was registered for them. They are named
#: in that commit's message and not here, for the reason step 3's paragraph
#: gives.
#:
#: **19 after sd:431 slice D, 2026-09-16.** `R10-D1` is a row. What held it
#: was not its enforcement -- `bin/sd-status::_age_rows` has flagged
#: `idle-planning` since the check existed -- but that the tool carried the
#: id in two strings, one of them the `CLASSES` cell the skill's table
#: mirrors, so registering it would have reddened the second-list check on
#: the spot. Owner decision Dec-3 rephrased both strings and moved the id
#: into the comments beside them, the way `R10-D5` cites itself in
#: `bin/sd_setup_github.py`; the skill's cell changed with the string, and
#: the id stays in that section's prose for leg a. Held until sd:10 cut the
#: age sweep (pack #995), because the threshold lived in the sweep module
#: until then.
#:
#: The rest were each looked at and each has a recorded reason it is not a
#: row yet, in the backfill section of this item's `implement.md`, rather
#: than left for the next reader to rediscover.
#: **17 after sd:431 step 8, slice 1, 2026-09-16.** `R10-D3` is a row, in
#: the narrowed form the audit of that step recorded: the design split
#: handoff into two lanes, Lane B is the repeal `R10-D2`, and what Lane A
#: holds as a rule is the restore hook's registration on `startup` and
#: `clear` and never on `compact`. Its checker is the hook table
#: `bin/sd_install.py::HOOK_SPECS`, pinned whole by
#: `tests/test_sd_install.py`, and the section that teaches it is the one
#: that states the matchers, `The restore side` in
#: `skills/sd-handoff/SKILL.md`, rather than the Lane B section that cited
#: the id already and teaches only what is not built.
#: **16 after sd:431 step 8, slice 2, 2026-09-17.** `R10-D7` is a row: the
#: local block reaching the prompt, held by `bin/sd-review::local_conventions`
#: and taught from a section of `skills/sd-review/SKILL.md` written for it,
#: `Local conventions reach the prompt`. The audit of that step found the id
#: cited by that function's docstring and by nothing under `skills/`.
STRANDED_RULE_IDS = frozenset({
    "R11-D1", "R11-D10", "R11-D13", "R11-D14", "R11-D15",
    "R11-D17", "R11-D20", "R11-D21",
    "R11-D24", "R11-D25", "R11-D27", "R11-D29", "R11-D30", "R11-D5", "R11-D6",
    "R5-D1",
})

#: Tool-behaviour claims in skills that cite no rule id, per document.
#: Measured on `cddd3b98`, and unchanged on `239ff624`, by `uncited_skill_claims`
#: below -- which is to say by `claims_in`, and by nothing else. `CLAIM_SCOPE`
#: says what that predicate is and which properties of it are load-bearing;
#: this is only where its answer is written down. `skills/sd-handoff/SKILL.md`
#: left the table when sd:10's 31(b1) cut the `stash_ref` field whose
#: "never pushed" line was its one claim.
#:
#: Per document rather than as one total, so a new uncited claim in `sd-ship`
#: fails even in a change that cleaned two out of `sd-plan`. One number for the
#: whole tree would net them off and say nothing.
UNCITED_SKILL_CLAIMS = {
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


def prose_of(text: str) -> str:
    """`text` with every fenced block and every code span blanked.

    A fenced line becomes an empty line rather than vanishing, so that a bold
    run cannot be read across the block that separated its halves. The fence
    walk is the one `markdown_headings` makes, and it is made on every file
    for the reason the bold forms are read in every file: a docstring can
    carry a fence as readily as a page can.
    """

    kept: list[str] = []
    fenced = False
    for line in text.splitlines(keepends=True):
        if FENCE.match(line):
            fenced = not fenced
            kept.append("\n")
            continue
        kept.append("\n" if fenced else line)
    return CODE_SPAN.sub(CODE_SPAN_STANDIN, "".join(kept))


def definitions_in(relative: str, text: str) -> set[str]:
    """Every rule id one file defines, by the forms `DEFINITION` and
    `MARKDOWN_DEFINITION` name.

    Fences and code spans are blanked first, and the block forms are read
    only when the file is Markdown; both reasons are on the patterns.
    """

    prose = prose_of(text)
    found = set(DEFINITION.findall(prose))
    if relative.endswith(".md"):
        found.update(MARKDOWN_DEFINITION.findall(prose))
    return found


def defined_rule_ids(*, live_only: bool) -> set[str]:
    """Every rule id a document defines, by the forms `definitions_in` reads."""

    found: set[str] = set()
    for relative, text in read_corpus():
        if live_only and relative.startswith(ARCHIVE):
            continue
        found.update(definitions_in(relative, text))
    return found


def registered_rule_ids() -> set[str]:
    """The registry's own answer, live rows and repealed rows alike.

    A repealed row still resolves a citation. That is the whole reason the
    state exists: prose citing a withdrawn rule must be answered, and the id
    must never be handed to a different rule later.
    """

    return {rule.id for rule in sd_rules.RULES}


def consumer_sources() -> list[tuple[str, str]]:
    """Every tracked file under `bin/`, Python or not.

    Not "every file that parses as Python", which is what this was and which
    made the pack dashboard's client script invisible -- until sd:719 step 6
    retired it, the one tracked file here that was not Python, and the same
    file an independent sd:525 pass named as the blind spot of this
    repository's other AST-only locator. A scope that silently drops the only
    file it cannot parse is the defect this module exists to end, committed
    inside the check built to end it; the scope stays whole after the file
    that taught it went, and after step 7 deleted the tree it was in.
    """

    return [(relative, text) for relative, text in read_corpus("bin")
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
    only -- so `// see R11-D20` in a JavaScript file stays a citation while
    `["R11-D20"]` does not (`dashboard/app.js` was that file until sd:719
    step 6). What neither reader sees is stated on the test.

    Empty while the table is empty, which is what lets the table land first.
    The first row for a rule some consumer already names in a string fails
    here on the spot -- and that was not a hypothetical: `bin/sd-status`
    carried `R10-D1` in a `CLASSES` row and in a reason string until
    2026-09-16, and registering it meant rephrasing both first.
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


def checker_location_errors(rule: sd_rules.Rule) -> list[str]:
    """Why a live row's `checker` does not resolve, or nothing at all.

    Four failures, and two of them the field's old shape made impossible to
    reach. A live row naming no checker: while `checker` held a function
    object, `callable(None)` caught that; now it is a string, so the emptiness
    is checked here rather than assumed away.

    And a checker path that leaves the checkout, which this caller has to
    reject itself. `source_declaration_error` returns `None` for a path
    resolving outside the tree, and that is deliberate -- it is how the
    citation rule keeps its containment exclusion, and other callers depend on
    it. Read here as *"valid checker"*, it is a hole: measured,
    `../outside.py` and `/etc/passwd` both come back `None` while
    `bin/nope.py` comes back `bin/nope.py: target is missing`. So the escape is
    refused before the shared resolver is asked, rather than by changing what
    the resolver means.
    """

    if not (rule.checker or "").strip():
        return [f"{rule.id}: live, but names no checker"]
    location = sd_rules.CHECKER.fullmatch(rule.checker or "")
    if not location:
        return [f"{rule.id}: checker={rule.checker!r} is not `path::symbol`"]
    path, symbol = location.groups()
    if not (REPO_ROOT / path).resolve().is_relative_to(REPO_ROOT):
        return [f"{rule.id}: checker path {path!r} resolves outside the "
                f"checkout, so no declaration here can answer it"]
    failure = source_declaration_error(REPO_ROOT, path, symbol)
    return [f"{rule.id}: {failure}"] if failure else []


#: The fields a repealed row must have surrendered. Both, not the checker
#: alone: a proof with no checker describes a mutation nothing runs, and on a
#: repealed row it is a tombstone as much as a stale checker name is.
TOMBSTONE_FIELDS = ("checker", "proof")


def tombstone_errors(rule: sd_rules.Rule) -> list[str]:
    """Why a repealed row is not a clean tombstone, or nothing at all.

    A withdrawn rule has nothing left to run, so a value in either field is
    reported by name. Separate from `checker_location_errors` so that a
    fixture row can be asked the question directly -- `sd_rules.RULES` holds
    only the valid tombstone, and a test that reads the real table can never
    reach the reporting branch.
    """

    return [f"{rule.id}: repealed, but still holds {field}={getattr(rule, field)!r}"
            for field in TOMBSTONE_FIELDS
            if getattr(rule, field) is not None]


def _lines(rows) -> str:
    return "\n".join(f"  {row}" for row in rows)


# --------------------------------------------------------------------------
# Step 1 -- the table keeps its own shape
# --------------------------------------------------------------------------


class Registry(unittest.TestCase):
    """The table's own tests. Zero rows passes every one of them."""

    def test_every_live_rule_names_a_checker_that_exists(self):
        """A row whose checker is missing is a failure, never a comment.

        `checker` is a `path::symbol` location, resolved by the function that
        resolves this pack's documentation citations, so a row naming a
        declaration that was renamed, moved or deleted fails here. That is the
        whole of what the field's old shape bought: a callable resolved at
        import, and an import proves only that the name is there. What it does
        is leg d's question, and asking it was the point of the change.

        A repealed row holds `None` exactly, in `checker` and in `proof` both
        -- a withdrawn rule has nothing left to run, and a stale name left in
        either place is a tombstone that still looks like a checker. The proof
        half was added with the first repeal, `R10-D2`: before it, a repealed
        row holding a proof and no checker was reported only by the pairing
        check below, as a proof with no checker, which is true and is not
        the diagnosis -- the row is repealed, and that is why it holds nothing.
        """

        wrong = []
        for rule in sd_rules.RULES:
            if rule.state == sd_rules.REPEALED:
                wrong += tombstone_errors(rule)
            else:
                wrong += checker_location_errors(rule)
        self.assertEqual(wrong, [], f"""
A registry row's checker or proof does not match its state.

{_lines(wrong)}

A `live` row must name one declaration that exists, as `path::symbol`. A
`repealed` row must hold `None` in `checker` and in `proof` -- not a leftover
name, which the first form of this check accepted: `(state == LIVE) !=
callable(checker)` is False for a repealed row holding the *string*
"stale_name", because neither side is true.""")

    def test_a_repealed_row_holding_a_checker_or_a_proof_is_reported_by_field(self):
        """The reporting branch, driven by fixture rows rather than the table.

        `sd_rules.RULES` carries one repealed row and it is a clean tombstone,
        so the test above never reaches the branch that reports a value; a
        change that dropped `proof` from `TOMBSTONE_FIELDS` would leave it
        green. Review said so. Three fixture rows ask the question directly:
        one holding a checker, one holding a proof, and the clean one as the
        control that the helper is not simply always red.
        """

        def repealed(**held) -> sd_rules.Rule:
            return sd_rules.Rule(id="R0-D0", subject="a fixture", checker=None,
                                 proof=None, scope="code", teaches="x#y",
                                 state=sd_rules.REPEALED)._replace(**held)

        self.assertEqual(tombstone_errors(repealed()), [])
        self.assertEqual(
            tombstone_errors(repealed(checker="bin/nope.py::guard")),
            ["R0-D0: repealed, but still holds checker='bin/nope.py::guard'"])
        self.assertEqual(
            tombstone_errors(repealed(proof="break the guard; a test goes red")),
            ["R0-D0: repealed, but still holds "
             "proof='break the guard; a test goes red'"])
        self.assertEqual(
            tombstone_errors(repealed(checker="bin/nope.py::guard", proof="x")),
            ["R0-D0: repealed, but still holds checker='bin/nope.py::guard'",
             "R0-D0: repealed, but still holds proof='x'"],
            "both fields are reported, checker first")

    def test_a_checker_outside_the_checkout_is_refused(self):
        """An escaping checker path is a failure here, not a silent pass.

        `source_declaration_error` answers `None` -- its word for *"nothing
        wrong"* -- for any path that resolves outside the checkout, and that is
        deliberate: it is how the citation rule keeps its containment exclusion,
        and the citation tests depend on it. Read by this caller as "the checker
        resolves", the exclusion becomes a hole through which `../outside.py`
        and `/etc/passwd` both pass while `bin/nope.py` fails. So the
        containment is the registry's own check, made before the shared resolver
        is asked.
        """

        for path in ("../outside.py", "/etc/passwd"):
            with self.subTest(path=path):
                escaping = sd_rules.Rule(
                    id="R0-D0", subject="a checker that is not in this tree",
                    checker=f"{path}::name", proof="nothing runs this",
                    scope="code", teaches="skills/sd-check/SKILL.md#Never")
                self.assertEqual(
                    checker_location_errors(escaping),
                    [f"R0-D0: checker path {path!r} resolves outside the "
                     f"checkout, so no declaration here can answer it"])
                self.assertIsNone(
                    source_declaration_error(REPO_ROOT, path, "name"),
                    "the shared resolver's containment exclusion changed; it "
                    "is what this check exists to cover")

    def test_a_checker_and_a_proof_arrive_together(self):
        """A checker with no proof is a name nobody ran.

        The pair is the row's whole claim to enforce anything: `checker` says
        where the enforcement is declared and `proof` says what makes it
        redden. Either one alone is the defect this slice closes -- a location
        with no proof is exactly the row that named `sd_lib.repo_root` and
        passed, and a proof with no location is a sentence about nothing.

        This is the cheap half. Leg d runs the sentence.
        """

        wrong = []
        for rule in sd_rules.RULES:
            if rule.checker and not (rule.proof or "").strip():
                wrong.append(f"{rule.id}: names {rule.checker} and no proof")
            if (rule.proof or "").strip() and not rule.checker:
                wrong.append(f"{rule.id}: states a proof and names no checker")
        self.assertEqual(wrong, [], f"""
A registry row carries a checker without a proof, or the other way round.

{_lines(wrong)}

`proof` is the mutation that makes the checker redden, in one sentence a reader
can execute, and `MUTATIONS` below has to carry it as code.""")

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

    def test_a_code_health_subject_states_the_current_ceiling(self):
        """The number in a subject is a copy of a constant, and it is held to it.

        A code-health row names its ceiling twice: by the constant's name,
        which a reader can follow, and by its value, which the reader needs
        beside the row and which nothing resolves for them. Two copies of one
        number is the drift this item exists to end, and `bin/sd_rules.py`
        cannot import the test module the constant lives in. So the value is
        read back off `tests/test_code_health.py` here: every `` `NAME`, N ``
        pair in the subject of a row whose checker is in that file states
        that constant's current value.

        **Which constant is read off the checker, not off the subject.** The
        first form of this checked each pair on its own, so the complexity
        row could have stated `` `LENGTH_CEILING`, 50 `` -- a true sentence
        about the wrong ceiling -- and passed (Copilot, #1008). The names the
        subject states have to be exactly the ceilings the checker's own body
        reads, enumerated from its AST by `ceilings_read_by`; a row that
        states none, or a different one, or one too many, fails.
        """

        wrong = []
        for rule in sd_rules.RULES:
            if not (rule.checker or "").startswith(f"{CODE_HEALTH}::"):
                continue
            checker = rule.checker.split("::", 1)[1]
            enforced = ceilings_read_by(checker)
            pairs = STATED_CEILING.findall(rule.subject)
            stated = {name for name, _ in pairs}
            if stated != enforced:
                wrong.append(f"{rule.id}: the subject states "
                             f"{sorted(stated) or 'no ceiling'}, and "
                             f"{checker} reads {sorted(enforced)}")
            for name, value in pairs:
                if name in enforced and int(value) != getattr(code_health, name):
                    wrong.append(f"{rule.id}: the subject states `{name}` "
                                 f"as {value}, and {CODE_HEALTH} has "
                                 f"{getattr(code_health, name)}")
        self.assertEqual(wrong, [], f"""
A code-health row's subject disagrees with the ceiling its checker reads.

{_lines(wrong)}

The subject carries the number so a reader at the row has it; the constant in
`{CODE_HEALTH}` is the one that enforces, and the checker's body says which.
Change the subject, never the constant: a ceiling moves in its own change,
with its baseline.""")

    def test_no_consumer_carries_a_second_list(self):
        """A rule id written as data outside the registry is a second list.

        This is requirement 1's only mechanical check, and it is the one that
        would have caught the drift `CLASSES` was built to prevent: a consumer
        that names a rule in a string has taken a copy of the table, and a copy
        is a thing that can disagree.

        **What it reads.** Every tracked file under `bin/`, including the
        ones that are not Python. The pack dashboard's client script was the
        only such file until sd:719 step 6 retired it, and it was invisible
        until review said so; the scope did not narrow when it went, and
        `dashboard/` left the pathspec when step 7 deleted the tree.

        **What it cannot see, which is stated rather than left to be found.**

        1. In a non-Python file there is no parser, only quoted runs. A rule id
           inside a quoted run *in a comment* reads as data, and one built by
           concatenation -- `"R11-" + "D20"` -- reads as neither.
        2. In Python, a string constant holding embedded CSS or JavaScript
           reads as data throughout, including where the id sits in that
           embedded language's own comment. `dashboard/server.py` carried
           `R11-D20` exactly that way until sd:719 step 6 retired it, and
           registering `R11-D20` would have reported it.

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

        for name, pattern in (("DEFINITION", DEFINITION),
                              ("MARKDOWN_DEFINITION", MARKDOWN_DEFINITION)):
            self.assertIn(sd_rules.RULE_ID.pattern, pattern.pattern,
                          f"{name} restates the rule-id grammar instead of "
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

        **And exercised against a name the tree does not have.** Asserting
        that today's matcher covers today's names is satisfied by a roster
        typed today: a hard-coded alternation carrying the same names passes
        the subset assertion and misses every tool written tomorrow. So
        `pack_nouns` is stubbed to a sentinel and the matcher must recognise
        it -- which only a matcher that reads the enumeration can do.
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
        sentinel = "zz-tool-that-does-not-exist"
        with mock.patch(f"{__name__}.pack_nouns",
                        return_value=frozenset({sentinel})):
            stubbed = names_a_pack_noun()
        self.assertIsNotNone(
            stubbed.search(f"the {sentinel} tool"),
            "`names_a_pack_noun` does not read `pack_nouns`: a name the stub "
            "returned is not matched, so the matcher carries its own roster.")
        self.assertIsNone(
            stubbed.search("the sd-status tool"),
            "`names_a_pack_noun` matched a name the stubbed `pack_nouns` did "
            "not return, so the matcher carries its own roster.")

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


class TheDefinitionGrammar(unittest.TestCase):
    """What leg c reads as a definition, held against the forms the corpus uses.

    Measured on `239ff624`, three of the four ids `DANGLING_RULE_IDS` then
    carried were not undefined at all. Each had a definition in a form the
    bold-run grammar could not see: a table cell, a heading, and a bold run
    closed before the parenthesised id. A grammar that sees only one of the
    ways this repository writes a definition reports the other three as
    missing, and a baseline built on it records a false finding as a fact.
    """

    #: One line per form, verbatim from the archive on `239ff624` except for
    #: the ids, which are fixture ids so that this docstring is not a live
    #: citation of anything. The line numbers those forms stand at are in
    #: the step-4 slice paragraph of this item's `implement.md`.
    FORMS = {
        "a table cell": (
            "| local exo :52415 (R98-D1, user 2026-08-29 — replaces llama.cpp "
            "row) | openai-compatible adapter | $0 |"),
        "a heading": "## PR 1 — R98-D2, re-derive `DASHBOARD_CAP`",
        "a bold run closed before the parenthesised id": (
            "| Decision queues | **Obsidian vault stays system-of-record** "
            "(R98-D3); accessed via `sd store` |"),
        "a bold run containing the id": (
            "**Re-derived 2026-09-07 as R98-D4, because the first figure here "
            "had gone ten\ntimes stale.** This section originally read 12,416 "
            "lines."),
        "a bold run opening with the id": "**R98-D5, 2026-09-06: the code cap "
                                          "is payable in kind.** Until this",
        "a table cell with an earlier parenthesised aside": (
            "| codex | $0 (ChatGPT sub; r8). Subscription only (R98-D11, user "
            "2026-08-29) | x |"),
        "a bold run opening with a code span, closed before the id": (
            "- **`mode: minimal` and `mode: guest` refuse it** (R98-D17). "
            "Shared and OSS"),
    }

    def test_every_form_the_corpus_writes_a_definition_in_is_seen(self):
        """Each shape in `FORMS` defines the one id it carries."""

        for form, text in self.FORMS.items():
            with self.subTest(form=form):
                expected = set(sd_rules.RULE_ID.findall(text))
                self.assertEqual(definitions_in("docs/work/archive/x/design.md",
                                                text), expected, form)

    def test_a_mention_is_not_a_definition(self):
        """The forms above are not "the id appears near some markup".

        Each control here is a way the widened grammar could over-read. The
        code-span and comment-line cases were measured on `2eafa78b` to move
        an id out of a baseline for the wrong reason; the rest are the same
        over-readings from another side, and the last five are the review
        round on #993: reverting the fence walk, the cell form or the pairing
        reddens at least one of them. A quoted example
        of a definition is a citation of the form, not a definition, so the
        id inside a code span or a fenced block never counts; the plain text
        between two bold runs is not bold; an unpaired `**` is an exponent;
        a bold run does not reach into the next paragraph; and a `#` line in
        a file that is not Markdown is a comment, and a comment cites.
        """

        controls = {
            "an id in a code span inside a bold run": (
                "docs/work/x/implement.md",
                "**A stranded id no earlier revision names: `R98-D6`.**"),
            "a quoted definition inside a code span": (
                "docs/work/x/implement.md",
                "`R98-D7` is written `**Obsidian vault stays\n"
                "system-of-record** (R98-D7)` in the archive."),
            "plain text between two bold runs": (
                "docs/work/x/implement.md",
                "**Slice 1.** `R98-D8` is a row now, and R98-D8 stays "
                "(**not** a stranded id)."),
            "a comment line in a Python file": (
                "tests/test_x.py",
                "# R98-D9, re-derived 2026-09-07: the ceiling is 4,600."),
            "a table row in a Python file": (
                "bin/x.py",
                "    rows = a | b(R98-D10)"),
            "a heading inside a backtick fence": (
                "docs/work/x/design.md",
                "An example:\n\n```markdown\n## PR 1 — R98-D12, the cap\n```\n"),
            "a table cell inside a tilde fence": (
                "docs/work/x/design.md",
                "~~~\n| local exo (R98-D13, user) | adapter |\n~~~\n"),
            "a bold run split by a fence": (
                "docs/work/x/design.md",
                "**opened here\n```\nR98-D14\n```\nand closed here**"),
            "an exponent before a parenthesised id in a Python file": (
                "bin/x.py",
                "    y = x** (R98-D15)  # not a bold run"),
            "a bold run and a parenthesised id in different paragraphs": (
                "docs/work/x/design.md",
                "**a statement**\n\n(R98-D16) is the next paragraph."),
        }
        for control, (relative, text) in controls.items():
            with self.subTest(control=control):
                self.assertEqual(definitions_in(relative, text), set(), control)


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


# --------------------------------------------------------------------------
# Leg d -- the named checker reddens when the rule is violated
# --------------------------------------------------------------------------


class Mutation(NamedTuple):
    """One violation of one rule, and the test that must notice it.

    `old` has to occur exactly once in `path`. A mutation whose pattern matches
    nothing edits nothing, the test it names stays green, and the leg reports
    that the checker enforces -- which is the false pass this leg exists to
    stop, arriving inside the leg. Two changes on this repository in one week
    were verified by a mutation script that matched nothing, so the count is
    asserted and never assumed.
    """

    path: str
    old: str
    new: str
    test: str


class Outcome(NamedTuple):
    """What one exercised mutation reported, with nothing inferred.

    Five numbers rather than a boolean, because "the checker reddened" is four
    separate claims and a boolean would let three of them fail silently: the
    edit landed, the test was green before it, the test was red after it, and
    the tree came back.

    The mutated run's own output is carried whole, because its *exit code* is
    not the evidence leg d needs and `enforcement_error` has to read what the
    child printed. The truncated copy stays for the failure messages; the whole
    one is what the predicate reads, so no verdict ever rests on a summary line
    a truncation cut in half.
    """

    applied: int    # how many times the mutated text was found
    reverted: int   # how many times the mutation was found on the way back
    control: int    # 0 when the named test was green before the mutation
    violated: int   # its exit code after it
    restored: int   # `diff -rq` between the restored copy and this tree
    report: str     # the mutated run's output, for a failure message
    violated_output: str  # that run's stdout and stderr, whole, for the predicate


#: The line `unittest` prints once it has run something. Its absence is the
#: broken-child case in `enforcement_error`: a child that never got as far as a
#: test, and whose non-zero exit says nothing about any checker.
RAN_TESTS = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)

#: The verdict line after it: `OK`, `OK (skipped=1)`, `FAILED (failures=1)`,
#: `FAILED (failures=1, errors=2)`.
VERDICT = re.compile(r"^(?:OK|FAILED)(?: \((.*)\))?$", re.MULTILINE)

#: One `name=number` inside that line's parentheses. The name may carry a
#: space, as `expected failures=1` does.
VERDICT_COUNT = re.compile(r"([a-z ]+)=(\d+)")


def unittest_counts(output: str) -> dict[str, int] | None:
    """What a `python -m unittest` run reported, or `None` if it ran nothing.

    `ran`, plus whatever the verdict line counted, under the names unittest
    prints (`failures`, `errors`, `skipped`, `expected_failures`). Parsed from
    the child's output rather than from its exit code, which says only that
    something went wrong somewhere.
    """

    ran = RAN_TESTS.search(output)
    if ran is None:
        return None
    counts = {"ran": int(ran.group(1))}
    verdict = VERDICT.search(output, ran.end())
    detail = (verdict.group(1) or "") if verdict else ""
    counts.update({name.strip().replace(" ", "_"): int(number)
                   for name, number in VERDICT_COUNT.findall(detail)})
    return counts


#: A node's line in a `-v` run: its name, then its id in parentheses. The
#: verdict follows on that line, or on the docstring line under it.
NODE_LINE = re.compile(r"^\w+ \(([\w.]+)\)", re.MULTILINE)
NODE_VERDICT = re.compile(
    r" \.\.\. (ok|FAIL|ERROR|skipped.*|expected failure|unexpected success)$",
    re.MULTILINE)


def node_verdicts(output: str) -> dict[str, str]:
    """Each node's verdict word from one `-v` run, keyed by the node's id.

    A node whose line carries no verdict before the next node's line reads
    `no verdict`; a node the loader could not resolve is listed under
    `unittest.loader._FailedTest` and so under no id a row names. The first
    line for an id wins, because the summary that follows repeats the id
    without a verdict.
    """

    starts = list(NODE_LINE.finditer(output))
    ends = [match.start() for match in starts[1:]] + [len(output)]
    verdicts: dict[str, str] = {}
    for match, end in zip(starts, ends, strict=True):
        verdict = NODE_VERDICT.search(output, match.end(), end)
        verdicts.setdefault(match.group(1),
                            verdict.group(1) if verdict else "no verdict")
    return verdicts


def enforcement_error(mutation: Mutation, outcome: Outcome) -> str | None:
    """Why the violated run is not evidence that the checker enforces.

    **A non-zero exit code is not that evidence**, and the measurement is the
    reason this function exists. Replacing `R10-D5`'s mode guard with
    `if repo_mode != "full": ((((` keeps the guard text, so the rule is not
    violated at all, and breaks only the parse. The child exits 1 with a
    `SyntaxError` and no `Ran` line -- and leg d's first form, `violated != 0`,
    read that as *"the checker enforces"*. An unresolvable node id walks in
    through the next door along: `FAILED (errors=1)` over
    `unittest.loader._FailedTest`, with a `Ran 1 test` line in front of it.

    So the run has to have *run the named test* and reported a genuine
    assertion failure. Measured on this Python, over the four cases leg d can
    produce:

        a violation      `Ran 1 test`, `FAILED (failures=1)`, exit 1
        a broken parse   no `Ran` line at all, `SyntaxError`, exit 1
        a node id typo   `Ran 1 test`, `FAILED (errors=1)`, exit 1
        no violation     `Ran 1 test`, `OK`, exit 0

    **An error is refused even though it is red.** A checker that reddens by
    raising is indistinguishable from a child this leg broke, and the row has
    the cheaper answer available: state a mutation whose named test fails an
    assertion. Every row in `MUTATIONS` does.
    """

    counts = unittest_counts(outcome.violated_output)
    if counts is None:
        return (f"the child printed no `Ran N tests` line, so {mutation.test} "
                f"never ran -- the mutated copy did not get that far")
    if not counts["ran"]:
        return f"the child ran no tests at all, so {mutation.test} did not run"
    if counts.get("errors"):
        return (f"{mutation.test} reported errors={counts['errors']} and not a "
                f"failure; an error is a broken child or an unresolved node "
                f"id, which is not a checker noticing anything")
    if not counts.get("failures"):
        return (f"{mutation.test} ran and reported no failures, so nothing "
                f"noticed the violation")
    return None


#: The mutation per checker, keyed by the location a registry row names.
#:
#: **Keyed by the checker location, not by the rule id.** A rule id written as
#: data outside `bin/sd_rules.py` is the second list
#: `test_no_consumer_carries_a_second_list` refuses, and that check reads `bin/`
#: -- it would not see a dictionary here, so the discipline has
#: to be kept rather than relied on. A checker location is the row's own value,
#: read back off `RULES` by `test_every_live_checker_carries_a_mutation` as an
#: equality: a row added with no mutation fails, and a mutation outliving the row
#: that needed it fails too.
#: Where the four code-health mutations write their violation: the first
#: `def` line of `bin/sd_library_guard.py`, the smallest module in the corpus
#: `tests/test_code_health.py` governs, replaced by the violation and then the
#: same line again. The anchor stays, so the file still parses and
#: `schema_version` is still measured under its own name; the violation is a
#: new function ahead of it, which no baseline exempts. A lowered ceiling
#: would prove only that the test reads its constant.
CODE_HEALTH_ANCHOR = "def schema_version(source: str) -> int | None:"


def ahead_of_the_anchor(*definitions: str) -> str:
    """`definitions` written above `CODE_HEALTH_ANCHOR`, as a mutation's `new`."""

    return "\n\n\n".join((*definitions, CODE_HEALTH_ANCHOR))


def a_function(name: str, body: str) -> str:
    """One `def` taking `flag`, with `body` indented under it."""

    return f"def {name}(flag):\n{textwrap.indent(body, '    ')}"


#: One decision point past `COMPLEXITY_CEILING`: `complexity` starts at one
#: and charges one per `if`, so `COMPLEXITY_CEILING` of them score one over.
TOO_BRANCHY = a_function("_leg_d_too_branchy", "".join(
    f"if flag == {n}:\n    return {n}\n"
    for n in range(code_health.COMPLEXITY_CEILING)) + "return None\n")

#: One statement past `LENGTH_CEILING`, as `ast.unparse` renders them.
TOO_LONG = a_function("_leg_d_too_long", "".join(
    f"step_{n} = {n}\n" for n in range(code_health.LENGTH_CEILING + 1)))

#: One block past `DEPTH_CEILING`: nested `if`s, never an `elif` ladder,
#: which `depth` holds at one level.
TOO_DEEP = a_function("_leg_d_too_deep", "".join(
    "    " * n + "if flag:\n" for n in range(code_health.DEPTH_CEILING + 1))
    + "    " * (code_health.DEPTH_CEILING + 1) + "return flag\n")



def a_body_past_the_clone_floor() -> str:
    """Statements added until their AST nodes reach `CLONE_FLOOR`, then a return.

    Counted the way `tests/test_code_health.py` counts a function's `nodes`,
    one `ast.walk` per statement, so a raised floor grows this body with it
    instead of leaving both clones under it and the checker green.
    """

    lines = ["total = 0"]
    while sum(1 for statement in ast.parse("\n".join(lines)).body
              for _ in ast.walk(statement)) < code_health.CLONE_FLOOR:
        lines.append(f"total += flag[{len(lines)}]")
    return "\n".join((*lines, "return total")) + "\n"


#: Two functions of one body under two names, each past `CLONE_FLOOR` in AST
#: nodes. Renaming the locals would not part them either: the digest renames
#: locals and blanks constants before it compares.
CLONE_BODY = a_body_past_the_clone_floor()
TWO_OF_A_KIND = (a_function("_leg_d_clone_a", CLONE_BODY),
                 a_function("_leg_d_clone_b", CLONE_BODY))

#: Where the three prose mutations write their violation: the section of
#: `skills/sd-check/SKILL.md` that teaches the `R13-D*` rows, one sentence of
#: it per row, so the page that cites a rule is the page that proves it.
PROSE_RULES_PAGE = "skills/sd-check/SKILL.md"


def a_line_inside(path: str, symbol: str) -> int:
    """The first body line of `symbol` in `path`, read off the tree at import.

    The `R13-D1` mutation cites a line inside a function, and the number is
    derived rather than written down for the reason the code-health mutations
    are built from their ceilings: a line number typed here is stale the day
    the file above it grows, and the mutation would then violate nothing.
    """

    tree = ast.parse((REPO_ROOT / path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == symbol:
            return node.body[0].lineno
    raise LookupError(f"{path} declares no function {symbol}")


#: A `path:line` into the body of `schema_version`, the anchor the code-health
#: mutations already lean on, in the file `tests/test_code_health.py` governs.
INSIDE_A_SYMBOL = (f"bin/sd_library_guard.py:"
                   f"{a_line_inside('bin/sd_library_guard.py', 'schema_version')}")

MUTATIONS: dict[str, Mutation] = {
    "bin/sd_setup_github.py::setup_github": Mutation(
        path="bin/sd_setup_github.py",
        old='    if repo_mode != "full":',
        new="    if False:  # leg d: the mode guard, defeated",
        test="tests.test_mode_detection.TheInstallerGate"
             ".test_a_fork_with_no_mode_line_is_refused",
    ),
    "tests/test_verb_inventory.py::test_no_command_accepts_a_repository_path":
        Mutation(
            path="bin/sd_work.py",
            old='belongs.add_argument("--belongs-to", metavar="PATH",',
            new='belongs.add_argument("--repo", metavar="PATH",',
            test="tests.test_verb_inventory.InventoryTests"
                 ".test_no_command_accepts_a_repository_path",
        ),
    "bin/sd-review::codex_preflight": Mutation(
        path="bin/sd-review",
        old='    if mode != "chatgpt":',
        new="    if False:  # leg d: the auth_mode guard, defeated",
        test="tests.test_sd_review_codex.PreflightTests"
             ".test_a_non_chatgpt_auth_mode_refuses",
    ),
    "bin/sd-review::local_conventions": Mutation(
        path="bin/sd-review",
        old='    if not block:\n        return ""',
        new='    if True:  # leg d: the empty-block guard, defeated\n        return ""',
        test="tests.test_sd_review.PipelineTests"
             ".test_the_local_block_reaches_the_prompt",
    ),
    "bin/sd_install.py::HOOK_SPECS": Mutation(
        path="bin/sd_install.py",
        old='    ("bin/sd-handoff-restore", "SessionStart", ("startup", "clear")),',
        new='    ("bin/sd-handoff-restore", "SessionStart", '
            '("startup", "clear", "compact")),',
        test="tests.test_sd_install.IdempotencyTests"
             ".test_the_hook_table_is_exactly_these_three_registrations",
    ),
    "bin/sd-status::_age_rows": Mutation(
        path="bin/sd-status",
        old="    if age <= IDLE_DAYS:",
        new="    if False:  # leg d: the idle threshold, defeated",
        test="tests.test_sd_status.WorkItemInventoryTests"
             ".test_a_planning_item_past_the_threshold_ages_into_a_finding",
    ),
    "tests/test_code_health.py::test_no_function_is_branchier_than_the_ceiling":
        Mutation(
            path="bin/sd_library_guard.py",
            old=CODE_HEALTH_ANCHOR,
            new=ahead_of_the_anchor(TOO_BRANCHY),
            test="tests.test_code_health.CodeHealth"
                 ".test_no_function_is_branchier_than_the_ceiling",
        ),
    "tests/test_code_health.py::test_no_function_is_longer_than_the_ceiling":
        Mutation(
            path="bin/sd_library_guard.py",
            old=CODE_HEALTH_ANCHOR,
            new=ahead_of_the_anchor(TOO_LONG),
            test="tests.test_code_health.CodeHealth"
                 ".test_no_function_is_longer_than_the_ceiling",
        ),
    "tests/test_code_health.py::test_no_function_nests_deeper_than_the_ceiling":
        Mutation(
            path="bin/sd_library_guard.py",
            old=CODE_HEALTH_ANCHOR,
            new=ahead_of_the_anchor(TOO_DEEP),
            test="tests.test_code_health.CodeHealth"
                 ".test_no_function_nests_deeper_than_the_ceiling",
        ),
    "tests/test_code_health.py::test_no_two_functions_are_the_same_function":
        Mutation(
            path="bin/sd_library_guard.py",
            old=CODE_HEALTH_ANCHOR,
            new=ahead_of_the_anchor(*TWO_OF_A_KIND),
            test="tests.test_code_health.CodeHealth"
                 ".test_no_two_functions_are_the_same_function",
        ),
    "tests/test_doc_citations.py::"
    "test_line_citations_into_a_symbol_match_their_baseline": Mutation(
        path=PROSE_RULES_PAGE,
        old="where the line it would name sits inside one.",
        new=f"where the line it would name sits inside one (the line "
            f"`{INSIDE_A_SYMBOL}` does).",
        test="tests.test_doc_citations.TheSymbolPreference"
             ".test_line_citations_into_a_symbol_match_their_baseline",
    ),
    "tests/test_prose_counts.py::"
    "test_present_tense_counts_match_their_baseline": Mutation(
        path=PROSE_RULES_PAGE,
        old="page being written.",
        new="page being written. The pack ships 16 tools.",
        test="tests.test_prose_counts.ProseCounts"
             ".test_present_tense_counts_match_their_baseline",
    ),
    "tests/test_rule_registry.py::"
    "test_uncited_tool_behaviour_claims_match_their_baseline": Mutation(
        path=PROSE_RULES_PAGE,
        old="The rows in `bin/sd_rules.py` state what each rule exempts;",
        new="`sd-check` refuses a tree it did not measure.\n"
            "The rows in `bin/sd_rules.py` state what each rule exempts;",
        test="tests.test_rule_registry.LegB"
             ".test_uncited_tool_behaviour_claims_match_their_baseline",
    ),
}


def child_environment() -> dict[str, str]:
    """This process's environment, minus the coverage harness.

    `.github/scripts/run-tests.sh` exports `PYTHONPATH`, `COVERAGE_FILE` and
    `SD_COVERAGE_PROCESS_START` so that a subprocess it spawns files a coverage
    shard. A run inside a temporary copy would file shards for paths that are
    gone by the time `coverage combine` reads them, so those are dropped, and
    coverage's own `COVERAGE_PROCESS_START` with them for a caller that sets it.
    `PYTHONDONTWRITEBYTECODE` is set for the reason the tree is copied at all:
    the run has to leave nothing behind that the restoration check would then
    report as a difference.
    """

    environment = dict(os.environ)
    for name in ("PYTHONPATH", "COVERAGE_FILE", "SD_COVERAGE_PROCESS_START", "COVERAGE_PROCESS_START"):
        environment.pop(name, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def edit(tree: pathlib.Path, mutation: Mutation, *, violate: bool) -> int:
    """Write the violation into the copy, or write the original back.

    Returns how many times the text it looked for occurred, so the caller
    asserts it was exactly one in both directions. Restoration is a replacement
    like the mutation, never a checkout: the copy's index exists for the
    checkers that enumerate by it, not for restoring, and a leg that restored
    with git would be proving something about git.

    **The target is held inside the copy.** `MUTATIONS` is a literal in this
    module, so no mutation today can escape and this is hardening rather than a
    live defect. But `tree / mutation.path` follows an absolute path or a `..`
    straight out of the copy, and the tree immediately outside it is this
    checkout -- so the escape would read and write the very files the copy
    exists to keep untouched. It raises instead of being written.
    """

    root = tree.resolve()
    if not (tree / mutation.path).resolve().is_relative_to(root):
        raise ValueError(
            f"mutation path {mutation.path!r} resolves outside the copy at "
            f"{root}; a mutation only ever edits the copy")
    target = tree / mutation.path
    text = target.read_text(encoding="utf-8")
    before = mutation.old if violate else mutation.new
    after = mutation.new if violate else mutation.old
    found = text.count(before)
    if found == 1:
        target.write_text(text.replace(before, after), encoding="utf-8")
    return found


def run_tests(tree: pathlib.Path, nodes: tuple[str, ...]) -> subprocess.CompletedProcess:
    """The named unittest nodes in one child, verbose, the copy as its cwd.

    The one place leg d spawns a child, so that `TheSharedCopy` can count
    children by wrapping it. Verbose, because a child running more than one
    node reports per node only on its `-v` lines; `unittest_counts` reads the
    same `Ran` and verdict lines either way.
    """

    return subprocess.run([sys.executable, "-m", "unittest", "-v", *nodes],
                          cwd=tree, env=child_environment(),
                          capture_output=True, text=True)


def run_one_test(tree: pathlib.Path, node: str) -> subprocess.CompletedProcess:
    """The named unittest node, run with the copy as the working directory."""

    return run_tests(tree, (node,))


def batched_controls(tree: pathlib.Path,
                     mutations: Iterable[Mutation]) -> dict[str, str]:
    """Every distinct test the rows name, run clean in one child; id to verdict.

    The control half of every row at once (sd:971). A row's control asked
    whether its named test is green on the clean copy, and each of the four
    code-health tests answered by walking `bin/` (and `dashboard/`, until
    sd:719 step 7 deleted it) afresh in a
    child of its own: about 1.2 s a child against 0.1 s for a test that walks
    nothing, and one child running all four walked once. So the controls run
    in one child before any mutation, and `exercise` reads a row's answer off
    that child's `-v` line for the node. It is the same question, because the
    `diff -rq` proof after every row is what says the copy the mutation lands
    in is still the copy the control ran on.
    """

    nodes = tuple(sorted({mutation.test for mutation in mutations}))
    run = run_tests(tree, nodes)
    return node_verdicts(run.stdout + run.stderr)


def copy_tracked(destination: pathlib.Path) -> None:
    """Every tracked file, copied into a private tree with its mode.

    The index rather than a directory walk, for two reasons. It is stable:
    nothing in the suite writes a tracked file, while the repository root
    collects coverage shards, logs and other suites' scratch directories for as
    long as a run lasts -- copying those is waste at best and, if one vanishes
    mid-walk, a failure in the copy rather than in anything being tested. And it
    is the enumeration every other population in this module already comes from.

    `.git` is left behind with them: in a worktree it is a pointer to a gitdir
    this copy has no business writing to. The copy then gets an index of its
    own, `git init` and one `git add` of everything copied, because the
    code-health checkers enumerate their corpus with `git ls-files` -- by the
    index and not the directory, which is that module's own reasoning -- and
    ran no test at all in an index-less copy: `CalledProcessError`, exit 128,
    `Ran 0 tests`, which `enforcement_error` rightly refuses as evidence.
    `-f` because the copy holds tracked files only, and a global excludes file
    must not thin them; the index lists paths, so a mutated file stays listed.
    """

    for path in tracked_paths():
        target = destination / path.relative_to(REPO_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for command in (["git", "init", "-q"], ["git", "add", "-A", "-f", "--", "."]):
        subprocess.run(command, cwd=destination, env=child_environment(),
                       check=True, capture_output=True)


def exercise(mutation: Mutation, tree: pathlib.Path,
             controls: dict[str, str] | None = None) -> Outcome:
    """Run one mutation end to end in a private copy of this tree.

    The protocol, in order: run the named test clean in the copy, apply the
    mutation, run it again, put the original text back, and prove the copy is
    identical to this tree again.

    **The clean run is a child of its own or a line of `controls`**, the
    verdicts `batched_controls` read off one child that ran every row's test.
    A node that child never reported is a red control, named, and never a
    child run quietly in its place: the budget `TheSharedCopy` holds is one
    control child for all the rows, and a fallback would spend past it while
    passing.

    **The copy is the caller's, made once per run and shared by every row**
    (sd:431, owner decision Dec-6: per-row copying was linear in rows and
    budgeted nowhere). Sharing is as strong as copying because the restore is
    proved, not trusted: the `diff -rq` against this checkout runs after every
    row, so a row that left a byte behind fails on its own restore instead of
    handing the next row a tree that is no longer this one.

    **In a copy rather than in place, and the runner is the reason.**
    `.github/scripts/run-tests.sh` shards the suite across parallel workers, so
    a leg that edited `bin/sd_work.py` in the live tree would be editing it
    while another shard imports it -- a flake that costs a week to find and is
    caused by the check meant to prevent defects. The copy is the *save a copy*
    half of the mutation protocol made structural: the pristine bytes stay where
    nothing can touch them, the edit happens where nothing else is looking, and
    the restoration is compared against the original rather than against a
    remembered string.
    """

    if controls is None:
        control = run_one_test(tree, mutation.test)
        control_code = control.returncode
        control_text = control.stdout + control.stderr
    else:
        verdict = controls.get(mutation.test, "no verdict")
        control_code = 0 if verdict == "ok" else 1
        control_text = f"batched control for {mutation.test}: {verdict}\n"
    applied = edit(tree, mutation, violate=True)
    violated = run_one_test(tree, mutation.test)
    reverted = edit(tree, mutation, violate=False)
    top = pathlib.PurePosixPath(mutation.path).parts[0]
    identical = subprocess.run(
        ["diff", "-rq", "-x", "__pycache__", "-x", "*.pyc",
         str(tree / top), str(REPO_ROOT / top)],
        capture_output=True, text=True)
    printed = violated.stdout + violated.stderr
    report = (control_text[-2000:] if control_code else "") + printed[-2000:]
    return Outcome(applied, reverted, control_code,
                   violated.returncode, identical.returncode,
                   report + identical.stdout, printed)


#: The first control's edit: a docstring phrase in the file `R10-D6` mutates,
#: run through that row's test. It violates no rule, so the test stays green.
DOCSTRING_SENTINEL = Mutation(
    path="bin/sd_work.py",
    old="Which checkout `--belongs-to` names",
    new="Which checkout the misfiling flag names",
    test="tests.test_verb_inventory.InventoryTests"
         ".test_no_command_accepts_a_repository_path")


class LegD(unittest.TestCase):
    """A checker that exists and enforces nothing."""

    tree: pathlib.Path

    @classmethod
    def setUpClass(cls):
        """One private copy of the tracked tree for the whole run.

        Under the system's temporary directory, never this checkout, and
        removed when the class is done. `TheSharedCopy` counts it.
        """

        scratch = tempfile.mkdtemp(prefix="leg-d-")
        cls.addClassCleanup(shutil.rmtree, scratch, ignore_errors=True)
        cls.tree = pathlib.Path(scratch) / "tree"
        copy_tracked(cls.tree)

    def test_every_live_checker_carries_a_mutation(self):
        """The coverage is enumerated from the registry, never from the table.

        An equality, so it fails from both sides: a row registered with no
        mutation is a checker nobody proved, and a mutation left behind by a
        deleted row is a fixture pointing at nothing. Reading the coverage off
        `MUTATIONS` instead would make the leg's scope whatever somebody
        remembered to add, which is the listed-roster defect this item is about.
        """

        expected = {rule.checker for rule in sd_rules.RULES
                    if rule.state == sd_rules.LIVE and rule.checker}
        self.assertEqual(set(MUTATIONS), expected, """
`MUTATIONS` and the registry's live checkers are not the same set.

Above: the mutations first, the registry's live checkers second. A live row with
a checker needs a mutation proving that checker reddens; a mutation whose row is
gone needs deleting.""")

    def test_no_two_live_rows_share_one_checker(self):
        """Two rows on one checker collapse this leg's coverage to one.

        `MUTATIONS` is keyed by checker location and the coverage above compares
        it against a *set* of locations, so a second live row naming a checker
        some row already names needs no mutation of its own. Its rule then goes
        unproven while the coverage equality still passes -- the leg reports full
        coverage of a rule nothing mutated.

        The contract is one checker per live row, which is the statement rather
        than the workaround: a rule needing enforcement some other rule already
        names needs its own mutation, and a mutation needs its own key. In
        practice that is the test that proves *this* rule rather than the one
        that proves the other.
        """

        rows = collections.defaultdict(list)
        for rule in sd_rules.RULES:
            if rule.state == sd_rules.LIVE and rule.checker:
                rows[rule.checker].append(rule.id)
        shared = [f"{location}: {', '.join(sorted(ids))}"
                  for location, ids in sorted(rows.items()) if len(ids) > 1]
        self.assertEqual(shared, [], f"""
Live registry rows share a checker location.

{_lines(shared)}

`MUTATIONS` is keyed by that location, so only one of the rows above is proved
and the coverage check cannot see the other. Give each row its own checker.""")

    def test_every_mutation_touches_what_its_rows_checker_names(self):
        """The mutation is bound to the row's `path::symbol`, not to a label.

        Leg d ran with the checker location as nothing but a `subTest` label:
        `exercise` receives the `Mutation` and never reads the row it came from.
        So repointing `R10-D5` at any other declaration that exists, and
        renaming the dict key to match, leaves the leg green while it proves a
        different pair -- the leg would report that a checker reddens without
        ever having touched the checker the row names. The proof check below
        does not close that, because `proof` is prose the same author rewrites
        in the same edit.

        The relationship is derived from the row, in the two shapes a checker
        has. A checker under `tests/` *is* the enforcement, so the mutation has
        to run that module and that symbol. A checker in code is enforcement
        some test reads, so the mutation has to edit that file.
        """

        wrong = []
        for rule in sd_rules.RULES:
            mutation = MUTATIONS.get(rule.checker or "")
            location = sd_rules.CHECKER.fullmatch(rule.checker or "")
            if mutation is None or location is None:
                continue  # a malformed checker is the registry's own failure
            path, symbol = location.groups()
            if path.startswith(TESTS):
                module = path.removesuffix(".py").replace("/", ".")
                if not mutation.test.startswith(f"{module}."):
                    wrong.append(f"{rule.id}: checker is declared in {path}, "
                                 f"and its mutation runs {mutation.test}, "
                                 f"which is not in {module}")
                if mutation.test.rsplit(".", 1)[-1] != symbol:
                    wrong.append(f"{rule.id}: checker names {symbol}, and its "
                                 f"mutation runs {mutation.test}")
            elif mutation.path != path:
                wrong.append(f"{rule.id}: checker is declared in {path}, and "
                             f"its mutation edits {mutation.path}")
        self.assertEqual(wrong, [], f"""
A mutation does not touch the checker its registry row names.

{_lines(wrong)}

Leg d passes the mutation to `exercise` and the location only labels the
subtest, so an unbound pair proves a checker nobody asked about. A checker under
`{TESTS}` has to be the test the mutation runs; a checker in code has to be the
file the mutation edits.""")

    def test_every_proof_names_the_file_and_the_test_its_mutation_uses(self):
        """The sentence and the code say the same thing, or this fails.

        `proof` is prose and `MUTATIONS` is what runs, so they are two copies of
        one fact -- the shape this whole item exists to refuse. They cannot be
        collapsed into one: a sentence a reader can follow is not a tuple, and a
        tuple is not a sentence. So they are held to naming the same file and the
        same test, which is the part of the agreement a check can reach.
        """

        wrong = []
        for rule in sd_rules.RULES:
            mutation = MUTATIONS.get(rule.checker or "")
            if mutation is None:
                continue
            for token in (mutation.path, mutation.test.rsplit(".", 1)[-1]):
                if token not in (rule.proof or ""):
                    wrong.append(f"{rule.id}: proof does not name {token}")
        self.assertEqual(wrong, [], f"""
A registry row's proof does not name what its mutation actually touches.

{_lines(wrong)}

The proof sentence has to name the file the mutation edits and the test that
goes red, or a reader following it runs something else.""")

    def test_every_live_checker_reddens_when_its_rule_is_violated(self):
        """The leg itself: violate the rule, and the named checker must notice.

        Four assertions per row, because "it went red" on its own is not
        evidence. The edit has to have landed, the test has to have been green
        before it, red after it, and the tree has to come back. The green
        half is one child for every row, run first; see `batched_controls`.
        """

        controls = batched_controls(self.tree, MUTATIONS.values())
        for location, mutation in sorted(MUTATIONS.items()):
            with self.subTest(checker=location):
                outcome = exercise(mutation, self.tree, controls)
                self.assertEqual(outcome.applied, 1, f"""
The mutation for {location} did not match exactly once in {mutation.path}.

Found {outcome.applied} occurrences of the text it replaces, so the edit either
landed nowhere or landed twice. A mutation that matches nothing leaves the test
green and reports that the checker enforces.""")
                self.assertEqual(outcome.control, 0, f"""
{mutation.test} was already failing before the mutation for {location}.

A test that was red anyway proves nothing about the violation.

{outcome.report}""")
                reason = enforcement_error(mutation, outcome)
                self.assertIsNone(reason, f"""
{location}'s rule was violated and {mutation.test} did not fail on it.

{reason}

That is the defect leg d exists to catch: the checker exists, and it does not
enforce. Either the row names the wrong checker, or the rule has no enforcement
and the row should not be live.

A non-zero exit code is not what is asserted here, and the reason is measured:
a mutation that keeps the guard text and breaks the parse violates nothing and
still exits 1. See `enforcement_error` and
`test_a_child_that_never_ran_the_test_does_not_read_as_enforcement`.

{outcome.report}""")
                self.assertEqual(outcome.reverted, 1, "the restore matched once")
                self.assertEqual(outcome.restored, 0, f"""
The copy did not come back identical after {location}'s mutation.

{outcome.report}""")

    def test_a_mutation_that_violates_nothing_leaves_the_checker_green(self):
        """The first control on leg d, without which the leg is vacuous.

        The sentinel edits the very file the `R10-D6` mutation edits, and runs
        the very test that mutation runs -- it rewrites a docstring phrase rather
        than an option name. The only difference between the two runs is whether
        the edit is a violation, so a green result here is evidence that the red
        result above came from the violation.

        **This control cannot reach the broken-child case**, and the concession
        used to sit in this docstring rather than in a test: the sentinel leaves
        the file parseable, so the run it produces is a clean `OK`. A child that
        cannot parse, or a node id that does not resolve, exits non-zero having
        noticed nothing at all. `enforcement_error` is what refuses those, and
        the control below is what proves it refuses them.
        """

        sentinel = DOCSTRING_SENTINEL
        outcome = exercise(sentinel, self.tree)
        self.assertEqual(outcome.applied, 1, "the sentinel edit did not land")
        self.assertEqual(outcome.control, 0, f"already red: {outcome.report}")
        self.assertEqual(outcome.violated, 0, f"""
The sentinel edit reddened {sentinel.test}, and it violates no rule.

It rewrites a sentence in a docstring. A checker that notices that is not
reading what it claims to read, and every red result leg d reports is suspect
until this passes.

{outcome.report}""")
        self.assertEqual(outcome.restored, 0, "the copy did not come back")

    def test_a_child_that_never_ran_the_test_does_not_read_as_enforcement(self):
        """The second control: red for the wrong reason is not evidence.

        This sentinel keeps `R10-D5`'s mode guard exactly as the mutation's
        `old` text has it -- built from that text, so the two cannot drift -- and
        breaks the parse straight after it. The rule is not violated; the file
        merely stops importing. The child then exits non-zero having run no
        test, and that is what leg d accepted as proof of enforcement until
        `enforcement_error` read the child's output instead of its exit code.

        Both halves are asserted, because the pair is the finding: the exit code
        *is* non-zero, and the predicate still refuses it.
        """

        guard = MUTATIONS["bin/sd_setup_github.py::setup_github"]
        sentinel = guard._replace(new=f"{guard.old} ((((")
        outcome = exercise(sentinel, self.tree)
        self.assertEqual(outcome.applied, 1, "the sentinel edit did not land")
        self.assertEqual(outcome.control, 0, f"already red: {outcome.report}")
        self.assertNotEqual(outcome.violated, 0, f"""
The parse-breaking sentinel exited 0, so this control proves nothing.

It has to be the case leg d's first predicate would have passed: a child that
exits non-zero having noticed no violation. If the exit code is 0 the sentinel
no longer breaks anything, and it has to be rewritten until it does.

{outcome.report}""")
        reason = enforcement_error(sentinel, outcome) or ""
        self.assertIn("never ran", reason, f"""
A child that never ran {sentinel.test} read as enforcement.

`enforcement_error` returned {reason!r}. The sentinel keeps the mode guard and
breaks the parse, so no rule is violated and no test runs -- and leg d must not
report that the checker reddened. Any predicate that reads only the exit code
fails this control, which is why it exists.

{outcome.report}""")
        self.assertEqual(outcome.restored, 0, "the copy did not come back")

    def test_a_byte_left_in_the_shared_copy_fails_the_restore_proof(self):
        """The third control, and the one that makes sharing the copy safe.

        Every row starts from the tree the row before it restored, so the
        restore has to be proved after each row. A newline is appended to the
        sentinel's file -- it still imports, so the control run stays green and
        only the `diff -rq` can notice -- and `restored` has to be non-zero.
        The byte is removed again here, so later rows start from this checkout.
        """

        target = self.tree / DOCSTRING_SENTINEL.path
        pristine = target.read_bytes()
        try:
            target.write_bytes(pristine + b"\n")
            outcome = exercise(DOCSTRING_SENTINEL, self.tree)
        finally:
            target.write_bytes(pristine)
        self.assertEqual(outcome.control, 0, f"already red: {outcome.report}")
        self.assertNotEqual(outcome.restored, 0, """
A byte left in the shared copy passed the restore proof.

The next row would have started from a tree that is not this checkout, and
nothing would have said so. Sharing one copy across rows is sound only while
this proof runs after every row.""")

    def test_a_mutation_cannot_edit_outside_the_copy(self):
        """`edit` refuses a path that leaves the private tree.

        Hardening rather than a live defect: `MUTATIONS` is a literal in this
        module and every entry names a tracked file. But `tree / mutation.path`
        follows an absolute path or a `..` out of the copy, and the tree just
        outside it is this checkout -- so the escape would write the files the
        copy exists to keep untouched, which is the one guarantee leg d makes
        about itself.
        """

        with tempfile.TemporaryDirectory() as scratch:
            tree = pathlib.Path(scratch) / "tree"
            tree.mkdir()
            for path in ("../escaped.py", str(REPO_ROOT / "bin/sd_work.py")):
                escape = Mutation(path=path, old="a", new="b", test="none")
                with self.subTest(path=path):
                    with self.assertRaises(ValueError) as caught:
                        edit(tree, escape, violate=True)
                    self.assertIn("outside the copy", str(caught.exception))


class TheSharedCopy(unittest.TestCase):
    """Leg d copies the tracked tree once per run, and spawns a budgeted few children."""

    copies: int
    children: int
    result: unittest.TestResult

    @classmethod
    def setUpClass(cls):
        """One real leg d pass, counted by wrapping and never by replacing.

        `copy_tracked` and `run_tests` are wrapped, so the copy stays real
        and every child still runs; the pass has to succeed, or a leg that
        copied nothing and ran nothing would count as one that stayed in
        budget. The three tests are the rows and the two controls that
        exercise a mutation.
        """

        module = sys.modules[__name__]
        suite = unittest.TestSuite(LegD(name) for name in (
            "test_every_live_checker_reddens_when_its_rule_is_violated",
            "test_a_mutation_that_violates_nothing_leaves_the_checker_green",
            "test_a_child_that_never_ran_the_test_does_not_read_as_enforcement"))
        cls.result = unittest.TestResult()
        with mock.patch.object(module, "copy_tracked", wraps=copy_tracked) as copies, \
                mock.patch.object(module, "run_tests", wraps=run_tests) as children:
            suite.run(cls.result)
        cls.copies = copies.call_count
        cls.children = children.call_count

    def setUp(self):
        self.assertTrue(self.result.wasSuccessful(), _lines(
            trace for _, trace in self.result.failures + self.result.errors))

    def test_the_leg_copies_the_tree_once_for_every_row_and_control(self):
        """Before the copy was shared this read five: three rows and two controls."""

        self.assertEqual(self.copies, 1, f"""
Leg d copied the tracked tree {self.copies} times in one run.

One copy per run is the budget: every row runs clean, mutates, reddens and
restores in the same tree, and the `diff -rq` proof after each restore is what
lets the next row start from the bytes this checkout has.""")

    def test_the_leg_spawns_one_child_per_row_and_one_for_every_control(self):
        """The child budget: `rows + 1 + 2 * controls` (sd:971).

        One child runs every row's named test clean, before any mutation --
        the controls, batched, read per node off its `-v` lines -- then one
        child per row runs the mutated copy. The two sentinel controls each
        keep a control child and a violated child of their own. Before the
        batching this read `2 * rows + 2 * controls`: the four code-health
        rows each walked the corpus twice, about 1.2 s a child.
        """

        rows, controls = len(MUTATIONS), 2
        budget = rows + 1 + 2 * controls
        self.assertLessEqual(self.children, budget, f"""
Leg d spawned {self.children} unittest children in one run; the budget is
rows + 1 + 2 * controls = {rows} + 1 + 2 * {controls} = {budget}.

One batched control child for every row, one mutated child per row, and two
children per sentinel control. A row's proof runs in a shared child, never
dropped; a shape past this budget is a control run again per row.""")


if __name__ == "__main__":  # pragma: no cover - the suite runs this by module
    unittest.main()
