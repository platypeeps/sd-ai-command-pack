# Regenerate the frozen source-only fleet-refresh adapters

## Goal

Make the only runnable fleet-refresh surface carry the current checkout-trust gate and the current pipeline description, instead of a body frozen at the 0.20.0 era.

## Requirements

- `.github/scripts/generate-command-surfaces.py:568` must emit source-only command adapters into the dev tree, not only under `templates/`.
- The four frozen source-only adapter paths must be added to the surface-drift gate so divergence fails CI.
- `.claude/commands/sd/fleet-refresh.md` must carry the same checkout-trust policy block as `templates/.claude/commands/sd/fleet-refresh.md:7`.
- Do not change `SOURCE_ONLY_COMMAND_NAMES` semantics (`installer/registry.py:1176`) — source-only targets must still be excluded from consumer installs.

## Acceptance Criteria

- [ ] `.claude/commands/sd/fleet-refresh.md` and its template twin agree on the checkout-trust block.
- [ ] Hand-editing one of the four adapters out of sync fails `make check`.
- [ ] `make check` passes.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-044 (P1 · S · Verified · architecture).
- `.agents/skills/sd-fleet-refresh/SKILL.md` has zero `checkout-trust` hits — the gate lives only in the adapter, which is why the frozen adapter is the whole exposure.
- `installer/removal.py:272` skips source-only targets in source checkouts, so `install.py` neither refreshes nor prunes them.
- `tests/test_pack_drift.py:144` iterates `load_manifest()`, which excludes source-only targets — that is why the twin-parity gate never caught this.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision.
- Complex task. Planning complete 2026-07-28: `design.md` and `implement.md` added.
