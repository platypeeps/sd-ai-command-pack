# Retired Review-Body Guidance Removal Implementation Plan

## Execution Order

1. Replace placeholder context records with the applicable frontend adapter
   and backend quality specifications.
2. Remove the retired environment-variable bullet from the canonical shipped
   `sd-full-check` skill.
3. Extend `tests/test_review_scope.py` to scan every unique current shipped
   guidance source selected by manifest kind.
4. Bump the patch version, add the changelog entry, run generation/self-install,
   and refresh the Obsidian KB and fleet candidate ledger.
5. Run the focused review-scope tests, parity/release gates, and canonical full
   check before shipping.

## Validation

```bash
.venv/bin/python -m unittest tests.test_review_scope
.venv/bin/python -m unittest tests.test_generated_parity tests.test_pack_drift
make check
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py
```

## Completion Evidence

- Current manifest guidance sources contain no retired variable reference.
- Runtime retirement tests still prove the old variable is ignored.
- Canonical template and installed mirror remain byte-identical.
- Release, candidate-ledger, KB, and full-check gates pass.
