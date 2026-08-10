# Research: the watch-pr (0.57.0) removal as the mechanism precedent

- **Query**: How does the provenance-aware retirement mechanism remove installed
  copies on refresh, and how did the `sd-watch-pr` 0.57.0 removal execute the
  schedule→enforcement flip?
- **Scope**: internal
- **Date**: 2026-08-09
- **Precedent commit**: `71d12d1f` — *feat(ship): replace sd-watch-pr with
  internal read-only watch coordinator*, 2026-07-30, 52 files,
  +531 / −1174.

## The mechanism, end to end

### Step 1 — the registry row is the single source of truth

`installer/registry.py:1331-1339` defines `RetiredCommandSurface`:

```python
id: str
identifiers: tuple[str, ...]
installed_targets: tuple[str, ...]
removed_version: str
owner_task: str
source_paths_must_be_absent: bool = True
configuration_keys: tuple[str, ...] = ()
```

Two fields have teeth. `identifiers` drives a repo-wide text scan;
`source_paths_must_be_absent` drives two existence assertions. A schedule-only
row sets `identifiers=()` and `source_paths_must_be_absent=False` and asserts
nothing — that is the state the three transitional rows are in today
(`installer/registry.py:1387-1410`).

`installed_targets` is always built by `command_installed_targets(long, short)`,
never hand-listed. Each of the seven rows currently resolves to **26** consumer
paths. Only consumer-install paths may appear there — never a
`templates/scripts/…` manifest *source* — because everything in the tuple
becomes an unconditional deletion candidate under `--force`.

### Step 2 — `RETIRED_TARGETS` is hand-maintained and gates everything

`installer/removal.py:65-75`:

```python
RETIRED_REVIEW_LOCAL_ALL_TARGETS = retired_surface_targets("review-local-all-command")
SOURCE_ONLY_COMMAND_TARGETS = retired_surface_targets("fleet-refresh-consumer-targets")
RETIRED_WORK_DESIGNS_TARGETS = retired_surface_targets("work-designs-command")
RETIRED_WATCH_PR_TARGETS = retired_surface_targets("watch-pr-command")

RETIRED_TARGETS = (
    *RETIRED_REVIEW_LOCAL_ALL_TARGETS,
    *SOURCE_ONLY_COMMAND_TARGETS,
    *RETIRED_WORK_DESIGNS_TARGETS,
    *RETIRED_WATCH_PR_TARGETS,
)
```

This is a **hand-enumerated tuple, not a comprehension** over
`RETIRED_COMMAND_SURFACES`. Adding a registry row is therefore inert at install
time until someone adds a line here. Current length: **104** (4 × 26).

`install.py:127` re-exports `RETIRED_TARGETS` and `install.py:169` lists it in
`__all__`; the watch-pr commit added `RETIRED_WATCH_PR_TARGETS` to both
(`install.py`, +2 lines in the commit stat).

### Step 3 — `retire_stale_targets` deletes on every normal install/refresh

`installer/removal.py:252-297`. The contract, from its own docstring at
`:259-268` and the loop at `:275-296`:

1. **Ordering constraint** (`:261-264`): it must run *before* the receipt files
   are rewritten, because vouching reads the prior install's provenance records
   and the provenance rewrite drops retired entries once their targets leave the
   manifest.
2. It reads the prior provenance into `provenance_files`
   (`:269-272`, via `read_existing_provenance_files_for_remove`).
3. For each candidate in `RETIRED_TARGETS` it calls `remove_pack_file(...)` with
   `file=None` and `recorded_hash=provenance_files.get(candidate)` (`:278-286`).
4. Source-checkout guard (`:276-277`): when the target *is* the pack repo root,
   `SOURCE_ONLY_COMMAND_TARGETS` are skipped — the fleet-refresh row's targets
   legitimately exist in the source tree.
5. `RemoveStatus.MISSING` produces **no result row** (`:287-288`) — absent
   targets are silent.
6. Surviving statuses are renamed through `_RETIRED_STATUSES`
   (`installer/removal.py:80-84`): `REMOVED → RETIRED`,
   `PRESERVED → RETIRED_PRESERVED`, `WOULD_REMOVE → WOULD_RETIRE`, so the
   install summary reads as retirement rather than pack removal.

Per-file semantics mirror the removal flow: a hash-vouched file is deleted and
its empty parent dirs pruned (`:247-248`
`unlink_target_file` + `prune_empty_parent_dirs`); a drifted or unvouched file
is **preserved and reported** unless `--force`, which honors `--backup`
(`:240-246`).

