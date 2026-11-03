---
title: Fold repo.runner_merge and repo.ci into the policy declaration
created: 2026-11-03
item: sd:7366
---

# Design — repo-policy-fold

Ruling: system sd:7224 note #40950 (fold, delete the columns); note #40956 (keep `issues: ask`, only on
repositories the operator does not manage).

## Problem

Two stores hold a repository's rules: the `policy` declaration (sd:6715) and the `repo` columns
`runner_merge` and `ci`. `github_issues` already moved: migration 045 made it `policy.issues` and dropped
the column. The policy already has a `ci` object (`provider: jenkins`), so "where checks run" has two
homes today.

Live rows (2026-11-03): 27 `local`/`auto`, 71 `github`/`manual`; `issues: ask` on one unmanaged repo
and one managed repo (against #40956).

## Approach

Two keys join the policy; the columns go.

- `policy.merge`: `ask` or `auto`, a fourth act beside `commit`, `push`, `pr`. Absent reads `ask`
  (today's `manual` default) in every mode. The org/external `auto` refusal (note #34749) covers it.
- `policy.ci.provider`: `github`, `local` or `jenkins`. Absent reads `github`. `url` and `job` stay
  required for `jenkins` only.

`sd_db.repos` keeps the function names every caller uses: `set_runner_merge`, `set_ci`, `repo_ci`, and
gains `runner_merge(connection, path)`. Each reads or writes the policy, keeping its other keys, as
`set_github_issues` does. SQL readers use `json_extract(declarations, '$.policy.merge')`.

The CLI keeps its shape, so no parser changes:

| Surface | After |
| --- | --- |
| `sd-db repo list` | same fields and words: `... managed ci issues lane_host runner_merge`; `ci` prints the provider; `ask` prints `manual` |
| `sd-db repo runner-merge PATH manual\|auto` | same verb and words; writes `policy.merge`; prints `policy.merge` |
| `sd-db repo ci PATH github\|local` | same; writes `policy.ci.provider`; refuses a row whose policy declares `jenkins` |
| `sd-db repo declare PATH policy JSON` | carries `merge` and `ci.provider` over when the new value omits them |

Rejected: virtual generated columns named `runner_merge` and `ci`. They keep every reader unchanged, but
keep two names for one setting, which the ruling removes.

Mixed pins need no extra step. The hub refuses a satellite on another `sd_db` build (`BuildMismatch`),
and a library refuses a database newer than its schema (`SchemaTooNew`). An old reader therefore never
meets a dropped column; it fails closed: `runner_merge` unknown merges nothing, `repo_ci` answers
`github` and the merge refuses. `repo-sync.sh refresh` stops services, migrates and restarts them.

## Non-goals

- Folding `managed`, `lane_host`, `dependabot`, `channels` or `jira_project`.
- Renaming the `runner-merge`, `ci` or `github-issues` verbs (keep-commands-few).
- Changing the `issues` words; 045 settled them.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| S1 migration 047 backfill | `policy.merge=auto` where `runner_merge='auto'`; `policy.ci.provider='local'` where `ci='local'` | a write fails mid-file | `migrate` wraps the file in one transaction; 46 stays, rerun | `test_schema`: kill at the second UPDATE, schema 46, no key written |
| S1 backfill, org-mode row | `policy.merge=auto` on an org policy | the validator refuses it (none live) | the migration skips `merge` there; the row reads `ask` | `test_schema`: org row keeps `merge` absent |
| S1 dual write | writers set column and policy in one transaction | a caller writes the column by raw SQL | 048 re-copies column to policy before the drop | `test_repos`: raw column write, then 048, policy equals column |
| S1 readers switch | none | a reader still reads the column | the column still holds the same value; S2's grep test fails it | `test_no_column_readers` (grep over `bin lib dashboard`) |
| S1 `repo declare policy` | replaces policy | a preset drops `merge`, lane stops merging | carry-over (#41768); `repo runner-merge` restores it | `test_cli`: declare without `merge` keeps `auto` |
| S2 migration 048 drop | re-copy, then `DROP COLUMN runner_merge`, `DROP COLUMN ci` | drop fails (index, view, trigger names the column) | one transaction; 47 stays; reverse SQL in the file comment | `test_schema`: 47 to 48 and the 045-style reverse round-trip |
| S2 stale service on old build | none | dashboard or runner opens the 48 database | `SchemaTooNew` on open; refresh restarts it; `dashboard.sh health` | existing `test_database` SchemaTooNew case |
| S2 satellite on old pin | none | lanes read `hub_unavailable` | `repo-sync.sh refresh` on the satellite | existing `BuildMismatch` tests |
| S3 `issues: ask` limit | `set_github_issues` and `set_managed` refuse ask on a managed row | the managed `ask` row exists | #41768: set it to `read` before S3 lands | `test_repos`: ask on managed refused both ways |
| S4 instruction files | prose only | names a gone column | none needed: verbs and list shape hold | `sd-docs-lint`; grep for `repo.runner_merge` is empty |

## Slices

1. **pack: policy keys, readers, backfill** (migration 047). Adds `merge` and `ci.provider` to
   `sd_repo_policy`; `repos` accessors over policy with dual write; every reader switched.
   Readers to switch (from `grep -rlw -E 'runner_merge|repo_ci|set_ci|row\[.ci.\]'`): `lib/sd_db/repos.py`,
   `writes.py` (`upsert_repo` params), `runner.py` (lines 80, 607 SQL), `protection.py` (1964, 1990 SQL),
   `jobs/cli.py`; `bin/sd_lane.py` (`default_runner_merge`), `bin/sd-ship` (`row_merges`), `bin/sd_lib.py`
   (`repo_ci`), `bin/sd_ci.py`, `bin/sd_fleet.py`, `bin/sd_standard.py`, `bin/sd-status`;
   `dashboard/sd_dashboard/{management_screen,queue_screen,server}.py`, `v2/static/management.js`.
   Leaves every machine working: columns and policy agree.
2. **pack: drop columns** (migration 048). Re-copy, drop, remove dual write; grep test forbids the
   column names in SQL and row reads. Pack prose in the same PR: `WORKFLOW.md` (45, 67-68, 118, 123,
   131, 203, 256, 420, 468, 501-502, 628-633), `AGENTS.md:10`, `README.md`, `docs/sd-db.md`,
   `skills/{sd-ship,sd-review,sd-check,sd-status}/SKILL.md`, `skills/sd-review/references/setup-github.md`.
3. **pack: `issues: ask` only on unmanaged rows** (#40956). Small, independent of 1 and 2.
4. **system: instruction prose**, after 2 merges. `local-agent-prompt/prompt/shared.md` (installs
   `~/.claude/CLAUDE.md`): line 46 `github_issues on` -> `issues` read or ask (ask only on repos you do
   not manage); 96 and 134 `repo.runner_merge` -> `policy.merge`; 106 `repo.ci` -> `policy.ci`; 97 stays.
   system `CLAUDE.md` (Tests and CI, `repo.ci=local`) -> `policy.ci local`; `docs/local-ci-rollout.md` 4, 5, 69.
   `machine-setup.sh` (its `repo list` field parser) needs no change: list shape holds.

## Acceptance criteria

- [ ] `sd-db repo list` output is byte-identical before and after on a copy of the live database.
- [ ] Slice 2's `test_no_column_readers` passes: no SQL or row read names `runner_merge` or `ci`.
- [ ] `make check` passes in the pack; `make test SUITE=` for repo-sync and machine-setup passes in system.
- [ ] `sd-db status` reads `schema version 48` on the hub after refresh; `dashboard.sh health` is ok.

## Risks

- Accepted: satellites stop lanes until their refresh, as at every schema bump.
- A JSON key typo reads as the default (`ask`, `github`): fail closed, but silent. The validator
  refuses unknown keys; `repo list` shows the effect.

## Decisions

Rulings in note #41768 on sd:7366:

- Q1. The merge key is `policy.merge: ask|auto`, a fourth act; the org/external `auto` refusal covers it.
- Q2. `repo declare PATH policy` without `merge` or `ci` keeps the row's values for them.
- Q3. The managed repo with `issues: ask` moves to `issues: read`
  before slice 3 lands.
