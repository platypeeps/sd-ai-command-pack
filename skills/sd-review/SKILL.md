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
   is in and which providers that tier chains. `route` is a pure function with
   its own fixtures; never re-derive its decision by hand.
3. **The selected backends run on the exact diff the router was shown** — not
   the branch when the scope said worktree, not HEAD when the scope said
   branch. `resolve_subject` is the one place those endpoints exist.
4. **Findings are dispositioned here**, against this repository's severity
   floor, and printed.

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

`--challenge` (adversarial design-challenge stance) · `--explain` (print the
routing decision and why, run nothing) · `--dry-run` (print the exact
invocations, run nothing) · `--json` · `--draft` (routing reduces the tier) ·
`--timeout SECONDS` (per provider, default 900).

There is **no `--repo` and there will not be one** (R10-D6): a session that can
be pointed at another checkout is a session that reviews the wrong diff.

## Exit codes — each means something different

`0` ran, nothing blocks · `1` a finding at or above the severity floor · `2`
bad invocation or bad policy file · `3` a preflight refused (billing safety, an
unmet backend precondition) · `4` **a backend stopped on its rate limit — the
change is not reviewed clean** · `5` the deterministic gate failed, or every
selected backend was unavailable.

`rate_limited` and `unavailable` are deliberately distinct: a quota stop means
the provider *would* have reviewed the change and did not, so the run says so
and you do not get to call it clean. An unavailable provider is one the chain
may move past.

## Codex is subscription-only (R10-D4)

Every codex invocation is preceded by `codex_preflight`, which scrubs
`CODEX_API_KEY` and `CODEX_ACCESS_TOKEN` from the subprocess environment and
refuses unless `auth.json` reports `auth_mode == chatgpt` with no stored API
key. **Never work around a preflight refusal** — never export a key, never call
the codex CLI directly to get past it. A run must never silently fall over to
metered billing.

## Backends

Enabled today: `codex` (heads every chain, default planning provider) and
`prism`. Declared but disabled with a stated reason, on purpose: `gito`,
`kimi`, `antigravity` (probe P2 unrun), `exo`, `baseten`, and the two
github-kind backends `copilot` and `greptile` — those two review by *posting*,
which this lane never does. A disabled row still reports why it did not run,
which beats an unknown-backend error.

## Policy

`.github/sd-review.json` when present, otherwise a conservative built-in:
docs-only is free, everything else pays for codex, sensitive paths and changes
over 800 lines escalate. `never_skip` (default `docs/spec/**`) is a
non-removable deny-list — a path in it is never skipped no matter what
`docs_skip` says.

## setup-github

`sd-review setup-github` installs the opt-in CI routing lane
(`.github/workflows/sd-review-route.yml` + the policy file). It is **not
implemented in `bin/sd-review` yet** — the code carries a named seam
(`SETUP_GITHUB_SEAM`) and a separate PR builds it. When it exists:

- **`mode: minimal` and `mode: guest` refuse it.** Shared and OSS repos cannot
  grow the workflow at all. Do not hand-write the workflow to get around that.
- It will preflight and refuse over a legacy footprint without
  `--remove-legacy` -- a flag that does not exist yet either, and lands with
  the subcommand.

## Never

- Never post, comment, label, or open anything. Disposition is local, full stop.
- Never review a different diff than the one the scope named.
- Never call a provider CLI directly to bypass the router, the preflight, or
  the severity floor.
- Never report a rate-limited run as clean.
