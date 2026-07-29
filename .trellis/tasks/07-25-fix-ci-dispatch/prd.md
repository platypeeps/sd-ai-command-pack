# Add per-job dispatch protocol to sd-fix-ci

Parent: `.trellis/tasks/07-25-agent-artifacts` (Tier 1 pilot). Settled inputs: parent
`design.md` section 1 and `research/cross-platform-agent-support.md`.

## Goal

Pilot the SD dispatch pattern in sd-fix-ci: one read-only sub-agent per failing CI job,
each consuming only that job's failure logs in isolation and returning a typed triage
result, so the parent context stops absorbing every job's full log output.

## Requirements

- R1: Dispatch section modeled on the sd-audit-repo protocol (the house template):
  capability-first phrasing, "on sub-agent dispatch platforms run per-job triage in
  parallel; on inline platforms classify jobs sequentially in one context" fallback.
- R2: Worker contract: input = one failing job's identity + its `--log-failed` output +
  the change context; output = classification (`real-code | flake | infra |
  stale-baseline`), evidence quotes, and a suggested fix or rerun disposition. Workers are
  read-only; fixes are applied by the parent.
- R3: Checkout-trust preflight classification is restated in every dispatch prompt;
  structured answers cannot override safety gates; untrusted/indeterminate handling
  unchanged from the current command.
- R4: Parent owns job IDs, result assembly, fix application, rerun, and the final report;
  report contract unchanged.
- R5: Inline platforms produce the same outcome as today (no scope change).

## Acceptance Criteria

- [ ] sd-fix-ci canonical body carries the dispatch section; `make generate` byte-stable
      across all platform adapters; catalog regenerated.
- [ ] Worker result contract documented in the command body; classifications unchanged.
- [ ] Trust restatement present in the dispatch protocol text.
- [ ] Version bump + dated changelog entry per repo rules.

## Dependencies / order

- Independent of Tier 2 tasks (works with host built-in sub-agents).
- 07-25-dispatch-rollout MUST wait for this pilot. Informs the later sd-ci-triager named
  agent (07-25-worker-agents).

## Notes

- ~~Lightweight-to-medium; PRD + short design note likely sufficient.~~ **Revised
  2026-07-28.** This is the gating pilot whose pattern `07-25-dispatch-rollout` copies
  into three commands and `07-25-worker-agents` turns into a named agent. Both
  `design.md` and `implement.md` are authored, kept tight.
- **R3 as written diverges from the template R1 names.** Verified 2026-07-28:
  `templates/.agents/skills/sd-audit-repo/SKILL.md` contains **zero** occurrences of
  "trust", "untrusted", or "indeterminate" — its dispatch protocol restates the Active
  task prefix, not trust. The checkout-trust block is **generator-injected** by
  `.github/scripts/generate-command-surfaces.py:179-184` (`CHECKOUT_TRUST_POLICY_MARKER`)
  keyed off `CommandInfo.executes_checkout_code` / `trusted_static_only`
  (`installer/registry.py:726`, `:728`), which is why it appears at
  `.claude/commands/sd/fix-ci.md:27` and in no authored source. Writing trust prose into
  `SKILL.md` creates a second hand-maintained copy of a generator-owned classifier. R3 is
  satisfied instead by one sentence carrying the command's *already-resolved* state into
  each dispatch prompt, with workers barred from reclassifying.
- **"Canonical body" is ambiguous; the section goes in the skill body.** There are two
  hand-authored files per command: `.github/command-sources/sd-fix-ci.md` (16 lines,
  routing only) and `templates/.agents/skills/sd-fix-ci/SKILL.md` (157 lines, the
  workflow). The reference puts `## Dispatch protocol` in the skill body
  (`sd-audit-repo/SKILL.md:156`). The command source stays 16 lines.
- **The goal depends on a log-fetch change the requirements do not mention.**
  `SKILL.md:73` uses `gh run view <run-id> --log-failed`, which returns *every* failing
  job's log in one call. A parent that runs it and splits the blob has already absorbed
  everything, so "the parent context stops absorbing every job's full log output" is not
  met. Per-job fetch is required and is supported (`gh run view -j <job-id> --log-failed`).
  Costs to accept: `gh`'s help warns the per-job path falls back to API fetches that are
  "slower and more resource-intensive" and fails if more than 25 job logs are missing; and
  every `gh` call routes through the toolchain wrapper (`SKILL.md:27-33`), so N workers
  means N cache setups. No acceptance criterion currently catches a dispatch section
  layered over a whole-run log fetch.
- **Run-level evidence must be resolved once by the parent.** `stale-baseline` depends on
  "the branch is behind the default branch" (`SKILL.md:87`) and the report carries the
  PR-head/local-HEAD note (`SKILL.md:68-70`) — both are run properties. N workers deriving
  them independently can disagree inside one report.
- **The rerun budget cannot be delegated.** `max-reruns=N` (default 1, `SKILL.md:113`) is a
  shared counter; a worker able to call `gh run rerun` makes the bound unenforceable. R2's
  read-only worker rule is what holds this together.
- **Fan-out is unbounded.** `max-reruns` bounds reruns, not workers, and nothing caps the
  number of failing jobs. `sd-test-gaps` has `max-gaps` and `sd-fleet-refresh` has waves;
  sd-fix-ci is the one command in the rollout with no natural bound, so the decision is
  owed here.
