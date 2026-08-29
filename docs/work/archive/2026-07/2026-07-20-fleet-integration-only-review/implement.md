# Fleet integration-only review implementation plan

## Implementation steps

1. Add focused classifier tests using real temporary consumer Git histories
   and controlled release/inspection seams. Cover a qualifying pure refresh,
   retired managed targets, consumer-owned changes, dirty trees, invalid or
   unsafe base receipts, non-ancestor bases, stale release evidence, audit or
   provenance failure, and deterministic JSON.
2. Implement the source-only classifier with bounded Git and installer
   inspection subprocesses, safe exact-commit receipt parsing, rename-disabled
   diff collection, and schema-versioned human/JSON output.
3. Register the classifier as an allowed source-only fleet file in install
   audit policy so it is never mistaken for leaked consumer payload.
4. Update the canonical `sd-fleet-refresh` skill template to add
   `remote-review`, capture the exact base/head evidence, run classification,
   and delegate review/watch/housekeeping without requesting a remote reviewer
   for eligible branches.
5. Update the canonical `sd-review-pr` skill template with the trusted
   fleet-only profile, head-bound classifier recheck, fail-closed fallback, zero
   remote-round report, and unchanged thread/CI/learning/finish-work gates.
6. Synchronize root mirrors and update `docs/FLEET_ROLLOUT.md`, the detailed
   guide, README command help, and generated command catalog.
7. Bump the pack patch version and changelog because the shipped review skill
   and guide change. Run `make sync` after template and release bytes settle.
8. Run focused classifier, SDLC command, install-audit, generated-parity, and
   release-ledger tests. Exercise the classifier against a disposable
   installer-managed consumer fixture.
9. Regenerate the canonical full-fleet candidate ledger for the final payload,
   then run `make check` and the deterministic PR review gate before shipping.

## Primary files

- `scripts/sd-ai-command-pack-fleet-review-classify.py`
- `tests/test_fleet_review_classify.py`
- `templates/.agents/skills/sd-fleet-refresh/SKILL.md`
- `.agents/skills/sd-fleet-refresh/SKILL.md`
- `templates/.agents/skills/sd-review-pr/SKILL.md`
- `.agents/skills/sd-review-pr/SKILL.md`
- `scripts/sd-ai-command-pack-install-audit.py`
- `.github/scripts/check-shipped-script-coverage.sh`
- `tests/test_install_audit.py`
- `tests/test_sdlc_commands.py`
- `docs/FLEET_ROLLOUT.md`
- `templates/docs/SD_AI_COMMAND_PACK.md`
- `docs/SD_AI_COMMAND_PACK.md`
- `README.md`
- `manifest.json`
- `CHANGELOG.md`
- `docs/fleet/candidate-validation.json`

## Validation commands

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest \
  tests.test_fleet_review_classify tests.test_sdlc_commands \
  tests.test_install_audit tests.test_generated_parity tests.test_release_ledger

make sync

bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py

make check
```

## Risks and rollback

- Risk: an allowlist mistake suppresses remote review for consumer-owned work.
  Mitigation: require safe base and current receipts, disable rename collapsing,
  bind classification to the exact head, and fall back on every ambiguity.
- Risk: a valid retired pack target is misclassified. Mitigation: union the
  exact base receipt with the current receipt and cover deletion fixtures.
- Risk: review orchestration skips non-remote gates. Mitigation: keep the
  profile inside `sd-review-pr` and alter only the remote-request decision.
- Risk: source-only classifier leaks into consumers. Mitigation: keep it out of
  the install manifest and add install-audit source-only regression coverage.
- Rollback is a normal revert of the classifier, skill/profile text, docs,
  mirrors, release metadata, and tests; no consumer state schema changes.
