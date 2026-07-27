# Correct 0.55.0 consumer compatibility blockers

## Goal

Fix the released housekeeping-result UTF-8 policy defect and validate consumer integration contracts before issuing one corrective sd-ai-command-pack release.

## Requirements

- Add an explicit `errors="strict"` policy to the JSON input read in
  `templates/scripts/sd-ai-command-pack-housekeeping-result.py`, and keep the
  installed source-checkout mirror byte-identical.
- Add focused regression coverage proving valid UTF-8 still composes typed
  housekeeping results and malformed UTF-8 is rejected through the existing
  safe input-error path.
- Sweep equivalent managed JSON-input readers and generated/template mirrors
  for the same omitted decode-policy contract; record why adjacent surfaces
  are either changed or excluded.
- Re-run the canonical full-fleet candidate validation, with Mezmo included,
  before selecting and publishing exactly one corrective release.
- Preserve the active `refresh-v0-55-0-20260727T005724Z` evidence. Do not
  mutate additional consumer lanes or merge the unsettled rwbp-website PR
  while the controller reports a pack blocker.
- Capture consumer-owned full-gate incompatibilities separately rather than
  weakening their tests or patching immutable installed payloads in place.

## Acceptance Criteria

- [ ] The housekeeping-result helper pins UTF-8 strict decoding in the
  template and synchronized installed mirror.
- [ ] Focused tests cover valid and malformed UTF-8 input, and the pack's
  canonical checks pass.
- [ ] The contract-surface sweep is documented and finds no unaddressed
  equivalent released helper defect.
- [ ] One corrective release passes canonical full-fleet candidate validation,
  including the Mezmo consumer that exposed the blocker.
- [ ] The original rollout task can resume from fresh immutable release and
  controller preflight evidence without losing the 0.55.0 campaign history.

## Notes

- Fleet campaign: `refresh-v0-55-0-20260727T005724Z`.
- Blocked consumer: `answerbook/mezmo_benchmark`, local-check action
  `fc589f1c1f4df240d2b129290f6202549027763b7e1978874b277daedabc2a31`.
- Required gate evidence: `uv run --extra test pytest` reported 4,554 passed,
  9 skipped, and 14 failed. The pack-owned blocker is Mezmo's production-tree
  defect-pattern test against managed
  `scripts/sd-ai-command-pack-housekeeping-result.py:45`.
- The finding classifier owner is `MEZMO-055-UTF8`, compatibility family,
  disposition `block-corrective-release`, dedupe key
  `sha256:9ad986d4d88e4e33b700ae93cbe9ebd2cae5769f4b3347609e488e118653e1e7`.
- Contract-surface sweep: every other managed Python `Path.read_text` call
  under `templates/scripts/` already declares an explicit error policy. The
  source-only fleet preflight provenance reader had the same syntactic gap and
  is corrected in the same change; its existing `UnicodeError` fallback keeps
  behavior unchanged. Non-JSON text readers and test-only fixture reads are
  excluded because they are not equivalent managed JSON input boundaries.

## Finding Ledger

| ID | Contract family | Evidence | Severity | Disposition | Fix | Regression |
| --- | --- | --- | --- | --- | --- | --- |
| MEZMO-055-UTF8 | compatibility | Mezmo's required full test gate rejects the immutable managed helper because line 45 omits an explicit decode error policy. | blocker | block-corrective-release | Pin `errors="strict"` in template and mirror. | Valid JSON succeeds; malformed UTF-8 follows the typed input-error path. |
