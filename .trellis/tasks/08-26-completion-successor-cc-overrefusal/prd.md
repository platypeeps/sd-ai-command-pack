# Stop refusing a base update over files both sides merely touched

## Origin

Found on 2026-08-26 while shipping PR #560 at pack 0.71.60. The PR was green,
comment-clean and `CLEAN`-mergeable, and still could not produce a valid
finish-work receipt. The refusal:

```
status: invalid
reasonCodes: ['completion_successor_base_update_conflicted']
successor commit 4853ece1b648 updates the base but resolves a conflict; the
resolution is the branch's own content and is not covered by the base
```

#560 was merged by explicit user authorization outside the `sd-housekeeping`
gate, because no documented route produced the receipt. That is the second time
in two days a version-bearing PR in this repository has had to route around the
gate rather than through it — the first was #551, which produced the task
`08-25-completion-receipt-base-update`.

This task is the successor to that one, not a duplicate of it. #558 removed the
deadlock for a *clean* base update and deliberately kept refusing a conflicted
one. That decision is recorded in
`.trellis/tasks/08-25-completion-receipt-base-update/prd.md`:

> A conflicted base update is refused under its own reason code: a conflict
> resolution is the branch's own content, and it is the one place this
> relaxation could otherwise smuggle a task-path edit past the scope rule.

The property that sentence protects is real and must survive this change. The
test that was built to enforce it does not do what the sentence says.

## Premise correction: `--cc` does not mean "conflict"

`classifyFirstParentMerge` decides the case with
`git diff-tree --cc -r --name-only --no-commit-id <oid>`
(`templates/scripts/sd-ai-command-pack-review-preflight.mjs:1874`), and treats
any output as a conflict resolution.

`--cc` reports paths whose merged content differs from **every** parent. That is
true of a conflict resolution. It is also true of a file that both sides simply
touched and that git merged automatically, with no conflict and no human
involvement at all.

Measured in a scratch repository, not argued. Base file with nine lines; the
branch prepends a line, the base branch appends a different one; `git merge`
exits **0** with no conflict:

```
merge exit: 0 (0 = clean auto-merge, no human conflict)
--- diff-tree --cc output ---
f.txt
```

So the check fires on a merge that resolved nothing. Four artifacts describe
the rule in terms of conflicts and are therefore wrong about what ships:

- the reason code `completion_successor_base_update_conflicted`;
- its message, "updates the base but resolves a conflict";
- `templates/.agents/skills/sd-finish-work/SKILL.md:244` — "`git diff-tree --cc` reports nothing,
  meaning the update resolved no conflict";
- `templates/docs/SD_AI_COMMAND_PACK.md:1693` — "A base update that resolved a conflict is
  still refused".

A real conflict *is* recoverable after the fact — `git merge-tree --write-tree`
on the two parents replays the merge and exits non-zero on a genuine conflict
(verified: exit 0 on the clean auto-merge above). The implementation simply does
not ask that question. This matters for scoping the fix, and Direction A below
turns on it.

## Why this is structural, not an edge case

Every base update on the #560 branch was refused, and all four overlapped on the
same core set of files:

| merge | `--cc` paths |
| --- | --- |
| `6a3cb198` | 17 |
| `2e38340c` | 15 |
| `4853ece1` | 19 |
| `06ff1bc7` | 15 |

The intersection across all four is exactly 12 paths, and it is the
version-stamped and generated surface: `CHANGELOG.md`, `manifest.json`,
`.sd-ai-command-pack/manifest.json`, `plugins/sd/.claude-plugin/plugin.json`,
the **five** copies of `sd-help/references/command-catalog.md` (`.agents/`,
`.claude/`, `templates/.agents/`, `plugins/sd/skills/`, and
`plugins/sd/machine-payload/.agents/`), `docs/fleet/candidate-validation.json`,
`docs/fleet/surface-partition.json`, and
`plugins/sd/machine-payload/partition.json`.

That is not a coincidence of one branch — CI *forces* it. A change to
`templates/**`, `docs/SD_AI_COMMAND_PACK.md`, or the manifest must bump
`manifest.json`, and "every version bump must also add the matching top
`CHANGELOG.md` heading in the form `## <version> - YYYY-MM-DD`; the same gate
rejects missing or stale headings" (`README.md:798`). The `Release payload gate`
job blocks the merge otherwise (`CONTRIBUTING.md:148`), and a bump additionally
requires a regenerated all-pass `docs/fleet/candidate-validation.json`.

