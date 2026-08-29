# Design — default to local subscription review lanes

> **Revision note.** Two adversarial review rounds. Round 1 found eight defects,
> seven blocking. Round 2 found six more, all verified against the source:
> the false "byte-identical" claim (`configurationDigest` necessarily changes),
> a `--plan-only` flag the shell entrypoint does not have, an unspecified `POLICY_KEYS`
> registration and back-compat default for `ensembleProviders`, an API mismatch
> between `_read_json` and `_parse_argv_payload`, an unmapped-exit fallback of
> `failed` rather than the asserted `unavailable`, and an exit-code probe that
> would have measured the wrong code path outside a git repository.
>
> Round 3 found four more: a second scope vocabulary
> (`SCOPES` at `:51` is `changes|branch|codebase|pr`, not the internal
> `worktree|branch_delta|codebase`), the eligibility gate's inability to reuse
> `argv[0]` or the provider `PATH` at plan time, an unenumerated
> AC9 surface set, and an AC7 baseline command missing the required
> `--attempt-id`.
>
> Round 3 also left three concerns open, because fixing them in-round would have
> exceeded the review contract's three-round maximum. They were applied
> afterwards on explicit instruction and are now closed: **C-17**, the
> `ensembleProviders` absent-key default injecting `codex` into configs that do
> not define it (fixed by deriving the default from the configured identifiers —
> see "The absent-key default must be *derived*, not literal"); **C-18**, AC7
> reading fields at the JSON root that only exist under `.receipt` /
> `.plan`; and **C-19**, a missing `codex` binary failing the default shell run
> (see "A missing `codex` binary must not fail the run").
>
> This document reflects the corrected design. Where a rejected approach is
> instructive it is kept under "Rejected alternatives" rather than deleted.

## Where the edits go

`templates/**` is the source of truth (`AGENTS.md:29-33`). Root-level
`scripts/*` are byte-verified mirrors refreshed by `make sync` (`Makefile:29`,
`install.py . --force`). The behavioral tests import the template scripts
directly — `tests/test_review_stage.py:27` loads
`PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-local.py"`.

Every code edit below therefore targets `templates/scripts/...`, and `make sync`
propagates it. Editing the root copy first would be overwritten and would leave
the tests reading unchanged code.

## Why a `costTier: "none"` provider is most of the ordering work

`review-local.py:1247-1251` and `1269-1273` already select with

```python
sorted(eligible, key=lambda item: (COST_TIERS.index(item.cost_tier), item.identifier))[:1]
```

and `COST_TIERS = ("none", "low", "medium", "high")` (`:53-55`). A provider
declared `costTier: "none"` wins those paths with **no change to selection
code**. The ordering requirement is satisfied by data.

That leaves five real problems: the degradation hazard, the hardcoded ensemble,
the adapter, the shell dispatch, and the duplicated default config.

## Problem 1 — the degradation hazard (the one that matters)

This is the defect that would have shipped. Trace it:

| Step | Site | Result |
| --- | --- | --- |
| low-risk change selects only the cheapest provider | `:1247-1251` | `codex` alone |
| executable not found | `:1677-1680` | `unavailable` attempt, **no retry of another provider** |
| aggregate outcome | `:1850` | `unavailable` dominates |
| coordinator interprets it | `review.py:1889` | exit 3, `status="failed"` |

So on any machine without the Codex CLI, a naive version of this change turns a
working prism review into a failed review. That is a regression for the majority
of consumers.

**Fix: make the provider ineligible when the CLI is absent.** Eligibility is
already computed at `review-local.py:1211-1215`:

```python
eligible = [
    provider
    for provider in providers
    if provider.enabled
    and str(target["scope"]) in provider.scopes
    ...
]
```

Add an availability predicate to that filter for adapters that name a required
executable. When `shutil.which("codex")` is `None`, the codex provider is not
eligible, so no selection path can pick it — prism is once again the cheapest
eligible provider.

### The predicate must agree with the runtime check

`_run_provider` does its own availability test at `:1677`:

```python
executable = shutil.which(argv[0], path=environment.get("PATH"))
```

Two properties of that line constrain the gate.

