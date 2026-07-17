# Fleet Refresh 0.15.5 Design

## Overview

Roll out the tagged pack release through the existing operator-triggered fleet
pipeline. The source checkout remains the installer authority; each consumer
is an isolated sequential transaction with preflight, install, audit, local
gate, PR review, housekeeping merge, and post-merge verification.

## Proposal

Start with `scripts/sd-ai-command-pack-fleet-preflight.py`. Its target version,
local path, platform list, and exact install/audit commands define the worklist.
Consumers already at `0.15.5` are evidence rows only and receive no branch or
empty PR.

For each stale consumer, first update its clean default branch with a
fast-forward pull. Create a unique `codex/refresh-sd-ai-command-pack-0-15-5`
branch, run the printed installer command from this pack checkout, and run the
printed audit command with all four expected platforms. Inspect the resulting
diff to ensure it contains only pack-managed payload, receipts, provenance,
and marker blocks.

Run the consumer's documented full-check. A failure stops that consumer before
publication and leaves its branch for inspection. A passing consumer is
committed, pushed, and opened as a PR. Use the installed `sd-review-pr` and
`sd-housekeeping` contracts in that checkout: wait for CI and remote review,
fix only pack-integration findings, and merge only when the gate proves clean
state, identical heads, green checks, and zero unresolved threads.

After merge, rerun the source-owned install audit against the consumer's clean
default branch and verify `.sd-ai-command-pack/provenance.json` reports
`0.15.5`. Only then advance to the next manifest row.

## Boundaries

- Never edit consumer product code or repo-owned policy to make a refresh pass.
- Never modify original Trellis-owned files as part of the pack rollout.
- Never create PRs in the upstream Trellis repository.
- Never stash, reset, clean, or install into a dirty consumer checkout.
- Never process consumers concurrently or leave one unresolved while starting
  another.

## Risks

- A consumer may have repo-owned wrappers or ignored local platform state that
  changes the installer result. Treat audit/full-check failures as evidence and
  skip rather than loosening policy during this task.
- Review latency can make a cleared reviewer request look complete before
  threads materialize. Use the installed review/watch settle guards.
- A prior refresh branch or PR may already exist. Reuse only when it targets
  the same release and exact current head; otherwise report the conflict.

## Validation

- Release tag and source checkout are clean before rollout.
- Source preflight before and after the rollout.
- Expected-platform install audit before every PR and after every merge.
- Consumer-documented full-check before every PR.
- GitHub CI/review/thread state through installed SD skills.
- Final clean/default/head/provenance verification in every touched checkout.
