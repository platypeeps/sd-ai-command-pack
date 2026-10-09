# Design — serving tree

The requirements are in [prd.md](prd.md).
sd:3009 replaced the sd:1118 environment slots with a plain clone (operator ruling, 2026-10-08).
sd:3111 serves the working checkout's `HEAD`, not `origin/main` (operator ruling, 2026-10-08).

## Shape

A serving tree is a plain clone on a detached `HEAD`, at
`${XDG_DATA_HOME:-~/.local/share}/sd-ai-command-pack/serving`. It sits outside `~/repos`, so
repo-sync never reads it as a checkout. It is a separate clone, not a
worktree: nothing lists it as active work, and worktree cleanup cannot reach
it. It is detached because it serves a commit, not a branch: the working checkout's `HEAD`, so a pinned
checkout pins the commands too.

Git and `make setup` move it; the installer keeps no state of its own for it:

| Action | Command |
| --- | --- |
| Update | `make setup` in the working checkout |
| Roll back | in the tree, `git checkout --detach <commit> && make setup SERVE=no && .venv/bin/python bin/sd_install.py --user`; `git reflog` lists the commits it served |

`make setup` builds the tree's own `.venv` and ends with `bin/sd_install.py --serve`.
A rollback skips that step with `SERVE=no` and renders with `--user`: a commit from before sd:3009 refuses `--serve`
in the tree, and one from before sd:1118 has no such step.
In the tree, `--serve` renders it with `--user`.
In any other checkout, `--serve` clones `origin` into the tree the first time.
It then runs `git fetch <working checkout> HEAD` and `git checkout --detach FETCH_HEAD` in the tree, so a commit
`origin` lacks still arrives.
It splits `make setup` into `make setup SERVE=no` and the tree's own `--serve` under the tree's `.venv` python,
so `--home` and `--bin-dir` reach the tree's installer and the render reads the `sd_db` just built.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| Clone into a spare path, then rename | nothing until the rename | clone or rename fails | the spare stays and nothing serves from it; remove it, then rerun `make setup` | `test_a_clone_that_fails_is_reported_and_nothing_runs`, `test_a_clone_that_cannot_be_renamed_into_place_runs_nothing` |
| Fetch the working checkout's `HEAD` into the tree | the tree's `FETCH_HEAD` | no `HEAD` to fetch, or the fetch fails or times out | refused by name, nothing moved; the tree serves on | `test_a_fetch_or_checkout_that_fails_moves_nothing`, `test_a_fetch_that_will_not_finish_is_reported_and_not_raised` |
| Detach the tree at `FETCH_HEAD` | the tree's `HEAD` | git refuses, such as over local changes | tree unchanged; git names the cause | `test_a_fetch_or_checkout_that_fails_moves_nothing` |
| The tree's `make setup SERVE=no` | `HEAD` and `.venv` | setup fails, or make cannot start | error names the tree; fix it, then run `make setup` there, or roll back | `test_a_failed_setup_is_reported_and_nothing_renders`, `test_make_or_a_python_that_cannot_start_is_reported` |
| The tree's `--serve` render | renders, links, hooks, receipt | render fails | `cmd_user` puts back the earlier renders, links and hooks; the exit is relayed | `test_serve_reads_the_data_home_and_reports_the_tree_installer_exit` |
| Roll back in the tree to an older commit | `HEAD`, `.venv`, renders | that commit's `--serve` refuses in the tree, or it has none | `SERVE=no` skips it; the commit's own `--user` renders; `make setup` in the working checkout returns | `test_the_documented_rollback_and_update_cross_a_commit_from_before_the_plain_clone` |
| `make setup` in a working checkout on a pre-sd:3009 commit | nothing | its `--serve` calls the tree's `--pull`, which refuses | update the working checkout, then `make setup` | `test_pull_refuses_a_detached_checkout` |
| Retire the A/B slots | `.venv-a`, `.venv-b`, `serving.lock` | `.venv` is still a link | nothing removed; the next `make setup` retires them | `test_serve_in_a_tree_the_ab_slots_served_retires_them` |
| Links outside the bin directory, such as `~/bin/common` | nothing | they shadow the tree's commands | left alone; `--status` and `--verify` report the shadow | `test_links_into_the_working_checkout_outside_the_bin_dir_are_left_and_reported` |

## What it gives up

While `make setup` rebuilds `.venv`, served commands find it marked mid-provision and load no `sd_db`.
Between the checkout and the render, the tree's new code runs with the last render's links and hooks.
sd:1118 built beside the tree to close both windows, at 688 installer lines and 19 review rounds.
Before sd:1118 the working checkout had the same windows.

## Moving over from the A/B slots

`make setup` detaches a `.venv` link and builds a directory in its place, so a tree with `.venv -> .venv-b`
gets its own `.venv` on its first run. The tree's `--serve` then removes `.venv-a`, `.venv-b` and the
`serving.lock` beside the tree. It removes nothing while `.venv` is still a link.

## Verification

`verify_source` is unchanged. It compares `HEAD` with the receipt's commit
and reads `git status --porcelain`. A detached tree passes when it is clean
and at the rendered commit.

## Alternatives not taken

- A worktree of the working clone: it shares refs, and the lane's worktree
  cleanup and the fleet views would see it as work.
- A serving branch: the tree would follow a moving name, not a commit.
- The sd:1118 slots, lock and receipt-driven link moves: sd:3009 deleted them.
