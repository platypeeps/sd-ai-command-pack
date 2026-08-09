# Bookkeeping Tooling Guidelines

> Project-specific guidance for the Trellis bookkeeping validator and PR
> eligibility scripts.

---

## Scope

Use these specs when changing:

- `scripts/sd-ai-command-pack-review-preflight.mjs` (+ `templates/scripts/` mirror)
- `scripts/sd-ai-command-pack-pr-eligibility.py`
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
| [Runtime Coverage Lanes](./runtime-coverage-lanes.md) | Changing how shipped Python/Node/shell coverage is measured in CI — the `kcov-bash-shim.sh`, `summarize_shell_coverage.py`, `report-shell-coverage.sh`, or the `shell-coverage` job. Documents the kcov target-the-script gotcha and the summarizer exit contract |
| [Vendored Trellis Compatibility](./vendored-trellis-compatibility.md) | Writing or changing a wrapper that shells out to `.trellis/scripts/task.py` or `add_session.py`; upgrading the vendored Trellis version. Documents the `current --json` fallback contract, omit-empty journal sections, and the validated `trellis update` gate procedure |

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
