# Design — ship the executable bit for pack helper scripts

## Authoring boundary

`templates/**` is the source of truth (CONTRIBUTING, "Release And Payload
Rules"). Every shipped script exists in at least four copies:

```
templates/scripts/<name>                        <- edit here
scripts/<name>                                  <- `make sync` (install.py . --force)
plugins/sd/bin/<name>                           <- `make generate`
plugins/sd/machine-payload/scripts/<name>       <- `make generate`
```

This task is unusual for the pack in that **it changes no bytes**. The four
copies stay byte-identical throughout; only the tracked mode moves, and only
in the three trees named under Scope.
That distinction drives most of what follows: the mirror gate compares bytes and
is blind to the change, while two payload digests read modes and are not.

The 7 repository-only fleet helpers (`sd-ai-command-pack-fleet-*.py`) have no
template twin — they are dev tooling, not payload — so they exist in one copy
and participate in no mirror.

**One script has a fifth copy.** `manifest.json` maps
`templates/scripts/sd-ai-command-pack-review-layout.py` to *two* targets, both
`install: always`: `scripts/<name>` and `.sd-ai-command-pack/bin/<name>`. All
three tracked copies carry blob `8353b63c` and mode `100644`. The second target
matches no `FAMILIES` prefix (`installer/machinepayload.py:51-55`), so
`family_for_target` returns `None`, it never enters the machine payload, and it
is installed **only** through `installer/fileops.py:427`
`source_is_executable(source)` — the single path that reads the template's
mode. This asymmetry is why it needs its own decision below, and why it
falsifies the naive "consumers are unaffected" claim.

## The choice: modes, not dispatch

`08-18` offered two candidates and preferred the modes fix on a cost argument
that does not hold (PRD, "Corrections", item 1). The modes fix is still the
right one, on three grounds that are actually true.

**Correctness.** `run` is `exec "$RUN_COMMAND" "$@"` and the operand is a
program with a shebang. `100755` asserts a fact about these files that is
already true everywhere else they exist: three independent generators
(`installer/machinepayload.py:99`, `.github/scripts/generate-plugin.py:438`,
and the machine-install path) each conclude "executable" for exactly this set.
The checkout is the outlier, and the fix is to stop being one. The dispatch fix
instead teaches `run` to work around a mode that should not be wrong, and
leaves the mode wrong for every *other* consumer of these files — a
`./scripts/sd-ai-command-pack-check.py` typed by hand still fails.

**One-time versus per-invocation.** The modes fix is 50 index entries changed
once, guarded by a gate. The dispatch fix adds an extension→interpreter table
inside the single funnel every helper invocation passes through, needs a
defined failure for an unknown extension, and must keep agreeing with the
shebang lines forever. It converts a one-time data fix into permanent code.

**Consumer benefit.** A consumer checkout that runs `install.py` receives
`755` today from the machine-payload path, so the dispatch fix buys consumers
nothing. The modes fix additionally repairs the repo-install path
(`installer/fileops.py:427`), which is the one that serves the pack's own tree
and any future source-mode-derived destination.

The dispatch fix would be correct if a helper existed with no usable shebang.
None does — the enumeration in `implement.md` step 1 confirms all 50 start
`#!`. Do not implement both.

## The cost the absorbed record missed

`08-18`'s claim that a mode-only change is digest-free is confined to the
machine-payload digest. Three other computations read the mode, and the design
must account for all three.

| Site | Reads | Moves? |
| --- | --- | --- |
| `installer/machinepayload.py:99` `entry_is_executable` | destination family + name prefix | **No** — derived, by design |
| `.github/scripts/generate-plugin.py:438` | same derived rule | **No** |
| `scripts/sd_ai_command_pack_fleet_lib.py:792-795` `filesystem_payload_digest` | `st_mode & (S_IXUSR\|S_IXGRP\|S_IXOTH)` on the manifest source | **Yes** |
| `.github/scripts/release_identity.py:238-244` `payload_digest_at_commit` | git tree mode, `executable = mode == "100755"` | **Yes** |
| `scripts/sd-ai-command-pack-thin-resweep.py:565-586` `executable_bits_digest` | `os.access(X_OK)` over every tracked file | **Yes, in a consumer, on a fresh install** — see Compatibility |

`manifest.json` sources are `templates/**` paths (739 entries), so chmodding
`templates/scripts/**` moves both digests that read modes. Measured:

```
before  sha256:c4f9c34417673bfdd614a793b1605fd34a84307b710953332832cecec148be35
after   sha256:d458b3d63faa9698b6798f81964301eb9cd536ad15b79510b1aea0521f53b5d0
```

The "before" value equals the `payloadDigest` recorded in
`docs/fleet/candidate-validation.json`, which is fresh as of today. So the
ledger goes stale and **must** be regenerated.

There is a second, larger consequence. `run_pack_source_drift_gates`
(`scripts/sd-ai-command-pack-full-check.sh:611`) builds `changed_paths` from
`git diff --name-only`, which reports a mode-only change as a changed path.
Any path under `templates/` lands in `payload_changed`, and `payload_changed`
without a manifest version bump fails the gate. So a mode-only change carries
the **full release payload obligation**: `manifest.json` version bump,
`CHANGELOG.md` entry, and `make release-prep`. That is the honest cost, and it
is the same cost the dispatch fix would have carried. Both candidates pay it;
the asymmetry `08-18` relied on never existed.

`plugins/**` is regenerated but its modes are derived, so `make generate`
produces a byte- and mode-identical tree. That is worth verifying rather than
assuming (`implement.md`, check E).

## Scope: three trees, never the repository

The rule "a shebang implies `100755`" is true of shipped helpers and **false**
of this repository as a whole. `.github/workflows/tests.yml:147-155` reads the
prior revision's mode for `.github/scripts/bookkeeping_ci_scope.py` and treats
anything other than `100644` as untrusted:

```
if [ "$classifier_mode" != "100644" ] || ... ; then
  select_full "prior_classifier_unsafe"
fi
```

`select_full` is the *fallback*, not a failure. A `100755` classifier would
therefore turn every subsequent run into a full-lane run, permanently and
silently — CI stays green while the fast lane it guards stops existing. 12 of
the 77 repo-wide non-executable shebang files sit under `.github/scripts/`.

The mode is load-bearing there in the opposite direction, which is precisely
the "verify first that no gate reads the modes it changes" caveat `08-18`
raised and did not discharge. It is discharged here: enumerate the mode
readers, and scope the change to the three trees none of them constrain.

In scope, exactly 50 index entries across three trees:

- `templates/scripts/**` — 21 files, listed in `implement.md` step 2.
- `scripts/**` — the 21 mirrors of those, plus 7 repository-only fleet
  helpers: `sd-ai-command-pack-fleet-{candidate-check,controller,
  finding-classify,preflight,review-classify,timing,wave-plan}.py`.
- `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py` — one file.

Explicit non-goal: a repository-wide sweep, or any `.github/scripts/**` mode
change.

### Decision: `.sd-ai-command-pack/bin/` is **in** scope

The argument that settles it is that **excluding it does not avoid the
consumer-side effect.** The effect is caused by chmodding the *template*, which
step 2 must do for `scripts/` to work at all: once
`templates/scripts/sd-ai-command-pack-review-layout.py` is `755`,
`source_is_executable` returns `True` and every fresh consumer install writes
*both* targets `755`, whatever the pack's own third copy says. So the choice is
not "consumer change or no consumer change" — it is only whether the pack's own
checkout is consistent with what it installs.

Leaving it `100644` would put the same shipped file at `100755` in two tracked
trees and `100644` in a third, and — because of the `UNCHANGED` short-circuit —
the pack's own checkout would never self-heal. That is this task's own root
cause, reproduced inside the task that fixes it.

It is also the copy that most needs the bit. It is `CONSUMER_CONFIG`
(`.github/scripts/partition-surfaces.py:130`), committed in consumer
repositories, and the shipped documentation tells readers to run it directly:
`templates/docs/SD_AI_COMMAND_PACK.md:139-141`, "**Call this one from a
repository's own guards.**" A guard invoking a `644` file fails exactly the way
`run --` does.

The gate's enumeration therefore covers all three trees, and the baseline moves
from 49 to 50.

## The classification rule, and `shell-lib.sh`

**Decision: `templates/scripts/sd-ai-command-pack-shell-lib.sh` and its mirror
are tracked `100755`.**

The evidence, first. It is sourced and never executed —
`sd-ai-command-pack-housekeeping.sh:73`, `sd-ai-command-pack-full-check.sh:84`,
`sd-ai-command-pack-review-scope.sh:54`, each via
`local lib="$SCRIPT_DIR/sd-ai-command-pack-shell-lib.sh"` and a `.` — and no
authored `run --` site names it. On a naive reading of "importable things stay
`644`" it should be `644`.

But the pack already ships it `755`, from every generator, because the rule
those generators implement is not "sourced or importable" — it is
`LIBRARY_PREFIX = "sd_ai_command_pack_"`
(`installer/machinepayload.py:29,100`; the same constant restated at
`.github/scripts/generate-plugin.py:182,438`). The hyphenated name does not
match, so `~/.agents/bin/sd-ai-command-pack-shell-lib.sh` is `755`,
`plugins/sd/bin/sd-ai-command-pack-shell-lib.sh` is `100755`, and the
machine-payload copy is `100755`. Verified.

Three reasons to follow that rather than fight it:

1. **This task exists because one bit had two derivations.** Introducing a
   second, conflicting classification rule — "hyphenated but sourced, so
   `644`" — would re-create the exact defect being fixed, in the exact file
   where the two rules disagree. The gate must reuse `LIBRARY_PREFIX`, not
   invent a predicate beside it.
2. **`644` makes the checkout the sole outlier again.** It would leave one file
   whose repository mode contradicts all three shipped copies, and would force
   the new gate to carry a hand-written exception whose only justification is a
   naming convention the shipping rules do not implement. `08-19` explicitly
   asked for classification "from the shebang and from whether anything imports
   the file, not from a hand-written list"; a one-file exception list is that
   hand-written list.
3. **`755` on a sourced file costs nothing.** `source` ignores the mode
   entirely. And direct execution is harmless: the file's only top-level
   statements are the `REVIEW_SCAN_EXCLUDE_DIRS` array assignment (lines 11-39)
   and function definitions — the embedded Python at :78-121 is inside a
   heredoc. Running it directly defines some functions in a subshell and exits
   `0`. There is no side effect to guard against.

The exceptions, then, are exactly the four files whose basename starts with
`LIBRARY_PREFIX`, and they stay `100644`:

| File | Reason |
| --- | --- |
| `scripts/sd_ai_command_pack_lib.py` | Python module, imported by shipped helpers; never has a `__main__` entry point |
| `scripts/sd_ai_command_pack_fleet_lib.py` | same, fleet side |
| `templates/scripts/sd_ai_command_pack_lib.py` | template twin of the above |
| `templates/scripts/sd_ai_command_pack_fleet_lib.py` | template twin of the above |

These four already ship `644` from every generator, so the checkout and the
shipped copies agree once the other 50 are corrected. Every file in the three
trees is then covered by one rule with zero exceptions beyond the rule itself.

### Declined: rename `shell-lib.sh` to the underscore form

Renaming to `sd_ai_command_pack_shell_lib.sh` would make the naming convention
and the sourced/executed distinction agree, and would flip the file to `644`
everywhere without a special case. Declined: it is a payload rename touching
every `source` site across all copies, the shellcheck `source=` directives, the
`references.py` closure entries (`plugins/sd/installer/references.py:216,255`),
`pr-body-scope.py:319`, and the installed usage guide — a content change, in a
task whose whole property is that it changes no content. Recorded so it is not
re-derived; file it separately if the convention is ever worth the churn.

### Declined: collapse the duplicate `LIBRARY_PREFIX`

`.github/scripts/generate-plugin.py:182` restates the constant that
`installer/machinepayload.py:29` defines, even though the same file already does
`sys.path.insert(0, PACK_ROOT)` and imports from `installer` at :105-108. Two
copies of the constant is one more than needed and is the same class of defect
as the one this task fixes. Declined anyway: the two copies agree today,
collapsing them is a code change in a mode-only task, and the risk of touching
the plugin generator here outweighs the tidiness. The **new gate must import
the constant rather than restate it**, so the count stays at two and does not
become three.

## The gate

New: `.github/scripts/check-shipped-script-modes.py`, sitting beside
`check-helper-resolution.py` and `check-shipped-script-coverage.sh`.

Contract:

- Enumerate from
  `git ls-files -s scripts templates/scripts .sd-ai-command-pack/bin`. Reading
  the
  **index**, not the filesystem, is deliberate: `core.fileMode` is `true` here
  but a checkout with it disabled would let the filesystem and the index
  disagree — the drift mechanism `sd-ai-command-pack-thin-resweep.py:570`
  already documents. The index is what ships.
- Classify by content, not by name or extension: a file is a script when
  `git cat-file blob <oid> | head -c2` is `#!`.
- Expect `100755` unless the basename starts with `LIBRARY_PREFIX`, imported
  from `installer.machinepayload`.
- Fail with the offending `mode path` lines, and name the repair
  (`git update-index --chmod=+x <path>`).
- Also fail on the inverse: a `LIBRARY_PREFIX` file tracked `100755`. The
  invariant is two-sided or it does not hold.

Wired into `Makefile` beside `check-helper-resolution.py` (`Makefile:54`) and
into `.github/workflows/tests.yml` beside its run at `:472`, plus the `ruff`
and `mypy` argument lists at `Makefile:65-66` and `tests.yml:577,584`, which
enumerate `.github/scripts/*.py` by hand. Missing one of those four lists is the
likeliest incomplete-wiring failure, and it is silent — the invariant holds
either way once repaired. `implement.md` check G catches it by expanding
`make -n check` (`check: test lint audit full-check`, `Makefile:106`) and
requiring the same 3-and-3 count a correctly-wired sibling gate scores today.

**Why a gate and not a test.** `tests/test_script_sibling_resolution.py`
constructs its fixtures and chmods them (`:417-418`), so it can only ever
assert the resolver's behaviour on a well-formed tree. The invariant here is a
property of the *real* index, which a synthetic-fixture test structurally
cannot observe. A test is added too — one that exercises `run --` against the
actual `scripts/` tree — but the enumerating gate is the load-bearing half.

## Contracts that must not move

- `run --` semantics for non-pack operands. `resolve_pack_script_operand`
  (`toolchain.sh:50-61`) returns early for anything containing `/` or not
  matching `sd-ai-command-pack-*`/`sd_ai_command_pack_*`, so `run -- gh pr view`
  and `run -- node <script>` pass through untouched. Both forms are authored
  (`templates/.agents/skills/sd-help/references/pack-helper-resolution.md`) and
  both are unaffected by a mode change. The functional check must not treat a
  non-pack operand as in scope.
- The 14 authored `run --` sites that name a pack helper stay byte-identical.
- `run-python` (`toolchain.sh:519-524`) execs the interpreter with the script as
  an argument and never consults the bit. Unchanged, and not a fallback this
  task introduces.
- The four already-`100755` templates (`record-session.py`,
  `review-full-check.sh`, `toolchain.sh`, `work-loop.py`) and the two
  additional already-`100755` repo-only scripts (`fleet-publish.py`,
  `thin-resweep.py`) are already correct and are not touched.

## Compatibility and rollout

**Consumers are unaffected — with exactly one stated exception.** Everything
that reaches a consumer through `installer/machinepayload.py` is unaffected:
`entry_is_executable` ignores the source mode, those files are `755` before and
`755` after, and the machine-payload digest does not move.

The exception is `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py`,
the one target outside every payload family. It is installed by
`installer/fileops.py:427` from the template's mode, so:

- **A fresh consumer install writes it `755` where it previously wrote `644`.**
  It is `CONSUMER_CONFIG` and committed in consumer repositories. Measured
  2026-08-20 across `docs/fleet/consumers.json`: all **eight** consumers track
  it `100644` today and all eight are clean, so this is a real, visible
  one-line mode change in eight downstream repositories on their next clean
  install.
- **`thin-resweep`'s executable-bit digest moves with it.**
  `executable_bits_digest` (`scripts/sd-ai-command-pack-thin-resweep.py:565-586`)
  digests `os.access(X_OK)` over *every tracked file*, so a consumer that
  installs this file at `755` gets a different digest. The earlier claim that
  the surface digest is stable is true only for the machine-payload files, and
  is corrected here.

**The honest bound.** This lands on **fresh installs only**. An existing
consumer whose bytes already match hits the `UNCHANGED` short-circuit
(`installer/fileops.py:465-474`), which returns before any `chmod`, so it keeps
`644` until something rewrites the file. Nothing in this change reaches back
into an existing consumer checkout.

**And it is a fix, not a regression.** The shipped documentation tells consumers
to call this file directly from their own guards
(`templates/docs/SD_AI_COMMAND_PACK.md:139-141`); shipping it non-executable was
the same defect as the one in `scripts/`. The correct disposition is to accept
the change, state it in the CHANGELOG, and let the fleet's own candidate
validation observe it — not to suppress it by leaving the template at `644`,
which would abandon the task.

**`make sync` will not do this for you.** `installer/fileops.py:465-474`
returns `UNCHANGED` when the destination bytes already match the source and
returns *before* any `chmod`; the mode is only applied by `atomic_write_bytes`
(`:120`) on a real write. Since this task changes no bytes, running `make sync`
after chmodding `templates/` would leave `scripts/` — and
`.sd-ai-command-pack/bin/` — at `644`. All three trees are therefore chmodded
explicitly, and `make sync` is run afterwards only to prove byte-parity. (That the installer never repairs a drifted destination mode is a
latent defect in its own right; it is out of scope here, and noted so it is not
mistaken for this task's failure.)

**One PR, one revert point.** Ordering matters: chmod all three trees, then
`make generate` and assert a strict zero plugin diff **before** the manifest
version bump (the bump itself rewrites
`plugins/sd/.claude-plugin/plugin.json` via `render_plugin_manifest(version)`,
`.github/scripts/generate-plugin.py:452-454,471-478`, so a
zero-diff assertion taken after the bump would fire falsely), then bump, then
`make release-prep` last so no later edit invalidates the ledger it writes.

**Rollback** is `git revert -m 1 <merge-sha>`. The `-m 1` is required, not
optional: `sd-ai-command-pack-housekeeping.sh` defaults to
`--merge-strategy merge` (`:16`), so the landing commit is a true merge commit
and a bare `git revert` errors out on it. A mode revert is complete —
there are no migrations, no persistent state, no consumer-side writes, and no
content to reconcile. The one thing a revert must not miss is the regenerated
`docs/fleet/candidate-validation.json` and the manifest version bump, which
travel in the same commit and therefore revert with it.

**Risk if the gate is wired incompletely.** The failure mode is silent: the
invariant holds today because it was just repaired, so a gate that never runs
looks identical to a gate that passes. `implement.md` check D mutates a file to
`100644` and requires the gate to fail, which is the only check that
distinguishes the two.
