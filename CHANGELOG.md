# Changelog

## 0.59.1 - 2026-07-31

- Align the status and housekeeping selector contracts (review finding 1.1.1).
  `sd-status` and `sd-housekeeping` now describe only the shipped `F-*`
  follow-up and `T-*` task selectors — the retired `F/T/R` wording is gone —
  and a selector that does not resolve to an `F-*` or `T-*` row of the current
  snapshot is reported as unresolved input with no action taken. A new drift
  test scans the shipped surface (templates, docs, generated adapters and
  mirrors) so the retired selector contract cannot reappear; `.trellis/` task
  history stays out of scope by construction.

## 0.59.0 - 2026-07-31

- Declare and pin the build dependency toolchain (audit A-108/A-109/A-110).
  `pyproject.toml` gains a `[project]` table with `requires-python = ">=3.10"`
  as the single machine-readable Python floor — ruff now infers its lint
  target from it, and a new test checks the hand-written copies (CI matrix
  floor leg, toolchain interpreter probe) against it. **Consumer-facing:**
  `sd-ai-command-pack-review-preflight.mjs` now requires Node 22 or newer
  (was 16.9, EOL since 2023); repos that install the pack need a supported
  Node LTS to run the preflight. CI pins `actions/setup-node` to Node 22 in
  the jobs that execute or parse the script instead of taking whatever the
  runner image ships, and installs Python dependencies from hash-pinned
  compiled requirements with `--require-hashes`, so transitive dependencies
  stop re-resolving unreviewed on every run.

## 0.58.0 - 2026-07-31

- Close the shipped-script documentation gap (audit A-115). Every manifest
  `scripts/` target now carries an explicit public/internal classification:
  `sd-ai-command-pack-pr-eligibility.py` gains an installed-guide entry as the
  read-only exact-head PR eligibility evaluator, while
  `sd-ai-command-pack-review-local.py` and `sd_ai_command_pack_lib.py` are
  declared internal. The guide now distinguishes `review-local.sh` (documented
  operator runner) from `review-local.py` (internal review stage) — the two
  never call each other. CONTRIBUTING narrows the stable-surface promise to
  guide-documented script CLIs and names the internal category, and a new
  doc-coverage gate (`.github/scripts/check-shipped-script-docs.sh`, wired
  into `make test` and CI) fails when a shipped script is neither documented
  nor deliberately allowlisted — or is both allowlisted and given an explicit
  guide entry bullet — so the gap cannot reopen silently and a
  reclassification must update both places. The eligibility evaluator's guide
  entry documents its real exit mapping (`0` eligible, `1` blocked, `2`
  anything else).

## 0.57.2 - 2026-07-31

- Require a trailing `<!-- SD-AI-COMMAND-PACK:KB-COPY -->` provenance marker
  before the Obsidian KB prune deletes a plain file in a managed category
  folder, so user files are never removed just for sitting in a folder that
  shares a category title — or for quoting the marker text mid-file — including
  through a KB root symlink into a personal vault. Generated
  copies now end with that trailing marker instead of being byte-identical to
  their sources, and both the refresh currency check and `--check` compare
  against the marked payload. Copies written by older versions adopt the marker
  on the next refresh while their source exists; copies orphaned before the
  upgrade are no longer pruned automatically and need manual cleanup (audit
  A-070 residual).

## 0.57.1 - 2026-07-31

- Preserve the moved-aside foreign lock when work-loop lock recovery cannot
  restore it, and name the aside path in the raised error so an operator can
  move it back. Restore now falls back to an `O_CREAT|O_EXCL` rewrite on
  filesystems without hard-link support, so the canonical lock path is
  restored instead of silently voiding mutual exclusion (audit A-092).

## 0.57.0 - 2026-07-30

- Remove the public `sd-watch-pr` command. `sd-ship` Stage 3 now runs an
  internal read-only watch coordinator: it polls the PR-eligibility probe
  every 20 seconds with an attempt ceiling of `timeout-minutes × 3` (default
  30 minutes) and classifies the result as settled-green, settled-blocked,
  timed-out, or probe-failed; only settled-green continues to Stage 4. The
  retired command name joins the drift-scan retirement registry, and
  `no-merge` fails as an unknown `sd-ship` argument — `until=review` is the
  supported stop-before-merge point.
- Move finish-work finalization into `sd-ship` Stage 2b for both
  `until=review` and `until=merge`: the SD finish-work flow runs exactly once
  per chain, bound to the exact head Stage 2 reviewed, with the
  completion-vs-planning selection owned by the flow's typed deterministic
  contract. Stage 4 runs zero finish-work flow invocations of its own — on an
  unchanged head it passes Stage 2b's retained exact-head receipt to the
  housekeeping gate, and on a moved head it recomputes the receipt with a
  direct read-only final-bundle validator invocation (completion mode against
  the current head's empty delta, planning mode re-running the captured base
  under journal-only-recovery scope). The eligibility gate's independent
  recomputation remains the double-run guard.
- If Stage 2b's finalization produces a new head, the chain re-enters
  Stage 2's check/review once for that head; a second finalization head stops
  the chain as a defect. Re-entry repeats only Stage 2 — never the learning
  pass, finalization, or Stage 4's merge.
- Narrow `sd-create-pr` to publish-only in every invocation: Step 6 names the
  next command (`sd-review scope=pr`, or `sd-ship` for the full chain)
  instead of entering a review loop, and the composite-only Stage 1
  orchestration context (`caller:`/`stage:`/`return-after:`) is removed —
  `sd-ship` Stage 1 invokes the same public flow and reads the publish result
  from its report. The trusted `sd-work-backlog` and `sd-fleet-refresh`
  contexts are unchanged.

## 0.56.8 - 2026-07-30

- Repoint `sd-ship` Stage 2 from the transitional `sd-review-pr` loop to the
  routed successor, `sd-review scope=pr`. The successor is review-only, so the
  two lifecycle side effects that used to ride along with review move to a new
  explicit Stage 2b owned by the composite: the one read-only, PR-scoped
  post-cycle review-learning pass (run for both `until=review` and
  `until=merge`), and — for `until=review` only — the SD finish-work flow bound
  to the exact reviewed head. `until=merge` still defers finish-work to the
  Stage 4 housekeeping gate, which remains the only merge authority. The
  `until=review` stop-point now sits after Stage 2b instead of after Stage 2's
  loop; its user-visible contract — review completes, Trellis work finishes,
  no merge — is unchanged. The internal `defer-finish-work` delegation mode is
  gone from `sd-ship`; `sd-review-pr` itself stays installed and callable
  standalone.
- Rewrite the usage guide's recommended review loop around the successor
  lifecycle only: `sd-check`, routed `sd-review`, `sd-ship` with its stage
  composition, work-backlog delegation to `sd-ship until=merge`, and the
  lifecycle commands. The transitional `sd-review-local`, `sd-review-pr`, and
  merged-PR interception steps leave the recommended path; the commands remain
  installed, documented in the catalog, and callable.

## 0.56.7 - 2026-07-30

