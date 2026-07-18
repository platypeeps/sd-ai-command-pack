# Design: SD Pack Source Identity Validation

## Existing Boundary

`sd_ai_command_pack_source_identity` is the single classifier shared by the
source-drift gate and source-hook advisory. Generic repository markers establish
only that the checkout is an installer-pack candidate. Parsed root manifest data
establishes SD ownership.

The current contract is:

- missing generic markers -> `absent`;
- valid manifest with another name -> `other`;
- valid `sd-ai-command-pack` manifest with required fields -> SD identity;
- malformed content that textually asserts the SD identity, or invalid required
  SD fields -> controlled failure;
- unavailable Python -> advisory skip with an explicit warning.

## Planned Change

No runtime change is expected because current `main` already implements the
requested ownership boundary. Strengthen the SE fixture assertions in
`tests/test_pack_drift.py` to pin the externally visible non-behavior: the
source-drift body must not print its environment-variable summary or any stale
documentation errors.

## Compatibility

The test-only change has no consumer payload or installer impact. Consumers on
pack `0.15.6` remain stale until refreshed through the normal installer. Pack
`0.16.1` and newer already contain the runtime fix.

## Rollback

The only planned codebase change outside Trellis planning files is additive
test coverage. Reverting those assertions restores the prior test precision
without changing shipped behavior.
