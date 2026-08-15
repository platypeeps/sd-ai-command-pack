# Design — one pack-owned, layout-aware review guard

## D0 — What the five guards actually are

Read in full on 2026-08-14 from the checkouts named by
`docs/fleet/consumers.json` `pathHint`. Function inventories were taken from
the files, not from the PRD's description of them.

| consumer | guard | lines |
|---|---|---|
| `rwbp-coordinator` | `scripts/check-review-churn.mjs` | 762 |
| `loadsmith` | `scripts/check_review_readiness.sh` | 1139 |
| `hoa-manager` | `scripts/check-review-preflight.mjs` | 902 |
| `rwbp-website` | `scripts/review-guard.mjs` | 2466 |
| `mezmo_benchmark` | `scripts/check-review-cycle-patterns.py` | 812 |

The PRD's original consumer/filename pairing was wrong in four of five rows and
is corrected there. Two files that match the naming —
`loadsmith/scripts/check-review-preflight.mjs` (25 lines) and
`anomaly-metric-creator/scripts/check-review-preflight.mjs` (31) — are
dispatchers that `spawnSync` other checks. They contain no layout logic and are
not counted.

They are **not five copies of one script**. They are five different programs
that each contain the same small layout-dependent core, buried in a much larger
body of consumer-specific assertions. `rwbp-website`'s guard alone carries 20+
checks about `sharp` pinning, container scanning, action pins, CI concurrency,
`noopener` links, and `.env` examples — none of which has anything to do with
the pack.

That ratio is the design constraint. Shipping "what the five guards do" would
ship a Next.js lockfile check to a Python consumer.

## D1 — The behavior table (PRD requirement 2)

Every distinct behavior, with its disposition and the reason. **Ship** means
the pack owns it; **drop** means the pack already owns it and the consumer copy
is redundant; **consumer-local** means it stays where it is.

### Ship — layout-dependent, duplicated, and broken by thin mode

| behavior | where it appears now | why ship |
|---|---|---|
| Classify a changed path as vendored pack payload vs authored source | all 5 (`is_trellis_copied_path` + `is_sd_command_pack_path` loadsmith:201,233; `COPIED_TRELLIS_PATTERNS` hoa:13; `classifyPaths` coordinator:110; `_load_sd_ai_command_pack_targets` mezmo:186; `summarizeCopiedTemplateDiff` website:1792) | the single shared core. Four of five hardcode a glob list; only mezmo reads the receipt |
| Enumerate the installed SD command surface across platforms | hoa:51,57 (`FLAT_SD_COMMAND_PATHS`, `COLON_SD_COMMAND_PATHS`); website:368 (`checkReviewPackConsistency`, a per-command list of four platform paths) | the most layout-hardcoded behavior in the set, and the one thin mode breaks hardest: in thin mode these paths are not in the consumer at all |
| Assert the consumer's CI classifier keeps pack payload in the light lane | coordinator:332-353 (22 `expectIncludes` on `classify-ci-changes.sh`); loadsmith:325; website:641 | 22 hand-maintained globs asserting the pack's own layout. Must be generated from the pack's path inventory, never typed twice |
| Trellis markdown list-continuation indentation | mezmo:379; website:1399 (`findListContinuationIndentIssues`) | duplicated verbatim in two consumers, about Trellis-owned files |

### Drop — the pack already ships it and the consumer copy is redundant

| behavior | consumer copy | what already ships |
|---|---|---|
| PR-body generated-scope marker | hoa:78 `SCOPE_BODY_PATTERN`, hoa:204 `checkGeneratedScopeBody` | `scripts/sd-ai-command-pack-pr-body-scope.py` and `github_pr_body_mentions_scope` (`review-scope.sh:167`) — same three accepted headings, written in `grep -E` and JavaScript dialects, so equivalent in effect and not byte-identical |
| Trellis journal placeholder records | loadsmith:706-925 (219 lines), mezmo:345, website:579 | the bookkeeping validator: `checked 377 completed Trellis journal session(s) for placeholders and validation consistency` |
| Personal absolute machine paths in docs | hoa:69 `MACHINE_PATH_PATTERN` | `checked 1662 documentation/prompt/spec file(s) for personal absolute paths` |
| Documentation path references resolve | website:262 `checkDocumentationPathReferences` | `documentation path references resolve to existing repo files` |

Dropping these is worth more than shipping some of the ship rows: it is four
behaviors deleted from three consumers with zero new pack code.

### Consumer-local — never ship

