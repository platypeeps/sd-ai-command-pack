# Subprocess timeout hardening across shipped scripts

## Problem

Audit finding A-003 (P2·S, correctness/improvements), 2026-07-15 @ f6f3932:
external subprocess calls have no timeout in `installer/localonly.py:163`
(`trellis init`), `:51`, `:224`; `installer/fileops.py:608`, `:634`;
`installer/provenance.py:253`; `scripts/sd-ai-command-pack-install-audit.py:508`,
`-pr-body-scope.py:256`, `-update-spec-kb.py:136`, `-record-session.py:52`.
`scripts/sd-ai-command-pack-housekeeping.sh` uses no timeouts on network
`gh pr view/list/merge` and `git fetch` although `shell-lib.sh:61` provides
`run_command_with_timeout`. review-learnings already sets timeouts
(:438/:495/:574) after this failure class fired once
(journal-1.md:629), so the omission is inconsistency, not intent.

## Goal

Every external git/gh/trellis subprocess call in shipped code is bounded,
failing fast with a clear diagnostic instead of hanging installs or
automated cleanup/merge flows.

## Requirements

- Python: apply a default `timeout=` (match review-learnings' 60/120s tiers)
  and convert `TimeoutExpired` into a clear, actionable error.
- Shell: route housekeeping's network gh/git calls through
  `run_command_with_timeout`.
- If 07-15-shared-python-script-lib lands first, house the guarded runner
  there; otherwise keep per-script wrappers consistent.

## Acceptance Criteria

- [ ] No unbounded subprocess call remains in installer/ or shipped scripts
      (grep-able check or lint note).
- [ ] TimeoutExpired paths are tested for at least one Python script and
      exercise a clear error message.
- [ ] Housekeeping network calls are timeout-wrapped; self-test still passes.
