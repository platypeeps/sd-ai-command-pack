# Quality Guidelines

> Code quality standards for backend and CLI development.

---

## Overview

Prefer small, explicit stdlib Python over framework code. The installer should
remain easy to audit because it writes files into other repositories.

## Forbidden Patterns

- Do not overwrite user files unless `--force` is set.
- Do not overwrite an existing `.prism/rules.json` or report it as a conflict;
  preserve repo-specific review rules during pack refreshes.
- Do not stage, commit, or modify the target repo beyond the manifest-listed
  files.
- Do not duplicate platform install rules in several places; update
  `manifest.json` and let `selected_files()` apply the rules.
- Do not replace structured parsing with ad hoc string parsing for JSON.
- Do not reintroduce install-time legacy or obsolete cleanup in `install.py`;
  legacy artifacts are advisory-only, reported by the install audit's
  `LEGACY_PACK_PATHS` / `LEGACY_PACK_REFERENCES` scans (see
  manifest-and-filesystem.md, Legacy And Obsolete Artifact Advisories).

## Silent Paths Must Say Why

Adopted 2026-07-06. Any code path that intentionally does nothing must print a
one-line reason: a skipped platform install, a no-op refresh, an empty scan,
a disabled or short-circuited gate. Silence is indistinguishable from success
and from breakage. The 2026-07-06 deep review found four independent defects
of this shape (silent marker-miss adapter skips, a review gate exiting 0 via
symlink without running, a learnings scan reporting OK after scanning
nothing, CI staying green over skipped tests).

- Good: `warn "No changed files remain after standard review-scan exclusions; skipping Gito review."`
- Bad: `return 0` out of a gate because a tool or input was missing, with no
  output.

## Audit Charter Applicability Router Contract

### 1. Scope / Trigger

Use this contract when changing
`scripts/sd-ai-command-pack-audit-route.py`, its template twin, the
`sd-audit-repo` shared skill, or calibration tests that decide which charters
standard mode runs.

### 2. Signatures

- CLI: `sd-ai-command-pack-audit-route.py --repo PATH
  [--mode standard|exhaustive] [--dimension CHARTER]... [--json]`.
- Reusable entry point:
  `build_report(repo, mode, dimensions) -> schema-version-1 mapping`.
- Report rows carry charter ID/version, mandatory/optional classification,
  `run|not-applicable|not-selected|failed`, reason code, and bounded evidence.

### 3. Contracts

- The helper is read-only, stdlib-only, and installed beside
  `sd_ai_command_pack_lib.py`. Inventory includes tracked and non-ignored
  untracked files through bounded Git execution.
- Standard mode has a fixed correctness, security, testing, tooling, and
  release-hygiene core. Optional routing derives only from deterministic file,
  language, manifest, dependency, infrastructure, datastore, API, UI,
  deployment, documentation, and component evidence.
- Explicit dimensions are additive. Exhaustive mode runs every canonical
  charter. Output order follows the canonical charter and fingerprint tables,
  independent of filesystem order.
- Manifest reads are bounded, strict UTF-8, regular-file-only, and
  repository-contained. Structured JSON manifests are parsed rather than
  token-matched when their shape controls routing.
- Git, inventory, path, manifest, decode, or classifier failure returns a
  successful `fallback-exhaustive` report whose warning names the failure and
  whose every charter row is `run`. Invalid caller arguments remain exit `2`.
- Human output derives from the JSON fields and prints fingerprints, every
  charter row, counts including zero, and warnings including explicit `none`.

### 4. Validation & Error Matrix

- Missing/non-directory repository or unknown dimension -> controlled exit
  `2`, no traceback.
- Missing Git, non-repository input, unsafe/inventory overflow, symlinked or
  non-regular manifest, oversized/invalid-UTF-8 manifest, or malformed
  `package.json` -> exhaustive fallback with visible reason.
- Standard with absent optional signal -> explicit `not-applicable` for
  stack-bounded charters or `not-selected` for broad charters; never omission.
- Exhaustive or fallback -> all charters `run`; `failed` remains a runtime
  orchestration state applied after dispatch, so preflight starts its count at
  zero.

### 5. Good / Base / Bad Cases

- Good: a React path selects accessibility-i18n; database signals select
  architecture/performance/dependencies; every unselected charter stays in
  the report.
- Base: a small repository runs fewer charters than exhaustive while retaining
  the mandatory core and assurance warning.
- Bad: scan the whole content tree, follow a manifest symlink, infer from model
  memory, or turn a classifier exception into reduced coverage.

### 6. Tests Required

- Mandatory, additive, exhaustive, absent, and fallback routing.
- Representative UI, database, API, infrastructure, dependency, and release
  calibration fixtures comparing standard and exhaustive modes.
- CLI JSON/human/error output, deterministic order, bounded manifest safety,
  root/template parity, manifest install/provenance, and a per-file coverage
  floor.

### 7. Wrong vs Correct

```text
Wrong: malformed package.json means dependencies and UI are not applicable
Correct: malformed routing evidence triggers visible exhaustive fallback

Wrong: dimensions=performance runs only performance
Correct: standard runs its mandatory core and adds performance
```

## Review-Learning Planning Signal Contract

### 1. Scope / Trigger

Use this contract when changing the review-learning scanner's typed planning
output, its private attempt receipt, or a routed-review consumer that turns
historical defect families into current review questions.

### 2. Signatures

- Ordinary JSON scan: `sd-ai-command-pack-review-learnings.py --json` includes
  a nested schema-version-1 `reviewLearning` signal while retaining the
  existing top-level report schema.
- Attempt receipt: add `--planning-attempt ID`, explicit `--github-repo`, and
  either `--github-days` or repeated `--github-pr`; planning mode requires
  `--json` and cannot combine with update, dry-run, or allow modes.
- Optional reuse: `--review-artifact-root ABSOLUTE_PATH` and
  `--planning-cache-ttl SECONDS` store an exact schema-version-1 receipt.

### 3. Contracts

- Reuse the scanner's deterministic historical-family vocabulary. Each bounded
  cluster carries family ID/label, comment/signature counts, PR/time/path
  bounds, representative signature summaries, example references, and
  per-dimension truncation. Never copy full raw comment bodies into the signal.
- Map normalized changed paths to applicable families and expose only those
  clusters as planning inputs. Historical evidence may produce risk questions
  but always reports `confidenceCredit.granted=false`.
- Collect at most once per review attempt. A cache hit must match repository,
  attempt ID, request fingerprint, changed paths, schema, and lifetime and must
  return the cached GitHub watermark without calling GitHub again.
- Bound planning collection to 90 days or 100 explicit PRs, 10 inventory
  pages, 500 Copilot comments, 200 changed paths, a 16-KiB request, and a
  512-KiB receipt. Incomplete pagination is `truncated`, never complete.
- Ordinary scan and planning mode never mutate tracked files, Git, or GitHub.
  The only planning write is an optional atomic mode-0600 receipt beneath a
  real, absolute, current-user-owned mode-0700 directory outside the repo.
- Cache corruption or mismatch causes a fresh bounded read. Authentication,
  rate-limit, network, malformed-payload, or collector failure returns visible
  stale evidence when a matching expired receipt exists, otherwise visible
  unavailable evidence; neither grants confidence. Persist the bounded failure
  receipt so later stages in the same degraded attempt do not rescan.
- Human output derives planning status, source, applicable families, age, and
  limitations from the typed signal. It also reports the durable managed
  snapshot as current, stale, missing, or unknown by comparing its managed
  update date with the newest observed GitHub evidence. Curation remains an
  explicit, separately authorized update.

### 4. Validation & Error Matrix

- Unsafe changed path, attempt ID, repository identity, request size/type,
  cache TTL, or planning argument combination -> controlled exit `2` with no
  collection or write.
- Relative, repository-contained, symlinked, non-directory, permissive, or
  wrong-owner artifact root -> fail before collection.
- Missing, malformed, oversized, permissive, wrong-owner, or schema/request
  mismatched receipt -> cache miss and fresh bounded collection.
- Expired receipt plus successful collection -> refreshed receipt; expired
  receipt plus collection failure -> explicit stale result.
- Unavailable history without a valid stale receipt -> explicit unavailable
  result with zero confidence, a bounded reusable failure receipt when private
  storage is enabled, and no Markdown write.

### 5. Good / Base / Bad Cases

- Good: a state-controller diff selects recent boundary-validation clusters,
  records a bounded live receipt, and reuses it for later stages of the same
  attempt without a second GitHub call.
- Base: a documentation-only diff selects contract/documentation history and
  does not load unrelated boundary or generated-surface clusters.
- Bad: copy every historical comment to provider prompts, treat cache presence
  as sufficient without fingerprint validation, or let unavailable learning
  make a review cleaner.

