# Require a generated marker before pruning KB category files

## Goal

The KB refresh prune deletes any regular file sitting under one of the 13 managed
category folders, without checking that the pack generated it. Because the KB
root is allowed — by design — to be a symlink into a directory outside the
repository, that unmarked delete can reach an operator's own files. Make the
prune prove ownership before unlinking, the way its own sibling branches already
do.

## Origin

Created 2026-07-28 from the repo audit with explicit user consent. Owns the
**narrowed residual** of finding A-070 (P2 · S · Plausible · security).

The finding as filed is largely rebutted — see Notes. What survives verification
is one missing marker check, and it is a data-loss footgun rather than the
sandbox escape the finding describes.

## Evidence

`scripts/sd-ai-command-pack-update-spec-kb.py:239` `is_stale_generated_kb_entry`
decides what the prune at `:748` may delete. It has three branches, and they do
not apply the same standard:

- `:246-247` legacy generated paths — **checks a marker**:
  `file_contains_marker(candidate, legacy_marker)`.
- `:248-255` symlinks — **checks ownership**: `is_tool_owned_symlink(candidate, root)`.
- `:256` everything else — `return candidate.is_file() and is_managed_kb_category_path(relative_candidate)`.
  **No marker, no ownership check.** Any regular file is deletable purely because
  of where it sits.

`is_managed_kb_category_path` (`:225-226`) tests only `path.parts[0] in KB_CATEGORY_TITLES`,
a frozenset of 13 human-readable titles built at `:905`: `Repository Overview`,
`Agent and Platform Guidance`, `Pack Documentation`, `Architecture and Decisions`,
`Workflow and Configuration`, `Task Documentation`, `Backend Specs`,
`Frontend Specs`, `Thinking Guides`, `Repository Maps`, `Project Manifests`,
`Package Documentation`, `Other Documentation`.

The prune loop at `:748` walks `kb_root.rglob("*")` and unlinks at `:753`
everything `is_stale_generated_kb_entry` approves that is not in `wanted` or
`generated`. So the failure case is concrete: an operator points `.obsidian-kb`
at a vault directory that already contains a top-level folder named, say,
`Architecture and Decisions` or `Other Documentation`, and the next refresh
deletes every file in it that the pack did not just write.

Nothing about that requires an attacker. It is a collision between two
distinctive-but-not-unique folder names.

## Requirements

- R1: the `:256` branch must prove pack ownership before approving a delete, on
  the same footing as `:247` and `:250`. A generated marker in the file content
  is the mechanism already used at `:247` (`file_contains_marker`) — prefer it
  over a naming convention so a hand-copied file is never mistaken for a
  generated one.

- R2 (constraint on R1): the refresh must still converge. Pack-generated files
  that are genuinely stale — written by an earlier version, then dropped from
  the source set — must still be pruned, or the KB accumulates orphans forever.
  Files written before this change carry no marker, so the change needs a
  migration path: either a one-time grace pass that adopts unmarked files under
  a pack-written manifest, or a documented manual cleanup. Decide which and
  record it; do not leave the upgrade case undefined.

- R3: the two markers the file already defines are dashboard/overview-scoped
  (`DASHBOARD_MARKER` `:43`, `OVERVIEW_MARKER` `:44`, dispatched at `:219-221`).
  Category-copied documents are plain copies of repository files and carry no
  marker today. Adding one means either writing a marker into every copied
  document — which changes the bytes an operator reads in their vault — or
  tracking ownership out of band in a pack-owned manifest. Weigh both in
  `design.md`; the in-file marker is more robust, the sidecar manifest is less
  intrusive.

- R4: no new restriction on the root symlink. `ensure_kb_root` (`:267`) may keep
  returning a symlink that resolves outside the repository. That is documented
  behavior (`docs/SD_AI_COMMAND_PACK.md:1065-1071`) and asserted by
  `tests/test_update_spec_kb.py:138`. This task changes what the prune deletes,
  not where the KB may live.

- R5: template parity. `templates/scripts/sd-ai-command-pack-update-spec-kb.py`
  carries the same code; both copies change together and generated-parity checks
  stay green.

## Acceptance Criteria

- [ ] R1: a fixture KB whose root symlink targets a directory containing a
      pre-existing `Architecture and Decisions/notes.md` that the pack did not
      write survives a full refresh. This case deletes the file today.
- [ ] R1: a pack-written category document that is dropped from the source set
      is still pruned on the next refresh.
- [ ] R2: the upgrade path is exercised — a KB populated by the current version,
      then refreshed by the new one, ends in the same state a fresh KB would,
      with no orphans and no deletion of non-pack files.
- [ ] R4: the existing root-symlink tests and the documentation assertion at
      `tests/test_update_spec_kb.py:138` still pass unchanged.
- [ ] R5: `scripts/` and `templates/scripts/` copies are identical; `make sync`
      passes.
- [ ] `make check` passes.
- [ ] Changelog + version; fleet rollout via normal refresh.

## Notes

- Audit source: `.trellis/audit/report-2026-07-28.md` — A-070 (P2 · S ·
  Plausible · security).
- **A-070 headline rebutted, 2026-07-28.** The finding says `ensure_kb_root`
  follows a root symlink "with no containment check," treats that as an
  unguarded path escape, and proposes calling the file's own `is_within` helper
  on the KB root. Three facts rebut it:
  1. **It is documented, intended behavior.** `docs/SD_AI_COMMAND_PACK.md:1065-1071`:
     the root path "may itself be a symlink when it resolves to an existing
     directory, including a directory outside the repository. Refreshes preserve
     that root symlink and write through it." That is the feature — point the KB
     at an Obsidian vault.
  2. **A test asserts that documentation exists.**
     `tests/test_update_spec_kb.py:138`. The proposed containment check would
     fail the suite.
  3. **A hostile symlink cannot arrive through the repository.** `/.obsidian-kb`
     is gitignored (`.gitignore:172`, inside the pack-managed block at
     `:169-173`), so it cannot be committed, and a clone or PR cannot plant it.
     The operator must create it locally and deliberately.
- **The finding's supporting claim that `is_within` is unused is also false.**
  It has three callers — `update-spec-kb.py:615`, `:682`, `:1335` — all checking
  that symlinks *inside* the KB stay within root. The asymmetry the finding
  noticed is real (inner symlinks are contained, the root is not) but it is a
  deliberate policy, not an oversight.
- What survives is the unmarked delete at `:256`, which the finding did not
  mention. Reclassify: this is **P2 · correctness/data-loss**, not a security
  escape. No attacker is required and no privilege boundary is crossed; a
  plausible folder-name collision is enough.
- Complex task — R2 and R3 are genuine design decisions with a migration.
  Planning complete 2026-07-28: `design.md` and `implement.md` added.
