# Work-loop ledger cannot record a superseded PR replacement

> Consolidated scope (2026-08-14): issue #404 relays two further work-loop
> terminal-evidence gaps from `platypeeps/se-ai-command-pack` with observed
> runs and a working two-call workaround: (1) one-shot merge-boundary
> evidence fails after housekeeping deletes the merged branch — accept the
> boundary via the merge commit's second parent instead of the deleted ref,
> and let a green reconciliation clear earlier red reasons; (2) no sanctioned
> pre-mutation skip from `selected` — add `selected -> inventory` guarded by
> "no branch/head/PR evidence recorded". Same component, same ledger, same
> test harness: fix together with the superseded-PR gap below.
>
> Closure note (2026-08-14): #404 was closed as `not planned` when tracking
> moved to the Trellis task tree. The defect is unchanged and this task still
> owns it, so closing it is no longer part of shipping. Reference it as a
> bare `#404` in the shipping PR — never with a closing keyword, per
> `08-14-pack-paper-cuts` item 4.

## Goal

Let an active work-loop iteration record that its PR was closed as
superseded and replaced by a new PR for the same task, so the final
`result --from-receipt` path can accept the replacement instead of
rejecting it with `ship_receipt_pr_mismatch`.

## Context

During run 2158bfa4bda649e7b31c52ac25cb1d9f (task
08-09-thin-plugin-packaging), PR #400 became permanently unmergeable
(ruleset-required `update-branch` merge commit fails the finish-work
successor linearity rule) and was closed in favor of linear rebuild
PR #402. The ledger's `evidence` subcommand refuses
`cannot replace recorded pull request number`
(`sd-ai-command-pack-work-loop.py:1881`), and `result --from-receipt`
then fails `ship_receipt_pr_mismatch`, forcing the documented
`--outcome blocked` fallback even though the replacement PR merged
clean. The immutability guard is right for accidental drift but has no
deliberate supersession path.

## Requirements

- A typed, deliberate supersession operation (for example
  `evidence --supersede-pr <new> --supersede-reason <text>`) that
  records old and new PR number/URL, keeps the old pair in history, and
  requires the old PR to be verifiably CLOSED (not merged) on GitHub.
- `result --from-receipt` accepts a receipt naming the recorded
  replacement PR; accidental mismatches still fail
  `ship_receipt_pr_mismatch`.
- Status/report output shows the supersession chain.
- Fail closed: supersession with an open or merged old PR, or a
  replacement PR whose head is not for the recorded task branch's
  content, is rejected.

## Acceptance Criteria

- [ ] Ledger test covers supersede-then-result happy path and rejects
      supersession when the old PR is still open.
- [ ] `ship_receipt_pr_mismatch` still fires for receipts naming a PR
      that was never recorded via supersession.
- [ ] sd-work-backlog / sd-ship docs mention the supersession path where
      the nested-return contract discusses receipt rejection.
