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
