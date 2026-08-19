# Shipped executable scripts are tracked non-executable

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
