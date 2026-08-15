# Design: convert the canary cohort to thin mode

Written 2026-08-15 against measured state, not against the state the PRD was
drafted in. The PRD's numbers date from 0.71.2; the pack is at 0.71.11 and
every figure below was re-measured today. Where the two disagree, this file
says so explicitly rather than silently replacing a number.

## D0. What the measurement changed about the plan

The PRD's requirement 1 opens with step 0, "the consumer must already hold the
current payload", and its sequence assumes the only thing standing between a
canary and `--thin` is that step plus a `clear` resweep. Measured today, three
separate gates are shut, and two of them are not in the PRD's sequence at all:

| gate | measured 2026-08-15 | in the PRD? |
|---|---|---|
| consumer payload currency | all three at `0.71.6`, verdict `refresh-required`; pack is `0.71.11` | yes, step 0 |
| machine scope currency | `packVersion 0.71.2`, `pluginVersion 0.71.2` against `targetPackVersion 0.71.11` | requirement 8, but recorded as satisfied at 0.71.2 |
| pack-owned citations | 15 `packDefects` per consumer, identical set, in six `repo-native` pack surfaces | named as child 2b's job and recorded as done |
| consumer-owned citations | 49 / 50 / 34 blockers across 8 / 5 / 9 files | yes, requirement 1 step 1 |

`decide()` (`scripts/sd-ai-command-pack-thin-resweep.py:1773`) returns `blocked`
if **any** of `blockers`, `packDefects`, `missingFiles`, or a dirty worktree is
non-empty. So the 15 pack-owned citations alone would block all three canaries
even if every consumer-owned citation were rewritten today.

### D0a. Why the pack-owned citations are still there

`08-10-thin-prompt-surface-repoint` (child 2b, archived, all acceptance
criteria checked) names these exact six files and these exact line numbers in
its own PRD table, and its acceptance criterion reads "the pack side reports no
remaining hit among the seven surfaces". That task shipped before 0.71.4;
loadsmith holds 0.71.6, so it *has* 2b's change. The citations are still
present because 2b's fix made the cited paths **resolve** under both layouts —
its acceptance criteria are about resolution, not about absence — while the
resweep's rule is about the literal reference. Between 2b and today the scanner
also tightened repeatedly (its own comments record rounds R9 through R16).

This is not a regression to revert and not a defect in 2b's reasoning. It is
one task's acceptance criterion measuring a different property than the gate
that now governs. Phase 0 below closes the gap that leaves.

## D1. Phase order, and why this order

Five phases. The ordering is forced, not chosen: each phase's output is the
next phase's precondition, and doing them out of order is the trap
`docs/FLEET_ROLLOUT.md` names.

```
0. pack     repoint the 15 pack-owned citations; ship 0.71.12
1. machine  install.py --machine + plugin update to 0.71.12
2. refresh  the three canaries 0.71.6 -> 0.71.12, one PR each
3. rewrite  each canary's own citations, same PR or a second one
4. convert  resweep -> --thin -> 2b -> 2c -> consumer PR -> pack registry PR
5. revert   --revert-thin on one named canary, CI green, re-convert
```

Phase 0 before phase 2 because a refresh installs the pack's current text: a
consumer refreshed to a version that still carries the 15 citations arrives at
phase 4 blocked by them. Phase 1 before phase 4 because conversion removes the
surfaces the machine payload is supposed to supply; doing it while the machine
sits at 0.71.2 is the one configuration that loses a working surface (PRD
requirement 3, requirement 8). Phase 3 before phase 4 because `--thin` refuses
on a `blocked` verdict and that refusal is the contract, not an obstacle.

## D2. Phase 0: the scanner is wrong about 14 of the 15

**Rewritten in review round 2. The version below this heading's first draft
proposed rewording all six templates; that would have been actively harmful and
is recorded here rather than deleted, because the reasoning is the finding.**

The conversion already repoints these files. `repoint_kept_references`
(`installer/thin.py:675`) exists for exactly this population, and its docstring
names the consequence it prevents: kept `repo-native` files "still say
`scripts/<name>` and `docs/SD_AI_COMMAND_PACK.md`, which is exactly what the
conversion just removed... the resweep reports every one of them as a
`packDefect`." `THIN_PROFILE.literal_rewrites`
(`installer/references.py:355`) carries purpose-built rules for "the three
globs in the Copilot managed block".

