# Design — unfreeze the source-only command adapters

## Scope boundary

`.github/scripts/generate-command-surfaces.py`, the drift gate in
`.github/scripts/check-command-surface-drift.py`, and the four source-only
adapters in the dev tree. `SOURCE_ONLY_COMMAND_NAMES` semantics are fixed
(PRD R4): source-only targets stay out of consumer installs.

## Confirmed defect

```
.claude/commands/sd/fleet-refresh.md            checkout-trust: 0
templates/.claude/commands/sd/fleet-refresh.md  checkout-trust: 1
```

The dev-tree adapter — the only runnable fleet-refresh surface in a source
checkout — carries no checkout-trust policy block. Its template twin does. The
dev copy is frozen at the 0.20.0 era.

The four frozen source-only adapters:

- `.claude/commands/sd/fleet-refresh.md`
- `.gemini/commands/sd/fleet-refresh.toml`
- `.github/prompts/sd-fleet-refresh.prompt.md`
- `.opencode/commands/sd-fleet-refresh.md`

Neutral source: `.github/command-sources/sd-fleet-refresh.md`.

## Why they froze — three independent gaps stacked

1. **Generation.** `bespoke_adapter_path` (`generate-command-surfaces.py:568`)
   returns `templates/…` paths only. Nothing emits a source-only adapter into the
   dev tree, so regeneration never touches these four.
2. **Manifest.** `:881` builds `derived` from `COMMAND_REGISTRY` with
   `if command.name not in SOURCE_ONLY_COMMAND_NAMES` — source-only commands get
   **no manifest entry at all**. Correct for installs; it also means the manifest
   cannot be the enumeration source for any gate over these paths.
3. **Drift gate.** `tests/test_pack_drift.py:144` iterates `load_manifest()`,
   which by (2) never yields these targets. The twin-parity gate is structurally
   blind to them.

Each gap alone would be survivable. Together they make a frozen file invisible.

## The central tension

The obvious fix — give source-only commands manifest entries so the existing gate
picks them up — is forbidden by R4 and would be wrong: a manifest entry is what
makes a target install into a consumer, and `installer/removal.py:272` already
relies on source-only exclusion when pruning source checkouts. Adding entries
would ship fleet-refresh to all eight consumers.

So the drift gate needs an enumeration that is **not** the manifest.
`check-command-surface-drift.py:404` already accepts `source_only:
frozenset[str]` as a parameter, so the lint layer knows these names exist. The
registry — `installer/registry.py:1176` — is the single source of truth for which
commands are source-only, and `COMMAND_REGISTRY` supplies each command's target
families. Derive the four paths from those two, the same way
`derived_manifest_entries` does, but into the dev tree instead of the manifest.

**Recommendation:** one shared path-derivation helper used by both the generator
and the gate. Two independent lists of the same four paths is how this drifts
again.

## Contract after the change

- `generate-command-surfaces.py` emits source-only adapters to dev-tree paths in
  addition to `templates/`. Bespoke platforms (claude, gemini, github) plus
  opencode's neutral form.
- The drift gate fails when a dev-tree source-only adapter diverges from what
  regeneration would produce.
- `SOURCE_ONLY_COMMAND_NAMES` is unchanged; the manifest is unchanged; consumer
  installs are unchanged. This is verifiable: `manifest.json` must be
  byte-identical after the change.

## Note on the template asymmetry

Templates carry `.commands/sd-fleet-refresh.md` (neutral) while the dev tree
carries `.opencode/commands/sd-fleet-refresh.md`. Confirm which is canonical
before wiring path derivation, or the generator will emit a fifth file nobody
wants.

## Rollout and rollback

Repo-internal. No consumer sees any of this. First regeneration will produce a
large diff in the four adapters — that diff **is** the fix, and it must be read
rather than rubber-stamped, since it is the accumulated delta since 0.20.0.

Rollback is a plain revert; the frozen adapters return to their frozen state.

## Risk

The regenerated adapters may change fleet-refresh behavior in ways beyond the
trust block, because they have been frozen across many releases. Diff them
against the template twins before accepting, and treat any behavioral surprise as
a finding rather than noise.
