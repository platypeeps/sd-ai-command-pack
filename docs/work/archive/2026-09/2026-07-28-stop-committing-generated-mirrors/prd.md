---
title: Stop committing generated installed mirrors
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-07-28
---
# Stop committing generated installed mirrors

## Goal

Remove the 2.0 MB of committed generated mirrors that duplicate their `templates/` sources, and retire the 173,615 bytes of drift machinery that exists only to prove the copies still match.

## Requirements

- Gitignore the installed mirrors and make `install.py --force` a CI step, so the parity suites become a "regeneration is clean" check rather than a byte-comparison of committed duplicates.
- At minimum (if the full change is too large), drop the duplicate `.sd-ai-command-pack/manifest.json` (163,553 bytes duplicated verbatim from `manifest.json`).
- Retire or collapse the machinery that becomes redundant: `tests/test_generated_parity.py` (94,825 bytes), `tests/test_pack_drift.py` (25,841 bytes), `scripts/sd-ai-command-pack-surface-check.py` (29,730 bytes), `.github/scripts/check-command-surface-drift.py` (23,219 bytes).
- Consumer installs must be unaffected: the mirrors must still exist in a consumer checkout after `install.py`.
- Coordinate with A-058 (orphan manifest targets) before dropping any manifest entry — an orphaned target is a hard consumer-audit failure.

## Acceptance Criteria

- [ ] `git ls-files` no longer lists the generated mirrors (or, for the reduced scope, no longer lists the duplicate manifest).
- [ ] A deliberately stale mirror is caught by the regeneration check in CI.
- [ ] A fresh `install.py` in a scratch consumer repo produces a working install.
- [ ] `make check` passes.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-086 (P2 · L · Plausible · bloat).
- 175 duplicate groups totalling 1.97 MB; the single largest is `review-preflight.mjs` at 156,959 bytes.
- `make sync` (Makefile:31) already regenerates the mirrors from the sources on demand, so the regeneration path exists.
- Largest single complexity win identified by the 2026-07-28 audit.
- **Blocking sequencing constraint, found 2026-07-28.** `07-28-regenerate-fleet-refresh-adapters` must land first. The four source-only fleet-refresh adapters live in the dev tree with **no manifest entry** (`generate-command-surfaces.py:881` excludes source-only commands; `installer/removal.py:272` skips them in source checkouts), so `install.py . --force` does not regenerate them. Gitignoring the mirror roots before that task lands deletes the only copy.
- **The mirrors are this repo's own dogfood install**, not inert duplicates. `.claude/`, `.agents/`, `.gemini/`, `.opencode/` are the live agent surface the repo uses on itself, so ignoring them turns a zero-step clone into a one-step clone whose failure mode is silent — an agent operating with no pack skills rather than an error. `design.md` carries the bootstrap options.
- **Machinery figure corrected 2026-07-28:** the originating audit said ~210 KB; the measured total is 173,615 bytes, which is the sum of the four modules listed in R3 (94,825 + 25,841 + 29,730 + 23,219). The Goal states the measured figure.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision. Planning complete 2026-07-28: `design.md` and `implement.md` added.
