# active-task-review-successor rejects the spec updates finish-work itself requires

## Goal

Let a task finalized through `active-task-review-successor` carry the
`.trellis/spec/**` changes that the finish-work flow's own mandatory
spec-update step produces. Today those paths make the recovery fail, so the one
route designed for a task that legitimately stays `in_progress` is unavailable
to any session that followed the documented workflow.

## Problem

`07-31-completion-recovery-no-archive-anchor` shipped
`active-task-review-successor` for exactly this branch shape: a task that ships
work and stays `in_progress`, with no archive move to anchor on. Its documented
contract, in `sd-finish-work/SKILL.md:188-196`, is:

> every commit in it is limited to the task's own directory, **ordinary
> repository paths**, and journal/index workspace files.

The implementation defines "ordinary repository paths" as *anything not under
`.trellis/`* (`scripts/sd-ai-command-pack-review-preflight.mjs:1601-1604`):

```js
const allowed =
  (!path.startsWith('.trellis/') && !path.startsWith('.sd-ai-command-pack/finish-work'))
  || path.startsWith(`${taskDir}/`)
  || /^\.trellis\/workspace\/[^/]+\/(?:journal-\d+\.md|index\.md)$/.test(path);
```

So `.trellis/spec/**` is forbidden. That is the collision: **Phase 3.3 of the
Trellis workflow makes a spec update a required finish-work step**, and
`sd-update-spec` writes its output to `.trellis/spec/`. A session that follows
the workflow as written produces a branch the recovery then refuses.

The failure is also silent about itself — the findings are discarded before the
operator sees them; see `08-07-preflight-base-diagnosis` for that half.

## Evidence

`platypeeps/sd-github-review` PR #72, pack 0.64.3. One `in_progress` task,
`--base == --head`, branch containing two `.trellis/spec/` edits made by the
required spec-update step. Recovered by running a patched validator that
commits the active-task findings unconditionally:

```
completion_successor_scope_invalid | .trellis/spec/backend/directory-structure.md
completion_successor_scope_invalid | .trellis/spec/guides/cross-layer-thinking-guide.md
```

The same run also rejected two paths under a *second* active task directory.
That rejection is correct by design — "must not change another task" is an
explicit property of this route — and is not part of this task. Only the
`.trellis/spec/**` rejection is contested here.

Because no mode accepted the branch, no finish-work receipt could be produced,
`sd-housekeeping`'s eligibility gate had no receipt to verify, and the PR was
merged outside the gate on explicit operator authorization. That is the
concrete cost: the gate did not fail the change, it failed to be able to
evaluate it.

## Requirements

- A commit under `active-task-review-successor` may change `.trellis/spec/**`.
- Do not weaken the properties this route was built on: another task's
  directory, the archive, `.trellis/.runtime/`, the `finish-work` receipt
  prefix under `.sd-ai-command-pack/`, and non-journal workspace paths stay
  forbidden, and the status/`completedAt`/branch byte-identity requirement is
  unchanged.
- The documented contract and the predicate must agree afterwards, in whichever
  direction is chosen. If `.trellis/spec/**` is deliberately excluded, the
  SKILL.md sentence is what needs correcting, and the workflow's required
  spec-update step then needs a stated route.

## Acceptance criteria

- [ ] A branch with exactly one `in_progress` task, a spec change under
      `.trellis/spec/`, and a journal/index pair validates as
      `active-task-review-successor`.
- [ ] The same branch with an added change under a second active task directory
      still fails, with `completion_successor_scope_invalid` naming that path.
- [ ] The same branch with an added change under `.trellis/.runtime/` or the
      `finish-work` receipt prefix under `.sd-ai-command-pack/` still fails.
- [ ] `sd-finish-work/SKILL.md` and the predicate agree on what "ordinary
      repository paths" admits, verified by a test that reads the documented
      list rather than restating it.

## Notes

Found while finalizing a task parked on an upstream blocker, so its own branch
was documentation and spec only — no code. That makes the collision total
rather than partial: every path on the branch was either the task's own
directory, a second task's directory, or `.trellis/spec/`.

Related: `08-07-preflight-base-diagnosis` (the suppressed diagnosis that hid
this), `07-31-completion-recovery-no-archive-anchor` (shipped this route),
`07-30-recover-bookkeeping-repair-sessions` (the planning-side sibling gap,
different cause — lifecycle repair against a dirty parent).
