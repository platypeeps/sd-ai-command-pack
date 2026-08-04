# Implement — 0.64.5 fleet-publish + sibling-loader hardening

> Revised after adversarial review. Order: C → B → A → release. Each phase ends
> on a green gate. Tests: `.venv/bin/python -m unittest tests.test_<module>`;
> lint `.venv/bin/ruff check`. Mirror rule (AGENTS.md): edit `templates/**` first,
> then sync the `scripts/` mirror.

## Phase C — self-publish guard (fleet-publish.py)
- [ ] C1. In `check_preconditions`, after the worktree-root check, add the
  bookkeeping-CI fingerprint guard raising `PublishError(<gate-centric message
  naming sd-finish-work>, code=3)`.
- [ ] C2. Add the consumer-only note to `docs/FLEET_ROLLOUT.md` and the
  `fleet-publish.py` module docstring.
- [ ] C3. `tests/test_fleet_publish.py`: pack-shaped tree (with
  `.github/scripts/bookkeeping_ci_scope.py`) → `check_preconditions` raises code 3
  AND message names sd-finish-work; consumer-shaped tree passes; assert the code
  propagates through `main()`.
- [ ] Gate C: `.venv/bin/python -m unittest tests.test_fleet_publish` green.

## Phase B — archive auto-commit resilience
### B-store (primary fix, task_store)
- [ ] B1. In `.trellis/scripts/common/task_store.py::_auto_commit_archive`, wrap
  ONLY the final `git commit` in a bounded retry: retry (≤3 attempts, fixed
  backoff via `time.sleep`) iff the commit's git stderr indicates index-lock
  contention (`index.lock` / `Unable to create` / `File exists`). Staging is
  unchanged. Any non-lock failure returns False immediately. Never delete a lock.
- [ ] B2. Tests (`tests/test_task_store.py` or the existing archive test): stub
  `git commit` to fail with an `index.lock` stderr once then succeed → archive
  commits, `after_archive` hooks run, only archive paths staged; a non-lock
  failure returns False without retry; assert the ≤3 attempt bound (exhaustion).
### B-fleet (consumer safety, loud abort — no rollback)
- [ ] B3. In `fleet-publish.py archive_and_journal`, on a non-zero archive result
  raise PublishError naming the likely transient git-lock cause and the exact
  recovery (task may be moved + staged but uncommitted; resolve `git status` /
  re-run the fleet action). Do NOT rename, reset, or otherwise attempt a partial
  rollback — cmd_archive's status/children/session mutations (task_store.py:473-506)
  make a dir-only rollback incomplete (N-1). No manual commit, no `git add -A`.
- [ ] B4. Test (`tests/test_fleet_publish.py`): stub the archive subprocess to
  return non-zero → archive_and_journal raises PublishError; assert the message
  names the transient cause + recovery, and that fleet-publish performed NO
  rollback mutation (no rename/reset call; tree left exactly as the stub left it).
- [ ] Gate B: `unittest tests.test_task_store` + `tests.test_fleet_publish` green.

## Phase A — sibling-loader ENOTDIR → missing (templates first)
- [ ] A1. `templates/scripts/…-status.py`: advisory `ENOTDIR → "missing"`;
  authoritative branch explicit `elif ENOTDIR → "missing"` + defensive
  `else → "non_regular"`.
- [ ] A2. `templates/scripts/…-surface-check.py`: same edit.
- [ ] A3. Sync mirrors: copy the canonical templates changes into
  `scripts/…-status.py` and `scripts/…-surface-check.py`; assert twins
  byte-identical (`diff templates/scripts/X scripts/X` empty).
- [ ] A4. Verify (no rewrite) caller catch sites already read correctly for
  `missing` (status.py:935/1337; surface-check.py:344); confirm repo-relative path
  is the only path emitted (no absolute/home/credential leakage).
- [ ] A5. `tests/test_helper_loader_safety.py`: rename the advisory ENOTDIR test to
  `test_enotdir_parent_maps_to_missing` asserting `missing` (status + surface);
  ADD `test_enotdir_authoritative_branch_maps_to_missing` that mocks `os.lstat` to
  a regular file so the real `os.open(O_NOFOLLOW)` raises ENOTDIR, asserting
  `missing` for status + surface.
- [ ] Gate A: `unittest tests.test_helper_loader_safety` green; twin diffs empty;
  `.venv/bin/ruff check` clean.

## Phase R — release 0.64.5
- [ ] R1. Bump version to 0.64.5 + CHANGELOG entry covering A/B/C (note B scope:
  task_store retry + fleet-publish loud abort, no rollback).
- [ ] R2. `make release-prep` green.
- [ ] R3. Full `make check` green.
- [ ] R4. Archive the 3 children, then the parent; one 0.64.5 PR; Copilot review;
  settle CI; merge; tag `v0.64.5`.

## Validation summary (falsifiable checks)
- C: `unittest tests.test_fleet_publish` — guard raises code 3 + sd-finish-work
  message; consumer passes; main() propagates. Exit 0.
- B: `unittest tests.test_task_store` — lock-retry succeeds, hooks run, staging
  scoped, non-lock no-retry, ≤3 bound; `tests.test_fleet_publish` — non-zero archive
  raises PublishError with recovery message and no rollback mutation. Exit 0.
- A: `unittest tests.test_helper_loader_safety` — advisory + authoritative both
  `missing`; twin `diff` empty; `ruff check` clean.
- R: `make release-prep` + `make check` — exit 0; version==0.64.5.

## Rollback points
- After each phase gate the diff reverts in isolation.
- Pre-release: abandon by reverting the branch.
- Post-merge: revert the single 0.64.5 PR. Consumers on 0.64.4 untouched.
