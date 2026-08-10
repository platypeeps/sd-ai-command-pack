# Research: retired review/check surface inventory

- **Query**: Complete live-artifact inventory for `sd-full-check`,
  `sd-review-local`, `sd-review-pr`, `sd-watch-pr`; deletion-vs-refactor
  classification for anything a surviving successor depends on.
- **Scope**: internal
- **Date**: 2026-08-09
- **Repo state**: branch `feat/thin-machine-installer`, version `0.64.35`
  (`manifest.json:3`). Working tree has uncommitted changes in
  `installer/references.py` (new), `installer/machinestage.py` (new),
  `.github/scripts/generate-plugin.py`, `install.py`,
  `installer/machinescope.py`.

## Headline corrections to the plan's numbers

| plan claim | measured 2026-08-09 |
|---|---|
| PRD: "79 review/full-check manifest targets" | **72** rows for the three `sd-`-prefixed surfaces (24 each), **+11** script/short-name rows = **83** total in `manifest.json` |
| design.md: 23 manifest entries per surface | **24** per surface |
| design.md: `sd-watch-pr` = 23 entries | **0** — already fully deleted |
| design.md: `sd-review-pr/SKILL.md` fans out to 11 targets | **11** confirmed (`manifest.json`, 1 shared + 10 platform skill rows) |
| PRD/design: removal version `0.62.0` | **already passed.** Current version is `0.64.35`. The announced removal shipped ~2.35 minor releases ago and the surfaces still ship. See "Schedule already slipped" below. |
| PRD R2/R10: "package `check:full` hook" | **does not exist.** `package.json` has no `scripts` block at all (7 lines, `devDependencies: {c8}` only). The `check:full` string lives only *inside* `sd-ai-command-pack-review-full-check.sh:74` as an invocation of a hook the consumer repo might define. Nothing to remove from `package.json`. |

## Findings

### 1. Live command/skill/adapter files — 17 per surface, 51 total

`sd-watch-pr`: **0 live files.** Fully removed at 0.57.0; only the registry
row, three allowances, and archived task/journal text remain.

Identical shape for all three surviving surfaces. Substitute
`<SURFACE>` = `full-check` | `review-local` | `review-pr`:

**Authored sources (5)**

| File | Role |
|---|---|
| `templates/.agents/skills/sd-<SURFACE>/SKILL.md` | canonical skill; fans out to 11 platform targets |
| `templates/.commands/sd-<SURFACE>.md` | generated neutral command body; fans out to 9 platforms |
| `templates/.claude/commands/sd/<SURFACE>.md` | generated Claude command |
| `templates/.gemini/commands/sd/<SURFACE>.toml` | generated Gemini command |
| `templates/.github/prompts/sd-<SURFACE>.prompt.md` | generated GitHub prompt |
| `.github/command-sources/sd-<SURFACE>.md` | **authored neutral body** — the true source the generator reads (`.trellis/spec/frontend/directory-structure.md:56`) |

(That is 6 rows; `templates/.commands/…` is generated *from*
`.github/command-sources/…`.)

**Installed-into-source-checkout mirrors (6)**

`.agents/skills/sd-<SURFACE>/SKILL.md`,
`.claude/skills/sd-<SURFACE>/SKILL.md`,
`.claude/commands/sd/<SURFACE>.md`,
`.gemini/commands/sd/<SURFACE>.toml`,
`.opencode/commands/sd-<SURFACE>.md`,
`.github/prompts/sd-<SURFACE>.prompt.md`

**Claude-plugin payload (2)**

`plugins/sd/skills/sd-<SURFACE>/SKILL.md`,
`plugins/sd/commands/<SURFACE>.md`

**Machine payload (3)**

`plugins/sd/machine-payload/.agents/skills/sd-<SURFACE>/SKILL.md`,
`plugins/sd/machine-payload/.opencode/commands/sd-<SURFACE>.md`,
`plugins/sd/machine-payload/.gemini/commands/sd/<SURFACE>.toml`

Backups under `.trellis/.backup-*/` also carry copies; they are snapshot
artifacts, not live surfaces.

### 2. Scripts

Four trees carry byte-identical script copies: `scripts/` (installed),
`templates/scripts/` (source), `plugins/sd/bin/` (plugin payload),
`plugins/sd/machine-payload/scripts/` (machine payload). Line counts from
`scripts/`.

