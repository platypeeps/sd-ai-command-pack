# Enforce Untrusted Checkout Preflight Design

## Overview

Put one generated, fail-closed trust gate ahead of every command adapter that
may execute checkout-owned content. The gate uses only host-provided read-only
Git and GitHub metadata; it never executes a repository helper to decide
whether repository helpers are safe to execute.

## Proposal

Extend `CommandInfo` with conservative capability metadata:

- `executes_checkout_code`, defaulting to `true` for new commands;
- `mutates_local`;
- `mutates_remote`;
- `trusted_static_only`; and
- optional `safe_mode`.

Every current command records its mutation capabilities. `sd-help` is the sole
initial `trusted_static_only` exemption; every other command requires the
checkout-trust preflight.

Move the hand-authored neutral command bodies to the generator-owned source
area under `.github/command-sources/`. The command-surface generator inserts
the canonical trust block before the first skill-resolution step, writes the
guarded neutral adapters to `templates/.commands/`, and derives Claude,
Gemini, and GitHub adapters from the same guarded body. Manifest target paths
remain unchanged.

The preflight emits one bounded classification before any repository skill,
script, hook, package command, provider adapter, or command-bearing config is
loaded or run:

- `trusted / trusted_local_branch` for an unambiguous named local branch with
  no external PR head;
- `trusted / trusted_same_repo_pr` when the bound PR head repository exactly
  matches the base repository;
- `untrusted / untrusted_fork_pr` for a fork head; or
- `indeterminate` with a stable reason for detached HEAD, unreadable origin,
  unavailable PR identity, or contradictory metadata.

Untrusted and indeterminate states stop before checkout execution. They do not
offer an approval prompt. A future declared safe mode may inspect untrusted
text only as data using trusted static pack content and read-only metadata.

## Boundaries And Non-Goals

- The preflight is an adapter contract, not a sandbox for arbitrary providers.
- No checkout-owned classifier script is introduced.
- No GitHub permissions, branch protections, or Trellis-owned files change.
- This task does not attempt to make maliciously modified command text trust
  itself; it ensures the generated installed adapter places the trust boundary
  before delegated checkout content.
- Adapter target names and public command invocations do not change.

## Affected Files

- `installer/registry.py` for capability metadata and validation.
- `.github/scripts/generate-command-surfaces.py` for trust-block generation.
- `.github/command-sources/sd-*.md` for hand-authored neutral bodies.
- `templates/.commands/sd-*.md` and bespoke generated adapters.
- `manifest.json`, `CHANGELOG.md`, installed documentation, and candidate
  evidence for the consumer-visible release.
- `tests/test_help_command.py`, `tests/test_generated_parity.py`, and pack
  drift/install coverage.

## Data And Command Contracts

Capability metadata is immutable registry data. Validation rejects a trusted
static command that also executes checkout code or mutates state, rejects an
unsafe safe-mode identifier, and keeps execution-capable as the default for a
new registry row.

Generated guards precede the first `1. Resolve ... skill` step and contain the
same classification states, reason codes, stop behavior, and final
`checkout-trust: <state> (<reason>)` reporting requirement on every supported
adapter.

## Risks And Edge Cases

- A source body without exactly one resolution anchor fails generation.
- Detached, missing-origin, unavailable GitHub, and conflicting identities all
  fail closed instead of falling back to local execution.
- Neutral and bespoke adapters can drift if one bypasses the guarded generated
  body; parity and manifest-source tests prohibit that path.
- `sd-help` must remain non-executing despite reading command documentation;
  capability validation and read-only behavior tests pin its exemption.
- Release generation must run before sync so consumers never receive an
  unguarded neutral source.

## Validation

- Registry validation and conservative-default unit tests.
- Generator tests covering trusted-local, same-repository, fork,
  detached/unreadable/contradictory reason text and stop ordering.
- Exhaustive live-command and platform-adapter guard coverage with only the
  declared trusted-static exemption.
- `make generate`, `make sync`, focused tests, install audit, disposable fleet
  candidate validation, and `make check`.

## Rollback

Rollback reinstalls the preceding pack version. Do not retain the incomplete
four-command GitHub allowlist as a hidden fallback.
