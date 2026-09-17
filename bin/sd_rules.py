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
#: repealed id must never become reusable: live prose citing `R10-D2` must not
#: quietly start resolving to whatever rule next claims that id. A repealed row
#: carries no checker and no proof -- there is nothing left to enforce -- and
#: no skill has to teach it, so leg a skips it. Leg c still resolves it, which
#: is the point: prose citing a repealed rule is answered, not left dangling.
#: The first row to carry it is `R10-D2`, below. A repealed row may also
#: carry no `teaches`: a rule that no skill taught when it was withdrawn has
#: no section to name, and a section invented for it would send a reader to
#: a heading that says nothing about it (`R11-D1`, below, is the first).
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
    exists to end, and it would be absurd to commit it here. A live row must
    carry one; a `REPEALED` row may hold `None`, because nothing reads the
    field on a withdrawn rule and a never-taught rule has no section to name.
    """

    id: str
    subject: str
    checker: str | None
    proof: str | None
    scope: str
    teaches: str | None
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
    #: The other half of the handoff design, narrowed to the lane that exists.
    #: `R10-D3` split handoff into two lanes; Lane B is the repeal above, and
    #: what Lane A holds as a rule is the restore hook's registration --
    #: `SessionStart` on `startup` and `clear` and on nothing else: never
    #: `compact`, because a compact matcher would consume the packet into the
    #: dying session and the `/clear` that follows would find nothing, and
    #: never `resume`, which brings old context back and has no use for a
    #: packet. The checker is the hook table itself, pinned whole by its
    #: test, so both omissions are held by one row of that table and the
    #: subject names both (sd:431 step 8, slice 1, 2026-09-16).
    Rule(
        id="R10-D3",
        subject="`bin/sd-handoff-restore` is registered on `SessionStart` "
                "for the `startup` and `clear` matchers only -- never "
                "`compact`, so a packet is not consumed by the session being "
                "compacted and is restored into the one that follows the "
                "`/clear`, and never `resume`, which needs no packet",
        checker="bin/sd_install.py::HOOK_SPECS",
        proof="add `compact` to the `SessionStart` matchers of the "
              "`bin/sd-handoff-restore` row of `HOOK_SPECS` in "
              "`bin/sd_install.py`; the table is pinned whole and "
              "`test_the_hook_table_is_exactly_these_three_registrations` "
              "goes red",
        scope="code",
        teaches="skills/sd-handoff/SKILL.md#The restore side",
    ),
    #: The local block reaches the prompt. `R10-D7` is the design's partial
    #: fallback for a provider with no untracked-file import: in the lanes the
    #: pack itself invokes, the `CLAUDE.local.md` block is carried into the
    #: prompt by hand. What holds it is `local_conventions` in `bin/sd-review`,
    #: called once, on the dispatch path of `review` after the preflight has
    #: returned -- so the review prompt carries the block and the preflight,
    #: which sends a fixed synthetic probe, does not. The lanes
    #: the design listed beyond `sd-review` -- a planning review, a backlog
    #: ship with a codex agent -- either run through this call or no longer
    #: exist, so the subject names the one caller (sd:431 step 8, slice 2,
    #: 2026-09-17).
    Rule(
        id="R10-D7",
        subject="the review prompt `bin/sd-review` dispatches opens with "
                "this checkout's `CLAUDE.local.md` block, rendered by "
                "`local_conventions` from its one caller in `review`, after "
                "the preflight has returned without it",
        checker="bin/sd-review::local_conventions",
        proof="replace the empty-block guard `if not block:` in "
              "`local_conventions` of `bin/sd-review` with a condition that "
              "is always true, so the block is dropped whether or not one "
              "exists; `test_the_local_block_reaches_the_prompt` in "
              "`tests/test_sd_review.py` goes red",
        scope="code",
        teaches="skills/sd-review/SKILL.md#Local conventions reach the prompt",
    ),
    #: No shipped shell. `R11-D6` deleted the `Shell coverage` CI job because
    #: what it measured had ceased to exist, and the fact that made the
    #: deletion defensible is the rule that survives it: shell -- by suffix or
    #: by shebang -- lives under `.github/scripts/`, the directory `make check`
    #: runs on this repository itself, and nowhere else in the tracked tree.
    #: The checker is the test that stood in for the job, so it is named as a
    #: `tests/` symbol and the mutation runs it. Taught under `Code health`
    #: with the `R12` rows, per Dec-2, because it is a rule an author of code
    #: meets as a red result from the same entrypoint (sd:431 step 8, slice 3,
    #: 2026-09-17).
    Rule(
        id="R11-D6",
        subject="no tracked file with a shell suffix or a shell shebang "
                "lives outside `.github/scripts/`, the one directory the "
                "pack runs shell from on itself, so nothing the installer "
                "renders or a consumer receives is shell",
        checker="tests/test_no_shipped_shell.py::"
                "test_shell_lives_only_in_this_repository_s_own_tooling",
        proof="change the shebang of `bin/sd-rules` from "
              "`#!/usr/bin/env python3` to `#!/usr/bin/env bash`; the file "
              "is tracked, outside `.github/scripts/`, and now reads as "
              "shell, so "
              "`test_shell_lives_only_in_this_repository_s_own_tooling` "
              "goes red",
        scope="code",
        teaches="skills/sd-check/SKILL.md#Code health",
    ),
    #: The store and plugin contract, three rows taught from one section of
    #: `skills/sd-help/SKILL.md` -- the one skill that names `sd plugin`, and
    #: the host team-lead chose on 2026-09-17 for the reason Dec-2 declined a
    #: new skill for the code rules. `R11-D14` closed the kind vocabulary at
    #: the eight keys `KIND_KEYS` holds and made a ninth a decision record;
    #: what enforces it is `validate_kind`, once, by name, and the subject
    #: names the constant and the count rather than the keys, because the
    #: test that pins them already holds a copy and a third would drift
    #: (sd:431 step 8, slice 4, 2026-09-17).
    Rule(
        id="R11-D14",
        subject="a plugin kind is described with the eight keys `KIND_KEYS` "
                "in `bin/sd` holds and no other; `validate_kind` refuses a "
                "manifest carrying any further key by name, so a ninth key "
                "is a decision record and not a commit",
        checker="bin/sd::validate_kind",
        proof="replace the unknown-key guard `if unknown:` in `validate_kind` "
              "of `bin/sd` with a condition that is never true, so a manifest "
              "carrying a ninth key registers; `test_a_ninth_key_refuses` in "
              "`tests/test_sd_plugin.py` goes red",
        scope="code",
        teaches="skills/sd-help/SKILL.md#The store and plugin contract",
    ),
    #: `R11-D27` is the line edit: a field write replaces or inserts one line
    #: of the frontmatter and reads nothing else in, because a note parsed
    #: and rendered back loses what the parser did not keep -- list items,
    #: quoting, key order, blank lines -- and `sd`'s own reader is the one
    #: reader that cannot see the loss. The checker is `edit_field`, the one
    #: function every field write goes through, and the test reads the file
    #: back as bytes rather than through `sd`.
    Rule(
        id="R11-D27",
        subject="`sd store add` and `sd store set` write a frontmatter field "
                "by replacing or inserting one line through `edit_field` in "
                "`bin/sd`, so the note comes back byte-identical apart from "
                "that line and is at no point parsed and rendered back",
        checker="bin/sd::edit_field",
        proof="replace the one-line assignment `lines[hits[0]] = ...` in "
              "`edit_field` of `bin/sd` with one that rebuilds the list from "
              "the rendered line alone, so every other line of the note is "
              "dropped; "
              "`test_a_set_leaves_every_line_it_did_not_edit_byte_identical` "
              "in `tests/test_sd_store.py` goes red",
        scope="code",
        teaches="skills/sd-help/SKILL.md#The store and plugin contract",
    ),
    #: `R5-D1` is the oldest id in the table and the property the store was
    #: rebuilt for: the vault is the system-of-record, and a query reads it
    #: at the moment of asking rather than an index of it. The checker is
    #: `store_list`, which lists the kind's directory on every call and
    #: consults nothing else; the test writes a note by hand between two
    #: queries and requires the second to see it. The mutation is a stale
    #: index, not an empty listing, so what leg d proves is the violation the
    #: id names.
    Rule(
        id="R5-D1",
        subject="the vault is the system-of-record: an `sd store` query "
                "lists the kind's notes from the vault directory at the "
                "moment of asking, in `store_list` of `bin/sd`, with no index "
                "consulted and nothing held between invocations, so a note "
                "written by hand or by Obsidian is visible to the next query "
                "with no sync step",
        checker="bin/sd::store_list",
        proof="make `store_list` in `bin/sd` write the kind's listing to an "
              "index file on its first query and read that file instead of "
              "the vault on every query after; a note written by hand between "
              "two queries is then invisible to the second, and "
              "`test_a_note_written_directly_into_the_vault_is_visible_to_the_next_query` "
              "in `tests/test_sd_store.py` goes red",
        scope="code",
        teaches="skills/sd-help/SKILL.md#The store and plugin contract",
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
        subject="no function in `bin/` is branchier than "
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
        subject="no function in `bin/` is longer than "
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
        subject="no function in `bin/` nests deeper than "
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
        subject="no two functions in `bin/` of at least "
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
    #: The prose rules, in the narrowed forms sd:431's design records, on a
    #: round of their own for the same reason `R12` is one: the registry is
    #: native to them. Each holds a per-document baseline that may fall and
    #: may not rise, so a first run reddens nothing in the existing corpus and
    #: every new violation is red on the day it is written. The first two are
    #: new enforcement; the third registers leg b of the meta-check, which has
    #: held its rule since step 2, and enforces nothing that was not already
    #: enforced.
    Rule(
        id="R13-D1",
        subject="a `path:line` citation in a live document whose line sits "
                "inside a `def` or a `class` of a Python file names the "
                "symbol instead, as `source:<path>::<symbol>`, beyond the "
                "entries `SYMBOL_ANCHORED_CITATIONS` carries per document, "
                "and that baseline only shrinks; a line outside every "
                "symbol, a line inside a name the file declares more than "
                "once, a `[quoted: ...]` reason and a markdown target keep "
                "their line anchor, because the symbolic form cannot say them",
        checker="tests/test_doc_citations.py::"
                "test_line_citations_into_a_symbol_match_their_baseline",
        proof="append a `path:line` citation into the body of "
              "`schema_version` in `bin/sd_library_guard.py` to a sentence "
              "of `skills/sd-check/SKILL.md`; that document's count rises "
              "above its baseline and "
              "`test_line_citations_into_a_symbol_match_their_baseline` "
              "goes red",
        scope="prose",
        teaches="skills/sd-check/SKILL.md#Prose rules",
    ),
    Rule(
        id="R13-D2",
        subject="no line of live prose states a present-tense count of "
                "something the tree enumerates -- `<number> tools`, "
                "`commands`, `skills`, `tests`, `rules`, `files`, `verbs`, "
                "`checkers`, `surfaces`, `agents` or `platforms` -- unless "
                "the line reports it against a commit, a `#<n>` number or a "
                "`YYYY-MM-DD` date, beyond the entries `PRESENT_TENSE_COUNTS` "
                "carries per document, and that baseline only shrinks",
        checker="tests/test_prose_counts.py::"
                "test_present_tense_counts_match_their_baseline",
        proof="append `The pack ships 16 tools.` to a sentence of "
              "`skills/sd-check/SKILL.md` that carries no commit, number or "
              "date; that document's count rises above its baseline and "
              "`test_present_tense_counts_match_their_baseline` goes red",
        scope="prose",
        teaches="skills/sd-check/SKILL.md#Prose rules",
    ),
    #: Nothing new is enforced by this row. Leg b's predicate is `claims_in`
    #: and its baseline is `UNCITED_SKILL_CLAIMS`, both in
    #: `tests/test_rule_registry.py`, and both have run since step 2; the row
    #: is what lets a skill cite the rule it is held to, which leg a then
    #: requires of the section named here.
    Rule(
        id="R13-D3",
        subject="a line of a skill that asserts a tool behaviour -- an "
                "enforcement verb, `refuses`, `never`, `always` or `cannot`, "
                "with a pack tool or a test on the same line -- cites a rule "
                "id the registry carries, beyond the entries "
                "`UNCITED_SKILL_CLAIMS` carries per document, and that "
                "baseline only shrinks",
        checker="tests/test_rule_registry.py::"
                "test_uncited_tool_behaviour_claims_match_their_baseline",
        proof="add a line naming `sd-check` with `refuses` and no rule id to "
              "`skills/sd-check/SKILL.md`; that document gains an uncited "
              "claim its baseline does not carry and "
              "`test_uncited_tool_behaviour_claims_match_their_baseline` "
              "goes red",
        scope="prose",
        teaches="skills/sd-check/SKILL.md#Prose rules",
    ),
    #: The twelve repeals of sd:431 step 4, slice H, under one family decision
    #: team-lead took on 2026-09-17 (Dec-9, recommended on note 2665 and
    #: reversible by the owner by deleting these rows' `REPEALED` state).
    #: None of the twelve was taught by any skill, so none names a section;
    #: each keeps its id so the live prose that cites it is answered and the
    #: id is never handed out again, and each keeps the archive's own sentence
    #: as its subject so a reader following a citation learns what was ruled.
    #:
    #: The first two are the `R10-D2` shape (Dec-4): the enforcement each
    #: id claims was never built or is gone. `R11-D1` pinned the local exo
    #: model by name and had the preflight refuse a name absent from
    #: `/v1/models`; nothing under `bin/` or `tests/` reads `/v1/models`,
    #: and the `providers.yaml` entry it shaped ships `enabled: false`.
    #: `R11-D5` put the bash 3.2 gate in CI; no CI job invokes
    #: `check-bash32-syntax.sh`, as `CONTRIBUTING.md` records, and the local
    #: `make check` lane that survives is `R11-D6`'s subject, not this one.
    Rule(
        id="R11-D1",
        subject="the local exo provider on `:52415` is model-pinned by name "
                "in config, and the preflight refuses a name absent from "
                "`/v1/models`",
        checker=None,
        proof=None,
        scope="code",
        teaches=None,
        state=REPEALED,
    ),
    Rule(
        id="R11-D5",
        subject="the bash 3.2 gate, `check-bash32-syntax.sh`, runs in CI",
        checker=None,
        proof=None,
        scope="code",
        teaches=None,
        state=REPEALED,
    ),
    #: The ten dashboard and history ids, repealed as one family by the same
    #: decision: sd:719 is `done` with `dashboard/` and `bin/sd_ledger.py`
    #: deleted (#1013, #1017), so what each of them ruled on no longer
    #: exists to be enforced. Per id, what that was, what took it, and what
    #: still cites it -- every citation a record of what was decided, none a
    #: consumer of a rule:
    #:
    #: - `R11-D10`: the phone's writes and the dashboard's GET-only
    #:   assertion; `dashboard/` deleted; cited by sd:719's own pages.
    #: - `R11-D13`: a sequencing decision, plugin registration ahead of
    #:   step 6b, and a dashboard cap re-derived from the split; the cap
    #:   left with `dashboard/`; cited by a `tests/test_sd_plugin.py`
    #:   docstring as the point at which `kinds` was "never enforced". The
    #:   enforcement that docstring says arrived later is the closed kind
    #:   vocabulary, and that is `R11-D14`'s live row above, not this id's.
    #: - `R11-D15`: the `bin/` cap at 14,000; retired by `R11-D48` on
    #:   2026-09-11 (`tests/test_loc_caps.py`); cited by the 2026-09-05
    #:   item's pages and a `tests/test_sd_review_boundary.py` comment.
    #: - `R11-D17`: the plugin table contract, the loader's markup filter
    #:   and `dashboard/` at 4,000; loader and directory deleted; cited by
    #:   `tests/test_loc_caps.py`'s history.
    #: - `R11-D20`: `kind` as a category and one alert per id;
    #:   `dashboard/now.py` deleted; cited by sd:719's own pages.
    #: - `R11-D21`: Queues as a plugin tab and a declared action in the
    #:   manifest. The tab is deleted. `validate_actions` in `bin/sd`
    #:   survives and refuses a malformed `dashboard.actions` block, but
    #:   it validates the shape of a key no dashboard reads any more
    #:   (sd:719 recorded the actions as staying in the manifest and
    #:   leaving every dashboard), and no test names it, so a live row on
    #:   it would carry a checker leg d cannot prove; cited by that
    #:   function's docstring.
    #: - `R11-D24`: the dashboard cap at 4,300 split into a total and a
    #:   code-only ceiling; the three dashboard constants deleted at sd:719
    #:   step 7. Its clause "a cap is never raised in the pull request that
    #:   busts it" survives as prose in `tests/test_loc_caps.py` and
    #:   `docs/workflow-control-capacity.md` with no checker; cited there,
    #:   by the 2026-09-05 item's pages and by sd:719's.
    #: - `R11-D25`: the read-only Queues tab; deleted; cited by the
    #:   2026-09-05 item's prd.
    #: - `R11-D29` and `R11-D30`: the dashboard total re-derived at 4,350
    #:   and `DASHBOARD_CAP` re-derived under `dashboard/`; the constants
    #:   deleted; cited by `tests/test_loc_caps.py`'s history, the
    #:   2026-09-05 item's prd and sd:719's pages.
    Rule(
        id="R11-D10",
        subject="the phone keeps its writes, and the dashboard's GET-only "
                "assertion is temporary by design",
        checker=None,
        proof=None,
        scope="code",
        teaches=None,
        state=REPEALED,
    ),
    Rule(
        id="R11-D13",
        subject="plugin registration moves ahead of step 6b, and the "
                "dashboard cap is re-derived from the split rather than "
                "from the estimate that set it",
        checker=None,
        proof=None,
        scope="code",
        teaches=None,
        state=REPEALED,
    ),
    Rule(
        id="R11-D15",
        subject="the `bin/` cap is 14,000, derived from built code, and "
                "`sd-help` leaves `bin/` because the taxonomy already said "
                "it is not a command",
        checker=None,
        proof=None,
        scope="code",
        teaches=None,
        state=REPEALED,
    ),
    Rule(
        id="R11-D17",
        subject="a plugin declares what its table can do and the backbone "
                "does it; the markup it sends is filtered on the way out of "
                "the loader; and `dashboard/` is re-derived at 4,000",
        checker=None,
        proof=None,
        scope="code",
        teaches=None,
        state=REPEALED,
    ),
    Rule(
        id="R11-D20",
        subject="`kind` is a category and never a severity, and an alert id "
                "identifies one alert",
        checker=None,
        proof=None,
        scope="code",
        teaches=None,
        state=REPEALED,
    ),
    Rule(
        id="R11-D21",
        subject="Queues is a plugin tab, and the plugin contract grows a "
                "declared action",
        checker=None,
        proof=None,
        scope="code",
        teaches=None,
        state=REPEALED,
    ),
    Rule(
        id="R11-D24",
        subject="the dashboard cap is re-derived at 4,300 and split in two, "
                "a total and a code-only ceiling prose cannot pay for",
        checker=None,
        proof=None,
        scope="code",
        teaches=None,
        state=REPEALED,
    ),
    Rule(
        id="R11-D25",
        subject="the Queues tab is read-only, and setting a status stays in "
                "Obsidian",
        checker=None,
        proof=None,
        scope="code",
        teaches=None,
        state=REPEALED,
    ),
    Rule(
        id="R11-D29",
        subject="the dashboard total is re-derived at 4,350, itemised",
        checker=None,
        proof=None,
        scope="code",
        teaches=None,
        state=REPEALED,
    ),
    Rule(
        id="R11-D30",
        subject="`DASHBOARD_CAP` is re-derived, and the invariant the "
                "re-derivation holds is nothing under `dashboard/`",
        checker=None,
        proof=None,
        scope="code",
        teaches=None,
        state=REPEALED,
    ),
)


#: Keyed lookup over the same tuple, so nothing restates a scope or a checker.
#: An id absent here raises at the caller that invented it, which is the loud
#: form of "the table is the enumeration".
BY_RULE_ID = {rule.id: rule for rule in RULES}
