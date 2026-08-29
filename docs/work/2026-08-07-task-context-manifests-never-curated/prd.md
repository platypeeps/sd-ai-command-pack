---
title: "PARKED: Nothing ever requires a task's spec manifests to be curated, so sub-agents dispatch with no spec context"
status: planning
created: 2026-08-07
---
# PARKED: Nothing ever requires a task's spec manifests to be curated, so sub-agents dispatch with no spec context

## Goal

Make an uncurated `implement.jsonl` / `check.jsonl` visible — and, at the
boundary where it starts to matter, blocking — so a task cannot be implemented
and archived with the generated scaffold standing in for its spec context.

## What this task is not

It is **not** a request to fail preflight on the `_example` scaffold. That
exemption is deliberate, is documented in the code, and must stay.
`validateBookkeepingTaskContexts`
(`scripts/sd-ai-command-pack-review-preflight.mjs:810`) says so directly:

```text
A manifest whose ONLY row is the untouched generated `_example`-only scaffold
`task.py create` writes is treated as unfilled/advisory, not a blocking seed
row -- regardless of task status or archival. A lone scaffold is
indistinguishable from an empty/unfilled manifest and is never genuine
leftover scaffold; that only happens when an `_example` row is MIXED with real
rows, which still fails below. Gating the exemption on `status === 'planning'`
was too narrow and produced a LATE, merge-time `task_context_seed` failure on
completion (finding #5); the match is on the lone-scaffold shape, not on
Trellis's seed text.
```

That reasoning is sound: a lone scaffold and an empty file carry the same
information, and failing at merge time on something that should have been
settled during planning is worse than not failing at all. The prior decision is
owned by the archived `07-29-exempt-planning-scaffold-preflight`.

The gap is what the exemption leaves behind: `void record; void archived;` — the
exemption applies at **every** status and after archival, and no other gate
takes over later. So "advisory" never becomes "required" anywhere.

## Problem

Sub-agent dispatch reads these manifests first. `.trellis/workflow.md:229`:

```text
Read context: jsonl entries -> `prd.md` -> `design.md if present` ->
`implement.md if present`.
```

An uncurated manifest therefore does not fail — it silently degrades. The
sub-agent starts with no spec context and proceeds, and the resulting work is
weaker in a way that leaves no signal anywhere: no error, no warning, no
status row, no preflight finding.

### Scale

Measured on the active backlog, 2026-08-07:

```text
active task dirs: 52 | jsonl files total: 102
jsonl files with _example: 54 | task dirs affected: 27
```

Twenty-seven of fifty-two tasks — over half the backlog — carry the scaffold in
at least one manifest. Every one of them is currently `planning`, so none is
wrong *today*. The point is that nothing between here and archival will ask.

### Why it stays invisible

- Preflight exempts it, correctly, at every status.
- `task.py start` does not look at manifests.
- `sd-status` reports task status and priority, not artifact readiness at this
  granularity.
- The completion path checks acceptance criteria, not whether the manifests
  that fed the implementation had anything in them.

## Requirements

1. The preflight exemption for a lone pristine scaffold is unchanged. This task
   adds no new failure at planning time and does not reintroduce the merge-time
   `task_context_seed` regression the exemption was written to fix.
2. Uncurated manifests are surfaced where a reader will see them before
   dispatch — an advisory row identifying which tasks have an unfilled
   `implement.jsonl` or `check.jsonl`, and which of the two.
3. At the dispatch boundary, an unfilled manifest is stated rather than
   silently skipped: the sub-agent context step reports that it is proceeding
   with no spec entries, instead of reading zero rows and continuing.
4. The distinction between *unfilled* and *deliberately empty* is preserved. A
   task that genuinely needs no spec context must have a way to say so that
   does not read as an oversight, and that way must be as cheap as leaving the
   scaffold in place, or nobody will use it.
5. Whatever gate is chosen fires at a boundary the author controls before
   implementation begins, not at merge. Late failure is the failure mode the
   existing exemption exists to prevent.

## Open decisions

**Where the requirement lands.** Three candidates, in increasing strength:

- *Advisory only* — surface it in `sd-status` and in the dispatch report,
  require nothing. Cheapest, changes no gate, and relies on authors noticing.
- *Gate at `task.py start`* — a task cannot become `in_progress` with unfilled
  manifests unless it declares it needs none. Fires exactly when the author is
  already looking at the task, and well before merge.
- *Gate at completion* — the strongest, and the one the existing exemption's
  history argues against: it is the late, merge-time failure that was already
  tried and reverted.

Recommendation: advisory surfacing plus a gate at `task.py start`. Explicitly
not at completion.

**Whether `check.jsonl` and `implement.jsonl` are held to the same standard.**
They feed different sub-agents and a task may legitimately need one and not the
other. Recommendation: evaluate them independently and report them
independently.

## Acceptance criteria

- The preflight result for every currently active task is unchanged by this
  work, verified by running the bookkeeping validator over the task tree before
  and after and diffing the findings.
- A task with a lone pristine scaffold in either manifest is reported as
  unfilled, naming which manifest.
- A task with real entries in both manifests produces no advisory row.
- A task that has declared it needs no spec context produces no advisory row,
  and the declaration is a single documented edit.
- A sub-agent dispatched against an unfilled manifest reports that it is
  proceeding without spec entries; the report is visible in the run, not only
  in a file.
- No new failure is introduced at merge time for any task state.
- The `_example`-mixed-with-real-rows case still fails, exactly as it does
  today.

## Out of scope

- Removing or narrowing the lone-scaffold exemption.
- Curating the 27 affected tasks' manifests. This task decides the rule; the
  backlog is swept separately once there is one.
- Changing what the `_example` seed row says, or whether `task.py create`
  writes it. That is upstream Trellis
  (`.trellis/scripts/common/task_store.py:163-169`).
- The sub-agent dispatch protocol itself, beyond the one report line in
  requirement 3.
