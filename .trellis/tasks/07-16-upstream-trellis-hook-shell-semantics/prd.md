# Park upstream Trellis lifecycle hook shell semantics

## Goal

Park the upstream-owned A-027 audit finding so it is not lost: Trellis task
lifecycle hooks execute repo-configured commands through `shell=True`. This is
not owned by `sd-ai-command-pack`; do not implement it in this repo or open a
Trellis pull request without explicit user consent for that upstream PR.

## Status

This is a parked task, not currently actionable backlog. It becomes actionable
only when the user explicitly approves upstream Trellis work, or when upstream
Trellis changes the hook contract and this pack needs to update docs,
compatibility expectations, or consumer guidance.

## Source Finding

Audit ledger item: `.trellis/audit/ledger.md` A-027.

- Severity: P3
- Dimension: security
- Confidence: plausible
- First seen: `2026-07-15 @ f6f3932`
- Last seen: `2026-07-16 @ 7d0172e`
- Ownership: upstream Trellis runtime, not pack payload

## Evidence

- `.trellis/scripts/common/task_utils.py:262-271` calls
  `subprocess.run(cmd, shell=True, ...)` for lifecycle hook commands.
- Hook commands come from `.trellis/config.yaml` hook lists parsed through
  `.trellis/scripts/common/config.py:275-292`.
- The affected runtime lives under `.trellis/scripts/**`, which Trellis owns and
  can overwrite during a future Trellis update.
- `sd-ai-command-pack` does not install or own these Trellis runtime files.

## Risk

A repository can place shell strings in Trellis lifecycle hook config. When a
developer runs a Trellis task command in that checkout, those strings execute
through the shell. This resembles the trust model of Git hooks or npm scripts:
expected for trusted repos, but risky if a repo's `.trellis/config.yaml` is
malicious or reviewed as plain configuration rather than executable behavior.

The risk is P3 rather than higher because it requires a developer to run Trellis
commands in a repository whose config they trust or have checked out. The
important gap is clarity and consent: users should know whether hook entries are
full shell scripts, whether first-use consent is expected, and whether Trellis
intends to support argv-list execution.

## Requirements

- R1: Do not modify `.trellis/scripts/**` in `sd-ai-command-pack` for this
  finding.
- R2: Do not open an upstream Trellis pull request without explicit user consent
  for that specific PR.
- R3: If upstream work is approved, decide the intended contract:
  documented full-shell trusted-repo semantics, first-use opt-in/consent, or
  argv-list execution instead of shell strings.
- R4: Preserve a paste-ready upstream handoff so a future Trellis session can
  pick this up without re-discovering the evidence.
- R5: If upstream Trellis later ships a hook-contract change, revisit pack docs
  or consumer guidance only if the pack has an actual compatibility surface to
  update.

## Acceptance Criteria

- [x] Finding is captured as a parked Trellis task.
- [x] Pack ownership boundary is explicit.
- [x] Evidence paths and risk rationale are recorded.
- [x] Paste-ready upstream handoff is recorded.
- [ ] User explicitly approves upstream Trellis work, or upstream Trellis ships
      a relevant hook-contract change.
- [ ] If activated, upstream Trellis behavior is verified before any pack-side
      cleanup or guidance change.

## Paste-Ready Upstream Handoff

```markdown
Task: clarify or harden Trellis lifecycle hook command execution.

Repo: mindfold-ai/Trellis

Finding from sd-ai-command-pack audit A-027:
Trellis task-command lifecycle hooks run config-sourced hook commands with
`subprocess.run(..., shell=True, ...)` in
`.trellis/scripts/common/task_utils.py`. Those commands are loaded from
`.trellis/config.yaml` hook lists via `.trellis/scripts/common/config.py`.

Please decide the intended contract:

- document full-shell semantics as trusted repo configuration, similar to Git
  hooks or npm scripts;
- add a first-use opt-in or warning gate for hook execution; or
- change hook config/execution to argv-list semantics where practical.

The generated consumer runtime is Trellis-owned. sd-ai-command-pack should not
patch `.trellis/scripts/**`, and no upstream Trellis PR should be opened without
explicit user consent.
```

## Non-Goals

- Patching consumer repos directly.
- Editing `.trellis/scripts/common/task_utils.py` or
  `.trellis/scripts/common/config.py` in this pack repo.
- Treating this as an `sd-ai-command-pack` release blocker.
- Opening a Trellis PR from this session without explicit user consent.

## Notes

- Parent task: `.trellis/tasks/07-16-audit-roadmap-cleanup`.
- Related open ledger item: A-027 remains open because the risk exists upstream
  and is not pack-owned.
- This task should remain `planning`/parked until activated by user consent or a
  released upstream Trellis change.
