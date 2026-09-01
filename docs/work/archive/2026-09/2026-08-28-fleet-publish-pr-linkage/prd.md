---
title: Record fleet-publish PR linkage in the archived refresh task
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-28
---
# Record fleet-publish PR linkage in the archived refresh task

## Goal

Make a completed fleet-refresh task carry the pull request that published it.
Today `sd-ai-command-pack-fleet-publish.py` archives the task before the PR
exists, so every merged refresh lands `pr_url: null` and `commit: null` while
its own `bundle-shape` acceptance criterion is ticked verified. Local review
flags this on every lane, and the disposition is always the same.

## Context

Discovered during the 0.71.62 fleet rollout (campaigns
`refresh-0.71.62-20260828T112956Z`, `...T115500Z-clear`, `...T124000Z-tail`).
The finding was raised and accepted on at least four consumers under three
different prism titles — "Completed task omits its commit and PR linkage",
"Completed task omits recorded commit and PR URL", "Archived task omits
completion commit and PR URL", "Published-PR criterion lacks matching task
evidence". Severity ranged low to medium.

Evidence, post-merge:

```
se-ai-command-pack {'status': 'completed', 'pr_url': None, 'commit': None}
loadsmith          {'status': 'completed', 'pr_url': None, 'commit': None}
```

The ordering is structural, not accidental. `fleet-publish` documents its own
sequence as: work commit (H1), `task.py archive` plus `add_session`, completion
receipt, assert the H1..H3 delta is `.trellis`-only, push. The PR is created by
the operator afterwards, against the pushed head. Archiving cannot know a PR
number that does not exist yet.

## Requirements

- A refresh task archived by `fleet-publish` must end up with its publishing PR
  recorded, or the `bundle-shape` criterion must stop claiming linkage the task
  does not carry. Pick one; do not leave both as they are.
- Preserve the invariant `fleet-publish` exists to hold: the pushed head already
  carries every bookkeeping artifact, so the merge stage sees zero head advance
  and no successor publication to reclassify.
- Do not reintroduce a second commit after the PR is created. That is the defect
  the fold pattern was built to remove.
- Whatever the fix, the recurring local-review finding must stop recurring — a
  fix that leaves reviewers dispositioning the same thing every lane has not
  landed.

## Open design question

Two shapes were considered during the rollout and neither was validated:

1. Have the fleet controller record the PR into the archived `task.json` at
   `pr-publication` receipt time, after the PR exists. This keeps the head
   frozen but mutates an archived task outside Trellis's own flow.
2. Narrow the `bundle-shape` criterion so it asserts only what the helper can
   prove from the tree — that the pushed head carries work, archive, and journal
   — and drop the implication of PR linkage.

Option 2 is smaller and matches the existing rule that a criterion naming
something the verifier cannot read is left unticked rather than ticked on an
exit code. Option 1 is closer to what a reader of the archive actually wants.
Decide before implementing.

## Acceptance Criteria

- [ ] A fleet refresh published end-to-end produces an archived task whose PR
      linkage state matches what its acceptance criteria claim, with no gap for
      a reviewer to find.
- [ ] The chosen option is recorded with its rationale, including why the other
      was rejected.
- [ ] `fleet-publish` still asserts the H1..H3 delta is `.trellis`-only before
      push, and the merge stage still sees zero head advance.
- [ ] A regression test covers the archived task's PR-linkage state.