**It resolves against the provider environment, not `os.environ`.** Today those
are the same `PATH`: `build_tool_environment` (`sd_ai_command_pack_lib.py:402`)
starts from `dict(os.environ)` and overrides only `CACHE_ENV_KEYS` and
`GIT_TERMINAL_PROMPT` — it never touches `PATH`. So a gate calling plain
`shutil.which("codex")` agrees with the runtime today. Record that as the
*reason* it is safe, not as a coincidence: if `build_tool_environment` ever
sanitizes `PATH`, the gate would pass while the runtime reported `unavailable`,
and the exact regression this design exists to prevent comes back silently. Add
a test asserting the two resolve identically rather than relying on inspection.

**The gate cannot reuse `argv[0]`.** Eligibility is computed at `:1211-1215`,
during planning; `_expand_argv` has not run yet, and a builtin provider's
configured `argv` is `[]` (`:402`), so there is no `argv[0]` to read. And
`build_tool_environment` is not called until `:2077`, after selection — so the
gate has no provider environment available either.

The predicate therefore needs an explicit **adapter → required executable** map
in the module (`{"codex": "codex"}`, with `prism`/`gito`/`argv` absent and so
unconstrained), consulted by identifier. Deriving the executable from `argv` at
plan time is not possible, and calling `build_tool_environment` a second time
during planning would duplicate cache setup for no benefit.

### What "no behavior change" does and does not cover

The gate preserves **provider selection, execution, and outcome**. It does not
and cannot preserve **receipt identity**, and an earlier draft of this design
claimed "byte-identical to `origin/main`", which is false.

`configuration_digest=_digest(config)` (`:2293`) hashes the entire configuration
object, `providers` included. Adding an entry to `_default_config()` changes it
for every consumer on the default config whether or not the provider is ever
eligible — eligibility is computed later, at `:1211-1215`, from the already
hashed config. The changed digest then propagates:

| Site | Field |
| --- | --- |
| `review-local.py:1307` | `plan["configurationDigest"]` |
| `review-local.py:1309` | `plan["policyDigest"] = _digest(plan)` |
| `review-local.py:1978` | receipt `policyDigest` |
| `review.py:950` | router evidence `configurationDigest` |

Adding `policy.ensembleProviders` to the default policy changes it a second
time, for the same reason.

This is contained, and checked rather than assumed:

- **Nothing in the pack reuses a receipt by digest.** `grep -n
  "reuse\|cached\|stale" templates/scripts/sd-ai-command-pack-review.py` returns
  nothing. There is no cache to invalidate.
- **The router never compares the value.** `src/protocol.js:437-439` validates
  `localReview.configurationDigest` as a 64-hex string and carries it; route
  lowering at `src/router.js:163-165` keys on `outcome`, `confidence`, and
  `dispositionCounts.unresolved`. (The `configurationDigest` in
  `src/review-plan-authorization.js` is the routed-review lane catalog's, a
  different field with the same name.)

So the honest claim — the one the PRD and the AC now make — is that a consumer
without the Codex CLI runs the same providers and gets the same outcome, and
that their receipts carry a new identity once. A review-configuration change
*should* produce a new configuration digest; suppressing it would be the bug.

Why this beats adding a retry-next-provider fallback:

- it is a filter, not a control-flow change, so the selection engine is
  untouched;
- "the tool isn't installed" is genuinely an eligibility fact, not a runtime
  failure, and modelling it as eligibility is more honest;
- a fallback would also mask genuine runtime failures of a provider that *is*
  installed, which should still surface.

The residual gap — no fallback when an installed provider fails at run time — is
pre-existing, unchanged by this task, and recorded in the PRD's out-of-scope
list rather than silently inherited.

## Problem 2 — the hardcoded ensemble

`review-local.py:1257-1263` filters `eligible` to the literal
`{"prism", "gito"}` for the substantive-risk and repeated-family paths. It
ignores cost tiers, so a free provider not named there is skipped exactly where
review matters most, and the literal rots as providers change.

**Rejected fix: `selected = list(eligible)`.** The first draft proposed this. It
is wrong, for a reason worth recording:

- `eligible` is every enabled, in-scope, data-handling-allowed provider —
  *including arbitrary repository-defined `argv` providers* (`:398`). Using it
  silently promotes `auto` substantive review to the equivalent of `all` for any
  consumer with a custom provider. That is a behavior change nobody asked for
  and a cost increase for the exact repositories most likely to have expensive
  custom reviewers.
