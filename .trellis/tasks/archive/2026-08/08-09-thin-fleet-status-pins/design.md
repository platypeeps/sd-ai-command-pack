# Fleet/status rework to pin + plugin inventory — Design

## Overview

Child 4 of `08-09-deployment-thin-consumers` (parent requirement 4).
Children 1–3 (`thin-surface-partition`, `thin-plugin-packaging`,
`thin-machine-installer`) have shipped, so the machine-scope receipt and
the plugin already exist and `sd-status` local mode already reports them.

What is still missing is the *fleet* half: the registry cannot say which
consumers are thin, and fleet mode still judges every consumer by
installed-tree drift — the exact signal a thin consumer no longer has.

Grounding (verified 2026-08-10 against this checkout; every citation below was
opened, not inferred):

- `scripts/sd_ai_command_pack_fleet_lib.py:17` — `FLEET_SCHEMA_VERSION = 4`.
  Strict equality lives in `_parse_fleet_consumers_without_policy`
  (`:539-544`); the per-consumer loop is `:555-600`.
- `scripts/sd_ai_command_pack_fleet_lib.py:35-43` — `FleetConsumer` has no
  mode and no pin field.
- `scripts/sd-ai-command-pack-status.py:1678-1830` — `collect_plugin_version`,
  `machine_receipt_state`, `machine_comparison`, `collect_machine_scope`
  already exist and already label absent sources `unavailable`; the
  `comparison` field is emitted at `:1819`. Local mode requirement 1 is
  therefore **already satisfied**; this task adds its regression test, not the
  feature. Proof: `sd-status --json --no-network` here returns `machineScope`
  with `state: "none"`, `pluginVersion: "unavailable"`,
  `pluginDetail: "plugin sd@sd-ai-command-pack is not installed"`,
  `comparison: "unknown"`.
- `scripts/sd-ai-command-pack-status.py:2408` — the local payload key is
  `machineScope`, carrying its own `MACHINE_SCOPE_SCHEMA_VERSION`.
- `scripts/sd-ai-command-pack-status.py:2908-2999` — `collect_fleet` calls
  `collect_local(..., include_machine_scope=False)` per consumer.
- `scripts/sd-ai-command-pack-status.py:2863-2894` — `fleet_next_steps` builds
  the stale row from `report["versions"]["sdAiCommandPack"] != target`
  (`:2871`) and **truncates to `HUMAN_ITEM_LIMIT` (5)** at `:2894`, before
  `fleet_follow_ups` (`:2897`) turns steps into `F-*` rows.
- `scripts/sd-ai-command-pack-status.py:546-563` — `collect_versions` already
  reads `.sd-ai-command-pack/provenance.json` for every consumer row
  (`installer/registry.py:2273` `PROVENANCE_FILE`). In a thin consumer that
  same receipt **is** the pin.
- `scripts/sd_ai_command_pack_fleet_lib.py:192-200` (`_pack_identity` returns
  `manifest_version(manifest)`) and `:251, 268, 284` (every resolution sets
  `target_version=version`) — the fleet "target" is the **resolved pack checkout's manifest
  version**. There is no GitHub release lookup anywhere in the fleet library.
- `docs/fleet/candidate-validation.json:6` pins `fleetManifestDigest`;
  `validate_candidate_ledger` compares it by equality at
  `scripts/sd_ai_command_pack_fleet_lib.py:745-750`, and
  `scripts/sd-ai-command-pack-surface-check.py:672-685` runs
  `fleet-candidate-check.py --check-ledger` inside `make check`.
- `scripts/sd-ai-command-pack-housekeeping-result.py:43` sets
  `STATUS_SCHEMA_VERSION = 2` and `:173` enforces it by equality — the status
  payload schema **does** have a strict consumer.
- `AGENTS.md:28-32` — `templates/**` is the source of truth; root-level copies
  are byte-verified mirrors. `Makefile:19-31` (`generate`) regenerates command
  surfaces, the partition, and the **plugin** trees; `Makefile:37-39` (`sync`)
  runs `install.py . --force`, installing templates over the root mirror.

