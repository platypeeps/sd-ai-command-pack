# Auto-add generated scope to sd-create-pr PR bodies — Implementation Plan

1. Inspect the current `sd-create-pr` Step 5 flow and the existing PR-body
   classifier APIs; choose the smallest reusable interface that can prove a
   branch is tooling/generated-only without duplicating path rules.
2. Add focused classifier/composition tests first for bookkeeping-only,
   mixed-scope, custom-body, missing-classifier, and temporary-file cases.
3. Implement the helper or classifier extension in `templates/scripts/` first,
   then synchronize the root script and manifest/install provenance as needed.
4. Update the template `sd-create-pr` skill so the no-custom-body publication
   path preserves fill content, adds the recognized section when eligible, and
   stops before review if compliant body materialization fails.
5. Synchronize installed skill/platform mirrors and update contract tests for
   standalone and verified `sd-ship` Stage 1 ownership.
6. Update the frontend adapter spec and user-facing docs with the automatic
   bookkeeping-only behavior and the unchanged custom-body contract.
7. Run focused tests, generated parity/install audit, `make check`, and the
   command-pack full-check. Verify no generated Markdown is passed through an
   inline shell `--body` argument.
8. Review the final diff for one authoritative classifier, template-first
   ownership, and no public orchestration controls added.

## Validation Commands

```bash
python3 -m unittest tests.test_pr_body_scope tests.test_sdlc_commands
python3 -m unittest tests.test_install_core tests.test_generated_parity
make check
bash scripts/sd-ai-command-pack-full-check.sh
```

## Rollback Point

Keep classifier/helper work and orchestration changes reviewable as separate
commits when practical. If composition proves unsafe or cannot preserve fill
content, revert the orchestration commit while retaining any independently
useful classifier tests.