Executed against loadsmith's actual bytes, `planned_repoints` changes all six
files and takes the removed-path citations from **17 to 1**:

| file | before | after |
|---|---:|---:|
| `.github/PULL_REQUEST_TEMPLATE.md` | 2 | 0 |
| `.github/copilot-instructions.md` | 7 | **1** |
| `.github/prompts/sd-housekeeping.prompt.md` | 3 | 0 |
| `.github/prompts/sd-review-learnings.prompt.md` | 2 | 0 |
| `.github/prompts/sd-review.prompt.md` | 2 | 0 |
| `.github/prompts/sd-status.prompt.md` | 1 | 0 |

So the pack's fat text is not the defect. A fat consumer that says
`scripts/sd-ai-command-pack-full-check.sh` is telling the truth — the script is
right there. Rewording those six templates to satisfy a pre-conversion scan
would degrade correct guidance for every fat consumer in the fleet, to work
around a measurement that is itself mistaken.

### D2a. The deadlock, stated plainly

`decide()` (`thin-resweep.py:1773`) returns `blocked` on a non-empty
`packDefects` bucket. `--thin` refuses any verdict that is not `clear`
(`installer/thin.py:124`). The scanner reads the tree's **current** bytes and
performs no repoint simulation (`thin-resweep.py:1596-1634`). Therefore every
fat consumer holding pack-owned kept files reports `packDefects` and can never
reach `clear`.

That is not a canary problem. **No consumer in the fleet can convert today**,
and this task is the first thing to actually try, which is why it surfaced
here rather than in the tooling task that built both halves.

### D2b. The fix: measure what the verdict authorizes

The verdict authorizes a conversion. So the bytes it should judge are the ones
the conversion produces, not the ones preceding it. For a **kept, pack-owned**
file, the resweep scans the text `planned_repoints` would write, and reports a
`packDefect` only for a citation that survives that rewrite.

Deliberately narrow. It changes nothing about `blockers` — a consumer-owned
citation is still scanned as written, because nothing rewrites those and the
consumer is the one who must act. It changes nothing about `scheduled`,
`advisories`, or `missingFiles`. It reuses the installer's own computation
rather than restating the rewrite rules in the scanner; two implementations of
"what will the conversion write" is the drift A-046 was about.

The honest cost: the resweep gains a dependency on the installer's plan, so a
consumer's verdict now depends on the pack version computing it. That is
already true of the removal set — `--thin` re-verifies the verdict's bindings
and refuses a stale one — so the coupling is not new, only newly visible.

### D2c. The one real defect

The survivor is `.agents/skills/sd-*` in `copilot-instructions.md`. The rewrite
turns `` `.agents/skills/sd-*/SKILL.md` `` into
`` `~/.agents/skills/sd-*/SKILL.md` ``, and `cites_removed_path` matches path
**suffixes** (`thin-resweep.py:1225`), so the rewritten text still ends with
the removed path and is still a citation of it.

This exact trap is already documented one screen above the rule that falls into
it. `AGENTS_DOC_DIRECTORY` (`installer/references.py:326`) explains that
`~/.agents/docs/SD_AI_COMMAND_PACK.md` "ends with the removed
`docs/SD_AI_COMMAND_PACK.md` and is classified as a citation of it", and solves
it by naming **the directory** and leaving the file to prose. The skills glob
needs the same treatment and did not get it. Fix: rewrite to `~/.agents/skills`
and let the surrounding sentence say what lives there.

### D2d. What phase 0 is now

Two changes, not six template rewrites:

- **0A** — the resweep scans post-repoint bytes for kept pack-owned files.
- **0B** — the `.agents/skills/sd-*/SKILL.md` literal rewrite names the
  directory, per D2c.

Neither is a payload text change, so the six templates keep their fat-correct
wording. 0B touches `installer/references.py`, which is shipped payload, so the
cascade and a version bump to `0.71.12` still apply.

