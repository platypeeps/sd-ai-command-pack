---
title: sd_db moves into the pack; the system pin retires
created: 2026-10-10
item: sd:2997
---

# Design: `sd_db` moves into the pack; the system pin retires (sd:2997)

## Status

The operator ruled the direction on 2026-10-08 and accepted D1 to D5 on 2026-10-10 (see Decisions).

## Problem

The workflow library `sd_db` lives in `platypeeps/system` (`local-sd-db/`).
Its main callers live in this pack (`bin/`, about 20 modules import it).
So one change to the schema, its migrations and their callers spans two repositories:

- The pack pins a system commit in `.sd-system-rev` for its gate.
  Each migration that pack code needs costs a pin-bump pull request.
- `make setup` installs a copy from the system checkout (`provision_library`).
  Four guards keep that copy honest: the provisioning lock, the schema downgrade guard,
  the ancestry check and the post-merge reprovision with its schema refusal (sd:2108, sd:3249).
- The system checkout must move before the pack's `make setup` (sd:3218).
- A satellite installs the hub's build by exporting `HEAD:local-sd-db` from its system checkout (sd:2802).

Operator ruling, 2026-10-08: move `sd_db` into the pack.
Delete `.sd-system-rev` and the pin-bump pull requests.
One repository owns the schema, the migrations and the callers. System keeps machine tools only.

## What exists today

Pack side:

| Piece | Where | What it does |
| --- | --- | --- |
| `import_sd_db` | `bin/sd_lib.py` | imports `sd_db` from `PATH`'s Python, then from the pack's `.venv` |
| `provision_library`, `library_pin`, `LIBRARY_TAGS` | `bin/sd_install.py` | installs `git+file://<system>@<ref>#subdirectory=local-sd-db` into `.venv` |
| `provision_guarded`, `provisioning_lock`, `ancestry_refusal`, `installed_library_commit` | `bin/sd_install.py` | the lock and the older-over-newer refusals |
| `downgrade_refusal`, `schema_version` | `bin/sd_library_guard.py` | refuses a copy built for an older schema |
| `reprovision_after_merge`, `schema_refusal`, `MIGRATE_STEPS` | `bin/sd_install.py`, called from `bin/sd-ship` | installs a system merge that touched the library, unless its schema differs (sd:3249) |
| `.sd-system-rev` | root | the gate's system ref |
| `provision-gate-env.py` | `.github/scripts/` | builds the gate's `.venv` with `sd_db` at the pin |
| `tests/test_system_pin.py` | `tests/` | fails when the installed library is older than the pin |

System side (read-only for this item):

| Caller | How it reaches `sd_db` |
| --- | --- |
| `local-sd-db/sd-db.sh` | runs the checkout's package or the pack venv's copy (`choose_library`, `SD_DB_LIBRARY`) |
| `local-project-dashboard` | runs under the pack's `.venv/bin/python -I`; refuses a copy older than the checkout's last library commit (sd:962) |
| `local-machine-setup/machine-setup.sh` | `sd-db.sh init` and `repo list`; `"$SD_DB_PYTHON" -I -m sd_db.satellite`; doctor reads `local-sd-db/sd_db/schema.py` |
| `local-repo-sync/repo-sync.sh` | knows the system checkout by `local-sd-db/sd_db/schema.py`; prints migrate steps from its `SCHEMA_VERSION` |
| `sd_db.self_install` | exports `HEAD:local-sd-db` from the system checkout |
| cron examples, the `sd-serve` LaunchAgent | name `local-sd-db/sd-db.sh` (`backup`, `serve`) |
| `tests/ci-native.sh`, `tests/run-macos-only.sh` | `pip install ./local-sd-db` into a throwaway venv |
| `local-sd-db/tests` | 86 files; the acceptance tests drive a pack checkout (`SD_ACCEPTANCE_PACK`) |

## Approach