### 6. Tests Required

- Bounded cluster schema and raw-body exclusion, changed-path family selection,
  truncation/freshness/limitations, and zero confidence.
- One-scan-per-attempt hit, expired refresh, stale fallback, corrupt cache,
  invalid permissions/path, unavailable collector, and no tracked writes.
- Planning CLI argument bounds, explicit PR and time-window collection,
  root/template parity, manifest installation, and per-file coverage floor.

### 7. Wrong vs Correct

```text
Wrong: rescan GitHub independently for local and remote review stages
Correct: collect once and reuse the exact attempt receipt

Wrong: historical comments prove that a current path is safe or defective
Correct: selected history supplies bounded advisory questions with zero confidence credit
```

## Pull Request Eligibility Evaluator Contract

### 1. Scope / Trigger

Use this contract when changing
`scripts/sd-ai-command-pack-pr-eligibility.py`, its template twin,
housekeeping merge behavior, or a workflow that decides whether a pull request
may enter housekeeping's merge mutation path.

### 2. Signatures

- JSON mode: `python3 scripts/sd-ai-command-pack-pr-eligibility.py --input PATH`
- Adapter mode: the same command with `--format shell`, producing a bounded
  shell receipt for housekeeping without transferring policy ownership to the
  shell caller.
- Combined adapter mode: `--format json-shell` emits one compact JSON line and
  the same shell receipt from one evidence collection so housekeeping can
  embed the authoritative result without querying a moving PR twice.
- Input schema major 1 supports `local-branch` and `dependency-pr` evaluation.
- Output schema major 1 reports `eligible`, `blocked`, or `indeterminate` with
  stable reason codes and observed evidence. `pullRequest.headOid` is the
  initial PR observation and additive nullable `pullRequest.finalHeadOid` is
  the completion observation; existing `head` fields retain their mode-specific
  schema-major-1 meanings.

### 3. Contracts

- The evaluator is read-only. It must not merge or approve a PR, push, resolve
  threads, modify labels or branches, update Trellis state, or write repository
  files.
- Every result after PR discovery binds repository identity, PR number, base
  branch, and initial plus final full PR head OIDs. Re-read the exact PR by its
  retained number after collecting evidence; a changed or unavailable final
  head is a retryable `indeterminate` result and cannot inherit prior evidence.
- Collect checks for the evaluated head. Blocking or pending checks are
  `blocked`; skipped and neutral checks are non-blocking, but at least one
  successful check is required.
- Paginate GraphQL `reviewThreads` through exhaustion. Any unresolved thread is
  blocking; malformed, incomplete, unauthorized, rate-limited, or otherwise
  unreadable evidence is `indeterminate`, never clean.
- `local-branch` requires a clean working tree, equal local, remote, and PR head
  OIDs, and finish-work evidence attested for that exact head.
- `dependency-pr` evaluates a classified PR from a clean default branch and
  does not fabricate Trellis finish-work evidence. Its PR head is still read
  twice and must remain exact.
- Routed-review receipt validation belongs to the routed-review integration
  contract. Until that schema is final, do not guess it or mint a local
  bookkeeping exemption in this evaluator.
- `sd-housekeeping` is the only live merge mutation owner. Other workflows,
  including `sd-update-deps`, delegate an eligible candidate to housekeeping
  instead of restating checks, thread, head, or merge policy.
- Housekeeping validates the evaluator's exact eligible receipt, rechecks the
  mutation-boundary head, and passes `--match-head-commit` to `gh pr merge`.

### 4. Validation & Error Matrix

- Unknown schema major, mode, policy value, or malformed JSON -> fail closed
  with an invalid-request result and no external mutation.
- Failed, pending, or absent-success checks -> `blocked` with stable reasons.
- One or more unresolved review threads -> `blocked`, including on later
  GraphQL pages.
- Provider, authentication, rate-limit, malformed-payload, or pagination
  failure -> `indeterminate` and retryable where appropriate.
- Failed, timed-out, malformed, missing, non-string, or non-OID final PR-head
  read -> retryable `indeterminate` with `head_unavailable` and a nullable
  `pullRequest.finalHeadOid`.
- Missing or stale finish-work evidence in `local-branch` -> `blocked`.
- PR head changes between the first and final observation -> retryable
  `indeterminate`, even if all earlier evidence was green.

### 5. Good / Base / Bad Cases

- Good: exact local, remote, PR, and finish-work heads match; the tree is clean;
  a successful check exists; all thread pages are readable and resolved; the
  final head is unchanged.
- Base: a classified dependency PR is evaluated from clean default branch and
  delegated through housekeeping without a Trellis finish-work requirement.
- Bad: green CI is treated as sufficient without direct review-thread
  evidence, or an earlier head's finish-work/review verdict is reused.
- Bad: `sd-update-deps` or another skill invokes `gh pr merge` directly or
  reconstructs eligibility prose independently.

### 6. Tests Required

- Eligible exact-head evaluation with mutation-spy assertions.
- Failed, pending, skipped, neutral, and no-success check combinations.
- Missing and stale finish-work evidence, dirty local state, and local/remote/PR
  head mismatches.
- Multi-page resolved and unresolved review threads.
- Provider/auth/rate-limit failures and malformed JSON/check/thread payloads.
- Unknown schema major, unknown fields, strict mode/policy validation, local
  and PR head changes during evaluation, and every malformed/unavailable final
  PR-head response.
- End-to-end housekeeping delegation for local and dependency modes, proving
  housekeeping remains the only `gh pr merge` owner.

### 7. Wrong vs Correct

```text
Wrong: re-read only the local branch and assume the PR still points to the earlier head
Correct: retain the PR number, re-read that exact PR at completion, and record its final OID independently

Wrong: overload local-branch head.endOid with the final PR observation
Correct: preserve existing head semantics and add pullRequest.finalHeadOid within schema major 1
```

## Housekeeping Result Contract

### 1. Scope / Trigger

Use this contract when changing
`scripts/sd-ai-command-pack-housekeeping-result.py`, its template twin,
housekeeping JSON output, coded housekeeping actions/anomalies, or final status
delegation.

### 2. Signatures

- `bash scripts/sd-ai-command-pack-housekeeping.sh --json` reserves stdout for
  one schema-version-1 result and writes progress/diagnostics to stderr.
- The stdlib result builder receives a delegated status JSON file or explicit
  status failure, optional eligibility JSON, invocation/identity fields, and
  repeatable coded action/anomaly pairs.

### 3. Contracts

- The builder validates and composes evidence only. It does not run Git/GitHub,
  collect status, merge, switch, pull, delete, prune, or mutate Trellis.
- Embed the existing eligibility and status documents without reimplementing
  their policies. Eligibility is `null` when no open-PR evaluation applies;
  status is `null` only with a typed status failure.
- Identity binds repository, start/default/current branches, PR, full heads,
  and finish-work evidence. Actions/anomalies contain lowercase stable codes
  and bounded control-free messages.
- Outcome is exactly `clean|blocked|indeterminate|failed`. Eligibility
  indeterminacy and unavailable evidence remain indeterminate; known blocking
  eligibility, coded anomalies, or status anomalies are blocked; status
  collection failure is failed.
- Human mode remains compatible. The canonical skill interprets structured
  fields and keeps authority, safety, mutation boundaries, and recovery rules
  explicit instead of pinning raw output choreography.

### 4. Validation & Error Matrix

- Unknown schema major, non-object JSON, unsafe/symlinked/oversized input,
  invalid code/message, or contradictory status input/error -> controlled exit
  `2`, no traceback or mutation.
- Valid status with strict anomalies -> typed `blocked` even when no shell
  anomaly was recorded.
- Missing/empty status result with an explicit collector error -> typed
  `failed` result with `status: null` and stable failure reason.
- JSON mode builder failure -> nonzero; never print progress on stdout or infer
  a human clean result.

### 5. Good / Base / Bad Cases

- Good: a merged branch cleanup embeds coded merge/branch/prune actions and a
  clean delegated status report in one machine-readable result.
- Base: default-branch verification has no applicable eligibility receipt and
  still returns a complete clean or blocked result.
- Bad: rerun PR evidence collection for JSON, parse human status lines, or let
  the result builder become a second merge/status policy owner.

### 6. Tests Required

- Clean, blocked, indeterminate, failed, null-eligibility, and missing-status
  classification; invalid schema/code/message/path inputs; CLI error behavior.
- End-to-end JSON stdout/stderr separation plus unchanged human lifecycle,
  exact-head, checks, thread, merge, cleanup, and dry-run tests.
- Root/template parity, manifest/provenance/install coverage, generated skill
  parity, and a per-file shipped-helper coverage floor.

### 7. Wrong vs Correct

