# Implementation plan

Ordered so that the shared rule lands and is proven before anything depends on
it, and so the pre-existing debt the narrowing exposes is cleared *before* the
narrowing can fail a green repo.

## Step 0 — clear the debt the narrowing will expose

Four rows in one active task self-cite today:

```
.trellis/tasks/08-09-deployment-thin-consumers/implement.jsonl:1,2
.trellis/tasks/08-09-deployment-thin-consumers/check.jsonl:1,2
```

Both point at that task's own `research/consumer-ci-usage.md` and
`research/claude-code-plugin-capabilities.md`.

Do this first, not last. The narrowing fires on any *changed* task context file,
so leaving these until after step 2 means the first unrelated edit to that task
fails a check the author did not touch.

Repair per the design's own guidance: fold each pointer's substance into the
row's `reason`, or repoint at a `.trellis/spec/**` path if one already covers it.
Do not delete the research files.

This edits **another active task's** manifests, which is normally out of scope.
It is in scope here because this task's rule change is what breaks them: shipping
a rule that fails a task nobody touched, and leaving the repair to whoever next
edits it, moves the cost onto someone with no context for it. Keep the edit to
those four rows — no other change to that task.

Enumerate, do not hand-count — the same script that finds them is the acceptance
check for this step:

```bash
python3 - <<'PY'
import json, pathlib, re
own = re.compile(r'^(\.trellis/tasks/(?:archive/\d{4}-\d{2}/)?[^/]+)/')
hits = []
for f in pathlib.Path('.trellis/tasks').rglob('*.jsonl'):
    m = own.match(f.as_posix())
    if not m:
        continue
    for i, line in enumerate(f.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            ref = json.loads(line).get('file')
        except Exception:
            continue
        if isinstance(ref, str) and (m2 := own.match(ref)) and m2.group(1) == m.group(1):
            hits.append(f'{f}:{i} -> {ref}')
print(len(hits))
for h in hits:
    print(' ', h)
PY
```

**Gate:** prints `0`. Expect `4` before the repair.

## Step 1 — narrow the shared context rule

`scripts/sd-ai-command-pack-review-preflight.mjs`,
`findTrellisTaskContextIssues` (`:3981`):

- derive the citing file's own task directory from the `file` argument with
  `/^(\.trellis\/tasks\/(?:archive\/\d{4}-\d{2}\/)?[^/]+)\//`;
- after the existing allowed-root test passes, emit `kind: 'self_reference'`
  when the reference's own task directory equals the citing file's. Snake_case
  is load-bearing: the bookkeeping reason code is interpolated as
  `task_context_${issue.kind}` (`:876`);
- add the branch to **both** reporters — the bookkeeping ternary at `:871-875`
  and the merge-time loop at `:3820-3843`, whose `else` otherwise labels the new
  kind with the allowed-roots message and names the wrong rule. Use the
  two-option repair message from the design, not a bare refusal.

Tests in `tests/` alongside the existing `findTrellisTaskContextIssues`
coverage. Four cases, and the third and fourth are the ones that matter:

1. own `research/foo.md` → rejected;
2. sibling task's `research/foo.md` → **accepted** (deliberate, requirement 5);
3. archived task citing its own archived `research/**` → rejected — proves the
   `owner` pattern captures the `archive/YYYY-MM/` prefix rather than treating
   the archive form as automatically stable;
4. `.trellis/spec/**` → accepted.

**Gate:** new tests pass; `node scripts/sd-ai-command-pack-review-preflight.mjs`
reports 0 failures on this repo — which, after step 0, it will.

