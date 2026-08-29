# Implementation plan: task metadata provenance validation

## Activation

1. Validate this task, activate it through Trellis, and load the backend
   quality and manifest/filesystem contracts.
2. Confirm the branch targets `main` and the working tree contains only this
   task's planning artifacts.

## Test-first coverage

3. Extend helper-level assertions in `tests/test_review_preflight.py` for
   absent, valid, malformed, partial, invalid, same-priority, empty, and
   oversized provenance.
4. Add executable fixtures for valid and invalid changed task records.
5. Add real-Git fixtures proving archived later-deleted path references pass
   while active PRD references fail.

## Canonical implementation

6. Add bounded priority constants and a pure provenance validator to
   `templates/scripts/sd-ai-command-pack-review-preflight.mjs`.
7. Compose its issues into `validateTrellisTaskMetadata()` without changing
   unrelated task behavior or diagnostics.
8. Update `.trellis/spec/backend/quality-guidelines.md` with the signature,
   contract, matrix, cases, tests, and wrong/correct example.

## Payload synchronization

9. Bump `manifest.json` to `0.32.0` and add the matching top `CHANGELOG.md`
   entry.
10. Run `make sync` to regenerate the root mirror, manifest/provenance hashes,
    installed adapters, and Obsidian KB.
11. Regenerate `docs/fleet/candidate-validation.json` with the full fleet
    candidate validator after the payload is final.

## Validation

12. Run:

    ```bash
    node --check templates/scripts/sd-ai-command-pack-review-preflight.mjs
    bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
      -m unittest tests.test_review_preflight
    cmp templates/scripts/sd-ai-command-pack-review-preflight.mjs scripts/sd-ai-command-pack-review-preflight.mjs
    make check
    ```

13. Run `trellis-check`, capture any durable spec learning, and commit the
    focused release payload.
