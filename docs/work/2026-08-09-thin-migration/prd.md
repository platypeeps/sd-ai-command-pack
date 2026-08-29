---
title: Thin-mode migration, consumer CI cleanup, gate retirement
status: planning
created: 2026-08-09
---
# Thin-mode migration, consumer CI cleanup, gate retirement

Child of `08-09-deployment-thin-consumers`. Requirements 3, 5, 6 of
the parent PRD; architecture in parent `design.md` ("Migration").

## Deliverable

Thin install mode coexisting with fat, per-consumer conversion in
cohort order, one-command revert, consumer CI/sync cleanup, and
vendoring-gate retirement after the last conversion.

## Requirements

1. Conversion gate per consumer: exact-HEAD resweep (workflows, git
   hooks, Make targets, docs) for pack references before deletion —
   the 2026-08-09 fleet sweep is a dated snapshot, not a migration
   authority.
2. Conversion PR deletes: vendored payload (minus `repo-native` +
   `consumer-config` slices, enumerated from the partition artifact
   `docs/fleet/surface-partition.json` — schema version 1, contract
   documented in `.trellis/spec/backend/manifest-and-filesystem.md`,
   "Surface Partition Artifact"; platforms whose `platforms.<id>`
   entry carries `provisional: true` are treated as repo-native,
   fail closed, until verified), all
   pack CI steps (syntax lints and the
   anomaly-metric-creator advisory `pr-body-scope.py` call — parent
   D2), and consumer-side sync automation
   (`sd-ai-command-pack-sync.yml` in anomaly-metric-creator, which
   would otherwise recreate the vendored state). Adds:
   `.claude/settings.json` marketplace/enable entries, pin receipt,
   `mode: thin` registry flip.
3. Revert (`install.py TARGET --revert-thin`, one command): restores
   fat payload, removes thin artifacts it added, flips mode back,
   writes per-repo `enabledPlugins` disable to prevent duplicate
   surfaces.
4. Candidate loop rescoped, not dropped: release-prep validates the
   thin shape (plugin build + `--strict` validate + `--plugin-dir`
   load smoke + machine install to scratch prefix) against disposable
   consumer checkouts before any machine-wide update.
5. Gates retire only after the final consumer converts: consumer
   mirror byte-identity, shipped-surface closure over consumers,
   fat-candidate choreography. Pack-internal template/root mirror
   gates stay. Spec/doc updates found by enumeration (grep of
   install/fleet spec surfaces), not memory.
6. Cohort order respected: canary (rwbp-coordinator, loadsmith,
   hoa-manager) before post-canary before final
   (anomaly-metric-creator last).

## Ordering constraints

- Last child. Requires `thin-surface-partition`,
  `thin-plugin-packaging`, `thin-machine-installer`, and
  `thin-fleet-status-pins` all shipped before the first consumer
  converts. Verified 2026-08-10: all four are archived `completed`, so
  this constraint is satisfied.

## Decomposition

This task is a parent. The requirements above are delivered by six
ordered children (see `design.md` for the contracts and `implement.md`
for the gate between them):

1. `08-10-thin-conversion-tooling` — pack-internal
2. `08-10-thin-candidate-loop-rescope` — pack-internal. **Narrowed
   2026-08-11** to contract C-F's reachability half only: binding a
   validator digest into the candidate ledger so `make release-prep` stops
   skipping a changed validator. Its title now reads "Make release-prep
   reach a changed candidate validator"; the directory slug predates the
   split and `task.py` has no rename.
2b. `08-10-thin-prompt-surface-repoint` — pack-internal, added
   2026-08-10 after child 1's step-3 measurement. Seven pack-shipped
   surfaces survive conversion and still cite paths it removes — four
   prompts telling agents to run removed scripts, the managed block in
   `.github/copilot-instructions.md`, the force-preserved
   `.github/PULL_REQUEST_TEMPLATE.md`, and the surviving `obsidian-kb`
   block in `.gitignore`: 16 hits in 7 files, or 14 in 6 for the three
   consumers that have taken the PR template over and own its stale
   citations themselves. The resweep reports these as `packDefects`,
   which blocks `--thin`, so this child gates children 3–5 on the **pack**
   side and must land before any real conversion.
2c. `08-11-thin-undeclared-codex-marker` — pack-internal, added
   2026-08-11. A second, different pack-side blocker found while
   measuring 2b's baseline: the pack ships
   `.claude/sd-ai-command-pack/planning-adversarial-review.md`, which
   invokes the `codex` CLI, and no consumer declares `codex` as a
   platform. The resweep reports one `undeclared codex usage`
   `packDefect` for all eight consumers. It is not a path citation, so
   2b's rewrite cannot reach it and the two are independent — but both
   must reach zero before any consumer converts, so this child gates
   children 3–5 alongside 2b.
2d. `08-11-thin-candidate-loop-shape` — pack-internal, split out of child 2
   on 2026-08-11 after three planning-review rounds found four blocking
   concerns against the thin-shape half: the conversion mutates this
   repository's own fleet registry, the clean-tree precondition defeats the
   install-then-resweep ordering, already-thin checkouts reject
   `--platform`, and a `blocked` consumer has no representation in the
   current ledger contract. Carries the release-gate policy question.
   Ordered after child 2 for observability — until the digest binding lands,
   an edited validator is not reached by release-prep at all.
3. `08-10-thin-canary-conversion` — mutates consumer repositories
4. `08-10-thin-post-canary-conversion` — mutates consumer repositories
5. `08-10-thin-final-conversion-gate-retirement` — mutates a consumer
   repository, then retires gates
6. `08-16-thin-migration-record-closure` — records only. Added 2026-08-16,
   after the conversion finished, to close this task's own acceptance
   criteria against the evidence that settles them and to clear a stale
   blocker header on the grandparent. It mutates no repository and no
   consumer; it is a child rather than an edit-in-place because it edits
   two active tasks' artifacts and therefore needs its own finalization
   scope.

Children 3–5 are blocked on explicit per-cohort user authorization,
because they change repositories outside this one. That work is also
**larger than "run the converter"**: measured 2026-08-10, every one of
the 8 registered consumers has consumer-authored callers, in command
position, of paths the conversion removes (14 hits in 10 files at the low
end, 205 in 21 at the high end), so each consumer needs its execution
surface repointed before it can convert. Evidence and per-consumer figures:
`08-10-thin-conversion-tooling/research/fleet-blocker-scan.json`.

## Acceptance criteria

- [ ] First canary consumer converted: CI green with zero pack CI
      steps and no vendored payload beyond `repo-native` +
      `consumer-config` slices.
- [ ] Revert executed on a converted consumer restores fat mode, CI
      stays green, no thin artifacts remain except the intentional
      per-repo `enabledPlugins` disable marker the revert writes
      (requirement 3).
- [ ] anomaly-metric-creator conversion removes both the advisory CI
      call and `sd-ai-command-pack-sync.yml`.
- [ ] After final conversion: retired gates removed/rescoped; grep of
      spec surfaces finds zero descriptions of consumer vendoring as
      current behavior.
- [ ] Rescoped candidate loop runs in release-prep and blocks on
      failure.
