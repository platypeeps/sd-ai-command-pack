# Adapter Guidelines

> How shared workflow instructions and platform entry points are written.

---

## Overview

The shared skill is the product. Platform adapters are thin entry points that
load the shared skill and summarize the required behavior.

Reference files:

- `templates/.agents/skills/sd-help/SKILL.md`
- `templates/.agents/skills/sd-help/references/command-catalog.md`
- `templates/.agents/skills/sd-help/references/examples.md`
- `templates/.commands/sd-help.md`
- `templates/.agents/skills/sd-status/SKILL.md`
- `templates/.commands/sd-status.md`
- `templates/.agents/skills/sd-review-pr/SKILL.md`
- `templates/.agents/skills/sd-review-local/SKILL.md`
- `templates/.agents/skills/sd-review-local-all/SKILL.md`
- `templates/.agents/skills/sd-full-check/SKILL.md`
- `templates/.agents/skills/sd-housekeeping/SKILL.md`
- `templates/.agents/skills/sd-work-backlog/SKILL.md`
- `templates/.agents/skills/sd-work-designs/SKILL.md`
- `templates/.agents/skills/sd-continue/SKILL.md`
- `templates/.agents/skills/sd-finish-work/SKILL.md`
- `templates/.agents/skills/sd-update-spec/SKILL.md`
- `templates/scripts/sd-ai-command-pack-review-full-check.sh`
- `templates/scripts/sd-ai-command-pack-review-local.sh`
- `templates/.commands/sd-review-local.md`
- `templates/.commands/sd-review-local-all.md`
- `templates/.commands/sd-work-backlog.md`
- `templates/.commands/sd-work-designs.md`
- `templates/.commands/sd-review-pr.md`
- `templates/.claude/commands/sd/continue.md`
- `templates/.claude/commands/sd/finish-work.md`
- `templates/.claude/commands/sd/work-backlog.md`
- `templates/.claude/commands/sd/work-designs.md`
- `templates/.claude/commands/sd/review-pr.md`
- `templates/.claude/commands/sd/review-local.md`
- `templates/.claude/commands/sd/review-local-all.md`
- `templates/.gemini/commands/sd/review-pr.toml`
- `templates/.gemini/commands/sd/work-backlog.toml`
- `templates/.gemini/commands/sd/work-designs.toml`
- `templates/.github/prompts/sd-review-pr.prompt.md`
- `templates/.github/prompts/sd-work-backlog.prompt.md`
- `templates/.github/prompts/sd-work-designs.prompt.md`

OpenCode command targets use the neutral `templates/.commands/sd-*.md` files
as their source; do not add platform-owned OpenCode command source copies.
The pack repo should not carry an OpenCode package manifest or Bun lockfile
unless its checked-in OpenCode plugins or tools import external npm packages.
The current dogfood plugins use Node builtins and sibling helpers only, so the
local OpenCode surface remains dependency-free.

## Shared Skill Pattern

Keep detailed workflow rules in the matching shared skill under
`templates/.agents/skills/<command>/SKILL.md`.

## Positional Primary Subjects

### 1. Scope / Trigger

Use positional input only when a command has one obvious primary subject. Bare
text names what the command acts on; explicit arguments continue to control
behavior, safety, lifecycle, depth, budgets, and output.

### 2. Signatures

- `sd-retro <topic text>` is equivalent to `topic=<topic text>`.
- `sd-test-gaps <path>` is equivalent to `file=<path>`.
- `sd-fleet-refresh <consumer...>` is equivalent to
  `consumer=<consumer,...>`.
- `sd-audit-repo <dimension...>` is equivalent to
  `dimensions=<dimension,...>`.
- `sd-status <repo-path>` is equivalent to `sd-status --repo <repo-path>`;
  the exact positional token `fleet` remains the reserved fleet mode.

### 3. Contracts

- Parse recognized flags and key/value arguments before positional fallback.
- Preserve positional order and de-duplicate exact repeated list values.
- Keep explicit compatibility forms supported and semantically identical.
- Mutating commands report the normalized subject and controls before acting.
- Platform adapters pass invocation text unchanged; the shared skill or
  executable parser owns normalization.

### 4. Validation & Error Matrix

- Unknown option-shaped input -> usage error before any side effect.
- Positional subject plus its explicit equivalent -> usage error.
- Unknown fleet consumer or audit charter -> usage error; never broaden to all.
- `sd-audit-repo follow-up` plus dimensions -> usage error because the modes
  are mutually exclusive.
- `sd-status fleet --repo <path>` or positional path plus `--repo` -> usage
  error.
- Multiple positional status paths -> usage error.

### 5. Good / Base / Bad Cases

- Good: `sd-fleet-refresh loadsmith rwbp-website no-merge` normalizes two
  consumers and preserves the explicit lifecycle flag.
- Base: `sd-status` inspects the current checkout exactly as before.
- Bad: `sd-fleet-refresh typoed-consumer` stops before preflight or mutation.

### 6. Tests Required

- Assert each positional form maps to the documented explicit form.
- Assert existing no-argument and explicit forms remain supported.
- Assert mixed positional/explicit forms and extra positional status paths exit
  with usage status `2` where an executable parser owns the boundary.
- Assert generated adapters retain the thin argument-forwarding contract.

### 7. Wrong vs Correct

Wrong: infer an unrecognized option or invalid filter as ordinary subject text,
then fall back to an unfiltered operation.

Correct: normalize and validate the primary subject before any side effect,
fail closed on ambiguity, and retain explicit controls for behavior and safety.
- Thin adapters pass the user's invocation arguments unchanged to the canonical
  skill; they do not duplicate parsing policy.

