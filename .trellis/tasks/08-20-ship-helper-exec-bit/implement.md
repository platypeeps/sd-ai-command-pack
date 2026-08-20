# Implementation plan — ship the executable bit for pack helper scripts

Mode-only change: no shipped script's bytes move. Chmod all **three** tracked
trees explicitly — `make sync` will not propagate a mode when the bytes already
match (`design.md`, "Compatibility and rollout").

Record these baselines **before** any edit; they are what the after-state is
compared against.

- Check A (static index, two-sided) → **50 NOT-EXEC**, **0 LIB-EXEC**.
- Check B (functional `run --` sweep) → **21 DENIED** of 25, 0 MISSING,
  0 BROKEN.
- Check B2 (same sweep via `~/.agents/bin`) → **0** of every label. This path is
  already correct; B2 is a no-regression check, not a repair.
- Check F2 (authored `run --` sites) → **14**.
- Check I (consumer cleanliness) → **measured 2026-08-20: all 8 consumers
  `dirty=0`, all `mode=100644`** for
  `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py`
  (rwbp-coordinator, loadsmith, hoa-manager, rwbp-website, mezmo_benchmark,
  se-ai-command-pack, sd-github-review, anomaly-metric-creator). Re-run and
  confirm unchanged after.
- `.venv/bin/python -m unittest tests.test_script_sibling_resolution` → note the
  `Ran N tests … OK` line.
- `git rev-parse HEAD` → the revert point.

## 1. Confirm the enumeration before changing it

- [ ] Run check A. Confirm **50** NOT-EXEC lines and **0** LIB-EXEC lines, and
      confirm the split: 21 under `templates/scripts/`, 28 under `scripts/`
      (21 mirrors + 7 fleet-only), 1 under `.sd-ai-command-pack/bin/`.
- [ ] Confirm every one of the 50 blobs starts `#!` — the check already filters
      on this, so a count of 50 *is* the confirmation. This is what rules out
      the dispatch fix (`design.md`, "The choice").
- [ ] Confirm no path in the 50 lies outside those three trees. Any
      `.github/scripts/` path appearing here means the check was widened; stop
      (`design.md`, "Scope").

## 2. Chmod `templates/scripts/**` (21 files)

```
sd-ai-command-pack-audit-inventory.py     sd-ai-command-pack-review-layout.py
sd-ai-command-pack-audit-route.py         sd-ai-command-pack-review-learnings.py
sd-ai-command-pack-check.py               sd-ai-command-pack-review-local.py
sd-ai-command-pack-full-check.sh          sd-ai-command-pack-review-preflight.mjs
sd-ai-command-pack-housekeeping-result.py sd-ai-command-pack-review-scope.sh
sd-ai-command-pack-housekeeping.sh        sd-ai-command-pack-review.py
sd-ai-command-pack-install-audit.py       sd-ai-command-pack-shell-lib.sh
sd-ai-command-pack-pack-update.sh         sd-ai-command-pack-status.py
sd-ai-command-pack-pr-body-scope.py       sd-ai-command-pack-surface-check.py
sd-ai-command-pack-pr-eligibility.py      sd-ai-command-pack-update-spec-kb.py
sd-ai-command-pack-recovery-artifacts.py
```

- [ ] `chmod +x` each, then `git update-index --chmod=+x` each (or `git add`,
      since `core.fileMode=true` here — but stage the index bit explicitly so
      the change does not depend on that config).
- [ ] `sd-ai-command-pack-shell-lib.sh` is included deliberately. It is sourced,
      not executed, and goes to `100755` because `LIBRARY_PREFIX` is the rule
      the pack's three generators actually implement and all three already ship
      it `755`. See `design.md`, "The classification rule".
- [ ] Do **not** touch `templates/scripts/sd_ai_command_pack_lib.py` or
      `templates/scripts/sd_ai_command_pack_fleet_lib.py`.

**This step is what changes consumer behaviour**, via
`review-layout.py` → `installer/fileops.py:427`. Read `design.md`,
"Compatibility and rollout" before proceeding, and be able to state the bound:
fresh installs only, existing consumers keep `644`.

## 3. Chmod `scripts/**` (28 files)

- [ ] The 21 mirrors of step 2, same names.
- [ ] The 7 repository-only fleet helpers with no template twin:
      `sd-ai-command-pack-fleet-candidate-check.py`,
      `-controller.py`, `-finding-classify.py`, `-preflight.py`,
      `-review-classify.py`, `-timing.py`, `-wave-plan.py`.