```text
Wrong: run status and eligibility twice so the JSON can disagree with the merge receipt
Correct: collect each once, embed its versioned document, and keep Bash as mutation owner
```

## Review Preflight Runtime Contract

### 1. Scope / Trigger

Use this contract when changing
`scripts/sd-ai-command-pack-review-preflight.mjs`, its template twin, or tests
that exercise the generic JavaScript review preflight.

### 2. Signatures

- Command: `node scripts/sd-ai-command-pack-review-preflight.mjs`
- Reusable API: exported helpers such as `runReviewPreflight()` and parser
  helpers may be imported by Node-based tests.
- Internal validator: `validateTrellisTaskPriorityProvenance(record)` returns
  field-relative issue strings and never includes rationale contents.

### 3. Contracts

- The executable entry check must work when the script is invoked through a
  symlink. Compare resolved real paths before deciding whether to run.
- The script requires Node 16.9 or newer and must print a clear version error
  before running checks when invoked with an older supported-parser runtime.
- The module invokes its main routine before lower helper declarations are
  evaluated. Any `const`, `let`, or class binding used by that run must be
  declared above the invocation; lower function declarations remain safe
  because they are hoisted.
- Changed-path detection for copied/generated disclosure must include staged,
  branch, working-tree, and untracked files instead of letting one source hide
  another.
- Diff-size review advisories compare the review base with the complete working
  tree and add untracked regular files. The authored-source threshold excludes
  installed pack/Trellis mirrors, task/workspace records, and known generated
  reports; canonical `templates/**` sources remain included.
- The same selected diff compares its complete file count with the positive
  integer `copilotReviewFileLimit`, which defaults to `300`. Equality passes;
  a greater count warns that GitHub Copilot will not review the diff and tells
  the author to split it before requesting remote review. This check remains
  local and deterministic and never queries GitHub.
- Changed production code that adds structured-input/strict-type, subprocess,
  environment/global-state, path/filesystem, normalization/canonical-evidence,
  or diagnostic/redaction behavior emits one advisory with stable category IDs
  and bounded good/base/failure prompts. The sweep is deterministic, does not
  infer coverage, and must never invoke a review provider.
- Conventional tests and fixtures, vendored/generated directories, installed
  payload mirrors, and known generated review paths remain outside the content
  scan. GitHub workflow YAML participates as executable configuration; other
  declarative YAML remains outside the scan.
- Repositories may add at most 20 literal signals of at most 120 characters to
  each known category through `reviewRiskCategorySignals` in the existing
  preflight config. Invalid category configuration fails closed.
- A routine string `.split(...)` call is not structured-input evidence by
  itself. Preserve explicit parser signals and direct splits of CLI arguments,
  environment values, or file-read results; keep the heuristic conservative
  rather than inferring data flow between assignments.
- More than one changed Trellis task directory emits a soft scope warning so
  unrelated outcomes can be split before remote review.
- Trellis journal sessions present at the review base and older than the newest
  current session are append-only. Compare normalized session blocks against
  the base and fail when an older block changes, disappears, or is renumbered;
  newly appended/current sessions remain editable.
- Completed journal sessions added or amended after the review base must not
  pair a positive validation claim in Summary or Main Changes with Trellis'
  exact `Validation (was )?not recorded for this session.` Testing fallback.
  Point failures at the fallback line and grandfather byte-equivalent baseline
  sessions so a new guard does not require historical journal rewrites.
- Documentation scans intentionally inspect regular files only; symlinked docs
  are skipped so local or generated links do not expand outside the repo.
- Documentation-path checks mask only complete managed `sd-review-learnings`
  blocks because their GitHub paths and comment snippets are remote provenance.
  Preserve newlines for accurate diagnostics, and keep surrounding human text
  plus incomplete marker pairs in the normal local-path check.
- Diff-scoped Trellis task checks inspect every changed `implement.jsonl` and
  `check.jsonl` file regardless of whether its task is planning, in progress,
  completed, or archived. A changed non-planning `task.json` also checks both
  sibling context files. Every non-empty line must parse as one JSON value;
  malformed rows fail with bounded file-and-line diagnostics. Parsed records
  with an own `_example` key fail; rows with a `file` key may reference only
  `.trellis/spec/**` or `.trellis/tasks/**/research/**`; empty and grounded
  context pass. Present
  changed context artifacts outside the active or
  month-bucketed archive layout fail even when the directory entry is a broken symlink;
  archive task directory names remain unrestricted for legacy Trellis compatibility,
  deleted old paths during moves are ignored, and untouched historical and
  symlinked valid-layout context files remain outside the check.
- Diff-scoped Trellis task metadata checks inspect every added or modified
  `.trellis/tasks/**/task.json` without migrating untouched history. Records
  must use the active or month-bucketed archive layout; keep `id` and `name`
  aligned, and when a directory uses `MM-DD-name`, keep `name` aligned with its
  suffix; require `status` to be `planning`, `in_progress`,
  `review`, or `completed`; keep lifecycle timestamps coherent with that
  status; keep `base_branch` non-empty, an optional `branch` distinct from its
  base, and parent/child links present and reciprocal. Stacked branch bases are valid.
  Missing/deleted old paths are ignored during moves, while malformed JSON,
  oversized or unreadable files, unsafe symlinks, invalid layouts, and
  unverifiable linked records fail closed with path- and field-specific output.
- Optional `meta.priorityProvenance` records an intentional priority remap. When
  present it must be a plain object with a valid `sourcePriority` (`P0` through
  `P3`) that differs from the task's current valid `priority`, plus a trimmed,
  non-empty `rationale` of at most 1000 characters. Extra keys are tolerated,
  absence preserves existing behavior, and diagnostics must identify fields
  without echoing rationale text.
- Diff-scoped Trellis task topology semantics inspect added or modified active
  `task.json` files and active task directories whose `task.json` or `prd.md`
  changed. A deferred planning child (`status: planning`, `branch: null`, and a
  valid parent) must use either its parent's durable `base_branch` or that
  parent's non-empty branch while the parent remains active. This preserves
  explicit stacks without treating an unrelated current feature branch as an
  integration target. An in-scope active task with declared children must have
  a bounded regular sibling `prd.md` that references every child as an exact
  task-ID token; tables, dependencies, links, and prose are equivalent, and
  longer IDs do not satisfy shorter children. Deleted changed PRDs fail when
  child metadata remains, while archived PRDs, standalone or branch-assigned
  planning tasks, extra prose references, and unchanged history remain outside
  the semantic gate. Missing, unreadable, oversized, non-regular, or symlinked
  in-scope PRDs fail closed with path-specific output.
- A repository-wide bounded scan inspects regular `task.json` files in direct
  `.trellis/tasks/` children. A record with `status: completed` fails with the
  Trellis archive command; the `archive/` subtree, non-completed records,
  nested paths, and symlinks remain outside the scan.

### 4. Validation & Error Matrix

- Node below 16.9 -> exit nonzero with a concise `requires Node >= 16.9.0`
  message.
- Symlinked script invocation -> run the same checks and print the normal
  summary.
- Untracked copied pack/Trellis surface -> report the copied/generated scope
  warning just like a staged or branch diff would.
- Malformed `.sd-ai-command-pack/review-preflight.json` -> fail the preflight
  without wiping the failure during result-buffer reset.
- Missing `copilotReviewFileLimit` -> use `300`; a positive integer override ->
  apply that boundary; zero, negative, fractional, string, or other invalid
  values -> fail configuration validation without weakening the default check.
- Older Trellis journal session differs from the review base -> fail with the
  session number and direct the author to restore history and edit the intended
  current session by heading.
- Review-base Trellis journal session is deleted or renumbered -> fail as a
  historical-session removal, including when its journal file or the entire
  current workspace disappears.
- New or amended completed session claims successful validation while Testing
  retains an exact no-validation fallback -> fail with the session, fallback
  line, and corrective action; unchanged baseline sessions remain accepted.
- Changed planning/in-progress/completed/archived context owns `_example` ->
  fail with the exact file and line plus grounded-context-or-empty guidance.
- Changed context contains a malformed non-empty JSONL row -> fail with the
  exact file and line without echoing the malformed content.
- Changed task metadata violates identity, lifecycle, branch, layout, or
  reciprocal-link invariants -> fail with the exact `task.json` path and field;
  unchanged historical metadata -> remain grandfathered.
- Changed task metadata is malformed, oversized, unreadable, symlinked, or
  depends on an unsafe/missing/ambiguous linked record -> fail closed rather
  than following the path or accepting unverifiable state.
- Absent priority provenance or a complete declaration with distinct valid
  source/current priorities and a bounded rationale -> pass; a non-object,
  partial, same-priority, invalid-priority, blank-rationale, or oversized-
  rationale declaration -> fail with field-specific output that omits the
  rationale contents.
