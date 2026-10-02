---
title: A review receipt binds only what decides a review
created: 2026-09-29
item: sd:1834
branch: feat/review-binding-1834
---

# PRD — review binding semantics

Bundles sd:1834, sd:1397 and sd:1246. sd:1834 is the row of record; the
other two close with it or narrow to what this plan leaves out.

## Status

2026-09-29, operator decisions (relayed by session system-41):

- The binding is approved as designed. `verdict` files bind by normalized
  hash; `policy` entries stay byte-exact; `gate` and `check` files leave the
  digest and are recorded per file, so a refusal names them. Log and refusal
  strings count as changes; only comments and docstrings are ignored.
- **Override recorded.** This replaces the archived rule "Tool-binding
  values must change when gate code changes" for the `gate` and `check`
  classes. Reason: gate code runs live on every `prepare` and `merge`
  against the stored report, and the merge gate runs the check again at the
  landing head, so binding them spent a review pass and added no evidence.
  The archived "never backfill" rule stands.
- `adjudicator_binding` changes for tool files only; the `sd_db` library,
  skills and references stay byte-exact.
- Slices 1 to 3 ship in one pull request. Slice 4 waits for 14 days of data.
  sd:1397 narrows to option E.

2026-09-30: option E built under sd:1397. A moved `verdict`-only binding
replays `sd-review --explain` and keeps a receipt whose `request_sha256`
is unchanged; policy and legacy entries still refuse. Operator ruling
(option A): a move in `FINDING_FILES`, the code that parses or disposes
findings, re-reviews even when the request is unchanged.

Slices 1 to 3 built on `feat/review-binding-1834`. The class map as built is
the four tuples in `bin/sd_ship_bindings.py`, exactly as the design's class
table lists them. Replayed over the 30 days before 2026-09-29 with the built
normalizer and `VERDICT_FILES`: 73 of 162 landings that moved the old
binding leave the new digest unchanged (acceptance floor: 70).

## Problem

`review_binding` in `bin/sd_ship_bindings.py` is one SHA-256 over the bytes
of the 25 files in `REVIEW_TOOL_FILES`, read from the running pack, plus the
repository's review policy and the `external_reviews` machine setting.
`SharedReview.review_inputs` in `bin/sd_ship_review.py` compares the stored
digest with a fresh one and refuses on any difference:
"review tools or repository policy changed after review".

Any byte change to any bound file on pack `main` therefore voids every open
review receipt on every repository. That includes changes that cannot alter
a verdict: a docstring, a comment, a squash-message helper, a lint rule.
sd:1390 turned the deadlock into a re-review, so the cost is now one review
pass per open branch per landing, not a stuck branch.

Observed cost:

- 2026-09-21, system #489: pack #1126 touched `bin/sd-docs-lint`; the
  receipt died eight minutes after `prepare` (sd:1246).
- 2026-09-27: pack #1233 and #1234 landed; system #643 and #645 each spent
  an extra review round on an unchanged diff (sd:1834).
- 2026-09-29: the installed pack was held frozen for a day so open receipts
  would survive.

Measured 2026-09-29 on `origin/main` at `3edab6f6`, first-parent history,
with a script that diffs the bound files per commit:

| Window | Landings that moved the binding | Of which docstring/comment/format only |
|---|---|---|
| since 2026-08-29 | 162 | 11 |
| since 2026-09-15 | 109 | 6 |

sd:1397 asked for this measurement before a redesign. Binding moves are not
rare: about five per day. Most are not semantically empty, so a normalizer
alone does not fix the problem; see the design for the class split.

The refusal also names nothing. sd:1246 found the cause by substituting
blobs until the stored digest reproduced.

The manifest is also incomplete. `sd-review` imports `sd_jev.py` and
`sd_opencode.py`, and `sd-check` imports `sd_gate_slots.py`; none is bound.
`sd_opencode.opencode_answer` parses reviewer output into findings, so a
change there can change a verdict without moving the binding. The
import-walk test in `tests/test_sd_workflow_state.py` walks `sd-ship` only.

## Goals

1. A pack landing that cannot change what a reviewer was asked, who
   answered, or how the answer was judged leaves open receipts valid.
2. A landing that can change any of those still voids them, as today.
3. A refusal names the files and policy entries that moved.
4. Every module the review process loads is bound, and a test proves it.
5. A dirty or mid-branch pack checkout stays honest: the binding describes
   the bytes that run, not a claim about them.

## Requirements

1. Every file the binding reads belongs to exactly one class: `verdict`,
   `gate`, `check` or `policy`. The class map is code, in
   `bin/sd_ship_bindings.py`, and a test fails on an unclassified module.
2. The `verdict` class is the code that runs inside the `sd-review` process,
   plus the argv `sd-ship` builds for it. The `review_binding` digest covers
   `verdict` files by a normalized hash and `policy` entries by raw hash.
3. The normalized hash of a Python file ignores comments, docstrings and
   formatting, and keeps every other string literal. A file that does not
   parse is hashed raw. A `verdict` file that reads `__doc__` fails a test.
4. `gate` and `check` files do not enter the digest. The receipt records
   their raw hashes so a moved receipt can name them, never to refuse.
5. At dispatch the receipt stores a per-entry manifest beside the digest.
6. A moved binding names each changed entry and its class in the refusal and
   in the `review_binding_change` record of the re-review pass.
7. A receipt stored before this change has no manifest. It is treated as
   moved, once, and the refusal says it predates the manifest. No binding is
   backfilled from current files.
8. `adjudicator_binding` uses the same `verdict` normalized hashes in place
   of the raw 25-file hash. It keeps the library file, the adjudicator
   policy files and the skill references raw.
9. A missing bound file still refuses with
   "required review binding file cannot be read"; no class is optional.

## Acceptance criteria

- Each `verdict` member: a semantic edit refuses a stored receipt; a
  docstring-only edit does not. Each `gate` and `check` member: any edit
  leaves the receipt valid. Each `policy` entry: any edit refuses.
- The refusal text for a moved binding contains the changed entry names.
- A receipt state without `binding_manifest` refuses with the "predates"
  wording and re-reviews through the sd:1390 path.
- The import walk covers `sd-ship`, `sd-review` and `sd-check`, and names
  any module that is in no class and not on the exemption list.
- Replaying the measurement script over the 30 days before 2026-09-29 with
  the final class map: at least 70 of 162 landings leave the digest
  unchanged. The design's own estimate is 73.

## Decision record

- The archived no-item acceptance PRD
  (`archive/2026-09/2026-09-17-no-item-review-acceptance/prd.md`, section
  "Stable record identity") says "Tool-binding values must change when gate
  code changes." This PRD supersedes that sentence for `gate` and `check`
  classes, on the ground that gate code runs live on every `prepare` and
  `merge` against the stored report. The same PRD's rule "Missing
  historical tool bindings remain missing. Never backfill them from current
  files." (section "Shared history integration") stands; requirement 7
  follows it.
- Rejected: hashing the shipped repository's `bin/` (sd:1397 records why).
- Rejected: a pack identity claim, commit or version (design, option D).

## Out of scope

- Symbol-level binding inside `bin/sd_lib.py`. Measured as the largest
  remaining lever; deferred to an optional slice (implement, slice 4).
- Re-deriving the reviewer plan and prompt at merge time (design, option E).
- Changing what `sd-review` or the gate validates.