| Script | Lines | Classification |
|---|---|---|
| `sd-ai-command-pack-full-check.sh` | 1087 | **DELETE** (×4 copies) |
| `sd-ai-command-pack-review-full-check.sh` | 79 | **DELETE** (×4) — thin wrapper; `:24` resolves `full-check.sh`, `:74`/`:79` exec it |
| `sd-ai-command-pack-review-local.sh` | 771 | **DELETE** (×4) — no surviving code caller |
| `sd-ai-command-pack-review-local.py` | 2354 | **KEEP — live dependency of the successor.** See §5 |
| `sd-ai-command-pack-review-preflight.mjs` | 5480 | **KEEP** — survivor; used by `sd-check`, `sd-create-pr`, `sd-finish-work` |
| `sd-ai-command-pack-review-scope.sh` | 437 | **KEEP** — survivor; used by `sd-check`, `pr-body-scope`, preflight |
| `sd-ai-command-pack-review.py` | 2142 | **KEEP** — the successor coordinator |
| `sd-ai-command-pack-fleet-review-classify.py` | 519 | **KEEP** — source-only fleet tool (`install-audit.py:119`) |

No `watch-pr` script exists in any tree.

### 3. Manifest — 83 rows

`manifest.json` has 777 file entries total.

| token | rows |
|---|---|
| `sd-full-check` | 24 |
| `sd-review-local` | 24 |
| `sd-review-pr` | 24 |
| `sd-watch-pr` | 0 |
| script rows (`full-check.sh`, `review-full-check.sh`, `review-local.sh`) | 3 |
| short-name Claude/Gemini command rows | 6 |
| `review-local.py` script row (**keep**) | 1 |
| `review-preflight.mjs` script row (**keep**) | 1 |

The 24 per surface break down as: 1 shared skill source → 1 `.agents` target
plus 10 platform skill targets (antigravity, claude, codebuddy, devin, droid,
kilo, kiro, pi, qoder, reasonix, trae = 11 skill targets total); 1
`templates/.commands/sd-<S>.md` source → 12 command/workflow/prompt targets
(cursor, github, opencode, antigravity, codebuddy, devin, droid, kilo, pi,
qoder, trae, zcode).

Installed receipt `.sd-ai-command-pack/manifest.json` mirrors the same 24×3;
`.sd-ai-command-pack/provenance.json` carries 23 matching path entries.

`docs/fleet/surface-partition.json` (777 targets, generated) carries 21 rows
per surface and classifies all four retired scripts as
`category: machine-claude`, `sharedRuntime: true`.

### 4. Environment-variable families

Totals exclude `.git` and `.trellis/.backup-*`; they include generated mirrors
and archived task text.

| family | total occurrences | distinct keys |
|---|---|---|
| `SD_AI_COMMAND_PACK_FULL_CHECK*` | 613 | 24 |
| `SD_AI_COMMAND_PACK_REVIEW_LOCAL*` | 407 | 22 |
| `SD_AI_COMMAND_PACK_REVIEW_PR_*` | 130 | 7 |
| `SD_AI_COMMAND_PACK_WATCH_PR*` | 0 | 0 |

**Trap:** a naive grep for `SD_AI_COMMAND_PACK_REVIEW_PR` also matches
`SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF`, which is a **surviving** key
with 29 occurrences. Anchor on `SD_AI_COMMAND_PACK_REVIEW_PR_` with the
trailing underscore.

#### 4a. `SD_AI_COMMAND_PACK_FULL_CHECK*` readers inside *surviving* code

These are the ones that force refactoring rather than deletion:

| file:line | key | disposition |
|---|---|---|
| `scripts/sd-ai-command-pack-review-scope.sh:60` | `..._FULL_CHECK_BASE_REF` | **REFACTOR** — review-scope.sh survives |
| `scripts/sd-ai-command-pack-review-preflight.mjs:4751` | `..._FULL_CHECK_BASE_REF` | **REFACTOR** — preflight survives |
| `scripts/sd-ai-command-pack-surface-check.py:176` | `..._FULL_CHECK_RELEASE_BASE_REF` | **REFACTOR** — pack-source-only release gate, survives |
| `.github/scripts/prepare-release.py:262` | `..._FULL_CHECK_RELEASE_BASE_REF` (message text) | **REFACTOR** |
| `.github/workflows/tests.yml:657` | `..._FULL_CHECK_TEST_SOURCE=1` | **REFACTOR** — CI job |
| `.github/workflows/tests.yml:658` | `..._FULL_CHECK_RELEASE_BASE_REF` | **REFACTOR** — CI job |
| `scripts/sd-ai-command-pack-install-audit.py:200` | maps legacy `TRELLIS_FULL_CHECK` → `SD_AI_COMMAND_PACK_FULL_CHECK` | **REFACTOR** — audit survives |
| `Makefile:99` | `..._FULL_CHECK_PRISM=0 ..._FULL_CHECK_GITO=0` | **DELETE with the target** |

Each of the four `scripts/` entries has a byte-identical twin in
`templates/scripts/`, `plugins/sd/bin/`, and
`plugins/sd/machine-payload/scripts/` — multiply by four.

#### 4b. `FULL_CHECK` readers inside code that is itself being deleted

- `scripts/sd-ai-command-pack-full-check.sh` — 32 occurrences, 24 distinct keys.
- `scripts/sd-ai-command-pack-review-full-check.sh:71,74,79` — 3 occurrences
  (`..._PACKAGE_RUNNER`, `..._PRISM=0`, `..._GITO=0`).
- `scripts/sd-ai-command-pack-review-local.sh:299,309,312,327,332,337,351,604,619`
  — 9 occurrences, all as **fallback defaults** behind a `REVIEW_LOCAL_*` key
  (e.g. `:327` `"${..._REVIEW_LOCAL_PRISM_FAIL_ON:-${..._FULL_CHECK_PRISM_FAIL_ON:-high}}"`).
  These are the "dormant readers for migration convenience" R2 forbids; they
  die with the script.

Full distinct `FULL_CHECK` key list (24): `SD_AI_COMMAND_PACK_FULL_CHECK`,
`_BASE_REF`, `_GITO`, `_GITO_BASE_REF`, `_GITO_MAX_ATTEMPTS`, `_GITO_OUT_DIR`,
`_GITO_RETRY_DELAY_SECONDS`, `_GITO_RETRY_MAX_DELAY_SECONDS`,
`_GITO_TIMEOUT_SECONDS`, `_KB`, `_PACK_DRIFT`, `_PACKAGE_RUNNER`,
`_PACKAGE_SCRIPTS`, `_PRISM`, `_PRISM_EXCLUDE`, `_PRISM_FAIL_ON`,
`_PRISM_MAX_FINDINGS`, `_PRISM_RULES`, `_RELEASE_BASE_REF`,
`_REVIEW_PREFLIGHT`, `_REVIEW_PREFLIGHT_COMMAND`, `_REVIEW_PREFLIGHT_SCRIPT`,
`_SKIP_PACKAGE_SCRIPTS`, `_TEST_SOURCE`.

#### 4c. `SD_AI_COMMAND_PACK_REVIEW_LOCAL*`

22 distinct keys, all read only by `sd-ai-command-pack-review-local.sh`
(29 occurrences, ×4 copies) and its skill text (21 occurrences in each of the
5 SKILL.md copies). No surviving executable reads any `REVIEW_LOCAL_*` key.
`.trellis/tasks/08-07-default-local-review-lanes/*` (open task) references
them 10 times — check that task before deleting.

#### 4d. `SD_AI_COMMAND_PACK_REVIEW_PR_*`

**7 keys, zero executable readers.** Confirmed: no `.sh`, `.py`, or `.mjs`
under `scripts/`, `.github/scripts/`, `installer/`, or `install.py` reads any
of them. They are a *skill-text contract* — the agent reads the SKILL.md and
sets/interprets them itself:
`_REMOTE_AUTHOR_MATCH`, `_REMOTE_REQUEST_COMMAND`, `_REMOTE_REVIEWER`,
`_REMOTE_REVIEWER_LABEL`, `_REMOTE_ROUND_LIMIT`, `_REMOTE_SETTLE_POLLS`,
`_SELECTOR`.

