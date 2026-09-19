# Design — ten-pass-experiment

## Approach

The pass log is ten notes on sd:777, one shape, plain text, and the report
is one more note that sums them. Nothing new is stored: the store already
has `note` rows, the `cost` table already keys a session's cost by `pass`,
and the PR and head sha are what the note needs to rejoin them later.

Rejected: a `pass_log` table or a file under `docs/work/`. A table needs a
migration in `local-sd-db` for ten rows, and a file in this repository would
put a decision the owner makes into a pull request a lane opens. The item
is the ledger; sd:10's other criteria settled there too.

## Decisions

- 2026-09-16, lane: the header, the seven fields, their order, and the
  query are fixed here. Reversed by the first pass that cannot fill one,
  under the re-record rule below.
- 2026-09-17, lane: the re-record rule. A reversal is a decision note the
  owner writes on sd:777 that names the field, the new shape, and the pass
  that forced it; `PR`, `head sha` and `reviewer entry` are not reversible,
  and a pass that lacks one is not a pass. A lane then lands the new
  template in `prd.md`, and every pass note already recorded is re-recorded
  in the new shape, as a new note that names the note it supersedes, before
  the next pass runs, so the ten notes the report sums are one shape and
  main states it. The counted set is the current notes only.
  A replacement keeps the `pass N of 10` header.
  It adds `supersedes note: <id>` after that header.
  A superseded note is not counted.
  A note made between the reversal and re-recording is not a pass.
- 2026-09-17, owner: the other vendor is Codex (OpenAI), the `codex` entry,
  first in the reviewer chain at `WORKFLOW.md:278`. All ten passes are Codex
  passes, so the ratio the report gives is one reviewer's: a pass whose
  `reviewer entry` names any other entry is not a pass of this experiment.

## Risks

- The `cost` table holds no `run` row (0 on 2026-09-16 and on 2026-09-17;
  three `meter` rows arrived in between). If the reviewer entry runs outside the
  runner, the cost field is an owner estimate on every note and the report's
  cost per pass is estimated, not measured. Accepted; the note marks it
  `estimate`, and the report never sums an estimate with a copied cost and
  carries no combined total over the ten.
- The Copilot round on a pull request is advisory and outside every cap; it
  is not the other-vendor pass and must not be logged as one.
- Codex can be unavailable for a pull request, and the chain would then fall
  through to another entry. That review is not a pass; the pull request is
  not one of the ten, and the next code pull request takes its place.

## Decisions (continued)

- 2026-09-18, owner: the pass runs after the merge, not before it. The owner
  asked for a more direct comparison and for the review not to need triggering.
  Route taken, of the two the lane put up: the pack's code review point stays
  *code, before merge*, its table row unchanged in both copies and every string
  keyed on its Point cell untouched, and this experiment's pass becomes a
  post-merge measurement that observes the point instead of being it. Rejected:
  rewording the Point cell, which would have moved the point for every future
  review and not only for these ten, and would have broken
  `source:tests/test_sd_ship_skill.py::code_row_cap`,
  `skills/sd-review/SKILL.md:40-43` and `docs/lane-brief.md:136-139`. The one
  edit the chosen route needs is `WORKFLOW.md`'s experiment paragraph, which
  equated the point with the experiment; this item reworded that paragraph and
  nothing else there. sd:10 criterion 7 is untouched, and stays literally true:
  the other vendor still reviews the next ten code pull requests, and only the
  moment of the review moves.
- 2026-09-18, owner: `accepted` post-merge is defined by a counterfactual, not
  by a change to a pull request. A finding is accepted when the owner judges
  that, had it arrived before the merge, the owner would have asked for the
  change. Each accepted finding's entry on the note carries a destination, a
  followup row `sd:<n>`, a 40-hex commit sha, or `wontfix`; a finding with no
  destination does not count toward `A`. The destination records what happened
  and does not gate acceptance, so a real defect the owner defers is still
  accepted.
- 2026-09-18, owner: the note gains an eighth field, `reviewed sha`, the squash
  commit the pass ran against, never `none`. `head sha` keeps its meaning, the
  pull request's head, which is the sha Copilot reviewed and the one that
  survives the branch's deletion on the pull request record. No pass note exists
  yet, so the re-record rule above has nothing to re-record and the eighth field
  costs nothing today.

## Approach (continued) — where the diff comes from

Nothing new is needed to resolve a post-merge subject.
`source:bin/sd-review::resolve_subject` accepts `--scope branch --base <40 hex>`
when the base is an exact ancestor of `HEAD`, and every merge on this repository
is a squash with a single parent, so the squash commit's first parent is the
base and `<parent>..<squash>` is exactly the change the pull request landed.
That diff is arguably tighter than the pre-merge one: `merge-base..head` can
omit changes that arrived on the default branch under the review, while the
squash commit's parent is the default branch at the moment the change landed.

## Risks (continued)

- The "would this have blocked the merge" signal is gone. Post-merge nothing
  waits, so `source:bin/sd-review::dispose`'s `blocking` and `advisory` labels
  correspond to no outcome and the acceptance test is a stated judgement with no
  mechanism confirming it. Accepted by the owner: the experiment now measures
  what a second vendor finds, not what a second vendor would have stopped, and
  the report says so.
- The second vendor reviews code Copilot already reviewed and the owner already
  fixed, so its raw finding count falls and its ratio is not comparable to a
  pre-merge one. Post-merge acceptance also costs the owner a followup row or a
  second pull request where pre-merge it cost an edit to an open branch, which
  biases the cheaper disposition toward `rejected`. Accepted; the report names
  both biases and presents no clean vendor-against-vendor figure.
- No merge-time dispatch exists. `.github/workflows/sd-review-route.yml:14-16`
  fires on `pull_request` `opened`, `synchronize`, `reopened` and
  `ready_for_review` only, holds `contents: read`, and states that asking a
  remote reviewer for a review is a separate change with its own decision
  record. The trigger is new work, not configuration, and it is not built by
  this item.