**Where the code goes.** `local-sd-db/sd_db/` moves to `lib/sd_db/` in the pack.
`pyproject.toml` and `_build.py` move to `lib/`. The tests move to `tests/sd_db/` and join `make check`.

**How the pack loads it.** From its own tree. `import_sd_db` puts `<checkout>/lib` first on `sys.path`.
`bin/` and `lib/` then always come from one commit. A worktree runs its own library.
The hub's pack checkout is pinned (sd:3097), so the library moves only when `refresh` moves the checkout.
That is the property the installed copy gave; the pinned checkout now gives it.

**How system reaches it.** Through the pack checkout, one path: `SD_PACK_CHECKOUT`, default
`~/repos/platypeeps/sd-ai-command-pack`, as `dashboard.sh` and `sd-db.sh` name it today.
`sd-db.sh` moves to the pack as `bin/sd-db`. It replaces `local-sd-db/sd-db.sh`.
System keeps `local-sd-db/sd-db.sh` as a short shim that runs the pack's `bin/sd-db` until no caller names it.

**What the system gate tests against.** The pack checkout's `lib/` at its `HEAD`. No pin file.
On the hub that checkout is the pinned, deployed pack. A system change that needs newer library code waits for the refresh that deploys it.
The rule becomes: a library change lands in the pack first; its system callers follow.

**History.** A plain copy, not a subtree merge. The copy commit names the system commit it came from (`S` below).
`git -C system log -- local-sd-db` at the deletion's parent keeps the 90 commits readable.
A subtree merge would put an unrelated root and a merge commit into a squash-merged repository.
Recorded as a routine choice (sd note).

## Non-goals

- Moving the dashboard (`local-project-dashboard`); D3 makes it a later item.
- Changing the schema, a migration or any `sd_db` behavior during the move.
- Automatic migration on a satellite: satellites never migrate; they follow a migrated hub.
- Carrying system's commit history into the pack.

## Mechanisms

| New or changed | Replaces |
| --- | --- |
| `lib/sd_db` in the pack | `local-sd-db/sd_db` in system |
| `bin/sd-db` (moved, same verbs) | `local-sd-db/sd-db.sh` |
| `import_sd_db` reads `<checkout>/lib` first | `provision_library` and the `.venv` copy |
| The system gate installs from `SD_PACK_CHECKOUT` | `pip install ./local-sd-db` |

Deleted at the end: `.sd-system-rev`, `test_system_pin.py`, the `sd_db` part of `provision-gate-env.py`,
`provision_library`, `library_pin`, `LIBRARY_TAGS`, `provision_guarded`, `provisioning_lock`, `ancestry_refusal`,
`installed_library_commit`, `reprovision_after_merge`, `schema_refusal`, `sd_library_guard.py`,
`sd-db.sh release` and the `sd-db-v*` tags, `SD_DB_LIBRARY` and `choose_library`,
the dashboard's library-staleness refusal (sd:962), and `sd_db.self_install` (D4).
Each deletion greps both repositories first; the step's PR body quotes the grep.

## Slices

Each step is one PR, in order: step 1 (pack), step 2 (system), step 3 (pack), step 4 (system).
Every machine keeps working between steps.
A satellite moves only to a pair the hub published in `hub-pin`, so it never mixes steps.
Steps 1 and 3 are design and concurrency work; run them on Opus.
Step 2 is mostly path edits plus the shim and the `repo-sync` detection; Sonnet can run it with the failure table.

**Step 1, pack: copy and load from the tree.**
1. Copy `local-sd-db` at system commit `S` into `lib/` and `tests/sd_db/`. The commit message names `S`.
2. `import_sd_db` reads `<checkout>/lib` first, then today's two tries.
3. `bin/sd-db`: `sd-db.sh` with its folder pointed at `lib/`.
4. `make setup` still installs a `.venv` copy, now from this checkout's `lib/` at `HEAD` (`git+file://<pack>@HEAD#subdirectory=lib`).
   System callers still read that copy until step 2. The guards stay and read `lib/`.
