# Design — stop refusing a base update over files both sides merely touched

Written 2026-08-26 against `main` at `399b4e38`, pack 0.71.60. Every line
number below was resolved on that tree.

## What the PRD settled, and what it left open

The PRD establishes the premise correction (`--cc` reports paths differing from
every parent, which includes clean auto-merges), proves that narrowing the
refusal to genuine conflicts would **not** have unblocked #560 — all four of its
base updates were real conflicts — and names Direction B, scope-checking the
resolution, as the fix that removes the deadlock.

It left one thing under-specified, and it is the whole design problem.
Direction B says to run the resolution's paths through

> the same per-commit category rules the range already applies via
> `bookkeepingChangedEntries`

**There is no "the" rule set. There are two, and they disagree.**

## The two call sites are not duplicates

`classifyFirstParentMerge` (`templates/scripts/sd-ai-command-pack-review-preflight.mjs:1851`)
is shared, and the reason-code branch is duplicated at `:1926` and `:2280`. That
much the PRD has right. But the surrounding scope machinery differs in shape and
in policy:

| | site 1 — `evaluateActiveTaskSuccessorRange` | site 2 — post-archive successor |
| --- | --- | --- |
| call | `:1915` | `:2271` |
| scope check | inline, per commit (`:1955-1958`) | deferred; commits accumulate into `unionEntries` (`:2299`), checked once at `:2341` |
| `.trellis/spec/**` | **forbidden** | **allowed** |
| journal/index workspace | allowed | **forbidden** |
| task's own directory | allowed | forbidden |

Both are faithful to their own documented contract, which is why neither is
simply a bug:

- site 2 — `templates/.agents/skills/sd-finish-work/SKILL.md:217`: "may change
  code, tests, **specs**, and generated payloads, but never task, workspace, or
  finalization evidence";
- site 1 — `:224-229`: "limited to the task's own directory, **ordinary
  repository paths**, and journal/index workspace files".

"Ordinary repository paths" is the load-bearing phrase, and the code reads it as
*not under `.trellis/`* (`:1956`). That is a defensible reading. It is also why
the two sites disagree about specs.

## Measured: Direction B unblocks #560, and does not unblock its sibling

Replaying all four #560 base updates and running each one's `--cc` paths through
both allowlists (24 distinct paths across the four merges):

```
6a3cb198: 17 cc paths | site1 refuses 1 | site2 refuses 0
2e38340c: 15 cc paths | site1 refuses 0 | site2 refuses 0
4853ece1: 19 cc paths | site1 refuses 0 | site2 refuses 0
06ff1bc7: 15 cc paths | site1 refuses 0 | site2 refuses 0
```

The single refusal is `.trellis/spec/backend/manifest-and-filesystem.md`, and it
is refused **not because anything conflicted** but because site 1 forbids all
`.trellis/` paths outside the task directory.

#560 archived its task, so it took the completion path and site 2's rules. Under
those, Direction B clears every one of its four base updates and the receipt
becomes obtainable. **The deadlock is genuinely removed for the case that
motivated this task.**

But an otherwise identical PR on the *active-task* path — a spec edit plus a
version bump, which is an ordinary shape in this repository — would still be
refused after Direction B lands, under a reason code that says "resolves a
conflict" when the real objection is a spec file. That is the over-refusal this
task exists to remove, surviving in a second location.

## Decision

**Implement A and B, and do not widen site 1's path policy.**

A base update's resolution is scope-checked against **the allowlist its own call
site already applies** — site 1's for the active-task range, site 2's for the
post-archive range. The resolution is held to exactly the standard every other
commit in that range is held to, and no looser.

Rejected: unifying the two allowlists as part of this task. It is a real
question, but it is a change to what a *linear* commit may contain, which is
outside this task's premise and would silently widen two contracts while
claiming to fix a conflict classifier. Recorded as a follow-up instead.

Consequence, stated plainly so a later round does not read the acceptance
criteria as promising more than they do: after this task, a *conflicted* base
update is refused only when its resolution touches something the range could not
have contained anyway. A spec edit on the active-task path is still refused —
now with an accurate reason code naming the path, not a false conflict claim.

## Mechanism

### A. Classify accurately

`classifyFirstParentMerge` currently returns `conflicted-base-update` whenever
`--cc` is non-empty (`:1879`, over the `--cc` call at `:1874`). Split that — but
not on `merge-tree`'s exit code alone, which is not sufficient.

**Measured, because the obvious version of A opens a smuggling hole.**
`git merge-tree --write-tree <p1> <p2>` replays the merge from the two parents.
It knows nothing about the commit that was actually recorded. A committer can
`git merge --no-commit`, edit any file at all, and commit: the replay is still
clean, so exit is still 0.

