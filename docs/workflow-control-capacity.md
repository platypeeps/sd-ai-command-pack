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


## Committed-source and stdin transport correction, 2026-09-10

The baseline is `d9c1a7717c6d55532f99d9ba38c9dc4b422d018e`.
The bounded correction reads prior-finding source from exact committed regular blobs.
It excludes untracked files and Git metadata, retains deleted-file evidence, and refuses unreadable or oversized blobs.
Codex receives the complete prompt through stdin instead of a platform-limited command argument.
The existing prompt limit, finding retention, completion checks, and provider selection remain unchanged.

| Tracked component | Baseline lines | Corrected lines | Change |
| --- | ---: | ---: | ---: |
| `bin/sd-review` | 1,641 | 1,660 | +19 |
| Other 40 `bin/` files | 19,085 | 19,085 | 0 |
| Total | 20,726 | 20,745 | +19 |

Set `BIN_CAP` to 20,745, consuming seven existing spare lines and adding twelve lines of capacity.
Set the review-lane ceiling to 1,986, an increase of nineteen lines.
The lane remains `sd-review` plus the unchanged 326-line `sd_setup_github.py`.
The inventory remains 41 runtime files, with zero reserve after the correction.
Removing the required validation or transport evidence to fit would weaken the correction.

This preparatory change contains only this record, the two ceilings, and the appended bin ceiling history entry.
Its runtime remains at 20,726 bin lines and 1,967 review-lane lines, within both old ceilings.
Implementation follows in a separate commit on the same delivery branch under the existing closeout exception.
All behavioral, inventory, native, external-review, and merge gates remain enforced.
This capacity decision neither proves implementation correctness nor increases the provider-call allowance.

## Installer calling-convention line, 2026-09-10

The baseline is `9a70cc0fd042889761f9f00185e56fd9b54bb7ad`.
`sd_install.py --status` gains one `commands:` line that says how this checkout's commands are reached.
It enumerates the executables in `bin/` and the entries of `PATH` at run time, and names a command that `PATH` resolves to another install.
The installer records surfaces only, so its receipt read as a partial install whenever the commands were looked for on `PATH`.

| Tracked component | Baseline lines | Corrected lines | Change |
| --- | ---: | ---: | ---: |
| `bin/sd_install.py` | 1,834 | 1,892 | +58 |
| Other 40 `bin/` files | 18,911 | 18,911 | 0 |
| Total | 20,745 | 20,803 | +58 |

Set `BIN_CAP` to 20,803, adding fifty-eight lines of capacity and no reserve.
The fifty-eight lines are measured on the written change, not forecast: `command_report()` is 49 lines, `_resolves_to()` is 3, and the 6 lines of glue are the `shutil` import, one call in `cmd_status`, and four blank separators.
The derivation is recorded beside `BIN_CAP` in `tests/test_loc_caps.py`.
The review-lane ceiling remains at 1,986; `sd_install.py` is not in that lane.
The inventory remains 41 runtime files, with zero reserve after the change.

This preparatory change contains only this record, `BIN_CAP`, and the appended bin ceiling history entry.
Its runtime remains at 20,745 bin lines, within the old ceiling.
Implementation follows in a separate pull request stacked on this one.
All behavioral, inventory, native, external-review, and merge gates remain enforced.
This capacity decision neither proves implementation correctness nor increases the provider-call allowance.

## R11-D48, 2026-09-11: the `bin/` ceiling is retired

`BIN_CAP` is deleted, along with its derivation chain and
`test_bin_stays_under_its_ceiling`. `bin/` now has no line-count ceiling and no
successor mechanism. This is a removal, not a raise, and it is the last entry
this document will carry for that ceiling.

The record it is argued from is `CEILING_HISTORY["BIN_CAP"]`, which is kept in
`tests/test_loc_caps.py` after the constant is gone:

| | |
| --- | --- |
| Recorded values | 21 |
| First | 8,000 on 2026-08-30 |
| Last | 20,803 on 2026-09-10 |
| Span | 11 days |
| Downward moves | 0 |
| Refusals | 0 |

