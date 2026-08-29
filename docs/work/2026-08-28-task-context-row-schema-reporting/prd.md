---
title: Report a task-context row missing its file key instead of an empty manifest
status: planning
created: 2026-08-28
---
# Report a task-context row missing its file key instead of an empty manifest

## Goal

A task-context manifest whose rows omit the `file` key is reported as containing
no rows at all. The operator reads `contains no context rows` against a file
that visibly has rows, and the receipt points at the wrong defect. Name the
actual defect: the row is present and carries no `file` key.

## Context

Found during the 0.71.62 fleet rollout. A manifest row written as
`{"path": ..., "type": ...}` instead of `{"file": ..., "reason": ...}` fails the
lane at `task_context_unfilled`, which is not what went wrong.

The reporting path is `scripts/sd-ai-command-pack-review-preflight.mjs:1120-1160`.
Both halves of the check key on one thing: whether the row carries a `file`
property.

`findTrellisTaskContextIssues` (`:4676`) classifies a row as a generated
`_example` scaffold, malformed JSONL, a reference outside the allowed
spec/research roots, or a self-reference. The last two are reachable only from
inside `if (... hasOwnProperty(record, 'file'))` at `:4697`. A row without a
`file` key matches no branch and falls out of the loop, so nothing is pushed and
`emittedForFile` stays at 0.

`countTrellisTaskContextRows` (`:4579`) then counts a row as usable iff it
`hasOwnProperty('file')` (`:4591`), so it returns 0, and the final guard fires:

```js
if (seedReady && emittedForFile === 0 && countTrellisTaskContextRows(loaded.text) === 0) {
  add('task_context_unfilled', file,
      'contains no context rows; add at least one '
        + '{"file": "<spec-or-research-path>", "reason": "<why>"} row');
}
```

Three things follow. The finding is misdirected — a row missing `file` and a
genuinely empty file are indistinguishable in the receipt. The check runs only at
seeding time (`seedReady`), by the comment's own reasoning at `:1135-1140`: at
merge time an unfilled manifest cannot be told apart from one never curated, so
failing there produced a late, completion-time failure. A row missing `file` is
not subject to that ambiguity — it is unambiguously a defect wherever it is read
— so it may warrant different staging than `unfilled` does.

And the trigger is narrower than the reported message implies. `reason` is never
inspected by either function, so `{"file": ..., "type": ...}` counts and
validates normally while `{"path": ..., "reason": ...}` counts as nothing. The
defect is a missing `file` key, not an unrecognized key set. Whether an absent
`reason` should also be reported is a scope question to settle, not an
assumption to inherit.

Mitigating factor, and the reason this is not higher severity: the message does
print the correct row shape, so an operator who reads it to the end can repair
the row without knowing why the count was zero.

## Requirements

- A row that carries no `file` key must produce a finding that says so, and must
  name the offending line number the way the sibling defects do.
- Preserve the `emittedForFile` guard's purpose. The comment at `:1142-1144`
  states it exists to keep the receipt precise — a lone scaffold, a malformed
  line, and a self-citation each already say exactly what to fix, and a vaguer
  "no rows" finding stacked on top makes it worse. A new finding must not
  reintroduce double-reporting.
- `task_context_unfilled` must keep meaning what it says: no rows. A file whose
  rows lack `file` is not unfilled.
- Decide deliberately whether the new finding is seeding-only like `unfilled` or
  runs at every stage like the malformed and self-reference checks, and record
  the reasoning. Do not inherit `seedReady` by accident.

## Non-goals

- Widening the accepted row schema. `{"file", "reason"}` stays the contract;
  this task changes reporting, not what is valid.
- Adding validation of `reason`. Today neither function inspects it; deciding to
  start is a separate change with its own blast radius across seeded tasks.
- Revisiting the scaffold exemption or the allowed spec/research roots.

## Implementation note

`review-preflight.mjs` exists at four paths, all carrying this logic at the same
line number:

```
scripts/sd-ai-command-pack-review-preflight.mjs
plugins/sd/bin/sd-ai-command-pack-review-preflight.mjs
plugins/sd/machine-payload/scripts/sd-ai-command-pack-review-preflight.mjs
templates/scripts/sd-ai-command-pack-review-preflight.mjs
```

Establish which is the source of truth and how the others are produced before
editing. A fix that lands in one copy and not the rest ships a validator that
disagrees with itself depending on which install ran it.

## Acceptance Criteria

- [ ] A manifest containing only rows without a `file` key produces a finding
      naming the line and the missing key, and does **not** produce
      `task_context_unfilled`.
- [ ] A genuinely empty or whitespace-only manifest still produces
      `task_context_unfilled`, unchanged.
- [ ] A manifest with one valid row and one row missing `file` reports exactly
      one finding, against the bad row.
- [ ] No input produces both the new finding and `task_context_unfilled`.
- [ ] `tests/test_bookkeeping_validator.py` covers the new case alongside the
      existing `task_context_unfilled` assertions at `:325`, `:383`, and `:439`.
- [ ] All four `review-preflight.mjs` copies agree, verified by comparing them
      rather than by editing each from memory.
