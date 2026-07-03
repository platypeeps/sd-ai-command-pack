# Fix claude adapter drift: installer detection/receipt stability and sd:start delegation

## Goal

Stop the pack from corrupting its own installed state on consumer repos that
gitignore `.claude/`, and make the Claude command adapters work on Claude
Code as actually installed there.

## Problem

Two related defects (observed on rwbp-website 2026-07-01 and
anomaly-metric-creator 2026-07-02):

1. **Receipt/detection drift.** `install.py` detects the claude platform via
   `ACTIVE_TRELLIS_PLATFORM_MARKERS`, which are all paths under `.claude/`.
   In repos that gitignore `.claude/`, those markers exist only in checkouts
   where Trellis was initialized locally. A refresh run from a fresh
   checkout/worktree silently skips the claude platform and rewrites the
   git-tracked receipt (`.sd-ai-command-pack/installed-targets.txt`) without
   the claude entries — consumers lose their `/sd:*` Claude commands. The
   reverse also happens: a refresh from an initialized checkout commits a
   receipt promising gitignored files, and the install audit then hard-fails
   ("installed target is missing") in every other checkout, breaking the
   local full-check gate repo-wide.
2. **Claude command delegation.** `sd/start.md` requires resolving a
   `trellis-start` skill, which never exists on Claude Code (the Trellis
   SessionStart hook replaces it; no `trellis:start` command is installed),
   so `/sd:start` always ends in its step-2 blocker path. `sd/continue.md`
   and `sd/finish-work.md` require `trellis-continue`/`trellis-finish-work`,
   but Claude Code installs those as namespaced commands
   `trellis:continue`/`trellis:finish-work`, so a strict resolver reports a
   false blocker.

## Requirements

- R1: A pack refresh must never drop previously recorded receipt entries for
  a platform skipped by marker detection or by an explicit `--platform`
  filter. Preserved entries are visibly reported so the operator knows the
  files may be local-only in this checkout. Entries skipped because the
  platform anchor directory is absent keep today's drop behavior (anchor
  removal reads as intentional platform removal).
- R2: The install audit must distinguish real drift from local-only absence:
  a receipt target that is missing but gitignored in the target repo is a
  warning with a remediation hint, not an error. Missing targets that are
  not gitignored — or whose ignore status cannot be determined (no git) —
  remain errors. Warnings-only runs exit 0.
- R3: `/sd:start` on Claude Code runs the start workflow without requiring a
  `trellis-start` skill: derive the equivalent session context directly from
  `.trellis/scripts/get_context.py` and report the recommended next action,
  preserving the wrapper's safety rules (no agent-config modification,
  recursion guard, blocker reporting).
- R4: `/sd:continue` and `/sd:finish-work` Claude adapters accept the
  namespaced `trellis:continue`/`trellis:finish-work` resolutions as valid,
  unchanged otherwise.
- R5: Repo quality gates hold: template twins stay in sync with installed
  copies, tests cover all new branches (100% coverage gate), docs that
  describe installer/audit semantics are updated, manifest version bumped.

## Non-goals

- No `--prune` flow for intentionally dropping a platform's receipt entries
  (manual receipt edit remains the mechanism; note it in docs).
- No changes to detection markers or non-claude platform adapters.

## Acceptance Criteria

- [ ] A1 (R1): installing into a repo whose receipt lists claude targets but
      whose checkout lacks claude markers keeps those receipt lines and
      prints a preservation notice; same under a `--platform` filter that
      excludes claude. An absent anchor (e.g. no `.cursor/`) still drops
      cursor entries.
- [ ] A2 (R2): audit on a repo with a gitignored absent receipt target exits
      0 with a warning naming the target; a missing non-ignored target still
      exits 1; git-unavailable keeps the error behavior.
- [ ] A3 (R3/R4): the Claude `sd/start.md` template has no hard
      `trellis-start` resolution requirement and instructs the
      `get_context.py`-based flow; `sd/continue.md`/`sd/finish-work.md` name
      the `trellis:` command form as an accepted resolution; installed twins
      match templates (full-check twin gate passes).
- [ ] A4 (R5): full suite passes at 100% coverage; full-check passes;
      manifest version 0.5.9.

## Notes

- Execution detail lives in `design.md` and `implement.md`.
