# Implementation plan

## Phase A — surface generation
- [ ] A1. Add COMMAND_NAMES (name, short) tuple to installer/registry.py;
  include every current sd-* command.
- [ ] A2. Write .github/scripts/generate-command-surfaces.py: adapters
  (claude/gemini/github) from neutral bodies with override list; manifest
  from static base + derived command entries; --check mode.
- [ ] A3. Move CLAUDE_COMMAND_ALIAS_REWRITES data into generator config;
  parity test reads or mirrors it.
- [ ] A4. Makefile `generate` target; tests/test_surface_generation.py
  drift test (--check clean on committed tree).
- [ ] A5. Run generator; verify adapters byte-identical to current
  (except intended normalizations = none) and manifest semantically equal
  (same entry set) with canonical order; commit regenerated manifest.
- [ ] Gate: make test green before Phase B.

## Phase B — review-local merge
- [ ] B1. Merge -all content into sd-review-local SKILL.md with `all` arg.
- [ ] B2. Delete sd-review-local-all skill + neutral + generated adapters;
  drop from COMMAND_NAMES; regenerate.
- [ ] B3. Wire removed installed targets into installer/removal.py legacy
  removal (investigate mechanism; add targets + test).
- [ ] B4. Docs merge (guide/README/lists); test-pin updates (parity/core
  -all lines out, `all` pins in).

## Phase C — sd-ship
- [ ] C1. Skill + neutral per design contract; add to COMMAND_NAMES;
  regenerate surfaces.
- [ ] C2. Format-drift pins (stop-points, gate-deference, stage table) in
  tests/test_sdlc_commands.py (extend COMMANDS map).
- [ ] C3. Docs (guide bullets/lists/prose; README section + heading pin).

## Ship
- [ ] install.py --force fan-out; KB regen; bump 0.13.0 + CHANGELOG (all
  three deliverables + the -all removal notice).
- [ ] make test; make full-check; commit; PR; Copilot; watch; gated merge;
  v0.13.0; journal; archive parent+children.
- [ ] Annotate ledger A-034 (tracked → surface-generation task); note the
  trigger-firing on parked platform-registry-manifest-sections task.
