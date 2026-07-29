# Implementation — remove all retired review and check surfaces

## Blocking prerequisites

All three must be verified, not assumed:

```bash
grep -n "removed_version" installer/registry.py
```

**Gate:** four schedule-only rows exist for `sd-full-check`, `sd-review-local`,
`sd-review-pr`, `sd-watch-pr` (from `07-28-retire-transitional-review-surfaces`).
No rows, no schedule to execute against — stop (R8).

```bash
grep -rn "sd-review-pr\|sd-watch-pr\|sd-review-local" .agents/skills/sd-ship/SKILL.md .agents/skills/sd-work-backlog/SKILL.md
```

**Gate:** no live caller. `07-24-simplify-review-shipping-composition` R7 must
have repointed the delivery path first.

Plus the PRD's stated dependencies: `07-24-implement-read-only-sd-check` and
`07-24-implement-unified-routed-sd-review` landed.

## Order

### Stage 0 — decide, before deleting anything

1. **Apply the decided `make check` composition.** Decided in planning
   (2026-07-28), not deferred: **option A — `check: test lint audit`.**
   `Makefile:94` is `check: test lint audit full-check`, and `full-check` is
   `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0
   bash scripts/sd-ai-command-pack-full-check.sh` (`Makefile:91-92`). Both AI
   lanes are hard-disabled, so dropping the target removes a wrapper around
   already-dead lanes. Option B (`check: … sd-check`) is rejected here: it
   couples the repo's own gate to a successor CLI surface inside the same commit
   that deletes four command families, and a gate failure would then be
   ambiguous between the deletion and the new coupling. Route `make check`
   through `sd-check` as a separate follow-up if wanted.
   **Gate:** the `full-check` target and the `check` dependency on it disappear
   in the same commit as the script. A `check` target naming a deleted
   prerequisite fails at parse time, so a split commit leaves no working gate.

2. **Recount the surface.** The PRD says 79 manifest targets; measured 105.
   ```bash
   python3 -c "import json;m=json.load(open('manifest.json'));print(sum(1 for f in m['files'] if any(n in json.dumps(f) for n in ('sd-full-check','sd-review-local','sd-review-pr','sd-watch-pr'))))"
   ```
   Record the current number as the deletion target.

### Stage 1 — relocate before deleting (R9)

3. Move the Fleet Integration-Only Recheck procedure from
   `templates/.agents/skills/sd-review-pr/SKILL.md:196` into the source-only
   `sd-fleet-refresh` skill. It calls `fleet-review-classify.py`, listed
   source-only at `install-audit.py:112-118`, so it is dead in all 11 shipped
   copies but is the only written record of the procedure.
   **Gate:** the procedure is reachable from `sd-fleet-refresh` and its script
   reference resolves, verified before stage 2 starts. Deletion is irreversible
   within the release (R6).

### Stage 2 — delete (R1, R2, R3, R6, R10)

4. Delete skills, commands, prompts, workflows, adapters, scripts, and registry
   entries for the four surfaces across every platform, and regenerate.

5. Apply the stage-0 Makefile decision **in the same commit**. Remove the
   `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0` / `..._GITO=0` disabling together with
   the lanes it gated (R10) — these are inseparable, because removing the
   disabling without deleting the lanes enables code that has never run in this
   repo's gate.

6. Remove the environment-variable families, the package `check:full` hook, shell
   string command readers, direct Copilot/custom-remote dispatch, reviewer-author
   matching, and the old output/state formats (R2). No ignored readers.

7. Remove old help/catalog/examples, README/guide/spec claims, workflow names,
   pinning tests, manifest targets, installed receipts, provenance entries, and
   candidate-ledger expectations (R3).

### Stage 3 — retirement register (R4, R11)

8. Flip the four registry rows: populate `identifiers`, set
   `source_paths_must_be_absent=True`, keep the pre-registered `removed_version`
   unchanged (R8 — do not mint a second version).

9. Add the four target families to `RETIRED_TARGETS`
   (`installer/removal.py:69-73`). This tuple is hand-maintained; without this
   edit uninstall never reaches the old copies.