`rwbp-coordinator`'s ~60 `expectIncludes` assertions on `CLAUDE.md`,
`README.md`, `AGENTS.md`, `docs/DEVELOPMENT_CYCLE.md`, and
`docs/REVIEW_PATTERNS.md`; `hoa-manager`'s load-testing env docs, stack-version
docs, AI-route rethrows, knowledge-FTS helpers, migration guardrails, payload
access; `rwbp-website`'s `sharp` hardening, container scan gate, immutable
action pins, CI gate coverage, concurrency policy, socket failure policy,
branch-protection contexts, Prism rules, `noopener`, `.env` examples,
`next dev` types, fsevents lockfile portability; `mezmo_benchmark`'s Python
constant-literal scan and PR-template contract; every consumer's Repomix
*freshness* command.

These are assertions about the consumer's own product, and the fact that they
were filed as "pack-layout blockers" is a measurement artifact: they live in the
same file as the layout core, so a file-level blocker count attributes them to
the pack.

## D2 — Do not ship a new guard; make the existing classifier reachable

The PRD says "ship one pack-owned review guard". Taken literally that means a
new script. It should not be, and the evidence is in the consumers:

- `is_copied_review_scope_path` (`templates/scripts/sd-ai-command-pack-review-scope.sh:130`)
  already answers the D1 core question, and already resolves at runtime — it
  matches against `.sd-ai-command-pack/installed-targets.txt`, overridable with
  `SD_AI_COMMAND_PACK_TARGETS_FILE` (`:7`), rather than hardcoding globs.
- `hoa-manager/scripts/check-review-preflight.mjs:70` says in a comment that its
  matcher "Mirrors the pack's own matcher at
  scripts/sd-ai-command-pack-review-scope.sh:170". It knew, and copied anyway.
- `rwbp-website/scripts/review-guard.mjs:6` already
  `import { runReviewPreflight } from './sd-ai-command-pack-review-preflight.mjs'`.

So the consumers did not reimplement because the pack lacked the logic. They
reimplemented because the logic is reachable only by running a shell script for
its exit code, and a Node or Python guard that needs *the classification of a
list of paths* cannot get it that way without shelling out per path.

**Decision: expose the existing classifier as a data interface, in the three
languages the fleet actually writes guards in, and delete the duplicated
behaviors rather than growing a sixth program.**

Rejected alternatives:

- **A new unified guard script that supersedes all five.** It would have to
  carry the consumer-local column to be adoptable, which is exactly the
  Next.js-check-in-a-Python-repo failure. A consumer would keep its guard *and*
  gain the pack's.
- **Ship only the shell function.** It is what already exists and it is what
  five consumers already declined to use. Repeating it and expecting a
  different result is not a plan.

## D3 — The interface

Two queries — classify a path set (D3), resolve a script name (D3b) — over one
implementation, with three bindings.

```
sd-ai-command-pack-review-layout.py --json [--path P ...]
```

```json
{
  "schemaVersion": 1,
  "mode": "fat|thin",
  "receipt": ".sd-ai-command-pack/installed-targets.txt",
  "paths": [
    {"path": "scripts/sd-ai-command-pack-review.py", "category": "pack-payload"},
    {"path": "src/app.ts", "category": "authored"}
  ],
  "surface": {
    "commands": [
      {"name": "review-pr",
       "paths": [".agents/skills/sd-review-pr/SKILL.md",
                 ".claude/commands/sd/review-pr.md"]}
    ]
  }
}
```

`--path` may be repeated or omitted; omitted yields an empty `paths` array, and
the caller supplies its own changed set.

An earlier draft of this paragraph said omitting `--path` classifies the current
changed set. It does not, and shipping that contract would have been worse than
the wrong doc: every one of the five guards already computes its changed set —
from `git diff`, from a CI event payload, or from `argv` — and each computes it
differently. A resolver that ran its own `git diff` would either silently
disagree with the caller's set or force every caller onto its definition. The
one question worth centralizing is the classification, not the enumeration.

### D3b — The second query: resolve a pack script's invocation path

