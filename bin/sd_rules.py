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

**Why a code table and not a YAML or JSON file.** A data file reads better, and
that is why the rejection has to be explicit. A data file cannot name a
callable; it names a string, and something must resolve that string back to a
function. That resolver would be a second source of truth about which checkers
exist, and it would fail at run time rather than at import time. This table
holds the function object itself, so a row naming a checker that does not exist
raises on the first import, before any test runs.

**The meta-check is the deliverable, not the rules.** Legs a, b and c in
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

import pathlib
import re
import sys
from collections.abc import Callable
from typing import NamedTuple

_BIN = str(pathlib.Path(__file__).resolve().parent)
if _BIN not in sys.path:  # pragma: no cover - import bootstrap, not behaviour
    sys.path.insert(0, _BIN)

import sd_setup_github  # noqa: E402 - after the bootstrap that makes `bin/` importable

#: What a rule id looks like, in one place. Every reader of rule ids -- the
#: meta-check's three legs, and anything that grows later -- compiles nothing
#: of its own against this shape, for the reason the table exists at all.
#:
#: The form is the pack's existing `R<round>-D<decision>` id, deliberately.
#: Inventing a second id space would leave the 47 ids cited in live prose on
#: `cddd3b98` resolving to nothing, and "a rule id cited nowhere in the registry
#: fails" is leg c's whole job.
RULE_ID = re.compile(r"\bR\d+-D\d+\b")

#: A rule that is in force. Its checker runs and its skill teaches it.
LIVE = "live"

#: A rule that has been withdrawn. Its id stays in the table forever.
#:
#: This state exists before the first repeal rather than after it, because a
#: repealed id must never become reusable: live prose citing `R5-D1` must not
#: quietly start resolving to whatever rule next claims that id. A repealed row
#: carries no checker -- there is nothing left to enforce -- and no skill has
#: to teach it, so leg a skips it. Leg c still resolves it, which is the point:
#: prose citing a repealed rule is answered, not left dangling.
REPEALED = "repealed"

#: The scopes a rule can have. `code` rules read source, `prose` rules read the
#: documentation corpus, `both` reads both.
SCOPES = ("code", "prose", "both")

#: Every state a row may carry.
STATES = (LIVE, REPEALED)


class Rule(NamedTuple):
    """One quality rule that exists, and everything a consumer needs of it.

    `checker` is the callable that enforces the rule, held as the function
    object rather than as its name. A row naming a checker that does not exist
    is an `ImportError` at the top of this module, which is the loud form of
    "every registry row names its checker". A `REPEALED` row carries `None`,
    because a withdrawn rule has nothing left to run.

    `teaches` names the skill section that teaches the rule, as
    `path#heading`. The skill cites the rule id; it does not restate the rule,
    because two copies of a sentence are two things that can disagree. That
    second half has no mechanical check and this module does not claim one --
    asserting an enforcement nothing performs is the exact defect the registry
    exists to end, and it would be absurd to commit it here.
    """

    id: str
    subject: str
    checker: Callable[..., object] | None
    scope: str
    teaches: str
    state: str = LIVE


#: The enumeration. This tuple is the *only* answer to "which rules exist".
#: Every consumer iterates it; no consumer carries a second list, which
#: `test_no_consumer_carries_a_second_list` holds them to. Adding a rule means
#: adding a row here and a checker -- never editing a skill's list of rules,
#: which is how the sentence and the machinery come apart.
#:
#: `checker` holds a callable that lives in `bin/`, not a test. A test proves a
#: rule holds; the code is what performs it, and a row pointing at the code
#: breaks at import the day that code is deleted -- which is the signal worth
#: having. It also keeps this module out of `tests/`, which nothing under
#: `bin/` imports.
#:
#: The cost of that is an import edge from here to every module a row names, so
#: a consumer importing this table imports them too, and a module named by a
#: row must never import this one back. Neither of today's two does. The day a
#: rule's enforcement lives in a suffixless tool -- `R10-D4`'s
#: `codex_preflight` in `bin/sd-review` is the first -- that edge is not
#: payable: `source:bin/sd_lib.py::sibling` is the pack's way to import one and
#: its contract is that every caller defers it, which a module-level row cannot
#: do. That is the open question the next backfill slice has to answer, and it
#: is recorded in this item's `implement.md` rather than discovered again.
RULES: tuple[Rule, ...] = (
    Rule(
        id="R10-D5",
        subject="only a full-mode repository installs the review routing "
                "lane; `minimal` and `guest` refuse it, so a shared or "
                "upstream repository can never grow the framework's workflow",
        checker=sd_setup_github.setup_github,
        scope="code",
        teaches="skills/sd-review/SKILL.md#setup-github",
    ),
)


#: Keyed lookup over the same tuple, so nothing restates a scope or a checker.
#: An id absent here raises at the caller that invented it, which is the loud
#: form of "the table is the enumeration".
BY_RULE_ID = {rule.id: rule for rule in RULES}
