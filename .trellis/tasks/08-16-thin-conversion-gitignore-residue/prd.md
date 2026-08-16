# Untrack the artifacts the pre-adoption thin conversion committed

## Goal

Remove the 236 files that `platypeeps/sd-github-review`'s thin conversion
committed into its default branch, and which its own `.gitignore` has excluded
again ever since. The pack-side cause is already fixed; this is the consumer
residue that fix could not undo.

## Background

`sd-github-review` was the first consumer converted, on 2026-08-15, before
`.gitignore` adoption existed. Its conversion commit deleted the managed block
outright:

```text
$ git -C ~/repos/platypeeps/sd-github-review show 9a4787a -- .gitignore
--- a/.gitignore
+++ b/.gitignore
@@ -1,146 +1,3 @@
-# sd-ai-command-pack trellis-gitignore start
```

The deleted block carried `.build/` and `node_modules/` — rules about the
consumer's own tree, not about the payload being deleted. Removing them in the
same commit that staged the conversion left the artifacts they had been hiding
newly stageable, and the commit took them:

```text
$ git -C ~/repos/platypeeps/sd-github-review show --format='' --shortstat 9a4787a
 757 files changed, 93644 insertions(+), 55899 deletions(-)
$ git -C ~/repos/platypeeps/sd-github-review show --format='' --diff-filter=A --name-only 9a4787a | wc -l
     572
```

The follow-up `c299260 fix: keep the ignore rules the conversion removed`
landed the same day and did two things: it restored the rules, and it untracked
the `.build/**` files the gap had admitted. It did not untrack `node_modules/**`.
Restoring an ignore rule does not untrack anything by itself, so whatever that
commit did not explicitly remove is still tracked. At HEAD:

```text
$ git ls-files -z | git check-ignore --no-index --stdin -z | tr '\0' '\n' | cut -d/ -f1 | sort | uniq -c
   1 code-review-report.md
 235 node_modules
```

Every one of those 236 paths was introduced by the conversion commit and by
nothing else:

```text
$ git ls-files -z | git check-ignore --no-index --stdin -z | tr '\0' '\n' \
    | while read -r f; do git log --diff-filter=A --format='%h' -1 -- "$f"; done \
    | sort | uniq -c
 236 9a4787a
```

So the partial repair is the reason this task is small and specific: `c299260`
already did the same operation on the other half, and the remaining work is to
finish it. `git log --full-history -- .build/` names exactly two commits,
`9a4787a` and `c299260`; `node_modules/` has only the first.

### The pack-side cause is already closed

`installer/fileops.py:778` `adopt_marked_block` now hands the block's contents
to the repository instead of deleting them, under a plain
`ADOPTED_BLOCK_START` comment pair (`installer/fileops.py:768`) that no longer
claims pack ownership. Its docstring records the same measurement that motivates
this task. Every consumer converted after that fix landed carries the adopted
block, and every one of them added zero files in its conversion commit:

| Consumer | Conversion commit | Files added |
| --- | --- | --- |
| `rwbp-website` | `7d4215f` | 0 |
| `mezmo_benchmark` | `5047241` | 0 |
| `se-ai-command-pack` | `b7dd320` | 0 |
| `sd-github-review` | `9a4787a` | **572** |

So this task fixes one repository's history-shaped residue. It is not a request
to change the converter.

### Blast radius, enumerated

All eight fleet consumers were swept, not just the converted-recently ones:

```text
rwbp-coordinator: 1   loadsmith: 0    hoa-manager: 0        rwbp-website: 3
mezmo_benchmark: 2    se-ai-command-pack: 0                 sd-github-review: 236
anomaly-metric-creator: 1
```

The four small counts are all pre-existing and unrelated — `.env.*.example`
files and `.trellis/.template-hashes.json`, added between 2026-05-16 and
2026-06-25, months before any conversion. Only `sd-github-review` has
conversion-caused residue.

## Requirements

