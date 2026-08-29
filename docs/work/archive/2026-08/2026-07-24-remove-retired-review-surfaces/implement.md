# Implementation — remove the sd-full-check and sd-review-local surfaces

> **Rescoped to Narrow 2026-08-09.** Two surfaces, not three. `sd-review-pr`
> and everything reachable only through it moved to
> `08-09-retire-review-pr-surface`. Read `design.md` first — the split changes
> what is *not* here, and most of the pre-split plan's hazards left with it:
> the `Makefile` gate, `run_pack_source_drift_gates`, `PRISM=0/GITO=0`, the
> `FULL_CHECK` env family, the plugin closure allowlist, R9's relocation, and
> both full-check test modules.
>
> Verified numbers (2026-08-09, enumerated from `manifest.json` and the live
> tree — never from a hand-written list):
> **53** manifest rows · **34** live files (17 per surface) · **4**
> `review-local.sh` copies · **2** registry rows flipped ·
> `RETIRED_TARGETS` **104 → 157**.

## Blocking prerequisites

Verify, do not assume.

```bash
grep -n "removed_version" installer/registry.py
```

**Gate:** the two schedule-only rows `full-check-command` and
`review-local-command` exist at `installer/registry.py:1387-1410` with
`identifiers=()`, `source_paths_must_be_absent=False`,
`removed_version="0.62.0"`, `owner_task="07-24-remove-retired-review-surfaces"`.
The third row, `review-pr-command`, **stays schedule-only** — leave it exactly
as it is. No rows means no schedule to execute against: stop (R8).

`removed_version` stays `0.62.0` (design D1). The earlier "update the inert
rows in place if the removal slips" instruction is **struck** — R8 forbids
minting a second version, and the slip is recorded in `CHANGELOG.md` instead.

```bash
# Enumerate every skill. Do not name the ones you expect to fail — that is how
# the original gate missed sd-fleet-refresh.
grep -rn "sd-full-check\|sd-review-local" templates/.agents/skills/*/SKILL.md
```

**Gate:** five surviving skills name a surface being deleted, exactly one of
them as a live caller. Take this table from the grep output, not from the table
— it has already been wrong twice.

| Site | Kind | Action |
|---|---|---|
| `sd-fix-ci/SKILL.md:43,47,109` | **live caller** — "the local gate every fix must pass" | repoint to `sd-check` |
| `sd-check/SKILL.md:76` | negative instruction ("do not call `sd-full-check` or read its environment/package-hook contract") | delete — vacuous once gone |
| `sd-review/SKILL.md:15` | supersession prose listing what it replaced | reword; keep `sd-review-pr` |
| `sd-test-gaps/SKILL.md:26` | positioning prose — "complements `sd-full-check` (the gate that proves configured floors…)" | repoint to `sd-check` |
| `sd-audit-repo/SKILL.md:39,40,275,276` | positioning prose ×2 — "complements `sd-review-local` (provider loop), `sd-review-pr` (PR loop), and `sd-full-check` (gate)" | rewrite both blocks; keep the `sd-review-pr` clause |

All paths are under `templates/.agents/skills/`. `sd-review-local/SKILL.md:251`
needs nothing — it is inside a skill being deleted. Hits naming only
`sd-review-pr` are **not** in scope (PRD R7) — that surface still ships.

PRD dependencies remain satisfied: `07-24-implement-read-only-sd-check`,
`07-24-implement-unified-routed-sd-review`, and
`07-24-simplify-review-shipping-composition` are archived.

## Order

Three commits, per design D8. The payload release gate diffs the **PR base SHA**
to HEAD (`full-check.sh:709-717`, `tests.yml:652`), so the PR carries **one**
version bump and **one** `CHANGELOG.md` heading — landed in commit 1 — while the
**exact candidate ledger is per-head** and must be refreshed in every commit
that changes `templates/**`.

