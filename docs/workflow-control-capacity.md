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

## Measured review recovery reservation, 2026-09-09

The remaining closeout corrects review timeouts, renewals, and response parsing.
This reservation uses the combined implementation, not estimates from separate patches.
Its baseline is `bb7c6653d7f96669ead1e25ebe444351d2cc51e8`.

| Tracked component | Baseline lines | Combined lines | Change |
| --- | ---: | ---: | ---: |
| `bin/sd-ship` | 539 | 682 | +143 |
| `bin/sd-review` | 1,518 | 1,559 | +41 |
| Other 38 `bin/` files | 17,990 | 17,990 | 0 |
| Total | 20,047 | 20,231 | +184 |

The ship changes budget the complete eligible reviewer chain, including fallbacks.
They bound process-group cleanup and preserve timeout evidence without certifying completion.
A renewed request binds one allowance to the exact prior history and current head.
The reviewer binds timing inputs and accepts whole-message JSON fences only for URL responses.
Bounded schema diagnostics retain the existing findings and completion requirements.

The review lane remains `bin/sd-review` plus `bin/sd_setup_github.py`.
It grows from 1,844 to 1,885 lines; the 326-line GitHub module is unchanged.
The import-derived inventory continues to enforce this boundary.

Set `BIN_CAP` to 20,231 and the review-lane ceiling to 1,885.
The increases are 181 and 25 lines, consuming the existing headroom of 3 and 16 lines.
No additional reserve is included. Any further growth requires another capacity decision or a reduction.
No dashboard, migration, file-enumeration, or completion gate changes.

This preparatory commit changes only this record, the two ceilings, and the appended bin ceiling history entry.
Its runtime remains at 20,047 bin lines and 1,844 review-lane lines, within both previous ceilings.
The implementation follows on the same delivery branch, under the existing closeout exception.
The required tests, static checks, external review, and exact-head CI still govern delivery.
This capacity decision does not establish implementation correctness or external review completion.


## Deterministic review preflight correction, 2026-09-09

The completed review found that oversized prior evidence passed planning and then consumed a reservation before refusing.
The correction validates evidence during planning and reserves a provider pass only after planning succeeds.
It keeps complete prior history, preserves planning timeout diagnostics, and leaves execution failures spent.
The current pack history is 48,932 findings bytes, below the unchanged 65,536-byte input bound.

| Tracked component | Reviewed lines | Corrected lines | Change |
| --- | ---: | ---: | ---: |
| `bin/sd-ship` | 682 | 695 | +13 |
| `bin/sd-review` | 1,559 | 1,561 | +2 |
| Other 38 `bin/` files | 17,990 | 17,990 | 0 |
| Total | 20,231 | 20,246 | +15 |

Set `BIN_CAP` to 20,246 and the review-lane ceiling to 1,887.
The inventory remains 40 files, with zero reserve and no change to the 326-line GitHub module.
These fifteen lines fund bounded source reads and the preflight reservation/diagnostic boundary.
Malformed or failed planning retains bounded stream tails and hashes, so its exact refusal remains inspectable.
No review-history truncation, numeric review allowance, provider selection, or automatic cap changes.
The coordinator approved this measured correction within the existing closeout scope.
The capacity commit precedes its implementation; required validation and external review still govern delivery.

## Evidence-backed acceptance and advisory routing, 2026-09-09

The user approved evidence-backed disposition acceptance and correction of Dependabot issue #799.
The remaining review-reliability work also adds a final compact output contract for URL reviewers.
This reservation uses the combined implementation against `f6a78c8edf428e2b480614bf90ad12e58c75e465`.

| Tracked component | Baseline lines | Combined lines | Change |
| --- | ---: | ---: | ---: |
| `bin/sd-ship` | 695 | 725 | +30 |
| `bin/sd_ship_dispositions.py` | 0 | 175 | +175 |
| `bin/sd-review` | 1,561 | 1,585 | +24 |
| Other 38 `bin/` files | 17,990 | 17,990 | 0 |
| Total | 20,246 | 20,475 | +229 |

The acceptance helper binds explicit decisions to the exact head, raw findings, review history, tools, policy, and evidence.
It appends separate receipts and preserves every raw review and spent reservation.
Publication still requires complete review coverage, passing checks, and the existing merge guards.
The shipping changes also prevent advisory unknown-authorship results from consuming a provider reservation.

