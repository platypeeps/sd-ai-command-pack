# Design — measure the unmeasured shipped runtime

## Scope boundary

`.coveragerc`, the CI test workflow, and whatever JS/shell coverage tooling is
adopted. **No coverage floors are added by this task** (PRD R4) — measurement
first, gating in a follow-up.

## Confirmed state

`.coveragerc` `[run] include` lists `install.py`, `installer/*`, and the
`scripts/sd-ai-command-pack-*.py` family plus twins. `.github/scripts/*.py` is
absent, so `bookkeeping_ci_scope.py` (477 lines) is mypy-checked at
`tests.yml:346` but never coverage-measured.

`review-preflight.mjs` is 4,547 lines and its only CI check is:

```yaml
- name: Review preflight JavaScript syntax
  run: |
    node --check scripts/sd-ai-command-pack-review-preflight.mjs
```

`node --check` parses. It does not execute a single line.

`full-check.sh` is 1,073 lines and contains an inline Python program started at
`:610` with `python3 - <<'PACK_SOURCE_DRIFT_GATES'`. Code delivered on stdin has
no file path, so coverage cannot attribute it — structurally unmeasurable where
it stands.

## The measure/gate separation is already structural

`.coveragerc` has two include lists:

- `[run] include` — what gets **measured**
- `[report] include` — `install.py` + `installer/*` only, with `fail_under = 100`

Adding `.github/scripts/*.py` to `[run] include` therefore measures without
touching the strict 100% gate. **R1 is genuinely a one-line, zero-risk change**
and should land alone and first, as its own commit. This is worth stating
explicitly because the instinct on a coverage task is to fear that any include
change tightens a gate; here it does not.

The shipped-scripts gate passes its own `--include`/`--fail-under` on the command
line, so it is likewise unaffected.

## Three surfaces, three different problems

| surface | size | today | difficulty |
|---|---|---|---|
| `.github/scripts/*.py` | 477 lines (one file) | nothing | trivial — config only |
| `review-preflight.mjs` | 4,547 lines | `node --check` | new toolchain (c8), new CI step |
| `.sh` surface | 1,073 lines (full-check alone) | nothing | new toolchain + an unmeasurable region |

They share a goal but not a solution, and bundling them makes the trivial one wait
on the hard one. Land them as three independent changes.

## The inline Python program

The ~262-line program at `full-check.sh:610` must be extracted to a real file
before it can be measured. That extraction is a behavior-preserving refactor of a
gate that guards releases — it deserves its own change and its own review, not a
paragraph inside a coverage task. Treat it as a prerequisite for the shell lane,
or explicitly scope the shell lane to exclude it and say so.

## Subprocess plumbing already exists

`tests/coverage_sitecustomize/sitecustomize.py:22` already handles subprocess
coverage, and `.coveragerc` `[paths]` maps installed/template twins back onto
canonical sources. The omission is configuration, not capability — no new
infrastructure is needed for the Python half.

## Reopening a prior decision

A-033 (fixed) closed by *documenting* shell and `.github/scripts` as
coverage-exempt. This task reverses that. Record the reversal explicitly wherever
that exemption is written down; leaving both statements in the repo recreates the
contradiction pattern that `07-28-document-remaining-shipped-scripts` exists to
fix.

## Rollout and rollback

Each of the three changes is independently revertable. Publishing numbers changes
no gate, so a bad measurement is embarrassing rather than blocking. Floors arrive
in a separate follow-up task, set at or below measured values.

## Risk

The real risk is the opposite of the usual one: adding a measurement lane that
*silently reports nothing* — a c8 invocation that instruments no files, or a shell
tracer that produces an empty profile — looks like success. Every new lane must
assert a **non-zero** measured line count, not merely exit 0.