**Order within any commit that regenerates.** `make generate` ends with
`surface-check.py` (`Makefile:19-23`), which runs the fleet candidate checker
and fails on a stale ledger (`surface-check.py:673`). Refreshing the ledger
*after* `make generate` therefore never passes on the first run. Use:

```bash
python3 .github/scripts/generate-command-surfaces.py
python3 .github/scripts/partition-surfaces.py
python3 .github/scripts/generate-plugin.py
python3 scripts/sd-ai-command-pack-fleet-candidate-check.py   # refresh the ledger
python3 scripts/sd-ai-command-pack-surface-check.py            # verify last
make sync
```

`make generate` is then a final verification, not the first step. The bare
candidate-check invocation is the one that **writes** the ledger — it clones and
checks each consumer, so it is slow and needs network. `--check-ledger` (what
`surface-check.py:679` runs) only verifies, and a `--consumer`-limited run never
writes at all.

### Commit 1 — repoint live callers while the old surfaces still work

1. **Recount before sizing.** The deletion target is **53**:

   ```bash
   python3 - <<'PY'
   import json
   files = json.load(open("manifest.json"))["files"]
   blob = lambda f: json.dumps(f)
   surf = [f for f in files if any(t in blob(f) for t in
           ("sd-full-check", "sd-review-local"))]
   extra = [f for f in files if f not in surf and any(t in blob(f) for t in
            ("/full-check.", "/review-local.",
             "sd-ai-command-pack-review-local.sh"))]
   print(len(surf), "+", len(extra), "=", len(surf) + len(extra))
   PY
   ```

   Expect `48 + 5 = 53`. Rows for `review-local.py`, `review-preflight.mjs`,
   `full-check.sh`, and `review-full-check.sh` must **not** appear — those four
   files survive. `sd-review-local-all` rows are already retired and out of
   scope.

2. **Repoint `sd-fix-ci` to `sd-check`**; delete `sd-check:76`'s now-vacuous
   negative instruction; reword `sd-review:15`. Edit
   `templates/.agents/skills/<name>/SKILL.md` (the source), then regenerate into
   every shipped root.

3. `make generate && make sync`, version bump, changelog heading, candidate
   ledger.

   **Gate:** this lands while `sd-full-check` and `sd-review-local` still exist
   and still work, so the repoint is provable independently of the deletion.

### Commit 2 — the atomic cutover

This cannot be subdivided: deleting files and regenerating while the
`CommandInfo` rows still exist **recreates** the manifest rows
(`generate-command-surfaces.py:1092`), and dropping `CommandInfo` without the
matching `SUPERSEDED_COMMANDS` keys fails at **module import**
(`installer/registry.py:1801`).

4. **Delete the two surfaces** — 34 live files across `templates/.agents/skills/`,
   `templates/.commands/`, `templates/.claude/commands/sd/`,
   `templates/.gemini/commands/sd/`, `templates/.github/prompts/`,
   `.github/command-sources/`, their installed source-checkout mirrors, the 2
   Claude-plugin payload copies, and the 3 machine-payload copies — plus
   `sd-ai-command-pack-review-local.sh` in all four script trees (`scripts/`,
   `templates/scripts/`, `plugins/sd/bin/`,
   `plugins/sd/machine-payload/scripts/`). Deleting only the consumer copy makes
   `make sync` regenerate the script from the surviving template.

   **Do not delete** `scripts/sd-ai-command-pack-review-local.py` — it is
   `sd-review`'s local-review stage (`review.py:37,:718,:720`).

4b. **Delete the `review-local.sh` manifest row by hand** (`manifest.json:268`,
   `kind: script`). Regeneration will **not** drop it: `generate_manifest_text()`
   re-reads the existing `manifest.json` (`generate-command-surfaces.py:256,:1086`),
   rebuilds only command- and agent-shaped rows, and carries every other entry
   through verbatim (`:1087-1101`). Delete the files without this edit and the
   manifest keeps a row pointing at a source that no longer exists — and the
   recount in step 1 counts this row as one of the 53. The 48 command rows *are*
   derived and do disappear on regeneration once the `CommandInfo` rows are gone
   (step 5).