Examples: bare text can identify an `sd-retro` topic, `sd-test-gaps` file,
`sd-fleet-refresh` consumer set, `sd-audit-repo` dimension set, or `sd-status`
repository path. Keep `sd-ship` stop points, housekeeping merge controls,
timeouts, retries, dry-run behavior, and output formats explicit.

## Scenario: Resumable Autonomous Orchestration

### 1. Scope / Trigger

- Trigger: a command repeats multi-phase work across tasks or must survive
  context compaction, interruption, external PR changes, or process restart.
- Use one canonical controller with selector-specific entry points; do not let
  two public skills maintain competing lifecycle loops.

### 2. Signatures

- Canonical controller: `sd-work-backlog [FOCUS] [focus=...] [focus-only=...]
  [until=design|merge]`.
- Design selector: `sd-work-designs ...` resolves the controller with trusted
  `mode: designs`, `selector: needs-design` context.
- Nested ship context: `caller: sd-work-backlog`, ledger run ID, positive
  iteration, and `return-after: merge-result`.
- Durable helper: `scripts/sd-ai-command-pack-work-loop.py` owns the user-local
  ledger, lock, focus ranking, transitions, same-phase evidence updates,
  reconciliation, and snapshots.

### 3. Contracts

- Platform adapters preserve invocation text unchanged. The canonical skill
  validates bare focus, repeatable ordered focus, strict focus-only, lifecycle
  controls, and conflicts before acquiring a lock or mutating repo state.
- Work exactly one task, branch, and PR at a time. Reconcile ledger state with
  live Trellis, Git, and GitHub evidence before every phase or iteration
  transition and before retrying any side effect.
- Keep phase progression separate from mutable evidence. `transition` changes
  lifecycle phase and accepts only task/base-branch identity fields; `evidence`
  atomically records locally verified commits, PR publication, review/finish
  commits, and the final default-branch merge state without a checkpoint
  detour. Task and base branch are stable identity. A missing previously
  recorded local branch ref does not block head-only ancestry evidence, while
  explicit branch evidence must resolve and any resolvable recorded branch
  must match the submitted head. Conflicting PRs, unrelated branches, and
  non-descendant commits fail red.
- User-local state stores only bounded coordination metadata and uses atomic
  writes, versioned JSON, private permissions where supported, and a
  recoverable run lock. Every non-null current-state string must remain
  nonblank; malformed persisted evidence fails validation before reconciliation
  or mutation. The ledger never becomes a tracked repository artifact.
- Terminal reconciliation is a separate local-only audit mutation for stopped
  or completed ledgers. The canonical skill verifies exact merged GitHub PR
  facts before invoking it; the helper validates archived-task identity,
  locally available commits, a clean synchronized default branch, and a
  distinct short-lived exclusive lock. It preserves lifecycle evidence and
  counters, accepts identical evidence as a byte-for-byte no-op, and rejects
  live owners, unsafe stale locks, or contradictory evidence without reviving
  the run.
- Terminal-lock diagnostics must preserve that safety boundary: active owners
  tell the operator to wait, while stale owners name `reconcile-terminal
  --recover-stale-lock` and require verification that the prior process is
  gone. A diagnostic must never imply an abandoned owner will finish itself or
  silently remove its lock.
- Existing lifecycle owners remain authoritative. The outer loop invokes
  `sd-ship until=merge` once; it never separately invokes create-pr, review-pr,
  watch-pr, finish-work, or housekeeping.
- A nested ship report is data returned to the controller. It must not become
  the parent session's final response or start another iteration itself.
- Context health is evidence-based: green agrees, amber rehydrates and
  reconciles, red checkpoints and stops or safely parks.
- A checkpoint is an overlay on its owning lifecycle phase. New ready and
  paused checkpoints retain the lifecycle phase in both `phase` and
  `checkpoint.resumePhase`; their human `target` remains descriptive rather
  than becoming phase state. Schema-v1 ledgers with literal `phase=checkpoint`
  recover from a phase-valued target, or require explicit `--resume-phase`
  when the target is human-only.
- Verified checkpoint recovery supplies every recorded non-null current field,
  validates the complete candidate at the observed lifecycle phase, then
  atomically advances phase/evidence and clears the checkpoint. A forward
  recovery is amber until the same complete evidence reconciles exactly to
  green. Partial evidence, regressions, or identity, PR, Git, and branch
  conflicts remain red without a partial candidate update.
- Follow-ups are addressed, tasked, captured, parked, or blocked before
  re-inventory. PR-scoped review learnings remain owned exactly once by the
  existing review lifecycle.

### 4. Validation & Error Matrix

- Bare plus explicit focus, mixed focus/focus-only, unknown selectors, unknown
  option-shaped input, or invalid lifecycle values -> usage error before lock.
- Concurrent active lock -> stop; stale lock -> reconcile live state, then use
  explicit recovery only when the prior process is gone.
- Active terminal reconciliation lock -> wait and retry after reconciliation
  finishes. Stale terminal reconciliation lock -> fail without mutation and
  require explicit `reconcile-terminal --recover-stale-lock` recovery.
- Unreadable or malformed terminal reconciliation lock, including an invalid
  heartbeat timestamp -> require inspection without mutation, even when stale
  recovery was requested.
- A non-null `task`, `branch`, `head`, `baseBranch`, `prUrl`, or
  `lastShippedSha` that is not a string or becomes empty after trimming ->
  malformed current state before reconciliation or mutation. A head-only
  evidence update with a blank recorded branch -> non-empty branch evidence
  error rather than preserving the malformed ledger value.
- A transition-supplied `task` or `baseBranch` that becomes empty after bounded
  normalization -> field-specific non-empty string error before the phase or
  persisted ledger changes.
