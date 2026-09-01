---
title: Address Prism findings on the installed sd-* prompt adapter prose
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-21
---
# Address Prism findings on the installed sd-* prompt adapter prose

## Goal

Seven Prism findings were raised during the 0.71.45 fleet rollout, in the
`hoa-manager` lane, against prose the pack owns and installs byte-identical to
every consumer. The severity gate classified all seven `consumer-unrelated`
with zero blockers, so the lane continued and this task carries the deferred
work to its actual owner: the pack source.

The finding text arrives from an LLM reviewer that saw only the rendered
prompt diff, without the release history that produced it. Deciding which
findings are real is part of this task, not a premise of it.

## Context

The cited files are generated. Fixing them means editing the command source
under `.github/command-sources/`, then `make generate` and `make sync`; editing
a rendered prompt directly is reverted by the next sync.

Reviewer: Prism (`openai/gpt-4.1`), unstaged mode, run as part of
`npm run check:full` in `hoa-manager` on the 0.71.45 refresh branch. That gate
exited `1` on these findings alone. The same seven are expected to reappear in
any consumer whose Prism threshold is at or below medium, because the diff is
identical fleet-wide.

## Requirements

- Decide each finding on its merits and record the verdict. Two carry real
  substance and the rest are lower-confidence variations on them:
  - `sd-audit-repo.prompt.md` — the 0.71.44 wording says the charter directory
    resolves either inside the installed skill payload or at
    `.agents/skills/sd-audit-repo/charters/` under the same root as that
    payload. It does not say what to do when both candidates exist. Decide
    whether the prose should state a tie-break and require the chosen root to
    be reported. Three further findings (docs tie-break precedence, redundant
    fallback computation, missing tests for ambiguous installs) are the same
    gap seen from different angles.
  - `sd-review.prompt.md` — 0.71.41 deliberately removed the bare
    `sd-ai-command-pack-review.py` filename because a thin install cannot
    resolve it, replacing it with the typed review coordinator reached through
    the toolchain bootstrap. Prism read the removal as introducing ambiguity.
    Decide whether the replacement wording should pin the coordinator's
    interface, and record why the bare filename is not coming back.
  - `sd-housekeeping.prompt.md` — "report the exact blocker" does not specify
    an output shape, and its script-path rules overlap
    `sd-review-learnings.prompt.md`. Both are generated from the same command
    sources, so any deduplication happens there.
- For every finding kept, fix it in `.github/command-sources/`, then propagate
  with `make generate` and `make sync` so `templates/`, `scripts/`,
  `plugins/sd/bin/`, and `plugins/sd/machine-payload/scripts/` stay identical.
- For every finding rejected, write the reason down in this task. A finding
  dismissed without a recorded reason will be raised again by the next rollout.
- Do not widen scope into the pack's install-resolution implementation. These
  findings are about prose; a behavior change is a separate task with its own
  tests.

## Acceptance Criteria

- [ ] Each of the seven findings has a recorded verdict: fixed, or rejected with a stated reason.
- [ ] Any prose change was made in `.github/command-sources/` and propagated, so the four mirrors are byte-identical and `make check` passes.
- [ ] Re-running the reviewer over the resulting prompt diff no longer reproduces the findings that were accepted as real.

## Provenance

Fleet campaign `refresh-0-71-45-20260821T234057Z`, `hoa-manager` lane,
`local-checks` stage. Severity-gate decision `continue-with-follow-ups`:
0 blockers, 7 deferred, 7 owners, 0 duplicates, 0 overrides.