5. **Flip the two registry rows** (`installer/registry.py:1387-1410`) to match
   the `watch-pr-command` precedent exactly (`:1376-1382`): set
   `identifiers=("sd-full-check",)` / `("sd-review-local",)` — the **long name
   only**; a bare `full-check` identifier would fire on the surviving
   `full-check.sh`, the `Makefile` target, and every `FULL_CHECK` env key — and
   **delete** the `source_paths_must_be_absent=False` line rather than setting
   it to `True`, since enforcing rows omit the field. Keep
   `removed_version="0.62.0"`.

   **Populate `configuration_keys` on the `review-local-command` row (R5).**
   `identifiers` alone does not lint environment names: the drift lint's
   `retired_identifiers` set is `(*identifiers, *configuration_keys)`
   (`check-command-surface-drift.py:485-489`) and the field defaults to empty
   (`installer/registry.py:1339`). Without it, a reintroduced
   `SD_AI_COMMAND_PACK_REVIEW_LOCAL_*` reader passes the lint silently and R5 is
   unenforceable. The 23 concrete keys:

   ```
   ..._REVIEW_LOCAL_ALL_CUSTOM_COMMAND        ..._REVIEW_LOCAL_PRISM_CODEBASE_BATCH_SIZE
   ..._REVIEW_LOCAL_ALL_GITO_OUT_DIR          ..._REVIEW_LOCAL_PRISM_CODEBASE_FALLBACK
   ..._REVIEW_LOCAL_BASE_REF                  ..._REVIEW_LOCAL_PRISM_CODEBASE_MAX_EMPTY_CHUNK_FAILURES
   ..._REVIEW_LOCAL_CUSTOM_COMMAND            ..._REVIEW_LOCAL_PRISM_EXCLUDE
   ..._REVIEW_LOCAL_GITO_BASE_REF             ..._REVIEW_LOCAL_PRISM_FAIL_ON
   ..._REVIEW_LOCAL_GITO_MAX_ATTEMPTS         ..._REVIEW_LOCAL_PRISM_MAX_FINDINGS
   ..._REVIEW_LOCAL_GITO_MODE                 ..._REVIEW_LOCAL_PRISM_MODE
   ..._REVIEW_LOCAL_GITO_OUT_DIR              ..._REVIEW_LOCAL_PRISM_RULES
   ..._REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS  ..._REVIEW_LOCAL_PRISM_TIMEOUT_SECONDS
   ..._REVIEW_LOCAL_GITO_RETRY_MAX_DELAY_SECONDS  ..._REVIEW_LOCAL_SCOPE
   ..._REVIEW_LOCAL_GITO_TIMEOUT_SECONDS      ..._REVIEW_LOCAL_SEMGREP_COMMAND
   ..._REVIEW_LOCAL_TOOLS                     ..._REVIEW_LOCAL_UV_*  (prefix — see below)
   ```

   Verified safe: no live `CommandInfo` declares any of them, so the
   `config_overlap` check (`:1626`) cannot fire, and no other retired row
   declares them, so `repeated_keys` (`:1633`) cannot either.

   The lint matches whole tokens (`check-command-surface-drift.py:271`), so a
   **prefix stub** like `..._REVIEW_LOCAL_UV_` matches only that literal string,
   not the keys built from it. List concrete keys, not prefixes; where only a
   prefix is documented (`README.md`, the docs' `..._REVIEW_LOCAL_UV_` and
   `..._REVIEW_LOCAL_ALL_<TOOL>_COMMAND` placeholders), delete the prose rather
   than expecting the lint to catch it.

   This is deliberately expensive: with the keys listed, the lint demands that
   all ~392 repo-wide occurrences be deleted or allowanced. That is R5 working.

   In the same edit remove the two live `CommandInfo` rows and the two
   `SUPERSEDED_COMMANDS` entries (`:1436-1440`).

   Three things about the surviving `review-pr-command` row:
   - it stays schedule-only — `identifiers=()`,
     `source_paths_must_be_absent=False`, `removed_version="0.62.0"`;
   - its `owner_task` changes to `"08-09-retire-review-pr-surface"`. Leaving
     `07-24-remove-retired-review-surfaces` there points the registry at a task
     that archived without deleting the surface;
   - the block comment at `:1383-1386` says "the **three** transitional review
     surfaces still ship" — correct it to one.

