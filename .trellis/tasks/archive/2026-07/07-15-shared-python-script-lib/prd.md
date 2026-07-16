# Shared Python script library (sd_ai_command_pack_lib)

## Problem

Audit finding A-013 (P2·M, improvements/architecture), 2026-07-15 @ f6f3932:
the shipped Python scripts re-implement the same git/subprocess shim
(`record-session.py:50`, `pr-body-scope.py:255`, `review-learnings.py:423`,
`update-spec-kb.py:135`) and repo-root detection (`record-session.py:246`,
`update-spec-kb.py:153`); the shell side has `shell-lib.sh` precedent but
also under-centralizes (`have()` copy-pasted in 4 scripts). Cross-cutting
concerns (timeouts, encoding, error handling) drift per copy — the timeout
gap (A-003) is the realized consequence.

Note: a cross-script shared module was assessed as not viable in the July
2026 optimization pass (import-coupling and shipped-file-set concerns). This
task reopens that decision with the audit's drift evidence; the design phase
must address the earlier objections explicitly.

## Goal

One shipped consumer-side home for cross-cutting Python helpers (guarded
git/gh runner, repo-root resolver), so fixes land once instead of per-copy.

## Requirements

- Ship a new `sd_ai_command_pack_lib.py` under `scripts/` with a byte-identical
  `templates/scripts/` twin and manifest entries.
- House: guarded subprocess runner (default timeouts, TimeoutExpired
  handling), repo-root resolver; keep the surface minimal.
- Migrate the four standalone wrappers onto it without changing script CLIs,
  output, or exit codes.
- Move shell `have()` into `shell-lib.sh` for symmetry.
- Design must state why the earlier "not viable" objections no longer hold
  (or scope the lib to avoid them).

## Acceptance Criteria

- [ ] Lib shipped + twinned + manifest-registered; install-audit passes.
- [ ] Four scripts import the lib; no behavioral diff (byte-identical
      output/exit codes on existing tests).
- [ ] Coverage floors hold; lib itself covered.
