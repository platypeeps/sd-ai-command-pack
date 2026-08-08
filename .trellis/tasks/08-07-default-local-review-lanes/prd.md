# Default to local subscription review lanes before remote paid review

## Goal

Make a zero-marginal-cost local review lane a first-class configured provider
that runs before the metered ones, so routine review is paid for by a
subscription the developer already holds rather than by per-token API spend or a
native Copilot request — **without** degrading review for anyone who does not
have the Codex CLI installed.

## Problem

The pack's local review stage ships two builtin providers, both metered:

- `templates/scripts/sd-ai-command-pack-review-local.py:251` — `prism`,
  `costTier: "low"`
- `templates/scripts/sd-ai-command-pack-review-local.py:266` — `gito`,
  `costTier: "medium"`

`templates/scripts/sd-ai-command-pack-review.py:220` carries a second,
independent copy of that default provider list for the `sd-review` coordinator.
Nothing enforces that the two agree.

`templates/scripts/sd-ai-command-pack-review-local.sh:643` defaults its tool set
to `prism gito`, and lines 196-197 alias `all` and `default` to the same pair.

The Codex CLI is on the supported toolchain but appears only as an *additive
peer lane* in the skill templates — never a configured provider, never a
default, explicitly outside the selection policy. The cheapest available
reviewer is the one the system is least likely to run.

Two selection paths determine what executes:

1. `review-local.py:1247-1251` and `1269-1273` sort eligible providers by
   `COST_TIERS.index(cost_tier)` and take the cheapest. `COST_TIERS` is
   `("none", "low", "medium", "high")` (`:53-55`), so a provider declared
   `costTier: "none"` wins these paths with no ordering change.
2. `review-local.py:1257-1263` hardcodes the substantive-risk and
   repeated-family ensemble to the literal `{"prism", "gito"}`, ignoring cost
   tiers. It is the path taken for the changes that most need review, so a free
   provider not named in that literal is skipped precisely when it matters.

## The failure this must not cause

Adding a `costTier: "none"` provider naively makes the pack **worse** for anyone
without the Codex CLI. On a low-risk change the cheapest-only path selects
codex alone (`:1247-1251`); a missing executable yields an `unavailable` attempt
with no retry of another provider (`:1677-1680`); `unavailable` dominates the
aggregate (`:1850`); and the coordinator turns that into a hard failure —
`review.py:1889` returns exit 3 with `status="failed"` for
`local_status in {"unavailable", "failed", "cancelled"}`.

So the naive change converts "review ran on prism" into "review failed" for
every consumer without Codex. Preventing that is a requirement, not a nicety.

## Requirements

- R1. Add a builtin `codex` provider to both default configurations with
  `costTier: "none"`, so it is selected ahead of `prism` and `gito` on every
  cost-ordered selection path.
- R2. Add a `codex` adapter: command construction per scope, and payload parsing
  that yields findings carrying real content in the fields the existing
  normalizer reads.
- R3. Make the `codex` provider **ineligible** when the Codex CLI is not
  present, so selection never picks it and consumers without the CLI keep
  today's *provider selection, execution, and outcome*.

  This is deliberately narrower than "no change at all", which is not
  achievable. `configurationDigest` is `_digest(config)` over the whole
  configuration object including `providers` (`review-local.py:2293`), so adding
  an entry to `_default_config()` changes it for every consumer on the default
  config regardless of whether the provider is ever eligible. That flows into
  `policyDigest` (`:1309`), the receipt (`:1978`), and the router evidence field
  (`review.py:950`). The change is confined to identity: nothing in the pack
  reuses a receipt by digest, and the router validates
  `localReview.configurationDigest` as a 64-hex string
  (`sd-github-review src/protocol.js:437-439`) without ever comparing its value
  — evidence eligibility is decided by `outcome`, `confidence`, and
  `dispositionCounts.unresolved` (`src/router.js:163-165`). So previously issued
  receipts stop matching a freshly computed digest once, which is the correct
  signal for "the review configuration changed", not a regression to hide.
- R4. Replace the hardcoded `{"prism", "gito"}` ensemble literal with a
  configuration-derived, explicitly bounded set — not an unbounded "everything
  eligible", which would silently promote `auto` substantive review to `all` for
  any repository with custom `argv` providers.
- R5. Keep the two default-provider declarations in agreement and add a check
  that fails on divergence.