Classification alone does not help the consumer with the most blockers. The
resweep of `anomaly-metric-creator`, run 2026-08-14, measured **175** blockers
(not the PRD's 207 — the 0.70.0 correction, as its Evidence section predicted),
`verdict: blocked`, worktree clean. **112 of the 175** are references to a
hardcoded `scripts/sd-ai-command-pack-*` literal, and **14 distinct pack paths
account for all 112**:

An earlier draft of this paragraph said every one of the 175 was such a
reference, spread over 18 paths. The full per-consumer measurement (D6) refuted
both figures: 8 more blockers name a command or skill file rather than a script,
and the remaining 55 are glob patterns that no runtime resolver rewrites. The
table below is unchanged — its counts were always script references — but it
sizes 112, not 175.

| refs | path |
|---|---|
| 27 | `scripts/sd-ai-command-pack-pr-body-scope.py` |
| 26 | `scripts/sd-ai-command-pack-full-check.sh` |
| 11 | `scripts/sd-ai-command-pack-install-audit.py` |
| 10 | `scripts/sd-ai-command-pack-housekeeping.sh` |
| 10 | `scripts/sd-ai-command-pack-review-scope.sh` |

Concentrated in `tools/check_copilot_instruction_contract.py` (30) and its test
(33), `tools/check_ci_review_contract.py` (15) and its test (17),
`tests/test_ci_change_classifier.py` (23), and
`.github/instructions/anomaly-metric-creator.instructions.md` (14).

They break because every `scripts/sd-ai-command-pack-*` is partition category
`machine-claude`, so thin conversion moves it out of the consumer. A thin
consumer retains six files total — `.claude/rules/`,
`.claude/sd-ai-command-pack/`, `.gito/`, `.prism/` — and no script among them.

So the interface gains a second query:

```
sd-ai-command-pack-review-layout.py --resolve sd-ai-command-pack-full-check.sh
```

```json
{"schemaVersion": 1, "mode": "thin", "name": "sd-ai-command-pack-full-check.sh",
 "path": "<home>/.agents/bin/sd-ai-command-pack-full-check.sh"}
```

This is requirement 1's "resolves pack-owned paths through the same resolution
the rest of the installed pack uses" read literally, so it needs no PRD change.

Resolution is derived, not guessed. Measured 2026-08-14: the machine receipt's
`files` array holds 115 entries shaped
`{"family": "agents-bin", "path": "sd-ai-command-pack-audit-inventory.py",
"digest": ..., "executable": true}`, and `family_roots(home=, environ=)`
(`installer/machinepayload.py:103`) maps a family name to its absolute root. So
`--resolve` is: find the receipt entry whose `path` matches, map its `family`,
join. In fat mode it is `scripts/<name>` after confirming membership in
`installed-targets.txt`. A name in neither receipt is an error with the name
echoed, never a guessed path.

`family_roots` is in `installer/`, which does not ship (D3a), so the family
root table is redefined in the shipped script under D3a's redefine-and-test
rule.

### D3c — The bootstrap literal, stated plainly

The resolver is itself `machine-claude` payload, so a thin consumer cannot
reach it at a fixed consumer-relative path either. It must probe two candidate
locations in order — `scripts/<resolver>`, then
`<agents-bin root>/<resolver>` — and the second is derived from the same
`resolve_state_root` ladder the resolver itself uses, so the bootstrap carries
the ladder rather than a literal home path.

That is one *bootstrap site* per consumer, not one literal: the probe is a
fixed two-branch snippet. Calling it "one path" would understate it.

This is not zero and the design does not claim it is. It takes
`anomaly-metric-creator` from **18 hardcoded pack paths to 1**, and the same
ratio holds for every other consumer. Driving it to zero needs a new
`consumer-config`-category entrypoint that survives conversion — a partition
change that alters what the conversion cohorts retain, which is out of scope
here and is recorded as a follow-up rather than smuggled in.

The Node and shell bindings are thin: `review-scope.sh` keeps its existing
functions and gains a `--json` path-classification mode; the `.mjs` binding is
an `export` in the already-shipped `sd-ai-command-pack-review-preflight.mjs`, so
`rwbp-website` gains it through the import it already has. Python is the
implementation because the receipt and manifest readers are already Python.
(This sentence originally also cited the partition reader; D3a removes the
partition as a source, so it is no longer a reason.)

`surface.commands` is enumerated **from the receipt** at runtime, never from a
literal list. That is the thing that makes hoa's `FLAT_SD_COMMAND_PATHS` and
website's `checkReviewPackConsistency` deletable rather than portable.

### D3a — The guard may only use what is installed in a consumer, which is less than it looks

Measured against this repository's own receipt, 199 entries:

```
$ grep -c "^installer/" .sd-ai-command-pack/installed-targets.txt
0
$ grep -n "partition" .sd-ai-command-pack/installed-targets.txt
(no match)
$ grep -n "sd_ai_command_pack_lib" .sd-ai-command-pack/installed-targets.txt
199:scripts/sd_ai_command_pack_lib.py
$ grep -cE "commands/|skills/" .sd-ai-command-pack/installed-targets.txt
140
```

The first draft of this design sourced `surface.commands` from
`docs/fleet/surface-partition.json` and named `installer.registry` and
`installer.machinescope` constants to reuse. **None of those exists in a
consumer.** `installer/` is repo-owned build machinery and ships zero files;
`surface-partition.json` is repo-owned fleet data. A guard written against
them works perfectly in this checkout and `ImportError`s in every consumer it
was written for — the same shape of defect as designing against a GitHub
Release this project never publishes.

What is reachable:

- `scripts/sd_ai_command_pack_lib.py` — shipped, so `resolve_state_root` is a
  legitimate reuse and D4a stands.
- `.sd-ai-command-pack/installed-targets.txt`, `manifest.json`,
  `provenance.json` — the three metadata files.
- The 140 receipt lines under `commands/` or `skills/`.

So the receipt is not merely *a* source for `surface.commands`; it is the only
one, and it is the better one regardless. The partition says what the pack
*intends* to install; the receipt says what *is* installed. A guard answering
"which SD command paths exist in this consumer" wants the second.

Any constant needed from `installer/` is redefined in the shipped script with a
comment naming the repo-side original, and a pack test asserts the two agree —
duplication that is checked, rather than an import that cannot resolve.

## D4 — Thin mode is where `mode` comes from, and it must not be a consumer conditional

Requirement 1 says the guard must work in both modes with no consumer-side
conditional. The `mode` field is therefore **output, not input** — the guard
reports what it resolved, and the consumer's guard code branches on nothing.

### D4a — The thin receipt is not under `~/.agents`, and the PRD says it is

Measured 2026-08-14, because getting this wrong is the whole failure mode:

```
$ python -c "import sd_ai_command_pack_lib as L; print(L.resolve_state_root())"
<home>/.local/state/sd-ai-command-pack
```

Two different user-level roots exist and the PRD's requirement 1 conflates
them:

- **Payload** — the installed skills and commands — goes to `~/.agents`,
  `~/.gemini/commands`, and the XDG command directories
  (`installer/machinescope.py:4`). This is what an operator sees, and it is
  what requirement 1 names.
- **State** — including the machine receipt, `machine/machine-receipt.json`
  (`machinescope.py:66-67`) — goes to `resolve_state_root()`
  (`sd_ai_command_pack_lib.py:248-292`), a five-rung ladder: explicit argument,
  `SD_AI_COMMAND_PACK_STATE_HOME`, `XDG_STATE_HOME/sd-ai-command-pack`, the
  Windows `LOCALAPPDATA` location, then `~/.local/state/sd-ai-command-pack`.

The guard resolves from the **state** root, not `~/.agents`. A guard that
looked in `~/.agents` would find payload it cannot enumerate authoritatively
and would miss the receipt entirely; and on a consumer that sets
`XDG_STATE_HOME` it would be wrong even about the fat case. `~/.agents` is
never hardcoded and never read.

Resolution order, first hit wins:

1. `SD_AI_COMMAND_PACK_TARGETS_FILE` if set — the existing override
   (`review-scope.sh:7`), preserved so nothing that sets it today changes
   behavior.
2. `.sd-ai-command-pack/installed-targets.txt` in the consumer — `fat`.
3. `resolve_state_root() / "machine" / "machine-receipt.json"` — `thin`. Call
   `resolve_state_root`; do not reimplement the ladder, and in particular do
   not expand `~` directly, which skips four of its five rungs.
4. None of the above: `mode: "unresolved"`, no `paths` array, exit non-zero
   with a named reason.

Step 4 fails **loud, not open**. The tempting fallback is to classify
everything as `authored`, on the reasoning that over-reporting is the safe
direction for a review guard. It is the safe direction, and it is still wrong
here: a guard that cannot find the pack is broken, and silently grading every
PR as all-authored looks identical to a healthy run on a consumer with no pack
changes. Emitting no classification at all is what makes the breakage visible.

## D5 — Consumer adoption is install-plus-delete (requirement 3)

The new script ships as pack payload through the existing install path, so a
consumer gets it from `sd-refresh` with no new integration. Adoption per
consumer is then: replace the guard's own classification block with a call, and
delete the drop-column checks outright.

No consumer repository is touched by this task (PRD Out of scope). The
deletions are the conversion cohorts' work; this task's deliverable is that
they are deletions.

## D6 — Measurement (requirement 5)

The projected blocker reduction must be re-measured, not carried forward:

- the 510/330 figures predate 0.70.0's resweep correction, which the PRD's own
  Evidence section already flags as lowering five consumers' counts;
- they inherit the corrected mis-attribution — in particular
  `anomaly-metric-creator`, whose share was re-measured at **175**, not 207
  (D3b). It owns no bespoke layout guard, so none of it is reducible by the
  ship column. The projection must therefore be split by which query does the
  work, or a reduction cannot be attributed to a change.

Any per-consumer projection is stated as measured-after, or not stated.

### Measured 2026-08-14

All eight consumers resweept from a clean worktree
(`sd-ai-command-pack-thin-resweep.py <consumer> --json`), each blocker attributed
to the single query that reaches it:

| consumer | blockers | `--resolve` | `surface` | `--path` | unreached |
|---|---:|---:|---:|---:|---:|
| `anomaly-metric-creator` | 175 | 112 | 8 | 0 | 55 |
| `rwbp-website` | 66 | 36 | 12 | 9 | 9 |
| `loadsmith` | 50 | 40 | 2 | 3 | 5 |
| `rwbp-coordinator` | 49 | 29 | 6 | 9 | 5 |
| `mezmo_benchmark` | 44 | 21 | 1 | 4 | 18 |
| `hoa-manager` | 34 | 22 | 5 | 6 | 1 |
| `se-ai-command-pack` | 24 | 16 | 1 | 0 | 7 |
| `sd-github-review` | 14 | 12 | 1 | 0 | 1 |
| **total** | **456** | **288** | **36** | **31** | **101** |

Buckets are disjoint and tested in that order, so a hardcoded script path inside
a bespoke guard is counted once, under `--resolve`. `surface` is the
`surface.commands` enumeration in the classification document — a reference to a
concrete installed command or skill file, which that array resolves; a *glob*
over the same directory is not counted there, because enumeration cannot rewrite
a pattern.

Three findings, all of which lower or complicate this design's own framing:

1. **The fleet total is 456, not 510.** The PRD's figure was flagged as an
   upper bound pending 0.70.0's resweep correction; measured, the correction is
   worth 54 blockers.
2. **This design's claim that `--resolve` puts *all 175* of
   `anomaly-metric-creator` in reach is wrong.** Measured: 112 by `--resolve`,
   8 by `surface`, and **55 unreached**. The 55 are not script references at
   all — they are glob patterns in one instructions file
   (`.gemini/commands/sd/**`, `.agents/skills/sd-*/**`) plus a CI-change
   classifier's fixture list. No runtime resolver rewrites a glob, so no
   version of this task reaches them.
3. **Reached: 355 of 456, or 78%.** Larger in share than the PRD's "65% of
   510" framing, smaller in absolute terms (355 against 330 of a total that no
   longer exists). The two numbers are not comparable and the PRD's should not
   be restated as if this confirmed it.