- Ledger behind in the same phase -> validate and record the evidence, clear an
  obsolete recovery checkpoint, and return green. A verified later phase uses
  amber rehydration until exact reconciliation. Ledger ahead, invalid ancestry,
  identity/PR conflict, or duplicate-side-effect attempt -> red checkpoint.
- Task-local pre-mutation blocker -> park and continue from clean state;
  uncommitted work, blocking PR, unexplained dirty path, or repository-wide
  contradiction -> stop the run.
- Missing/contradictory nested result -> blocked iteration, never a guessed
  successful merge.

### 5. Good / Base / Bad Cases

- Good: `sd-work-backlog CI pipeline` persists one preferred focus, completes
  matching tasks first, then continues normal deterministic ranking.
- Base: optional current-state evidence remains JSON `null` until observed; no
  focus retains status/priority/readiness/age/lexical ranking.
- Bad: a persisted current-state text field contains `""` or whitespace, a
  design adapter implements its own loop, or housekeeping prints a clean report
  and the parent agent exits without re-inventorying or recording a stop.

### 6. Tests Required

- Cover state-root precedence, POSIX/Windows paths, repository identity, private
  atomic writes, secret-like key rejection, lock concurrency/staleness,
  transition legality, bounded history, pause/resume, invalid state, and blank
  persisted current-state evidence.
- Cover natural and structured focus evidence, ordered bands, preferred
  fallback, focus-only exhaustion, and pre-mutation argument rejection.
- Cover green/amber/red reconciliation; verified versus unverified live
  advancement; create/push/review-fix/finish/merge evidence; invalid identity,
  ancestry, branch, and PR updates; atomic failure; old ledgers; and obsolete
  checkpoint clearing. Include paused lifecycle-overlay recovery after merge,
  legacy checkpoint targets, explicit legacy resume phases, and incomplete
  recovery evidence with no partial mutation.
- Pin canonical-controller, thin-selector, nested-return, status visibility,
  generated adapter, reference fanout, manifest, and template/root parity.
- Assert active and stale terminal-lock diagnostics independently, including
  the stale recovery flag and byte-for-byte preservation of the unrecovered
  lock.

### 7. Wrong vs Correct

Wrong: duplicate the task loop in `sd-work-designs`, call `sd-create-pr` and
housekeeping around `sd-ship`, or use retained chat history as phase evidence.

Correct: one state-backed controller composes a selector, delegates one full
ship lifecycle, reconciles the compact result, processes follow-ups, and emits
an overall final response only after persisting a verified stop reason.

Wrong: tell an operator to wait for a stale terminal reconciliation owner that
cannot finish.

Correct: preserve the lock and direct the operator to verified, explicit
`reconcile-terminal --recover-stale-lock` recovery.

## Scenario: Post-Finish KB Freshness Ownership

### 1. Scope / Trigger

- Trigger: a lifecycle archives Trellis task documentation or records follow-up
  tasks after the normal update-spec refresh has already run.
- Apply only when the repository already has `.obsidian-kb`; lifecycle cleanup
  must not opt an unrelated repository into generated knowledge.

### 2. Signatures

- Guarded helper:
  `scripts/sd-ai-command-pack-update-spec-kb.py --if-present`.
- Archive owner: the one `sd-housekeeping` run after finish-work and before
  fetch/merge side effects.
- Follow-up owner: `sd-work-backlog` after follow-up task processing and before
  recording the iteration result.

### 3. Contracts

- `--if-present` composes with refresh, `--dry-run`, and `--check`.
- An absent KB prints a skip reason, returns success, and writes neither the KB
  nor an ignore entry.
- A regular file, directory, or symbolic link at `.obsidian-kb` counts as
  present so occupied and broken-link states reach normal validation.
- Housekeeping blocks before merge when the post-finish refresh fails.
- The backlog loop blocks its clean iteration boundary when the post-follow-up
  refresh fails.
- `sd-ship` delegates archive refresh ownership to housekeeping and never
  invokes the helper itself.

### 4. Validation & Error Matrix

- KB absent plus any supported mode -> visible no-op, exit `0`, no writes.
- Existing valid KB -> selected helper mode and existing exit-code contract.
- Existing conflict or invalid path -> nonzero helper result; owning lifecycle
  reports the helper diagnostics and exact recovery command.
- Dry-run housekeeping with an existing KB -> preview only; no generated-file
  mutation.
- Missing helper or toolchain with an existing KB -> actionable lifecycle
  failure before merge.

### 5. Good / Base / Bad Cases

- Good: finish-work archives a task, housekeeping refreshes the existing KB,
  then merges after the refreshed branch passes its gate.
- Base: no `.obsidian-kb` exists, so housekeeping and backlog each print the
  guarded skip and continue without creating one.
- Bad: `sd-ship` refreshes directly and housekeeping refreshes again, or the
  backlog reports completion after creating a follow-up task without a refresh.

### 6. Tests Required

- Present, absent, occupied-path, dry-run, and check helper behavior.
- Archive and post-ship follow-up task copies become current after refresh.
- Housekeeping success/failure ordering and exact recovery command.
- Skill ownership assertions that prevent duplicate unconditional refreshes.
- Template/root parity and canonical full-check with KB freshness enabled.

### 7. Wrong vs Correct

Wrong: create `.obsidian-kb` during every cleanup, silently ignore refresh
failure, or copy task files in a lifecycle skill.

Correct: call the canonical helper with `--if-present` once at each mutation
boundary and stop the owning workflow when an existing KB cannot be refreshed.

## Scenario: First-Review Boundary-Risk Source Classification

### 1. Scope / Trigger

- Trigger: changing which diff paths feed the preflight's parser, subprocess,
  filesystem, environment, or integrity token scan.
- The advisory identifies new production boundary behavior; test harnesses may
  exercise those APIs without adding the behavior under review.

