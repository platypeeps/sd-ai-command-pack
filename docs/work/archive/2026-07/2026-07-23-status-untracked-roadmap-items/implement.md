# Implementation plan: Untracked roadmap follow-ups

1. Add failing status fixtures for roadmap-like source discovery, unchecked
   and unmarked item extraction, indentation/completion exclusions, stable
   source evidence, duplicate items, Trellis ID/path/title deduplication, and
   ignored/symlinked/oversized sources.
2. Remove task-backed roadmap construction from the canonical status template
   and add bounded roadmap-source discovery and parsing helpers.
3. Merge unmatched roadmap candidates into the existing follow-up candidate
   pipeline as `kind=roadmap`, preserving existing precedence and deterministic
   `F-*` assignment.
4. Remove separate Roadmap rendering/JSON assertions, advance the status schema
   and housekeeping status-input boundary together, and preserve complete
   Tasks, empty Follow-ups behavior, fleet nesting, strict housekeeping, and
   compatibility Next Steps.
5. Update the canonical `sd-status` skill, installed guide, frontend status
   contract, and focused parity/housekeeping tests. Keep platform adapters thin.
6. Bump the pack minor version, add the matching changelog entry, run
   `make sync`, and inspect template/root parity and generated knowledge.
7. Run focused unit/parity/housekeeping tests, Ruff, mypy where applicable,
   `git diff --check`, and review preflight.
8. Refresh the full exact-payload fleet candidate ledger, run `make check`,
   review the final diff, and complete the normal Trellis archive/journal
   lifecycle.

## Validation commands

```bash
.venv/bin/python -m unittest \
  tests.test_status tests.test_sdlc_commands \
  tests.test_generated_parity tests.test_housekeeping
.venv/bin/ruff check \
  templates/scripts/sd-ai-command-pack-status.py \
  scripts/sd-ai-command-pack-status.py tests/test_status.py
make sync
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py
make check
```

## Stop and rollback points

- Stop if deterministic matching would require fuzzy inference; surface the
  unmatched item instead.
- Stop if bounded scanning cannot distinguish ignored/generated paths without
  mutation or unsafe traversal.
- Keep the prior release installable as rollback; do not publish a partial
  collector/skill/version update.
