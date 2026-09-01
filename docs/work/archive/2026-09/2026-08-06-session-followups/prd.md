---
title: "PARKED: Add sd-session-followups sweep-and-act loop"
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-06
---
# PARKED: Add sd-session-followups sweep-and-act loop

## Goal

A session ends with value still uncommitted: content written to scratchpad but
never shipped, defects observed repeatedly but never filed, branches pushed
without a PR, procedures that failed as written. None of it is captured by the
existing surfaces. `sd-review-learnings` is PR-scoped and runs inside a ship
chain; `sd-status` reports current repository state and explicitly refuses to
act. Neither asks the retrospective question: *what did this session produce
that has not landed anywhere?*

Add `sd-session-followups`: a bounded loop that sweeps a finished session for
learnings, recommendations, bugs, suggestions, issues, and cleanups; acts on
what is safely actionable; re-sweeps to catch items the actions themselves
created; and ends with a status report.

## Motivation: what leaked from one session

Every item below is from the 2026-08-06 session that shipped PRs #346 and
#347. Each was noticed in conversation and would have been lost when the
context ended. They are the acceptance fixtures for this command.

| Leaked item | Class |
|---|---|
| Guide section "When Closing Out a Task Whose Work Already Landed" written, pulled off #346 to satisfy the bookkeeping-only rule, left in scratchpad | unshipped artifact |
| `chore/task-upstream-add-session-numbering` pushed, no PR opened | orphan branch |
| Missing `config/routed-review-setup-v1.json`; every review reports `router-not-configured` and `zero-remote-confidence` | unfiled defect |
| Eight `legacy pack reference remains` install-audit warnings | unfiled defect |
| Receipt-pinning defect hit 5 times; its task `08-06-review-check-receipt-pinning` still P2 | under-prioritized recurrence |
| Session-number collision hit 4 times; task filed, no design | under-prioritized recurrence |
| sd-ship Stage 4's documented moved-head recipe (`--base` equal to head) failed with `completion_successor_active_task_ambiguous` | procedure defect |
| Fresh `--artifact-root` at mode 700 used 5 times as an ad-hoc escape, never encoded | uncaptured workaround |
| Trellis active-task pointer left stale after archive | state hygiene |
| Six `08-06-*` tasks remain PRD-only | planning debt |

## Requirements

### R1. Deterministic evidence sources

The sweep must not depend on conversation recall. Its inputs are inspectable
and reproducible:

- `git log <session-base>..HEAD`, and the working tree
- local and remote branches versus open PRs
- the scratchpad directory for the session
- the session's journal entry and its sibling index
- `sd-status --json` (follow-ups, tasks, anomalies, recovery artifacts)
- review receipts and durable coordinator artifacts produced during the session
- the `sd-review-learnings` receipt from sd-ship Stage 2b, consumed rather than
  re-derived (see "Write ownership")
- active-task pointer state and task-directory artifact completeness

Conversation context may *enrich* an item but may never be its sole evidence.
Every reported item carries a concrete reference — path, path:line, branch
name, reason code, or command output.

### R2. The checklist

The sweep asks each question below and reports `none` explicitly when a
category is empty.

**Durable output that has not landed**

1. Content written to scratchpad that represents shippable work, with no
   corresponding commit or open PR.
2. Local or remote branches other than the default with no open PR.
3. Uncommitted or untracked files that are deliverables rather than debris.
4. Corrections made to content that already merged elsewhere — the blast-radius
   check: every store that derives from a corrected fact.

**Defects and recurrences**

5. Failures observed during the session with no Trellis task representing them.
6. Existing tasks whose defect recurred during the session — count the
   recurrences and recommend a priority raise, since recurrence count is the
   evidence a P2 is really a P1.
7. Documented procedures that failed as written: a skill recipe, a flag, or a
   contract whose stated steps did not produce the stated result.
8. Workarounds applied more than once and never encoded in a guide, a script,
   or a check.
9. Facts that were wrong on first attempt and cost a round-trip — wrong flag
   names, wrong paths, wrong invocation shapes.

**State hygiene**

10. Stale Trellis pointers and completed tasks outside the archive.
11. Tasks left PRD-only that the session proved are complex.
12. Spec or KB drift — knowledge indexes stale relative to spec edits.
13. Temporary receipts and `mktemp` artifacts left behind, and any secret or
    credential written into scratchpad or a receipt.
14. Recovery artifacts the session created: stashes, worktrees, receipts.

**Propagation**

15. Shipped surfaces changed this session that fleet consumers have not
    received.
16. Superseded or stale open PRs the session's work has obsoleted.

**Verification debt**

17. Claims made during the session whose named check never ran, and anything
    reported "verified" without decisive output.

### R3. Disposition, not blanket action

"Automatically take action" is scoped by a typed disposition per item:

- `fix-now` — act directly. Permitted **only** for sinks with no other owner:
  untracked debris, leftover `mktemp` receipts and temporary artifacts, and
  stale-pointer clearing. Never a tracked-content edit.
- `delegate` — the item belongs to another command's sink. Invoke that owner
  with its own controls and gates; never write the file directly. See
  "Write ownership".
- `file-task` — separable, larger, or needs a product decision. Create or
  update a Trellis task. Never silently implement it.
- `report-only` — outside this run's authority, or evidence is insufficient.

An item requiring a product decision that cannot be inferred from repository
evidence is always `file-task` or `report-only`, never `fix-now`.

Keeping `fix-now` off tracked content is a security boundary, not caution about
scope. A command that sweeps a session, judges something actionable, and edits
tracked files directly is a route for unreviewed changes to reach the tree
without passing the gates the rest of the pack enforces. It costs almost
nothing: the genuinely automatic cleanups observed so far are all untracked or
state-pointer work.

