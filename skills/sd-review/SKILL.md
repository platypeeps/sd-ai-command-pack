---
name: sd-review
description: Review the exact current diff with local providers and dispose of the findings locally, never posting them.
disable-model-invocation: true
---

# sd-review

Ordinary `bin/sd-review` reviews run four steps.
The provider preflight below uses a separate synthetic probe.

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
   build has no reader for (`READERS` lists the implemented protocols) is
   marked ineligible on the chain rather than occupying a slot and leaving the
   change read by fewer reviewers than its tier asked for. Rate limits,
   missing executables, authentication failures, failed runs and timeouts
   advance through the remaining eligible entries in registry order until
   that count is met. An exhausted chain with too few completed reviews fails.
4. **Findings are dispositioned here**, against this repository's severity
   floor, and printed.

`standard` and `deep` require two completed independent reviewers.
`cheap` requires one; `skip` requires none, subject to the existing planning and challenge floor.
MiniMax and Kimi can replace each other in configured chain order when an attempt cannot complete.
Only consented, eligible entries can run, within the operator's authorized spending allowance.
A completed adverse review counts and retains its findings; it does not trigger a replacement.
Each chain stops when its required depth completes.
One completion cannot satisfy a two-review requirement.

`--scope planning` is the development flow's *prd and design* review point;
`--scope branch` before a push is *code, before merge*. Both caps are those
rows' in `.claude/rules/sd-planning-adversarial-review.md`, and this tool
states neither.

## Nothing is ever posted

There is no PR comment, no review submission, no label, no check-run update,
and no GitHub writes. `git`, `sd-check`, and provider CLIs use the injectable
runner; URL providers use the injectable `sd_registry` client.
`tests/test_sd_review_boundary.py` checks these boundaries.
**Do not "helpfully" relay findings to GitHub** — publishing is
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
the chain, with no fallback) · `--explain` (print the routing decision, the whole chain and why
each entry was or was not eligible, run nothing) · `--dry-run` (print the exact
invocations, run nothing) · `--json` · `--draft` (routing reduces the tier) ·
`--timeout SECONDS` (per provider, default 1800).

There is **no `--repo` and there will not be one** (R10-D6): a session that can
be pointed at another checkout is a session that reviews the wrong diff.

## Exit codes — each means something different

`0` ran, nothing blocks · `1` a finding at or above the severity floor · `2`
bad invocation or bad policy file · `3` a preflight refused (billing safety, an
unmet precondition on the entry) and the chain could not complete · `4` the
chain exhausted after a rate limit without enough completed reviews · `5` the
deterministic gate failed, or too few reviewers could complete.

An incomplete run does not go quiet about it: it prints completed versus
requested reviews, the actual providers in `reviewed_by`, and each attempt's
outcome. `not enough reviewers were available:` includes eligibility reasons:
registry refusal if there is no registry, missing or denied effective authorization,
and every entry the chain passed over with why. That report is printed on an
ordinary run, not only under `--explain`.

`rate_limited` and `unavailable` remain distinct attempt outcomes. A later
eligible provider can complete the missing review; the receipt retains both
attempts. Findings always remain attached to their provider, including usable
findings from a failed process. Fallback never discards an adverse finding.
Every transport validates the same declared findings schema. Malformed or
oversized responses do not count toward review depth, but usable findings are
retained, including blockers beyond the output count limit and findings with
an unknown location. A clean fallback cannot erase that evidence.

## Provider recovery preflight

`sd-review --preflight --provider NAME --explain --json` resolves one URL provider without calling it.
It applies current consent, enabled-state, credential, transport, and committed branch authorship guards.
Without `--explain`, it sends one fixed synthetic schema probe. No repository source or local conventions are sent.
This is one provider call, subject to the operator's remaining spending allowance. It never retries or selects a fallback.
It runs no repository check and cannot replace the ordinary deterministic gate or exact-head review.
Review modifiers, CLI providers, and `--dry-run` refuse; use `--explain` for zero calls.

