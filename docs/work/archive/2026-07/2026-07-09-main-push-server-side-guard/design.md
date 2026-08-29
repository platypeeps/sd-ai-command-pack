# Add Server-Side Backstop For Direct Main Pushes Design

## Overview

The local pre-push hook protects the maintainer's intentional chore-only direct
push lane, but GitHub still accepts admin pushes when the hook is unarmed or
bypassed. Add a CI backstop for pushes to `main` that detects non-chore changes
after the fact and makes the failure visible.

## Proposal

Add a small script or workflow step that runs only on `push` to `main`. It
computes the pushed diff between the before and after SHAs and rejects any path
outside `.trellis/tasks/**` and `.trellis/workspace/**`. Use rename-aware
logic that exposes the deleted/source side for renames, matching the
`07-09-shell-hook-hardening` correction for `.githooks/pre-push`.

Keep the check as a detective control: it should not change branch-protection
policy or remove the explicit bypass, but it should fail loudly with the first
offending paths and point to the PR workflow.

## Boundaries And Non-Goals

Do not enable `enforce_admins` or remove the maintainer's emergency bypass.
This is defense in depth for accidental direct pushes.

## Affected Files

- `.github/workflows/tests.yml` or a dedicated workflow
- `.githooks/pre-push` if shared scope logic is extracted or mirrored
- `tests/test_generated_parity.py` if workflow text is pinned
- `README.md` and possibly `CONTRIBUTING.md`

## Risks And Edge Cases

GitHub push payloads can include branch creation or forced updates. Fail closed
when a reliable diff cannot be computed. Rename handling must not allow moving
source files into chore paths to appear chore-only.

## Validation

Add a local script test or workflow fixture for chore-only allowed, non-chore
rejected, rename-into-chore rejected, unknown base refused, and clear output.
