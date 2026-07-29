# Implementation — consolidate the two divergent secret redactors

## Order

### Step 0 — make the existing test able to fail

1. Rewrite the body assertions in
   `tests/test_script_lib.py:670` `test_environment_evidence_redacts_and_bounds_diagnostic`
   so each asserts the **credential body alone**, not prefix+body as one literal:
   `assertNotIn("ABCDEFGH012345678", diagnostic)`, not
   `assertNotIn("ghp_ABCDEFGH012345678", diagnostic)`.

   **Gate:** this passes on today's code, unchanged. Verified 2026-07-28 that the
   current form passes even when only the `ghp_` prefix is redacted and the body
   survives — so until this is fixed, the suite cannot detect the regression this
   task is most likely to introduce. Land it as its own commit, before any
   pattern change.

### Step 1 — the shared table

2. Add the shape table to `scripts/sd_ai_command_pack_lib.py`. Each row carries a
   **detector** form and a **substituter** form; see `design.md` for the table and
   why one regex cannot serve both.

   Substituter rows require a body charset and a minimum length. A prefix-only
   substituter leaves the secret in the text — measured: fleet's pattern under
   `.sub()` turns `ghp_ABCDEFGH012345678` into `[redacted]ABCDEFGH012345678`.

3. Export two accessors: a compiled detector alternation, and an ordered list of
   `(pattern, replacement)` pairs for substitution.

   **Gate:** substituter ordering is explicit and tested. The PEM span must run
   before the key-value rule, or a `-----BEGIN … PRIVATE KEY-----` header
   following a `key:` on the same line is partly consumed by the shorter rule.

4. PEM needs a span, not a header match. Redact from `-----BEGIN … PRIVATE KEY-----`
   through `-----END … PRIVATE KEY-----`, with a length bound so an unterminated
   header does not eat the whole diagnostic.

5. Bound the key-value substituter. The fleet detector's `\S+` is greedy across
   trailing punctuation — measured: `password: hunter2trailing, then continue`
   becomes `[redacted] then continue`, losing the comma. R3.

### Step 2 — repoint both call sites, keep both policies

6. `scripts/sd_ai_command_pack_lib.py:512` `_redact_environment_text` consumes the
   **substituter** list at `:519`, in place of `_ENVIRONMENT_SECRET_RE`. Still
   returns a bounded string; still never raises.

7. `scripts/sd-ai-command-pack-fleet-timing.py:172` consumes the **detector**, in
   place of `SECRET_RE`. Still raises
   `FleetTimingError(f"{label} contains secret-like material")`.

   **Gate:** R2. Neither site acquires the other's policy. A fail-closed reject in
   the diagnostic path drops the diagnostic recovery depends on; a silent
   substitution in the fleet path accepts what that path exists to refuse.

8. Add the R7 no-weakening check: keep the old `_ENVIRONMENT_SECRET_RE` as
   **test-only data**, run it and the new substituter set over the same corpus,
   and assert every span the old one redacted is still redacted.

### Step 3 — R4, widen the test table

9. Positive substituter cases, each asserting the **body** is absent:
   `github_pat_`, `xox[baprs]-`, `sk-`, a PEM block, `password:`, `api_key=`.
   The `github_pat_` case fails today (AC2) — `gh[pousr]_` excludes the `i`.

10. Positive detector cases: the same shapes make `fleet-timing.py` raise.

11. Negative case for R3: a diagnostic whose surrounding context survives
    redaction. Assert the context, not just the absence of the secret.

### Step 4 — R6 template parity

12. Mirror every lib edit into `templates/scripts/sd_ai_command_pack_lib.py`, then
    `make sync`. The generated-parity check compares the copies.

### Step 5 — R5, wire the orphans

13. Take shape **A** from `design.md` unless step 14 rules it out: keep the
    current `key=value` invocation, and on non-zero exit re-invoke with `--json`
    to capture `{"outcome": "blocked", "environmentBlocked": …}`.

    **Do not** simply add `--json` to the existing call.
    `_cache_env_main:695-700` switches the **success** output to JSON as well, and
    `toolchain.sh:421`'s `while IFS='=' read -r key value` loop hard-fails on any
    unrecognized key (`fail "cache setup returned an unexpected variable: $key"`,
    then `count -eq 7`). That breaks every successful toolchain invocation, in a
    shell layer with no test coverage.

14. Before adopting A, confirm `build_tool_environment` is idempotent — shape A
    calls it twice on the failure path.
    **Gate:** if it is not idempotent, use shape B (parse JSON on both paths) and
    rewrite the `key=value` loop plus its empty-value and `count -eq 7` guards.

15. Drop `2>/dev/null` from the failing invocation (`toolchain.sh:417`). It is
    discarding the `f"error: {error}"` text the non-json path emits.

16. Replace `toolchain.sh:418`'s hardcoded remediation prose with the structured
    `recoveryAction`. Keep the wording equivalent — this removes a duplicate, it
    does not change what the operator is told.

17. Call `validate_environment_blocked_evidence` (`:606`) on the fragment before
    `toolchain.sh` consumes it. That gives it its first non-test caller (AC5) and
    fails a malformed fragment at the producer rather than delivering it to an
    agent as a plausible-looking blocker.

### Step 6

18. Changelog + version. Fleet rollout via normal refresh.

## Validation

Step 0's gate — the rewritten assertions pass on unchanged code:

```bash
python3 -m pytest tests/test_script_lib.py -k environment_evidence -q
```

AC2's decisive check — the case that fails today:

```bash
python3 -m pytest tests/test_script_lib.py -k "github_pat" -q
```

Both policies preserved, asserted separately (AC3):

```bash
python3 -m pytest tests/test_script_lib.py tests/test_fleet_timing.py -q
```

R6 parity:

```bash
diff scripts/sd_ai_command_pack_lib.py templates/scripts/sd_ai_command_pack_lib.py
```

Expect no output.

```bash
make sync && make check
```

R5 has no automated fixture today. Verify by forcing a cache failure — point
`SD_AI_COMMAND_PACK_CACHE_ROOT` at an unwritable path — and confirm `toolchain.sh`
emits the validated fragment's `recoveryAction` rather than the hardcoded string.
Confirm separately that the **success** path still exports 7 variables; that is
the regression step 13 is guarding against.

## Review gates

- Step 0 lands alone, first. Without it the suite cannot fail on the prefix-only
  leak, which is this task's most likely defect.
- No substituter row ships with a prefix-only pattern. Reviewed row by row.
- R2 is checked as two assertions, not one: lib substitutes and returns; fleet
  raises. A shared helper that made both behave alike would pass a
  "secret is gone" test and violate the requirement.
- Step 13's success-path check runs before the R5 commit is accepted. It touches
  untested shell.
- Land this task before `07-28-consolidate-shared-script-helpers` if both are
  active — that task's "preserve existing `environment_blocked` evidence
  behavior" constraint should be checked against the final redactor.

## Rollback

Three independent commits (redactor / parity / R5 wiring), each a plain revert.
Nothing is persisted, versioned, or consumed across a release boundary, so there
is no window during which rollback is release-level.
