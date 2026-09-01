---
title: Harden sd-ai-command-pack-review-layout.py against malformed layout JSON
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-21
---
# Harden sd-ai-command-pack-review-layout.py against malformed layout JSON

## Context

Raised by Copilot during the 0.71.45 fleet refresh, on `answerbook/mezmo_benchmark`
PR #521 (campaign `refresh-0-71-45-20260821T234057Z`), against the vendored copy at
`.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py`.

The finding targets pack-owned payload, not the consumer: the file is written into
every thin consumer by the installer, so no consumer can fix it and a local edit
there is reverted by the next install. It was dispositioned through the fleet
finding severity gate as `consumer-unrelated` / `defer-follow-up` (decision
`continue-with-follow-ups`, zero blockers) and carried here.

Reviewer summary, verbatim:

> **Moderate (2 votes):** Validate JSON object and `files` entry shapes in the
> layout resolver and raise `LayoutError` for malformed input.

## Requirements

- Decide, with evidence from the current source, whether the resolver actually
  accepts malformed input today, and what it does when it does — a traceback, a
  silent wrong answer, or an already-correct `LayoutError`. Record the verdict
  either way. If the reviewer is wrong, this task closes with that finding
  written down, not with a speculative change.
- If the gap is real: validate that the parsed layout document is a JSON object
  and that each `files` entry has the expected shape, and raise `LayoutError`
  with a message naming the offending path and field. Malformed input must not
  surface as a bare `KeyError`, `TypeError`, or `AttributeError`.
- The change is pack-source-owned. It lands in the canonical source under the
  pack repository and reaches consumers only through a release and the normal
  fleet refresh. No consumer repository is edited by this task.
- Every copy of the helper the pack ships stays byte-identical. Enumerate them
  from the filesystem rather than from memory before claiming the sweep is
  complete.

## Acceptance criteria

- [ ] A test covers each rejected shape — non-object document, non-list `files`,
      and a `files` entry missing or mistyping a required field — and asserts
      `LayoutError`, not an incidental exception type.
- [ ] `git grep -l sd-ai-command-pack-review-layout.py` enumerates every shipped
      copy, and all of them carry the change.
- [ ] `make check` passes.

## Out of scope

- The three consumer-owned defects from the same review round. Those were fixed
  in `mezmo_benchmark` commit `ab677900` and in that PR's description.

## References

Research notes that lived beside this item's Trellis record and were not carried
into docs/work. Recover the bodies from git history under `.trellis/tasks/08-21-review-layout-malformed-json-validation`:

- research/resolver-malformed-input-verdict.md
