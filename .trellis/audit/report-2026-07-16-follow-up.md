# Repo Audit — sd-ai-command-pack @ 772bf2a — 2026-07-16
Mode: follow-up · Depth: standard · Dimensions: open-ledger verification, touched-area regression sweep

## Verdict

The follow-up audit found one still-open item and no new, fixed, or regressed findings. A-027 remains a valid P3 upstream Trellis-owned security/documentation concern: lifecycle hook commands are still loaded from repo config and executed through `shell=True`. The finding is tracked by a parked Trellis planning task, and its archived parent-task reference has been corrected.

Counts: P0 0 · P1 0 · P2 0 · P3 1 still-open.

## Findings

#### [A-027] P3 · S · Plausible — Trellis lifecycle hooks execute config-sourced commands via shell=True (upstream-owned)
- evidence:
  - `.trellis/scripts/common/task_utils.py:262` — lifecycle hooks still call `subprocess.run(...)`.
  - `.trellis/scripts/common/task_utils.py:264` — hook execution still passes `shell=True`.
  - `.trellis/scripts/common/config.py:275` — hook commands still come from `get_hooks(...)`.
  - `.trellis/scripts/common/config.py:290` — hook config still accepts a list and coerces entries to strings.
- why: A repo can ship executable shell strings in Trellis hook config; this matches trusted-repo hook/script semantics, but the contract belongs upstream and should be explicit.
- fix: Upstream Trellis should decide whether to document full-shell trusted config, add first-use consent, or move to argv-list hook execution.

## Trellis reconciliation

- tracked-accurate:
  - A-027 is tracked by `.trellis/tasks/07-16-upstream-trellis-hook-shell-semantics/prd.md`.
  - The task is correctly parked in `planning`, names the upstream ownership boundary, includes a paste-ready handoff, and points at the archived parent task.
- tracked-stale:
  - none.
- untracked:
  - none.
- task proposals awaiting user consent:
  - none.

## Prioritized actions

1. Keep A-027 parked until the user explicitly approves upstream Trellis work or upstream Trellis ships a hook-contract change.
2. If upstream work is approved, use the paste-ready handoff in `.trellis/tasks/07-16-upstream-trellis-hook-shell-semantics/prd.md`.
3. Do not patch `.trellis/scripts/**` in this pack for A-027; those files are Trellis-owned generated runtime.

## Ledger delta

- new: 0
- still-open: 1
- fixed: 0
- regressed: 0

## Coverage & limits

- Full charter sweep skipped because this was `follow-up` mode.
- Sub-agent reviewer/refuter dispatch skipped because this session is inline-only.
- Verification scope:
  - Rechecked every open/regressed ledger item; only A-027 was open.
  - Ran a quick touched-area sweep from `7d0172e..772bf2a`.
  - Confirmed prior PR #131 CI was green and the current working tree was clean before ledger/report edits.
- Regression sweep result:
  - No new P0-P2 findings.
  - No new P3 findings worth adding to the ledger.
- Validation note:
  - `git diff --check` passed.
  - Follow-up cleanup corrected the stale archived parent-task reference in the A-027 PRD and task metadata.
- Refuted-finding log:
  - none.
