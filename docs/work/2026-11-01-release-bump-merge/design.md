---
title: Release chain PR 2, the deploy bump and its merge
created: 2026-11-01
item: sd:7014
branch: docs/sd-7014-design
---

# Design — release-bump-merge

## Problem

PR 1 (sd:6881) tags a release after a lane merge and runs `verify`; a
policy that names a `deploy_repo` is refused. The rest of the hand
release (0.11 to 0.17.2) is still manual: set the image tag in the deploy
repository, open its PR, merge it once green, verify the rollout.

Build 363 wrote that code and went through seven review rounds. Each round
found a new instance of a class it had not listed: file reads that stripped
whitespace, terminal paths that skipped `verify`, acts checked against the
wrong policy keys, the version form, and a merge-queue add read as merged.
This page lists every step's failure first, so the next round has a
table to check against.

## Approach

Port `_bump`, `_merge` and the deploy-repository half of `Repositories`
from `build/sd-363` (fb45e3d1d) onto PR 1's chain. Drop PR 1's
`deploy_repo` refusal. Keep each step's rule from PR 1: save the step
before the next external act, read origin's state rather than the local
checkout, and run `verify` on every path that ends the chain.

The merge goes through `gh pr merge --match-head-commit`, not `sd-ship`:
the deploy repository is not a lane repository. Its gates are those
`sd-ship merge` holds a merge for, read from the deploy repository's
policy: green checks, `review.human` approvals of the head, and a green
Jenkins build when `ci` names Jenkins.

