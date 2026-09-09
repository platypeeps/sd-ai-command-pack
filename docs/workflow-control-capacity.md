# Capacity for the approved workflow controls

2026-09-08. The user approved task controls, reliable database progress,
writing integration, and operational controls, in that order. These add CLI
interfaces that the previous 18,550-line budget did not include.

The first approved CLI reservation was 19,500 lines. It allocated 950 lines for the
task/work interface, writing gateway, operations gateway, shared-library
loading, and existing callers that must use verified completion. Domain
operations remain in the system repository's `sd_db` library, shared with the
dashboard. The gateways must not duplicate their validation or storage rules.

This is a capacity change for the approved feature scope, not evidence that
the implementation is correct. The full test, lint, type, installer, and
security checks remain required. The line-count inventory and its history
remain enforced. No dashboard ceiling is raised: replacing its old unverified
delivery implementation pays for its read-only cache opening change.

No pull request or commit is created by this local implementation. When the
work is published, keep this capacity decision and its test constant as the
preparatory change required by the existing cap policy, before publishing the
implementation that uses it.

2026-09-08 closeout: the user asked to close all remaining work, including
reviewer reliability. The review lane's separate cap moves from 1,700 to 1,800
lines. It measured 1,768 lines after the Claude reader and exact-subject
transport were added, and 1,770 after preserving untracked symlinks as links.
Schema-validation closeout brings the lane to 1,776 lines, with 24 lines of
headroom. This adds capacity for:

- Ordered availability fallbacks that preserve findings, honor the requested
  review depth, and report the providers that actually completed.
- A Claude structured-output reader with read-only tools, disabled local
  customizations, and explicit error-envelope handling.
- Exact diff and file material for Claude and URL transports, with unreadable
  and oversized input refused instead of a partial review.
- Shared output-schema validation that keeps malformed responses incomplete
  while retaining usable blockers, including unknown locations and overflow.

The registry also gains per-provider environment filtering and read-only
database state resolution. At this checkpoint the filesystem-derived tracked
`bin/` inventory measures 19,159 lines against its existing 19,500-line cap;
the overall cap is unchanged. `tests/test_sd_review_boundary.py` continues to
enumerate the review lane and enforces its 1,800-line cap. Publish this decision
and that constant in the preparatory commit before the implementation, on the
same delivery branch. No separate bookkeeping pull request is needed.

## Mechanical delivery adapter reservation, 2026-09-08

The closeout adds a real ship/merge adapter where only prose existed. The
final adapter measures 470 lines for CLI sequencing and 146 for fresh remote
guards. The review lane measures 1,830 lines after exact fix-range, original
blocker context, multiple-author and native authentication integration. The
shared receipt/proof module lives in the owning system repository and measures
196 lines. Tests are outside the bin total.

The new code pays for durable pre-dispatch receipts, bounded review and fix
verification, exact-head push and squash merge, authoritative CI/protection/
ownership checks, lost-response reconciliation, explicit database binding,
read-only observation, and atomic completion from owned-clone merge proof.
The proof preserves the historical verified default tip; delayed retention
does not invalidate it or require fetching into a frozen clone.

Approved combined reservation: bin 20,050; reviewer lane 1,860. Against the
initial measured 19,159-line bin baseline, the complete current inventory is
19,890 lines across 40 files, including untracked new source. The reservation
includes the runner and Skills gateway changes and leaves 160 lines for
integration. The coordinator repeats this inventory after all lanes settle.

The capacity decision and constants belong in a preparatory commit before the
implementation commit on the same delivery branch. No separate bookkeeping
pull request is needed. The preparatory commit contains this decision, the
test constants and the ceiling history entry; implementation follows it.
