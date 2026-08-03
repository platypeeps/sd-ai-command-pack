# Research: Read-only classification of the 13 non-authority `sd-*` skills

- **Query**: Classify the 13 remaining `sd-*` skills (those without a "Standing GitHub authority" section) into SAFE-TO-AUTO-INVOKE (read-only / analysis / discovery) vs UNSAFE (mutates files, git/workflow state, or takes outward actions the skill performs itself). This allow-list becomes the set surfaced into `.claude/skills/sd-*` for description-based auto-invocation.
- **Scope**: internal (source read of each `SKILL.md`)
- **Date**: 2026-08-02

## Method

Read all 13 target `SKILL.md` files in full under
`templates/.agents/skills/<skill>/SKILL.md`. For the three thin wrapper skills
that delegate to a bundled Trellis skill (`sd-continue`, `sd-start`,
`sd-update-spec`), also read the delegated Trellis skill body
(`.agents/skills/trellis-{continue,start}/SKILL.md`) to judge the real
side-effect surface, because the wrapper inherits the delegate's behavior.

Rubric applied (from the task): repo mutation, git commit/push/branch,
PR/merge, `task.py` state change, generated-output regeneration, or any
outward/destructive action the skill performs **on its own** = UNSAFE. Pure
read/analyze/report/recommend/print-copy-ready-text = SAFE. One mutating step in
an otherwise read-only skill = UNSAFE (step named). Genuine ambiguity = UNSAFE.

## Findings

### Classification table

| skill | verdict | most side-effecting action (file:line) | justification |
|---|---|---|---|
| sd-audit-repo | UNSAFE | `templates/.agents/skills/sd-audit-repo/SKILL.md:130` ("Report + ledger — emit the canonical report, then update the ledger"); reinforced at `:263` ("Ledger and report writes are the only file mutations this skill performs") | Writes/updates the committed audit ledger at `.trellis/audit/ledger.md`. Read-only reviewers, but the orchestrator mutates a tracked repo file. |
| sd-check | SAFE | `templates/.agents/skills/sd-check/SKILL.md:62` ("This command is strictly read-only") | Deterministic verification only; a before/after state guard fails the run if anything changed. No repo/git/task mutation. |
| sd-continue | UNSAFE | delegate `.agents/skills/trellis-continue/SKILL.md:38` ("`status=in_progress` + check passed → 3.3 (spec update) → 3.4 (commit)") and `:55` ("Follow the loaded instructions") | Wrapper (`sd-continue/SKILL.md:8`) resumes and *advances* the active task; the delegate routes into implementation, spec-update, and commit steps. Auto-invoking it continues mutating work. |
| sd-full-check | UNSAFE | `templates/.agents/skills/sd-full-check/SKILL.md:104-107` (KB lane default `auto`: "if stale output is already ignored, it refreshes once and requires a passing recheck") | Mostly a read-only gate, but on its own the default Obsidian-KB freshness lane regenerates the `.obsidian-kb/` folder (file write) whenever one exists and is stale+ignored. One self-performed mutating step ⇒ UNSAFE. |
| sd-help | SAFE | `templates/.agents/skills/sd-help/SKILL.md:126` ("strictly read-only. Do not modify files, create or update Trellis tasks, run checks, call GitHub, install or refresh the pack, or invoke another skill") | Pure discovery/explain/recommend; treats other skills' text as documentation, never executes them. |
| sd-retro | UNSAFE | `templates/.agents/skills/sd-retro/SKILL.md:76-90` (record journal via recorder) and `:116-117` ("The recorder's own journal commit is the only commit this command causes") | Writes a journal entry and produces a git commit through the session recorder. Self-performed file write + commit. |
| sd-review-learnings | UNSAFE | `templates/.agents/skills/sd-review-learnings/SKILL.md:82-86` (`--update`) and `:169-170` ("`--update` replaces only the managed `sd-review-learnings` block in the target file") | Scan mode is read-only, but the skill's stated purpose/description is to *update* `docs/review-learnings.md`; the `--update` step writes a managed block into a tracked file. Mutating step present ⇒ UNSAFE. |
| sd-review-local | UNSAFE | `templates/.agents/skills/sd-review-local/SKILL.md:283-284` (Step 4 "Fix Selected Findings … Implement the smallest correct fix") | Edits product code and tests to fix review findings. Direct repo mutation. |
| sd-start | SAFE | delegate `.agents/skills/trellis-start/SKILL.md:15-50` (runs `get_context.py`, reads spec indexes, decides next action) + wrapper `sd-start/SKILL.md:22` ("Report the skill outcome with `next action`, `task state`, and `blockers`") | Own steps are read-only context load + classify + report. Does not run `task.py start`, does not edit code; for "no active task" it *asks* before creating a task. See caveat below — borderline because it routes toward workflows that themselves mutate. |
| sd-status | SAFE | `templates/.agents/skills/sd-status/SKILL.md:99` ("strictly read-only. Never fetch, pull, switch branches, stage, commit, push, merge, delete branches, modify tasks, refresh the pack, or rewrite generated files") | Delivery/fleet status report only; recovery artifacts explicitly reported read-only. |
| sd-test-gaps | UNSAFE | `templates/.agents/skills/sd-test-gaps/SKILL.md:16` ("This command writes test files and fixtures only") and Step 4 author `:71-86` | Creates/edits test and fixture files in the repo. Direct file mutation. |
| sd-update-deps | UNSAFE | `templates/.agents/skills/sd-update-deps/SKILL.md:84-90` (housekeeping "performs the only `gh pr merge --match-head-commit` mutation") / Step 5 `:78-99` | Merges dependency-bot PRs — an outward, hard-to-reverse action. Highest-risk of the set. |
| sd-update-spec | UNSAFE | wrapper `templates/.agents/skills/sd-update-spec/SKILL.md:24` (run `trellis-update-spec`, which owns `.trellis/spec/` writes) and `:42-43` (KB refresh regenerates `.obsidian-kb`) | Delegates to a skill whose job is to write `.trellis/spec/` docs, plus regenerates repospec/architecture/KB output. Spec + generated-output mutation. |

