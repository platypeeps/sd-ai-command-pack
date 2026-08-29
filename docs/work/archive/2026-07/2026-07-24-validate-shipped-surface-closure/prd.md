---
title: Validate complete shipped-surface closure
status: done
created: 2026-07-24
---
# Validate complete shipped-surface closure

## Goal

Catch incomplete command-pack changes locally by deriving and validating the
complete affected surface from authoritative registry and manifest data before
publication.

## Confirmed Evidence

- The recent review scan grouped 30 comments under generated-surface failures.
- PR #237's initial CI failed because
  `templates/.agents/skills/sd-fleet-refresh/references/controller-recovery.md`
  was tracked but absent from both manifest and source-only registration.
- PR #234 required follow-up fixes for omitted adapter families, duplicate
  findings, manifest-line diagnostics, registry type validation, and local/CI
  lint-scope drift.
- Templates are authoritative and the manifest owns installable files; local
  and CI policy must not maintain separate path inventories.

## Dependencies And Boundaries

- Parent: `07-24-implement-read-only-sd-check`.
- Reuse the canonical platform/command registry, manifest loader,
  command-surface drift lint, release-payload gate, and generated-parity
  contracts. Do not introduce a competing registry.
- The checker is read-only. `make generate`, `make sync`, candidate-ledger
  refresh, and KB refresh remain explicit preparation actions owned by their
  existing commands.
- `07-22-validate-sd-workflow-program-integration` owns the final caller and
  lifecycle matrix.

## Requirements

- R1: Build one versioned affected-surface graph from validated authoritative
  data. Represent template sources and source-only references, manifest
  entries, generated mirrors, installed platform targets, command/help/docs
  identifiers, registry records, local-check registrations, CI-check
  registrations, provenance, and release/candidate evidence.
- R2: Given the complete committed and intended working diff, compute the
  transitive closure for every changed shipped or checker surface. Include
  tracked and non-ignored untracked files through bounded, NUL-safe Git output;
  do not follow symlinks or scan vendored, generated-cache, or archive history
  outside declared rules.
- R3: Fail with stable path- and relation-specific diagnostics when a required
  node or edge is missing, duplicated, mistyped, unsafe, stale, or registered
  only in local or CI policy. Unknown schema versions and unreadable
  authoritative data fail closed.
- R4: Distinguish installable, generated, source-only, documentation-only,
  check-only, and retired provenance nodes. A source-only reference must be
  declared explicitly rather than forced into the install manifest.
- R5: Make `sd-check`, the local pre-publication gate, and CI invoke the same
  helper and configuration. Human output derives from the versioned JSON
  result; no caller reconstructs surface policy from prose or separate globs.
- R6: Report the exact owning preparation command for fixable stale state but
  never generate, synchronize, stage, commit, or refresh from this check.
- R7: Keep diagnostics bounded, repository-relative, control-free, and
  deterministic. Detect duplicate logical findings before rendering.
- R8: Preserve release-version, changelog, candidate-ledger, provenance, and
  install-audit requirements for any changed shipped payload.

## Acceptance Criteria

- [ ] A new skill reference missing from both manifest and source-only
  registration fails locally before first push with the exact path and allowed
  remedies.
- [ ] Fixtures cover each supported platform family, source-only references,
  generated mirrors, retired targets, docs/help, local/CI checker registration,
  and release/candidate evidence.
- [ ] Local and CI scopes are generated or consumed from the same inventory;
  changing only one side is a deterministic failure.
- [ ] Duplicate registrations, duplicate diagnostics, wrong scalar/container
  types, unsafe paths, symlinks, oversized inputs, and unknown schemas fail
  safely.
- [ ] Stale generated state reports its owner command without changing any
  tracked, untracked, ignored, Git, or GitHub state.
- [ ] Focused closure tests reproduce the PR #237 and PR #234 failure families;
  generated parity, install audit, `make sync`, and `make check` pass.

## Out Of Scope

- Automatically editing the manifest or guessing whether a new file is
  installable versus source-only.
- Replacing semantic review of command behavior.
- Scanning archived Trellis task prose for live command surfaces.
