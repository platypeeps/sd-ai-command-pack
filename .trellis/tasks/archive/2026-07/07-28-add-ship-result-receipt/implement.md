# Implementation — validated ship result receipt

## Order

1. **Fix the two independent defects first, separately.** They are real today and
   do not depend on the receipt:
   - `record_result` sets `state["phase"] = "complete"` by direct assignment.
     Route it through `transition_state`, which enforces
     `LEGAL_TRANSITIONS[current_phase]`.
   - `mergedPrs` increments on `outcome == "completed" and pr_number is not None`.

   Landing these first keeps the receipt diff readable and gives two small
   revertable commits instead of one large one.
   **Gate:** `transition_state` change must surface any currently-illegal path
   into `complete`. If tests go red here, that is the bug being found, not the
   change being wrong — investigate before adjusting `LEGAL_TRANSITIONS`.

2. **Extend `CURRENT_FIELD_ORDER`** for the four fields with no destination
   (merge state, finish-work state, housekeeping state, anomalies). Decide
   explicitly whether each belongs in `STABLE_CURRENT_FIELDS` /
   `TRANSITION_CURRENT_FIELDS`.
   **Gate:** write down the stable/transient decision per field. A field that
   should survive a transition but does not will drop receipt data silently.

3. **Define the schema-v1 receipt** and emit it from
   `.agents/skills/sd-ship/SKILL.md:202`, alongside the existing free-text block.
   Do not remove the free-text block — `tests/test_sdlc_commands.py:724` asserts
   its presence and operators read it.

4. **Add `result --from-receipt`** to `scripts/sd-ai-command-pack-work-loop.py`.
   Parse, validate the version, then **independently recompute** against git and
   the PR rather than trusting the receipt's assertions. Cross-check at minimum:
   PR identity, final head, merge state.

5. **Add named reason codes** for malformed JSON, version mismatch, and each
   cross-check failure. Use the existing reason-code table at the top of
   `work-loop.py`; do not start a parallel error vocabulary.

6. **Flip `mergedPrs`** to increment from the verified merge state rather than the
   typed outcome string.

7. **Fix the test that encodes the defect.** `tests/test_work_loop.py:3257`
   passes a mismatched PR URL and is accepted. Change it to assert rejection.

8. **Repoint the consumer instruction** at
   `.agents/skills/sd-work-backlog/SKILL.md:274` — prose today, no command block,
   no `--json`. Give it the actual `--from-receipt` invocation.

9. **Mirror all skill and script twins**, `make sync`.

## Validation

```bash
python3 -m pytest tests/test_work_loop.py tests/test_sdlc_commands.py -q
```

The decisive case — a receipt whose PR URL disagrees with the validated PR must
be rejected:

```bash
python3 -m pytest tests/test_work_loop.py -k receipt -q
```

```bash
make sync && make check
```

## Review gates

- After step 1: the two defect fixes land as their own commits, green, before any
  receipt work starts.
- Before step 4: schema v1 written down, including what each field means and
  which are required.
- Before completion: step 7 done. A suite where `:3257` still passes a mismatched
  URL has not verified this task.

## Rollback

Three separable commits (defect fixes / state fields / receipt). The typed path
stays live throughout, so a receipt-side failure degrades to today's behavior
rather than blocking the loop. Release-level revert for the shipped skills.

## Explicitly not in this task

Removing the typed `result` path. It stays until the receipt path has run in
anger; deleting it here would make rollback mean "the loop cannot record results."
