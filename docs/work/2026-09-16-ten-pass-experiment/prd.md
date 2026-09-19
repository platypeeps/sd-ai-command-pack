---
title: The ten-pass experiment on the code review point has a pass-log shape before its first pass
created: 2026-09-16
item: sd:777
---

# PRD — ten-pass-experiment

## Problem

sd:777 carries sd:10 criterion 7, the ten-pass forward experiment on the code
review point. The criterion stands unchanged at
`2026-09-05-the-pack-runs-a-team-process-for-one-person/prd.md:1352-1358`:
the other vendor reviews the next ten code pull requests, each pass logs
accepted against rejected findings with severities and cost, and a recorded
decision keeps or removes the point. `WORKFLOW.md:139-141` still describes
the experiment. No pass log, no report and no decision exist, and nothing
says what one pass note looks like. Ten passes written ten ways cannot be
summed. The `cost` table that would supply each pass's cost held 0 rows on
2026-09-16, and 0 `run` rows on 2026-09-17, so the cost field needs a query
that is agreed before the first pass.

## Requirements

1. One pass is one plain-text note on sd:777 with the header and the eight
   fields below, in that order, so the report is a sum over ten notes of one
   shape. Each accepted finding's severity is on the note, not only the
   highest, because criterion 7 asks for each.
2. The cost field is copied from the one query below, and the `session`
   field names the row it was copied from. When no row exists, the field is
   the owner's estimate, marked `estimate`, with the reason the runner was
   not used; an unmarked number is a copied one, and a note whose `session`
   is `none` must use the `estimate` form.
3. The passes, the report and the decision are OWNER-ONLY. No lane runs a
   pass, writes a note, or decides. This item's pages fix the shape only.

## Acceptance criteria

- [ ] Ten code PRs have a logged other-vendor pass each, the report is a note
      on this item, and a decision note keeps or removes the code review point.
      A grep of bin/ and skills/ for a percentage that disables a review point
      still returns nothing.
- [ ] Every one of the ten notes carries a cost in USD copied from the query
      by its `session`, or the owner's estimate marked `estimate` with the
      reason the runner was not used. A note with neither is not a logged
      pass and does not count toward ten.

## Pass note template

One note per pass uses a `pass N of 10` header and eight required fields.
The eighth, `reviewed sha`, arrived with the post-merge amendment below, which
is why the count reads eight and not the seven this section carried until
2026-09-18; this block is the only copy of the shape, and the amendment cites
it rather than restating it.
A replacement adds `supersedes note: <id>` directly after the header.
`PR`, `head sha`, `reviewed sha` and `reviewer
entry` are never `none`; a note missing one of them is not a logged pass and
does not count toward ten, whatever its cost field says. `none` is allowed
only where a field's own line says so: `session` when no runner row exists,
the accepted severities and the highest severity when no finding was
accepted, and the cost field never.
Severity values are the review schema's, `source:bin/sd-review::SEVERITIES`:
`high`, `medium`, `low`, `unspecified`; `none` means no finding was accepted.

    pass N of 10
    PR: #<number>
    head sha: <40 hex, the pull request's head, the sha Copilot reviewed>
    reviewed sha: <40 hex, the squash commit this pass ran against; never none>
    reviewer entry: <registry name, codex for every pass of this experiment>
    session: <the runner session identifier, the value of cost.pass, the key that selects the cost row; or none when no runner row exists>
    findings accepted / rejected: <A> / <R>; accepted: <one entry per accepted finding, severity then its destination, e.g. high -> sd:1099, low -> 4f2a...; or none when A is 0>
    highest severity accepted: <high|medium|low|unspecified|none>
    cost in USD: <usd from the query row whose pass equals session; or estimate <usd>, and why the runner was not used; the estimate form is required when session is none>

## Cost query

Read-only. The query joins `cost` to `assignment` on `a.id = c.assignment`,
the assignment row the reviewer session ran under (the `run` row that
`sd_db/runner.py` writes: one session is one pass). It does not join by
`pass`: `cost.pass` is the reviewer session's identifier, selected and
ordered only, and the note's `session` field is what matches it. Run it as
`sqlite3 -readonly -header ~/.local/share/sd/sd.db` and copy `usd` from the
row whose `pass` equals the note's `session`. The note carries that value so
a later reader selects the same row.

    SELECT c.pass, c.timestamp, c.provider, c.source, a.item, a.role, a.status,
           c.tokens_in, c.tokens_out, c.usd
    FROM cost AS c
    JOIN assignment AS a ON a.id = c.assignment
    WHERE a.role = 'reviewer' AND c.source = 'run'
    ORDER BY c.pass, c.timestamp;

