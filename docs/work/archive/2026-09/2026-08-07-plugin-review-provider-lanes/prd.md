---
title: "PARKED: Add gemini and kimi as opt-in parallel local review providers when installed as plugins"
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-07
---
# PARKED: Add gemini and kimi as opt-in parallel local review providers when installed as plugins

## Goal

Let the local review stage run `gemini` and `kimi` alongside `codex`, in the
parallel pool it already has, when those tools are installed as plugins **and
the operator has opted in** — and behave exactly as it does today on a machine
where either condition is unmet.

Installation is a capability signal, not consent. These reviewers send
repository content to a third party, and a plugin installed for unrelated
reasons must never be read as permission to do that. Opt-in is a requirement of
this task, not a deployment preference; see **Opt-in** below.

## Dependency

This builds on `08-07-default-local-review-lanes`, which makes `codex` a
configured provider and replaces the hardcoded `{"prism", "gito"}` substantive
-risk ensemble with a bounded configuration-derived set. That task must land
first: without it there is no free-provider precedent, no configuration-derived
ensemble to extend, and no eligibility gate to reuse. This task adds two more
providers to a mechanism that task establishes; it does not re-litigate the
mechanism.

## What already exists

Three things this task does **not** need to build:

1. **Parallel execution.** Selected providers already run concurrently —
   `scripts/sd-ai-command-pack-review-local.py:2080` submits each selected
   provider to a `ThreadPoolExecutor` sized to the selection. "Parallel" is the
   current behaviour, not a new capability. Adding providers adds lanes.
2. **A provider schema.** `.sd-ai-command-pack/review.json` carries
   `schemaVersion`, `providers`, `policy`, and `remoteIntegration`. Each
   provider declares `id`, `adapter`, `version`, `argv`, `scopes`,
   `dataHandling`, `costTier`, `qualityTier`, `timeoutSeconds`, `enabled`, and
   `outcomeByExitCode`. `MAX_PROVIDERS` is 16, so two more fit.
3. **Argv safety.** The parser rejects shell command strings, inline code
   strings, and NUL bytes, and requires an `argv` adapter to supply `argv`.
   These providers inherit that; no new invocation path is introduced.

## What does not exist

**The pack has no plugin awareness at all.** A search across `scripts/` for
plugin handling returns one unrelated path-matching entry
(`.opencode/plugins/` in the preflight). There is no Claude Code plugin
discovery, no plugin manifest reader, and no notion of a tool being present
*because a plugin installed it*.

Nor do these two tools exist as reviewers today:

- `gemini` exists only as a **platform adapter surface**. The tracked
  directories are `.gemini/agents/`, `.gemini/commands/sd/`,
  `.gemini/commands/trellis/`, and `.gemini/hooks/` — places the pack
  *installs command files into*. That is the opposite direction from a review
  provider and must not be confused with one. There is no `.gemini/skills/`
  directory in this repository, despite `sd-ai-command-pack-pr-body-scope.py`
  listing such a pattern; that entry is a scope glob, not evidence of an
  existing path.
- `kimi` has no tool surface, no provider definition, and no executable
  integration. It appears exactly once in the repository, in
  `07-25-add-multi-reviewer-learning-and-effectiveness-analysis/prd.md:27`, and
  that mention is a constraint rather than an integration — see Related work.

So the work is: two provider definitions, plus the detection mechanism that
decides whether each one is present, plus the gating that makes absence a
non-event.

## Related work

`07-25-add-multi-reviewer-learning-and-effectiveness-analysis` (parked) already
sets a design constraint that governs this task:

```text
- Support variable-length cheap/deep reviewer sets generically without
  hard-coding Copilot, Kimi, Qwen, providers, models, or exactly two reviewers.
```

This task names `gemini` and `kimi` as **configuration entries**, which is what
the provider schema is for. It must not name them in the *mechanism*: detection
enumerates the plugin surface rather than matching known names (requirement 2),
and selection treats them as ordinary providers rather than special cases
(requirement 5). Read together, the two tasks agree — the reviewer set stays
variable-length and generic, and these two are simply members of it.

## The failure this must not cause

`08-07-default-local-review-lanes` documents the hazard precisely, and it
applies with more force here because this task adds *two* optional providers
rather than one.