- Changed deferred planning child uses a base found in neither its parent's
  durable base nor active branch -> fail with the child `task.json`, observed
  base, and allowed parent-derived targets; an intentional parent-branch stack
  -> pass.
- Changed active parent metadata or PRD omits a declared exact child ID, or the
  required PRD is missing or unsafe -> fail with the parent PRD and missing
  child IDs; unchanged or archived PRD drift -> remain grandfathered.
- Completed direct active-root task -> fail with the exact `task.json` path and
  `task.py archive` remediation; archived, planning, in-progress, and symlinked
  records -> pass.
- Untouched historical context or symlinked context -> skip without reading
  outside the repository; changed empty or grounded context -> pass.
- Added boundary-sensitive production code -> warn once with stable category
  IDs and deterministic good/base/failure prompts; do not fail the gate or
  claim that coverage exists.
- Workflow `run:` and `env:` additions -> subprocess and environment entries;
  non-workflow YAML -> no production-risk entry.
- Unknown, malformed, blank, oversized, or over-count configured category
  signals -> fail with the exact config field.
- Routine string tokenization -> no parser/structured-input warning; direct
  `argv`, environment-value, and file-read splits -> retain the advisory.
- A check reaches a lower `const` or class before initialization -> fail the
  executable preflight test; move that binding above the module-level main run.
- Installed mirrors or known generated reports dominate a large diff -> retain
  the total-size warning but exclude them from the authored-source threshold.
- Two changed task directories -> warn to confirm one reviewable outcome or
  split the work.
- Exactly 300 changed files at the default boundary -> pass; 301 changed files
  -> warn with both counts, the Copilot consequence, and split guidance.
- A live changed PRD references a missing local path -> fail; the same
  historical reference in an archived task PRD -> remain accepted after that
  path is deleted.

### 5. Good/Base/Bad Cases

- Good: `node scripts/check-review-preflight-link.mjs` points at the pack
  preflight and still runs the checks.
- Good: a new session is appended while all base sessions remain byte-equivalent
  after line-ending and trailing-whitespace normalization.
- Good: a completed new session records concrete Testing evidence that agrees
  with its positive Summary validation claim.
- Base: a clean repo with no changed paths reports a no-current-diff pass.
- Base: an untouched baseline session with the legacy no-validation
  contradiction remains grandfathered.
- Good: a deferred child targets its active parent's feature branch and the
  parent names that child in a dependency link.
- Good: a task remapped from `P3` to `P2` declares both priorities and a concise
  rationale in `meta.priorityProvenance`.
- Base: an unchanged legacy parent PRD omits a child, so an unrelated branch
  does not become a historical migration.
- Base: an ordinary task omits `meta.priorityProvenance` and retains its current
  metadata behavior; an archived PRD retains a historical path reference.
- Bad: a newly planned child inherits the author's unrelated feature branch,
  or a changed parent PRD mentions only a longer child-ID prefix match.
- Bad: provenance supplies only a rationale, repeats the current priority, or
  uses an unbounded explanation.
- Bad: a broad replacement updates a repeated fallback line in an older journal
  session while adding the intended current session.
- Bad: a new completed session says the full gate passed while Testing retains
  `Validation was not recorded for this session.`.

### 6. Tests Required

- Script invocation through a symlink.
- Node-version helper coverage for below, at, and above the declared floor.
- Untracked copied-surface detection in a real Git fixture.
- Workspace index parsing with trailing whitespace.
- Historical-session comparison in a real Git fixture, including an appended
  session that leaves prior history unchanged, per-line trailing whitespace,
  renumbering, and deletion of a baseline journal file.
- Positive and negative journal-validation fixtures covering new
  contradictions, both exact fallback forms, incomplete/planning-only records,
  failure/skip wording, concrete Testing evidence, line-specific diagnostics,
  and unchanged baseline grandfathering.
- Planning scaffold and malformed-JSONL rejection, multi-file aggregation,
  empty and grounded context acceptance, newly archived seed rejection,
  untouched historical grandfathering, and symlink skipping.
- Valid active, archived, parent/child, and stacked-base task metadata;
  unchanged-history grandfathering; identity, lifecycle, branch, and layout
  rejection; reciprocal-link failures; malformed JSON; and symlink rejection.
- Priority-provenance coverage for absence, valid remapping, extra keys,
  malformed and partial declarations, invalid and identical priorities, blank
  rationale, the 1000-character boundary, and redacted diagnostics.
- Parent-relative deferred planning bases, including durable-base and active-
  branch acceptance; unrelated-base rejection; standalone and assigned-branch
  exclusion; changed-parent and PRD-only child-map drift; exact token
  boundaries; flexible Markdown placement; unsafe PRDs; archived scope; and
  unchanged-history grandfathering.
- Stable first-review risk categorization, good/base/failure rendering,
  overlap deduplication, output/path caps, configured literal signals,
  production-source exclusions, workflow YAML, authored-source exclusions,
  and multi-task directory extraction, plus a real Git fixture covering all
  three advisory types.
- Real-Git file-count coverage at 300 and 301 files, a positive configured
  override, and invalid zero, negative, fractional, and string values.
- Positive CLI/environment/file split cases and a negative routine string
  split case, exercised through both the exported helper and executable
  preflight path.
- Template twin byte identity.
- Generated review-learning remote paths and path-like comment snippets are
  exempt only inside a complete managed block; surrounding human references
  and incomplete marker pairs remain checked with accurate line numbers.
- Real-Git documentation-path coverage proving an active changed PRD fails when
  a referenced path is later deleted while the archived-task equivalent passes.

### 7. Wrong vs Correct

```text
Wrong: import.meta.url === pathToFileURL(process.argv[1]).href
Correct: realpath(import.meta.url path) === realpath(process.argv[1])

Wrong: currentChangedPaths returns the first non-empty diff source
Correct: currentChangedPaths unions staged, branch, working-tree, and untracked paths

Wrong: wait for Copilot to reject an already-published 301-file pull request
Correct: warn locally from the selected diff before requesting remote review

Wrong: replace the first repeated fallback sentence in a whole journal file
Correct: edit content inside the explicit current `## Session <n>:` block

Wrong: reject every historical no-validation fallback when adding a new guard
Correct: reject new/amended contradictions and grandfather unchanged baseline sessions

Wrong: force every deferred planning child onto main or inherit the author's current feature branch
Correct: accept only the recorded parent's durable base or active branch for changed deferred children

Wrong: treat a longer task-ID prefix in free-form PRD prose as a declared child reference
Correct: require each changed active parent's declared child as an exact delimited PRD token

Wrong: infer priority remapping from free-form prose or accept a declaration that repeats the current priority
Correct: declare bounded, field-valid `meta.priorityProvenance` only when the source and current priorities differ

Wrong: require archived task PRDs to keep every historical local path alive forever
Correct: enforce live PRD paths while allowing archived task evidence to retain historical references

