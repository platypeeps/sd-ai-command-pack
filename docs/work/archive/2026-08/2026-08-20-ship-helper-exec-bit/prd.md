---
title: Ship the executable bit for pack helper scripts
status: done
created: 2026-08-20
branch: feat/ship-helper-exec-bit
---
# Ship the executable bit for pack helper scripts

Absorbs `08-19-shipped-scripts-tracked-non-executable` and
`08-18-toolchain-run-non-executable-helper`. Both are folded in whole; their
requirements and acceptance criteria are carried forward below, with three
corrections recorded under "Corrections to the absorbed records".

## Goal

Make the pack's one documented way to reach a helper — `toolchain.sh run --` —
work in the pack's own checkout, which is the only place its maintainers ever
run it, by tracking shipped helpers with the executable bit they already ship
with everywhere else.

## Problem

The same file is executable once installed and non-executable in the repository
it ships from. Measured in this checkout on 2026-08-20, counting only tracked
files whose first two bytes are `#!`:

| Tree | shebang files | `100644` | `100755` |
| --- | --- | --- | --- |
| `scripts/` | 36 | 30 | 6 |
| `templates/scripts/` | 27 | 23 | 4 |

Excluding the four importable `*_lib.py` modules (two per tree), **50 tracked
files carry a shebang and no executable bit**: 21 under `templates/scripts/`,
21 root mirrors of those, 7 repository-only fleet helpers with no template
twin, and one third tracked copy under `.sd-ai-command-pack/bin/`.

### The third tracked copy

`manifest.json` maps one source to **two** targets:
`templates/scripts/sd-ai-command-pack-review-layout.py` installs to both
`scripts/sd-ai-command-pack-review-layout.py` and
`.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py`, both
`install: always`. All three are tracked `100644` with the same blob
`8353b63c` and a `#!` first line.

That second target is outside every `FAMILIES` prefix in
`installer/machinepayload.py:51-55`, so `family_for_target` returns `None` for
it and it never enters the machine payload. It is installed **only** by
`installer/fileops.py:427` `source_is_executable(source)` — the one path that
reads the template's mode. It is classified `CONSUMER_CONFIG`
(`.github/scripts/partition-surfaces.py:130`), so it is committed in consumer
repositories, and it is documented as directly invoked:
`templates/docs/SD_AI_COMMAND_PACK.md:139-141` — "**Call this one from a
repository's own guards.**"

A `644` file a consumer is told to call directly is the same defect this task
exists to fix, one tree over.

Meanwhile every generated and installed copy is `755`. `plugins/sd/bin` tracks
26 × `100755` / 2 × `100644`; `plugins/sd/machine-payload/scripts` tracks
25 × `100755` / 2 × `100644`; `~/.agents/bin` matches. The two `100644` entries
in each are the `*_lib.py` modules, which is correct.

`run` execs the file it resolves:

```text
scripts/sd-ai-command-pack-toolchain.sh:508: exec "$RUN_COMMAND" "$@"
```

and `resolve_pack_script_operand` (`:60`) prefers the copy next to the
toolchain. Inside the pack's own repository that is `scripts/`, so the one
tree with the wrong mode is the one tree that answers.

Reproduced 2026-08-20:

```text
$ bash scripts/sd-ai-command-pack-toolchain.sh run -- \
    sd-ai-command-pack-review-preflight.mjs --help
scripts/sd-ai-command-pack-toolchain.sh: line 508:
<checkout>/scripts/sd-ai-command-pack-review-preflight.mjs: Permission denied
```

21 of the 25 shipped non-library helpers fail this way. The 4 that work are
exactly the 4 already tracked `100755`
(`record-session.py`, `review-full-check.sh`, `toolchain.sh`, `work-loop.py`).

Two hits during real work, both worked around by hand rather than reported:
`housekeeping.sh` during the 2026-08-19 fleet audit campaign (worked around by
invoking the installed copy) and `review-preflight.mjs` during the 08-08
publish flow and again during `08-17-plugin-path-version-split`'s own
pre-archive gate (worked around with `node <path>`). A documented command in a
shipped skill failing on a fresh clone is the defect; the workarounds are why
it stayed invisible through eleven review rounds and a green CI run.

### Why nothing caught it

`tests/test_script_sibling_resolution.py:417-418` builds a synthetic helper and
chmods it `0o755` before exercising `run --`. The suite therefore cannot
observe the real tree's `644` — it asserts the resolver, never the mode of the
thing resolved. `run_pack_source_drift_gates`
(`scripts/sd-ai-command-pack-full-check.sh:611`) compares each manifest target
to its template twin with `source.read_bytes() != target.read_bytes()`, which
is blind to modes by construction.

### Root cause: two independent derivations of one bit

