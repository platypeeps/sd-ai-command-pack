# Implementation Plan: Discoverable sd-help command

## Preconditions

- Keep this work separate from PR #146.
- Before final release metadata and fleet evidence, reconcile with current
  `main` and select the next available minor version. Expect `0.18.0` if PR
  #146's `0.17.0` release lands first.
- Treat `templates/**` as the shipped source of truth and root platform files as
  self-installed mirrors.

## Implementation Checklist

1. Add registry and generator tests for the shared SD/SE-style catalog model.
   - Introduce family metadata while preserving derived `COMMAND_NAMES`
     compatibility and manifest order.
   - Assert valid family membership, duplicate/unknown rejection, source-only
     policy, and reference-consumer validation.
   - Assert deterministic catalog rendering from family metadata, canonical
     frontmatter, source-only policy, and manifest version.
   - Assert Markdown escaping, generated markers, `--check` drift detection,
     atomic prevalidation, shared-reference fanout, and temp-path isolation.
2. Add focused failing tests for the `sd-help` interaction contract.
   - Assert the canonical skill frontmatter and read-only safety rules.
   - Assert list, explain, compare, recommend, examples, and tour modes plus
     optional explicit keys and compact/standard detail.
   - Assert available, bundled-but-not-discoverable, source-only, and
     unknown/external labels.
   - Assert smallest-fit behavior, one-question maximum, three-stage chain cap,
     named handoffs, command-form normalization, aliases, unique misspellings,
     ambiguity, and malformed/duplicate discovery behavior.
   - Assert source-only `sd-fleet-refresh` labeling and honest external fallback.
   - Validate every command named in authored examples against the registry.
   - Extend install/parity expected-path coverage for the shared skill and
     active platform adapters plus both references.
3. Add the canonical command sources.
   - Create `templates/.agents/skills/sd-help/SKILL.md` with the discovery,
     query, output, failure, and no-execution contracts from `design.md`.
   - Create `templates/.agents/skills/sd-help/references/examples.md` with
     realistic family prompts, overlap comparisons, onboarding, and bounded
     multi-stage handoffs.
   - Create `templates/.commands/sd-help.md` as a thin resolver wrapper that
     passes the user's help query through and never runs a selected workflow.
   - Register `sd-help` in the canonical command/family model and derive
     `COMMAND_NAMES` for compatibility.
4. Extend and run generation.
   - Generate
     `templates/.agents/skills/sd-help/references/command-catalog.md` and its
     manifest fanout from the same registry/frontmatter model.
   - Run `make generate`.
   - Review generated catalog, Claude, Gemini, GitHub, and `manifest.json`
     changes.
   - Confirm `sd-fleet-refresh` remains the sole source-only command.
5. Update user documentation.
   - Add `sd-help` to README command navigation and examples.
   - Add it to `templates/docs/SD_AI_COMMAND_PACK.md` command inventories,
     native invocation blocks, workflow guidance, and targeted examples.
   - Let self-install refresh `docs/SD_AI_COMMAND_PACK.md` from its template.
6. Complete release metadata only after the branch is based on the intended
   predecessor release.
   - Reconcile current `main` without rewriting unrelated history.
   - Bump `manifest.json` to the next available minor version and add the top
     `CHANGELOG.md` entry.
   - Run full-fleet candidate validation and commit the refreshed
     `docs/fleet/candidate-validation.json` evidence.
7. Refresh dogfood and generated knowledge.
   - Run `make sync` to install the final manifest into this checkout, refresh
     root skill/platform mirrors and provenance, and update `.obsidian-kb/`.
   - Verify template/root twins and installed-target receipts.
8. Validate the complete change.
   - Run the focused help, surface-generation, parity, and installer tests.
   - Run `make check` with the repository-selected Python/toolchain.
   - Run the deterministic full check with Prism and Gito disabled.
   - Run `git diff --check` and inspect the final payload/release diff.

## Validation Commands

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  -m unittest tests.test_help_command tests.test_surface_generation \
  tests.test_generated_parity tests.test_install_core tests.test_registry
make generate
make sync
make check
SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 \
SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 \
bash scripts/sd-ai-command-pack-full-check.sh
git diff --check
```

## Review Gates

- The generated help catalog contains only registry-owned released or
  source-only commands; runtime output separately reports what is discoverable
  in the current repository/session.
- The bundled catalog and runtime discovery are reported separately; pack-owned
  availability is never inferred from an `sd-` prefix alone.
- Every current registry command appears in exactly one help family, and
  generated descriptions come from canonical skill frontmatter.
- Help never executes, delegates, mutates, or creates tasks.
- Recommendations prefer one smallest-fit command, cap chains at three stages,
  and identify handoffs; examples remain registry-valid.
- Adapter bodies remain thin and generated surfaces pass `--check`.
- The manifest version, changelog, candidate ledger, installed metadata,
  provenance, and KB describe the same final payload.
- PR #146 and this feature remain independently reviewable; resolve release
  ordering before this feature is merged.

## Rollback Points

- Before generation: remove the registry row and two canonical template files.
- After generation: remove the row/templates and rerun `make generate` rather
  than deleting generated adapter entries manually.
- After release metadata: revert the complete payload release commit; do not
  hand-edit consumer receipts.
