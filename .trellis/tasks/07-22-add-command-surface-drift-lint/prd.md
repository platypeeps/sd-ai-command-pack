# Add command surface drift lint

## Goal

Prevent removed or renamed commands from remaining in live specifications,
documentation, adapters, manifests, help catalogs, and configuration guidance.
Derive live and retired identifiers from one canonical registry and validate the
complete generated/public surface.

## Evidence

- `.trellis/spec/frontend/adapter-guidelines.md:20-49`, 736-743, and 975-983
  still describe removed `sd-review-local-all` files and behavior.
- Current tests strongly cover generated parity and selected strings but do not
  comprehensively reject stale public identifiers in live prose.
- Upcoming clean-cut retirement of review/check and work-design commands raises
  the cost of relying on manual search alone.

## Dependencies

- The lint infrastructure can land independently.
- `07-22-integrate-routed-review-backends` owns registering the retired
  full-check/review/watch identifiers during its cutover.
- `07-22-streamline-backlog-design-workflows` owns registering
  `sd-work-designs` retirement.
- Historical archives, changelogs, migration notes, and retirement fixtures
  require an explicit bounded allowlist rather than a global exclusion.

## Requirements

- R1: Define one canonical registry of live public command IDs, generated target
  families, configuration keys, and retired identifiers/paths.
- R2: Validate manifest targets, source templates, generated adapters, help and
  completion catalogs, README/guides, live specs, and active task-independent
  product docs against the registry.
- R3: Fail when a live identifier lacks its required source/generated targets,
  when a retired identifier appears in live content, or when an undocumented
  public target appears outside the registry.
- R4: Support narrow contextual allowlist entries for migration/changelog,
  retired-target constants, archive fixtures, and tests that intentionally
  mention old names. Every allowance records file pattern and reason.
- R5: Do not scan vendored/build/cache content or treat archived Trellis task
  history as live product documentation by default.
- R6: Produce machine-readable findings with identifier, file, line, category,
  and suggested registry/content action.
- R7: Integrate with generated-surface checks and `make check` so drift fails
  before release and fleet rollout.
- R8: Add fixtures for rename, removal, missing adapter, stale spec, stale help,
  unregistered target, and allowed migration history.

## Acceptance Criteria

- [ ] The existing `sd-review-local-all` live-spec references fail before
  cleanup and pass after the spec is corrected or intentionally migrated.
- [ ] Retired review/check/watch/design identifiers cannot appear in live help,
  adapters, manifests, config docs, or specs after their owning cutovers.
- [ ] A new public command missing capability/target registry data fails lint.
- [ ] Historical archive and bounded migration fixtures remain readable through
  explicit reasoned allowlist entries.
- [ ] JSON findings identify exact files/lines and distinguish stale content
  from a missing registry/target declaration.
- [ ] Focused lint fixtures, generated parity, `make sync`, and `make check`
  pass.

## Out Of Scope

- Automatically rewriting ambiguous prose.
- Deleting historical task archives or changelogs.
- Preserving live compatibility aliases for retired commands.