Measured 2026-09-16 against the live store, read-only: 0 rows. A pass whose
review ran outside the runner writes no `cost` row; its note carries the
owner's estimate marked as one, with the reason the runner was not used, and
the report keeps estimated and copied costs apart, with no combined total
over the ten.

## References

- sd:777 body, and sd:10 criterion 7 as cited above.
- `skills/sd-review/SKILL.md:121-123`: MiniMax and Kimi are under recovery,
  and a single-provider review naming the registry entry whose `reader` is
  `claude-json` is the temporary mitigation. `claude-json` is a reader, not a
  reviewer entry: the entry is `claude` (`providers.yaml`, the `providers`
  map), and that is the name a note's `reviewer entry` field would take.
  Such a review is not a pass of this experiment: the owner named Codex the
  other vendor on 2026-09-17 (`design.md`, Decisions), so only a `codex`
  review counts.

## Log

- 2026-09-16 created. Two of the item body's citations moved on main: the
  criterion 7 row is now at
  `2026-09-05-the-pack-runs-a-team-process-for-one-person/implement.md:1850`
  and the 2026-09-07 log entry at
  `2026-09-05-the-pack-runs-a-team-process-for-one-person/prd.md:5167-5198`;
  the claims hold at both.
- 2026-09-17 lane, sd:777 note 2602's six page findings from #991's
  verification review at 94aab556: `PR`, `head sha` and `reviewer entry` are
  mandatory; the `session` line names the row it selects; the cost query
  prose says the join is on `assignment` and the match is by `pass`;
  `claude-json` is a reader and the entry is `claude`; `design.md`'s reversal
  clause gained a re-record rule; `implement.md` step 4 keeps each cost's
  marker and forbids a combined total. Step 1 ticked (#991 merged as
  e2810a6f). Step 6 re-run at ea32e76a: 34 lines, was 33 at 2eafa78b, none
  disables a review point; the drift is itemised at `implement.md` step 6.
  Cost query re-run 2026-09-17, read-only: 0 rows; the `cost` table holds
  three `meter` rows and no `run` row. Planning review, host lane once: one
  blocking finding, the accepted-severities sub-list had no value at zero
  accepted, fixed on the template line; ten non-blocking, all addressed.
  Copilot round on #1023 at dcc6a954, two findings folded: step 3 names
  the `estimate` form, and the Problem's row count is dated. Verification
  round at c012a736, one finding folded: the re-record rule names the
  counted set, current notes only, a superseded note excluded by id.
- 2026-09-17 owner: the other vendor is Codex. `design.md` records it as a
  decision and drops the risk that summed Codex with a recovered vendor;
  implement step 2's note on sd:777 is still to be written.
- 2026-09-17 owner: the decision note naming Codex is on sd:777, so the
  note the previous entry called still to be written exists; implement step
  2 is ticked.
- 2026-09-18 owner, then lane: the pass runs after its pull request merges.
  The owner asked for a more direct comparison and for the review not to need
  triggering. The lane put up two routes and the owner took the second: the
  pack's code review point stays *code, before merge*, its table row unchanged
  in `WORKFLOW.md` and `.claude/rules/sd-planning-adversarial-review.md`, and
  this experiment's pass becomes a post-merge measurement. `WORKFLOW.md`'s
  experiment paragraph, which equated the point with the experiment, is
  reworded; nothing else there changed and sd:10 criterion 7 was not touched.
  The amendment section above settles `accepted` post-merge, names the lost
  "would this have blocked the merge" signal and both biases as costs, adds a
  `reviewed sha` field, and records that no merge-time dispatch exists, so the
  trigger is new work. Requirement 3 needs one clarifying sentence, quoted
  there for the owner; it is not applied. No criterion is ticked.

## Amendment — the post-merge position (2026-09-18)

The owner asked, 2026-09-18: "for 777, can we run the reviews on merged
branches? That way we get a more direct comparison and I don't have to trigger
the review". Two motives: a more direct comparison, and no manual trigger. The
owner ruled the same day on how to reconcile them with the pack's review point,
and this section is that ruling's page. Nothing here ticks a criterion; the
passes, the report and the decision stay OWNER-ONLY.

### What the ruling had to resolve