10. **Prove uninstall on a real prior-release install**, not only fixtures:
    unchanged vouched copy deleted, locally modified copy preserved and reported,
    empty dirs pruned, no retired path in the new receipt.
    **Gate:** a wrong `recorded_hash` silently *preserves* instead of removing,
    and the receipt still looks clean — so this must be observed on disk.

10b. **Record the two findings that die with the deletion (R11).** Neither is
    fixed here; both are resolved *by* removal, and a register that does not say
    so invites their rediscovery as open work against files that no longer exist:

    ```
    A-102   gito filter argv overflow    full-check.sh:231 :256 :261 :454
                                         measured 142,524 joined bytes,
                                         past Linux MAX_ARG_STRLEN
    A-114   stale contract               sd-full-check/SKILL.md:32 :104
    ```

    Mark both `resolved-by-removal` in `.trellis/audit/ledger.md`, in the same
    commit that lands the deletion — not before it.

    **The ledger is the only place these go.** `RetiredCommandSurface`
    (`installer/registry.py:1226-1234`) has fields `id`, `identifiers`,
    `installed_targets`, `removed_version`, `owner_task`,
    `source_paths_must_be_absent`, `configuration_keys` — and no finding or
    evidence field. Do not extend the dataclass to carry audit IDs: the registry
    is consumed by the drift and removal checks, which would then have a second
    reason to change whenever an audit is re-run. `owner_task` already points at
    this task, and this task's ledger rows carry the findings.

    **Gate:** R11's condition is a slip, not a date. If the deletion does **not**
    land by the announced `removed_version`, these two stop being resolved and
    become live P-findings needing interim fixes — and those fixes belong to
    `07-28-retire-transitional-review-surfaces`, not to this task. Check the
    announced `removed_version` against the release actually shipping before
    marking either row resolved; if it slipped, hand both to that task instead
    and leave the ledger rows open.

### Stage 4 — lint the absence (R5, R7)

11. Enumerate `CommandSurfaceAllowance` entries for the genuinely historical
    references (CHANGELOG, README migration note, retirement fixtures). Each needs
    a `reason` naming why it is historical.
    **Gate:** the lint will be red until every remaining occurrence is either
    deleted or allowed. Resist adding an allowance per red line — an allowlist
    grown to green is a lint that verifies nothing.

12. Verify all public callers use only `sd-check`, `sd-review`, `sd-create-pr`,
    `sd-ship`, `sd-housekeeping` (R7).

13. `make sync`.

## Validation

The decisive absence check:

```bash
python3 .github/scripts/check-command-surface-drift.py
```

Nothing retired survives in a fresh install:

```bash
rm -rf /tmp/sdcut && mkdir -p /tmp/sdcut && git -C /tmp/sdcut init -q && python3 install.py /tmp/sdcut
grep -rl "sd-review-pr\|sd-watch-pr\|sd-review-local\|sd-full-check" /tmp/sdcut | head
```

Expect no output.

```bash
python3 -m pytest tests/test_retired_targets.py tests/test_install_core.py tests/test_command_surface_drift.py -q
```

```bash
make sync && make check
```

## Review gates

- Stage 0 complete before any deletion: the `make check` composition is decided.
- Stage 1 verified before stage 2: the fleet recheck procedure is reachable from
  `sd-fleet-refresh`.
- Stage 3 step 10 observed on a real prior install, not asserted from fixtures.
- Stage 4: every allowance carries a reason. Count them; a large count is a
  finding, not a formality.
- No new `removed_version` value appears anywhere (R8).
- A-102 and A-114 are marked `resolved-by-removal` in the same commit as the
  deletion, or handed to `07-28-retire-transitional-review-surfaces` if the
  removal slipped past the announced `removed_version` (R11, step 10b). Silence
  on both is the failure mode: it reads as done and leaves them open.

## Rollback

Release-level reinstall of the last pre-cut release (R6). There is no in-release
undo, which is why stages 0 and 1 gate everything else.
