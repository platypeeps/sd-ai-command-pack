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
- R2: The added rung(s) locate a root that actually carries `installer/`. Reuse
  the resolution order already documented in
  `templates/.agents/skills/sd-help/references/pack-helper-resolution.md` and
  mirrored by `collect_toolchain_resolution()` (`:1953-1962`) rather than
  inventing a second, divergent ladder. A symlinked plugin root reached through
  `~/.agents/bin` is one install wearing two paths (`real_path()`, `:1888`).
- R3: When no rung answers, the failure still names what was looked for and
  where — the current message's virtue — and now names every rung tried, not
  just the first. Absence stays reported, never guessed around.
- R4: The engine's helper-library loading contract in the docstring (first
  import of `sd_ai_command_pack_lib` wins, deliberately) is unchanged; update
  the docstring's arrangement list to include the machine install.

## Acceptance Criteria

- [ ] A fixture reproducing the machine-install arrangement (collector at
      `<root>/bin/`, no sibling `installer/`, a resolvable plugin root
      elsewhere) resolves the engine. This test fails on current `main`.
- [ ] A pack-checkout fixture and a plugin-root fixture resolve through the
      first rung, proven by asserting the resolved path, not just success.
- [ ] A fixture with no resolvable rung anywhere still raises, and the message
      names each candidate tried.
- [ ] `sd-status` on a thin consumer renders the machine-scope row, including
      the skew case that issue #496 reports as hidden.
- [ ] Changelog + version; fleet rollout via normal refresh.

## Notes

- Lightweight: one resolver ladder plus its regression tests. No contract,
  data-flow, or compatibility decision is open — the precedent above settles the
  direction, and R1 makes the change strictly additive.
- Related and already resolved: #497 was filed alongside #496 and withdrawn;
  that half shipped in 0.71.27. This half did not.
