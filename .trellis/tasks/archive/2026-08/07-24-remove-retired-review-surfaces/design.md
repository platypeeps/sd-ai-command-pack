# Design — remove retired review and check surfaces (Narrow scope)

## Scope boundary

**Rescoped 2026-08-09 (operator decision: Narrow).** This task deletes two
command surfaces — `sd-full-check` and `sd-review-local` — plus
`sd-ai-command-pack-review-local.sh`. `sd-review-pr` and everything reachable
only through it moved to `08-09-retire-review-pr-surface` (P1).

The removal **version** and transitional catalog status belong to
`07-28-retire-transitional-review-surfaces` (archived); the `sd-ship` repoint
belongs to `07-24-simplify-review-shipping-composition` (archived). This task
executes against a schedule it does not set (R8).

### Why the split, and what it changed

Adversarial planning review found that `sd-review-pr` is not a superseded alias
but the sole implementation of a trusted nested contract used by a live caller
(`sd-fleet-refresh/SKILL.md:192`), which `sd-review` does not implement
(`sd-review/SKILL.md:40` takes public `key=value` controls only). Removing it is
a behavioral migration, so it was split out.

### Correction (adversarial review round 3)

An earlier draft of this section claimed `sd-review-pr` is the last caller of
`full-check.sh` and `review-full-check.sh`, citing
`templates/.agents/skills/sd-review-pr/SKILL.md:262-263`. **That line is a
prohibition, not an invocation**: "Do not discover `package.json` scripts, read
the legacy full-check environment contract, or fall back to
`sd-ai-command-pack-full-check.sh` or `sd-ai-command-pack-review-full-check.sh`."
`sd-review-pr` calls neither script.

The two scripts still survive this task, for two different and better-evidenced
reasons:

- **`full-check.sh` is the repo's own gate.** `Makefile:98-101` defines
  `full-check:` and `check: test lint audit full-check`, and
  `.github/workflows/tests.yml:652-659` sources it for the release-payload
  drift gate. That dependency predates the split and is unaffected by which
  command surfaces are retired. Deleting it requires recomposing `make check` —
  deliberately out of scope here (see below).
- **`review-full-check.sh` has no live caller at all.** It was already orphaned
  before this task: the only surviving references are `README.md:611`'s
  `bash -n` syntax check, its manifest rows, and generated doc copies. It is
  **deferred, not blocked** — R6 scopes this task to helpers "made unreachable
  by the cutover", and this one was unreachable beforehand. Deleting it would
  add a manifest row, a `RETIRED_TARGETS` registration, and doc churn for a
  script belonging to the full-check family, whose single owner is
  `08-09-retire-review-pr-surface`. Recorded there, not silently dropped.

The split's consequences for this task are unchanged; only the mechanism is
corrected. Six hazards the pre-split plan carried are gone:

| Pre-split problem | Status under Narrow |
|---|---|
| "The gate eats itself" — `make check` depends on `full-check`, R1 deletes the script | **Gone.** The script survives; `Makefile:98-101` is untouched. |
| Option A vs B for `make check` | **Deferred** with the script. |
| R10 — remove `PRISM=0 GITO=0` with the lanes | **Deferred**; removing the disabling while the lanes live is exactly the trap R10 warns about. |
| A2 — `run_pack_source_drift_gates` lives inside the deleted script, sourced by `tests.yml:659` | **Gone.** No relocation needed; the function stays where it is. |
| A1 — deleted scripts unreachable by `retired_surface_targets()` | **Reduced** to one script (`review-local.sh`), still real. |
| R9 — relocate the fleet recheck out of `sd-review-pr` | **Deferred** with that surface. |
| A5 — `sd-fleet-refresh` loses its review stage | **Gone.** It calls `sd-review-pr`, which still ships. |
| Local preflight coverage lost from `make check` | **Gone.** `full-check.sh` still runs it. |

Note that the first four rows resolve because `full-check.sh` survives on the
`Makefile`/CI dependency, which would have held even without the split. The
split is what removes A5 and R9; it is not what saves the script.

What remains is a genuine deletion with no behavioral migration inside it.

## Measured scale (Narrow, verified 2026-08-09 against `manifest.json`)

| item | count |
|---|---|
| `sd-full-check` manifest rows | 24 |
| `sd-review-local` manifest rows | 24 |
| short-name command rows (`full-check.md/.toml`, `review-local.md/.toml`) | 4 |
| `review-local.sh` script row | 1 |
| **manifest rows deleted** | **53** |
| live files (17 per surface) | 34 |
| `review-local.sh` copies (4 trees) | 4 |

