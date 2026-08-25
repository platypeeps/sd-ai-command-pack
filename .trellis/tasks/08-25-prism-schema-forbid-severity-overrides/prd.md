# Forbid severityOverrides in the shipped prism rules schema

## Problem

Release 0.71.48 retired `severityOverrides`. The review runner now *refuses* a
`.prism/rules.json` that carries the key: `_prism_rules()` returns a
`RulesDecision` with receipt status `refused`, and the rules file is not passed
to prism at all. The fleet rollout dropped the key from every consumer's
`rules.json` and from the schema's `required` list.

The schema still declares it a valid property. `templates/.prism/rules.schema.json`
lists `severityOverrides` under `properties`, so a consumer who hand-writes one
gets a file that validates cleanly and that the pack then refuses. Two
pack-owned artifacts disagree about the same key.

Copilot raised this independently on three consumer PRs during the 0.71.48
rollout — platypeeps/loadsmith#255, platypeeps/rwbp-website#276, and
platypeeps/rwbp-coordinator#264 — which is the signal that the contradiction is
legible from outside, not just to us.

## Why this was not fixed in the rollout

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

1. A `rules.json` containing `severityOverrides` fails schema validation.
2. The pack's own `.prism/rules.json` and all consumer copies still validate.
3. A test ties the schema's admitted keys to the runner's accepted keys, so the
   two cannot drift apart again without a failure.
4. The three Copilot threads cited above are answered by a shipped release, not
   only by this task's existence.
