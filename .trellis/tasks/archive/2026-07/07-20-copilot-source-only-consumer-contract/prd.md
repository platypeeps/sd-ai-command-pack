# Teach Copilot the source-only consumer contract

## Goal

Prevent Copilot from treating source-only SD fleet helpers and their
operator-facing documentation as missing consumer payload.

## Requirements

- Extend the canonical managed Copilot guidance template, not a consumer-only
  copy.
- Explain that `SOURCE_ONLY_ALLOWED_PACK_FILES` permits pack-like files in the
  source checkout and does not define required consumer targets.
- Require reviewers to use the consumer manifest, installed-target receipt,
  provenance, and install audit before reporting a missing payload file.
- Preserve source-workflow documentation in consumer guides when its section
  explicitly identifies the command or workflow as source-only.
- Keep the instruction concise and evidence-oriented so Copilot can apply it
  during pack-refresh reviews.

## Acceptance Criteria

- [ ] The managed Copilot template states the source-only allowlist contract.
- [ ] The guidance gives a concrete pre-comment verification sequence.
- [ ] The guidance permits explicitly scoped source-workflow documentation in
      consumer repositories.
- [ ] Focused tests pin the instruction text and prove a consumer audit does
      not require source-only fleet files.
- [ ] The tracked upstream Copilot instructions remain synchronized with the
      managed template.
- [ ] Focused tests, the full unittest suite, and whitespace checks pass.

## Notes

- This is a lightweight prompt-and-test regression; no new manifest target or
  consumer runtime behavior is required.
