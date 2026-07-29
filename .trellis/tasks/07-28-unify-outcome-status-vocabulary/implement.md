# Implementation — unify the outcome and status vocabulary

## Order

### Step 0 — scope the rule before touching a payload

1. Adopt the envelope-scoped form of R1 from `design.md`: at the **top level of
   an emitted payload**, `status` means an embedded sd-status document and a
   verdict is `outcome`; nested per-entity state (`task["status"]`,
   `lane["status"]`, `providers[].status`) keeps `status`.

   **Gate:** written down before any rename. Measured 148 `status` reads against
   16 `outcome` reads; the unscoped rule renames essentially all 148 and attaches
   R5's dual-emit obligation to each.

2. Re-decide `review-local.py:2041` explicitly. It is `"status": row["status"]`
   inside a `providers[]` row, so the owning object already disambiguates it. The
   PRD's `attemptState` rename may still be worth it for clarity, but it is not
   forced by the envelope rule.

### Step 1 — R2, the shared core

3. Define the shared verdict core in `scripts/sd_ai_command_pack_lib.py` — from
   the PRD's own overlap analysis this is roughly `clean`, `blocked`, `skipped`,
   `failed`. Redefine the five per-domain sets as explicit extensions of it:
   `classify_outcome`, `review-local.py:58` `OUTCOMES`, `fleet-timing.py:62`
   `STAGE_OUTCOMES`, `fleet-timing.py:64` `CONSUMER_OUTCOMES`.

4. Add the drift test: a domain declaring a verdict absent from the core without
   an explicit opt-out fails (AC2).
   **Gate:** the opt-out must exist. Without it the test rejects legitimate
   values like `at-target`; without the test the sets drift apart again.

5. R3 — resolve `"ok"` (`sd_ai_command_pack_lib.py:697`) and `"recorded"`
   (`record-session.py:255`) onto the core, or record why each domain needs a
   distinct spelling. These are top-level keys, so they are in scope.

### Step 2 — R4, housekeeping's double `status`

6. Fix `housekeeping-result.py:358-359`. Either rename the embedded document key
   or rename the enum inside `outcome` — after this, `result["status"]` and
   `result["outcome"]["status"]` must not both exist with different types.

   Do **not** adopt the audit's `fix:` line verbatim: "standardize on top-level
   `outcome: {status, reasonCodes}`" reproduces the collision, because that is
   already the `classify_outcome` shape at `:258`.

7. **Update the shipped skill prose in the same commit.**
   `.agents/skills/sd-housekeeping/SKILL.md:75`, `:113`, `:120`, `:121`, `:130`
   name the key path and enumerate the enum values for an agent to follow, and
   each is 11 files after `make sync`. Also `docs/SD_AI_COMMAND_PACK.md:1154`.

   **Gate:** payload and prose agree at every commit. A dual-emit window protects
   code consumers, which fail loudly on a missing key; an agent reading stale
   prose does not fail, it improvises.

8. Emit the new key alongside the old (R5). Add a fixture consumer written
   against the **old** names that must keep passing for the whole window (AC5).

### Step 3 — review-local

9. Fix the dual naming: `:2035` emits `"outcome": receipt["outcome"]` and `:2064`
   emits `"status": receipt["outcome"]` — identical source value, two names.
   Converge on `outcome`, dual-emit per R5.

10. Update the readers at `scripts/sd-ai-command-pack-review.py:837` and `:1577`.

### Step 4

11. `make sync`, both `scripts/` and `templates/scripts/` copies.

12. Changelog + version. Record a `removed_version` for every deprecated key;
    the old keys drop in a later release, not this one.

## Validation

Decisive check — no envelope carries two types under one name:

```bash
python3 -m pytest tests/test_housekeeping_result.py tests/test_review_local.py -q
```

AC1 wants this asserted by a test that walks emitted shapes, not by inspection.
Write that walker; a grep cannot see value types.

Old-name consumers still work for the whole window:

```bash
python3 -m pytest tests/ -k "compat or deprecat" -q
```

Payload and shipped prose agree:

```bash
grep -rn "outcome.status\|outcome\.reasonCodes" .agents/skills/sd-housekeeping/SKILL.md
```

Every key path named there must exist in the emitted payload at this commit.

```bash
make sync && make check
```

## Review gates

- Step 0 before any rename. An unscoped R1 is a several-hundred-site refactor.
- Step 7 in the same commit as step 6 — never deferred to the end of the
  deprecation window.
- Before completion: `design.md`'s consumer table is current. It is AC6, and a
  rename with an unenumerated reader is a silent break.
- No old key is removed in this version (R5).

## Rollback

Plain revert while both key names are live — which is the entire deprecation
window. After the old keys are dropped in a later release, rollback is
release-level. Nothing in this task should reach that point.