That is exactly PRD R4: *"Refresh deletes unchanged vouched copies, preserves
and reports a locally modified copy, prunes empty directories, and never records
retired paths in the new receipt."* The last clause holds because the retired
paths have left `manifest.json`, so the rewritten
`.sd-ai-command-pack/provenance.json` and `installed-targets.txt` cannot contain
them.

**Failure mode to prove against a real prior-release install, not a fixture:** a
wrong `recorded_hash` makes `remove_pack_file` classify a file as drifted and
*preserve* it. The receipt still looks clean, because the path is gone from the
manifest either way. design.md flags this; it is the reason R4 needs a real
upgrade test.

### Step 4 — `recognized_removal_targets` keeps old paths deletable on `--remove`

`installer/removal.py:98-107` unions `RETIRED_TARGETS` into the recognized set
so a full `--remove` on a consumer whose receipts still list them deletes the
leftovers instead of rejecting them as unrecognized
(`removal_candidate_rejection`, `:110-118`).

## What commit `71d12d1f` actually changed

### Registry — the row appeared *fully enforcing*, in one commit

`sd-watch-pr` was never a schedule-only row. The commit added it complete:

```python
RetiredCommandSurface(
    id="watch-pr-command",
    identifiers=("sd-watch-pr",),
    installed_targets=command_installed_targets("sd-watch-pr", "watch-pr"),
    removed_version="0.57.0",
    owner_task="07-24-simplify-review-shipping-composition",
)
```

(now at `installer/registry.py:1376-1382`; `source_paths_must_be_absent` left at
its `True` default). It also deleted the live
`CommandInfo("sd-watch-pr", "watch-pr", "pull-requests-shipping", …)` row from
`COMMAND_REGISTRY` in the same diff.

**This is the one structural difference from the task at hand.** The three
transitional rows already exist as schedule-only and must be *flipped*:
populate `identifiers=("sd-full-check",)` etc., set
`source_paths_must_be_absent=True` (or drop the explicit `False`), remove the
three `CommandInfo` rows, and remove the three `SUPERSEDED_COMMANDS` entries at
`installer/registry.py:1436-1440` — `validate_superseded_commands` (`:1443-1459`)
rejects a key naming an unknown command, so leaving them behind fails at import.

### Allowances — five, added with the flip, not after

`installer/registry.py:1508-1532`, all five for `identifier="sd-watch-pr"`:

| path_pattern | reason |
|---|---|
| `installer/registry.py` | canonical retired-surface declaration |
| `CHANGELOG.md` | bounded historical release record |
| `tests/test_retired_targets.py` | retired-target cleanup regression fixture |
| `.trellis/audit/ledger.md` | bounded historical audit record |
| `.trellis/audit/report-2026-07-28.md` | bounded historical audit record |

A sixth was added later at `:1547-1551` for
`plugins/sd/installer/registry.py` — the generated plugin copy of the same
declaration. Any new enforcing row needs that plugin-copy allowance too, or
`make generate` output trips the lint.

For comparison, the earlier `sd-review-local-all` retirement needed six
(`:1463-1492`), including `README.md`, `tests/test_install_core.py`, and
`tests/test_command_surface_drift.py`. Expect at least the watch-pr five plus a
README migration note per surface here.

### Removal — three lines

`installer/removal.py` gained exactly `RETIRED_WATCH_PR_TARGETS = …` and one
splat line in `RETIRED_TARGETS`. `install.py` gained the import and the
`__all__` entry. Nothing else.

### Test fixture — the count assertions are the tripwire

`tests/test_retired_targets.py` gained a stale-file fixture
(`:26-27` `STALE_WATCH_PR_SKILL = ".agents/skills/sd-watch-pr/SKILL.md"`,
`STALE_WATCH_PR_CONTENT`), a per-family length assertion
(`:81` `assertEqual(len(install.RETIRED_WATCH_PR_TARGETS), 26)`), a total
(`:82` `assertEqual(len(install.RETIRED_TARGETS), 104)` — was 75 → 100 in the
commit, later 104 as platform families grew), a uniqueness check (`:84-85`), a
token check (`:96-98` every target contains `"watch-pr"`), a
manifest-disjointness check (`:102`
`manifest_targets.intersection(install.RETIRED_TARGETS)`), an install-output
assertion (`:174` `assertIn(f"{'retired':17} {STALE_WATCH_PR_SKILL}", result.stdout)`),
and `:307` `assert_paths_absent(root, install.RETIRED_TARGETS)`.

