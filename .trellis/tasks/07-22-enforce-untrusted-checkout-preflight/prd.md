# Enforce untrusted checkout preflight

## Goal

Prevent generated command adapters from executing checkout-owned code before
establishing whether the checkout and PR source are trusted. Replace the current
four-command warning allowlist with a canonical, generated, fail-closed policy.

## Evidence

- `.github/scripts/generate-command-surfaces.py:132-141` limits the current
  untrusted-PR note to `start`, `continue`, `finish-work`, and `full-check`.
- Other generated prompts execute repository-owned scripts or checks; for
  example `templates/.github/prompts/sd-review-local.prompt.md:13-18` invokes
  the local review runner and can apply fixes.
- A warning attached to selected prompt prose is not an enforceable capability
  boundary and drifts as new commands are added.

## Dependencies

- This is an independent foundation with no implementation prerequisite.
- It owns canonical checkout-trust metadata and generated adapter preflight;
  downstream command-surface work, including routed review, consumes that
  policy rather than defining command-specific exceptions.
- If another foundation task lands generator or manifest changes first,
  reconcile against that contract without restoring earlier generated output.

## Requirements

- R1: Classify every public command in canonical metadata by whether it may
  execute checkout-owned code, mutate local state, mutate remote state, or only
  interpret trusted static pack content.
- R2: Generate a trust preflight for every adapter that may execute checkout
  code. New commands default to requiring the preflight unless explicitly
  classified as non-executing.
- R3: Run the preflight before loading or executing repository-provided scripts,
  hooks, configs containing commands, package tasks, provider adapters, or
  changed skill instructions.
- R4: Distinguish trusted local branches, same-repository PRs, untrusted forks,
  unreadable origin state, and detached/ambiguous checkout identity. Ambiguous
  or unreadable state fails closed.
- R5: For untrusted code, use trusted-base inspection or non-executing static
  reporting where a useful safe mode exists. Otherwise stop with precise
  guidance; do not offer a casual approval prompt that normalizes executing
  attacker-controlled code.
- R6: Keep platform-specific mechanics generated from one policy. Canonical
  skill content must not assume one host's tool names.
- R7: Preserve explicitly safe read-only Git/GitHub metadata inspection needed
  to classify trust, while avoiding checkout-owned binaries and hooks.
- R8: Make exemptions rare, documented, testable, and limited to commands that
  cannot execute checkout content. `sd-help` is the expected exemplar; command
  names alone are not sufficient evidence.
- R9: Include trust classification and the selected safe/blocked path in final
  command reporting.

## Acceptance Criteria

- [ ] Generated adapter tests enumerate every live command and fail if an
  execution-capable command lacks the preflight.
- [ ] Fork-PR fixtures prove no changed checkout script, package command, hook,
  provider adapter, or skill payload executes before trust is established.
- [ ] Same-repository and trusted-local fixtures retain normal operation.
- [ ] Detached, unreadable, and contradictory origin states fail closed with
  actionable diagnostics.
- [ ] New command metadata defaults to execution-capable/preflight-required
  until deliberately classified.
- [ ] No platform-specific prompt can silently opt out of the canonical policy.
- [ ] Templates, generated adapters, manifest parity, focused security tests,
  and `make check` pass.

## Out Of Scope

- Sandboxing arbitrary third-party review providers.
- Treating user confirmation as a substitute for code-origin trust.
- Changing GitHub repository permissions or branch-protection settings.
- Opening an upstream Trellis PR.