### R4. Loop and termination

- At most 5 iterations.
- Terminate early when an iteration produces no new actionable item.
- Deduplicate against every item seen in the run, not merely against items
  acted on — otherwise a `report-only` item resurfaces each iteration and the
  loop never converges.
- Deduplicate `file-task` items against existing Trellis tasks by durable ID
  and by exact normalized title, reusing the matcher `sd-status` already
  applies to roadmap follow-ups, so a re-run does not double-file.
- Deduplicate `file-task` items against the current content of the
  `sd-review-learnings` delimited block as well, using the same normalized-title
  matcher. Without this, one pattern lands as prose in the learnings block and
  as a task in Trellis, and neither knows about the other.
- Each iteration reports what it found, what it did, and what changed.
- Re-running the command on an unchanged repository is a no-op.

### R5. Authority boundary

Inherits every existing gate; adds none of its own and weakens none. The run
never merges, force-pushes, pushes to the default branch, deletes branches,
archives Trellis work, runs housekeeping, opens an upstream Trellis pull
request, bypasses branch protection, or weakens a deterministic check. Pushing
a fix to an existing PR branch of the current stream is in scope; creating a
new PR is a decision, not a cleanup.

### R6. Final status

The loop ends by displaying status, so the operator sees the repository state
the sweep left behind rather than the sweep's own summary of it.

## Write ownership

Resolved. Each knowledge sink has exactly one writer. This command writes to
one of them and reaches the others by invoking their owner.

| Sink | Owner | This command |
|---|---|---|
| `docs/review-learnings.md` (delimited block) | `sd-review-learnings` | never writes; invokes its `--update` |
| Trellis tasks | `sd-session-followups` | **owns** — `sd-review-learnings` performs no task creation |
| `.trellis/spec/**` | existing spec owner | recommends only |
| Journal and sibling index | `sd-finish-work` | never touches |

Routing rather than writing is deliberate: `sd-review-learnings` already carries
canonical-containment, ownership, digest-drift, and atomic-replace validation on
its target, and writes only inside a delimited block that preserves surrounding
human-written content. Editing that file directly bypasses machinery that exists
precisely because a machine writes into human prose there.

### Partition by evidence type

Two commands must not surface the same finding. The split is checkable because
evidence type is deterministic:

- evidence is **a review comment** — `sd-review-learnings` owns it;
- evidence is **anything else** in R1 — this command owns it.

Both may legitimately fire on one event without contention, because they write
to different sinks. Worked example from the motivating session: Copilot's
provenance finding. The *pattern* — a close-out PRD asserted provenance that
`implement.md` contradicted — is review-derived and belongs in the learnings
block. The *task* to fix the underlying defect belongs here.

### Composition, not overlap

Ordering already favors this. Stage 2b's learning pass runs inside the ship
chain; this command runs after the chain ends. So the sweep consumes the Stage
2b receipt as an evidence source (R1) instead of re-deriving review patterns,
turning a potential overlap into a dependency.

### Scope correction

An earlier reading of this overlap overstated it. In the default ship path
`sd-review-learnings` runs `--dry-run` and writes nothing at all; it writes only
on an explicit `--update`, and then to a single delimited block in a single
file. The ownership table above therefore prevents a narrow, mostly latent
collision — it is cheap insurance, not the resolution of an active conflict.

## Non-goals

- Replacing `sd-review-learnings`. See "Write ownership" for the resolved split.
- Replacing `sd-status`. The sweep consumes its JSON and ends by displaying it.
- General repository maintenance, dependency upgrades, or broad branch pruning.

## Open questions for design

1. **Session boundary.** What defines `<session-base>`? Candidates: the ledger
   run's recorded base, the last journal session's commit range, or the reflog.
   The command is unreproducible until this is pinned.
2. **Where it hooks in.** Standalone only, or also an optional terminal stage of
   `sd-work-backlog` after the final iteration?
3. **Recurrence counting.** Recurrences are currently visible only in
   conversation. Is there a durable source — receipt artifacts, reason codes
   across runs — or does this category stay evidence-limited?

## Acceptance Criteria

- [ ] `sd-session-followups` exists as a skill and reports every R2 category,
      writing `none` for empty ones.
- [ ] Every reported item carries deterministic evidence per R1; no item rests
      on conversation recall alone.
- [ ] Each item carries a typed disposition per R3, and `fix-now` is refused
      for anything needing a product decision.
- [ ] `fix-now` never edits tracked content: an item whose sink has another
      owner is `delegate`, and the owning command performs the write.
- [ ] `docs/review-learnings.md` is never written directly; a durable review
      pattern reaches it only through `sd-review-learnings --update`.
- [ ] `file-task` candidates dedup against the `sd-review-learnings` delimited
      block as well as against Trellis tasks, so one pattern does not land in
      both.
- [ ] A review-comment-derived finding is left to `sd-review-learnings` per the
      evidence-type partition, while any task it warrants is still filed here.
- [ ] The loop caps at 5 iterations, terminates early when an iteration adds no
      new actionable item, and deduplicates against all seen items per R4.
- [ ] A second run against an unchanged repository files no duplicate task and
      makes no commit.
- [ ] The authority boundary in R5 is enforced and covered by tests.
- [ ] The run ends by displaying status.
- [ ] Replaying the ten leaked items from the motivation table against a
      fixture repository surfaces each one in its stated class.

## Notes

- Complex task: needs `design.md` and `implement.md` before `task.py start`.
  The three open questions above are design inputs, not implementation details.