The reviewer adds eleven lines for advisory authorship reporting and thirteen lines for the final URL output contract.
Advisory routing selects no provider when attribution is unknown; actual reviews still refuse.
The URL contract follows the complete unchanged source and history input.
It requests compact findings without changing parsing, completion requirements, or provider selection.
Its effect on live provider truncation remains unverified until an authorized review runs.

Set `BIN_CAP` to 20,475 and the review-lane ceiling to 1,911.
The inventory contains 41 runtime files, including the new helper, and includes no additional reserve.
The review lane remains `sd-review` plus the unchanged 326-line GitHub module.
No dashboard ceiling, shared-core exemption, file-enumeration rule, or numeric review allowance changes.

This preparatory commit changes only this record, both ceilings, and the appended ceiling history entry.
Its runtime remains at 20,246 bin lines and 1,887 review-lane lines, within the previous ceilings.
Implementation follows on the same delivery branch under the existing closeout exception.
The capacity decision does not establish correctness, accept any finding, or authorize further paid reviews.

## Provider diagnostics and contribution tracking, 2026-09-09

The user approved tasks sd:131 and sd:132, captured from issues #800 and #801.
Provider preflight adds a synthetic schema probe and bounded diagnostics.
Contribution commands and status use the shared database projection in the system repository.

The combined inventory starts at `2272ac43c516d848660b75adb903c0ca1a96ebaf`.
Git and filesystem enumeration agree on all 41 runtime files.

| Tracked component | Baseline lines | Combined lines | Change |
| --- | ---: | ---: | ---: |
| `bin/sd-review` | 1,585 | 1,641 | +56 |
| `bin/sd_registry.py` | 1,274 | 1,297 | +23 |
| `bin/sd_work.py` | 202 | 333 | +131 |
| `bin/sd-status` | 2,583 | 2,629 | +46 |
| Other 37 `bin/` files | 14,831 | 14,831 | 0 |
| Total | 20,475 | 20,731 | +256 |

Set `BIN_CAP` to 20,731 and the review-lane ceiling to 1,967, with zero reserve.
The review lane still includes the unchanged 326-line GitHub module.
Shared validation, activity classification, and notification state remain in the system repository.
The pack adds no duplicate storage or dependency rules.

This preparatory commit changes only this record, the two ceilings, and the appended history entry.
Its runtime remains within the previous ceilings: 20,475 total lines and 1,911 review-lane lines.
Implementation follows on the same delivery branch under the existing closeout exception.
All existing inventory, test, lint, security, review, and merge checks remain required.
This capacity record neither proves live provider recovery nor grants additional provider calls.

## Review planning and installed-schema guards, 2026-09-09

The latest review exposed two failures in `0dc1be4cfe6f319224187a88ef0cd82d524298a7`.
Shipping reserved a review pass when eligible reviewers could not meet the requested depth.
An unreadable committed schema raised `TypeError` instead of returning the installed-library preservation refusal.

| Tracked component | Baseline lines | Corrected lines | Change |
| --- | ---: | ---: | ---: |
| `bin/sd-ship` | 725 | 727 | +2 |
| `bin/sd_library_guard.py` | 44 | 44 | 0 |
| Other 39 `bin/` files | 19,962 | 19,962 | 0 |
| Total | 20,731 | 20,733 | +2 |

The two added lines require a positive integer review depth and sufficient eligible candidates before reservation.
The schema guard handles the existing Git callback's missing-result value without adding lines.
Set `BIN_CAP` to 20,733 for this measured correction, with zero reserve across the same 41 runtime files.
The review lane remains at its unchanged 1,967-line ceiling.

The preparatory commit contains this record, `BIN_CAP`, and its appended history entry.
Implementation follows on the same delivery branch under the existing closeout exception.
All existing validation, review, reservation-history, and merge requirements remain enforced.
This capacity correction grants no additional provider calls.

## Review history input bound, 2026-09-10

The separate 65,536-byte findings limit refused complete retained history before the existing verification budget was reached.
Remove that smaller limit and preserve every finding and its provenance.
Enforce the existing 2,000,000-byte UTF-8 verification-prompt limit after all prompt assembly, including empty and advisory-only history.
This check precedes explanation, dry-run output, deterministic checks, and provider execution.
The bounded prior-report loader, current-source reads, incremental prompt checks, and separate review-material guard remain in place.

The runtime change removes two lines and adds two lines in `bin/sd-review`.
Runtime inventory, line ceilings, review depth, and spent-pass history remain unchanged.
These byte limits do not define an aggregate URL-request limit, model token budget, or platform command-argument limit.
This correction does not discard history or authorize additional provider calls.
