---
title: Report the thin revert's disable marker instead of leaving it to wedge a re-conversion
status: planning
created: 2026-08-16
---
# Report the thin revert's disable marker instead of leaving it to wedge a re-conversion

## Goal

Make a re-conversion that aborts on the marker `--revert-thin` wrote say so.
Today it reports a settings collision with no indication that the pack itself
authored the value it is refusing.

## Background

Reverting a thin consumer back to fat does not simply undo the conversion's
settings edit. It replaces it with a positive disable marker
(`installer/thin.py:1265`):

```python
            if is_marker_key:
                container[name] = False
                marker_written = True
```

That is deliberate and correct. A reverted consumer has the vendored payload
back, so the plugin must not also run beside it; leaving the key absent would
let a machine-level enable do exactly that. The note at
`installer/thin.py:1285` shows the same concern from the other direction.

The cost lands on the next conversion. `plan_settings_merge` blocks rather than
overwrites on every collision — the file is consumer-owned, and there is no way
to tell a deliberate `false` from a stale one — so `install.py TARGET --thin`
aborts at `installer/thin.py:316`:

```text
.claude/settings.json: enabledPlugins['sd@sd-ai-command-pack'] is already set
to false, which is not true
```

Observed during the loadsmith revert rehearsal. Both halves are behaving as
designed; the failure is that the operator is given a bare collision and has to
already know that `--revert-thin` is what wrote the `false`. The fix — remove
the key so the conversion re-creates and re-owns it — is not discoverable from
the message, and setting it to `true` instead is the wrong repair, because then
the conversion finds an equal value, records nothing, and a later revert has no
addition to undo.

## Requirements

1. When the blocking value at the plugin marker key is exactly `false`, the
   diagnostic must name `--revert-thin` as the likely author and name removing
   the key as the resolution.
2. Do not narrow the block itself. The collision must still stop the
   conversion; this changes what the operator is told, not what is allowed.
   Auto-clearing a `false` the pack cannot prove it wrote is the outcome this
   requirement exists to prevent.
3. Do not special-case any key other than the plugin marker. A `false` at an
   unrelated key carries none of this history and must keep the generic
   message.
4. Say to remove the key, not to set it to `true`. A pre-existing `true` is
   equal to the value the conversion wants, so nothing is recorded as an
   addition, and the revert that follows finds nothing to undo.

## Acceptance criteria

- [ ] A conversion against a consumer whose settings carry the marker key set
      to `false` reports a message naming `--revert-thin` and the removal
      remedy, and still exits nonzero without writing.
- [ ] A conversion against a consumer whose settings carry some other key at a
      colliding value reports the current generic message unchanged.
- [ ] A revert followed by a key removal followed by a conversion succeeds and
      records the marker as an addition, so a second revert can undo it. The
      round trip is the criterion; the message alone is not.
- [ ] The existing revert behaviour is untouched: `--revert-thin` still writes
      `false` rather than deleting the key.

## Notes

The loadsmith rehearsal is the only observation so far, and it was resolved by
hand. Nothing is currently broken in the fleet — all eight consumers are thin
and none carry a stale marker. This is a diagnostic debt that will be paid by
whoever next reverts and re-converts, which is exactly the person least likely
to have this context.
