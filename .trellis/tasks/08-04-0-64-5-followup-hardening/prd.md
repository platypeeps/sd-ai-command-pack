# 0.64.5 fleet-publish + sibling-loader hardening

## Goal

Ship pack release **0.64.5** addressing three follow-ups surfaced by the 0.64.4
fleet rollout. All three are pack-source hardening; none change consumer product
code. This parent owns the requirement set, the cross-child acceptance criteria,
mirror-discipline integration, and the single 0.64.5 release (version bump,
CHANGELOG, `make release-prep`, PR, review, tag).

## Children

- `08-03-improve-unsafe-sibling-diagnostics` (A) — sibling-loader diagnostics.
- `08-04-fleet-publish-archive-commit-retry` (B) — archive auto-commit resilience.
- `08-04-fleet-publish-pack-self-publish-gate` (C) — consumer-only guard.

## Requirements

### A. Sibling-loader diagnostics
- Map `ENOTDIR` (a non-directory parent component ⇒ the module is unresolvable
  at the computed path) to reason `missing`, not `non_regular`, in BOTH the
  advisory `lstat` branch and the authoritative `O_NOFOLLOW`-open branch of
  `status.py` and `surface-check.py`, in `scripts/` AND `templates/scripts/`
  (byte-identical twins).
- Keep advisory/authoritative parity: both branches must agree on the reason for
  a given errno. The change must not weaken fail-closed refusal — behavior is
  unchanged; only the diagnostic `reason`/message differs.
- Update the advisory `tests/test_helper_loader_safety.py` ENOTDIR test to assert
  `missing` (rename off `_specific_reason`), covering both `status` and `surface`,
  AND add an authoritative-branch test (mock `os.lstat` to a regular file so the
  real `os.open(O_NOFOLLOW)` raises ENOTDIR) — the existing test only hits `lstat`.
- Caller wording is VERIFY-ONLY, no rewrite: catch sites already read correctly for
  `missing` (`status.py:935/1337` "not installed"; `surface-check.py:344` "missing
  source validator module: {relative}"). The reason-code flip alone yields the right
  message. Diagnostics may keep the repo-relative path (intended); the contract
  forbids only absolute/home paths and credentials.
- OUT OF SCOPE (verified already fixed): recovery schema-version mismatch error
  already emits expected-vs-actual (`recovery-artifacts.py:459`).
- OUT OF SCOPE: `fleet-controller.py` loader — simpler, no granular reason codes;
  intentionally excluded.

### B. archive auto-commit resilience (task_store retry + fleet-publish loud abort)
- A transient `.git/index.lock` contention during 0.64.4 self-publish aborted the
  helper mid-run with the task already moved on disk. Fix at the correct layer:
- Primary (the real fix): `task_store._auto_commit_archive` retries ONLY the final
  `git commit` on index-lock-specific stderr (bounded ≤3, fixed backoff, no lock
  deletion), preserving its existing scoped staging and the `after_archive` hook
  lifecycle. Non-lock failures still fail closed. This reaches the pack repo and
  any Trellis-updated repo. (Fixing here, not fleet-publish, avoids skipping hooks
  and broad `git add -A` — see design C-1/C-2.)
- Consumer safety (loud abort, no fabricated rollback): a consumer runs unpatched
  task.py, so fleet-publish cannot get the retry. `fleet-publish.py
  archive_and_journal` FAILS LOUDLY on a non-zero archive result — raises
  PublishError naming the likely transient git-lock cause and the exact recovery
  (task may be moved + staged but uncommitted; resolve `git status` / re-run the
  fleet action). It attempts NO partial rollback: cmd_archive also mutates task
  status, child parent links, and sessions before the move
  (task_store.py:473-506), so a dir+index-only rollback would be incomplete and
  misleading (see design N-1).

### C. fleet-publish self-publish guard (approach c)
- `fleet-publish.py` must refuse to run against the pack's OWN repository (detected
  by the presence of the pack bookkeeping-CI gate, e.g. `.github/scripts/
  bookkeeping_ci_scope.py`), because the fold pattern trips that gate
  (`completion_archive_move_missing`). Exit with the precondition failure code and
  a message directing self-publish to `sd-finish-work`.
- Document fleet-publish as consumer-only in `docs/FLEET_ROLLOUT.md` (and/or the
  script docstring).

## Acceptance Criteria

- [ ] A: `ENOTDIR` yields `missing` in all four twin files, both branches; twins
  byte-identical; advisory AND authoritative-branch tests assert `missing`.
- [ ] A: caller messages already read correctly for `missing` (verified, no
  rewrite); diagnostics emit no absolute/home path or credential (repo-relative
  path is allowed).
- [ ] B: task_store commit retries on index-lock stderr (hooks run, staging
  scoped, ≤3 bound, non-lock no-retry); on a consumer, a non-zero archive makes
  fleet-publish raise PublishError with transient-cause + recovery guidance and
  attempt NO partial rollback (no silent corruption); both covered by tests.
- [ ] C: running fleet-publish against this pack repo refuses with a
  sd-finish-work pointer and precondition exit code; running against a consumer
  is unaffected; covered by a test; doc updated.
- [ ] Release: version bumped to 0.64.5, CHANGELOG entry, `make release-prep`
  green (mirror + surface + candidate ledger), full `make check` green.
- [ ] All three children archived; single 0.64.5 PR merged and tagged.

## Notes

- Mirror discipline: `status.py` + `surface-check.py` have byte-identical twins
  in `scripts/` and `templates/scripts/` — edit BOTH. `fleet-publish.py` is
  pack-source only (`scripts/`, no twin).
- Test runner: `.venv/bin/python -m unittest tests.test_<module>`;
  `.venv/bin/ruff check`; `make release-prep`.
