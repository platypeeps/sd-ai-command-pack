# Add shellcheck/actionlint coverage for pack-shipped shell

## Goal

From loadsmith's security audit absences: consumers vendor ~6k lines of
pack shell with only `bash -n` syntax gates, while exempting those files
from line review ("reviewed upstream"). Make upstream lint rigor the
compensating control.

## Requirements

- R1: Pack CI runs `shellcheck` over every tracked shell script (templates
  and installed twins) plus the tracked git hooks, gating at severity
  `warning` — the achieved baseline, stricter than the originally planned
  `error` floor.
- R2: All existing findings are fixed or explicitly annotated: real
  defects get code fixes; deliberate patterns get targeted
  `shellcheck disable` directives with a justification comment.
- R3: Template fixes ship to consumers (version bump + fleet refresh).

## Non-goals

- actionlint for workflows: zizmor already gates `.github/workflows/` for
  security, the workflow-pip checker covers the recurring mechanical
  pattern, and adding a pinned actionlint binary is deferred until a
  concrete workflow-syntax defect motivates it.

## Acceptance Criteria

- [x] `shellcheck -S warning` clean across `git ls-files '*.sh'` and
      `.githooks/pre-push`, enforced in the CI security lane.
- [x] The two baseline findings addressed: SC2164 in
      `sd-ai-command-pack-review-local.sh` (real fix: `cd ... || exit 1`
      under a no-`errexit` script) and SC2123 in
      `sd-ai-command-pack-housekeeping.sh` (annotated: emptying `PATH` is
      the hermetic self-test's purpose).
- [ ] Fleet refreshed with the fixed templates (post-merge step).
