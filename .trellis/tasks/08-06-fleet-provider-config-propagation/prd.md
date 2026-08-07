# Shipped provider-config fixes never reach fleet consumers

## Goal

Give the two `if-not-exists` provider configs a way to receive a shipped
correction, so a fix to a broken default reaches consumers that never edited it,
without overwriting a consumer that deliberately customized theirs.

## Problem

`manifest.json` installs 776 files. Exactly two carry
`"install": "if-not-exists"`:

- `.gito/config.toml`
- `.prism/rules.json`

For those two, `install.py TARGET --force` reports `preserved` and writes
nothing. The policy exists so a consumer's local provider tuning survives a pack
refresh, which is right. Its cost only appears when the shipped default is
itself wrong: the correction has no delivery path at all.

### The live instance

Release 0.64.21 narrowed `templates/.gito/config.toml`, replacing a blanket
`".trellis/**"` exclusion with the six copied surfaces the review preflight's
`isTrellisCopiedPath` recognizes. The blanket entry excluded the authored
delivery documents the repository owns, so a diff confined to task or spec
Markdown reached the provider empty; the provider exited 0 with no structured
report, `sd-review` recorded that as a provider failure, and — because an absent
optional router requires a *clean* local receipt — the review stage could not
complete by any combination of `local=` and `remote=` controls. That failure
mode is filed separately as
`.trellis/tasks/08-06-local-provider-empty-scope`.

The narrowing landed in this repository only. Counting the blanket entry across
the fleet:

| Consumer | `".trellis/**"` entries |
|---|---|
| `anomaly-metric-creator` | 1 |
| `hoa-manager` | 1 |
| `loadsmith` | 1 |
| `people-profiles` | 1 |
| `sd-github-review` | 1 |
| `se-ai-command-pack` | 1 |
| `sd-ai-command-pack` | 0 |

Six of seven repositories still carry the configuration that produces the dead
end. Every one of them will hit it on the next task-only or spec-only diff, and
`install.py --force` will not fix any of them.

### What makes this tractable

All six consumer files are **byte-identical to the pre-0.64.21 shipped
template**, verified by `diff` against `templates/.gito/config.toml` at 0.64.20.
Not one has been customized. The policy is currently protecting nothing while
blocking a fix that every consumer needs.

That is evidence about today's fleet, not a permanent property — the design must
still be safe on the day someone does customize one.

## Requirements

### Functional

- R1: a consumer whose `if-not-exists` config is byte-identical to a shipped
  template — the current one or any earlier released one — must be able to
  receive the current template.
- R2: a consumer whose config differs from every shipped template must not be
  overwritten. Its content is a local decision and the installer has no basis to
  discard it.
- R3: R2's outcome must be reported, not silent. A consumer left behind on a
  known-broken default needs to show up in fleet status or the install audit
  with what it is missing, so a human can merge it by hand.
- R4: whatever mechanism lands must apply to `.prism/rules.json` on the same
  terms. The pair is the policy's whole population; a fix that special-cases
  `.gito/config.toml` leaves the same trap armed for the other.

### Non-functional

- N1: recognizing a prior shipped template must not require the consumer to have
  recorded anything at install time. Existing checkouts have no such record, and
  they are exactly the population that needs the fix.

## Constraints

- Do not change `if-not-exists` to `always`. That discards local customization
  outright and is the failure R2 exists to prevent.
- Do not weaken any deterministic check to make an out-of-date consumer pass.
  Falling behind on a config should be visible, not tolerated.
- The six consumers are real working repositories. Whatever lands must be safe
  to run against all of them unattended.

## Open questions (resolve in design)

- Where does the set of "previously shipped templates" come from — hashes
  recorded in `manifest.json`, a lookup over release tags, or a digest list
  generated at release time by `prepare-release.py`? N1 rules out anything
  requiring consumer-side state.
- Is the right shape an installer upgrade path, an `sd-fleet-refresh` action, or
  a report-only detector that leaves the edit to a human? R3 is satisfiable by
  the third alone, and R1 is not.
- Should a consumer that diverged only by *added* lines — the template's content
  intact plus local additions — be treated as customized (R2) or merged? A
  three-way merge is more useful and much more to get wrong.
- What is the correct behavior when a consumer matches an old template but the
  new template would remove a line the consumer's provider depends on? The
  0.64.21 change is additive-plus-one-removal, so this is not hypothetical.
- Does anything else in the pack depend on consumers carrying the blanket
  exclusion, such that narrowing it fleet-wide changes their review cost? The
  narrowing adds a real local-provider round on diffs that previously produced
  none.

## Acceptance Criteria

- [ ] A consumer checkout whose `.gito/config.toml` is byte-identical to the
      0.64.20 template receives the current template through the chosen
      mechanism, verified by `diff` against `templates/.gito/config.toml`.
- [ ] A consumer checkout whose `.gito/config.toml` has one added exclusion line
      is left byte-unchanged by the same run.
- [ ] That preserved-but-outdated consumer appears in the run's report naming
      the config and that it is behind.
- [ ] The same three cases pass for `.prism/rules.json`.
- [ ] All six fleet consumers listed above end with a narrowed `.trellis`
      exclusion, proven by a zero count of `".trellis/**"` across their configs.
- [ ] A consumer left on the old config is visible in `sd-status fleet` or the
      install audit before the change lands, so the gap is detectable and not
      only fixable.

## Notes

- Source: audit on 2026-08-06 after shipping 0.64.21. The narrowing itself was
  driven by PR #339, where the review stage dead-ended on an all-excluded diff.
- The byte-identical finding was measured, not assumed: each consumer config was
  diffed against `templates/.gito/config.toml` as of 0.64.20.
- Complex enough to need `design.md` and `implement.md` before `task.py start`:
  R1 and R2 are in direct tension, and the open question about where prior
  template digests come from is a real architectural choice with a release-time
  cost.
