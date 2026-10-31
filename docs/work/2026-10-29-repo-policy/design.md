---
title: Per-repo policy for org repositories, held in the repo row
created: 2026-10-29
item: sd:6715
branch: build/sd-244
---

# Design — repo-policy

The item's row holds status, progress and decisions; this page holds the shape.

## Problem

30 of 94 registered repositories belong to an employer organization.
Their rules differ from the operator's own repositories, and today they live in prose that agents forget:

| Rule | Where it lives today |
| --- | --- |
| Commit types (`doc`, not `docs`), a required body, a `Ref: LOG-N` footer | a CLAUDE.md line and one repo's CLAUDE.md; commitlint failed a PR on 2026-10-28 |
| Human review before merge, bot findings (Greptile) to triage | nowhere; asked by hand each time |
| Jenkins is the CI, not the local gate | hand `curl` loops over the StrongDM Jenkins port |
| Release: tag, bump the deploy repo, merge when green, verify the rollout | done by hand 6 times (0.11 to 0.17.2) |
| No rollout or ship during a demo or a scored act | a chat message, 2026-10-29 |
| Issues are the record in some repositories | the global `github_issues` line |

The operator ruled the full design, both PRs, all keys (note #34745), and no `auto` for an org repository (note #34749).

## Approach

Add one declaration kind, `policy`, to `repo.declarations`; add no column and no verb.
`repo declare PATH policy '<json>'` already validates a kind with its reader, refuses unknown keys and stores the object (`docs/sd-db.md` § Declarations).
The `review` kind stays what it is, the `sd-review` routing; `policy.review` covers people and bots, not lenses.

```json
{
  "mode": "org",
  "commit": "ask", "push": "ask", "pr": "ask",
  "merge_method": "squash",
  "issues": "read",
  "review": {"human": 1, "reviewers": ["<name>"], "request_when": "after-green",
             "bots": "triage", "copilot": "never", "after_approval": "add-commits-only"},
  "commit_convention": {"types": ["feat", "fix", "doc", "chore", "pkg", "svc"],
                        "aliases": {"docs": "doc"}, "body": "required",
                        "footer": "^Ref: LOG-\\d+$", "title_max": 63, "line_max": 72},
  "ci": {"provider": "jenkins", "job": "<folder/job>"},
  "release": {"deploy_repo": "<path>", "file": "<values file>", "key": "<image.tag>", "verify": "<command>"},
  "test": {"setup": "<command>", "env": ["NAME"], "teardown": "<command>"},
  "links": ["<registered path>"]
}
```

- **No policy means today's behaviour.** A repository without the kind reads as `mode: managed` with today's defaults, so the 64 other rows change nothing.
- **Values stay in the config folder.** The pack is public; a preset is a JSON file under `<config>/policy/<org>.json`, applied as `repo declare PATH policy "$(cat …)"`. Per-key override is an edit of that row. No preset verb, no inheritance store.
- **`ask` never becomes `auto` for an org repository** (note #34749). The reader refuses `auto` for `commit`, `push`, `pr` and `issues` unless `mode` is `managed`. So no generated allow rules are needed, and the `settings.local.json` writer in note #34687 is dropped.
- **`issues`** takes `off|read|ask`. `read`: agents read issues and map one to an sd item with `--ref github:<owner>/<repo>#N`. `ask`: `sd-issue-guard` answers an update of the repository's own issue with the harness's `ask`, so the operator approves each write in the prompt before the tool runs; an unattended run drafts it as a `--kind question` note on the item instead. Filing stays denied. The `github_issues` column migrates into the kind as `ask` and is dropped (migration 45, sd:6849; 2 rows were on).
- **Commit convention** is checked where sd moves a commit out, not by a hook installed into the repository: an org repository owns its hooks (husky, commitlint). `sd-ship lane enqueue` checks the title and each branch commit before the push, naming the reworded subject for an alias; `sd-ship merge` rewrites an alias in the squash subject. Anything else refuses with the rule it broke.
- **Columns that already work stay columns:** `runner_merge` is the merge key, `lane_host` the lane host, `jira_project` the Jira key. `ci` gains the value `jenkins`; `policy.ci` holds only the job name.
- **Freeze windows** are rows in the `state` table (`freeze:<target>` with `until` and `reason`), not policy: they are short-lived. `sd-ship merge`, the release chain and a repository's own ship script read them first and refuse inside a window.
- **The session-start summary** prints a repository's policy in one line, so an agent sees `commit=ask, issues=read, review=human(1)` before it acts.

Rejected: a column per key (16 columns for 30 rows, and a migration per new key); a preset verb with inheritance (one more store for what a file and a copy do); `auto` for org issue comments (ruled out, note #34749).

## Non-goals

- The org's human review stays human. The policy says when and whom to ask, never that a review passed.
- No `auto` for any org repository, in any key.
- No Jenkins job management: `sd-ship` reads a job's status and waits; it never edits or triggers a job beyond the build a push starts.
- No change for a repository without the kind.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| Migrate `github_issues` into `policy.issues` | 2 repo rows; the column dropped | the migration stops between writing the kind and dropping the column | the migration is one transaction; a rerun finds the column gone, or the kinds written and the column still there, and finishes | `test_migration_moves_github_issues_in_one_transaction` stops after the kind write and reruns |
| Enqueue and merge check the convention | the push, then the squash subject after an alias rewrite | a branch commit or the rewritten squash message breaks a rule | enqueue refuses before the push, merge before GitHub writes the squash; nothing to undo | `test_a_commit_the_convention_refuses_is_named_before_any_push`, `test_the_squash_message_takes_the_declared_convention` |
| Issue action on `ask` | the GitHub write, after the operator's prompt approval | the write fails after the approval | nothing stored to undo: the agent sees the failure and asks again; `read` and `off` deny | `test_an_update_of_this_repository_asks_the_operator`, `test_read_and_off_deny_the_update` |
| Review hold in `sd-ship merge` | none until merge | the approval drops after a push (dismiss-stale-reviews) | `sd-ship` reads the setting and the current approvals at merge time, not at enqueue; a dropped approval holds the entry with the reason | `test_dismissed_approval_holds_the_merge` |
| Jenkins status wait | the lane entry's phase | Jenkins unreachable (StrongDM signed out) | the entry holds as `ci_unreachable`, names `sdm-login`, and never reads unreachable as green | `test_unreachable_jenkins_is_not_green` |
| Release: tag on main | a tag | the tag push fails | nothing else moved; rerun pushes the same tag | `test_release_stops_at_tag_push` |
| Release: bump PR in the deploy repo | a branch and a PR there | the PR opens but the tag was already deployed | the chain reads the current `key` value first and stops if equal | `test_release_skips_a_bump_already_deployed` |
| Release: merge when green | the deploy repo's main | CI red, or a freeze window opens mid-chain | the chain leaves the PR open with the reason; no merge inside a window; rerun resumes at this step | `test_freeze_window_stops_the_chain_before_merge` |
| Release: verify the rollout | none | verify fails | the chain reports the failed verify and the merged version; rollback is the org's process, never automatic | `test_failed_verify_reports_and_rolls_nothing_back` |
| Lane host routing | the lane entry | an enqueue on a machine that is not the lane host | forwarded, never refused (note #36885): the entry goes in the shared queue, names the host in `forwarded_to`, and that host runs it from origin | `test_enqueue_off_the_lane_host_forwards_to_it` |

## Slices

1. **Policy kind and the PR1 keys** (pack): the `policy` reader and validator, `mode`, `commit|push|pr`, `merge_method`, `issues` with the `github_issues` migration, `review`, `commit_convention`, the session-start line, the review hold. Leaves every machine working: no row has the kind yet, so behaviour is unchanged until the operator applies a preset.
2. **CI provider, release chain, test recipe, freeze windows, links, lane host routing** (pack). Then the operator applies the org preset to the 30 rows, and one system PR deletes the prose rules it replaces (the commitlint line in the shared agent prompt, the `github_issues` line, the per-repo rules in CLAUDE.md files).

About a week in all (note #34745).

## Acceptance criteria

- [ ] `make check` passes in the pack with the failure-table tests above, each failing before its fix.
- [ ] `sd-db repo declare <org repo> policy "$(cat <config>/policy/<org>.json)"` stores the policy; `sd-db repo declare <path> policy '{"mode":"org","commit":"auto"}'` refuses with the rule.
- [ ] A builder commit in an org repository with `docs:` lands as `doc:` with a body and the `Ref:` footer, and commitlint passes in Jenkins.
- [ ] `sd-ship` on an org repository waits for the Jenkins job and holds the merge until one human approval exists.
- [ ] A repository without the kind behaves as before: the full pack suite passes with no fixture changed.

## Risks

- Accepted: an org's rules change upstream and the preset lags. The commit step refuses loudly, and the Jenkins result is still the merge gate, so a stale preset costs a retry, not a bad merge.
- Accepted: approval is read at merge time from GitHub; a token without read access to the org reads as no approval and holds, never as approved.
- Evidence binding: the review hold ties an approval to the PR's head commit (GitHub's `commit_id` on the review); the Jenkins wait ties a green build to the pushed head SHA, not to the branch name.
- A preset file names the org's people and jobs; it stays in the config folder and never enters the pack.