- The first draft claimed membership was inert downstream. It is not. It feeds
  the policy digest and receipt identity (`:1295`, `:1973`) and the router
  evidence's `providers`, `latencyMs`, and maximum `costTier`
  (`review.py:951`).
- `tests/test_review_stage.py:1115-1118` asserts the exact list
  `["gito", "prism"]` for `policyId == "substantive-ensemble"`, so the change is
  observable and covered.

**Accepted fix: a bounded, configuration-derived set.** Add
`policy.ensembleProviders`, defaulting to the three builtin ids
`["codex", "gito", "prism"]`. Selection filters `eligible` by membership in that
list.

`policy` is strictly validated against a closed key set — `set(policy) -
POLICY_KEYS` raises `"review policy must use only supported fields"` (`:507`,
`POLICY_KEYS` at `:149`) — so the key needs four things, not one:

1. registration in `POLICY_KEYS`, or every config carrying it is rejected;
2. parsing through `_string_list` and validation of each member against the
   configured provider ids, exactly as `requiredProviders` does at `:519-525`;
3. normalization into `normalized_policy` (`:526-530`) so the key is always
   present downstream and selection never has to branch on absence;
4. a default supplied by `_default_config()`.

### The absent-key default must be *derived*, not literal (C-17)

A repository with an existing `.sd-ai-command-pack/review.json` omits the key,
and `_default_config()` does not apply to that file — so the **normalizer**
supplies the default, not the default config.

An earlier draft said the normalizer should supply the literal
`["codex", "gito", "prism"]`. That is wrong, and it contradicts this design's
own compatibility claim. Members are validated against the configured provider
ids the way `requiredProviders` is (`:519-525`), and configured ids come solely
from the consumer's own provider list (`:502-505`). A repository defining only
`prism` and `gito` — the shape of the fixture at
`tests/test_review_stage.py:66-109` — would get `codex` injected, fail the
unknown-id check, and hard-error on **every run**. The change would break every
custom-configured consumer.

The default must therefore be derived from the configuration in hand:

```python
ENSEMBLE_DEFAULT_ORDER = ("codex", "gito", "prism")
# when policy.ensembleProviders is absent:
default_ensemble = [i for i in ENSEMBLE_DEFAULT_ORDER if i in identifiers]
```

| Configuration | Derived default | Matches today? |
| --- | --- | --- |
| shipped default (codex, gito, prism) | `["codex","gito","prism"]` | new behavior, intended |
| legacy custom (prism, gito) | `["gito","prism"]` | yes — identical to the literal it replaces |
| custom with only `argv` providers | `[]` | yes — `[p for p in eligible if p.identifier in {"prism","gito"}]` is also empty today |

The empty case is pre-existing behavior, not a regression introduced here. Do
not "fix" it by falling back to every eligible provider — that is the
`list(eligible)` mistake rejected above, and it would sweep in custom `argv`
providers.

An **explicit** `ensembleProviders` stays strictly validated: a member naming a
provider the configuration does not define is an input error, because the author
chose it deliberately. A member naming a provider that is defined but not
currently eligible is simply filtered out — that is what makes the `codex` entry
harmless on a machine without the CLI.

This:

- removes the literal from the selection code, so it cannot drift as a *code*
  constant (AC4);
- stays bounded, so a custom `argv` provider is not swept in;
- is overridable by a repository that genuinely wants a different ensemble.

`tests/test_review_stage.py:1115-1118` updates from `["gito", "prism"]` to
`["codex", "gito", "prism"]` when a codex stub is present, and remains
`["gito", "prism"]` when it is not — which doubles as coverage for Problem 1.

## Problem 3 — the `codex` adapter

### Why not `codex review`

`codex review` is the purpose-built reviewer, but against `codex-cli 0.147.0`
its entire flag surface is `--strict-config`, `-c`, `--uncommitted`, `--base`,
`--commit`, `--title`, `--enable`, `--disable`. No structured output. Deriving
findings from prose by regex would feed a fragile parser into an authoritative
receipt. Rejected.

### Why `codex exec`

