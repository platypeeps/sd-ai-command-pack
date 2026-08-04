# Design — 0.64.5 fleet-publish + sibling-loader hardening

> Revised after adversarial review (host + Codex, 2 rounds). See the concern ledger
> in the completion report; C-1..C-9 and round-2 N-1 dispositions are baked into the
> sections below.

## A. Sibling-loader ENOTDIR → missing

### Current
Both loaders classify `ENOTDIR` as `non_regular` in two places:
- advisory `lstat` branch: `elif error.errno == errno.ENOTDIR: reason = "non_regular"`
- authoritative `O_NOFOLLOW`-open branch: `if ENOENT→missing / elif ELOOP→symlink /
  else→non_regular`, where `_PATH_POLICY_ERRNOS = {ENOENT, ELOOP, ENOTDIR}` so the
  `else` catches only `ENOTDIR`.

Canonical source is `templates/**` (AGENTS.md); the `scripts/` copies are
byte-verified mirrors. Files:
- `templates/scripts/…-status.py` (canonical) + `scripts/…-status.py` (mirror)
  — advisory ~856; authoritative else ~882
- `templates/scripts/…-surface-check.py` (canonical) + `scripts/…-surface-check.py`
  — advisory 268-269; authoritative 288-294

### Change
- Advisory branch: `elif ENOTDIR → reason = "missing"`.
- Authoritative branch: replace the bare `else → non_regular` with an explicit
  `elif errno == ENOTDIR → "missing"`, keeping a defensive final
  `else → "non_regular"` (unreachable for the current errno set, but safe if the
  policy set grows).
- Both branches now agree: ENOENT→missing, ELOOP→symlink, ENOTDIR→missing.
  Refusal behavior is unchanged; only the reason string differs. Rationale:
  ENOTDIR means a parent path component is not a directory, so no regular file is
  resolvable at the path — semantically "not found", not "present but refused".

### Caller wording (C-8 — verified, no rewrite)
The reason-code flip is sufficient. Catch sites already branch on the reason and
read correctly for `missing`:
- `status.py:935` / `:1337` → `"… helper is not installed"`.
- `surface-check.py:344` → `"missing source validator module: {relative}"`.
So an ENOTDIR path now surfaces as "not installed / missing" automatically. No
caller edit is required beyond the reason change; A-phase only VERIFIES these
messages, it does not rewrite them.

### Path in diagnostics (C-8 ruling)
Repo-relative paths in diagnostics are intended for operability and stay. The
"no path leakage" contract means: no absolute or home-relative paths, no
credentials, no remote URLs. `surface-check.py:344`'s `{relative}` is compliant.

### Parity invariant + test coverage (C-5)
The advisory `lstat` verdict and the authoritative-open verdict must map each
errno to the same reason. The EXISTING `test_enotdir_parent_maps_to_specific_reason`
creates a real non-directory parent, so advisory `lstat` raises ENOTDIR first and
the authoritative `os.open` is never reached. Renaming + reasserting it alone
would leave both authoritative branches untested. So:
- Update the advisory test to assert `missing` (rename → `…_maps_to_missing`).
- ADD a companion test that forces the authoritative branch: mock `os.lstat` to
  report a regular file (advisory passes), with a real non-directory parent so the
  fd-anchored `os.open(..., O_NOFOLLOW)` raises ENOTDIR; assert `reason == "missing"`.
  Cover both `status` and `surface`.

### Out of scope (verified)
- recovery-artifacts.py schema-mismatch already emits expected-vs-actual (:459/455).
- fleet-controller loader: simpler, no granular reason codes — unchanged.

## B. archive auto-commit resilience — task_store internal retry (C-1/C-2/C-3/C-4)

### Decision
The retry lives in `.trellis/scripts/common/task_store.py::_auto_commit_archive`,
NOT in fleet-publish. That function already stages exactly the archive source,
destination, and modified children (task_store.py:544/574) and its caller runs
`after_archive` hooks only after it returns success (task_store.py:~525→hooks).
Retrying there preserves correct staging AND the hook lifecycle. Completing the
commit from fleet-publish would skip hooks (C-1) and a `git add -A` would stage
unrelated/concurrent work (C-2) — both rejected.