Pinned by `tests/test_review_scope.py:1638,1642,1645-1648,1724` (asserts the
skill and doc still contain them) — those assertions must be deleted, not
edited. This is R2's "direct Copilot/custom-remote dispatch, reviewer-author
matching": deleting the SKILL.md deletes the whole contract.

### 5. Cross-dependencies — deletion vs refactor

This is the load-bearing table.

| Artifact | Depends on / depended on by | Classification | Evidence |
|---|---|---|---|
| `scripts/sd-ai-command-pack-review-local.py` | **The successor coordinator imports it.** `sd-ai-command-pack-review.py:37` `LOCAL_SCRIPT = Path(__file__).resolve().with_name("sd-ai-command-pack-review-local.py")`; used at `:718` and hard-fails at `:720` (`raise ReviewError(f"missing regular local review helper: {LOCAL_SCRIPT.name}")`) | **KEEP UNCHANGED.** Despite the `review-local` name it is the internal local-review *stage* of `sd-review`, documented as such at `docs/SD_AI_COMMAND_PACK.md:132-133`. Deleting it breaks `sd-review`. | `scripts/sd-ai-command-pack-review.py:37,718,720` |
| `scripts/sd-ai-command-pack-review-local.sh` | separate 771-line legacy shell path; only the `sd-review-local` skill/commands call it | **DELETE** ×4 | callers are all skill text + docs + tests; no code caller |
| `scripts/sd-ai-command-pack-review-scope.sh` | reads `..._FULL_CHECK_BASE_REF` at `:60`; consumed by `sd-ai-command-pack-check.py`, `pr-body-scope.py`, `review-preflight.mjs` | **REFACTOR** — drop the FULL_CHECK fallback, keep the script | `scripts/sd-ai-command-pack-review-scope.sh:60` |
| `scripts/sd-ai-command-pack-review-preflight.mjs` | reads `..._FULL_CHECK_BASE_REF` at `:4751`; invoked by `sd-ai-command-pack-check.py:988`, `sd-create-pr` SKILL `:213-218`, `sd-finish-work` SKILL `:85,:150`, `fleet-publish.py:324`, `pr-eligibility.py:352` | **REFACTOR** | `scripts/sd-ai-command-pack-review-preflight.mjs:4751` |
| `scripts/sd-ai-command-pack-surface-check.py` | `:37` `FULL_CHECK = "templates/scripts/sd-ai-command-pack-full-check.sh"`; `:176` reads `..._FULL_CHECK_RELEASE_BASE_REF` | **REFACTOR** — this is `make surface-check`, a live gate that would break on a dangling path constant | `scripts/sd-ai-command-pack-surface-check.py:37,176` |
| `scripts/sd-ai-command-pack-install-audit.py` | `:146`/`:194` map legacy `scripts/trellis-full-check.sh` → `scripts/sd-ai-command-pack-full-check.sh`; `:183`/`:216` list `review-local.sh`; `:200` maps `TRELLIS_FULL_CHECK` env prefix | **REFACTOR** — audit survives; these rows become dangling advice | `scripts/sd-ai-command-pack-install-audit.py:146,183,194,200,216,217` |
| `scripts/sd-ai-command-pack-pr-body-scope.py` | `:253`/`:305` `scripts/sd-ai-command-pack-full-check.sh` region globs; `:299` legacy `scripts/check-review-preflight.mjs`; `:301` `review-local.sh` | **REFACTOR** — classifier survives | `scripts/sd-ai-command-pack-pr-body-scope.py:253,299,301,305` |
| `plugins/sd/bin/sd-ai-command-pack-toolchain.sh` | `:309` special-cases `sd-ai-command-pack-full-check.sh` (`suffix = "\|recursive"`); `:381`/`:414` probe for the script | **REFACTOR** — toolchain is the universal runner | `plugins/sd/bin/sd-ai-command-pack-toolchain.sh:309,381,414` (and its `scripts/` twin) |
| **`installer/references.py`** (new, uncommitted) | `:111-116` `BIN_LITERAL_ALLOWLIST["sd-ai-command-pack-full-check.sh"]`; `:137` inside install-audit allowlist; `:152` and `:157` (`review-local.sh`) inside pr-body-scope allowlist; `:186` inside surface-check allowlist; `:194` inside toolchain allowlist; `:216` `PLUGIN_CLOSURE_ALLOWLIST[("skills/sd-review-pr/SKILL.md", fleet-review-classify)]`; `:222` `MACHINE_CLOSURE_ALLOWLIST[(".agents/skills/sd-review-pr/SKILL.md", …)]` | **REFACTOR** — the two closure-allowlist entries become dead keys the moment the `sd-review-pr` SKILL.md is deleted, and its own docstring at `:208-212` says "a follow-up task fixes the skill text and retires this entry". That follow-up is this task. | `installer/references.py:111,137,152,157,186,194,208-225` |
| `installer/removal.py` | `:65-75` hand-maintained `RETIRED_TARGETS` tuple, four ids | **EDIT** — add `full-check-command`, `review-local-command`, `review-pr-command` | `installer/removal.py:65-75` |
| `installer/registry.py` | `:1349-1411` the seven `RetiredCommandSurface` rows; `:1436-1440` `SUPERSEDED_COMMANDS`; `:1462-1552` `COMMAND_SURFACE_ALLOWANCES`; plus three live `CommandInfo` rows for the surfaces | **EDIT** — see §8 | `installer/registry.py:1349,1436,1462` |
| `Makefile:98-101` | `full-check:` target and `check: test lint audit full-check` | **EDIT in the same commit** — `make` fails at parse time on a missing prerequisite; design.md decided option A (`check: test lint audit`) | `Makefile:98,99,101` |
| `.github/scripts/generate-command-surfaces.py:355-361` | derives the `transitional until <version>` catalog literal from `SUPERSEDED_COMMANDS` | **REFACTOR** — becomes dead once the three keys leave `SUPERSEDED_COMMANDS`; `:128` also hardcodes the `review-local.sh` sentence | `.github/scripts/generate-command-surfaces.py:128,355,357-361` |
| `.github/scripts/check-shipped-script-coverage.sh:51` and `check-shipped-script-docs.sh:26` | list `sd-ai-command-pack-review-local.py` (the survivor) | **NO CHANGE** — but if `full-check.sh`/`review-local.sh` also appear there, their rows must go | `.github/scripts/check-shipped-script-coverage.sh:41,51` |
| `.github/scripts/kcov-bash-shim.sh:61` | comment referencing `review-local.sh` | **REFACTOR** (comment only) | `.github/scripts/kcov-bash-shim.sh:61` |

