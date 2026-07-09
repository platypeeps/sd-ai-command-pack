# Close the Fleet Refresh Loop Design

## Overview

This task is a reconciliation pass, not a new feature release. The goal is to
turn the 0.5.11-0.5.28 fleet refresh history into an auditable final state:
each consumer repo is confirmed current enough, old review-thread promises are
answered or marked moot, archived PRDs tell the truth, and the duplicate
journal Session 29/30 incident has a recorded root cause.

The work crosses local task records, GitHub PR/review state, consumer repo
install state, and the pack's session recorder. It should proceed as an
evidence ledger first, then targeted cleanup.

## Proposal

Build a small reconciliation ledger before making changes. Each row should
name the repo or archived task, the expected outcome, the command or URL used
to verify it, and the final decision.

The fleet inventory starts from the PRD's known repos:

- `platypeeps/anomaly-metric-creator`
- `platypeeps/rwbp-website`
- `platypeeps/rwbp-coordinator`
- `platypeeps/loadsmith`
- `answerbook/mezmo_benchmark`
- any remaining consumer named by the archived task evidence or rollout
  journal entries

For each consumer repo, verify the installed pack version is `0.5.28` or later
and that the install audit exits successfully. Prefer live repo evidence over
journal memory: inspect `.sd-ai-command-pack/provenance.json` or
`manifest.json` when available, run the repo-local install audit when present,
and use `gh pr list/view/checks` to resolve any still-open rollout PRs. If a
repo needs an update, use the pack installer and route changes through that
repo's normal PR flow.

Review-thread reconciliation is a separate pass. The PRD names four specific
items: mezmo PR #313 comment 3522276141, anomaly-metric-creator PR #193,
rwbp-website PR #85, and loadsmith 0.5.15 review threads. For each, check the
live thread/comment state, reply with the shipped-fix evidence when still
actionable, and resolve only after the evidence supports the reply. If a PR was
merged, closed, or superseded, record that as the reason the archived
acceptance criterion is moot.

Archived PRD updates should be conservative. Only check an acceptance item
when there is direct evidence. Otherwise append a dated note explaining why the
item is moot, superseded, or still blocked. Do not rewrite completed task
history beyond those truth-maintenance notes.

The duplicate Session 29/30 investigation should start with the local evidence
already captured in this repo:

- `.trellis/workspace/sdelmas/journal-1.md` contains duplicate Session 29 and
  Session 30 bodies for "Expand SD command pack workflows".
- `scripts/sd-ai-command-pack-record-session.py` calls
  `.trellis/scripts/add_session.py` once with `--no-commit`, then patches and
  commits the journal itself.
- `.trellis/scripts/add_session.py` owns session numbering, journal append,
  index update, and optional auto-commit behavior.
- `.trellis/tasks/07-07-file-upstream-trellis-issues/upstream-issue-5-journal-duplicate-session.md`
  is intentionally unfiled until this root cause is confirmed.

The preferred output is a root-cause note with enough detail to decide whether
issue 5 belongs upstream in Trellis or locally in the pack. If the pack wrapper
can double-invoke, fix it here with tests. If Trellis append/index behavior is
the likely source and the wrapper path is exonerated, update the issue-5 draft
and hand it to the upstream issue task.

## Boundaries And Non-Goals

- Do not create upstream Trellis pull requests from this task.
- Do not infer fleet success from old journal entries when live repo or PR
  state is easy to check.
- Do not upgrade consumers beyond the currently intended pack release unless a
  repo is already behind and needs a refresh to satisfy this task.
- Do not rewrite archived task history wholesale; add small reconciliation
  notes and checkboxes only where evidence supports them.
- Do not delete one of the duplicate journal sessions until the root cause and
  desired journal/index correction are recorded.

## Affected Files

- `.trellis/tasks/07-06-close-fleet-refresh-loop/prd.md`
- `.trellis/tasks/archive/2026-07/*/prd.md` for the archived tasks whose
  acceptance criteria mention fleet refresh, audit follow-up, or review-thread
  promises
- `.trellis/workspace/sdelmas/journal-1.md`
- `.trellis/workspace/sdelmas/index.md`
- `scripts/sd-ai-command-pack-record-session.py`
- `templates/scripts/sd-ai-command-pack-record-session.py`
- `.trellis/scripts/add_session.py` for investigation only; do not ship
  durable pack changes there because it is Trellis-owned runtime
- `.trellis/tasks/07-07-file-upstream-trellis-issues/upstream-issue-5-journal-duplicate-session.md`
  if the duplicate-session root cause is Trellis-owned

## Risks And Edge Cases

- Some rollout PRs may have been merged, closed, or superseded since the task
  was written. Treat that as evidence to reconcile, not as a failure by itself.
- Consumer repos may be on a later pack version than `0.5.28`. That satisfies
  the version side if the install audit also passes.
- GitHub review comments can be stale after force-pushes or branch deletion;
  use PR URLs, review thread state, and merge status together.
- The duplicate journal may have been caused by an interrupted or retried
  command rather than deterministic code behavior. The final note should say
  when root cause is confirmed, probable, or still unreproduced.
- If journal dedupe edits change session numbering, update both the journal and
  workspace index in one commit and verify no references rely on the old
  duplicate number.

## Validation

- `gh pr list/view/checks` evidence for any still-open consumer PRs.
- Repo-local install audit in each consumer checkout, or a documented reason it
  cannot run.
- `python3 ./.trellis/scripts/task.py list-archive` after archived task edits.
- `git diff --check`.
- Focused recorder tests if `sd-ai-command-pack-record-session.py` changes.
- Full local gate from this repo when pack-owned files change:
  `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh`.
