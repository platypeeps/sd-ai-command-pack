# Implementation — measure the unmeasured shipped runtime

## Order

### Lane 1 — `.github/scripts/*.py` (land alone, first)

1. Add `.github/scripts/*.py` (and the twin path if one exists) to `[run] include`
   in `.coveragerc`. Do **not** touch `[report] include` — the `fail_under = 100`
   gate stays scoped to `install.py` + `installer/*`.

2. Run the suite and read the number.

   **Gate:** `bookkeeping_ci_scope.py` must appear in the report with a
   **non-zero statement count**. A file that is included but never imported
   reports 0% and looks like a finding when it is actually a plumbing failure —
   check which it is before recording the number.

3. Record the measured baseline in the task notes. No floor is set here (R4).

### Lane 2 — `review-preflight.mjs`

4. Confirm the current state is what R2 claims:

   ```bash
   grep -n "node --check" .github/workflows/tests.yml
   ```

   Expect the syntax-only check at `:348-350`.

5. Add `c8` (or the chosen Node coverage tool) and wire it around the existing
   JS test invocation. If there is no JS test invocation, say so plainly — then
   this lane's real content is "there are no tests to measure", which is a
   different and larger task than adding a coverage tool.

   **Gate:** decide and record which it is before writing any config. Adding c8
   to a suite that executes nothing produces a green lane reporting 0% over 4,547
   lines.

6. Publish the number in CI output.

### Lane 3 — shell

7. Decide the scope question first: is the inline Python program at
   `full-check.sh:610` extracted, or is the shell lane explicitly scoped to
   exclude it?

   **Gate:** answer recorded before any tooling work. Extraction is a
   behavior-preserving refactor of a release gate and belongs in its own change,
   not folded in here.

8. Add the shell coverage tool (`kcov` or `bashcov`) for the remaining shell
   surface and publish the number.

## Validation

Lane 1 — the decisive check is that the newly included file is actually measured:

```bash
python3 -m pytest -q && python3 -m coverage report --include=".github/scripts/*"
```

Expect a row for `bookkeeping_ci_scope.py` with a non-zero statement count.

Confirm the strict gate did not move:

```bash
grep -n -A4 "^\[report\]" .coveragerc
```

Expect `include` still listing only `install.py` and `installer/*`, and
`fail_under = 100` unchanged.

Full gate:

```bash
make check
```

## Review gates

- Lane 1 lands and ships alone before lanes 2 and 3 begin. It is a one-line
  config change; do not let it wait on a toolchain decision.
- Each new lane must be shown to measure something. A lane reporting 0% is
  reviewed as a suspected plumbing failure until proven to be a genuine
  coverage gap.
- No `fail_under` and no minimum threshold is added anywhere in this task (R4).
  If a reviewer asks for one, that is the follow-up task.
- The A-033 exemption note must be updated or removed in the same change that
  reverses it, so the repo does not simultaneously document these surfaces as
  exempt and measure them.

## Rollback

Each lane is a self-contained revert. Because no gate is added, reverting a lane
removes a number from CI output and blocks nothing.
