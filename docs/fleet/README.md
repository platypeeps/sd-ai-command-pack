# Fleet registry

> [!important]
> **Both files this directory held were deleted on 2026-09-02.** Nothing is
> left here but this page. It stays at this path so that a link into
> `docs/fleet/` still answers what was here, rather than 404-ing on a reader who
> found the path in `CONTRIBUTING.md`, in `CHANGELOG.md`, or in an archived work
> item.

## What was here

`consumers.json` (schema version 5, 330 lines) was the operator-triggered
inventory that ordered fleet refreshes: rollout order, cohort policy,
concurrency, and each of ten consumers' `fat`/`thin` install mode with the pin
path fleet status compared against. Decision R10-D6 dropped the fleet walk that
read it, and the tools that consumed it -- `templates/scripts/sd-ai-command-pack-status.py fleet`
and `install.py --configure-fleet` -- were deleted on 2026-08-30 by step 3e
(`43170716`, #610). Two of its ten rows named repositories that are now
archived: `sd-github-review`, archived by step 4 on 2026-08-31, and
`se-ai-command-pack`, archived on 2026-09-01.

`surface-partition.json` (schema version 1, 4,529 lines) partitioned the
`manifest.json` payload of release 0.72.0 into machine, repo-native and
consumer-config scopes across eighteen platforms. It carried
`"manifestVersion": "0.72.0"`, the terminal release. `manifest.json` itself was
deleted at step 3e, and so was `.github/scripts/partition-surfaces.py`, which
generated this file. Of the 740 target paths it listed, 731 did not exist in
the tree, and its 562 `repo-native` rows named targets inside consumer
repositories that R10-D6 forbids the pack from writing at all.

## Why they were deleted rather than kept

On 2026-09-01 both files were annotated rather than removed, on the reasoning
that "a registry nothing reads is a record." That held for one day. The triage
that annotated them had already returned a `delete` verdict for both, and
keeping an unread 4,859-line registry to preserve a record it shares with the
triage table is paying storage for a second copy. What they were is recorded
above and, in more detail, in the triage table under step 7 of
`docs/work/2026-08-29-artifacts-as-product/implement.md`. Their contents remain
in git history.

`docs/FLEET_ROLLOUT.md`, the procedure that read `consumers.json`, was deleted
in the same pass.
