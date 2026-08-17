# Design: leftover-branch classification and anomaly severity

All line citations below are against `templates/scripts/` — the source of
truth. `scripts/` is a byte mirror produced by `make sync`, and the PRD's
`scripts/...` citations are stale (the file has moved by ~400 lines since it
was written). Current locations:

| Thing | Now |
| --- | --- |
| `strict_anomalies` definition | `templates/scripts/sd-ai-command-pack-status.py:2108` |
| "extra local branches remain" entry | `.../sd-ai-command-pack-status.py:2140-2146` |
| `expect_clean` gate on strict entries | `.../sd-ai-command-pack-status.py:2540-2549` |
| advisory call site (`expect_clean=False`) | `.../sd-ai-command-pack-status.py:3372` |
| exit rule | `.../sd-ai-command-pack-status.py:3637` |
| worktree inventory / `branchesHeldElsewhere` | `.../sd-ai-command-pack-status.py:343`, `:505-519` |
| `classify_outcome` | `.../sd-ai-command-pack-housekeeping-result.py:229` |
| `status_anomalies` read | `.../sd-ai-command-pack-housekeeping-result.py:237` |
| the blocking branch | `.../sd-ai-command-pack-housekeeping-result.py:255-259` |
| `default_branch_switch_failed` | `.../sd-ai-command-pack-housekeeping.sh:551` |
| `branch_switch_incomplete` | `.../sd-ai-command-pack-housekeeping.sh:925` |
| shell anomalies replayed into status | `.../sd-ai-command-pack-housekeeping.sh:1231` |

## Decisions

### Open question 1 — should strict mode block on leftover local branches?

**No. The entry leaves `strict_anomalies` entirely.** It is replaced by an
always-computed classification that both modes read, and by one narrower strict
check that covers the postcondition the entry was accidentally standing in for.

Rationale, in the order that decides it:

1. **It is not a postcondition of the run.** `strict_anomalies` exists to verify
   what *this housekeeping run* was supposed to achieve: a clean tree, the
   default branch checked out and matching its remote, the run's own source
   branch retired. Local branches the run never touched are pre-existing
   repository state. Attributing them to a merge that succeeded is a category
   error, and it is why the verdict fired on all seven merges in the PRD's
   evidence while every action through `remote_refs_pruned` completed.
2. **It is unresolvable by construction for its loudest case.** A branch held by
   another live worktree cannot be deleted by any correct cleanup. Blocking on
   it guarantees a permanent `blocked`, which is the mechanism that trained the
   reader to ignore the signal — not a side effect of it.
3. **It does not scale with severity.** 3 branches and 14 branches produce the
   same verdict shape, so the signal cannot distinguish "tidy up sometime" from
   "a 222-line PRD is stranded on an 18-commit-behind branch with no PR". Making
   it louder cannot fix that; only classifying it can.
4. **The condition worth noticing is narrower than the entry.** What mattered was
   *unmerged and PR-less*, which the entry does not detect: it reports every
   extra branch, merged or not.

What the removal must not lose: the entry incidentally caught a source branch
that housekeeping failed to delete. That postcondition gets its own explicit
check (`local_source_branch_retained`, below) rather than riding on a
set-difference over unrelated branches. It blocks — with one exception that
would otherwise rebuild the trap this task removes: when the worktree inventory
shows the source branch held by another live worktree, deletion was impossible,
so it reports as advisory `local_source_branch_held_elsewhere` naming the
holder. Held-ness is proof of impossibility, not an excuse; every other reason a
source branch survived still blocks.

### Open question 2 — should "unmerged branch with no PR" get its own reason code?

**Yes as a classification and a follow-up; no as a blocking housekeeping reason
code.** It is real, it is the condition that cost this repository a stranded
PRD, and no surface names it today — so it gets a stable name
(`unmerged-without-pull-request`), a structured row, and an advisory anomaly
carried by *both* modes. It does not become a blocking reason code, because
blocking it would reintroduce exactly the defect this task removes: a verdict
that fires on repository state a successful merge did not create and the
operator may not be free to resolve in that moment.

