# Define Trellis version compatibility contract when incompatibilities appear

## Goal

Capture the conditional task for a declared Trellis version compatibility
contract. The pack currently relies on active Trellis installs plus install
audits rather than a hard version range. A version-range contract should be
introduced only when a real Trellis version incompatibility appears.

## Trigger

Waiting for external trigger: a consumer repo, installer run, audit, or review
cycle shows that a specific Trellis version is too old, too new, or missing a
runtime behavior required by the pack.

Source:
`.trellis/tasks/archive/2026-07/07-06-introduce-platform-registry/prd.md`.

## Requirements

- Identify the exact Trellis behavior or file contract that is incompatible.
- Decide where the compatibility contract belongs: manifest metadata,
  installer preflight, install audit warning/error, docs, or a combination.
- Keep local-only installs and consumer refreshes understandable when the
  version check blocks or warns.
- Avoid hardcoding a version range without evidence from the triggering
  incompatibility.

## Acceptance Criteria

- [ ] The triggering incompatibility is linked and described.
- [ ] The pack reports the compatibility issue with clear remediation guidance.
- [ ] Tests cover both compatible and incompatible Trellis versions or fixture
  equivalents.
- [ ] Docs explain the compatibility policy and how users should update Trellis.

## Notes

- Do not start this task until the trigger exists.
- This is a parked task, not currently actionable backlog.
- Re-evaluated 2026-07-14 against the installed Trellis runtime and canonical
  Trellis 0.6.7 checkout. No pack behavior in this P3 sweep exposed a concrete
  version incompatibility, so a speculative version-range gate remains
  unwarranted.
