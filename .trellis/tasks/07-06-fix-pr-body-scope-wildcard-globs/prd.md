# Fix wildcard-base /** pattern matching in PR-body scope checker

## Goal

Fix a verified HIGH defect in
`scripts/sd-ai-command-pack-pr-body-scope.py` (`_matches_pattern`,
lines 297-305): when a pattern ends in `/**`, the base is compared
literally with `==`/`startswith`, so any glob character in the base is
never expanded. Verified empirically:
`'.claude/skills/sd-*/**'` does NOT match
`.claude/skills/sd-review-pr/SKILL.md`, while wildcard-free bases
(`.sd-ai-command-pack/**`) work. Roughly 40 of the `DEFAULT_RULES`
"Tooling/generated scope" patterns use the `.PLATFORM/skills/{sd,trellis}-*/**`
idiom, so a PR that changes any platform skill directory with no scope
section in the body exits 0 — the checker's core purpose silently fails
for those categories. User-supplied config rules using the same idiom
are equally dead.

## Requirements

- R1: `_matches_pattern` expands globs in the base of `/**` patterns,
  e.g. via `fnmatch.fnmatchcase(path, base)` or
  `fnmatch.fnmatchcase(path, f"{base}/*")` (fnmatch `*` crosses `/`,
  so `base/*` covers arbitrary depth).
- R2: Wildcard-free `/**` bases keep their current semantics (base
  itself or anything under it matches).
- R3: Fix lands in both `scripts/` and `templates/scripts/` copies
  (byte-identical).
- R4: Add table-driven tests that exercise every `DEFAULT_RULES`
  pattern against at least one representative matching path and one
  non-matching path, so no rule can silently go dead again.

## Acceptance Criteria

- [ ] `'.claude/skills/sd-*/**'` matches `.claude/skills/sd-review-pr/SKILL.md`;
  a PR body without a scope section fails the check for such paths.
- [ ] Table-driven DEFAULT_RULES coverage test in place and green.
- [ ] Full battery green: unittest suite, 100% coverage on install.py,
  full-check, shellcheck; template twin byte-identical.

## Notes

- Origin: 2026-07-06 deep architectural/code review (Python H1,
  verified in-session).
