---
title: Convert the eight fleet consumers off superseded provider configs
status: done
created: 2026-08-11
branch: chore/convert-fleet-provider-configs
---
# Convert the eight fleet consumers off superseded provider configs

## Problem

`08-06-fleet-provider-config-propagation` shipped the mechanism that can carry
a corrected `if-not-exists` default to a consumer, and the detector that says
who needs it. It deliberately converted nobody: mutating repositories outside
this one needs explicit per-cohort user authorization, which the autonomous
work loop does not hold.

Measured with `sd-status fleet --json --no-network` at pack version 0.71.0
(2026-08-12, read-only), across all eight registered consumers:

| target | current | superseded | locally owned |
|---|---|---|---|
| `.gito/config.toml` | 0 | 8 | 0 |
| `.prism/rules.json` | 1 (`sd-github-review`) | 1 (`loadsmith`) | 6 |

The eight superseded `.gito/config.toml` copies still carry the blanket
`".trellis/**"` exclusion that the narrowed template replaced. Until they are
converted, every one of them keeps excluding surfaces the pack now expects its
local review lane to see.

## Authorization, recorded 2026-08-12

The user was asked which cohort the autonomous run may convert and answered
**"Provider configs, all 8"**, naming this task. That authorization covers the
eight `.gito/config.toml` targets and nothing else; the thin-mode conversion
cohorts remain unauthorized, and `--thin` requires its own `--resweep-verdict`
so an ordinary forced install cannot reach them.

## Measured state, 2026-08-12 at pack 0.71.1

`sd-status fleet --json --no-network`, read-only, all eight consumers
`available`:

| target | current | superseded | locally owned |
|---|---|---|---|
| `.gito/config.toml` | 0 | 8 | 0 |
| `.prism/rules.json` | 1 (`sd-github-review`) | 1 (`loadsmith`) | 6 |

The 2026-08-12 measurement reproduces the 0.71.0 table above exactly.

### The mechanism carries more than the cohort

`install.py <consumer> --force --dry-run`, run against every consumer on the
same day, reports the provider-config conversion as one `refreshed` line — and
writes 55 to 83 other paths alongside it, because the fleet is installed at
0.64.3–0.64.33 and the install refreshes the whole payload to 0.71.1:

| consumer | installed | overwritten | would-retire | updated | created | refreshed | preserved |
|---|---|---|---|---|---|---|---|
| rwbp-coordinator | 0.64.4 | 77 | 13 | 3 | 2 | 1 | 1 |
| loadsmith | 0.64.27 | 68 | 13 | 3 | 2 | 2 | 0 |
| hoa-manager | 0.64.3 | 78 | 13 | 3 | 2 | 1 | 1 |
| rwbp-website | 0.64.3 | 78 | 13 | 3 | 2 | 1 | 1 |
| mezmo_benchmark | 0.64.3 | 78 | 13 | 3 | 2 | 1 | 2 |
| se-ai-command-pack | 0.64.33 | 50 | 13 | 3 | 2 | 1 | 1 |
| sd-github-review | 0.64.3 | 78 | 13 | 3 | 2 | 1 | 1 |
| anomaly-metric-creator | 0.64.3 | 78 | 13 | 4 | 2 | 1 | 2 |

`refreshed` is the superseded provider-config population and `preserved` the
locally owned one, exactly as the note below predicted. What the note did not
say is that the ordinary install is also a seven-minor-version pack upgrade per
consumer. Counting the report's own lines, a conversion writes 56 paths
(`se-ai-command-pack`) to 84 (`hoa-manager`, `rwbp-website`,
`mezmo_benchmark`, `sd-github-review`, `anomaly-metric-creator`) and retires 13
more, per consumer — not one file. That is a materially larger change than the
cohort name suggests, and the scope question this task must settle before it
mutates anything.

Three consumers are not ready for an unattended mutation either:
`loadsmith` and `anomaly-metric-creator` have dirty trees, and
`mezmo_benchmark` is on `cr/triage-grading-channel` with no upstream.

### Decisions, 2026-08-12

Both were put to the user with the measurement above in hand.

- **Delivery**: canary first. `sd-github-review` is converted alone — clean
  tree, synchronized with its default branch, and the one consumer whose
  `.prism/rules.json` the detector already calls `current`, so its PR isolates
  the `.gito/config.toml` change from any local-provider noise. Its pull request
  is reviewed before the remaining seven are touched. The prescribed mechanism
  is unchanged; only the order is.
- **The three not-ready consumers**: stash, convert, restore. The user was told
  plainly that this touches uncommitted work in repositories this run does not
  own, and chose it over skipping them. Each stash is created with a named
  message, its ref recorded in this task before the conversion, and restored
  immediately after; a restore that conflicts stops that consumer and is
  reported rather than resolved.

### Canary result, 2026-08-12