### 2. Signatures

- Path classifier: `isBoundaryRiskReviewPath(path) -> boolean`.
- Token classifier: `reviewRiskCategories(text) -> string[]`.
- Diff owner: `checkReviewRiskSweep()` reads added lines only from paths
  accepted by the path classifier.

### 3. Contracts

- Normalize path separators before classification.
- Accept executable source extensions `cjs`, `js`, `mjs`, `py`, `sh`, `ts`,
  and `tsx` unless the normalized path is a conventional test path.
- Exclude directory segments `test`, `tests`, and `__tests__`, plus filename
  stems matching `test_*`, `*_test`, `*.test`, or `*.spec`.
- Do not infer a test from a merely similar production name such as
  `test-runner.sh` under the `scripts/` directory.
- Test-path exclusion affects only the boundary-risk content scan. Authored
  source sizing, task scope, unreadable/oversized production warnings, and the
  category regexes keep their existing contracts.
- Declarative manifests such as `package.json` remain outside the executable
  source-extension set.

### 4. Validation & Error Matrix

- Test-only diff with boundary tokens -> no boundary-risk behavior warning.
- Production-only diff with boundary tokens -> existing categorized warning.
- Mixed diff -> categories derive only from production added lines.
- Windows separators -> normalize and apply the same directory/filename rules.
- Oversized or unreadable production source -> preserve the bounded explicit
  warning without reading the file in full.

### 5. Good / Base / Bad Cases

- Good: a test stubs `subprocess.run` and modifies `os.environ` while the
  production wrapper is declarative, so no production-risk warning appears.
- Base: a production script adds no risk token and the sweep reports a pass.
- Bad: concatenate production and test diffs before classification, causing
  test-only tokens to demand runtime boundary evidence.

### 6. Tests Required

- Unit-test directory, filename, Windows-path, non-test-name, and unsupported-
  extension classification.
- Integration-test test-only, production-only, and mixed diffs with assertions
  on the exact warning categories.
- Preserve large/unreadable untracked-source tests, root/template parity, Node
  syntax checks, and the full repository quality gate.

### 7. Wrong vs Correct

#### Wrong

```javascript
const codePaths = changed.paths.filter((path) => REVIEW_CODE_PATH_PATTERN.test(path));
```

This scans test harness tokens as though they were new runtime behavior.

#### Correct

```javascript
const codePaths = changed.paths.filter(isBoundaryRiskReviewPath);
```

The shared classifier preserves production advisories while removing test-only
noise.

## Scenario: Registry-Backed Command Discovery

### 1. Scope / Trigger

- Trigger: adding, renaming, retiring, or reclassifying an `sd-*` command, or
  adding reference files that must remain inside an installed skill directory.
- The registry, generated adapters, manifest, help catalog, installed mirrors,
  and focused tests form one consumer-facing contract.

### 2. Signatures

- Command row: `CommandInfo(name: str, short: str, family: str)`.
- Family row: `CommandFamily(id: str, label: str, summary: str)`.
- Compatibility view: `COMMAND_NAMES: tuple[tuple[str, str], ...]`, derived
  from `COMMAND_REGISTRY` rather than maintained separately.
- Reference declaration:
  `SHARED_SKILL_REFERENCES[skill_name] = ("references/<file>.md", ...)`.
- Generator entry point:
  `.github/scripts/generate-command-surfaces.py [--check]`.
- Help modes: `list`, `explain`, `compare`, `recommend`, `examples`, and
  `tour`, with optional `family`, `skill`, `skills`, `goal`, and `detail` keys.

### 3. Contracts

- Every pack-owned command appears exactly once in `COMMAND_REGISTRY` and
  belongs to exactly one declared family. `SOURCE_ONLY_COMMAND_NAMES` remains
  the single source for source-checkout-only availability.
- The generator reads canonical skill frontmatter for descriptions and the
  root manifest for the bundled version. Do not hand-maintain those values in
  the help skill or catalog.
- Shared skill references use safe relative Markdown paths below
  `references/`. Authored references must exist before manifest generation;
  generator-owned references must be declared explicitly.
- Reference entries fan out to the shared `.agents` skill plus every supported
  platform-specific skill root so installed skill directories are
  self-contained.
- `sd-help` reconciles the generated pack catalog with the current runtime
  skill inventory. An `sd-` prefix alone never proves pack ownership or local
  availability.
- Help is strictly read-only. It may inspect skill text and metadata but never
  invokes the selected workflow or mutates repository, Trellis, or GitHub
  state in the same request.
- Status is also strictly read-only. Its adapters delegate to the installed
  collector, preserve cached/refreshed labels, and never reconstruct the report
  with platform-specific Git or GitHub commands.
- Status reports Git stash counts consistently in local human output, fleet
  rows, and the local JSON `git.stashCount` field. Saved stashes are
  informational rather than a dirty-tree or unhealthy-state signal; failed
  stash inventory is reported as unavailable instead of zero.
- Status reports the relevant PR's complete review-event total through a
  bounded GraphQL `reviews.totalCount` query. It must not use the length of a
  single paginated REST response; unavailable or malformed totals remain
  explicitly unavailable.
- Review preflight applies `untrackedFileReadLimitBytes` to both diff sizing and
  the first-review boundary-risk scan. Oversized untracked code files are never
  read in full and must be named in an explicit advisory warning.

### 4. Validation & Error Matrix

- Duplicate command name or short form -> registry import fails.
- Missing/unknown family or mismatched `sd-<short>` name -> registry import
  fails.
- Unsafe, duplicate, unknown-skill, or missing authored reference -> generation
  fails before writing any surface.
- Missing/malformed canonical frontmatter or manifest version -> generation
  fails with the source path and field named.