6. **Extend `installed_targets` with the script path.**
   `command_installed_targets("sd-review-local", "review-local")` returns 26
   command paths and **zero** under `scripts/`, so the row alone leaves every
   consumer copy of `review-local.sh` undeletable forever (R4). Append the
   **consumer-install** path `scripts/sd-ai-command-pack-review-local.sh` to the
   `review-local-command` row. **Never** the `templates/scripts/` twin: that is
   a manifest *source*, and listing it marks a consumer-owned file for
   unconditional deletion under `--force`.

   `full-check-command` gets **no** script path — `full-check.sh` survives.

7. **Register both families in `RETIRED_TARGETS`** (`installer/removal.py:65-75`).
   The tuple is hand-enumerated, not a comprehension over
   `RETIRED_COMMAND_SURFACES`, so a registry row is inert at install time until
   this lands. Add:

   ```python
   RETIRED_FULL_CHECK_TARGETS = retired_surface_targets("full-check-command")
   RETIRED_REVIEW_LOCAL_TARGETS = retired_surface_targets("review-local-command")
   ```

   splat both into `RETIRED_TARGETS`, and add each to `install.py`'s re-export
   (`install.py:127`) and `__all__` (`:169`) — the watch-pr precedent changed
   exactly those two lines.

8. **Update `tests/test_retired_targets.py`**: `RETIRED_FULL_CHECK_TARGETS` is
   **26**, `RETIRED_REVIEW_LOCAL_TARGETS` is **27** (26 command paths + 1
   script), total `RETIRED_TARGETS` **104 → 157**. Add per-family substring
   loops matching the existing style (`assertIn("full-check", target)`,
   `assertIn("review-local", target)`), a stale-file fixture per surface, and —
   decisively — a fixture proving a stale **script** copy is retired. The
   command-path fixtures would not have caught the missing script registration.

   The manifest-disjointness assertion (`:102`) is the tripwire for rows added
   before their manifest entries were removed: expect it to fail if step 4's
   regeneration has not run.

9. **Delete the `SD_AI_COMMAND_PACK_REVIEW_LOCAL_*` family (R2)** — including
   the four dormant readers inside the **surviving** `full-check.sh` (design
   D7):

   ```
   :166  ..._FULL_CHECK_GITO_MAX_ATTEMPTS:-${..._REVIEW_LOCAL_GITO_MAX_ATTEMPTS:-2}
   :170  ..._FULL_CHECK_GITO_RETRY_DELAY_SECONDS:-${..._REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS:-30}
   :174  ..._FULL_CHECK_GITO_RETRY_MAX_DELAY_SECONDS:-${..._REVIEW_LOCAL_GITO_RETRY_MAX_DELAY_SECONDS:-120}
   :178  ..._FULL_CHECK_GITO_TIMEOUT_SECONDS:-${..._REVIEW_LOCAL_GITO_TIMEOUT_SECONDS:-600}
   ```

   Drop the `REVIEW_LOCAL` half of each `:-` chain; keep the `FULL_CHECK`
   primary and the literal default. ×4 script trees, byte-identical.

