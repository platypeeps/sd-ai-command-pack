---
title: repo.github_issues - a per-repo switch for third-party GitHub issue intake, set with sd-db repo and shown in repo list
created: 2026-10-16
item: sd:4827
branch: sd4810-repo-github-issues
---

# Design: repo.github_issues (sd:4827)

Write this page only when the shape needs agreement before the code.
The item's row holds status, progress and decisions; this page holds the shape.

## Status

Pack half of system sd:4810. The system half (agent prompt text, a Today intake pass) waits; see Slices.

Adversarial review: one read-only `codex exec` round on 2026-10-16 found seven findings. Dispositions:

- R1 a database the guard cannot open (old hook meets 35, hub down) reads as not managed and allows: rebutted for
  this change. That fail-open is the guard's documented rule ("Every way of not knowing is False", sd:2256), it
  predates this item and covers every migration. The new exception only narrows a deny once a row is found, so it
  adds no allow on that path. Older state now says so instead of claiming a deny.
- R2 a satellite whose build or schema differs from the hub fails before the column is read: same disposition as
  R1; a failure row now names it.
- R3 an `on` checkout would pass an `update` aimed at another repository: fixed. The exception also needs the call's
  `owner`/`repo` to name the row's GitHub remote; a missing or different target denies.
- R4 an origin two rows share resolves a worktree to itself, so no row and no deny: rebutted for this change, as R1:
  `registered_for` refuses to guess (sd:1219) and the guard was silent there before. The Risks line no longer
  claims every worktree resolves.
- R5 `test_judgment_compare`'s replay and `test_home_relative`'s inventories need 035: accepted; both are in
  acceptance.
- R6 the stop-mid-file test must drop its pre-added column before the rerun, as 033's does: fixed in the table.
- R7 rollback needs the services stopped and the matching build: fixed in Older state.

After the round, the guard exception was dropped (decision, 2026-10-16). The operator's global deny list, which
system `local-machine-setup/claude_settings.py` writes, holds `mcp__github__issue_write` for every repo, and a
permission deny wins over a silent hook. The exception could never run, so R1 to R4 now concern only the guard as it
stands on `origin/main`. `gh issue close` is the close path: neither the deny list nor the guard blocks it.

## Problem

Agents follow one global rule: never use GitHub issues; sd items are the record.
Some repos take issues from people outside the workflow, and those reporters need an answer on the issue.
Today the exception lives in prose: one line in the operator's global instructions and a section in one repo's
`CLAUDE.md` (sd:4809). Prose cannot be listed, set or tested, and an agent in another repo cannot tell it applies.

The ban is enforced twice, and both stay. `bin/sd-issue-guard` denies `gh issue create` and
`mcp__github__issue_write` in every managed repo, and the operator's global deny list holds `issue_write` too.
Neither blocks `gh issue close` or `add_issue_comment`, which are what an agent in an `on` repo needs.

## Approach

### The column

Migration 035 adds `repo.github_issues INTEGER NOT NULL DEFAULT 0 CHECK (github_issues IN (0, 1))`.
Every row starts at 0, off: the ban holds for every repo until the operator turns one on.
`ADD COLUMN`, as 015 (`managed`) and 033 (`dependabot`) did: SQLite adds it in place, moves no row and touches no
other table. The file's header carries the reverse as `--   ` lines, back to 34.

### The verb

`sd-db repo github-issues <path> on|off`, shaped like `repo runner-merge` and `repo managed`:

- `repos.set_github_issues(connection, path, value)` returns `(path, before)`; the verb prints
  `sd-db: <path> github_issues off -> on`.
- `GITHUB_ISSUES_VALUES = {"on": 1, "off": 0}` names the words, as `MANAGED_VALUES` does for `yes|no`.
- It refuses, with exit 1 and no write: a word other than `on` or `off` (exact, so `On`, `ON`, `yes`, `1`, empty
  and padded words refuse), a path no row holds (naming `repo add`), and a wrong argument count.
- The read and the write share one transaction, as `set_dependabot` does.

`on|off` and not `yes|no`: the owner's brief names `on|off`, and the column is a switch, not a membership flag.

### The list field

`sd-db repo list` prints `path  remote  managed  ci  github_issues  lane_host  runner_merge`, the new field as
`on` or `off`.
`runner_merge` stays the last field: the operator's instructions and `machine-setup.sh`'s `local_blocks` read `$NF`.
Between `ci` and `lane_host` keeps the first four fields and the last two where they are.
One reader still moves: `machine-setup.sh`'s hub lane check reads the remote as `$(NF-4)`. It must read `$2` before
this lands (Slices, Risks).

### The read path

- Agents read the `github_issues` field of `sd-db repo list` for their repo, as they read `runner_merge`.
- Code calls `repos.github_issues(connection, path) -> bool`: True only when the row holds 1.
  No row reads False, the column default: an unregistered repo is not switched on.
  A store not yet at 35 raises `SchemaTooOld`, as `repo_channels` does; it never reads as off silently.
- The system's Today intake pass would call it (Slices, step 3). Nothing in the pack reads it yet.

### The guard does not change

`sd-issue-guard` reads no new column. With the setting on, it still denies `gh issue create` and
`mcp__github__issue_write` in a managed repo; `GithubIssuesOnLoosensNothing` pins that, and that `gh issue close`
passes. An agent comments with `add_issue_comment` or `gh issue comment` and closes with `gh issue close`.

