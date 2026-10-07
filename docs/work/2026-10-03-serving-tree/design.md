# Design — serving tree

The requirements are in [prd.md](prd.md).

## Shape

A serving tree is a clean clone on a detached `HEAD`, at
`${XDG_DATA_HOME:-~/.local/share}/sd-ai-command-pack/serving`. It sits outside `~/repos`, so
repo-sync never reads it as a checkout. It is a separate clone, not a
worktree: nothing lists it as active work, and worktree cleanup cannot reach
it. It is detached because activation names a commit, not a branch.

`bin/sd_install.py` tells the modes apart by `git rev-parse --abbrev-ref HEAD`:

| HEAD | `--pull` | `--rollback` |
| --- | --- | --- |
| `main` | fast-forward and render, as before | refused |
| detached (`HEAD`) | fetch, detach at `origin/main`, render | detach at `previousCommit`, render |
| any other branch | refused | refused |

Both refuse tracked and untracked changes before they run git.

## The way back

`cmd_user` writes the receipt. It now records `previousCommit` through
`previous_commit(recorded, commit)`:

- a render at a new commit records the commit the receipt held;
- a render at the same commit keeps the recorded `previousCommit`, so a
  re-render does not forget the way back.

`--rollback` is an ordinary activation. The commit it leaves becomes the new
`previousCommit`, so a second `--rollback` undoes the first. It refuses a
receipt with no `previousCommit` and a commit the tree does not have.

## Activation (review round 1)

`_activate` ran the whole activation in the installer already loaded.
Review round 2 replaced that: see the next section.

- **Contract.** The next activation runs the target commit's installer. So
  `--pull` and `--rollback` refuse a target whose `bin/sd_install.py`
  declares no `ACTIVATION_CONTRACT`. An installer from before the serving tree
  rejects `--rollback`, and no second rollback could come back from it.
- **Put back.** A render that refuses or raises returns the tree to the
  commit it started from, and the receipt to its bytes before the run. The
  commands served and the receipt never disagree, so `--rollback` after a
  failed update still starts from the commit the receipt names.

## Activation (sd:1118 review round 2)

- **The target renders itself.** After the checkout, `_activate` runs the
  target commit's installer as `--user`, so a change to rendering applies in
  the update that brings it. The loaded installer only supervises.
- **Put back.** A target render that fails returns the tree to the original
  commit and the receipt to its bytes, then renders the original commit
  again with the loaded installer, which is that commit's. It renders only
  when the restored receipt names the tree: on a failed first `--serve` the
  receipt names the working checkout, which stays installed (review round 10).
- **Prune last.** Renders and links the new checkout drops are pruned only
  after its receipt is written, so a failed install deletes nothing of the
  last one (review round 11).
- **Renders recover.** A failed `cmd_user` restores every render it wrote,
  not only the Codex policies, so a failed target leaves none of its files.
  Every render is written to a scratch file and renamed over the old one, so
  a write that fails part way, as on a full disk, leaves the previous file
  whole for the restore (review round 14).
- **Recovery from the first change on.** `_activate` arms recovery before
  the tree's checkout moves, so a checkout git stops part way, a `.venv` link
  that cannot move, or a failed render all return the tree to the previous
  commit (review rounds 14 and 17). The code goes back first, with
  `--force`; `.venv`, the receipt and the re-render follow, and each is
  attempted when an earlier one fails. If git cannot move the code back,
  `.venv` stays with the code it was built for.

## `make setup` serves (sd:1118, second pass)

The ruling makes `make setup` the only step that moves the serving tree.
Its last line runs `bin/sd_install.py --serve` from the working checkout:

- **Clone.** A missing tree is cloned from the working checkout's `origin`
  into a spare directory beside it, detached at `origin/main`, then renamed
  into place. A clone cut short leaves no half-made tree.
- **Library.** One order, in `_activate`: build the target's environment,
  then check out the target and move `.venv` back to back, then render.
  The build is the target's own `make setup SERVE=no VENV=<slot>`, run in a
  scratch checkout of the target (`git worktree add --detach` beside the
  tree, removed and pruned after), with the caller's `MAKEFLAGS` and
  `VENV` removed, into `.venv-a` or `.venv-b`, whichever `.venv` does not
  resolve to; a `.venv` that resolves to neither is refused before any build
  (review round 16). A failed build moves nothing, so the previous code,
  environment and install serve on.
- **Build beside, not in place (review round 17).** Links and hooks run the
  tree's code, so checking out the target before its build ran new code on
  the old environment for the whole build. Two ways out: (a) build from a
  scratch checkout and move the code and `.venv` back to back; (b) two code
  slots behind one stable link. (a) holds, so it is taken: the environment
  holds copies, never a path into the code. `make setup` writes only under
  `$(VENV)`, pip installs the requirements and `sd_db` as copies, and the
  scripts and `pyvenv.cfg` name the slot. One thing reads the checkout: the
  `sd_db` downgrade guard compares with `<checkout>/.venv`, so the scratch
  checkout's `.venv` links to the live environment. What remains is the
  seconds git takes to check out, on each move and each put-back; (b)
  would close that too, at the cost of a second tree and a link every
  receipt, link and hook would name.
  Two slots, not a temporary directory renamed into place: a virtualenv's
  scripts name its path, and replacing one would delete the other, which
  the deletion guard forbids. `--provision-library --venv <slot>` installs
  `sd_db` into the slot, not into `.venv`. A link to the caller's
  environment broke when a lane worktree that ran `make setup` was removed
  (lane review, rounds 13 and 14). The clone's `info/exclude` names `.venv`
  and both slots, so `--verify` stays clean.
