# Typed result-status vocabulary for installer results

## Problem

Audit finding A-011 (P2·M, design), 2026-07-15 @ f6f3932: result `status`
is a stringly-typed ad-hoc enum. `installer/fileops.py:50-60` keeps
`status: str` with membership frozensets; producers emit bare literals
(fileops.py:237-271, removal.py, localonly.py); consumers hard-code them
across module boundaries (`install.py:436` `== "symlink-conflict"`,
`install.py:676`, `removal.py:306`). Renaming a producer literal silently
breaks a consumer in another file.

## Goal

Producers and consumers share one checked status vocabulary per result
type; a renamed status is a type/lint error, not a silent behavior change.

## Requirements

- Model status as `StrEnum` (or `Literal` unions) for
  `InstallResult`/`RemoveResult`/`LocalOnlyResult`.
- Replace inline literal comparisons with enum members / named sets;
  keep `CONFLICT_STATUSES`/`VOUCHABLE_STATUSES` as enum sets.
- Preserve all emitted strings byte-for-byte (status values are printed);
  mypy on installer/ must enforce membership.

## Acceptance Criteria

- [ ] No bare status literal comparisons remain outside the enum
      definitions (grep check).
- [ ] Output and exit codes unchanged (existing tests pass untouched
      except imports).
- [ ] Installer coverage stays 100% line+branch; mypy clean.
