# Analyze recurring Trellis workflow instability

## Goal

Review recent Trellis-backed sessions across repositories, identify recurring status and journaling recovery failures, determine root causes and fixes, and map findings to existing sd-ai-command-pack tasks.

## Requirements

- Review the 2026-07-14 through 2026-07-28 session inventory for every
  indexed checkout whose resolved repository root contains `.trellis/`.
- Separate workflow defects from expected fail-closed gates, stale installed
  pack versions, sandbox/filesystem restrictions, and ordinary GitHub review
  settlement.
- Identify repeated lifecycle and journaling failure classes with concrete
  repository, session, PR, reason-code, or task evidence.
- Verify which mitigations are already shipped in the current command pack
  and which remain only as planned Trellis tasks.
- Map every recommended fix to one existing task when ownership is already
  clear; identify uncovered gaps without creating duplicate tasks.
- Keep the review read-only outside this task directory and do not modify
  consumer repositories or upstream Trellis.

## Acceptance Criteria

- [x] Recent indexed sessions are inventoried across every physical Trellis
      repository, with aliases deduplicated and coverage limits disclosed.
- [x] Recurring failures are grouped by root cause rather than counted from
      repeated transcript text.
- [x] Shipped mitigations are verified against current source and focused
      tests.
- [x] Consumer pack and Trellis versions are compared to identify rollout
      skew.
- [x] Remaining work is mapped to active tasks and uncovered gaps are called
      out explicitly.
- [x] A durable research report records evidence, conclusions, and the
      recommended implementation order.

## Post-Completion Audit Residue — 2026-07-28

This task's acceptance criteria above are all satisfied and the remediation work
carried by its accepted child tasks merged in v0.56.0. Its own record is **not**
closed: `task.json` still reads `"status": "planning"` with `"completedAt": null`,
and `handoff.md:5-8` states that no implementation task was started here. Closing
that lifecycle gap is a separate housekeeping decision and is not done by this
section.

The 2026-07-28 repo audit (`.trellis/audit/report-2026-07-28.md`) named this task
as the nominal owner of three findings that the delivered work does not cover.
They are recorded here as residue, not as reopened scope — none is a regression
of what this task delivered — and recording them is **not** the same as assigning
them. All three were dispositioned on 2026-07-28; see each entry.

- **A-069** (P2 · S · Plausible · security) — the environment-blocked diagnostic
  redactor misses most common secret shapes. `sd_ai_command_pack_lib.py:497`
  `_ENVIRONMENT_SECRET_RE` covers only bearer, token, and `gh[pousr]_`, while
  `sd-ai-command-pack-fleet-timing.py:28` already covers `github_pat_`,
  `xox[baprs]-`, `sk-`, PEM, and key-value forms. The weak redactor feeds every
  environment-blocked fragment (`work-loop.py:160`) into agent-visible reports
  (`docs/SD_AI_COMMAND_PACK.md:1154`), and `tests/test_script_lib.py:670` asserts
  only the three shapes already caught. A fine-grained PAT passes through
  verbatim. Confirmed exposure is the `--json` housekeeping result's
  `environmentBlocks` array, the `outcome: blocked` fragments printed by
  `work-loop.py:2844`, `update-spec-kb.py:1542`, and `record-session.py:292`,
  and whatever agent or log consumes them; a repo-wide search found **no**
  GitHub/PR publication path for these fragments, so do not claim PR visibility
  without one. Work package B required bounded diagnostic text, not redactor
  consolidation, so this was never in scope here. Disposition (2026-07-28):
  **owned by `07-28-consolidate-secret-redactors`** R1-R4. Note the fix as
  originally written is half right — the two sites cannot share a *redactor*,
  only a *pattern set*: `sd_ai_command_pack_lib.py:519` substitutes `[redacted]`
  while `sd-ai-command-pack-fleet-timing.py:172` raises `FleetTimingError`, and
  neither policy is safe at the other's call site.
- **A-077** (P2 · M · Plausible · design) — `outcome` and `status` mean
  structurally different things across sibling scripts. Note the premise limit:
  these are *distinct* payloads that embed or sit beside one another, not one
  payload assembled from four producers, so the fix is envelope/key
  standardization plus a compatibility plan, not a forced merge of four domain
  vocabularies into one enum. The divergence itself is real:
  `housekeeping-result.py:358` uses `status` for a whole sd-status document
  beside `outcome`, while `classify_outcome()` at `:258` returns
  `{"status": enum, …}`; `work-loop.py:2844` emits a bare-string outcome;
  `pr-eligibility.py:1257` reads the enum out of `result["status"]`; and
  `review-local.py:58` carries a six-value vocabulary disagreeing with
  housekeeping's four. Work package A fixed housekeeping only and its remediation
  child is archived. Disposition (2026-07-28): **owned by
  `07-28-unify-outcome-status-vocabulary`**, whose R6 makes the consumer
  inventory a blocking prerequisite. That task rejects the audit's candidate fix
  — a top-level `outcome: {status, reasonCodes}` reproduces the collision, since
  it nests an enum named `status` while `status` also names the embedded
  document — and counts five verdict vocabularies rather than two.
