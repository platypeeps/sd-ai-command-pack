# Implementation — split behavior and content payload digests

## Order

1. **Resolve the doc classification first.** Confirm or reject the design's
   recommendation that `templates/.claude/sd-ai-command-pack/planning-adversarial-review.md`
   stays behavior-bearing despite `kind: "doc"`. Everything downstream depends on
   it and it is a judgement call, not a code change.
   **Gate:** decision written into `design.md` before any code is touched.

2. **Add the manifest projection helper** in
   `scripts/sd_ai_command_pack_fleet_lib.py`, next to `payload_digest`. Pure
   function: manifest in, behavior-relevant subset out. Unit-test it directly —
   this is the piece the finding omits and the easiest to get subtly wrong.

3. **Split `payload_digest` (`:663`) into two functions** with distinct domain
   separators. Do not parameterize one function with a flag; two named functions
   keep the separators impossible to swap by accident.

4. **Extend the ledger schema** — add the second digest field, bump
   `CANDIDATE_LEDGER_SCHEMA_VERSION` at `:19` from `2` to `3`.

5. **Update `validate_candidate_ledger` (`:728`).** Behavior digest keeps today's
   hard-fail at `:743-751`. Content digest records a note and does not append to
   `errors`.

6. **Restamp `docs/fleet/candidate-validation.json`** in the same commit as step 4.
   A schema bump without a restamp red-lights the fleet gate for everyone.

7. **Tests, both directions:**
   - doc-only edit → behavior digest unchanged, validator passes (PRD AC 1)
   - shipped-script edit → behavior digest moves, stale ledger still hard-rejects
     (PRD AC 2)
   - allowlisted behavioral doc edit → behavior digest **moves** (design decision
     from step 1)
   - adding a `kind: "doc"` manifest entry → behavior digest unchanged. This is
     the projection test; without it R3 silently does not work.

## Validation

```bash
python3 -m pytest tests/ -k "digest or candidate_ledger" -q
```

```bash
make check
```

Confirm the restamp is real rather than assumed:

```bash
git diff --stat docs/fleet/candidate-validation.json
```

## Review gates

- Before step 2: doc classification decided and recorded.
- Before step 6: schema bump and restamp staged together, never separately.
- Before completion: the negative test (script edit still rejects) passes. A
  behavior digest that is too narrow is worse than no split at all.

## Rollback

Single commit containing code, schema bump, and restamped ledger. Plain revert
restores the working state. No consumer reads the ledger, so no consumer-side
rollback exists or is needed.