- R6. Update the shell entrypoint so `codex` is genuinely executable through it,
  including dispatch and state — not only the alias, default, and help text.
- R7. Distinguish the two Codex lanes in documentation. They are different
  things and must not be conflated.
- R8. Declare `dataHandling` honestly: Codex transmits diff content to a
  third-party service.
- R9. Satisfy the repository's release policy for shipped-payload changes.

## Constraints

- **`templates/**` is the source of truth.** `AGENTS.md:29-33`: root-level
  installed copies are byte-verified mirrors; change the template side first and
  keep the installed copy synchronized via `make sync`. Behavioral tests load
  the template scripts directly (`tests/test_review_stage.py:27`,
  `tests/test_review_controller.py:20`). Every edit in this task targets
  `templates/scripts/...`; editing root `scripts/` first is backwards and the
  next `make sync` would overwrite it.
- `review-local.py:398` allows exactly `{"prism", "gito", "argv"}` as adapters.
  A new builtin adapter must be added there and to every place branching on
  adapter identity: command construction in `_expand_argv` (`:1376`, with the
  prism/gito branches at `:1386` and `:1412`) and payload parsing in
  `_parse_provider_payload` (`:1612-1616`).
- Findings are normalized by `_bounded_provider_findings`, which reads
  `path`, `line`, `severity`, **`summary`**, and **`family`**
  (`review-local.py:1640-1642`), defaulting the last two to
  `"provider finding"` and `"other"`. A schema emitting `title`/`details`
  instead would validate and then silently discard every finding's content.
- Ensemble membership is not inert: it propagates into the policy digest and
  receipt identity (`review-local.py:1295`, `:1973`) and into the router
  evidence's `providers`, `latencyMs`, and maximum `costTier`
  (`review.py:951`). `tests/test_review_stage.py:1115-1118` asserts the exact
  list `["gito", "prism"]` for `substantive-ensemble`.
- `COST_TIERS`, `QUALITY_TIERS`, `DATA_CLASSES` (`review-local.py:53-55`) are
  closed vocabularies validated at `:431-439`. `costTier: "none"` and
  `dataHandling: "public-network"` are already members; no vocabulary change is
  needed and none should be made.
- `argv` may be omitted for a builtin adapter — it defaults to `[]`
  (`review-local.py:402`). `:405-407` only forbids a builtin adapter that
  *supplies* argv.
- `codex review` has **no** structured-output flag (verified against
  `codex-cli 0.147.0`: only `--uncommitted`, `--base`, `--commit`, `--title`,
  `-c`, `--enable/--disable`). `codex exec` does support `--output-schema
  <FILE>` and `--output-last-message <FILE>`, the only supported path to
  structured findings.
- Nothing the adapter needs at run time may live under `config/`. That directory
  is consumer-owned, not a pack-installed surface: there is no
  `templates/config/` and `manifest.json` declares no `config/` install target.
- `policy` is strictly validated against a closed key set:
  `if not isinstance(policy, dict) or set(policy) - POLICY_KEYS` raises
  `"review policy must use only supported fields"` (`review-local.py:507`,
  with `POLICY_KEYS` at `:149`). A new `ensembleProviders` key must be added to
  `POLICY_KEYS`, must be normalized into `normalized_policy` alongside
  `allowedDataHandling` and `requiredProviders` (`:526-530`) so it is present
  even when omitted, and must validate its members against the configured
  provider ids the way `requiredProviders` does at `:519-525`. Omitting the
  `POLICY_KEYS` registration makes every configuration carrying the key a hard
  input error.
- The runtime availability check is
  `shutil.which(argv[0], path=environment.get("PATH"))` (`review-local.py:1677`),
  and R3's gate must agree with it. The gate cannot reuse either input: at
  `:1211-1215` planning has not run `_expand_argv`, a builtin provider's `argv`
  is `[]` (`:402`), and `build_tool_environment` is not called until `:2077`.
  The gate therefore needs an explicit adapter→executable map. The two `PATH`
  values agree today because `build_tool_environment`
  (`sd_ai_command_pack_lib.py:402`) copies `os.environ` and overrides only
  `CACHE_ENV_KEYS` and `GIT_TERMINAL_PROMPT` — a test must hold that true rather
  than the design assuming it.
