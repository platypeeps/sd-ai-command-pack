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

- [ ] Per-cohort authorization is recorded in this task before any consumer
      repository is modified.
- [ ] After conversion, `sd-status fleet` reports zero `superseded`
      `.gito/config.toml` across the eight consumers.
- [ ] The count of `".trellis/**"` across the eight consumer `.gito/config.toml`
      files is zero.
- [ ] The six locally owned `.prism/rules.json` files are byte-unchanged, and
      the shipped delta each one is missing is written down for its owner.

## Notes

- The detector is the input: run `sd-status fleet --json --no-network` first
  and convert against measured state, never against a table copied from a prior
  session.
- `install.py <consumer> --force` now reports `refreshed` for exactly the
  superseded population and `preserved` for the locally owned one, so the
  conversion is the ordinary install rather than a bespoke script.