- `installer/fileops.py:427` — `executable = source_is_executable(source)`.
  This is the repo-install path (`make sync` = `install.py . --force`,
  `Makefile:38`), so it carries the **template's** mode forward verbatim.
- `installer/machinepayload.py:99-100` — `entry_is_executable` derives the bit
  from the destination family plus a `sd_ai_command_pack_` name prefix and
  ignores the source mode entirely, deliberately, so the machine-payload digest
  survives checkouts that lost their mode bits.
- `.github/scripts/generate-plugin.py:438` — a third site, using the same
  derived rule as machine payload.

So the machine payload ships `755` everywhere *except* the pack's own checkout,
which is the single place where the source mode is authoritative and the single
place `run --` resolves. One bit, two rules, disagreeing in exactly one tree.

## Requirements

1. `bash "$SD_PACK_TOOLCHAIN" run -- <helper>` runs the helper from the pack's
   own checkout for every shipped helper, or fails with a message naming the
   file and the missing property.
2. Every shipped script meant to be executed carries `100755` in the index, and
   every importable module stays `100644`. The classification is derived from a
   rule that already exists in the codebase, not from a hand-written list, and
   every file the rule treats as an exception is enumerated with its reason.
3. Every tracked copy of a shipped script agrees on the mode, not only on the
   bytes — `templates/scripts/**`, its `scripts/**` mirror, and the third
   `.sd-ai-command-pack/bin/` copy. `templates/**` remains the source of truth
   (`AGENTS.md:36`).
4. Behaviour from `~/.agents/bin`, from `plugins/sd/bin`, and from an existing
   consumer checkout is unchanged. Those paths work today and must keep
   working. The one deliberate exception is
   `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py`, which a
   **fresh** consumer install will write `755` where it wrote `644`; that is a
   fix, not a regression, and it is bounded and stated in `design.md`.
5. The fix is one change in one place. The 14 authored `run --` sites that name
   a pack helper are unchanged; a per-site workaround re-creates the drift that
   `08-17-plugin-path-version-split` removed.
6. A gate fails when a shebang-carrying shipped script is added or changed to
   `100644`. A mode is invisible in diff review, so this needs a check rather
   than care. The gate enumerates from `git ls-files -s`, so a script added
   later is covered without editing the gate.
7. Every ledger, digest, and release artifact that reads the changed modes is
   identified and brought back into agreement in the same change.

## Constraints

- **No repository-wide chmod.** `.github/workflows/tests.yml:154` asserts
  `[ "$classifier_mode" != "100644" ]` on
  `.github/scripts/bookkeeping_ci_scope.py` and, on mismatch, calls
  `select_full "prior_classifier_unsafe"`. That **fails open**: making the
  classifier `100755` would not redden CI, it would silently and permanently
  disable fast-lane selection. 12 of the 77 repo-wide non-executable shebang
  files live under `.github/scripts/`; none of them are in scope.
- The change must be mode-only. No content edit to any shipped script.
- `core.fileMode` is `true` in this checkout, so the working tree and the index
  agree; the fix must not depend on that being true elsewhere, which is why the
  gate reads the index (`git ls-files -s`) rather than the filesystem.

## Acceptance criteria

- [ ] `git ls-files -s scripts templates/scripts .sd-ai-command-pack/bin`
      reports no `100644` entry whose first two bytes are `#!`, and no
      `100755` entry whose basename starts with `sd_ai_command_pack_`. The
      importable modules are enumerated in `design.md` with their reason.
      Baseline today: 50 offending entries.
- [ ] `run --` reaches every shipped helper from a clean checkout of this
      repository, enumerated from `git ls-files templates/scripts` rather than
      from a list in a test. Baseline today: 21 of 25 report
      `Permission denied`.
- [ ] The same enumeration passes when driven through
      `~/.agents/bin/sd-ai-command-pack-toolchain.sh`, before and after the
      change. (`make sync` is `install.py . --force` and is repo-scoped;
      `~/.agents/bin` is populated by the machine-payload install, whose modes
      are derived and therefore already correct. This criterion is a
      no-regression check on that path, not a repair of it.)
- [ ] The two scripts that failed on 2026-08-19 (`housekeeping.sh`,
      `review-preflight.mjs`) succeed from the checkout and from
      `~/.agents/bin`.
- [ ] A check fails when a shebang-carrying shipped script is added or changed
      to `100644`, and that check runs in both `make check` and CI.
- [ ] `docs/fleet/candidate-validation.json` `payloadDigest` matches
      `filesystem_payload_digest(manifest.json)` after the change.
- [ ] A consumer checkout is verified read-only and unchanged, per the fleet
      per-lane cleanliness rule: `git status --porcelain` empty before and
      after, and the consumer's tracked mode for
      `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py` recorded so
      the fresh-install effect in Requirement 4 is measured rather than
      assumed.
