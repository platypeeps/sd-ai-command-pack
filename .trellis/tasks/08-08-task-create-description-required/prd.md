# `task.py create` writes task records that the pre-archive gate refuses

## Goal

Stop `task.py create` from producing a task record that the pre-archive
metadata gate will reject. The failure surfaces at creation, when it costs one
retyped command, rather than at finalization, when a pull request is already
open and green.

The gate checks `title` and `description` in one loop, so this task covers both
fields. Requiring a description alone leaves the same defect reachable through
a whitespace title.

## Problem

Two surfaces disagree about what a valid record is.

`task.py create` treats an empty description as a warning
(`.trellis/scripts/common/task_store.py:300-312`):

```text
description = (args.description or "").strip()
if not description.strip():
    print(
        colored(
            "warning: task description is empty; pass --description to improve search and later audits.",
            Colors.YELLOW,
        ),
        file=sys.stderr,
    )
```

It then writes `"description": description` — an empty string — at
`.trellis/scripts/common/task_store.py:314`.

The pre-archive gate treats it as fatal
(`scripts/sd-ai-command-pack-review-preflight.mjs:3348`):

```text
for (const field of ['title', 'description']) {
  if (typeof record[field] !== 'string' || record[field].trim().length === 0) {
    issues.push(`${field} must be a non-empty string`);
  }
}
```

`task.py create --help` advertises `--description` as an ordinary option, with
nothing to indicate that omitting it makes the task unarchivable.

### The title has the same hole

`task_store.py:207` guards the title with a truthiness test:

```text
if not args.title:
    print(colored("Error: title is required", Colors.RED), file=sys.stderr)
    return 1
```

`"   "` is truthy, so it passes. The slug is normally derived from the title
and would fail, but `--slug` bypasses that path entirely
(`.trellis/scripts/common/task_store.py:242`). `task.py create "   " --slug x`
therefore writes a whitespace title, which the same gate loop at `:3348`
refuses. Fixing only the description would leave the goal unmet.

### The two emptiness tests are not the same test

Creation uses Python `str.strip()`; the gate uses JavaScript `String.trim()`.
Their whitespace sets differ, measured in this checkout:

```text
char         py .strip() empty    js .trim() empty     agree
U+0085       True                 False                NO -- DIVERGES
U+FEFF       False                True                 NO -- DIVERGES
U+00A0       True                 True                 yes
ASCII space  True                 True                 yes
```

U+FEFF diverges in the dangerous direction: creation would accept it as a
non-empty description and the gate would refuse the record — reproducing this
exact defect *after* the fix. Any requirement that the two "agree by
construction" is false unless the shared predicate is defined explicitly rather
than assumed from two languages' built-ins.

## Why this is a defect and not a preference

Same shape as the `record-session` defect closed in 0.64.27: the documented
command produces an artifact the documented validator always refuses. A warning
on stderr at creation is separated from the failure by the entire life of the
task.

Observed on 2026-08-08, when finalization of PR #376 failed with

```text
task_metadata_invalid .trellis/tasks/08-08-codex-lane-consent-gate/task.json
field description must be a non-empty string
```

on a task created hours earlier. The pull request could not merge until an
unrelated task's record was corrected inside it.

The defect is already known and already worked around once. `sd-fleet-refresh`
carries a guard asserting the description is present and non-empty before
advancing, described in `CHANGELOG.md:518-521` as "a belt-and-suspenders guard
against an upstream `task.py create` that tolerates an empty description". That
is a point fix in one workflow; every other creation path is unprotected.

## Existing records already carrying the defect

Three of 53 active task records have an empty description as of 2026-08-08, and
each will fail the same way at its own finalization:

```text
07-25-agent-artifacts                 Ship SD commands as cross-platform sub-agents
07-25-harden-toolchain-failure-paths  Harden toolchain failure paths
07-25-reduce-review-tooling-spawns    Reduce review tooling process spawns
```

All three are `planning`. They already exist, so a creation-time rule cannot
reach them; backfilling is part of this task.

## Decision already made

**A non-empty description becomes required at `task.py create`.** The
alternative — dropping `description` from the gate's non-empty check — was
considered and rejected: an archived task with no description is worth less to
every later reader and audit, and the field already carries a warning precisely
because it matters. Recorded so it is not reopened.

Open is *how* and *where* it is enforced, and what happens to the callers.

## Callers that would break

Requiring the flag is a breaking change to documented invocations. `grep -rn
"task\.py create" --include=*.md`, excluding task directories and the archive,
returns **77 invocations that pass no `--description`**, including the two
canonical ones:

```text
.trellis/workflow.md:317
  python3 ./.trellis/scripts/task.py create "<task title>" --slug <name>

.agents/skills/trellis-brainstorm/SKILL.md:33
  TASK_DIR=$(python3 ./.trellis/scripts/task.py create "<short task title>" --slug <slug>)
```

`sd-work-backlog` also creates follow-up and split tasks autonomously
(`.agents/skills/sd-work-backlog/SKILL.md:209`), so a required flag that its
instructions do not supply turns an unattended run into a failed one. Every one
of these has an installed mirror that must change with it.