`unavailable` is both a terminal failure and a declared opt-out outcome
(`review-local.py:62-68`). A provider that is selected and then cannot run
returns `unavailable`; `unavailable` dominates the aggregate; and the
coordinator turns that into exit 3 with `status="failed"`. The user-visible
result is that "review ran on prism and gito" becomes "review failed" —
strictly worse than not adding the provider.

The rule that follows: **a tool that is not installed must be excluded from
selection before dispatch, never dispatched and then reported unavailable.**
This is an eligibility question, not a fallback question.

## Requirements

### Detection

1. A provider backed by a plugin is eligible only when that plugin is
   installed. Installation is determined by inspecting the platform's actual
   plugin surface at run time, not by assuming a path, shelling out to the
   tool, or trusting a configuration flag alone.
2. Detection is enumerated from the environment rather than matched against a
   hardcoded list of plugin names, so a rename or relocation upstream surfaces
   as "not installed" rather than as a wrong positive.
3. Detection failure — unreadable directory, malformed manifest, unsupported
   platform — resolves to **not installed**. It is never an error that fails
   the review, and never an optimistic assumption that the tool is present.
4. Detection is bounded and side-effect free: no network, no plugin
   installation, no writes, and a cost that does not scale with repository
   size.

### Selection

5. `gemini` and `kimi` are ordinary entries in the configuration-derived
   provider set, subject to the same `scopes`, `costTier`, `qualityTier`, and
   `enabled` rules as every other provider. They are not a special case in the
   selection policy — including for opt-in, which is a general provider
   property rather than a rule about these two names.
6. An undetected provider is filtered out during eligibility, before any
   dispatch, and never contributes an `unavailable` outcome to the aggregate.
7. With neither plugin installed, the selected set, the aggregate outcome, the
   exit code, and the receipt's provider list are identical to the behaviour
   before this change. This is the single most important property of the task.
8. Adding these providers must not starve the metered ones. Whatever
   cost-ordered selection `08-07-default-local-review-lanes` establishes, the
   substantive-risk ensemble must not silently become "the free ones only"
   because two more free providers appeared.
9. The bound stays enforced: the combined configured set respects
   `MAX_PROVIDERS`, and exceeding it is a configuration error with a clear
   message, not a silent truncation.

### Execution and results

10. These providers run in the existing parallel pool with no new concurrency
    machinery, and each carries its own `timeoutSeconds` — a slow optional
    reviewer must not extend the wall-clock of the required ones beyond its own
    timeout.
11. Findings from three or more reviewers are deduplicated before disposition.
    Overlapping reviewers produce near-identical findings on the same lines,
    and the existing instruction to deduplicate provider findings becomes load
    bearing rather than advisory at this count.
12. Provider identity is preserved on every finding. A finding's origin is
    evidence for adjudication; merging findings must not erase which reviewer
    raised it.

### Disclosure

13. `dataHandling` is set truthfully for each provider, and the receipt makes
    it visible which providers received repository content. Running these
    reviewers sends code to third-party services; that is an operator decision
    and must be legible in the record rather than implied by a provider name.
14. The receipt distinguishes *ran*, *skipped because not installed*, *skipped
    because no opt-in was recorded*, and *failed*. A review that skipped two of
    four reviewers must never read as equivalent to one that ran all four, and
    "the tool is absent" must never be recorded for a tool that is present and
    merely unconsented — those are different facts that call for different
    actions from whoever reads the receipt.

### Opt-in

The existing configuration already carries most of what opt-in needs, and one
verified detail is the reason it is not simply "ship them `enabled: false`".

Eligibility filters on `enabled` **first**
(`sd-ai-command-pack-review-local.py:1211-1216`), and every later selection
branch reads from that filtered set. So `enabled: false` does not mean "off by
default" — it means *unreachable*:

```text
elif local != "auto":
    if local not in by_id:
        raise ReviewInputError(
            f"requested local provider is unavailable or ineligible: {local}"
        )
```

An operator who wanted one run with `gemini` would get an invocation error, not
a review. `enabled` conflates permission with default selection, and opt-in
needs those separated.

15. A provider carries a **default-selection** property distinct from `enabled`.
    `enabled` stays the permission gate — a disabled provider cannot run by any
    route. The new property decides whether an enabled provider participates in
    automatic selection. An opt-in provider is enabled, eligible, addressable by
    name, and simply not chosen on its own.
