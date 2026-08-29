# Design: Backlog Work Loop Command

## Architecture

`sd-work-backlog` is a prompt/skill orchestration command, not a standalone
automation script. The shared skill is the source of truth under
`templates/.agents/skills/sd-work-backlog/SKILL.md`, and platform adapters are
thin entry points that resolve and load that skill.

The command composes existing tools:

- Trellis task commands for backlog inventory, task activation, and normal
  task state.
- `trellis-before-dev` before editing a selected task.
- `sd-create-pr` for spec refresh, commit, push, PR creation/reuse, and PR
  review handoff.
- `sd-housekeeping` for merge and branch cleanup.

This keeps the new command focused on task selection and loop control, while
the existing commands retain ownership of safety-sensitive PR and merge logic.
The loop is strictly sequential: it never starts a second backlog task until
the selected task is merged and cleaned up, explicitly parked, or stopped with
a reported blocker.

## Command Surface

Primary name: `sd-work-backlog`.

Installable surfaces follow existing conventions:

- Shared Codex/agent skill:
  `templates/.agents/skills/sd-work-backlog/SKILL.md`
- Claude command: `templates/.claude/commands/sd/work-backlog.md`
- Cursor command: `templates/.cursor/commands/sd-work-backlog.md`
- Gemini command: `templates/.gemini/commands/sd/work-backlog.toml`
- GitHub Copilot prompt:
  `templates/.github/prompts/sd-work-backlog.prompt.md`
- OpenCode command: `templates/.opencode/commands/sd-work-backlog.md`

The manifest should also map the existing reusable Cursor-style adapter and
shared skill into the other platform targets that already use those sources
for analogous `sd-*` commands.

## Selection Contract

Candidate tasks come from `.trellis/tasks/**/task.json`, excluding archived
tasks. The command should use Trellis CLI output first and inspect files only
for PRD readiness details.

Actionable readiness:

- status is `planning` with complete planning artifacts, or `in_progress`
- `prd.md` exists and has meaningful non-placeholder content
- PRD includes a goal and at least one requirement or acceptance criterion
- no unresolved blocking open question, explicit waiting-for-user note, or
  `Parked by sd-work-backlog` note
- if the task appears complex, `design.md` and `implement.md` exist before
  `task.py start`

Ranking:

1. `in_progress` before `planning`
2. priority `P0`, then `P1`, `P2`, `P3`
3. complete planning artifacts before PRD-only tasks
4. older created date/name before newer tasks

The command reports why each selected task won and summarizes skipped tasks.

## Loop Contract

Each iteration has one active work item:

1. Select one actionable task.
2. Start or continue that task.
3. Implement, check, publish, review, merge, and clean up that task through the
   existing SD flows.
4. Run an extra housekeeping pass.
5. Process follow-ups and learnings from that task.
6. Only then return to task inventory and selection.

The command must not stack multiple active implementation tasks, create several
PRs at once, or start a new task while the previous task has unmerged work,
unresolved review feedback, failing checks, dirty local state, or unprocessed
follow-ups.

## Follow-Up And Learning Contract

After each completed task, inspect the just-finished stream for follow-ups and
learnings:

- Address immediately when the item is small, unblocked, and directly part of
  making the just-completed task truly done.
- Record as a Trellis task when the item is larger, separable, blocked, lower
  priority, or outside the just-completed task's scope.
- Update specs, docs, or review learnings when the item is a durable convention,
  gotcha, review pattern, or prevention mechanism.
- Include a short follow-up ledger in the iteration report before selecting the
  next backlog task.

## User-Input Parking

When a selected task needs user input:

1. Ask exactly one blocking question with the recommended answer and tradeoff.
2. Wait up to 15 minutes if the active platform supports timed waiting.
3. If no answer arrives, append a dated `Parked by sd-work-backlog` note to
   that task's PRD with the question, the reason it blocks, and what answer is
   needed to resume.
4. If the task was active, clear or leave it in a normal Trellis-compatible
   state according to existing Trellis commands; do not invent a new status.
5. Continue to the next actionable task.

## Safety And Boundaries

- The command must stop on dirty unrelated work, ambiguous staging, failed PR
  gates, unresolved review threads, failing CI, or housekeeping anomalies.
- The command must stop rather than continue if follow-ups cannot be addressed
  or recorded safely.
- The command must not bypass `sd-create-pr`, `sd-review-pr`, or
  `sd-housekeeping`.
- The command must not create upstream `Trellis` PRs without explicit user
  approval for that specific PR.
- The command only runs while the agent session is active. It is not a daemon
  and cannot wake itself after the session ends.

## Testing Strategy

- Installer tests verify the new shared skill and adapters are installed.
- Adapter-reference tests verify each adapter resolves `sd-work-backlog`.
- Shared-skill tests verify the skill contains the core orchestration terms:
  task readiness, highest-value ranking, 15-minute wait/park behavior,
  `sd-create-pr`, `sd-housekeeping`, and Trellis PR consent.
- Full-check verifies manifest/source drift, adapter docs, KB freshness, and
  PR-body scope rules.
