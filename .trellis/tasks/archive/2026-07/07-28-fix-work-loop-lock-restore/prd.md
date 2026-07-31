# Preserve the aside lock file when restore fails

## Goal

Work-loop lock recovery moves a foreign lock aside, decides it is not stale, then
tries to restore it. If the restore fails it deletes the aside copy anyway — the
only remaining copy of that lock. The recovering process aborts, but the lock is
now gone from the filesystem while its original holder is still running, so the
*next* process acquires a lock that should have been held. Make the failure path
preserve the evidence it needs to stay correct.

## Origin

Created 2026-07-28 from the repo audit with explicit user consent. Owns finding
A-092 (P2 · S · Plausible · correctness).

## Evidence

`scripts/sd-ai-command-pack-work-loop.py:1019` `_recover_locked_path`. The
foreign-lock path runs `:1057-1073`:

```python
restore_error: OSError | None = None
try:
    os.link(aside, lock_path)          # :1059
except FileExistsError:
    pass                               # :1061-1062  a newer lock already exists
except OSError as error:
    restore_error = error              # :1063-1064  restore FAILED
try:
    aside.unlink()                     # :1065-1066  unconditional
except FileNotFoundError:
    pass
except OSError as error:
    restore_error = restore_error or error
if restore_error is not None:
    raise WorkLoopError(...)           # :1070-1073
```

Three things follow:

1. **The unlink at `:1065` is unconditional.** It runs in the `restore_error`
   branch too, where `lock_path` does not exist and `aside` holds the only copy
   of the foreign lock's payload. After this line the lock is unrecoverable.

2. **Deleting the aside is correct in the `FileExistsError` branch and wrong in
   the `OSError` branch.** `FileExistsError` means another process already
   created a newer lock at `lock_path`; that lock is authoritative and the aside
   is genuinely redundant. The fix must keep that case deleting and change only
   the failure case — a blanket "never unlink" would leak an aside file on every
   contended recovery.

3. **`os.link` is the specific trigger.** Hard links are not available on every
   filesystem the pack runs on: some network mounts, FUSE filesystems, and
   cross-device layouts fail `os.link` with `EPERM`, `EXDEV`, or `ENOSYS` while
   `os.rename` at `:1040` succeeded. So the precondition for reaching the broken
   branch is exactly "a filesystem where the rename worked and the link cannot."

Call sites: `:1123`, `:1141` (`acquire_lock`, `:1076`) and `:1214`
(`acquire_terminal_lock`, `:1179`), all gated on `recover_stale`.

## Requirements

- R1: when restore fails, the aside file survives. The recovery raises
  `WorkLoopError` as it does today, but the foreign lock's payload must still
  exist on disk so the situation is recoverable rather than terminal.

- R2 (constraint on R1): the `FileExistsError` branch keeps unlinking the aside.
  Distinguish "a newer lock won the race" (delete) from "restore failed"
  (preserve). These are different outcomes of the same `try` and today they
  share a line.

- R3: the raised `WorkLoopError` names the aside path. An operator who hits this
  cannot act on `cannot recover <context>: <errno>` alone; they need to know
  which file to move back. This is the only recovery instruction they will get.

- R4: consider restoring by rename rather than by link. `os.rename(aside, lock_path)`
  works on filesystems where `os.link` does not, and it is the exact inverse of
  the `:1040` operation that created the aside. It is not a drop-in — rename
  clobbers a newer lock where link fails safely with `FileExistsError`, so a
  rename fallback must first confirm `lock_path` is absent, and that check is
  racy. Decide in `design.md` whether the fallback is worth the race or whether
  R1's preserve-and-report is the whole fix. Preserving is sufficient for
  correctness; the fallback only reduces operator toil.

- R5: no change to the stale/matching path (`:1052-1056`). When the lock is ours
  or unreadable-and-unowned, unlinking the aside is the intended behavior and
  stays as is.

- R6: template parity. `templates/scripts/sd-ai-command-pack-work-loop.py`
  carries the same function; both copies change together and generated-parity
  checks stay green.

## Acceptance Criteria

- [x] R1: a test that forces `os.link` to raise a non-`FileExistsError` `OSError`
      leaves the aside file present on disk after `_recover_locked_path` raises.
      This file is deleted today.
- [x] R2: a test where `lock_path` is recreated between the rename and the link
      still removes the aside and does not raise.
- [x] R3: the raised message contains the aside path.
- [x] R1/R2: after a failed restore, a subsequent `acquire_lock` on the same path
      does **not** silently succeed — either the restored lock blocks it or the
      preserved aside is detected and reported.
- [x] R5: existing stale-recovery tests pass unchanged.
- [x] R6: `scripts/` and `templates/scripts/` copies are identical; `make sync`
      passes.
- [x] `make check` passes.
- [x] Changelog + version; fleet rollout via normal refresh.

## Notes

- Audit source: `.trellis/audit/report-2026-07-28.md` — A-092 (P2 · S ·
  Plausible · correctness).
- **Ledger wording corrected 2026-07-28.** The note says mutual exclusion is
  "silently voided." It is not silent for the *recovering* process: `:1070-1073`
  raises `WorkLoopError`, so that process aborts loudly. The silence is on the
  other two sides — the original holder keeps running believing it holds a lock
  that no longer exists, and the next arriving process sees an empty path and
  acquires cleanly. The defect is the destroyed aside, not a missing raise.
- The last acceptance criterion is the one that actually proves the bug matters;
  the first only proves the file survives. Keep both.
- Effort is S in the audit and that looks right for R1–R3. R4 is the only part
  that could grow, which is why it is scoped as a decision rather than a
  requirement.
- Planning: R1–R3, R5, R6 are mechanical and well-specified. If R4 is answered
  "preserve and report only," this task is lightweight and can stay PRD-only. If
  the rename fallback is adopted, the race analysis belongs in `design.md` before
  `task.py start`.
