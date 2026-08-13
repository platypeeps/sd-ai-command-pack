# Design

## Two surfaces, one rule source

| Surface | Kind | Ships to consumers? |
| --- | --- | --- |
| `scripts/sd-ai-command-pack-review-preflight.mjs` | new `seeded-task` subcommand + two narrowed/extended shared rules | yes, at `install-update` |
| `.agents/skills/sd-fleet-refresh/SKILL.md` | `checkout-validation` stage text | no — source-only skill |

Requirement 4 forbids restating the preflight's rules. The strongest available
form of that is not "call the same three helpers" but "call the same *entry
point*": `validateBookkeepingTaskDirectory` (`:750`) already composes task-record
validation, PRD checks, and context-manifest checks, already reads from disk
rather than from git, and is already parameterized for a lifecycle stage by its
`completionReady` flag. The `seeded-task` command is that function with a
different flag, not a new engine beside it.

## Where the gate runs

**From the pack source checkout, against the consumer's task directory.** Not
from the consumer's installed copy.

`checkout-validation` is `LANE_STAGES[0]` and `install-update` is
`LANE_STAGES[1]` (`scripts/sd-ai-command-pack-fleet-controller.py:44-56`). At
the moment the seeded task exists and is checkable, the consumer still carries
the *previous* release, whose preflight exits `2` with
`unknown review-preflight command` (`:514-517`) — on exactly the consumers that
have not been refreshed yet. That is requirement 1's trap wearing a different
hat: a remedy that ships with the release it guards is absent wherever it is
needed. The precedent is already in the skill — `sd-review-pr`'s fleet path runs
`sd-ai-command-pack-fleet-review-classify.py` from `source-root` against the
consumer checkout.

```bash
node scripts/sd-ai-command-pack-review-preflight.mjs \
  seeded-task --repo <absolute consumer checkout> \
  --task-dir <consumer-relative task dir> --json
```

`--repo` needs no new plumbing and is genuinely repo-wide: it is parsed at
`:566`/`:591`, assigned to the module-level `rootDir` at `:616`, and `runGit`
spawns with `cwd: rootDir` (`:4661-4666`). Both filesystem reads and git queries
therefore target the consumer.

**One leak to close.** `trellisRootDefaultBranchName()` prefers the
`SD_AI_COMMAND_PACK_DEFAULT_BRANCH` environment variable over the repository's
`origin/HEAD` (`:4738-4744`). Under `--repo`, a value exported for the *source*
checkout would silently decide the *consumer's* default branch — and the
base_branch rule is the one thing this gate exists to enforce. The lane must not
export it globally; if a consumer needs an override it belongs to that
consumer's invocation. The subcommand records the resolved branch name and its
source in `evidence` so a wrong answer is visible in the receipt rather than
silent.

## Rule inventory

| Property | Owner today | Action |
| --- | --- | --- |
| non-empty `description`, `id`/`name`, timestamps, topology | `validateBookkeepingTaskDirectory` → `validateTrellisBookkeepingMetadata` (`:817`) | inherited free |
| `_example` scaffold row, malformed JSONL, reference outside allowed roots | same → `validateBookkeepingTaskContexts` → `findTrellisTaskContextIssues` (`:3981`) | inherited free, one narrowing + one un-exemption |
| citation of the citing file's **own** task directory | nothing | new issue kind in the same function |
| `base_branch` equals default branch | `validateTrellisRootTaskBaseBranch` (`:3331`) — **not** wired into the bookkeeping validator; its only call site is the merge-time preflight (`:3186`) | call it explicitly from the new command |
| `- TBD` planning placeholders | **nothing, anywhere** | new exported function, adopted by both entry points |

`TBD` is not an oversight in that table. It appears in exactly one file under
`scripts/**` and `.trellis/scripts/**` — `task_store.py`, where it is *written*.
The ready gate at `.trellis/workflow.md:424` is scoped to the two manifests and
says nothing about the PRD.

### What `completionReady: false` buys

`pre-archive` passes `completionReady: true`, which turns on two archive-only
rules: status must be `in_progress`/`review` (`:820`), and `branch` must be
non-empty (`:823`). A task at `checkout-validation` legitimately fails both, so
the seeded-task command passes `false` — the same lifecycle parameterization the
function already uses, rather than a fork of it.

### The lone-scaffold exemption must be switched off here

This is the subtle one, and it contradicts a claim the PRD made before this
design existed.

`validateBookkeepingTaskContexts` skips the `seed` finding when the manifest's
*only* row is the generated `_example` scaffold (`isPristineTrellisTaskContextScaffold`,
`:3932`; skip at `:870`). The comment above it explains why: at merge time a lone
scaffold is indistinguishable from an unfilled manifest, and failing it produced
a late completion-time failure.

So the merge-time preflight does **not** reject a freshly created seeded task's
untouched manifests. Defect 3 is less covered than the PRD's earlier wording
implied — for the exact shape a fleet lane produces, it is not covered at all.

At `checkout-validation` the ambiguity that justifies the exemption does not
exist: the stage's whole purpose is to assert the manifests were filled, and an
unfilled manifest *is* the defect. The command therefore passes a `seedReady`
flag that disables the exemption. That is parameterization of the shared rule,
not a restatement of it — the same shape as `completionReady`, and the reason
this design does not need a second scaffold check.

## The self-citation narrowing

Implemented **inside** `findTrellisTaskContextIssues` (`:3981`), which already
receives the citing file's path as its first argument, so the citing task
directory is derivable without a new parameter and without a second call site
learning the rule:

