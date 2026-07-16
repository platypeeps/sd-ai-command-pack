# P3 polish batch from the 2026-07-15 audit

## Problem

15 P3 audit findings live in the ledger with no task. Nine are safe,
small-effort polish suitable for one batch PR; the rest are excluded here
with reasons and stay open in the ledger.

## In scope (9 items)

- A-016 (bloat): trim the 42 dead re-export forwards from install.py's
  import block and __all__ (keep every name tests actually reach via
  install.X — re-derive the reached set, don't trust the count blindly).
- A-017 (correctness): review-preflight.mjs spawnSync calls get an explicit
  large maxBuffer and treat result.error as a hard failure instead of an
  empty diff.
- A-021 (documentation): document the REVIEW_PR_REMOTE_* env-var family
  (incl. SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER_LABEL) in the guide
  Configuration section and the README table.
- A-022 (documentation): one-line responsibility docstrings on the six
  installer/ modules + short docstrings on load_manifest, validate_manifest,
  selected_files, and the removal entry point.
- A-023 (improvements): `make sync` target running the dogfood
  install.py . --force and the KB refresh (the two steps this session
  forgot four times); document in CONTRIBUTING.
- A-024 (performance): review-preflight.mjs computes documentationGuardFiles
  once and memoizes readText per path.
- A-028 (testing): review-learnings error-branch tests (git nonzero-exit
  RuntimeError path; untracked-file diff path).
- A-029 (tooling): STRICT=1 make mode turning the node/shellcheck skip
  warnings into hard errors; note in CONTRIBUTING for CI parity.
- A-030 (tooling, scoped): extend mypy to install.py; for scripts/, attempt
  and keep only if the error surface is trivial — otherwise document the
  exclusion rationale in the workflow/Makefile comment (the finding's
  sanctioned alternative).

## Excluded, staying open in the ledger

- A-020: PackFile.source Optional refactor — core installer type change
  with 100%-coverage ripple; deserves focused work, not a polish batch.
- A-027: Trellis-owned shell=True hooks — upstream, not pack-fixable.
- A-031/A-032: install-path I/O re-reads — perf-only micro-gains against
  installer-core churn; same risk class the maintainer declined in July.
- A-033: shell coverage tooling — infrastructure-scale, not polish.
- A-018/A-019, A-025/A-026 remain folded into their existing tasks.

## Acceptance Criteria

- [ ] All 9 items implemented; excluded items untouched.
- [ ] make test + make full-check green; installer coverage 100%; no
  behavior change outside the preflight hard-fail (documented in CHANGELOG).
- [ ] Bump 0.13.1 (payload: preflight mjs + guide) with CHANGELOG entry.
- [ ] Ledger notes annotate the 9 items (fixed-in-0.13.1 breadcrumb; status
  flips stay owned by the next audit run).
