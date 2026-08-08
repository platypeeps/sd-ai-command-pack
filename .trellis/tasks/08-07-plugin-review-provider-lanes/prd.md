# Add gemini and kimi as parallel local review providers when installed as plugins

## Goal

Let the local review stage run `gemini` and `kimi` alongside `codex`, in the
parallel pool it already has, whenever those tools are installed as plugins —
and behave exactly as it does today on a machine where they are not.

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
   selection policy.
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
14. The receipt distinguishes *ran*, *skipped because not installed*, and
    *failed*. A review that skipped two of four reviewers must never read as
    equivalent to one that ran all four.

## Acceptance criteria

- With neither plugin installed: selected providers, aggregate outcome, exit
  code, and receipt provider list are byte-identical to the pre-change
  behaviour, verified by comparing receipts across the change on the same
  repository and head.
- With both plugins installed: both appear in the selection, run concurrently
  with the others, and contribute findings tagged with their own provider id.
- With exactly one installed: that one runs, the other is absent from the
  selection, and no `unavailable` outcome is produced for it.
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
  ran / skipped-not-installed / failed applied.

## Open decisions

**Enabled by default, or opt-in.** Defaulting to enabled maximises review
coverage for anyone who already has the plugins, and costs nothing for anyone
who does not, given requirement 7. Defaulting to opt-in is more conservative
about sending repository content to a third party without an explicit choice.
Recommendation: **opt-in**, because requirement 13's disclosure obligation is
weaker than an actual decision, and a reviewer that silently starts sending
code off-machine because a plugin was installed for unrelated reasons is a
surprise worth avoiding.

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
  ensemble, all owned by `08-07-default-local-review-lanes`.
- The remote review lane, its router, and its dispatch idempotency.
- The local finding rebuttal channel, already shipped.
- Installing, updating, or managing plugins. This task detects; it never
  installs.
- Adding further reviewers beyond these two. The mechanism should not foreclose
  them, but each additional provider is its own decision about data egress.
- Fleet propagation of the resulting provider configuration, owned by
  `08-06-fleet-provider-config-propagation`.
