---
title: Changelog entries live in the sd database; CHANGELOG.md is rendered at release
created: 2026-10-05
branch: sd2783-changelog-db
item: sd:2783
---
# PRD — changelog entries in the database

## Status

Accepted. The operator ruled Q1 to Q7 on 2026-10-05; the log is in
[design.md](design.md), "Decision log".

## Problem

Almost every pack pull request adds an entry at the top of `CHANGELOG.md`.
Two branches that each add an entry conflict on that one file. Branch
protection is strict, so a branch that falls behind must merge `main`
before it lands. Each such catch-up can stop on `CHANGELOG.md`.

The measurement below covers 2026-09-21 to 2026-10-05 (origin/main at
`5dff9e55`). It uses each pull request's head ref, `refs/pull/<n>/head`.
For every merge commit between the squash's parent and that head, it
recomputes the conflicts with `git merge-tree --write-tree --name-only`.

| Measure | Count |
| --- | --- |
| Pull requests squash-merged to `main` | 234 |
| Of those, squashes that change `CHANGELOG.md` | 167 (71%) |
| Pull requests with at least one catch-up merge | 191 |
| Catch-up merges in those heads | 427 |
| Catch-up merges that conflict | 201 |
| Conflicts on `CHANGELOG.md` only | 142, in 89 pull requests |
| Conflicts on `CHANGELOG.md` and other paths | 30 |
| Conflicts with no `CHANGELOG.md` path | 29 |

`CHANGELOG.md` is in 172 of 201 conflicted catch-ups (86%). The keep-both
resolver (sd:2174) landed on 2026-09-30 in `0bf6323a`. Before it, 68
`CHANGELOG.md`-only conflicts needed a hand resolution. From 2026-09-30, 74
more occurred. The resolver handles a catch-up that `sd-ship` or the lane
runs. It does not handle a builder's own `git merge origin/main`, and it
refuses the 30 conflicts that also name another path.

What the measurement cannot show:

- Whether the resolver or a person resolved each conflict after 2026-09-30.
  The merge commit looks the same either way.
- The time each resolution took.
- The gate runs. Strict protection needs the catch-up and its gate anyway,
  so a conflict-free file would not remove those runs.
- `git merge-tree` uses today's merge algorithm. A builder's git may have
  answered a conflict differently.

The lane logs under `/Volumes/local/repo-storage/sd-ai-command-pack/lane/`
agree in kind: 3 `CONFLICT (content): Merge conflict in CHANGELOG.md` lines
and 9 `Auto-merging CHANGELOG.md` lines. They cover only lane-run catch-ups.

The file also costs review and diff weight. It holds 7,009 lines (421 KB).
Its `## Unreleased` section runs from line 3 to line 2195, because no release
was cut after `1.0.0` on 2026-09-01.

No gate requires an entry. `sd-docs-lint`, the citation tests and
`tests/governed.py` read past `CHANGELOG.md` as history. The entry is a
habit that builder briefs repeat ("an Unreleased Added entry").

## Goal

A feature pull request never edits `CHANGELOG.md`. Its entry is text in the
pull request that a reviewer sees. `sd-ship merge` stores the entry in the
workflow database. One verb renders `CHANGELOG.md` from the stored entries,
in a pull request that only renders. No two feature branches share a file
for their release notes.

## Requirements

R1. An opted-in repository declares its entry in the pull request body, in a
    `## Changelog` section. The section holds `### Added`, `### Changed`,
    `### Deprecated`, `### Removed`, `### Fixed` or `### Security`
    subsections with bullets, or the one word `none`.

R2. `sd-ship prepare` in an opted-in repository refuses a body without a
    valid section. It refuses a section that matches a privacy pattern.
    It refuses a branch whose diff changes `CHANGELOG.md`, unless the branch
    is a render pull request (R6).

R3. `sd-ship merge`, after GitHub confirms the squash, writes one entry row
    per pull request to the database. A second run writes nothing new.

R4. The entry row uses the existing `state` checkpoint table. No
    `SCHEMA_VERSION` change in the system repository is needed.

R5. `sd changelog render` writes the generated part of `CHANGELOG.md` from
    the rows and git alone. The same rows and the same base give the same
    bytes.

R6. A render pull request changes `CHANGELOG.md` only, and its content equals
    `sd changelog render` at its base. `sd changelog render --check` proves
    it, and prepare runs that check.

R7. Render refuses when a merged pull request since the last release has a
    `## Changelog` section in its squash message and no row. It names each
    missing pull request. Render also re-runs the privacy check.

R8. A repository that did not opt in behaves exactly as today.

R9. The existing `CHANGELOG.md` text stays byte for byte. Rendered entries
    go in a marked region under `## Unreleased`.

## Acceptance criteria

1. A test prepares an opted-in fixture branch without a `## Changelog`
   section. Prepare refuses and names the section. On `main` the same branch
   prepares.
2. A test prepares an opted-in branch that edits `CHANGELOG.md`. Prepare
   refuses. A render branch whose file equals `render` output prepares.
3. A test merges a fixture pull request twice through reconcile. The
   database holds exactly one entry row for it.
4. Two renders over the same rows and base produce identical bytes.
   Reordering the rows' write order does not change the output.
5. A test deletes one row and runs render. Render refuses and names that
   pull request number.
6. A row whose text matches a synthetic privacy pattern makes render refuse.
   The test uses a pattern file in a temporary home, never the real one.
7. A fixture repository without the opt-in file prepares and merges as on
   `main`. No entry row is written.

## Out of scope

- A release train, version bumps, or tags. The operator ruled Q4 on
  2026-10-05: `--release` stays unused until a release is cut.
- Moving the 2,193 hand-written Unreleased lines into rows.
- Other repositories. The opt-in is per repository; the pack is first.