10. **Refactor the surviving executables that name the deleted things:**

    - `scripts/sd-ai-command-pack-install-audit.py:138,:196` — `LEGACY_PACK_PATHS`
      / `LEGACY_PACK_REFERENCES` map `trellis-full-check → "use sd-full-check"`.
      Repoint the advice to `sd-check`; a migration hint pointing at a deleted
      command is worse than none.
    - `install-audit.py:162,:163` — `full-check` and `review-local` in the
      `sd-command-pack-*` legacy-name list; `:183,:216` — `review-local.sh` in
      the per-script lists. Remove the entries whose successor no longer exists.
    - `scripts/sd-ai-command-pack-pr-body-scope.py:301` — path literal
      `scripts/sd-ai-command-pack-review-local.sh`, **paired with**
      `installer/references.py:157`, which allowlists that same literal as
      `pr-body-scope.py`'s consumer-layout data. Remove both together: the
      reference gate fails on a literal without its allowance, and an allowance
      without its literal is dead configuration.
    - `README.md:614` — `bash -n scripts/sd-ai-command-pack-review-local.sh`.
    - `.github/scripts/generate-command-surfaces.py:125-152` —
      `CLAUDE_COMMAND_BODY_INSERTIONS["review-local"]`, the Claude-only native
      Codex lane text keyed to the deleted command. Delete the whole entry; the
      parity tests import this mapping and strip the insert before comparing
      bodies, so a stale key desynchronizes generation from parity.
    - `.github/scripts/generate-command-surfaces.py:175` — `"review-local"` in
      `GEMINI_SD_HEADING_STRIPPED`, a committed-bytes stability list. Remove it.
      `"full-check"` is not in the list; `"review-pr"` stays.
    - `.github/scripts/kcov-bash-shim.sh:61` — a comment naming `review-local.sh`
      as an observer of the shim's behavior. Comment-only, but it is the last
      written claim that the script exists.

    **`full-check.sh` references stay.** `installer/references.py:111,:137,:152,:186,:194`
    and `scripts/sd-ai-command-pack-toolchain.sh:274,:309,:321,:381,:414,:415`
    all name the surviving script — touching them here is a defect. Only
    `references.py:157` (the `review-local.sh` literal) changes.

    Every `scripts/` edit is ×4; `make generate` + `make sync` must reproduce
    them byte-identically.

    **Grep discipline:** anchor `SD_AI_COMMAND_PACK_REVIEW_LOCAL` searches to
    the trailing underscore or exact key names, and remember that
    `sd-review-local-stage` / `sd-review-local-policy` are deliberate residue
    (PRD "Deliberate residue"). A bare substring search reports them as misses.

11. **Documentation and specs (R3):** `README.md`, `docs/SD_AI_COMMAND_PACK.md`
    (×3 copies), `.trellis/spec/frontend/index.md`,
    `frontend/adapter-guidelines.md`, `frontend/directory-structure.md:56-59`,
    `backend/manifest-and-filesystem.md:671`. Successor documentation only — no
    "formerly known as" prose that reintroduces the identifier outside an
    allowanced historical note.

12. **Tests (R3, R6):** delete `tests/test_review_local.py` (1435 lines) whole.
    Prune retired-surface assertions from the modules that pin them —
    `tests/test_generated_parity.py` (29 hits), `tests/test_install_core.py` (18,
    including `:3272,:3280` asserting the `sd-review-local` skill *does* invoke
    `review-local.sh`), `tests/test_surface_generation.py`,
    `tests/test_review_scope.py`, `tests/test_audit_repo.py`,
    `tests/test_machine_stage.py`, `tests/test_command_surface_drift.py`.
    Inverted assertions are **deleted, not edited** — an assertion that a
    deleted thing does not appear is vacuous, and
    `tests/test_script_lib.py:327` (`assertNotIn("SD_AI_COMMAND_PACK_REVIEW_LOCAL_UV_", shell_lib)`)
    is exactly that shape. `tests/test_install_core.py:3273,:3293` assert the
    deleted skill *does* carry `..._REVIEW_LOCAL_TOOLS` and
    `..._REVIEW_LOCAL_ALL_<TOOL>_COMMAND`; both go with it.

    **Keep and do not touch:** `tests/test_full_check.py` and
    `tests/test_review_full_check.py` (they test surviving scripts; their six
    `sd-full-check` hits are `tempfile` prefixes, and the drift lint's token
    boundary rejects hyphen-suffixed matches, so they need no allowance).
    **Negative control:** `tests/test_review_controller.py`,
    `tests/test_review_stage.py`, `tests/test_verdict_vocabulary.py`,
    `tests/test_git_invocation_boundary.py` must pass unchanged.

