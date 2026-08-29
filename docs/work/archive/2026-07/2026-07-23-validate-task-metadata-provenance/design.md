# Design: task metadata provenance validation

## Boundary

Extend `validateTrellisTaskMetadata()` in the shipped review preflight. The
template script remains authoritative and the root script remains its synced
dogfood mirror. No new command, configuration file, or Trellis runtime change
is introduced.

## Metadata contract

The optional task record shape is:

```json
{
  "priority": "P2",
  "meta": {
    "priorityProvenance": {
      "sourcePriority": "P3",
      "rationale": "Promoted because the task owns the broader mutation-safety policy."
    }
  }
}
```

Absence of `meta`, absence of `priorityProvenance`, or an ordinary task with no
known source priority adds no new validation. Presence of the property opts the
record into the complete provenance contract.

Use a small pure helper adjacent to `validateTrellisTaskMetadata()`. It returns
field-relative issue strings so the existing changed-file check retains one
diagnostic pipeline. Validate in this order:

1. provenance is a plain object;
2. current and source priorities are members of `P0..P3`;
3. valid priorities differ; and
4. rationale is a trimmed, non-empty string within 1,000 characters.

Additional keys are ignored for forward compatibility. Rationale content is
never included in diagnostics, keeping output bounded and avoiding accidental
disclosure of copied source prose.

## Historical path regression

Keep the existing code-level archive exclusion in
`checkDocumentationPathReferences()`. Prove its intent with two real Git
fixtures:

- an archived task PRD references a tracked path, the path is deleted later,
  and preflight still passes; and
- an active task PRD follows the same sequence and preflight fails with the
  missing-path diagnostic.

The fixtures exercise the executable boundary rather than exporting another
helper. They prevent future refactors from treating archived evidence as live
documentation or accidentally grandfathering active PRDs.

## Compatibility and release

The optional metadata is backward compatible, but malformed declared
provenance becomes a new consumer-visible rejection. Under the pack versioning
policy this is changed command semantics, so the release identity advances
from `0.31.0` to `0.32.0` with synchronized payload hashes, changelog, and
candidate ledger.

## Rollback

Revert the template, spec, tests, manifest/changelog, regenerated mirrors, and
candidate ledger together. Do not hand-edit the root mirror or provenance
hashes independently.
