# Design: journal validation consistency

## Boundaries

The change has two defensive layers that solve one lifecycle defect:

1. `templates/scripts/sd-ai-command-pack-review-preflight.mjs` detects the
   contradiction in completed Trellis journal records.
2. `templates/.agents/skills/sd-review-pr/SKILL.md` routes non-deferred
   finish-work through `sd-finish-work`, which already owns the safe recorder.

Root dogfood copies and platform adapters are generated mirrors and must not be
edited as independent sources.

## Preflight Contract

Journal parsing remains section-aware. For each completed session:

- read only Summary and Main Changes when looking for a positive validation
  claim;
- read Testing when looking for the two exact Trellis fallback forms;
- fail only when both predicates are true;
- point the diagnostic at the fallback line in Testing.

Positive validation claims use a narrow, case-insensitive vocabulary pairing
a success verb/state (for example passed, verified, validated, green, or
successful) with a validation surface (for example quality gate, full check,
tests, lint, typecheck, build, CI, CodeQL, Playwright, or validation). Explicit
negation/failure/skip wording is excluded. Existing legacy placeholder checks
remain unchanged.

## Lifecycle Routing

`sd-review-pr` keeps ownership of the decision to finish or defer. When it
finishes locally, it resolves `sd-finish-work` by the same trusted installed
skill mechanism used elsewhere in the pack and executes that wrapper. The
wrapper then:

- resolves `trellis-finish-work`;
- follows Trellis archive/dirty-state rules;
- replaces direct `add_session.py` use with
  `sd-ai-command-pack-record-session.py` at journal time.

Deferred `sd-ship` and `sd-fleet-refresh` flows do not invoke the wrapper in
Step 8. Already-merged routing still finishes first and then runs housekeeping.

## Compatibility And Rollout

This is a compatible patch release. No command name, argument, environment
variable, or generated state format changes. Consumers receive the updated
preflight and skill payload through the normal installer/fleet refresh.

Rollback is a normal revert of the patch release. The preflight has no write
side effects, and the routing change delegates to an already shipped wrapper.

## Validation Strategy

- Unit fixtures for contradiction detection and negative boundaries in
  `tests/test_review_preflight.py`.
- Skill-contract assertions in `tests/test_sdlc_commands.py`.
- Existing record-session and generated-parity suites.
- `make sync`, full fleet candidate validation, and `make check`.
