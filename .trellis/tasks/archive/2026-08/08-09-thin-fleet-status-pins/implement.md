# Fleet/status rework to pin + plugin inventory — Implementation Plan

Every path below is `templates/**`-first: `AGENTS.md:28-32` makes templates the
source of truth and the root copies byte-verified mirrors. Editing a root copy
and then running `make sync` reinstalls the template version over it.

## Execution Order

1. **Requirement 1 is already satisfied — verified 2026-08-10.**
   `sd-status --json --no-network` on this checkout returns `machineScope`
   with `state: "none"`, `pluginVersion: "unavailable"`, and an explanatory
   `pluginDetail`. Requirement 1 is a *regression-test* deliverable; do not
   re-implement `collect_machine_scope`.

2. **Set up a scratch dir and capture the pre-change fleet baseline**:

   ```bash
   SCRATCH="$(mktemp -d)"; echo "$SCRATCH"
   bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
     scripts/sd-ai-command-pack-status.py fleet --json --no-network \
     > "$SCRATCH/fleet-before.json"
   ```

   Keep `$SCRATCH` exported for the rest of the task; an unset variable would
   write to `/fleet-before.json`.

3. **Enumerate the blast radius** — three spellings, because the version is
   enforced as prose and as an asserted error string too:

   ```bash
   grep -rn '"schemaVersion": 4' tests/ docs/ scripts/ templates/ plugins/
   grep -rn 'schemaVersion must be 4' tests/ scripts/ templates/
   grep -rn 'schema.version.4\|schema version 4' docs/ .trellis/spec/ tests/
   grep -rn 'FLEET_SCHEMA_VERSION' . --include='*.py'
   ```

   Known hits: `tests/install_test_support.py:70`,
   `tests/test_fleet_wave_plan.py:76`, `tests/test_fleet_controller.py:41`,
   `tests/test_fleet_candidate.py:449-450`, `tests/test_sdlc_commands.py:415`,
   `docs/FLEET_ROLLOUT.md:7`,
   `.trellis/spec/backend/manifest-and-filesystem.md:552, 557, 1710`.

4. **`templates/scripts/sd_ai_command_pack_fleet_lib.py`** — smallest first
   step:
   - `FLEET_SCHEMA_VERSION = 5`;
   - `FleetConsumer` gains `mode: str = "fat"` and
     `pin_path: str = DEFAULT_PIN_PATH`, **declared last with defaults** —
     `tests/test_fleet_candidate.py:45`,
     `tests/test_fleet_preflight.py:272`, and
     `tests/test_fleet_wave_plan.py:31` construct the dataclass directly and
     would otherwise fail the focused gate;
   - validate in `_parse_fleet_consumers_without_policy`'s consumer loop:
     mode in `{"fat", "thin"}`; `pinPath` rejected when absolute or containing
     `..`; both defaulted when absent.

5. **`docs/fleet/consumers.json`** — bump to `schemaVersion: 5`, add `mode` to
   nothing: all 8 consumers are fat, so the real registry exercises the
   default.

6. **Update every hit from step 3**, including the two enforced-string tests
   and the backend spec's fleet-registry contract (parent
   `.trellis/tasks/08-09-deployment-thin-consumers/prd.md:83` requires the
   *existing* spec be updated, not only a new one).

7. **`templates/scripts/sd-ai-command-pack-status.py`, fleet collection:**
   - call `collect_machine_scope` once in `collect_fleet`; publish under the
     existing `machineScope` key;
   - add `installMode` and `pin` to each consumer row. The pin block does its
     **own** read even for the default path: `collect_versions:547-555` falls
     back to `.sd-ai-command-pack/manifest.json` and collapses
     absent/unreadable/versionless into one `None`, so its result cannot carry
     the three pin states;
   - the pin reader resolves the path with `resolve(strict=True)` +
     `relative_to(<consumer root>)` — the existing containment pattern at
     `scripts/sd_ai_command_pack_fleet_lib.py:706-709` — before parsing.
     Missing ⇒ `absent`; escape, unparseable, or no `version` string ⇒
     `unreadable`;
   - do **not** touch the status payload `SCHEMA_VERSION`:
     `scripts/sd-ai-command-pack-housekeeping-result.py:43,173` requires
     exactly 2 by equality.

8. **Skew classification** — build the complete row set first, then:
   - fat: existing installed-vs-target row, unchanged;
   - thin, per consumer: pin vs machine-install version;
   - fleet-level: machine-install version vs target;
   - fleet-level: plugin vs receipt (`machineScope.comparison`);
   - machine inventory unavailable: its own explicit row.

   **Gate all fleet-level rows on `any(consumer.mode == "thin")`.** With
   today's all-fat registry the machine rows must not appear at all — that is
   both the correct semantics and what keeps AC3 provable.

   Derive `followUps` from the **untruncated** set; apply `HUMAN_ITEM_LIMIT`
   only to rendered `nextSteps`, with skew rows sorted ahead of advisory rows.

