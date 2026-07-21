# Remove unused normalize_pr field parameter

## Goal

Remove the misleading unused `normalize_pr` field parameter from the canonical and generated status scripts while preserving terminal reconciliation validation behavior and preparing the next patch release.

## Requirements

- Remove the unused `field` parameter from the nested `normalize_pr` helper in both `scripts/sd-ai-command-pack-status.py` and its template twin.
- Update both call sites to pass only the pull-request evidence value.
- Preserve all validation behavior and diagnostics, including the distinction between `terminalReconciliation` and `terminalReconciliation.status`.
- Keep canonical/template source byte-identical and retain focused status regression coverage.
- Bump the shipped payload to `0.25.3`, update the changelog and generated command catalog, and refresh release-candidate evidence required by the pack gate.
- Run focused status tests, generated parity checks, the complete unit suite, and the canonical full check before publishing the branch.

## Acceptance Criteria

- [x] Neither canonical nor template status script declares or passes the unused `normalize_pr` field parameter.
- [x] Status validation behavior and focused terminal-reconciliation regressions remain green.
- [x] Canonical/template parity and installer provenance checks pass.
- [x] Manifest, dogfood manifest, changelog, and command catalog consistently report `0.25.3`.
- [x] Release-candidate ledger and repository gates pass.
- [x] The focused upstream change is committed, pushed, and published as a PR targeting `main`.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
- Merging, tagging the release, and refreshing downstream consumers require the later merge/release lifecycle and are outside this implementation turn unless separately authorized.
- Verification: 61 focused status/parity tests and all 794 unit tests pass; the canonical candidate validator passed all seven configured consumers; `scripts/sd-ai-command-pack-full-check.sh` passes.
- The complete suite exposed a pre-existing review-local fixture defect: it supplied a nonexistent `TMPDIR` and inherited UV/XDG overrides while asserting fallback paths. The fixture now creates its temp root and clears those overrides; production review behavior is unchanged.
- Update-spec decision: no code-spec or architecture update is warranted because this internal helper cleanup changes no executable contract, and the existing status and release specs already cover the preserved behavior. The generated Obsidian knowledge base was refreshed with no conflicts.
