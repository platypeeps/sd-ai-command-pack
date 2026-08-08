# add_session.py numbers sessions from the working tree alone

## Goal

Make `.trellis/scripts/add_session.py` produce a journal session that survives
being merged alongside another branch's session — a number no sibling branch has
taken, a `Main Changes` section the caller can actually fill, and a commit table
the bookkeeping validator accepts.

## Problem

Three defects, all in one script, all reachable in a single afternoon. They are
grouped because they share a cause: the script models journal recording as if
one branch existed.

### D1 — the session number comes from the working tree

`.trellis/scripts/add_session.py:482`:

```text
current_session = get_current_session(index_file)
new_session = current_session + 1
```

`get_current_session` (`.trellis/scripts/add_session.py:96`) reads one number out
of the working tree's `index.md` and nothing else. It consults no Git ref, no
sibling branch, and no remote. Every branch cut from the same base therefore
computes the same successor.

Observed on 2026-08-06, three branches recording against base session 307:

| Journal commit | Session claimed | Branch |
|---|---|---|
| `9d490afd` | 308 | `chore/task-task-create-base-branch-seed` |
| `4ccd02fb` | 308 | `chore/task-fleet-gito-exclusion-propagation` |
| `8bb9f7a8` | 308 | `codex/kb-advisory-external-symlink` |

The first to merge keeps 308. Each later branch then conflicts in both
`journal-7.md` and `index.md`, and resolving means renumbering the session and
rewriting its `index.md` row by hand. That happened twice on the same day, and
the second resolution introduced a further failure: dropping one blank line
inside the session inherited from `main` tripped the pack's append-only rule with
`modifies historical Session 308 from origin/main; Trellis journal history is
append-only`.

The collision is invisible until merge. Nothing warns at record time.

### D2 — `Main Changes` cannot be filled without duplicating its heading

`generate_session_content` (`.trellis/scripts/add_session.py:205`) interpolates
the caller's text under headings it emits itself:

```text
### Main Changes

{extra_content}

### Git Commits

{commit_table}

### Testing

{testing_content}
```

`testing_content` defaults to `DEFAULT_TESTING`
(`.trellis/scripts/add_session.py:62`), the string
`- Validation was not recorded for this session.` — and **no CLI flag sets it**.
The parser (`.trellis/scripts/add_session.py:562`) exposes `--title`,
`--commit`, `--summary`, `--content-file`, `--package`, `--branch`,
`--no-commit`, and `--stdin`. There is no `--testing`.

So a caller with validation evidence to record has exactly one route: put a
`### Testing` heading inside `--content-file`. Doing that also tends to carry a
`### Main Changes` heading along with it, and the result is a session with the
heading twice, an empty first instance, and a second `### Testing` section still
carrying the "not recorded" placeholder.

That is what happened to session 311. The bookkeeping validator rejected it:

```
journal_content_missing — Session 311 Main Changes must contain real content
```

The empty first heading is what it read.

### D3 — merge commits are accepted into the commit table

The same function builds the table by splitting on commas with no inspection of
what each hash is:

```text
for c in commit.split(","):
    c = c.strip()
    commit_table += f"\n| `{c}` | (see git log) |"
```

Passing a merge commit produces a table the validator refuses:

```
planning_recovery_commit_non_linear — Session 311 commit 60b6238c must have
exactly one parent
```

A branch that merged its base rather than rebasing has such a commit in its own
log, so this is reachable whenever the recorded range spans a merge.

Two smaller things sit in the same three lines. The message column is the literal
placeholder `(see git log)` — 173 occurrences across `journal-1.md` through
`journal-6.md`, and 0 in `journal-7.md`, where they were filled in by hand. And
`--commit` is unvalidated free text: nothing checks that a hash resolves, or that
it belongs to the branch being recorded.

## Where the fix lands

`.trellis/scripts/` has **zero** entries in `manifest.json`. The pack does not
own, install, or vouch for `add_session.py`; it is vendored Trellis. The
correction to the script therefore belongs upstream, and this task tracks it the
way the repository already tracks nine other upstream-tagged tasks. Six of those
are corrections owed upstream — closest in shape are
`07-30-upstream-task-start-branch-recording` and
`08-04-trellis-upstream-archive-commit-lock-retry` — and the other three are
pack-side cleanups waiting on an upstream change to land. This task is the first
kind.

Worth knowing before planning: eight of those nine carry a `PARKED:` prefix.
Upstream-owed work in this repository has a strong tendency to stall on the
round trip, which is an argument for making the pack-local detection carry its
own weight rather than depending on the upstream fix arriving.

