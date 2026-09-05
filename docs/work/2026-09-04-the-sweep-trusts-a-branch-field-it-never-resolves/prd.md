---
title: the staleness sweep is silenced by a branch field that nothing resolves
status: planning
created: 2026-09-04
---

# PRD — a claim the sweep believes without checking

## Problem

`sd_sweep` finds work items that have gone quiet. It excludes two kinds of item
from that search, and one of the exclusions is a claim nobody verifies:

```python
if item.status != SWEEPABLE_STATUS or item.branch:
    continue
```

Its own comment says what the field means: *"`in_progress` is somebody's open
work whatever its age, and a `branch:` field claims a branch exists for the
item."* **Claims.** Nothing resolves it. Presence of the string is the whole
test, so an item carrying a `branch:` naming a branch that was deleted months
ago is excluded from the staleness sweep permanently — and the sweep is the only
mechanism that would have surfaced it.

That is a gate silenced by exactly the stale metadata it exists to notice.

**This was demonstrated, not theorised.** The host-parsing item
(`2026-09-04-host-parsing-refuses-what-it-cannot-parse`) was the first item in
this repository ever to use `status: in_progress`, so it was the first to carry
a `branch:` field at all. It named `cap/r11-d30-dashboard-ceiling`. #737 merged
and deleted that branch. The field went on naming it, through a `make check` and
a full CI run, until the next pull request repointed it by hand. Nothing warned,
because nothing looks.

That item closed by dropping the field, and wrote the rule down for the next
one. A convention a human has to remember is what this item replaces.

## Why the obvious fix is wrong

**Not a lint rule.** `sd-docs-lint` and `sd_lib` both check the field is
*present* for an `in_progress` item, and the tempting move is to make one of
them check it *resolves*. That check cannot work where it would run:
`.github/workflows/tests.yml` configures no `fetch-depth`, so CI gets the
default depth-1 checkout with no other branches present. The rule would fail
every branch-carrying item, or be written loosely enough to pass everything —
a gate that cannot fail, which is the shape this repository keeps finding and
should not be adding.

**Not a single `git rev-parse` either.** `sweep()` takes *many* roots, not one.
`bin/sd` builds them from the project allowlist and calls
`sd_sweep.sweep(roots, ...)`, so an item under `loadsmith` must have its branch
resolved against `loadsmith`, not against whichever checkout the sweep was
launched from. A naive resolution in the current working directory would compare
branch names across unrelated repositories and answer on a coincidence of
naming.

## Acceptance criteria

1. An item whose `branch:` names a branch that does not exist in *its own*
   repository is annotated gone and appears as due if it is otherwise due.
2. An item whose `branch:` names a live branch is annotated live and appears
   as due if it is otherwise due; the annotation changes, the listing does
   not.
3. Resolution is per-root. A branch name that exists in one swept repository and
   not another gives different answers for items in each, and a test asserts
   that rather than assuming it.
4. "git cannot answer" is a distinct outcome from "the branch is absent". A root
   that is not a git checkout, or a git invocation that fails, annotates every
   item inside it unknown and says so once per root; it neither adds nor
   removes an item from the report.
5. Branch liveness is advisory, never an exclusion. The sweep asks the remote
   once per root, `git ls-remote --heads <remote>` with no branch argument,
   holds every head the answer lists, and matches each item's `branch:`
   against that set and against local refs by exact ref name; a branch found
   in either is annotated live, a branch found in neither is annotated gone,
   and a query that fails annotates every item in the root unknown. Every
   item past the age threshold is in the report with its annotation; none is
   hidden by it. A test covers each of the three annotations and asserts the
   report's item count is the same across all three; a fixture root with two
   items whose branches exist only on the remote asserts both are annotated
   live and that the recording remote answered exactly one query.
6. Mutation-tested, per the standing bar. At minimum: live and gone swapped,
   the per-root argument replaced by a fixed root, and the "git cannot answer"
   path made to report gone.

## Open questions

1. `scan()` currently needs no git at all — it reads frontmatter off the
   filesystem. This adds a subprocess per item with a `branch:` field. Is that
   acceptable, or should resolution be batched to one `git for-each-ref` per
   root and looked up from a set? Batching is the obvious answer if any
   repository has many branch-carrying items; today the repository has zero, so
   the cost is unmeasured and should be measured rather than assumed.
2. Does a stale `branch:` mean "sweep it" or "report it differently"? An item
   naming a deleted branch is arguably a third state — not quiet, but *lost* —
   and folding it into the due list may hide that it was started and abandoned
   rather than never picked up. A separate line in `render()` is cheap.
3. Should `done` items be checked too? They are already excluded by status, so
   a leftover `branch:` on a `done` item costs nothing today — but it is the
   same dangling claim, and the host-parsing item only avoided it by hand.

## Log

- **2026-09-05** — Recorded from the planning review of
  `2026-09-05-the-pack-runs-a-team-process-for-one-person`, round two, finding
  C-7 against criterion 5 here: counting remote-tracking refs does not
  establish that a branch is live. A deleted branch's ref survives until
  `git fetch -p`, and a branch never fetched has no ref at all, so the rule as
  written can keep hiding the deleted-branch item this item exists for, or
  flag live work on another machine. If this item proceeds, criterion 5 must
  say whether liveness is a fresh remote query or a cached observation, use
  one per-root query with failure reported as unknown, or keep branch
  resolution advisory. That item's criterion 21 removes the sweep; when it
  lands, this item closes as superseded and the question is moot.
- **2026-09-05** — Criterion 5 rewritten from the planning review of
  `2026-09-05-the-pack-runs-a-team-process-for-one-person`, round four,
  finding C-12 there: liveness is advisory, one fresh remote query per root,
  failure is unknown, and no annotation hides an item. The supersession
  recorded above still stands.
- **2026-09-05** — Criteria 1, 2, 4 and 6 brought in line with criterion 5,
  from the planning review of
  `2026-09-05-the-pack-runs-a-team-process-for-one-person`, round five,
  finding C-13 there: liveness annotates, nothing excludes, and the mutation
  set tests the annotation.
- **2026-09-05** — From the solo-first item's ninth planning review, C-20:
  one remote query per root filtered by one item's branch could only
  classify that item, and a second remote-only branch in the same root was
  annotated gone. Criterion 5 now fetches every remote head once per root
  and matches locally; the fixture has two remote-only branches.