Superseded figures, kept only so they are not re-derived: the PRD's original
"79", the 2026-07-28 count of 105, and the research file's 83 (which counted
two surviving rows). `sd-watch-pr` has been fully removed since 0.57.0 — 0 live
files, 0 manifest rows, an already-enforcing row.

The 17 live files per surface: 6 authored sources (`templates/.agents/skills/`,
`templates/.commands/`, `templates/.claude/commands/sd/`,
`templates/.gemini/commands/sd/`, `templates/.github/prompts/`,
`.github/command-sources/`), 6 installed source-checkout mirrors, 2
Claude-plugin payload copies, 3 machine-payload copies.

## Decisions

### D1 — the announced `removed_version` stays `0.62.0`

The rows say `0.62.0`; the repo ships `0.64.35`. The earlier note "if deletion
slips past 0.62.0, update the inert rows in place" contradicts the PRD's
acceptance criterion and R8 ("do not mint a second version"). **The PRD wins:
keep `0.62.0`.**

No removal enforcement consumes the field. The only behavior it drives is the
catalog literal `transitional until <version>; use <successor>`
(`generate-command-surfaces.py:359`), rendered from `SUPERSEDED_COMMANDS` — and
this task deletes the two keys that render it. It is still *read* by the generic
lookup `retired_surface_removed_version` (`installer/registry.py:1423`),
enforced non-empty by validation (`:1575`), tested
(`tests/test_help_command.py:570,614`), and copied into
`plugins/sd/installer/registry.py` — so the justification is "nothing enforces
it", not "nothing reads it". It degrades to announcement provenance: the version
consumers were told to expect. The slip is recorded in `CHANGELOG.md` (D6).

Precedent does not settle this: `sd-watch-pr`'s `0.57.0` was accurate because
that row was created *at* removal, never pre-registered. The schedule-only →
enforcing flip has never been executed in this repo.

### D2 — registering the rows does not make `review-local.sh` removable

`command_installed_targets("sd-review-local", "review-local")` returns 26 paths
and **zero** under `scripts/`. Normal refresh deletes only what is in
`RETIRED_TARGETS` (`installer/removal.py:275`), so flipping the row alone leaves
every consumer's copy of `review-local.sh` in place forever — a direct R4
violation. It is a real consumer manifest target.

Append the **consumer-install** path `scripts/sd-ai-command-pack-review-local.sh`
to the `review-local-command` row's `installed_targets`. Never the
`templates/scripts/` source: that is a manifest *source*, and listing it marks a
consumer-owned file for unconditional deletion under `--force`.

Counts: `full-check-command` 26 (no script — `full-check.sh` survives),
`review-local-command` 27, so `RETIRED_TARGETS` moves **104 → 157**.

Two further mechanics, both found in round 3:

- **The manifest row does not disappear on regeneration.**
  `generate_manifest_text()` reads the existing `manifest.json`
  (`generate-command-surfaces.py:256,:1086`), rebuilds only command- and
  agent-shaped rows, and carries every other entry through verbatim
  (`:1087-1101`). The `review-local.sh` row is `kind: script`
  (`manifest.json:268`), so deleting the four files and regenerating leaves a
  **dangling row pointing at nothing**. It must be deleted from `manifest.json`
  by hand — and it is one of the 53 the recount claims.
