---
name: sd-plan
description: Interview the user into a work item under docs/work, review the plan, and open its branch.
disable-model-invocation: true
---

# sd-plan

`sd-plan <slug>` turns an intention into one tracked work item:
`docs/work/<YYYY-MM-DD>-<slug>/prd.md`, plus `design.md` and `implement.md`
**only when the work warrants them**. Invocation is explicit approval to write
inside `<work>/` and to create the item's branch. It is approval for nothing
else.

## When to use

Before writing code for anything larger than a one-line fix, and whenever a
change needs a record someone else could pick up. Not for a typo, not for a
revert, not to retro-document work already merged.

## The sequence

1. **Interview.** Ask until the PRD's headings can be filled honestly. The
   problem stated in terms an outsider would recognise; requirements each
   testable by someone who did not write them; acceptance criteria that name a
   check *and its result* ("`pytest tests/auth` passes with 0 failures"), never
   an intention ("tests pass").
2. **Write from the templates** in `skills/sd-plan/templates/` (`prd.md`,
   `design.md`, `implement.md`, `decision.md`, `work-README.md`). Create
   `<work>/README.md` from the template if the directory is new. Add
   `design.md` only when the approach is not obvious from the PRD — a design
   that restates requirements is a design nobody needed — and `implement.md`
   only when the work is more than one landable step.
3. **Review the plan.** Run `sd-review --scope planning`, which resolves the
   active `planning`/`in_progress` item's `prd.md`/`design.md`/`implement.md`
   and routes them to the codex second-model lane. Record its findings under a
   `## Review` heading in the item.
4. **Promote.** `planning → ready` only when acceptance criteria are present
   and **no open `BLOCKING` line remains**. An unresolved blocking concern is a
   stop, not a note.
5. **Branch.** Create the branch and record it as `branch:` in the PRD
   frontmatter. `status: in_progress` without `branch:` is a lint failure
   (`sd-docs-lint` rule 2) and `sd_lib.status_report` reports it as an
   inconsistency.
6. **Sweep, on the first commit.** Move merged items to `archive/YYYY-MM/`,
   and park any item idle in `planning` for more than **45 days with no
   `branch:`** (R10-D1). A parked item keeps its directory under
   `archive/YYYY-MM/`, gets `parked: <date> age-sweep` written into its own
   frontmatter, and is recoverable with `git mv`. Print every item the sweep
   touched — parked is not hidden. `sd-status --parked` lists them from that
   field; never write a separate ledger.

## Flags

| Flag | Effect |
|---|---|
| `--decision` | Write a `docs/decisions/` record instead of a work item |
| `--work-dir` | Work root other than `docs/work` |
| `--worktree` | Create the branch in its own git worktree (one writer per checkout) |
| `--from gh:o/r#N` / `--from jira:KEY` | Seed `## References` from a tracker item |
| `--from-suggestion` | Seed from a pending `sd-suggest` draft |
| `--from-proposal` | Seed from a skill proposal |

## Never

- **Never accept a repo path.** The repository is the one enclosing cwd
  (R10-D6). A work item whose `branch:` resolves to a different checkout is a
  refusal with the path printed, never a silent `cd`.
- **Never write outside `<work>/`** (plus `docs/decisions/` under `--decision`).
  No `.claude/`, no `.trellis/`, no hooks, no labels, no managed gitignore
  blocks, no bookkeeping commits, and never `AGENTS.md` or any other tracked
  file the user did not ask you to change.
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
out by the agent. `sd-review`, `sd-check`, `sd-status`, `sd-handoff` and
`sd-docs-lint` are real and callable today.
