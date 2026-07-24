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
- `.github/command-sources/sd-help.md`
- `templates/.commands/sd-help.md` (generated guarded adapter)
- `templates/.agents/skills/sd-status/SKILL.md`
- `templates/.commands/sd-status.md`
- `templates/.agents/skills/sd-review-pr/SKILL.md`
- `templates/.agents/skills/sd-review-local/SKILL.md`
- `templates/.agents/skills/sd-full-check/SKILL.md`
- `templates/.agents/skills/sd-housekeeping/SKILL.md`
- `templates/.agents/skills/sd-work-backlog/SKILL.md`
- `templates/.agents/skills/sd-continue/SKILL.md`
- `templates/.agents/skills/sd-finish-work/SKILL.md`
- `templates/.agents/skills/sd-update-spec/SKILL.md`
- `templates/scripts/sd-ai-command-pack-review-full-check.sh`
- `templates/scripts/sd-ai-command-pack-review-local.sh`
- `templates/.commands/sd-review-local.md`
- `templates/.commands/sd-work-backlog.md`
- `templates/.commands/sd-review-pr.md`
- `templates/.claude/commands/sd/continue.md`
- `templates/.claude/commands/sd/finish-work.md`
- `templates/.claude/commands/sd/work-backlog.md`
- `templates/.claude/commands/sd/review-pr.md`
- `templates/.claude/commands/sd/review-local.md`
- `templates/.gemini/commands/sd/review-pr.toml`
- `templates/.gemini/commands/sd/work-backlog.toml`
- `templates/.github/prompts/sd-review-pr.prompt.md`
- `templates/.github/prompts/sd-work-backlog.prompt.md`

Hand-authored neutral bodies live under `.github/command-sources/`. The
generator inserts the canonical checkout-trust policy and writes the guarded
neutral adapters under `templates/.commands/`; OpenCode and the other neutral
platforms install from those generated files. Do not add platform-owned
OpenCode command source copies or hand-edit the generated neutral adapters.
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

## Scenario: Evidence-routed repository audits

### 1. Scope / Trigger

- Trigger: changing `sd-audit-repo` depth, dimension selection, charter
  applicability, coverage reporting, or post-audit follow-up interaction.
- Keep the shared skill, generated adapters, shipped router, docs, and focused
  calibration tests synchronized.

### 2. Signatures

- Public controls: `depth=standard|exhaustive`, additive
  `dimensions=<charter,...>`, equivalent bare charter names, and `follow-up`.
- Applicability preflight:
  `bash scripts/sd-ai-command-pack-toolchain.sh run-python --
  scripts/sd-ai-command-pack-audit-route.py --repo . --mode
  standard|exhaustive [--dimension CHARTER]... --json`.

### 3. Contracts

- Standard mode always runs correctness, security, testing, tooling, and
  release-hygiene. Explicit dimensions add charters and cannot remove that
  core.
- The router owns deterministic applicability from bounded repository paths
  and manifest content. Prompt prose consumes its versioned report and never
  reclassifies charters from conversation memory.
- Unknown, conflicting, unavailable, or malformed classification falls back
  to exhaustive coverage with a visible reason.
- Every canonical charter remains present in Coverage & limits as
  `run|not-applicable|not-selected|failed` with evidence and a reason code.
- Standard is not equivalent to exhaustive. Recommend exhaustive for release,
  security, or other policy-required assurance.
- Do not ask before or during deterministic routing. The only structured
  audit interaction is the independent multi-select for proposed follow-up
  tasks after findings are complete.

### 4. Validation & Error Matrix

- Unknown depth, dimension, or option-shaped input -> usage error before
  reviewer dispatch.
- Missing/nonzero/malformed/unsupported router report -> exhaustive fallback,
  visible classifier warning, and no omitted charter.
- Charter read or reviewer failure -> mark that charter `failed`, retain all
  other charter rows, and stop with the underlying diagnostic.
- `follow-up` plus dimensions -> usage error because it is a distinct mode.

### 5. Good / Base / Bad Cases

- Good: a UI fixture selects accessibility-i18n and retains the mandatory
  core; the report shows both selected and omitted charters.
- Base: a small CLI repository runs the mandatory core plus its matched
  optional charters and recommends exhaustive when assurance policy requires.
- Bad: treat absence of `package.json` as proof that every optional risk is
  irrelevant, or ask the user which fingerprints to trust.

### 6. Tests Required

- Assert mandatory-core and additive-dimension behavior, exhaustive selection,
  unknown/conflicting fallback, complete coverage rows, and human/JSON output.
- Calibrate UI, datastore, API, infrastructure, dependency, and release
  fixtures so each seeded material finding's charter runs in standard mode;
  compare every fixture with exhaustive selection.
- Preserve generated adapter parity, template/root byte identity, install
  provenance, shipped-script coverage, and `make check`.

### 7. Wrong vs Correct

```text
Wrong: dimensions=testing replaces the core and suppresses security
Correct: dimensions=testing is additive; the standard core remains intact

Wrong: an uncertain manifest parse silently skips dependencies
Correct: classifier uncertainty is visible and falls back to exhaustive
```

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
- Use one canonical controller with typed selectors; do not add preset commands
  or let two public skills maintain competing lifecycle loops.

### 2. Signatures

- Canonical controller: `sd-work-backlog [FOCUS] [focus=...] [focus-only=...]
  [selector=all|needs-design] [until=design|merge]`.
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
- Read-only status emits one stable `recovery.reasonCode` plus at most one
  `recovery.reference`. Healthy runs load no recovery reference. Missing or
  invalid ledgers, stale or invalid owners, stopped or red runs, and terminal
  reconciliation each route to a bounded reference; unknown or mismatched
  reason/path pairs fail closed.
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
- Pin canonical-controller, typed design selection, nested-return, status
  visibility, conditional recovery routing, generated adapter, retirement,
  reference fanout, manifest, and template/root parity.