There is a pack-local half. `scripts/sd-ai-command-pack-review-preflight.mjs`
already owns journal rules — it is what produced both diagnostics quoted above.
A collision check belongs there too, because the preflight is what can fail the
gate before a review round is paid for, and because it works even against an
unfixed upstream script.

This split — upstream defect, pack-local detection — is the same one
`.trellis/tasks/08-06-task-create-base-branch-seed` names as its first design
decision. The two tasks should resolve it the same way.

## Requirements

### Functional

- R1: a session number must not silently collide with one already taken on
  another branch reachable from the same base. Detection is enough; automatic
  renumbering is a design choice, not a requirement.
- R2: `Main Changes` must be fillable through the CLI without the caller
  supplying the heading, and `Testing` must be fillable at all.
- R3: a commit that is not reachable from the recorded branch, or that has more
  than one parent, must not silently enter the commit table.
- R4: every failure above must be reported at record time, not discovered later
  by `final-bundle` or by a merge conflict.

### Non-functional

- N1: the numbering check must not require network access. `add_session.py` runs
  in the finish-work path, and a remote round-trip there would slow every session
  record for a case that is rare per-record.

## Constraints

- `add_session.py` is vendored, not pack-owned. Do not edit it as though it were
  a pack surface, and do not add it to `manifest.json` as a side effect of this
  work. A local patch is acceptable only as a documented carry until upstream
  lands, and must be recorded the way other upstream carries are.
- Any pack-local preflight rule must hold the repository's existing
  false-failure budget. A blocking gate that fires on a legitimate single-branch
  session is worse than the collision it prevents.
- Do not weaken the append-only journal rule or the non-linear-commit rule to
  make room. Both caught real defects on 2026-08-06.

## Open questions (resolve in design)

- What is the collision signal — the maximum session number across local
  branches, across `origin/*` refs, or a per-branch numbering scheme that cannot
  collide at all? A scheme change is the only option that removes the conflict
  rather than reporting it, and it is also the only one that changes the existing
  journal format.
- Should `add_session.py` renumber automatically, or refuse and report? Refusing
  is safer but leaves the operator doing by hand exactly what was done twice on
  2026-08-06.
- Is a `--testing` flag the right shape for D2, or should `--content-file` be
  parsed for headings it already supplies and merged rather than nested? The
  second handles today's callers without an interface change.
- Should the commit table resolve real subjects instead of `(see git log)`? 173
  existing rows carry the placeholder; backfilling them is separable from
  stopping new ones.
- Does the pack-local rule belong in the existing preflight journal check or in a
  new one? The existing check already reads the journal and `index.md`.

## Acceptance Criteria

- [ ] Two branches cut from the same base, each recording a session, produce a
      detectable condition — the second is reported at record time rather than
      only at merge.
- [ ] Replaying the 2026-08-06 sequence (`9d490afd`, `4ccd02fb`, `8bb9f7a8`, all
      claiming 308) reproduces the collision before the fix and is caught after
      it.
- [ ] A session recorded with validation evidence contains exactly one
      `### Main Changes` heading and exactly one `### Testing` section, with no
      `Validation was not recorded for this session.` placeholder left behind.
- [ ] Passing a merge commit to `--commit` is refused at record time, with the
      offending hash and its parent count in the diagnostic.
- [ ] Passing a hash not reachable from the recorded branch is refused.
- [ ] A session produced by the fixed script validates under `final-bundle`
      without hand repair — specifically, neither `journal_content_missing` nor
      `planning_recovery_commit_non_linear` is raised.
- [ ] The upstream/pack-local split is recorded explicitly, and any local carry
      of the upstream patch is documented alongside the other upstream carries.

## Notes

- Source: shipping PRs #321, #343, #344, and #345 on 2026-08-06. D1 was hit three
  times, D2 and D3 once each — both on session 311, both caught by `final-bundle`
  rather than by the script.
- Related: `.trellis/tasks/08-06-task-create-base-branch-seed` shares the
  upstream-defect / pack-local-detection split and should be designed with it.
- Complex enough to need `design.md` and `implement.md` before `task.py start`:
  the numbering scheme is a real choice with a compatibility cost against every
  existing journal, and R1 pulls against N1.

## Note (2026-08-08 consolidation)

D3 (merge-commit derivation) resolution is delegated to
08-08-merge-commit-policy, which owns the single decision resolving the
planning-recovery vs record-session vs D3 contradiction. Do not resolve D3
independently here.
