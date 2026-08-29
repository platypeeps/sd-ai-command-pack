# Constrain Remove To Manifest-Recognized Targets Design

## Overview

`install.py --remove` should delete only pack-owned artifacts. The current
receipt-driven candidate set trusts consumer-editable files enough to delete a
hash-matched arbitrary in-repo path, which is a data-loss bug.

## Proposal

Introduce a manifest-scoped removal allowlist. Removal candidates may come from
receipts/provenance, but before `remove_pack_file()` is called each candidate
must be recognized as one of:

- a selected manifest target for the current platform selection;
- a generated pack state target such as `.sd-ai-command-pack/provenance.json`,
  `.sd-ai-command-pack/installed-targets.txt`, or the local-only marker; or
- a managed block target handled through its block remover.

Receipt or provenance entries outside that allowlist should produce an
`ignored` or `preserved` result with a clear detail such as "not a recognized
pack target". Anything under `.git/` should be rejected before hash checks,
even if a future manifest mistake lists it.

Keep `--force` limited to recognized pack targets. Force may override drift for
pack files, but it must not turn corrupted receipt contents into delete
authorization.

## Boundaries And Non-Goals

Do not sign receipts or change provenance format. The fix is candidate scoping,
not authentication.

## Affected Files

- `installer/removal.py`
- `install.py` only if the public remove flow needs a new helper import
- `tests/test_remove.py`
- Potentially `installer/provenance.py` if the shared generated-target list
  should live with receipt code

## Risks And Edge Cases

Preserved receipt entries for skipped platform targets must still be removable
when that platform is selected in a later remove run. Managed blocks such as
`.gitignore` and Copilot instructions should remain block-edit operations, not
whole-file deletions.

## Validation

Add tests for tampered `.git/config`, arbitrary user files, absent manifest
targets, and dry-run parity. Keep existing legitimate remove, force, backup,
and drift-preservation tests green with 100% removal coverage.