1. Untrack `node_modules/**` and `code-review-report.md` in
   `platypeeps/sd-github-review` without deleting them from the working tree.
   `git rm -r --cached` is the operation; a plain `git rm` is not.
2. Do not modify that repository's `.gitignore`. The rules are already correct —
   `c299260` restored them — and the residue exists precisely because they were
   correct and the files were tracked anyway.
3. Do not touch the four unrelated pre-existing tracked-but-ignored files in the
   other consumers. They predate the migration and are outside this task.
4. Land it as an ordinary consumer pull request against `main`, gated by that
   repository's own CI.

## Acceptance criteria

- [x] `git ls-files -z | git check-ignore --no-index --stdin -z` reports zero
      paths in `sd-github-review` after the change.
- [x] `npm ci` still populates `node_modules` in that repository's CI. The
      dependency is declared in `package.json` with a `package-lock.json`
      beside it, and that consumer's `ci.yml` runs `npm ci`, so nothing
      depended on the tracked copy — but the passing CI run is the proof, not
      the reasoning.
- [x] The change deletes only tracked entries: its diff contains zero
      insertions and zero modifications.
- [x] The other seven consumers' tracked-but-ignored counts are unchanged,
      re-measured after the merge rather than assumed.

## Closure

Shipped in
[platypeeps/sd-github-review#90](https://github.com/platypeeps/sd-github-review/pull/90),
commit `1b1ca58`, merged `2026-08-16T15:17:10Z` as `557ceba`. Every measurement
below was taken against merged `main`, not against the branch.

```text
$ git ls-files -z | git check-ignore --no-index --stdin -z | tr -d -c '\0' | wc -c
0                                    # was 236
$ git show --format='' --numstat 1b1ca58 | awk -F'\t' '{a+=$1; d+=$2} END {print a+0, d+0}'
0 18829                              # zero insertions
$ git show --format='' --name-status 1b1ca58 | cut -c1 | sort -u
D                                    # deletions only, no M and no A
```

Criterion 2 is the one that could not be settled locally, and CI settled it:
the `test` lane passed on a runner where `node_modules` is no longer in the
repository, so `npm ci` rebuilt it from `package-lock.json` alone. `route` also
passed. Copilot reviewed and generated no comments.

Criterion 4, re-measured after the merge:

| Consumer | Tracked-but-ignored | vs. pre-merge |
| --- | --- | --- |
| `rwbp-coordinator` | 1 | unchanged |
| `loadsmith` | 0 | unchanged |
| `hoa-manager` | 0 | unchanged |
| `rwbp-website` | 3 | unchanged |
| `mezmo_benchmark` | 2 | unchanged |
| `se-ai-command-pack` | 0 | unchanged |
| `anomaly-metric-creator` | 1 | unchanged |

Requirements 2 and 3 held: `.gitignore` was not touched, and none of the four
unrelated pre-existing entries in other consumers was disturbed.

### One observation worth recording

The commit removes the files from the index while leaving them on disk, which
is what `git rm --cached` does and what requirement 1 asks for. That is not the
same as their surviving a branch switch. Checking out `main` restored the
still-tracked copies, and pulling the merge then deleted them as ordinary
tracked-file removals, so `node_modules/` did briefly disappear from the
working tree before `npm ci` restored it. No harm — the directory is
reconstructible by definition, which is the whole reason it should not have
been tracked — but "the files stay on disk" is true of the commit and not of
every path through it.

This closes the deviation recorded against criterion 4 of
`08-10-thin-post-canary-conversion`. That task is already archived with the
deviation documented and pointing here; the pointer now resolves to a fix
rather than to an open defect.

## Notes

A cosmetic second-order difference was measured while enumerating this and is
recorded here rather than filed: the three canary consumers
(`rwbp-coordinator`, `loadsmith`, `hoa-manager`) carry the adopted block at
line 1 of `.gitignore`, while the four post-canary consumers carry it where the
managed block originally sat. Both preserve every rule; only the position
differs, and it splits exactly on the cohort boundary because the adopt-in-place
refinement landed between the two waves. No action is proposed.
