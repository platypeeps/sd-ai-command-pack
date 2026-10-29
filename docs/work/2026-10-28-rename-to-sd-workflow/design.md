---
title: Rename the pack repository and checkout to sd-workflow
created: 2026-10-28
item: sd:6027
---

# Design — rename-to-sd-workflow

The item's row holds status, progress and decisions; this page holds the shape.

## Problem

The pack is the workflow now, dashboard included (sd:5987), but its name still says "command pack".
The operator ruled the rename (grill Q51) and its scope (note #30498):
rename the GitHub repository to `sd-workflow`, move the checkout to `~/repos/platypeeps/sd-workflow` on all three machines,
leave a symlink at the old path for the transition, repair worktrees, re-key the database, and update tracked references.
`~/.config/sd-ai-command-pack` and `~/.local/share/sd-ai-command-pack` keep their names.

The old path is a key, not just a location. On the hub, 2026-10-28:

| Where | What names the old path |
| --- | --- |
| Workflow database | `repo.path` and `repo.remote`, and the `repo` column of `item` (1078 rows), `cost`, `repo_protection`, `runner_lease`, `runner_run` and `shadow` |
| `runner-journal/` beside `sd.db` | 2 of 108 records; each carries a sha256 of its record |
| Checkout | `.venv` (absolute shebangs), 3 worktrees, `origin` URL |
| Config folder | 2 launchd plist templates, `repo-sync/repos.{work,personal}.conf`, 8 cron jobs |
| Home | 20 symlinks under `~/.local/bin` and `~/.claude`, 2 permission lines in `~/.claude/settings.json` |
| Tracked files | 382 lines in 83 pack files, 113 lines in 75 system files (`docs/work` excluded) |

Hooks run from `~/.local/share/sd-ai-command-pack/serving/`, which keeps its name, so no hook path changes.
Free text that names the old path (note and state bodies, judgments) is history and stays as written.

## Approach

One cutover on the hub inside a stop window, then two reference PRs through the lane, then the satellites.

- The database stores a repository as its resolved, `~`-relative path (`sd_db.paths.store` resolves).
  After the re-key, a command run through the old-path symlink resolves to the new key, so old spellings keep working.
- The re-key follows `docs/sd-db.md` § Renaming a repository: there is no rename verb (sd:3172), and none is added here.
  It changes the keyed rows and the runner journal in one window, bracketed by `bin/sd-db backup`.
- GitHub redirects the old remote URL, so a satellite that still fetches the old URL keeps working until it moves.
- Rejected: change the tracked references first and move later. Every default path would point at a missing checkout until the move.
  Moving first keeps every old reference working through the symlink.
- Rejected: add a rename verb. It runs once; the documented procedure covers it (ask-before-adding rule).

## Non-goals

- Renaming `~/.config/sd-ai-command-pack`, `~/.local/share/sd-ai-command-pack` or the `serving/` copy (note #30498).
- Rewriting history: note, state, judgment and archived `docs/work` text.
- Moving system tools into the pack (grill Q69); that wave is its own item.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| 1. Preflight | none | pack lane not empty, a builder or worktree holds the checkout, a gate slot held | stop; rerun when `sd gate status --json` shows no holders and the lane is empty | `sd-ship lane` list and `git worktree list` read before step 2 |
| 2. Stop | `sd-serve`, dashboard, runner, cron jobs paused | a job starts mid-window | `launchctl bootout` each label; check `launchctl list` before step 3 | label list empty for `sd-*` and paused jobs |
| 3. Backup | backup copy | backup exits non-zero | stop; fix the cause; nothing else moved yet | backup exit 0 |
| 4. GitHub rename | remote repository name | rename refused or name taken | nothing local moved; retry or stop | `get_file_contents` on `platypeeps/sd-workflow` |
| 5. Move checkout | directory moved, symlink at old path | `mv` fails half-way (same volume: atomic) | `mv` back, remove the symlink | `test -L old && test -d new/.git` |
| 6. Repair | worktree links, `origin` URL, `.venv` rebuilt | `make setup` fails | old `.venv` is unusable after the move; rerun `make setup`; services stay stopped until it passes | `.venv/bin/python -c 'import sd_db'` |
| 7. Re-key DB | keyed rows rewritten in one transaction | a column missed, transaction aborted | aborted transaction moves nothing; restore from step 3's backup if a commit was partial | `SELECT count(*)` of old key in every `repo` column returns 0 |
| 8. Re-key journal | 2 journal files rewritten with fresh sha256 | a digest wrong | rewrite from the backup copy | `bin/sd-db backup` exit 0 ("rows and journal agree") |
| 9. Config | plist templates, `repos.*.conf`, cron jobs, settings permissions, symlinks | a template still names the old path | old path still resolves via the symlink; fix and rerun `machine-setup.sh status` | `machine-setup.sh status` shows no drift |
| 10. Start | services and jobs back | a service on the old build or path | `dashboard.sh health`; kickstart any stale service | health exits 0; `sd today` reads |
| 11. Reference PRs | tracked lines in pack, then system | the lane gate fails on a missed reference | fix in the PR; the symlink keeps the old path working | `git grep 'platypeeps/sd-ai-command-pack'` returns only the kept config and data names |
| 12. Satellites | each satellite's checkout, symlink, setup | a satellite session holds the checkout | ask its session to stop; the hub keeps working meanwhile | satellite `machine-setup.sh status` clean, `sd today` reads |
| 13. Remove symlinks | old-path symlinks gone | a caller still uses the old path | recreate the symlink; fix that caller | an item (below) closes only after a week with no old-path use |

## Slices

1. Cutover on the hub, steps 1-10, run by the lead in one window; no PR. It leaves every machine working: the hub through the new path and the symlink, the satellites unchanged.
2. Pack PR: tracked references to the new path and the new repository name, excluding the kept config and data names. The lane runs from the new path.
3. System PR: the same for system (`SD_PACK_ROOT` defaults, bin-links, cron examples, Makefile).
4. Satellites, steps 12: work, then terra, through their sessions.
5. A later item removes the symlinks once a week passes with no old-path use.

## Acceptance criteria

- [ ] `git -C ~/repos/platypeeps/sd-workflow remote get-url origin` prints `git@github.com:platypeeps/sd-workflow.git` on all three machines.
- [ ] No row in any `repo` column of the database names `~/repos/platypeeps/sd-ai-command-pack`.
- [ ] `bin/sd-db backup` exits 0 after the re-key.
- [ ] `machine-setup.sh status` shows no drift on the hub and both satellites.
- [ ] The first pack merge after slice 2 lands through the lane and its post-merge exits 0.
- [ ] `git grep -n 'sd-ai-command-pack'` in pack and system lists only the kept config and data paths and history.

## Risks

- The window stops every lane on the hub, the mezmo lanes on work included while `sd-serve` is down. Accepted: about 30 minutes, run when the lanes are empty.
- A satellite's build digest could change with the path and trip `BuildMismatch` until it moves. Slice 4 follows slice 1 the same day.
- A hard-coded absolute path outside the inventory (another repository, a plist on a satellite) breaks only when the symlink goes; slice 5 waits a week for that.
- The 382 pack lines include the kept config and data names; slice 2 must not rewrite those. Its review checks each kept name.
