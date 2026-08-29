---
title: Correct the fleet install-audit path cited in consumer task records
status: done
created: 2026-08-19
branch: task/08-19-fleet-audit-path-in-consumer-records
---
# Correct the fleet install-audit path cited in consumer task records

## Goal

Five consumers refreshed in campaign `v0-71-33-20260819T095717Z` carry a task
PRD acceptance criterion citing `scripts/sd-ai-command-pack-install-audit.py`
as if it were a path inside the consumer, and four of the five repeat it in the
journal testing note for the same session. Every one of those consumers is a
thin install, so no such file exists there. Correct those nine records and
close the source of the mistake in this pack's own documentation. One of
the five, `rwbp-website`, additionally cites a work commit that is not
reachable from its default branch; correct that in the same pass.

## Background

`docs/FLEET_ROLLOUT.md` step 3 instructs the operator to run

```
python3 scripts/sd-ai-command-pack-install-audit.py --repo <repo> ...
```

That relative path is correct, because the step runs **from the pack source
checkout** with `--repo` pointed at the consumer. Step 3 neither says so nor
inherits it: the immediately preceding step 2 states "from this pack checkout"
and the following step 4 states "from the consumer checkout", so step 3 is the
one step in that run of three that leaves its working directory implicit. The
command was transcribed into each consumer's own task record, where the same
relative path resolves to nothing.

GitHub Copilot independently flagged this on both open refresh pull requests
(`platypeeps/rwbp-website#252`, `answerbook/mezmo_benchmark#514`), citing
`.sd-ai-command-pack/installed-targets.txt` as evidence that the path is not an
installed target. The finding is correct.

The installed payload is unaffected: the audit itself ran from the pack source
checkout against each consumer and passed with `31 targets checked` and matching
vouched hashes on all five. This is a defect in the durable record of how the
work was verified, not in the verification.

## Requirements

- Correct the acceptance criterion in the `08-19-sd-ai-command-pack-0-71-33`
  PRD that each consumer keeps under its own `.trellis/tasks/archive/2026-08/`
  directory, so it describes the audit as running from the sd-ai-command-pack
  source checkout with `--repo` pointed at that repository, with no
  consumer-relative path.
- Correct the matching `[OK]` testing note the same way in the four consumers
  whose 0.71.33 journal session carries it; `rwbp-coordinator`'s does not, so
  its correction is PRD-only. Keep the recorded result (`31 targets checked`,
  provenance 0.71.33, vouched hashes match) unchanged — it is accurate.
- Fix `docs/FLEET_ROLLOUT.md` step 3 so the command's working directory is
  explicit, and the next operator cannot transcribe it into a consumer record
  the same way.
- Fix the unreachable work-commit citation in `rwbp-website`. Its journal entry
  and `.trellis/workspace/sdelmas/index.md` both cite
  `7ab13689c95030c58372cbe14f01cee0f06d3481`, the pre-rebase commit: the branch
  was rebased onto the prep fix in `platypeeps/rwbp-website#253`, making
  `662d9500b1445e5762093a926fa513a86a609515` the rebased work commit — the
  pull request's final head was `083c57b2c5c1a11a159bb2b61d3eba477fda5180`
  ("chore: record journal"), two bookkeeping commits later. None of the three is
  reachable from `main`. This repository normally merges with a merge commit, so
  a journal's cited branch commit survives — sessions 89 through 93 all cite
  commits that are ancestors of `main` — but `#252` was squash-merged, and the
  only commit on `main` carrying this work is
  `60d706506ae14db31bb9966581dbaf8911731765`
  ("chore(pack): refresh sd-ai-command-pack to 0.71.33 (#252)"). Cite that.
  Replacing one unreachable hash with the rebased-but-equally-unreachable
  `662d9500` would leave the same defect at a different value.
- Open one pull request per affected repository. These are separate repositories
  with separate review gates; do not attempt a single cross-repo change.
  Acceptance ends at six open, gated pull requests; merging them is the
  post-archive handoff.