Wrong: declare a helper-used `const` below the module-level main invocation
Correct: declare non-hoisted bindings above that invocation
```

## Status Work-Loop Snapshot Contract

### 1. Scope / Trigger

Use this contract when changing the dynamically loaded work-loop boundary in
`sd-ai-command-pack-status.py`, its template twin, or the paired snapshot
schema.

### 2. Signatures

- Adapter: `collect_work_loop(repo: Path) -> dict[str, Any]`
- Validator: `validate_work_loop_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]`
- Helper source: `sd-ai-command-pack-work-loop.py::status_snapshot()`

### 3. Contracts

- Accept lightweight terminal states `none`, `invalid`, and `unavailable`.
- Persisted run states are `active`, `paused`, `stopped`, and `completed`.
- Run snapshots require non-empty string `runId`, `mode`, `selector`, `phase`,
  `focusMode`, and `heartbeatAt`; integer-but-not-boolean `iteration`; string
  list `focus`; dictionary `counters`, `contextHealth`, and `checkpoint`; and
  non-empty `contextHealth.level` plus `checkpoint.state`.
- The canonical helper snapshot emits every current-state evidence field:
  `task`, `branch`, `head`, `baseBranch`, `prNumber`, `prUrl`, and
  `lastShippedSha`. Its human renderer prints each non-null field so direct
  work-loop status and `sd-status` observe the same ledger evidence.
- When the ledger is absent, the canonical helper still emits both `lock` and
  `terminalLock` diagnostics. Each mapping contains `present`, `stale`,
  `runId`, and `error`; an unreadable lock remains `present` with a bounded
  error and no inferred run ID. Keep the two lock sources distinct so the
  typed recovery directive can be executed from one status response without
  reconstructing user-state paths manually.
- A run snapshot may include a complete `terminalReconciliation` audit record
  with verified status, timestamp, archived task path/ID, delivery PR evidence,
  optional all-or-none bookkeeping PR evidence, and observed default
  branch/head. The adapter validates and allowlists the entire nested shape.
  The record is valid only when the top-level run status is `stopped` or
  `completed`; an otherwise valid record attached to `active` or `paused` is a
  cross-field error on `terminalReconciliation`, not on its nested `status`.
  Verified terminal evidence suppresses obsolete red-checkpoint guidance and
  renders external completion separately from loop-owned counters.
- Optional run-snapshot strings may be omitted or explicitly `null`, but when
  present as strings they must remain non-empty after bounded sanitization.
  This applies to top-level evidence and stop fields, checkpoint target/reason,
  checkpoint `resumePhase`, and lock run identity. The helper exposes
  `resumePhase` so direct status and `sd-status` show the lifecycle owner of a
  paused checkpoint consistently.
- Terminal diagnostics must also remain non-empty after sanitization. Missing
  or blank `invalid` diagnostics receive the bounded adapter-owned fallback;
  a blank supplied `unavailable` diagnostic is a malformed terminal field.
- Missing, unsupported, and incomplete mappings become adapter-owned `invalid`
  snapshots. Diagnostics name only the structural field and never echo a
  helper-controlled value.
- Terminal pull-request URLs are bounded parsed input at both the helper and
  status-adapter boundaries. Access to `urlsplit()`, `SplitResult.hostname`,
  and `SplitResult.port` must stay inside a `ValueError` boundary so malformed
  authorities and ports fail closed instead of escaping as tracebacks.
- Valid helper snapshots and their human/JSON rendering remain unchanged.

### 4. Validation & Error Matrix

- Non-dictionary helper result -> `invalid data` anomaly.
- Missing or non-string status -> `snapshot without a valid status` anomaly.
- Unsupported status -> `unsupported status` anomaly without the supplied
  value.
- Missing or malformed run field -> `invalid run snapshot field: <field>`.
- Missing ledger with no locks -> `none` plus `normal` recovery and both lock
  diagnostics present with `present: false`; valid, stale, digest-mismatched,
  or unreadable active/terminal locks -> preserve the corresponding diagnostic
  source while selecting the typed recovery reason.
- Present-but-blank optional run string -> `invalid run snapshot field:
  <field>`; explicit `null` remains valid.
- `terminalReconciliation` on an `active` or `paused` run -> `invalid run
  snapshot field: terminalReconciliation`.
- Nested reconciliation status other than `verified` -> `invalid run snapshot
  field: terminalReconciliation.status`.
- Invalid terminal PR URL syntax, malformed IPv6 authority, or invalid port ->
  helper rejects the PR evidence with its controlled validation error; status
  adapter returns `invalid run snapshot field: terminalReconciliation.<field>`.
- Import, syntax, filesystem, or helper exception -> existing bounded
  `invalid` anomaly behavior.

### 5. Good/Base/Bad Cases

- Good: a complete paused snapshot renders the same run, focus, heartbeat,
  context, checkpoint, and counters as before.
- Base: `{"status": "none"}` remains a valid no-loop result.
- Good: a missing ledger with an unreadable active lock reports
  `owner_invalid`, `lock.present: true`, a bounded `lock.error`, and an absent
  `terminalLock` instead of collapsing the evidence into the reason code.
- Base: an optional run field such as `branch` may be absent or `null`.
- Good: a `completed` run carries a complete reconciliation with nested status
  `verified`.
- Bad: a drifted helper returns `{"status": "active"}` and the report prints
  `None` for required metadata.
- Bad: an active helper returns `{"branch": "   "}` and the report treats the
  sanitized empty value as valid evidence.
- Bad: an `active` or `paused` run carries an otherwise valid reconciliation;
  report the invalid record presence, not its valid nested status.

### 6. Tests Required

- Every accepted terminal and persisted-run status.
- Missing and unsupported status, including proof that the unknown value is
  not included in the error.
- Missing string fields, boolean iteration, mixed-type focus, non-dictionary
  containers, and missing nested renderer members.
- Existing real-ledger JSON and human-output tests plus template twin parity.
- Missing-ledger helper snapshots with no lock, a valid active lock, a valid
  terminal lock, a digest mismatch, and malformed lock JSON; assert both lock
  diagnostic mappings and the selected recovery reason.
- Canonical helper snapshots and human output include all non-null
  current-state evidence, including base branch and last shipped SHA.
- Invalid-port and malformed-IPv6 PR URL regressions at both the work-loop
  normalizer and status terminal-record boundary, asserting no raw
  `ValueError` escapes.
- Cross-field regressions for `active` and `paused` runs with an otherwise valid
  reconciliation, asserting the diagnostic ends in `terminalReconciliation`;
  separately assert an invalid nested status ends in
  `terminalReconciliation.status`.

### 7. Wrong vs Correct

```text
Wrong: any helper-returned dictionary flows directly into the renderer
Correct: validate its status and renderer-required fields at the load boundary

Wrong: return only the recovery reason when the ledger is missing and make the operator rediscover which lock exists
Correct: return bounded active and terminal lock diagnostics alongside the typed recovery directive

Wrong: include an unsupported helper value in the diagnostic
Correct: report only that the status is unsupported

Wrong: validate `split.hostname`, then access `split.port` outside the parse guard
Correct: parse and read all URL authority properties inside one fail-closed `ValueError` boundary

Wrong: blame `terminalReconciliation.status` when the nested status is valid but the record is illegal for the top-level run state
Correct: blame `terminalReconciliation` for cross-field presence errors and reserve `.status` for an invalid nested status
```

## Work-Loop Evidence Reconciliation Contract

### 1. Scope / Trigger

Use this contract when changing `validated_evidence()`, `reconcile_state()`,
merge-boundary evidence, or recovery-checkpoint behavior in
`sd-ai-command-pack-work-loop.py` and its template twin.

### 2. Signatures

- Evidence validator:
  `validated_evidence(state, updates, *, repo=None, phase=None) -> dict`
- Recovery mutator:
  `reconcile_state(state, observations, *, signal=None,
  verified_live_advance=False, explicit_resume_phase=None, repo=None) -> None`

### 3. Contracts

- The feature-to-base branch transition is the merge boundary. A submitted
  `lastShippedSha` must resolve locally and belong to the remembered feature
  branch before branch evidence may change to the base branch.
- After that verified transition, a squash merge intentionally leaves the
  recorded feature SHA disconnected from base-branch ancestry. Complete
  checkpoint recovery may retain that unchanged historical SHA while advancing
  the already-recorded base-branch head.
- The historical exception applies only when `lastShippedSha` resolves to the
  remembered value and the ledger already records a non-empty branch that is
  unchanged and equals both the submitted branch and `baseBranch`. First-time
  branch/head evidence, and new or changed shipped-SHA evidence, still require
  descendant and shipped-branch proof.
- A later base-branch head must remain a descendant of the remembered head;
  task, base branch, PR number, and PR URL remain immutable.

### 4. Validation & Error Matrix

- Feature branch -> base branch with an unrelated shipped SHA -> reject with
  `lastShippedSha evidence must belong to the shipped branch`.
- Missing remembered branch + newly submitted base branch/head + unchanged
  unrelated shipped SHA -> reject with the shipped-branch error.
- Already on base branch + unchanged historical shipped SHA + descendant head
  -> accept and allow complete checkpoint recovery.
- Already on base branch + changed shipped SHA not descending from the
  remembered shipped SHA -> reject with the descendant error.
- Already on base branch + non-descendant head -> reject with the head
  descendant error.
- Partial recovery evidence -> keep the checkpoint and report the existing
  complete-evidence diagnostic.

### 5. Good / Base / Bad Cases

- Good: PR head `F` is squash-merged as `M`; later bookkeeping merge `B`
  advances `main`; recovery records head `B` while retaining shipped SHA `F`.
- Base: a normal merge makes `F` an ancestor of `M`; the same recovery path
  remains valid.
- Bad: after reaching `main`, recovery replaces `F` with unrelated head `B`
  and calls it shipped evidence.

### 6. Tests Required

- Merge-boundary feature-to-base evidence, including squash delivery.
- Paused or blocked same-phase recovery after a squash merge and later
  base-branch commit, using every recorded current-state field.
- Self-anchored or unrelated shipped-SHA rejection.
- First-time branch/head evidence cannot activate the historical exception.
- Changed shipped-SHA descendant enforcement and non-descendant head rejection.
- Template twin byte identity.

### 7. Wrong vs Correct

```text
Wrong: require an unchanged squash-delivered feature SHA to be an ancestor of every later main head
Correct: prove it at the merge boundary, then retain it as immutable historical evidence

