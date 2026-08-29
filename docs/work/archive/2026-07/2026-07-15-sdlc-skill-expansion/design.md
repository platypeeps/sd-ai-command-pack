# Design: six SDLC command skills

## Shared wiring (per command)

Mirror sd-audit-repo's surfaces exactly, minus charters:
- templates/.agents/skills/<name>/SKILL.md (fans to 11 skill targets)
- templates/.commands/<name>.md (neutral; fans to 11 command targets)
- templates/.claude/commands/sd/<short>.md, templates/.gemini/commands/sd/
  <short>.toml, templates/.github/prompts/<name>.prompt.md
- manifest entries mirroring the sd-audit-repo block per-section.
Short names: watch-pr, fix-ci, update-deps, fleet-refresh, test-gaps, retro.

Every SKILL.md: frontmatter (name, description "Use when..."), sections
When to use · Arguments · Workflow · Safety rules · Final report. Final
reports are mandatory-shaped with explicit-empty sections and scannable
formatting (bullets, one point per line). No env vars; args arrive as free
text (`key=value` and bare flags), unknown argument names are an error.

## Per-skill contracts

### sd-watch-pr
Watch the current branch's open PR until it settles, then hand off to the
housekeeping gate. Preconditions: feature branch, exactly one open PR.
Loop (bounded; default 30 min, `timeout-minutes=N` arg; poll ~20s via gh):
pending checks, requested-reviewer state, review events, unresolved
threads. Settled = zero pending checks AND (reviewer reviewed OR a short
grace period after checks settle). Then: if green + comment-clean and
`no-merge` not passed, run the sd-housekeeping flow (its gate remains the
only merge authority); else report blockers (failing checks by name,
unresolved threads by path). Never merges directly, never resolves other
people's threads, never force-pushes. Report: PR, settle state, checks
summary, threads, action taken, next step.

### sd-fix-ci
Triage a red CI run to green. Target selection: current branch's PR checks
by default; `main` arg targets the default branch's latest failing run.
Workflow: enumerate failing runs/jobs (gh run list/view --log-failed);
classify each failure: real-code / flake / infra / stale-baseline; for
real-code on a PR branch: reproduce via the matching local target (map CI
job to make target), fix, run the full local gate, push; for main: never
push non-chore fixes directly — create a fix branch + PR through the
normal flow; for flakes: `gh run rerun --failed` bounded at 1 rerun
(`max-reruns=N` to raise), and report flake evidence; infra: report only.
Safety: no force-push, no guard bypass, no test deletion/skips to get
green, reruns bounded. Report: per-job classification table, actions,
resulting run states, follow-ups.

### sd-update-deps
Batch-triage open dependency-bot PRs (dependabot/renovate authors).
Workflow: enumerate → classify per PR: ecosystem, semver delta,
security-advisory flag → auto-merge class = patch/minor dev-dependencies,
GitHub Actions SHA bumps, and security patches; runtime-dependency minors
only with `include-runtime-minor`; majors always manual → for each
auto-class PR sequentially: verify green + comment-clean + heads current
(dependabot rebase races: re-check after each prior merge), merge with the
housekeeping gate criteria, wait for main to stay green before the next →
park everything else with a one-line recommendation each. `dry-run` lists
classifications without merging. Safety: sequential merges only; never
merge red/commented/behind PRs; majors never auto-merged. Report:
classification table, merged list, parked list with reasons, main status.

### sd-fleet-refresh
Roll the pack release across consumer repos, following docs/FLEET_ROLLOUT.md
as the procedure authority. Workflow: run fleet-preflight from the pack
checkout (skips at-target consumers) → for each stale consumer (or
`consumer=a,b` filter): verify clean tree in the consumer checkout (skip +
report if dirty) → branch → install from the pack release ref per the
rollout doc → run the consumer's full-check → commit/push/PR → watch to
settled → merge via the consumer's housekeeping gate (skip merge with
`no-merge`) → next consumer (strictly sequential). `dry-run` = preflight
report only. Safety: never touches a dirty consumer; consumer merges only
via green+clean gate; one consumer at a time. Report: per-consumer status
table (at-target / refreshed+merged / PR-open / skipped+why), fleet
version summary.

### sd-test-gaps
Close the worst coverage gaps with targeted tests. Workflow: run the
repo's coverage flow (make test or documented equivalent) → parse per-file
report → rank shipped files by coverage ascending (`file=<path>` to
target one) → for the top `max-gaps=N` (default 3) files: read the missing
ranges, write focused tests through the normal implement/check flow →
re-run coverage → report per-file before/after. Safety: writes test files
and fixtures only — never product code; aborts if the baseline coverage
run fails; never lowers configured floors. Report: baseline, per-gap
before/after table, files added, remaining worst gaps.

### sd-retro
Capture a structured retrospective after a debugging stream or incident.
Workflow: gather evidence (session context, journal entries, recent git
history) → compose the retro: what broke · root cause · why existing
gates/tests missed it · what limited the blast radius → record it as a
journal entry via the session recorder (title `Retro: <topic>`) → derive
prevention candidates (gate/test/doc changes) and present them as
consent-gated Trellis task proposals — never auto-create → optionally
surface repeated-pattern learnings toward sd-review-learnings. Safety: no
code changes; task creation requires explicit user consent. Report: retro
summary, journal reference, proposals awaiting consent.

## Testing design

One format-drift test module (tests/test_sdlc_commands.py) parameterized
over the six skills: frontmatter name, section order, argument names,
safety pins (e.g. "never merges directly", "majors always manual", "never
touches a dirty consumer", "test files and fixtures only", "requires
explicit user consent"), final-report mandatory items, and adapter
contract pins per command (resolve line + 2-3 body pins across the four
adapter files). Parity/core lists extended with the six commands (sibling
insertion; adapter-expectations tuple + dispatch elif + gemini description
per command). README heading pins extended.

## Tradeoffs decided

- Six commands in one release: one review cycle and one CHANGELOG story;
  accepted Copilot review-size warning (advisory).
- sd-watch-pr as its own command rather than a housekeeping flag: keeps
  the safety-critical housekeeping contract unchanged.
- Zero env vars: argument-only tuning avoids growing the env-var doc gate.

## Rollout / rollback

Purely additive; consumers receive on next fleet refresh (which
sd-fleet-refresh itself will run). Rollback = revert the PR.