- **Hand-over.** `--serve` runs the tree's own installer as `--pull`, so the
  activation is the tree's code, as in the first pass.
- **One move at a time.** `--pull` and `--rollback` hold `fcntl.flock` on
  `<tree>.lock` from the fetch or receipt read through the render and any
  put-back; `--serve` holds it around the clone, and a run that waited finds
  the tree and clones nothing. A second run waits up to `SERVE_LOCK_WAIT`
  (600 s), so concurrent lane `make setup` runs succeed, then refuses with
  nothing moved, so a stuck run cannot hang every later one. Without it, two runs built the same slot and one published it
  half-built (review round 15). The kernel drops the lock with its process.
- **Links.** `link_plan` gains a fourth state, `recorded`: a link the
  receipt names, still at its recorded target. The install moves it to the
  new checkout with one rename, and puts it back on a failure. Any other
  link stays foreign and refuses the run.
- **Hooks.** The install adds the new checkout's hook commands, then drops
  the ones the receipt recorded for the last checkout, so each hook runs
  once. A hook the receipt does not name stays. A later failure puts the
  settings bytes back, unless another writer changed them (review round 6).
- **Opt-out.** `make setup SERVE=no` provisions without moving the tree,
  for a rollback that should stay put.

## Failure table (review round 17)

Every step of `--serve`, `--pull` and `--rollback`, in code order, built from
`bin/sd_install.py`. A step that moves no state needs no recovery; its
refusal is the whole answer. A step that moves state has a recovery and a
test, or a named follow-up. "What runs meanwhile" is the code and the
environment that live links and hooks run while the step is in progress.
"Original" is the commit the tree served when the run began.

