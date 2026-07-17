# Fix false-positive SD pack source detection

## Goal

Prevent generic installer repositories such as `se-ai-command-pack` from
running source-only `sd-ai-command-pack` drift and hook checks while preserving
strict behavior in the actual SD pack source checkout.

## Requirements

- Define one reusable shell classifier in the canonical full-check script and
  its shipped template twin.
- Treat `manifest.json` field `name == "sd-ai-command-pack"` as the
  authoritative source identity. The presence of `install.py`,
  `manifest.json`, and `templates/` is not sufficient by itself.
- Skip SD-specific drift gates and source-hook warnings for valid manifests
  whose name is another pack, including `se-ai-command-pack`.
- Fail with a controlled, traceback-free diagnostic when a manifest text
  asserts the SD pack name but cannot be parsed, or when a parsed SD manifest
  lacks the minimum `version` string or `files` list required by the gate.
- Preserve the explicit `SD_AI_COMMAND_PACK_FULL_CHECK_PACK_DRIFT=0` override
  and the existing SD drift-gate behavior and exit codes after identity passes.
- Keep source/template copies byte-identical and document the identity contract.
- Add focused true-positive, false-positive, malformed-identity, and source-hook
  regression coverage.
- Keep this change in the already unreleased `0.16.1` payload and refresh its
  changelog, provenance, knowledge base, and fleet candidate evidence.

## Acceptance Criteria

- [x] A real SD source fixture runs the pack drift gate.
- [x] An SE-shaped installer fixture skips all SD source-only assumptions.
- [x] Malformed JSON that asserts `sd-ai-command-pack` fails conservatively
  without a traceback.
- [x] A parsed SD manifest with malformed required identity fields fails with a
  controlled diagnostic.
- [x] The source-hook warning uses the same identity classifier.
- [x] Script/template parity, focused regressions, and canonical checks pass.
- [x] Distributed docs/specs and `0.16.1` release evidence are current.

## Notes

- Do not modify `se-ai-command-pack`; it is a consumer-shaped regression case,
  not the owner of this detection policy.
- Do not add a second marker file when the existing manifest already carries an
  explicit pack name.