### Notable caveats per skill

- **sd-start (the one borderline SAFE call).** Its delegate `trellis-start`
  performs only read-only context loading and then *classifies / routes* — its
  description (line 3) says it "routes to brainstorm, direct edit, or task
  workflow." Routing here means recommending/loading another skill's
  instructions, not executing a mutation; the wrapper's contract is to *report*
  the next action. It therefore satisfies the "reads/analyzes/recommends"
  SAFE rubric. The residual risk is only that it is a session *entry point*
  that points at downstream mutating workflows, and unlike sd-check/sd-help/
  sd-status it has no explicit "strictly read-only" safety section. If the
  human wants maximum conservatism, sd-start is the single skill to consider
  demoting to UNSAFE; on the literal rubric it is SAFE.

- **sd-full-check** looks read-only from its "Do not stage, commit, push, or
  edit files … unless the user separately asks for fixes" safety rule
  (`:56-57`), but the KB-freshness lane (`:104-107`) is a documented automatic
  write it performs itself under the default `auto` setting. That is why it is
  UNSAFE despite the safety-rule wording.

- **sd-review-learnings** and **sd-audit-repo** are the "read-only by default,
  but writes a managed artifact" pair. sd-audit-repo *always* updates its
  ledger on a normal run; sd-review-learnings only writes under `--update`.
  Both are excluded because auto-invocation by description could reach the
  write path.

- **sd-continue vs sd-start** (both thin Trellis wrappers): the split is real.
  `trellis-continue` explicitly proceeds through implementation/commit
  (`:38`, `:55` "Follow the loaded instructions"); `trellis-start` stops at
  "decide next action" and the wrapper reports it. Hence continue=UNSAFE,
  start=SAFE.

## Final allow-list (SAFE — surface these)

- **sd-check** — deterministic, state-guarded, strictly read-only verification.
- **sd-help** — read-only command discovery / explain / recommend.
- **sd-start** — read-only session context load + classify + report next action (borderline; see caveat).
- **sd-status** — read-only delivery/fleet status report.

## UNSAFE (exclude — self-performed mutation or outward action)

- **sd-audit-repo** — writes/commits the audit ledger.
- **sd-continue** — resumes and advances the task into implementation/commit steps.
- **sd-full-check** — default KB lane regenerates `.obsidian-kb/` (file write).
- **sd-retro** — writes a journal entry and creates a commit.
- **sd-review-learnings** — `--update` writes the managed block into a tracked file.
- **sd-review-local** — edits product code/tests to fix findings.
- **sd-test-gaps** — writes test/fixture files.
- **sd-update-deps** — merges dependency PRs (`gh pr merge`).
- **sd-update-spec** — writes `.trellis/spec/` docs and regenerates KB/repospec output.

## Caveats / Not Found

- Evidence for the three wrapper skills (sd-continue, sd-start, sd-update-spec)
  rests partly on the delegated Trellis skill bodies read from
  `.agents/skills/trellis-*/SKILL.md` (the installed copies), which match the
  wrappers' stated delegation. If the delegated skills differ in a consumer
  repo, sd-continue/sd-start verdicts should be re-confirmed against that
  repo's Trellis skills.
- The 9 already-excluded "Standing GitHub authority" skills were taken as given
  by the task and not re-read.
