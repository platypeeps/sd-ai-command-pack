# Design — restore the aside lock without voiding mutual exclusion

## Scope boundary

One function: `_recover_locked_path` in
`scripts/sd-ai-command-pack-work-loop.py:1019`, plus its template twin. No change
to the stale-judgement callers (`acquire_lock:1076` via `:1123`/`:1141`,
`acquire_terminal_lock:1179` via `:1214`) and no change to the lock schema.

## The defect, precisely

The restore path runs only when `matches` is false — meaning the file that was
renamed aside is **not** the lock this process judged stale. In the common case a
competitor already replaced the lock, so the aside file is a live lock belonging
to somebody else, and the correct behavior is to put it back untouched.

```python
restore_error: OSError | None = None
try:
    os.link(aside, lock_path)        # :1059  no-clobber restore
except FileExistsError:
    pass                             # :1061  newer lock exists — aside is redundant
except OSError as error:
    restore_error = error            # :1063  RESTORE FAILED
try:
    aside.unlink()                   # :1066  runs regardless
except FileNotFoundError:
    pass
except OSError as error:
    restore_error = restore_error or error
if restore_error is not None:
    raise WorkLoopError(...)         # :1070
```

When `os.link` raises anything other than `FileExistsError`, the unlink at `:1066`
still executes and destroys the only remaining copy of a live lock. The raise at
`:1070` informs *this* process. It does not inform the lock holder, which
continues believing it holds the lock, and it does not inform the next arriver,
which now finds no lock at all and acquires. Mutual exclusion is gone for
everyone except the process that already gave up.

`os.link` is not exotic-only: it fails with `EPERM`/`ENOSYS` on filesystems
without hardlink support and `EACCES` under some container and network mounts —
exactly the environments where lock recovery matters most.

## Contract after the change

`_recover_locked_path` keeps its signature and its two success outcomes (deleted
the judged-stale lock, or found a newer one and left it alone). It gains a third,
explicit failure outcome: **the aside file still exists on disk and the canonical
lock path may be empty.** That state is recoverable by hand and must be named in
the error so it can be.

Invariant the fix must establish: *no code path deletes the aside file while the
canonical lock path is empty and the aside content was not the judged-stale
lock.*

## Restore-failure options

`os.link` was chosen because it is the atomic create-if-absent primitive — it
cannot clobber a newer lock. Any fallback must preserve that property.

- **A — leave the aside in place, raise naming its path.** Minimal, no new race.
  Necessary but **not sufficient on its own** — see below.
- **B — `os.rename(aside, lock_path)` fallback.** Restores the canonical path,
  but rename clobbers. If a competitor created a lock between the failed `os.link`
  and the rename, that lock is destroyed and two runs proceed. This reintroduces
  the exact race the docstring at `:1028-1035` says the hardlink exists to avoid.
  Rejected unless a measurement shows option A leaves locks stranded in practice.
- **C — `os.open(lock_path, O_CREAT | O_EXCL)` and rewrite the aside bytes.**
  Preserves no-clobber semantics without hardlinks, so it works where `os.link`
  does not. Costs a read plus a non-atomic write, and a crash mid-write leaves a
  truncated lock that `validate_lock` must reject rather than treat as stale.
  Viable second attempt layered on top of A; only worth it if hardlink-less
  filesystems are a real deployment target.

### A alone does not close the acceptance criterion

Corrected 2026-07-28 after adversarial review. An earlier draft called A the
"recommended baseline" and left "A alone, or A with C" open. **A alone fails the
PRD's R1/R2 criterion**, which requires that after a failed restore "a subsequent
`acquire_lock` on the same path does **not** silently succeed."

`acquire_lock` tests exactly one path:

```python
descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)   # :1112
```

It never enumerates the lock directory and never looks for a recovering-aside
file. Under A the canonical path is empty, so that `os.open` succeeds and the
next run proceeds — which is precisely the silent loss of mutual exclusion this
task exists to remove. The loud raise happens in the *recovering* process; the
*next* process never sees it.

So A is the error-reporting half and must be paired with one of:

- **A + C** — after the failed `os.link`, attempt
  `os.open(lock_path, O_CREAT | O_EXCL)` and rewrite the aside bytes. Restores
  the canonical path without clobbering, so `acquire_lock` needs no change. Costs
  a read plus a non-atomic write; a crash mid-write leaves a truncated lock that
  `validate_lock` must reject rather than treat as stale.
- **A + aside detection** — leave the canonical path empty and make
  `acquire_lock` fail closed when a recovering-aside file is present. Keeps the
  write path minimal, but adds a directory scan to the hot path and a second
  place that must agree on the aside naming convention.

**Recommendation: A + C.** It confines the change to the recovery path, leaves
`acquire_lock` untouched, and the truncated-write case is already covered by
`validate_lock`. Take A + aside detection only if a filesystem without working
`O_EXCL` is a real deployment target — in which case neither `os.link` nor
`os.open` gives exclusion and the task's premise needs revisiting.

Do not ship B.

## Compatibility and rollout

Behavior changes only on a path that is currently broken, so no caller contract
moves. `WorkLoopError` remains the raised type; only the message gains the aside
path. Rollout is the normal pack release; rollback is release-level reinstall.

## Test strategy

The failure is not reachable by ordinary fixtures — `os.link` succeeds on any
sane test filesystem. Force it: monkeypatch `os.link` to raise `OSError(errno.EPERM, ...)`,
then assert **on disk** that either `lock_path` or the aside file still holds the
competitor's bytes. Asserting only that `WorkLoopError` was raised passes against
the current defective code and proves nothing.
