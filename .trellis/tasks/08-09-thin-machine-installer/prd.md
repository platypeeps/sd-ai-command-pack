# Machine-scope installer for non-Claude surfaces + unified update

Child of `08-09-deployment-thin-consumers`. Requirement 2 (remainder)
of the parent PRD; architecture in parent `design.md` ("Machine-scope
installer").

## Deliverable

`install.py --machine` writing user-level surface equivalents for
the `machine-other` partition slice plus rows flagged
`sharedRuntime: true` in the partition artifact (the
surface-partition JSON under fleet docs, created by
`thin-surface-partition` — schema in that child's design) — shared
scripts that non-Claude surfaces invoke at runtime; the rest of the
`machine-claude` slice belongs exclusively to the plugin
(`thin-plugin-packaging`). Platforms with `provisional: true` are
not installable until this child's verification flips them
(fail-closed schema semantics). Plus `sd-pack-update` (shipped in
plugin `bin/`) as the single machine update action.

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

- [ ] Machine install into a scratch prefix produces receipt with
      correct version/digest; rerun is a no-op.
- [ ] Unowned-file collision refused without force; diagnostic names
      the path.
- [ ] Interrupted update (plugin updated, machine install failed)
      shows skew in `sd-status`; rerunning `sd-pack-update` converges.
- [ ] Per-platform disposition verdicts recorded in task research and
      reflected in the partition output.