### Change — task_store._auto_commit_archive
- Wrap ONLY the final `git commit` in a bounded retry: on failure whose git
  stderr indicates index-lock contention specifically (`index.lock` /
  `Unable to create '…/index.lock'` / `File exists`), sleep a fixed backoff and
  retry the SAME commit (staging is unchanged). Max 3 attempts, fixed steps
  (e.g. 0.2s, 0.5s). Never delete another process's lock. Any non-lock commit
  failure returns False immediately (unchanged fail-closed).
- Keying on the git lock stderr — not task.py's generic "Archive moved on disk"
  line (C-4) — ensures signing/identity/hook failures are NOT retried.

### Change — fleet-publish.py (consumer safety, loud abort — no rollback) (C-3/N-1)
A consumer checkout runs its OWN (unpatched) task.py, so fleet-publish cannot get
the retry and must handle a returned archive failure safely. `archive_and_journal`
wraps the archive call: on a non-zero result it raises PublishError naming the
likely transient git-lock cause and the exact recovery — the task may be moved on
disk AND staged but uncommitted; resolve `git status` or re-run the fleet action.

It deliberately does NOT attempt a rollback. Before the on-disk move, cmd_archive
already writes `status=completed`, detaches every child (`parent=None`), and clears
active sessions (task_store.py:473-506). A fleet-publish rollback that only renamed
the archive dir back and unstaged the index (N-1) would leave those three mutations
in place — a partial, misleading "pre-archive" state that is worse than a clean
loud failure. Because a fleet lane is isolated and re-runnable, a loud abort is a
correct terminal state: the operator (or a re-run) resolves the rare transient. No
manual commit, no `git add -A`, no fabricated rollback.

### Why not fix consumers directly
`task_store.py` is Trellis framework, not shipped in the sd-ai-command-pack
payload, so the internal retry reaches the pack repo (and any repo that updates
Trellis) but not consumer checkouts. The fleet-publish loud abort keeps consumer
behavior safe and unambiguous without the hook/staging hazards of a manual commit
or the incompleteness of a partial rollback.

## C. self-publish guard (fleet-publish.py)

### Change
In `check_preconditions` (after the worktree-root check), if
`(repo / ".github" / "scripts" / "bookkeeping_ci_scope.py").exists()`, raise
`PublishError(<gate-centric message>, code=3)`.

The fingerprint detects the completion-mode incremental-push bookkeeping GATE that
the fold pattern violates — today only the pack carries it (verified: no fleet
consumer, incl. pack-like se-ai-command-pack / sd-github-review, has it). Because
the trigger is the gate, not pack identity, the message is gate-centric:
`"refusing to run: target carries the completion-mode bookkeeping gate that a
folded publish would violate (fleet-publish is consumer-only); use sd-finish-work
for a folded-bookkeeping release"`. Exit code 3 = precondition failure.

### Docs
- `docs/FLEET_ROLLOUT.md`: one note stating fleet-publish is consumer-only and the
  pack self-releases via sd-finish-work.
- fleet-publish.py module docstring: same one-liner.

## Testing strategy
- A: `tests/test_helper_loader_safety.py` — advisory test asserts `missing`
  (renamed); NEW authoritative-branch test (mocked `lstat`) asserts `missing` for
  status + surface; verify caller messages for missing unchanged. Twin byte-diff
  check (`scripts/` == `templates/scripts/`).
- B: `tests/test_task_store.py` (or existing archive test) — stub `git commit` to
  fail with an `index.lock` stderr on the first attempt then succeed; assert the
  archive commits, hooks run, and only archive paths are staged; a NON-lock
  failure returns False without retry; assert the ≤3 attempt bound.
  `tests/test_fleet_publish.py` — a non-zero archive result makes archive_and_journal
  raise PublishError with the transient-cause + recovery message and perform NO
  rollback mutation (leaves the tree exactly as task.py left it); no `git add -A`.
- C: `tests/test_fleet_publish.py` — a tree with
  `.github/scripts/bookkeeping_ci_scope.py` makes `check_preconditions` raise code
  3 AND the message names sd-finish-work; a consumer-shaped tree passes; assert the
  code propagates through `main()`.
- Release gate: `make release-prep` + `make check`.

## Rollback
Each child is an isolated diff; revert per child. The release is a single PR —
revert the PR to roll back 0.64.5 wholesale. No consumer state is touched by this
work (consumers already on 0.64.4 stay there).