- **`identifiers` alone does not lint environment names.** The drift lint's
  `retired_identifiers` set is `(*identifiers, *configuration_keys)`
  (`check-command-surface-drift.py:485-489`), and
  `RetiredCommandSurface.configuration_keys` defaults to empty
  (`installer/registry.py:1339`). No existing row populates it. Without it, R5's
  commitment to lint environment names is unenforceable and a reintroduced
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_*` reader passes silently. The
  `review-local-command` row must carry the 23 concrete keys. Verified safe: no
  live `CommandInfo` declares any of them, so the `config_overlap` check
  (`:1626`) cannot fire, and no other retired row declares them, so the
  `repeated_keys` check (`:1633`) cannot either. The cost is real and intended —
  the lint then demands that all ~392 repo-wide occurrences be deleted or
  allowanced.

### D3 — `sd-fix-ci` is a live caller and must be repointed

Globbing `templates/.agents/skills/*/SKILL.md` (rather than naming skills by
hand, which is how the original gate missed this) finds retired references in
nine skills. Under Narrow, exactly one is a live caller of a surface being
deleted: **`sd-fix-ci/SKILL.md:43,47,109`** routes the agent to `sd-full-check`
as "the local gate every fix must pass" → repoint to `sd-check`.

`sd-check/SKILL.md:76` ("do not call `sd-full-check`…") becomes vacuous →
delete. `sd-review/SKILL.md:15` names both retired surfaces in supersession
prose → reword.

**Corrected in round 3:** an earlier draft said the remaining six name
`sd-review-pr` only. Two of them do not — `sd-audit-repo/SKILL.md:39,40,275,276`
positions itself against `sd-review-local` and `sd-full-check` in two separate
blocks, and `sd-test-gaps/SKILL.md:26` names `sd-full-check` as its gate. Five
surviving skills need edits, not three. The hand-written table was wrong twice;
`implement.md`'s gate now says to take it from the grep output.

### D4 — R11's fallback owner no longer exists

Step 10b routed A-102/A-114 to `07-28-retire-transitional-review-surfaces` if
the removal slipped. That task is archived and the slip has happened. Under
Narrow both findings belong to `08-09-retire-review-pr-surface`, because both
die with `full-check.sh` and the `sd-full-check` **contract text**, and this
task deletes only the latter. Leave both rows open in `.trellis/audit/ledger.md`
and note the new owner — do not mark them resolved here.

### D5 — this cutover invalidates part of an open task's plan

`08-07-default-local-review-lanes` (open, P2) plans edits **into**
`review-local.sh`: `implement.md:332` edits `:643`'s `raw_tools` default, and
acceptance criterion AC8 (`prd.md:211`, `implement.md:410,416`) runs
`bash templates/scripts/sd-ai-command-pack-review-local.sh codex`.

Its goal survives intact — the provider list it needs to change lives in
`review-local.py:251,266` (the **surviving** engine) and `review.py:220`. Only
the shell half of its plan dies. Record as a follow-up; do not edit another
task's artifacts mid-flight, and do not let it argue for keeping the `.sh`
alive (R2 forbids dormant readers; it has no executing caller).

### D6 — the CHANGELOG entry is load-bearing

D1 keeps `0.62.0` on the grounds that the slip is recorded in `CHANGELOG.md`.
That makes the entry a required artifact: it must state that the surfaces
announced for removal in 0.62.0 were actually removed in the shipping version.
Without it, D1's rationale is unbacked. `CHANGELOG.md` also needs
`CommandSurfaceAllowance` coverage once `identifiers` is populated.

### D7 — four surviving `REVIEW_LOCAL` readers inside a surviving script

`full-check.sh` survives, and it reads four retired keys as fallbacks:
`:166`, `:170`, `:174`, `:178` each spell
`${..._FULL_CHECK_GITO_X:-${..._REVIEW_LOCAL_GITO_X:-default}}`.

These are precisely R2's forbidden "dormant readers for migration convenience",
and they do **not** die with `review-local.sh`. Delete the `REVIEW_LOCAL` half
of each `:-` chain, keeping the `FULL_CHECK` primary and the literal default.
Behavior changes only for someone who set `..._REVIEW_LOCAL_GITO_*`, which is
the retired surface's own configuration — correctly dying.

### D8 — commit boundaries

Two hazards make the registry edit and the deletion inseparable:

- Generation derives manifest rows from `COMMAND_REGISTRY`
  (`generate-command-surfaces.py:1092`), so deleting files and regenerating
  while the `CommandInfo` rows still exist **recreates** the rows just deleted.
- Removing `CommandInfo` rows without the matching `SUPERSEDED_COMMANDS`
  entries fails at **module import** (`installer/registry.py:1801`).

Any change under `templates/**` is also treated as a payload change by the
release gate, which then requires a version bump, a matching changelog heading,
and an exact candidate ledger (`full-check.sh:719,:755,:780`).

**Corrected in round 3:** the gate is *not* per-commit. It diffs
`SD_AI_COMMAND_PACK_FULL_CHECK_RELEASE_BASE_REF...HEAD`
(`full-check.sh:709-717`), and CI supplies the **PR base SHA**
(`.github/workflows/tests.yml:652`). Once commit 1 bumps the version, every
later head is still bumped relative to that same base — so the PR needs **one**
version bump and **one** changelog heading, not one per commit. The exact
candidate ledger *is* per-head, because it pins the payload digest of whatever
is checked out.

| Commit | Contents |
|---|---|
| 1 | D3 repoints (`sd-fix-ci`, `sd-test-gaps` → `sd-check`; `sd-check`/`sd-review`/`sd-audit-repo` prose) + regenerate + **the PR's one** version bump and changelog heading + refreshed ledger. Retired surfaces still exist and still work, so the repoint is provable on its own. |
| 2 | **atomic cutover**: delete 34 files + 4 script copies + the `review-local.sh` manifest row + `tests/test_review_local.py`; flip both registry rows (`identifiers` + `configuration_keys`); drop `CommandInfo` + `SUPERSEDED_COMMANDS`; extend `installed_targets`/`RETIRED_TARGETS` (157); D7 fallback removal; refactor sites; regenerate; refreshed ledger. |
| 3 | allowances until the drift lint is green, plus any residue the lint surfaces. |

**Execution order inside a commit** matters, and the obvious order deadlocks:
`make generate` ends with `surface-check.py` (`Makefile:19-23`), which runs the
fleet candidate checker and fails on a stale ledger (`surface-check.py:673`) —
so "generate, then refresh the ledger" can never pass on its first run. Run the
generators individually, refresh the ledger, then run `surface-check.py` last;
or use the `prepare-release.py` orchestration, which already sequences it that
way. A bare `make generate` is a verification step at the end, not the first
step.

Commit 2 cannot be subdivided without leaving the repo unimportable or
regenerating what it deleted. Commit 3 is separate because the drift lint can
only be evaluated after `identifiers` is populated, and enumerating allowances
against a red lint is the intended workflow — that redness is the lint working.

`make check` must be green at every boundary; `make generate` runs
`surface-check.py`, which incorporates drift findings (`:751`) and exits nonzero
(`:895`), and `tests/test_command_surface_drift.py:94` requires the live
repository to be clean. So commit 2 must not be pushed with a red lint — if
enumerating allowances is needed to make it green, they belong in commit 2 and
commit 3 collapses into it.

## What survives, and why the names mislead

- **`scripts/sd-ai-command-pack-review-local.py`** — despite the name, this is
  `sd-review`'s local-review stage: `review.py:37` binds it as `LOCAL_SCRIPT`,
  uses it at `:718`, and hard-fails at `:720` when absent. Deleting it breaks
  `sd-review`. Its tests (`test_review_controller.py`, `test_review_stage.py`,
  `test_verdict_vocabulary.py`, `test_git_invocation_boundary.py`) survive
  unchanged and act as the negative control for this cutover.
- **`full-check.sh`** — the repo's own gate (`Makefile:98-101`,
  `tests.yml:652-659`). Not reachable from `sd-review-pr`; its
  `SKILL.md:262-263` forbids falling back to it.
- **`review-full-check.sh`** — already orphaned before this task; deferred to
  the full-check family's owner rather than deleted here (see the correction
  above).
- **`tests/test_full_check.py`, `tests/test_review_full_check.py`** — they test
  surviving scripts. Only `tests/test_review_local.py` (1435 lines) is deleted.
- **`review-preflight.mjs`, `review-scope.sh`, `fleet-review-classify.py`** —
  survivors throughout.

## Deliberate residue

`review-local.py` emits `"command": "sd-review-local-stage"`
(`:2177,:2192,:2202,:2301,:2313`) and `review.py:950` emits provider id
`sd-review-local-policy`. These are the **successor's** internal stage
identifiers, not the retired command; renaming them changes a consumer-visible
receipt schema and is filed separately. The drift lint will not flag them — its
token boundary rejects hyphen-suffixed matches
(`check-command-surface-drift.py:271`) — so any absence check must use the same
boundary semantics or an explicit exclusion, or it will fail on intended
residue.

## R5's real difficulty

The live-surface drift lint already exists; R5 is mostly *configuring*
`check-command-surface-drift.py`, not building it. The hard part is the word
**minimal**: every allowance is a permanent exception, and the easy failure mode
is adding one per red line until the lint is green and meaningless. Each
allowance needs a `reason` naming why the reference is historical rather than
live, matching the existing rows' style. The already-deleted
`sd-review-local-all` needed six (`installer/registry.py:1463-1492`); watch-pr
needed five plus a generated plugin-copy row (`:1508-1532`, `:1547-1551`). Any
new enforcing row needs that plugin-copy allowance too, or `make generate`
output trips the lint.

## Rollback

R6 is explicit: rollback is installing the last pre-cut release, not retaining
legacy code. There is no in-release undo, which is why D3's repoint lands in its
own commit while the old surfaces still work, and why the uninstall path (D2)
must be proven on a real prior-release install — a wrong `recorded_hash`
silently *preserves* a file instead of removing it, and the receipt still looks
clean because the path left the manifest either way.

## Compatibility

Intentionally non-backward-compatible (parent R13-R15, R18, R22, R29; user
accepted). The only surviving obligations: a modified old target is preserved
and reported rather than deleted, and no retired path appears in the new
receipt.
