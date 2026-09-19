# Coding to release

This describes the active-session workflow, not an unattended queue runner.
An agent runs the commands; the user owns scope, exceptions, and release permission.

## Steps and owners

| Step | Command or surface | Owner | Exit condition |
|---|---|---|---|
| Inspect | `sd-status --json`; Git status; existing handoff | Coordinating agent | Scope, existing work, and blockers are understood. |
| Plan when needed | `sd-plan` skill; `sd work register docs/work/<item>/prd.md` | User decides; agent records | Required decisions and acceptance checks are clear. Small changes need no plan artifact. |
| Isolate and implement | Git branch or worktree; editor; focused tests | Coding agent | Scoped changes and regression tests exist. Concurrent work remains untouched. |
| Check readiness | `sd-review --scope branch --challenge --explain --json` | Pack inspects; agent handles approval | Local blockers are resolved before checks or dispatch. Runtime approval remains separate. |
| Check | `sd-check --json`; repository `make check` | Repository checks, invoked by agent | Required checks pass. A partial test run does not replace the full gate. |
| Review | `sd-review --scope branch --challenge`; `sd-gate-probes` skill | Independent reviewer; agent dispositions findings | Required coverage completes and blocking findings have evidenced dispositions. |
| Commit, push, open PR | `sd-ship prepare --item ID --json` | Pack command, directed by agent | Exact reviewed head is published. Optional commit flags enumerate each path. |
| Wait for CI | `gh pr checks N --watch --fail-fast` | GitHub runs checks; agent watches once | Checks pass for the intended head. Failures return to implementation. |
| Merge | `sd-ship merge --item ID --expected-head SHA --manual --watch --json` | User authorizes; pack checks; GitHub merges | Review, ownership, protection, and exact-head checks permit the merge. |
| Record delivery | `sd work deliver ID FULL_MERGE_SHA`; `sd-ship reconcile --item ID --json` | Shared database verifies evidence | Delivering merge is confirmed. Slice merges leave the item open. |
| Close out every merge | Ship skill's [post-merge procedure](../skills/sd-ship/references/post-merge-closeout.md); `sd-review-ack --pr N --check --json` | Agent inspects; user approves exact deletions | Findings have evidenced dispositions; retained work and cleanup candidates are inventoried. |
| Activate and verify | Pack: `python3 bin/sd_install.py --pull`; `python3 bin/sd_install.py --verify --json`; system: component installer and check | Operator or authorized agent | Receipt, source, rendered files, PATH resolution, and bounded help checks pass. |

`sd-plan` and `sd-gate-probes` are agent skills, not shell executables.
In Codex, invoke skills with `$sd-plan`, `$sd-review`, or `$sd-ship`.
Their absence from the `/` menu does not establish that skills or shell commands are missing.
The `sd-ship` skill coordinates the sequence; its executable has separate prepare, merge, observe, and reconcile operations.
For itemless changes, use `--no-item --review-id ID` instead of `--item ID` throughout those operations.
Reuse the stable review record; do not create another record to escape review history.
Itemless merge remains manual and retains the same protection, ownership, review, and exact-head gates.
Do not run every listed check twice: the local review also invokes the repository gate.
Check reviewer eligibility and approval boundaries before that expensive invocation.
Read the sd-ai-command-pack checkout's [operator defaults](../.claude/rules/sd-operator-defaults.md) for reviewer, writing, and diagram preferences.

## Implementation ownership

- **Pack:** agent procedures, CLI adapters, local checks, review routing, shipping, and skill installation.
- **System:** shared `sd_db` state, provider settings, spending records, task progress, and runner infrastructure.
- **GitHub:** remote branches, pull requests, Actions, repository protections, and merge execution.
- **User:** desired outcome, provider exceptions, accepted risks, and permissions beyond existing authority.

An active-session agent remains the coordinator.
`sd runner` owns queue execution when that separate workflow is explicitly used.

## Current behavior and limits

- Itemless shipping uses a stable review record without a task row or placeholder planning files.
  Its prepare, merge, observe, and reconcile operations preserve the same review history and authorization gates.
- Readiness is a zero-call local probe, not proof of runtime approval, remote provider health, or OS confinement.
  Oversized-input reports retain the full inventory and propose branch splits; they provide no aggregate review approval.
- Shipping's additive `workflow` object names state, blocker, and next action without replacing existing results or exit codes.
- Explicit local check reuse requires a tracked complete local-only declaration and unchanged full-check identity.
  Read the [receipt contract](../skills/sd-check/references/check-receipts.md) before enabling it.
  Unknown dependencies, dirty inputs, and legacy receipts rerun checks; the pack's network-dependent full gate remains ineligible.
- The pack has an accepted protection exception in `.github/sd-status.json`.
  Its executable merge refuses absent protection; the maintainer uses the documented manual path after inspecting checks.
- Each reviewing tier requires one independent local review under the revised policy.
  Existing installations need the updated code and an explicit reviewer-order migration.
  Local review precedes any explicitly requested Copilot escalation.
- Copilot is a separate advisory PR reviewer, not a substitute automatically credited by the local review gate.
  The system repository currently prohibits requesting Copilot reviews.
- The `sd-review route` GitHub job reports routing; it does not perform a model review.
- Merge and installation are different outcomes.
  The pack's terminal version is `v0.72.0`; current delivery does not create new release tags.
  Use strict installation verification before claiming that merged source is active.
- Local branches and worktrees remain after delivery unless the user approves their removal.
  Routine closeout still inventories refs, branches, stashes, and worktrees after every confirmed in-scope merge.
  Preserve dirty, active, locked, unrelated, primary, and serving worktrees, unique work, and shared runtimes.
  Recovery evidence and a fresh identity check precede any approved deletion.

## Recommended improvements

These are recommendations, not implemented behavior.

| Priority | Change | Benefit |
|---|---|---|
| 1 | Migrate existing installations to the revised one-local-review policy and explicit-only alternatives. | Updated source defaults do not overwrite existing machine choices. |
| 2 | Make review dispatch and fallback policy visible across CLI, dashboard, and agent prompts. | Claude and Codex follow the same configured decisions. |
| 2 | Keep one full PR CI run; scope development checks and cancel superseded runs. | Preserve merge assurance while reducing repeated work. Measure before removing coverage. |

## Evidence

- [Workflow contract](../WORKFLOW.md)
- [Ship procedure and executable boundary](../skills/sd-ship/SKILL.md)
- [Review procedure](../skills/sd-review/SKILL.md)
- [Contribution and release policy](../CONTRIBUTING.md)
- [CI routing implementation](../.github/workflows/sd-review-route.yml)

Command forms were checked with their local `--help` output on 2026-09-18.
The settings check found STE-Concise in Claude's configuration and Codex's global instructions.
The pack's Claude override also selects STE-Concise; the system checkout inherits the global setting.
Configured instructions do not prove that every generated sentence follows the style.
