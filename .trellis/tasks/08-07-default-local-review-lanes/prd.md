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
  present, so selection never picks it and behavior for consumers without the
  CLI is byte-identical to today.
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
- The shell entrypoint has per-tool dispatch and state, not a generic loop
  (`review-local.sh:702`, `:730`). An unrecognized tool token falls through to
  the unknown-tool branch and exits 2.
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
- [ ] AC7. With **no** `codex` on `PATH`, the stage behaves exactly as it does
  on `origin/main`: the metered providers run, the review does not fail, and
  `review.py` does not return exit 3. This must be demonstrated by running the
  same scenario against both revisions and comparing, not by asserting a
  hand-written expectation.
- [ ] AC8. `bash templates/scripts/...review-local.sh codex` actually dispatches
  Codex rather than hitting the unknown-tool branch, and
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS` unset selects the free lane.
- [ ] AC9. Every template surface describing Codex as an additive or peer
  *review* lane is corrected, and the two lanes are named distinctly. The
  surface set is enumerated with `grep -rln -i codex templates/`, then each hit
  classified as local-review lane, planning-adversarial-review lane, or an
  unrelated `.codex/` directory listing. Hits in
  `templates/docs/SD_AI_COMMAND_PACK.md` at the local-review sections (`:861`,
  `:1819`) are in scope; the planning-review mention (`:32`) is not.
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
