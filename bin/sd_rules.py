"""The rule registry: the single answer to "which quality rules exist".

A rule stated only in prose is advisory, and advisory rules are the ones that
silently stop being true, because nothing fails when the sentence and the
machinery disagree. `WORKFLOW.md` claimed for weeks that every writing skill
refuses the upstream tree while nothing refused. That claim did not decay; it
was never true, and no check existed that could have said so.

This table is modelled on `CLASSES` in `bin/sd-status`, which is the same
pattern already done right in this repository: one tuple answers "which checks
exist", every consumer iterates it, and adding a check means adding a row and a
producer rather than editing a renderer, a sort, or a list in a skill. The
`sd-status` skill states the reason in one sentence: *"That is how those drift
apart."*

**`checker` is a source location, and `proof` is how it is held to enforcing.**
A row names its checker as `path::symbol` -- a string -- and states in one
sentence the mutation that makes that checker redden. The pair is what leg d of
the meta-check runs: it applies the mutation in a private copy of the tree and
requires the named test to go from green to red. Until leg d existed the only
thing asserted about a checker was that it *existed*, and a row was drafted
naming `sd_lib.repo_root` -- the resolver by which its rule would be violated,
not a guard on it -- which passed. That is the hole this field pair closes.

**Why the location is a string and not the function object.** It was the
function object until sd:431's second slice, and two things cost more than the
import-time resolution bought. A callable field makes this module import every
checker's module at load time, so the registry acquires an import edge to every
enforcement in the pack and anything reading the table pays for all of them. And
an import cannot reach the two places enforcement actually lives: an
extensionless entrypoint such as `bin/sd-review`, where `R10-D4`'s
`codex_preflight` sits, and a test over the tree, which this module must never
import. Both were recorded as blockers on the backfill; the string answers both.

**Why a code table and not a YAML or JSON file.** The rejection needs restating,
because the argument it used to rest on is gone. It used to be that a data file
cannot name a callable, so something would have to resolve a string back to a
function, and that resolver would be a second source of truth failing at run
time rather than at import time. The field is a string now, so that argument has
expired -- and the answer does not depend on it. The string is resolved by
`source_declaration_error` in `tests/test_doc_citations.py`, which is the
resolver this pack already uses for the `source:path::symbol` citations in its
documentation, so there is still exactly one resolver and this table did not
bring a second. What a data file would cost instead is the rest of a row: a
`subject` and a `proof` are paragraphs whose whole value is that a reader meets
them beside the row, they are reviewed as code is reviewed, and their shape is
checked by the type of this tuple rather than by a schema file somebody has to
keep honest. And what the import used to buy is bought better: leg d proves the
checker enforces, which is more than resolution ever proved.

**The meta-check is the deliverable, not the rules.** Legs a to d in
`tests/test_rule_registry.py` are what keep the system from drifting, and a
registry with the meta-check and no rules is worth more than fifteen rules with
no meta-check, because the second one starts drifting the day it lands. Zero
rows passed every test here, which is what made this module landable before any
rule argued about its content.

**The rows arrive by backfill, one judgement at a time.** A rule id cited in
live prose whose only definition sits in `docs/work/archive` is a citation of a
page the pack has stopped maintaining, and moving one here is a decision about
whether it is still a rule or only a record of one. `STRANDED_RULE_IDS` in
`tests/test_rule_registry.py` is that backfill's meter: it falls by exactly the
ids a change registers, in the same change, because it is an equality and not a
ceiling.
"""

from __future__ import annotations

import re
from typing import NamedTuple

#: What a rule id looks like, in one place. Every reader of rule ids -- the
#: meta-check's four legs, and anything that grows later -- compiles nothing
#: of its own against this shape, for the reason the table exists at all.
#:
#: The form is the pack's existing `R<round>-D<decision>` id, deliberately.
#: Inventing a second id space would leave the 47 ids cited in live prose on
#: `cddd3b98` resolving to nothing, and "a rule id cited nowhere in the registry
#: fails" is leg c's whole job.
RULE_ID = re.compile(r"\bR\d+-D\d+\b")

#: What a checker location looks like: `path::symbol`, the same spelling the
#: pack's documentation citations use inside `source:...`. Held here rather than
#: in the test module for the reason `RULE_ID` is: one grammar, one source.
#:
#: The path deliberately does not require a suffix. `bin/sd-review` is a Python
#: file with no `.py`, and the first checker this registry could not name was in
#: one -- which is half of why the field stopped being a callable.
CHECKER = re.compile(r"([A-Za-z0-9_./-]+)::([A-Za-z_][A-Za-z0-9_]*)")

#: A rule that is in force. Its checker runs and its skill teaches it.
LIVE = "live"

#: A rule that has been withdrawn. Its id stays in the table forever.
#:
#: This state existed before the first repeal rather than after it, because a
#: repealed id must never become reusable: live prose citing `R5-D1` must not
#: quietly start resolving to whatever rule next claims that id. A repealed row
#: carries no checker and no proof -- there is nothing left to enforce -- and
#: no skill has to teach it, so leg a skips it. Leg c still resolves it, which
#: is the point: prose citing a repealed rule is answered, not left dangling.
#: The first row to carry it is `R10-D2`, below.
REPEALED = "repealed"

