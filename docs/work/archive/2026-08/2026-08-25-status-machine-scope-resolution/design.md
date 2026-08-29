# Status Collector Machine-Scope Resolution Design

## Overview

`machine_scope_api()` (`scripts/sd-ai-command-pack-status.py:1717-1754`) loads
the machine-scope engine from exactly one place: `installer/machinescope.py`
beside the directory holding the running script. On a machine install the
script lives at `~/.agents/bin/`, so that arithmetic yields `~/.agents`, which
ships no `installer/` at all — and the `sd-status` skill routes thin consumers
to precisely that copy. The row is therefore permanently `unavailable` for the
documented path, which in issue #496 hid a live 0.71.26-against-0.71.22 skew.

This design adds one resolution rung *below* the existing one and defines the
trust rule that a second rung requires.

## Proposal

### Resolution ladder

`machine_scope_api()` gains an ordered candidate list. Rung one is today's
arithmetic, unchanged and still first, so every arrangement that resolves
today resolves identically and through the same path.

| # | Rung | Source | Resolves when |
| --- | --- | --- | --- |
| 1 | script-adjacent | `Path(__file__).resolve().parent.parent` | pack checkout, plugin root, or a `~/.agents/bin` that is a symlink into a plugin root |
| 2 | `PATH` toolchain dirs | `path_pack_bins()` (`:1900`), parent of each entry, in `PATH` order | a pack install whose `bin/` is on `PATH` — the observed plugin cache case |

**Two rungs, not three.** A working-directory rung was drafted and dropped in
review (2026-08-25): `runtime_pack_root()` (`:3547`) adds one for the fleet
manifest, but reading a *manifest* from the working directory and *importing
executable code* from it are different risks, and rung 2 already resolves the
arrangement #496 reports. The PRD authorizes the rungs needed to fix that
arrangement; a third rung would be scope the PRD does not carry and attack
surface the defect does not require.

`Path(__file__).resolve()` already follows symlinks, so a plugin root
symlinked into `~/.agents/bin` is served by rung one and needs no special
case. The defect is specific to a machine install holding a real copy.

### Trust rule (the part that is not a refactor)

Rung 1 is safe by construction: the engine comes from the tree already
executing. Rung 2 is not — it imports and executes Python from a directory
named by `PATH`, which an unprivileged process can influence. The added rung
is therefore gated:

1. **Identity** — the candidate root must look like a pack install, not merely
   contain the file the loader wants. Require `installer/__init__.py` *and*
   `installer/machinescope.py` (a real package, not a lone dropped module),
   *plus* one root-identity marker.

   The marker set is not a guess; the naive choice fails. Measured
   2026-08-25 against the three real arrangements on the observed machine:

   | root | `manifest.json` | `.claude-plugin/plugin.json` |
   | --- | --- | --- |
   | pack checkout | yes (`name: sd-ai-command-pack`) | yes |
   | plugin cache `.../sd/0.71.51/` | **no** | yes (`name: sd`, `version: 0.71.51`) |
   | marketplace root | yes | — |

   The plugin cache root — the one this fix exists to reach — carries no
   `manifest.json` at all. A gate keyed on it alone would reject the target
   root and ship a fix that does not fix anything. So: accept
   `manifest.json` with `name` `sd-ai-command-pack`, **or**
   `.claude-plugin/plugin.json` with `name` `sd`. The plugin manifest's
   `version` also supplies the engine-root version for the provenance below.
2. **Writability** — reject a candidate whose root, `installer/` directory, or
   `machinescope.py` is world-writable. A directory anyone can write to is a
   directory anyone can use to choose what this collector executes.
3. **Order** — candidates are tried in `PATH` order, because that is the order
   in which a bare helper invocation would already have reached them.

A rejected candidate is **recorded, not silently skipped**. Silent skipping
would degrade to plain `unavailable` — reintroducing the exact
uninformative failure this task removes, while also hiding a possible attack.

### Provenance in the report

`machine_receipt_state()` gains the resolved root and the rung that supplied
it, and `format_machine_scope()` (`:3146`) renders it when the engine did not
come from rung one. The plugin cache root is version-qualified
(`.../sd/0.71.51/`), so the engine may be a different version from the install
it reports on — tolerable only if the reader can see it.

## Boundaries And Non-Goals

- **Not** changing the layout resolver's answer for `sd-status.py` (issue
  #496 direction 2). The resolver's answer is correct for what it resolves;
  the loader's assumption is what is wrong.
- **Not** shipping `installer/` in the machine payload (direction 3). That
  grows every machine install to carry an installer it does not use, and the
  partition exists to avoid exactly that.
- **Not** touching the engine's helper-library contract. The first import of
  `sd_ai_command_pack_lib` still wins, deliberately; only the docstring's list
  of shipped arrangements is corrected.
- **Not** changing `machinescope.status()` or its schema.

## Affected Files

Canonical:

- `templates/scripts/sd-ai-command-pack-status.py` — ladder, trust gate,
  provenance. **This tree is the source**, corrected during implementation
  (2026-08-25) after the first edit landed in `scripts/` and `make sync`
  reported `mirror.stale`. `manifest.json` marks it `kind: managed-block`
  material; the other three trees are generated from it.
- `tests/` — new fixtures per arrangement and per refusal. Note the tests
  import the `templates/` copy, so editing only a mirror produces a green
  mirror and a red canonical tree.

Generated mirrors of the collector (never hand-edited; regenerated by
`make sync` / `make generate`):

- `scripts/sd-ai-command-pack-status.py`
- `plugins/sd/bin/sd-ai-command-pack-status.py`
- `plugins/sd/machine-payload/scripts/sd-ai-command-pack-status.py`

## Data And Command Contracts

- `machine_scope_api()` returns the module as today. On total failure it still
  raises `RuntimeError`; the message now names every candidate tried and, for
  each refusal, why.
- `machine_receipt_state()` adds `engineRoot` (string or `None`) and
  `engineRung` (`"adjacent" | "path"`), plus `engineRefusals` (bounded
  list of `{root, reason}`). Absent keys must not break an older reader: these
  are additive, and `format_machine_scope` renders them only when present.
- No new CLI flags, no new configuration, no new environment variable. The
  ladder is discovery, not policy.

## Risks And Edge Cases

| Risk | Handling |
| --- | --- |
| A decoy on `PATH` supplies the engine | Identity + writability gate; refusal is reported |
| Version skew between engine root and reported install | `engineRoot`/`engineRung` rendered; skew stays visible rather than reconciled |
| A later rung silently answers where rung 1 used to | Tests assert the *resolved path*, not merely success |
| `PATH` with many entries | `path_pack_bins()` already bounds at `MAX_PATH_PACK_ENTRIES` |
| Symlinked plugin root | Served by rung 1 via `resolve()`; asserted by fixture |
| `~/.agents` present but empty | Rung 1 misses, ladder continues, message names it |

Rollback is a revert: the ladder is additive and no state or schema migration
is involved.

## Validation

- Per-rung fixtures asserting the resolved path.
- Refusal fixtures: decoy identity, world-writable root, each asserting both the
  refusal and that it is reported rather than swallowed.
- A no-rung fixture asserting the message names every candidate.
- The machine-install reproduction from #496, asserted to fail on `main`.
- `make generate` for the mirrored copies; repo gate before shipping.
