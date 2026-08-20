# Shipped executable scripts are tracked non-executable

## Closure — 2026-08-20: SUPERSEDED by 08-20-ship-helper-exec-bit

Not fixed and not declined. This task described the tracked-index half (49 shebang-carrying scripts tracked 100644) of a single defect with
one root cause, and has been absorbed whole into
`.trellis/tasks/08-20-ship-helper-exec-bit/`, which carries every acceptance
criterion from both records forward. The defect is still live at closure time.

Root cause, established 2026-08-20: the pack has two independent executable-bit
derivations. `installer/fileops.py:427` carries the template's mode forward on
the repo-install path, while `installer/machinepayload.py:99-100` derives the
bit from the destination family and the `sd_ai_command_pack_` prefix, ignoring
source mode entirely. The machine payload therefore ships 755 everywhere except
the pack's own checkout — the one place `run --` resolves.

### Corrections carried into the successor

Three claims in the body below are wrong and are corrected in the successor's
`design.md`; do not implement from this record.

1. **A mode-only change DOES move the fleet ledger.** The absorbed record cites
   the machine-payload digest to argue otherwise. The fleet candidate digest is
   a different function that reads the filesystem mode
   (`scripts/sd_ai_command_pack_fleet_lib.py:792-795`, folded in at `:778`).
   Measured: `sha256:c4f9c344…` today, `sha256:d458b3d6…` after the chmod. A
   second mode-reading digest exists at `.github/scripts/release_identity.py:244`
   (`executable=mode == "100755"`) and also moves. The cost asymmetry used to
   prefer this fix over the dispatch fix never existed; the successor re-argues
   the choice on correctness grounds instead.
2. **`make sync` will NOT propagate the chmod.** `installer/fileops.py:465-474`
   returns `UNCHANGED` as soon as destination bytes match, and returns before
   any chmod; the mode is applied only by `atomic_write_bytes` (`:120`) on a
   real write. Since this change moves no bytes, `scripts/` would stay 644. Both
   trees must be chmod'd explicitly. That the installer never repairs a drifted
   destination mode is a latent defect of its own, recorded as out of scope.
3. **The baseline is 49, not 51.** 30 under `scripts/` plus 23 under
   `templates/scripts/`, minus the four `sd_ai_command_pack_` library files
   across both trees.

Also corrected: there are now 14 authored `run --` sites, not 11.

### The trap this record did not know about

No repository-wide chmod. `.github/workflows/tests.yml:147-155` asserts that
`.github/scripts/bookkeeping_ci_scope.py` is not `100644`, and it **fails
open** — making it 100755 would not redden CI, it would permanently and
silently disable fast-lane selection while CI stays green. 12 of the 77
repo-wide non-executable shebang files live under `.github/scripts/`. The
successor scopes the change to two trees and treats any `.github/scripts/**`
change as an explicit non-goal.

Superseded 2026-08-20. Track the work at `08-20-ship-helper-exec-bit`.



## Goal

Make the pack's executable scripts carry the executable bit in the index, so a
source checkout can run them the same way an installed copy does.

## Problem

Measured 2026-08-19 in this checkout, counting only files whose first two bytes
are `#!`:

| Directory | Shebang scripts | Tracked `100644` | Tracked `100755` |
| --- | --- | --- | --- |
| `scripts/` | 36 | 30 | 6 |
| `templates/scripts/` | 27 | 23 | 4 |

The installed copies under the machine bin directory are `755` -- 25 of 27
entries, the two exceptions being the importable `*_lib.py` modules, which is
correct. So the same file is executable once installed and not executable in
the repository it ships from.

That is not cosmetic. The toolchain resolver execs the script it resolves, and
it prefers the repository copy:

```
$ bash scripts/sd-ai-command-pack-toolchain.sh run -- sd-ai-command-pack-review-preflight.mjs
scripts/sd-ai-command-pack-toolchain.sh: line 508: .../scripts/sd-ai-command-pack-review-preflight.mjs: Permission denied
```

Two hits so far, both during real work rather than testing: the housekeeping
script during the 2026-08-19 fleet audit campaign, and the review preflight
during the 08-08 publish flow. Both were worked around by hand -- invoking the
installed copy in the first case, `node <path>` in the second. A documented
command in a skill file failing on a fresh clone is the actual defect; the
workarounds are why it has stayed invisible.

## What is not yet known

Nothing in `install.py` or `sd-ai-command-pack-toolchain.sh` calls `chmod`, so
where the installed `755` comes from is unestablished. Find that before
changing anything: if the installer derives the bit from something other than
the source mode, fixing the index alone may not be the whole fix.

`scripts/sd-ai-command-pack-thin-resweep.py:570` already discusses
`core.fileMode=false` making the working tree and the index disagree about the
executable bit. Read it first -- it is the closest existing evidence about how
this repository handles the bit, and it may explain how 53 files drifted.

## Requirements

- Every shipped script meant to be executed carries `100755` in the index, and
  every importable module stays `100644`. Decide the classification from the
  shebang and from whether anything imports the file, not from a hand-written
  list.
- `templates/**` and its root mirror agree, since the template is the source of
  truth for shipped payload (`AGENTS.md:36`).
- The toolchain's exec path works from a fresh clone with no install step, for
  every script a skill file tells a reader to run that way.
- A test or check keeps the modes from drifting again. A mode is invisible in a
  diff review, so this needs a gate rather than care.
- Establish where the installed `755` originates, and state whether the index
  fix is sufficient or the installer also needs a change.

## Acceptance criteria

- [ ] `git ls-files -s scripts templates/scripts` reports no `100644` entry
      whose first two bytes are `#!`, except files established as importable
      modules, which are enumerated with their reason.
- [ ] `bash scripts/sd-ai-command-pack-toolchain.sh run -- <script>` succeeds
      from a clean clone for the two scripts that failed on 2026-08-19, and for
      every other script a skill file documents running that way.
- [ ] A check fails when a shebang-carrying shipped script is added or changed
      to `100644`.
- [ ] `make check` passes, including template/root mirror verification.

## Out of scope

- Consumer checkouts. This is the pack's own index.
- Changing how the toolchain resolves a script; only the mode is wrong.