### 6. Package hooks

**None exist.** `package.json` (7 lines) declares no `scripts`. The
`check:full` reference is at `scripts/sd-ai-command-pack-review-full-check.sh:74`
(`exec env … "$package_runner" run check:full`) and dies with that script.
PRD R2's "package `check:full` hook" is satisfied by deleting the wrapper.

### 7. Tests pinning retired behavior

**Whole modules to delete:**

| File | Lines |
|---|---|
| `tests/test_full_check.py` | 1621 |
| `tests/test_review_local.py` | 1435 |
| `tests/test_review_full_check.py` | 254 |

**Modules with retired-surface assertions to prune** (20 total mention at
least one retired name):
`tests/install_test_support.py`, `tests/test_audit_repo.py`,
`tests/test_command_surface_drift.py`, `tests/test_completion_lifecycle.py`,
`tests/test_generated_parity.py`, `tests/test_housekeeping.py`,
`tests/test_install_audit.py`, `tests/test_install_core.py`,
`tests/test_machine_stage.py` (new, uncommitted), `tests/test_pack_drift.py`,
`tests/test_retired_targets.py`, `tests/test_review_preflight.py`,
`tests/test_review_scope.py`, `tests/test_script_lib.py`,
`tests/test_sdlc_commands.py`, `tests/test_surface_generation.py`,
`tests/test_update_spec_kb.py`, plus `tests/test_release_ledger.py`,
`tests/test_bookkeeping_ci_scope.py`, `tests/test_script_sibling_resolution.py`
for env-key/script-name pins.

Notable individual pins:
- `tests/test_install_core.py:3204` asserts `sd-review-pr` does **not** contain
  `bash scripts/sd-ai-command-pack-review-full-check.sh` — inverted assertion,
  deleting the skill makes it vacuous.