- Duplicate/case-folding manifest target -> generation fails.
- Runtime skill missing from the catalog -> help labels it `unknown/external`.
- Catalog command absent from runtime discovery -> help labels it bundled but
  unavailable instead of claiming it can run.

### 5. Good / Base / Bad Cases

- Good: one registry row plus canonical skill/adapter sources regenerates every
  adapter, manifest row, and the version-bound help catalog.
- Base: a catalog command missing from the current platform remains visible
  with an honest availability label and a limited explanation.
- Bad: a new command is added to a hand-written help list, a reference is copied
  to only `.agents`, or help executes a recommended mutating workflow.

### 6. Tests Required

- Assert registry uniqueness, family completeness, short-name consistency, and
  source-only policy.
- Assert deterministic family/catalog order, canonical frontmatter
  descriptions, version binding, Markdown escaping, and no-write failure.
- Assert reference path validation and manifest fanout to every skill root.
- Assert adapter generation/parity, install/update/remove behavior, root
  dogfood parity, and manifest case-fold uniqueness.
- Assert help's availability labels, bounded recommendation behavior,
  read-only boundary, failure guidance, and registry-valid authored examples.

### 7. Wrong vs Correct

#### Wrong

```python
COMMAND_NAMES = (("sd-example", "example"),)
HELP_FAMILIES = {"Example": ("sd-example",)}
```

This creates parallel command and help registries that can drift.

#### Correct

```python
COMMAND_REGISTRY = (
    CommandInfo("sd-example", "example", "orientation-knowledge"),
)
COMMAND_NAMES = tuple((item.name, item.short) for item in COMMAND_REGISTRY)
```

The generator derives the compatibility view, catalog, adapters, and manifest
fanout from the same validated row.

## Scenario: Repository-Owned Review Full-Check Prelude

### 1. Scope / Trigger

- Trigger: `sd-review-pr` must run its deterministic local gate in a consumer
  repository that may own prerequisites around the pack full-check, such as
  generated-type cleanup, database readiness, or isolated browser-test setup.
- Keep the shipped helper, shared skill, distributed docs, manifest, and tests
  synchronized because the selection behavior is a consumer-facing command
  contract.

### 2. Signatures

- Review helper: `scripts/sd-ai-command-pack-review-full-check.sh`.
- Repository-owned entry point: package script `check:full` in the root
  `package.json`.
- Package runner override:
  `SD_AI_COMMAND_PACK_FULL_CHECK_PACKAGE_RUNNER` (default `npm`).
- Direct fallback: `bash scripts/sd-ai-command-pack-full-check.sh`.

### 3. Contracts

- Parse `package.json` with the pack toolchain helper, not shell text matching.
- A nonempty string `scripts["check:full"]` is authoritative: execute the
  package runner as `run check:full` so repository-owned preludes run before
  the pack gate.
- If the script is absent or invalid, execute the direct pack full-check
  fallback. Do not treat a selected runner failure as permission to fall back
  and run a second gate.
- Force `PRISM=0` and `GITO=0` for both paths so the command-owned PR cycle does
  not invoke optional local review providers.
- Reject configured commands that invoke `sd-review-pr`, `sd:review-pr`,
  `sd/review-pr`, or the review helper itself, preventing recursive review
  loops.
- Preserve the selected runner or fallback exit status exactly.

### 4. Validation & Error Matrix

- Missing `package.json`, malformed JSON, non-object top level, missing or
  non-object `scripts`, or missing/empty/non-string `check:full` -> direct pack
  full-check fallback.
- Present but unreadable `package.json` -> fail with the filesystem diagnostic;
  do not fall back and bypass repository-owned prerequisites.
- Configured recursive command -> fail before runner execution.
- Selected package runner missing -> exit `127`; do not fall back.
- Toolchain helper missing or failing while configuration is being resolved ->
  fail with its diagnostic; do not guess repository intent.
- Direct fallback helper missing -> exit `127` with an actionable diagnostic.
- Selected runner or fallback returns nonzero -> return the same status.

### 5. Good / Base / Bad Cases

- Good: a repository's `check:full` cleans generated types, verifies database
  readiness, then invokes the pack full-check under `PRISM=0 GITO=0`.
- Base: a repository without a valid `check:full` script runs the direct pack
  full-check once.
- Bad: `sd-review-pr` hardcodes the pack helper and bypasses repository-owned
  prerequisites, or retries the fallback after the selected package script
  fails.

### 6. Tests Required

- Assert configured selection, package-runner override, forced provider flags,
  and selected exit-status propagation.
- Assert fallback selection for every missing or invalid configuration shape
  and fallback exit-status propagation.
- Assert recursion rejection, missing runner, authoritative toolchain failure,
  and missing fallback diagnostics.
- Preserve root/template parity, install/audit coverage, manifest registration,
  and shared-skill delegation assertions.

### 7. Wrong vs Correct

Wrong: `sd-review-pr` calls `sd-ai-command-pack-full-check.sh` directly in
every consumer, bypassing repository prerequisites.

Correct: `sd-review-pr` calls the review helper, which selects a valid root
`check:full` script or the direct pack fallback exactly once while disabling
Prism and Gito.

The `sd-review-pr` shared skill should continue to define:

- required local checks before starting, including `gh --version`,
  `gh auth status`, and PR resolution from the current branch
- a deterministic local full-check gate that disables Prism and Gito for the
  command-owned PR cycle; those local review tools should run only through an
  explicit `sd-full-check`, `sd-review-local`, or `sd-review-local-all`
  invocation
- a local `HEAD` versus PR `headRefOid` check before marking a PR ready or
  requesting review, so the remote reviewer sees the pushed code the user
  intends
- dirty working-tree classification before staging or committing
- the configured remote reviewer request path and fallback, with GitHub Copilot
  as the default reviewer