## Model: a matrix, not three labels

Two independent axes, as the PRD requires.

**Axis A — disposition** (one value per branch):

| Value | Evidence |
| --- | --- |
| `merged` | reachable from the local default branch tip |
| `unmerged-with-pull-request` | not merged; an open PR has this branch as `head` |
| `unmerged-without-pull-request` | not merged; PR evidence is complete and contains no PR for it |
| `unknown` | any required evidence is missing, truncated, or stale (below) |

**Axis B — `heldByWorktree`**: the absolute path of the other worktree holding
the branch, or `null`. Derived from the existing inventory
(`git["branchesHeldElsewhere"]`, `:505-519`) plus the `worktrees.rows`
`path`/`branch` pairing — this task does **not** reimplement worktree discovery.

The default branch itself is excluded from the inventory; it is covered by the
existing default-branch strict checks (`:2130-2138`).

### `unknown` is asserted, never inferred away

`unmerged-without-pull-request` may only be claimed when every one of these
holds. Any failure ⇒ `unknown`, carrying the reason:

- `github.openPrsStatus == "available"` — else reason `github_unavailable`
  (covers `--no-network`, missing `gh`, no slug, and a failed `gh pr list`;
  `:2036-2051`);
- `len(openPrs) < MAX_ITEMS` — else reason `pr_evidence_truncated`. `gh pr list`
  is called with `--limit MAX_ITEMS` (`:2061-2062`) and `parse_gh_lines` slices
  to `MAX_ITEMS` (`:1858`), so a full page means "there may be more" and cannot
  prove absence;
- the local default branch exists and matches its remote
  (`git["defaultLocalExists"]` and `git["defaultMatchesRemote"] is True`) — else
  reason `default_branch_stale`. Merge evidence is computed against the *local*
  default tip from cached refs (sd-status never fetches, per the skill's
  freshness rule), so a default branch behind its remote would report a branch
  merged upstream as unmerged, and then — finding no *open* PR, because it was
  merged and closed — as PR-less. That is the exact false claim the PRD forbids.

`merged` needs only the local default ref, so it stays available under
`--no-network`.

## Data contract

### `report["localBranchClassification"]` (new, both modes)

Computed unconditionally in `build_local_report` — never under `expect_clean` —
so both surfaces read one classification. Additive key; schema major stays 2.

```json
"localBranchClassification": {
  "status": "ok",
  "evidence": {
    "pullRequests": "available|github_unavailable|pr_evidence_truncated",
    "defaultBranch": "current|stale|unknown"
  },
  "rows": [
    {"branch": "task/x", "disposition": "unmerged-without-pull-request",
     "pullRequest": null, "heldByWorktree": null},
    {"branch": "task/y", "disposition": "merged",
     "pullRequest": null, "heldByWorktree": "<repo>/../wt-2"}
  ],
  "truncated": false
}
```

`rows` is bounded at `MAX_ITEMS`, sorted by branch name, with `truncated: true`
when the local branch count exceeds it. Paths are `safe_text`-bounded like every
other externally controlled field.

### `report["anomalyDetails"]` (new, both modes)

`report["anomalies"]` keeps its type (`list[str]`) and its contents, so no
existing reader breaks. A parallel typed list gains the two things the PRD needs
— a stable code and a severity:

```json
"anomalyDetails": [
  {"code": "working_tree_dirty", "severity": "blocking",
   "message": "working tree is dirty after housekeeping"}
]
```

Invariants, pinned by test: same length as `anomalies`, same order, and
`anomalyDetails[i]["message"] == anomalies[i]`. Codes match
`[a-z][a-z0-9_]{0,63}` so they can be copied straight into housekeeping's
result, whose `validate_event` enforces that shape
(`housekeeping-result.py:204-216`).

Both new blocks are computed after the `report` dict literal is assembled
(`:2472-2506`), because the classification reads `report["github"]` — the
`collect_github` call is inline in that literal at `:2482`. They sit next to the
existing `expect_clean` block at `:2540`, before `followUps` and `nextSteps` are
derived at `:2551-2555`.

