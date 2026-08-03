# Implement: add Claude to sd-skill fanout (full parity, guard dropped)

Parity-only (owner option 3): guard-embed evaluated and dropped. One PR.

## Preconditions

- Clean tree; `make check` green at baseline (record commit + timing).
- Change is `installer/registry.py:456` (`SKILL_FANOUT_PLATFORMS` += `"claude"`)
  + regen + pinned-test/gate updates. No skill-body edits, no new generator code.
- Expected new outputs: 21 non-source-only sd skills → `.claude/skills/sd-<n>/
  SKILL.md` + `references/*`, each with a `manifest.json` row. `sd-fleet-refresh`
  excluded (SOURCE_ONLY).
- **Concern ledger** (`review-ledger.md`) C-1..C-5 folded below. Key mechanics
  from round 1:
  - **C-1 order:** `make generate` writes manifest/templates AND runs surface-check
    inline; the root `.claude/skills/*` mirrors land only via `make sync`. So
    generate's inline check fails until sync runs. Correct order: generator →
    `make sync` → checks.
  - **C-2 footprint:** `command_installed_targets` iterates `SKILL_FANOUT_PLATFORMS`
    (`registry.py:1211`) for EVERY footprint incl. retired + source-only
    fleet-refresh (`registry.py:1289`). Adding claude grows each pinned footprint
    +1 and breaks fixed counts. fleet-refresh's footprint is already fully phantom
    (source-only ships none), so this only extends existing behavior.

## Steps

0. **Baseline.** `git status` clean; `make check` → exit 0 (record). Capture
   `grep -c '"target": ".claude/skills/sd-' manifest.json` → expect **0** (pre).
   Capture `.qoder`/`.kiro` sd-skill file counts as the parity reference for AC4.

1. **Edit the tuple.** Add `"claude"` to `SKILL_FANOUT_PLATFORMS`
   (`installer/registry.py:456`). Keep the tuple's existing byte-order convention
   (it is alphabetical today: insert `"claude"` between `"antigravity"` and
   `"codebuddy"` — verify no ordering gate depends on a different position).

2. **Update pinned footprint counts FIRST (C-2).** Before any check runs, fix the
   fixed-count assertions that `command_installed_targets` growth breaks —
   otherwise generate/sync-time and suite checks fail on stale numbers:
   - `tests/test_retired_targets.py:78-82` — each of `RETIRED_REVIEW_LOCAL_ALL_TARGETS`,
     `SOURCE_ONLY_COMMAND_TARGETS`, `RETIRED_WORK_DESIGNS_TARGETS`,
     `RETIRED_WATCH_PR_TARGETS`: `25` → `26`; `RETIRED_TARGETS`: `100` → `104`.
     (Confirm the uniqueness assertion still holds — the added claude paths are
     distinct.)
   - `tests/test_help_command.py:139` — `command_installed_targets("sd-one","one")`
     `25` → `26`.
   - `tests/test_install_audit.py:95` + `SOURCE_ONLY_ALLOWED_PACK_FILES`
     (`install-audit.py:85-110`) — reconcile the pinned equality (C-14). The 10
     existing fanout phantom fleet-refresh skill paths (e.g.
     `.kiro/skills/sd-fleet-refresh/SKILL.md`) are **already INCLUDED** in that
     allow-set; adding claude to fanout adds `.claude/skills/sd-fleet-refresh/
     SKILL.md` to fleet-refresh's footprint, so it must be **ADDED to
     `SOURCE_ONLY_ALLOWED_PACK_FILES`** exactly like the other 10 (NOT excluded —
     round-1's "exclude" note was backwards). Update the `test_install_audit.py:95`
     expected set to match. No fleet-refresh skill is actually shipped (source-only,
     no manifest row) — this is purely footprint bookkeeping.

3. **Regenerate + sync in the correct order (C-1).** `make generate` runs
   surface-check inline and will FAIL until mirrors exist, so:
   - run the generator script directly first
     (`python .github/scripts/generate-command-surfaces.py`) → updates
     `manifest.json` with `.claude/skills/sd-<n>/SKILL.md` (+ refs) rows for the 21
     non-source-only skills;
   - `make sync` (`install.py . --force`) → materializes `.claude/skills/sd-*`
     files into this repo;
   - THEN `make generate` (full, incl. inline surface-check) → now green;
     idempotent second run is a no-op.
   Assert after sync:
   - `grep -c '"target": ".claude/skills/sd-' manifest.json` > 0; **no**
     `.claude/skills/sd-fleet-refresh` row (AC3);
   - `.claude/skills/sd-*` files present for 21 skills + refs; `sd-fleet-refresh`
     absent; each byte-identical to `templates/.agents/skills/sd-<n>/…`
     (`diff -q` loop, AC1); `.claude/skills/trellis-*` untouched;
   - Claude's existing `.claude/commands/sd/*.md` rows untouched (diff = additions
     only, no command deletions).