13. **Audit ledger (R11, design D4).** Do **not** mark A-102 or A-114
    `resolved-by-removal` — both die with `full-check.sh` and the
    `sd-full-check` **contract text**, and this task deletes only the latter.
    Re-own both rows in `.trellis/audit/ledger.md` to
    `08-09-retire-review-pr-surface`; the originally named fallback owner
    `07-28-retire-transitional-review-surfaces` is archived. Leaving them silent
    is the failure mode: it reads as done.

14. **CHANGELOG entry (design D6).** It must state that `sd-full-check` and
    `sd-review-local`, announced for removal in `0.62.0`, were actually removed
    in the shipping version. D1's decision to keep `removed_version="0.62.0"`
    depends on this entry existing.

15. `make generate && make sync`, version bump, candidate ledger refresh.

16. **Refresh the fleet candidate ledger.** 53 changed manifest rows stale
    `docs/fleet/candidate-validation.json`, and `surface-check.py:691` rejects a
    stale payload digest. Run the candidate check (orchestrated path:
    `.github/scripts/prepare-release.py:335`) and commit the refreshed ledger —
    it cannot be deferred to release time, since `make generate`'s surface-check
    step fails on it.

### Commit 3 — lint the absence (R5)

Fold into commit 2 if allowances are needed to make `make generate` green — see
below.

17. Enumerate `CommandSurfaceAllowance` entries for genuinely historical
    references: the `CHANGELOG.md` entry from step 14, any README migration
    note, retirement fixtures, and — per the watch-pr precedent
    (`installer/registry.py:1547-1551`) — the generated plugin-copy row, without
    which `make generate` output trips the lint.

    Each allowance carries a `reason` naming why the reference is historical
    rather than live. **The lint will be red until every occurrence is deleted
    or allowed, and that redness is the lint working.** Resist one allowance per
    red line: an allowlist grown to green verifies nothing. `sd-review-local-all`
    needed six; watch-pr needed five plus the plugin-copy row. Count them; a
    large count is a finding.

    **Ordering constraint:** `make generate` runs `surface-check.py`, which
    incorporates drift findings (`:751`) and exits nonzero (`:895`), and
    `tests/test_command_surface_drift.py:94` requires the live repository to be
    clean. So commit 2 must not be pushed with a red lint — if allowances are
    what make it green, they belong in commit 2 and this commit collapses into
    it.

18. **Prove uninstall on a real prior-release install**, not only fixtures:
    unchanged vouched copy deleted (command paths **and**
    `scripts/sd-ai-command-pack-review-local.sh`), locally modified copy
    preserved and reported, empty directories pruned, no retired path in the new
    receipt.

    **Gate:** a wrong `recorded_hash` silently *preserves* instead of removing,
    and the receipt still looks clean either way — so this must be observed on
    disk, not asserted.

19. **File the follow-ups** (recording them is the step):
    - correct `08-07-default-local-review-lanes`, whose `implement.md:332` edits
      the deleted `review-local.sh` and whose AC8 (`prd.md:211`) runs it — its
      goal survives in `review-local.py:251,:266` and `review.py:220` (design
      D5);
    - rename the successor's internal `sd-review-local-stage` /
      `sd-review-local-policy` identifiers (receipt-schema change);
    - route `make check` through `sd-check` — deferred with `full-check.sh` to
      `08-09-retire-review-pr-surface`.

## Validation

The decisive absence check:

```bash
python3 .github/scripts/check-command-surface-drift.py
```