- Publish each consumer correction as a plain maintenance pull request: no Trellis
  task in the consumer, no new journal session, and no finish-work bundle. The
  bundle validators reject exactly this change — `planning_archive_mutation`
  refuses any planning bundle touching `.trellis/tasks/archive/`
  (`templates/scripts/sd-ai-command-pack-review-preflight.mjs:2505`) and the
  completion path refuses task changes outside its own archive move (`:2407`) —
  so routing these through finish-work or housekeeping would block them. No
  consumer gate reaches those validators: of the five `candidateChecks` entries
  in `docs/fleet/consumers.json`, only `rwbp-website` runs the shared preflight
  directly, and the other four run scripts local to their own repositories:
  check-review-churn.mjs in rwbp-coordinator, check_review_readiness.sh in
  loadsmith, check-review-preflight.mjs in hoa-manager, and
  check-review-cycle-patterns.py in mezmo_benchmark. None of the four names
  `final-bundle` or `pre-archive`. The shared preflight's own default checks
  carry no archive-mutation rule. (Those four names are deliberately left
  unformatted: they are paths in other repositories, and the documentation
  path-reference check would resolve them against this one. That is the defect
  `08-08-preflight-absent-path-prose` exists to fix, reproduced here.)

## Affected repositories

| Consumer | Checkout | Refresh PR |
| --- | --- | --- |
| rwbp-coordinator | `~/repos/rwbp/rwbp-coordinator` | #246 |
| loadsmith | `~/repos/platypeeps/loadsmith` | #240 |
| hoa-manager | `~/repos/platypeeps/hoa-manager` | #273 |
| rwbp-website | `~/repos/rwbp/rwbp-website` | #252 (also needs the commit-hash fix) |
| mezmo_benchmark | `~/repos/mezmo/mezmo_benchmark` | #514 |

A sixth repository carries a change: `sd-ai-command-pack` itself, whose
`docs/FLEET_ROLLOUT.md` fix lands in this task's own pull request. It is not in
the table because it holds no consumer record to correct — it is the source of
the wording, not a copy of it.

All five refresh pull requests are already merged, so each correction is an
ordinary content change on that repository's default branch, not a
post-archive-review-successor on the refresh branch.

Two per-repository facts, enumerated from the checkouts rather than assumed:

- `rwbp-coordinator`'s 0.71.33 journal session carries no install-audit path,
  so its correction is PRD-only. The other four need both edits.
- Every consumer's 0.71.33 session is currently the newest in its journal, so
  `findHistoricalTrellisJournalSessionEdits` permits the edit. The guard
  compares final state, not operation order: it derives `newestCurrentSession`
  from the post-change file
  (`templates/scripts/sd-ai-command-pack-review-preflight.mjs:5771`) and rejects
  any changed session numbered below it. So a branch that both corrects the
  0.71.33 session and records a newer one fails regardless of the order the two
  edits are made in. The correction branch must add no journal session at all.

## Why this was deferred rather than fixed in the refresh PRs

The two open lanes had already spent the fleet controller's head-republication
budget: `PR_HEAD_REPUBLICATION_STAGES` allows a `pr-head-advanced` rewind only
while `attempt < 2`, and `_next_stage_attempt` only ever increments, so a third
published head would have driven both lanes to terminal `retry-exhausted` for a
documentation-wording change. Fixing two of the five consumers mid-campaign
would also have left the fleet's task records inconsistent. The finding was
answered and its review threads resolved on both pull requests with a
`defer-follow-up` disposition pointing at this task.

## Out of scope

Older refresh records in the same consumers that carry the same wording:
`rwbp-coordinator`'s 0.71.2 refresh and its journal session 19, `loadsmith`'s
`06-29-command-pack-doc-consistency` and its journal session 13,
`hoa-manager`'s `07-18-speed-local-fullcheck-dx`, its `08-03` refresh, and its
journal session 110, and `mezmo_benchmark`'s `07-06-ci-workflow-hardening`.
Those were written while the consumer carried a fat install with the script
present in its own tree — `rwbp-coordinator`'s 0.71.2 record reports "199
targets checked" against the 31 a thin audit reports — so the relative path
resolved when the record was written. Rewriting an accurate historical record
to match today's layout is a different change from correcting an inaccurate
one, and this task is the latter.

`mezmo_benchmark`'s own 0.71.33 journal citation, `77c71a9b76ff36e32b6e0d0eac31342452dda884`,
is likewise unreachable from its `main` — that repository squash-merges, so the
branch commit is orphaned and the surviving commit is
`9ba71a21371b667deeebf3b855c37cadf860fb1a`. It is still out of scope, because
there it is not an anomaly: nine of the nineteen commits its ten most recent
sessions cite are orphaned the same way, so correcting one entry would single
out a single row in a journal where unreachable citations are routine.
`rwbp-website` is the opposite case — it merges with merge commits, sessions 89
through 93 all cite commits reachable from `main`, and session 94 is the lone
outlier — which is why only that one is corrected here. A fleet-wide policy for
citing commits in squash-merged repositories is a separate task.

