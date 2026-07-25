# sd-review Data Operations Design

## Boundary

The command pack performs capability discovery, validates explicit operator
intent, delegates to versioned router contracts, and renders bounded results.
It never calculates retention deadlines, accesses storage directly, or decides
what data a purge covers.

```text
sd-review data status -> capability discovery -> retention_status -> render
sd-review data purge  -> confirm repo/actor/reason -> purge_repository_data
                       -> render live + backup deletion phases
```

Status is read-only. Purge is destructive, repository-scoped, idempotent, and
requires exact confirmation. GitHub-native artifacts are always listed as
outside the private purge boundary. Legal holds are visible but remain private
administrative operations in the initial release.

## Compatibility And Rollback

Missing or incompatible capabilities disable only data operations with
actionable guidance. Rollback removes the operator adapter but never cancels an
accepted purge, extends retention, mutates holds, or suppresses backup expiry.