- polling behavior that avoids fetching full comment bodies on every interval
- thread-aware review inspection through GraphQL when using `gh`
- CI check inspection through the stable `gh pr checks` fields `name`,
  `workflow`, `state`, `bucket`, `link`, and `completedAt`, plus failed-log
  routing; do not request unsupported `status` or `conclusion` fields
- standing permission to reply to review comments and resolve addressed review
  threads without asking for separate approval
- reply, resolve, fix, commit, and push behavior
- the five-round limit before asking the user to continue
- deterministic disposition of first-review boundary-risk, authored-source
  size, and multi-task scope advisories before requesting review for a head
- exactly one read-only, PR-scoped `sd-review-learnings` attempt after the
  overall review loop reaches its clean stop conditions; never run it after
  individual rounds or repeat it from `sd-ship`/housekeeping
- automatic Trellis finish-work after a clean final standalone review or an
  `sd-ship until=review` stop; when `sd-ship` continues through merge, accept
  its internal `defer-finish-work` mode and hand lifecycle ownership to the
  composite Stage 4
- the final report fields

The `sd-full-check` shared skill should continue to define the canonical
local verification script, deterministic checks, optional local review-provider
behavior, skipped-check reporting, and no-edit safety rules.

The `sd-create-pr` shared skill should never stop only because the current
checkout is on the repository default branch. It should create a feature
branch before committing or opening a PR, preferring
`SD_AI_COMMAND_PACK_CREATE_PR_BRANCH`, then a derived `codex/<slug>` from
`SD_AI_COMMAND_PACK_CREATE_PR_BRANCH_SLUG` or the commit message, with a
timestamped fallback for empty or colliding names.

### SD Create-PR Composite Delegation Contract

#### 1. Scope / Trigger

Use this contract whenever `sd-create-pr` is called by `sd-ship` or either
skill's stage ownership changes. Standalone `sd-create-pr` must continue into
`sd-review-pr`; the composite needs a publish-only Stage 1 so its Stage 2 owns
review exactly once.

#### 2. Signatures

- Public command: `sd-create-pr` with no publish-only argument.
- Internal orchestration context: `caller: sd-ship`, `stage: 1`,
  `return-after: pr`.
- Composite stop-points: `sd-ship until=pr|review|merge`.

#### 3. Contracts

- Only the active `sd-ship` Stage 1 may supply all three internal context
  values directly to `sd-create-pr`.
- Verified delegation runs update-spec, commit, push, and PR creation/reuse,
  then returns the PR identity without resolving or invoking `sd-review-pr`.
- Standalone mode keeps the normal non-deferred `sd-review-pr` handoff.
- The context is not an environment variable or public argument, and thin
  platform adapters must not expose it.

#### 4. Validation & Error Matrix

- Active `sd-ship` Stage 1 plus the exact context -> publish and return to the
  composite.
- Standalone invocation without internal context -> publish and enter review.
- User-supplied `publish-only`, `caller=`, `stage=`, or `return-after=` -> stop
  before update-spec or Git/GitHub side effects.
- Partial, mismatched, inferred, or stale internal context -> reject rather
  than skipping review.

#### 5. Good / Base / Bad Cases

- Good: `sd-ship until=merge` publishes in Stage 1, reviews once with
  `defer-finish-work` in Stage 2, and leaves finish-work to Stage 4.
- Base: standalone `sd-create-pr` publishes and runs normal review once.
- Bad: Stage 1 invokes standalone `sd-create-pr`, which reviews immediately,
  then Stage 2 reviews the same head a second time.

#### 6. Tests Required

- Assert standalone `sd-create-pr` retains its review handoff.
- Assert the exact internal context returns after PR publication.
- Assert all three `sd-ship` stop-points assign review to Stage 2 correctly.
- Assert public adapters do not expose the internal controls.
- Assert user attempts to select the internal mode are rejected before side
  effects.

#### 7. Wrong vs Correct

```text
Wrong: sd-ship Stage 1 runs the complete standalone sd-create-pr review flow
Correct: sd-ship Stage 1 supplies the internal context and Stage 2 owns review

Wrong: expose publish-only as a public command argument or environment variable
Correct: accept it only as verified in-process orchestration context from sd-ship
```

When `sd-create-pr` supplies a custom or generated Markdown body, it must write
the exact text through a literal file API and call `gh pr create --body-file`
or `gh pr edit --body-file`. Never interpolate Markdown into a shell `--body`
argument: backticks, dollar signs, and command-substitution syntax are content,
not shell instructions. Secure temporary creation plus option-safe cleanup are
part of this contract; `gh pr create --fill` remains valid when no custom body
is needed.

The `sd-review-local` and `sd-review-local-all` shared skills should continue
to define the interactive local review/fix loop while delegating provider
execution to `scripts/sd-ai-command-pack-review-local.sh`. Keep their behavior
parallel except for review scope:

- `sd-review-local` reviews local changes first; when no local changes exist,
  it reviews the current branch diff against the configured base ref.
- `sd-review-local-all` reviews the full checked-out repository and should not
  infer scope from dirty-state or branch diffs.
