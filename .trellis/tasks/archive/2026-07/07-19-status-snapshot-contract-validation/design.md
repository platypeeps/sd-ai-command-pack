# Validate sd-status work-loop snapshot contracts Design

## Overview

`sd-status` dynamically loads the shipped work-loop helper and currently trusts
every mapping it returns. Add a local validation boundary so a drifted or
substituted helper cannot make the human report render `None` for required run
metadata.

## Proposal

Validate the helper result after confirming it is a dictionary:

- accept `none`, `invalid`, and `unavailable` without requiring persisted-run
  fields;
- accept `active`, `paused`, `stopped`, and `completed` only when the fields
  consumed by the renderer have the expected top-level shape;
- return an adapter-owned `invalid` snapshot for a missing or unsupported
  status and for the first missing or malformed required field; and
- keep diagnostics bounded and structural by naming the field, never the
  helper-controlled value.

Persisted-run snapshots require non-empty strings for `runId`, `mode`,
`selector`, `phase`, `focusMode`, and `heartbeatAt`; a non-boolean integer for
`iteration`; a list of strings for `focus`; dictionaries for `counters`,
`contextHealth`, and `checkpoint`; and non-empty string members for
`contextHealth.level` and `checkpoint.state`. Optional task, PR, branch, and
stop-reason fields keep their existing behavior.

## Boundaries And Non-Goals

- Do not change the user-local work-loop ledger schema or helper validation.
- Do not alter valid status JSON or human rendering.
- Do not weaken installer provenance or template parity checks.
- Do not echo malformed helper values in diagnostics.

## Affected Files

- `templates/scripts/sd-ai-command-pack-status.py` (canonical shipped source)
- `scripts/sd-ai-command-pack-status.py` (source-checkout mirror)
- `tests/test_status.py`
- release metadata, docs/spec, generated catalog, and candidate ledger required
  by the pack release process

## Data And Command Contracts

`collect_work_loop(repo)` always returns a dictionary with a supported `status`.
Malformed helper mappings become:

```python
{"status": "invalid", "error": "work-loop helper returned ..."}
```

The error is deterministic, bounded, and identifies only the structural
contract failure.

## Risks And Edge Cases

- Python `bool` is an `int`; explicitly reject it for `iteration`.
- Empty strings are not useful renderer values and must fail.
- Lists containing non-string focus values must fail without rendering them.
- Nested `contextHealth` and `checkpoint` dictionaries need the specific
  members used by the report.
- Valid terminal snapshots may omit an error and preserve existing fallback
  text.

## Validation

- Focused status tests cover every accepted state plus missing, unsupported,
  and incomplete snapshots.
- Template/source twin checks remain byte-identical.
- Canonical `make check` and exact-payload disposable fleet validation pass for
  the release candidate.