- The unmapped-exit-code outcome is **`failed`**, not `unavailable`, and it is
  not configurable: `provider.outcome_by_exit.get(exit_code, "failed")`
  (`review-local.py:1716`). `outcomeByExitCode` is additionally capped at 32
  entries (`:450-452`). So the adapter cannot choose its own fallback outcome;
  it can only enumerate the codes it knows. `failed` is the correct conservative
  default anyway — the requirement is that no unmapped code maps to `clean` or
  `findings`, which the built-in default already guarantees.
- The shell entrypoint has per-tool dispatch and state, not a generic loop.
  Adding a tool touches seven sites, not the three a `--help` reading suggests:
  `list_tools()`, the `usage()` heredoc (`:196-197`), the default tool set
  (`:643`), state init (`:702-703`), the `all|default` alias branch
  (`:717-718`), the per-tool `case` (`:732`, `:735`), and the execution guards
  (`:753`, `:757`). An unrecognized token reaches the `*)` branch, warns
  `"No command configured for local review tool '<name>'"`, and sets
  `OVERALL_STATUS=2`.
- `configured_command_for_tool` is consulted **before** the builtin `case`
  (`:723-728`), so a consumer who already sets
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_CODEX_COMMAND` keeps their override after
  `codex` becomes builtin. That ordering must not be changed.
- **Release policy is CI-enforced.** `CONTRIBUTING.md:136-142`: any change to
  `templates/**` or `docs/SD_AI_COMMAND_PACK.md` requires a `manifest.json`
  version bump and a matching top `CHANGELOG.md` heading; a `Release payload
  gate` job blocks merge otherwise. A version bump additionally requires an
  all-pass `docs/fleet/candidate-validation.json` from `make release-prep`.
- `manifest.json:6` still describes the pack as shipping "Prism/Gito defaults".

## Acceptance Criteria

- [ ] AC1. `_default_config()` in `templates/scripts/...review-local.py` returns
  a `codex` provider with `adapter: "codex"`, `costTier: "none"`,
  `dataHandling: "public-network"`, and an `outcomeByExitCode` mapping; the
  equivalent entry exists in `...review.py`'s default config.
- [ ] AC2. A test fails when the two default provider lists diverge on provider
  ids or cost tiers.
- [ ] AC3. The adapter allow-list at `review-local.py:398` accepts `codex`, and
  both `_expand_argv` and `_parse_provider_payload` branch on it.
- [ ] AC4. `grep -rn '{"prism", "gito"}' templates/scripts/ scripts/` returns
  nothing, and the ensemble set is bounded by configuration rather than being
  every eligible provider.
- [ ] AC5. With a stub `codex` on `PATH`, a low-risk worktree review executes
  `codex` and does **not** execute `prism` or `gito`.
- [ ] AC6. With a stub `codex` on `PATH`, a substantive-risk review executes
  `codex` **and** the metered ensemble providers.
- [ ] AC7. With **no** `codex` on `PATH`, the stage's *behavior* matches
  `origin/main`: the same metered providers are selected and executed, the same
  aggregate outcome is produced, and `review.py` does not return exit 3. Compare
  against a baseline captured from the unmodified tree rather than against a
  hand-written expectation.

  The comparison must **exclude** `configurationDigest`, `policyDigest`, and
  `receiptId`. Those necessarily change per R3 and a diff that includes them
  fails for the wrong reason — which would push an implementer toward loosening
  the assertion until it passes. Compare the plan's `providers` list, `policyId`,
  each attempt's `status`, and the aggregate `outcome`; assert separately that
  `configurationDigest` differs from the baseline and is still a 64-hex string,
  so the identity change is proven intentional rather than incidental.
- [ ] AC8. `bash templates/scripts/...review-local.sh codex`, run with a stub
  `codex` first on `PATH`, invokes that stub and does **not** emit
  `No command configured for local review tool 'codex'`. There is no
  `--plan-only` flag on the shell entrypoint — the only options its parser accepts
  are `--all/--codebase/--full/--full-codebase`, `--help/-h`, `--list-tools`,
  `--diff/--changed`, `--scope[=]`, and `--`. `--list-tools` must also list
  `codex`, but that alone does not satisfy this criterion: `list_tools()` is a
  hardcoded `printf` block independent of dispatch, so it can be right while
  dispatch is still missing. With `SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS` unset
  the default set includes `codex`.
- [ ] AC9. Every template surface describing Codex as an additive or peer
  *review* lane is corrected, and the two lanes are named distinctly. The
  surface set is enumerated with `grep -rln -i codex templates/` — 16 files,
  most of them false positives — then each hit classified as local-review lane,
  planning-adversarial-review lane, or unrelated. In
  `templates/docs/SD_AI_COMMAND_PACK.md` the in-scope text is `:862-878`
  (current-diff peer lane) and `:1821-1826` under the `### Local Review`
  heading at `:1819`. Out of scope: `:32-35` and the entire
  `### Planning Artifact Review` section `:1798-1817`, which is a different
  feature; and `:1951`, `:1955`, `:2134-2137`, `:2162`, `:2240`, which are
  `codex/<slug>` branch names, `.codex/` directory listings, and platform-adapter
  references.
- [ ] AC10. `manifest.json` version is bumped, its description no longer
  promises "Prism/Gito defaults", and the top `CHANGELOG.md` heading matches.
- [ ] AC11. `make check` passes: `make test`, `make lint`, `make audit`,
  `make full-check` all green with zero failures. `tests/test_review_stage.py`
  and `tests/test_review_controller.py` are included, not only
  `tests/test_review_local.py`.
- [ ] AC12. `make sync` and `make surface-check` report no drift between
  `templates/` and the installed root copies.

## Out of scope

- Changing `prism` or `gito` behavior, cost tiers, or command construction.
- Changing the router's route-selection policy — owned by `sd-github-review`.
- Adding a retry-next-provider fallback to the selection engine. R3's
  eligibility gate solves this task's degradation problem without it. The
  absence of a fallback when a *configured and present* provider fails at run
  time is a pre-existing property, recorded here as a known gap.
- Adding the Claude-native lane as an executable provider. Claude Code's review
  is agent-driven, not a subprocess the coordinator can spawn.
- Feeding native-lane (`codex review`) results into the router. No input exists
  for that; the coordinator builds router evidence solely from its own local
  receipt (`review.py:1839`, `:1941`). Documentation cannot close that gap and
  must not claim to.
- The user-global Claude Code hook that auto-requests Copilot on push. It lives
  in `~/.claude/settings.json`, belongs to no repository, and is reported
  separately.

## Adversarial review ledger

Three automatic rounds, the maximum the project contract permits.

| ID | Round | Concern | Disposition |
| --- | --- | --- | --- |
| C-1 | 1 | Edits targeted root `scripts/`; `templates/**` is source of truth | Fixed |
| C-2 | 1 | Naive add regresses every consumer without the Codex CLI to exit 3 | Fixed — eligibility gate |
| C-3 | 1 | Schema used `title`/`details`; normalizer reads `summary`/`family` | Fixed |
| C-4 | 1 | `selected = list(eligible)` sweeps in custom `argv` providers | Fixed — bounded `ensembleProviders` |
| C-5 | 1 | Version bump declared out of scope, but CI-enforced | Fixed — in scope |
| C-6 | 1 | Runtime schema planned under `config/`, not a pack surface | Fixed — per-attempt materialization |
| C-7 | 1 | Native and provider Codex lanes conflated | Fixed |
| C-8 | 2 | "byte-identical" false; `configurationDigest` necessarily changes | Fixed — R3/AC7 reworded |
| C-9 | 2 | `--plan-only` asserted on the shell entrypoint, which has no such flag | Fixed |
| C-10 | 2 | `ensembleProviders` needed `POLICY_KEYS` registration and normalization | Fixed |
| C-11 | 2 | `_read_json`(object) does not compose with `_parse_argv_payload`(bytes) | Fixed — shared helper |
| C-12 | 2 | Unmapped exit default is `failed` (`:1716`), not `unavailable` | Fixed |
| C-13 | 2 | Exit-code probe ran outside a git repo without `-C`/`--skip-git-repo-check` | Fixed |
| C-14 | 3 | Gate cannot reuse `argv[0]` or the provider `PATH` at plan time | Fixed — explicit adapter→executable map |
| C-15 | 3 | AC9 surface set unenumerated; 12 of 16 grep hits unclassified | Fixed — full classification |
| C-16 | 3 | Two scope vocabularies conflated (`SCOPES` vs `target["scope"]`) | Fixed |
| C-17 | 3 | `ensembleProviders` absent-key default breaks custom configs | **OPEN** — see below |
| C-18 | 3 | AC7 `jq` paths read the root; the receipt is nested under `.receipt` | **OPEN** — see below |
| C-19 | 3 | Shell runner has no missing-CLI contract; AC8 probe reads `tee`'s status | **OPEN** — see below |

## Open blocking concerns — round 3, UNRESOLVED

The project adversarial-review contract permits at most two remediation rounds
(three automatic rounds total). Rounds 1 and 2 were reviewed and remediated.
Round 3's Codex lane produced the three concerns below. They are **not fixed**,
because fixing them would be a fourth automatic round. They are recorded here so
the next session starts from them, and **this plan is not approved for
implementation** until they are resolved by human judgment.

Each was verified against this checkout; none is speculative.

### C-R3-1 — the `ensembleProviders` absent-key default breaks custom configs

`design.md` and `implement.md` (Step 6) say an absent `policy.ensembleProviders`
normalizes to `["codex", "gito", "prism"]`, and that members must be configured
provider ids (mirroring `requiredProviders` at `review-local.py:519-525`).

Those two rules contradict each other. Provider ids come only from the
consumer's own provider list (`:502-505`). A repository with its own
`.sd-ai-command-pack/review.json` defining just `prism` and `gito` — the shape
of the fixture at `tests/test_review_stage.py:66-109` — would get `codex`
injected as a default, fail the unknown-id check, and hard-error on every run.
That directly contradicts this design's own compatibility claim that custom
configurations do not inherit the new provider.

Identified direction, not applied: the absent-key default must be derived from
the configuration in hand — the builtin ensemble names intersected with the ids
actually defined, e.g. `[i for i in ("codex","gito","prism") if i in ids]`. That
yields `["gito","prism"]` for a legacy custom config and all three for the
shipped default. Explicit members stay strictly validated.

This is the concern that most needs a decision: it is the difference between a
compatible change and one that breaks every custom-configured consumer.

### C-R3-2 — the AC7 baseline commands and jq paths are wrong

Two separate defects:

1. Step 0's receipt-capture used `--scope worktree` and omitted the required
   `--attempt-id`. Running it verbatim exits 2 with
   `argument --scope: invalid choice: 'worktree'`. The CLI vocabulary is
   `changes|branch|codebase|pr` (`:51`, `:2227`); `--attempt-id` is required
   (`:2240`). **This one was corrected in the round-3 host lane** — Step 0 now
   uses `--scope changes --attempt-id ... --plan-only`.
2. The AC7 `jq` expressions read `providers`, `policyId`, and the digests from
   the JSON root. On an executed run the payload is nested: `_report`
   (`:2173-2185`) wraps everything under `.receipt`, with attempts at
   `.receipt.attempts`, plan fields at `.receipt.plan`, and identity at
   `.receipt.receiptId`. The `--plan-only` payload (`:2310`) is a *different*
   shape — `{status, target, plan}` at the root. The plan uses one set of paths
   for both. **Not corrected.**

Also unaddressed: the comparison never asserts each attempt's `status`, which
`prd.md`'s AC7 wording requires, and never exercises the coordinator's exit-3
condition at `review.py:1889-1895` — the exact failure R3 exists to prevent.

### C-R3-3 — the shell runner has no missing-CLI contract, and its probe is broken

Step 7 says to add `run_codex_review` but does not specify its scoped command
construction or its behavior when the CLI is absent. The existing builtin
runners treat a missing executable as an overall failure —
`review-local.sh:535-538` (prism) and `:596-599` (gito) both call
`mark_overall_failure`. Mirroring that pattern while adding `codex` to the
default tool set would make the default set fail for every consumer without the
Codex CLI: precisely the regression R3 exists to prevent, reintroduced through
the shell instead of the Python.

Identified direction, not applied: the shell already has a per-tool
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_<TOOL>_MODE` with an `is_disabled` check
(`:530-533`). Codex should default to an optional mode so a missing CLI warns
and returns **without** `mark_overall_failure`.

Separately, the AC8 probe is invalid as written:

```bash
... review-local.sh codex 2>&1 | tee "$stub/log"; echo "exit=$?"
```

`$?` after a pipeline is `tee`'s status, not the script's. It must use
`${PIPESTATUS[0]}` or drop the pipe. As written the probe proves only that some
codex command ran, not that the runner succeeded.
