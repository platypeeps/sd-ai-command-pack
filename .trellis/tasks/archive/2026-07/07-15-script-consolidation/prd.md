# Script consolidation: update-spec-kb git wrappers + source_destination; review-learnings GraphQL dig

## Goal

Close the safe, behavior-preserving subset of the optimization review's deferred
script-refactor items (findings 6, 9, 11) in the shipped Python helpers. Modest
value on already-hardened code, so correctness and byte-identical twins take
priority. Every fix applies to BOTH the `scripts/` copy and its
`templates/scripts/` twin.

## Requirements

- R1 (finding 6): In `scripts/sd-ai-command-pack-update-spec-kb.py`, the three
  inline git wrappers `repo_root` (~134), `git_remote_url` (~154), and
  `git_info_exclude_path` (~493) repeat the same ~9-line `subprocess.run` block.
  Extract one `_git_stdout(root, *args) -> str | None` (stripped stdout, or None
  on non-zero/failure) and have the three delegate. Preserve each caller's exact
  post-processing (including `repo_root`'s not-a-repo warning path).
- R2 (finding 11): `source_destination_entries` (~978) is a pure function
  recomputed 4× per run (called at ~595, ~996, ~1007, ~1246 via the dashboard/
  overview/copy paths). Compute it once and thread the result (or a derived map)
  through the callers that currently recompute it, without changing output.
- R3 (finding 9): In `scripts/sd-ai-command-pack-review-learnings.py`
  (`fetch_recent_copilot_comments`, ~657), the ~6-deep stacked
  `isinstance(...)/continue` GraphQL descent is hard to read. Add a small
  `_dig(obj, *keys)` helper returning None/`[]` on shape mismatch and collapse
  the staircase. PRESERVE the exact skip-not-raise semantics (unexpected shapes
  are silently skipped, never raised).

## Constraints (HARD)

- No behavior change: emitted text, exit codes, JSON/journal/KB output identical;
  the existing suite (test_update_spec_kb, test_review_learnings) is the oracle.
- Apply each change to the `scripts/` file AND its `templates/scripts/` twin so
  they stay byte-identical (`diff` empty; pack-drift gate green).
- `make test` green with shipped-scripts coverage ≥76% (don't drop the touched
  files' coverage); `make lint` (ruff+mypy) and `make full-check` green.
- Scripts are shipped payload → the main session will bump the manifest version
  (to 0.10.3) + CHANGELOG at commit time; the sub-agent must NOT bump.

## Acceptance Criteria

- [ ] R1–R3 implemented in both copies (twins byte-identical).
- [ ] `make test` green, scripts coverage ≥76%; behavior unchanged (suite oracle).
- [ ] `make lint` green.

## Non-goals

- Finding 10 (write_generated_markdown / planned_generated_markdown_state
  mirror-merge) — DEFERRED: the compute-vs-apply mirror guards dry-run/`--check`
  vs refresh, and merging it risks letting `--check` write. Not worth the risk
  for the concision gain.
- install-audit / pr-body-scope micro-items (findings 12, 13).