`codex exec` has `--output-schema <FILE>` and `-o/--output-last-message <FILE>`
— the only supported path from the CLI to parseable findings.

### Command construction — `_expand_argv` (`review-local.py:1376`)

Note the function is `_expand_argv`, not `_provider_command`; the prism and gito
branches are at `:1386` and `:1412`. Add a `codex` branch:

```
codex exec
  -s read-only
  -C <repo>
  --ephemeral
  --output-schema <attempt_dir>/codex-schema.json
  -o <attempt_dir>/codex-review.json
  <scope-specific prompt>
```

- `-s read-only` is a correctness requirement. Non-PR scopes are worktree-only;
  a reviewer must not be able to mutate the tree, and a sandbox flag makes that
  a property rather than a promise.
- `--ephemeral` keeps review runs out of persisted Codex session history.
- `-C <repo>` binds the working root explicitly.
- The output filename is **not** `provider-output`: `gito` passes that name to
  `--out` as a *directory* and `_gito_payload` reads
  `attempt_dir/provider-output/code-review-report.json` from inside it
  (`:1554-1557`). Codex's `-o` takes a file.

Scope maps into the prompt, because `codex exec` has no `--base`:

| `target["scope"]` | prompt instructs the agent to review |
| --- | --- |
| `worktree` | staged, unstaged, and untracked changes limited to the target paths |
| `branch_delta` | `git diff <base>..<head>` |
| `codebase` | the tracked files at the target paths |

The shared tail of `_expand_argv` (`:1453-1459`) applies the
`MAX_EXPANDED_ARGV_BYTES` bound to every adapter, so the prompt is bounded
without new code.

### The schema — field names are load-bearing

Not a shipped file. `config/` is not a pack-installed surface: there is no
`templates/config/` and `manifest.json` has no `config/` target. The
`remoteIntegration.descriptorPath` value `config/routed-review-setup-v1.json` is
a *consumer-owned* path the pack reads if present, not one it installs.

Instead, materialize it per attempt. `review-local.py:1657-1658` already creates
`attempt_dir` with mode `0o700` immediately before the provider runs; write
`attempt_dir/codex-schema.json` there from a module-level literal, and point
`--output-schema` at it. The schema and the parser then live in one module and
cannot drift.

The schema must constrain the final message to the fields the **normalizer**
reads, which are not the obvious ones:

```json
{"status": "clean" | "findings",
 "findings": [{"path": str, "line": int|null, "severity": str,
               "summary": str, "family": str}]}
```

`_bounded_provider_findings` (`review-local.py:1640-1642`) reads `summary` and
`family`, defaulting them to `"provider finding"` and `"other"`. The first draft
specified `title` and `details` — which validate fine and then silently discard
every finding's content, leaving a receipt full of findings all summarized as
"provider finding". `title`/`details` is what `_gito_payload` maps *from*
(`:1600-1604`), not what the shared normalizer reads.

### Payload parsing — `_parse_provider_payload` (`:1612-1616`)

Add a `codex` branch reading `attempt_dir/codex-review.json` via
`_read_json(path, limit=MAX_OUTPUT_BYTES, ...)` — the bounded reader
`_gito_payload` uses at `:1557`.

**The two readers are not interchangeable.** `_read_json` is
`(path: Path, *, limit, label) -> object` (`:358`); `_parse_argv_payload` is
`(stdout: bytes) -> dict | None` (`:1515`). The codex output arrives as a file,
not on stdout, so `_parse_argv_payload` cannot be called on the `_read_json`
result — it would be handed a parsed object where it expects raw bytes. The
correct shape is to factor the *validation* body of `_parse_argv_payload`
(`:1515-1522`: `status` in `OUTCOMES`, `findings` a list within `MAX_FINDINGS`)
into a helper taking the already-parsed object, and have both call sites use it.
That keeps one validation rule rather than a second copy that drifts.

Return `None` on any mismatch; that is the existing contract for "provider
produced nothing usable".

### Exit-code mapping

`0 -> clean`. Concrete non-zero codes must be **observed** against the installed
CLI during implementation, not assumed.

The unmapped-code fallback is **not** the adapter's to choose. `:1716` is

```python
status_value = provider.outcome_by_exit.get(exit_code, "failed")
```