- `tests/test_install_core.py:3272,3280` assert the `sd-review-local` skill
  *does* contain `bash scripts/sd-ai-command-pack-review-local.sh`.
- `tests/test_review_scope.py:1631` asserts a `bash scripts/…-review-full-check.sh`
  invocation string.
- `tests/test_script_sibling_resolution.py:163` pins
  `review-full-check.sh` → `"$SCRIPT_DIR/sd-ai-command-pack-toolchain.sh"`.

**Modules that must survive and keep working:**
`tests/test_review_controller.py` (`:22`, `:632` exercise
`templates/scripts/sd-ai-command-pack-review-local.py` — the KEEP script),
`tests/test_review_stage.py:27` (same script),
`tests/test_verdict_vocabulary.py:48`,
`tests/test_git_invocation_boundary.py:31`.

### 8. Registry / catalog / partition

`installer/registry.py`:

- `:1349-1411` — seven `RetiredCommandSurface` rows. The three transitional
  rows (`full-check-command` `:1387-1394`, `review-local-command` `:1395-1402`,
  `review-pr-command` `:1403-1410`) all carry `identifiers=()`,
  `source_paths_must_be_absent=False`, `removed_version="0.62.0"`,
  `owner_task="07-24-remove-retired-review-surfaces"`. Each already resolves to
  **26** installed targets via `command_installed_targets(...)`.
- `:1436-1440` — `SUPERSEDED_COMMANDS` maps the three names to
  `(successor, retirement_id)`: `sd-full-check → sd-check`,
  `sd-review-local → sd-review`, `sd-review-pr → sd-review`. Validated by
  `validate_superseded_commands` `:1443-1459`, which rejects unknown command
  names — so the dict entries must be removed in the same edit that removes the
  `CommandInfo` rows, or import fails.
- `:1462-1552` — 16 `CommandSurfaceAllowance` rows today (6 for
  `sd-review-local-all`, 3 `sd-work-designs`, 5 `sd-watch-pr`, plus 3 generated
  plugin-copy rows). Expect a comparable number per newly-enforcing surface.

Catalog (generated into 5 roots — `templates/.agents/skills/sd-help/references/command-catalog.md`
plus `.agents`, `.claude`, `plugins/sd/skills`, machine-payload):

- `:40` `sd-review-local` — `included in installed pack — transitional until 0.62.0; use sd-review`
- `:43` `sd-full-check` — `… transitional until 0.62.0; use sd-check`
- `:54` `sd-review-pr` — `… transitional until 0.62.0; use sd-review`

Generator: `.github/scripts/generate-command-surfaces.py:355-361`.

Drift lint `.github/scripts/check-command-surface-drift.py`:

- `:380`, `:485-504`, `:514-533` — repo-wide text scan of every retirement's
  `identifiers`, emitting `retired_identifier_live` unless a
  `CommandSurfaceAllowance` matches. **Populating `identifiers` turns this on.**
- `:453-462` — manifest-target intersection, now flag-aware (`:453`
  `if not retirement.source_paths_must_be_absent: continue`) — the fix
  `07-28-retire-transitional-review-surfaces` landed.
- `:638-646` — source-checkout existence pass, also flag-gated at `:638`.

`docs/fleet/surface-partition.json` — regenerated by
`.github/scripts/partition-surfaces.py`; 21 rows per surface plus the four
script rows, all `machine-claude` / `sharedRuntime: true`.

Fleet candidate ledger: `docs/fleet/candidate-validation.json` was touched by
the watch-pr removal commit (`71d12d1f`) and will need the same regeneration.

### 9. Docs and spec claims

`README.md` — 13 mentions of the three names; env-family mentions 9
(FULL_CHECK) + 8 (REVIEW_LOCAL) + 7 (REVIEW_PR); script `bash -n` lines at
`:610`, `:611`, `:614`, `:615`.

`docs/SD_AI_COMMAND_PACK.md` (mirrored in `templates/docs/` and
`plugins/sd/machine-payload/docs/`) — 43 FULL_CHECK + 36 REVIEW_LOCAL + 13
REVIEW_PR occurrences each; script inventory at `:86`, `:129`, `:132`;
usage at `:567-568`, `:933`, `:2243`, `:2246`.

