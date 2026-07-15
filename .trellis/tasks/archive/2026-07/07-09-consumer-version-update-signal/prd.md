# Give consumers a pack-version update signal

## Goal

Give a consumer repo a cheap, local way to learn that a newer pack version
exists, closing the pull-side gap: today the pack can only *push* refreshes,
and a consumer has no signal that it has drifted behind upstream.

## Problem

Surfaced by the 2026-07-09 architecture review (LOW). The vendored
`scripts/sd-ai-command-pack-install-audit.py` is integrity-only — it checks
receipt presence/structure and provenance hash/tamper, and prints the
installed version — but never compares against upstream. The installed guide
documents `--force` refresh mechanics but has no "how you learn a new version
exists" story. Combined with the fleet being 6 versions behind at review time,
consumers have no self-service drift signal; they depend entirely on a manual,
maintainer-driven rollout (tracked separately in
`07-09-fleet-refresh-081-completeness`, which is the push side).

Note the release-ledger work (`07-09-release-ledger-enforcement`) is a
soft dependency: a reliable version→tag anchor makes an upstream comparison
meaningful.

## Requirements

- R1: Provide a way for a consumer to compare its installed
  `.sd-ai-command-pack/provenance.json` version against an upstream pack
  reference (a pack checkout's `manifest.json` version, or a documented
  git/tag lookup) and report behind / current / ahead.
- R2: The check is read-only and fail-soft — if the upstream reference is
  unavailable (offline, no checkout), it degrades to a clear "could not
  determine upstream version" note, never an error that breaks a gate.
- R3: Decide the delivery vehicle and record the rationale: an optional
  `install-audit` mode/flag vs. a small standalone helper vs. documentation
  only. Prefer the lowest-maintenance option that consumers can run.
- R4: Document the update-detection flow in the installed guide alongside the
  existing `--force` refresh mechanics.

## Acceptance Criteria

- [x] A consumer can run one documented command that reports whether its
      installed pack version is behind the referenced upstream.
- [x] Missing/unreachable upstream reference yields a soft note, not a
      failure; no existing gate changes exit code because of this feature.
- [x] Installed guide documents the flow; docs twins byte-identical;
      review-preflight doc-path checker passes.
- [x] If implemented in Python, shipped-scripts coverage floor maintained.

## Non-goals

- Automatic self-updating by consumers (installs must stay reviewed/PR-driven).
- Network calls to a pack registry — comparison is against a local pack
  checkout or git ref, not a new hosted service.