## Proposal

### 1. Registry: `schemaVersion` 4 → 5, per-consumer `mode`

`docs/fleet/consumers.json` bumps to `schemaVersion: 5`. Each consumer entry
may carry:

- `"mode": "fat" | "thin"` — optional, defaults to `"fat"`.
- `"pinPath": "<repo-relative path>"` — optional, defaults to
  `.sd-ai-command-pack/provenance.json`. Only meaningful for `thin`.

`FleetConsumer` gains `mode: str = "fat"` and
`pin_path: str = DEFAULT_PIN_PATH` — **with dataclass defaults, declared
last**. Three tests construct `FleetConsumer` positionally/directly
(`tests/test_fleet_candidate.py:45`, `tests/test_fleet_preflight.py:272`,
`tests/test_fleet_wave_plan.py:31`); defaults keep those call sites valid
instead of breaking the focused gate. Load-time validation in
`_parse_fleet_consumers_without_policy` rejects an unknown mode, an absolute
`pinPath`, and any `pinPath` containing `..`.

**Load-time syntax checks are not containment.** A purely relative path can
still leave the checkout through a symlink, so the *reader* repeats the
existing filesystem pattern from `filesystem_payload_digest`
(`scripts/sd_ai_command_pack_fleet_lib.py:706-709`): `resolve(strict=True)`
then `relative_to(<consumer root>)`. An escape is reported as `unreadable`
with a reason, never followed.

**Version-skew semantics of the bump (not backward compatible, by design).**
`_parse_fleet_consumers_without_policy` demands exact equality, so a schema-4
registry is rejected after this change, as it was for 3 → 4. The invariant
this task guarantees — and the one AC3 states — is: *a schema-5 registry
carrying no `mode` on any consumer behaves exactly like the schema-4 registry
it replaces.*

### 2. Machine inventory is collected once per fleet run, not per consumer

`collect_fleet` calls the existing `collect_machine_scope` exactly once
against the pack root and publishes it under the **same `machineScope` key
local mode already uses**. Each consumer row keeps
`include_machine_scope=False`, so no extra `claude plugin list --json`
subprocess is spawned per consumer. The once-per-run property is asserted by a
call-count test, not by convention.

### 3. Per-consumer row gains `installMode` and `pin`

```json
{"name": "...", "installMode": "thin", "pin": {"version": "0.65.0", "source": ".sd-ai-command-pack/provenance.json", "state": "present"}}
```