9. **`render_fleet`** — mirror the mode split in the attention counter and the
   per-row line. Human output and JSON must not disagree.

10. **Shipped contract docs** (payload — they force step 12's version bump):
    - `templates/.agents/skills/sd-status/SKILL.md:93-95` — currently promises
      "installed versus target pack version" per consumer; state the thin
      shape (pin, machine version, skew) alongside it;
    - `docs/SD_AI_COMMAND_PACK.md` fleet-mode section (~`:612-616`).

11. **Tests** (in `tests/test_status.py` and `tests/test_fleet_*.py`):
    - requirement-1 regression: local `machineScope` reports plugin + receipt
      versions and labels absent sources `unavailable` with a detail string;
    - parser contracts: invalid `mode`, absolute `pinPath`, `pinPath`
      containing `..` — each raises `FleetConfigError` naming the consumer;
    - pin reader: `absent`, `unreadable` (invalid JSON), `unreadable` (dict
      with no `version`), and `unreadable` (symlink escaping the consumer
      root);
    - mixed fat/thin registry renders both shapes; stale thin pin ⇒ `F-*` row;
    - machine inventory unavailable with thin present ⇒ skew `unavailable`
      + follow-up;
    - plugin-vs-receipt divergence ⇒ its own `F-*` row;
    - **all-fat gate**: a registry with no thin consumer emits no
      machine-level rows;
    - **truncation guard**: enough rows to exceed `HUMAN_ITEM_LIMIT`,
      asserting a skew row still appears in `followUps`;
    - **call-count guard**: `collect_fleet` invokes `collect_machine_scope`
      exactly once for an N-consumer registry;
    - **AC3 guard**: a schema-5 registry with no `mode` produces output
      identical to the schema-4 baseline apart from the additive fields. A
      unit test *can* hold the target constant — it builds its own fixture
      pack root, so `_pack_identity` reads a version the test chose — which is
      exactly what the CLI proof cannot do.

12. **Version bump + changelog** — `manifest.json` version and a matching top
    `CHANGELOG.md` heading. `CONTRIBUTING.md:136` makes this mandatory for any
    `templates/**` or `docs/SD_AI_COMMAND_PACK.md` change, and the
    `Release payload gate` CI job blocks the PR without it.

13. **Regenerate in the right order** — `make generate` (command surfaces,
    partition, **plugin** trees) then `make sync` (root mirror + spec KB), and
    only then `make release-prep`, which refreshes the fleet candidate ledger
    when stale and finishes with `make check`. `CONTRIBUTING.md:129-134`
    explicitly forbids running the full-fleet validator earlier: later
    generation or sync invalidates its evidence.

## Validation Plan

Focused, after step 6 and again after step 9:

```bash
.venv/bin/python -m unittest tests.test_status tests.test_fleet_preflight \
  tests.test_fleet_controller tests.test_fleet_wave_plan \
  tests.test_fleet_candidate tests.test_sdlc_commands
```

Broad, before finalization:

```bash
bash .github/scripts/run-tests.sh
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'   # CI's form
make generate && make sync && make release-prep
```

### AC3 proof as executed (2026-08-10) — stronger than the plan below

The planned proof compared a baseline captured *hours* earlier against a
post-change run, which conflates the code change with (a) the per-row
`report.versions.targetPack` echo the manifest bump also moves, and (b) real
drift in a consumer checkout another session was actively editing. Both showed
up as failures that were not the change.

What was run instead pairs the two binaries at the same instant:

```bash
git worktree add --detach "$SCRATCH/pre-change" HEAD      # pre-change pack, schema-4 registry
.venv/bin/python "$SCRATCH/pre-change/scripts/sd-ai-command-pack-status.py" \
  fleet --json --no-network \
  --fleet-manifest "$SCRATCH/pre-change/docs/fleet/consumers.json" \
  > "$SCRATCH/paired-before.json"
.venv/bin/python scripts/sd-ai-command-pack-status.py fleet --json --no-network \
  --fleet-manifest docs/fleet/consumers.json > "$SCRATCH/paired-after.json"
git worktree remove --force "$SCRATCH/pre-change"
```

The comparison script below is unchanged except that `canonical` also pops
`report.versions.targetPack` (asserting it equals the payload target first) and
`configuration.manifest` (the two registries necessarily sit at two paths in
this pairing). Result over the real 8-consumer fleet:

```text
AC3 OK: 8 rows, 2 nextSteps, 2 followUps identical apart from the additive fields
```

Falsification check: mutating one row's `status` in the after payload makes the
same script exit 1, so the pass is not vacuous.

Manual all-fat proof (read-only). The manifest bump from step 12 moves the
fleet target, and fat stale rows compare against it, so a raw before/after
diff shows unrelated churn. `parse_args` (`status.py:3068+`) has **no**
target-version override and this task does not add one, so the two runs cannot
be pinned to one version — the proof normalizes the version strings instead:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-status.py fleet --json --no-network \
  > "$SCRATCH/fleet-after.json"

python3 - "$SCRATCH/fleet-before.json" "$SCRATCH/fleet-after.json" <<'PY'
import json, sys

ADDITIVE_TOP = {"machineScope"}
ADDITIVE_ROW = {"installMode", "pin"}
STALE_PREFIX = "Refresh stale SD pack installations: "


def stale_names(payload):
    """Recompute the stale set from the payload's own rows."""
    target = payload["targetPackVersion"]
    return sorted(
        row["name"]
        for row in payload["repositories"]
        if row.get("status") == "available"
        and row["report"]["versions"]["sdAiCommandPack"] != target
    )


def canonical(payload):
    """Strip additive fields; replace the target-driven stale row with a
    marker so the two runs stay comparable across the manifest bump."""
    out = json.loads(json.dumps(payload))
    for key in ADDITIVE_TOP:
        out.pop(key, None)
    out.pop("targetPackVersion", None)
    for row in out["repositories"]:
        for key in ADDITIVE_ROW:
            row.pop(key, None)

    reported = [s for s in out["nextSteps"] if s.startswith(STALE_PREFIX)]
    assert len(reported) <= 1, reported
    if reported:
        listed = sorted(reported[0][len(STALE_PREFIX):].rstrip(".").split(", "))
        assert listed == stale_names(payload), (listed, stale_names(payload))

    def mark(text):
        return "<STALE-ROW>" if text.startswith(STALE_PREFIX) else text

    out["nextSteps"] = [mark(s) for s in out["nextSteps"]]
    out["followUps"] = [
        {**item, "summary": mark(item["summary"])} for item in out["followUps"]
    ]
    return out


before, after = (json.load(open(path)) for path in sys.argv[1:3])

# additive fields must actually be present after the change
assert isinstance(after.get("machineScope"), dict), "machineScope missing"
for row in after["repositories"]:
    assert row.get("installMode") == "fat", (row["name"], row.get("installMode"))
    assert row.get("pin") is None, row["name"]

# everything else must be byte-identical once the target-driven row is marked
a, b = canonical(before), canonical(after)
assert a == b, next(
    (k for k in set(a) | set(b) if a.get(k) != b.get(k)), "unknown key"
)
print("AC3 OK: full payload unchanged apart from the additive fields")
PY
```

That assertion script — not a raw diff, and not a comment-only placeholder —
is the AC3 evidence. Note it also proves the step-8 gate: any fleet-level
machine row would appear as a `nextSteps` inequality.

## Documentation And Spec Updates

- `templates/.agents/skills/sd-status/SKILL.md` and
  `docs/SD_AI_COMMAND_PACK.md` — shipped contract text (step 10).
- `.trellis/spec/backend/manifest-and-filesystem.md` — the existing
  fleet-registry contract (schema 5, `mode`, `pinPath`, defaulting,
  containment). Parent PRD:83 names this file.
- `docs/FLEET_ROLLOUT.md` — schema-version prose and the pin/skew report shape.
- `CHANGELOG.md` — top heading matching the `manifest.json` bump.
- A `.trellis/spec/tooling/` entry only if the contract does not fit the
  backend spec; do not split one contract across two specs.

## Review Notes

- Templates first; `make generate` ≠ `make sync` (plugin trees vs root mirror).
- Ledger regeneration runs last, via `make release-prep`, never early.
- Fleet-level rows gated on thin presence — that gate is what makes the all-fat
  output unchanged.
- Follow-ups derived before truncation is a correctness fix, not polish.
- One machine probe per fleet run, asserted by call count.
- Status payload `SCHEMA_VERSION` must stay 2 (housekeeping-result consumer).
- Read-only discipline: no new subprocess may fetch, install, or write.

## Rollback Points

- After step 6 (schema + registry + fixtures + docs): one commit, no status
  behavior change.
- After step 9 (status changes): revertable independently of the bump.
- Whole task: a single `git revert` restores schema-4 semantics; no migration
  state exists because no consumer is thin yet.

## Follow-Ups

Explicitly outside this PR:

- Converting any consumer to `thin` — `08-09-thin-migration`.
- Retiring tree-drift reporting and the vendoring gates — `thin-migration`.
- Comparing against the newest published GitHub release rather than the
  resolved checkout's `manifest.json` version — would add a network lookup to
  a read-only collector; file separately if wanted.
- Any actor that fixes skew from a status row; status stays read-only.
