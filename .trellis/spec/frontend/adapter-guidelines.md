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