4. **Auto-deriving gates (verify green, NO edit).** Confirmed during planning
   these derive from `SKILL_FANOUT_PLATFORMS` and self-adjust when claude is
   added — run them, do not edit:
   - `.github/scripts/check-command-surface-drift.py` — `SKILL_PUBLIC_ROOTS`
     (`:58`) is built from `SKILL_FANOUT_PLATFORMS`, so `.claude` auto-joins the
     public roots. `PUBLIC_PATH_PATTERNS` (`:98`) target `(sd-[a-z0-9-]+)`
     explicitly, so `.claude/skills/trellis-*` is NOT falsely flagged.
     `generated_registry_mismatch` stays green (`sd-fleet-refresh` still the only
     SOURCE_ONLY command). Expect clean.
   - `tests/test_surface_generation.py:595-603` and
     `tests/test_help_command.py:700-732` build `expected_targets` by iterating
     `SKILL_FANOUT_PLATFORMS` → auto-adjust. Authority-skill assertion (`:496`)
     unaffected.
   - `tests/test_generated_parity.py` (C-12): it verifies manifest sources exist +
     targets unique + skill frontmatter/substrings — NOT exact skill-body bytes.
     So byte-parity of `.claude/skills/sd-*` is NOT auto-covered; rely on the
     explicit `diff -q` in V1. (Optional: add an exact-byte twin test.)
   - `scripts/sd-ai-command-pack-surface-check.py` closure: new nodes arrive as
     manifest-backed `installable` with `mirrors` edges to sources — expect no
     orphan/missing. If closure fails, diagnose before proceeding (do not force).
   - `test_generated_parity.py:238` (`assert_paths_are_files`) is assertIn-style
     (not exact-set) → safe. BUT `assert_installed_targets_snapshot_matches_selection`
     may be a snapshot fixture — if it pins an installed-target set including
     Claude, regenerate/verify the snapshot after sync. Run the full parity module
     to catch any snapshot break.

5. **Install-audit — BOTH twins + Claude rogue test (C-3, mandatory).**
   - Add `".claude/skills/sd-*/*"` to `PACK_FILE_PATTERNS` in **both**
     `scripts/sd-ai-command-pack-install-audit.py:38` AND the shipped twin
     `templates/scripts/sd-ai-command-pack-install-audit.py:38` (consumers run the
     twin). Every other platform's `skills/sd-*/*` is listed; Claude was missing.
   - Add a Claude-specific rogue-skill regression test mirroring the Qoder one
     (`test_install_audit.py:35`): plant an unrecorded `.claude/skills/sd-rogue/
     SKILL.md`, assert audit exits 1 and names it. The generic coverage test
     (`test_install_core.py:2113`) will NOT catch the omission (any `.claude/`
     pattern satisfies it), so the explicit Claude case is required.
   - `pr-body-scope.py:142` already lists `.claude/skills/sd-*` pack-owned — no
     change there. Run install-audit + touched tests → green.

6. **Consumer parity proof (AC4).** Fresh `install.py` into a temp consumer;
   assert `.claude/skills/sd-*` now materializes and its set matches the
   `.kiro`/`.qoder` sd-skill set (minus platform dir). This is the intended new
   behavior. Also regen fleet candidate ledger if cheap → clean.

7. **Resolver check (AC2, C-10 — NO execution).** After sync
   (fresh-session fallback for a,c):
   (a) `Skill("sd-help")` (read-only) resolves and can be invoked;
   (b) a side-effecting skill (`sd-ship`) is confirmed **resolvable by inspection
   only** — resolver lists it / `.claude/skills/sd-ship/SKILL.md` present with
   valid `name`+`description` frontmatter. **Do NOT invoke it** (invocation =
   commit/push/merge authority);
   (c) run a read-only `/sd:*` command and confirm it proceeds past its
   skill-resolution step.
   Every `.claude/skills/sd-*/SKILL.md` has `name`+`description` frontmatter
   (byte-identical to source).

8. **Version + CHANGELOG (AC5).** Bump version; CHANGELOG entry: "Claude Code now
   receives the sd skill set in `.claude/skills/` (full parity with the other
   fanout platforms); shipped to consumers." `make generate`/`make sync` to
   propagate the version stamp.

9. **`make check`** → exit 0 (AC5): parity, closure, audit, surface-drift,
   candidate ledger all green. `make generate` a second time is a no-op.

## Validation commands (summary)

- V1 twin parity: `diff -q` every `.claude/skills/sd-*` vs source → identical (AC1).
- V2 manifest rows present: `grep -c '"target": ".claude/skills/sd-' manifest.json` > 0; `sd-fleet-refresh` absent (AC3).
- V3 consumer install: temp-repo install → `.claude/skills/sd-*` present, set == `.kiro` sd set (AC4).
- V4 gates: `make check` exit 0 (AC5); `make generate` idempotent.
- V5 resolver: `Skill("sd-help")` resolves + invokes; `sd-ship` resolvable by
  inspection (NOT invoked); a read-only `/sd:*` run proceeds past resolution (AC2).

## Rollback

- Pre-commit: revert the one tuple edit + gate/test edits, `git checkout`
  regenerated `.claude/skills/sd-*` + `manifest.json`, `make generate` to restore.
- Post-commit: revert the single commit — removes the manifest rows, so consumers
  drop the skills on their next `make sync` (clean, no lingering tree).

## Commit

One commit: registry tuple + regenerated `.claude/skills/sd-*` + manifest +
gate/test updates + version bump + CHANGELOG. Consumer-visible surface change →
full version-bump + CHANGELOG + `make generate`/`make sync` discipline; `make
check` green before PR.