```
merge-tree replay:  exit=0  computed_tree=b7f555e0441fc85d52d020b7ea65532c1cc421d6
recorded commit  :         actual_tree=3d138e5fb9fd9d530c8bc85448805db1ab97d931
diff-tree --cc   :  f.txt          (the clean auto-merge)
                    other.txt      (the hand edit — nothing on either parent vouches for it)
```

Today's code refuses that commit, because `--cc` is non-empty. Classifying on
exit 0 alone would walk it through contributing **zero** paths, so nothing would
ever scope-check `other.txt`. That is precisely the smuggling route #558's
sentence exists to close, re-opened by the fix meant to preserve it.

So the verdict is the pair, not the exit code:

- `merge-tree` exits 0 **and** its computed tree OID equals the commit's own
  tree — the recorded merge *is* the clean merge, nothing was added. Plain
  `base-update`, contributes nothing, regardless of `--cc`.
- **anything else** — exit 1, a differing tree on exit 0, an unusable exit, or
  a `merge-tree` that cannot run at all — the `--cc` paths are content the base
  does not vouch for, and B scope-checks them.

The second bullet is deliberately the catch-all rather than a fail-closed
`non-linear`. It is exactly today's posture (`--cc` non-empty is not waved
through) plus B (it is checked instead of refused), so no input is treated more
leniently than it is today by any path through this function. That matters for
one practical reason: `merge-tree --write-tree` is **Git 2.38+** (2022-10) and
this repository declares no minimum git version anywhere — verified by grep over
`README.md`, `CONTRIBUTING.md`, `docs/`, and `.github/`. On an older git the flag
simply fails, A degrades to a no-op, and B alone still removes the deadlock.
Routing that failure to `non-linear` instead would refuse *every* base update on
such a host, which is worse than what ships today.

`--cc` is still needed — it is what enumerates the paths for B — so this adds
calls rather than replacing one.

### B. Scope-check instead of refusing

Replace the `shape === 'conflicted-base-update'` refusal branch at both sites
with a scope check over the `--cc` paths:

- **site 1**: check each path against the existing inline allowlist at
  `:1955-1958`, which already emits `completion_successor_scope_invalid` at
  `:1961`; a refused path emits a new reason code naming that path, and the
  commit is otherwise walked through contributing nothing, exactly as
  `base-update` does today at `:1917-1921`.
- **site 2**: push the `--cc` paths into `unionEntries` (`:2299`) so the existing
  union check at `:2341-2354` covers them. This is the smaller change and it
  reuses the site's own reporting path rather than adding a parallel one.

A clean `base-update` keeps contributing nothing, unchanged.

### Reason codes

`completion_successor_base_update_conflicted` is retired as a shape verdict. Two
codes replace it, and both name the offending path rather than the commit alone:

- `completion_successor_base_update_scope_invalid` — the resolution touched a
  path the range may not contain. This is the only remaining refusal.
- the existing `completion_successor_history_non_linear` continues to cover
  genuinely non-linear history.

This departs from the PRD, which proposed to *reserve*
`completion_successor_base_update_conflicted` for merges that genuinely
conflicted rather than retire it. Under B a genuine conflict is no longer a
refusal, so a refusal code named for one would have nothing left to name: every
surviving refusal is a scope refusal, and the useful thing to report is the
path. The PRD's Direction A was written before Direction B's consequences for
the code set were worked out; this is the resolution, not an oversight.

Retiring a reason code is a consumer-visible change; see Compatibility.

## Compatibility and rollout

`completion_successor_base_update_conflicted` appears in
`templates/docs/SD_AI_COMMAND_PACK.md:1693` and
`templates/.agents/skills/sd-finish-work/SKILL.md:244`, both of which describe
the rule in terms of conflicts and both of which become false when A lands. They
are updated in the same change, which is acceptance criterion 3.

The code is emitted, never consumed as an input: no script matches on it and no
fleet consumer keys behavior to it. Verify that with a fleet-wide grep before
removing it — that check is in `implement.md`, not assumed here.

Receipts are not persisted across runs in a way that would strand an old code:
the housekeeping evaluator recomputes the validator result rather than reading a
stored one.

## Rollback

Revert the commit. The refusal is strictly wider than what replaces it, so
reverting can only re-block PRs that this change unblocks — it cannot admit
anything that was previously refused. No data migration, no receipt rewrite.

## Follow-up recorded, not silently absorbed

Site 1 forbids `.trellis/spec/**` while site 2 allows it, and the finish-work
skill uses different words for the two ranges. Whether that divergence is
intentional is a live question this task does not answer. It needs its own task
because the answer changes what a linear commit may contain, not merely how a
merge is classified.
