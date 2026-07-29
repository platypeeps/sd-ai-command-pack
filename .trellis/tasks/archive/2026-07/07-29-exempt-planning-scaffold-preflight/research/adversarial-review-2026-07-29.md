# Planning adversarial review — 2026-07-29

Contract: `.claude/sd-ai-command-pack/planning-adversarial-review.md`.
Scope: this task's `prd.md` and the landed diff it describes (the record is
retroactive — implementation preceded the task, so the review covers both).

## Lanes

- **Host lane** — run inline. Status: **completed**, 1 blocking concern (C-1).
- **Codex CLI lane** — run via `codex exec` in the worktree. Status:
  **completed**, verdict "Blocking concerns found", 3 concerns (C-2 … C-4).

Neither lane was skipped and neither failed to produce a verdict.

## Concern ledger

### C-1 — a second seed-row lane was left unexempted (host) · **addressed**

`validateBookkeepingTaskContexts` is an independent enforcement path that emits
the `task_context_seed` reason code from the bookkeeping / final-bundle
validator. The first fix touched only `checkTrellisTaskContextManifests`, so
creating a task still failed through the validator lane — the same defect,
different exit.

Fix: threaded `archived` into `validateBookkeepingTaskContexts`, gated the seed
issue on `!archived && record.status === 'planning'` plus the same
`isPristineTrellisTaskContextScaffold` predicate, and added both-ways coverage
in `tests/test_bookkeeping_validator.py`. Recorded as R1 and A4.

### C-2 — exemption is shape-based, not the exact Trellis scaffold (Codex) · **addressed (wording corrected, behavior kept)**

Codex is factually right: `isPristineTrellisTaskContextScaffold`
(`scripts/sd-ai-command-pack-review-preflight.mjs:3063`) checks only that the
single row parses to a plain object with exactly one `_example` key. It never
compares the value with `_SEED_EXAMPLE`
(`.trellis/scripts/common/task_store.py:139`). So an `_example`-only row whose
value was hand-edited is also exempt, and the PRD's "the exact file `task.py
create` writes" / "cannot mask a real stale scaffold" overstated that.

The behavior stands. Pinning the exact `_SEED_EXAMPLE` string would make the
pack's gate depend on Trellis-owned text that changes across Trellis versions —
the next Trellis upgrade would re-break task creation in exactly the way this
task fixes, and consumers would have to wait for a pack release to recover. The
shape predicate is deliberately value-agnostic.

Fix: corrected R2, Out of Scope, A3, and the changelog to state the actual
predicate, its rationale, and the accepted residual (inside `planning` only; the
row still has no `file` key and still fails the moment status changes).

Codex's sub-point that the end-to-end fixtures write rows directly instead of
invoking `task.py create` is also correct, and A3 no longer claims otherwise.
Byte-level agreement with the real generator rests on the live dogfood recorded
under Verification, which is named as such rather than implied by the suite.

### C-3 — candidate ledger stale, so A4/A5 were not true of the tree (Codex) · **addressed**

Reproduced read-only:

```
candidate ledger error: candidate ledger payloadDigest is 'sha256:9c2a4b0a…';
expected 'sha256:3f0e7bda…'
```

The ledger was generated before the C-1 fix, and both changed templates are
manifest payload sources, so `make generate` could not report clean. Fix:
regenerated the ledger after the last payload edit and re-ran the gates. A6 now
states the digest-match requirement explicitly.

### C-4 — affected-population claim too broad (Codex) · **addressed**

`prd.md`, `task.json`, `CHANGELOG.md`, and the parent's residue section said
task creation broke "every"/"any" pack-installed repo. Trellis seeds the
manifests only when `_has_subagent_platform` succeeds
(`.trellis/scripts/common/task_store.py:146`, `:346`).

Fix: narrowed the claim in all four places to pack-installed repositories where
task creation actually seeds the JSONL manifests.

## Round 2

The corrected record was re-submitted to the Codex lane. It returned two
residuals, both correct, both now fixed.

### C-2r — the source comment still carried the retracted claim · **addressed**

`validateBookkeepingTaskContexts` opened with a comment calling the scaffold
"the exact file `task.py create` writes" — the exact wording retracted
everywhere else. Fix: rewrote the comment to state the shape match and why the
seed text is not pinned.

### C-4r — the "unaffected population" was still wrong · **addressed**

The first correction said a repo "with Codex in inline dispatch mode" is not
seeded. That misreads the predicate: `_has_subagent_platform` returns true on
the first matching entry of `_SUBAGENT_CONFIG_DIRS` and only reaches the Codex
dispatch-mode branch when none matched. A `.claude` repo is seeded whatever
Codex's mode is — this worktree is the counterexample, with Codex inline,
`.claude` present, and both scaffolds written. Fix: `prd.md` now states the
fall-through order and names this worktree as an affected case.

## Disposition

Six concerns across two rounds — C-1 (host), C-2 … C-4 (Codex round 1), C-2r
and C-4r (Codex round 2). All addressed; none deferred, none open.
Implementation is unblocked.
