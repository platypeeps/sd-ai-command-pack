# Implementation — fix work-loop lock restore

## Order

1. **Write the failing test first.** In `tests/test_work_loop.py`, add a case
   that monkeypatches `os.link` to raise `OSError(errno.EPERM, "no hardlinks")`,
   drives `_recover_locked_path` with a competitor lock already in place
   (`expected_run_id` deliberately not matching), and asserts the competitor's
   bytes survive on disk at either `lock_path` or the aside path.
   **Gate:** this test must fail against unmodified `scripts/sd-ai-command-pack-work-loop.py`.
   If it passes, the test is asserting on the exception rather than on disk state
   — rewrite it before continuing.

2. **Add the acquisition test — this is the one that closes R1/R2.** Same
   monkeypatched `os.link` failure, then call `acquire_lock` on the same path and
   assert it **raises**. A-only fails this test by construction: `acquire_lock`
   tests just the canonical path with `os.open(..., O_EXCL)` (`:1112`) and never
   scans for a recovering-aside file, so an empty canonical path admits the next
   run silently.
   **Gate:** step 1's test proves the bytes survive; only this one proves
   exclusion survives. Shipping step 1 alone satisfies the visible symptom and
   leaves the defect.

3. **Implement A + C** (see `design.md` — restore-failure options): leave the
   aside and raise naming it, *and* attempt
   `os.open(lock_path, O_CREAT | O_EXCL)` plus a rewrite of the aside bytes so
   the canonical path is restored without clobbering. Record the choice and the
   reason in a comment above the restore block. Do not ship option B (`os.rename`
   fallback). If a measurement forces A + aside-detection instead, `acquire_lock`
   changes too and step 2's test still governs.

4. **Apply the fix** at `scripts/sd-ai-command-pack-work-loop.py:1058-1073`. The
   unlink at `:1066` becomes conditional on the restore having succeeded. Keep
   the `FileExistsError` branch deleting the aside — a newer lock exists there, so
   the aside is genuinely redundant and leaving it would litter the lock
   directory.

5. **Name the aside path in the error.** The `WorkLoopError` message must carry
   the aside filename so an operator can restore it by hand. Without this, option
   A leaves a stranded file with a uuid name and no way to know it matters.

6. **Mirror to the template twin** and run `make sync`.

7. **Re-run the tests from steps 1 and 2** — both must now pass.

8. **Check the sibling deletion path.** `:1053-1056` unlinks the aside when
   `matches` is true. That branch is correct (the process is deleting the lock it
   judged stale) and is out of scope per PRD R5. Confirm the fix did not disturb
   it rather than assuming.

## Validation

```bash
python3 -m pytest tests/test_work_loop.py -k recover -q
```

```bash
make sync && make check
```

## Review gates

- Before step 4: both failing tests exist and fail for the right reason.
- Before step 6: the restore-option decision is written down in the source
  comment.
- The acquisition test (step 2) is not optional. It is the only check that
  distinguishes "the bytes were preserved" from "mutual exclusion was
  preserved", and the two came apart in planning once already.
- Before completion: `make check` green and the template twin byte-identical.

## Rollback

Single-function change with a dedicated test. Revert the commit; no migration, no
state format change, no consumer-visible contract moved.