Wrong: infer historical branch proof from newly submitted main-branch evidence
Correct: require an already-recorded non-empty main branch before skipping the repeated shipped-branch check; still validate head ancestry and all identities
```

## Session Recorder Retry Contract

### 1. Scope / Trigger

Use this contract when changing `scripts/sd-ai-command-pack-record-session.py`,
its template twin, or the `sd-finish-work` flow that calls it.

### 2. Signatures

- Command:
  `python3 scripts/sd-ai-command-pack-record-session.py --title ... --summary ... --change ... --test ...`
- Trellis dependency: `.trellis/scripts/add_session.py --no-commit`
- Commit behavior: the pack wrapper, not Trellis, stages
  `.trellis/workspace/<developer>/journal-*.md` plus sibling `index.md` and
  commits them as `chore: record journal` unless `--no-commit` is passed.

### 3. Contracts

- The wrapper may call Trellis `add_session.py` only when no modified
  workspace journal already has the requested title as its latest session
  heading.
- If a previous run appended the session but failed during the pack-owned
  staging or commit step, a retry must patch and commit that pending latest
  session instead of appending another one.
- Journal discovery must enumerate untracked files inside `.trellis/workspace/`
  (for example with `git status --untracked-files=all`) because local-only and
  fresh workspaces can otherwise collapse to `?? .trellis/workspace/` and hide
  the actual `journal-*.md` file.
- If more than one modified journal has the requested title as its latest
  session heading, fail closed with a clear error rather than guessing.
- The patcher anchors on session headings, commit hashes, and section headings;
  it must not depend on Trellis placeholder wording.

### 4. Validation & Error Matrix

- Unknown or duplicate commit hash -> exit `2` before touching the journal.
- Trellis append succeeds, later `git add` fails -> exit `1`, leave one
  pending session, and surface git output.
- Retry after the pending-session failure -> exit `0`, reuse the pending
  session, and keep a single journal entry.
- Retry after the pending-session failure with an untracked workspace -> same
  result: exit `0`, reuse the pending session, and keep a single journal entry.
- Multiple matching pending journals -> exit `1` and do not append.

### 5. Good/Base/Bad Cases

- Good: a sandbox or index-lock failure after append can be rerun safely.
- Base: a clean run appends, patches, verifies placeholders are absent, stages,
  and commits one journal/index pair.
- Bad: retrying a post-append failure calls `add_session.py` again and creates
  duplicate consecutive sessions.

### 6. Tests Required

- End-to-end happy path against a Trellis-bootstrapped scratch repo.
- Fail-fast validation for unknown, duplicate, and option-like commit hashes.
- Retry after synthetic `git add` failure proves no duplicate session is
  appended.
- Retry coverage must include both tracked and untracked `.trellis/workspace/`
  states.
- Template twin byte identity.

### 7. Wrong vs Correct

```text
Wrong: rerun add_session.py whenever the previous wrapper command exits nonzero
Correct: detect a modified latest same-title journal session and patch it

Wrong: rely on default git status output for a fully untracked .trellis/workspace/
Correct: enumerate untracked workspace files so journal-*.md remains visible

Wrong: search for "(see git log)" or "(Add test results)" before patching
Correct: replace hash-keyed commit rows and section bodies by structural anchors
```

## Journal-Only Planning Finalization Recovery Contract

### 1. Scope / Trigger

Use this contract when changing `final-bundle --mode planning` in
`sd-ai-command-pack-review-preflight.mjs`, its template twin, or the
`sd-finish-work` retained-result boundary. It covers the narrow case where
planning work was published before finish-work captured its base and the exact
base-to-head delta therefore contains only the successor journal commit.

### 2. Signatures

- CLI remains `final-bundle --mode completion|planning --base COMMIT --head
  COMMIT --json`; journal-only recovery is not a third public mode.
- A successful recovery keeps schema version 1, `mode: planning`, and
  `planning_bundle_valid`, adding only
  `evidence.planningSubtype: journal-only-recovery` and recovered active task
  directories.

### 3. Contracts

- Select recovery automatically only when the exact final range has no task
  entries. Normal task-plus-journal planning and completion validation remain
  unchanged.
- Require exactly one newly completed, index-matched journal session and no
  exact-range paths beyond that journal file and its sibling index.
- Resolve every journal commit uniquely. Each commit must be at or before the
  immutable captured base, have exactly one parent, remain within the bounded
  commit/path limits, and change only regular files below active dated
  Trellis task directories.
- Inspect regular-file modes with one bounded Git tree query per referenced
  commit; never spawn one subprocess per changed path.
- Reject archives, workspace history, code, specs, configuration, deletion,
  rename, copy, Git links, symlinks, roots, merges, unknown objects, and
  non-ancestor commits. A mixed task/non-task commit is invalid in full.
- Aggregate at least one active task directory and verify that each referenced
  commit's task record and its parent-baseline record preserve `status:
  planning`, `completedAt: null`, and `branch: null`.
- Label recovered-commit and recovered-commit-parent artifact read and JSON
  failures with `planning_recovery_commit_*` reason codes and precise
  recovered-work-commit wording; reserve `bundle_base_artifact_*` diagnostics
  for reads from the captured bundle base.
- Recovery proves already-published scope and lifecycle; it does not
  retroactively apply current metadata, topology, context, PRD, or other
  publication-quality content checks to artifacts before the captured base.
  The normal planning bundle retains those complete checks.
- Never widen the captured base, rewrite the preserved journal commit, execute
  referenced content, or infer success from an invalid/indeterminate result.

### 4. Validation & Error Matrix

- Zero or multiple new completed sessions ->
  `planning_recovery_session_count_invalid`.
- Duplicate full commit identity -> `planning_recovery_commit_duplicate`.
- Commit not at or before captured base ->
  `planning_recovery_commit_not_published`; unavailable ancestry evidence is
  indeterminate.
- Root or merge commit -> `planning_recovery_commit_non_linear`.
- Non-task, non-regular, deletion, rename, copy, or oversized commit delta ->
  `planning_recovery_commit_scope_invalid` plus applicable planning findings.
- No qualifying active task delta -> `planning_recovery_task_change_missing`.
- Invalid current or baseline lifecycle -> existing planning lifecycle reason
  codes; no valid result is emitted.
- Missing, oversized, unreadable, non-UTF-8, or invalid-JSON task metadata at a
  recovered work commit or its parent -> a specific
  `planning_recovery_commit_*` diagnostic, never a bundle-base diagnostic.
- Regular-artifact inspection chunks pathspec arguments under a conservative
  cross-platform command-line budget and fails closed if any batch cannot be
  inspected.

### 5. Good / Base / Bad Cases

- Good: two already-published linear planning commits are listed by one new
  journal session; both are task-only and lifecycle-safe, so the journal-only
  tail validates without changing the captured range.
- Base: task artifacts and a journal are both inside the exact range, so the
  existing normal planning validator runs with its full content checks.
- Bad: widen the base to rediscover task changes, treat a merge parent as the
  work delta, or accept a commit because some of its paths belong to a task.

### 6. Tests Required

- Positive normal planning, completion, journal-only recovery, and the
  preserved real-range regression.
- Unknown/non-ancestor and duplicate commits, roots/merges, code/spec/config/
  workspace scope, deletion/rename, non-regular artifacts, invalid lifecycle,
  multiple sessions, and no-task evidence.
- A published-content-debt fixture proving recovery does not become a
  retroactive content audit, paired with existing normal-planning tests that
  retain full validation.
- Root/template byte identity, bounded repository-relative diagnostics, Node
  syntax, a runtime argument-budget batching regression, a recovered-commit
  diagnostic-label regression, focused lifecycle tests, and `make check`.

### 7. Wrong vs Correct

```text
Wrong: change --base until the already-published task commits reappear
Correct: keep the captured range and prove its one journal session's referenced commits

