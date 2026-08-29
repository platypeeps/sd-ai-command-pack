# Design: registry-driven command surface lint

## Registry

Extend or normalize the existing generator data into one validated model:

- live command ID and public name;
- canonical skill/template path;
- generated platform target families;
- capability metadata;
- help/completion visibility;
- live configuration keys; and
- retired identifiers/paths with removal version and owning task.

Other tasks update this model instead of maintaining independent name lists.

## Scan Domains

The linter scans known live roots and file types. It excludes generated cache,
vendor/build output, and archived task history by policy. Explicit migration and
retirement fixtures are scanned but matched against contextual allowances.

## Finding Categories

- `retired_identifier_live`;
- `live_identifier_missing_target`;
- `unregistered_public_target`;
- `stale_configuration_key`;
- `generated_registry_mismatch`; and
- `invalid_allowance`.

Text matches are token/boundary aware so substrings do not create avoidable
noise. Structured files are parsed where practical.

## Integration

Run the linter after generation/parity and before the candidate ledger/release
gate. JSON output supports focused diagnostics; human output is concise.

## Rollback

If false positives block rollout, narrow the scanner or add a reasoned
contextual allowance. Do not disable retired-identifier validation globally.