The 101 unreached blockers are outside this task and outside the follow-up shim
that removes the bootstrap site. They are consumer prose and fixtures that
enumerate the pack's surface by pattern; whoever converts each consumer either
rewrites those lines or accepts them, and this design does not claim otherwise.

## Risk

The honest one: the ship column is four behaviors and the drop column is four,
but the five guards total ~6100 lines and a reader of the PRD's "covers the
behavior the five bespoke scripts actually implement" could expect all of it.
D1's consumer-local column is the explicit answer to that, and it is the part
of this design most likely to be wrong — if a behavior filed there is in fact
duplicated across consumers, it belongs in ship. The table is per-behavior with
file:line so that claim is checkable rather than asserted.

Second risk: `surface.commands` is enumerated from the receipt (D3a), so it is
only as good as the receipt. If the receipt and the files actually on disk
disagree — a consumer deleted an installed command, or a partial install never
finished — this guard reports what the receipt claims and the real drift goes
unseen. That is the correct division: the existing `install-audit` is the check
that compares the receipt against the filesystem, and this guard does not
duplicate it. The earlier draft of this paragraph named the partition as the
source, which D3a had already replaced because
`docs/fleet/surface-partition.json` does not ship to consumers.

## Rollout and rollback

New payload script at the four byte-identical paths, so: edit
`templates/scripts/`, `make sync`, `make generate`, refresh
`docs/fleet/candidate-validation.json`, bump `manifest.json` with a matching
`CHANGELOG.md` heading, and give the PR a `## Tooling/generated scope:`
section. Same cascade as `08-10-fleet-status-release-target`.

Rollback is reverting the commit. The guard is read-only and no consumer has
adopted it yet at merge time, so nothing depends on it.
