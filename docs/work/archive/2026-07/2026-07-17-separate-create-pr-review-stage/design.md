# Separate sd-create-pr Publish And Review Stages Design

## Overview

`sd-create-pr` currently combines two responsibilities: publish or reuse a
pull request, then invoke `sd-review-pr`. That is correct for standalone use,
but `sd-ship` already models review as its own Stage 2. Calling the complete
standalone flow from Stage 1 therefore runs review twice and prevents Stage 2
from selecting the merge-through `defer-finish-work` behavior.

## Invocation Contract

Keep standalone `sd-create-pr` as the default and only public behavior. Add an
internal orchestration context with three required values:

- caller: `sd-ship`
- stage: `1`
- return-after: `pr`

The context is supplied directly by an active `sd-ship` workflow while it
delegates Stage 1. It is not an environment variable or public command
argument. A user attempt to supply `publish-only`, `caller=`, `stage=`, or
`return-after=` to `sd-create-pr` must stop before any side effects.

After Step 5, the verified internal context returns the PR identity and publish
result to `sd-ship` instead of entering Step 6. Every standalone invocation
continues through Step 6 and hands off to `sd-review-pr` as before.

## Stage Ownership

- `sd-ship until=pr`: Stage 1 delegates `sd-create-pr` with the internal
  context, receives the PR result, and stops without review.
- `sd-ship until=review`: Stage 1 publishes only; Stage 2 invokes the normal
  `sd-review-pr` flow once, including finish-work.
- `sd-ship until=merge`: Stage 1 publishes only; Stage 2 invokes
  `sd-review-pr defer-finish-work` once; Stage 4 owns finish-work and merge.
- Standalone `sd-create-pr`: publishes and invokes normal `sd-review-pr` once.

## Boundaries

This is an instruction-contract change, not a new executable or persistent
state mechanism. It does not change update-spec, staging, commit, push, PR,
review, CI, watch, finish-work, or housekeeping internals. Platform adapters
remain thin entry points and do not expose the internal context.

## Validation

Focused tests inspect the shared skill contracts and prove all four routing
cases, rejection of user-supplied internal controls, standalone review
preservation, and template/mirror parity. Canonical pack checks and the fleet
candidate validation cover manifest, generated surfaces, and consumer payload
compatibility.