- Assert active and stale terminal-lock diagnostics independently, including
  the stale recovery flag and byte-for-byte preservation of the unrecovered
  lock.

### 7. Wrong vs Correct

Wrong: add a public preset command for design selection, call `sd-create-pr`
and housekeeping around `sd-ship`, or use retained chat history as phase
evidence.

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
- Housekeeping creates or refreshes `.obsidian-kb` after finish-work. A later
  backlog follow-up refresh remains guarded and only updates an existing KB.

### 2. Signatures

- Archive owner helper:
  `scripts/sd-ai-command-pack-update-spec-kb.py`.
- Follow-up owner helper:
  `scripts/sd-ai-command-pack-update-spec-kb.py --if-present`.
- Archive owner: the one `sd-housekeeping` run after finish-work and before
  fetch/merge side effects.
- Follow-up owner: `sd-work-backlog` after follow-up task processing and before
  recording the iteration result.

### 3. Contracts

- Housekeeping invokes normal refresh, which creates an absent KB and its
  managed ignore entry; housekeeping dry-run previews without creating either.
- The backlog's `--if-present` refresh prints a skip reason, returns success,
  and writes neither the KB nor an ignore entry when the KB is absent.
- A valid root symlink to an existing directory is preserved and refreshed
  through its target.
- A regular file, directory, or symbolic link at `.obsidian-kb` counts as
  present so occupied and broken-link states reach normal validation.
- Housekeeping blocks before merge when the post-finish refresh fails.
- The backlog loop blocks its clean iteration boundary when the post-follow-up
  refresh fails.
- `sd-ship` delegates archive refresh ownership to housekeeping and never
  invokes the helper itself.

### 4. Validation & Error Matrix

- KB absent plus housekeeping normal refresh -> create the KB and ignore entry.
- KB absent plus backlog `--if-present` -> visible no-op, exit `0`, no writes.
- Existing valid KB -> selected helper mode and existing exit-code contract.
- Existing conflict or invalid path -> nonzero helper result; owning lifecycle
  reports the helper diagnostics and exact recovery command.
- Dry-run housekeeping with an existing KB -> preview only; no generated-file
  mutation.
- Missing helper or toolchain -> actionable housekeeping failure before merge.

### 5. Good / Base / Bad Cases

- Good: finish-work archives a task, housekeeping creates or refreshes the KB,
  then merges after the refreshed branch passes its gate.
- Base: no `.obsidian-kb` exists, so housekeeping creates it; a later backlog
  follow-up refresh uses the guarded mode and skips only if it is still absent.
- Bad: `sd-ship` refreshes directly and housekeeping refreshes again, or the
  backlog reports completion after creating a follow-up task without a refresh.

### 6. Tests Required

- Present, absent, occupied-path, dry-run, and check helper behavior.
- Archive and post-ship follow-up task copies become current after refresh.
- Housekeeping success/failure ordering and exact recovery command.
- Skill ownership assertions that prevent duplicate unconditional refreshes.
- Template/root parity and canonical full-check with KB freshness enabled.

### 7. Wrong vs Correct

Wrong: guard housekeeping with `--if-present`, silently ignore refresh failure,
or copy task files in a lifecycle skill.

Correct: call normal refresh once from housekeeping, call guarded refresh once
from the backlog follow-up boundary, and stop the owning workflow when the KB
cannot be refreshed.

## Scenario: Full-Check KB Auto-Repair

### 1. Scope / Trigger

- Trigger: the full-check Obsidian KB lane finds an existing generated KB stale
  in its default, non-required mode.
- Auto-repair applies only to already-ignored `.obsidian-kb` output. A gate must
  never make an unignored generated tree safe by editing `.gitignore` for the
  operator.

### 2. Signatures

- Lane owner: `run_sd_ai_command_pack_kb_freshness_check` in
  `scripts/sd-ai-command-pack-full-check.sh`.
- Freshness and refresh helper:
  `python3 scripts/sd-ai-command-pack-update-spec-kb.py [--check]`.
- Mode: `SD_AI_COMMAND_PACK_FULL_CHECK_KB=auto|required|<disabled>`; unset is
  equivalent to `auto`.

### 3. Contracts

- `auto` runs `--check` first. On failure it verifies the KB is ignored,
  refreshes once through the canonical helper, then requires a passing second
  `--check` before continuing.
- `required` is read-only and fail-closed: a failed check reports the canonical
  refresh command but never runs it.
- An absent KB skips in `auto` without creating a generated tree or ignore
  entry. Disabled mode skips before helper or KB discovery.
- Ignore verification distinguishes exit `1` (not ignored) from operational
  Git errors; neither state permits mutation.
- Missing helper and Python behavior retains the existing mode-dependent skip
  or required failure contract.

The repair sequence is deliberately bounded:

```sh
python3 scripts/sd-ai-command-pack-update-spec-kb.py --check || {
  git check-ignore -q -- .obsidian-kb
  python3 scripts/sd-ai-command-pack-update-spec-kb.py
  python3 scripts/sd-ai-command-pack-update-spec-kb.py --check
}
```

### 4. Validation & Error Matrix

- Fresh existing KB -> one read-only check, exit `0`, no refresh.
- Stale ignored KB in `auto` -> one refresh and passing recheck, exit `0`.
- Stale KB in `required` -> no refresh, actionable failure, nonzero exit.
- Stale unignored KB -> refuse refresh, preserve KB and `.gitignore`, nonzero
  exit.
- Missing `git` -> report the missing prerequisite and refuse refresh, exit
  `127`.