The registry field is `mode` (parent design's wording) but the status row
field is `installMode`: the fleet payload already carries a top-level
`"mode": "fleet"` discriminator, and two `mode` meanings in one document is a
misread waiting to happen.

`state` is `present`, `absent`, or `unreadable` — never silently empty.
`read_json_object` (`scripts/sd-ai-command-pack-status.py:165`) collapses a
missing file, an I/O error, a Unicode error, and invalid JSON all to `None`,
so it cannot produce this three-way classification alone. The pin reader
stats/resolves the path first (`absent`, or `unreadable` on an escape), then
parses (`unreadable` on bad JSON or a missing `version` string), else
`present`.

**Read count, stated accurately (corrected again 2026-08-10):** the pin block
does its **own** read, even for the default path. Reusing
`collect_versions`' result is not viable: `:547-555` falls back to
`.sd-ai-command-pack/manifest.json` when provenance has no usable `version`,
and collapses "absent", "unreadable", and "present but versionless" into a
single `None`. That value cannot express the three pin states, so reuse would
trade a correct classification for one avoided read of an already-cached file.
Cost accepted; the earlier "no second file read" and "reuse the parsed
version" claims are both withdrawn.

For `fat` consumers `pin` is `null` and every existing field is unchanged.

### 4. Skew classification replaces tree drift for thin consumers

Three comparisons, not two — the parent design
(`.trellis/tasks/08-09-deployment-thin-consumers/design.md:116-119`) names
plugin-vs-receipt divergence as skew `sd-status` reports, and `machineScope`
already exposes `pluginVersion`, receipt `packVersion`, and their `comparison`
(`scripts/sd-ai-command-pack-status.py:1819`):

- **fat consumers** — unchanged: `installed != target` produces the existing
  "Refresh stale SD pack installations" row.
- **pin skew** (per thin consumer): consumer pin != machine-install version.
- **machine skew** (one fleet-level row): machine-install version != target.
- **plugin/receipt skew** (one fleet-level row): `machineScope.comparison`
  reports divergence.

**Every fleet-level row is gated on the registry containing at least one
`thin` consumer.** An all-fat fleet — the state of the registry today — emits
no machine rows at all, which is both semantically right (nothing consumes the
machine install yet) and what makes the AC3 all-fat proof achievable.

When the machine inventory is `unavailable` *and* thin consumers exist, thin
rows report `skew unavailable` and emit a follow-up saying so — an unavailable
source is never rendered as agreement.

**Truncation must not swallow skew.** Today `fleet_next_steps` returns
`steps[:HUMAN_ITEM_LIMIT]` and `fleet_follow_ups` derives `F-*` rows from that
truncated list, so with eight consumers plus missing/dirty/divergent rows a
skew row can silently vanish — contradicting PRD requirement 3. Fix: build the
full row set once, derive `followUps` from the **complete** set, truncate only
the human `nextSteps`, and sort skew rows ahead of advisory rows.

`render_fleet`'s attention counter applies the same mode split, so the human
summary and the JSON agree.

### 5. Terminology: "target", not "latest release"

The comparison target is the resolved pack checkout's `manifest.json` version.
All artifacts say **target pack version**. Comparing against the newest
published GitHub release would need a lookup that does not exist and would put
a network call in a read-only collector — out of scope, recorded as a
follow-up.

## Boundaries And Non-Goals

- Status stays strictly read-only: no fetch, no install, no pin rewrite, no
  machine update, no new network call.
- The pin is an expectation record, not execution control (parent PRD).
- No consumer is converted to thin here; `thin-migration` owns conversion.
- Fat-consumer tree-drift reporting is untouched; `thin-migration` retires it.
- No change to `install.py`, the machine installer, or the plugin.

## Affected Files

**Source of truth is `templates/**` (`AGENTS.md:28-32`)** — edit there, never
in the root mirror:

- `templates/scripts/sd_ai_command_pack_fleet_lib.py` — schema bump,
  `FleetConsumer` fields, validation.
- `templates/scripts/sd-ai-command-pack-status.py` — fleet `machineScope`
  block, per-consumer `installMode`/`pin`, three-way skew, untruncated
  follow-ups, renderer.
- `templates/.agents/skills/sd-status/SKILL.md:93-95` — the shipped contract
  currently promises "installed versus target pack version" for *every*
  consumer; thin rows report pin/machine instead.
- `docs/SD_AI_COMMAND_PACK.md` — the fleet-mode section (around `:612-616`).
- `manifest.json` — mandatory version bump for any shipped payload change
  (`CONTRIBUTING.md:136`), plus a matching top `CHANGELOG.md` heading; the
  `Release payload gate` CI job blocks the PR otherwise.

Pack-repo files (not shipped payload):

- `docs/fleet/consumers.json` — `schemaVersion: 5`.
- `docs/fleet/candidate-validation.json` — regenerated; its
  `fleetManifestDigest` pins the registry bytes.
- `docs/FLEET_ROLLOUT.md:7` — "schema-version-4 manifest" prose.
- `.trellis/spec/backend/manifest-and-filesystem.md:552, 557, 1710` — the
  existing fleet-registry contract the parent PRD
  (`.trellis/tasks/08-09-deployment-thin-consumers/prd.md:83`) requires
  updating.

Generated mirrors — never hand-edited: root `scripts/` (via `make sync`) and
`plugins/sd/bin/` + `plugins/sd/machine-payload/scripts/` (via `make
generate`, which runs `generate-plugin.py`). Two different targets; `make
sync` alone does not refresh the plugin trees.

Fixtures and enforced strings:

- `tests/install_test_support.py:70`, `tests/test_fleet_wave_plan.py:76`,
  `tests/test_fleet_controller.py:41` — `"schemaVersion": 4`.
- `tests/test_fleet_candidate.py:449-450` — asserts the literal error text
  `"schemaVersion must be 4"`.
- `tests/test_sdlc_commands.py:415` — pins the doc phrase
  `"schema-version-4 manifest"`.

## Data And Command Contracts

Registry entry (schema 5):

| Field | Type | Required | Default | Constraint |
|---|---|---|---|---|
| `mode` | string | no | `"fat"` | one of `fat`, `thin` |
| `pinPath` | string | no | `.sd-ai-command-pack/provenance.json` | repo-relative, no `..`, no leading `/`; resolved and contained at read time |

Fleet JSON additions. The status payload's own `SCHEMA_VERSION` **stays 2, and
that is now a hard constraint, not a convenience**:
`scripts/sd-ai-command-pack-housekeeping-result.py:43,173` requires exactly 2
by equality, so a bump would break housekeeping's result path. All additions
here are optional fields and extra rows. Removing or retyping a field would
require coordinating that consumer.

| Path | Type | Meaning |
|---|---|---|
| `machineScope` | object | one machine-scope inventory for the run |
| `repositories[].installMode` | string | `fat` or `thin` |
| `repositories[].pin` | object\|null | `{version, source, state}` for thin |

Error matrix:

| Condition | Result |
|---|---|
| `schemaVersion` != 5 | `FleetConfigError: ... schemaVersion must be 5` |
| `mode` not in {fat, thin} | `FleetConfigError` naming consumer and value |
| `pinPath` absolute or containing `..` | `FleetConfigError` naming the consumer |
| `pinPath` resolves outside the consumer root | row `state: "unreadable"` + reason |
| pin path does not exist | row `state: "absent"` + follow-up; exit stays 0 |
| pin unparseable or has no `version` | row `state: "unreadable"` + follow-up |
| machine inventory unavailable, thin consumers present | skew `unavailable` + follow-up |
| registry has no thin consumers | no machine-level rows at all |

## Risks And Edge Cases

- **The bump invalidates release evidence.** Regenerating the ledger clones
  each consumer's default branch; `CONTRIBUTING.md:129-134` forbids running
  the full-fleet validator early, because later generation or sync
  invalidates it. It belongs in `make release-prep`, at the end.
- **Wrong tree edited.** Editing root `scripts/` then running `make sync`
  silently reinstalls the template version over it.
- **`make sync` does not refresh plugin trees** — `make generate` does.
- **Strict-equality schema bump is partly prose.** A grep for
  `"schemaVersion": 4` misses `"schemaVersion must be 4"` and
  `"schema-version-4 manifest"`.
- **Follow-up truncation** is the mechanism that would make skew silent.
- **A thin consumer with no pin must not read as healthy** — hence the
  three-way state and the containment check.
- **AC3's before/after proof crosses the mandatory manifest bump**, which
  moves the fleet target and therefore which consumers count as stale. The
  target cannot be pinned — `parse_args` (`scripts/sd-ai-command-pack-status.py:3068+`)
  exposes no override and this task adds none — so the proof instead compares
  everything except the additive fields, and reconciles the stale-row
  difference by recomputing each payload's stale set from its own rows
  (implement.md's validation plan). String-normalizing the version is not
  sufficient on its own: stale rows name consumers, not versions.

## Validation

- Focused: `python3 -m unittest tests.test_status tests.test_fleet_preflight
  tests.test_fleet_controller tests.test_fleet_wave_plan
  tests.test_fleet_candidate tests.test_sdlc_commands`.
- Full suite via `.github/scripts/run-tests.sh`, plus CI's discovery form.
- `make generate`, `make sync`, then `make release-prep` (which refreshes the
  fleet ledger only when stale and finishes with `make check`).
- Manual all-fat proof: full-payload comparison minus the additive fields,
  with the stale row reconciled by recomputation (implement.md validation plan).