16. `local=auto` never selects an opt-in provider. `local=all` means all
    *default* providers, not every eligible one: `all` silently expanding to
    include third-party egress is precisely the surprise this requirement
    exists to prevent. Selecting opt-in providers requires naming them, or a
    distinct explicit token — never a token whose plain meaning is "the usual
    set". Every provider that exists today is default-selection, so `all` is
    observably unchanged for every configuration that predates this task.
17. `policy.allowedDataHandling` stays what it is: an **organizational
    prohibition**, not the consent mechanism, and its defaults do not change.
    Both currently permit all three classes — the shipped
    `.sd-ai-command-pack/review.json` lists `["local", "private-network",
    "public-network"]`, and the in-code fallback is `list(DATA_CLASSES)`
    (`sd-ai-command-pack-review-local.py:278`, `DATA_CLASSES` at `:53`).

    Tightening those defaults was considered and rejected as self-defeating: an
    un-widenable ceiling that denies `public-network` by default makes
    requirement 18's per-machine overlay impossible to use, because the only way
    to opt in would be editing the tracked, fleet-propagated file that
    requirement 18 exists to avoid editing. A ceiling and a default-off switch
    cannot be the same field. So consent lives in requirements 15-16 and 18-19,
    and this field remains what an organization sets when it wants a class
    forbidden outright — a decision no lower layer may override, including
    `local=<id>`.
18. A per-machine overlay lives outside the repository, under the pack's
    existing user state root — `SD_AI_COMMAND_PACK_STATE_HOME`
    (`sd_ai_command_pack_lib.py:116`) resolved through `resolve_state_root`,
    whose documented ladder is explicit argument, that variable,
    `XDG_STATE_HOME`, the Windows local-app-data location, then the home
    fallback (`:248`). Plugin installs are per-person and per-machine while
    `.sd-ai-command-pack/review.json` is tracked and fleet-propagated, so a
    repository-file-only opt-in either cannot express an individual choice or
    propagates one person's consent to every consumer. The overlay chooses among
    providers the repository already permits; it never widens
    `allowedDataHandling`.
19. Layer roles are distinct, and only the first is a ceiling.
    `policy.allowedDataHandling` **forbids**; the provider's default-selection
    property, the user overlay, and a `local=<id>` argument each **select**
    within what is not forbidden. Selecting something permitted but not
    default-selected is an act of consent, not a widening — the overlay and
    `local=<id>` are exactly that, and either alone is sufficient consent for
    its scope. Absent configuration at every layer resolves to **not
    selected**, never to selected.
20. When a provider is installed, permitted, and not selected, the report says
    so in one line with the exact command that would enable it. Opt-in that
    nobody can discover is indistinguishable from an unimplemented feature. This
    is advisory output only: never a prompt, never a blocker, and never a
    reason to run the provider.
21. `policy.requiredProviders` cannot force an opt-in provider. This is the
    hole that would otherwise make every requirement above decorative:

    ```text
    selected.extend(by_id[item] for item in required if item not in selected_ids)
    ```

    That line (`sd-ai-command-pack-review-local.py:1276`) runs *after* every
    selection branch, including `explicit-provider`, so a `requiredProviders`
    entry overrides whatever selection decided. An opt-in provider named there
    would run on every review, and `review.json` is a tracked, fleet-propagated
    file — so one repository's entry becomes every consumer's. Naming an
    opt-in provider in `requiredProviders` must be rejected during
    configuration validation, not resolved at selection time: a config-parse
    error names the contradiction, while a silent subordination leaves an
    operator believing a reviewer is required when it is not running.
22. The user overlay is untrusted input and is parsed with the rigour
    `review.json` already gets — bounded size, no shell command strings, no
    inline code strings, no NUL bytes. It is a new file-shaped input read from
    a location outside the repository, which is the least reviewed place in the
    system. A malformed overlay takes the existing `ReviewInputError` path and
    nothing softer: `status="invalid"`, exit 2, no provider dispatched
    (`sd-ai-command-pack-review-local.py:2341`). It must not degrade to a
    review that silently proceeds with defaults, and equally must not degrade
    to one that silently drops a valid opt-in. An **absent** overlay is not an
    error — it is the ordinary no-opt-in state and resolves per requirement 19.

