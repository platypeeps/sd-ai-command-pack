# Clarify fleet PR audit scope for Trellis adapters

## Goal

Clarify fleet rollout PR guidance so pack-owned receipt and provenance coverage is distinguished from Trellis-owned shared adapter validation.

## Requirements

- Update the fleet rollout PR guidance/template to distinguish the pack-owned
  targets covered by `installed-targets.txt` and `provenance.json` from
  Trellis-owned platform adapters that become newly tracked because of an
  ignore-policy change.
- Require the PR verification summary to state which checks validate each
  ownership class instead of describing every generated surface as covered by
  the pack install audit.
- Preserve the existing immutable-release, tooling/generated-scope, and
  consumer-gate evidence required by `sd-fleet-refresh`.
- Add focused tests or fixtures that prevent generated rollout guidance from
  implying that Trellis-owned files belong in pack provenance.
- Do not add Trellis-owned files to the pack manifest or provenance merely to
  simplify review wording.

## Acceptance Criteria

- [ ] Fleet-generated PR guidance explicitly says that the install audit
      vouches pack-owned receipt targets only.
- [ ] When Trellis-owned adapters are newly tracked, the PR guidance identifies
      their owner and the separate integration/readiness checks that cover them.
- [ ] Tests cover a rollout that exposes previously ignored Claude/Trellis
      adapters without adding those files to pack receipts or provenance.
- [ ] Existing tooling/generated scope recognition and immutable release
      evidence continue to pass.

## Notes

- Recovered from the preserved pre-PR-262 task-draft stash.
- Originating evidence: the deferred documentation finding in loadsmith PR
  #171, where rollout continued after the consumer PR description was
  clarified and the addressed review thread was resolved.
- Lightweight task; PRD-only is appropriate. Classified 2026-07-28: the deliverable is
  generated rollout-PR guidance wording plus a fixture proving the wording holds when
  previously ignored Trellis-owned adapters become tracked. The ownership boundary that
  would otherwise need designing is already fixed by the last requirement — Trellis-owned
  files do not enter pack manifest or provenance — so no new contract is being defined.