- Both commands should default to the configured local providers, currently
  Prism and Gito, and remain open to repo-local custom providers named through
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS`.
- Custom provider commands are shell snippets supplied by the target repo or
  user configuration; run them with `bash -c` from the repo root so profile
  startup files do not unexpectedly change review behavior.
- Standard review exclusions must stay aligned across providers. Prism receives
  exclusions from the runner through `--exclude`; Gito receives distributed
  defaults through `.gito/config.toml`, with the runner also filtering full
  codebase path lists to tracked, existing files outside excluded top-level
  directories.
- Gito HTTP 429 handling should retry only when recent output contains an
  explicit error-like 429 or slow-down response. Do not retry because prose,
  docs, or source examples mention `429`.
- The runner must register temporary files as they are created and remove them
  through its cleanup trap, including paths created by Prism chunking, Gito
  output capture, and review path/filter generation.

## Scenario: Bounded Local Review Provider Execution

### 1. Scope / Trigger

- Trigger: changing Prism or Gito invocation, timeout, fallback, retry, or
  response-validation behavior in the shipped local-review runner.
- Keep the runtime, shared skills, distributed documentation, and focused
  tests synchronized because these settings are consumer-facing contracts.

### 2. Signatures

- Shared helper: `run_command_with_timeout <seconds> <command> [args...]`.
- Prism timeout: `SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_TIMEOUT_SECONDS`
  (default `300`).
- Gito timeout: `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_TIMEOUT_SECONDS`
  (default `600`).
- Full-check Gito timeout:
  `SD_AI_COMMAND_PACK_FULL_CHECK_GITO_TIMEOUT_SECONDS`, falling back to the
  local-review Gito timeout and then `600`.
- Prism fallback failure budget:
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_MAX_EMPTY_CHUNK_FAILURES`
  (default `3`).

### 3. Contracts

- Timeout values are nonnegative integers; `0` disables the timeout.
- A timed-out command terminates its process group, escalates from `SIGTERM`
  to `SIGKILL` after five seconds when needed, and exits `124`.
- Exit `124` is terminal for both providers. In particular, Gito must not
  interpret a timeout as a rate-limit response or retry it.
- Prism full-codebase fallback activates only for Prism exit `4` plus a
  recognized empty or malformed provider response. It stops after the
  configured failed single-path request budget; `0` permits all paths.
- Gito retries only when recent output contains an explicit error-like HTTP
  `429` or slow-down response.
- Distributed Prism rules must satisfy `.prism/rules.schema.json`; unknown
  root or required-item properties are rejected.

### 4. Validation & Error Matrix

- Invalid timeout or fallback-budget value -> use the documented default.
- Provider completes before timeout -> preserve its original exit status.
- Provider exceeds timeout -> terminate the process group and return `124`.
- Prism exit `4` with recognized empty response -> use the bounded fallback.
- Prism exit `4` with an unrelated API error -> fail without fallback.
- Gito exit `124` -> fail without retry.
- Gito explicit rate-limit response within the attempt budget -> retry with
  bounded backoff.

### 5. Good / Base / Bad Cases

- Good: a hung provider and its child process are terminated, and the caller
  receives exit `124` within the configured bound.
- Base: a successful provider keeps its output and exit `0`; no fallback or
  retry occurs.
- Bad: a generic provider error is labeled an empty response, a timeout starts
  another paid request, or fallback continues through every tracked file after
  repeated empty responses.

### 6. Tests Required

- Unit-test timeout defaulting, disabled timeouts, exit `124`, process-group
  cleanup, and Gito's no-retry-on-timeout behavior.
- Unit-test Prism's recognized empty-response fallback, unrelated-error
  rejection, and configured failure budget.
- Validate root and template Prism rules against the strict schema.
- Preserve root/template byte parity for every shipped runtime, skill, doc,
  and schema changed by this contract.

### 7. Wrong vs Correct

#### Wrong

```bash
gito review || retry_gito
```

This retries every failure, including timeouts and non-rate-limit errors.

#### Correct

```bash
run_command_with_timeout "$timeout_seconds" gito review
status=$?
if [ "$status" -eq 124 ]; then
  exit 124
fi
```

Only the explicit rate-limit classifier may choose a later retry.

The `sd-housekeeping` shared skill should continue to define the
post-merge task list, the expected clean-state report, anomaly reporting, and
safety rules that prevent deleting branches unless GitHub confirms the PR is
merged and the local branch head matches that PR.

The `sd-ship` shared skill must assign lifecycle side effects to one stage.
For `until=review`, Stage 2 invokes `sd-review-pr` normally and that command
runs finish-work. For `until=merge`, Stage 2 uses the review skill's internal
`defer-finish-work` mode, Stage 3 uses `sd-watch-pr no-merge`, and Stage 4
invokes `sd-housekeeping` exactly once. If Stage 3 blocks or times out, the
active Trellis task remains unarchived for a later resume. These internal
delegation modes are not public `sd-ship` arguments, and they must not weaken
any delegated stage gate.
Stage 2 also owns the one post-cycle review-learning pass inside
`sd-review-pr`; the composite and later stages must not repeat that pass.

The `sd-work-backlog` shared skill should compose existing task, PR, review,
and housekeeping workflows instead of duplicating them. It must work exactly
one Trellis backlog task per iteration, rank only implementation-ready tasks,
delegate publish/review to `sd-create-pr`, delegate merge/cleanup to
`sd-housekeeping`, and address or record follow-ups and learnings before
selecting the next task.

When follow-ups, planning notes, or deferred work are recorded as Trellis
tasks, make those tasks the canonical tracking surface. Use normal task slugs
and descriptions such as `conditional task` rather than preserving a separate
planning namespace, and update prior notes so they point at the canonical tasks
instead of continuing to act as a parallel backlog.

The `sd-work-designs` shared skill should compose existing Trellis planning
artifacts instead of starting implementation. It must inventory existing
Trellis tasks, rank tasks that have real PRDs but still need `design.md` or
`implement.md`, create or append grounded implementation proposals and
execution guidance, preserve existing user-authored artifact content, park
tasks that need user input, and finish with numbered links to every planning
document it created or updated.

Codex does not read the platform command adapter directories for slash-command
completion. It exposes enabled skills in the slash list, so this pack also
installs `sd-*` skills under `.agents/skills/`. Keep the shared skills parallel
with the platform `sd` adapters, and keep each command's detailed behavior in
its matching shared skill.

