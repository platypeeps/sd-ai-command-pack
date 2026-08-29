---
title: Comment the best-effort directory fsync in the atomic-write path
status: planning
created: 2026-08-12
---
# Comment the best-effort directory fsync in the atomic-write path

## Problem

`scripts/sd_ai_command_pack_lib.py` (and its `templates/scripts/` mirror) ends
its atomic-write helper with a best-effort fsync of the *directory* handle:

```python
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            except OSError:
                pass
            finally:
                os.close(directory_fd)
```

The swallow is correct. By that point the file's own data is written, flushed,
and fsynced, and the destination has already been replaced atomically; a
directory fsync that fails costs durability of the *directory entry* across a
power loss, not integrity of the file. But nothing in the code says so, and an
uncommented `except: pass` reads as an oversight.

This surfaced on 2026-08-12 from the fleet conversion cohort
(`08-11-convert-fleet-provider-configs`): six consumer repositories ran their
own code scanning over the copied pack payload and each raised the same
"Empty except" finding. Every one was rebutted against the pack source, and the
rebuttals are on those pull requests — but the finding is fair, it will recur
in every consumer on every pack refresh, and the pack owns the file.

Measured on 2026-08-12: the same conversion also produced 34 other findings
across those six repositories, all in two families that are genuinely false —
`...` bodies in `@overload` stubs, and the annotated `STATE_HOME_ENV`
re-export, which already carries `# noqa: F401` naming itself.

## Requirements

- R1: The `except OSError` around the directory fsync carries a comment stating
  what is already durable at that point and what the swallow gives up.
- R2: Behavior is unchanged. This is a comment, not a control-flow change.
- R3: `scripts/` and `templates/scripts/` stay byte-identical, and the change
  ships with the version bump and CHANGELOG entry the release drift gate
  requires for any shipped payload change.

## Acceptance Criteria

- [ ] The handler carries the comment, in both copies, and `diff` between them
      is empty.
- [ ] `make check` passes.
- [ ] The task records whether the two false-positive families are worth
      addressing too, with evidence, rather than leaving that open. A `pass`
      body in an `@overload` stub is a behavior change in the reader's mind and
      probably should not be made; the `noqa` re-export is already annotated and
      almost certainly should not be touched.

## Notes

- Do not chase "make consumer code scanning quiet" as a goal. The pack cannot
  see, and must not depend on, which scanners a consumer has enabled. Fix what
  is genuinely worth fixing on its own merits and rebut the rest, which is what
  the conversion cohort did.
