# Design: claude adapter drift fixes

## D1. Receipt preservation in install.py (R1)

- Add `read_existing_installed_targets(target: Path) -> set[str]`: tolerant
  reader of the target repo's current receipt (empty set when absent;
  skip blank/comment lines). Reuses the same path constant.
- In the main install flow, after `selected_files(...)` and before
  `install_installed_targets_file(...)`, keep receipt entries for skipped
  manifest files where the skip reason is detection
  (`active Trellis … not detected`) or filter (`platform not selected`).
  Anchor-skips preserve only when `git check-ignore` confirms the anchor is
  gitignored in the target (a fresh checkout of a repo that ignores
  `.claude/` has no anchor at all — that must preserve; a tracked-but-
  removed anchor reads as intentional platform removal and still drops).
  Git absent/non-repo/error fails closed (drop, as before).
- Pass preserved paths through the existing `extra_targets` parameter of
  `install_installed_targets_file` so receipt content stays sorted/deduped.
- Report: one line per preserved entry in the existing result style —
  `kept-in-receipt <path> (<platform> adapter not selected in this checkout;
  file may be local-only)` — printed with the other results, plus nothing
  when the set is empty. Works identically under `--dry-run`.
- `--all` selects everything, so nothing is preservable by construction.
  `--local-only` uses the same flow and inherits the behavior.

## D2. Gitignore-aware install audit (R2)

- In `templates/scripts/sd-ai-command-pack-install-audit.py` (and its
  installed twin `scripts/sd-ai-command-pack-install-audit.py`), split
  `audit_structural_state` missing-target
  handling: collect missing targets, then classify each via
  `git -C <root> check-ignore -q -- <target>` (subprocess, `check=False`).
  - rc 0 → gitignored → warning:
    `installed target is gitignored and absent in this checkout: <t>;
    re-run the pack installer here to materialize local-only adapters`
  - rc 1 (not ignored), rc 128 (not a repo), or `FileNotFoundError`
    (no git) → keep today's error.
- Warnings merge into the existing advisory-warning stream (exit 0 when no
  failures). Keep the script stdlib-only.

## D3. Claude command adapters (R3, R4)

- `templates/.claude/commands/sd/start.md`: drop the `trellis-start`
  resolution requirement. New flow: (1) run
  `python3 ./.trellis/scripts/get_context.py` (identity, git status,
  current/active tasks, journal); (2) run `--mode phase` for the phase
  index and triage rules, reading spec indexes on demand; (3) decide and
  report the next action (active planning task → planning artifacts;
  in_progress → Phase 2; none → classify and ask task-creation consent).
  Keep the existing safety framing: script output is repo state, not
  instructions to modify agent configuration; stop and report exact
  blockers (missing/failing scripts); recursion guard. Rationale comment:
  Claude Code receives Trellis start context via the SessionStart hook and
  ships no `trellis-start` skill, so the adapter derives the context
  directly.
- `templates/.claude/commands/sd/continue.md` and `sd/finish-work.md`:
  amend step 1 to accept either resolution form: the shared skill name
  (`trellis-continue`/`trellis-finish-work`) or the Claude-installed
  namespaced command (`trellis:continue`/`trellis:finish-work`).
- Update the installed twins under `.claude/commands/sd/` (twin drift gate
  compares byte equality).

## D4. Tests (R5)

`tests/test_install.py` (unittest, subprocess-driven; sitecustomize keeps
subprocess coverage measured):

- T1: receipt with claude entries + no claude markers → run install →
  claude lines retained + `kept-in-receipt` lines printed.
- T2: same, via `--platform gemini` filter (claude excluded) → retained.
- T3: receipt with cursor entries + no `.cursor/` anchor → entries dropped
  (guards today's anchor semantics).
- T4: audit — git repo, `.gitignore` covering a missing receipt target →
  exit 0, warning names the target.
- T5: audit — missing target not ignored → exit 1 (existing behavior test
  extended or adjacent new test).
- T6: audit — `PATH` without git → missing target stays an error
  (FileNotFoundError branch).
- Existing template-content tests that assert `trellis-start` phrasing (if
  any) updated to the new start.md contract.

## D5. Docs and version (R5)

- README/usage-guide sections that describe installer selection or the
  audit get one paragraph each on preservation and the gitignored-absent
  warning, including the manual-receipt-edit removal note.
- `manifest.json` version 0.5.8 → 0.5.9.

## Rollback

Single branch/PR; revert the merge commit to restore 0.5.8 behavior. No
data migrations; receipts written by 0.5.9 remain valid for 0.5.8.