`docs/FLEET_ROLLOUT.md:509`, `docs/review-learnings.md:48` (historical PR #191
finding about `review-full-check.sh`), `CONTRIBUTING.md:94` (preflight, keep),
`CHANGELOG.md` (historical, needs allowances).

`.trellis/spec/` claims to update:
`frontend/index.md:11,12,18,32,35,48,51,74`;
`frontend/adapter-guidelines.md:21,22,23,31,33,41,1031-1032,1079,1306,1320,1370,1390-1391,1472,1477,1479,1534,1763`;
`frontend/directory-structure.md:56,57,59`;
`backend/manifest-and-filesystem.md:671`;
`backend/quality-guidelines.md:1365` (names `review-local.py` — the KEEP
script, verify wording still true);
`backend/logging-guidelines.md`; `guides/index.md`.

### 10. R9 — the fleet recheck procedure to relocate

`templates/.agents/skills/sd-review-pr/SKILL.md:195-217` — section
`### Fleet Integration-Only Recheck`. It invokes
`scripts/sd-ai-command-pack-fleet-review-classify.py` (`:202-206`), which
`scripts/sd-ai-command-pack-install-audit.py:119` lists as source-only, so the
block is unreachable in all 11 shipped copies. Destination:
`templates/.agents/skills/sd-fleet-refresh/SKILL.md`, which already references
the classifier at `:175`.

## Deletion vs refactor summary

**DELETE outright** (×4 script trees / ×5 skill roots as applicable):
`sd-full-check`, `sd-review-local`, `sd-review-pr` skills, commands, prompts,
command-sources, plugin and machine-payload copies (51 files);
`full-check.sh`, `review-full-check.sh`, `review-local.sh` (12 files);
`tests/test_full_check.py`, `tests/test_review_local.py`,
`tests/test_review_full_check.py`; `Makefile` `full-check` target;
83 manifest rows.

**REFACTOR — surviving code that names retired things:**
`review-scope.sh:60`, `review-preflight.mjs:4751`, `surface-check.py:37,176`,
`install-audit.py:146,183,194,200,216,217`,
`pr-body-scope.py:253,299,301,305`, `toolchain.sh:309,381,414`,
`installer/references.py:111,137,152,157,186,194,216,222`,
`generate-command-surfaces.py:128,355-361`, `prepare-release.py:262`,
`.github/workflows/tests.yml:657-658`, `kcov-bash-shim.sh:61`,
`Makefile:101`.

**KEEP UNCHANGED (do not let the name fool you):**
`scripts/sd-ai-command-pack-review-local.py` and its four copies, plus
`tests/test_review_controller.py`, `tests/test_review_stage.py`,
`tests/test_verdict_vocabulary.py`, `tests/test_git_invocation_boundary.py`.

## Caveats / Not found

- **Schedule already slipped.** `removed_version="0.62.0"` vs shipped
  `0.64.35`. PRD R8 says "do not mint a second version", and the acceptance
  criterion is that the removal is "the one that was announced". Deciding
  whether to keep `0.62.0` (historically false but matches the announcement) or
  re-announce is a planning decision this research cannot make. PRD R11 names
  the fallback: if removal slips past the announced version, the interim fixes
  belong to `07-28-retire-transitional-review-surfaces` — which is already
  archived.
- **`installer/references.py` and `installer/machinestage.py` are uncommitted**
  on `feat/thin-machine-installer`. Their retired-surface entries
  (`references.py:216`, `:222`, `tests/test_machine_stage.py`) did not exist
  when this task was planned. They add cross-dependencies the design does not
  mention.
- `.trellis/tasks/08-07-default-local-review-lanes/` is an **open, unarchived**
  task with 10 `SD_AI_COMMAND_PACK_REVIEW_LOCAL*` references across its prd,
  design, and implement docs. Not read for this inventory; it may conflict.
- I did not verify that `check-shipped-script-coverage.sh` /
  `check-shipped-script-docs.sh` carry rows for `full-check.sh` and
  `review-local.sh` (only confirmed rows for the surviving
  `review-local.py` and `fleet-review-classify.py`).
- `python3 ./.trellis/scripts/task.py current` reports the active task as
  `08-09-codex-home-skills-family`, not this task. Research was written to the
  task directory named in the assignment.