Enumerate from the repository when implementing; 77 is a snapshot, and its
point is that this is a fleet-wide instruction change, not a one-file edit.

## Constraints

- `.trellis/scripts/**` is vendored Trellis —
  `scripts/sd-ai-command-pack-review-preflight.mjs:4253` classifies it through
  `isTrellisCopiedPath`. A `task_store.py` change is an upstream change.
- The `scripts/` and `templates/scripts/` preflight copies must stay
  byte-identical. The rule at `:3348` is already present in both at that line.
- `cmd_create` calls `ensure_tasks_dir(repo_root)` at
  `.trellis/scripts/common/task_store.py:236`, which creates `.trellis/tasks`
  and `.trellis/tasks/archive` when absent — well before description handling
  at `:300`. "Fails before mutating anything" therefore means before `:236`,
  not merely before the task directory `mkdir`.

## Requirements

### Functional

1. `task.py create` exits nonzero and creates nothing when the description is
   absent or whitespace-only.
2. The same rule applies to `title`, replacing the truthiness test at
   `.trellis/scripts/common/task_store.py:207`, so `--slug` cannot smuggle a
   blank title past it.
3. Validation runs before `ensure_tasks_dir` at `:236`, so a rejected
   invocation leaves the filesystem untouched.
4. The failure message names the flag and states that the record would be
   refused at archive.
5. `task.py create --help` documents the description as required.
6. The three existing empty-description records are backfilled from their own
   `prd.md`, not invented.
7. Every in-repository invocation that would newly fail is updated, in both
   source and installed-mirror copies, in the same change.

### Non-functional

8. No change to the pre-archive gate's rule at `:3348`. Creation is made to
   agree with the gate; the gate is not relaxed.
9. The emptiness predicate is stated explicitly — which characters count as
   whitespace — rather than inherited from `str.strip()` and `String.trim()`
   independently. Whatever is chosen, the two implementations agree on the
   divergent characters measured above.

## Open questions (resolve in design)

1. **This has no standalone pack-local half.** The sibling task needs a *new*
   pack-local detection rule; here the pack-local validator already rejects
   empty descriptions — that rejection is the whole problem statement, and
   requirement 8 forbids touching it. So the enforcement half is upstream
   Trellis only, with caller migration and backfill as separately scoped work.
   Decide whether this ships as an upstream report, a vendored patch carried in
   `.trellis/scripts/`, or a parked task in the style of
   `07-30-upstream-task-start-branch-recording`.
2. **Which whitespace definition?** ASCII-only is the simplest predicate both
   languages can implement identically. Unicode-aware is friendlier but needs
   an explicit character list. Requirement 9 demands a choice, not a default.
3. **How do the 77 callers migrate?** A hard cutover breaks any consumer whose
   installed mirror lags the source. A deprecation window that warns first and
   fails later costs a release but cannot strand a fleet consumer mid-upgrade.
4. **Does `sd-work-backlog` have a description to supply?** It creates tasks
   from its own analysis. If it cannot always produce one, a required flag
   converts a recoverable gap into a stopped autonomous run.

## Acceptance criteria

- [ ] `task.py create "<title>"` with no `--description` exits nonzero, names
      the flag, and leaves no new directory under `.trellis/tasks/`
- [ ] `task.py create "<title>" --description "   "` fails identically
- [ ] `task.py create "   " --slug <valid>` fails on the blank title
- [ ] A rejected invocation in a repository with no `.trellis/tasks` directory
      leaves that directory absent, proving the check precedes `:236`
- [ ] A record created with a valid title and description passes the metadata
      portion of validation — `task_metadata_invalid` absent from the reason
      codes. Note that a freshly created `planning` task cannot reach
      `pre_archive_valid`: it legitimately reports
      `task_lifecycle_not_completion_ready`, `task_branch_invalid`, and
      `pre_archive_acceptance_incomplete` until it is started and finished, so
      the criterion isolates metadata rather than asserting a valid gate run
- [ ] A test covers the divergent characters above and fails if creation and
      the gate classify any of them differently
- [ ] A survey of active task records reports zero empty descriptions
- [ ] No in-repository documented invocation of `task.py create` omits the
      description, in source or installed mirrors
- [ ] `scripts/` and `templates/scripts/` preflight copies remain
      byte-identical

## Notes

Filed 2026-08-08 after the defect blocked PR #376's finalization. Adversarially
reviewed the same day; that review found the title hole, the `str.strip()` /
`String.trim()` divergence, the `ensure_tasks_dir` ordering, and the false
claim of a pack-local half, all of which are now recorded above.

Related: `08-06-task-create-base-branch-seed` covers `base_branch` seeded from
the current branch at `.trellis/scripts/common/task_store.py:296-298` — a
different defect in the same `cmd_create` function, an adjacent statement
rather than an adjacent line. Same vendored-upstream constraint, and the two
should be designed together even if they ship apart.