```js
// .trellis/tasks/<slug>/check.jsonl  ->  .trellis/tasks/<slug>
const owner = /^(\.trellis\/tasks\/(?:archive\/\d{4}-\d{2}\/)?[^/]+)\//.exec(file)?.[1];
```

A reference that clears the existing allowed-root test is rejected when its own
task directory, extracted with the same pattern, equals `owner`. New issue kind:
`self_reference` — snake_case, because the bookkeeping reason code is built by
interpolation as `task_context_${issue.kind}` (`:876`) and every sibling code is
snake_case.

Placing it here means the narrowing applies to the merge-time preflight in the
same commit — which matters, because the merge-time run is what caught nothing
on hoa-manager PR 247. A `seeded-task`-only rule would leave every non-fleet task
free to reproduce the defect.

`.trellis/spec/**` is untouched: specs do not move on archival.

**Deliberately not covered:** a *sibling* task's `research/**`, which dangles
later when that sibling archives. Requirement 5 states this. Detecting it needs
a prediction about a directory that still exists and still resolves — a different
rule with a different failure mode.

### Why the archive form stays allowed

The allowed-root regex admits `archive/YYYY-MM/`. An archived task's `research/**`
is a *stable* citation — the move already happened — so the narrowing compares
directories rather than rejecting the archive shape. An archived task citing its
own archived research is still self-reference and is still rejected; the `owner`
pattern captures the archive prefix for exactly that reason.

### Two message sites, not one

A new issue kind is only half-wired if one reporter knows it. Both must gain a
branch, and a test must cover each:

- the bookkeeping ternary at `:871-875`, which feeds `task_context_self_reference`;
- the merge-time reporting loop at `:3820-3843`, whose `else` currently assumes
  every non-`seed`, non-`malformed` issue is an allowed-roots violation and would
  otherwise print a message that names the wrong rule.

## Subcommand contract

Same envelope as the existing bookkeeping validators — `schemaVersion: 1`,
`kind: "trellis-bookkeeping-validation"`, `status`, `reasonCodes`, `findings`,
`evidence` — so the fleet lane consumes it the way it already consumes
`pre-archive`.

- `status: "valid"`, reason `seeded_task_valid`, exit `0`.
- `status: "invalid"`, exit `1`. **Reason codes are the existing ones**, not a
  parallel namespace: `task_metadata_invalid`, `task_json_invalid`,
  `task_prd_empty`, `task_context_seed`, `task_context_malformed`,
  `task_context_reference`, `task_context_self_reference`. Only the two rules
  this task adds need new codes — `task_prd_placeholder` and
  `task_base_branch_invalid`, named to sit inside the same namespace.
- Everything fails closed, but not all of it is `indeterminate`, and the command
  must not invent a second answer for a condition the shared path already
  decides. `add()` defaults to `disposition: 'invalid'` (`:629`), so an
  unreadable task directory or unparseable `task.json` comes back **`invalid`**
  (`:784`, `:813`) — the same verdict `pre-archive` gives it. The new command
  keeps that. `indeterminate` is reserved for the one condition the shared path
  does not cover: a default branch that cannot be resolved, where the gate
  genuinely cannot tell. Both exit `1`; neither advances the stage.

Requirement 3 wants an actionable message, and here the shared rule is not
enough. `validateTrellisRootTaskBaseBranch` returns a message whose repair verb
is `task.py set-meta <task-dir> base_branch_exemption "<reason>"` (`:3350-3354`)
— the *escape hatch*, not the fix. Handed to a fleet operator verbatim it
advises stamping an exemption over the exact defect requirement 1 exists to
prevent. The finding therefore appends the `task.py set-base-branch <task-dir>
<default-branch>` repair and leads with it. This is additive: the shared rule
still decides *whether* the task is wrong, and only the remediation text is
stage-specific.

### The self-reference message must name an alternative

Requirement 5's last paragraph: "cite a spec instead" is not actionable when the
consumer's specs are all product-domain. The finding names the two forms that
actually work for a refresh lane:

1. move the facts into the *pack's* task and cite nothing consumer-local; or
2. inline the fact into the `reason` string, which is what the field is for — a
   manifest row is a pointer plus a rationale, and a rationale that needs no
   pointer is complete on its own.

Option 2 is what `08-13-sd-ai-command-pack-0-71-2` should have done on
hoa-manager.

## SKILL.md changes

Two edits to the `checkout-validation` bullet (`SKILL.md:152-165`):

1. After `task.py create`, run `task.py set-base-branch <task-dir> <default-branch>`
   — never `create --base-branch`, which the skewed consumers reject as an
   unrecognized argument. `set-base-branch` exists in both vendored revisions
   (verified: 5 occurrences in `loadsmith/.trellis/scripts/task.py`; `:15,56,392`
   here).
2. Replace the prose "assert the `description` is present and non-empty" with the
   `seeded-task` invocation, run from the source checkout with `--repo`. The
   prose guard is the thing that got skipped; the sentence stays as rationale.

## Compatibility and rollout

- **New subcommand; existing ones unchanged.** The dispatch at `:500` and the
  usage text at `:544-547` gain a third name.
- **Two behavior changes reach the merge-time preflight**, by design: the
  self-reference narrowing, and the `TBD` rule. Both are new failures for
  existing repos. The narrowing has four live instances here today (all in one
  active task) and the implementation plan clears them first.
- **The `seedReady` un-exemption does not reach merge time.** It is off unless
  the seeded-task command asks for it, so the late-completion-failure regression
  its comment documents cannot recur.
- **Rollback** is deletion of the subcommand plus reversion of two branches in
  shared functions. Nothing persists state and no receipt schema changes.
