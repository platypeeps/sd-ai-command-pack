# Robustness fixes for housekeeping, recorder, learnings, and KB scripts

## Goal

Bundle of MEDIUM/LOW robustness defects across four shipped helpers
from the 2026-07-06 deep review. Theme: guards that fail open or
degrade silently.

Housekeeping (`scripts/sd-ai-command-pack-housekeeping.sh`):
1. **`working_tree_is_clean` treats a failing `git status` as clean**
   (:158-164): command-substitution failure inside `[ -z "$(...)" ]`
   doesn't trip `set -e`, so index.lock contention or an FS error
   reads as "clean" and the dirty-tree guards before auto-merge /
   branch-switch (lines 522, 631) pass. Fail closed:
   `out="$(git status --porcelain)" || return 1`.
2. **`--remote` not hardened** (:133-138, 249): `-`-prefixed remotes
   parse as git options; `${symbolic#${REMOTE}/}` treats glob chars as
   a pattern (shellcheck SC2295 — the one real shellcheck hit in the
   repo). Reject `-*` remotes in parse_args; quote the expansion.
3. **`detect_default_branch` can set `DEFAULT_BRANCH="null"`**
   (:255-262): `gh repo view --jq .defaultBranchRef.name` prints
   literal `null` with exit 0 on empty repos, skipping the
   main/master fallback.

Recorder (`scripts/sd-ai-command-pack-record-session.py`):
4. **`modified_workspace_journals` ignores git failure and mis-parses
   rename/quoted status lines** (:80-87): returncode never checked
   (failure → misleading "found: none"); `line[3:]` breaks for
   `R old -> new` and core.quotePath-quoted paths.

Review-learnings (`scripts/sd-ai-command-pack-review-learnings.py`):
5. **Raw `AttributeError` traceback on non-object `gh api graphql`
   JSON** (:643, 846-854): `_run_gh_json` can return None/list;
   `payload.get("data")` then raises outside main's caught tuple.
6. **Managed-marker injection** (:104-106, 687-719): a Copilot comment
   body containing the literal end-marker (≤220 chars survives
   `_one_line`) becomes an early END marker; next update splices at
   the embedded marker. Escape/strip marker substrings from rendered
   bodies.
7. **Silent no-op scan when no base ref discoverable** (:455-474,
   511-518): prints `[sd-review-learnings:OK] no ... findings` after
   scanning nothing. Print an explicit "no base ref found; nothing
   scanned" notice.

Update-spec-kb (`scripts/sd-ai-command-pack-update-spec-kb.py`):
8. **`refresh()` exits 0 while printing `conflicts:`** (:1376-1411):
   `--check` returns 1 on conflicts but write mode returns 0, so
   automation reads stale-KB states as success. Return non-zero (or a
   distinct documented code) when conflicts are non-empty; update the
   sd-update-spec skill wiring if it checks exit codes.

## Requirements

- R1-R8: fix each item with a regression test in the existing
  subprocess-test style (stub `gh`, real temp repos).
- R9: fixes land in both `scripts/` and `templates/scripts/`.
- R10: exit-code/message changes documented in
  `docs/SD_AI_COMMAND_PACK.md` where user-visible (KB conflicts code).

## Acceptance Criteria

- [ ] Each of the eight scenarios has a test demonstrating the fixed
  behavior (fail-closed, hardened, or explicit-notice as applicable).
- [ ] Full battery green; template twins byte-identical.

## Notes

- Origin: 2026-07-06 deep review (Shell M2/L2/L3; Python M4/M7 and
  record-session/learnings LOW items). Split into sub-tasks if any
  single item balloons.
- Upstream: two drafted Trellis issues in
  `07-07-file-upstream-trellis-issues` reduce this task's long-term
  surface — issue 1 (structured add_session content) shrinks the
  recorder wrapper, and issue 2 (`--json` output) removes the
  sentinel-grep that item 8's neighbor code relies on. Fix pack-side
  regardless; revisit when the issues land.