Nothing retired survives a fresh install. **Token-bounded** — a bare substring
grep fails on the deliberate `sd-review-local-stage` residue:

```bash
rm -rf /tmp/sdcut && mkdir -p /tmp/sdcut && git -C /tmp/sdcut init -q && python3 install.py /tmp/sdcut
grep -rEn "sd-full-check([^-]|$)|sd-review-local([^-]|$)" /tmp/sdcut | head
```

Expect no output. `sd-review-pr` and `full-check.sh` **will** be present — they
still ship.

This repo runs `unittest` through `.venv`, not `pytest` — `make test` is
`.github/scripts/run-tests.sh` plus a 100%-coverage floor on `install.py` and
`installer/*` and two shipped-script checks. For the focused pass:

```bash
.venv/bin/python -m unittest -q \
  tests.test_retired_targets tests.test_install_core \
  tests.test_command_surface_drift tests.test_generated_parity \
  tests.test_full_check tests.test_review_full_check \
  tests.test_review_controller tests.test_review_stage
```

Deleting `tests/test_review_local.py` (1435 lines) can drop `installer/*`
coverage below the `--fail-under=100` floor even though the deletion is correct;
`make test` is where that surfaces, not the focused run.

The last four are the **negative control**: two exercise the surviving
`full-check.sh` / `review-full-check.sh`, two the surviving `review-local.py`. A
green run proves the deletion took neither the successor's local-review stage
nor the surviving full-check scripts with it.

Public-caller verification (R7) — **glob every surface root**, do not name the
ones expected to fail. The current table was wrong twice because it was
hand-written:

```bash
grep -rEn "sd-full-check([^-]|$)|sd-review-local([^-]|$)" \
  templates/.agents/skills/*/SKILL.md templates/.commands/*.md \
  templates/.claude/commands/sd/*.md templates/.gemini/commands/sd/*.toml \
  templates/.github/prompts/*.md .github/command-sources/*.md \
  .github/workflows/*.yml
```

Every surviving hit must be an allowanced historical reference; every live
caller must name only `sd-check`, `sd-review`, `sd-create-pr`, `sd-ship`,
`sd-housekeeping`, or the still-shipping `sd-review-pr`.

Generated-tree gates:

```bash
make generate && python3 .github/scripts/generate-plugin.py --check
python3 .github/scripts/partition-surfaces.py
python3 scripts/sd-ai-command-pack-install-audit.py   # rejects reintroduced retired targets
```

Env-family residue:

```bash
grep -rn "SD_AI_COMMAND_PACK_REVIEW_LOCAL_" --exclude-dir=.git --exclude-dir=.trellis . \
  | grep -v CHANGELOG.md
```

Expect only allowanced historical hits; baseline before the cut is **392**
occurrences repo-wide. `SD_AI_COMMAND_PACK_FULL_CHECK_*` must **survive** — it
belongs to the surviving script.

```bash
make sync && make check
```

`make check` is unchanged (`test lint audit full-check`) — `full-check.sh`
survives this task, so a `Makefile` edit here is a defect, not progress.

## Review gates

- The `review-pr-command` registry row is still schedule-only and
  `full-check.sh` / `review-full-check.sh` still exist at the end of this task.
- Commit 1 lands while the retired surfaces still work.
- Commit 2 is atomic: no intermediate state where the repo is unimportable or
  regeneration recreates deleted rows.
- Every commit that touches `templates/**` carries a version bump, a matching
  changelog heading, and an exact candidate ledger at that head.
- Step 18 observed on a real prior install, not asserted from fixtures.
- Every allowance carries a reason. Count them.
- No new `removed_version` value appears anywhere (R8).
- A-102 and A-114 are **re-owned**, not resolved (R11, design D4).

## Rollback

Release-level reinstall of the last pre-cut release (R6). There is no in-release
undo, which is why commit 1 is separate and step 18 is observed rather than
asserted.
