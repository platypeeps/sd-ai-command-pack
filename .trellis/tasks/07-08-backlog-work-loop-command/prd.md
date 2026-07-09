# Add backlog work loop command

## Goal

Add a new `sd-work-backlog` command that lets an agent repeatedly work down a
Trellis task backlog in one active repository: pick the highest-value task that
has implementation-ready planning, implement exactly one task at a time,
publish it through the existing SD PR workflow, merge and clean it up through
housekeeping, address or record follow-ups and learnings, then continue to the
next actionable task until nothing remains that can proceed without user input.

## Background

The pack already has reliable single-stream commands:

- `sd-create-pr` refreshes specs, stages intended work, commits, pushes,
  creates or reuses a PR, and hands off to `sd-review-pr`.
- `sd-review-pr` runs the deterministic full-check, requests the configured
  remote reviewer, handles comments and CI, and runs finish-work.
- `sd-housekeeping` merges only clean, green, comment-clean PRs and returns the
  repo to the default branch.

The new command should orchestrate those workflows rather than replacing their
merge, review, or cleanup logic.

## Requirements

- R1: Install a new shared `sd-work-backlog` skill under
  `.agents/skills/sd-work-backlog/SKILL.md` and expose thin platform adapters
  matching the existing command pattern.
- R2: The command must inventory active Trellis tasks through existing Trellis
  task/context commands and select only actionable tasks:
  - task status is `planning` or `in_progress`
  - `prd.md` exists and is not placeholder-only
  - PRD has a goal plus testable requirements or acceptance criteria
  - no blocking open question or parked marker indicates the task currently
    needs user input
  - for complex tasks, `design.md` and `implement.md` are present before the
    command starts implementation
- R3: Highest-value selection must be deterministic enough to explain in the
  final report: prefer `in_progress` tasks, then priority `P0` through `P3`,
  then tasks with complete implementation artifacts, then older tasks.
- R4: For each selected task, the command must use existing Trellis and SD
  flows as sources of truth, and it must complete or park the selected task
  before starting another one:
  - activate/start the task only after its planning artifacts are ready
  - load `trellis-before-dev` before editing
  - implement inline in the current session
  - run the relevant checks
  - invoke `sd-create-pr` for publish/review
  - invoke `sd-housekeeping` after the PR is ready or merged
  - run one extra housekeeping pass after cleanup
  - return to backlog selection only after the current stream is merged and
    clean, or after the task is explicitly parked
- R5: If a task needs user input, the command must ask one concise blocking
  question, wait up to 15 minutes when the platform/session can wait, then park
  the task and continue to the next actionable candidate if no answer arrives.
- R6: Parking must use existing Trellis-compatible state, not a new unsupported
  task status. Add a dated `Parked by sd-work-backlog` note to the task PRD and
  leave the task in its compatible status so normal Trellis commands still work.
- R7: The command must stop when no active tasks remain, or when all remaining
  tasks are parked, missing implementation-ready planning, blocked by user
  input, or otherwise unsafe to run autonomously.
- R8: The command must not create PRs in the upstream `Trellis` repository
  without explicit user approval. If a selected task discovers a Trellis-owned
  change, it must park or hand off with a paste-ready message.
- R9: After each completed task, the command must process follow-ups and
  learnings before selecting the next task:
  - directly address follow-ups that are small, unblocked, and clearly belong
    to the just-completed task stream
  - record larger, separate, blocked, or lower-priority follow-ups as Trellis
    tasks with enough detail to resume later
  - update specs, docs, or review learnings when the completed task produced a
    durable convention or prevention pattern
  - report which follow-ups were addressed immediately and which were recorded
    as tasks
- R10: Add README and installed docs coverage describing the command, its
  selection rules, its 15-minute user-input wait/park behavior, and its safety
  boundaries.
- R11: Add installer/manifest coverage so supported adapters install the new
  command consistently.

## Out Of Scope

- No background daemon or unattended scheduler.
- No new Trellis task status, lifecycle hook, or task queue schema.
- No bypass of existing `sd-create-pr`, `sd-review-pr`, or `sd-housekeeping`
  safety gates.
- No automatic continuation after the agent session has ended.
- No upstream `Trellis` pull request creation.

## Acceptance Criteria

- [ ] `sd-work-backlog` appears in the shared skills and supported platform
  adapters installed by the pack.
- [ ] The shared skill documents backlog inventory, PRD readiness checks,
  ranking, implementation, publish/review/merge/cleanup, follow-up handling,
  stop conditions, and final reporting.
- [ ] The command explicitly delegates PR creation/review to `sd-create-pr` and
  merge/cleanup to `sd-housekeeping`; it does not duplicate their internals.
- [ ] The command loops sequentially: one selected task is completed, parked,
  or stopped before another task starts.
- [ ] Follow-ups and learnings from each completed task are either addressed
  immediately as the next step in the stream or recorded as Trellis tasks /
  durable knowledge before the backlog loop advances.
- [ ] The 15-minute input wait and parking behavior are documented without
  requiring unsupported Trellis statuses.
- [ ] `manifest.json`, README, installed docs, and installer tests are updated
  for the new command.
- [ ] Local validation passes for focused installer tests and the deterministic
  full-check.

## Open Questions

None blocking. The implementation uses `sd-work-backlog` as the command name,
matching the earlier recommendation.
