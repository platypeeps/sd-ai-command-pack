---
title: Fewer and cheaper local gate runs per pull request
created: 2026-09-29
branch: feat/gate-reuse-2041
item: sd:2041
---
# PRD — gate reuse

## Problem

Under `repo.ci = local`, `sd-ship prepare` and the `sd-ship merge` local gate
each ran the repository's full check on the same head. Prepare's run was
bounded by the reviewers' 1800-second phase, while the merge gate allows 3600
seconds; on 2026-09-28 a branch that needed 1449 s alone risked a prepare
timeout. A Markdown-only pull request paid the full check twice too: 16 to 25
minutes of Rust tests in mezmo-world-simulator for a one-line docs change.

This item bundles sd:2041, sd:1912 (the PRD in
`docs/work/2026-09-28-check-receipts-on-the-item-lane/`) and sd:2072.

## Requirements

1. Prepare's passing gate run at a head leaves a receipt; the merge gate at
   the same head and inputs, on this machine, within 30 minutes, reads it
   instead of running the check again. Nothing else reuses a receipt.
2. Any gate prepare starts takes the sd:1996 machine-wide slot.
3. Prepare's gate bound equals the merge gate's `CHECK_SECONDS`.
4. A repository may declare a docs-only scope in its reviewed tree. When every
   changed path matches, `sd-check` and the local gate run only the docs
   command, and the status names the scope. A change to the declaration, the
   Makefile or the check scripts forces the full check. No declaration is
   today's behaviour.

## Acceptance criteria

- [x] The merge gate at a head with an equal binding reuses prepare's
      receipt; a changed input, environment variable, head or a receipt older
      than 30 minutes runs again. A second prepare, or a second merge gate,
      runs again.
- [x] Prepare's gate takes a slot from the shared slot directory.
- [x] With no `--review-timeout`, prepare's gate gets `sd_lib.GATE_CHECK_SECONDS`.
- [x] A docs-only change with a declaration posts `sd-check pass (docs-only)`.

Trust boundary: inputs outside the repository (external makefiles, tool
files, machine state) are not bound. The short same-head window is the
accepted residual risk. A repository that needs stronger guarantees uses the
explicit dependency contract; sd:1912 stays open for that.

The decisions, and what the binding does not cover, are in [design.md](design.md).
