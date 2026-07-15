# Review nits cleanup batch

## Goal

Close the residual low-value nits from the 2026-07-09 deep review that were
individually below the bar for their own task. Each is independent and cheap;
this batch exists so the review has zero untracked findings. Any item that
turns out non-trivial on inspection should be split into its own task rather
than bloating this one.

## Problem / items

Each item is CONFIRMED by the review and is a small, self-contained fix:

- **N1 — housekeeping offline `gh` message (tooling INFO).**
  In `scripts/sd-ai-command-pack-housekeeping.sh`, an offline/unauthenticated
  `gh` failure in the merge step is reported the same as "no PR", so the run
  fails closed but the message misattributes the cause. A `gh auth status`
  probe would distinguish "unauthenticated" from "no open PR".
- **N2 — predictable `/tmp` uv-cache path (tooling LOW/PLAUSIBLE).**
  `scripts/sd-ai-command-pack-shell-lib.sh` defaults
  `UV_CACHE_DIR=/tmp/sd-ai-command-pack-uv-cache` when `TMPDIR` is unset
  (typical Linux/CI), which another user on a shared host could pre-create and
  squat. Include `$(id -u)` in the default or prefer `XDG_CACHE_HOME`.
- **N3 — unguarded `symlink_to` in a test (testing LOW).**
  `tests/test_pack_drift.py:205`
  (`(stub_bin / "python3").symlink_to(...)`) lacks the try/except guard the
  four sites fixed in 282999e/e3e5aeb use; on a symlink-hostile platform it
  errors instead of skipping. Either guard it or declare symlink support a
  suite prerequisite and drop the inconsistent guards elsewhere.
- **N4 — Makefile `test` lacks CI's skip backstop (tooling INFO).**
  `make test` can pass with skipped tests that CI's "Fail on skipped tests"
  step (`.github/workflows/tests.yml`) would reject, so local `make check`
  and CI disagree. Add the same skip check to the Makefile target (or document
  the intentional asymmetry).
- **N5 — `install_test_support.py` is a grab-bag mega-mixin (testing LOW).**
  One ~785-line `InstallTestCase` holds repo factories, gh/gito stub writers,
  and 60-string content asserts. Split into per-concern support modules on the
  next substantive touch (repo factories / stub writers / content asserts).
- **N6 — no Python 3.11/3.12 CI lanes (testing/tooling LOW).**
  The matrix covers 3.10 + 3.13 only. Decide whether to add 3.11/3.12 (closes
  the interpreter gap between the floor and the ceiling) or document the
  two-ended matrix as intentional.
- **N7 — consumer legacy-name references (cross-repo LOW, consumer-owned).**
  Two consumers' own files still carry legacy pack references: loadsmith's
  generated repository map reports old command names, and rwbp-coordinator's
  review-churn checker references `TRELLIS_REVIEW_PR_PACK.md`. Mezmo's
  review-cycle checker warning was resolved during the 0.8.6 fleet rollout in
  PR #341. (The former green-button-manager copy was loadsmith's now-deleted
  duplicate clone, not a distinct consumer.)
  These are repo-owned, not pack payload — the pack cannot fix them; this item
  is a tracked note to raise the cleanup with those repos during the next fleet
  touch, not pack work.

## Requirements

- R1: Address N1–N6 in the pack (fix or document-as-intentional per item);
  each fix keeps the relevant gate green (shellcheck `-S warning`, 100%
  installer coverage, scripts/templates twins byte-identical, CI parity test).
- R2: N7 is recorded as a consumer-coordination note (no pack code change);
  fold it into the fleet-refresh touch or raise issues on the three repos.
- R3: Any item that proves non-trivial (e.g. N5 splitting the support module,
  or N6 if adding lanes surfaces failures) is split out into its own task
  rather than expanding this batch.

## Acceptance Criteria

- [x] N1: housekeeping distinguishes unauthenticated `gh` from no-PR in its
      report; `--self-test`/housekeeping tests still green.
- [x] N2: uv-cache default is per-user (or `XDG_CACHE_HOME`); shellcheck clean;
      twins byte-identical.
- [x] N3: the test symlink call is guarded consistently, or the suite's
      symlink prerequisite is documented and the other guards reconciled.
- [x] N4: `make test` and CI agree on skipped-test handling, or the asymmetry
      is documented.
- [x] N5: decision recorded (split now vs defer); if split, tests still green.
- [x] N6: 3.11/3.12 decision recorded and applied (lanes added or intent
      documented); CI green.
- [x] N7: consumer-coordination note filed (issues or fleet-touch checklist).
      Recorded in `07-09-07-10-rollout-085-to-fleet`; remaining warnings are
      loadsmith `docs/repomix-map.md` and the rwbp-coordinator repo-owned
      review-churn checker.

## Non-goals

- Any behavior change to shipped installer/removal logic.
- Turning this into a dumping ground: genuinely new findings get their own
  task; this batch is frozen to N1–N7.

## Decisions (2026-07-14)

- N5 is closed as a deliberate defer. `InstallTestCase` is large but remains a
  test-only support surface with stable concern headings, and this sweep needed
  no substantive restructuring of those helpers. Splitting it now would create
  node-ID/import churn without reducing production risk. Reconsider only when
  a future feature requires changing multiple unrelated helper concerns.
- N6 keeps endpoint coverage: Python 3.10 is the supported floor and 3.13 is
  the current runtime, with a macOS 3.13 leg. Adding duplicate 3.11/3.12 jobs
  is not justified without a version-specific defect; CONTRIBUTING.md records
  that cost/coverage decision.
