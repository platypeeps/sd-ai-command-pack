# Design: current review-learning planning signal

## Design Summary

Expose the scanner's existing historical clusters in its typed read-only JSON
report, then let the unified review controller select only clusters relevant to
the current changed path families. Collect once per review attempt and reuse a
bounded receipt; never update the tracked learning document implicitly.

## Report Contract

Each cluster contains family ID/label, counts, PR and time bounds, normalized
path families, bounded representative signatures, example references,
truncation facts, and evidence freshness. Raw full comments remain on GitHub or
in existing local artifacts and are not copied into the planning payload.

The top-level report distinguishes `live`, `cached`, `stale`, `truncated`, and
`unavailable` evidence. Authentication/rate-limit/network failures retain a
typed limitation and zero confidence.

## Collection And Reuse

At review-attempt start, the controller requests one bounded scan. A private
review-artifact cache may be reused only when repository identity, schema,
GitHub watermark, and lifetime match. Cache writes belong to `sd-review`, not
`sd-check`, and use atomic private storage outside tracked paths.

Changed path families select applicable clusters. The resulting matrix is
passed to local review as historical risk evidence. It may suggest questions or
sibling checks but cannot mark code defective, tests covered, or review clean.

## Durable Curation

The tracked `docs/review-learnings.md` remains an explicit maintainer snapshot.
Ordinary review reports its age and whether newer live evidence exists.
`sd-review-learnings --update` retains its separate authorization and atomic
write contract.

## Rollback

If live learning consumption is disabled, review continues under the parent's
provider policy with a visible `historical-learning-unavailable` limitation. No
review receipt or exact-head evidence is reused from the learning cache.
