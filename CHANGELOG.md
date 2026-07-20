# Changelog

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