**The total will move from 104 to 182** (104 + 3 × 26) and the
manifest-disjointness assertion at `:102` is the check that catches a row added
before its manifest entries were removed.

### The rest of the 52 files

Deletions (all already removed by that precedent task; named here without
directory prefixes because the paths no longer exist): the skill, the
`.github/command-sources/` neutral body, and every generated adapter in both
`templates/` and the installed roots — `watch-pr.md` under `.claude/commands/sd/`,
`watch-pr.toml` under `.gemini/commands/sd/`, `sd-watch-pr.md` under
`.opencode/commands/`, `sd-watch-pr.prompt.md` under `.github/prompts/`,
`sd-watch-pr.md` under `templates/.commands/`, and so on.

Regenerated: `manifest.json` and `.sd-ai-command-pack/manifest.json` (−252
lines each), the `sd-help` command catalog (one row removed in each of its
generated roots), `docs/fleet/candidate-validation.json`.

Repointed prose: `README.md`, `docs/SD_AI_COMMAND_PACK.md`,
`docs/FLEET_ROLLOUT.md`, `.trellis/spec/frontend/adapter-guidelines.md`,
`sd-fix-ci`, `sd-fleet-refresh`, `sd-ship`, `sd-work-backlog`, `sd-help`
examples, `scripts/sd-ai-command-pack-status.py`.

**Successor written before the delete:** the commit added
`templates/.agents/skills/sd-ship/references/watch-coordinator.md` (+71 lines)
and registered it in `SHARED_SKILL_REFERENCES` (`installer/registry.py`,
`"sd-ship": ("references/watch-coordinator.md",)`) in the *same* commit that
removed the 128-line `sd-watch-pr/SKILL.md`. That is the direct precedent for
R9: the Fleet Integration-Only Recheck at
`templates/.agents/skills/sd-review-pr/SKILL.md:195-217` must land in
`sd-fleet-refresh` in or before the deletion commit.

## Ordered recipe for this task, from the precedent

1. Relocate the Fleet Integration-Only Recheck into
   `templates/.agents/skills/sd-fleet-refresh/SKILL.md` (R9). Verify it reads
   correctly there **before** anything is deleted — there is no in-release undo
   (PRD R6: rollback is reinstalling the last pre-cut release).
2. Delete the 51 skill/command/prompt/adapter files and the 12 script copies;
   delete the three whole test modules.
3. In the same commit, change `Makefile:101` to `check: test lint audit` and
   delete `Makefile:98-99` — `make` fails at parse time on a prerequisite whose
   target no longer exists, so a split leaves no working gate at all.
4. Flip the three registry rows: populate `identifiers`, set
   `source_paths_must_be_absent=True`, delete the three `CommandInfo` rows and
   the three `SUPERSEDED_COMMANDS` entries.
5. Add `RETIRED_FULL_CHECK_TARGETS` / `RETIRED_REVIEW_LOCAL_TARGETS` /
   `RETIRED_REVIEW_PR_TARGETS` to `installer/removal.py:65-75` and to
   `install.py`'s import and `__all__`.
6. Add allowances until the drift lint is green — one per genuinely historical
   reference, each with a `reason` in the existing style. The lint being red
   between steps 4 and 6 is the lint working.
7. Regenerate: `make generate`, `make sync`, refresh `manifest.json`,
   `.sd-ai-command-pack/*`, the command catalog in all five roots,
   `docs/fleet/surface-partition.json`, `docs/fleet/candidate-validation.json`.
8. Update `tests/test_retired_targets.py` counts (104 → 182) and add the three
   stale-file fixtures.
9. Prove the upgrade path on a real prior-release install, not a fixture.

## Caveats

- The precedent removed a surface that had **no scripts and no environment
  variables**. Nothing in commit `71d12d1f` shows how to retire a
  1087-line script whose environment keys are read by four surviving
  executables. That part of this task has no precedent — see the
  deletion-vs-refactor table in `retired-surface-inventory.md`.
- `sd-watch-pr` also had no schedule-only phase, so the flip from
  `source_paths_must_be_absent=False` to `True` has never actually been
  executed in this repo. The fleet-refresh row (`installer/registry.py:1359-1368`)
  is permanently `False` and is not a flip precedent.
- `removed_version="0.57.0"` was accurate when that commit shipped. The three
  rows here say `0.62.0` and the repo is at `0.64.35`, so this removal cannot
  reproduce the precedent's "row version equals shipping version" property.