- [ ] Do **not** touch `scripts/sd_ai_command_pack_lib.py` or
      `scripts/sd_ai_command_pack_fleet_lib.py`.

## 3b. Chmod the third tracked copy (1 file)

- [ ] `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py` →
      `100755`. Same source, same blob `8353b63c`, second `install: always`
      manifest target. Skipping it would leave the same shipped file at
      `100755` in two tracked trees and `100644` in a third — this task's own
      root cause, reproduced (`design.md`, "Decision: `.sd-ai-command-pack/bin/`
      is **in** scope").
- [ ] Re-run check A → **0 lines of either label**. This is the first review
      gate; do not proceed while it is non-zero.

## 4. Prove the fix functionally

- [ ] Run check B → **no DENIED, MISSING, or BROKEN lines**.
- [ ] Spot-check the two helpers that failed in production, by hand:

      ```
      bash scripts/sd-ai-command-pack-toolchain.sh run -- \
        sd-ai-command-pack-housekeeping.sh --dry-run --json
      bash scripts/sd-ai-command-pack-toolchain.sh run -- \
        sd-ai-command-pack-review-preflight.mjs --help
      ```

      **`--dry-run` is mandatory here.** `housekeeping.sh` defaults to
      `DRY_RUN=0` (`:9`), `AUTO_MERGE=1` (`:13`), and
      `MERGE_STRATEGY=merge` (`:16`); all three are opt-out, not opt-in.
      Invoked bare it fetches, prunes, pulls, cleans, and **merges an
      already-green open PR and deletes its remote branch** — in this
      repository, mid-task. Never run it without `--dry-run` as a smoke test.
      (Check B is unaffected: an unknown option exits `2` at
      `templates/scripts/sd-ai-command-pack-housekeeping.sh:250-254`, before
      any work.)
- [ ] Run the third copy the way the docs tell consumers to:
      `./.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py --help`
      (`templates/docs/SD_AI_COMMAND_PACK.md:139-141`). This fails before
      step 3b and succeeds after.
- [ ] Confirm non-pack operands still pass through:
      `bash scripts/sd-ai-command-pack-toolchain.sh run -- node --version` and
      `... run -- gh --version`. A mode change must not have reached
      `resolve_pack_script_operand`'s early return (`toolchain.sh:50-61`).
- [ ] Run check B2 → still 0 of every label from `~/.agents/bin`.

## 5. Add the gate

- [ ] New `.github/scripts/check-shipped-script-modes.py`, per `design.md`,
      "The gate": enumerate from
      `git ls-files -s scripts templates/scripts .sd-ai-command-pack/bin`,
      classify by `#!` first bytes, expect `100755` unless the **basename**
      starts with `LIBRARY_PREFIX`, fail two-sided, print the repair command.
- [ ] **Import** `LIBRARY_PREFIX` from `installer.machinepayload` (via the
      `sys.path.insert(PACK_ROOT)` pattern at
      `.github/scripts/generate-plugin.py:105-108`). Do not restate it — a third
      copy of the constant re-creates this task's own root cause.
- [ ] Match on `PurePosixPath(path).name`, not on a path substring. `LIBRARY_PREFIX`
      is a basename-prefix rule; a substring match would also exempt any future
      directory containing the string.
- [ ] Wire into `Makefile` beside `check-helper-resolution.py` (`Makefile:54`).
- [ ] Wire into `.github/workflows/tests.yml` beside its run at `:472`.
- [ ] Add the new file to **all four** hand-maintained tool argument lists:
      `Makefile:65` (ruff), `Makefile:66` (mypy), `tests.yml:577` (ruff),
      `tests.yml:584` (mypy). Missing one of these is the likeliest incomplete
      wiring; check G catches it.

## 6. Add the test

- [ ] Extend `tests/test_script_sibling_resolution.py` (or add
      `tests/test_shipped_script_modes.py`) with a case that runs `run --`
      against the **real** `scripts/` tree rather than a chmodded synthetic
      fixture. The existing fixtures at `:417-418` chmod `0o755` and therefore
      structurally cannot observe this defect — do not weaken that by adding
      another synthetic case and calling it coverage.
- [ ] Add a case for the gate itself: a tree with one shebang file at `100644`
      fails; a `LIBRARY_PREFIX` file at `100755` also fails.

## 7. Propagate, then take on the release payload obligations

**Order is load-bearing.** `make generate` writes
`plugins/sd/.claude-plugin/plugin.json` from `render_plugin_manifest(version)`
(`.github/scripts/generate-plugin.py:452-454,471-478`) with `version` read from
`manifest.json` (`:421`). Both files read `0.71.35` today, so bumping the
manifest **guarantees** a `plugins/**` diff on the next generate. A strict
zero-diff assertion must therefore be taken *before* the bump, or it fires
falsely. **The choice taken here is to reorder** — assert strictly first, then
bump, then re-assert with a narrowly scoped check.

### 7a. Generate and assert strictly — before any version edit

- [ ] `make generate`.
- [ ] Run check E → **strict zero** `plugins/**` diff. This is the real test of
      the derived-mode claim: plugin modes come from
      `generate-plugin.py:438` (`not name.startswith(LIBRARY_PREFIX)`), not from
      the source, so a mode-only change upstream must produce nothing here. A
      diff at this point means a generator reads the source mode after all;
      stop and re-derive.

### 7b. Bump the payload version

`templates/scripts/**` changes — even mode-only — land in `payload_changed`,
because `run_pack_source_drift_gates` builds that set from
`git diff --name-only` (`scripts/sd-ai-command-pack-full-check.sh:749-767`),
which reports mode-only changes. The `Release payload gate` CI job
(`.github/workflows/tests.yml:641`) will fail `CI Result` without these.

- [ ] Bump `manifest.json` `version` (patch — no behavior change to shipped
      content; the fix is that the shipped content becomes reachable).
- [ ] Add the matching top `CHANGELOG.md` heading. It must name three things:
      the executable bit, the new gate, and **the consumer-visible effect** —
      that a fresh install now writes
      `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py` executable
      where it previously wrote it `644`, and that existing installs are
      untouched.

### 7c. Sync and finish

- [ ] `make sync` — proves byte-parity of the copies. It will **not** move any
      mode; steps 2, 3, and 3b already did that.
- [ ] `make release-prep` — regenerates surfaces, self-syncs, refreshes
      `docs/fleet/candidate-validation.json` for the exact payload, then runs
      `make check`. Run this **after** every other edit, never mid-cycle.
- [ ] Run check E2 → the only `plugins/**` change is
      `plugins/sd/.claude-plugin/plugin.json`, and within it only the `version`
      line.
- [ ] Run check C → the two digest lines match.
- [ ] Run check I → every consumer still reports `git status --porcelain` empty.

## 8. Gates

Run in order; each must pass before the next.

- [ ] `.venv/bin/python -m unittest tests.test_script_sibling_resolution` —
      fastest signal.
- [ ] `.venv/bin/python .github/scripts/check-shipped-script-modes.py`
- [ ] `make test` — must report **zero** skips (`Makefile` fails the gate on
      `skipped=[1-9]`).
- [ ] `make lint`
- [ ] `make audit`
- [ ] `make full-check`
- [ ] `make release-prep` (step 7c) — ends in `make check`; run it last.

## 9. Verification checks (named before the work)

### A — static index invariant, two-sided

```
git ls-files -s scripts templates/scripts .sd-ai-command-pack/bin | while read -r m h s p; do
  [ "$(git cat-file blob "$h" | head -c2)" = '#!' ] || continue
  case "$(basename "$p")" in
    sd_ai_command_pack_*) [ "$m" = 100755 ] && printf 'LIB-EXEC %s %s\n' "$m" "$p" ;;
    *)                    [ "$m" = 100644 ] && printf 'NOT-EXEC %s %s\n' "$m" "$p" ;;
  esac
done
```

Pass = **zero lines of either label**. Baseline today = **50 NOT-EXEC, 0
LIB-EXEC**. Failure = any line.

Two-sided on purpose: the one-directional form (`grep '^100644' | grep -v
'/sd_ai_command_pack_'`) can never observe a `LIBRARY_PREFIX` file wrongly
tracked `100755`, which is half of what the gate enforces. It also matched a
path substring where the rule is a **basename** prefix.

This is the blast-radius check: it enumerates from the index rather than from
the file lists in steps 2, 3, and 3b, so it catches a file nobody wrote down.

### B — functional `run --` sweep

```
git ls-files templates/scripts | while read -r f; do
  b=$(basename "$f")
  case "$b" in sd_ai_command_pack_*) continue ;; esac
  err=$(bash scripts/sd-ai-command-pack-toolchain.sh run -- "$b" --sd-bogus-flag 2>&1 >/dev/null)
  case "$err" in
    *"Permission denied"*)      printf 'DENIED  %s\n' "$b" ;;
    *"pack helper is missing"*) printf 'MISSING %s\n' "$b" ;;
    *"not found"*|*"No such file or directory"*) printf 'BROKEN  %s\n' "$b" ;;
  esac
done
```

Pass = **zero lines of any label**. Baseline = **21 DENIED of 25**, 0 MISSING,
0 BROKEN.

Enumerating from `git ls-files templates/scripts`, not a filesystem glob, is
what the acceptance criterion requires — a glob would sweep untracked or
generated files and miss a tracked file that is absent from the working tree.

Three labels, not one: a check that greps only for `Permission denied` would
report a clean pass if `run --` stopped resolving helpers altogether and
started saying "not found". A non-zero exit from a helper rejecting
`--sd-bogus-flag` is expected and is not a failure.

### B2 — the same sweep from `~/.agents/bin`

Identical to B with
`bash ~/.agents/bin/sd-ai-command-pack-toolchain.sh` as the driver, and
`git ls-files templates/scripts` still supplying the names.

Pass = **zero lines of any label**, both before and after the change. These
copies come from the machine payload, whose modes are derived, so they are
already correct; B2 exists to prove the change did not regress them. If
`~/.agents/bin/sd-ai-command-pack-toolchain.sh` is absent, record that and say
so — do not report the criterion as met.

### C — fleet candidate ledger

```
.venv/bin/python -c "import sys;sys.path.insert(0,'scripts');import sd_ai_command_pack_fleet_lib as m,json,pathlib;print(m.filesystem_payload_digest(pathlib.Path('manifest.json')));print(json.load(open('docs/fleet/candidate-validation.json'))['payloadDigest'])"
```

Pass = the two lines **match**, after regeneration in step 7c. Use
`.venv/bin/python`: the repo's fleet lib does not import under Homebrew
python3.14.

Expected transition:
`sha256:c4f9c34417673bfdd614a793b1605fd34a84307b710953332832cecec148be35` →
`sha256:d458b3d63faa9698b6798f81964301eb9cd536ad15b79510b1aea0521f53b5d0`.
If the digest does **not** move, the chmod did not reach the manifest sources;
stop.

### D — the gate actually fires

```
git update-index --chmod=-x scripts/sd-ai-command-pack-check.py
.venv/bin/python .github/scripts/check-shipped-script-modes.py; echo "exit=$?"
git update-index --chmod=+x scripts/sd-ai-command-pack-check.py
```

Pass = **non-zero exit** on the mutated index, and the offending path named in
the output. Repeat once with a `LIBRARY_PREFIX` file chmodded `+x` to exercise
the inverse direction.

The invariant holds after step 3b because it was just repaired, so a gate that
never runs looks identical to a gate that passes. This is the only check that
tells them apart. Restore the index afterwards and re-run check A.

### E — strict plugin zero-diff, taken *before* the version bump

```
git diff --stat -- plugins
```

Pass = **empty**, run at step 7a. Failure = any line.

### E2 — scoped plugin diff, taken *after* `make release-prep`

```
git diff --numstat -- plugins
git diff -- plugins/sd/.claude-plugin/plugin.json
```

Pass = the numstat names **only** `plugins/sd/.claude-plugin/plugin.json`, and
its diff touches only the `version` line. Any other `plugins/**` path is a
failure.

E and E2 are split because a single strict assertion cannot survive the bump:
`render_plugin_manifest(version)` rewrites `plugin.json` by construction, and
`manifest.json` and `plugin.json` both read `0.71.35` today.

### F — the diff is modes and nothing else

```
git diff --numstat <base>...HEAD -- scripts templates/scripts .sd-ai-command-pack/bin \
  | awk '$1!="0" || $2!="0"'
git diff --summary  <base>...HEAD -- scripts templates/scripts .sd-ai-command-pack/bin
```

Pass = the **filtered** numstat is empty. NOTE, corrected 2026-08-20: an
earlier draft of this check claimed `--numstat` omits pure mode changes so any
line is a content edit. **That is false.** Verified against 50 staged mode
changes: `git diff --cached --numstat` emits one `0\t0\t<path>` row per
mode-only change, so an unfiltered "expect empty" test fails on a CORRECT
implementation. The `awk` filter keeps only rows with a nonzero add or delete
count, which is the content-edit signal this check actually wants. Any line
is a content edit), and `--summary` showing **only**
`mode change 100644 => 100755` lines.

