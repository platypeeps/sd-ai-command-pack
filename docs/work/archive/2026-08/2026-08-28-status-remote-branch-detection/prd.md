---
title: sd-status never classifies remote-only branches, so an abandoned remote ref is invisible
status: done
created: 2026-08-28
branch: task/08-28-bookkeeping-integrity
---
# sd-status never classifies remote-only branches, so an abandoned remote ref is invisible

## Goal

An abandoned branch that exists only on the remote should be reported by `sd-status`. Today
the leftover-branch classification walks local refs alone, so a branch that was deleted
locally — or never checked out on this machine — is never classified, never becomes a
follow-up, and never appears in the anomaly list, no matter how long it has been dead.

## Origin

Found on 2026-08-28 clearing the F-1 advisory on `sd-ai-command-pack`. Status reported exactly
one leftover branch — this session's own docs branch — and was correct about it. The same
report also listed, in its ordinary inventory line:

```text
- remote branches (5): origin/HEAD, origin/docs/file-review-and-kb-defects,
  origin/feat/codex-local-review-lane, origin/main, origin/task/08-28-fleet-rollout-followups
```

`origin/feat/codex-local-review-lane` was dead: 5 commits, head `0484fb6c`, its pull request
(#570) closed unmerged two days earlier on an explicit "not shipping this" rationale, its own
final commit retracting its two task records, and a native replacement already on `main`. No
local branch pointed at it, so nothing classified it. It survived the report only because a
human read the inventory line and asked about it.

## The mechanism

The remote refs are already collected. `scripts/sd-ai-command-pack-status.py:529-543` runs

```python
remote_branches = git_output(
    repo, "for-each-ref", "--format=%(refname)", f"refs/remotes/{remote}",
)
...
state["remoteBranches"] = sorted(...)
```

and that value is read at `:2798` and `:3509-3510` for the inventory line and its counts.

`classify_local_branches` (`:2488`) never consumes it. It reads `git.get("localBranches")` at
`:2518` and nothing else, and its own docstring states the scope plainly:

> Classify every local branch other than the default one.

The merge evidence behind the classification is scoped the same way (`:567-574`):

```python
merged = git_output(
    repo, "for-each-ref", "--format=%(refname:short)",
    "--merged", f"refs/heads/{resolved_default}",
    "refs/heads",
)
```

The trailing `refs/heads` confines reachability to local refs, so even if a remote branch were
handed to the classifier there would be no merge evidence for it.

The follow-up and anomaly both derive from that classification (`:2639-2647`), so a
remote-only branch cannot reach either:

```python
prless = [row for row in rows if row.get("disposition") == "unmerged-without-pull-request"]
```

## Why the existing evidence discipline matters here

`unmerged-without-pull-request` is deliberately the one disposition that asserts an absence,
and the classifier already refuses to assert it from incomplete evidence — `gh pr list` is
bounded at `MAX_ITEMS`, and a full page reports `unknown` rather than a false "no pull
request". Any extension to remote refs must inherit that discipline rather than route around
it.

The `feat/codex-local-review-lane` case shows why the PR axis cannot be dropped: the branch
had a pull request, #570, and it was *closed unmerged*. A classifier that only consults open
pull requests would call it PR-less, which is true but misleading — the informative fact is
that its PR was closed deliberately. A closed-unmerged PR is stronger evidence for cleanup
than no PR at all, and the disposition set should be able to say so.

Squash and rebase merges remain a false-positive source on this axis, exactly as the existing
docstring notes for local branches. That is tolerable on an advisory row that names the branch
and blocks nothing; it is not tolerable if a remote row is ever made blocking.

## Requirements

- A branch present on the remote with no corresponding local ref is classified and, when its
  disposition warrants, reported as a follow-up.
- The default branch and `HEAD` are excluded, as they are for local refs.
- The absence-claim discipline is preserved: incomplete, truncated, or stale pull-request or
  merge evidence yields `unknown` with a reason, never a false "no pull request".
- Merge evidence for a remote ref is drawn from a ref that can actually witness it. Reusing
  the local-only `refs/heads` query would report every remote branch unmerged.
- The report distinguishes a remote branch whose pull request was closed unmerged from one
  that never had a pull request. The two call for different operator action.
- Status stays read-only and keeps its no-fetch contract: classification runs off existing
  remote-tracking refs, and their staleness is labelled rather than repaired. A stale
  remote-tracking ref must not produce a confident claim.
- A remote branch that also exists locally is not double-reported.

## Non-goals

- Deleting, pruning, or fetching anything. Status never mutates; cleanup stays with
  housekeeping.
- Making any remote-branch row blocking. These are advisory, for the squash/rebase
  false-positive reason above.
- Classifying refs under remotes other than the configured one.

## Acceptance criteria

- [x] A fixture repository with a remote-tracking ref and no matching local branch produces a
      classified row for it; the same fixture on today's code produces none.
- [x] A remote branch whose pull request is closed unmerged is reported with a disposition
      distinguishing it from a branch with no pull request at all.
- [x] A remote branch reachable from the default tip is reported merged, not unmerged —
      pinning that merge evidence is not the local-only `refs/heads` query.
- [x] Truncated pull-request evidence (`MAX_ITEMS`) yields `unknown` with a reason for a
      remote row, matching the existing local-row guarantee.
- [x] A branch present both locally and on the remote yields exactly one row.
- [x] `--json` exposes the remote rows in the structured inventory, and the human report keeps
      its bounded fleet output.
- [x] No new `git fetch` is introduced on the status path; a test asserts the collector issues
      no network-mutating git command.

## Related

- `.trellis/tasks/08-28-fleet-lane-procedural-defects` — other defects found in the same
  0.71.62 rollout window.
