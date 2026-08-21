# Mark retired-file citations absent in anomaly-metric-creator docs

## Goal

Get anomaly-metric-creator's `main` back to a clean review preflight by marking
its two citations of deliberately deleted files as absent, without deleting the
sentences that describe why those files are gone.

## Context

anomaly-metric-creator's `main` currently fails the review preflight with two
findings, both in its development-cycle documentation:

```
FAIL docs/DEVELOPMENT_CYCLE.md:236 references missing path scripts/_sd_pack_forward.py.
FAIL docs/DEVELOPMENT_CYCLE.md:251 references missing path tests/test_sd_check_helper_forwarders.py.
```

Found while verifying an unrelated change against that repository; established
as pre-existing by running the preflight against the same base with and without
the change and diffing the sorted FAIL sets. Neither finding was introduced by
that work. Paths named here without repo-relative form on purpose: the file
lives in that consumer, not in the pack, and citing it as a path would fail the
pack's own documentation path-reference gate.

The sentences are not wrong. They are a retirement note — a "Local review-gate
helper forwarders (retired)" section describing five forwarders the repository
used to carry and explicitly recording that they are gone and must not be
reintroduced. The paths do not resolve *because the removal succeeded*.

Deleting the citations would be the wrong fix twice over: it would erase the
record of what was removed, and the section's whole purpose is to stop someone
reintroducing those files.

## Requirements

- Use the affordance the checker already provides rather than inventing one.
  The pack's review preflight skips a reference followed by an `[absent: <reason>]`
  marker, and it fails closed on every malformed or misplaced form — empty
  reason, missing colon, unclosed bracket, a marker on the next line or before
  the reference, or anything but spaces and tabs in between. The marker must sit
  immediately after the reference on the same line.
- Give each marker a reason that says *why* the path is absent, not merely that
  it is. A retirement note whose marker reads `[absent: missing]` has laundered
  a deliberate removal into an unexplained gap.
- Change nothing else in that section. The prose is accurate; only the two
  references need marking.
- Confirm the fix the same way the problem was established: preflight before and
  after against the same base, diffing sorted FAIL sets. A total that drops from
  2 to 0 is the expected result, but the diff is what proves nothing else moved.

## Acceptance Criteria

- [ ] The whole-tree review preflight on anomaly-metric-creator's default branch reports zero failures. Invoked with no arguments — passing `--base` silently scans nothing and reports a clean run against an empty set.
- [ ] Both retired-file citations survive in the prose, each carrying an `[absent: <reason>]` marker whose reason names the retirement rather than restating that the file is missing.
- [ ] The before/after FAIL-set diff shows exactly the two known findings removed and no other change.
- [ ] No other repository is touched. This defect is local to one consumer's documentation and is not a pack payload change.
