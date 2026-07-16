# Evaluate manifest-section support for platform registry entries

## Goal

Capture the conditional task for manifest-section support in the platform
registry. The current manifest and installer behavior are stable, so this
schema change should wait until future shipped payload structure makes grouped
manifest sections materially safer, clearer, or easier to maintain.

## Trigger

Waiting for external trigger: a concrete manifest maintenance problem, payload
grouping requirement, or installer safety issue that would be better addressed
by first-class manifest sections than by the current flat manifest entries plus
registry-derived metadata.

Source:
`.trellis/tasks/archive/2026-07/07-06-introduce-platform-registry/prd.md` and
`.trellis/tasks/archive/2026-07/07-06-installer-module-decomposition/design.md`.

## Requirements

- Identify the specific flat-manifest pain point that motivates the schema
  change.
- Design the section schema so older installers fail clearly rather than
  misinstalling unknown shapes.
- Preserve current install, update, audit, local-only, and remove behavior for
  existing manifest entries.
- Keep registry-derived platform metadata as the source of truth unless the new
  section schema deliberately supersedes part of it.
- Update tests, docs, and template/install parity checks if the schema changes.

## Acceptance Criteria

- [ ] A concrete triggering defect or maintenance problem is linked in this PRD.
- [ ] The manifest schema change includes compatibility and failure-mode
  handling for older installers.
- [ ] Installer, install-audit, remove, and generated parity tests cover the new
  section behavior.
- [ ] Docs explain the manifest-section contract if it becomes user- or
  maintainer-visible.

## Notes

- Do not start this task until the trigger exists.
- This is a parked task, not currently actionable backlog.
- Re-evaluated 2026-07-14 after installer preflight, concurrency, and audit
  changes. The flat manifest plus the single platform registry still represents
  the payload without duplicated groups or unsafe maintenance overhead, so the
  schema-change trigger remains absent.

## Status note (2026-07-16)

The trigger condition (a concrete manifest maintenance problem) fired: the
manifest reached 534 hand-written entries growing 25 per command. The 0.13.0
surface-generation work (07-15-surface-generation) addressed it by deriving
command entries from the registry instead of introducing manifest sections.
Maintainer decision pending: archive this task as superseded, or keep it
parked for a future section-schema need.
