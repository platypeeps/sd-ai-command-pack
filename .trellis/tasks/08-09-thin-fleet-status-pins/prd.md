# Fleet/status rework to pin + plugin inventory

Child of `08-09-deployment-thin-consumers`. Requirement 4 of the
parent PRD; architecture in parent `design.md` ("Fleet/status
rework").

## Deliverable

`consumers.json` schema bump (per-consumer `mode: fat|thin`, pin
source location) and `sd-status` machine/fleet inventory: plugin
version via `claude plugin list --json`, machine receipt version,
per-consumer pin, latest release — skew visible, tree diffing only
for remaining fat consumers.

## Requirements

1. Local mode adds machine-install inventory (plugin + receipt
   versions) with explicit unavailable labeling when sources are
   absent.
2. Fleet mode reports pin vs. machine vs. latest for thin consumers;
   fat consumers keep the existing tree-drift report until migrated.
3. Skew is a follow-up row (`F-*`), never silent; pin is an
   expectation record, not execution control (parent AC wording).
4. Schema bump follows existing consumers.json versioning
   conventions; status remains strictly read-only.

## Ordering constraints

- Can start after `thin-surface-partition`; needs
  `thin-machine-installer` receipt shape for final integration, and
  must ship before any consumer converts (`thin-migration` gate).

## Acceptance criteria

- [ ] `sd-status` on a machine with plugin + receipt installed
      reports both versions; absent sources reported unavailable, not
      empty-healthy.
- [ ] Fleet mode on a mixed fat/thin registry renders both report
      shapes; a stale thin pin produces an F-row.
- [ ] Schema bump documented; existing fat-only fleets parse
      unchanged.
