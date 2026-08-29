---
title: Machine-scope installer for non-Claude surfaces + unified update action
status: done
created: 2026-08-09
branch: feat/thin-machine-installer
---
# Machine-scope installer for non-Claude surfaces + unified update

Child of `08-09-deployment-thin-consumers`. Requirement 2 (remainder)
of the parent PRD; architecture in parent `design.md` ("Machine-scope
installer").

## Deliverable

`install.py --machine` writing user-level surface equivalents for
the `machine-other` partition slice plus rows flagged
`sharedRuntime: true` in the partition artifact
`docs/fleet/surface-partition.json` (schema version 1; contract
documented in `.trellis/spec/backend/manifest-and-filesystem.md`,
"Surface Partition Artifact") — shared scripts that non-Claude
surfaces invoke at runtime; the rest of the `machine-claude` slice
belongs exclusively to the plugin (`thin-plugin-packaging`).
Platforms whose `platforms.<id>` entry carries `provisional: true`
are not installable machine-scope until this child's verification
flips the flag; consumers of the artifact fail closed and treat them
as repo-native until then. Plus `sd-pack-update` as the single machine
update action — shipped under the pack's script naming convention as
`sd-ai-command-pack-pack-update.sh` in the plugin's `bin/`, which is the
command every criterion below names by its shorthand.

## Requirements

1. Per-platform verification FIRST: prove user-level surface
   resolution actually works for each candidate platform (Gemini,
   OpenCode, Codex/`.agents`); a platform that only reads repo-local
   files is re-dispositioned `repo-native` in the partition, not
   force-fitted.
2. Receipt file records pack version + payload digest; installer
   touches only receipt-owned paths; refuses unowned overwrites
   without an explicit force flag.
3. Self-containment: plugin bundles `installer/` package and the
   `machine-other` payload under the plugin root; no pack checkout
   required on the machine.
4. `sd-pack-update` executable sequence: `claude plugin update
   <plugin-name>@<marketplace-name>` (plugin argument required), then
   resolve the NEW plugin root via `claude plugin list --json` (never
   the running script's own location — roots change on update), then
   run the machine install from that resolved root; idempotent
   halves; partial failure surfaces as version skew in `sd-status`,
   rerun converges.

## Ordering constraints

- Requires `thin-surface-partition` (payload set) and
  `thin-plugin-packaging` (bundling + bin/ shipping).
- Blocks `thin-migration`.

## Acceptance criteria

- [x] Machine install into a scratch prefix produces receipt with
      correct version/digest; rerun is a no-op.
- [x] Unowned-file collision refused without force; diagnostic names
      the path.
- [x] Interrupted update (plugin updated, machine install failed)
      shows skew in `sd-status`; rerunning
      `sd-ai-command-pack-pack-update.sh` converges.
- [x] Per-platform disposition verdicts recorded in task research and
      reflected in the partition output.

## References

Research notes that lived beside this item's Trellis record and were not carried
into docs/work. Recover the bodies from git history under `.trellis/tasks/archive/2026-08/08-09-thin-machine-installer`:

- research/adversarial-review-ledger.md
- research/platform-probes.md
- research/platform-verification.md