Both halves are required. `--summary` alone emits nothing for a pure content
modification — so a content edit to a shipped script, the exact violation of
this task's defining property, would pass it silently. `--numstat` is the half
that sees content.

Then over the whole change:

```
git diff --summary <base>...HEAD
```

Pass = no line that is not a `mode change 100644 => 100755`, outside
`manifest.json`, `CHANGELOG.md`, `docs/fleet/candidate-validation.json`,
`plugins/sd/.claude-plugin/plugin.json`,
`.github/scripts/check-shipped-script-modes.py`, `Makefile`,
`.github/workflows/tests.yml`, `tests/`, `.trellis/`.

### F2 — the 14 authored `run --` sites are unchanged

```
git diff --numstat <base>...HEAD -- templates/.agents/skills templates/docs .github/command-sources \
  | awk '$1!="0" || $2!="0"'
grep -rn -- 'run -- sd-ai-command-pack-' templates/.agents/skills templates/docs .github/command-sources | wc -l
```

Pass = the **filtered** numstat is empty (see the note on check F — an
unfiltered numstat emits a `0\t0` row per mode change) and the count is **14**,
unchanged from the
baseline. This is the discharging step for the acceptance criterion "The 14
authored `run --` sites are unchanged"; without it that criterion had no check
behind it.