Rejected: open the deploy PR and leave the merge to a person. That keeps
one manual step in every release. The operator ruled the chain runs as a
lane step and asks where the org policy holds an act at `ask`
(note #37273).

## Non-goals

- Rollback. A failed `verify` reports and stops; rollback is the org's process.
- More than one deploy file or key per release.
- A deploy repository with no origin, or one this machine has no checkout of.
- Release notes or a GitHub release object.

## Failure table

Steps run in order: version, tag (PR 1), bump, merge, verify. Each step is
saved before its external act, so a kill resumes at that step.

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| bump: read the deployed file | none | `key` is missing, or not a one-line scalar | stop failed at bump; file untouched | `test_a_key_that_holds_no_scalar_is_refused_and_the_file_kept` |
| bump: read the deployed file | none | a key on the path holds a block, flow or multi-line scalar, a flow collection, an anchor, alias or tag, so a line inside it reads as the key | stop failed at bump; file untouched | `test_a_key_path_through_text_that_is_no_block_mapping_entry_is_refused`, `test_a_key_under_a_block_scalar_stops_the_bump_and_opens_nothing` |
| bump: read the deployed file | none | the key or a key on its path appears twice | stop failed at bump; file untouched | `test_a_key_path_through_text_that_is_no_block_mapping_entry_is_refused` |
| bump: read the deployed file | none | the file holds a second document (`---` or `...` after content) | stop failed at bump; a leading `---` reads | `test_a_key_path_through_text_that_is_no_block_mapping_entry_is_refused`, `test_a_key_path_reads_only_block_mapping_entries_and_rewrites_the_one_it_names` |
| bump: read the deployed file | none | the path runs through a sequence item (`- key:`) | no entry at the key: stop failed at bump, `has no <key>` | `test_a_key_path_through_text_that_is_no_block_mapping_entry_is_refused` |
| bump: read the deployed file | none | text elsewhere looks like the key: inside a block scalar, a quoted scalar or flow collection over several lines, or one that never closes | only block-mapping entries match; a value open at the end of the file stops failed at bump | `test_a_key_path_reads_only_block_mapping_entries_and_rewrites_the_one_it_names`, `test_a_key_path_through_text_that_is_no_block_mapping_entry_is_refused` |
| bump: read the deployed file | none | `#` inside a quoted value, a comment as the value, a comment line, a quoted key | the quoted value reads whole; a comment-only value stops failed at bump; comment lines are skipped; a quoted key matches | `test_a_key_path_reads_only_block_mapping_entries_and_rewrites_the_one_it_names`, `test_a_key_path_through_text_that_is_no_block_mapping_entry_is_refused` |
| bump: read the deployed file | none | a `[`, `{` or quote inside a plain scalar, such as `the '90s` | only one that starts the value opens a flow collection or quoted scalar; the rest read as plain | `test_a_bracket_or_quote_inside_a_plain_scalar_opens_nothing` |
| bump: read the deployed file | none | a read strips edge whitespace, so the rewrite loses content | read raw (`strip=False`) | `test_file_reads_keep_leading_and_trailing_whitespace` |
| bump: compare versions | none | the deployed value already equals the version | skip to verify, reason `no bump` | `test_release_skips_a_bump_already_deployed` |
| bump: compare versions | none | the deployed value drops or adds the `v` the tag has | keep the deployed value's form | `test_the_bump_keeps_the_deployed_values_v_prefix_and_form` |
| bump: ask | a question note | `commit`, `push` or `pr` is `ask` | wait; a `go` ruling runs the step; any other stops it | `test_the_bump_asks_when_its_commit_or_push_is_held_at_ask` |
| bump: message | none | the deploy commit convention refuses it (no ticket footer) | stop failed at bump; nothing pushed | `test_the_bump_follows_the_deploy_repositorys_commit_convention` |
| bump: push branch | a `release/<repo>-<tag>` branch on the deploy origin | push fails | nothing on origin, no worktree left; rerun pushes again | `test_a_failed_push_leaves_nothing_on_origin_and_a_rerun_pushes` |
| bump: open PR | a PR | push landed, `gh pr create` failed, maybe deploy main moved since | rerun reuses the branch if it sets the key to this version; refuses if not | `test_a_branch_pushed_before_a_failed_pr_create_is_reused`, `test_a_pushed_bump_is_reused_after_deploy_main_moves`, `test_a_pushed_branch_with_other_content_is_not_reused` |
| bump: open PR | a PR | kill after `gh pr create`, before the save | rerun finds the open PR by head branch (`gh pr list --head`) | `test_a_kill_after_the_pr_is_opened_finds_it_by_its_head_branch`, `test_a_deploy_release_runs_version_through_verify_against_bare_origins` |
| bump: open PR | none | the open PR found by branch sets the key to another value | refuse; nothing merged | `test_an_open_pr_on_the_branch_with_other_content_is_not_reused` |
| bump: message | none | a run resumed at bump never read origin's tags, so the footer read refused | read origin's tags on first use | `test_a_resumed_run_reads_origins_tags_before_the_messages_since_one` |
| merge: freeze | none | a freeze window on either repository | wait; PR stays open with the reason | `test_freeze_window_stops_the_chain_before_merge` |
| merge: checks | none | checks pending, or none reported | wait, unless `ci` is Jenkins and its build stands in | `test_a_jenkins_only_deploy_repo_merges_on_its_green_build_with_no_github_check` |
| merge: checks | none | a check red, or the PR closed | stop failed with the check names | `test_red_or_pending_checks_leave_the_pull_request_open` |
| merge: gates | none | fewer `review.human` approvals of the head than the policy needs | wait with the count | `test_the_deploy_policy_gates_the_merge_as_sd_ship_does` |
| merge: ask | a question note | `push` is `ask` on the deploy policy | wait for `go` | `test_each_act_the_policy_holds_at_ask_waits_for_a_go_ruling` |
| merge: merge | the deploy main | head moved after the gates read it | `--match-head-commit` refuses; next run reads the gates again | `test_the_deploy_policy_gates_the_merge_as_sd_ship_does` (passes the gated head) |
| merge: gates | none | a push to the release branch set another value at the key while the checks ran | stop failed at merge; nothing merged | `test_the_merge_lands_only_the_bump_the_chain_opened` |
| merge: gates | none | the PR was moved to another base than origin's default branch | stop failed at merge; nothing merged | `test_the_merge_lands_only_the_bump_the_chain_opened` |
| merge: gates | none | the PR head moved between `gh pr view` and the branch read | wait; the next run reads the PR and its gates again | `test_a_head_that_moved_as_it_was_read_waits_and_an_ungated_merge_refuses` |
| merge: merged | none | the PR merged outside the chain (by hand, a queue, an earlier run) with another value at the key | stop failed at merge; no verify | `test_a_pr_merged_outside_the_chain_advances_only_with_the_bump_on_main` |
| merge: merged | none | the PR merged into another base than origin's default branch | stop failed at merge; no verify | `test_a_pr_merged_outside_the_chain_advances_only_with_the_bump_on_main` |
| merge: gates | none | the PR was closed outside the chain | red at merge; nothing gated or merged | `test_a_pr_closed_outside_the_chain_reads_red_and_gates_nothing` |
| merge: merge | none | a resumed run merges a head an earlier run gated | `merge_bump` refuses a PR not gated in this run | `test_a_head_that_moved_as_it_was_read_waits_and_an_ungated_merge_refuses` |
| merge: merge | a merge-queue entry | `gh pr merge` only adds the PR to a merge queue | stay at merge until `gh pr view` reads `MERGED`; no verify before | `test_a_merge_that_only_queues_the_pull_request_stays_at_merge_until_merged`, `test_a_merge_queue_add_reads_as_not_merged` |
| merge: merge | the deploy main | kill after the merge, before the save | next run reads `MERGED` first, merges nothing again, and goes to verify | `test_a_kill_after_the_merge_before_its_save_resumes_at_verify` |
| verify | none | `verify` exits non-zero or runs past its bound | stop failed: reason names the tag and merged version; nothing rolled back | `test_failed_verify_reports_and_rolls_nothing_back` |
| verify | a detached worktree | the deploy checkout lacks the merged commit | fetch origin's default branch; run `verify` in a detached worktree at the merged commit, as PR 1 does at the tagged one | `test_verify_runs_in_a_detached_deploy_worktree_at_the_merged_commit`, `test_a_deploy_release_runs_version_through_verify_against_bare_origins` |
| any | none | a chain PR 1 stored at verify, then the policy named a deploy | go back to bump | `test_a_chain_tagged_before_the_policy_named_a_deploy_bumps_before_its_verify` |
| any | none | a chain stored at bump or merge, then the policy dropped the deploy | stop failed; act on nothing | `test_a_deploy_step_whose_policy_dropped_the_deploy_fails_rather_than_acts` |
| bump | `deploy` (deploy_repo, file, key) on the chain | the chain reaches bump | stored with the bump step's save, before `open_bump` acts | `test_each_step_is_saved_before_the_next_external_act`, `test_a_kill_after_the_pr_opens_then_a_changed_deploy_opens_no_second_pr` |
| merge | none | `deploy_repo`, `file` or `key` changed while the merge waits, so the new repository's gates read the old one's PR | stop failed at merge, nothing merged; the policy set back resumes | `test_a_deploy_changed_while_the_merge_waits_merges_nothing` |
| bump | none | a kill after `gh pr create`, then `deploy_repo` changed: the rerun opened a PR in the new repository | stop failed at bump; no second PR | `test_a_kill_after_the_pr_opens_then_a_changed_deploy_opens_no_second_pr` |
| bump: ask | none | a `go` ruling, read by tag and step, covered a deploy repository the question never named | stop failed at bump; nothing opened | `test_a_go_ruling_on_the_bump_covers_only_the_deploy_it_asked_about` |
| verify | none | the deploy dropped or changed after the merge: verify ran tag-only on the source, or in the new checkout | stop failed at verify; no verify | `test_a_deploy_dropped_or_changed_after_the_merge_runs_no_verify` |
| any | none | a gate changed between steps: the deploy policy's acts, `commit_convention`, `review.human`, `ci`, `merge_method`, a freeze; the source's `push`, `verify`, `release_types` | none needed: each is read at the one act it holds, in the run that acts, and no earlier step acted on it; the stored deploy keeps the deploy gates that repository's | `test_the_deploy_policy_gates_the_merge_as_sd_ship_does`, `test_freeze_window_stops_the_chain_before_merge`, `test_each_act_the_policy_holds_at_ask_waits_for_a_go_ruling` |

Each row once marked "to write", each row added in the build, each row of the review round 1 class pass ("a key path matches text that is not a block-mapping entry") and of round 2 ("a resumed step reads policy that changed since an earlier step acted on it") has a test that failed first, except the round 2 row for gates, which needs no fix.

## Acceptance criteria

- [x] Every "to write" row has a test that failed before its fix; the PR body quotes each failing line.
- [x] `tests.test_sd_release` and `tests.test_sd_lane -k release` pass.
- [x] A policy with `deploy_repo` runs version through verify against a bare local deploy origin in one test.
- [ ] `make check` passes through the lane gate.

## Risks

- `gh` calls are tested with fakes. Only the git half runs against real local repositories. The first real deploy release is the first end-to-end run. Accepted: the operator watches it, and every act the org holds at `ask` waits for a ruling.
- The merge skips `sd-ship`'s own gates. It reads the same policy keys, but a gate added to `sd-ship merge` later is not added here.
- Evidence ties: `green` is bound to the PR head SHA it read, and the merge passes that SHA; approvals count only reviews of that head.
