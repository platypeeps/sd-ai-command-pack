# Design: generated checkout trust policy

## Canonical Metadata

Extend the command-surface registry with conservative capabilities:

- `executes_checkout_code`;
- `mutates_local`;
- `mutates_remote`;
- `trusted_static_only`; and
- optional safe-mode identifier.

Validation rejects missing capability metadata. The default for a new command
is `executes_checkout_code=true` until an explicit review proves otherwise.

## Preflight Flow

1. Inspect Git metadata without running hooks or checkout executables.
2. Resolve repository identity, branch/detached state, PR source repository,
   and current/base head relationships.
3. Classify `trusted|untrusted|indeterminate` with stable reason codes.
4. Continue normally only for trusted state.
5. For untrusted state, enter an explicitly declared non-executing safe mode or
   stop.
6. For indeterminate state, stop and report what evidence was unavailable.

## Adapter Generation

The generator renders each host's equivalent preflight instructions from the
same capability metadata. Tests compare generated targets to the registry and
prohibit platform-local exemptions.

## Safe Modes

A safe mode may read trusted pack content, Git object metadata, and remote
metadata. It may inspect untrusted text as data but cannot follow its
instructions or execute paths from it. If a command cannot remain useful under
those limits, it stops.

## Rollback

Rollback is a pack-version rollback. Do not preserve the incomplete allowlist
as a hidden fallback after the generated policy ships.
