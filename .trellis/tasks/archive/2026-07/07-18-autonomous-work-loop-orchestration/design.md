# Resumable Autonomous Work Loops Design

## Overview

Turn the two existing work skills into selector-specific entry points for one
autonomous state machine. `sd-work-backlog` owns selection and repetition,
`sd-work-designs` supplies the missing-design candidate filter, and `sd-ship`
continues to own the complete publish-to-merge tail for each iteration.

Durability comes from a small user-local state helper. The helper cannot run
the AI workflow itself, but it can make lifecycle transitions, locking,
resumption, context-health reconciliation, and final-stop validation explicit
and testable. The agent remains the executor while repository and ledger state,
not conversational memory, remain authoritative.

## Proposal

### Public Skill Shape

Make `sd-work-backlog` the canonical autonomous controller. Its default
selector considers every task that can responsibly become implementation-ready
from existing repository evidence. A task with a real PRD but missing design
artifacts is therefore eligible; the controller completes those artifacts
before implementation.

Make `sd-work-designs` a thin entry point that resolves the canonical
controller with a trusted `needs-design` selector. The selected task still
continues through implementation and merge. Preserve planning-only usage with
an explicit `until=design` public stop point rather than a separate duplicated
loop.

Add optional `focus` and `focus-only` arguments to both public entry points.
`focus` creates ordered preference bands ahead of normal ranking and then
allows the normal backlog to continue. `focus-only` applies the same matching
but treats exhaustion of matching actionable tasks as a valid terminal state.
The `needs-design` selector is applied first for `sd-work-designs`; focus ranks
only candidates that survive that selector.

Use repeatable public arguments rather than comma parsing:

```text
/sd:work-backlog CI pipeline
/sd:work-backlog focus="CI pipeline"
/sd:work-backlog focus="CI pipeline" focus="release automation"
/sd:work-backlog focus-only="priority:P1" focus-only="scope:ci"
```

Adapters pass the raw argument text to the canonical skill resolver. The
controller validates and normalizes it once. If the invocation contains no
recognized option syntax, trim the full remaining text and store it as one
implicit `focus` expression. Do not split it on whitespace or commas. Explicit
`focus=` remains the form for multiple ordered preferences, and `focus-only=`
remains the form for strict matching. Reject mixed `focus`/`focus-only` modes or
bare-plus-explicit focus before any side effect. An empty invocation follows
the existing ranking contract.

Recognized lifecycle options, including `until=design`, must be parsed before
bare-focus fallback. Unknown option-shaped tokens fail rather than becoming
focus text. This keeps convenient natural-language invocation from hiding
misspelled safety or lifecycle controls.

Move detailed one-task planning guidance from the current design skill into a
shared reference owned by the canonical controller. This avoids circular
delegation and keeps the public design skill small.

### Focus Resolution And Ranking

Represent focus as an ordered list of expressions plus a `prefer` or `only`
mode. Support structured expressions for stable task fields, including
`priority:`, `package:`, `task:`, `status:`, and `scope:`. Treat an unprefixed
expression such as `CI pipeline` as a conservative case-insensitive semantic
match over the task title, description, converged PRD text, package, scope,
related files, and explicit task metadata.

For every candidate, return match evidence rather than only a score. Evidence
names the field and short matching value, for example `title contains CI` or
`related file .github/workflows/ci.yml`. Exact structured matches outrank
natural-language matches. Multiple focus expressions create ordered bands in
the order supplied. Existing task priority, readiness, age, and lexical rules
remain deterministic tie-breakers inside each band.

Do not use embeddings, network calls, or source-tree-wide inference for focus
selection. If no natural-language candidate has grounded evidence, `prefer`
mode reports the miss and falls back to normal ranking; `only` mode stops with
`focused_backlog_exhausted`. Persist both the original user text and normalized
form so the report remains understandable after resume.

### Iteration State Machine

Use these durable phases:

1. `inventory` - reconcile repository, Trellis, GitHub, lock, and prior ledger.
2. `selected` - record the ranked task, selector evidence, and initial plan.
3. `planning` - converge PRD/design/implementation artifacts and decisions.
4. `implementing` - establish branch/task state and make the scoped changes.
5. `validating` - run focused checks and prepare the branch for shipping.
6. `shipping` - invoke `sd-ship until=merge` through a trusted nested context.
7. `followups` - address or record follow-ups and durable learnings.
8. `complete` - verify clean default-branch state and increment counters.
9. `checkpoint` - offer a stop or persist a context/operator checkpoint.
10. `stopped` - record an evidence-backed terminal reason.

