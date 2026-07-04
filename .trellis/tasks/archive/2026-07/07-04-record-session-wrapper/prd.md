# One-shot journal recording without placeholders

## Goal

Trellis' `add_session.py` hardcodes `(Add test results)` and
`(see git log)` placeholders (only Main Changes is fillable via
`--content-file`) and auto-commits them, while the pack's preflight
rejects placeholders in completed sessions — forcing a manual
fill-and-amend dance after every session (six times this week, twice
briefly landing placeholder or wrong-hash content on main).

## Requirements

- R1: `scripts/sd-ai-command-pack-record-session.py` records a complete
  entry in one shot: Main Changes from repeatable `--change` flags via
  `--content-file`, commit-table subjects resolved from git, Testing from
  repeatable `--test` flags, optional `--next-step` overrides.
- R2: Unknown commit hashes fail fast (exit 2) before anything is
  written; a patched entry is verified placeholder-free before the
  workspace auto-commit (`--no-commit` skips the commit).
- R3: The `sd-finish-work` skill instructs using the wrapper instead of
  bare `add_session.py`, with a manual-fill fallback when the wrapper is
  absent.
- R4: Manifest ships the script (shared/always); docs list it; tests
  cover the happy path and the fail-fast path against a
  Trellis-bootstrapped scratch repo. 0.5.16 + fleet refresh.

## Acceptance Criteria

- [x] Happy path: entry carries real commit subjects, changes, and test
      lines; zero placeholders; workspace committed as
      `chore: record journal`.
- [x] Unknown hash exits 2 with a named error and writes no session.
- [x] Suite green at 100% install.py coverage; full-check clean; twins
      in sync.
- [ ] Fleet refreshed to 0.5.16 (post-merge step).