Every existing append site gets a code. Severity is `blocking` for all of them —
this task reclassifies exactly one condition and adds two more, and must not
become a general exit-zero rule (acceptance criterion 5):

| Site | Code | Severity |
| --- | --- | --- |
| `:525` stash unavailable | `git_stash_unavailable` | blocking |
| `:550` remote missing | `git_remote_unconfigured` | blocking |
| `:2508` work-loop invalid | `work_loop_state_invalid` | blocking |
| `:2513` recovery invalid | `recovery_state_invalid` | blocking |
| `:2521` machine receipt invalid | `machine_receipt_invalid` | blocking |
| `:2536` completed tasks outside archive | `completed_tasks_outside_archive` | blocking |
| roadmap diagnostics (`:2502`) | `roadmap_source_unreadable` | blocking |
| strict: dirty tree, unknown/mismatched/missing default, wrong current branch, remote source branch state (`:2118-2156`) | one code each | blocking |
| **strict, new**: source branch survived deletion | `local_source_branch_retained` | blocking |
| **strict, new**: source branch survived and is held elsewhere | `local_source_branch_held_elsewhere` | **advisory** |
| **new, both modes**: unmerged and PR-less | `local_branches_unmerged_without_pr` | **advisory** |
| **new, both modes**: unmerged, PR state unknown | `local_branches_pr_state_unknown` | **advisory** |
| `--prior-anomaly` replay (`:2501`) | the caller's own code | mirrors it |

### The replay channel must carry the code

`housekeeping.sh:1231` replays each of its own anomaly *messages* into the
collector as `--prior-anomaly <message>`, and they land in `report["anomalies"]`
at `:2501`. That channel decides two things at once, so it cannot be given a
fixed severity:

- if replayed entries stay **blocking**, a shell anomaly reclassified as
  advisory below (`default_branch_held_elsewhere`) blocks anyway through the
  back door — the verdict would be `clean` while the collector exits 1;
- if they become **advisory**, the human (non-JSON) housekeeping path silently
  stops failing. That path returns the collector's exit status directly
  (`housekeeping.sh:1275-1279`), so a genuinely blocking shell anomaly such as
  `local_branch_delete_failed` would exit 0.

So `--prior-anomaly` takes two values, `CODE MESSAGE`, and the collector mirrors
the caller's severity. The only caller is `housekeeping.sh:1231`, which already
holds both arrays (`ANOMALY_CODES`, `ANOMALIES`).

Severity for a shell code is then named in two files, which is a drift risk with
a deterministic fix: `status.py` gets `ADVISORY_CALLER_ANOMALY_CODES`,
`housekeeping-result.py` keeps `ADVISORY_ANOMALY_CODES`, and a test loads both
modules and asserts the two frozensets are equal. An unknown replayed code is
blocking — fail-closed.

### Which advisory entries are emitted

Only when they say something. `merged` and `unmerged-with-pull-request` rows
produce **no anomaly** — a merged-but-undeleted branch and a branch with an open
PR are ordinary states, and an entry firing on them would rebuild the noise
floor this task is removing. They remain visible as structured rows, in the
human branch list, and as follow-ups.

- `local_branches_unmerged_without_pr` — emitted when ≥1 row has that
  disposition. Message names the count and the branches, each held branch marked
  with its worktree path: `2 local branches are unmerged with no pull request:
  chore/a, chore/b [held by <repo>/../wt-2]`.
- `local_branches_pr_state_unknown` — emitted only when ≥1 **unmerged** row is
  `unknown`, naming the count and the evidence reason. A `--no-network` run in a
  repository whose leftovers are all merged stays silent, because nothing was
  actually left unanswered.

### Follow-ups

`collect_follow_ups` already turns every anomaly into an `issue` row prefixed
`Resolve status anomaly:` (`:2192-2195`), so both advisory entries surface there
automatically — but with the wrong voice, since an advisory entry is not
something to resolve before proceeding. The kind derives from severity instead:
`issue` for blocking, `recommendation` for advisory. Add one `action` row for
merged-and-undeleted branches that are **not** worktree-held — the only
genuinely deletable class — so "you can tidy this" stays available without being
an anomaly.

