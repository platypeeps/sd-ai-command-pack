# Introduce a single platform registry for per-platform metadata

## Goal

Resolve a HIGH missing-abstraction finding: adding one platform today
requires coordinated edits to at least eight parallel tables —
`PLATFORMS` (install.py:21-40), `ACTIVE_TRELLIS_PLATFORM_MARKERS`
(43-124), `TRELLIS_INIT_PLATFORM_FLAGS` (427-444),
`PLATFORM_LOCAL_GITIGNORE_PATTERNS` (168-281, ~110 hand-repeated
lines), `LOCAL_ONLY_TRELLIS_EXCLUDES` (290-358),
`LOCAL_ONLY_TRACKED_CHECK_PATHS` (359-426), manifest entries, the
README adapter table, and three shipped scripts. Drift has already
happened: `scripts/sd-ai-command-pack-install-audit.py`
`PACK_FILE_PATTERNS` (:30-43) and `REFERENCE_SCAN_BASES` (:82-97)
cover only the original six platforms
(`.agents`, `.claude`, `.cursor`, `.gemini`, `.github`,
`.opencode`) — `.qoder`,
`.codebuddy`, `.factory`, `.trae`, `.devin`, `.kilocode`, `.pi`,
`.kiro`, `.reasonix`, `.zcode`, `.agent` appear nowhere — so the
audit's "pack-like file not recorded in receipt" and legacy-reference
scans are silently blind on 10 of 16 platforms. Same for
`scripts/sd-ai-command-pack-review-scope.sh:128-146`
(`is_trellis_runtime_path`). Meanwhile
`sd-ai-command-pack-pr-body-scope.py:66-110` WAS updated for all 16 —
proof the tables evolve independently.

## Requirements

- R1: Define one platform registry (recommended: a `platforms` section
  in `manifest.json`: `{id, dir, markers, initFlag, adapterGlobs}`)
  and derive install.py's per-platform tables from it.
- R2: Update `install-audit.py` `PACK_FILE_PATTERNS` /
  `REFERENCE_SCAN_BASES` and `review-scope.sh`
  `is_trellis_runtime_path` to cover all 16 platforms. Since shipped
  scripts must stay standalone, either generate their tables from the
  registry at pack-build time or keep tested static copies.
- R3: Add a cross-table consistency unit test: every platform dir in
  `PLATFORM_LOCAL_GITIGNORE_PATTERNS` / `ACTIVE_TRELLIS_PLATFORM_MARKERS`
  must be matchable by the audit's patterns and by review-scope's
  runtime-path classifier. This test is the durable guard even if R1
  is descoped.
- R4: While in the area, address the identifier oddities from the same
  review: `--platform codex` is accepted but installs nothing
  platform-specific while `trellis_init_command` hardcodes `--codex`
  (print an explanatory note or remove/document); zcode's marker set
  includes a Codex-install artifact (`.agents/skills/trellis-before-dev/SKILL.md`)
  so any repo with `.zcode/` plus a Codex Trellis install auto-installs
  zcode adapters — give zcode a zcode-owned marker. Refresh the stale
  platform list in `.trellis/spec/backend/directory-structure.md:55-56`.
- R5: Make marker-miss detection observable: when a platform's anchor
  directory exists but no Trellis marker for that platform matches,
  the installer prints a hint (e.g. "`.qoder/` present but no active
  Trellis qoder install detected; pass `--platform qoder` or update
  Trellis") instead of skipping silently. This is the adopted scope of
  the Trellis-coupling follow-up: a declared Trellis version-range
  contract was considered and explicitly deferred (2026-07-06 session
  decision) until a real version incompatibility motivates it.

## Acceptance Criteria

- [ ] One source of truth for platform metadata; per-platform tables
  derived or consistency-tested against it.
- [ ] Audit and review-scope recognize pack files on all 16 platforms
  (fixture test per platform dir).
- [ ] codex/zcode identifier quirks resolved and spec platform list
  current.
- [ ] Full battery green; template twins byte-identical.

## Notes

- Origin: 2026-07-06 deep review (Architecture finding 2 HIGH +
  finding 8 LOW). Registry work also unlocks shrinking install.py
  (~21% of it is per-platform constant tables).
- Related: `07-06-installer-module-decomposition` (merged via PR #45)
  splits install.py into modules. Sequence or coordinate these: the
  registry extraction removes ~450 lines of constant tables and should
  inform the decomposition's module boundaries.