### What agents do (system half writes the prose)

On: read the repo's open issues; give each one sd item, `sd task add --ref github:<owner>/<repo>#N`; keep the
process on the item; write reporter-facing comments only, naming no sd item, lane, gate, builder or `docs/work`;
close the issue with `gh issue close` when its item is done; file no new issue.
Off: today's ban, unchanged.
`local-agent-prompt/prompt/shared.md` in the system repo carries that text; this PR changes no system file.

### Rejected

- A `channels` key (`github=` already names an issue source): it means "the operator's issues for Today", a
  managed repo refuses it, and the owner asked for a `runner_merge`-shaped setting with its own verb.
- A one-argument read form (`repo github-issues PATH` printing the value): a new surface; `repo list` already answers.
- Appending the field after `runner_merge`: it would move the last field the operator's rules read.
- A guard exception for `issue_write` `update` in an `on` repo, built and reviewed in round 1: the global deny list
  refuses `issue_write` first, so the exception was dead code; `gh issue close` already works.

## Non-goals

- The agent prompt text, the dashboard control and a Today intake pass: system sd:4810.
- Lifting the managed repo's refusal of `channels github=`, or collecting other people's issues into `shadow`.
- Any change to `sd-issue-guard` or to the global deny list.
- Deleting the interim prose of sd:4809: it goes when the system half lands.

## Older state

- A process on the old library meets a store at 35: it refuses with `SchemaTooNew`, as for every migration.
  The guard then cannot read `managed` and stays silent, its rule for any open failure; the same holds on a
  satellite whose build differs from the hub's. The global deny list still holds `issue_write` meanwhile.
- The new library meets a store at 34 (installed, not yet migrated): reads open read-only; `repos.github_issues`
  raises `SchemaTooOld`; `repo list` and the verb open for write and refuse with `SchemaTooOld`, naming `migrate`.
- Rollback to the previous commit: stop the runner, the dashboard and the serve agent; take `bin/sd-db backup`;
  run the reverse in 035's header; check out the previous commit in the pack; restart them and run
  `dashboard.sh health`. The reverse drops every setting; turn each repo on again after the next upgrade.
- A shell or awk reader of `repo list` that counts fields from the end past `lane_host` reads a shifted field.
  The one found is `machine-setup.sh` `$(NF-4)` (Risks).

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| `migrate` runs 035 | `repo` gains `github_issues`, version 34 to 35, one transaction | the ALTER or the version write fails | the transaction rolls back; the store stays at 34 and `migrate` runs again | `TheGithubIssuesColumn`: a hand-added column fails the file, the store stays at 34; the test drops that column and a rerun finishes |
| New library, store still at 34 | none | the column is missing | `repos.github_issues` raises `SchemaTooOld`; the verb and `list` refuse | `test_a_store_before_35_raises_and_never_reads_as_off` |
| A process on the old library meets 35, or a satellite's build differs from the hub's | none | its open refuses (`SchemaTooNew`, a build mismatch) | restart it on the new library | existing `SchemaTooNew` and remote build tests |
| Rollback to the previous commit | none until the reverse runs | the old library refuses a 35 store | stop the services, back up, run the reverse lines in 035's header, check out the old build, restart | `TheGithubIssuesColumn` runs the reverse; `one_migration_back` in `test_backup.py` uses it |
| `repo github-issues PATH on` | one row's column and `updated_at` | a bad word, an unknown path, or the write fails | refusal before the write; a failed write rolls back; rerun the verb | verb and `set_github_issues` tests |
| `repo list` after the field lands | none | a reader counts from the end past `lane_host` | that reader reads by position from the front (`$2`) | `test_repo_list_keeps_runner_merge_as_the_last_field`; the system follow-up's own test |

## Slices

1. System: `machine-setup.sh`'s hub lane check reads the remote as `$2`, not `$(NF-4)`. It must merge first, or
   the hub check finds no lane repository after this PR lands and reports `ok`.
2. Pack (this PR): migration 035, the verb, the list field, `repos.github_issues`, docs.
3. System sd:4810: `shared.md` text for on and off, the dashboard control, an optional Today intake pass, and
   removal of the interim prose of sd:4809.

## Acceptance criteria

- [ ] `migrate` takes a store at 34 to 35; every row reads `github_issues = 0` and keeps its other values.
- [ ] `sd-db repo github-issues PATH on` prints `github_issues off -> on`; `repo list` shows `on` before
  `lane_host`, and `runner_merge` is still the last field.
- [ ] `On`, `ON`, `yes`, `1`, ``, ` on` and an unregistered path exit 1 and write nothing.
- [ ] In a managed repo with the setting on, the guard still denies `issue_write` and `gh issue create`, and
  `gh issue close` passes.
- [ ] `test_schema`, `test_repos`, `test_cli`, `test_home_relative`, `test_backup`, `test_judgment_compare` and
  `test_sd_issue_guard` pass.
- [ ] `sd-docs-lint` passes from the repo root.

## Risks

- The setting is advice to agents, not a gate: nothing stops `gh issue close` in an `off` repo, as nothing does
  today. Accepted: the one operator's agents follow the rule text, and the guard was never about closing.
- The field order shift breaks any unlisted reader that counts from the end past `lane_host`. The search covered
  the pack, the system repo and `platypeeps/*`; slice 1 fixes the one hit.