### G — the gate is reachable, not merely mentioned

```
make -n check 2>/dev/null | grep -c check-shipped-script-modes
grep -c check-shipped-script-modes .github/workflows/tests.yml
```

Pass = **3 and 3**, matching a correctly-wired sibling gate exactly.

`make check` is `test lint audit full-check` (`Makefile:106`), so a fully wired
gate appears three times in the expanded graph: its own invocation in the `test`
target, plus the `ruff` and `mypy` argument lists in `lint`. `tests.yml` scores
3 the same way — the workflow run plus its own ruff and mypy lines. Measured
today for `check-helper-resolution`: **3 and 3**. Anything less than 3 names
which list was missed.

`make -n check` is used rather than a raw `grep` over `Makefile` because it
expands the actual target graph: it distinguishes a gate that *runs* from one
that is merely mentioned, in a comment or in an unreachable target.

### H — the CI classifier is untouched

```
git ls-files -s .github/scripts/bookkeeping_ci_scope.py
```

Pass = `100644`. Anything else silently disables fast-lane selection via the
fail-open guard at `.github/workflows/tests.yml:154`.

### I — consumer checkouts are read-only and unchanged

```
python3 -c "import json;[print(c['pathHint']) for c in json.load(open('docs/fleet/consumers.json'))['consumers']]" | while read -r h; do
  d=$(eval printf '%s' "$h"); [ -d "$d/.git" ] || { printf 'ABSENT %s\n' "$d"; continue; }
  printf '%s dirty=%s mode=%s\n' "$d" \
    "$(git -C "$d" status --porcelain | wc -l | tr -d ' ')" \
    "$(git -C "$d" ls-files -s .sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py | awk '{print $1}')"
done
```