## Acceptance Criteria

- [x] All five `08-19-sd-ai-command-pack-0-71-33` PRD criteria and all four
  0.71.33 journal testing notes describe the audit as running from the
  sd-ai-command-pack source checkout against that consumer. Verified positively,
  by reading each of the nine records and confirming two things in every one —
  it names the source checkout as the working directory, and it does not present
  `scripts/sd-ai-command-pack-install-audit.py` as a consumer-relative path —
  plus the result evidence each record actually carries today, which differs by
  kind and must not be enriched to match: the five PRDs keep their
  expected-platform count and provenance `0.71.33`, and the four journal notes
  keep `31 targets checked`, provenance `0.71.33`, and matching vouched hashes.
  A bare zero-hit grep is the wrong check twice over: deleting the evidence
  outright would pass it, and a correctly qualified command that names the
  script would fail it. Scoped to the 0.71.33 records — every consumer
  also carries the same wording in older refresh records written while it was a
  fat install, where the relative path did resolve, and those are out of scope.
- [x] `docs/FLEET_ROLLOUT.md` step 3 states the working directory the command
  runs from.
- [x] `rwbp-website` cites `60d706506ae14db31bb9966581dbaf8911731765` as the
  0.71.33 refresh commit in both its journal entry and its workspace index, with
  no remaining reference to `7ab13689` or `662d9500`. Verified by
  `git merge-base --is-ancestor <cited hash> main` succeeding for the hash the
  records name — the check that would have caught the original error and both
  proposed replacements.
- [x] Six pull requests exist, one per repository: the five consumers and this
  pack. Each is recorded here with its URL and the head commit it carries. They
  are intentionally independent — no consumer correction depends on another, and
  none depends on the `docs/FLEET_ROLLOUT.md` fix — so a repository that fails
  pauses only itself.
- [x] Each affected repository's own gate passes on the change, run in that
  repository. Merging those pull requests is the post-archive handoff, not an
  acceptance criterion.

### Verification evidence

Run 2026-08-19 against the six pull-request heads, reading each record with
`git show <branch>:<path>` rather than the working tree — the consumer
checkouts sit on an unrelated branch, and checking them in place is how an
earlier pass produced four false failures.

- Criterion 1: nine of nine records `PASS` both halves — each names the source
  checkout and passes `--repo`, and each retains the evidence it already
  carried (five PRDs: expected platform plus provenance `0.71.33`; four journal
  notes: `31 targets checked`, provenance `0.71.33`, `vouched file hashes
  match`). Each journal also carries an older fat-era line
  (`199 targets checked, provenance 0.71.4`) that the scoping clause excludes.
- Criterion 2: step 3 reads "command from this pack checkout, like step 2 and
  unlike step 4".
- Criterion 3: zero remaining references to `7ab13689` or `662d9500`, and
  `git merge-base --is-ancestor 60d706506ae14db31bb9966581dbaf8911731765 origin/main`
  exits 0.
- Criterion 4: six pull requests, each recorded above with its URL and head.
- Criterion 5: every gate run in its own repository and quoted in that
  repository's pull request. Copilot reviewed all six heads clean with zero
  unresolved threads.

## The archived-record decision

Operator decision, 2026-08-19: correct the archived PRDs in place.

`.trellis/spec/tooling/bookkeeping-validator.md:55-63` states that nothing may
legally mutate `.trellis/tasks/archive/**` again, and says the
`post-archive-review-successor` mechanism relies on that — it calls
live-worktree readers inside what is conceptually a historical proof, and gets
away with it only because archived content is guaranteed static. Editing five
consumers' archived PRDs contradicts that contract, and this task does it
knowingly rather than by oversight.

What bounds the risk: no code compares an archived directory's live content
against its content at the archiving ref. `validateBookkeepingTaskDirectory`
reads the live `prd.md` (`templates/scripts/sd-ai-command-pack-review-preflight.mjs:977`)
and validates its structure and content quality. So the concrete failure mode is
narrow — a corrected PRD that violates a content rule would block a later
finish-work in that consumer — and it is directly testable.

