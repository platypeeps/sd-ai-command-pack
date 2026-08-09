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
  converts.

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