Pass = every `dirty=0`, before and after. Record every `mode=` value.

This is the criterion that would have caught the third tracked copy. Measured
2026-08-20: `dirty=0` and `mode=100644` in all eight. Expect exactly that both
before and after — this change never
reaches into an existing checkout (`installer/fileops.py:465-474`). The mode
moves only when a consumer next performs a **fresh** install, which is outside
this task's boundary and is what the CHANGELOG entry in step 7b announces.

## Review gates

Do not proceed past any of these unresolved:

1. **After step 3b** — check A returns zero lines of either label. If not, the
   enumeration in steps 2, 3, and 3b is incomplete.
2. **After step 4** — check B and check B2 return no labelled lines, the third
   copy runs directly, and the non-pack operand pass-through still works.
3. **After step 5** — check D fires in both directions and check G reports ≥ 1
   from `make -n check`.
4. **After step 7a** — check E is strictly empty. Take this **before** the
   version bump.
5. **After step 7c** — check C matches, check E2 is scoped to `plugin.json`'s
   version line, check I is clean.
6. **Before PR** — check F (both halves), check F2, and check H.

## Rollback

```
git revert -m 1 <merge-sha>
```

`-m 1` is required, not optional: `sd-ai-command-pack-housekeeping.sh` defaults
to `--merge-strategy merge` (`:16`), so the landing commit is a true merge
commit and a bare `git revert` errors out on it.

Otherwise complete by construction: no migrations, no persistent state, no
writes into existing consumer checkouts, and no content to reconcile. The
manifest bump, the CHANGELOG entry, the regenerated
`docs/fleet/candidate-validation.json`, and the regenerated `plugin.json` travel
in the same commit and revert with it.

The one thing a revert does **not** undo is a consumer that has already
performed a fresh install against the new payload and committed
`.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py` at `100755`. That
is a one-line mode change in that consumer's own repository, repaired there with
`git update-index --chmod=-x` if the revert is meant to be fleet-wide.
