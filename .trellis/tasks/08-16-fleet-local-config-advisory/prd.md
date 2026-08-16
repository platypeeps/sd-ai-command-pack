# Stop emitting a fleet follow-up that no action can clear

## Goal

Make the fleet report's provider-config advisory fire when there is something to
merge, instead of whenever a consumer owns its own copy. Today it is the only
follow-up the fleet report ever shows, it has shown on every run since the
migration, and nothing an operator can do will retire it.

## Background

`sd-status fleet` currently emits exactly one follow-up:

```text
$ scripts/sd-ai-command-pack-status.py fleet --json --no-network
followUps:
 - {"kind": "action", "summary": "Merge shipped provider config changes by hand
    where the consumer owns the file: rwbp-coordinator, hoa-manager,
    rwbp-website, mezmo_benchmark, se-ai-command-pack, anomaly-metric-creator."}
```

It is emitted at `scripts/sd-ai-command-pack-status.py:3251` on a single
condition — any provider config in state `local`:

```python
    local_configs = [
        item["name"]
        for item in reports
        if any(
            state.get("state") == "local"
            for state in item.get("providerConfigs") or ()
        )
    ]
```

### `local` is permanent by construction

The state is assigned at `scripts/sd-ai-command-pack-status.py:3078-3088`. A
config is `current` when its digest equals the shipped one, `superseded` when
its digest appears anywhere in the shipped history, and `local` when it matches
nothing the pack has ever shipped — that is, the consumer edited it, or
symlinked it, which the code deliberately classifies the same way.

The classification is right. The advisory drawn from it is not. `superseded`
already means "behind a shipped version", and it has its own correctly-worded
row three lines above telling the operator to run `install.py`. `local` means
"diverged, deliberately" — and the comment beside the emitter says so:

```python
        # Not skew: a locally owned config is a decision the installer will
        # keep honoring. It is listed so a shipped correction that will never
        # reach it is visible to a human who can merge it.
```

A decision the installer will keep honoring does not stop being made. There is
no acknowledgement, suppression, or opt-out path, so the row cannot clear. Its
stated purpose — surfacing a *shipped correction* that cannot reach the
consumer — is never actually tested: the condition asks whether the file
diverges, not whether the pack has shipped anything since it diverged.

### Measured across the fleet

```text
rwbp-coordinator         current  .gito/config.toml    local    .prism/rules.json
loadsmith                current  .gito/config.toml    current  .prism/rules.json
hoa-manager              current  .gito/config.toml    local    .prism/rules.json
rwbp-website             current  .gito/config.toml    local    .prism/rules.json
mezmo_benchmark          current  .gito/config.toml    local    .prism/rules.json
se-ai-command-pack       current  .gito/config.toml    local    .prism/rules.json
sd-github-review         current  .gito/config.toml    current  .prism/rules.json
anomaly-metric-creator   current  .gito/config.toml    local    .prism/rules.json
```

Six of eight, all on `.prism/rules.json`, none on `.gito/config.toml`. The two
`current` rows confirm the classifier rather than contradicting it: loadsmith's
`.prism/rules.json` is byte-identical to `templates/.prism/rules.json`
(`sha256:cea5089e…`), while rwbp-coordinator's (`sha256:49008faa…`) and
hoa-manager's (`sha256:3e9d6031…`) are not.

The cost is that the fleet report's follow-up section is permanently occupied by
a row no one can act on, which is the reliable way to teach a reader to stop
looking at follow-ups.

## Requirements

1. Emit the row only when the shipped provider config has changed since the
   consumer's copy could last have matched it. Divergence alone is not the
   trigger; an unmerged shipped change is.
2. Leave the `superseded` row at `scripts/sd-ai-command-pack-status.py:3237`
   alone. It already covers "behind a shipped version" and its remedy
   (`install.py`) is correct for that state.
3. Keep the symlink case classified as `local`
   (`scripts/sd-ai-command-pack-status.py:3078`). Whatever replaces the
   advisory condition must not turn a deliberate symlink into a skew row.
4. If no shipped-change signal is available to compare against, the row must
   not be emitted at all rather than fall back to firing on divergence. A
   permanently-on advisory is worse than a missing one.
5. Both copies change together. `scripts/sd-ai-command-pack-status.py` and
   `templates/scripts/sd-ai-command-pack-status.py:3256` are byte-identical
   twins; the shipped payload change requires a `manifest.json` version bump, a
   CHANGELOG heading, and `make sync`.

## Acceptance criteria

- [ ] A fleet with a consumer whose provider config is `local` and whose shipped
      counterpart has not moved since emits no provider-config follow-up.
- [ ] A fleet with a consumer whose provider config is `local` and whose shipped
      counterpart *has* moved emits the row, naming that consumer.
- [ ] A consumer whose config is a symlink is still reported in state `local`
      and is not reported as skew.
- [ ] `superseded` consumers still get the `install.py` row, unchanged.
- [ ] Run against the live fleet, `sd-status fleet --json` reports zero
      follow-ups. This is the criterion the current code cannot satisfy at any
      version, and it is checked against the real registry rather than a
      fixture.
- [ ] `make release-prep` passes, covering the twin sync and the payload digest
      the candidate ledger pins.

## Notes

Worth deciding during design rather than assuming: whether "the shipped
counterpart has moved" is answerable at all from what a consumer records. The
receipt knows which pack version installed the file; if it also knows the digest
that was shipped at that moment, the comparison is a lookup. If it does not,
requirement 4 applies and the row should be dropped rather than approximated.