`WORKFLOW.md` said the code point *is* the experiment: "The code point is an
experiment: over ten pull requests, findings accepted against findings rejected
with each accepted finding's severity, and cost logged per pass." Under that
wording the ten Codex passes were not a measurement taken beside the review
point, they were the point in operation, and moving them after the merge would
have moved the point itself. Fourteen lines above, `WORKFLOW.md:125` and
`.claude/rules/sd-planning-adversarial-review.md:14` carry the same row byte for
byte:

    | Development | Code, before merge | Defects a second reader finds | 1, plus one verification of the fix |

That row is read by string, not only by a reader:
`source:tests/test_sd_ship_skill.py::code_row_cap` scans the rule file for a
`| Development |` line containing `Code, before merge` and raises
`AssertionError` when none is found. `skills/sd-review/SKILL.md:40-43` glosses
the same point as `--scope branch` "before a push", and
`docs/lane-brief.md:136-139` cites the row by name to keep the capped pack
review apart from the advisory Copilot round.

The owner's ruling: the pack's code review point stays *code, before merge*,
that row unchanged in both copies and every string keyed on it untouched, and
the experiment's Codex pass becomes a post-merge measurement that observes the
point rather than being it. The one edit that requires is `WORKFLOW.md`'s
experiment paragraph, which equated the two; this item's change reworded it and
nothing else there. sd:10 criterion 7 is untouched and stays literally true:
the other vendor still reviews "the next ten code pull requests", and only the
moment of the review moves.

### The cost the ruling accepts

A post-merge pass cannot show whether a finding would have changed the outcome
before the merge. Pre-merge, accepting a finding had a mechanism behind it: the
merge waited, and the acceptance was visible in the landed diff. Post-merge
nothing waits, so the "would this have blocked the merge" signal is gone and
`source:bin/sd-review::dispose`'s `blocking` and `advisory` labels stop
corresponding to any outcome. The experiment's original claim is weaker for it:
it measures what a second vendor finds, not what a second vendor would have
stopped. The owner chose this knowingly, and the report states it rather than
presenting its ratio as if a merge had been at stake.

### What `accepted` means after the merge

The numerator carries the whole ratio, and post-merge no change to a pull
request evidences it, so the word needs a test of its own:

> A finding is **accepted** when the owner judges that, had it arrived before
> the merge, the owner would have asked for the change. Everything else is
> rejected.

That is a judgement about the finding's truth and materiality, not about
scheduling, so a real defect the owner decides not to fix now is still accepted.
What happened next is recorded separately and does not gate acceptance: each
accepted finding's entry on the note carries a destination, one of a followup
row `sd:<n>`, a 40-hex commit sha that fixes it, or `wontfix`. A finding with no
destination is not an accepted finding and does not count toward `A`. That is
what keeps the numerator auditable: every accepted finding on a note names a
severity and a place it went, and a later reader can check both.

### Bias, in both directions

- **Against the second vendor.** It reviews a diff Copilot already reviewed
  *and* the owner already fixed. The defects Copilot caught are gone from the
  merged tree, so the vendor is given partly cleaned code. Its raw finding count
  falls, and its accepted ratio moves in an unknown direction: depressed if only
  hard findings remain, inflated if the survivors are the real ones. Either way
  the ratio is not comparable to a pre-merge one.
- **Toward rejecting.** Accepting now costs the owner a followup row or a second
  pull request. Pre-merge it cost an edit to a branch that was open anyway. The
  cheaper disposition has become `rejected`.
- **For the comparison.** The merged commit is immutable, so the ten passes sit
  on ten stable subjects; pre-merge the head sha moves under a review. And
  Copilot's dispositions are already recorded per pull request, so a per-pull-
  request comparison is available that the pre-merge ordering does not give.

Net: more direct on the *subject* reviewed, less direct on the *consequence*,
and contaminated by Copilot having been acted on first. The report says it
measures a second vendor's findings on already-reviewed, already-fixed code, and
does not present the ratio as a clean vendor-against-vendor figure.

### The trigger, and that it does not exist

Nothing dispatches a review at merge time today.
`.github/workflows/sd-review-route.yml:14-16` fires on `pull_request` types
`opened`, `synchronize`, `reopened` and `ready_for_review` only. It holds
`permissions: contents: read`, and its own header says it "requests no
reviewer, posts no comment, sets no label" and that "Asking a remote reviewer
for a review is a separate change with its own decision record." No workflow in
`.github/workflows/` fires on `pull_request: closed`, and nothing ties a push to
the default branch to a review. The owner's "I don't have to trigger the review"
is new work, not configuration, and this item builds none of it.

The diff a post-merge pass would be given already resolves, so the new work is
the dispatch and nothing else. `source:bin/sd-review::resolve_subject` accepts
`--scope branch --base <40 hex>` when the base is an exact ancestor of `HEAD`,
and every merge on this repository is a squash with a single parent (`e5f17b04`'s
parent is `99ca6fde`), so the squash commit's first parent is that base and
`<parent>..<squash>` is exactly the change the pull request landed.