so anything absent from `outcomeByExitCode` becomes `failed`, and an earlier
draft of this design was wrong to assert it should be `unavailable` — that would
require a code change nobody needs. `failed` already satisfies the actual
requirement: no unmapped code may become `clean` or `findings`, because a
`findings` outcome from a crashed reviewer would carry an empty finding list and
read as a clean review.

`outcomeByExitCode` is capped at 32 entries (`:450-452`), which is ample for an
observed set and is a reason not to speculatively enumerate codes.

Findings presence comes from the parsed payload, not the exit code.

### `dataHandling`

`public-network`. Codex transmits diff content to a third-party service. `prism`
and `gito` declare `private-network`; copying that would be a false statement a
repository narrowing `allowedDataHandling` would then act on. `public-network`
is already in `DATA_CLASSES` (`:53`) and the default policy allows all three, so
the default install runs codex and a restricted repository correctly excludes it.

Note `argv` may simply be omitted — it defaults to `[]` (`:402`). `:405-407`
only forbids a builtin adapter that *supplies* argv.

## Problem 4 — the shell entrypoint

`review-local.sh` does not have a generic tool loop. It carries per-tool state
and dispatch for prism and gito only, and an unrecognized token reaches the `*)`
branch, warns `"No command configured for local review tool '<name>'"`, and sets
`OVERALL_STATUS=2`. So changing the default list at `:643` and the aliases at
`:196-197` alone would make the default set *immediately fail*.

Seven sites, enumerated rather than remembered:

| Site | What it is |
| --- | --- |
| `list_tools()` | hardcoded `printf` block behind `--list-tools` |
| `:196-197` | the `usage()` heredoc's tool table and `all`/`default` alias text |
| `:643` | `raw_tools="${SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS:-prism gito}"` |
| `:702-703` | `NEED_PRISM=0` / `NEED_GITO=0` state init |
| `:717-718` | the `all\|default` alias branch |
| `:732`, `:735` | the per-tool `case` arms |
| `:753`, `:757` | the `if [ "$NEED_X" -eq 1 ]` execution guards |

plus a new `run_codex_review` alongside `run_prism_reviews` and
`run_gito_review`. `list_tools()` is separate from `usage()`, so a plan that
says "update `--help`" misses it.

**Preserve the override ordering.** `configured_command_for_tool` is consulted
*before* the builtin `case` (`:723-728`). A consumer who already runs Codex
through `SD_AI_COMMAND_PACK_REVIEW_LOCAL_CODEX_COMMAND` keeps that override
after `codex` becomes builtin, because the custom branch still wins. Moving the
builtin `case` ahead of it would silently break those consumers.

### A missing `codex` binary must not fail the run (C-19)

`run_prism_reviews` (`:530-538`) and `run_gito_review` (`:591-599`) are
identical in shape: read `..._MODE` (default `required`), `is_disabled` → warn
and return, `! have <x>` → warn, `mark_overall_failure`, return.

`run_codex_review` must **not** copy that. Codex is in the new default tool set,
so under the required shape every machine without the Codex CLI — which is most
of them — starts failing a command that passes today. That is exactly the
degradation AC7 guards against in the stage, arriving instead through the shell.

There is no `optional` tier to reach for: `is_disabled` recognizes only
`0|false|FALSE|no|NO|skip|none`, so the string `optional` currently falls
through and behaves as required. The tier has to be introduced, as a sibling
predicate rather than an extension of `is_disabled` — `optional` means "run if
present", and folding it into the disable list would skip Codex on the machines
that *do* have it.

| Mode | `codex` present | `codex` absent |
| --- | --- | --- |
| `optional` (new default for codex) | runs | warn, return, **no** `mark_overall_failure` |
| `required` (prism/gito default, unchanged) | runs | warn, `mark_overall_failure` |
| `0`/`false`/`no`/`skip`/`none` | skipped | skipped |

Prism and gito keep `required`. A consumer that wants the Codex lane enforced
sets `SD_AI_COMMAND_PACK_REVIEW_LOCAL_CODEX_MODE=required` and gets the failure
back, which is also what makes the mode testable: the absent-binary run must
exit 0 by default and non-zero under `required`. Asserting only the first would
pass against a lane that was never wired up.