| # | Step | State moved | If it fails here | Recovery | What runs meanwhile | Test |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | `--serve`: resolve the tree; refuse the tree itself or a path that is not a clone | none | refuses, exit 1 | nothing to undo | the previous install | `test_serve_refuses_to_run_from_the_serving_clone_or_without_origin`, `test_serve_refuses_a_path_that_is_not_a_clone` |
| S2 | take the lock for a first clone | lock | waits 600 s, then refuses | nothing moved | the previous install | `test_a_first_run_that_waits_too_long_clones_nothing` |
| S3 | read `origin`'s URL | none | refuses | nothing to undo | the previous install | `test_serve_refuses_to_run_from_the_serving_clone_or_without_origin` |
| S4 | clone into a spare directory, check it out | spare directory | reported, naming the spare | the spare stays for the operator; nothing serves from it | the previous install | `test_a_clone_that_fails_is_reported_and_nothing_runs` |
| S5 | write the slot excludes, rename the spare into place | spare, then tree | raises; the error names the path | nothing serves from it; a run that waited uses the tree | the previous install | `test_a_clone_that_cannot_be_renamed_into_place_runs_nothing`, `test_a_first_run_that_waited_for_another_clone_uses_it` |
| S6 | hand over to the tree's own `--pull` | the P and A rows | relays the exit code | the P and A rows | the previous install until A6 | `test_serve_reads_the_data_home_and_reports_the_clone_installer_exit` |
| P1 | `--pull`: refuse a branch other than `main`, or a dirty tree | none | refuses | nothing to undo | original, on its environment | `test_pull_refuses_a_dirty_serving_tree_and_moves_nothing`, `test_pull_still_refuses_a_checkout_on_another_branch` |
| P2 | take the lock | lock | waits 600 s, then refuses | nothing moved | original | `test_a_move_that_waits_too_long_for_the_lock_refuses_and_moves_nothing` |
| P3 | fetch `origin`, read `origin/main` | remote-tracking refs | refuses | nothing served moved | original | `test_a_serving_pull_that_cannot_fetch_or_find_origin_main_moves_nothing`, `test_a_fetch_that_will_not_finish_is_reported_and_not_raised` |
| R1 | `--rollback`: under the lock, refuse a branch, a dirty tree, or a missing or unknown `previousCommit` | lock | refuses | nothing moved | original | `test_rollback_refuses_without_a_previous_commit_off_a_serving_tree_dirty_or_unknown`, the P2 test |
| A1 | check the target's `ACTIVATION_CONTRACT` | none | refuses | nothing to undo | original | `test_a_target_whose_installer_predates_the_contract_is_refused` |
| A2 | read `HEAD`, the receipt bytes and the `.venv` link | none | refuses or raises | nothing moved | original | `test_an_unreadable_head_moves_nothing`, `test_an_unreadable_venv_link_moves_nothing` |
| A3 | pick the slot `.venv` does not resolve to | none | refuses a real directory or a link outside both slots | nothing moved | original | `test_a_real_venv_directory_is_refused_and_nothing_moves`, `test_a_link_outside_both_slots_is_refused_and_nothing_moves`, `test_an_absolute_link_to_a_slot_rebuilds_the_other_one` |
| A4 | check the target out into a scratch checkout beside the tree | scratch checkout, git's worktree entry | reported | the scratch checkout is removed and the entry pruned | original | `test_a_build_checkout_git_refuses_moves_nothing` |
| A5 | build the inactive slot with the target's `make setup SERVE=no` | inactive slot | fails, or cannot start `make` | the slot stays inactive; nothing else moved | original, on its environment, for the whole build | `test_the_tree_serves_its_own_commit_while_the_target_builds`, `test_a_failed_provision_keeps_serving_the_previous_commit`, `test_make_that_cannot_start_keeps_serving_the_previous_commit`, `test_a_failed_first_provision_leaves_no_venv_and_the_retry_builds_before_rendering` |
| A6 | check out the target in the tree | checkout | git refuses, or stops part way | F1, F2 | a mix of original and target files on the original environment, for the seconds git takes | `test_a_checkout_git_refuses_is_reported_and_nothing_renders`, `test_a_checkout_that_stops_part_way_is_put_back` |
| A7 | move `.venv` to the new slot | `.venv` link | raises | F1, F2 | the target's code on the original environment, from A6's end to this rename | `test_a_failed_link_switch_keeps_serving_the_previous_commit` |
| A8 | render with the target's `--user` (the U rows) | renders, links, hooks, excludes, receipt, prune | returns non-zero, or raises | the child restores its renders, links and settings; then F1 to F4 | the target, on its environment | `test_a_failed_render_puts_the_tree_and_the_receipt_back`, `test_a_render_that_raises_puts_the_tree_and_the_receipt_back_and_raises`, `test_a_failed_render_puts_the_venv_link_back` |
| A9 | the render child is killed (SIGKILL, out of memory) | part of the U rows | the child's recovery never runs | F1 to F4 re-render original; a render the target added and original does not name stays | the target, then original | Follow-up sd:2932 (P4) |
| A10 | the supervising run itself is killed | any | nothing recovers | the next `make setup` fetches and activates `origin/main` from whatever the tree holds | whatever the kill left, until the next `make setup` | `test_the_next_pull_converges_after_a_run_was_killed_part_way` |
| F1 | put-back: check out original with `--force` | checkout | reported with the command to run; stops | the operator runs it, then `make setup` | the target's code, with `.venv` as it was at the failure | `test_a_put_back_git_refuses_after_a_failed_checkout_names_the_command`, `test_a_put_back_git_refuses_names_the_split_and_the_command` |
| F2 | put `.venv` back | `.venv` link | reported; the put-back goes on | `make setup` again | original's code on the target's environment, until the next `make setup` | `test_a_link_that_cannot_go_back_still_puts_the_tree_back` |
| F3 | put the receipt bytes back, through a scratch file | receipt | reported; the target's receipt stays whole; stops | `make setup` again | original | `test_a_receipt_that_cannot_go_back_is_left_whole_and_reported` |
| F4 | render original again, only if the receipt names the tree | the U rows | reported with the command to run | original's own recovery | original | `test_a_put_back_whose_re_render_fails_says_so`, `test_a_failed_first_serve_leaves_the_install_of_another_checkout` |
| F5 | release the lock | lock | the kernel drops it with the process | none needed | — | the P2 and S2 tests |
| U1 | `--user`: write each render through a scratch file | renders | the previous file stays whole | restored from backups | each render is whole, old or new | `test_a_render_that_fails_midway_leaves_the_previous_render_whole` |
| U2 | link the commands | links | raises | the recovery stack undoes each link | each link runs the checkout it names, on that checkout's environment | the link recovery tests in `LinkEdgeCaseTests` |
| U3 | add and remove hooks | settings | raises | settings restored from their bytes | each hook runs the checkout it names | `test_a_failed_hook_removal_puts_the_added_hooks_back`, `test_a_failure_after_the_hook_move_puts_the_hooks_back` |
| U4 | add the excludes line and git config | global excludes | left in place | additive and idempotent; not undone | as U2 | `test_a_failure_after_the_hook_move_puts_the_hooks_back` |
| U5 | write the receipt | receipt | the old receipt stays whole | renders, links and settings restored | as U2 | `test_a_failure_before_the_receipt_prunes_nothing_of_the_last_install` |
| U6 | prune what the new receipt drops | renders, links | stale files stay, and no receipt names them | Follow-up sd:2927 (P4) | the new install | none |

## Verification

`verify_source` is unchanged. It compares `HEAD` with the receipt's commit
and reads `git status --porcelain`. A detached tree passes when it is clean
and at the rendered commit.

## Alternatives not taken

- A worktree of the working clone: it shares refs, and the lane's worktree
  cleanup and the fleet views would see it as work.
- A serving branch: activation would follow a moving name, not a commit.
