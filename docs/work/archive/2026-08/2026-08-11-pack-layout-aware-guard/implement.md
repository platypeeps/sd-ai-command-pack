# Implement — pack-owned layout-aware review guard

Order matters: the drop column (§2) deletes duplicated behavior and needs no
new code, so it lands first and independently of the interface work.

## 1. Prove the drop column before writing anything

Design D1's drop table claims the pack already ships four behaviors that three
consumers reimplement. If any row is wrong, that behavior moves to ship and the
scope changes. Verify each against the pack, not against the consumer:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-check.py --json | python3 -c "
import json,sys
d=json.load(sys.stdin)
for c in d['checks']:
    if c['id']=='pack.review-preflight': print(c['diagnostic'])
"
```

Expect its diagnostic to name, in one run: journal session placeholders,
personal absolute paths, and documentation path references. The fourth row —
the PR-body scope marker — is proven by showing the pack and the consumer
accept the same three headings:

```bash
grep -n 'Tooling/generated scope' templates/scripts/sd-ai-command-pack-review-scope.sh
grep -n 'SCOPE_BODY_PATTERN =' \
  "$HOA/scripts/check-review-preflight.mjs"   # $HOA = hoa-manager pathHint
```

Both must list `Tooling/generated scope`, `Generated/tooling scope`, and
`Copied/generated scope`. Compare the alternation sets by eye and record them;
the two regexes are written in different dialects (`grep -E` versus JavaScript)
so a byte diff is meaningless and asserting "byte-equivalent" would be false.

A row that does not reproduce is a design defect. Record it and stop; do not
quietly reclassify it into ship, because the ship column's size is the argument
D2 rests on.

## 2. New payload script

`templates/scripts/sd-ai-command-pack-review-layout.py`. Python because the
receipt and manifest readers are already Python. The first draft of this line
also said "partition reader"; D3a removed the partition as a source entirely,
so it is not a reason.

**Import nothing from `installer/`.** It ships zero files
(`grep -c "^installer/" .sd-ai-command-pack/installed-targets.txt` is `0`), so
any such import works here and fails in every consumer — design D3a. The same
goes for `docs/fleet/surface-partition.json`, which is repo-owned fleet data
and is not installed.

Reuse what is actually shipped:

- `resolve_state_root` (`scripts/sd_ai_command_pack_lib.py:248`, receipt line
  199) for the thin rung. **Call it.** Expanding `~/.local/state` directly
  skips `SD_AI_COMMAND_PACK_STATE_HOME`, `XDG_STATE_HOME`, and the Windows
  rung — four of five (design D4a).

Redefine, with the repo-side original named in a comment:

- the fat receipt's relative path (`installer/registry.py:2281`
  `INSTALLED_TARGETS_FILE`);
- the thin receipt's name (`installer/machinescope.py:66-67` `MACHINE_STATE_DIR`
  / `RECEIPT_FILE`).

Add a pack test asserting each redefined constant equals its `installer/`
original. The duplication is deliberate; leaving it unchecked is not.

Resolution order and the four `mode` values are D4a's list, in that order.
`unresolved` exits nonzero and emits **no** `paths` array — not an
all-`authored` array. Assert that in a test; an empty-but-present array is the
failure this is written to prevent.

Output is D3's JSON, `schemaVersion: 1`.

`surface.commands` is enumerated from the **receipt** — the 140
`installed-targets.txt` lines under `commands/` or `skills/` — and never from a
literal list. **No literal command list anywhere in the file.** The test for
this is a grep, not an assertion: a hardcoded list would pass every behavioral
test on the current pack.

### `--resolve` (design D3b)

Second query, same script: given a bare script name, return its invocation path
for the resolved mode.

- **fat** — `scripts/<name>`, but only after confirming `<name>` is in
  `installed-targets.txt`. Do not synthesize a path for a name the receipt does
  not list.
- **thin** — read the machine receipt's `files` array (measured: 115 entries,
  each `{"family", "path", "digest", "executable"}`), find the entry whose
  `path` equals `<name>`, map `family` through the redefined family-root table,
  and join.
- **neither** — error, echoing the requested name. Never guess a path; a
  wrong-but-plausible path is worse than a refusal, because the caller will run
  it.

Redefine the family-root table under the D3a rule and add the same
equals-the-original test against `family_roots`
(`installer/machinepayload.py:103`).

## 3. Bindings

Three, over the one implementation:

1. **Shell** — `review-scope.sh` gains a `--json` classification mode. Keep
   every existing function and exit code; consumers depend on them today.
2. **Node** — one `export` from the already-shipped
   `sd-ai-command-pack-review-preflight.mjs` that shells to §2 and returns the
   parsed object. `rwbp-website` gets it through the import it already has at
   `review-guard.mjs:6`, so its adoption is a call, not an integration.
3. **Python** — importing §2 directly.

The bindings must not each re-derive the mode. One implementation, three
callers; a binding that answers differently from the others is the bug this
task exists to stop.

## 4. Tests — `tests/test_review_layout.py`

Criterion 4 requires a thin-mode and a fat-mode invocation both exercised.

1. Fat: a temp consumer with `.sd-ai-command-pack/installed-targets.txt` ->
   `mode: "fat"`, receipt path relative.
2. Thin: no `.sd-ai-command-pack/`, `SD_AI_COMMAND_PACK_STATE_HOME` pointed at
   a temp dir holding `machine/machine-receipt.json` -> `mode: "thin"`.
   Setting the env var rather than faking `$HOME` is the point: it proves the
   ladder is used.
3. `XDG_STATE_HOME` set and `SD_AI_COMMAND_PACK_STATE_HOME` unset -> still
   `thin`. This is the rung a `~` expansion skips, and the only test that
   catches that mistake.
4. `SD_AI_COMMAND_PACK_TARGETS_FILE` set -> wins over both, `mode: "fat"`.
   Existing consumers set this; it must not regress.
5. Neither present -> `mode: "unresolved"`, nonzero exit, **no** `paths` key.
6. **Same input, same answer from all three bindings.** Classify one fixed path
   list through shell, Node, and Python and assert the three results are equal.
   Without this, the bindings drift and each consumer gets a different answer —
   which is the original defect, reintroduced inside the pack.
7. `surface.commands` is non-empty and every entry's paths exist in the fat
   fixture, proving runtime enumeration rather than a literal.
8. `--resolve` in fat returns `scripts/<name>` for a receipt-listed name.
9. `--resolve` in thin returns the `family_roots`-derived path for the same
   name, and it differs from the fat answer. Asserting they differ is the
   point: a resolver that returned `scripts/<name>` in both modes would pass
   test 8 and be useless.
10. `--resolve` on a name in neither receipt errors and echoes the name. Assert
    no path-shaped string appears in the output; a guessed path is the failure
    mode this test exists for.
11. The redefined family-root table equals `family_roots`
    (`installer/machinepayload.py:103`), and the redefined receipt-path
    constants equal their `installer/` originals. Pack-only test — `installer/`
    exists here even though it never ships.

## 5. Validation

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  -m unittest tests.test_review_layout -v
make sync
make generate
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py
.venv/bin/python -m ruff check install.py installer scripts templates/scripts tests
.venv/bin/python -m mypy installer install.py scripts
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-check.py --json
make check
make release-prep
```

