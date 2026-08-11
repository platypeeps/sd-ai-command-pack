# Fleet/status rework to pin + plugin inventory

Child of `08-09-deployment-thin-consumers`. Requirement 4 of the
parent PRD; architecture in parent `design.md` ("Fleet/status
rework").

## Deliverable

`consumers.json` schema bump (per-consumer `mode: fat|thin`, pin
source location) and `sd-status` machine/fleet inventory: plugin
version via `claude plugin list --json`, machine receipt version,
per-consumer pin, and the target pack version — skew visible, tree
diffing only for remaining fat consumers.

Terminology corrected 2026-08-10: "latest release" above originally
implied a published-release lookup. The fleet target is the resolved
pack checkout's `manifest.json` version
(`sd_ai_command_pack_fleet_lib.py:192-200` (`_pack_identity` returns `manifest_version`) and `:251, 268, 284` (`target_version=version`)); no release API
call exists and status stays read-only, so comparing against the
newest published release is a recorded follow-up, not this task.

## Requirements

1. Local mode adds machine-install inventory (plugin + receipt
   versions) with explicit unavailable labeling when sources are
   absent.
2. Fleet mode reports pin vs. machine vs. target pack version for thin
   consumers (corrected 2026-08-10, was "latest"); fat consumers keep
   the existing tree-drift report until migrated. Fleet-level machine
   rows appear only when the registry contains at least one thin
   consumer, so today's all-fat registry reports exactly as it does now.
3. Skew is a follow-up row (`F-*`), never silent; pin is an
   expectation record, not execution control (parent AC wording).
4. Schema bump follows existing consumers.json versioning
   conventions; status remains strictly read-only.

## Ordering constraints

- Can start after `thin-surface-partition`; needs
  `thin-machine-installer` receipt shape for final integration, and
  must ship before any consumer converts (`thin-migration` gate).

## Planning note (2026-08-10)

Requirement 1 landed with `08-09-thin-machine-installer`: `sd-status` local
mode already returns a `machineScope` block with the plugin version, the
machine receipt state, and explicit `unavailable` labeling (verified on this
checkout — `pluginVersion: "unavailable"` with an explanatory detail string,
not an empty-healthy result). This task therefore owns a regression test for
requirement 1, not a reimplementation; the code work is requirements 2–4.

## Acceptance criteria

- [x] `sd-status` on a machine with plugin + receipt installed
      reports both versions; absent sources reported unavailable, not
      empty-healthy.
- [x] Fleet mode on a mixed fat/thin registry renders both report
      shapes; a stale thin pin produces an F-row.
- [x] Schema bump documented; a schema-5 registry carrying no `mode` on
      any consumer behaves exactly like the schema-4 registry it
      replaces (corrected 2026-08-10:
      `_parse_fleet_consumers_without_policy` demands exact version
      equality, so a *schema-4* file is rejected after the bump by
      design, as it was for 3 → 4. The invariant is default-behavior
      preservation, not cross-version parsing).
- [x] The candidate ledger is regenerated: `docs/fleet/candidate-validation.json`
      pins `fleetManifestDigest`, which the registry edit changes and
      `make check` validates by equality.
- [x] Skew rows survive `HUMAN_ITEM_LIMIT` truncation: follow-ups are
      derived from the complete row set, not the truncated human list.
- [x] Plugin-vs-receipt divergence produces its own follow-up row
      (`.trellis/tasks/08-09-deployment-thin-consumers/design.md:116-119`
      names it as reportable skew).
- [x] Shipped payload obligations met: `manifest.json` version bump plus a
      matching top `CHANGELOG.md` heading (`CONTRIBUTING.md:136`), and the
      `sd-status` skill / pack-guide fleet contract updated for the thin
      report shape.
