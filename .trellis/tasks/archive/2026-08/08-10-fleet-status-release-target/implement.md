# Implement — fleet status compares against the newest published release

Edit `templates/scripts/sd-ai-command-pack-status.py`, then regenerate the
three mirrors (see §6 — it takes both `make sync` and `make generate`). All
line numbers below are the pre-edit `scripts/` copy, which is byte-identical to
the template.

## 1. Add the release lookup

New function beside `collect_github` (`:1944`), same sentinel vocabulary:

```python
def collect_release_target(
    pack_source: Path,
    *,
    network: bool,
) -> dict[str, Any]:
    """The newest published sd-ai-command-pack release tag, or a labeled reason."""
```

This project publishes annotated tags, not GitHub Releases — see design D2 for
the measurement. Do not reach for `gh`.

Order of operations, each returning `{"status": ..., "version": None, "tag": None}`
unless stated:

1. `not network` -> `disabled`. No subprocess runs. Assert that in the test.
2. `run_command(["git", "remote", "get-url", "origin"], cwd=pack_source)`
   (`:140-144`) — `cwd` is the repository selector, so no `git -C`. Nonzero
   exit or empty output -> `not-configured`. The URL itself is not parsed;
   only its existence is required (design D3).
3. `run_command(["git", "ls-remote", "--tags", "--refs", "origin"], cwd=pack_source)`.
   Nonzero exit or a timeout -> `unavailable`.
4. Parse each line as `<oid>\t refs/tags/<tag>`. Keep only tags matching
   `^v(\d+)\.(\d+)\.(\d+)$`. Everything else is skipped, not coerced.
5. No surviving tag -> `unavailable`. A remote with no releases yet is a real
   state, not an error.
6. **Select by integer tuple, never by string.** `max()` over
   `(major, minor, patch)`. Sorting the strings puts `v0.9.2` above `v0.71.8`
   and would silently report a year-old version as newest (design D2a).
7. Success -> `{"status": "available", "version": "<tag without v>", "tag": tag}`.

Reuse `run_command`'s default `timeout_seconds=COMMAND_TIMEOUT_SECONDS`
(`:143`). Do not add a new timeout constant.

## 2. Call it once per fleet run

In `collect_fleet`, after `target = resolution.target_version` (`:3214`):

```python
release_target = collect_release_target(resolution.pack_source, network=network)
```

Once per run, not once per consumer — the pack has one release regardless of
fleet size. Place it before the `ThreadPoolExecutor` block (`:3281-3287`) so
the round trip is not multiplied by the pool, and add
`"releaseTarget": release_target` to the returned mapping beside
`"targetPackVersion"` (`:3301`).

`resolution.pack_source` is already bound on `FleetResolution`
(`sd_ai_command_pack_fleet_lib.py:118`); do not re-derive the pack root from
`__file__`.

## 3. One fleet-level record, not per-consumer rows

`fleet_step_records` (`:3005`) gains a keyword-only
`release_target: Mapping[str, Any] | None = None`. Default `None` keeps every
existing caller and test valid.

Emit exactly one record, and only when `release_target["status"] == "available"`
and its `version != target`:

> pack checkout is at `<target>`, newest published release is `<release>`;
> pull the pack source before refreshing the fleet

String inequality, never ordering, and the wording says *differs from*, not
*is behind* (design D6) — an unreleased working copy is ahead, and that is the
second failure mode the PRD names.

Rank it `FLEET_STEP_RANK_SKEW` (`:120`), not `FLEET_STEP_RANK_ADVISORY`: it
invalidates every consumer comparison in the same report, so it must not be
truncated away.

Note this deliberately does **not** match the existing per-consumer stale row,
which is `ADVISORY` (`:3196`). That row says one consumer drifted from a valid
target; this one says the target itself is not what is published, which is the
stronger claim.

Do **not** touch the `stale` list (`:3026-3030`) or `target_pack_version` on
consumer rows (`:3245`). Consumer comparisons stay checkout-based (design D4).

## 4. Render it

In `render_fleet` (`:3317`), print one line near the target version. Show the
status when not `available`:

```
release target: 0.71.8 (v0.71.8)
release target: unavailable
```

Do not add it to the `attention` counter (`:3323-3343`). An unreachable remote
must not make a healthy fleet look broken.

## 5. Tests — `tests/test_status.py`

All three existing `collect_fleet` call sites pass `network=False`
(`:2333`, `:2422`, `:2499`), so they short-circuit at step 1 and never spawn a
subprocess. They must keep passing with no edit; if any needs one, the change
is not additive and that is a design defect, not a test defect.