Wrong: rerun today's entire task-content audit over historical published planning artifacts
Correct: prove historical task-only scope and lifecycle while keeping full checks on normal new planning bundles
```

## Read-Only SD Check Runtime Contract

### 1. Scope / Trigger

Use this contract when changing the `sd-check` coordinator, its versioned
configuration/result schema, built-in verification inventory, state guard, or
cache boundary.

### 2. Signatures

- `python3 scripts/sd-ai-command-pack-check.py [--json] [--repo PATH]`
- `.sd-ai-command-pack/check.json` with exact `schemaVersion: 1`,
  `prerequisites`, and `checks` fields.

### 3. Contracts

- Use argv arrays only; reject shell/code strings, remote-review commands,
  unknown fields, duplicate IDs, path escapes, symlink cwd traversal, and
  timeouts outside the documented bound before configured execution.
- Run the closed shipped deterministic inventory followed by configured
  prerequisites and checks in declared order. A prerequisite that is not
  `passed` blocks later configured checks with explicit `skipped` rows.
- Normalize rows to `passed`, `failed`, `skipped`, `unavailable`, `invalid`, or
  `indeterminate`; missing shipped helpers are unavailable, never successful.
- Hash HEAD, symbolic HEAD, refs, index, tracked/nonignored-untracked content,
  and declared ignored generated paths before and after every row. Report any
  delta as failure without reverting it.
- Use `sd_ai_command_pack_lib.py` for sandbox-safe external caches. Never write
  repository caches, refresh generated output, invoke AI/GitHub review, or
  perform publish/lifecycle mutation.

### 4. Validation & Error Matrix

- Passed required rows and unchanged state -> exit 0.
- Check failure or mutation -> exit 1.
- Invalid repository/configuration -> exit 2 before configured execution.
- Missing executable/helper, cache-boundary failure, or timeout -> exit 3 with
  an unavailable or indeterminate row.

### 5. Good / Base / Bad Cases

- Good: stale generated knowledge is reported with its owner command and no
  byte changes.
- Base: absent optional knowledge output is visibly skipped while required
  shipped checks pass.
- Bad: a helper refreshes output, dispatches a provider, or a missing binary is
  counted as passed.

### 6. Tests Required

- Typed status/exit/precedence, strict schema, timeout, cache, and prerequisite
  fixtures.
- Byte/state snapshots for pass, failure, stale output, unavailable tools, and
  deliberate mutation, plus provider/GitHub dispatch sentinels.
- Registry/generated adapter parity, manifest install/audit/provenance, root/
  template parity, per-file coverage, and `make check`.

### 7. Wrong vs Correct

```text
Wrong: run an inferred package script or shell string and hope it is read-only
Correct: validate argv config, run it once, and fail if the state guard changes
```

## Exact-Scope Local Review Stage Contract

### 1. Scope / Trigger

Use this contract when changing the internal local-review stage consumed by the
successor `sd-review` lifecycle, its review configuration, provider planning,
attempt isolation, exact-scope receipts, or pre-remote gate.

### 2. Signatures

- Executable: `scripts/sd-ai-command-pack-review-local.py`.
- Required coordination identity: `--attempt-id ID`.
- Typed controls: `--scope changes|branch|codebase|pr`,
  `--local auto|all|none|PROVIDER`,
  `--successor first|low-risk|high-risk|repeated-family|bookkeeping`,
  repeatable `--finding-family ID`, optional `--family-evidence PATH`,
  `--local-policy optional|required`, and `--fix auto|ask|none`.
- Optional consumer-repository configuration filename:
  **.sd-ai-command-pack/review.json**, schema major 1.

### 3. Contracts

- Resolve one canonical target before provider calls. Branch and PR scopes use
  the same clean `branch_delta` identity, so PR creation alone does not cause a
  second paid call. Any base, head, content, provider, adapter, configuration,
  local/fix policy, finding-family, or other policy change invalidates reuse.
- Treat source, tests, scripts, executable configuration, state/receipt code,
  and ambiguous paths as substantive. A first substantive head selects Prism
  and Gito and starts both isolated attempts before awaiting either. A bounded
  low-risk successor or documentation/metadata change may select the cheapest
  eligible provider. Do not substitute an unselected provider after failure.
- Provider configuration uses validated argv arrays or built-in adapters. Ban
  shell/code strings, bound argv and timeouts, route tool caches through the
  shared external cache helper, terminate timed-out process groups, and keep
  stdout, stderr, and state in separate ignored attempt directories.
- Built-in adapters request each provider's native structured report and map
  that report into the normalized outcome. An exit-zero human transcript or a
  missing/malformed native report fails closed; never infer clean from exit
  status alone. Avoid lossy path serialization, and reject a provider/scope
  combination before dispatch when its CLI cannot encode an exact path.
- Persist an invocation record before dispatch. A partial existing attempt
  fails closed rather than duplicating a paid call. Write receipts atomically,
  and reuse only an exact validated receipt.
- Normalize `clean|findings|unavailable|failed|cancelled|skipped` without
  treating operational failure as findings or positive confidence. Deduplicate
  overlapping findings while retaining every provider identity and original
  provider family. Normalize unknown family labels to the bounded `other`
  family instead of extending the coordination vocabulary implicitly.
- Strict schema-version-1 family evidence binds one lifecycle and current
  round to the exact target head. It carries only bounded finding identity,
  provider, round/head, normalized family, actionability/disposition, fix/audit
  references, completed audit evidence, and approved extension decisions; it
  never copies raw finding text into local-review state.
- Two actionable observations of the same family on distinct rounds select the
  repeated-family Prism/Gito plan and block remote routing until one complete
  family checklist, clean limitation-free local receipt, passing exact-head
  check, at least two unique sibling-finding IDs whose count equals the declared
  batch size, and at most one fix commit are recorded. Different families do
  not share a recurrence counter.
- A later observation of an already-audited family blocks before provider
  execution until the existing `review.round-extension` structured decision is
  recorded for that exact round. Missing, failed, unavailable, incomplete, or
  head-mismatched audit evidence never completes the sibling gate.
- Outstanding findings block remote routing. Optional local policy may pass a
  terminal provider failure forward only as an explicit limitation with zero
  confidence; required local policy blocks. `bookkeeping-successor` skips need
  exact external evidence and always grant zero new confidence.
- The router summary is allow-listed and excludes changed paths, raw findings,
  prompts, transcripts, credentials, configuration values, and local artifact
  paths. This stage never selects or dispatches a remote reviewer.

### 4. Validation & Error Matrix

- Dirty branch/PR target, unsafe path, malformed config, ineligible required
  provider, shell string, unsafe artifact root, or mismatched bookkeeping
  evidence -> invalid before dispatch.
- Malformed, oversized, symlinked, wrong-head, unknown-family, duplicate-ID,
  multi-fix-commit, or unsupported family evidence -> invalid before dispatch.
- Second same-family round without a complete audit -> local sibling-audit plan
  may run, but its remote gate remains blocked until the controller records the
  complete audit bundle. Post-audit recurrence without an approved extension
  -> blocked before another provider call.
- Missing provider -> `unavailable`; timeout or unexpected exit -> `failed`;
  provider finding exit/payload -> `findings`; none becomes clean.
- Same target and plan with a valid receipt -> reuse; a changed exact field ->
  new receipt and provider attempt; a conflicting partial attempt -> stop for
  reconciliation.

### 5. Tests Required

- Prove substantive first-head overlap, artifact isolation, deterministic
  documentation/metadata/ambiguous plans, and low/high/repeated successor
  selection.
- Prove exact branch-to-PR reuse, head/config/policy invalidation, retry
  collision refusal, timeout termination, missing-provider handling,
  provenance-preserving finding deduplication, and optional/required gates.
- Prove same-family versus unrelated-family recurrence, deterministic family
  matrices, failed local-audit behavior, one-commit batching, exact-head
  rejection, post-audit extension gating, and bounded telemetry.
- Preserve template/root parity, manifest installation, per-file coverage,
  release-ledger evidence, and `make check`.

### 6. Wrong vs Correct

```text
Wrong: run Prism, wait, then run Gito and bill both again after PR creation
Correct: start the selected ensemble concurrently and reuse its exact branch-delta receipt

