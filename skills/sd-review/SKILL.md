---
name: sd-review
description: Review the exact current diff with local providers and dispose of the findings locally, never posting them.
disable-model-invocation: true
---

# sd-review

`bin/sd-review` is four steps and no more:

1. **`sd-check`** runs the repository's own deterministic gate. A failing gate
   is a failing review — no model is asked to guess at a change that does not
   build.
2. **`sd_route.route`** decides, from policy data alone, which tier the change
   is in and how deep that tier reads it. **It does not say who reviews.** A
   tier is a count — how many reviewers a change earns off the chain — and the
   registry's `reviewer` line is the chain that count is taken from. `route` is
   a pure function with its own fixtures; never re-derive its decision by hand.
3. **The chosen entries run on the exact diff the router was shown** — not the
   branch when the scope said worktree, not HEAD when the scope said branch.
   `resolve_subject` is the one place those endpoints exist. An entry this
   build has no reader for (`READERS` is `codex-json` and nothing else) is
   marked ineligible on the chain rather than occupying a slot and leaving the
   change read by fewer reviewers than its tier asked for.
4. **Findings are dispositioned here**, against this repository's severity
   floor, and printed.

`--scope planning` is the development flow's *prd and design* review point;
`--scope branch` before a push is *code, before merge*. Both caps are those
rows' in `.claude/rules/sd-planning-adversarial-review.md`, and this tool
states neither.

## Nothing is ever posted

There is no PR comment, no review submission, no label, no check-run update,
and no HTTP client of any kind in this tool. The only outbound calls are
`git`, `sd-check`, and the provider CLIs, each through one injectable runner.
`tests/test_sd_review_boundary.py` asserts that absence rather than trusting
the paragraph. **Do not "helpfully" relay findings to GitHub** — publishing is
the CI lane's business, installed separately by `sd-review setup-github`.

## Scopes

| `--scope` | Subject |
|---|---|
| `worktree` (default) | uncommitted change against `HEAD`, including untracked files |
| `branch` | `merge-base(HEAD, base)..HEAD`, base = `origin/HEAD` else `main`/`master` |
| `pr` | resolves identically to `branch` today — the tool makes no network call, so it cannot read PR state; pass `--draft` yourself if the PR is a draft |
| `planning` | the active `planning`/`in_progress` item's `prd.md`, `design.md`, `implement.md` |

## Flags

`--challenge` (adversarial design-challenge stance) · `--item NAME` (planning
scope only: the one active item whose directory is NAME, when two are
active) · `--provider NAME` (one registry entry instead of the tier's share of
the chain) · `--explain` (print the routing decision, the whole chain and why
each entry was or was not eligible, run nothing) · `--dry-run` (print the exact
invocations, run nothing) · `--json` · `--draft` (routing reduces the tier) ·
`--timeout SECONDS` (per provider, default 1800).

There is **no `--repo` and there will not be one** (R10-D6): a session that can
be pointed at another checkout is a session that reviews the wrong diff.

## Exit codes — each means something different

`0` ran, nothing blocks · `1` a finding at or above the severity floor · `2`
bad invocation or bad policy file · `3` a preflight refused (billing safety, an
unmet precondition on the entry) · `4` **a provider stopped on its rate limit —
the change is not reviewed clean** · `5` the deterministic gate failed, or the
run wanted a reviewer and got none.

Those two are one exit code because they are one sentence: nobody read the
change. A run that wanted reviewers and found none does not go quiet about it —
it prints `no reviewer was available:` and then the reason for each: the
registry refusal if there is no registry, the missing `reviewers` consent line,
and every entry the chain passed over with why. That report is printed on an
ordinary run, not only under `--explain`.

`rate_limited` and `unavailable` are deliberately distinct: a quota stop means
the provider *would* have reviewed the change and did not, so the run says so
and you do not get to call it clean, and the chain does not silently substitute
another provider for it. An unavailable provider is one the chain may move
past.

## The `codex-json` entry is subscription-only (R10-D4)

Every entry whose `reader` is `codex-json` is preceded by `codex_preflight`,
which scrubs `CODEX_API_KEY` and `CODEX_ACCESS_TOKEN` from the subprocess
environment and refuses unless `auth.json` reports `auth_mode == chatgpt` with
no stored `OPENAI_API_KEY` field. **Never work around a preflight refusal** —
never export a key, never invoke the entry's `start` program by hand to get
past it. A run must never silently fall over to metered billing.

## Who reviews

Not stated here. The registry (`providers.yaml`, read through `sd_registry`, its
format documented in `WORKFLOW.md`) is the only list of providers anywhere, and
this file must not grow a second copy of it. What the chain is comes from the
registry's `reviewer` line, intersected with the repository's own `reviewers`
consent line in `CLAUDE.local.md`; without that line no reviewer resolves. Ask
the tool — `--explain` prints the chain, every entry, and the reason for each
one it passed over.

## Policy

`.github/sd-review.json` when present, otherwise a conservative built-in:
docs-only is free, everything else pays for a review, sensitive paths and
changes over 800 lines escalate. **The policy names no provider and no chain.**
A file still carrying `tiers`, `challenge_providers` or `planning_providers` is
refused by that key's name, with the deletion to make, rather than by "unknown
key" — the file is a version behind, not malformed (`RETIRED_POLICY_KEYS`).
`never_skip` (default `docs/spec/**`) is a non-removable deny-list — a path in
it is never skipped no matter what `docs_skip` says.

## setup-github

`sd-review setup-github` installs the opt-in CI routing lane, one file:
`.github/workflows/sd-review-route.yml`. The code lives in
`bin/sd_setup_github.py`, reached through the `SETUP_GITHUB_SEAM` dispatch in
`bin/sd-review`, and it is the only surface in this lane that writes.

**What the lane does is report.** It resolves the pull request's diff, runs
`route()` over the policy, and prints the plan into the check output and the
job summary. It requests no reviewer, posts no comment, and holds
`contents: read`, so it cannot change a pull request's outcome. Asking a remote
reviewer for a review is a separate change with its own decision record — do
not add it to the workflow by hand.

Three refusals:

- **`mode: minimal` and `mode: guest` refuse it** (R10-D5). Shared and OSS
  repositories cannot grow the workflow at all. Do not hand-write the workflow
  to get around that.
- **A legacy sd-github-review footprint refuses without `--remove-legacy`.**
  Two routers in one repository is how a change gets reviewed twice and read
  once.
- **A dirty pack checkout refuses to pin itself.** The workflow names the
  action by commit; `--pin SHA` names a different one deliberately.

Other flags: `--dry-run` (print what would be written, write nothing), `--json`,
`--force` (replace an existing workflow that differs).

## Never

- Never post, comment, label, or open anything. Disposition is local, full stop.
- Never review a different diff than the one the scope named.
- Never call a provider CLI directly to bypass the router, the preflight, or
  the severity floor.
- Never report a rate-limited run as clean.
