# Derive the fleet-publish allowlist from manifest.json

Follow-up recorded during the 0.71.5 fleet campaign
(`refresh-0.71.5-20260814T113545Z`).

## Goal

Stop `scripts/sd-ai-command-pack-fleet-publish.py` from carrying a
hand-maintained `DEFAULT_ALLOWED_PREFIXES` tuple that must silently agree
with `manifest.json`. The helper refuses to run when the consumer tree is
dirty outside that allowlist; today the list is a literal
(`fleet-publish.py:76`) naming platform directories and two special files.
When the installer payload gains a new platform directory or target path, the
tuple does not learn it, and every fleet lane on an affected consumer fails
the dirty-tree gate with a stale allowlist — an inventory-drift defect of
exactly the kind the verification guidance warns about (prefer enumerating at
runtime over reciting a list).

## Requirements

- Derive the installer-managed portion of the allowlist from the consumer's
  installed receipt/manifest evidence (`.sd-ai-command-pack/manifest.json`
  target paths, or the installed-targets receipt) at runtime.
- Keep the non-installer entries — `.trellis/`, `docs/repomix-map.md`,
  `.gitignore` (managed KB block) — as explicit, commented residue: they are
  owned by Trellis, the map generator, and housekeeping, not the installer.
- Fail closed when the receipt evidence is absent or unreadable: fall back is
  refusal with a named reason, never a silently widened or narrowed list.
- `--allow-path-prefix` keeps its current semantics.

## Non-goals

- Any change to the helper's commit/archive/journal/push sequence.
- Widening what the helper will commit; this changes only how the dirty-tree
  gate learns which paths are installer-managed.

## Acceptance Criteria

- [x] A payload target path present in the installed manifest but absent from
      the old literal tuple passes the dirty-tree gate without a code edit,
      proven by a test.
      `test_new_payload_target_passes_without_a_code_edit`.
- [x] A dirty path outside both the derived set and the explicit residue
      still refuses with the existing exit code and message shape.
      `test_path_outside_derived_set_and_residue_still_refuses`.
- [x] Missing/malformed receipt evidence refuses with a named reason code.
      The evidence file is `.sd-ai-command-pack/manifest.json`, not the
      installed-targets receipt — see design D1 for why the receipt is unsafe
      here. Four codes, one test each: `manifest_missing`,
      `manifest_unreadable`, `manifest_malformed`, `manifest_targets_empty`.
- [x] The remaining literal entries each carry an ownership comment.
      Both residue constants: `DEFAULT_ALLOWED_PREFIXES` (directories) and
      `DEFAULT_ALLOWED_EXACT` (files).