Every transition first validates the permitted prior phase, then atomically
writes the resulting state. The controller may not emit its final response
until the helper confirms either `stopped` with a valid reason or `complete`
with no remaining actionable candidates.

### Nested Skill Return Contract

Extend `sd-ship` with a trusted internal caller context for the autonomous
controller. Its existing stages and safety rules remain unchanged. After
housekeeping, it returns a compact result containing PR, merge state,
finish-work outcome, housekeeping outcome, review rounds, final branch, HEAD,
and anomalies. The result is data for the parent controller, not the parent
session's final response.

The outer loop must not invoke `sd-create-pr`, `sd-review-pr`, `sd-watch-pr`,
or `sd-housekeeping` separately. This preserves the single lifecycle owner and
prevents duplicated review-learning, finish-work, or merge actions.

### Durable State Helper

Add a shipped standard-library Python helper with commands for starting,
inspecting, transitioning, reconciling, checkpointing, parking, completing,
and stopping a loop. Prefer this state-root order:

1. `SD_AI_COMMAND_PACK_STATE_HOME` when it is an absolute path.
2. `XDG_STATE_HOME/sd-ai-command-pack` when set and absolute.
3. `%LOCALAPPDATA%/sd-ai-command-pack/state` on Windows when available.
4. `~/.local/state/sd-ai-command-pack` otherwise.

Identify a repository with a digest of its normalized root and canonical Git
remote. Store a human-readable repository label alongside the digest. State
files must use schema-versioned JSON, atomic temporary-file replacement, and
user-only permissions where the platform supports them.

The ledger should contain:

- schema version, run ID, repository identity, mode, selector, ordered focus
  expressions, normalized focus selectors, and focus mode;
- status, phase, iteration, timestamps, heartbeat, and context epoch;
- current task, branch, HEAD, base branch, PR number/URL, and last shipped SHA;
- completed/parked/blocked counters and compact iteration results;
- decisions, follow-up pointers, checkpoint target/state, and stop reason; and
- lock owner metadata sufficient to detect concurrent or stale runs.

Do not persist tokens, environment values, raw logs, complete PR bodies, or
review payloads. Bound historical iteration entries so state remains compact;
completed details already live in Trellis, Git, and GitHub.

### Reconciliation And Idempotency

At startup, resume, every phase boundary, and every iteration boundary, compare
the ledger with live state. Reconciliation checks include:

- repository root and remote identity;
- active Trellis task and planning status;
- current branch, clean/dirty paths, HEAD, and remote tracking state;
- open or merged PR for the branch and its head SHA;
- review requests/results keyed to head SHA;
- finish-work/archive evidence; and
- post-merge default-branch and stale-ref state.

When live state is ahead of the ledger, advance the ledger only after verifying
the corresponding evidence. When the ledger is ahead, mark context health red
and stop rather than replaying an unverified side effect. Reuse existing branch
and PR discovery from the delegated skills instead of implementing alternate
GitHub policy.

### Context Health

Use evidence-based health levels:

- `green`: ledger, stated phase, and live state agree.
- `amber`: a compaction/continuation/truncation signal occurred, context was
  reloaded, or a remembered detail lacks current evidence but no contradiction
  exists. Re-read the selected task, applicable specs, Git state, and PR state,
  increment the context epoch, and continue after reconciliation.
- `red`: a state contradiction, duplicate-side-effect attempt, wrong task or
  branch, unexplained dirty file, or unverifiable completed phase exists.
  Persist a checkpoint and stop or safely park.

Begin every iteration from rehydrated state. Also allow a context checkpoint at
a clean boundary after several complex phases, independent of the operator's
near-ten-iteration checkpoint. On platforms without automatic fresh-context
continuation, the final report must include the exact resume command and the
ledger must make that resume lossless.

### Autonomy And Interrupts

Document that invoking a full-cycle loop authorizes ordinary repo-local work
through a green merge and the recording of clearly scoped follow-up tasks.
Before the first mutation, print the authority boundary and current checkpoint
target. Never extend that authority to upstream Trellis PRs, destructive
operations, credentials, security-sensitive choices, or product decisions that
cannot be inferred responsibly.

Check for newer operator instructions before selecting each task. `stop after
current` finishes the active iteration and exits cleanly; `stop now` checkpoints
at the next safe transition; `pause` releases or marks the lock resumable;
`skip` parks only before mutation; `reprioritize` affects the next inventory;
and focus updates are persisted before immediate re-inventory.

