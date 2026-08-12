# Shipped provider-config fixes never reach fleet consumers

## Goal

Give the two `if-not-exists` provider configs a way to receive a shipped
correction, so a fix to a broken default reaches consumers that never edited it,
without overwriting a consumer that deliberately customized theirs.

## Problem

`manifest.json` installs 724 files. Exactly two carry
`"install": "if-not-exists"`:

- `.gito/config.toml`
- `.prism/rules.json`

For those two, `install.py TARGET --force` reports `preserved` and writes
nothing. The policy exists so a consumer's local provider tuning survives a pack
refresh, which is right. Its cost only appears when the shipped default is
itself wrong: the correction has no delivery path at all.

### The live instance

Release 0.64.21 narrowed `templates/.gito/config.toml`, replacing a blanket
`".trellis/**"` exclusion with five narrower entries — the copied-tooling
boundary the review preflight's `isTrellisCopiedPath` recognizes
(`.template-hashes.json`, `.version`, `scripts/**`, `agents/**`) plus
`tasks/archive/**`, and deliberately *not* `workspace/**`. The blanket entry excluded the authored
delivery documents the repository owns, so a diff confined to task or spec
Markdown reached the provider empty; the provider exited 0 with no structured
report, `sd-review` recorded that as a provider failure, and — because an absent
optional router requires a *clean* local receipt — the review stage could not
complete by any combination of `local=` and `remote=` controls. That failure
mode is filed separately as
`.trellis/tasks/08-06-local-provider-empty-scope`.

The narrowing landed in this repository only. Re-measured 2026-08-11 against
the fleet registry (`docs/fleet/consumers.json`, schema 5) by hashing each
consumer's config and comparing it to every blob the template has ever had in
this repository's history:

| Consumer | `".trellis/**"` entries | `.gito/config.toml` |
|---|---|---|
| `rwbp-coordinator` | 1 | older shipped default |
| `loadsmith` | 1 | older shipped default |
| `hoa-manager` | 1 | older shipped default |
| `rwbp-website` | 1 | older shipped default |
| `mezmo_benchmark` | 1 | older shipped default |
| `se-ai-command-pack` | 1 | older shipped default |
| `sd-github-review` | 1 | older shipped default |
| `anomaly-metric-creator` | 1 | older shipped default |

**All eight** registered consumers still carry the configuration that produces
the dead end, and every one of them holds the *same* older shipped blob —
none is customized. Every one will hit the dead end on the next task-only or
spec-only diff, and `install.py --force` will not fix any of them.

The 2026-08-06 version of this table listed seven repositories including
`people-profiles`, which the registry does not contain, and omitted
`rwbp-coordinator`, `rwbp-website`, and `mezmo_benchmark`, which it does. The
registry is the authority; the earlier table was a hand-taken snapshot.

### What makes this tractable, and where it does not hold

For `.gito/config.toml` the policy is currently protecting nothing: 8 of 8
consumers hold an unmodified shipped default, so the policy blocks a fix every
consumer needs and preserves no local decision at all.

For `.prism/rules.json` the opposite is true, measured the same way:

| State | Consumers |
|---|---|
| current template | `sd-github-review` |
| older shipped default | `loadsmith` |
| matches no shipped blob | the other six |

Those six are genuinely customized — `rwbp-coordinator`, for one, carries its
own `required` rule set and its own focus ordering, not a stale copy of ours.
R2 is therefore not a hypothetical safeguard for a future customizer: it is
protecting six real files today, and a mechanism that overwrites them is a
regression the moment it ships.

The two files together are the whole argument for the design: on the day this
lands it should refresh 8 `.gito` configs and exactly 1 `.prism` config, and
leave 6 `.prism` configs untouched and reported.

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
- The eight registered consumers are real working repositories. Whatever
  lands must be safe to run against all of them unattended.

## Open questions

All five are resolved in `design.md`, in order: D1, D2 + D3, D4, D5, D8.

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

- [ ] A consumer checkout whose `.gito/config.toml` is byte-identical to an
      earlier shipped template — specifically the blob all eight consumers hold
      today — receives the current template through the chosen mechanism,
      verified by `diff` against `templates/.gito/config.toml`.
- [ ] A consumer checkout whose `.gito/config.toml` has one added exclusion line
      is left byte-unchanged by the same run.
- [ ] That preserved-but-outdated consumer appears in the run's report naming
      the config and that it is behind.
- [ ] The same three cases pass for `.prism/rules.json`.
- [ ] The mechanism and its detector are shipped and validated against
      throwaway checkouts, not against the fleet. Converting the eight real
      consumers is **out of scope for this task**: it mutates repositories
      outside this one, which needs explicit per-cohort user authorization the
      autonomous work loop does not hold. It is filed as a follow-up whose
      acceptance criterion is the zero count of `".trellis/**"` across the
      eight consumer configs. Landing the detector first is also the safer order —
      the conversion then runs against measured state rather than the
      2026-08-06 table above. See `design.md` D7.
- [ ] A consumer left on the old config is visible in `sd-status fleet` or the
      install audit before the change lands, so the gap is detectable and not
      only fixable.

## Notes

- The payload was 776 files when this PRD was written on 2026-08-06 and is 724
  at 2026-08-11; the thin surface partition removed the difference. The
  `if-not-exists` population is still exactly the same two files, so the
  problem is unchanged — only the denominator moved.
- Source: audit on 2026-08-06 after shipping 0.64.21. The narrowing itself was
  driven by PR #339, where the review stage dead-ended on an all-excluded diff.
- The byte-identical finding was measured, not assumed. The 2026-08-06 pass
  diffed each consumer config against `templates/.gito/config.toml` at 0.64.20;
  the 2026-08-11 pass hashed every consumer config against every blob in each
  template's git history, which is what surfaced the six customized
  `.prism/rules.json` files the first pass did not look for.
- Complex enough to need `design.md` and `implement.md` before `task.py start`:
  R1 and R2 are in direct tension, and the open question about where prior
  template digests come from is a real architectural choice with a release-time
  cost.
