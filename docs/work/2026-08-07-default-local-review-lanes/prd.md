---
title: Default to local subscription review lanes before remote paid review
status: planning
created: 2026-08-07
---
# Default to local subscription review lanes before remote paid review

> **Correction (2026-08-10, from `07-24-remove-retired-review-surfaces`).**
> AC8 below invokes `templates/scripts/...review-local.sh`, which pack 0.65.0
> deleted along with the `sd-review-local` surface. Restate that criterion
> against the surviving local-review stage
> (`templates/scripts/sd-ai-command-pack-review-local.py`) and the `sd-review`
> coordinator before this task starts. The criterion's intent — a stub `codex`
> on `PATH` is invoked rather than reported as unconfigured — still holds.


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
  and `tests/test_review_controller.py` are included. (The former
  `test_review_local.py` was deleted with the `sd-review-local` surface by
  `07-24-remove-retired-review-surfaces`.)
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
| C-17 | 3 | `ensembleProviders` absent-key default breaks custom configs | Fixed — post-round, see below |
| C-18 | 3 | AC7 `jq` paths read the root; the receipt is nested under `.receipt` | Fixed — post-round, see below |
| C-19 | 3 | Shell runner has no missing-CLI contract; AC8 probe reads `tee`'s status | Fixed — post-round, see below |

## Round-3 concerns, resolved after the round budget

The project adversarial-review contract permits at most two remediation rounds
(three automatic rounds total). Round 3's Codex lane produced C-17, C-18 and
C-19 with no remaining budget to remediate them, so they were carried as open
blocking concerns and this plan was withheld from implementation approval.

They have since been applied on explicit instruction, outside the automatic
round sequence. Each was verified against this checkout; none was speculative.
This section records what changed, because the fixes are the least obvious part
of the plan and the reasoning does not survive as a diff.

### C-17 — the `ensembleProviders` absent-key default

Two rules in the round-2 remediation contradicted each other: an absent
`policy.ensembleProviders` normalized to the literal `["codex", "gito", "prism"]`,
while members had to be ids the consumer actually configured (mirroring
`requiredProviders`, `review-local.py:519-525`). Provider ids come only from the
consumer's own list (`:502-505`), so a repository defining just `prism` and
`gito` — the fixture shape at `tests/test_review_stage.py:66-109` — would get
`codex` injected, fail the unknown-id check, and hard-error on every run. That
contradicted this design's own compatibility claim.

**Applied:** the default is now *derived*, not literal — the builtin ensemble
order intersected with the ids actually defined
(`[i for i in ENSEMBLE_DEFAULT_ORDER if i in identifiers]`). The shipped default
config yields all three; a legacy `prism`+`gito` config yields `["gito","prism"]`,
identical to today; an argv-only config yields `[]`, also identical to today.
Explicit members stay strictly validated. `design.md` carries the truth table;
`implement.md` Step 6 carries the regression test.

### C-18 — the AC7 comparison read fields that do not exist

The `jq` expressions read `providers`, `policyId` and the digests from the JSON
root. No plan field lives at the root: `_report` (`:2173-2185`) nests an executed
run under `.receipt`, and `--plan-only` (`:2310-2317`) emits a *different* shape with
`plan` at the root and no attempts or outcome at all. One set of paths was used
for both, and `jq -r` on a missing path prints `null` — so two wrong paths
compare equal and the assertion passes while verifying nothing.

**Applied:** `implement.md` Step 8 now carries a shape table and separate
normalizers for the two payloads, plus a non-null guard so a wrong path fails
loudly instead of passing silently. The missing per-attempt `status` assertion
was added, Step 0 now captures per-scope plan baselines *and* an executed
baseline (`--plan-only` cannot show attempt status), and AC7 gained a
coordinator-level assertion against `review.py:1889-1895` — the exit-3 path R3
exists to prevent, which a stage-only diff cannot reach.

### C-19 — the shell runner's missing-CLI contract

Step 7 said to add `run_codex_review` without specifying its behavior when the
CLI is absent. Both existing builtin runners treat a missing executable as an
overall failure (`review-local.sh:535-538` [absent: surface deleted by 07-24-remove-retired-review-surfaces] prism, `:596-599` gito). Copying that
shape while adding `codex` to the default tool set would fail the default run on
every machine without the Codex CLI — the same regression as C-2, reintroduced
through the shell instead of the Python.

**Applied:** an `optional` mode tier is introduced — it does not exist today,
since `is_disabled` matches only `0|false|FALSE|no|NO|skip|none` and `optional`
currently falls through to required-like handling. It is added as a sibling
predicate, not an extension of `is_disabled`, because `optional` means "run if
present" rather than "do not run". Codex defaults to `optional`; prism and gito
keep `required` unchanged. Scope handling follows `run_gito_review`.

The AC8 probe was also invalid: `... | tee "$stub/log"; echo "exit=$?"` reports
`tee`'s status, not the script's, so it passed regardless of the outcome. It now
redirects instead of piping, and AC8 gained both halves of the mode contract —
absent binary must exit 0 by default, and must exit non-zero under
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_CODEX_MODE=required`. The first alone would
pass against a lane that was never wired up.

## Absorbed: 08-08-codex-lane-consent-gate (2026-08-08 consolidation)

That task established consent-not-capability gating for the two shipped Codex
lanes (planning adversarial review at
`.claude/sd-ai-command-pack/planning-adversarial-review.md:41-44`; local
review at line 166 of the since-deleted `sd-review-local` skill, removed by
`07-24-remove-retired-review-surfaces`). Both then
launch on a successful capability probe alone — "can this run?" answering
"should this run?" — sending planning artifacts or diffs to a third party
because a CLI happens to be installed. This task, which owns the local-review
provider surface, inherits the full acceptance set; the consent decision
shape (per-lane records under `SD_AI_COMMAND_PACK_STATE_HOME`, fail-closed
reads) comes from 08-07-plugin-review-provider-lanes requirements 15-22.

Carried acceptance criteria (both the planning-review and local-review lanes):

- With `codex` installed, compatible, and no consent recorded: neither lane
  launches a `codex` process, and both report a skip naming absent consent
  rather than absent capability.
- With `codex` installed, compatible, and consent recorded: both lanes behave
  exactly as today.
- With `codex` absent and consent recorded: both lanes report the
  not-installed skip, unchanged.
- A planning run that skips Codex for lack of consent still performs the host
  adversarial review and still refuses to proceed past an unresolved blocking
  concern.
- No skipped lane — for any of the three reasons — is reported or summarized
  as Codex approval.
- Consent recorded on one machine does not appear in any tracked file and does
  not reach another consumer through fleet propagation.
- Consent for one lane does not enable the other; no single record enables
  both.
- A consent record that is missing, unparseable, wrong-schema, unreadable, or
  not a regular file yields *no consent* and a successful run — never an error,
  never an optimistic grant.
- Whether consent is machine-wide or per repository is stated in design.md
  with a rationale, and the implemented behaviour matches.
- Source and `templates/` copies identical after the change; surface-generation
  and review tests pass against the new gate.
