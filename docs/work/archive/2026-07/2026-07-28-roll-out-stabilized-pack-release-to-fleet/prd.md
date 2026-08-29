---
title: Roll out the stabilized command-pack release to the fleet
status: done
created: 2026-07-28
---
# Roll out the stabilized command-pack release to the fleet

## Goal

After the investigation's required pack-owned stability fixes pass integration
validation and ship in a successor release, refresh every eligible fleet
consumer through the source-owned campaign controller.

The rollout is a deployment step, not a diagnostic prerequisite. Version skew
at the 0.55.5 baseline is accepted temporarily so known-broken lifecycle
behavior is not distributed before its fixes are available.

## Requirements

- Do not start this task against 0.55.5. The target must be a later verified
  release containing the required fixes listed below.
- Treat `docs/FLEET_ROLLOUT.md`, `docs/fleet/consumers.json`, and the eventual
  successor release identity as the rollout authorities.
- Run source-owned fleet status and preflight before any consumer mutation.
- Before release preparation, complete and merge
  `07-28-stabilize-self-hosted-delivery-lifecycle`. Its single PR must satisfy
  and archive all eleven pack-owned work-package tasks from findings F1, F3,
  F4, and F5 and pass the bounded cumulative self-hosting matrix.
- Do not block this stabilization release on the broader
  `07-22-validate-sd-workflow-program-integration` backlog. Feed the umbrella
  matrix into that task for later program closure.
- Upstream Trellis tasks and upstream publication are not release blockers.
  Prefer pack-local compensation or local Trellis-checkout handling. Treat an
  upstream change as absolutely required only when final integration proves no
  safe local mitigation can satisfy the release invariants.
- Scope the campaign to every manifest consumer below the successor version at
  execution time. Do not freeze the worklist to the seven consumers that were
  below 0.55.5 during diagnosis.
- Treat `anomaly-metric-creator` as no-touch while its unrelated active task or
  any uncommitted work remains; include it only after it becomes clean and the
  controller declares its lane eligible.
- Use the source-owned campaign controller and manifest cohort policy. Do not
  reconstruct rollout state from conversation history or bypass a controller
  stop condition.
- For each eligible consumer, use its dedicated Trellis task and the normal
  install, audit, preparation, full-check, review, exact-head merge, cleanup,
  and post-merge provenance gates.
- Never mutate a dirty consumer, product code, repo-owned policy, or upstream
  Trellis to make the refresh pass. Record and preserve blockers instead.
- If the pack itself blocks an otherwise clean integration, stop the campaign,
  create a pack-owned corrective task/release, and resume through the
  controller's documented corrective-release path.
- Do not assume the candidate-validation gate binds the whole payload digest.
  `07-28-split-payload-behavior-digest` (audit finding A-057) splits
  `payload_digest` into a behavior digest and an informational content digest and
  makes `validate_candidate_ledger` gate on behavior only. This rollout consumes
  the candidate ledger as a precondition, so read the digest semantics in force
  at execution time rather than the current whole-payload ones. That split is not
  a release blocker for this campaign, and until it ships the current gate stands
  unchanged: `scripts/sd_ai_command_pack_fleet_lib.py:728` `validate_candidate_ledger`
  rejects **any** `payloadDigest` mismatch, including a documentation-only
  restamp. Do not treat a restamped ledger as still-valid evidence on the theory
  that the change was informational — revalidate against the current whole-payload
  digest. Once A-057 ships, read the digest semantics then in force instead.

## Acceptance Criteria

- [ ] The single-merge stabilization task and all eleven work packages are
      completed and archived, and its cumulative matrix passes before
      successor release preparation.
- [ ] No upstream dependency is introduced without exact final-integration
      evidence that the successor release cannot be made safe locally.
- [ ] The successor release identity, candidate ledger, manifest, and selected
      consumer base commits pass source preflight before rollout.
- [ ] Every manifest consumer below the successor release has a terminal
      controller result:
      `at-target`, `refreshed+merged`, `PR-open`, or `blocked+<reason>`.
- [ ] Every refreshed consumer passes expected-platform audit, repo-owned
      preparation, and its documented validation before publication.
- [ ] Every merged refresh is green, review-clean, exact-head verified, and
      merged through the consumer's installed housekeeping gate.
- [ ] Post-merge provenance and install audit report the successor version for
      every merged consumer, and each touched checkout ends clean on its
      synchronized default branch.
- [ ] `anomaly-metric-creator` receives no mutation while unrelated work is
      active; its eventual terminal result is recorded explicitly.
- [ ] Final fleet status contains no unexplained version skew or untracked
      rollout follow-up.
- [ ] The campaign state, consumer PR URLs, exact heads, checks, review result,
      merge state, and any blockers are recorded as durable task evidence.

## Notes

- Created from finding F6 in
  `07-28-analyze-recurring-trellis-workflow-instability` so version-skew
  remediation has one explicit owner after framework stabilization.
- Decision updated 2026-07-28: do not distribute 0.55.5 merely to normalize
  diagnostics. Fix, integrate, release, then roll out once.
- Upstream Trellis work remains an independent local concern unless it becomes
  an evidence-backed absolute release requirement.
- This is operational rollout work, not authorization to change consumer
  product code or publish an upstream Trellis change.
- 2026-07-28 audit: this task was tracked-stale against finding A-057
  (P2 · M · Plausible · consumer-impact) because it consumes the candidate
  ledger as a precondition without splitting the digest. A-057 now has a
  dedicated owner, `07-28-split-payload-behavior-digest`, so this task carries a
  cross-reference and a semantics caveat rather than duplicated scope. Source:
  `.trellis/audit/report-2026-07-28.md`.
