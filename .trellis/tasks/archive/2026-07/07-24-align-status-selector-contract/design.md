# Design — align status and housekeeping selector contracts

## Scope boundary

Two authored prose lines and their two dogfood mirrors, plus one drift test.
No code change to `scripts/sd-ai-command-pack-status.py`, no schema change, no
new category, no compatibility reader.

The narrowness is a measurement, not an ambition. See measurement 3.

## Confirmed measurements

### 1. All three PRD evidence citations are off, one badly

| PRD says | actually |
|---|---|
| `sd-status/SKILL.md:68-81` defines `F-*` and `T-*` | the definition is **`:74-89`** — `:68-73` is the recovery-artifacts reference and the roadmap-source sentence |
| `sd-status/SKILL.md:134-138` still accepts `F/T/R` | the token is on **`:140`** |
| `sd-housekeeping/SKILL.md:75-77` describes the delegated result as containing `F/T/R` selectors | `:75-77` is the `sd-ai-command-pack-pr-eligibility.py` receipt contract (`status`, `reasonCodes`, `checks`, `reviewThreads`, `finishWork`) and `gh pr merge --match-head-commit`. The F/T/R mention is on **`:118`**, ~43 lines away, in the `status` bullet of the delegated-result list |

The third citation does not merely drift — it points at unrelated content.
Anyone implementing from it edits the PR-eligibility contract.

### 2. There is no `R-*` in code. The Roadmap collection was already deleted

`select_items(items, prefix=...)` (`scripts/sd-ai-command-pack-status.py:478-481`)
is the sole producer of `selectionId`, and it is called from exactly three sites,
emitting exactly two prefixes:

```
scripts/sd-ai-command-pack-status.py:559    prefix="T"    tasks
scripts/sd-ai-command-pack-status.py:1715   prefix="F"    follow-ups
scripts/sd-ai-command-pack-status.py:2290   prefix="F"    fleet_follow_ups
```

A grep for `"R-` / `R-1` across `scripts/`, `installer/`, `tests/`, and
`.github/scripts/` returns **nothing**. `07-23-status-untracked-roadmap-items`
finished the code half; what survived is wording.

So AC1 ("no Roadmap collection or `R-*` selector exists") is **already true of
the emitted output** and is verified, not achieved, by this task.

### 3. The live surface is four lines, not the enumeration R1 describes

R1 says "every live skill, command, prompt, guide, generated adapter, test
expectation, and active program task". Repo-wide sweep for `F/T/R`, `` `R-*` ``,
and `R-1` across `*.md`/`*.py`/`*.sh`/`*.mjs`/`*.toml`/`*.json`:

```
templates/.agents/skills/sd-status/SKILL.md:140
templates/.agents/skills/sd-housekeeping/SKILL.md:118
.agents/skills/sd-status/SKILL.md:140            (mirror, diff -q identical)
.agents/skills/sd-housekeeping/SKILL.md:118      (mirror, diff -q identical)
```

No command, no prompt, no guide, no generated adapter, no doc, no test
expectation. Every remaining hit is under `.trellis/`:

- **archived task history** — `archive/2026-07/07-23-expand-sd-status-selectable-inventory/`
  (`prd.md`, `design.md`, `implement.md`) and
  `archive/2026-07/07-23-status-untracked-roadmap-items/prd.md`;
- **the journal** — `.trellis/workspace/sdelmas/journal-5.md:169`;
- **three active task PRDs that describe the removal** — this task's own PRD
  (7 hits), the parent `07-24-correct-sd-skill-contract-drift` (5 hits), and
  the finding row `07-22-streamline-sd-skill-workflows/prd.md:70`.

R1's qualifier "that describes current behavior" is what saves the third group:
those are tracking records for the removal. Editing them destroys the finding's
own description.

### 4. The exact edits

`sd-status/SKILL.md:140` — the paragraph is correct apart from one token:

> If the user later supplies an `F/T/R` identifier, treat it as a report-local
> selector for this snapshot and resolve it back to the durable row contents. A
> selection is a new request; it does not retroactively authorize `sd-status` to
> mutate the repository or bypass the selected workflow's task, approval, and
> safety gates.

`F/T/R` → `F/T`. The safety sentence stays untouched.

`sd-housekeeping/SKILL.md:118` — `F/T/R selectors,` → `F/T selectors,`.

### 5. R3 and R5 collide, and the resolution is to reject generically

R3 wants an incoming `R-*` treated as unsupported input. R5 wants a test that
fails when live surfaces mention the retired contract. Writing "`R-*` is no
longer supported" satisfies R3 and **fails R5's own test** — the retired
selector is back on a live surface.