5. `reprovision_after_merge` triggers on a pack merge that touched `lib/`, not on a system merge.
6. The gate builds `.venv` from the worktree's own `lib/`. Delete `.sd-system-rev` and `test_system_pin.py`.

Leaves working: every machine runs today's callers. Pack `bin/` reads `lib/` (`S`); system callers read the `.venv` copy, also `S`.
From this merge on, the pack owns `sd_db`. System's `local-sd-db` is frozen at `S` until step 2 merges; record the freeze in an sd note.
A library change during the freeze goes to the pack.

**Step 2, system: callers move to the pack.**
1. Precondition: `git diff --quiet S origin/main -- local-sd-db` in system, and the hub's pack checkout contains step 1.
   The builder quotes both in the PR body. A non-empty diff is ported to the pack first.
2. `local-sd-db/sd-db.sh` becomes a shim: `exec "$SD_PACK_CHECKOUT/bin/sd-db" "$@"`.
   With no `bin/sd-db` there, it exits 1 and names `repo-sync.sh refresh` or `follow`.
3. The dashboard bootstrap adds `<pack>/lib` to `sys.path`; its staleness refusal goes.
4. `machine-setup.sh` runs `bin/sd-db` for `init`, `repo list` and the satellite check; doctor reads `<pack>/lib/sd_db/schema.py`.
5. `repo-sync.sh` knows the system checkout by `local-repo-sync/repo-sync.sh` alone.
   It reads `SCHEMA_VERSION` from the pack's `lib/sd_db/schema.py`. The system-first order (sd:3218) stays; it costs nothing.
6. `tests/ci-native.sh` and `tests/run-macos-only.sh` install `sd_db` from `$SD_PACK_CHECKOUT/lib` at its `HEAD`, and print that sha.
7. Cron examples and the `sd-serve` example plist keep the shim path; nothing installed needs editing.
8. Delete `local-sd-db/sd_db`, `local-sd-db/tests`, `_build.py` and `pyproject.toml`.
   The README keeps one paragraph: the library lives in the pack; the shim is for old callers.

Leaves working: installed cron jobs and LaunchAgents through the shim; the dashboard and machine-setup through the pack's `lib/`.

**Step 3, pack: one copy.**
1. `make setup` installs no `sd_db`. It runs `pip uninstall -y sd-db` in `.venv`,
   so a caller that still reads the venv copy fails loudly instead of running stale code.
2. Delete the provisioning code, the guards, `reprovision_after_merge` and its `sd-ship` call (list above).
3. Reword the "install the current system/local-sd-db build" refusals in `bin/` to name `make setup` in the pack.
4. Delete `sd_db.self_install` (D4); `BuildMismatch` names `repo-sync.sh follow`.

Leaves working: every caller reads the pack's `lib/`; a missed caller fails with `ImportError` rather than running stale code.

**Step 4, system: retire the shim.**
After the operator's config folder, LaunchAgents and cron jobs name `bin/sd-db`
(`machine-setup.sh` doctor lists any left), delete `local-sd-db/` and the root `CLAUDE.md` lines that name it.

Leaves working: callers name `bin/sd-db`; nothing names `local-sd-db`.

## Schema migration after the move

Today a system merge that bumps the schema installs nothing until a hand migrate (sd:3249).
Then `refresh` prints the steps and the operator runs them.

After step 3, a merge installs nothing at all: the hub's pack checkout is pinned and the lane skips its fast-forward.
`refresh` is the one point where new library code reaches the hub. D2 sets what it does there.

D2: inside `refresh`'s existing drain, when the database's schema version is below the target library's `SCHEMA_VERSION`.
The check reads the database and the library, never the checkout movement, and runs at every `refresh`: a rerun after a kill finds the same pending migrations.