## Exit rule and human rendering

- `:3637` becomes: exit 1 iff `expect_clean` **and** at least one
  `anomalyDetails` entry has `severity == "blocking"`. This is what makes
  acceptance criterion 5 true, and it also avoids a trap: `classify_outcome`
  maps `status_exit == 1` with no other cause to `failed`
  (`housekeeping-result.py:260-262`), so leaving the exit keyed on the whole
  list would turn a reclassified advisory into `failed` instead of `clean`.
- `render_local`'s `attention` header (`:2650-2654`) keys on blocking anomalies
  only; advisory ones do not flip a healthy repository to `attention`.
- The `==> Anomalies` heading and its `none` sentinel are unchanged — the
  `sd-status` skill's final-response contract depends on them. Advisory entries
  render in the same list with an `[advisory]` prefix, so one heading still
  holds everything and the two surfaces print the same lines.
- `nextSteps` (`:2334-2335`) keys on blocking anomalies; advisory ones already
  have their recovery in the follow-up rows.

## Worktree-held default branch (absorbed 08-08)

`git switch main` fails when another worktree holds `main`. Today that produces
`default_branch_switch_failed` (`housekeeping.sh:551`) and then
`branch_switch_incomplete` (`:925`), both opaque, both blocking.

The fix is **not** to reclassify those two codes wholesale — a switch that fails
for a dirty tree or an index lock is a real blocker and must keep blocking.
Instead, diagnose the cause and emit a distinct code only when the worktree
inventory proves it:

- on switch failure, read `git worktree list --porcelain -z` and look for a
  worktree (not this one) whose branch is `$DEFAULT_BRANCH`;
- if found: `add_anomaly default_branch_held_elsewhere "$DEFAULT_BRANCH is
  checked out in worktree <path>; left this checkout on <branch>"`;
- if not found: keep `default_branch_switch_failed`, now carrying the bounded
  first line of git's stderr so the opaque message names its cause. Bounded to
  fit `validate_event`'s 1000-character limit and stripped of control characters
  (`housekeeping-result.py:207-215`);
- the downstream skip at `:925` mirrors it: `branch_retained_default_held` when
  the default was held, `branch_switch_incomplete` otherwise.

In `housekeeping-result.py`, alongside the existing `INDETERMINATE_ANOMALY_CODES`
precedent (`:54-63`):

```python
ADVISORY_ANOMALY_CODES = frozenset(
    {"default_branch_held_elsewhere", "branch_retained_default_held"}
)
```

`classify_outcome` splits `event_codes` into blocking and advisory. Only blocking
codes select `blocked` or contribute to `reasonCodes`; advisory codes stay in
`result["anomalies"]` with their full message, so the evidence is present and
the verdict is `clean` with `reasonCodes: []`. Advisory codes are checked
against `INDETERMINATE_ANOMALY_CODES` first, so an advisory code can never
outrank an indeterminate one.

**Honest residual:** after this change the checkout is still on the merged
feature branch and that branch is still present, because the default branch is
held elsewhere and this run cannot legally take it. That is reported — the
anomaly names the holding worktree, and the branch appears in the classification
as `merged` + `heldByWorktree` — but it is not resolved. Making housekeeping
detach or relocate the worktree is a separate decision and is out of scope here;
the absorbed task asked for the verdict shape and the diagnosis, and this
delivers exactly those.

## Naming the cause in the reader's structure

`status_anomalies` (`housekeeping-result.py:259`) is the opaque code the PRD
objects to: the top-level `anomalies` array is empty while the cause sits one
level down in `status.anomalies`. Replace it with the real codes:

- read `status["anomalyDetails"]`, keep entries with `severity == "blocking"`,
  and append `status_<code>` for each (deduplicated by the existing
  `deduplicate`, `:219`);
