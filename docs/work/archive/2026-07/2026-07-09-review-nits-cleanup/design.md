# Review Nits Cleanup Batch Design

## Overview

This task is a bounded cleanup list for seven already-triaged review findings.
The design should keep the batch small: fix or explicitly document N1-N6 in the
pack and record N7 as consumer coordination.

## Proposal

Implement N1 by probing `gh auth status` or otherwise distinguishing CLI
authentication failure from "no PR" in housekeeping messages. Implement N2 by
making the default uv cache/tool paths per-user, preferably honoring
`XDG_CACHE_HOME` and falling back to a `TMPDIR` path that includes
`$(id -u)` or bash's `$UID`.

Handle N3 by applying the same symlink-hostile guard pattern already used in
other tests, unless the suite decides symlinks are a hard prerequisite. For N4,
bring `make test` into parity with CI's skipped-test backstop by teeing unit
test output and grepping for skipped tests. For N5 and N6, record explicit
decisions: split support modules now only if it stays mechanical; add 3.11/3.12
lanes or document the two-ended matrix rationale.

For N7, add a fleet-touch checklist note or issues in the consumer repos rather
than changing pack payload.

## Boundaries And Non-Goals

Do not change installer/removal behavior. Do not add new nits to this task.

## Affected Files

- `templates/scripts/sd-ai-command-pack-housekeeping.sh` and root twin
- `templates/scripts/sd-ai-command-pack-shell-lib.sh` and root twin
- `Makefile`
- `.github/workflows/tests.yml` if Python matrix changes
- `tests/test_pack_drift.py`, `tests/test_housekeeping.py`
- Fleet or task notes for N7

## Risks And Edge Cases

Changing `make test` output capture must preserve coverage shard behavior. CI
matrix expansion can uncover unrelated compatibility failures; split if it
stops being small.

## Validation

Run focused housekeeping and pack drift tests, `make test`, shellcheck, and the
CI-equivalent coverage commands.