1. Stop the dashboard, the runner and `sd-serve` (launchd `bootout`).
2. `bin/sd-db backup`. A failure refuses with nothing moved.
   A backup taken before `migrate` is not owned by retention, so it stays until the operator removes it; a rerun reuses the newest such backup at the database's current version.
3. Move system, then the pack; run `make setup`. A rerun with both already at target skips this step.
4. `bin/sd-db migrate`. Each migration is its own transaction, so a failure can leave earlier ones committed.
   On failure, read the database's schema version. If it is still the old version, move the pack back to the old sha (the follow rollback, sd:3218).
   If it moved, first restore the step 2 backup with `bin/sd-db restore`, which proves the copy, then move the pack back. Old code never starts on a newer database.
   If that restore fails, leave the services stopped, push no `hub-pin`, and report both errors: the operator decides.
5. Start the three services. A library change without a schema change restarts them too:
   the running `sd-serve` refuses sessions with `HubRestartNeeded` once its files change.
6. Push `hub-pin` only after step 5. Satellites follow only a migrated hub.

Before step 5 and before step 6, `refresh` reads the schema version again. Below the library's version, it does not start services or push: it runs steps 2 and 4, whatever the checkouts did.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| 1 merge | pack `main` holds `lib/sd_db` = `S` | system merges a library change after `S` | step 2's precondition refuses; port the delta to the pack | step 2 PR quotes `git diff --quiet S origin/main -- local-sd-db` |
| 1 refresh (hub) | pack checkout at step 1; `.venv` copy from `lib/` | `make setup` dies mid-install | the `sd-provisioning` marker refuses borrowing; rerun `make setup` | existing marker test; new: provision from `lib/` refuses a schema below the database's |
| 1 refresh (hub) | `bin/` imports `lib/`, system callers import `.venv` | the two differ | none needed: both come from one pack sha | new: `import_sd_db` resolves `<checkout>/lib` before `.venv` |
| 1 follow (satellite) | pair moves to the hub's | self-install exports system `HEAD:local-sd-db` (`S`) while the hub runs `lib/` | none needed: the digest hashes relative paths and bytes, equal at `S` | new: `tree_digest` of `lib/sd_db` at step 1 equals `local-sd-db/sd_db` at `S` |
| 2 merge | system callers name the pack | a machine's pack predates step 1 | the shim exits 1 and names `refresh` or `follow`; nothing writes | new shim test with a pack checkout that has no `bin/sd-db` |
| 2 refresh (hub) | system moves, then pack | the pack move fails after system moved | none needed: the precondition put step 1 on the hub, so `bin/sd-db` exists | precondition quoted in the PR body |
| 2 older state | installed cron jobs and plists name `local-sd-db/sd-db.sh` | path removed | the shim keeps the path until step 4 | example-job tests run through the shim |
| 2 older state | `repo-sync` knew system by `local-sd-db/sd_db/schema.py` | system read as an unknown checkout | detect by `local-repo-sync/repo-sync.sh` | new `repo-sync` test on a system tree without `local-sd-db/sd_db` |
| 3 merge | `.venv` has no `sd_db` | a missed caller imports the venv copy | it fails with `ImportError`, not stale code; fix the caller | new: after `make setup`, `.venv/bin/python -I -c 'import sd_db'` fails |
| 3 older state | a satellite venv copy from self-install | stale copy imported | follow's `make setup` uninstalls it | same test, run against a venv with a planted copy |
| migrate (D2) | services stopped | backup fails | refuse, start services, nothing moved | new `refresh` test with a failing backup double |
| migrate (D2) | pack moved, schema unchanged | the first pending migration fails | its transaction rolls back; move the pack back; start services; no `hub-pin` push | new `refresh` test against a real database: a first migration that fails leaves the old version, the old sha and no tag push |
| migrate (D2) | pack moved, schema partly moved | a later migration fails after an earlier one committed | restore the step 2 backup, then move the pack back; start services; no `hub-pin` push | new `refresh` test against a real database with two real migrations, the second failing: the version reads the old one after recovery, the restore row names the step 2 backup, old code opens it |
| migrate (D2) | schema partly moved, pack moved | the restore also fails | services stay stopped; no `hub-pin` push; both errors reported; the operator decides | same test with a failing restore: services stay down and the report names both errors |
| migrate (D2) | migrated, services down | `refresh` killed before start | the next `refresh` reads the version at target, then starts the services and pushes | new test: second run with checkouts at target and a migrated database starts services |
| migrate (D2) | pack moved, one migration committed, services down | `refresh` killed before the rest | the next `refresh` reads the version below target, takes a backup, migrates the rest, then starts services and pushes; on a failure it follows rows above | new test against a real database: kill after the first of two migrations; rerun with checkouts at target finishes both before any start |
| migrate (D2) | pack moved, services down | `refresh` killed before `migrate` starts | same: the version reads below target, so the rerun migrates before starting anything | new test: kill between step 3 and step 4; rerun migrates first |
| migrate (D2) | services down after a failed restore | the operator runs `refresh` again | the version check runs first: below target it backs up and migrates; it never starts services on an unmigrated database | new test: rerun after the failed-restore row starts nothing until the version matches |
| rollback | revert step 3 | `.venv` copy returns | `make setup` installs from `lib/` again | none new: step 1 tests cover that path |
| rollback | revert step 2 after a later schema bump | system's frozen copy is older than the database | `SchemaTooNew` refuses; nothing is written | none new: existing `SchemaTooNew` tests; revert in reverse order only |