Use bounded retry/backoff for transient failures. A task-local blocker may be
parked and skipped only when no uncommitted implementation or blocking open PR
prevents returning to a clean default branch. Otherwise the blocker is
repository-wide for this run and must stop the loop.

### Iteration And Status Reports

Before work begins, report iteration number, task, selection reason, concise
plan, current focus and match evidence, and current decisions. After cleanup,
report outcome, PR, checks, review rounds, counters, decisions, follow-ups,
context health, focused tasks remaining, and next candidate.

Around iteration ten, choose a clean boundary between approximately iterations
eight and twelve and emit a non-blocking stop offer. Continue unless the user
asks to stop. Track time, CI retries, and remote-review rounds as informational
budgets; never relax a gate when a budget is reached.

Extend `sd-status` to read the same helper and show active/paused/stopped loop
state without mutating it, including focus mode and expressions.

## Boundaries And Non-Goals

- Do not build a daemon, scheduler, or provider-specific agent launcher.
- Do not promise automatic fresh-session creation on platforms that lack it.
- Do not run multiple task branches or PRs concurrently.
- Do not replace Trellis task state, Git history, GitHub PR state, or existing
  SD lifecycle skills with the local ledger.
- Do not make the state ledger a tracked repository artifact.
- Do not change upstream Trellis runtime files as part of this task.

## Affected Files

Expected source-of-truth surfaces include:

- `templates/.agents/skills/sd-work-backlog/SKILL.md`
- `templates/.agents/skills/sd-work-backlog/references/autonomous-loop.md`
- `templates/.agents/skills/sd-work-designs/SKILL.md`
- `templates/.agents/skills/sd-ship/SKILL.md`
- `templates/.agents/skills/sd-status/SKILL.md`
- a new `templates/scripts/sd-ai-command-pack-work-loop.py`
- synchronized root mirrors under `.agents/skills/` and `scripts/`
- `manifest.json` and generated platform adapters/installed targets as required
- `tests/test_work_loop.py`, `tests/test_sdlc_commands.py`,
  `tests/test_status.py`, installer tests, and generated parity tests
- `templates/docs/SD_AI_COMMAND_PACK.md`, `README.md`, `CHANGELOG.md`, and
  `templates/.agents/skills/sd-help/references/` command documentation
- `.trellis/spec/frontend/adapter-guidelines.md` for the durable orchestration
  contract

Exact platform adapter changes should be determined through manifest/install
generation rather than hand-maintained duplication.

## Risks And Edge Cases

- A stale lock can block legitimate recovery. Recovery must distinguish an
  expired heartbeat from live branch/PR activity and avoid silently stealing an
  active run.
- A repository move or remote rename can change identity. Provide explicit
  state inspection and conservative migration rather than guessing.
- The design skill's new default full lifecycle is a visible semantic change.
  Documentation and `until=design` must make the behavior unambiguous.
- A user can merge or edit a PR externally while the loop waits. Reconciliation
  must treat GitHub as authoritative and avoid replaying lifecycle steps.
- Review and CI output can be large. Persist only compact deltas and query live
  details on demand.
- Automatic context degradation cannot be measured reliably on every platform.
  The health protocol detects consequences and uses proactive rehydration; it
  must not claim a precise context-usage metric.
- Follow-up task creation can expand the backlog indefinitely. Rank newly
  created work normally, split only oversized tasks, and honor the operator
  checkpoint and stop controls.
- Natural-language focus can be ambiguous. Require grounded field evidence,
  expose the match reason, preserve deterministic tie-breakers, and provide
  structured selectors for users who need exact behavior.

## Validation

Use deterministic state-machine tests with temporary repositories and mocked
GitHub/Trellis observations. Exercise every transition, invalid transition,
atomic-write recovery, stale lock, repository identity mismatch, state/live
contradiction, bounded history, operator control, and context-health result.

Add skill-contract tests that prove both selectors enter the same lifecycle,
planning occurs when artifacts are missing, `until=design` stops before
implementation, `sd-ship` returns to the controller, iteration summaries are
required, focus preference falls back correctly, focus-only never broadens,
operator focus changes re-inventory, and final output requires a verified stop
condition.

Run focused tests, installer and generated-parity suites, payload drift checks,
documentation checks, and the repository's canonical `make check`/full-check
before release.
