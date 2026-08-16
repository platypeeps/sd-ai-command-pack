# Implement: reconcile agreeing duplicate plugin registrations

Executes `design.md` in this directory. Every source edit lands in
`templates/scripts/`; `scripts/` and `plugins/sd/**` are regenerated, never
hand-edited.

## Step 0 — capture the before state

Both "before" artifacts are required by `prd.md` acceptance and cannot be
reconstructed after the fix.

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-status.py fleet --json --no-network \
  > "$SCRATCH/machinescope-before.json"

claude plugin list --json > "$SCRATCH/plugin-list.json"

diff -q ~/.agents/bin/sd-ai-command-pack-status.py scripts/sd-ai-command-pack-status.py
diff -q ~/.agents/bin/sd-ai-command-pack-pack-update.sh scripts/sd-ai-command-pack-pack-update.sh
```

Record `machineScope` from the first, and from the second the entry count, the
distinct `version` set, and the distinct `installPath` set. Replay the updater's
resolver against the captured listing and record the exit status — expected
`12`.

The two `diff` calls satisfy `prd.md`'s requirement to re-measure the
byte-identity claim rather than trust this record. They must run here and only
here: both are expected to report no difference now, establishing that the
installed copies carry the bug, and both are expected to *differ* after Step 4.
Re-running them later as a pass condition would fail for the right reason and
be read as the wrong one.

If either reports a difference at Step 0, the machine install is already ahead
of or behind the source in some way this task did not account for. Stop and
report before editing — the bootstrap reasoning in `design.md` assumes the
installed updater is the buggy one.

**Gate:** if the live listing no longer has duplicates — a plugin uninstalled
from a consumer, a `claude` version that dedupes — stop and report. The whole
task is premised on reproducing the failure, and a green before-state means the
premise moved. Do not synthesize a duplicate listing to keep going; a fixture
would prove the tests pass, not that the bug was real.

## Step 1 — `templates/scripts/sd-ai-command-pack-status.py`

In `collect_plugin_version`, replace the `len(matches) > 1` branch at `:1726`
with distinct-version reconciliation.

1. After `matches` is built and the empty case returns, collect the distinct
   non-empty versions across all matches, normalizing each through `safe_text`
   with the existing `limit=80` exactly as the single-entry path does at
   `:1732`. Normalizing before deduplicating matters: two entries that differ
   only past the limit must not read as a conflict.
2. Zero distinct values keeps the existing "carries no version" return at
   `:1734`, with wording that still reads correctly for more than one entry.
3. More than one returns `MACHINE_UNAVAILABLE` with a detail naming the
   conflict and the values, not the count.
4. Exactly one returns it.

Update the docstring at `:1695`–`:1701`. It currently lists "a missing or
duplicated entry" among the failures; duplication alone is no longer one. The
sentence at `:1699` about refusing to guess stays and becomes the justification
for the conflict branch.

## Step 2 — `templates/scripts/sd-ai-command-pack-pack-update.sh`

Same shape in the embedded resolver, on `installPath` instead of `version`.

1. Replace the `len(matches) > 1` / `SystemExit(12)` pair at `:145`–`:146` with
   a distinct-path collection over all matches, stripping each as the
   single-entry path does at `:147`–`:150`.
2. Zero distinct paths keeps `SystemExit(13)`; more than one raises
   `SystemExit(12)`; exactly one is printed.
3. Reword the `:20` header comment from "the plugin is listed more than once"
   to the path-conflict meaning.
4. Reword the `:158` failure text. "Resolve the duplicate install before
   updating" only ever prints now when the duplicates genuinely disagree, so
   name the conflicting paths in the message — the operator's next action is to
   find which registration points somewhere unexpected.

## Step 3 — tests, before regenerating

Run each new test against the *unfixed* mirror first where practical, to
confirm it fails for the reason intended. A test written after the fix that has
never been seen red proves only that it agrees with the code.

`tests/test_status.py`:

- The case table at `:3212`–`:3235` keeps all seven rows. The
  `"plugin duplicated"` row at `:3219` (versions `9.9.9` / `9.9.8`) stays a
  refusal; its `expected_detail` changes from `"more than once"` to the new
  conflict wording. The other six rows are untouched — that is the regression
  guard for a function whose contract is "every discovery failure reports
  unavailable".
- Add a success test: three entries, all version `9.9.9`, receipt written at
  `9.9.9` via `write_machine_receipt`. Assert `pluginVersion == "9.9.9"`,
  `pluginDetail is None`, and `comparison == "current"`.
- Add the seam test from `design.md` D4: same agreeing three-entry listing,
  receipt at `9.9.8`. Assert `comparison == "skew"`. This is the case
  `tests/test_status.py:2766` and `:2793` cannot reach, because both inject
  `comparison="skew"` through `machine_scope_fixture` rather than computing it.

Both new tests use `machine_scratch` and `machine_section` so nothing reads the
developer's real `~/.agents` or state root — `machine_scratch`'s docstring at
`:190`–`:194` states that constraint and it applies here.

`tests/test_pack_update.py`:

- `test_duplicate_entries_are_refused` at `:320` inverts. It builds its listing
  as `[*listing, dict(listing[-1])]` — an exact copy of the same entry, which
  is the benign shape. Rename it to describe reconciliation and assert exit `0`
  with the machine installer having run.
- Add a conflicting-path test that keeps exit `12`: duplicate the entry via
  `dict(listing[-1])` and then point the copy's `installPath` at a different
  directory. `listing_for` builds the entry, so the second path has to be
  written onto the copy explicitly.

## Step 4 — propagate

```bash
make generate
make sync
```

Then confirm the mirrors agree:

```bash
grep -rn 'len(matches) > 1' --include=*.py --include=*.sh . \
  --exclude-dir=.venv --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=.build
