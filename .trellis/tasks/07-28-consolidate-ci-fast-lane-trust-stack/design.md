# Design — consolidate or retire the bookkeeping CI fast-lane trust stack

## Scope boundary

`.github/workflows/tests.yml`'s bookkeeping job, `.github/scripts/bookkeeping_ci_scope.py`
(477 lines), and `.github/scripts/check-ci-result.sh` (73 lines). The rest of the
test matrix is out of scope.

## Do not sequence A-038 behind the measurement

The PRD's sequencing note offers "decide this before hardening, unless A-038 is
urgent." It is urgent. A-038 is **P0 · Verified** — adversarially confirmed, not a
pointer — and it is a branch-protection bypass:

- `tests.yml:148` materializes the classifier with
  `git show "$BEFORE_SHA:.github/scripts/bookkeeping_ci_scope.py"`.
- `tests.yml:47` — on `synchronize`, `BEFORE_SHA` is the PR's *previous head*, so
  the classifier comes from the PR branch itself.
- `tests.yml:145` guards only mode `100644`, type `blob`, and exact path. No blob
  identity check.
- `bookkeeping_ci_scope.py:26` — `ALLOWED_PATH_PREFIXES` and every fail-closed
  reason live inside that untrusted file.
- `tests.yml:9` — `concurrency` cancels the in-progress run, so the tamper commit
  is never linted or tested.

**Harden first, decide second.** The hardening is small and is not wasted work if
the lane is later retired: compare the classifier's blob hash at `BEFORE_SHA`
against the same path at the PR base, and select full mode on any mismatch.
Retirement also fixes A-038, but retirement is a measurement-gated decision with
an unknown date, and a P0 bypass should not wait on a scheduling question.

**Correction, 2026-07-28.** An earlier revision of this section proposed reading
the classifier from `PROTECTED_REF` (`tests.yml:52`). That is wrong.
`PROTECTED_REF` is `${{ github.ref }}`, which on a `pull_request` event is
`refs/pull/<n>/merge` — the PR author's content merged into base — so it is not a
trust anchor on the exact event type where the fast lane engages. The anchor is
`github.event.pull_request.base.sha`, already used under the name `BASE_SHA` by
the `release-payload-gate` job at `tests.yml:410`.
`07-28-pin-bookkeeping-ci-classifier-trust` owns the fix and carries the detail.

## The measurement, concretely

R1 asks for CI minutes saved. Make it falsifiable rather than impressionistic:
over a representative window of merged PRs, compare wall-clock and billable
minutes for runs that took the bookkeeping fast lane against the full-matrix
runs, and record how many runs actually hit the fast lane. A lane that fires
rarely saves little regardless of how much it saves per hit — frequency is half
the number and is the half most likely to surprise.

## A-041 — one allowlist, three copies, already drifted

Confirmed 2026-07-28:

| location | prefixes |
|---|---|
| `.githooks/pre-push:54` | `.trellis/tasks/*`, `.trellis/workspace/*`, `.trellis/audit/*` |
| `.github/scripts/check-main-push-scope.sh:71` | the same three |
| `.github/scripts/bookkeeping_ci_scope.py:26` | `.trellis/tasks/`, `.trellis/workspace/` — **`.trellis/audit` absent** |

The consequence is the one the finding names: an audit-ledger chore push passes
both push guards but classifies as `changed_path_not_bookkeeping` and pays the
full matrix. The `sd-audit-repo` command writes `.trellis/audit/ledger.md` on
every run, so this is a live, recurring miss.

Note the two copies are also mechanically different — shell `case` globs versus
Python string prefixes. A `--print-allowed-prefixes` mode on the classifier,
consumed by both shell guards, unifies the *value*; the matching semantics stay
separate and should be tested on a path that distinguishes them.

Whether `.trellis/audit/**` should be bookkeeping-scoped at all is a deliberate
decision, not an oversight to paper over: the ledger is written by an automated
command, which is an argument both for (routine, low-risk) and against (machine-
generated content skipping the full matrix).

## Retain vs retire

**Retire** is the honest option if the measured saving is small. It deletes the
untrusted-classifier materialization, the eight-argument acceptance table in
`check-ci-result.sh`, and 477 lines of classifier — and A-038 and A-041 go with
them.

**Retain** obliges R2: move the receipt validation and the `ls-tree` guard out of
~200 lines of inline workflow bash plus multi-clause jq (`tests.yml:57` onward)
into `bookkeeping_ci_scope.py` as one testable entry point. Two things make this
worth doing beyond tidiness:

- Inline workflow bash is the least testable layer in the repo — there is no way
  to unit-test a `run:` block.
- `07-28-measure-unmeasured-runtime-surface` R1 adds `.github/scripts/*.py` to
  `.coveragerc`. Logic moved into the classifier becomes coverage-measured for
  free; logic left in YAML never can be. The two tasks compose.

The retain path is therefore "move the trust decision into a place where it can
be tested and measured", not merely "consolidate".

## Contract

Whichever path: exactly one component decides scope, and its inputs come from the
protected ref. `check-ci-result.sh:52` currently accepts
`(pull_request, success, bookkeeping, skipped×5)` as green — that acceptance
table is the last line of defense and must be derived from the same source as the
classification, not hand-maintained alongside it.

## Rollout and rollback

Hardening lands first and alone; it is a small diff to one `run:` step and
reverts cleanly. The retain/retire change is larger and should land after a
recorded measurement. Retirement is the harder one to reverse — restoring a
deleted fast lane means restoring the trust stack too — so if the measurement is
ambiguous, prefer retain-and-harden.

## Risk

The stated risk is CI minutes. The real risk is that this stack decides *whether
the test matrix runs at all*, from code it fetches at runtime. Any change here
should be reviewed as a security boundary change, not a CI optimization.