Scope handling follows `run_gito_review`, which already reads
`REVIEW_LOCAL_SCOPE`: `all` reviews the tree, anything else reviews the diff
against the base.

The **shell** entrypoint has **no `--plan-only` flag** — its parser accepts only `--all`,
`--codebase`, `--full`, `--full-codebase`, `--help`/`-h`, `--list-tools`,
`--diff`/`--changed`, `--scope[=]`, and `--`. AC8 therefore verifies by running
the script with a stub `codex` first on `PATH` and asserting the stub was
invoked and the "No command configured" warning is absent. `--list-tools`
listing `codex` is necessary but not sufficient: it is a hardcoded `printf`
independent of dispatch, so it can be correct while dispatch is still missing.

## Problem 5 — the duplicated default config

`review-local.py:_default_config()` and `review.py:load_review_configuration()`
(`:220`) carry independent literal copies of the provider list, with nothing
enforcing agreement. Adding a provider to one only would make the coordinator
plan a different set than the stage executes.

Fix: a test asserting the two agree on provider ids and cost tiers. Extracting a
shared module is cleaner but crosses a script boundary the pack keeps
deliberately separate; the test buys the safety far more cheaply. Recorded as
accepted debt.

## The two Codex lanes are different things

They must not be conflated, and the first draft did conflate them:

| | Native lane | Provider lane (new) |
| --- | --- | --- |
| command | `codex review` | `codex exec` |
| driven by | the agent, per `sd-review-local/SKILL.md:155` | the coordinator |
| structured output | no | yes, via `--output-schema` |
| in the selection policy | no | yes |
| reaches router evidence | **no** | yes, via the local receipt |

The coordinator builds router evidence solely from its own local-stage receipt
(`review.py:1839`, `:1941`). There is no input for native-lane results. So a
claim that documenting the native lane makes its result "feed the router" is
false, and the PRD no longer makes it.

Documentation must name both lanes distinctly and say which one participates in
routing.

## Release policy

`CONTRIBUTING.md:136-142` makes this CI-enforced, not advisory: any change to
`templates/**` or `docs/SD_AI_COMMAND_PACK.md` requires a `manifest.json`
version bump plus a matching top `CHANGELOG.md` heading, and a `Release payload
gate` job blocks merge without them. A version bump additionally requires an
all-pass `docs/fleet/candidate-validation.json` produced or reused by
`make release-prep`.

The first draft declared all version work out of scope, which would have made
the PR unmergeable. It is in scope. `manifest.json:6` also still describes the
pack as shipping "Prism/Gito defaults" and must be updated.

## Compatibility and rollback

- Consumers pick this up on their next pack install.
- A repository with its own `.sd-ai-command-pack/review.json` does not get the
  new provider — `_default_config()` applies only when that file is absent.
  Those consumers opt in by adding the provider themselves; the documentation
  must say so. They *do* get the `ensembleProviders` default from the policy
  normalizer, which is why that default lives there rather than in
  `_default_config()`.
- A consumer without the Codex CLI runs the same providers and gets the same
  outcome, by construction (Problem 1). Their `configurationDigest`,
  `policyDigest`, and `receiptId` change once, because the review configuration
  genuinely changed; see "What 'no behavior change' does and does not cover".
- Rollback is a revert. No migration, no persisted state, no schema version
  change.

## Rejected alternatives

- **`selected = list(eligible)` for the ensemble.** Unbounded; promotes `auto`
  to `all` for custom configurations; observably changes receipt identity and
  router evidence. See Problem 2.
- **A retry-next-provider fallback instead of an eligibility gate.** Larger
  blast radius, changes control flow, and masks genuine runtime failures.
- **Register codex through the existing `argv` adapter.** Needs no Python
  change, but pushes scope-to-command translation and exit-code mapping into
  per-repository config and gives no home for the read-only sandbox guarantee.
- **Parse `codex review` prose.** Best review quality, unacceptable parser
  fragility feeding an authoritative receipt.
- **Add a `subscription` cost tier.** `COST_TIERS` is closed and threaded
  through selection, receipts, and the router's `cost_mapping`. `"none"` already
  means "no marginal cost".
- **Extract the shared default config into a common module.** Correct
  long-term, larger blast radius than this task warrants. Covered by a
  divergence test and recorded as debt.