So any two PRs that touch shipped surface are *required* to write a heading at
the same top-of-file position and to regenerate the same ledgers. Whichever
merges second conflicts on base update by construction. The refusal is the
guaranteed outcome for the repository's most common PR shape, not an unlucky
one — which is why it has now blocked two consecutive ones.

## What the cheap fix would not have fixed

Replaying each of the four #560 base updates with `git merge-tree --write-tree`:

```
6a3cb198 merge-tree=1   2e38340c merge-tree=1
4853ece1 merge-tree=1   06ff1bc7 merge-tree=1
```

All four were **genuine** conflicts. So narrowing the refusal to true conflicts —
the obvious reading of the premise correction above — would have left #560
exactly as blocked as it was. Correcting the classifier's accuracy is worth
doing, but it is not the fix for the deadlock. Recording this here so a later
round does not spend itself on the tempting half.

## Goal

A pull request that resolves a conflict while updating onto a moved base must
have at least one route to a valid completion receipt that does not require
rewriting published history — without weakening the property that a base update
cannot carry a task, workspace, or finalization edit past the scope rule.

## Directions worth weighing

- **A. Classify accurately.** Replay the merge with `git merge-tree` and reserve
  `completion_successor_base_update_conflicted` for merges that genuinely
  conflicted; a clean auto-merge that merely differs from both parents stops
  being called a conflict. Necessary for the artifacts to be true. Proven above
  to be insufficient on its own.
- **B. Scope-check the resolution instead of refusing it.** The stated objection
  is that the resolution "is not covered by the base". The answer to content
  nothing vouches for is to *check* it, not to refuse the receipt. Run the
  resolution's `--cc` paths through the same per-commit category rules the range
  already applies via `bookkeepingChangedEntries`. The successor range "may
  change code, tests, specs, and generated payloads, but never task, workspace,
  or finalization evidence" (`templates/.agents/skills/sd-finish-work/SKILL.md:217`) — and every path in
  the #560 intersection is code, generated payload, or docs. A resolution
  touching `.trellis/tasks/**` or `.trellis/workspace/**` would still be
  refused, which is precisely the smuggling #558 set out to prevent. This
  preserves the original safety property exactly while removing the deadlock.
- **C. Do nothing and document the escape.** Rejected for the same reason
  `08-25-completion-receipt-base-update` rejected it: the deadlock is only
  reachable by a caller who may not force-push, so documenting a rebase is not a
  route for the people standing in it. #560 shows the actual fallback is a
  human waiving the merge gate, which is worse than either fix.

A and B are complementary, not alternatives: B removes the deadlock, A stops the
diagnostics from lying about why anything was refused.

## Out of scope

- The generated-file conflict rate itself. Reducing how often these merges
  conflict is a separate question about version-bump mechanics; this task is
  about the receipt being obtainable when they do.
- Both call sites must be fixed together —
  `sd-ai-command-pack-review-preflight.mjs:1926` (active-task successor) and
  `:2280` (post-archive successor) share `classifyFirstParentMerge` and duplicate
  the reason-code branch. Fixing one is not a partial delivery, it is a
  divergence; #558's own changelog records that these two paths had already
  drifted apart once.

## Acceptance criteria

- [ ] A completion receipt validates for a branch whose base update resolved a
      real conflict in code, docs, or generated payload, with no history
      rewrite. The test is built from an actual conflicted merge, not a
      synthesized range.
- [ ] A base update whose resolution touches `.trellis/tasks/**`,
      `.trellis/workspace/**`, or finalization evidence is still refused, and
      the test asserts the reason code rather than only the invalid status.
- [ ] A merge that git auto-merged without conflict is no longer described as a
      conflict anywhere: reason code, message, the canonical `sd-finish-work` SKILL.md, and
      `SD_AI_COMMAND_PACK.md` agree with what the code tests.
- [ ] Both `classifyFirstParentMerge` call sites — review-preflight.mjs:1926 and
      :2280 — take the change, with a test covering each.
- [ ] The #560 regression is pinned: a branch carrying the version-bump file set
      (`CHANGELOG.md` plus the three manifests) updated onto a base that bumped
      the same files must end in a valid receipt.
- [ ] All four copies of `sd-ai-command-pack-review-preflight.mjs` are
      byte-identical and `make generate` reports `shipped-surface closure:
      clean`.
