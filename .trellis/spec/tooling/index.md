# Bookkeeping Tooling Guidelines

> Project-specific guidance for the Trellis bookkeeping validator and PR
> eligibility scripts.

---

## Scope

Use these specs when changing:

- `scripts/sd-ai-command-pack-review-preflight.mjs` (+ `templates/scripts/` mirror)
- `scripts/sd-ai-command-pack-pr-eligibility.py`
- `scripts/sd-ai-command-pack-review.py` (+ `templates/scripts/` mirror), for
  its per-attempt state and stage memoization only — the review workflow
  itself is owned by the `sd-review` skill
- `tests/test_bookkeeping_validator.py`, `tests/test_pr_eligibility.py`
- `.agents/skills/sd-finish-work/SKILL.md` (+ template mirror) where it
  documents this validator's contract

This tooling is distinct from the installer (`install.py`, covered under
`backend/`) and from the platform adapter templates (covered under
`frontend/`): it is CI/session-lifecycle logic that gates PR merges and
finish-work receipts, shipped as part of the pack but never installed as an
adapter.

## Guides

| Guide | Use When |
|-------|----------|
| [Bookkeeping Validator Notes](./bookkeeping-validator.md) | Adding a bundle shape, recovery subtype, or historical-proof mechanism to `review-preflight.mjs`; adding a top-level `const`/`let` to that file; touching the root-task `base_branch` rule or its default-branch resolver; touching a git-failure `*_unavailable` finding or the `lastBookkeepingGitFailure` diagnostics slot |
| [Fleet Publish Generated Content](./fleet-publish-generated-content.md) | Adding or changing pack-managed generated content a consumer regenerates from a script (`docs/repomix-map.md`, the `.gitignore` `.obsidian-kb` block); changing `fleet-publish.py`'s step order or `DEFAULT_ALLOWED_PREFIXES`. Documents why regeneration must precede `work_commit()`, why allowlisting alone is not the fix, and the `--if-present`/cwd traps in matching housekeeping's invocation |
| [Fleet Publish Acceptance Criteria](./fleet-publish-acceptance-criteria.md) | Changing how the publish helper writes a consumer's archived `prd.md`, or the acceptance criteria the `sd-fleet-refresh` skill authors. Documents the `verify:` tag grammar, why the tick lands immediately before `task.py archive` and nowhere else, the fail-closed set (untagged, unknown id, missing lane evidence), the never-guess and never-untick rules, and the idempotent rewrite |
| [Review Attempt State](./review-attempt-state.md) | Changing what the review coordinator stores in, or serves from, its per-attempt state file — which stage results a resume replays and which recompute. Documents the attempt key's blind spots (live PR body, gitignored paths, provider reachability, per-invocation argv) and the phase-rewind trap |
| [Runtime Coverage Lanes](./runtime-coverage-lanes.md) | Changing how shipped Python/Node/shell coverage is measured in CI — the `kcov-bash-shim.sh`, `summarize_shell_coverage.py`, `report-shell-coverage.sh`, or the `shell-coverage` job. Documents the kcov target-the-script gotcha and the summarizer exit contract |
| [Surface Retirement Doc Gates](./surface-retirement-doc-gates.md) | Deleting a shipped script, a command surface, or any file a Trellis `prd.md`/`research/*.md` cites by path. Documents the public/internal classification contract in `check-shipped-script-docs.sh` and the documentation path-reference exemptions in `review-preflight.mjs` — both fail in files the deletion never touched |
| [Vendored Trellis Compatibility](./vendored-trellis-compatibility.md) | Writing or changing a wrapper that shells out to `.trellis/scripts/task.py` or `add_session.py`; upgrading the vendored Trellis version; testing a defect whose fix already exists upstream but is unreleased. Documents the `current --json` fallback contract, omit-empty journal sections, the validated `trellis update` gate procedure, and where a suite that must skip until a release lands lives instead of `tests/` (`Makefile:49` fails on any skip) |

## Pre-Development Checklist

Before editing `review-preflight.mjs`:

1. Read the target function and its callers fully — this file reuses a small
   set of primitives (`bookkeepingChangedEntries`, `loadBookkeepingJsonAtRef`,
   `validateBookkeepingTaskDirectory`, `validateBookkeepingJournalBundle`)
   across many call sites; check whether your change can reuse one of these
   before writing new traversal/read logic.
2. Read [Bookkeeping Validator Notes](./bookkeeping-validator.md) in full —
   it documents two non-obvious, previously-costly gotchas specific to this
   file's structure.
3. If the change adds or modifies a `final-bundle` bundle shape or recovery
   subtype, find the most recent prior task under
   `.trellis/tasks/archive/**` that touched this same mechanism (search
   `.trellis/tasks/archive/*/design.md` for `review-preflight.mjs`) and read
   its design doc — this validator's safety properties (bounded ranges, no
   merge commits in a validated range, archived history immutable, no
   unaudited workspace admission) accumulate across tasks and must not be
   silently narrowed.

## Quality Check

Run:

```bash
python3 -m unittest tests.test_bookkeeping_validator tests.test_pr_eligibility
node --check scripts/sd-ai-command-pack-review-preflight.mjs
node --check templates/scripts/sd-ai-command-pack-review-preflight.mjs
diff scripts/sd-ai-command-pack-review-preflight.mjs templates/scripts/sd-ai-command-pack-review-preflight.mjs
```

`pytest` is not installed/pinned in this project; use `python3 -m unittest`
(the same runner `.github/scripts/run-tests.sh` uses), via the project's own
`.venv` (`make setup`).

**If the change modifies control flow that existing tests already pin**
(a new bundle shape, a new recovery subtype, a changed orchestration
discriminator), running the existing suite against a real implementation is
its own required gate, separate from and in addition to any design-review
reasoning about the change — see
[guides/index.md](../guides/index.md)'s "When Verifying AI Cross-Review
Results" section for why these catch different classes of defects.
