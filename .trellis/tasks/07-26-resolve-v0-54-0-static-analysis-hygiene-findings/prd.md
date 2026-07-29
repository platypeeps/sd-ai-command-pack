# Resolve v0.54.0 static analysis hygiene findings

## Goal

Address the non-blocking GitHub Code Quality findings repeated across v0.54.0 fleet consumers, changing canonical templates and mirrors together with focused regression validation and an explicit overload-stub policy.

## Requirements

- Remove the dead initial `status_value` write in provider execution without weakening terminal-status typing or failure handling.
- Add concise intent comments or explicit fallback assignments for best-effort cleanup and optional metadata reads identified by static analysis.
- Resolve the repeated overload-stub `...` findings consistently: use a type-checker-compatible body that satisfies static analysis, or document and test a narrow suppression if `pass` would weaken the typing contract.
- Apply changes to canonical `templates/scripts/**` sources first and keep root installed mirrors synchronized.
- Keep these behavior-preserving cleanups out of the immutable v0.54.0 rollout and publish them in a later reviewed release.
- Cover every deferred fleet finding owner from `rwbp-coordinator` PR #177: `rwbp-coordinator-177-code-quality-2` through `rwbp-coordinator-177-code-quality-7`.
- Reuse this task for the eight equivalent or adjacent deferred owners from `anomaly-metric-creator` PR #299: `AMC299-1` through `AMC299-8`.

## Acceptance Criteria

- [ ] Provider execution has no dead initial status assignment and all reachable result paths retain a terminal status.
- [ ] The intentional `FileNotFoundError`, process termination/wait, optional HEAD lookup, and directory `fsync` fallbacks are explicit to readers and static analysis.
- [ ] Both `_git` overload declarations satisfy typing and static analysis without consumer-local divergence.
- [ ] Template and installed-mirror files are byte-identical after the changes.
- [ ] Focused unit tests for the affected helpers pass.
- [ ] `make check` and the pack install audit pass before publication.

## Notes

- Origin: GitHub Code Quality findings on `platypeeps/rwbp-coordinator` PR #177 at discussions `discussion_r3652755393`, `discussion_r3652755418`, `discussion_r3652755421`, `discussion_r3652755429`, `discussion_r3652755411`, and `discussion_r3652755414`.
- Repeated origin: GitHub Code Quality findings on `platypeeps/anomaly-metric-creator` PR #299 at discussions `discussion_r3653108288`, `discussion_r3653108298`, `discussion_r3653108299`, `discussion_r3653108302`, `discussion_r3653108304`, `discussion_r3653108307`, `discussion_r3653108310`, and `discussion_r3653108313`.
- Fleet severity disposition: six `style` owners classified `continue-with-follow-ups`; none blocks v0.54.0.
- The anomaly-metric-creator batch independently classified all eight observations as `style` and `continue-with-follow-ups`; the repeated overload findings are now explicitly in scope for a durable source-level decision.
- Lightweight task; PRD-only is appropriate. Classified 2026-07-28: fourteen finding
  owners, but they collapse to six behavior-preserving edits repeated across two consumer
  repos, and every acceptance criterion above is already a per-edit check.
- **The one apparent design fork is decidable by experiment, not by design.** R3 offers
  "type-checker-compatible body" or "documented narrow suppression if `pass` would weaken
  the typing contract". The two declarations are
  `templates/scripts/sd-ai-command-pack-review-local.py:533-538` (`_git` with
  `binary: Literal[False]` and `Literal[True]`), bodies `...` on the signature line.
  Whether `pass` changes anything is answered by running the type checker once with it
  substituted — do that before choosing, and record the observed result rather than
  arguing the branch.
- Both copies must move together: `scripts/sd-ai-command-pack-review-local.py:533-538` is
  the installed mirror of the same declarations.
- **All six edit sites are in this checkout; only the fourteen finding *owners* are not.**
  The `rwbp-coordinator-177-*` and `AMC299-*` identifiers are GitHub discussion threads on
  two consumer PRs and cannot be read from here, so "cover every deferred owner" is checked
  by mapping each owner to one of the six edits, not by opening the threads. The code they
  point at is all one pack file — `templates/scripts/sd-ai-command-pack-review-local.py`:
  the initial `status_value = "failed"` at `:1681` that every reachable path reassigns
  (`:1705`, `:1713`, `:1718`, `:1723`, `:1738`, `:1748`, `:1756`), the swallowed
  `FileNotFoundError` at `:596` and `:1361`, the `os.fsync` at `:1356`, the
  `process.wait(timeout=5)` pair in `_terminate` (`:1467`, `:1477`), the `HEAD` diff at
  `:705`, and the two overload stubs at `:533-538`. Do the work and the verification
  against this repo; the consumer PRs are provenance, not a dependency.
