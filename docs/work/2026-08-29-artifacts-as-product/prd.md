---
title: sd-ai-command-pack v1.0 — artifacts as product
status: done
created: 2026-08-29
closed: 2026-09-02
---

# PRD — artifacts as product

## Problem

The maintainer spends too much time managing Trellis, three packs, and the workflow itself. Principles:
prd/design/implement discipline lives in GitHub; the framework helps enforce, never a burden of
conflicting approvals; KISS; honor preexisting repo/org setups; zero externally visible footprint
beyond doc artifacts; collaborators never need to adopt the framework; old ways are removed after
agreement (ratchet). The framework must serve research, prototyping, development, and personal
work; OSS participation respects target-project processes (fork-first); sub-agents and worktrees
are encouraged; sessions stick to their repos.

## Measured cost

| Cost | Number |
|---|---|
| Commits, 60 days | 2,968 (532 PRs, ~9 PRs/day) |
| Bookkeeping share of non-merge commits | 1,187 / 2,428 = **49%**; 389 are `chore: record journal` |
| PRs whose last commit is `feat` | **10 of 532 (2%)** |
| Open Trellis tasks in pack | 101; **98 about pack machinery**; 100 never left `planning` |
| Fleet-wide open tasks | ~306 Trellis tasks across 10 consumers at r1 (217 item dirs in the 7 platypeeps repos, re-counted 2026-08-29), 300 in `planning` |
| Most churned file | `review-preflight.mjs` (historical — since deleted, lives in git history): 125 commits, 79 fixes, 6,448 LOC at peak |
| Releases since 07-30 | 126 (4.2/day); all 10 consumers 4 versions behind |
| Copies of every shipped script | 4 |
| Tests vs code | tests 92k lines > scripts 54k + installer 11k |
| Per-session injection | ~16 KB per SessionStart; consumer settings.json hooks block ~67 lines (r1's "2,632" not reproducible — struck) |
| Consumer footprint | 45–80k LOC per repo, 40–60% of tracked files |
| Friction clusters from memory (13) | **11 pack/Trellis machinery, 1 mixed (Copilot rounds), 0 product** |
| system repo | 55 tools, 30 launchd jobs; dashboard.py 1,728 LOC (2,475 with the rest of the dir — r1's 3,177 was wrong), stdlib, tailnet-bound, iOS PWA in use |
| Skill-intake pipeline outcome | 10 proposals → 8 declined, 2 filed, **0 adopted** (6 stages, 4 repos) |
| Rollout ceremony | 8 releases × 10 consumers ≈ 80 two-line PRs in 4 days; skew structural |

**Root cause.** The pack gates the *process* (receipts, ledgers, digests, session numbers) instead
of the *artifacts*. Every process gate stores state that drifts from git/GitHub and then needs its
own repair machinery. Second cause: built for a fleet operator across 18 platforms; the audience is
one engineer plus agents.

## Requirements

1. The unit of work is a git-tracked artifact set (`prd.md`, optional `design.md` /
   `implement.md`) under `docs/work/<date>-<slug>/`; no runtime state is committed.
2. Merge authority is GitHub branch protection **where protection is enforcing**; local
   tooling mirrors it read-only and reports the gap where it is not, rather than asserting a
   guarantee the config does not provide.
3. The framework never edits a tracked repo file for its own purpose; the entire
   tracked footprint in a consuming repo is `<work>/**` (+ opt-in CI workflow files).
4. Collaborators never adopt the framework: CI checks report-and-pass for unlisted
   authors; `minimal`/`guest` modes cannot grow it.
5. One prefix (`sd-*`), one repo, machine-scope install, no release train.
6. Old mechanisms are removed as their replacements land (ratchet); no new
   gate/ledger/hook/rule without a linked incident and a deletion criterion.
7. Session handoff on the same machine works without git or GitHub.
8. Codex lanes run on the ChatGPT subscription only, never API billing.

## Acceptance criteria

- [x] M0 tombstone release 0.72.0 tagged; ~~`Pack version update check` on any consumer names it~~. *(Tag verified 2026-09-01. The consumer half is **retired 2026-09-02**: the check it names was deleted by this item's own step 3-c, so it has no subject left to pass. See the retirement note below.)*
- [x] Step 0: release/gate jobs deleted; every remaining CI job green.
- [x] Steps 1–3: one copy of every shipped file; `.trellis` gone from the pack; new installer + 12 skills land; scratch-repo `sd-plan` → `sd-ship` E2E merges a PR with only `<work>/**` tracked.
- [x] Step 3-c: one removal PR per consumer (9); zero trellis/router greps per repo; CI green.
- [x] Steps 4–7: routers retired, se-* folded as sd-*, machine cleanup leaves `handoff/`~~+`intents/`~~ intact, backlog parked, 1.0.0 tagged. *(Four clauses verified 2026-09-01 and re-verified 2026-09-02. The `intents/` half is **retired 2026-09-02**: the `item set-status` lane that would create it was deliberately not built, so the clause was vacuous rather than failing. See the retirement note below.)*
- [x] Steps 8–11: plugin interface, sd-writing-pack migrated, vault move last with golden-corpus byte-compare green. *(Ticked 2026-09-02 — three clauses pass, the fourth was retired on the record rather than rounded up; see below.)*
- [ ] 60-day criteria evaluated for ~~R10-D1 (backlog lane)~~ and R10-D3 (handoff hook). *(R10-D1's half is **retired 2026-09-02** — its clock is conditioned on a lane that was never built. R10-D3's stays open and is now answerable: earliest evaluation **2026-11-01**.)*
- [x] `chore: record journal` commits = 0; bookkeeping share of non-merge commits < 5%. *(Ticked 2026-09-02 — 123 non-merge commits since the last one, none of them bookkeeping; see below.)*

**2026-09-02 — three clauses are retired, in strikethrough, with the date.**
This needs saying carefully, because rewriting an acceptance criterion after the
fact is the exact move this document has spent two dated notes refusing. The
distinction is not subtle and it is the only thing that makes the edit
legitimate: **a check is never swapped for one that passes.** A clause is struck
only when *this item deliberately deleted the thing the clause was about*, and
the strikethrough leaves the original words on the page so the deletion is
readable rather than tidied away.

Three qualify, and each was verified from the filesystem rather than from prose:

- *`Pack version update check` on any consumer.* Step 3-c's nine removal PRs
  deleted it. `grep -rl 'Pack version update check'` over the repository returns
  `CHANGELOG.md` and this file — a historical entry and the clause itself, and
  no consumer anywhere.
- *Machine cleanup leaves `intents/` intact.* `intents/` has never existed. The
  `item set-status` lane that creates it was deliberately not built, which
  `bin/sd-dashboard`'s own module docstring states in its first paragraph:
  "Three verbs now, not the five the design lists." A clause about preserving
  something that was never created cannot fail and cannot pass.
- *R10-D1's 60-day criterion.* Conditioned on the backlog lane landing, and
  `skills/sd-ship/SKILL.md` says "`--backlog`/`--agent codex` is not
  implemented." The clock never started.

What is **not** retired: R10-D3's 60-day criterion, which has a mechanism, now
has a counter, and needs sixty days. It stays open with a date on it.

The rule this establishes, for whoever closes the next item: an acceptance
clause that survives its own subject is not evidence of anything, and leaving
it unticked forever is not honesty — it is a box nobody can ever act on. Strike
it, date it, say what deleted the subject, and leave the words visible.

**2026-09-01 — two of the unticked boxes above are half-true, and are left
unticked rather than rounded up.** Checked from the repository and the remote,
not from `implement.md`'s prose.

- *M0 tombstone 0.72.0.* The tag half holds: `git ls-remote --tags origin`
  returns `fea7e1331d1dad25ed4d1ab81abebf03f8f156ee	refs/tags/v0.72.0`. The
  consumer half has no subject any more — the `Pack version update check` that
  was to name the release went with the rest of the framework footprint in the
  nine step 3-c removal PRs, and the string now survives only in `CHANGELOG.md`
  and in this file. A clause whose subject was deleted is not a clause that
  passed, so the box stays open and this says why.
- *Steps 4–7.* Four of five clauses verify. The four router repositories all
  report `archived: true` (`sd-github-review`, `sd-review-test`,
  `sd-github-review-pilot`, `sd-review-control-plane`). `skills/` holds 76
  `sd-*` directories and zero `se-*`. `docs/work/archive/` carries **100** files
  with a `parked:` line, and `sd-status` reports `488 items (2 active)` against
  a ceiling of 20 — mezmo_benchmark's 48 are outside D2's scope under the R11-D7
  freeze, so they do not count against this. `git ls-remote --tags origin`
  returns `daebee6c6cd456a81cbbbba91de6196c8b8b7de0	refs/tags/v1.0.0`. The
  fifth is half-met: the state root `~/.local/state/sd-ai-command-pack/` is
  exactly `handoff/` and `installed.json`, so `handoff/` survived the cleanup —
  but `intents/` has never existed, because the `item set-status` lane that
  creates it was deliberately not built (`implement.md:563-567`, step P3's
  "Deliberately not built" list) — step 6 recorded the same thing at the time
  (`implement.md:1429`). "Leaves `intents/` intact" is vacuous rather than
  passed, and the box waits on the lane being built or the clause being
  rewritten.

**2026-09-02 — the steps 8–11 clause names a byte-compare that will not run.**
Step 11 was re-scoped to move nothing, so "vault move last with golden-corpus
byte-compare green" has no move to bracket and no green to report. The
baseline tool survives, re-pointed at step 10b as a before/after bracket
around the retarget, and is deleted when 10b lands. The box stays open on the
rest of the clause — the plugin interface is built, `sd-writing-pack` is not
yet migrated — and the byte-compare half is retired rather than passed.

**2026-09-02 — the item closes, and here is what each remaining box is
resting on.** Every step in `implement.md`'s checklist is ticked, all execution
PRs are merged, and `task/08-29-artifacts-as-product-m0` no longer exists on the
remote (`git ls-remote --heads origin task/08-29-artifacts-as-product-m0`
returns nothing), so `status: in_progress` — which this directory's README says
*requires* a `branch:` — had become unsupportable on its own terms. The
frontmatter drops `branch:` with the status change rather than pointing at a
deleted ref.

Two boxes are ticked here and three are left open **as of this close**. The
2026-09-01 rule holds: a clause whose subject was deleted is not a clause that
passed, and an item closes with its open boxes visible rather than tidied.
*(The retirement pass above ran later the same day and struck the subjects of
two of those three. From 2026-09-02 onward the count a reader will find in this
file is one open box, R10-D3's.)*

*Steps 8–11 — ticked.* This box was open on one thing: "`sd-writing-pack` is not
yet migrated." It is. `sd plugin list` reports the `sdw` plugin registered with
four kinds and `store: vault at $OBSIDIAN_VAULT`; the sibling repository's
`sd-writing-pack/scripts/pack.py` -- outside this checkout, which is why the
path is written in full -- has five surviving verb groups (`tips pieces gh
review meter`) holding **zero** vault-path constants, measured there with
`grep -cw -e BI_DB -e SP_DB -e TT_DB -e TP_DB -e VAULT scripts/pack.py`.
The byte-compare half stays retired, as the 2026-09-02 note above said it would
be — but it is retired having *run*: the bracket was re-pointed at the step 10b
retarget and read `784 notes byte-identical to the baseline` across the first
change with two writers on those notes. The clause asked for evidence that the
migration did not corrupt a note. That evidence exists; it brackets a different
change than the clause named, and this sentence is the substitution written down
rather than assumed.

*Journal and bookkeeping — ticked.* The last `chore: record journal` commit on
`main` is `21eed68c`, 2026-08-29T01:38:37-06:00. **123** non-merge commits have
landed since it, and `git log --no-merges --grep='^chore: record journal'
21eed68c..HEAD` returns **0**. No subject matching `journal|ledger|bookkeep`
appears among them either, so the bookkeeping share over the window is 0%
against a `< 5%` bar. Counting all of history instead gives 391 and 15.07%,
which measures the practice this item deleted rather than whether it stayed
deleted — the wrong window, recorded here so nobody re-derives it and reaches
the opposite conclusion.

*M0 tombstone — still open, unchanged.* The 2026-09-01 finding stands: the tag
exists, the consumer that was to name it does not.

*Steps 4–7 — still open, unchanged.* Four of five clauses verify today
(`~/.local/state/sd-ai-command-pack/` is exactly `handoff/` and
`installed.json`; `skills/` holds 76 `sd-*` and zero `se-*`; both tags resolve
on the remote). "Leaves `intents/` intact" is still vacuous, because the lane
that creates `intents/` was deliberately not built.

*60-day criteria — still open, and not for the reason the box implies.* Sixty
days from 2026-08-29 is 2026-10-28, so the obvious answer is "not due." That is
not the honest answer. **Neither criterion is evaluable, for two different
reasons, and waiting until October would not change either.**

- **R10-D1 (backlog lane).** The criterion is "if 60 days after *it lands*
  fewer than 5 items have reached a merged PR through `--agent codex`, delete
  the flag." It has not landed. There is no `bin/sd-ship`, and
  `skills/sd-ship/SKILL.md` says so in its own words: "`--backlog`/`--agent
  codex` is not implemented; do not simulate it with ad-hoc worktree
  scripting." The clock never started. This is the M0 shape again — a criterion
  whose subject does not exist.
- **R10-D3 (handoff hook).** This one *did* land: `sd-handoff-restore` is wired
  into `~/.claude/settings.json` on the `startup` and `clear` matchers, which is
  what the two-lane design asks for. But the criterion is "if after 60 days
  fewer than 5 packets have been auto-loaded, or the median packet age at load
  exceeds 7 days," and **nothing recorded a load**.

  *Corrected 2026-09-02, having read the code instead of the summary.* The
  mechanism is not what the first draft of this bullet said. `claim()` renames
  the packet away to take exclusive ownership and then **writes it back** with
  `consumed` stamped beside the `created` it already carried; the unlink is of
  the temporary claim name, not of the packet. So a restored packet does keep
  both of the criterion's numbers. What it does not keep is *history*: there is
  one packet per directory, and the next `sd-handoff` overwrites it. The highest
  count the packets can ever report is the number of directories, and a busy
  directory is indistinguishable from an idle one. The criterion was
  unevaluable, but for a subtler reason than "nothing is written down."

  That is precisely the failure standing rule 1 exists to prevent, and this
  item has already named it once, at `implement.md:2069-2076`, about R11-D10:
  "a deletion criterion nobody can evaluate is the failure mode standing rule 1
  is for." It happened twice. The rule catches a mechanism arriving without a
  criterion; it does not catch a criterion arriving without a counter.

  **Closed 2026-09-02 at Sven's direction.** `sd-handoff-restore` now appends
  one line per restore to `handoff/loads.jsonl` — `consumed`, `created`,
  `age_seconds`, and a 16-character digest of the directory rather than its
  path — so the count survives the packet being overwritten. The criterion
  becomes two commands over that file. The count is `wc -l < loads.jsonl`.
  The median is one `jq` — sorting alone is not a median, so it takes the
  middle value, or the mean of the two middles on an even count:

  ```sh
  jq -s 'map(select(.age_seconds != null) | .age_seconds) | sort
         | if length == 0 then null
           elif length % 2 == 1 then .[(length / 2) | floor]
           else (.[length / 2 - 1] + .[length / 2]) / 2 end' loads.jsonl
  ```

  The `select` is load-bearing. `age_seconds` is null when a packet's
  `created` cannot be parsed, and jq sorts null below every number — which
  drags the middle value down, and a low median is the reading that says the
  hook is serving live restarts. A median that swallows nulls therefore keeps
  a hook the criterion would have deleted. Two null lines beside one 10-day
  load: unfiltered, the middle value is `null`; filtered, it is 900000
  against a 604800 threshold.
  Answerable on 2026-11-01 -- sixty days from the counter, not from the item,
  which is a different date from the 2026-10-28 above and the reason both are
  written out. Only
  the hook writes it: `sd-handoff --show` claims a packet too, but the criterion
  counts packets *auto-loaded* and `--show` is the manual path it is measured
  against. The write is guarded, and a fixture proves the guard earns its place
  — with it removed, an unwritable log takes the whole restore down and the
  session starts with no context at all.

  **The box stays open, because the clock starts now.** Sixty days of data did
  not exist before today and one line of code does not create them; the earliest
  honest evaluation is 2026-11-01. Ticking this on the strength of the counter
  existing would be the rounding-up this document has refused twice.

## References

- Full decision record: `design.md` (rounds r1–r9c + R10/R11, adversarially reviewed).
- Execution sequence: `implement.md`.

## Log

- 2026-08-29 created; M0 tombstone PR opened from this branch.
- 2026-09-02 closed: every step ticked and merged; two acceptance boxes ticked with
  evidence, three left open with the reason each cannot be ticked.
- 2026-09-02, later the same day: three clauses retired in strikethrough, each
  because this item deleted the thing it was about. The open-box count goes from
  three to one. What remains is R10-D3's 60-day criterion, answerable 2026-11-01.
