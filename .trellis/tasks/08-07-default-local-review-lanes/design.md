# Design — default to local subscription review lanes

> **Revision note.** An adversarial review of the first draft found eight
> defects, seven blocking. This document reflects the corrected design. Where a
> rejected approach is instructive it is kept under "Rejected alternatives"
> rather than deleted.

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
eligible, so no selection path can pick it, and the resulting behavior is
**byte-identical to `origin/main`** — prism is once again the cheapest eligible
provider.

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
list. This:

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
`_gito_payload` uses at `:1557` — then apply the validation
`_parse_argv_payload` performs (`:1515-1522`): `status` in `OUTCOMES`,
`findings` a list within `MAX_FINDINGS`. Return `None` on any mismatch; that is
the existing contract for "provider produced nothing usable".

### Exit-code mapping

`0 -> clean`. Everything unmapped must default to `unavailable`, never `clean`
and never `findings` — a `findings` outcome from a crashed reviewer would be
silently empty and read as a clean review. The concrete non-zero codes must be
**observed** against the installed CLI during implementation, not assumed.
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
and dispatch (`:702`, `:730`) for prism and gito only, and an unrecognized token
falls through to the unknown-tool branch with exit 2. So changing the default
list at `:643` and the aliases at `:196-197` would make the default set
*immediately fail*.

The shell work is therefore: add codex dispatch and its state alongside the
existing two, then update `:643`, `:196-197`, and `--help`. AC8 verifies by
invoking the tool, not by reading the help text.

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
- A repository with its own `.sd-ai-command-pack/review.json` is unaffected —
  `_default_config()` applies only when that file is absent. Those consumers opt
  in by adding the provider themselves; the documentation must say so.
- A consumer without the Codex CLI sees no behavior change at all, by
  construction (Problem 1).
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