- Scope the finalization bundle validator to the change delta. The final-bundle
  gate previously validated every changed task directory wholesale, so a defect
  in an untouched sibling file — a stale `task.json` description, a leftover
  scaffold row — blocked finalization of work that never touched that file
  (PR #273 failed on 25 such findings). Defects anchored to files inside the
  bundle delta still block; defects anchored to untouched files are demoted to
  a new non-blocking `advisories` array in the result document (capped at 25
  entries, overflow reported via `evidence.advisoriesDropped`, same path and
  message truncation as findings). Topology findings follow the anchor rule:
  a broken link blocks when the anchoring `task.json` is in the delta and
  advises when it is not, including the two sites that report the neighbor's
  path. The `pre-archive` command and historical completion replay keep their
  strict whole-directory behavior, and the housekeeping receipt loader
  tolerates the new fields.
- Widen journal-only planning recovery to ordinary repository maintenance
  commits. Cited-commit paths now partition five ways: active-task paths keep
  the current per-path and lifecycle rules; ordinary repository paths are
  allowed, including deletes and renames; the task archive, malformed
  task-namespace paths, and `.trellis/workspace/**` paths remain forbidden.
  `planning_recovery_task_change_missing` now fires only when the cited
  commits collectively change no allowed path, so a maintenance branch can
  finalize with a journal session citing its repository-only work commits.
- Document the finalization receipt contract in `sd-finish-work`: the captured
  base is the last work commit (not the merge-base with the default branch),
  the maintenance-branch planning flow, the widened recovery scope, and the
  advisory semantics.

## 0.56.6 - 2026-07-30

- Allowlist the documented `.sd-ai-command-pack/review.json` configuration file
  in the shipped install audit. `sd-review` declares the path and the pack docs
  describe it as supported, but `LOCAL_ALLOWED_PACK_FILES` never admitted it, so
  a consumer that created the file exactly as documented failed `install-audit`
  — and with it the `pack.install-audit` gate in sd-check, sd-full-check, and
  sd-review — with a hard error. The audit collector walks the filesystem, so
  the failure hit tracked and untracked copies alike, and no managed gitignore
  pattern covers the path. A fixture-backed test now locks the entry in place:
  it installs the pack into a consumer fixture, writes the documented
  configuration file, and asserts the audit passes; removing the allowlist
  entry fails the test. Audit finding A-056.

## 0.56.5 - 2026-07-30

- Silence the pre-PR tooling/generated scope advisory once the PR body already
  carries the required section. Advisory mode previously warned on every branch
  that touched a tooling/generated file and returned before the PR body was ever
  consulted, so a correctly written PR body could not stop the warning and every
  local `make check` on such a branch reported one warning that no action could
  clear. Advisory mode now resolves the body through the same path the enforcing
  check uses — `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` first, then `gh pr view` — and
  warns only when the resolved body lacks the section or when no body can be
  resolved. The pre-PR reminder is unchanged when no PR exists yet, the advisory
  still never fails, and it resolves nothing on a branch with no
  tooling/generated change, so no `gh` call is added to the common case. The
  enforcing full-check path is unchanged except that a PR body parser that
  crashes is now a named failure instead of an unlabeled abort, and a resolver
  that returns no state at all is reported as such rather than as an
  indeterminate one.

## 0.56.4 - 2026-07-30

- Resolve a deadlock between two finalization gates over `task.json`'s `branch`
  field. The pre-archive gate refuses a completion-ready task whose `branch` is
  null, but `task.py start` never writes that field, so every task is born in
  the refused state. Recording the branch where `sd-finish-work` step 4 puts the
  operator — after the finalization base is captured — lands the write inside
  the archive commit, which the completion bundle gate then rejects with
  `completion_archive_identity_changed` because an archive move may change only
  `status` and `completedAt`. A compliant run had no exit at all: the step's own
  stop clause forbids repairing an `invalid` pre-archive result by mutating the
  task.
- `sd-finish-work` step 4 now records a missing branch *before* capturing the
  finalization base, for every task directory the gate is invoked for. It takes
  the value from `git symbolic-ref --quiet --short HEAD`, stops rather than
  guessing on a detached HEAD or a value equal to `base_branch`, and commits
  only that `task.json` as a branch-metadata commit — not a work commit, which
  `trellis-finish-work` reserves for pre-invocation code commits. A task that
  surfaces only after the base is captured cannot be prepared this way and is
  declined for the round, or the finalization restarts with it included.
- The completion bundle gate tolerates exactly one branch transition across an
  archive move, `null` to a non-empty string, so a run already past base capture
  can still finalize. A rewrite, an erasure, and a key absent from the source
  record all stay rejected, as does any change to any other field. The reason
  code had no regression coverage in either direction before this change.

## 0.56.3 - 2026-07-29

- Add an explicit fleet-controller recovery transition for `retry-exhausted`
  lanes. A lane's retry budget is per stage, so a consumer whose infrastructure
  failure consumed both automatic attempts became permanently terminal: nothing
  short of a new campaign could reopen it, and because a `retry-exhausted` lane
  reads as a failed observation it also tripped the canary health stop for every
  other consumer in the campaign. `resume --recover-exhausted-consumer NAME
  --exhausted-action ID --release VERSION` now grants one operator-authorized
  attempt at the stage that exhausted, bounded to two recoveries per consumer
  and stage. It validates that the lane is terminal `retry-exhausted`, that the
  named action is the lane's latest receipt, and that the receipt's stage,
  attempt, and reason code all agree with the lane; `--release` is compared
  against the campaign's own target version rather than the current
  `manifest.json` version, so a campaign on an older release stays recoverable.
  Replaying the same exhausted action returns the existing record and changes
  nothing.
- Bump the campaign state schema to version 2 and migrate version-1 state on
  load: an absent `recoveries` key becomes an empty list and every untagged
  recovery row gains `kind: "pack-blocker"`. Recovery rows are now a tagged
  union on `kind`, so exhaustion recoveries and pack-blocker recoveries are
  validated against their own field sets instead of one shared shape, and the
  pack-blocker idempotency lookup filters on `kind` rather than assuming every
  row carries a blocking head. Migration is read-only — loading a version-1
  campaign to report on it leaves the state file byte-for-byte unchanged until
  the next mutating command writes it. Historical `receipts` remain immutable
  under both recovery kinds.

## 0.56.2 - 2026-07-29

- Exempt a planning task's untouched context scaffold from both review-preflight
  seed-row lanes — the diff-scoped task-context gate and the bookkeeping
  validator that emits `task_context_seed`. `task.py create` writes
  `implement.jsonl` and `check.jsonl` with a generated `_example` seed row,
  which both lanes failed on immediately, so creating a task put the repo into a
  failing state until the author blanked or rewrote both files by hand. This
  affected pack-installed repositories where task creation actually seeds those
  manifests; Trellis skips seeding when no sub-agent platform is configured. The
  exemption is deliberately narrow: a single row that parses to an object whose
  sole key is `_example`, in a non-archived task whose `task.json` status is
  `planning`. It matches on that shape rather than on Trellis's exact seed text,
  which is Trellis-owned and changes across versions — pinning it would re-break
  task creation on the next Trellis upgrade. A seed row that survives beside
  authored rows, carries extra keys, or appears in any non-planning or archived
  task still fails, so the curation requirement at `task.py start` is unchanged.

## 0.56.1 - 2026-07-29

- Treat a remote review body that reports no new comments as clean only after
  parsing it for a collapsed low-confidence block. Copilot withholds
  observations it scored as low confidence and discloses them only inside that
  block, so they never become inline comments or review threads and a loop
  reading only thread state never sees them. Each disclosed entry is now
  classified with the same rules as an inline comment, and the round is clean
  only when none survives verification.
- Compare every review event's `commit_id` to the recorded head before counting
  a review round. A reviewer can submit against an earlier commit while a newer
  one is already the head, and its body still reports full coverage because the
  file count is taken against the commit it actually read.
- Require the audit ledger and report to be committed separately from any
  `.trellis/tasks/**` planning artifacts written in the same session. The
  bookkeeping validator admits only task and workspace paths into a
  finalization delta, so a commit mixing `.trellis/audit/**` with task
  artifacts can be neither journaled nor finalized, and the mix cannot be
  undone once published.
- Extend the planning adversarial review to check a task's artifacts against
  each other, not only against the repository. A value repeated across
  `prd.md`, `design.md`, `implement.md`, and `task.json` is enumerated by
  search rather than by reading the artifacts in sequence, and any
  cross-artifact citation is confirmed to still describe what its target says.

## 0.56.0 - 2026-07-28

- Add a typed, additive `environment_blocked` recovery contract. When an
  environment or authority boundary refuses a Git-metadata, user-state,
  tool-cache, or knowledge-base write, the owning operation attaches a bounded,
  secret-safe fragment naming the boundary, last verified checkpoint, mutation
  state, and a non-authoritative recovery action, without changing its own
  outcome or exit. The housekeeping result surfaces these as an additive
  `environmentBlocks` array that consumers which do not understand it ignore.
- Route housekeeping by pull-request lifecycle state and validate the
  finish-work receipt path before any side effect, failing fast on an invalid
  receipt while leaving downstream merge eligibility unchanged.
- Gate task archival on a read-only pre-archive acceptance-readiness check that
  does not fire on handoff prose, non-canonical directories, or fenced examples.
- Make housekeeping the sole owner of general recovery-artifact cleanup while
  the creating workflow keeps success-path cleanup; ambiguous or unique content
  defaults to preserve and `sd-status` stays read-only.
- Recover a stale work-loop lock with an identity-checked rename-aside so a
  concurrent run cannot remove a live lock, and expose blocked and parked
  backlog markers so the selector distinguishes parked work from ready work.
- Scope toolchain caches per user with uid and ownership checks, and record the
  housekeeping-result schema migration explicitly as an in-major change with no
  silent contract break or compatibility alias.

## 0.55.5 - 2026-07-27

- Classify `.gemini/settings.json` consistently as Trellis-owned across the
  platform registry and shipped review-scope scanner, matching the JavaScript
  preflight and preventing consumer review-scope drift.

## 0.55.4 - 2026-07-27

- Accept a completed task archive move when Git reports a rewritten active PRD
  as deleted but exposes the matching task metadata only at its changed archive
  destination.
- Keep the topology guard fail closed when a live task directory is missing
  `task.json`, with focused regression coverage for both paths.

## 0.55.3 - 2026-07-27

- Let a controller-issued merge action record the required finish-work head
  advance as one bounded `pr-head-advanced` republication instead of forcing a
  contradictory old-head merge receipt or terminal pack blocker.
- Retain the exact finish-work receipt across successor publication, review,
  and merge eligibility, then consume it through housekeeping only after the
  new PR head remains unchanged and fully eligible.
- Preserve exact publication epochs, serialized merges, the two-attempt head
  churn bound, and the separate corrective-release path for terminal missing
  task evidence.

## 0.55.2 - 2026-07-27

- Make publication and review workflow invocation explicit standing approval
  for in-scope commits, PR-branch pushes, and configured GitHub review requests
  or re-requests, while preserving ambiguity, risk, round-limit, destructive,
  exact-head, and merge gates.
- Surface that authority in startup-visible skill descriptions and prevent the
  portable structured-question contract from adding redundant approval prompts
  for routine GitHub publication or review actions.
- Make a merge-capable `sd-fleet-refresh` campaign standing approval for every
  eligible controller-issued consumer housekeeping merge, including after
  review-finding remediation; retain `no-merge` as the explicit opt-out.
- Prefer the optional `archify` skill when `sd-update-spec` creates or
  materially updates repository documentation visuals, with a reported
  repo-native fallback when Archify is unavailable.

## 0.55.1 - 2026-07-26

- Pin strict UTF-8 decoding explicitly in the shipped housekeeping-result JSON
  reader and the source fleet-preflight provenance reader, preserving existing
  fail-closed behavior while satisfying consumer static-analysis contracts.

## 0.55.0 - 2026-07-26

- Commit `.claude/` by default like every other platform: replace the
  `.claude/**` blanket plus SD allow-list in the managed `.gitignore` block with
  the standard runtime deny-list, so Trellis runtime, agents, `settings.json`,
  and repo-authored skills are tracked instead of hidden. Only local Claude
  state (`settings.local.json`, caches, logs, tmp) stays ignored.
- Extend the Claude `--local-only` exclude set and the review-scope and
  review-preflight classifiers to cover `.claude/agents/trellis-*.md` and
  `.claude/settings.json`, and add a `git check-ignore` regression test that no
  platform ignores its own declared markers.

## 0.54.1 - 2026-07-26

- Require fleet refresh lanes to establish a dedicated consumer Trellis task
  before installation so deferred finish-work can produce canonical completion
  evidence instead of a structurally invalid taskless journal.
- Add an explicit corrective-release controller transition that preserves the
  blocker receipt, records recovery evidence, republishes on a new exact-head
  epoch, and avoids replaying the failed merge action.
- Document an append-only recovery for already-published taskless refresh PRs
  while keeping ordinary journal-only planning validation fail closed for
  arbitrary implementation commits.

## 0.54.0 - 2026-07-25

- Recover a canonical adjacent completion tail when review fixes follow task
  archival, proving a bounded linear successor without another journal or
  bookkeeping-only commit.
- Replace the head-only housekeeping attestation with the exact retained
  finish-work JSON receipt and independently recompute it inside eligibility
  before any merge mutation.
- Keep the public finalization modes at `completion|planning`, expose the
  internal `post-archive-review-successor` subtype, and fail closed on stale,
  forged, nonlinear, invalid-anchor, or bookkeeping-mutating successor evidence.

## 0.53.0 - 2026-07-25

- Let planning finish-work automatically validate a journal-only successor
  when its referenced work commits were already published before the captured
  finalization base.
- Prove one exact journal/index pair, unique published single-parent commits,
  regular active-task-only deltas, and planning lifecycle state while keeping
  normal planning bundles on the complete content-quality validator.
- Preserve schema version 1, `mode: planning`, and `planning_bundle_valid`,
  adding only the machine-visible `journal-only-recovery` evidence subtype and
  bounded recovered task directories.

## 0.52.1 - 2026-07-25

- Warn deterministically before remote review when the selected diff exceeds
  GitHub Copilot's configurable 300-file review limit.

## 0.52.0 - 2026-07-25

- Add `sd-review` as the unified exact-scope review lifecycle for changes,
  branches, codebases, and pull requests, composing the typed deterministic
  check with cost-aware local review receipts and routed GitHub review.
- Discover the released `sd-github-review` v1 capability from a strict
  repository descriptor, persist dispatch intent before mutation, reconcile
  durable exact-head receipts, and observe only receipt-declared finding
  channels without a direct reviewer fallback.
- Extend the shared review configuration with bounded `remoteIntegration`
  policy, keep optional router absence visibly local-only, and fail closed for
  provider failures, invalid routing, ambiguous dispatch, or stale heads.

## 0.51.0 - 2026-07-25

- Extend the canonical review-preflight executable with schema-version-1
  `pre-archive` and completion/planning `final-bundle` bookkeeping modes.
- Validate bounded task identity, descriptive metadata, lifecycle, topology,
  context, archive moves, journal/index content, commit reachability, and
  whitespace before finish-work may publish its final bookkeeping head.
- Make finish-work retain one exact validator result for review, ship, and
  housekeeping callers while preserving failed local archive/journal commits
  for inspection instead of rewriting or pushing them.

## 0.50.0 - 2026-07-25

- Add strict exact-head finding-family evidence to the internal local-review
  stage, using the bounded review-learning vocabulary while preserving original
  provider labels separately.
- Stop automatic remote eligibility when the same actionable family appears on
  a second round, emit a deterministic sibling-audit matrix, and require clean
  local-review, passing check, sibling, batch, and one-commit evidence before
  redispatch.
- Stop post-audit recurrence before another provider call until the existing
  structured round-extension decision is recorded, with bounded family, cost,
  batch, sibling, and redispatch telemetry.

## 0.49.0 - 2026-07-24

- Add the internal exact-scope local stage consumed by the successor
  `sd-review` lifecycle, with deterministic risk/cost provider plans and
  isolated parallel Prism/Gito attempts for substantive first heads.
- Persist normalized provider evidence and exact target-bound receipts so an
  unchanged pre-publication branch review can satisfy the PR stage without a
  duplicate provider call; invalidate reuse on any target, provider, or policy
  change.
- Keep failures and findings distinct, block remote routing on outstanding
  local findings, and permit bookkeeping-only skips only with exact external
  evidence and zero new confidence.
- Parse Prism and Gito native structured reports rather than treating exit zero
  as clean, and fail before dispatch when a provider cannot safely encode the
  exact target paths.

## 0.48.0 - 2026-07-24

- Expose bounded, normalized historical review-learning clusters as a typed
  path-filtered planning signal without copying full review comment bodies.
- Add one-scan-per-attempt private receipts with exact cache reuse, bounded
  GitHub evidence, explicit tracked-snapshot freshness, visible
  stale/unavailable states, and zero confidence credit.

## 0.47.0 - 2026-07-24

- Add `sd-check` as a typed deterministic verification command with strict
  argv-array repository configuration and normalized outcome/exit semantics.
- Keep checks read-only by removing provider and refresh behavior, routing tool
  caches outside the repository, and failing when before/after repository or
  Git state differs.
- Add a registry-derived shipped-surface closure validator shared by
  `sd-check`, local pre-publication, and CI. It explicitly registers
  source-only references and reports stale generated state with its owning
  preparation command.

## 0.46.0 - 2026-07-24

- Route XDG/GitHub CLI, Python, uv, pip, Ruff, and npm caches through one
  validated private per-user/per-repository environment shared by Python and
  shell entry points without changing authentication state.
- Replace command-specific UV and disposable-candidate cache fragments with
  the shared builder, controlled failures, deterministic external namespaces,
  and documented cache-root/retention behavior.

## 0.45.0 - 2026-07-24

- Keep formal repository audits read-only by replacing checkout-owned Make and
  help probes with static inspection.
- Add a deterministic committed-tree architecture inventory that safely ranks
  regular blobs while preserving hostile valid filenames.

## 0.44.0 - 2026-07-24

- Re-read the exact pull request head by retained PR number at local-branch
  eligibility completion, failing closed when it changes or becomes unreadable.
- Bind schema-major-1 eligibility evidence to additive initial and final PR
  head observations while preserving local-head and housekeeping safeguards.

## 0.43.0 - 2026-07-23

- Add a Claude project rule that adversarially reviews materially changed
  Trellis planning artifacts before implementation approval or task start.
- Run an optional read-only native `codex exec` peer review in parallel with
  Claude's host review, reconcile all concerns explicitly, and degrade cleanly
  when the Codex CLI is unavailable or fails.

## 0.42.0 - 2026-07-23

- Add a Claude-only native Codex CLI peer lane to normal `sd-review-local`
  scopes, running it concurrently with the selected Prism, Gito, or configured
  runner stack and joining verified findings before fix selection.
- Preserve runner-only fallback for missing, incompatible, failed, or
  full-codebase Codex review without requiring or patching the OpenAI Codex
  Claude plugin.

## 0.41.0 - 2026-07-23

- Remove the duplicate R-prefixed Trellis roadmap inventory from `sd-status`
  and advance its machine-readable report schema to version 2.
- Route unmatched task-like items from bounded roadmap sources into the
  existing F-prefixed follow-up list with deterministic source evidence and
  exact Trellis task deduplication.

## 0.40.0 - 2026-07-23

- Add a schema-versioned housekeeping result that composes the existing
  exact-head eligibility receipt and delegated status report with stable
  cleanup action and anomaly codes.
- Shorten `sd-housekeeping` around that typed runtime contract and move rare
  `sd-update-spec` architecture, repository-map, and knowledge-base mechanics
  into flat, conditionally loaded references.

## 0.39.0 - 2026-07-23

- Consolidate design-first backlog work into typed `sd-work-backlog`
  `selector=needs-design` and `until=design|merge` arguments, retiring the
  separate `sd-work-designs` command without an alias.
- Route stopped, red, missing-ledger, stale-owner, and terminal-reconciliation
  states through deterministic helper reason codes and conditional recovery
  references so healthy runs avoid rare recovery prose.

## 0.38.0 - 2026-07-23

- Add a deterministic, versioned audit-charter applicability router with a
  non-removable standard core, additive dimensions, transparent evidence, and
  fail-safe exhaustive fallback.
- Replace legacy quick/deep audit depths with `standard|exhaustive`, enumerate
  every charter's coverage state, and calibrate standard routing against UI,
  database, API, infrastructure, dependency, and release fixtures.

## 0.37.1 - 2026-07-23

- Make `sd-review-learnings` observably read-only by default, constrain local
  updates to canonical repository-contained UTF-8 files, and require an exact
  structured confirmation for exceptional external writes.
- Add atomic target revalidation and structured mode, containment, digest,
  finding, change, and write-status reporting without staging or publishing
  learning updates.

## 0.37.0 - 2026-07-23

- Add a private, atomic fleet campaign controller with deterministic
  `plan`/`next`/`record`/`status`/`resume`/`validate` operations, exact-release
  and exact-head receipts, bounded retries, interruption reconciliation,
  canary/wave enforcement, and single-candidate merge execution.
- Reduce `sd-fleet-refresh` to controller action ownership and exception
  interpretation, with rare recovery and corrective-release mechanics loaded
  only when needed instead of keeping the rollout state machine in prompt prose.

## 0.36.0 - 2026-07-23

- Add a validated portable structured-question registry, generate
  `AskUserQuestion` guidance only for capable Claude adapters, and preserve
  concise interactive fallbacks plus explicit noninteractive behavior for
  help, review, backlog, audit, retro, spec, PR, and finish-work decisions.

## 0.35.0 - 2026-07-23

- Expand `sd-status` with deterministic F-prefixed follow-ups, complete
  T-prefixed unarchived task inventory, and R-prefixed top-level roadmap work,
  preserving explicit empty sections and structured report-local selectors.

## 0.34.1 - 2026-07-23

- Add a registry-driven command-surface drift lint with exact-line JSON
  findings, reasoned historical allowances, canonical retirement footprints,
  and maintainer-gate coverage for stale names and missing targets.

## 0.34.0 - 2026-07-23

- Generate a capability-driven, fail-closed checkout-trust preflight for every
  execution-capable command adapter, with `sd-help` as the sole non-executing
  trusted-static exemption.

## 0.33.0 - 2026-07-23

- Centralize exact-head pull-request eligibility in a versioned read-only
  evaluator, keep housekeeping as the sole merge mutation owner, and route
  classified dependency updates through that shared gate.

## 0.32.2 - 2026-07-23

- Fail closed when changed Trellis task-context manifests contain malformed
  non-empty JSONL rows instead of silently skipping them.

## 0.32.1 - 2026-07-23

- Preserve review-learning path-family and test-harness signal classification
  for repositories using either `test/` or `tests/`.

## 0.32.0 - 2026-07-23

- Validate optional Trellis task priority provenance with deterministic,
  redacted diagnostics, and retain executable coverage that archived task
  evidence may reference later-deleted paths while live PRDs may not.

## 0.31.0 - 2026-07-22

- Reject changed deferred Trellis tasks whose bases are not grounded in their
  parent's durable or active branch, and require changed active parent PRDs to
  reference every declared child without disrupting intentional stacks or
  unchanged history.

## 0.30.8 - 2026-07-22

- Run deterministic review preflight in `sd-create-pr` before staging or
  pushing, and reject changed Trellis task-context references outside spec and
  task research roots before publication.

## 0.30.7 - 2026-07-22

- Keep the full-check Obsidian KB freshness lane strict for broken root
  symlinks and occupied non-directory roots in auto mode.

## 0.30.6 - 2026-07-22

- Make the missing finish-work attestation diagnostic resolve the tracked local
  branch after finish-work instead of suggesting the stale pre-finish commit.

## 0.30.5 - 2026-07-22

- Accept legacy task directory names inside month-bucketed Trellis archives
  while keeping active task directories date-prefixed.

## 0.30.4 - 2026-07-22

- Remove equivalent unmanaged Obsidian KB ignore rules when refreshing an
  existing managed block, and make live fleet refreshes run each consumer's
  declared deterministic preparation commands before the local gate.

## 0.30.3 - 2026-07-22

- Make changed non-planning Trellis task metadata trigger sibling context
  scaffold validation, matching the documented review-preflight contract.

## 0.30.2 - 2026-07-22

- Document the intentional best-effort cleanup in the installed PR-body scope
  helper so CodeQL accepts the copied payload without behavior changes.

## 0.30.1 - 2026-07-22

- Require an exact current-head finish-work attestation before housekeeping can
  auto-merge an open PR, while preserving cleanup-only and already-merged
  operation without the attestation.

## 0.30.0 - 2026-07-21

- Keep current unresolved review comments individually actionable while
  deterministically deduplicating historical comments into bounded,
  evidence-backed signal clusters with category-specific preventive actions.

## 0.29.0 - 2026-07-21

- Replace the generic first-review boundary warning with a deterministic,
  configurable six-category regression matrix that emits bounded
  good/base/failure prompts, scans executable workflow YAML, and excludes
  test, fixture, generated, vendored, and installed-mirror paths.

## 0.28.0 - 2026-07-21

- Make housekeeping create or refresh `.obsidian-kb`, preserve valid root
  directory symlinks, reject invalid root paths before writes, and manage the
  root with an anchored ignore rule that covers directories and symlinks.

## 0.27.0 - 2026-07-21

- Preserve GitHub's auto-filled PR summary while automatically appending the
  required tooling/generated scope section for fully classified bookkeeping
  branches before standalone or `sd-ship` review handoff.

## 0.26.1 - 2026-07-21

- Reject completed Trellis journal sessions that claim successful validation
  while retaining the default no-validation Testing fallback, and route
  non-deferred PR review through the safe SD finish-work recorder wrapper.

## 0.26.0 - 2026-07-21

- Add a diff-scoped review-preflight guard for Trellis task identity,
  lifecycle, branch-target, layout, and reciprocal parent/child metadata while
  grandfathering untouched historical records.

## 0.25.5 - 2026-07-21

- Make full-check Prism review local-first: when tracked staged or unstaged
  changes exist, review each non-empty local layer and defer the committed
  branch range, avoiding a redundant paid scan during iteration.

## 0.25.4 - 2026-07-21

- Let the default full-check repair and recheck an existing ignored stale
  Obsidian KB once, while keeping required mode and unignored state read-only
  and fail-closed.

## 0.25.3 - 2026-07-20

- Remove the unused terminal reconciliation pull-request normalizer parameter
  so the helper signature reflects its value-only validation contract.

## 0.25.2 - 2026-07-20

- Restrict the first-review boundary-risk token scan to production source so
  conventional test harness files do not create subprocess, filesystem, or
  environment advisories for behavior they only exercise.

## 0.25.1 - 2026-07-20

- Reject generated `_example` scaffold rows in diff-changed Trellis task
  context files even while a task is still planning, without scanning
  untouched historical context.

## 0.25.0 - 2026-07-20

- Keep fleet canaries sequential, then schedule independent post-canary
  refresh work in manifest-configured bounded waves while serializing gated
  merges in deterministic manifest order.

## 0.24.8 - 2026-07-20

- Report a verified terminal reconciliation attached to a non-terminal run as
  an invalid `terminalReconciliation` record without mislabeling its valid
  nested status.

## 0.24.7 - 2026-07-20

- Require an already-recorded concrete base branch before treating an
  unchanged shipped SHA as historical evidence during work-loop recovery.

## 0.24.6 - 2026-07-20

- Distinguish active and stale terminal reconciliation locks so stale-lock
  failures point operators to explicit `reconcile-terminal
  --recover-stale-lock` recovery instead of waiting for an abandoned owner.

## 0.24.5 - 2026-07-20

- Fixed work-loop checkpoint recovery after a verified squash merge so a
  later default-branch advance can retain the historical shipped feature SHA
  without weakening merge-boundary or changed-SHA ancestry validation.

## 0.24.4 - 2026-07-20

- Teach Copilot that source-only fleet helpers and source-workflow documentation
  are intentionally absent from consumer manifests, and require receipt,
  provenance, and install-audit evidence before reporting a missing-file defect.

## 0.24.3 - 2026-07-20

- Reject malformed pull-request URLs, including invalid ports and malformed
  IPv6 authorities, without leaking `urllib.parse` exceptions from work-loop
  ledger or status-snapshot validation.

## 0.24.2 - 2026-07-20

- Route `sd-review-pr` through a deterministic helper that honors a
  repository-owned `check:full` prelude, preserves the direct pack-script
  fallback, disables Prism/Gito on both paths, and rejects recursive wrappers.

## 0.24.1 - 2026-07-20

- Keep work-loop checkpoints as lifecycle overlays and recover paused ledgers
  atomically from complete, locally verified forward evidence, with explicit
  schema-v1 fallback for legacy human-only checkpoint targets.

## 0.24.0 - 2026-07-20

- Add a fail-closed `reconcile-terminal` work-loop operation that records
  preverified external task and PR completion without reviving stopped runs or
  rewriting their historical evidence and counters.
- Surface verified terminal completion as historical in status and
  housekeeping, with exact delivery/bookkeeping PR evidence and no obsolete
  red-checkpoint recommendation.

## 0.23.16 - 2026-07-20

- Record private, resumable fleet stage timing with monotonic elapsed evidence,
  reviewer/CI overlap, retry and critical-path summaries, and no change to the
  authoritative rollout gates.

## 0.23.15 - 2026-07-20

- Classify verified fleet findings by canonical owner so only blocker families
  interrupt the rollout, while deferred and duplicate observations retain
  evidence-backed replies, thread settlement, and one recorded follow-up.

## 0.23.14 - 2026-07-20

- Classify exact fleet refresh heads against verified release, audit,
  provenance, and receipt-bounded diffs so pure integrations skip redundant
  remote implementation-review requests without skipping existing feedback,
  consumer checks, CI, watch, or housekeeping.

## 0.23.13 - 2026-07-20

- Fail fleet preflight before consumer inventory unless the local and remote
  release tag, exact tagged payload, ancestry, and tagged/current full-fleet
  candidate evidence agree.

## 0.23.12 - 2026-07-20

- Batch related fleet-rollout defects into one bounded corrective campaign,
  one release identity, and one canonical full-fleet validation before the
  original rollout resumes.

## 0.23.11 - 2026-07-19

- Include base-branch and last-shipped-SHA evidence in canonical work-loop
  status snapshots, and render every non-null current-state field in the
  direct human-readable status output.

## 0.23.10 - 2026-07-19

- Reject transition task and base-branch values that are non-string or become
  empty after normalization, preserving field-specific diagnostics and leaving
  the phase and persisted ledger unchanged.

## 0.23.9 - 2026-07-19

- Reject optional work-loop snapshot strings that are present but become empty
  after bounded sanitization, while preserving explicit `null` values and
  fail-closing blank terminal diagnostics.

## 0.23.8 - 2026-07-19

- Reject empty or whitespace-only persisted work-loop current-state strings,
  including recorded branch evidence, before a head-only evidence update can
  preserve malformed ledger state.

## 0.23.7 - 2026-07-19

- Preserve bounded diagnostics when a dynamically loaded work-loop helper
  reports an invalid snapshot without an error.
- Allow head-only evidence updates after a recorded local branch is removed,
  while retaining branch-tip consistency checks whenever that ref is
  available and requiring explicit branch evidence to resolve locally.
- Limit the work-loop `transition` CLI to task and base-branch identity fields
  so its help and accepted arguments match the transition contract.

## 0.23.6 - 2026-07-19

- Require reconciliation to supply every non-null recorded current-state field
  before clearing a ready or blocked recovery checkpoint, preventing unrelated
  partial evidence from erasing unresolved contradiction context.

## 0.23.5 - 2026-07-19

- Keep ready or blocked work-loop recovery checkpoints fail-closed until
  reconciliation supplies matching current-state evidence; a phase-only
  observation can no longer erase unresolved contradiction context.

## 0.23.4 - 2026-07-19

- Normalize dynamically loaded active work-loop snapshots to an allowlisted,
  bounded output contract before status JSON or terminal rendering.

## 0.23.3 - 2026-07-19

- Normalize dynamically loaded terminal work-loop snapshots before status
  rendering, discarding untrusted fields and sanitizing bounded diagnostics.

## 0.23.2 - 2026-07-19

- Prevent phase transitions from bypassing work-loop branch, commit, PR, and
  shipped-SHA evidence validation; mutable facts now require the dedicated
  `evidence` operation.
- Validate shipped SHA membership against the recorded branch tip when no HEAD
  was recorded, with a targeted diagnostic when neither source is available.

## 0.23.1 - 2026-07-19

- Remove the expired `REVIEW_PREFLIGHT_PR_BODY` compatibility fallback from
  current shipped `sd-full-check` guidance.
- Guard every manifest-declared skill, command, prompt, and guide source
  against reintroducing the retired variable while preserving historical and
  runtime retirement evidence.

## 0.23.0 - 2026-07-19

- Add an atomic work-loop `evidence` operation for verified same-phase commit,
  pull-request, review-fix, finish-work, and merge updates.
- Keep stable task/base identity and invalid Git ancestry, branch, or PR changes
  fail-closed while letting successful recovery clear obsolete checkpoints.

## 0.22.0 - 2026-07-19

- Add `--if-present` to the shipped Obsidian KB helper so lifecycle workflows
  can refresh an existing KB without opting other repositories into one.
- Make housekeeping refresh generated knowledge after finish-work task
  archival and make the autonomous backlog loop refresh again after any later
  follow-up task creation, with actionable failure handling and one owner per
  lifecycle boundary.

## 0.21.7 - 2026-07-19

- Report completed Trellis tasks stranded outside the archive in `sd-status`
  and fail review preflight with the exact `task.py archive` remediation.
- Ignore archived, non-completed, nested, and symlinked task entries while
  keeping the recurrence scan bounded to direct active-task records.

## 0.21.6 - 2026-07-19

- Validate dynamically loaded work-loop status snapshots before rendering and
  report missing, unsupported, or incomplete shapes as bounded `invalid`
  anomalies instead of printing absent run metadata.

## 0.21.5 - 2026-07-19

- Keep generated GitHub review provenance inside the managed review-learning
  block out of local documentation-path validation while preserving checks and
  line diagnostics for surrounding human-authored content.
- Render remote review paths containing backticks with safe Markdown code-span
  fences and keep managed-marker neutralization intact.

## 0.21.4 - 2026-07-19

- Keep direct `sd-status` local and fleet reads from creating repository-local
  Python bytecode caches while restoring the caller's bytecode setting after
  helper imports.

## 0.21.3 - 2026-07-19

- Reject missing positional `sd-status` repository paths instead of silently
  inspecting an existing parent repository; existing file paths inside a
  repository remain supported.

## 0.21.2 - 2026-07-19

- Rely on `tempfile.mkstemp()` for private temporary-file creation so work-loop
  state writes remain portable when a filesystem does not support `chmod`.

## 0.21.1 - 2026-07-19

- Pin strict UTF-8 decoding for work-loop candidate files so consumer defect
  scanners and locale-independent file-boundary policy agree.
- Document intentional best-effort permission and cleanup suppression in the
  work-loop helper without changing its atomic-write behavior.

## 0.21.0 - 2026-07-18

- Make `sd-work-backlog` a resumable autonomous plan-to-merge controller and
  make `sd-work-designs` its `needs-design` selector, with ordered focus,
  strict focus-only, planning-only stops, operator controls, and bounded
  iteration checkpoints.
- Ship a standard-library, user-local work-loop ledger and lock helper with
  atomic state, repository identity, legal transitions, conservative focus
  evidence, context-health reconciliation, and interruption-safe resume.
- Add trusted nested `sd-ship` results and read-only loop visibility to
  `sd-status` without changing existing review, finish-work, merge, or cleanup
  ownership.

## 0.20.0 - 2026-07-18

- Accept bare primary subjects for retrospective topics, coverage target files,
  fleet consumers, audit dimensions, and status repository paths while keeping
  lifecycle and safety controls explicit and fail-closed.

## 0.19.12 - 2026-07-18

- Narrow the first-review structured-input advisory so routine string
  `.split(...)` calls do not trigger it, while direct CLI argument,
  environment-value, and file-content splits remain covered.

## 0.19.11 - 2026-07-18

- Compare review-size and added-code risk advisories from the branch merge
  base so upstream-only changes do not create false first-review warnings.

## 0.19.10 - 2026-07-18

- Bound first-review risk scanning of untracked code with the existing byte
  limit and warn when oversized files are skipped.

## 0.19.9 - 2026-07-18

- Count all review events for the relevant pull request with GitHub GraphQL's
  bounded `reviews.totalCount` field instead of the first REST page length.

## 0.19.8 - 2026-07-18

- Run `sd-status` repository discovery from the normalized candidate directory
  so file arguments do not retain an avoidable dependency on the caller's
  current working directory.
- Skip the GitHub commit-to-PR API lookup for traditional two-parent merge
  commits while preserving fail-closed evidence checks for squash and rebase
  merges.
- Preserve the reserved Trellis `archive/` task root as non-task state while
  continuing to recognize valid `archive/<month>/<task>/` artifacts.

## 0.19.7 - 2026-07-18

- Add a review-preflight byte-size guard for untracked files so very large
  artifacts are treated as large diffs without loading the full file into
  memory just to count lines.

## 0.19.6 - 2026-07-18

- Add explicit review-preflight regression coverage for Markdown and code-span
  documentation references that use `path.md:line` and `path:line:column`
  anchors.

## 0.19.5 - 2026-07-18

- Resolve `sd-status --repo` when callers pass relative files or other
  non-directory paths inside a Git checkout by probing the parent directory
  before `git -C`. Paths whose parent cannot be used as a repository still
  fail cleanly.
- Clarify first-time fleet profile creation by documenting the intentional
  missing-file path instead of leaving an empty exception block.

## 0.19.4 - 2026-07-18

- Resolve repository status correctly when `--repo` names a file within a Git
  checkout, while continuing to reject missing repository paths.

## 0.19.3 - 2026-07-18

- Exempt forward-looking `design.md` and `implement.md` planning artifacts under
  `.trellis/tasks/` from the review-preflight path-existence check, so a task's
  proposed (to-be-created) files no longer fail the local gate. `prd.md` and
  specs still describe current state and keep the check.
- Extend the review-preflight line-anchor stripper to resolve `~` approximate
  markers (for example `path:~145` and `path:~315-366`) alongside the
  comma-joined multi-ranges added in 0.19.2, so compact citations of existing
  files in PRDs and specs are no longer reported as missing.

## 0.19.2 - 2026-07-18

- Resolve documentation citations that use comma-joined multi-line ranges
  (for example `path:1-2,3-4,5-6`) in the review preflight, so valid anchored
  references are no longer flagged as missing paths. Existing single-range,
  column, and internal-colon citation forms continue to resolve unchanged.

## 0.19.1 - 2026-07-18

- Fail review preflight when changed Trellis task context still contains
  generated `_example` rows after the task enters implementation, while
  preserving planning-time scaffolds and existing archive safety boundaries.
- Report the Git stash count in local, fleet, human-readable, and JSON status
  output without treating saved stashes as an unhealthy working tree.
- Inspect complete GitHub review-learning windows by default, report PR
  inventory/truncation, and support explicit PR-scoped analysis.
- Warn before remote review when changed code adds boundary-sensitive behavior,
  the authored source surface is large, or the diff spans multiple Trellis
  tasks; installed/generated mirrors remain outside the authored threshold.
- Run one read-only PR-scoped review-learning pass after the complete
  `sd-review-pr` cycle, never after individual rounds or again from `sd-ship`.

## 0.19.0 - 2026-07-17

- Add the read-only `sd-status` command across supported adapters, with bounded
  local reports, portable fleet aggregation, explicit cached/refreshed
  ref labels, schema-versioned JSON, pack/Trellis version visibility, and
  evidence-backed numbered next steps.
- Ship the fleet parser to consumers and add an opt-in machine-local profile so
  `sd-status fleet` can locate canonical versioned fleet policy from any
  installed repository while preserving per-machine checkout path overrides.
- Add `install.py --configure-fleet` with dry-run, profile validation, atomic
  writes, and preservation of existing checkout overrides; ordinary installs
  and status collection remain free of user-global side effects.
- Make housekeeping delegate final Git, GitHub, Trellis, anomaly, and next-step
  reporting to the shared status collector in strict mode while preserving its
  existing merge and cleanup safety gates.

## 0.18.0 - 2026-07-17

- Add the read-only `sd-help` command across supported adapters, with
  list/explain/compare/recommend/examples/tour modes, honest runtime
  availability labels, bounded workflow recommendations, and copy-ready native
  invocations.
- Generate the help catalog and all shared-reference fanout from a validated
  command/family registry so command names, descriptions, source-only policy,
  adapters, and installed skill resources cannot drift independently.
- Make fleet candidate checks representative of generated repository metadata
  and isolate npm, uv, and Python bytecode caches during disposable validation.

## 0.17.0 - 2026-07-17

- Separate `sd-ship` publication and review ownership: Stage 1 now delegates
  an internal publish-only `sd-create-pr` flow and Stage 2 runs review exactly
  once according to the selected stop-point.
- Keep standalone `sd-create-pr` behavior unchanged and reject user attempts
  to select the composite-only orchestration context before any side effects.

## 0.16.2 - 2026-07-17

- Keep standalone `sd-review-pr` and `sd-ship until=review` finish-work
  behavior while allowing the merge-through composite to defer finish-work to
  Stage 4.
- Run the composite watch stage with its existing `no-merge` mode so
  `sd-housekeeping` owns finish-work, merge, and cleanup exactly once, and a
  blocked watch leaves the active Trellis task available for resume.

## 0.16.1 - 2026-07-17

- Fail the generic review preflight when changed `implement.jsonl` or
  `check.jsonl` files in newly completed or archived Trellis tasks still
  contain generated `_example` seed rows.
- Check both context siblings when `task.json` marks completion while
  grandfathering untouched historical archives, active planning scaffolds,
  and symlinked context files.
- Identify SD pack source checkouts by the parsed manifest name rather than the
  generic presence of `install.py`, `manifest.json`, and `templates/`, so other
  installer repositories skip SD-only drift and hook checks.
- Fail conservatively, with a controlled diagnostic, when a malformed manifest
  asserts the SD identity or omits the fields required by the source gate.
- Explain when the source-hook advisory cannot verify pack identity because
  Python is unavailable instead of silently skipping hook configuration checks.

## 0.16.0 - 2026-07-17

- Added read-only installer self-inspection with human and schema-versioned
  JSON output: `--status` optionally runs the install audit, while `--check`
  always audits and returns exit `3` when a valid target needs a refresh.
- Validate installed receipts and vouched hashes before classifying a target,
  report installed and active platform adapters, and preserve the target
  byte-for-byte during every inspection mode.
- Removed the expired `REVIEW_PREFLIGHT_PR_BODY` compatibility fallback; use
  `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` or the dedicated PR-body-scope variable.

## 0.15.8 - 2026-07-17

- Surface the tooling/generated PR-scope requirement early. `review-scope.sh`
  gains an `advisory` mode (`SD_AI_COMMAND_PACK_SCOPE_CHECK=advisory`) that
  classifies the working/branch diff and, when a scope-requiring file is
  present, warns naming the required PR body section (e.g.
  `Tooling/generated scope:`) with no `gh`/PR lookup and no failure. The shared
  review preflight now runs this advisory, so the local pre-PR gate reminds the
  author to add the section before the PR exists. The full-check hard-fail with
  a PR present is unchanged; `off`/`disabled` now also disable the checks.

## 0.15.7 - 2026-07-17

- Fixed `sd-ai-command-pack-housekeeping.sh` flagging a false
  "remote source branch still tracked" anomaly (nonzero exit) after a clean
  merge on remotes with GitHub's auto-delete-head-branch enabled. The branch
  is removed server-side at merge time, after the initial fetch/prune; the
  "already absent" cleanup path now prunes the stale local tracking ref so the
  final verification passes.

## 0.15.6 - 2026-07-16

- Add an explicit fast-canary fleet order and repo-owned lightweight
  compatibility checks, with anomaly-metric-creator last.
- Validate release candidates in disposable consumer-origin clones and require
  a payload-bound all-pass ledger before release PRs can merge or tags can be
  created.
- Document the rollout interruption threshold and keep consumer refresh review
  focused on installation, provenance, integration, and repo-owned changes.
- Make `sd-create-pr` pass custom Markdown bodies through literal temporary
  files and `--body-file`, preventing shell expansion of body content.
- Keep fleet payload digest framing uniform and make exact-commit tag checks
  resolve supported in-repo manifest symlinks like candidate validation does.
- Prevent candidate subprocess environments from adding an implicit
  current-directory search when the inherited `PATH` is empty.

## 0.15.5 - 2026-07-16

- Make the install audit's optional upstream-manifest read explicitly use
  strict UTF-8 decoding, preserving its existing advisory-only failure path
  while satisfying repository encoding-policy checks.
- Add regression coverage for malformed UTF-8 upstream manifests.

## 0.15.4 - 2026-07-16

- Route every shared SD skill invocation of a pack-owned Python helper through
  the shipped toolchain selector, preventing older system `python3` binaries
  from failing on the pack's Python 3.10+ syntax.
- Add regression coverage that rejects direct
  `python3 scripts/sd-ai-command-pack-*` invocations in shared skill templates.

## 0.15.3 - 2026-07-16

- Convert shared Git/GitHub helper `CommandError` failures in the shipped
  review-learnings command into its existing phase-tagged diagnostics and exit
  code `2` instead of leaking Python tracebacks.
- Add focused regression coverage for both local Git scanning and GitHub
  comment collection failures.

## 0.15.2 - 2026-07-16

- Make all variable-path cleanup in the shipped shell review and full-check
  tooling option-safe with `rm -f --`, including every temp-file path surfaced
  by fleet PR review.
- Add a regression guard that rejects unguarded variable-path `rm -f` cleanup
  in shipped shell templates.

## 0.15.1 - 2026-07-16

- Made `sd-fleet-refresh` a source-checkout-only operator command because it
  depends on the pack's installer, fleet registry, and rollout procedure.
  Consumer refreshes now retire vouched copies shipped by earlier releases,
  while the pack source checkout keeps its generated command surfaces.

## 0.15.0 - 2026-07-16

- Added a distributed review-preflight guard that treats Trellis journal
  history as append-only relative to the review base. It rejects accidental
  edits, removals, and renumbering of older sessions while allowing the newly
  appended/current session to be completed, preventing broad repeated-text
  replacements or whole-workspace deletion from corrupting historical records
  before remote review.
- Review-learning summaries now truncate at word boundaries while honoring
  their configured length limit.

## 0.14.2 - 2026-07-16

- Resolved audit-roadmap cleanup items: generated install receipts no longer
  pretend to have a manifest template source, installer apply can reuse
  preflight source bytes/digests, provenance prefers install-result digests,
  and review-scope fallback docs now name the `0.16.0` removal target.
- Documented coverage.py exemptions for shell/GitHub automation and corrected
  historical 0.7.1-0.7.4 changelog dates against the release tags.

## 0.14.1 - 2026-07-16

- Added a shipped `sd_ai_command_pack_lib.py` helper for common Python script
  behavior, moved four shipped helpers onto the shared git/command runner, and
  shared the shell `have()` probe through the shell helper.
- Hardened pack git/gh/Trellis subprocess calls with bounded timeouts and
  clearer timeout diagnostics in installer, audit, full-check, and
  housekeeping paths.
- Added manifest-backed scanner coverage so PR-body scope and install-audit
  static path tables fail tests when shipped manifest targets drift.

## 0.14.0 - 2026-07-16

- Restored the remote PR review round limit default to five
  (`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT`; it was reduced to two in
  0.9.0 — the env var still overrides).
- Added review-cycle counters to the reports: `sd-review-pr` now reports
  `Remote review rounds used: <n> of <limit>` as a mandatory row, and the
  `sd-housekeeping` final state gains a mandatory `PR review rounds:` row
  (submitted reviewer review count for the merged/confirmed PR, or `n/a` on
  verification-only runs).

## 0.13.3 - 2026-07-16

- Hardened pack text writes: generated installer text files now report
  symlink conflicts instead of replacing in-repo symlinks, and the shipped
  recorder, review-learnings, and update-spec KB helpers write user-facing
  markdown/ignore files through temp-file + `os.replace` atomic writes. The KB
  refresh reports symlinked ignore files as partial refresh conflicts instead
  of silently writing through or replacing them.

## 0.13.2 - 2026-07-16

- Batched install-audit `git check-ignore` probes so each audit phase resolves
  candidate ignored paths with one `git check-ignore --stdin -z` subprocess
  instead of one subprocess per missing or unlisted pack-shaped path. Existing
  fail-closed behavior is preserved for missing git, non-repo roots, git
  errors, and the `check-ignore` exit-code-1 no-match case.

## 0.13.1 - 2026-07-16

- P3 polish batch from the 2026-07-15 audit (nine items). Shipped-payload
  changes: the review preflight's git subprocess calls now set an explicit
  64 MiB buffer and fail hard when git cannot run instead of proceeding with
  an empty diff; the preflight also caches its documentation file list and
  file reads per run; typing-only fixes in the session recorder and install
  audit. Repo-side: the install.py facade drops 42 unused re-exports, the
  installer modules gain responsibility docstrings, the REVIEW_PR_REMOTE_*
  variables are documented in the configuration references, review-learnings
  gains git-failure and untracked-diff tests, `make sync` wraps the dogfood
  install and KB refresh, `STRICT=1 make lint` turns missing-tool skips into
  errors, and mypy now covers install.py and the shipped scripts.

## 0.13.0 - 2026-07-16

- Generated the bespoke Claude/Gemini/GitHub command adapters and all derived
  manifest command entries from a single registry command list
  (`make generate` + a drift test); adding a command is now a skill, a neutral
  body, and one list entry. One-time canonical manifest reordering; entry set
  unchanged.
- Merged `sd-review-local-all` into `sd-review-local` behind the `all`
  argument (same runner, `--full-codebase`). The old command is removed;
  refreshes delete the retired installed files automatically when their
  content is vouched by prior provenance (drifted copies are preserved unless
  `--force`). Invoke `sd-review-local` with `all` for the full-codebase loop.
- Added `sd-ship`: a composite orchestrator sequencing the sd-create-pr flow,
  the sd-review-pr loop, the sd-watch-pr settle watcher, and the
  sd-housekeeping merge gate with `until=pr|review|merge` stop-points. It adds
  no new gate logic; every stage's own gates remain authoritative.

## 0.12.0 - 2026-07-16

- Added six distributed SDLC edge-loop commands, each with the full adapter
  surface and format-drift tests: `sd-watch-pr` (bounded PR settle watcher
  handing off to the housekeeping merge gate), `sd-fix-ci` (red-CI triage that
  classifies real/flake/infra failures and never weakens tests), `sd-update-deps`
  (sequential gated triage of dependency-bot PRs; majors always manual),
  `sd-fleet-refresh` (consumer fleet rollout per the documented procedure, one
  consumer at a time), `sd-test-gaps` (coverage-driven test authoring, test
  files only), and `sd-retro` (structured debug retrospectives recorded to the
  journal with consent-gated prevention proposals). All tuning is via command
  arguments — no new environment variables — and merge-affecting behavior
  defers to the existing housekeeping gate criteria.

## 0.11.0 - 2026-07-15

- Added the distributed `sd-audit-repo` command and shared skill: a formal
  multi-dimension repository audit that dispatches one read-only reviewer per
  charter (12 always-on dimensions plus fingerprint-selected consumer-impact,
  observability, and accessibility-i18n), adversarially verifies findings,
  reconciles them against the Trellis backlog, and produces a canonical report
  with mandatory sections backed by a committed findings ledger at
  `.trellis/audit/ledger.md`. Supports `dimensions=` filtering,
  `depth=quick|standard|deep`, and a `follow-up` mode that re-verifies open
  ledger items instead of re-sweeping the repository. The review preflight
  treats `.trellis/audit/ledger.md` as an optional documented path so repos
  that have not yet run their first audit pass the documentation path check.

## 0.10.5 - 2026-07-15

- Made the `sd-housekeeping` skill always report the current Trellis task and a
  `Next Steps` section listing the next high-value Trellis tasks / roadmap items,
  including on verification-only clean runs. Previously the report could end with
  "No follow-up needed for this cleanup stream." and omit the task inventory, so
  the end-of-run handoff format was inconsistent across repos. Documentation only
  — no command, flag, or script behavior change.

## 0.10.4 - 2026-07-15

- Internal micro-refactors of shipped helpers (no behavior change): unified the
  review-learnings git-command wrappers behind one runner, and precompute the
  PR-body scope rule's normalized glob patterns at rule-build time instead of
  re-normalizing them on every path match. Byte-identical output and exit codes.

## 0.10.3 - 2026-07-15

- Internal consolidation of shipped helpers (no behavior change): deduplicated
  the three inline git wrappers in the update-spec KB tool behind one helper,
  compute the source→destination mapping once per run instead of four times, and
  simplified the review-learnings GraphQL response walk. Byte-identical output
  and exit codes.

## 0.10.2 - 2026-07-14

- Trimmed the installed guide's verbatim per-platform `.gitignore` example to a
  single representative block plus a note that the installer regenerates the
  full per-platform set, and removed README prose that duplicated the guide's
  "Updating the pack" and "What is installed" sections. Documentation only — no
  command, flag, or behavior change; ~240 fewer lines across README and the guide.

## 0.10.1 - 2026-07-14

- Replaced the update-spec KB dry-run/`--check` conflict classification — which
  matched human-readable message suffixes — with structured issue kinds, so
  editing a display string can no longer silently change which entries count as
  conflicts. Emitted text and exit codes are unchanged.
- Micro-efficiency in shipped helpers (no behavior change): hoisted the KB
  category-title lookup out of the directory-walk loop, removed a duplicate
  `git status` on the session recorder's no-new-journal fallback, and made the
  review-learnings shell-shebang probe split once and cache its verdict per path.

## 0.10.0 - 2026-07-14

- Made remote PR review rounds use GitHub's documented Copilot request identity
  and require author-matched review activity before counting a request as
  materialized.
- Added plan-before-apply installer conflict handling, concurrent-run coverage,
  rollback guidance, and an optional fail-soft consumer version comparison.
- Hardened CI with SHA-pinned actions, bounded dependency updates, installer
  mypy coverage, OpenCode syntax checks, and a server-side direct-main scope
  backstop.
- Closed shell and housekeeping reliability gaps around disjoint histories,
  interrupt cleanup, delimiter parsing, default-branch detection, and per-user
  review-tool caches; refreshed contributor and security documentation.

## 0.9.2 - 2026-07-14

- Backfilled the missing release ledger and historical version tags since
  `v0.6.0`.
- Required every manifest version bump to add a matching top changelog release
  heading, and added post-CI automation that creates the corresponding tag on
  `main`.

## 0.9.1 - 2026-07-14

- Migrated the exact legacy Claude adapter ignore sequence into the managed
  `.gitignore` block without changing later project-owned overrides.
- Excluded generated Repomix maps from legacy-reference scans while retaining
  scans of their source documentation.

## 0.9.0 - 2026-07-11

- Added a distributed, Bash 3.2-compatible toolchain preflight that selects and
  verifies a supported Python once, reports project-check candidates without
  executing them, and provides deterministic JSON diagnostics.
- Updated SD workflow guidance to separate project checks, pack full-checks,
  and optional AI review while avoiding nested Git writes during finish-work.
- Reduced the default remote PR review loop from five rounds to two while
  retaining the environment-variable override for exceptional review cycles.

## 0.8.7 - 2026-07-09

- Bounded Prism and Gito provider calls, capped repeated Prism fallback
  failures, and tightened empty-response detection and Prism rules validation.
- Hardened the direct-main pre-push guard for rename and unusual-filename
  handling with NUL-delimited Git paths and behavioral coverage.
- Replaced installer wildcard imports with explicit public surfaces, restored
  Ruff import checks, and enabled import-order and Bugbear lint rules.

## 0.8.6 - 2026-07-09

- Fixed rollout CI blockers by classifying the installed pack manifest as
  generated SD command-pack state in review preflight and scope checks.
- Reworded shipped Copilot guidance and remove-mode docs to avoid optional
  directory/glob examples tripping consumer narrow-glob preflight checks.

## 0.8.5 - 2026-07-09

- Added a generated installed manifest snapshot and manifest-backed audit
  completeness checks, including explicit `--expected-platform` support for
  fleet refreshes.
- Added checked-in fleet inventory and a source-owned fleet preflight helper
  so at-target repos are skipped before opening refresh PRs.

## 0.8.4 - 2026-07-09

- Single-sourced OpenCode command adapters from the neutral command templates
  and added registry-derived parity coverage for thin command fan-out.
- Reconciled GitHub prompt body drift against the neutral command source and
  strengthened bespoke adapter body-parity tests.

## 0.8.3 - 2026-07-09

- Hardened `install.py --remove` so consumer-editable receipts and provenance
  can discover prior pack files but cannot authorize deletion of `.git/*` or
  arbitrary non-pack repository files, even when hashes match and `--force` is
  set.

## 0.8.2 - 2026-07-09

- Fixed session recorder retry safety for local-only or fresh workspaces where
  `.trellis/workspace/` is still untracked, so reruns patch the pending journal
  entry instead of appending duplicate sessions.

## 0.8.1 - 2026-07-09

- Made the session recorder retry-safe after a post-append staging or commit
  failure, so rerunning finish-work patches the pending journal entry instead
  of appending a duplicate session.
- Reconciled the closed fleet-refresh loop, archived stale rollout acceptance
  criteria, and the duplicate Session 29/30 journal entry.

## 0.8.0 - 2026-07-09

- Added the distributed `sd-work-designs` command and shared skill for working
  through Trellis tasks that still need `design.md` or `implement.md` planning
  artifacts.

## 0.7.5 - 2026-07-09

- Moved shared command adapter bodies to neutral templates and generated the
  OpenCode command surface from those sources.

## 0.7.4 - 2026-07-09

- Consolidated common shell helpers used by the local review runners while
  preserving the shipped script interfaces.

## 0.7.3 - 2026-07-08

- Added maintainer contributor workflow docs and a Makefile for setup, tests,
  linting, audits, and the SD full-check gate.
- Made the shipped full-check script warn in the pack source checkout when the
  `.githooks` pre-push guard is not armed.
- Pinned the OpenCode plugin dependency used by the dogfood platform files.

## 0.7.2 - 2026-07-08

- Fixed installed-guide quick links, documented
  `SD_AI_COMMAND_PACK_REVIEW_PR_SELECTOR`, and made the pack-source full-check
  env-var documentation gate cover shipped skill-only variables.
- Added maintainer guidance that `templates/**` are the shipped payload source
  of truth and replaced stale-prone README per-command platform lists with
  references to the supported adapter mapping.

## 0.7.1 - 2026-07-08

- Hardened `sd-ai-command-pack-review-preflight.mjs`: symlink invocation now
  runs the preflight instead of silently exiting, Node versions below 16.9 get
  a clear error, copied-surface checks include untracked files, workspace index
  parsing tolerates trailing whitespace, and the regular-file-only
  documentation scan behavior is documented.

## 0.7.0 - 2026-07-08

- Added the distributed `sd-work-backlog` command and shared skill for
  sequentially selecting implementation-ready Trellis backlog tasks, completing
  them through the normal `sd-create-pr`/`sd-housekeeping` flow, and recording
  or addressing follow-ups before moving to the next task.

## 0.6.1 - 2026-07-08

- Hardened the `sd-review-pr` wait-for-review step against a remote-review race:
  the completion signal (a reviewer request clearing / a review event) can fire
  before the reviewer's inline review-thread comments are queryable, so an
  immediate thread read can report a false "clean". The skill now waits a short
  settle interval before reading threads and treats the pre-merge unresolved-thread
  re-check (the housekeeping merge guard) as the authoritative clean check, never a
  single post-completion read.

## 0.6.0 - 2026-07-08

- Added the full-check Obsidian KB freshness lane
  (`SD_AI_COMMAND_PACK_FULL_CHECK_KB`) for repos that maintain generated
  `.obsidian-kb/` knowledge folders.
- Made `sd-ai-command-pack-update-spec-kb.py` return exit code 3 when a KB
  refresh is blocked by conflicts that need manual reconciliation.
- Hardened shipped scripts and audits across Bash 3.2 compatibility,
  all-platform install-audit coverage, PR-body scope matching, review-runner
  robustness, recorder/housekeeping behavior, and KB runtime exclusions.
- Added a release guard in full-check so shipped payload changes under
  `templates/**`, the installed usage guide, or `manifest.json` must include a
  manifest version bump.
- Started the release log and tag process at `v0.6.0`; earlier versions remain
  traceable through git history but are not retroactively changelogged here.
