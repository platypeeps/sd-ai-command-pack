---
title: Forbid severityOverrides in the shipped prism rules schema
status: done
created: 2026-08-25
branch: task/prism-schema-forbid-severity-overrides
---
# Forbid severityOverrides in the shipped prism rules schema

## Problem

Release 0.71.48 retired `severityOverrides`. The review runner now *refuses* a
`.prism/rules.json` that carries the key: `_prism_rules()` returns a
`RulesDecision` with receipt status `refused`, and the rules file is not passed
to prism at all. The fleet rollout dropped the key from every consumer's
`rules.json` and from the schema's `required` list.

The schema still declared it a valid property. `templates/.prism/rules.schema.json`
listed `severityOverrides` under `properties`, so a consumer who hand-wrote one
got a file that validated cleanly and that the pack then refused. Two pack-owned
artifacts disagreed about the same key.

Copilot raised this independently on **four** consumer PRs during the 0.71.48
rollout — platypeeps/loadsmith#255, platypeeps/rwbp-website#276,
platypeeps/rwbp-coordinator#264, and platypeeps/hoa-manager#290 — which is the
signal that the contradiction is legible from outside, not just to us.

This PRD originally named three and omitted hoa-manager#290, which carries two
such threads; the 0.71.49 changelog says four. Reconciled 2026-08-25 by
enumerating Copilot-authored `severityOverrides` threads across every consumer
rollout PR rather than by trusting either count.

## Why this was not fixed in the rollout *at the time*

The failure is loud, not silent. A refused rules file produces a receipt record
naming the refusal; it never yields a review that is quietly wrong. Fixing it
properly means a patch release plus re-running the installer across all eight
consumer branches, which would have redone a rollout that was already green.
Deferred deliberately, with the threads resolved against this task.

## Requirements

1. Remove the `severityOverrides` property from
   `templates/.prism/rules.schema.json`. The root object already carries
   `"additionalProperties": false`, so deletion is what forbids it — no
   `"not"` clause is needed.
2. Confirm no consumer's `rules.json` carries the key before shipping, so the
   tightened schema cannot invalidate a file already in the fleet. The rollout
   verified this once; verify it again at release time rather than trusting the
   earlier check.
3. Ship as a patch release and propagate through the normal installer path, so
   consumers receive the schema from the pack rather than carrying a local edit.
4. The schema and the runner must be checked against each other, not just
   individually. A test that asserts the schema rejects a `severityOverrides`
   document is the cheap half; the half that matters is that the set of keys the
   schema admits and the set the runner accepts are the same set.

## Acceptance criteria

Shipped in **0.71.49** (`6cb0cf8b`, PR #539), with 0.71.50 (#540) restoring the
schema's authored formatting. Verified 2026-08-25.

- [x] A `rules.json` containing `severityOverrides` fails schema validation.
      — `templates/.prism/rules.schema.json` admits exactly
      `$schema`, `description`, `focus`, `required`, and carries
      `"additionalProperties": false`. Deletion plus that flag is what forbids
      the key; neither alone would.
- [x] The pack's own `.prism/rules.json` and all consumer copies still validate.
      — pack copy carries only the four admitted keys. Eight of nine consumers
      likewise (loadsmith, rwbp-website, rwbp-coordinator, hoa-manager,
      sd-github-review, people-profiles, anomaly-metric-creator,
      se-ai-command-pack). `mezmo_benchmark` has no `.prism/rules.json` at all,
      so it is not a prism-rules consumer rather than a violation. Checked
      against the repositories, not against the rollout's earlier check, which
      is what requirement 2 asked for.
- [x] A test ties the schema's admitted keys to the runner's accepted keys, so
      the two cannot drift apart again without a failure.
      — `test_the_shipped_schema_admits_no_key_the_runner_refuses` reads both
      sides from their files rather than from literals, asserts the
      intersection with `REFUSED_RULES_KEYS` is empty, and separately pins
      `additionalProperties is False` so the deletion cannot decay into the key
      merely being undescribed. Paired with
      `test_every_refused_key_carries_its_own_receipt_reason`.
      `Ran 6 tests / OK`.
- [x] The Copilot threads cited above are answered by a shipped release, not
      only by this task's existence.
      — all four PRs MERGED with zero unresolved threads: loadsmith#255,
      rwbp-website#276, rwbp-coordinator#264, hoa-manager#290.
