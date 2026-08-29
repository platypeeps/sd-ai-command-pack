---
title: Give the ship to work-loop handoff a validated receipt
status: done
created: 2026-07-28
---
# Give the ship to work-loop handoff a validated receipt

## Goal

Replace the free-text `SD_SHIP_MERGE_RESULT` block with a schema-versioned JSON receipt that the work loop parses and validates, so the one unattended boundary with no parser stops carrying outcome and counters through an LLM transcription step.

## Requirements

- `sd-ship` emits the merge result as a schema-v1 JSON receipt alongside the existing human-readable block (`.agents/skills/sd-ship/SKILL.md:202`), which becomes display-only.
- `scripts/sd-ai-command-pack-work-loop.py` gains `result --from-receipt` that parses and validates the receipt rather than accepting agent-typed values.
- The receipt must carry destinations for merge state, final head, review rounds, finish-work state, housekeeping state, and anomalies — `CURRENT_FIELD_ORDER` (work-loop.py:65) has no home for four of these today.
- `mergedPrs` (work-loop.py:2131) must be incremented from validated receipt state, not from the typed outcome string.
- The forced `phase = "complete"` at work-loop.py:2148 must go through `transition_state` (:1618) rather than bypassing it.
- Model the boundary on the existing peer contract: `--finish-work-receipt --json` with independent recompute (`.agents/skills/sd-housekeeping/SKILL.md:28`).

## Acceptance Criteria

- [ ] A receipt whose PR URL disagrees with the validated PR is rejected — today `tests/test_work_loop.py:3257` passes a different URL and it is accepted.
- [ ] A malformed or version-mismatched receipt fails closed with a named reason code.
- [ ] `make check` passes.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-061 (P1 · M · Verified · improvements).
- The only current code reference to `SD_SHIP_MERGE_RESULT` is a presence assertion (`tests/test_sdlc_commands.py:724`); the consuming instruction (`.agents/skills/sd-work-backlog/SKILL.md:274`) is prose with no command block and no `--json`.
- `record_result` (work-loop.py:2105) validates only enum membership and non-negative counts.
- Untracked before this task: `SD_SHIP_MERGE_RESULT` returns zero hits across the entire active task tree.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision.
- Complex task. Planning complete 2026-07-28: `design.md` and `implement.md` added.