- Ignore-verification error -> report that ignored state could not be verified,
  preserve KB, nonzero exit.
- Refresh failure or failing post-refresh check -> preserve helper diagnostics,
  report the exact recovery command, nonzero exit.

### 5. Good / Base / Bad Cases

- Good: documentation makes an ignored KB stale; full-check refreshes it once,
  verifies the result, and resumes the remaining gates.
- Base: the KB is fresh or absent, so full-check performs no generated-file
  mutation.
- Bad: refresh before checking, refresh in `required`, add an ignore entry from
  the gate, or treat refresh success as freshness without a second check.

### 6. Tests Required

- Assert fresh and required modes never print or execute the refresh lane.
- Assert default stale repair executes the check-refresh-check sequence and
  leaves the helper's `--check` passing.
- Assert absent and disabled modes remain no-op success paths.
- Assert unignored state preserves the generated copy and `.gitignore`
  byte-for-byte.
- Inject refresh and post-refresh failures and assert helper diagnostics,
  invocation count, recovery text, and nonzero status.
- Keep template/root script and skill parity under generated validation.

### 7. Wrong vs Correct

Wrong: turn full-check into an unconditional generator or silently edit ignore
configuration so a stale tracked tree can be overwritten.

Correct: check first, repair only known ignored output once, recheck, and fail
closed whenever safety or freshness cannot be proven.

## Scenario: First-Review Boundary-Risk Source Classification

### 1. Scope / Trigger

- Trigger: changing which diff paths feed the preflight's parser, subprocess,
  filesystem, environment, or integrity token scan.
- The advisory identifies new production boundary behavior; test harnesses may
  exercise those APIs without adding the behavior under review.

### 2. Signatures

- Path classifier: `isBoundaryRiskReviewPath(path) -> boolean`.
- Token classifier: `reviewRiskCategories(text, extraSignals?) -> string[]`.
- Matrix classifier: `reviewRiskMatrix(text, extraSignals?) -> Array<{ id,
  label, variants: { good, base, failure } }>`.
- Diff owner: `checkReviewRiskSweep()` reads added lines only from paths
  accepted by the path classifier.

### 3. Contracts

- Normalize path separators before classification.
- Accept executable source extensions `cjs`, `js`, `mjs`, `py`, `sh`, `ts`,
  and `tsx`, plus YAML under `.github/workflows/`, unless the normalized path
  is non-production.
- Exclude directory segments `test`, `tests`, `__tests__`, `fixture`,
  `fixtures`, `vendor`, `vendored`, `third_party`, `node_modules`, and
  `generated`, plus filename stems matching `test_*`, `*_test`, `*.test`, or
  `*.spec`.
- Exclude installed Trellis/pack payload mirrors and known generated review
  paths. Canonical `templates/**` production sources remain eligible.
- Do not infer a test from a merely similar production name such as
  `test-runner.sh` under the `scripts/` directory.
- Test-path exclusion affects only the boundary-risk content scan. Authored
  source sizing, task scope, unreadable/oversized production warnings, and the
  category regexes keep their existing contracts.
- Declarative manifests and non-workflow YAML such as `package.json` and
  `.github/dependabot.yml` remain outside the executable source set.
- Emit stable category IDs in declarative table order. Every triggered entry
  contains bounded good/base/failure prompts, and overlapping signals produce
  one entry per category.
- `reviewRiskCategorySignals` in `.sd-ai-command-pack/review-preflight.json`
  may add bounded literal signals to known category IDs. Invalid category IDs,
  types, counts, blank values, or oversized strings fail the preflight.
- Category detection is advisory evidence for author disposition, never proof
  that a test is present or missing.

### 4. Validation & Error Matrix

- Test-only diff with boundary tokens -> no boundary-risk behavior warning.
- Production-only diff with boundary tokens -> existing categorized warning.
- Mixed diff -> categories derive only from production added lines.
- Workflow `run:` / `env:` additions -> subprocess/environment categories.
- Configured literal signal -> its known category in stable table order.
- Invalid category configuration -> explicit preflight failure.
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

- Unit-test directory, filename, Windows-path, fixture/vendor/generated/copied
  exclusions, workflow YAML, non-test-name, and unsupported-extension
  classification.
- Integration-test test-only, production-only, and mixed diffs with assertions
  on exact category IDs, good/base/failure prompts, configured literal signals,
  stable order, deduplication, and bounded output.
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

- Command row: `CommandInfo(name: str, short: str, family: str,
  executes_checkout_code: bool = True, mutates_local: bool = False,
  mutates_remote: bool = False, trusted_static_only: bool = False,
  safe_mode: str | None = None, target_families: tuple[str, ...] = ...,
  configuration_keys: tuple[str, ...] = (),
  interaction_decisions: tuple[str, ...] = ())`.
- Family row: `CommandFamily(id: str, label: str, summary: str)`.
- Platform capability: `PlatformInfo(...,
  structured_question_tool: str | None = None)`; capability names are exact
  host tool identifiers or `None`, never inferred from model identity.
- Interaction rows:
  `InteractionOption(label: str, consequence: str,
  recommended: bool = False)` and
  `InteractionDecision(id: str, category: str, header: str, question: str,
  options: tuple[InteractionOption, ...] = (), option_source: str | None =
  None, multi_select: bool = False, noninteractive: str = "stop")`.
- Retirement row: `RetiredCommandSurface(id, identifiers, installed_targets,
  removed_version, owner_task, ...)`, with targets derived by
  `command_installed_targets()` rather than copied into the remover.
- Historical allowance row:
  `CommandSurfaceAllowance(identifier, path_pattern, reason)`.
- Compatibility view: `COMMAND_NAMES: tuple[tuple[str, str], ...]`, derived
  from `COMMAND_REGISTRY` rather than maintained separately.