**Falsification:** revert only the `self_reference` branch and confirm case 1
fails while 2-4 still pass. A test that passes with the rule removed is testing
nothing. (This is the exact check that caught the ordering test on PR #440.)

## Step 2 — the `TBD` placeholder rule

New exported function beside the others — `findTrellisPlanningPlaceholders(file, text)`
— matching the **three** shapes `_default_prd_content` writes, not two: the Goal
body `TBD.` (`task_store.py:199`), the `- TBD` requirement bullet (`:209`), and
the `- [ ] TBD` acceptance criterion (`:213`). The Goal line is the one an
earlier draft of this plan missed, and it is the one a hand-edited PRD most
often leaves behind, because it does not look like a list item.

Adopt it in **both** entry points, merge-time and `seeded-task`. A rule that only
the fleet lane runs is a second rule engine with one caller.

Anchor on the line shape, not a bare substring: a PRD is allowed to discuss the
string `TBD` in prose, and this task's own PRD does.

**Gate:** a fixture PRD with a seeded `- TBD` bullet fails; this repo's real
PRDs — including this one, which mentions `TBD` in prose — still pass.

## Step 3 — the `seeded-task` subcommand

- extend the dispatch at `:500` and the usage text at `:544-547`;
- accept `--task-dir` and `--repo`, already parsed at `:566`/`:591`;
- call `validateBookkeepingTaskDirectory(taskDir, {add, archived: false,
  completionReady: false, seedReady: true})` — **one** call, not a
  hand-composition of its parts. It already runs the metadata, PRD, and context
  rules from disk;
- add the `seedReady` flag to `validateBookkeepingTaskContexts` so it skips the
  lone-`_example` exemption at `:870`. Default `false`, so merge-time behavior
  is byte-identical;
- call `validateTrellisRootTaskBaseBranch` (`:3331`) explicitly — the
  bookkeeping validator does **not** wire it up; its only call site today is the
  merge-time preflight at `:3186`;
- resolve the default branch with the existing `trellisRootDefaultBranchName()`;
  do not add a second resolver. Record the resolved name **and whether it came
  from `SD_AI_COMMAND_PACK_DEFAULT_BRANCH` or `origin/HEAD`** in `evidence`
  (`:4738-4744`);
- emit the design's envelope, reusing the existing `task_*` reason codes and
  adding only `task_prd_placeholder` and `task_base_branch_invalid`.

**Gate:** run against this repo's own seeded task from a *different* cwd with
`--repo`, and confirm the result is identical to the same run with cwd inside
the repo. `--repo` correctness is the whole cross-checkout premise; a gate that
silently reads the wrong repository is worse than no gate (the trap
`sd-ai-command-pack-update-spec-kb.py` already documents). Include a git-backed
assertion, not just a filesystem one: run with `--repo` pointed at a checkout
whose default branch differs from this one and confirm the *consumer's* branch
name lands in `evidence`, proving `runGit`'s `cwd: rootDir` followed.

**Env-leak check:** with `SD_AI_COMMAND_PACK_DEFAULT_BRANCH` exported to a value
that is wrong for the consumer, the run must not silently pass. This is the one
way a green `base_branch` result can be meaningless.

**Un-exemption check:** a manifest whose only row is the untouched `_example`
scaffold must fail under `seeded-task` and still **pass** the merge-time
preflight. Both halves matter — the second is the regression the exemption's
comment at `:850-857` was written to prevent.

**Fail-closed check:** point `--task-dir` at a missing directory and at a
`task.json` containing `{`. Both must exit `1` and never report `valid`. Assert
the status the shared path actually produces — `invalid`, because `add()`
defaults to `disposition: 'invalid'` (`:629`) — not `indeterminate`. Reserve
`indeterminate` for an unresolvable default branch, and assert that case
separately.

## Step 4 — SKILL.md `checkout-validation`

`.agents/skills/sd-fleet-refresh/SKILL.md:152-165`:

1. after `task.py create`, `task.py set-base-branch <task-dir> <default-branch>`,
   with the explicit note that `create --base-branch` must not be used;
2. replace the prose description assertion with the `seeded-task` invocation,
   run from the pack source checkout with `--repo <consumer>`;
3. keep the "belt-and-suspenders" sentence as rationale only.

**Gate:** `node scripts/sd-ai-command-pack-review-preflight.mjs` and
`scripts/sd-ai-command-pack-check.py --json` both clean — the doc path-reference
gate is what catches a wrong script name or a moved path here.

## Step 5 — acceptance criteria, against a scratch consumer

The PRD's criteria are checkable without a live campaign. Seed each defect
deliberately in a throwaway checkout and run the stage gate:

| Criterion | Fixture |
| --- | --- |
| `base_branch` correct on both vendored revisions | one consumer checkout (old `task_store.py`) + this repo (new). Pick by grepping `task_store.py` for `resolve_default_branch`, **never by pack version** — loadsmith is at 0.71.2 and still carries the old one |
| empty description fails | `task.py create` with `--description ""` |
| `TBD` / `_example` fails | untouched `task.py create` output |
| correct task advances | this repo's own seeded task |
| one rule source | read both call sites; confirm a single function. Not "two implementations agreed on one sample" |
| self-citation fails, with a usable alternative named | a row citing the fixture's own `research/**` |
| spec + sibling research still pass | rows citing `.trellis/spec/**` and another task's `research/**` |

## Review gates

- Adversarial planning review before `task.py start` (already run for this
  batch).
- `sd-review-pr` loop on the PR; treat every Copilot finding as a claim to
  verify against source before acting, and rebut with evidence when it is wrong.
- Finalization: this task is `planning` today, so if it starts, its receipt
  becomes `--mode completion`, not the `--mode planning` the PRD-only rounds used.

## Rollback points

Each step is independently revertible and ordered so nothing later depends on
an unproven earlier step:

- step 0 is a content fix with no rule behind it yet — safe to keep on revert;
- step 1 reverts to the pre-narrowing branch; step 0 stays valid regardless;
- steps 2-3 revert as a unit if the subcommand is abandoned, but step 2's rule
  can stand alone in the merge-time preflight;
- step 4 is documentation and reverts independently of all of it.

No step writes persistent state, changes a receipt schema, or touches a
consumer checkout.