## Guards that the steps skip

- Step 3 deletes the downgrade and ancestry guards. What they protected, an older copy over a newer one,
  cannot happen with no copy. The pinned checkout and `refresh` take that role. Test: none needed; named here.
- Step 3 deletes the post-merge schema refusal (sd:3249). A merge installs nothing, so nothing can install a schema-bumping copy.
- Step 2 deletes the dashboard's staleness refusal (sd:962). The dashboard reads the deployed checkout; there is no copy to go stale.

## Decisions

Operator, 2026-10-10.

- D1. System callers read the library from the pack checkout's `lib/`, path from `SD_PACK_CHECKOUT`.
- D2. `refresh` stops services, backs up, migrates and restarts inside its drain; `hub-pin` waits for it.
- D3. The dashboard stays in system for this item and reads the pack's `lib/`; its own move is a later item.
- D4. Satellite self-install (sd:2802) is deleted in step 3; follow moves the pack to the hub's sha, which is the hub's build.
- D5. `sd-db.sh` moves to the pack as `bin/sd-db`; a system shim keeps old paths until step 4.

## Acceptance criteria

1. The pack has no `.sd-system-rev`; `grep -rn sd-system-rev` over both repositories finds only archives.
2. `make check` in the pack runs the `sd_db` suite from `tests/sd_db/`.
3. A pack worktree that changes `lib/sd_db` runs its own library under `bin/sd`.
4. System has no `local-sd-db/sd_db`; its gate prints the pack sha it tested against.
5. On the hub and on one satellite after step 3: `sd task show 1`, the dashboard, `sd-serve`, a backup job and `repo-sync follow` all work.
6. One schema-bumping pack merge after step 3 reaches the hub through `refresh` with the D2 flow, and a satellite follows.

## Risks

- A system caller that imports `sd_db` some way this design did not list keeps reading the `.venv` copy until step 3 removes it.
  Step 3's uninstall turns that into a loud failure; the step 2 builder greps for `sd_db` outside `local-sd-db` first.
- The freeze depends on the lane: a system PR touching `local-sd-db` after step 1 must not merge.
  Step 2's precondition catches it late, not early; the accepted cost is one port.
- The D2 flow stops services on every library change at `refresh`. A refresh with no library change stops nothing.