GitHub Copilot prompt adapters use `.github/prompts/sd-<command>.prompt.md`
with YAML frontmatter descriptions and `mode: agent`, so prompt completion has
explicit metadata and runs in agent mode. Cursor, OpenCode, and the generic
Markdown adapters for Antigravity, CodeBuddy, Devin, Droid/Factory, Kilo Code,
Pi, Qoder, Trae, and Zed Code are installed from the neutral
`templates/.commands/sd-<command>.md` source files. Their installed target
paths still use each platform's native command/workflow/prompt directory, but
the shared source must not live under a platform-owned template directory.
Do not add duplicate OpenCode command source files under
`templates/.opencode/commands/`; if OpenCode ever needs wording that differs
from the neutral source, record the deviation beside the parity test.

Gemini CLI command adapters use TOML under `.gemini/commands/sd/<command>.toml`
because Gemini derives command names from paths under `.gemini/commands/`, with
subdirectories becoming colon namespaces. Keep the `sd/` directory for Gemini;
it is what makes `/sd:<command>` appear. Give every Gemini command a useful
one-line `description`, since Gemini shows it in `/help`.

The `sd-start`, `sd-continue`, `sd-finish-work`, and `sd-update-spec` shared
skills are wrappers around Trellis-provided skills. Do not copy, fork, or
modify Trellis' built-in `trellis-start`, `trellis-continue`,
`trellis-finish-work`, or `trellis-update-spec` skills in `templates/`. Each
shared wrapper should locate the matching Trellis-provided skill in the target
repo and follow it as-is.

The `sd-update-spec` shared skill should locate the existing Trellis
`trellis-update-spec` skill, follow that skill as-is for its `.trellis/spec/`
update process, then refresh repo-owned repospec artifacts through existing
maintenance infrastructure when available, perform the pack-specific
architectural-overview gate, and rebuild the repo-local `.obsidian-kb` folder:

- If the repo has checked-in infrastructure for maintaining a repospec artifact
  (docs, scripts, package tasks, make targets, or similar), use that
  infrastructure to refresh the artifact.
- Do not hand-edit generated repospec output unless repo docs explicitly say
  that file is the source of truth.
- Do not create new repospec infrastructure or a new repospec artifact unless
  the user asks.
- When the repospec refresh uses Repomix or another repository-map tool, follow
  the target repo's documented output path. If no path is documented, prefer
  `docs/repomix-map.md` and report the chosen path.

- Search for an existing architecture overview, such as `ARCHITECTURE.md`,
  `docs/ARCHITECTURE.md`, or `.trellis/spec/**/architecture*.md`.
- Update it only when the work changes high-level architecture: packages,
  services, command surfaces, data flow, persistence, external integrations,
  config/env, or runtime/deployment topology.
- Do not create a new overview unless the user asks.
- Ensure `.obsidian-kb/` is listed in the repo root `.gitignore`.
- Run `python3 scripts/sd-ai-command-pack-update-spec-kb.py` to create or
  refresh `.obsidian-kb/` with real copies of repository-knowledge files such
  as README files, agent instructions, architecture and decision docs,
  `.trellis/spec/**/*.md`, `.trellis/workflow.md`, `.trellis/config.yaml`, and
  repo-owned repospec or Repomix outputs such as `docs/repomix-map.md`.
- The helper should place copies under visible semantic category folders rather
  than raw hidden source paths, and generated KB file/folder names should not
  start with `.` or use Trellis-specific naming.
- If an existing `.obsidian-kb/` folder came from the older symlink helper, the
  refresh should replace pack-owned relative symlinks with category-layout
  copies and report how many legacy symlinks were converted.
- The generated dashboard should link to the GitHub repository when `origin`
  resolves to GitHub, and `.obsidian-kb/LLM-KB - <repo>.md` should provide an
  indexable, self-contained overview for LLM and Obsidian use.
- Generated dashboard and overview sections should group links by semantic
  categories, not raw source folder names.
- The dashboard filename should be `Dashboard - <repo>.md`, and dashboard link
  entries should include brief one-line document descriptions.
- The overview filename should be `LLM-KB - <repo>.md`; old generated
  `LLM-KB.md` files with the pack marker should be pruned during refresh.
- Do not copy secrets, caches, build output, dependency/vendor directories,
  `.git/`, `.trellis/workspace/`, or broad source trees unless a specific source
  entrypoint is intentionally maintained as repo documentation.
- Report `Update-spec skill`, `Spec updates`, `Repospec`,
  `Architectural overview`, `Obsidian KB`, `Obsidian vault copy`, and
  `Validation` in the final response.

## Platform Adapter Pattern

Adapters should stay short and parallel:

1. State the command goal.
2. Tell the agent to read the matching `.agents/skills/<command>/SKILL.md`.
3. Summarize only the command's high-level behavior.
4. Include any command-specific safety stop condition.
5. Include the expected final reporting shape.

The Gemini adapter uses TOML because Gemini commands require it. GitHub Copilot
and OpenCode adapters use Markdown with short YAML frontmatter metadata.

## Drift Control

When changing adapter wording, check all adapters in the same pass. The
adapters intentionally have equivalent prompt text with only format-level
differences.

When changing workflow details, change the shared skill first. Adapter text
should only be updated if the summary becomes inaccurate.

## Anti-Patterns

- Do not copy the full shared workflow into every adapter.
- Do not introduce a platform-specific trigger unless the target platform
  requires it and the README/test coverage are updated.
- Do not describe unsupported shortcuts as reliable, such as assuming a reviewer
  bot comment trigger works everywhere.
- Do not let adapter files drift into different behavior for the same command.
