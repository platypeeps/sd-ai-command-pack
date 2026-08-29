# Implementation plan: sd-status worktree inventory

Ordered checklist. A step's named check failing blocks the next step.
Edit direction throughout: `templates/scripts/` and `templates/` skill
sources first (AGENTS.md source-of-truth rule), root installed mirrors
synchronized after.

1. **Collector implementation** in
   `templates/scripts/sd-ai-command-pack-status.py`: add
   `parse_worktree_porcelain(text)` (pure, `-z` NUL-record parsing) and
   `collect_worktrees(repo)` plus the `git.worktrees` /
   `git.branchesHeldElsewhere` wiring per `design.md` (porcelain `-z`
   enumeration, current-row resolution via resolved
   `--git-common-dir`/`--show-toplevel` comparison, identity-checked
   `--no-optional-locks` cleanliness probes, safe_text bounding,
   unavailable shape, porcelain row order preserved). Check:
   `python -m py_compile` passes and a manual `--json` run on this
   repository shows the new keys with `status: ok`.
2. **Human output** in the same file: `==> Worktrees` section (porcelain
   order with `(reporting)` marker; explicit empty and unavailable
   lines; bounded rows with `; +N more`) and the ` [worktree]` suffix in
   the local-branches line. Check: manual run here shows the section; a
   scratch repo with no linked worktrees shows `linked worktrees: none`.
3. **Mirror + docs surfaces.** Sync the root `scripts/` twin
   byte-identically (`cmp` exits 0). Update
   `templates/.agents/skills/sd-status/SKILL.md` step-4 report list
   (worktree inventory + held-branch marking), then `make generate &&
   make sync` for command surfaces and installed mirrors. Check: `cmp`
   on the script pair; the shipped-surface closure reports clean.
4. **Tests.** Add the eleven tests from `design.md` to
   `tests/test_status.py` (including the external checkout oracle for
   held branches, the linked-worktree `--repo` invocation, the
   adversarial `-z` parser cases with the long-path integration half,
   the stale-path-reuse guard, the sentinel-receipt read-only
   assertion, and the index-byte comparison). Check, per the design's
   baseline classification, against the pre-change collector
   materialized from
   `git show HEAD:templates/scripts/sd-ai-command-pack-status.py` into a
   temp copy (never stash or revert the working tree): behavioral tests
   1, 2, 3, 6, 7, 8, 9, 10, 11 fail on the baseline and pass on the new
   code; regression invariants 4 and 5 pass on both.
5. **Spec update.** `.trellis/spec/backend/manifest-and-filesystem.md`,
   "Read-Only Status And Housekeeping Delegation": add the
   worktree-inventory sentence and correct the stale "schema version 1"
   claim to 2. Check: grep of that section shows no "schema version 1"
   remnant.
6. **Release preparation.** Bump both manifests to 0.64.32, add the
   changelog entry, then `make release-prep` (canonical wrapper:
   generate, self-sync, fleet evidence refresh when stale, full
   maintainer `make check` gate — CONTRIBUTING.md). Expect the candidate
   ledger to refresh for the new payload digest. Check:
   `make release-prep` exit 0.
7. **Publish** via `sd-create-pr` (feature branch off main, preflight
   gate, Tooling/generated scope section in the PR body, Copilot review
   convergence, CI green). Merge on user instruction.
8. **Finish flow** — journal session with Testing section and Git
   Commits table; archive in its own completion-bundle push; any
   follow-up filings in a separate push. Then return to
   `08-07-status-housekeeping-anomaly-disagreement` (T-1), whose
   worktree-held axis this task unblocks, and fix its PRD's stale
   "(merged)" dependency claim.

Rollback: steps 1–4 are one revertable commit; the release bump is a
second commit in the same PR (PR #392 precedent). All new surface area
is additive, so reverting both commits restores the current report
exactly.
