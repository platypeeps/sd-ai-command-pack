# Design: Native Codex review in Claude local-review fan-out

## Boundary

`sd-ai-command-pack` owns the Claude-specific orchestration and invokes the
supported `codex review` CLI directly. The OpenAI Codex Claude plugin is neither
required nor modified. Claude continues to own concurrent task execution, while
the existing local-review runner retains Prism, Gito, and configured shell
provider behavior.

Codex is an automatic Claude host lane, not a new generic runner tool identity.
Explicit runner tool names continue to select only the runner stack.

## Claude orchestration

The command-surface generator will support a bounded Claude-only insertion for
`sd-review-local`, keeping the neutral source and non-Claude adapters unchanged.
The generated Claude flow will:

1. Resolve checkout trust, the SD skill, tool selection, effective scope, and
   base ref through existing contracts.
2. If scope is `all`, run only the selected full-codebase runner stack and
   report the Codex scope limitation.
3. Otherwise capability-check `codex review --help` for the required native
   target flag without invoking a review.
4. Launch the validated runner command and matching Codex review concurrently
   using Claude background Bash task support.
5. Collect both tasks even when either lane fails.
6. Normalize, verify, and deduplicate findings from every completed lane before
   the existing `review-local.findings` decision.

The adapter must not inspect Claude marketplace metadata, resolve plugin cache
paths, invoke `codex-companion.mjs`, or mutate user-level plugin state.

## Scope mapping

- Dirty working tree: `codex review --uncommitted`.
- Clean tree with a resolvable branch base: `codex review --base <resolved-ref>`.
- Full checked-out repository (`all`): Codex is skipped with an explicit scope
  mismatch because the native reviewer has no equivalent target.

The existing SD skill remains authoritative for dirty-state and base-ref
resolution. Both lanes must review the same effective change set.

## Capability and fallback

Before launching Codex, verify that `codex` exists and that `codex review
--help` advertises the required flag. Authentication/runtime failures may still
occur only during review and are handled as a failed lane.

| Codex state | Runner state | Result |
| --- | --- | --- |
| Compatible and succeeds | Completes | Combine and verify both outputs |
| Missing/incompatible | Completes | Continue runner; report Codex skipped with setup guidance |
| Starts and fails | Completes | Keep runner findings; report incomplete Codex lane; never claim clean |
| Any | Fails | Preserve Codex result if present and report runner failure under its existing contract |
| Full-codebase scope | Completes | Runner only; report unsupported Codex scope |

The fallback guidance points to supported Codex CLI installation and login
flows. It does not suggest installing the Claude plugin.

## Fix-loop behavior

Codex findings participate in the same user selection boundary as Prism/Gito
findings. A selected Codex finding is verified against repository evidence
before editing. Because native Codex review has no file-only target, verification
reruns it at the original supported scope. The final original-stack regression
pass includes Codex only when it was compatible initially; later failure or
unavailability is reported as a degraded lane.

## Compatibility and rollout

The generated Claude adapter activates automatically anywhere a compatible,
authenticated Codex CLI is available. This is already the runtime prerequisite
used by the optional Claude plugin, so plugin users do not need separate Codex
credentials or configuration.

No plugin version constraint, cache patch, environment variable, new command
argument, or generic runner alias is introduced. Users can install, update, or
uninstall the Claude plugin independently. Rolling back this feature restores
the existing runner-only Claude flow without touching Codex or Claude state.