Resolution: the skill never names `R`. It enumerates `F-*` and `T-*` as the
only selectors and rejects everything else by exclusion. One sentence after
`:144`:

> A selector that is not an `F-*` or `T-*` row of this snapshot is unsupported
> input: report it as unresolved against the current report and take no action.

This is strictly better than naming `R`, because it also covers the common real
case — `F-9` against a three-row report — which is the "stale-snapshot" half of
AC4 that no current wording handles.

### 6. R5's test must be an allowlist, not an exclusion list

The obvious shape — grep the repo, exclude `.trellis/tasks/archive/` and the
journal — breaks the moment a new active task PRD describes the removal. Three
active PRDs already would trip it today.

Invert it: scan the **shipped surface** and nothing else — `templates/`, the
root mirrors, `docs/`, generated adapters — and never `.trellis/`. A denylist
must be extended every time someone writes about the history; an allowlist is
correct by construction, and the thing R5 actually cares about ("current
surfaces") is exactly the shipped set.

## The central tension

The task is scoped as a sweep and is actually a two-token edit. The risk is not
missing a surface — measurement 3 enumerates the whole surface — it is
**building the machinery the requirements imply**: a compatibility path for R3,
and a denylist drift test for R5 that has to be maintained against the project's
own tracking documents. Both would be larger and more fragile than the fix.

## Contract

**Selectors.** `F-*` = evidence-backed follow-ups, including untracked task-like
roadmap-file items with path/line evidence. `T-*` = every valid unarchived
Trellis task. No third category. Definitions at `sd-status/SKILL.md:74-89` are
already correct and are not edited.

**Selection input.** `F-*` and `T-*` resolve against the snapshot that produced
them. Anything else — wrong prefix, out-of-range ordinal, or a row that no
longer exists — is unresolved input, reported precisely, with no mutation. The
existing sentence that a selection "does not retroactively authorize `sd-status`
to mutate the repository" is unchanged and still governs the resolving case.

**Handoff (R4).** `sd-housekeeping:118` relays the `sd-status` result verbatim,
so it inherits `F-*`/`T-*` and the `none` relay rule at `sd-status:87-88` by
reference. Two words change; no second copy of the selector contract is written
into housekeeping.

**Drift test (R5).** Fails when the shipped surface mentions `F/T/R`, `R-*`, or
a separate Roadmap collection. Scope is the shipped surface only.

## Compatibility

The emitted status JSON and human output do not change — measurement 2 shows
no `R-*` is produced today. Nothing consuming status output can break, because
nothing observable moves.

`SKILL.md` bodies are shipped payload, so both edits change the payload digest.
That is R6's "release metadata, and candidate evidence": version bump, changelog,
candidate ledger restamp. Root mirrors regenerate through `make sync`
(`install.py . --force`), not by hand.

Coordination, per the PRD's own 2026-07-25 reconciliation note plus one it does
not carry:

- `07-25-parallelize-fleet-status` and `07-24-track-clean-recovery-artifacts` R5
  both touch the status surface; this lands first or independently.
- **`07-28-stop-committing-generated-mirrors` deletes the two mirror files
  outright.** If it lands first, this task edits two files instead of four and
  the drift test's mirror paths must not be hardcoded. Not in the PRD.

## Rollout and rollback

One commit: two prose edits, `make sync` for the mirrors, the drift test, then
version bump plus changelog plus candidate restamp. Splitting the test from the
edit means shipping a test that fails on the tree that introduced it.

Rollback is a revert. No data, no state, no migration — the wording described a
capability the code had already lost.

## Risk

1. **Implementing from the `sd-housekeeping/SKILL.md:75-77` citation.** Those
   lines are the PR-eligibility receipt contract. Editing them to remove a
   selector that is not there damages an unrelated, working contract.
2. **Naming `R-*` in the rejection sentence to satisfy R3.** It reintroduces the
   retired selector onto a live surface and trips R5's own test (measurement 5).
3. **Writing R5's test as an exclusion list.** It must then exclude three active
   PRDs, the archive, and the journal — and the next task that documents this
   history breaks CI (measurement 6).
4. **Reading R1 literally and editing the active-task PRDs.** They are the
   removal's tracking record, not a claim about current behavior; R1's own
   qualifier excludes them.
5. **Rewriting `sd-status/SKILL.md:74-89`.** The `F-*`/`T-*` definitions are
   already correct and match R2 exactly. Touching them for tidiness is
   unreviewable churn in the middle of a two-token change.
6. **Treating AC1 as work.** It describes emitted output, which measurement 2
   shows is already conformant. Verify it; do not build toward it.