- Reference declaration:
  `SHARED_SKILL_REFERENCES[skill_name] = ("references/<file>.md", ...)`.
- Generator entry point:
  `.github/scripts/generate-command-surfaces.py [--check]`.
- Drift-lint entry point:
  `.github/scripts/check-command-surface-drift.py [--json]`.
- Help modes: `list`, `explain`, `compare`, `recommend`, `examples`, and
  `tour`, with optional `family`, `skill`, `skills`, `goal`, and `detail` keys.

### 3. Contracts

- Every pack-owned command appears exactly once in `COMMAND_REGISTRY` and
  belongs to exactly one declared family. `SOURCE_ONLY_COMMAND_NAMES` remains
  the single source for source-checkout-only availability.
- Generated target families, consumer target footprints, retired identifiers,
  retired paths, and bounded historical allowances derive from the same
  registry module. Installer compatibility aliases must be derived views, not
  second authoritative lists.
- Capability metadata is conservative: new commands execute checkout code by
  default. A `trusted_static_only` command cannot execute checkout code, mutate
  local or remote state, or declare a safe mode; non-executing commands must be
  explicitly trusted-static.
- Structured interaction metadata is also conservative. Every declared
  decision ID resolves to one validated descriptor and at least one owning
  command. Static descriptors have two or three mutually exclusive options,
  put the only recommendation first, and state each consequence. Dynamic
  descriptors are multi-select and explicitly describe independent runtime
  candidates. Headers are at most 12 characters and true batches contain no
  more than three independent questions.
- The canonical interaction categories are ambiguous scope, higher-risk
  mutation, external path, blocked-run disposition, finding/task batch, and
  bounded budget extension. Each descriptor declares `stop`, `park`, or
  `report-only` behavior for noninteractive execution.
- The generator reads hand-authored neutral bodies only from
  `.github/command-sources/`, inserts exactly one capability-driven
  checkout-trust policy before skill resolution, and writes guarded neutral
  adapters to `templates/.commands/`. Claude, Gemini, and GitHub adapters derive
  from the same guarded body. Any declared hand-authored platform override must
  pass the same marker and ordering validation; platform-specific sources
  cannot opt out.
- For commands with `interaction_decisions`, the generator inserts one
  structured-interaction policy after checkout trust and before skill
  resolution. Claude adapters name `AskUserQuestion`; hosts without a declared
  capability receive the same concise plain-question fallback and must not
  name or guess a tool. The generated host-neutral descriptor reference lives
  at `sd-help/references/structured-questions.md` so existing skill-root
  classifiers and manifest fanout install it portably.
- Structured answers select or narrow behavior inside existing invocation
  authority. They cannot override checkout trust, exact-head, required-review,
  failed-closed, no-touch, destructive-operation, or merge gates. Do not add
  prompts for deterministic checks, ordinary in-scope fixes, bounded polling,
  review-thread replies or resolution, normal backlog iterations, or an
  already-authorized housekeeping merge.
- Checkout trust is classified using trusted host-provided, read-only Git and
  GitHub metadata. Fork heads are untrusted; detached, unreadable, unavailable,
  or contradictory identity is indeterminate. Both states stop before any
  checkout-owned script, hook, package task, provider adapter, command-bearing
  config, or changed skill instruction is loaded or run. User approval does not
  override the stop.
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
- Local status always renders complete, separately selectable `F-*` follow-up
  and `T-*` unarchived-task sections. Empty sections render `none`;
  report-local ordinals are deterministic for an unchanged snapshot but never
  replace durable Trellis task IDs. Bounded roadmap-like Markdown/text sources
  contribute source-backed `F-*` items only when no unarchived task ID/path or
  exact normalized title represents them. Fleet human output stays bounded
  while nested local JSON retains each repository's complete follow-up and task
  inventory.
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
- Contradictory command capabilities or an unsafe safe-mode id -> registry
  import fails.
- Invalid or duplicate interaction IDs, unknown categories, malformed headers
  or questions, missing consequences, invalid recommendation order, invalid
  option counts, non-independent dynamic selections, unknown command links,
  unreferenced descriptors, or invalid platform tool identifiers -> registry
  import fails.
- Missing or duplicate skill-resolution anchor, or an authored checkout-trust
  marker -> generation fails before writing any adapter.
- An authored structured-interaction marker, an unknown interaction platform,
  or an unknown decision link -> generation fails before writing any adapter.
- Missing registered sources/targets, unknown public paths, live retired
  identifiers/configuration keys, stale or unsafe allowances, and retired
  manifest entries -> command-surface lint fails with exact file/line JSON
  findings.
- Archived Trellis task/workspace history, backups, caches, vendor, and build
  output -> excluded by scanner policy; live specs, docs, adapters, manifests,
  help, configuration, code, and bounded migration fixtures remain in scope.
- Runtime skill missing from the catalog -> help labels it `unknown/external`.
- Catalog command absent from runtime discovery -> help labels it bundled but
  unavailable instead of claiming it can run.

### 5. Good / Base / Bad Cases

- Good: one registry row plus canonical skill/adapter sources regenerates every
  adapter, manifest row, and the version-bound help catalog.
- Good: one validated decision descriptor and its owning command links
  regenerate Claude-native guidance, portable fallbacks, the shared reference,
  manifests, and installed mirrors from one contract.
- Base: a catalog command missing from the current platform remains visible
  with an honest availability label and a limited explanation.
- Base: an interactive host without a declared structured capability asks one
  concise plain-text question with the registered choices; a noninteractive
  host applies the descriptor's stop, park, or report-only outcome.
- Bad: a new command is added to a hand-written help list, a reference is copied
  to only `.agents`, a neutral adapter names `AskUserQuestion`, or a question
  is used to approve a failed safety gate.