**Validation is immediate and local**, which the first draft got wrong by
deferring it to a phase-2 refresh: the resweep runs from this checkout and
reads consumer bytes, so `packDefects: 0` for all three canaries is measurable
the moment 0A and 0B land, with the canaries untouched at 0.71.6.

## D2-superseded. What the first draft proposed (retained for provenance)

The 15 citations, measured against `templates/`, are:

| template | lines | cites |
|---|---|---|
| `.github/copilot-instructions.sd-ai-command-pack.md` | 7, 8, 17, 32, 35, 87, 89 | `docs/SD_AI_COMMAND_PACK.md`, `scripts/sd-ai-command-pack-install-audit.py`, globs `.agents/skills/sd-*/SKILL.md` and `**/skills/sd-*/**`, `scripts/sd-ai-command-pack-*` |
| `.github/PULL_REQUEST_TEMPLATE.md` | 7, 14 | `docs/SD_AI_COMMAND_PACK.md`, `scripts/sd-ai-command-pack-full-check.sh` |
| `.github/prompts/sd-housekeeping.prompt.md` | 37, 38 | `scripts/sd-ai-command-pack-housekeeping.sh` |
| `.github/prompts/sd-review-learnings.prompt.md` | 44, 46 | `scripts/sd-ai-command-pack-review-learnings.py` |
| `.github/prompts/sd-review.prompt.md` | 43 | `scripts/sd-ai-command-pack-review.py`, `scripts/sd-ai-command-pack-toolchain.sh` |
| `.github/prompts/sd-status.prompt.md` | 43 | `scripts/sd-ai-command-pack-toolchain.sh` |

