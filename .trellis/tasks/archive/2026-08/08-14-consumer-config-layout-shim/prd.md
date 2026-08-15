# Consumer-config layout shim: zero pack-path literals

## Problem

Thin conversion fails closed. `sd-ai-command-pack-thin-resweep.py` returns
`blocked` when a consumer holds **any** reference to a path conversion removes
(`scripts/sd-ai-command-pack-thin-resweep.py:1784`, "N consumer reference(s) to
removed paths"). One blocker is as blocking as ninety.

`08-11-pack-layout-aware-guard` shipped `sd-ai-command-pack-review-layout.py`,
whose `--resolve NAME` query answers "where does this pack script live right
now" so a consumer stops hardcoding the fat layout. That closed the *content*
gap and left the *reachability* gap open: the resolver is itself
`machine-claude`, so a consumer must still name it by a path conversion
removes in order to ask it anything. The reference that asks "where is the
pack" is a blocker on exactly the same terms as the references it replaces.

That task's design stated the residue as one bootstrap site per consumer
(`design.md` D3c, archived). Measured against the eight saved resweeps, that is
not a property of the current code:

| consumer | resolve-reachable blockers | distinct files holding them |
|---|---:|---:|
| anomaly-metric-creator | 112 | 17 |
| rwbp-website | 36 | 6 |
| loadsmith | 40 | 2 |
| rwbp-coordinator | 29 | 6 |
| mezmo_benchmark | 21 | 15 |
| hoa-manager | 22 | 8 |
| se-ai-command-pack | 16 | 6 |
| sd-github-review | 12 | 8 |
| **total** | **288** | **68** |

Adopting `--resolve` without a surviving entrypoint converts 288 blockers into
up to **68** — one probe per file that asks — not into 8. Reaching one site per
consumer is per-consumer centralization work nobody has scoped, and it is work
the cohorts would do once and then delete. A pack file at a path conversion
keeps removes the requirement instead: 68 files may each name it, and none of
them is a blocker.

## Goal

Ship a pack entrypoint at a path that survives thin conversion, so a consumer
reference to the pack is not a conversion blocker, without requiring the
consumer to centralize its call sites first.

## Requirements

R1. The entrypoint's installed path is classified `consumer-config` by
`docs/fleet/surface-partition.json`, so `installer/conversion.py`
`KEEP_CATEGORIES` retains it and the resweep does not count references to it.

R2. It installs into a consumer that declares no `claude` platform. The two
existing `.claude/**` consumer-config rows carry `platform: "claude"`; this row
must not depend on a platform a consumer may not declare.

R3. Its committed bytes are identical in every consumer and on every machine.
A consumer-config file is committed to the consumer repository, so it must not
contain a resolved machine path, a home directory, or any install-time value.

R4. It answers correctly under both layouts — a fat consumer that still
vendors `scripts/`, and a thin consumer where the payload lives machine-scope —
and reports which, without the caller branching on it.

R5. It does not import `sd_ai_command_pack_lib`. That module is
`machine-claude`; under thin it is not beside the entrypoint and the import
fails. Any state-root logic it needs is carried in its own bytes, with a pack
test asserting the carried copy and `resolve_state_root` agree.

R6. It is callable from shell, Python, and Node without a bespoke launcher per
language, because the 68 measured call sites are written in all three.

R7. Adding it does not regress the install, conversion, plugin-build, or audit
gates: `make check`, `make release-prep`, and the shipped-script coverage,
advisory, and docs gates pass.

## Constraints

C1. No consumer repository is edited by this task. Rewriting the 68 call sites
is the conversion cohorts' work; this task makes it a rewrite to a stable path
rather than a rewrite plus a centralization.

C2. No change to what conversion removes. The categories that move are
additive: one new row enters `consumer-config`.

C3. The entrypoint is a payload file, so the full payload cascade applies —
`manifest.json` registration, `make sync`, `make generate`, candidate-check,
version bump, CHANGELOG heading.

## Out of scope

- **A literal fleet-wide zero.** 101 of the 456 measured blockers are glob
  patterns in instructions prose (`.gemini/commands/sd/**`,
  `.agents/skills/sd-*/**`) and CI-change-classifier fixture lists. No runtime
  resolver rewrites a glob. Those lines need per-consumer rewriting or explicit
  acceptance, owned by each conversion cohort, and this task does not claim
  them. The claim here is bounded to the 288 resolve-reachable blockers plus
  the bootstrap references adopting `--resolve` would introduce.
- Converting any consumer to thin.
- Deleting the bespoke guards in the five consumers that have them.
- Touching any consumer repository.

## Acceptance criteria

- [x] AC1 — Measured before: `{'repo-native': 551, 'machine-other': 89,
  'machine-claude': 80, 'consumer-config': 6}`, total 726. After:
  `consumer-config` 7, total 727, every other category unmoved.
  `partition-surfaces.py --check` passes inside `make check`.
- [x] AC2 — A test asserts the row installs for a consumer whose declared
  platform set excludes `claude`, and that `installer/conversion.py` retains it
  in `expected_residual_targets` for that same consumer.
- [x] AC3 — A test drives the entrypoint under a simulated fat layout and a
  simulated thin layout from the same bytes and asserts the two answers differ
  and that neither depends on `sd_ai_command_pack_lib` being importable.
  Evidence: the thin case runs with that module absent from `sys.path`.
- [x] AC4 — A test asserts the carried state-root logic and
  `sd_ai_command_pack_lib.resolve_state_root` agree across all five rungs.
- [x] AC5 — Shell, Python, and Node callers reach it, and a test asserts all
  three return the same answer for the same query.
- [x] AC6 — `make check` and `make release-prep` exit 0; the shipped-script
  coverage floor, `test_install_audit` advisory gate, and shipped-script docs
  gate all pass for any new script.
- [x] AC7 — A resweep fixture (not a live consumer) containing a reference to
  the new entrypoint's path reports it as **not** a blocker, and the same
  fixture with the old `scripts/sd-ai-command-pack-review-layout.py` reference
  reports it as a blocker. Both directions, so the test cannot pass by the rule
  never firing.
- [x] AC8 — `docs/FLEET_ROLLOUT.md` (or the conversion doc it points at)
  records the ordering the cohorts depend on: ship, refresh the fleet to the
  version that carries it, rewrite call sites, resweep, convert.
- [x] AC9 — The `--path` bound is documented and pinned by a test: in a
  converted consumer the query answers about the current install, so a
  `scripts/sd-ai-command-pack-*.py` path classifies `authored`. Pre-existing
  behaviour this task makes reachable rather than introduces; see design D5b
  and ledger entry C-4.

## Evidence

- **AC2** — `tests/test_conversion_plan.py::test_the_layout_resolver_survives_conversion_for_any_platform_set`,
  read against the shipped partition rather than a fixture, over platform sets
  `{gemini}`, `{github, opencode}`, and empty. The same test asserts the
  `scripts/` copy is *not* retained, so it cannot pass with conversion removing
  nothing.
- **AC3** — `test_the_module_imports_without_the_library` blocks
  `sd_ai_command_pack_lib` in `sys.modules` and then resolves a thin layout.
  Verified the block is not vacuous: `import of sd_ai_command_pack_lib halted;
  None in sys.modules`. The fat-versus-thin answers are asserted to *differ* by
  the pre-existing `test_thin_resolves_somewhere_other_than_the_consumer`,
  which the carried ladder now serves.
- **AC4** — `test_carried_state_root_ladder_matches_library`, ten cases across
  all five rungs plus three absolute-path refusals, each side raising its own
  `CommandError` type. The tenth (`nt` with no `LOCALAPPDATA`) was added to
  close the one branch the carried ladder left uncovered.
- **AC5** — `test_the_shell_binding_agrees_with_the_script` added; the Node
  case already existed. Both compare against the same `--root`, because
  `review-scope.sh:6` picks its own (see implement 4.4).
- **AC6** — `make check` exit 0. Resolver coverage `210 0 86 0 100%` against a
  floor of 95. `make release-prep` recorded below.
- **AC7** — `tests/test_thin_resweep.py::LayoutResolverReferenceTests`, three
  cases: the `scripts/` citation blocks, the `.sd-ai-command-pack/bin/`
  citation is `clear`, and the partition really does classify the two
  oppositely — so the buckets are decided for the reason claimed.
- **AC9** — `test_a_converted_consumer_classifies_a_removed_script_as_authored`,
  which also asserts the surviving copy still classifies `pack-payload`, so the
  test reads as a bound rather than as "classification is broken under thin".

Install-time evidence (open questions O1, O3, O4, O5): install audit passed at
201 targets with both paths in `installed-targets.txt`; machine installer
payload unchanged at 116 rows with no `consumer-config` row in it; both
installed copies byte-identical at mode `644`; the machine receipt's 115
entries contain no `.sd-ai-command-pack` path.
