# Expand sd-status selectable inventory

## Goal

Make a normal `sd-status` response a complete, selectable inventory of the
current repository's remaining follow-ups, Trellis tasks, and roadmap-level
work so the user can choose an item by replying with an identifier such as
`F-1`, `T-2`, or `R-1`.

## Background

The status collector currently reports anomalies, a bounded summary of Trellis
work, and a short numbered `Next Steps` list. It does not enumerate all active-
root Trellis tasks, distinguish program-level roadmap entries from their child
tasks, or give those categories separate selection identifiers. The repository
has intentionally consolidated prior program-design and implementation-plan
backlogs into Trellis task trees, so the task tree is the canonical roadmap
source.

## Requirements

- Local status must always include three separately headed sections in this
  order: `Follow-ups`, `Tasks`, and `Roadmap`.
- Follow-up rows use `F-1`, `F-2`, and so on. They contain evidence-backed
  repository issues, recommendations, actions, or follow-up suggestions that
  are not already represented by an unarchived Trellis task.
- Task rows use `T-1`, `T-2`, and so on and enumerate every valid unarchived
  task directly under `.trellis/tasks/`, including planning, in-progress, and
  completed-but-not-archived tasks.
- Roadmap rows use `R-1`, `R-2`, and so on. An item is an open, top-level
  Trellis task with no parent; child tasks remain visible in `Tasks` but do not
  become separate roadmap rows.
- IDs must be deterministic for an unchanged repository snapshot, unique
  within their category, and assigned after a documented deterministic sort.
  They are report-local selection handles, not durable task identities.
- Each task and roadmap row must retain the durable Trellis task ID, title,
  status, priority, and task path. Task rows also expose their parent when one
  exists.
- Each follow-up must identify its kind and concise recommended action. The
  collector must derive these only from state it already reads: Git, GitHub,
  pack/Trellis versions, work-loop state, anomalies, and Trellis lifecycle
  state. This is not a replacement for a formal repository audit.
- A category with no items must remain visible and contain the exact text
  `none`; machine-readable output represents the same state as an empty array.
- Existing local facts, anomaly reporting, cached/refreshed labels,
  housekeeping strict-mode behavior, fleet summary behavior, and read-only
  guarantees must remain intact.
- Fleet JSON may expose each repository's complete local F/T/R inventory via
  its nested report. Fleet human output remains rollout-oriented and bounded;
  it must use F-prefixed fleet follow-ups but does not expand every consumer's
  task tree.
- The canonical template collector and `sd-status` skill own the behavior;
  generated/dogfood mirrors, distributed documentation, and tests must stay in
  sync.

## Acceptance Criteria

- [x] A clean local status report with no repository-derived follow-up prints
  `Follow-ups` followed by `none`, while still printing populated `Tasks` and
  `Roadmap` sections when Trellis work exists.
- [x] Dirty, divergent, lifecycle, GitHub-issue, or other supported actionable
  evidence produces deterministic F-prefixed rows with a kind and recommended
  action.
- [x] Local human output enumerates all valid unarchived tasks with T-prefixed
  IDs and all open top-level tasks with R-prefixed IDs; it never silently
  truncates either category.
- [x] A repository without Trellis tasks prints `none` in both the `Tasks` and
  `Roadmap` sections.
- [x] JSON output exposes structured follow-up records plus task and roadmap
  records carrying the same selection IDs shown in human output.
- [x] Unchanged repository state produces identical F/T/R ordering and IDs.
- [x] Archived tasks and symlinked or malformed task records remain excluded;
  completed tasks stranded outside the archive appear in `Tasks`, remain an
  anomaly, and are excluded from `Roadmap`.
- [x] The status skill tells agents to relay all three sections exactly and to
  treat an identifier supplied in a later request as a report-local selector,
  not as authorization to mutate the repository.
- [x] Focused status, skill/parity, housekeeping integration, read-only, and
  template/root parity tests pass.
- [x] The shipped behavior is documented, versioned according to repository
  policy, synchronized from `templates/**`, and passes the repository's
  required release and validation gates.

## Validation Evidence

- `tests.test_status` passes with deterministic F/T/R, empty-section,
  malformed/symlink, fleet, and read-only coverage; the shipped status helper
  remains above its per-file coverage floor at 87%.
- Focused status, SDLC-skill, generated-parity, and housekeeping tests pass.
- A live local human/JSON smoke test enumerated all 19 current unarchived tasks
  and nine open top-level roadmap items with matching report-local selectors.
- Exact-payload 0.35.0 candidate validation passed install, audit,
  preparation, and configured checks for all eight fleet consumers.
- `make check` passed unit/coverage, Ruff, mypy, Zizmor, install audit, KB
  freshness, command/template/release drift, and the deterministic full-check.
- Review-preflight normalization evidence is covered by good/base/failure
  tests for active ordering, parent normalization, deterministic repeated
  snapshots, and malformed/symlink exclusion. The changed parent and child
  Trellis directories are one topology update, and a future PR body must name
  the tooling/generated scope already reported by the gate.

## Out of Scope

- Restoring or scanning retired roadmap/program-plan files as a second source
  of truth.
- Running a static-analysis, security, architecture, or formal audit as part of
  status collection.
- Creating, starting, editing, archiving, or otherwise mutating a selected
  task or follow-up during the status request.
- Making report-local F/T/R ordinals durable across repository changes.