`make check` and `make release-prep` are criterion 3 and are not optional.

New payload means the full cascade from `08-10-fleet-status-release-target`:
`make sync` writes `scripts/`, `make generate` writes both `plugins/sd/**`
copies and then **fails** `surface-check` with `provenance.candidate-stale`
until `sd-ai-command-pack-fleet-candidate-check.py` refreshes
`docs/fleet/candidate-validation.json`. Bump `manifest.json` with a matching
`CHANGELOG.md` heading — the release payload gate refuses a payload change
without it — and give the PR a `## Tooling/generated scope:` section.

Four copies byte-identical:

```bash
for f in scripts plugins/sd/bin plugins/sd/machine-payload/scripts; do
  diff -q templates/scripts/sd-ai-command-pack-review-layout.py \
    "$f/sd-ai-command-pack-review-layout.py"
done
```

**A new script does not automatically reach all four paths.** Measured:
`scripts/` holds 27 `.py` files and both plugin mirrors hold 18. The nine that
stop at `scripts/` are the repo-owned family — every `sd-ai-command-pack-fleet-*`
plus `sd-ai-command-pack-thin-resweep.py` — and the partition is what decides,
not the filename. So this guard must not be named `fleet-*`, and if the loop
above reports a missing file rather than a differing one, the partition has
classified it repo-owned and the fix is the partition, not another `make`
run.

Then confirm the receipt grows, because a payload file the receipt does not
list is a file no consumer installs and therefore cannot run:

```bash
grep -c "sd-ai-command-pack-review-layout.py" .sd-ai-command-pack/installed-targets.txt
```

Expect `1`.

## 6. Measure, do not project (criterion 5)

Re-run the fleet resweep and record the per-consumer blocker delta from the
measurement, not from the PRD's tables. Two known corrections apply and both
lower the figure:

- the 510/330 counts predate 0.70.0's resweep fix (PRD Evidence);
- `anomaly-metric-creator`'s count is **175**, re-measured 2026-08-14, not the
  PRD's original 207. It owns no bespoke layout guard, so none of it falls to
  the ship column. Report the reductions separately per query, or the number
  cannot be attributed to a change.

If the measured reduction is materially smaller than the PRD's framing implies,
say so in the PR body. That is a finding, not a failure.

**Done 2026-08-14.** All eight consumers measured; the table and the three
findings are in design D6. This step's own expectation — "all 175 fall to
`--resolve`" — was one of the things the measurement refuted: 112 do, 8 fall to
the surface enumeration, and 55 are globs no resolver reaches. Fleet total is
456, not 510, and this task reaches 355 of them. Both corrections belong in the
PR body under the rule above.

## 7. Out of scope, restated because it is easy to drift into

No consumer repository is edited. Not one line, not the obvious two-line
deletion. Adoption belongs to the conversion cohorts and needs the per-cohort
authorization those tasks document. This task's deliverable is that their work
becomes a delete.

## 8. Rollback

Revert the commit, version bump included. The guard is read-only and unadopted
at merge time, so nothing depends on it.