- **A-099** (P3 · M · Plausible · bloat) — **contradicts this task's own
  design and needs a decision, not an implementation.** The audit finds the
  `environment_blocked` evidence schema has no machine consumer: the composer,
  validator, and tables span ~226 of the lib's 705 lines
  (`sd_ai_command_pack_lib.py:444`), the only reader of the discriminating fields
  is the lib's own validator (`:618`), `validate_environment_blocked_evidence`
  (`:606`) has no caller outside tests, `cache_setup_blocked_evidence` (`:641`)
  is reachable only via `--json`, the production caller uses plain mode and
  discards stderr (`toolchain.sh:417`), and `retryable`/`mutationState` semantics
  are decided in prose
  (`.agents/skills/sd-help/references/environment-blocked-recovery.md:19`).
  But this task's work package B deliberately mandates those five fields and
  states that skills interpret the structured blocker — agent-prose
  interpretation is the design, not an oversight. So "remove the fields you just
  added" cannot be a requirement on this task. The open question is whether the
  schema's intended consumer is an agent (in which case A-099 is rebutted and the
  ledger entry should say so) or a program (in which case one programmatic
  consumer honoring `retryable` and `mutationState` is owed). That is a product
  decision for the pack owner.
  Decided 2026-07-28: **the intended consumer is an agent, so A-099 is rebutted**
  and the ledger records it as such. The residual is narrower and real —
  `sd_ai_command_pack_lib.py:606` has no non-test caller and the
  `sd_ai_command_pack_lib.py:641` `--json` path is unreachable because
  `toolchain.sh:417-418` passes no `--json` and discards stderr — and is owned by
  `07-28-consolidate-secret-redactors` R5, which wires the flag through rather
  than deleting the validator.

No acceptance criteria are added above: this task's stated criteria are met and
silently reopening it would misrepresent that. As of 2026-07-28 all three items
are dispositioned elsewhere: A-069 and the A-099 residual to
`07-28-consolidate-secret-redactors`, A-077 to
`07-28-unify-outcome-status-vocabulary`, and A-099's headline claim rebutted in
the ledger. No `tracked (needs owner)` or `tracked (needs decision)` entry
remains. This task stays as it is — the residue record above is history, not a
work queue.

## Post-Completion Residue — 2026-07-29

Recorded on the same terms as the 2026-07-28 section above: history, not a work
queue. No acceptance criteria are added and this task is not reopened.

Both PRs merged on 2026-07-29 — #273 (`5fc11c2f`) and #274 (`16b6ebe2`) — were
merged by hand because `sd-finish-work` could produce no receipt, so
`sd-housekeeping` never reached its merge gate. In both cases the failure was in
the finalization validator, not in the change under review: #273 was green with
zero unresolved review threads, and #274 was green with a clean Copilot round on
its exact head.

- **Whole-directory validation.** `final-bundle --mode planning` on #273 returned
  27 findings, of which **25 were in files the PR never modified** — 20
  `task_context_seed` (`_example` scaffold rows) and 5 `task_metadata_invalid`
  (empty `task.json` descriptions). `validatePlanningBundle`
  (`scripts/sd-ai-command-pack-review-preflight.mjs:1505`) derives task
  directories from the delta at `:1513-1517` but then validates each directory's
  entire current content at `:1532-1535`. Editing one `prd.md` inherits every
  stale artifact its neighbours accumulated.
- **No mode for a repo-maintenance branch.** `:523` admits only `completion` and
  `planning`. #274 changed skills, scripts, and the release payload, archiving no
  task and touching no active task artifact, so it satisfied neither: `completion`
  gave `completion_archive_move_missing` (`:1462`) and `planning` gave
  `planning_recovery_commit_scope_invalid`.

Disposition (2026-07-29): both are **owned by
`07-29-scope-final-bundle-validator-to-delta`**, created for them. That task
records the mode question as an open design decision rather than presuming a
fix, and explicitly keeps `bundle_scope_invalid` blocking.

The third failure on #273 needs no owner. Its 2 `bundle_scope_invalid` findings
were correct — commit `0ff58e88` mixed `.trellis/audit/ledger.md` and
`report-2026-07-28.md` into a delta of 152 task files. The v0.56.1 `sd-audit-repo`
contract already prevents recurrence; it cannot repair an already-published
commit, which is why #273 could not be finalized after the fact.

## Notes

- Findings: `research/recent-trellis-workflow-instability.md`.
- New-session handoff and finding-to-task ownership map: `handoff.md`.
- Accepted remediation tasks:
  - `07-28-stabilize-self-hosted-delivery-lifecycle`
  - `07-28-route-housekeeping-by-pr-lifecycle-state`
  - `07-28-standardize-environment-blocked-recovery-evidence`
  - `07-28-roll-out-stabilized-pack-release-to-fleet`
- Accepted upstream Trellis planning tasks:
  - `07-28-harden-add-session-retry-convergence`
  - `07-28-restore-install-safe-opencode-mem-reader`
- OpenCode session storage is not indexable by Trellis 0.6.7; the report does
  not claim OpenCode coverage. Upstream restoration is now tracked by the
  second task above.