Mitigation, required per consumer: after editing, run that repository's own gate
and confirm it passes on the edited archived file. A consumer whose gate fails
on the correction stops there and is reported, not forced.

## Delivery

Six pull requests, one per affected repository, each gated in its own
repository. Heads are the heads Copilot reviewed clean, after the two rounds of
review feedback described below. `rwbp-coordinator` carries no journal note, so
the second round left it untouched at the head it was already reviewed at.

| Repository | Pull request | Head | Gate |
| --- | --- | --- | --- |
| loadsmith | platypeeps/loadsmith#241 | `88a8d41` | `check_review_readiness.sh --all --skip-build`: passed, 0 warnings |
| hoa-manager | platypeeps/hoa-manager#274 | `a4ca49a` | `check-review-preflight.mjs`: passed, 1 tooling-scope warning addressed in the PR body |
| rwbp-coordinator | platypeeps/rwbp-coordinator#247 | `170d9ad` | `check-review-churn.mjs`: passed |
| rwbp-website | platypeeps/rwbp-website#254 | `d39d640` | `check-review-preflight.mjs` and `ops-check.mjs`: passed |
| mezmo_benchmark | answerbook/mezmo_benchmark#515 | `9b36a53` | `check-review-cycle-patterns.py --base HEAD --include-working-tree`: passed |
| sd-ai-command-pack | platypeeps/sd-ai-command-pack#516 | `972b389` (the source fix; later commits on this branch are this task's own records, so this row's head advances with them) | review preflight: 0 failures, 0 warnings |

### The follow-up wording round

The first four consumer corrections said *where* the audit runs but dropped the
command itself, leaving a criterion that named no invocation at all. Copilot
raised that on loadsmith#241; the same wording was then applied to all four so
the fleet records stay uniform, and mezmo_benchmark was written that way from
the start. Each record now names the working directory and the command
together:

> The sd-ai-command-pack install audit passes for ... It runs from the
> sd-ai-command-pack source checkout, not from this repository:
> `python3 scripts/sd-ai-command-pack-install-audit.py --repo <this repository>
> --expected-platform ...`.

### The placeholder-rendering round

The journal notes carried the invocation as plain prose, leaving the
`<this repository>` placeholder unescaped. CommonMark parses that as a raw HTML
open tag — `this` is a legal tag name and `repository` a legal attribute name —
so a renderer swallows it and shows a command missing its `--repo` argument.
Copilot raised it on answerbook/mezmo_benchmark#515; all four journal notes
carried the same defect and all four now wrap the whole invocation in an inline
code span, matching how the PRD criteria already carried it.

Copilot also asked, on this pack's own pull request, that
`docs/FLEET_ROLLOUT.md` step 3 stop wrapping its inline code span across a line
break. That one was rebutted rather than applied: CommonMark
[§6.1](https://spec.commonmark.org/0.31.2/#code-spans) specifies that line
endings inside a code span are converted to spaces, and eight such spans already
exist in `docs/` and render correctly, the oldest since `ba0bd20b`.

### mezmo_benchmark was delivered from a rebuilt branch

Its first branch was cut without re-asserting `main`, while a concurrent
Trellis `0.6.7 -> 0.6.16-sd.0` update was running in that same checkout. The
branch therefore came off `chore/trellis-0.6.16-sd.0` carrying that update's
uncommitted files, and the concurrent process then committed everything in the
working tree — its 124 files plus this task's 2 — as
`1b6878c chore: update Trellis 0.6.7 -> 0.6.16-sd.0` onto it.

Nothing was pushed and nothing was lost. The contaminated branch was renamed to
`chore/trellis-0.6.16-sd.0-recovered`, which keeps `1b6878c` reachable, and a
fresh `chore/fix-install-audit-path-citation` was cut from `main` with the
correction re-applied from the same script the other four used. The delivered
diff is exactly two files and two lines. No reset, stash, clean, or force-push
was used at any point, because that commit holds work that exists nowhere else.

## Rollback

Each pull request is independently revertible, and a revert is an ordinary
forward commit: never a history rewrite, because the records being corrected sit
in files whose history other guards treat as append-only. A consumer that fails
its gate stays unmerged and is tracked as partial completion; consumers already
corrected and merged stay merged rather than being rolled back to keep the fleet
uniform, since each record is accurate or inaccurate on its own.