#: The scopes a rule can have. `code` rules read source, `prose` rules read the
#: documentation corpus, `both` reads both.
SCOPES = ("code", "prose", "both")

#: Every state a row may carry.
STATES = (LIVE, REPEALED)


class Rule(NamedTuple):
    """One quality rule that exists, and everything a consumer needs of it.

    `checker` names where the enforcement is declared, as `path::symbol`
    matching `CHECKER`. A live row must carry one and it must resolve to exactly
    one declaration in the checkout; a `REPEALED` row carries `None`, because a
    withdrawn rule has nothing left to run.

    `proof` is the mutation that makes that checker redden, in one sentence a
    reader can execute, and it is what stops `checker` from being a name nobody
    ran. A row with a checker and no proof fails the meta-check, and leg d
    executes the mutation rather than trusting the sentence.

    `teaches` names the skill section that teaches the rule, as
    `path#heading`. The skill cites the rule id; it does not restate the rule,
    because two copies of a sentence are two things that can disagree. That
    second half has no mechanical check and this module does not claim one --
    asserting an enforcement nothing performs is the exact defect the registry
    exists to end, and it would be absurd to commit it here.
    """

    id: str
    subject: str
    checker: str | None
    proof: str | None
    scope: str
    teaches: str
    state: str = LIVE