## Codex, and the two surfaces this rule reaches

"Review by codex" names two different things, and only one of them is a
provider:

1. **The planned `codex` local review provider**, owned by
   `08-07-default-local-review-lanes`. Requirements 15-22 are properties of the
   provider mechanism rather than of these two provider names, so they reach
   `codex` the moment that task defines it.

   **That dependency, as written, contradicts opt-in, and this conflict must be
   resolved before either task is implemented.** Its R1 adds `codex` with
   `costTier: "none"` "so it is selected ahead of `prism` and `gito` on every
   cost-ordered selection path", and its AC5/AC6 require that a stub `codex` on
   `PATH` *executes* — presence as the sole condition, which is the exact
   pattern requirement 15 breaks. Both PRDs cannot pass as written.

   Neither task currently owns the fix: that one authors the entry without
   knowing about opt-in, and this one declares the entry out of scope. The
   resolution belongs to `08-07-default-local-review-lanes` because it owns the
   provider entry, its cost tier, and those acceptance criteria — this task
   supplies the rule, that task applies it to `codex`. Implementing this task
   against an unamended dependency would ship a mechanism that `codex` bypasses
   on the first run.
2. **The Codex lanes that already ship and already run.** Both gate on
   capability alone. Neither gates on consent: a *compatible* installed CLI —
   one that clears the probes below — runs with no consent check anywhere in
   the path. That is the conflation requirement 15 exists to break. (Presence
   alone is not quite sufficient; both lanes also require their help or
   compatibility probe to succeed, and `sd-review-local` additionally requires
   a supported flag. A stricter capability gate is still not a consent gate.)
   - `.claude/sd-ai-command-pack/planning-adversarial-review.md:42` — "`command
     -v codex` and `codex exec --help`. When both succeed, launch one
     review-only `codex exec` command". `.claude/rules/` makes that contract
     mandatory whenever a run materially updates a planning artifact.
   - line 166 of the since-deleted `sd-review-local` skill (removed by
     `07-24-remove-retired-review-surfaces`) — the same shape with
     `codex review --help`, described there as checking "the host capability
     before launching paid review work". Capability is the only condition
     checked; there is no consent condition.

   Neither is a plan, and neither is confined to one file.
   `git grep -l "command -v codex" origin/main` returns 15 tracked paths: the
   two skills above, `.claude/skills/sd-review-local/SKILL.md` [absent: provider lane never built; path proposed, not present],
   the `.claude/commands/sd/review-local.md` [absent: provider lane never built; path proposed, not present] adapter, four
   `templates/` twin
   mirrors, `docs/SD_AI_COMMAND_PACK.md`, `.trellis/spec/frontend/adapter-
   guidelines.md`, `.github/scripts/generate-command-surfaces.py`, three test
   files, and one archived task's `design.md`. Whoever changes this gating
   changes a mirrored surface with generation and test gates behind it, which
   is the main argument for it being its own task.

Surface 2 is shipped behaviour spread across mirrored surfaces, not a
`review.json` entry, so its fix is a change to those contracts and needs its
own task rather than being smuggled into this one. The principle is identical
and should not be restated differently: **an external model reviewer runs
because the operator asked for it, never merely because it is installed.**

## Acceptance criteria

- With neither plugin installed: selected providers, aggregate outcome, exit
  code, and receipt provider list are identical to the pre-change behaviour,
  verified by comparing receipts across the change on the same repository and
  head. The comparison **excludes** `configurationDigest`, `policyDigest`, and
  `receiptId`. Adding provider definitions changes `_digest(config)`
  (`sd-ai-command-pack-review-local.py:2293`) and therefore all three by
  construction, so "byte-identical" over the whole receipt is unsatisfiable and
  would make this criterion untestable rather than strict. This matches the
  exclusion `08-07-default-local-review-lanes` already specifies for the same
  reason.
- With both plugins installed **and opted in**: both appear in the selection,
  run concurrently with the others, and contribute findings tagged with their
  own provider id.
- With both plugins installed and **no** opt-in recorded at any layer: neither
  appears in the selection under `local=auto` or `local=all`, and the run is
  otherwise identical to the neither-installed case above.
- With exactly one installed and opted in: that one runs, the other is absent
  from the selection, and no `unavailable` outcome is produced for it.
- Naming an installed, permitted, not-default provider with `local=<id>` runs
  exactly that provider — it does not raise `requested local provider is
  unavailable or ineligible`, which is what a plain `enabled: false` produces
  today.
- Removing the provider's declared data-handling class from
  `policy.allowedDataHandling` makes it unrunnable by every route, including an
  explicit `local=<id>` and any user-overlay opt-in.
- A user overlay cannot widen `policy.allowedDataHandling`; an overlay that
  tries is a configuration error naming the ceiling it violated.
- A pack update that adds a new third-party provider does not cause it to run
  on an operator who never opted in, with no action required from that
  operator.
- An installed, permitted, unselected provider produces exactly one advisory
  line naming the command that would enable it, and the review's outcome, exit
  code, and receipt are unaffected by whether that line was emitted.
- A configuration naming an opt-in provider in `policy.requiredProviders` fails
  validation with a message naming both the provider and the contradiction; it
  does not parse and then quietly run that provider.
- A malformed, oversized, or unreadable user overlay yields a configuration
  error and no opt-in — it never falls through to a review that runs opt-in
  providers, and never to one that silently drops a valid opt-in.
- `local=all` on a configuration containing only pre-existing providers selects
  exactly what it selected before this task.
- A plugin surface that is unreadable or malformed yields "not installed" and a
  successful review, not a failed one.
- A provider that is installed but exits nonzero maps through its own
  `outcomeByExitCode` exactly as any other provider does — this task does not
  make optional providers exempt from real failures.
- A configured set exceeding `MAX_PROVIDERS` fails validation with a message
  naming the limit.
- Two reviewers reporting the same defect on the same line produce one finding
  for disposition, with both provider ids retained.
- The receipt shows, for every configured plugin-backed provider, which of
  ran / skipped-not-installed / skipped-not-opted-in / failed applied. An
  installed, permitted, unconsented provider records the opt-in state, never
  the not-installed one.

## Open decisions

**Enabled by default, or opt-in — decided: opt-in.** Requirement 13's
disclosure obligation is weaker than an actual decision: recording in a receipt
that code was sent to a third party is not the same as having been asked. The
requirements above are now normative; see **Opt-in**.

A related question — whether a provider added later inherits an earlier
consent — is **not** left open, because leaving it open would reopen the
decision above. Consent is per provider. A new third-party provider arriving in
a pack update ships opt-in under requirement 15 and does not run, whatever the
operator previously permitted for a different provider in the same class.
`policy.allowedDataHandling` cannot carry that inheritance, because per
requirement 17 it is a prohibition rather than a grant.

**Whether "plugin-installed" is the right eligibility signal.** The request
scopes these to plugin installations specifically. A directly installed
`gemini` or `kimi` CLI on `PATH` is the same reviewer with the same output.
Recommendation: treat plugin installation as the *default* discovery mechanism
while keeping the provider definition itself ordinary, so an operator who
installs the CLI directly can still configure it by hand without a code change.

**Shared or separate provider definitions.** `gemini` and `kimi` may accept
sufficiently similar invocations to share one adapter shape parameterised by
executable. Recommendation: define them separately first and factor only if the
implementation shows the shapes are genuinely identical; a premature shared
adapter hides per-tool exit-code semantics, which `outcomeByExitCode` exists to
capture.

## Out of scope

- The `codex` provider itself, its cost tier, and the configuration-derived
  ensemble, all owned by `08-07-default-local-review-lanes` — including the
  amendment its R1 and AC5/AC6 need to stop contradicting opt-in. This task
  states the rule and flags the conflict; it does not edit that task's
  artifacts.
- Making the two shipped capability-gated Codex lanes opt-in. That is real
  behaviour across mirrored surfaces with generation and test gates, and it
  needs its own task.
- The remote review lane, its router, and its dispatch idempotency.
- The local finding rebuttal channel, already shipped.
- Installing, updating, or managing plugins. This task detects; it never
  installs.
- Adding further reviewers beyond these two. The mechanism should not foreclose
  them, but each additional provider is its own decision about data egress.
- Fleet propagation of the resulting provider configuration, owned by
  `08-06-fleet-provider-config-propagation`.