The receipt has `operation` and `scope` equal to `provider_preflight`, with zero requested and completed reviews.
`preflight_passed` requires the requested empty findings response, not just any schema-valid answer.
It proves neither review coverage nor the serving model's identity.
`preflight_failed` exits 5. `preflight_planned` under `--explain` makes no recovery claim.

URL diagnostics retain the configured provider, vendor, model, host, options, prompt digest, and observed HTTP status.
They distinguish transport, HTTP, API, envelope, completion, and schema failures.
Sanitized responses retain fixed-key structure, types, byte counts, digests, and bounded numeric usage.
Arbitrary content, reasoning, model identifiers, error messages, headers, and credentials are not copied into diagnostics.
The returned model is compared with the requested model; absence or mismatch remains explicit.
These projections cannot reconstruct a discarded raw response. Historical bodies cannot be recovered from their hashes.

MiniMax/Kimi recovery requires both named providers to pass preflight, followed by one complete multi-provider review.
Local fixtures do not satisfy that live acceptance. No provider call is permitted when the authorized allowance is spent.
Until live acceptance passes, an authorized exact-head `--scope branch --provider claude` review is the temporary mitigation.
That single-provider result does not waive the shipping workflow's required depth or review gates.

## The `codex-json` entry is subscription-only (R10-D4)

Every entry whose `reader` is `codex-json` is preceded by `codex_preflight`,
which scrubs `CODEX_API_KEY` and `CODEX_ACCESS_TOKEN` from the subprocess
environment and refuses unless `auth.json` reports `auth_mode == chatgpt` with
no stored `OPENAI_API_KEY` field. **Never work around a preflight refusal** —
never export a key, never invoke the entry's `start` program by hand to get
past it. Automatic fallback uses only the separately consented registry entries;
it never changes that entry's authentication or bypasses its refusal.

Each provider receives only `PATH`, `HOME`, `LANG`, `TERM`, `TMPDIR` and the
variables declared in its registry `env` list. Codex also receives the exact
`CODEX_HOME` whose authentication passed preflight. Unrelated credentials are
not inherited. This reduces accidental exposure; providers still run as the
operator and can read files accessible to that account.

The `claude-json` reader runs Claude in safe and restricted modes with only
Read, Grep and Glob tools, no custom MCP servers, and no saved session. The
exact diff and untracked or planning-file contents are supplied in a temporary
review file; URL providers receive the same material in their request. Its
reader accepts the documented `structured_output` result envelope and treats
error envelopes or missing structured results as failed attempts. The protocol
is documented in [Claude Code's headless guide](https://code.claude.com/docs/en/headless).

## Who reviews

The effective registry is the only provider list. Read `sd config get sd.external_reviews` for the operator's standing policy.
`configured` permits private code and scoped review context to eligible configured providers, including future entries.
Machine `deny` vetoes local consent. A present repository `reviewers` list restricts recipients; an empty list denies all.
Malformed local consent refuses. An absent key inherits standing policy; without either grant, stop before transmission.
Never treat installation or another user's setting as this operator's grant.
`--explain` prints the authorization source, chain, and reasons for skipped entries.
Provider selection, author exclusions, review depth, and spending or automatic pass limits remain unchanged.

When the database exists, provider enabled state and role order come from its
rows through a read-only connection. A missing database uses the registry file
without creating one. An unreadable database refuses instead of ignoring the
operator's controls and silently falling back to file defaults.

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
- Never count a rate-limited attempt as a completed review. A run can be clean
  only after eligible, consented replacements satisfy its full depth and no
  findings remain.

## Fix verification used by sd-ship

`--scope branch --base <full ancestor SHA> --verify-report <prior JSON>` reviews
only the committed fix range while carrying the prior review's blocking
findings and the current source for each of them. The saved report must name
that exact base. Actual author vendors from both ranges remain excluded. If
the default branch advanced, its new code remains in the reviewed tree diff,
while item authorship is measured against the refreshed target boundary. This
is evidence for the ship adapter's single fix verification, not authority to
replace a ship receipt with a claimed reviewed head.

Provider child environments include the actual operating-system `USER` identity
for native macOS keychain authentication, alongside the execution base and
explicitly declared provider variables. Unrelated credentials remain excluded.
