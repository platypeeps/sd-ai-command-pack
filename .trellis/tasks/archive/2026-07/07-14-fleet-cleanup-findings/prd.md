# Resolve lower-priority fleet cleanup findings

## Goal

Remove duplicate managed Claude ignore rules, suppress generated Repomix legacy-reference noise, and clear the coordinator review-churn stale filename assertion.

## Requirements

- Update the installer-managed `.gitignore` migration so the exact legacy
  four-line Claude adapter ignore sequence is removed when it appears before
  the managed block.
- Preserve user-authored ignore rules outside the managed block, including
  later rules whose order may intentionally override managed patterns.
- Exclude generated `docs/repomix-map.md` files from legacy pack-reference
  content scans while retaining scans of the source documentation included in
  those maps.
- Keep root and template copies of shipped audit scripts byte-identical.
- Remove the stale `TRELLIS_REVIEW_PR_PACK.md` assertion from the coordinator's
  repo-owned review-churn check.
- Clean the duplicate legacy Claude sequence from all current fleet
  `.gitignore` files without disturbing unrelated local work.

## Acceptance Criteria

- [x] Installer tests cover migration with and without an existing managed
  block, preservation of later overrides, and idempotence.
- [x] Install-audit tests cover generated Repomix-map exclusion while still
  warning on legacy references in ordinary documentation.
- [x] Root/template parity passes for shipped scripts.
- [x] All six fleet repositories contain only the managed copy of the Claude
  adapter ignore sequence.
- [x] Loadsmith's install audit no longer emits generated Repomix-map legacy
  warnings.
- [x] Coordinator's review-churn check and install audit pass without the stale
  repo-owned legacy-filename reference.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