`sd-github-review`, converted alone on branch `chore/sd-ai-command-pack-0.71.1`
from a clean synchronized `main`. No stash was needed.

| evidence | value |
|---|---|
| pull request | https://github.com/platypeeps/sd-github-review/pull/74 |
| commit | `49f65dc` |
| installed version | 0.64.3 to 0.71.1, `install.py --status --audit` reports `passed` |
| changed paths | 82 modified, 13 deleted, 2 added |
| `.gito/config.toml` | `refreshed`; `".trellis/**"` count on the branch is 0 |
| `.prism/rules.json` | `cea5089e24ac49f8e0e65ace7d32aa9d43852a5870d919a1352b8a458fde14c0` before and after — byte-unchanged |
| locally owned, preserved | `.github/PULL_REQUEST_TEMPLATE.md` |
| install mode | fat; no thin pin written, `--thin` never passed |

The `.gito/config.toml` diff is the intended narrowing and nothing else: the
blanket `".trellis/**"` line is replaced by five specific copied-surface
exclusions, with `.trellis/workspace/**` left reviewable on purpose.

The 13 retirements are the `sd-full-check` and `sd-review-local` surfaces the
pack dropped after 0.64.3, across every installed adapter. They are a
consequence of the version gap, not of the provider-config cohort — worth
naming because seven more consumers will show the same 13.

Copilot reviewed #74 with zero findings and zero inline threads, and the
repository's own `test` check passed in 18s. Phase B was authorized on that
evidence.

### Phase B result, 2026-08-12

All seven remaining consumers converted on branch
`chore/sd-ai-command-pack-0.71.1`, each from its own default branch, each
through `install.py <path> --force` from this checkout. Every one is an open
pull request in its own repository; none was merged here.

| consumer | from | pull request | M/D/A | `.gito` | `.prism/rules.json` |
|---|---|---|---|---|---|
| sd-github-review | 0.64.3 | platypeeps/sd-github-review#74 | 82/13/2 | refreshed | `current`, byte-unchanged |
| rwbp-coordinator | 0.64.4 | platypeeps/rwbp-coordinator#220 | 81/13/2 | refreshed | preserved, byte-unchanged |
| hoa-manager | 0.64.3 | platypeeps/hoa-manager#245 | 82/13/2 | refreshed | preserved, byte-unchanged |
| rwbp-website | 0.64.3 | platypeeps/rwbp-website#225 | 82/13/2 | refreshed | preserved, byte-unchanged |
| se-ai-command-pack | 0.64.33 | platypeeps/se-ai-command-pack#213 | 54/13/2 | refreshed | preserved, byte-unchanged |
| loadsmith | 0.64.27 | platypeeps/loadsmith#216 | 73/13/2 | refreshed | **refreshed** — it was `superseded`, not locally owned |
| anomaly-metric-creator | 0.64.3 | platypeeps/anomaly-metric-creator#368 | 83/13/2 | refreshed | preserved, byte-unchanged |
| mezmo_benchmark | 0.64.3 | answerbook/mezmo_benchmark#485 | 82/13/2 | refreshed | preserved, byte-unchanged |

Every branch reports `".trellis/**"` count 0, version 0.71.1, and an install
audit of `passed`; the conversion script aborted before committing on any
failure of those three, and none aborted. Copilot review was requested on all
eight.

`loadsmith`'s `.prism/rules.json` moving from
`6a06e3668fd89e0427ae0fe8879b27a8815144ba05381375a3fb1ed210fea4b7` to the
shipped `cea5089e…14c0` is R1 doing its job, not an R2 violation: the detector
classified that file `superseded`, so it was never one of the six locally owned
decisions R2 protects.

#### Stashes taken, and their fate

Three consumers had dirty trees. Each stash was created with the message
`sd-ai-command-pack provider config conversion 2026-08-12`, recorded here, and
popped on the branch it was taken from after the push.

| consumer | original branch | stash ref | restored |
|---|---|---|---|
| loadsmith | `main` | `da1d4914ddf03057a970339a91023f6afcf5e564` | yes, on `main`, no conflict |
| anomaly-metric-creator | `main` | `dc917cb5bd92ac98233c5c5fba9c23140f099e82` | yes, on `main`, no conflict |
| mezmo_benchmark | `cr/triage-grading-channel` | `55ad78cc47a7e7e51e16ad51ddeb771a7a5e96eb` | yes, on `cr/triage-grading-channel`, no conflict |

All three stashes held the same two paths, `.claude/agents/trellis-implement.md`
and `.claude/agents/trellis-research.md`, and all three checkouts ended with
exactly those two modified again and an empty stash list. The conversion
branches never carried them: the stash was taken on the original branch, the
install ran on a branch cut from the default, and the pop happened after
switching back.

#### Closing measurement, and why it reads 5/3

`sd-status fleet --json --no-network` after Phase B:

| `.gito/config.toml` | count |
|---|---|
| `current` | 5 |
| `superseded` | 3 |

