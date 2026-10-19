---
title: Repository declarations and plugin settings move into the workflow database
created: 2026-10-18
item: sd:5109
---

# Design — repo-row-config

Write this page only when the shape needs agreement before the code.
The item's row holds status, progress and decisions; this page holds the shape.

## Problem

The operator ruled that non-secret configuration lives in the workflow database (system sd:5109).
Two kinds of pack configuration still live in files.

- Four per-repository declarations sit in each checkout's `.github/`:
  `sd-review.json` (review routing policy, 17 repositories), `sd-gate-reuse.json` (gate receipt key, 2),
  `sd-check-scope.json` (docs-only check scope, 1) and `sd-status.json` (accepted protection gaps, 5).
  A change to any of them costs a pull request in that repository, and the dashboard cannot show or edit them.
- `sd config` keeps every plugin key (`hoa.*`, `sdw.*`, `songs.*`) in the per-machine `config.json`,
  and the fleet keys `sd.copilot_review` and `sd.fleet_owners` fall back to it while no row exists.

The operator dropped the branch-protection audit trail (note #23246),
so an accepted gap need not be read at the reviewed commit any more.

## Approach

### Repository declarations: one JSON column on the repo row

Migration 37 adds `repo.declarations`, a JSON object or NULL.
Its keys are the four kinds, `review`, `gate_reuse`, `check_scope` and `status`;
each value is the object the old file held, `$schema` dropped.
One column, not four: the four share one writer, one reader and one verb, and a fifth kind adds no migration.

- `sd_db.repos.set_declaration(connection, path, kind, value)` is the one writer.
  It refuses an unknown kind, a value that is not an object, more than `DECLARATION_BYTES` (16384) of JSON,
  and an unregistered path. `None` removes the kind.
  `sd_db.repos.declarations(connection, path)` reads the object.
  A store before 37 has no column and so holds no declaration: it reads `{}` for a row, a known answer.
  Code ahead of the hub's `sd-db migrate` then reads what the store holds, and the lane's gate passes before the migration.
- `sd-db repo declare PATH [KIND [JSON | off]]` prints all kinds, prints one, sets one or removes one.
  `bin/sd-db` checks the value with the pack reader's own validator before the library writes it,
  so the verb refuses what a reader would refuse; the library stays free of `bin/` imports.
  This is a new verb: `runner-merge`, `channels` and the others each set one fixed-vocabulary field,
  and none can carry a structured object without changing its meaning.
- `sd_lib.repo_declaration(root, kind)` is the one reader.
  It resolves `root` to its row through `registered_base`, as `repo_ci` does, so a linked worktree,
  a runner clone and a gate's detached worktree all read their repository's row.
  No database on the machine (`fleet_connection` answers `None`) reads as nothing declared.
  A failed open or read raises `DatabaseUnreadable`: unknown, never "not declared".
  So does a clone with no row whose origin two rows share: a guessed row would apply another repository's policy.

Each reader keeps its validator and its failure direction; only the source changes.

| Kind | Reader | No row | Unreadable |
| --- | --- | --- | --- |
| `review` | `sd-review` `load_policy`, so `sd-ship` and `setup-github` too | built-in default | `PolicyError`: the review and the merge gate refuse |
| `gate_reuse` | `sd_gate_receipts.keyed_by_tree`, `gates_itself` | head key | the gate returns a failure reading: no reuse, no record, no run |
| `check_scope` | `sd_check_scope.declaration` | full check | usage error (exit 2), as a malformed declaration already was |
| `status` | `sd_lib.load_acknowledgements`; `sd-ship merge` `acceptances` | no accepted gap | a problem line: every gap prints, the declared-gap merge refuses |

`sd-ship merge` reads the `status` declaration from the row at merge time, not at the reviewed head.
`parse_acknowledgements` takes the value instead of file text; one parser still serves both readers.

Bindings that named the files now name the row value:
`sd_ship_bindings.policy_files` and `sd_check_receipts.check_binding` hash the canonical JSON of the `review` declaration
in place of `.github/sd-review.json`, so a policy change still moves a review binding.
The gate binding already holds the scope decision and the receipt key kind, which are what the other two declarations decide.
`record_unless_moved` also compares the scope command the child ran with the one the binding named, so a row changed during a run records nothing.

`sd fleet stamp` stops proposing `.github/sd-status.json`.
For an owned repository GitHub reports unprotected and whose row declares no `unprotected` gap,
the plan prints the `sd-db repo declare` command instead; it writes no row, as a dry run writes nothing.
`forbids_ci` reads the row's `status` gaps; a declaration that does not read refuses the tracked half of the plan.
A `.github/sd-fleet.json` that still exempts the old path is accepted and ignored.

Rejected: reading the files as a fallback while no row exists.
That keeps two sources and the code that picks between them; the lead moves the values once, right after merge.

### Plugin and fleet settings: rows only where a database exists

`sd config get|set|unset|list` treats every plugin key (`<prefix>.<key>`, prefix not `sd`) as a fleet key:
a `setting` row named `<prefix>.<key>` when the machine has a workflow database, `config.json` only on a database-free install.
The fleet `sd.*` keys lose their file fallback the same way: with a database, the row alone answers.
A `config.json` line the row ignores is named on stderr, as today.

The machine-scoped `sd.*` keys stay in `config.json`: `gate_slots`, `gate_load_max`, `gate_settle_seconds`,
`gate_cache_gb`, `review_slots`, `lane_root`, `bulk_storage_root`, `privacy_patterns` and `external_reviews`.
Each describes one machine (its cores, its disks, its consent to send code out),
and a gate on a satellite must start when the hub does not answer. One fleet-wide row cannot hold them.

### Moving the values

Old code ignores plugin rows and already reads `sd.copilot_review` and `sd.fleet_owners` rows first.
So the lead writes the setting rows before the merge, and nothing reads them early.
Declarations need migration 37, and old code refuses a store newer than itself.
So the lead migrates and writes them right after the merge, then deletes each file in that repository's next pull request.
Between merge and move each reader sees no row: fail-closed, except review routing, which takes the built-in default.
Of 17 repository review policies, 16 differ from the default only in fields that relax nothing; the pack's own adds paths and is moved first.

## Non-goals

- The system side of sd:5109 (dashboard confs, `research.conf.py` keys, tool `.env` keys, the Settings view).
- `.github/sd-fleet.json`, workflow files, `dependabot.yml`: GitHub or the stamp reads them in the tree.
- Moving the values: the lead runs the commands in the pull request body after merge.
- Per-host setting rows for the machine-scoped keys.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| Migration 37 | `repo` gains `declarations` | Stops part way | `sd-db` backs up before migrating; the header's reverse drops the column and sets `user_version` 36 | `test_backup` `one_migration_back` runs the 037 reverse |
| `repo declare` write | One `UPDATE` of one row in a transaction | Bad kind, bad JSON, too large, unknown path, store before 37 | Refused before the write; nothing changes | `TheDeclarationsSetting`, `test_repo_declare_*` |
| Reader on a store before 37 | none | `no such column` | Reads `{}`: the store holds no declaration; the writer still refuses | `TheDeclarationsSetting.test_a_store_before_37_holds_no_declaration` |
| Reader, database down | none | Open or read fails | Review refuses, the gate fails unrun, the scope is a usage error, gaps print, the stamp refuses its tracked half | `RepoDeclarationTests`, per-reader unread tests |
| Reader, clone whose origin two rows share | none | No row for the path | `DatabaseUnreadable` naming the count | `RepoDeclarationTests.test_a_clone_whose_origin_two_rows_share_is_refused` |
| Gate run while the row changes | A receipt | The child ran another scope command | `record_unless_moved` records nothing | `record_unless_moved` scope-command test |
| Lead moves values after merge | Rows written, then files deleted | Stops between rows and deletions | Rows already win; rerunning `repo declare` with the same JSON is a no-op; deletion is a later commit in each repository | Idempotent write test; the body's commands are re-runnable |
| Gap between merge and move | Readers see no row | Review routes by default policy; gate reuse keys by head; declared-gap merges refuse | Fail-closed in each case; the lead runs the move first | Per-reader "no row" tests |
| `sd config set` plugin key | One `setting` row | Database write fails | `ConfigError` naming it; the file is not written in its place | `PluginSettingRowTests` |
| Lead writes setting rows before merge | Rows for plugin and fleet keys | Stops part way | Old code reads no plugin row; rerun writes the same values | The body's snippet is re-runnable |

## Acceptance criteria

- [ ] With a row and no file, `sd-review --explain` routes by the row's policy; with a file and no row, by the default.
- [ ] `sd-check --base` scopes to docs by the row; the gate keys by tree by the row.
- [ ] `sd-status` and `sd-ship merge` accept a gap the row declares and none a file declares.
- [ ] `sd config get songs.delivery_folder` reads the row and ignores the file line.
- [ ] `sd-db repo declare` refuses each extreme input (empty, nested, huge, wrong types) before writing.
- [ ] No reader under `bin/` opens `.github/sd-review.json`, `sd-gate-reuse.json`, `sd-check-scope.json` or `sd-status.json`.

## Risks

- A declaration change is no longer reviewed in a diff. The operator accepted this (note #23246).
- The GitHub Actions route workflow has no database, so it routes by the built-in policy. Actions CI is off on every managed repository.
- A database-free install of the public pack loses per-repository declarations and runs the defaults.
- Evidence: a review binding names the `review` declaration's hash; a gate receipt names the scope decision and the key kind.
  A row changed between prepare and merge moves the review binding and so re-reviews; a gate receipt under the old scope decision does not match the new one.
