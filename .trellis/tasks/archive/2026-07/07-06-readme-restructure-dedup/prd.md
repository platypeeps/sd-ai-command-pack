# Restructure README and remove docs duplication

## Goal

README.md is 42KB with lines 9-305 (all 11 command descriptions, the
exclusion list, Obsidian instructions) sitting under no heading at all;
the "Quick links" block lists only 4 of 7 H2 sections (missing
Configuration Quick Reference, Direct-to-main Chore Commits, and
Upstream Path). Separately, ~17% of README's substantive content is
byte-identical to `docs/SD_AI_COMMAND_PACK.md`, including the ~146-line
managed gitignore block (README 473-620 = docs 878-1023), the 29-line
review-exclusion list, the Obsidian vault copy commands, and the
PR-body scope example — and drift between the two has already started:
README:253-254 lists 3 architecture-overview candidates while
docs:463-465 lists 5; README's smoke test (394-401) omits the sandbox
cache-env exports docs:1069-1073 includes. The drift gate byte-compares
docs/ against templates/docs/ but nothing ties README to the guide, so
duplication decays silently.

## Requirements

- R1: Add a `## Commands` section with one `###` heading per command
  (mirroring the docs guide) so the 300-line preamble is navigable;
  complete the Quick-links TOC to cover all H2 sections.
- R2: De-duplicate: README keeps the marketing/install/verify surface
  and links to `docs/SD_AI_COMMAND_PACK.md` for per-command detail. At
  minimum, remove the duplicated managed-gitignore block and the
  review-exclusion list from README in favor of links.
- R3: Reconcile the two identified drifts (architecture-overview
  candidate list; smoke-test env exports) so the surviving copy is the
  complete one.
- R4: Verify no external references (skills, scripts, docs) deep-link
  to removed README anchors before deleting sections.

## Acceptance Criteria

- [x] Every README section reachable from the TOC; no unheaded
  content block over ~50 lines.
- [x] The gitignore block and exclusion list exist in exactly one
  documentation surface.
- [x] The two drifts resolved; content spot-check confirms no
  information was lost in the dedup.
- [x] Full battery green (pack source drift gates unaffected).

## Implementation Notes

- Added a `## Overview` heading plus a `## Commands` section with one `###`
  heading per installed command, and expanded the quick-links list to cover all
  README H2 sections in file order.
- Replaced the duplicated per-command detail, local-review exclusion list,
  managed gitignore/Copilot block examples, PR-body scope example, and Obsidian
  vault copy instructions with links to `docs/SD_AI_COMMAND_PACK.md`.
- Reconciled the documented drift by keeping the complete architecture overview
  candidate list in the installed guide and adding the sandbox cache environment
  exports to the README smoke test.
- Updated README regression coverage to assert the new command headings, guide
  link, smoke-test exports, and absence of managed-block markers in README.
- Validation: focused README/contributor tests, `git diff --check`, KB refresh,
  and SD full-check with Prism/Gito disabled passed.

## Notes

- Origin: 2026-07-06 deep review (Docs findings 2 and 3, MEDIUM).
  Coordinate with 07-06-docs-accuracy-fixes to avoid churn on the
  same files; land accuracy fixes first.