- [ ] `make check` passes, including template/root mirror verification and the
      release payload gate.
- [ ] The 14 authored `run --` sites are unchanged, shown by a content diff
      (`git diff --numstat`) over the authored trees, not only by
      `git diff --summary`, which is silent on pure content edits.

## Corrections to the absorbed records

Three claims in the absorbed PRDs are wrong or unresolved. `design.md` must
address each explicitly; they are recorded here so the corrected facts survive
in the requirements record.

1. **The cost claim in `08-18` is false.** That PRD argues a mode-only change
   "does not move the payload digest and does not stale the fleet ledger",
   citing `installer/machinepayload.py:90`. That citation is about the
   *machine-payload* digest, which is indeed mode-independent. The **fleet
   candidate** digest is not: `scripts/sd_ai_command_pack_fleet_lib.py:792-795`
   sets `executable=bool(mode & (S_IXUSR|S_IXGRP|S_IXOTH))` from the filesystem
   and `:778` folds it into the hash. Measured: the digest moves from
   `sha256:c4f9c34417673bfdd614a793b1605fd34a84307b710953332832cecec148be35`
   (current, and equal to the recorded `payloadDigest`) to
   `sha256:d458b3d63faa9698b6798f81964301eb9cd536ad15b79510b1aea0521f53b5d0`
   after the chmod. The candidate ledger **will** go
   stale and must be regenerated. The cost asymmetry `08-18` used to prefer the
   modes fix over the dispatch fix does not exist; the choice must be re-argued
   on other grounds.
2. **Scope, not sweep.** `08-19`'s "decide the classification from the shebang"
   phrasing reads as a repository-wide rule. It is not one — see the
   fail-open CI constraint above. Scope is `templates/scripts/**`, the named
   `scripts/**` files, and the single `.sd-ai-command-pack/bin/` copy; a
   repository-wide sweep is an explicit non-goal.
3. **`sd-ai-command-pack-shell-lib.sh` needs a recorded decision.** It is
   sourced and never executed (`housekeeping.sh:73`, `full-check.sh:84`,
   `review-scope.sh:54`), yet it already ships `100755` from all three
   generators because the library rule matches only the underscore-prefixed
   form. `644` diverges from the installed copy; `755` diverges from
   "importable things stay `644`". `design.md` picks one, justifies it, and
   records it — `08-19`'s acceptance criteria require the enumeration with
   reasons.

## Out of scope

- Repairing modes inside existing consumer checkouts. This is the pack's own
  index. Existing consumers keep whatever mode they have — the installer's
  `UNCHANGED` short-circuit (`installer/fileops.py:465-474`) returns before any
  `chmod` when the bytes already match — so nothing reaches back into them.
- Any `.github/scripts/**` mode change, for the fail-open reason above.
- Changing how the toolchain resolves a script. Only the mode is wrong. The
  bootstrap preferring the checkout copy inside the pack's own repository is
  correct — it is the version under test.
- The bootstrap's `[ -f ]`-versus-`[ -r ]` predicate, deferred from `#503`. It
  would require re-touching all 84 bootstrap sites, which this change does not.
- `run-python` (`toolchain.sh:519`), which execs the interpreter with the script
  as an argument and never consults the bit.
- Renaming `sd-ai-command-pack-shell-lib.sh` to the underscore-prefixed library
  form. That is a payload rename touching every source site and every generator
  rule; see `design.md` for why it is declined here.

## Evidence

- `git ls-files -s scripts templates/scripts .sd-ai-command-pack/bin`,
  filtered to `#!` first bytes: 50 × `100644` outside the `*_lib.py` modules.
- `manifest.json`: one source, two targets for `review-layout.py`; three
  tracked copies, all blob `8353b63c`, all `100644`.
- `scripts/sd-ai-command-pack-thin-resweep.py:565-586` `executable_bits_digest`,
  which digests `os.access(X_OK)` over every tracked file.
- `git ls-files -s plugins/sd/bin`: 26 × `100755`, 2 × `100644`.
- `ls -l ~/.agents/bin/sd-ai-command-pack-shell-lib.sh` → `755`;
  `~/.agents/bin/sd_ai_command_pack_lib.py` → `644`.
- `scripts/sd-ai-command-pack-toolchain.sh:508`, the `run` case.
- `installer/fileops.py:427`; `installer/machinepayload.py:99-100`;
  `.github/scripts/generate-plugin.py:438`.
- `scripts/sd_ai_command_pack_fleet_lib.py:778,792-795`;
  `.github/scripts/release_identity.py:238-244`.
- `.github/workflows/tests.yml:154`.
- `tests/test_script_sibling_resolution.py:417-418`.
- The failing transcripts above, and the recorded disposition in the archived
  `08-17-plugin-path-version-split` PRD's Out of scope.