For the cases that do need output, monkeypatch `status.run_command` — it is the
single seam every subprocess in this module goes through (`:140`). Do not
monkeypatch `subprocess.run` or `shutil.which` globally.

New cases:

1. `network=False` -> `status: "disabled"`, `version: None`, and `run_command`
   never called. Assert the call count, not just the status; that is
   criterion 3.
2. `git remote get-url origin` fails -> `not-configured`.
3. `ls-remote` exits nonzero -> `unavailable`.
4. `ls-remote` returns only non-`v<semver>` refs -> `unavailable`.
5. **Ordering.** A tag list containing both `v0.9.2` and `v0.71.8` selects
   `v0.71.8`. This is the case a string `max()` fails and every other case
   passes; without it the defect ships.
6. Happy path -> `available` with version and tag, `v` stripped from `version`
   and retained in `tag`.
7. Release differs from checkout -> exactly one new record, and the existing
   per-consumer stale rows are unchanged. Assert the count, or a passing test
   will not notice the record being emitted twice.
8. Release equals checkout -> no new record.
9. Release `unavailable` -> no new record, and the `attention` counter is
   identical to the same fixture with the release available.
10. A full fleet report with the release target unavailable still contains
    every existing key. This is criterion 2's "complete report" clause.
11. **Read-only, asserted.** Capture every argv `run_command` receives during
    the happy path and assert the set is exactly
    `git remote get-url origin` and `git ls-remote --tags --refs origin`.
    Criterion 3 says status stays read-only; `ls-remote` and `remote get-url`
    both are, but only an argv assertion keeps a later edit from slipping a
    `git fetch` in. Nothing here may write the local repository.

## 6. Validation

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  -m unittest tests.test_status -v
make sync
make generate
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py
git status --short
.venv/bin/python -m ruff check install.py installer scripts templates/scripts tests
.venv/bin/python -m mypy installer install.py scripts
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-check.py --json
```

Both `make` targets, in that order, and both before the lint sweep so the
generated mirrors are linted in the state they will be committed in.

**`make sync` alone regenerates only two of the four copies.** It runs
`install.py . --force` (`Makefile:37-39`), which writes `scripts/` from
`templates/`; the two `plugins/sd/**` copies come from
`.github/scripts/generate-plugin.py` under `make generate` (`Makefile:19-30`).
Running only `sync` leaves the plugin mirrors stale, and the tripwire below is
what catches it.

`make generate` ends in `sd-ai-command-pack-surface-check.py`, which **fails**
after any payload change with `provenance.candidate-stale`: changing the
payload changes its digest, and `docs/fleet/candidate-validation.json` still
records the old one. That is expected, not a defect. Refresh it with
`scripts/sd-ai-command-pack-fleet-candidate-check.py` — the command the error
itself names — and commit the ledger. This is why the precedent commit
`450c0a95` carried that file. Do not hand-edit the ledger, and do not run
`make release-prep`, which is release preparation and a different scope.

Blast-radius check — the four copies must be byte-identical after sync:

```bash
for f in scripts plugins/sd/bin plugins/sd/machine-payload/scripts; do
  diff -q templates/scripts/sd-ai-command-pack-status.py \
    "$f/sd-ai-command-pack-status.py"
done
```

All three must report identical. This tripwire is what caught `make sync`
covering only two of the four copies; if any DIFFERS, `make generate` has not
run or has failed partway.

Enumerate consumers of the fleet JSON rather than grepping for the key just
added:

```bash
grep -rn "targetPackVersion" . --include=*.py --include=*.mjs --include=*.sh \
  --include=*.md | grep -v "^./.git/"
```

Every hit that reads the fleet report must still work with an added sibling
key. A hit that enumerates top-level keys, rather than indexing them, is the
one that breaks.

## 7. Bump the manifest version

This script is shipped payload, so the release payload gate refuses the change
without a version bump:

```
error: release version drift: shipped payload changed without manifest version
bump (...); manifest version stayed at '0.71.8'
```

Bump `manifest.json` to `0.71.9`, add the matching `## 0.71.9 - <date>` heading
to `CHANGELOG.md` — the changelog gate requires the two to agree — then re-run
`make sync`, which rewrites `.sd-ai-command-pack/manifest.json` and the
`.agents/`/`.claude/` `command-catalog.md` mirrors from the new version.

Because those mirrors are tooling/generated paths, the PR body needs a
`## Tooling/generated scope:` section or
`sd-ai-command-pack-pr-body-scope.py` fails the drift gate.

## 8. Rollback

Revert the single commit, version bump included. Status writes nothing; no
consumer state and no cache to unwind.
