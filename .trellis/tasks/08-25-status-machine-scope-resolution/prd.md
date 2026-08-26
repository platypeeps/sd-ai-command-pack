# Status collector resolves the machine-scope engine on machine installs

## Origin

Issue #496, filed 2026-08-17 from consumer repo `platypeeps/se-ai-command-pack`
against pack 0.71.22 / machine install 0.71.26, and re-confirmed by its author
against `v0.71.29`.

Verified again in this checkout on 2026-08-25 at current `main`:
`scripts/sd-ai-command-pack-status.py:1734-1739` is unchanged.

## Problem

`machine_scope_api()` resolves the engine with a single rung:

```python
root = Path(__file__).resolve().parent.parent          # :1734
module_path = root / "installer" / "machinescope.py"   # :1735
if not module_path.is_file():
    raise RuntimeError(
        f"machine-scope engine is not installed beside this script ({module_path})"
    )
```

Its docstring states the assumption that fails: *"`installer/` sits next to the
directory holding this script in every shipped arrangement: `scripts/` in a pack
checkout, `bin/` under a plugin root."* A **machine install** is a third
arrangement. It puts the collector at `~/.agents/bin/`, so the arithmetic yields
`~/.agents`, which ships `bin/`, `docs/`, `skills/`, `.skill-lock.json` and no
`installer/` at all — the machine payload contains zero `installer/` targets.

The `sd-status` skill routes callers through the layout resolver, and on a thin
consumer that resolver returns exactly the machine-payload copy. So the
documented path is the one arrangement in which machine scope can never resolve.
The two collector copies are byte-identical; this is invocation directory, not
version skew.

## Impact

Machine-scope reporting is `unavailable` for every thin consumer following the
documented path. In the filed case it suppressed a real finding: machine install
**0.71.26** against pack **0.71.22**, and the skew row never rendered.

## Precedent that decides the shape

The same arithmetic was already corrected once in this file, for the fleet
manifest, in 0.71.22 — `runtime_pack_root()` (`:3547-3575`) documents it:

> `scripts/../` was the only rung ... A machine install puts this script at
> `~/.agents/bin/`, where the same arithmetic yields `~/.agents` — not a pack
> checkout ... So the script's own location is still asked first, and the
> working directory is the added rung rather than the new preference.

`machine_scope_api()` never received the equivalent treatment. Prefer that
established shape — **widen the ladder, do not change the preference** — over
the issue's other two directions (resolver returns a different copy; ship the
installer package in the machine payload), both of which move the contract into
a different component.

## Requirements

- R1: `machine_scope_api()` asks the script-adjacent rung first, exactly as
  today, and falls back to further rungs only where that rung misses. Every
  arrangement that resolves today resolves identically after the change.
- R2: The added rung(s) locate a root that actually **carries `installer/`**.
  This is the requirement most easily got wrong, so it is stated with the
  measurement behind it (2026-08-25, observed machine):

  | rung | root it yields | carries `installer/machinescope.py` |
  | --- | --- | --- |
  | script-adjacent, machine install | `~/.agents` | no — the reported defect |
  | script-adjacent, plugin cache | `~/.claude/plugins/cache/sd-ai-command-pack/sd/<version>` | yes |

  `collect_toolchain_resolution()` (`:1955-1961`) is **not** the ladder to
  reuse. Its three rungs are the `SD_AI_COMMAND_PACK_TOOLCHAIN` override,
  `<repo>/scripts`, and `~/.agents/bin` — and the third is precisely the rung
  that fails here. Reusing it would ship a fix that still cannot resolve on the
  arrangement #496 reports.

  The rung that does answer is a `PATH` scan. `path_pack_bins()` (`:1900`)
  already enumerates every `PATH` directory holding the toolchain, in `PATH`
  order, and on the observed machine the plugin cache `bin/` is on `PATH` with a
  parent that carries `installer/`. Build on that existing helper rather than a
  second scan.

  A symlinked plugin root reached through `~/.agents/bin` needs no rung at all:
  `Path(__file__).resolve()` already follows symlinks, so that arrangement
  resolves through rung one today. The defect is specific to a machine install
  holding a real copy — verified: `~/.agents/bin/sd-ai-command-pack-status.py`
  is a regular file, not a symlink.

- R3: **A `PATH`-derived rung is a code-execution surface and must be
  constrained as one.** Today the engine is imported only from the tree holding
  the script, so the import is safe by construction. Sourcing it from a
  directory discovered on `PATH` means any writable `PATH` entry can present an
  `installer/machinescope.py` that this collector imports and executes. The
  ladder must therefore:

  - accept a candidate root only when it looks like a pack install, not merely
    because it holds the file the loader wants;
  - refuse a world-writable candidate root or engine path, and say why rather
    than falling through silently; and
  - keep `PATH` order as the documented preference, since that is the order a
    bare helper invocation would already have reached.

  Report a refusal as a named limitation. A rung that silently skips an
  untrusted candidate and reports plain `unavailable` reintroduces the exact
  failure this task exists to remove.

- R4: When no rung answers, the failure still names what was looked for and
  where — the current message's virtue — and now names every rung tried, not
  just the first. Absence stays reported, never guessed around.

- R5: **The report names which root supplied the engine.** The plugin cache root
  is version-qualified (`.../sd/<version>/`) and can differ from the machine
  install being reported on — which is the whole point of the row, since #496
  hid a 0.71.26-against-0.71.22 skew. An engine loaded from one version
  describing an install of another is defensible only when the reader can see
  that happened.

- R6: The engine's helper-library loading contract in the docstring (first
  import of `sd_ai_command_pack_lib` wins, deliberately) is unchanged; update
  the docstring's arrangement list to include the machine install.

## Acceptance Criteria

- [ ] A fixture reproducing the machine-install arrangement (collector at
      `<root>/bin/`, no sibling `installer/`, a trusted pack root reachable on
      `PATH`) resolves the engine. This test fails on current `main`.
- [ ] A pack-checkout fixture and a plugin-root fixture resolve through the
      first rung, proven by asserting the resolved path, not just success. A
      ladder that silently answered from a later rung would pass a
      success-only assertion while changing which copy is loaded.
- [ ] A fixture with no resolvable rung anywhere still raises, and the message
      names each candidate tried, not just the first.
- [ ] R3 security boundary, each proven by its own fixture:
      - a `PATH` directory holding `installer/machinescope.py` but not
        resembling a pack install is not imported;
      - a world-writable candidate root is refused, and the refusal is
        reported as a named limitation rather than a silent skip that
        degrades to plain `unavailable`;
      - candidates are tried in `PATH` order.
- [ ] R5: the rendered row names the root the engine was loaded from, and a
      fixture where that root's version differs from the reported machine
      install shows both values rather than silently reconciling them.
- [ ] `sd-status` on a thin consumer renders the machine-scope row, including
      the skew case that issue #496 reports as hidden.
- [ ] Changelog + version; fleet rollout via normal refresh.

## Notes

- **Reclassified 2026-08-25 during planning review: no longer lightweight.**
  It was filed as "one resolver ladder plus its regression tests", on the
  reading that the precedent settled the direction and R1 made the change
  strictly additive. Both halves of that reading survive; the conclusion does
  not. Widening the ladder to a `PATH`-derived root changes *what authorizes
  the import*, not just where it looks — a security boundary that did not
  exist when the engine could only come from the tree holding the script. A
  task that adds a code-execution surface needs `design.md` to state the trust
  rule and `implement.md` to order the work, so this is a complex task.
- Related and already resolved: #497 was filed alongside #496 and withdrawn;
  that half shipped in 0.71.27. This half did not.