- when `anomalyDetails` is absent — an embedded document from an older collector
  — fall back to today's exact behavior: block on any `status.anomalies` and
  append the single `status_anomalies` code. This keeps a mixed-version pair
  fail-closed rather than silently unblocking. That fallback is the only path that can
  still emit the shape acceptance criterion 1 names, and it is reachable only by
  pairing an old collector with a new result script — a combination the pack
  never ships, since both files come from one release and `make generate` plus
  surface-closure enforce it.

So the PRD's signature shape becomes, for a genuinely dirty tree:
`reasonCodes: ['status_working_tree_dirty']` instead of
`reasonCodes: ['status_anomalies']`.

`docs`/skill update: `sd-housekeeping/SKILL.md:132` currently says a clean result
has "no anomalies". That becomes "no blocking anomalies", with one sentence
naming the advisory class and where its evidence lives.

## Compatibility and blast radius

Enumerated from the filesystem, not from the edit list:

- `status_anomalies` is read by exactly one non-archive consumer,
  `tests/test_housekeeping_result.py:244-251`. That test is rewritten to pin the
  new derived code and a second test pins the legacy fallback.
- "extra local branches" appears in no live skill, doc, or script other than the
  collector itself (`.trellis/.backup-*` and `.git/lost-found` hits are inert).
- `report["anomalies"]` keeps its type and contents, so every existing reader
  (`collect_follow_ups`, `next_steps`, `render_local`, the fleet roll-up, the
  work-loop status snapshot) is unaffected by the additive keys.
- Additive keys only; `STATUS_SCHEMA_VERSION` stays 2 and
  `housekeeping-result.py`'s `SCHEMA_VERSION` stays 1.
- Four copies of each edited script exist (`templates/scripts/`, `scripts/`,
  `plugins/sd/bin/`, `plugins/sd/machine-payload/scripts/`). Only
  `templates/scripts/` is edited; `make sync` and `make generate` produce the
  rest, and the check is a filesystem enumeration that every copy carries the
  change and none carries the old text.

## Rejected alternatives

- **Keep the entry and surface the advisory/strict distinction in both reports.**
  This was the PRD's other branch of open question 1. Rejected: it makes the
  reports mutually explicable but leaves the verdict permanently `blocked` for
  anyone with concurrent worktrees, which is the actual damage.
- **Per-anomaly severity supplied by the caller through `--prior-anomaly`.**
  Rejected: it splits severity ownership across two scripts and a CLI. One rule
  (replayed shell anomalies are advisory in the collector, authoritative in the
  result script) needs no plumbing and no second source of truth.
- **Change `anomalies` to a list of objects.** Rejected: a schema break across
  every consumer for information a parallel additive key carries just as well.
- **Reclassify `default_branch_switch_failed` unconditionally.** Rejected: it
  would silently unblock a dirty tree or a stale index lock. The evidence-gated
  distinct code blocks exactly what it should.
- **Fetch to make merge evidence current.** Rejected: sd-status is read-only and
  reports `cached` freshness by contract; `unknown` with a named reason is the
  correct answer to a question stale refs cannot settle.

## Risks

- **False `merged`.** A branch merged with `--squash` or rebased is not
  reachable from the default tip and reads `unmerged`; with its PR closed it
  then reads `unmerged-without-pull-request`. The advisory entry points at a
  branch that is really finished. Accepted: the entry is advisory and names the
  branch, so the cost is one look; the alternative (patch-id equivalence) is a
  large, slow addition for a follow-up-grade signal. Recorded in the collector's
  docstring so a reader is not surprised.
- **Large branch counts.** Classification is O(branches) with one extra
  `for-each-ref --merged` invocation, and rows are capped at `MAX_ITEMS`.
- **Fleet cost.** `build_local_report` runs once per consumer in fleet mode, so
  this adds one `for-each-ref` per consumer. It is a local ref walk with no
  network, alongside the several git calls each consumer already costs.
- **Advisory becoming the new noise floor.** Mitigated by emitting only the two
  entries that answer a question, and by keying `attention` on blocking
  anomalies.
