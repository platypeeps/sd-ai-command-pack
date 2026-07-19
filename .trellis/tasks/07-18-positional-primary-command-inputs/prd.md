# Add Positional Primary Inputs To SD Commands

## Goal

Let users supply the obvious primary subject as bare command text for five SD
commands while preserving explicit, fail-closed syntax for lifecycle, safety,
scope, budget, and output controls.

## Background

Several SD commands already use ergonomic positional or natural-language
inputs: `sd-help` accepts goals and command names, `sd-review-local` accepts
tool names, `sd-status` accepts `fleet`, and `sd-fix-ci` accepts `main`. Other
commands still require a key for a single obvious subject, creating avoidable
invocation friction.

This task applies one consistent rule: bare text names the primary object being
acted on; explicit options control how the command behaves. It must not turn
misspellings into broader or more destructive defaults.

## Requirements

### Shared Parsing Contract

- Preserve every existing explicit argument form. Positional input is an
  additive shorthand, not a replacement.
- Parse recognized flags and key/value arguments before considering positional
  fallback.
- Treat option-shaped unknown input as an error. Never reinterpret a misspelled
  option as a positional subject.
- Reject a positional subject combined with the explicit argument for the same
  subject. Do not guess which value wins.
- Validate positional values with the same rules as their explicit equivalent
  before any side effect.
- Commands that can mutate repositories or GitHub state must print a concise
  normalized interpretation before mutation.
- Do not make lifecycle, mutation, safety, depth, retry, timeout, merge,
  dry-run, or output-format controls positional.
- Update thin platform adapters only when needed to preserve the raw invocation
  text. The canonical skill remains the behavioral source of truth.

### `sd-retro`

- Treat all bare non-option text as one topic phrase.
- `sd-retro deployment timeout` is equivalent to
  `sd-retro topic="deployment timeout"`.
- Do not split the phrase into multiple topics.
- Reject bare topic text combined with `topic=`.

### `sd-test-gaps`

- Treat one bare path expression as the target file.
- `sd-test-gaps scripts/example.py` is equivalent to
  `sd-test-gaps file=scripts/example.py`.
- Preserve quoted paths containing spaces as one path.
- Validate that the path occurs in the coverage report exactly as `file=` does.
- Keep `max-gaps=` explicit. Preserve the existing documented interaction when
  `file=` or its positional equivalent is combined with `max-gaps=`.

### `sd-fleet-refresh`

- Treat bare fleet consumer names as the consumer filter.
- `sd-fleet-refresh loadsmith rwbp-website` is equivalent to
  `sd-fleet-refresh consumer=loadsmith,rwbp-website`.
- Accept whitespace- or comma-separated bare consumer names while preserving
  user order and de-duplicating exact repeats.
- Recognize `dry-run` and `no-merge` as flags before positional parsing.
- Validate every name against the fleet manifest before mutation. An unknown
  positional consumer must stop; it must never fall back to refreshing the
  entire fleet.
- Reject bare consumers combined with `consumer=`.

### `sd-audit-repo`

- Treat bare exact charter names as the dimensions filter.
- `sd-audit-repo security testing` is equivalent to
  `sd-audit-repo dimensions=security,testing`.
- Accept whitespace- or comma-separated names, preserve order, and de-duplicate
  exact repeats.
- Validate against the current charter roster before reviewer dispatch.
- Keep `depth=` explicit. Continue recognizing `follow-up` as its existing bare
  mode flag and reject it when combined with dimension selection if the modes
  are not semantically compatible.
- Unknown bare charter names must stop; they must never trigger a full audit.

### `sd-status`

- Keep the reserved positional keyword `fleet` unchanged.
- Treat any other single positional value as a repository path.
- `sd-status /path/to/repo` is equivalent to
  `sd-status --repo /path/to/repo`.
- Preserve quoted paths containing spaces and normalize them through the same
  path validation as `--repo`.
- Reject a positional path combined with `--repo`, more than one path, or a
  path combined with `fleet`.
- Preserve `--fleet-manifest`, `--json`, and `--no-network` as explicit flags.

## Constraints

- `templates/**` remains the source of truth for shipped skills, scripts, and
  documentation; installed mirrors must remain synchronized.
- Do not broaden any mutating command after a positional parse failure.
- Do not introduce a new runtime dependency.
- Do not change unrelated command semantics or convert safety controls into
  positional shortcuts.

## Implementation Ordering

Land this task before `07-18-autonomous-work-loop-orchestration`. This task
establishes the shared positional-primary-subject convention that the later
`sd-work-backlog`/`sd-work-designs` bare-focus syntax should follow. Keep the
deliverables in separate PRs; after this task merges, the autonomous-loop task
must re-read the resulting adapter guidance and help surfaces before editing
them.

## Acceptance Criteria

- [ ] `sd-retro deployment timeout` produces the same normalized topic as the
      explicit `topic=` form.
- [ ] `sd-test-gaps scripts/example.py` selects exactly that covered file and
      invalid paths fail as they do with `file=`.
- [ ] `sd-fleet-refresh loadsmith rwbp-website` selects only those validated
      consumers, and an unknown bare consumer fails before mutation.
- [ ] `sd-audit-repo security testing` selects exactly those known charters,
      and an unknown name fails before reviewer dispatch.
- [ ] `sd-status /path/to/repo` reports that checkout while existing `fleet`
      behavior remains unchanged.
- [ ] Every command rejects mixed positional/explicit primary subjects and
      option-shaped typos.
- [ ] Existing explicit forms and no-argument defaults remain unchanged.
- [ ] Mutating commands report their normalized target and controls before
      acting.
- [ ] Help/catalog examples explain positional and explicit forms consistently.
- [ ] Focused command-contract, status parser, generated parity, installer,
      documentation, and canonical repository checks pass.
- [ ] Shipped payload changes receive the required version and changelog update.
