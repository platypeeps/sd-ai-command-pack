# Design: shared sandbox-safe tool environment

## Design Summary

Extend the pack toolchain with one environment builder that prepares private
external cache roots for known tool classes and returns an argv-plus-environment
execution plan. Shell and Python callers share the same policy instead of
copying environment fragments.

## Environment Model

The builder begins with the inherited environment and changes only documented
cache variables. It selects a validated root in this order:

1. an explicit pack cache-root override;
2. a writable safe inherited user cache root;
3. a validated system temporary root.

Within that root it creates a private per-user/per-repository namespace using a
stable digest rather than a raw path. Tool adapters map supported cache classes
to variables such as `XDG_CACHE_HOME`, `UV_CACHE_DIR`, and `PIP_CACHE_DIR`.
GitHub configuration/authentication paths are never redirected.

## Validation

Roots must be absolute, outside the repository, bounded, directory-valued,
non-symlink at the private creation boundary, and writable with private
permissions where supported. Creation and concurrent reuse use race-safe
directory operations. Unsupported platforms receive the same semantic policy
through portable path handling.

The result identifies which cache classes were routed and why. If preparation
cannot succeed, the caller stops before the external tool and reports a cache
setup failure separately from an operation/provider failure.

## Caller Integration

Pack subprocess helpers consume the environment plan for checks, GitHub
observation, review, fleet, status, and housekeeping. Existing uv/toolchain
behavior is migrated into the shared builder before duplicate snippets are
removed. Explicit valid consumer overrides retain precedence.

## Cleanup And Rollback

Reusable caches remain after normal execution. A separate bounded maintenance
operation may prune only pack-created namespaces by age/size; ordinary
housekeeping does not clear them. Rollback restores inherited cache behavior
without moving auth/configuration or deleting caches.