### 6. Tests Required

- Assert registry uniqueness, family completeness, short-name consistency, and
  source-only policy, conservative capability defaults, target-family data,
  and exemption safety.
- Assert the complete interaction schema: identifier/category links, header
  and batching limits, static option counts, recommendation order, consequence
  text, independent multi-select sources, noninteractive disposition, and
  valid platform tool identifiers.
- Assert deterministic family/catalog order, canonical frontmatter
  descriptions, version binding, Markdown escaping, and no-write failure.
- Assert reference path validation and manifest fanout to every skill root.
- Assert adapter generation/parity, install/update/remove behavior, root
  dogfood parity, and manifest case-fold uniqueness.
- Assert Claude capability-present guidance, capability-absent plain fallback,
  noninteractive behavior, no unsupported tool-name leakage, no redundant
  prompts for invocation-authorized actions, shared-reference fanout, and
  template/root parity.
- Enumerate every live command and supported generated adapter, proving that
  execution-capable commands have the canonical policy before skill resolution
  and that only declared trusted-static commands receive the exemption.
- Assert help's availability labels, bounded recommendation behavior,
  read-only boundary, failure guidance, and registry-valid authored examples.
- Assert retired rename/removal, missing adapter, stale spec/help/configuration,
  unknown target, machine-readable finding, and reasoned historical allowance
  fixtures. The live repository must lint clean after generated parity.

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
    CommandInfo(
        "sd-example",
        "example",
        "verification-improvement",
        mutates_local=True,
        interaction_decisions=("example.scope",),
    ),
)
INTERACTION_DECISIONS = (
    InteractionDecision(
        "example.scope",
        "ambiguous-scope",
        "Scope",
        "Which bounded scope should be used?",
        (
            InteractionOption("Keep scope", "Preserve the current boundary.", True),
            InteractionOption("Expand", "Use only the confirmed wider boundary."),
        ),
    ),
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
  explicit `sd-full-check` or `sd-review-local` invocation
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

## Scenario: Bounded review-learning write modes

### 1. Scope / Trigger

- Trigger: changing `sd-review-learnings` target selection, managed-block
  rendering, update flags, filesystem behavior, structured reporting, or
  external-path interaction guidance.
- The script owns deterministic validation and replacement. The skill owns the
  structured external-path decision and passes only the confirmed exact path.

### 2. Signatures

- Default scan:
  `sd-ai-command-pack-review-learnings.py [scan controls] [--target PATH]
  [--json]`.
- Repository update:
  `sd-ai-command-pack-review-learnings.py [scan controls] --target PATH
  --update [--json]`.
- External update:
  `sd-ai-command-pack-review-learnings.py [scan controls] --target ABSOLUTE_PATH
  --update-external --confirmed-external-target RESOLVED_ABSOLUTE_PATH
  [--json]`.
- `--dry-run` emits the repository-local candidate Markdown and cannot combine
  with either update mode or `--json`.

### 3. Contracts

- No update flag is observably read-only: no file/directory/task creation, Git
  staging/commit/push, review request, or remote mutation. It still reports the
  canonical repository root, target, containment, findings, proposed changes,
  digests, and skipped write.
- Resolve the root and target canonically, inspect every existing path
  component, and classify the target as `repository-local` or `external`.
  `--update` accepts only the former. `--update-external` accepts only the
  latter and requires the confirmation argument to byte-match the displayed
  canonical absolute path.
- Existing targets and the nearest existing parent must satisfy regular-file,
  strict UTF-8, current-user ownership, and directory expectations before
  mutation. Preserve surrounding human content and replace or append only the
  complete managed block.
- Construct candidate content in memory. Before directory creation and again
  before atomic replacement, re-resolve containment and compare target
  identity plus content digest. Use a sibling temp file, flush/fsync, reject a
  cross-filesystem replace, and clean the temp on failure.
- JSON schema version 1 reports mode, root, requested/resolved target,
  containment/existence, exact external authorization, findings, GitHub scan
  counts, proposed/applied counts, write status/occurrence/reason, and
  before/after SHA-256 digests. Human output derives from the same fields.
- The skill always asks `review-learnings.external-target` for an external
  write, names the resolved path and one-file managed-block impact, recommends
  repository-local, and stops without writing when interactive confirmation is
  unavailable. A prior or general update request is not exact-path consent.

### 4. Validation & Error Matrix

- Relative traversal, absolute external target in scan/local mode, or parent
  symlink escape -> exit `2`, no target or parent creation.
- Broken/final symlink, directory/non-regular target, invalid UTF-8, unreadable
  content, or ownership mismatch -> exit `2`, prior bytes preserved.
- `--update-external` without confirmation, with a relative confirmation, with
  a noncanonical spelling, or with a different resolved path -> exit `2`.
- Local target passed to external mode, external confirmation passed without
  external mode, or dry-run combined with update/JSON -> usage/setup failure.
- Identity, digest, or containment changes between planning and replacement ->
  fail before replace and clean the sibling temp file.
- Scan failure -> write status `skipped`; requested update failure -> write
  status `failed`; an identical candidate -> `unchanged` with no replacement.

### 5. Good / Base / Bad Cases

- Good: an explicit local update preserves human notes, atomically replaces
  one canonical managed block, and reports one applied change.
- Base: default scan of a clean repository reports a proposed candidate and
  skipped write while the filesystem, Git status, refs, and task state remain
  unchanged.
- Good: the skill displays `/absolute/path/to/review.md`, receives the exact
  structured answer, and the script records that same path in external
  authorization and target fields.
- Bad: treat `--target ../notes.md --update` as a local convenience, infer
  external consent from a prior turn, decode invalid bytes with replacement,
  or fall back from atomic replace to a partial copy.

### 6. Tests Required

- Snapshot a real Git fixture before/after default scan and assert files,
  branch/ref, index/status, target parents, and remote state do not change.
- Cover local update/unchanged paths, surrounding content, strict JSON/human
  fields, write-status distinctions, and no stage/commit/push behavior.
- Cover traversal, external absolute, symlink escape, broken/existing final
  symlink, directory, unreadable, invalid-UTF-8, owner mismatch, missing and
  mismatched confirmation, target content/identity races, parent-symlink races,
  replace interruption, temp cleanup, and cross-filesystem refusal.
- Preserve template/root byte parity, generated structured-question adapters,
  install/audit provenance, the per-file coverage floor, and `make check`.

### 7. Wrong vs Correct

```text
Wrong: --target ../shared/review.md --update and assume the user's update request authorizes it
Correct: reject local escape; require update-external plus the exact displayed-path confirmation

Wrong: read with errors=replace, mkdir first, then overwrite the target directly
Correct: validate strict UTF-8 and ownership, render in memory, revalidate identity/digest, and atomically replace
```

## Review-learning signal clustering

### 1. Scope / Trigger

- Trigger this contract when `sd-review-learnings` includes GitHub Copilot
  review comments in a dry run or managed-block update.
- Current, non-outdated unresolved feedback is action state and must remain
  individually visible. Only resolved or outdated historical evidence may be
  deduplicated and clustered.

### 2. Signatures

- CLI: `sd-ai-command-pack-review-learnings.py [--github-days N |
  --github-pr NUMBER ...] [--github-limit N] [--dry-run | --update]
  [--target PATH]`.
- Collection: `PullRequestComment` retains PR identity, path, body, GitHub
  resolution/outdated state, and `created_at`.
- Pure analysis: `partition_review_comments(comments)`,
  `cluster_historical_comments(comments)`, and
  `preventive_actions(clusters)`.

### 3. Contracts

- Partition from GitHub thread state without local reinterpretation. Render
  current actionable rows before all historical clusters.
- Normalize exact historical signatures from bounded body text plus stable path
  family, removing volatile PR/line numbers and Markdown decoration. Group
  signatures under the ordered repository-owned categories `task-metadata`,
  `boundary-validation`, `contract-documentation-drift`,
  `generated-surfaces`, `reviewer-test-harness-quality`, and `other`.
- Rank historical clusters by recurrence count, recency, then category ID.
  Equivalent input order must produce byte-identical managed Markdown.
- Each cluster retains total observations, signature count, PR numbers, path
  families, observed date bounds, representative signatures, and original
  comment examples. Bound rendered clusters, signatures, PRs, paths, and
  examples independently and report every truncated dimension. Current
  actionable rows are never clustered or hidden by historical caps.
- Preventive actions are fixed category-owned text, emitted only when that
  historical category meets the deterministic recurrence threshold. Never
  synthesize advice with an LLM or emit generic actions for absent categories.
- Preserve managed-marker neutralization, atomic update replacement, surrounding
  human content, and root/template byte parity.

### 4. Validation & Error Matrix

- Negative GitHub days/limits, mixed day and explicit-PR selectors, or
  non-positive PR numbers -> existing setup error and exit `2`.
- Git/GitHub command, payload-shape, target-write, or managed-marker failure ->
  existing phase-tagged diagnostic and exit `2`; no partial target write.
- Missing or malformed `createdAt` -> retain the evidence with explicit
  unavailable time bounds; never discard or invent a timestamp.
- More evidence than a render cap -> deterministic prefix plus explicit
  truncation counts, not silent omission or an unbounded block.

### 5. Good / Base / Bad Cases

- Good: five terminology comments across documentation surfaces render as one
  counted contract/documentation cluster with bounded examples and one
  evidence-counted preventive action.
- Base: one current unresolved comment renders individually first while older
  related comments collapse into a historical cluster.
- Bad: cluster unresolved feedback, render one bullet per historical comment,
  order by GraphQL response order, or recommend categories absent from the
  scan.

### 6. Tests Required

- Assert current-versus-historical partitioning, exact signature deduplication,
  related category clustering, retained PR/path/date evidence, and captured
  multi-surface terminology comments.
- Assert shuffled input produces identical Markdown and recurrence/recency/
  lexical ranking is stable.
- Assert every inner cap and the cluster cap report truncation, preventive
  actions require recurrence, and absent categories produce no generic action.
- Preserve CLI selector, pagination, Markdown-marker safety, dry-run,
  idempotent atomic update, surrounding-content, generated-parity, install
  audit, and full-check regressions.

### 7. Wrong vs Correct

```text
Wrong: list every historical review comment and append the same generic advice
Correct: keep current action rows complete, cluster only historical evidence,
         and emit bounded category actions backed by visible recurrence counts
```

The `sd-full-check` shared skill should continue to define the canonical
local verification script, deterministic checks, optional local review-provider
behavior, skipped-check reporting, and no-edit safety rules.

The `sd-create-pr` shared skill should never stop only because the current
checkout is on the repository default branch. It should create a feature
branch before committing or opening a PR, preferring
`SD_AI_COMMAND_PACK_CREATE_PR_BRANCH`, then a derived `codex/<slug>` from
`SD_AI_COMMAND_PACK_CREATE_PR_BRANCH_SLUG` or the commit message, with a
timestamped fallback for empty or colliding names.

After update-spec and intended-path classification, `sd-create-pr` must run
`scripts/sd-ai-command-pack-review-preflight.mjs` on the complete branch plus
working-tree diff before its first `git add` or any push. A missing helper or
nonzero preflight stops publication; the later `sd-review-pr` gate is not a
substitute for catching known task metadata, generated context scaffolds, or
non-spec/non-research context references before they reach GitHub. Tests must
pin the preflight before staging and preserve fail-closed diagnostics.

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
- Auto-filled body preparation:
  `sd-ai-command-pack-pr-body-scope.py --prepare-tooling-body --body-file <regular-file> --changed-files <nul-list>`.
- Preparation exits: `0` means prepared/already compliant, `3` means an empty
  or mixed diff was intentionally unchanged, and every other nonzero result is
  an error.

#### 3. Contracts

- Only the active `sd-ship` Stage 1 may supply all three internal context
  values directly to `sd-create-pr`.
- Verified delegation runs update-spec, commit, push, and PR creation/reuse,
  then returns the PR identity without resolving or invoking `sd-review-pr`.
- Standalone mode keeps the normal non-deferred `sd-review-pr` handoff.
- The context is not an environment variable or public argument, and thin
  platform adapters must not expose it.
- The no-custom-body `--fill` path supplies the complete `base...HEAD` path set
  as NUL-delimited data to the pack-owned helper; the skill never duplicates
  its path rules.
- The helper accepts a regular UTF-8 body file, preserves the auto-filled body
  as an exact prefix, and writes only through an atomic regular-file
  replacement. User-provided body bytes never enter this preparation mode.
- A fully tooling/generated or Trellis-bookkeeping body is applied with
  `gh pr edit --body-file` before standalone review or verified Stage 1 returns.

#### 4. Validation & Error Matrix

- Active `sd-ship` Stage 1 plus the exact context -> publish and return to the
  composite.
- Standalone invocation without internal context -> publish and enter review.
- User-supplied `publish-only`, `caller=`, `stage=`, or `return-after=` -> stop
  before update-spec or Git/GitHub side effects.
- Partial, mismatched, inferred, or stale internal context -> reject rather
  than skipping review.
- Empty or mixed changed-path input -> exit `3`, leave the auto-filled body
  unchanged, and continue with normal mixed-scope review.
- Tooling-only input with an existing recognized heading -> exit `0` and
  preserve the body byte-for-byte.
- Tooling-only input without the heading -> append the canonical section,
  atomically replace the body file, then edit the PR through `--body-file`.
- Missing/malformed config, unreadable/non-regular body files, classifier
  failure, or failed PR fetch/edit -> stop before the Step 6 review handoff.

#### 5. Good / Base / Bad Cases

- Good: `sd-ship until=merge` publishes in Stage 1, reviews once with
  `defer-finish-work` in Stage 2, and leaves finish-work to Stage 4.
- Base: standalone `sd-create-pr` publishes and runs normal review once.
- Bad: Stage 1 invokes standalone `sd-create-pr`, which reviews immediately,
  then Stage 2 reviews the same head a second time.
- Good: a Trellis-bookkeeping-only fill retains the commit-derived summary and
  gains the recognized tooling/generated scope section before review.
- Base: a mixed authored/generated fill stays unchanged and follows the normal
  review path.
- Bad: a user-provided body is passed through automatic composition or
  generated Markdown is interpolated into an inline `--body` argument.

#### 6. Tests Required

- Assert standalone `sd-create-pr` retains its review handoff.
- Assert the exact internal context returns after PR publication.
- Assert all three `sd-ship` stop-points assign review to Stage 2 correctly.
- Assert public adapters do not expose the internal controls.
- Assert user attempts to select the internal mode are rejected before side
  effects.
- Assert bookkeeping/task/journal/map-only NUL paths append exactly one scope
  section while preserving the original body prefix and special characters.
- Assert mixed paths return `3`, custom bodies remain byte-for-byte unchanged,
  and non-regular body files or missing configs fail without rewriting.
- Assert both standalone publication and verified Stage 1 prepare the body
  before their existing review/return handoffs, using secure temporary files
  and no inline `--body` argument.

#### 7. Wrong vs Correct

```text
Wrong: sd-ship Stage 1 runs the complete standalone sd-create-pr review flow
Correct: sd-ship Stage 1 supplies the internal context and Stage 2 owns review

Wrong: expose publish-only as a public command argument or environment variable
Correct: accept it only as verified in-process orchestration context from sd-ship

Wrong: repeat tooling path globs in sd-create-pr or append Markdown in shell text
Correct: delegate classification/composition to the helper and edit via --body-file
```

When `sd-create-pr` supplies a custom or generated Markdown body, it must write
the exact text through a literal file API and call `gh pr create --body-file`
or `gh pr edit --body-file`. Never interpolate Markdown into a shell `--body`
argument: backticks, dollar signs, and command-substitution syntax are content,
not shell instructions. Secure temporary creation plus option-safe cleanup are
part of this contract; `gh pr create --fill` remains valid when no custom body
is needed.

The `sd-review-local` shared skill should continue to define the interactive
local review/fix loop while delegating provider execution to
`scripts/sd-ai-command-pack-review-local.sh`. Its argument selects review
scope:

- `sd-review-local` reviews local changes first; when no local changes exist,
  it reviews the current branch diff against the configured base ref.
- `sd-review-local all` reviews the full checked-out repository and should not
  infer scope from dirty-state or branch diffs.
- Both scopes should default to the configured local providers, currently Prism
  and Gito, and remain open to repo-local custom providers named through
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

## Scenario: Full-Check Prism Local-First Scope

### 1. Scope / Trigger

- Trigger: full-check selects Prism targets while committed branch work and
  local staged or unstaged work coexist.
- Apply only to the full-check Prism lane; `sd-review-local`, Gito, and
  full-codebase review retain their existing owners and contracts.

### 2. Signatures

- Lane owner: `run_prism_reviews` in
  `scripts/sd-ai-command-pack-full-check.sh`.
- Local targets: `prism review unstaged` and `prism review staged`.
- Clean-tree fallback: `prism review range <merge-base>..HEAD`.

### 3. Contracts

- Detect staged and unstaged Git layers before invoking Prism.
- If either local layer is non-empty, review every non-empty local layer and
  return without resolving or reviewing the committed branch range.
- If both local layers are empty, resolve the merge base and review the
  non-empty committed branch range exactly once.
- Print why the committed range is skipped after local review.
- Preserve `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM` availability, required-mode,
  argument, exclusion, and exit-code handling unchanged.

### 4. Validation & Error Matrix

- Staged plus unstaged plus committed work -> two local reviews, no range
  review, success/failure determined by the existing Prism exit contract.
- Exactly one local layer -> one matching local review, no range review.
- Clean tree plus committed work -> one range review.
- Clean tree plus no committed work -> existing no-range warning.
- Clean tree plus unresolved merge base -> existing merge-base warning.

### 5. Good / Base / Bad Cases

- Good: an operator iterates with staged and unstaged work on a feature branch;
  full-check reviews both local Git layers without paying for a third committed
  range scan.
- Base: the final clean-tree gate reviews the complete committed branch range.
- Bad: always run all three targets, or choose only one local layer and silently
  omit the other.

### 6. Tests Required

- Exercise mixed committed/staged/unstaged state with a logging Prism stub.
- Exercise clean-tree committed state and both single-local-layer states.
- Preserve optional/required provider-error tests and template/root parity.

### 7. Wrong vs Correct

```text
Wrong: review unstaged, staged, and committed range in every dirty feature tree
Wrong: review only staged changes when unstaged changes are also present
Correct: review every non-empty local layer, then review the committed range on a clean tree
```

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

The `sd-work-backlog selector=needs-design` path composes existing Trellis
planning artifacts through the canonical controller. With `until=design`, it
must rank real PRDs that still need `design.md` or `implement.md`, create or
append grounded implementation guidance, preserve user-authored content, park
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
Pi, Qoder, Trae, and Zed Code install from the generated guarded
`templates/.commands/sd-<command>.md` files. Hand-authored neutral bodies live
under `.github/command-sources/`; the generator inserts the canonical trust
policy before skill resolution and derives every generated platform adapter.
Installed targets still use each platform's native command/workflow/prompt
directory, but the authored shared source must not live under a platform-owned
template directory.
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
repo and use it as the primary workflow. Any pack-owned extension must be
explicit and tested; `sd-finish-work` currently replaces only the journal
write step with the safe pack recorder.

## Scenario: Wrapper-preserving lifecycle chaining

### 1. Scope / Trigger

- Trigger: one SD lifecycle skill delegates to a phase whose SD wrapper adds
  pack-owned behavior around a Trellis skill.

### 2. Signatures

- Non-deferred `sd-review-pr` finish step -> resolved `sd-finish-work` skill.
- `sd-finish-work` -> resolved `trellis-finish-work` skill plus
  `scripts/sd-ai-command-pack-record-session.py` at journal time.

### 3. Contracts

- The outer lifecycle resolves the SD wrapper by trusted installed-skill
  discovery; it does not resolve the underlying Trellis skill directly.
- The wrapper retains ownership of pack-specific validation and journal
  recording while the Trellis skill retains archive and session-finalization
  policy.
- Internal defer modes preserve the existing single lifecycle owner.

### 4. Validation & Error Matrix

- Missing, ambiguous, unreadable, invalid, or unavailable SD wrapper -> stop
  with the exact blocker before attempting the underlying Trellis phase.
- Deferred review -> return to the documented merge-tail owner without running
  finish-work.
- Non-deferred review -> run `sd-finish-work`; direct
  `trellis-finish-work` resolution is a contract failure.

### 5. Good / Base / Bad Cases

- Good: standalone review resolves `sd-finish-work`, which delegates to
  Trellis and records concrete change/test journal lines.
- Base: merge-through ship review defers finish-work to housekeeping exactly as
  before.
- Bad: review resolves `trellis-finish-work` directly and leaves the default
  Testing fallback beside a positive validation claim.

### 6. Tests Required

- Assert the review skill resolves `sd-finish-work`, names the pack recorder,
  and contains no direct Trellis finish-work resolution in Step 8.
- Assert deferred lifecycle wording and single-owner behavior remain intact.
- Assert preflight rejects a completed contradictory journal record while
  accepting incomplete, planning-only, failed/skipped, and concrete records.

### 7. Wrong vs Correct

Wrong: `sd-review-pr` invokes `trellis-finish-work` directly because Trellis
owns the underlying archive phase.

Correct: `sd-review-pr` invokes `sd-finish-work`, and that wrapper composes the
Trellis phase with the pack's safe journal recorder.

The `sd-update-spec` shared skill should locate the existing Trellis
`trellis-update-spec` skill, follow that skill as-is for its `.trellis/spec/`
update process, then refresh repo-owned repospec artifacts through existing
maintenance infrastructure when available, perform the pack-specific
architectural-overview gate, and rebuild the repo-local `.obsidian-kb` folder:

- Keep routine Trellis delegation, extension order, the normal one-line KB
  helper invocation, shared safety, and final reporting in the canonical skill.
- Put detailed repository-map, architecture, and exceptional Obsidian-KB
  procedures in three direct references registered through
  `SHARED_SKILL_REFERENCES`; every installed skill root must receive them.
- A routine spec-only pass loads no optional reference. Exact repository
  evidence or explicit invocation selects only applicable references; multiple
  independent extensions may apply, but each reference is loaded at most once
  and no reference links to another reference.
- A selected missing, unreadable, empty, escaping, or contradictory reference
  is a visible failure, never permission to skip the extension silently.

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