The line numbers above are **template-relative**. Each consumer's
`.github/copilot-instructions.md` carries a consumer-owned prologue of its own
length before the pack's managed block, so the same citation sits at a
different line in each of the three (loadsmith's offset is 10). The set is
identical across all three canaries **by file and text** — verified by
comparing `(file, detail)` pairs, which match exactly; comparing `(file, line)`
pairs does not, and reporting that as "identical" would have been a claim about
loadsmith presented as a claim about the cohort.

All seven `copilot-instructions` hits fall inside
`<!-- SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START -->`..`:END`, which spans the
whole template. The `TRELLIS:COPILOT-GUIDANCE` block visible in a consumer's
installed file is a **separate, Trellis-owned** block appended after it. This
task edits the pack's block only; nothing here implies an upstream Trellis
change or PR (`AGENTS.md:25-28`).

Three different fixes, because the citations are three different kinds:

**Kind 1 — an executable the reader is told to run** (`full-check.sh`,
`housekeeping.sh`, `review-learnings.py`, `review.py`, `toolchain.sh`,
`install-audit.py`). These get the treatment 0.71.11 exists to enable: name the
command, and where a path is needed, resolve it. The four prompt files already
carry "resolvable, either as a bare command on `PATH` or ..." phrasing, so the
edit is to drop the vendored alternative rather than to invent a new mechanism.

**Kind 2 — a document reference** (`docs/SD_AI_COMMAND_PACK.md`, four hits).
The document is `machine-other`; under thin it lives in the machine payload. A
consumer-visible surface should not name its repository-relative path at all.
Refer to it by title, the way the shipped guide already refers to itself.

**Kind 3 — a glob** (`scripts/sd-ai-command-pack-*`, `.agents/skills/sd-*/SKILL.md`,
`**/skills/sd-*/**`). No runtime resolver rewrites a glob — the same bound
0.71.11's PRD stated and did not claim. These appear in
`copilot-instructions.md`'s review-guidance block, where they are describing
*which files a reviewer should not nitpick*. Under thin those files are not in
the consumer at all, so the correct edit is to scope the guidance to the
surfaces that survive and drop the patterns that describe deleted ones.

Phase 0 is a payload change, so the full cascade applies: template edit,
`make sync`, `make generate`, `candidate-check`, `make generate`, version bump
to `0.71.12` with a CHANGELOG heading, `make sync` for the mirrors.

*(End of the superseded draft. Its D2a proposed deferring phase 0's validation
to a phase-2 refresh; D2d supersedes that with a local measurement.)*

## D3. Phase 3: the consumer rewrite policy

133 blockers across the three canaries, in 22 files. They are not one problem:

| class | example | count | fix |
|---|---|---|---|
| generated map | `loadsmith/docs/repomix-map.md` | 30 | exclude pack payload from the generator's input, then regenerate — see D3a; regeneration alone does **not** clear it |
| test fixture strings | `hoa-manager/scripts/check-review-preflight.test.mjs` | 13 | rewrite the fixture with the test |
| live invocation | `loadsmith/scripts/check.sh`, `check_review_readiness.sh` | 17 | resolve through `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py --resolve <name>` |
| CI workflow | each canary's `.github/workflows/ci.yml` | 10 | same as live invocation, plus the `git ls-files` exclude patterns |
| agent-executed rule | `rwbp-coordinator/.prism/rules.json:55` | 1 | PRD requirement 4; repoint in the same PR |
| prose and spec docs | `.trellis/spec/**`, `docs/REVIEW_PATTERNS.md` | 8 | reword to name the command, not the path |
| glob | `scripts/sd-ai-command-pack-*` and friends | 18 | scope or drop, per D2 kind 3 |

### D3a. `docs/repomix-map.md` cannot be fixed by regenerating it

Round 1 of the review killed the obvious plan. `loadsmith/docs/repomix-map.md`
holds 30 of that consumer's 50 blockers, and the first instinct — "it is
generated, regenerate it" — does not work, because of what it is. The map is a
repomix **concatenation of the repository's files**, and the blocking lines at
1407-1410 are the body of `docs/SD_AI_COMMAND_PACK.md` embedded in it, under
that file's own `## File:` header.

That doc is pack-owned, `machine-other`, and present in a fat consumer. So the
citations are *correct* pre-conversion: the map faithfully reproduces a file
that faithfully names scripts that are really there. Regenerating before
conversion reproduces them exactly. Regenerating after conversion drops them —
but `--thin` refuses on a `blocked` verdict, so "after conversion" is not
reachable from here.

The fix is to stop feeding pack payload into the map:
`loadsmith/scripts/update_repomix` writes `docs/repomix-map.md`, and excluding
the vendored pack surfaces from its input both clears the 30 blockers and is
right on its own terms — the map exists so an agent can navigate loadsmith,
and after conversion that payload is not in loadsmith at all. Regenerate after
the exclusion lands.

Two things follow. The exclusion is a **consumer product-code change**, inside
the 2026-08-15 authorization for these three repositories. And the same shape
will recur in any consumer that tracks a generated whole-repo artifact; this
task fixes loadsmith's, and records the pattern for the post-canary cohort
rather than pre-solving it.

### D3b. History-shaped files are annotated, not rewritten

`hoa-manager/.trellis/tasks/08-07-task-manifest-context-roots/prd.md` holds one
blocker. It is a task record describing what was true when it was written.
Editing it so a scanner passes would make the record say something that was not
the case, which is a worse outcome than the blocker. It gets a dated note
naming the current path, leaving the original line intact and legible as
history — the same treatment this repository gives its own superseded figures.

The 36 hits in `rwbp-coordinator/scripts/check-review-churn.mjs` are a single
file and, at 36, are worth reading before assuming they are 36 edits: a file
that names the pack this many times is likely to hold one resolution helper and
many uses of it.

**Constraint carried from the campaign's authority.** These are consumer
product-code edits, authorized by the user for these three repositories on
2026-08-15 and for nothing else. No fourth consumer is touched. No edit lands
outside what a blocker cites plus what it forces.

## D4. Phase 4: conversion mechanics

Per canary, exactly the PRD requirement 1 sequence, unchanged — it is
executable as written and this design does not restate it. Two properties of
it that decide whether a step can be retried:

- The verdict is a **file**, and `--thin` re-verifies that the recorded
  bindings still describe the tree. Any commit between the resweep and the
  conversion invalidates it; re-run the resweep rather than reusing the file.
- `--thin` writes **both roots** in one invocation — the consumer tree and this
  repository's `docs/fleet/consumers.json` row — and refuses unless both are
  writable. The registry row is never written by hand. The two edits then
  travel in two PRs, consumer first, and the window between them is the
  pin-vs-mode skew the parent design accepts.

An abandoned conversion leaves both roots dirty and uncommitted:
`git -C <path> checkout -- .` and `git checkout -- docs/fleet/consumers.json`
restore them.

## D5. Phase 5: the revert proof

`loadsmith` is the named canary for the revert proof. It is chosen because it
is the middle of the sequential cohort — reverting the first would prove the
revert only against a tree no other conversion had followed, and reverting the
last would prove it after the cohort was already complete.

The proof is executed, not read: `install.py <loadsmith> --revert-thin`, then
that consumer's own CI green in the reverted state at a named commit, then a
**fresh exact-head resweep** against the reverted tree before re-converting.
The revert changes the tree, so the verdict that authorized the first
conversion does not authorize the second. Expected residue: the
`enabledPlugins` disable marker, and nothing else.

## D6. Rollback

Per phase, in the order a failure would be met:

- **Phase 0** — `git revert` the merge; no consumer state has changed yet.
- **Phase 1** — the machine install is idempotent and re-runnable at any
  version; a stale machine is a skew report, not a loss.
- **Phase 2** — a refresh PR is a normal consumer PR; revert it in that repo.
- **Phase 3** — same.
- **Phase 4** — before the consumer PR merges, `git -C <path> checkout -- .`.
  After it merges, `--revert-thin` is the mechanism, which is exactly what
  phase 5 proves rather than assumes.
- **Phase 5** — the revert proof is itself the rollback rehearsal; if it
  fails, the cohort stops and the remaining canaries stay fat.

A `blocked` verdict at any point stops that consumer **and the cohort**
(PRD requirement 2): the wave planner halts starts and holds merges on any
unsettled terminal canary
(`scripts/sd-ai-command-pack-fleet-wave-plan.py:200`), and
`.trellis/spec/backend/manifest-and-filesystem.md:1778` permits progression
only through successful canaries absent an explicit parked-canary override.

## D7. Open questions

- **O1.** Does phase 0's rewrite of `copilot-instructions.md`'s review-guidance
  block change what Copilot is told to skip in a *fat* consumer? The block is
  emitted to every consumer regardless of mode. Answered by phase 0's own
  before/after read of the emitted block in a fat consumer.
- **O2.** `rwbp-coordinator` cites `.sd-ai-command-pack/*` — a glob over the
  receipt directory, which conversion **keeps**. Whether the scanner counts it
  as a blocker because the glob also matches a removed path decides whether it
  needs an edit at all.
- **O3.** The machine payload at 0.71.12 must carry every script the rewritten
  consumer call sites resolve. Verified by the phase-1 install audit, not by
  assuming the manifest is complete.
- **O4.** `sd-status fleet --json` reports `pin: null` for all three canaries
  today, while the acceptance criterion requires `pin.state == "present"` and
  `pin.version == machineScope.packVersion`. Whether the pin is written by
  `--thin`, by the refresh, or by neither is unverified. Answered in phase 2 by
  re-reading a refreshed canary's row: if a refresh alone does not produce a
  pin, the criterion is about conversion and phase 4 must produce it.
  (The list key is `repositories`, not `consumers`.)

## D8. Review ledger

Host lane, round 1, against the artifact set written 2026-08-15. Baselines:
`prd.md` existed (`sha256:1330381a869dadea…`); `design.md` and `implement.md`
were new.

| ID | severity | concern | evidence | disposition |
|---|---|---|---|---|
| C-1 | low | D0/PRD called the 15 pack-owned defects an "identical set" across the canaries | `(file, line)` sets differ; `(file, detail)` sets match exactly across all three | **addressed** — D2 now states the identity is by text and the line numbers are template-relative |
| C-2 | blocking if true | the `copilot-instructions` citations might sit in the Trellis-owned block, making phase 0 an upstream change `AGENTS.md:25-28` forbids opening | `SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START` at template line 1, `:END` at 93; all 7 hits inside; the `TRELLIS:` block is separate and appended | **rebutted** — no plan change; evidence recorded in D2 |
| C-3 | blocking | `implement.md` 3.2 said "regenerate `docs/repomix-map.md`"; regeneration reproduces all 30 blockers, so loadsmith could never reach `clear` | map lines 1407-1410 are the embedded body of `docs/SD_AI_COMMAND_PACK.md`, which exists in a fat consumer | **addressed** — new D3a; implement 3.2 rewritten to exclude pack payload from the generator first |
| C-4 | medium | rewriting `hoa-manager`'s archived task PRD to satisfy the scanner would falsify a historical record | the blocker is prose in `.trellis/tasks/08-07-task-manifest-context-roots/prd.md` | **addressed** — new D3b: annotate, do not rewrite |
| C-5 | medium | the acceptance criterion reads `pin.state == "present"`, but all three canaries report `pin: null` today and nothing in the plan produces one | `sd-status fleet --json`, `repositories[]` | **parked** — design O4; trigger is the first phase-2 refresh, owner is this task |
| C-6 | medium | PRD requirement 3's machine-provisioning evidence is dated 2026-08-12 at 0.71.2; phase 1 re-provisions and would leave the gate citing stale evidence | requirement 3's recorded lines vs. `machineScope.packVersion 0.71.2` | **addressed** — implement 1.5 re-records the three lines |
| C-7 | — | cross-artifact value sweep | 49/50/34, 133, 15, 8/5/9, `0.71.6`/`0.71.11`/`0.71.12`, and the three HEADs agree across `prd.md`, `design.md`, `implement.md`; the PRD's 179 removals is explicitly flagged as recomputed rather than restated | **verified** |

No unresolved blocker. C-5 is parked and non-blocking: it is a question about
which phase produces an artifact the criterion already requires, not a doubt
about whether the criterion is right.

### Round 2

Round 1 verified the plan's numbers. Round 2 asked the question round 1 did
not: *is the gate this plan is built to satisfy measuring the right thing?*

| ID | severity | concern | evidence | disposition |
|---|---|---|---|---|
| C-8 | blocking | Phase 0 proposed rewording six templates so a pre-conversion scan passes. The conversion **already** repoints them, so the rewording would degrade correct fat-mode guidance for the whole fleet to satisfy a mistaken signal | `installer/thin.py:675` `repoint_kept_references` exists for this population and names this consequence; `THIN_PROFILE.literal_rewrites` carries purpose-built rules for the three Copilot globs; executed, `planned_repoints` takes loadsmith's six files from 17 citations to 1 | **addressed** — D2 rewritten; the first draft retained as D2-superseded |
| C-9 | blocking | The resweep scans pre-conversion bytes and blocks on them, while `--thin` requires `clear`. No fat consumer can reach `clear`, so **no consumer in the fleet can convert** | `decide()` at `thin-resweep.py:1773`; the verdict gate at `installer/thin.py:124`; no repoint simulation in the scan loop at `thin-resweep.py:1596-1634` | **addressed** — D2b makes the scan judge the bytes the conversion produces, for kept pack-owned files only |
| C-10 | medium | One citation survives the repoint and is a genuine defect: the skills glob rewrite produces `~/.agents/skills/sd-*/SKILL.md`, which still ends with the removed path | measured 17 → 1; `cites_removed_path` matches suffixes (`thin-resweep.py:1225`); `AGENTS_DOC_DIRECTORY` (`references.py:326`) documents this exact trap and solves it by naming the directory | **addressed** — D2c; phase 0B |
| C-11 | low | Phase 0's validation was deferred to a phase-2 refresh on the assumption the fix was in shipped text | the resweep runs from this checkout and reads consumer bytes, so a scanner fix is measurable against untouched canaries | **addressed** — D2d validates locally |

Round 2's own cross-artifact sweep: the figure 15 now appears with two
readings — 15 measured, 14 of them repointed — and both `prd.md` and
`implement.md` were updated to state the distinction rather than the bare
count. Phase 0's deliverable changed from six template edits to two code
changes in `implement.md`, `design.md`, and the PRD's added acceptance
criterion.

Two remediation rounds have run; the contract permits no third automatic round.
Nothing is unresolved.