#: The enumeration. This tuple is the *only* answer to "which rules exist".
#: Every consumer iterates it; no consumer carries a second list, which
#: `test_no_consumer_carries_a_second_list` holds them to. Adding a rule means
#: adding a row here with a checker and a proof -- never editing a skill's list
#: of rules, which is how the sentence and the machinery come apart.
#:
#: `checker` may name code or a test, and the distinction that used to be made
#: between them is not one this table needs to carry. `R10-D5`'s enforcement is
#: runtime code refusing an install; `R10-D6`'s is a test enumerating `bin/`.
#: Both are enforcement, both redden when the rule is violated, and leg d asks
#: each of them the same question. What the table refuses is a row whose named
#: checker does not redden -- the failure that a callable field, checked only
#: for existence, let through.
RULES: tuple[Rule, ...] = (
    Rule(
        id="R10-D5",
        subject="only a full-mode repository installs the review routing "
                "lane; `minimal` and `guest` refuse it, so a shared or "
                "upstream repository can never grow the framework's workflow",
        checker="bin/sd_setup_github.py::setup_github",
        proof="replace the mode guard in `bin/sd_setup_github.py` with a "
              "condition that is never true; the installer then accepts a "
              "guest-mode fork and "
              "`test_a_fork_with_no_mode_line_is_refused` goes red",
        scope="code",
        teaches="skills/sd-review/SKILL.md#setup-github",
    ),
    Rule(
        id="R10-D6",
        subject="an `sd-*` command resolves its repository from the working "
                "directory and takes no path to another one, so a session "
                "that can be pointed at another checkout cannot exist",
        checker="tests/test_verb_inventory.py::"
                "test_no_command_accepts_a_repository_path",
        proof="rename the `--belongs-to` option in `bin/sd_work.py` to the "
              "banned spelling; the scan of `bin/` finds it and "
              "`test_no_command_accepts_a_repository_path` goes red",
        scope="code",
        teaches="skills/sd-check/SKILL.md#Never",
    ),
    Rule(
        id="R10-D4",
        subject="a codex review runs on the ChatGPT subscription or it "
                "does not run: `auth.json` must select `chatgpt` with no "
                "stored API key, so a run can never fall over to metered "
                "API billing",
        checker="bin/sd-review::codex_preflight",
        proof="replace the `auth_mode` guard in `bin/sd-review` with a "
              "condition that is never true; the preflight then accepts an "
              "`apikey` login and `test_a_non_chatgpt_auth_mode_refuses` "
              "goes red",
        scope="code",
        teaches="skills/sd-review/SKILL.md#"
                "The `codex-json` entry is subscription-only (R10-D4)",
    ),
    #: Registered once `bin/sd-status` stopped carrying the id in its strings
    #: (owner decision 2026-09-14, Dec-3): the `CLASSES` cell and the reason
    #: text cite it from an adjacent comment now, the way `R10-D5` does in
    #: `bin/sd_setup_github.py`, so the second-list check has nothing to
    #: report and the skill's table can mirror the cell without naming the id.
    Rule(
        id="R10-D1",
        subject="an item idle in `planning` past the 45-day threshold is "
                "flagged `idle-planning` at rank 100, and the threshold is "
                "read from `sd_lib.DEFAULT_DAYS` rather than restated",
        checker="bin/sd-status::_age_rows",
        proof="replace the `IDLE_DAYS` comparison in `bin/sd-status` with a "
              "condition that is never true; every dated planning item is "
              "then reported idle whatever its age, and "
              "`test_a_planning_item_past_the_threshold_ages_into_a_finding` "
              "goes red",
        scope="code",
        teaches="skills/sd-status/SKILL.md#One table enumerates the checks",
    ),
    #: The first repealed row, and the reason it is one rather than a live row
    #: with no checker. The section that teaches it says in its heading that
    #: Lane B is not implemented: `bin/sd-handoff` has no push flag, so nothing
    #: converts a pull request to draft and nothing suppresses a re-request. A
    #: live row here would assert an enforcement nothing performs, which is
    #: the defect the registry exists to end. The id stays so that the
    #: citation in that section resolves and the id is never reused; `teaches`
    #: still names the section, so a reader following the row lands on the
    #: sentence that says why there is nothing to run (owner decision
    #: 2026-09-14, Dec-4).
    Rule(
        id="R10-D2",
        subject="`sd-handoff`'s push lane, on finding an open pull request for "
                "the carrier branch, converts it to draft before pushing "
                "and suppresses the Copilot re-request, so the once-per-head "
                "rule does not fire on the moved head",
        checker=None,
        proof=None,
        scope="code",
        teaches="skills/sd-handoff/SKILL.md#Lane B is not implemented",
        state=REPEALED,
    ),
    #: The code rules, registered against sd:430's checkers and nothing new
    #: (owner decision 2026-09-14, Dec-1 and Dec-2): a new round for rules the
    #: registry is native to, taught from one section of the skill `R10-D6`
    #: already teaches from. The four checkers have run since
    #: `tests/test_code_health.py` landed; these rows only register them, and
    #: the ceilings stay where that file has them. Each subject states its
    #: ceiling twice, by the constant's name and by its value, because a reader
    #: at the row needs the number and nothing resolves it for them -- so
    #: `test_a_code_health_subject_states_the_current_ceiling` reads the value
    #: back off that module rather than trusting either copy.
    Rule(
        id="R12-D1",
        subject="no function in `bin/` or `dashboard/` is branchier than "
                "`COMPLEXITY_CEILING`, 20 on the cyclomatic score, beyond "
                "the entries `COMPLEX` carries, and that baseline only "
                "shrinks",
        checker="tests/test_code_health.py::"
                "test_no_function_is_branchier_than_the_ceiling",
        proof="insert a function with one decision point more than the "
              "ceiling ahead of `schema_version` in `bin/sd_library_guard.py`; "
              "it is in no baseline and "
              "`test_no_function_is_branchier_than_the_ceiling` goes red",
        scope="code",
        teaches="skills/sd-check/SKILL.md#Code health",
    ),
    Rule(
        id="R12-D2",
        subject="no function in `bin/` or `dashboard/` is longer than "
                "`LENGTH_CEILING`, 50 statements as `ast.unparse` renders "
                "them with the docstring left out, beyond the entries `LONG` "
                "carries, and that baseline only shrinks",
        checker="tests/test_code_health.py::"
                "test_no_function_is_longer_than_the_ceiling",
        proof="insert a function one statement longer than the ceiling ahead "
              "of `schema_version` in `bin/sd_library_guard.py`; it is in no "
              "baseline and `test_no_function_is_longer_than_the_ceiling` "
              "goes red",
        scope="code",
        teaches="skills/sd-check/SKILL.md#Code health",
    ),
    Rule(
        id="R12-D3",
        subject="no function in `bin/` or `dashboard/` nests deeper than "
                "`DEPTH_CEILING`, 5 indented blocks with an `elif` ladder "
                "held at one level, beyond the entries `DEEP` carries, and "
                "that baseline only shrinks",
        checker="tests/test_code_health.py::"
                "test_no_function_nests_deeper_than_the_ceiling",
        proof="insert a function nesting one block deeper than the ceiling "
              "ahead of `schema_version` in `bin/sd_library_guard.py`; it is "
              "in no baseline and "
              "`test_no_function_nests_deeper_than_the_ceiling` goes red",
        scope="code",
        teaches="skills/sd-check/SKILL.md#Code health",
    ),
    Rule(
        id="R12-D4",
        subject="no two functions in `bin/` or `dashboard/` of at least "
                "`CLONE_FLOOR`, 25 AST nodes each, are the same function "
                "once locals are renamed and constants blanked, beyond the "
                "pairs `CLONES` carries, and that baseline only shrinks",
        checker="tests/test_code_health.py::"
                "test_no_two_functions_are_the_same_function",
        proof="insert two functions of one body and two names, each past the "
              "clone floor, ahead of `schema_version` in "
              "`bin/sd_library_guard.py`; the pair is not in `CLONES` and "
              "`test_no_two_functions_are_the_same_function` goes red",
        scope="code",
        teaches="skills/sd-check/SKILL.md#Code health",
    ),
)


#: Keyed lookup over the same tuple, so nothing restates a scope or a checker.
#: An id absent here raises at the caller that invented it, which is the loud
#: form of "the table is the enumeration".
BY_RULE_ID = {rule.id: rule for rule in RULES}
