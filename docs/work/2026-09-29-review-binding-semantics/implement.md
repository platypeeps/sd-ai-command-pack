# Implement — review binding semantics

Four slices, in this order. Slices 1 to 3 land as one pull request, because
the class map, the stored manifest and the refusal change one contract.
Slice 4 is optional and waits for a measurement.

Each slice changes a bound file, so its own landing moves every open receipt
under the old rule. Land slices 1 to 3 together, at a time the operator
picks, so open receipts pay once.

## Step checklist

- [x] 1. Classes and normalizer, in `bin/sd_ship_bindings.py`. Size M
      (about 120 lines of code, 200 of tests).
      - Replace `REVIEW_TOOL_FILES` with `VERDICT_FILES`, `GATE_FILES`,
        `CHECK_FILES` and `IMPORT_EXEMPT` (with a reason per entry). Keep
        `REVIEW_TOOL_FILES` as their union for callers and tests that
        enumerate every bound file.
      - Add `sd_jev.py` and `sd_opencode.py` to `verdict`, `sd_gate_slots.py`
        to `check`, `sd_setup_github.py` and `sd_setup_guard.py` to
        `IMPORT_EXEMPT`.
      - Move `SharedReview.review_argv` to a new `bin/sd_review_request.py`
        (`verdict`); `sd_ship_review.py` calls it.
      - Add `normalized_hash(path)` and the tag `ast-docstring-1/py3.14`.
      - `review_binding` and `adjudicator_binding` hash `verdict` files
        normalized, per `design.md`, section "Digest and manifest".
      - Tests, in `tests/test_sd_workflow_state.py` and
        `tests/test_sd_ship_shared.py`: the import walk covers `sd-ship`,
        `sd-review` and `sd-check` and fails naming an unclassified module;
        each `verdict` member refuses on an appended statement and accepts
        an edited docstring; each `gate` and `check` member accepts any
        edit; an unparsable `verdict` file is hashed raw; a `verdict` file
        that reads `__doc__` fails the guard test; missing members read
        `absent` and unreadable ones refuse (sd:3272).
      - Fail-first: with `gate` files put back into the digest, the gate
        acceptance test fails naming the member.
- [x] 2. Manifest and refusal, in `bin/sd_ship_bindings.py`,
      `bin/sd_ship_review.py` and `bin/sd-ship`. Size M (about 80 lines of
      code, 150 of tests).
      - `binding_manifest(root)` and `binding_change(state, root)`.
      - `ReviewRuntime` gains `manifest` and `change`; `execute_review`
        stores `binding_manifest`; `DISPATCH_FIELDS` gains it.
      - `review_inputs` and `binding_moved` call `binding_change`.
      - Refusal text, `code` and `next_action` per `design.md`, section
        "Refusal". `review_binding_change` gains `changed`.
      - Tests: the refusal names a changed `verdict` file and a changed
        `policy` entry; a receipt without `binding_manifest` refuses with
        "predates the per-file manifest" and the next `prepare` records a
        full-branch re-review; a changed `gate` file appears under "also
        changed, not binding" only when a `verdict` or `policy` entry also
        moved; a released gate failure restores the manifest.
- [x] 3. Records. Size S. Built 2026-09-29 on `feat/review-binding-1834`
      with slices 1 and 2; the replayed measurement is in the PRD Status.
      The PR body narrows sd:1397 to option E; the operator updates the row.
      - This folder's PRD Status: the class table as landed, and the
        replayed measurement (acceptance: at least 70 of 162).
      - `skills/sd-ship/SKILL.md`: one paragraph on what moves a receipt
        and how to read the refusal.
      - Close sd:1246 and sd:1834 on merge. Narrow sd:1397 to option E, or
        close it with a pointer here, per the operator's answer.
- [ ] 4. Optional: symbol-level binding for `bin/sd_lib.py`. Size M.
      Start only if, 14 days after slices 1 to 3 land, `sd_lib.py`-only
      moves are still more than a quarter of binding moves.
      - Hash the normalized top-level definitions of `sd_lib.py` that the
        `verdict` modules reach by name, transitively, plus all imports.
      - Test: an added `sd_lib.py` function no `verdict` module reaches
        leaves the digest unchanged; an edit to `load_policy` moves it.

## Check that proves this wrong

Replay the measurement over the 30 days before 2026-09-29 with the landed
class map and normalizer. Fewer than 70 of 162 landings keeping the digest
means the class map or the normalizer is not what this plan says.
Any `verdict` member whose semantic edit does not refuse means the binding
lost a guard; the per-member test fails naming it.
