---
title: Close four sd-fleet-refresh lane defects found in the 0.71.62 rollout
status: planning
created: 2026-08-28
---
# Close four sd-fleet-refresh lane defects found in the 0.71.62 rollout

## Goal

Four defects cost an operator a failed or blocked lane, a rejected command, or
a recovery during the 0.71.62 fleet rollout. All four are knowable in advance and none is documented where
the operator is standing when it bites. Close each at the point of failure —
prefer a mechanical guard over a sentence in a skill file.

## Context

Found running `sd-fleet-refresh` across nine consumers on 2026-08-28. Each cost
a recovery, and the first cost a half-published lane.

### D1 — a seeded task that is not bound to its branch fails after the work commit

`task.py create` alone leaves `branch: null` and `status: planning`. The task
must also get `set-branch` and `start`. Without them, `fleet-publish` makes the
work commit first and only then calls `task.py archive`, which fails its
precondition (`.trellis/scripts/common/task_store.py:1290`, guarded by
`_validate_branch_metadata` at line 1128):

```
Not archived: <task dir> is unchanged.
```

The lane is now half-published: work commit made, no archive, no journal.
Recovery on rwbp-coordinator was `git reset --mixed <base>`, then `set-branch`,
`start`, and republish. `fleet-publish` performs no rollback on archive failure —
its own documentation says so.

The related trap is `--base-branch`. Without it, `create` resolves the base from
`origin/HEAD` and falls back to the *checked-out* branch, which by that point is
the refresh branch, and the review preflight rejects the lane at
`focused-candidate` under its root-task rule.

### D2 — a fleet PR body without the scope heading blocks the deterministic gate

`pack.review-scope` requires a PR-body heading matching, case-insensitively
(`grep -Eiq`, `scripts/sd-ai-command-pack-review-scope.sh:294`):

```
^[[:space:]>#*\-]*(Tooling/generated scope|Generated/tooling scope|Copied/generated scope)(:.*|[[:space:]]*)$
```

A fleet refresh PR without it fails the gate, and the review reports only
`deterministic-check-not-passed` — the operator must run the check by hand to
learn which of several sub-checks failed, and why.

The emitter already exists. `scripts/sd-ai-command-pack-pr-body-scope.py`
defines `TOOLING_SCOPE_SECTION` for a wholly-generated diff and
`MIXED_SCOPE_SECTION_*` for a mixed one, and `sd-create-pr` is already wired to
it. The fleet lane's `pr-publication` stage is not: during the 0.71.62 rollout
every fleet PR body was authored by hand, which is why the heading was missing
on the first one and hand-copied onto the following eight. So D2 is a wiring
gap, not missing functionality.

### D3 — a local disposition keyed on the provider's finding id is rejected

`--local-disposition` takes the coordinator-normalized id from
`local.receipt.findings[].id`, not the provider's internal id. Using the latter
gives:

```
local disposition ids match no finding at this head: 4b54c7711cec6832
```

Both ids are 16 hex characters and both appear in artifacts under
`.build/sd-review/`, so they are trivially confusable and the error names the
rejected id without naming where the right one lives.

A related trap — an empty `implement.jsonl` / `check.jsonl` failing seeded-task
validation with `task_context_unfilled`, and a row using `path` instead of
`file` being silently treated as unfilled
(`scripts/sd-ai-command-pack-review-preflight.mjs:1156`) — is in scope here only
as operator documentation. The reporting fix is tracked separately as
`08-28-task-context-row-schema-reporting`.

### D4 — `--release` is required, absent, or optional depending on the subcommand

The controller's campaign subcommands take three different positions on one flag
(`scripts/sd-ai-command-pack-fleet-controller.py`): `plan` (`:1939`) requires it
(`:1941`), `record` (`:1956`) requires it (`:1958`), `resume` (`:1984`) accepts
it optionally (`:1992`), and `next` (`:1953`) does not accept it at all, so
passing it is an argparse error.

The campaign already knows its own release. `status` and `validate` read it out
of state and print it without being told (`:2043-2060`). An operator who has just
been required to pass `--release` to `record` gets an unrecognized-argument
error for the same flag on the next command in the sequence.

## Requirements

- D1: seeding a fleet lane must either bind the branch itself or refuse to
  proceed unbound. A reference implementation exists at
  `~/.local/share/sd-fleet-tools/seed-lane.sh`; folding it into the pack is one
  candidate. Independently, `fleet-publish` should verify the archive
  precondition *before* making the work commit, so the failure mode stops being
  half-published.
- D2: the fleet lane's `pr-publication` must obtain its scope section from the
  existing `sd-ai-command-pack-pr-body-scope.py` emitter rather than from
  operator memory, choosing the wholly-generated or mixed form as that script
  already does. Do not add a second copy of the heading text. A missing heading
  should also be reported by name rather than only as
  `deterministic-check-not-passed`.
- D3: the disposition-id mismatch error must name where the accepted ids come
  from. Naming the field is the whole fix.
- D4: `--release` must behave consistently across the campaign subcommands.
  Since the campaign carries its release in state, accepting and ignoring it, or
  accepting it as a consistency assertion, are both better than one subcommand
  rejecting what the previous one demanded. If a subcommand keeps requiring it,
  say why in the help text.
- Documentation-only fixes are acceptable only where a mechanical guard is not
  possible; say which was chosen and why for each.

## Non-goals

- Redesigning `fleet-publish`'s fold pattern, the review scope gate, or the
  disposition mechanism. Each defect is a sharp edge on a working design.
- The archived-task PR linkage defect — tracked separately as
  `08-28-fleet-publish-pr-linkage`.
- The `task_context_unfilled` misreport — tracked separately as
  `08-28-task-context-row-schema-reporting`. Only its operator documentation is
  in scope here.

## Acceptance Criteria

- [ ] D1: seeding a lane without branch binding is impossible or refused before
      any commit is made, proven by a test.
- [ ] D1: `fleet-publish` cannot leave a lane with a work commit and no archive
      for this cause; the precondition is checked before the commit.
- [ ] D2: a fleet refresh PR body carries the required scope heading without the
      operator adding it, sourced from `pr-body-scope.py` with no second copy of
      the heading text, and a missing heading is reported by name rather than
      only as `deterministic-check-not-passed`.
- [ ] D3: the rejection message names `local.receipt.findings[].id` as the
      source of accepted ids.
- [ ] D4: the same `--release` invocation is valid across `plan`, `record`,
      `next`, and `resume`, or each divergence is documented in its own help
      text. A test covers the sequence an operator actually runs.
- [ ] The jsonl row schema (`file`, `reason`) and the empty-file failure are
      documented where a lane operator will encounter them.
- [ ] Each defect states whether it was closed mechanically or by documentation,
      with the reason.
