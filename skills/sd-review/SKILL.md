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
`--scope branch` before a push is *code, before merge*. Their caps are the ones
on those rows in the sd-ai-command-pack checkout's
`.claude/rules/sd-planning-adversarial-review.md`, and this tool states neither.

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

`sd-review setup-github` installs the opt-in CI routing lane, two files:
`.github/workflows/sd-review-route.yml`, and a Dependabot guard in
`.github/dependabot.yml`. The code lives in `bin/sd_setup_github.py`, reached
through the `SETUP_GITHUB_SEAM` dispatch in `bin/sd-review`, and it is the
only surface in this lane that writes.

**The guard.** The workflow pins the action by commit, and the action runs the
pack's own code out of that checkout, so a Dependabot bump of the pin is a
behaviour change across the whole pack dressed as a version number. The guard
is one `ignore:` item for the action in the file's github-actions entry, with
a comment that names no incident, pull request or SHA -- the reason lives in
`actions/review-route/README.md` and is cited by path, so the text has nothing
in it the next pin move can make false. The template is `GUARD_LINES` in
`bin/sd_setup_guard.py`, and it is the only copy: before it existed, seven
repositories carried the guard in six hand-written wordings, five of them
reciting a fix commit that was already behind their pin. Do not write the
guard by hand; run `setup-github` and let the file gain it.

The rest of `dependabot.yml` is the consumer's. With no file, `setup-github`
creates a minimal one (one github-actions entry, weekly, five open pull
requests, the guard). With a file, it appends the guard to the entry's
`ignore:` list, creating the list when the entry has none, and replaces an
existing item for the action -- comment and line -- when one is there. That
is a line transform, not a YAML round-trip, so the consumer's comments
survive. A file whose guard differs from the template refuses without
`--force`, the same way a differing workflow does; a file with no guard at all
simply gains one.

**`--check`.** `sd-review setup-github --check` renders both files at the
repository's own pin -- read from the tracked workflow, or `--pin` when there
is none -- and diffs them against what is tracked. One line per file, `same
<path>` or `DIFFERS <path>`, a unified diff under each `DIFFERS`, exit 1 on
any difference and 0 otherwise; nothing is written, and it asks nothing of the
mode or the policy. `DIFFERS` is the word `machine-setup.sh status` already
greps for in the system repository, so a fleet sweep can count drift without
reading the diffs. It compares the template, not the pin: a pin behind the
pack's HEAD is `same`, because moving it is a decision (`--pin <sha>
--force`, in its own commit), not drift.

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
`--force` (replace an existing workflow or guard that differs).

## Reading a test: name what would have to differ

For any assertion that two things are equal, name what would have to differ for
it to fail. If the answer is "a clock tick", "a filesystem ordering", or
"nothing", the test is decorative and its green is not evidence of anything.

The instance this came from was named `test_the_build_is_reproducible`. It built
a wheel twice and asserted the two artifacts matched. Both builds landed inside
the same second, so the clock the builder was wrongly stamping into the archive
read the same both times and the artifacts agreed — while the defect the test is
named for was present throughout. A concurrent run that straddled a second
boundary found it. The test never could, and had reported green for as long as
it had existed.

The replacement asserts the property instead of the agreement: every archive
entry's stamp is the normalised `(1980, 1, 1, 0, 0, 0)`, and the sdist case
mutates source mtimes between two builds and asserts the gzip MTIME field is
zeroed. Both fail against the pre-fix code. That is the general remedy — assert
what the code is supposed to produce, not that two runs of it matched.

`tests/test_suite_shape.py::AssertionsCanFail` enforces the part of this a
machine can decide: an assertion whose two operands are the same expression, an
assertion whose operands are all literals, and a test that reaches no assertion
at all. **It does not catch the case above, and no static check can** — whether
two different expressions can differ at run time is a question about the world
rather than about the source.

### Reading is not enough either. Introduce the defect.

The heuristic above is worth having and it is not sufficient, and this
repository has the counterexample rather than an argument for one. While
`tests/test_dashboard_plugins.py` was being fixed for an unrelated reason, its
lane ran a mutation check it had named in advance: put a deliberate defect into
`dashboard/plugins.py`, confirm each test goes red. One did not. The
process-group test — a two-second pause asserted against a child writing at
0.8s — passed against a mutant replacing `os.killpg` with `proc.kill()`, so the
tile's child survived the group kill and kept running:

    Ran 1 test in 10.992s

    OK

A test that could not fail on the defect it exists to catch, and it looked
correct by every other method: it passed, it was named well, it exercised the
right module, and its assertions had operands from the code under test. Reading
it would not have found this. Mutation did.

So when a test exists to catch a specific defect, the way to know it can is to
put that defect in and watch it go red. Quote the failing run. This costs one
edit and one test invocation for the narrow high-value surfaces — the
installer, the archive builders, anything killing or timing a process — and it
is the only instrument here that answers the question directly rather than by
inspection.

Asked in the other direction the same question finds the mirror defect: name
what would have to change for the test to stop passing. If the answer is a slow
machine, a loaded runner or a wall-clock deadline, the test fails for reasons
unrelated to the code under test. Both shapes defeat the gate — one by never
going red, the other by going red for nothing, and the process-group test
above was both at once.

### A control that asserts only absence is not a control

A refusal test needs a companion showing the refusal is about the condition and
not about the fixture. Written as `assertNotIn` alone, that companion passes on
every failure that does not happen to use the refusal's wording — a usage
error, a missing dependency, a crash before the code under test is reached —
so the one thing its name claims is the one thing it does not establish. The
instance was `test_the_same_repository_unforked_reaches_the_reviewer` in
`tests/test_guest_artifact_refusal.py`: two `assertNotIn`s and no return code.
A fault injected into `bin/sd-review` that had nothing to do with guest mode
left it green. **Assert the success positively** — the exit code, and some
output only the path under test produces — then the absence assertions are
narrowing a result that is already known to be the right one.

Nothing static catches this. The assertions are real, the operands come from
the code under test, and only the test's purpose says they are the wrong
assertions, which is why the sweep in `tests/test_suite_shape.py` did not see
it and no widening of that sweep would.

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
