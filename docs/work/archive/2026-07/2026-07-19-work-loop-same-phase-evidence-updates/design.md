# Support Same-Phase Work-Loop Evidence Updates Design

## Overview

The work-loop phase machine and its evidence ledger serve different purposes.
Phases prevent lifecycle steps from being skipped, while evidence records facts
that legitimately change inside one phase, such as a new commit or published
pull request. The current helper conflates those concerns by accepting evidence
only as part of a phase transition and treating any later observation as a
contradiction.

Add a dedicated `evidence` command that atomically validates and records
same-phase evidence without advancing the lifecycle. Make verified
reconciliation use the same update rules. Keep ordinary reconciliation
read-only and fail closed when observations disagree with the ledger.

## Proposal

Split current-state fields into two contracts:

- Stable identity: `task` and `baseBranch` may be initialized but cannot be
  replaced during an iteration.
- Advancing evidence: `branch`, `head`, `prNumber`, `prUrl`, and
  `lastShippedSha` may move only through field-specific validation.

The `evidence` command accepts the existing current-field flags and requires at
least one value. It applies all requested changes to a copy, validates every
change, then commits the copy through the existing atomic ledger writer. This
prevents a valid early field from being persisted when a later field fails.

Branch changes are allowed only at the verified merge boundary: from the
recorded feature branch to `baseBranch` while the phase is `shipping` or
`followups`. HEAD changes must be Git descendants of the remembered HEAD. A PR
number cannot change after it is set; a PR URL cannot conflict with an existing
URL and, when both are present, its final numeric path component must match the
PR number. `lastShippedSha` must name the current or an ancestor commit of the
recorded HEAD.

`reconcile --verified-live-advance` applies the same evidence validator before
performing a verified later-phase advance. Without that flag, mismatches remain
red contradictions. Successful exact reconciliation or a verified evidence
advance clears obsolete `ready` or `blocked` checkpoints and restores green
health; a verified phase advance remains amber until a subsequent exact
reconciliation.

## Boundaries And Non-Goals

- Do not allow `transition` to target its current phase.
- Do not infer commits, PRs, branches, or phase changes from the network.
- Do not weaken red handling for task changes, branch changes outside the merge
  boundary, non-descendant commits, conflicting PRs, or phase regressions.
- Do not change schema version 1; the existing state shape already contains all
  required fields.
- Do not modify upstream Trellis runtime files.

## Affected Files

- `templates/scripts/sd-ai-command-pack-work-loop.py` and root mirror.
- `templates/.agents/skills/sd-work-backlog/SKILL.md` and root mirror.
- `tests/test_work_loop.py` plus generated-contract assertions as needed.
- `README.md`, `docs/SD_AI_COMMAND_PACK.md`, and
  `.trellis/spec/frontend/adapter-guidelines.md`.
- Release metadata and installed provenance because the shipped helper changes.

## Data And Command Contracts

```text
sd-ai-command-pack-work-loop.py evidence --repo . --run-id <id> \
  [--task <id>] [--branch <name>] [--head <sha>] \
  [--base-branch <name>] [--pr-number <n>] [--pr-url <url>] \
  [--last-shipped-sha <sha>] [--json]
```

The operation returns the normal state snapshot. Unknown fields are impossible
through the CLI and rejected by the internal function. No supplied fields is a
usage error. Every state mutation continues through `mutate_state()` and its
private atomic write.

## Risks And Edge Cases

- Git ancestry can be unknown when a commit is not available locally. Explicit
  evidence updates fail closed in that case instead of guessing.
- A merge commit may not descend from the final feature commit after squash
  merge. The branch transition to the default branch therefore validates the
  feature tip against `lastShippedSha`, while the new default-branch HEAD is
  validated as a commit that exists locally rather than as its descendant.
- Old schema-version-1 ledgers may contain no current evidence; initialization
  remains allowed and requires no migration.
- Recovery must not silently erase stopped, paused, or completed checkpoint
  intent. Only obsolete `ready` and contradiction-created `blocked` states are
  cleared by a successful active reconciliation.

## Validation

- Unit tests for commit, PR publication, review-fix, finish-work, and merge
  updates; invalid identity/branch/PR/ancestry/field cases; old ledgers; atomic
  mutation failure; checkpoint clearing; and CLI resume behavior.
- Root/template byte parity and installed provenance checks.
- Repository canonical `make check` and full-check with explicit local-review
  providers disabled.