R11-D41 read the first nine of those on 2026-09-06 and kept the gate,
reasoning that a ceiling which only reports is what the retired stack had.
Twelve further raises have not changed the answer: the gate has still never
returned "no". What it has returned is cost — R11-D24's clause forbids raising
a cap in the pull request that crossed it, so every raise is a serialised
preparatory pull request of its own, and R11-D38 alone cost an agent
twenty-two minutes and blocked four units of work behind it.

A control that has never refused is not bounding anything; it is charging for
the paperwork of agreeing. The clause is what made that charge compulsory, so
the way to stop paying it is to remove the cap rather than to keep the cap and
waive the clause.

Not retired, and not to be read as covered by this: `MIGRATE_CAP`;
`DASHBOARD_CAP`, `DASHBOARD_CODE_CAP` and `DASHBOARD_CODE_SLACK`, which have a
code/prose split and a payable-in-kind rule that `bin/` never had; and the
review lane's ceiling of 1,986 in `tests/test_sd_review_boundary.py`.

This preparatory change touches nothing under `bin/`, so it lands in the shape
R11-D24 asks for, against a tree the retired cap still passes at exactly
20,803 of 20,803. All behavioral, inventory, native, external-review and merge
gates remain enforced.

## 2026-09-11: `bin/` gets a successor mechanism, and this record closes

R11-D48 above retired the `bin/` ceiling and left no successor. This entry
records the successor: `tests/test_code_health.py`, five ceilings that apply
per function rather than per directory -- cyclomatic complexity, statement
length, nesting depth, structural duplicate pairs and unreferenced public
functions.

The two entries are one decision in two commits, and the order matters. R11-D48
had to stand on its own argument, because "the cap never refused anything" is
true whether or not anything replaces it. Nothing here weakens it.

This document closes with this entry. Every record above it exists because a
directory total had to be raised before a feature could land, and R11-D24's
clause made each raise its own serialised pull request. The new ceilings do not
move when a feature is added -- that is the single property they were chosen
for -- so there is no number to raise and no preparatory record to write. A
function that exceeds one of them is over its ceiling because of how it is
written, which is a review question, not a capacity question.

What the file still governs: `MIGRATE_CAP`, the three dashboard constants, and
the review lane's ceiling, none of which R11-D48 retired and none of which this
change touches. The lane's ceiling is the one number left here that a feature
can still bust, so it still gets a record when it moves; the entry below is
the first since this one.

## Review-lane ceiling for the Dependabot guard, 2026-09-11

The baseline is `a380ea2b fix(status-source): the contract says what the marker says, and rule 1's row sign is pinned (#822)`.
`sd-review setup-github` gains a second emitted file, the Dependabot `ignore:` guard for the review-route pin that seven consumers hand-wrote in six wordings, and a `--check` verb that renders both files at the repository's own pin and prints `same` or `DIFFERS` against the tracked bytes (sd:435).

| Tracked component | Baseline lines | Corrected lines | Change |
| --- | ---: | ---: | ---: |
| `bin/sd-review` | 1,660 | 1,660 | 0 |
| `bin/sd_setup_github.py` | 326 | 383 | +57 |
| Review lane | 1,986 | 2,043 | +57 |

Set the review-lane ceiling to 2,043, an increase of fifty-seven lines and no reserve; the lane stood at exactly 1,986 of 1,986 before this change.
The fifty-seven lines are measured on the written change, not forecast: the import, a second read, the guard-state refusal, the one write loop that keeps the installer at a single write site, the `--check` dispatch and its renderer, two result keys and one render line.
The guard template, the line transform that merges it into a consumer's `dependabot.yml` without a YAML round-trip, and the same/DIFFERS report are in a new module, `bin/sd_setup_guard.py`, which the installer imports and `bin/sd-review` does not, so the lane's derivation does not count it.
That is a module boundary and not a way around the number: the module is text-in/text-out and a test asserts it opens nothing, so the lane's proof that the installer is its one writer still reads one file and counts one write site.
Trimming prose in `sd_setup_github.py` to pay for the wiring is the trade R11-D41 names as the wrong one.

This preparatory change contains only this record and the ceiling in `tests/test_sd_review_boundary.py`.
Its runtime remains at 1,986 review-lane lines, within the old ceiling.
Implementation follows in a separate pull request stacked on this one.
All behavioral, inventory, native, external-review, and merge gates remain enforced.
