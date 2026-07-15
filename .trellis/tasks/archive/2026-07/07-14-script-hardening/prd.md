# Script hardening from optimization review

## Goal

Remove one genuine error-proneness foot-gun and a few micro-efficiency
redundancies in the shipped Python helpers, surfaced by the 2026-07-14
optimization analysis, without changing behavior. Every fix must be applied to
BOTH the `scripts/` copy and its byte-identical `templates/scripts/` twin (the
pack-drift gate enforces equality).

## Requirements

- R1 (correctness, highest value): In
  `scripts/sd-ai-command-pack-update-spec-kb.py`, the `dry_run` path classifies
  conflicts by matching human-message suffixes
  (`issue.endswith(" is missing") / " is not current" / " is a legacy generated
  symlink")`, and `--check` treats the same strings as all-conflicts. Editing any
  display string silently breaks the dry-run filter. Change `collect_copy_state`
  (and the dashboard/overview equivalents it feeds) to return **structured**
  issues — e.g. `(kind, path)` with `kind ∈ {conflict, missing, stale, …}` — and
  have dry_run/check select by `kind`, formatting the human string last. No
  change to emitted output text or exit codes; exercise BOTH the dry-run and
  `--check` paths.
- R2 (micro-efficiency, safe): Hoist the per-call set build in
  `is_managed_kb_category_path` (`update-spec-kb.py` ~225,
  `{title for _, title, _ in KB_CATEGORIES}`, called per-candidate inside rglob
  loops) to a module-level `KB_CATEGORY_TITLES = frozenset(...)` beside the
  existing derived `KB_CATEGORY_*` structures.
- R3 (micro-efficiency, safe): In
  `scripts/sd-ai-command-pack-record-session.py` (~357), the fallback
  `[j for j in modified_workspace_journals() if j not in before] or
  (modified_workspace_journals())` calls `modified_workspace_journals()` (a
  `git status` subprocess) twice on the no-new-journal path. Assign
  `after = modified_workspace_journals()` once and reuse.
- R4 (micro-efficiency, safe): In
  `scripts/sd-ai-command-pack-review-learnings.py` (~173), `_is_shell_like` does
  `text.splitlines()[0] if text.splitlines() else ""` (splits twice) and is
  called per added line, re-reading extensionless files each time. Split once
  (`next(iter(text.splitlines()), "")`) and cache the shell-like verdict per path
  (fold into the existing `file_text_cache` pass).

## Constraints

- No behavior change: emitted text, exit codes, and JSON/journal output identical;
  existing suite (test_update_spec_kb, test_record_session, test_review_learnings)
  is the oracle and must stay green.
- Apply each change to the `scripts/` file AND the `templates/scripts/` twin so
  they remain byte-identical (pack-drift gate green).
- `make test` green with the shipped-scripts coverage gate ≥76% (ideally the
  touched scripts' coverage does not drop); `make lint` (ruff+mypy) and
  `make full-check` green.

## Acceptance Criteria

- [ ] R1–R4 implemented in both copies (twins byte-identical).
- [ ] `make test` green, scripts coverage ≥76%; behavior unchanged (suite is oracle).
- [ ] `make lint` and `make full-check` green.
- [ ] The dry-run/`--check` classification no longer depends on display-string
      suffixes (R1 verifiable by grepping out the `.endswith(" is …")` filter).

## Non-goals

- The larger update-spec-kb refactors (findings 6, 9, 10, 11 — inline git-wrapper
  consolidation, GraphQL `_dig`, write/plan mirror merge, source_destination
  recompute) — deferred; this batch is the correctness fix + three safe micro-wins.
- install-audit / pr-body-scope micro-items (findings 12, 13) — deferred.