Wrong: a failed provider silently becomes clean or triggers a different provider
Correct: retain the selected provider's failure and apply the declared local floor
```

## Shipped-Surface Closure Contract

### 1. Scope / Trigger

Use this contract when changing registry/manifest payload ownership, generated
platform surfaces, source-only references, checker registration, or release
evidence.

### 2. Signatures

- `python3 scripts/sd-ai-command-pack-surface-check.py [--json] [--base-ref REF]`
- JSON result `schemaVersion: 1` with changed paths, affected graph,
  deterministic finding counts, and owning preparation commands.

### 3. Contracts

- Derive nodes and relations from `installer/registry.py`, `manifest.json`, and
  the existing generator/lint metadata; do not maintain caller-specific globs.
- Inventory committed, staged, unstaged, and non-ignored untracked paths with
  bounded NUL-safe Git commands. Reject unsafe, control-bearing, non-UTF-8,
  symlinked, oversized, duplicated, mistyped, and unknown-schema inputs.
- Classify installable, generated, source-only, documentation-only,
  check-only, retired, and provenance nodes. A source-only reference requires
  an exact `SOURCE_ONLY_SKILL_REFERENCES` record.
- `sd-check`, local pre-publication, and CI must invoke the same shipped helper.
  Human output is rendered from the same typed result as JSON output.
- Report `make generate`, `make sync`, manifest registration, or source-only
  registration as ownership. Never prepare, refresh, stage, or repair state.

### 4. Validation & Error Matrix

- Complete closure and unchanged generated mirrors -> exit 0.
- Missing/stale/duplicate relation -> exit 1 with stable path and relation.
- Unreadable/unsafe/unknown authoritative input -> exit 2 without mutation.

### 5. Tests Required

- PR #237 unregistered source-only reference and PR #234 platform/duplicate/
  type/checker-scope regression fixtures.
- Complete platform fan-out, retired/docs/release node kinds, NUL-safe Git
  layers, symlink/oversize/unsafe/schema failures, deterministic deduplication,
  and stale-state no-mutation evidence.
- Shared caller registration, generated parity, install audit, `make sync`,
  `sd-check`, and `make check`.

### 6. Wrong vs Correct

```text
Wrong: allow every file below a source-only skill directory implicitly
Correct: declare each extra reference and validate the transitive surface graph
```

## Toolchain Preflight Runtime Contract

### 1. Scope / Trigger

Use this contract when changing the distributed toolchain helper, SD workflow
instructions that select Python, or tests that execute dependency-sensitive
pack commands.

### 2. Signatures

- `bash scripts/sd-ai-command-pack-toolchain.sh doctor [--json]`
- `bash scripts/sd-ai-command-pack-toolchain.sh python [--require-module NAME]...`
- `bash scripts/sd-ai-command-pack-toolchain.sh run-python [--require-module NAME]... -- ARGS...`

### 3. Contracts

- Resolve Python once in documented precedence order; explicit overrides and
  an existing repo `.venv` are authoritative and never fall through after a
  failed probe.
- Require Python 3.10 or newer and probe requested modules before executing a
  workload. Resolution and `doctor` must not execute project workloads.
- `SD_AI_COMMAND_PACK_PROJECT_CHECK_COMMAND` is the only automatically selected
  project check. Make targets, package scripts, and executable conventional
  scripts are report-only candidates.
- Keep the helper compatible with macOS Bash 3.2, quote paths, avoid `eval`,
  and support both `.venv/bin/python` and `.venv/Scripts/python.exe`.
- Report project checks, the pack full-check, and optional AI review as
  separate verification lanes.

### 4. Validation & Error Matrix

- Invalid CLI or module name -> exit `2` without selecting a tool.
- No supported Python -> exit `3` with the Homebrew Python 3.13/setup remedy.
- Invalid selected interpreter, unsupported version, or missing module -> exit
  `4`, identify the selected source, and do not try another interpreter.
- Valid `run-python` request -> probe once, then execute the workload once with
  the selected interpreter.
- Recursive project-check candidate -> report it as recursive and never invoke
  it from the full-check lane.

### 5. Good / Base / Bad Cases

- Good: a repo `.venv` lacking `coverage` produces one actionable failure and
  no Apple/Xcode Python retry.
- Base: `doctor --json` reports a supported interpreter and zero or more
  project-check candidates without changing the repo.
- Bad: trying `python3`, Homebrew Python, and `uv run` in sequence after each
  fails, or executing an inferred `make check` that recursively calls the pack
  full-check.

### 6. Tests Required

- Explicit override, repo `.venv`, active virtualenv, Homebrew, PATH fallback,
  Windows-style virtualenv, unsupported version, and missing-module fixtures.
- Probe/workload invocation counts and authoritative-candidate stop behavior.
- Non-mutating Makefile, package-script, executable-script, ambiguity, and
  recursive-candidate discovery.
- Installer, removal, provenance, manifest, executable-mode, and root/template
  parity coverage.

### 7. Wrong vs Correct

```text
Wrong: python3 check.py || /opt/homebrew/bin/python3.13 check.py || uv run check.py
Correct: sd-ai-command-pack-toolchain.sh run-python --require-module coverage -- check.py

Wrong: infer one project check and run it during doctor
Correct: report candidates; run only an explicitly configured or repo-documented check
```

## Shipped Script Coverage Gate Contract

### 1. Scope / Trigger

Use this contract when changing Python helper tests, `.coveragerc`,
`.github/scripts/run-tests.sh`,
`.github/scripts/check-shipped-script-coverage.sh`, `make test`, or the CI
unittest coverage lane.

### 2. Signatures

- `PYTHON_BIN=<python> bash .github/scripts/check-shipped-script-coverage.sh`
- CI command: `bash .github/scripts/check-shipped-script-coverage.sh`
- Local command: `make test`

### 3. Contracts

- The installer coverage gate remains a separate 100% line-and-branch floor for
  `install.py,installer/*`.
- The shipped-script gate runs both the aggregate
  `scripts/sd-ai-command-pack-*.py` floor and a per-file floor for every
  shipped Python helper.
- Every tracked `scripts/sd-ai-command-pack-*.py` helper must appear exactly
  once in `.github/scripts/check-shipped-script-coverage.sh` with an integer
  floor.
- The helper must resolve and `cd` to the repository root before choosing a
  Python interpreter or checking helper paths, matching other `.github/scripts`
  entry points.
- Floors should be set at or just below current measured coverage and ratcheted
  upward when focused tests improve a helper. Do not lower a floor to hide a
  real regression.
- The helper honors `PYTHON_BIN`, then `.venv/bin/python`, then `python3` so
  direct local runs avoid Apple/Xcode Python when the repo venv exists.

### 4. Validation & Error Matrix

- Missing helper listed in the coverage gate -> nonzero with the missing path.
- Helper coverage below its floor -> nonzero from `coverage report` for that
  helper.
- Aggregate shipped-script coverage below 76% -> nonzero before per-file
  reports.
- New shipped Python helper without a listed floor -> unit test failure.

### 5. Good/Base/Bad Cases

- Good: a fleet-preflight CLI test raises that script's measured coverage and
  the floor is ratcheted upward.
- Base: unrelated test changes leave all aggregate and per-file floors passing.
- Bad: one helper drops below its floor while the aggregate total remains above
  76% and CI still passes.

### 6. Tests Required

- CLI behavior tests for helper surfaces that automation invokes directly.
- A drift test proving every shipped Python helper has a per-file floor.
- A wiring test proving `make test` and CI call the shared coverage helper.

### 7. Wrong vs Correct

```text
Wrong: rely only on TOTAL coverage for scripts/sd-ai-command-pack-*.py
Correct: run aggregate coverage plus one fail-under report per shipped helper

Wrong: python3 -m coverage report ...
Correct: PYTHON_BIN=.venv/bin/python bash .github/scripts/check-shipped-script-coverage.sh
```

## Required Patterns

- Use `pathlib.Path` for filesystem work.
- Keep pack files declared in `manifest.json`.
- The pack-source full-check env-var documentation gate must scan both shipped
  scripts and shipped skill templates. A `SD_AI_COMMAND_PACK_*` variable that
  appears only in `templates/.agents/skills/**/SKILL.md` is still user-facing
  and must be documented in `docs/SD_AI_COMMAND_PACK.md`.
- Gate SD pack-source assumptions on the parsed manifest name, not generic
  installer paths. Other installer repositories must skip SD-only checks, while
  malformed manifests that assert the SD identity fail without a traceback.
- Validate manifest paths before deriving target destinations or anchors.
- Treat Windows drive/root anchors and backslash-separated parent traversal as
  unsafe manifest paths, even when tests run on POSIX.
- Validate resolved pack source paths so template symlinks cannot escape the
  pack root.
- Validate resolved write and backup paths so target-repo symlinks cannot
  redirect installer writes outside the target repo.
- Reject occupied non-file target paths with a controlled installer error.
- Keep platform selection behavior covered by tests when adding adapters or
  install modes.
- Run `git diff --check` against installed target paths after writes unless
  `--skip-diff-check` is requested.
- Keep force-overwrite behavior covered by tests, including backup behavior
  when `--backup` is used.

## Testing Requirements

Run the installer tests with:

```bash
python3 -m unittest discover -s tests
```

CI must fail when `unittest` reports skipped tests, even though local skipped
tests remain friendly for missing developer tools. The required CI aggregate
also includes Ruff, pinned in `requirements-dev.txt`, over `install.py`,
`installer/`, `scripts/`, `templates/scripts/`, and `tests/`; a macOS unittest
leg protects BSD-tool and bash-3.2 behavior that Ubuntu cannot exercise.

Add or update tests when changing:

- CLI flags or argument behavior
- conflict and force handling
- backup behavior
- platform selection and anchor rules
- manifest path validation
- template paths or manifest semantics

## Code Review Checklist

- Does the change preserve existing target files by default?
- Are manifest `source`, `target`, and `anchor` paths validated before any
  file writes?
- Are resolved pack source paths still inside the pack root?
- Are resolved destination and backup paths still inside the target repo?
- Do occupied directories, broken symlinks, and other non-file target paths
  fail without a traceback?
- Are new templates listed in `manifest.json` and documented in `README.md`?
- Do tests exercise the behavior through the CLI, not only helper functions?
- Does the installer still work with only Python 3.10+ stdlib dependencies?
- Is terminal output concise and stable enough for users to understand failures?