This is expected and is not a partial conversion. The detector reads each
consumer's **checked-out working tree**, and the three consumers that were
stashed were switched back to their original branch so their own uncommitted
work could be restored where it belonged — `loadsmith` and
`anomaly-metric-creator` to `main`, `mezmo_benchmark` to
`cr/triage-grading-channel`. Their conversions live on
`chore/sd-ai-command-pack-0.71.1`, pushed, with open pull requests. The other
five are still sitting on the conversion branch, which is why they read
`current`.

Put plainly: eight of eight are converted on a branch and in review; five
happen to have that branch checked out. The registry-level count reaches 8
when the consumers merge, which is the post-archive handoff below.

#### What the six locally owned `.prism/rules.json` files are missing

Compared against the shipped `templates/.prism/rules.json` (8 `focus` entries,
4 `required` entries, 8 `severityOverrides` keys):

| consumer | missing `focus` | missing `required` | differing `severityOverrides` |
|---|---|---|---|
| rwbp-coordinator | `bug`, `performance`, `style` | none | `bug`, `maintainability`, `performance` |
| hoa-manager | `bug`, `performance`, `style` | `review-recurrence-prevention`, `trellis-task-scope` | `bug`, `maintainability`, `performance` |
| rwbp-website | `bug`, `performance`, `style` | none | `bug`, `maintainability`, `performance` |
| anomaly-metric-creator | `bug`, `performance`, `style` | none | `bug`, `maintainability`, `performance` |
| mezmo_benchmark | `bug`, `performance`, `style` | all four: `installer-safety`, `review-recurrence-prevention`, `secret-hygiene`, `trellis-task-scope` | `bug`, `maintainability`, `performance` |
| se-ai-command-pack | none | none | none — its `focus`, `required`, and overrides already match shipped; the file differs only in prose fields |

All six carry more `required` rules by count than the shipped four (5 to 12) —
these are tightenings their owners chose, which is why R2 leaves them alone.
Two of them nonetheless omit shipped ids: `hoa-manager` is missing two, and
`mezmo_benchmark`'s six `required` rules share no id with the shipped four at
all. The common
gap is the same in five repositories: the shipped `focus` list gained `bug`,
`performance`, and `style`, and the shipped severities for `bug`,
`maintainability`, and `performance` moved. That is the delta each owner should
consider merging by hand.

## Requirements

- R1: Every consumer whose config the detector reports as `superseded` is
  refreshed by running `install.py` from a pack source checkout, and re-reports
  as `current`.
- R2: No consumer whose config the detector reports as `local` is modified by
  this task. The six customized `.prism/rules.json` files are decisions; any
  shipped change they should adopt is merged by hand, deliberately, and is out
  of scope here.
- R3: Each conversion travels the consumer's own review and merge path. The
  pack does not push to a consumer's default branch.
- R4: Explicit per-cohort user authorization is obtained before the first
  consumer is touched, and recorded in this task.

## Acceptance Criteria

- [x] Per-cohort authorization is recorded in this task before any consumer
      repository is modified.
- [x] The blast radius of the prescribed mechanism is measured and the scope it
      implies is settled with the user before the first consumer is mutated.
- [x] The canary consumer's pull request is opened and reviewed before any
      other consumer is touched. (sd-github-review#74: Copilot zero findings,
      `test` pass; Phase B authorized on that evidence.)
- [x] Every stash this task creates in a consumer repository is recorded here
      with its message and ref, and is restored or explicitly reported as
      unrestored. (Three stashes, all popped without conflict on their original
      branches; every stash list ends empty.)
- [x] Every consumer the detector reports as `superseded` has an open pull
      request in its own repository carrying the refreshed `.gito/config.toml`,
      or a recorded reason it has none. (Eight of eight.)
- [x] On each conversion branch, the count of `".trellis/**"` in that
      consumer's `.gito/config.toml` is zero. (Asserted by the conversion
      script before each commit; no consumer aborted.)
- [x] The six locally owned `.prism/rules.json` files are byte-unchanged
      against digests recorded before that consumer's install, and the shipped
      delta each one is missing is written down for its owner.

### Post-archive handoff

`sd-status fleet` reporting zero `superseded` `.gito/config.toml` across the
eight consumers is the end state this task exists for, and it is **not** an
acceptance criterion: R3 puts each conversion through its consumer's own review
and merge path, and this task has no authority to merge there. The registry
keeps reporting `superseded` until each consumer merges on its own schedule.
Verifying that is the handoff, checked after archive, not a box this task can
tick.

## Notes

- The detector is the input: run `sd-status fleet --json --no-network` first
  and convert against measured state, never against a table copied from a prior
  session.
- `install.py <consumer> --force` now reports `refreshed` for exactly the
  superseded population and `preserved` for the locally owned one, so the
  conversion is the ordinary install rather than a bespoke script.
