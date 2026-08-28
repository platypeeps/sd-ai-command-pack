# Planning adversarial review — 08-27-graphql-bot-login-thread-matching

## Trigger

`prd.md` created this run (baseline: scaffold only, `## Requirements` and
`## Acceptance Criteria` both `TBD`). `design.md` and `implement.md` do not
exist — lightweight task, PRD-only. Trigger applies to the `prd.md` write.

## Lanes

Host lane only. This repository defines no additional lane, so no second-lane
line is reported.

## Verified against source

Claims checked in `scripts/sd-ai-command-pack-review.py` rather than accepted
from the draft:

| Claim | Evidence | Verdict |
| --- | --- | --- |
| `authors` built from `receipt.backend.reviewAuthors`, lowercased | `_collect_observation`, `str(item).lower()` | holds |
| Threads fetched over GraphQL | `_collect_review_threads`, `reviewThreads(first:100,…)` query | holds |
| Thread kept only on author match | `if matching or not authors:` | holds |
| `"total"` is the kept count | `"total": len(threads)` | holds |
| `reviews` fetched over REST | `_paginated_rest_array`, `pulls/{n}/reviews?per_page=100` | holds |
| `materialized` satisfied by the check-run disjunct | `("check" in channels and bool(matching_checks))` | holds |
| GraphQL/REST spelling differs | live query, `copilot-pull-request-reviewer (Bot)` vs `copilot-pull-request-reviewer[bot]` | holds |
| Four collector copies, one commit | `git show --stat ecbfb0d1` | holds |
| PR-Agent `reviewAuthors` is `github-actions[bot]` | sd-review.yml run inputs | holds |

## Concern ledger

**C-1 — R2 was specified against a signal that does not exist. Blocking.**

The draft R2 said "a review whose body advertises inline comments, alongside
`reviewThreads.total == 0`". Verification: the REST review object carries no
comment count —

```
$ gh api repos/platypeeps/sd-github-review/pulls/157/reviews --jq '.[-1]|keys'
["_links","author_association","body","commit_id","html_url","id","node_id",
 "pull_request_url","state","submitted_at","user"]
```

So the only way to read "advertises N comments" is to parse Copilot's English
prose out of `body`. That is backend-specific, unversioned, and rots silently
the first time the wording changes — a detector for a silent-failure bug that
itself fails silently.

Disposition: **addressed**. R2 restated against a structural signal already
present inside `_collect_review_threads` — raw GraphQL rows fetched versus rows
kept. The contradiction is "every row discarded by the author filter while a
review by those same authors matched over REST", which needs no text parsing
and is not tied to any backend's phrasing. Owning artifact: `prd.md`, R2 and
acceptance criteria 3–4.

**C-2 — Verification named the wrong test runner. Blocking.**

The draft named `python3 -m pytest`. The repository runs `unittest`: `make
test` drives `.github/scripts/run-tests.sh` and then greps `unittest-output.log`
for `skipped=[1-9]`. A verification step that cannot execute is not a check.

Disposition: **addressed**. Verification section rewritten to
`python3 -m unittest tests.test_review_controller -k …` for the red/green proof
and `make test` for the gate, noting that the gate also fails on skips and
enforces shipped-script coverage/docs/mode checks that a new helper must
satisfy. Owning artifact: `prd.md`, Verification.

**C-3 — "compares verbatim" overstated. Non-blocking.**

`_matching_author` case-folds both sides; it is exact only after lowering.
Left uncorrected, R1's "matching stays case-insensitive, as it is today" would
read as contradicting the cause paragraph.

Disposition: **addressed**. Cause paragraph now says case-folds both sides but
is otherwise exact. Owning artifact: `prd.md`, Cause.

**C-4 — R2 could fire on a genuinely empty thread set. Blocking if unfixed.**

A PR with no review threads at all also has zero kept rows. If R2 keys on
"kept == 0" alone it would refuse `clean` on every clean PR, which is worse
than the bug.

Disposition: **addressed**. R2 keys on *raw rows returned AND all discarded*,
and acceptance criterion 5 now pins the negative case: a query returning no
rows still reports `clean`. Owning artifact: `prd.md`, R2 and criterion 5.

**C-5 — PR-Agent blast radius asserted without evidence. Non-blocking.**

`github-actions[bot]` has the same suffix shape, so the same drop is possible,
but no dropped PR-Agent finding has been observed. PR-Agent declares
`findingChannels: ["conversation-comment"]`, and conversation comments are
matched by the same `_matching_author` against REST-sourced `issue_comments` —
where the login *does* carry `[bot]`, so that path is probably unaffected.

Disposition: **parked**. Trigger: any PR-Agent lane configured with
`inline-comment` in its channels. Owner: follow-up task. The PRD states this as
not verified rather than asserting impact, and the non-goals exclude the fleet
audit.

## Cross-artifact sweep

Values appearing in more than one place, each enumerated and confirmed
consistent:

- issue `#159`, PR `#157`, head `45f892b` — `prd.md` only; match the filed
  issue and the merged branch.
- `ecbfb0d1` and the four collector paths — `prd.md` acceptance criterion 6;
  confirmed against `git show --stat`.
- task title and description in `task.json` versus the PRD goal — consistent;
  both name the `[bot]` suffix mismatch as the cause.
- "three unresolved threads" — `prd.md` Why-it-matters; matches the GraphQL
  output recorded in issue #159.

No stale copies found.

## Round 2

Reran the host review against the updated `prd.md`. C-1's remediation
introduced C-4 (the empty-set false positive), which round 2 caught and
criterion 5 now pins — the expected shape. No further defects found in the
corrected text; no figure changed in one artifact and left standing in another.

Two remediation rounds used of the permitted two. Not exhausted.

## Status

- Changed artifacts: `prd.md` (new).
- Host review: completed, two rounds.
- C-1 addressed, C-2 addressed, C-3 addressed, C-4 addressed, C-5 parked
  (non-blocking).
- No unresolved blocker.

**Implementation is unblocked.**
