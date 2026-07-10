# Verify Remote Reviewer Requests Actually Materialize Implementation Plan

## Execution Order

1. Add failing focused assertions for the documented identities:
   `@copilot` for the default CLI request and
   `copilot-pull-request-reviewer[bot]` for author matching.
2. Add fixture coverage for four request adapters: default Copilot CLI,
   generic GitHub reviewer, custom request command, and any explicit Copilot
   REST mode retained by the implementation.
3. Add state-machine fixtures for pending, materialized-clean,
   materialized-actionable, late inline comments, command rejection, and
   accepted-with-no-materialization.
4. Update the template `sd-review-pr` skill first. Separate request identity,
   author identity, request result, and materialization evidence; remove the
   bare Copilot slug and the request-disappeared-is-complete rule.
5. Update docs, adapter summaries where necessary, environment-variable
   descriptions, and troubleshooting guidance.
6. Bump the manifest version and changelog because this changes shipped review
   behavior.
7. Run `python3 install.py . --force` through the supported project
   interpreter so the root skill and provenance match the template source.
8. Refresh the KB and run focused tests before the deterministic full-check.

## Validation Commands

Use the repository-managed environment rather than raw macOS `python3`:

```bash
make setup                         # only when .venv is absent or stale
.venv/bin/python -m unittest tests.test_review_scope
.venv/bin/python -m unittest tests.test_install_core
python3 scripts/sd-ai-command-pack-update-spec-kb.py
SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 \
SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 \
bash scripts/sd-ai-command-pack-full-check.sh
```

Also validate a real PR request when Copilot code review is enabled:

```bash
gh pr edit <pr-number> --add-reviewer @copilot
```

Record the trigger timestamp/head and confirm author-matched review activity;
do not treat command exit `0` alone as success.

## Rollback Points

- If `@copilot` is unavailable because repository policy disables Copilot code
  review, preserve the deterministic local gate and report the policy blocker;
  do not fall back to the undocumented bare slug.
- If state-machine instructions prove too complex for reliable skill execution,
  stop and split an executable polling helper with fixture tests rather than
  adding more pseudo-code to the skill.

## Completion Checklist

- [ ] Focused fixtures fail before and pass after the skill change.
- [ ] Template source and root mirror are byte-identical.
- [ ] README/docs contain only documented Copilot identifiers.
- [ ] Existing custom-provider behavior remains covered.
- [ ] Version, changelog, manifest, and provenance are synchronized.
- [ ] KB freshness, install audit, and deterministic full-check pass.