Two shapes for the dispatch, neither built here:

1. A workflow on `pull_request: closed` gated on a merged check, running
   `sd-review --provider codex --scope branch --base <parent sha>`. It needs
   `OPENAI_API_KEY` in CI and somewhere to put the output, so it expands a lane
   that today holds `contents: read` and deliberately asks for nothing.
2. A step in the merge lane's own checkout, after the prescribed
   `gh pr merge --squash --match-head-commit`, running the same command with the
   owner's own key and writing nothing to GitHub.

Recommended: 2. It adds no secret, posts nothing, and leaves the advisory
workflow's contract intact. Either way it is new work, and this item's
`implement.md` records that the owner cancelled external provider reviews, so no
dispatch is built or run before that is reversed in writing.

One side effect worth having: a dispatch through `sd-review` runs under the
runner, which writes the `run` row the cost query needs. The `cost` table held
0 `run` rows on 2026-09-16 and on 2026-09-17, so the trigger is also the most
likely way the cost field becomes a copied number rather than an estimate.

### The template, field by field, after the merge

- `PR: #<number>` — satisfiable, unchanged, and still the key that joins a pass
  to the Copilot round on the same pull request.
- `head sha: <40 hex>` — satisfiable but ambiguous, because two shas now exist:
  the pull request's head, which Copilot reviewed, and the squash commit, which
  the second vendor reviews. `head sha` keeps its present meaning, the pull
  request's head sha, which survives the branch's deletion on the pull request
  record; and an eighth field `reviewed sha: <40 hex>` names the squash commit
  the pass ran against, never `none`, so a later reader reproduces the diff as
  `<reviewed sha>^..<reviewed sha>`. Requirement 1 and the template section now
  read eight fields, and the block under `## Pass note template` carries the
  eighth; this amendment states the reason and does not restate the shape. No
  pass note exists yet, so `design.md`'s re-record rule has nothing to re-record
  and the eighth field costs nothing today.
- `reviewer entry: codex` — satisfiable, unchanged. Confirmed against the
  registry rather than assumed: `providers.yaml`'s `roles` map lists
  `reviewer: [codex, claude, minimax, kimi, baseten]`, so `codex` is first in
  the reviewer chain and is the other vendor when Claude authors.
- `session` — satisfiable, and likelier to name a real row than before, per the
  trigger above.
- `findings accepted / rejected` and `accepted:` — satisfiable under the
  definition above, with each accepted finding's destination added.
- `highest severity accepted` — satisfiable, unchanged.
- `cost in USD` — satisfiable, unchanged.

The amended note shape lives in one place, the block under
`## Pass note template` above, which now carries the eighth field and the
destinations. A second copy here would drift from it, so there is none.

### Requirement 3

Requirement 3 says the passes are OWNER-ONLY and that "No lane runs a pass,
writes a note, or decides." Read literally, an automatic dispatch runs the
reviewer, and running the reviewer looks like running a pass. It needs amending,
as a clarification and not a reversal, because the ambiguity will otherwise be
read as a violation by whoever builds the trigger. The distinction: a pass is
the owner's disposition and note, not the reviewer's output. The template
already works this way, since a note missing a mandatory field "is not a logged
pass". The sentence the owner would add to Requirement 3:

> A mechanical dispatch of the reviewer entry is not running a pass. The pass is
> the owner reading the output, dispositioning each finding, and writing the
> note; a dispatch no one dispositions has produced no pass.

### Not worked examples

Today's Copilot round on #1062 and the `minimax` round on the research-opening
branch are not candidate passes and must not be logged as ones: the 2026-09-17
decision fixes the other vendor as the `codex` entry, and a pass whose
`reviewer entry` names any other entry is not a pass of this experiment. They
illustrate the arithmetic only. Verified on #1062 (head sha
`5314166bd7f5e8152fd5ccd44bd852957b71410e`, squash-merged as `e5f17b04`):
Copilot posted three inline threads, one High, one Medium, one Low, and named a
fourth finding in its summary table alone. The Medium asked for a `.git`-name
guard before `source:hooks/pre-commit::main_checkout` takes `common.parent`, and
the merged code on main still has no such guard, so a finding can be real, still
open, and dispositioned only after the merge. The High, a claimed
`FileExistsError` from a duplicate `.venv` symlink, was refuted, which is what a
rejected finding at a high severity looks like.
