# Harden Audit Read-Only Methods And Path Handling Design

## Overview

Keep the formal audit charter-driven while removing the two places where its
documented method can exceed read-only authority. Tooling review becomes
strictly static, and architecture review obtains largest-file evidence through
a small pack-owned inventory helper that reads committed Git blobs rather than
executing or opening checkout-owned programs.

## Proposal

1. Replace the tooling charter's `make -n` and arbitrary `--help` probes with
   static inspection of Makefiles, task definitions, scripts, workflows, and
   documentation. Runtime smoke testing remains outside a read-only audit
   unless a different command supplies explicit execution authority.
2. Add `sd-ai-command-pack-audit-inventory.py` as a shipped, read-only helper.
   It obtains NUL-delimited committed-tree entries from
   `git ls-tree -rlz --full-tree HEAD --`, accepts only regular blob modes,
   ranks the reported blob sizes, and emits escaped JSON. It never evaluates a
   filename as an option, command, revision expression, or filesystem path.
3. Point the architecture charter at the helper instead of the
   whitespace-delimited `xargs wc` pipeline.
4. Add behavioral tests using tracked files with spaces, tabs, newlines, and
   leading dashes, plus checkout-owned Make/help handlers that would write
   markers if executed. Also cover an empty tracked-file set and malformed Git
   output/failure behavior.

## Boundaries And Non-Goals

- Preserve charter selection, finding schema, severity guidance, and the
  generated checkout-trust preflight.
- Do not execute repository targets, package tasks, scripts, hooks, or help
  handlers.
- Do not add a compatibility path for the unsafe probes.
- Do not change upstream Trellis or the audit router's dimension selection.

## Affected Files

- `templates/.agents/skills/sd-audit-repo/charters/tooling.md`
- `templates/.agents/skills/sd-audit-repo/charters/architecture.md`
- `templates/scripts/sd-ai-command-pack-audit-inventory.py`
- synchronized root mirrors under `.agents/` and `scripts/`
- `manifest.json` and generated installed-manifest/provenance mirrors
- `tests/test_audit_repo.py` and focused helper tests
- `.trellis/spec/frontend/adapter-guidelines.md`, `CHANGELOG.md`, and release
  candidate evidence

## Data And Command Contracts

The helper accepts `--repo PATH`, `--limit N`, and `--json`. JSON schema v1
reports the resolved repository, measurement `blob-bytes`, total tracked
regular-file count, skipped non-regular count, and a deterministic
largest-first list containing an escaped path, byte count, and blob object ID.
The human renderer uses
JSON-style quoted paths so control characters never become structural output.

Git failures, malformed staged records, missing or non-blob objects, invalid
limits, and truncated batch output are controlled errors. The helper performs
no writes and does not fall back to reading worktree paths.

## Risks And Edge Cases

- The helper never reads blob contents; it consumes Git's bounded metadata
  records and rejects an inventory above the configured path cap.
- Equal-sized paths use their raw Git path bytes as the deterministic
  tie-breaker before display decoding.
- Symlinks and gitlinks are skipped rather than followed.
- Invalid filename bytes are round-tripped through the platform filesystem
  codec and escaped in JSON; NUL remains impossible in Git paths.
- Parallel release branches may require a later manifest-version rebase, but
  this branch carries the minor bump required for its new shipped helper and
  changed audit behavior.

## Validation

- Focused audit/helper unit and subprocess tests.
- Template/root parity and manifest/install audit tests.
- `make sync`, full fleet candidate validation, and `make check`.