```

Expect twelve hits before the change and four after: `sd-ai-command-pack-review.py`
in each of `templates/scripts/`, `scripts/`, `plugins/sd/bin/`, and
`plugins/sd/machine-payload/scripts/`. That file is routed-review receipts and
is out of scope. Any surviving hit in a `status.py` or `pack-update.sh` copy is
a stale mirror, not a second site.

`make generate` ends by running `scripts/sd-ai-command-pack-surface-check.py`;
a `mirror.stale` finding there means `make sync` did not run or did not take.

## Step 5 — release payload

`templates/**` changed, so:

- bump `manifest.json` `version` from `0.71.22`;
- add a matching top heading to `CHANGELOG.md`, whose current top is
  `## 0.71.22 - 2026-08-16`.

The changelog entry must state the bootstrap route from `design.md`: the first
refresh after this release has to run the pack source checkout's
`scripts/sd-ai-command-pack-pack-update.sh`, because the installed updater is
still the old one and will still exit `12`. An operator who hits that without
warning will read it as the fix not working.

`make check` does not run the release payload gate, so neither omission fails
locally.

## Step 6 — verify

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-status.py fleet --json --no-network \
  > "$SCRATCH/machinescope-after.json"
```

- `machineScope.pluginVersion` is a real version, `pluginDetail` is null, and
  `comparison` is not `unknown`. Both halves read `0.71.22` today so `current`
  is expected; a truthful `skew` also passes, and if it appears, report it —
  that is a genuine machine finding this bug was hiding.
- The resolver replayed against `$SCRATCH/plugin-list.json` exits `0` and prints
  one path, where Step 0 recorded `12`.
- `make check`.
- `make release-prep`.

Do not re-measure the "installed copy is byte-identical to source" claim as a
pass condition at this point — after Step 4 it is deliberately false. Measure it
in Step 0 instead, where it establishes that the installed updater carries the
bug.

## Ordering constraints

- Step 0 before any edit; the before-state is unrecoverable afterwards.
- Steps 1 and 2 are independent and may land in either order.
- Step 3 before Step 4: regenerating first makes it impossible to see a new test
  fail against the unfixed mirror.
- Step 5 after Step 4, so the manifest bump is not undone by a regeneration.

## Rollback

`git revert` the range, then `make generate && make sync`. No persisted state,
no schema movement, and a machine already refreshed past the fix keeps working
because reverted code still resolves single-entry listings.
