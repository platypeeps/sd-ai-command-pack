---
name: sd-plan
description: Interview the user into a work item under docs/work, review the plan, and open its branch.
disable-model-invocation: true
---

# sd-plan

`sd-plan <slug>` turns an intention into one tracked work item:
`docs/work/<YYYY-MM-DD>-<slug>/prd.md`, plus `design.md` and `implement.md`
**only when you ask for them**. Invocation is explicit approval to write
inside the selected work root, create the item's branch, and record that
item's progress and decisions through `sd_db`. The work root defaults to
`docs/work`; `--work-dir` selects another root within this repository. This
does not authorize unrelated database rows, other project files, or external
writes.

## When to use

Use when requested for work spanning more than one session or more than about
300 changed lines, as `WORKFLOW.md` describes. A smaller change follows the
normal branch, check, review and ship path without a planning artifact. Do not
create a PRD just to record routine progress or work already merged.

## The sequence

1. **Use the existing context.** Ask only for answers that would change the
   work and are not already available. The
   problem stated in terms an outsider would recognise; requirements each
   testable by someone who did not write them; acceptance criteria that name a
   check *and its result* ("`pytest tests/auth` passes with 0 failures"), never
   an intention ("tests pass"). Keep stated requirements apart from assumptions.
   Do not restart an interview when a handoff or an existing decision supplies
   the answer. In an authorized unattended run, record routine choices on the
   item and continue under `WORKFLOW.md`'s stop conditions.
2. **Write from the templates** in `skills/sd-plan/templates/` (`prd.md`,
   `design.md`, `implement.md`, `decision.md`, `work-README.md`). Create
   `<work>/README.md` from the template if the directory is new. Add
   `design.md` or `implement.md` only when explicitly requested. Adapt the
   templates to the selected work root's `.status-source` marker, including
   when `--work-dir` changes that root. When it says `row`, keep progress in
   the database and add no `status:` field. With `file` or no marker, add
   `status: planning` for the legacy reader. Report an
   unrecognized marker instead of falling back. Do not recreate retired
   frontmatter from a template.
3. **Register the row**, when the work root's `.status-source` says `row`.
   Run `sd work register <work>/prd.md` as soon as the file exists. The
   retirement handed status to the database and took the importer away with
   it, so a folder written after the cutover has a `prd.md` and no row, which
   is the state `sd-status` reports as `status-unreadable`. Registering is
   idempotent: a second call prints `already registered` and changes nothing,
   so re-running it on an item that already has a row is safe. The row takes
   its name and its date from the file's `title:` and `created:`, which must
   both be present. With `file` or no marker, skip this step — the `status:`
   field is the record there, and a row beside it would be a second answer to
   one question. `sd work register` refuses such a repository by name, so the
   step cannot create that state by mistake.
4. **Review the plan.** Run `sd-review --scope planning`, which resolves the
   active `planning`/`in_progress` item's `prd.md`/`design.md`/`implement.md`
   and routes them to the reviewer the registry gives. This is the development
   flow's *prd and design* review point; its cap is that row's in
   `.claude/rules/sd-planning-adversarial-review.md`. Record the findings
   under a `## Review` heading in the item.
5. **Promote.** `planning → ready` only when acceptance criteria are present
   and **no open `BLOCKING` line remains**. An unresolved blocking concern is a
   stop, not a note. In a checkout using row status, write the transition
   through `sd_db`; a missing item row is reported as missing, never replaced
   by a status field or a GitHub issue.
6. **Branch.** Create the branch and record it as `branch:` in the PRD
   frontmatter when work starts. An `in_progress` item still needs a branch
   (`sd-docs-lint` rule 2); in a checkout using row status, the status itself
   remains on the row.

There is no automatic archive or parking step. `sd sweep` reports idle items
without moving them or changing their status. Planning and the first commit
leave unrelated work items where they are.

## Flags

| Flag | Effect |
|---|---|
| `--decision` | Write a `docs/decisions/` record instead of a work item |
| `--work-dir` | Work root other than `docs/work` |
| `--worktree` | Create the branch in its own git worktree (one writer per checkout) |
| `--from gh:owner/repo#123` / `--from jira:KEY-123` | Seed `## References` from a tracker item, resolved by `sd-trackers ref` |
| `--from-suggestion` | Reserved: seed from a local proposal note; not implemented |
| `--from-proposal` | Seed from a skill proposal |

## Seeding from a tracker

`--from` resolves through one command, so the citation is what the tracker
says rather than what anyone remembered:

```bash
sd-trackers ref gh:openai/whisper#42
sd-trackers ref jira:ABC-45
```

It prints one bullet — the link, the title, the state, and the date the item
last moved — which goes verbatim under the PRD's `## References` heading, the
one the template already ships. Under `--decision`, where the template has no
such heading, add it above the bullet.

Read the exit code before pasting. **1** means the tracker was asked and the
reference did not resolve — no such issue, a repository you cannot see, or an
answer this could not read. **2** means it could not be asked at all: `gh`
missing or unauthenticated, the Jira variables unset, or a reference that does
not parse. Neither is a licence to hand-write a
citation: an unresolvable reference is a question for the user, and a made-up
link in a work item outlives the session that invented it.

The issue's own text stays in the issue. Cite the link, read the issue for the
interview, and leave its prose where it will still be current next month.

## Never

- **Never accept a repo path.** The repository is the one enclosing cwd
  (R10-D6). A work item whose `branch:` resolves to a different checkout is a
  refusal with the path printed, never a silent `cd`.
- **Keep writes within the authorized scope.** Files belong under the selected
  work root (plus `docs/decisions/` under `--decision`); database progress and
  decision writes belong only to the current item and go through `sd_db`.
  No unrelated rows, `.claude/`, `.trellis/`, hooks, labels, managed gitignore
  blocks, bookkeeping commits, or `AGENTS.md` edits are authorized here.
- **Never promote past an open `BLOCKING` line**, and never claim approval from
  a review lane that was skipped or that failed.
- **In `mode: guest`, never write artifacts into the upstream tree** — the
  triad lives on the fork's integration branch.
- **Never generate a design or implement file to look thorough.** Three files
  where one was warranted is the failure mode this command exists to avoid.

## Reattaching

If `sd-handoff --show` reports a pending packet for this directory, read it
before re-planning: it carries the previous session's `summary`, `next[]` and —
the field that saves the most rework — `dont[]`.

## State of the tooling

There is no `bin/sd-plan` yet; the templates ship and this procedure is carried
out by the agent. `sd-review`, `sd-check`, `sd-status`, `sd-handoff`,
`sd-trackers` and `sd-docs-lint` are real and callable today.

`sd suggest add` can record a proposal on an existing imported work item, but
`--from-suggestion` and `--from-proposal` have no resolution path yet. Do not
invent one. `sd task add` captures a standalone task; it does not create or
import a planning artifact. `sd work register` is the one command that makes
the row for an artifact already on disk; `sd-status` only reports, and never
registers the item it is complaining about.
