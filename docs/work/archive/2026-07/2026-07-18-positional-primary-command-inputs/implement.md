# Positional Primary Inputs Implementation Plan

## Execution Order

1. Review this planning package and start the task when it becomes the selected
   implementation stream.
2. Add focused tests that encode the shared parsing order and all five command
   mappings before changing the skill contracts.
3. Update the template `sd-retro` skill to accept one bare topic phrase and
   reject bare/explicit duplication; synchronize its root mirror.
4. Update the template `sd-test-gaps` skill to accept one bare target path with
   existing coverage-path validation; synchronize its root mirror.
5. Update the template `sd-fleet-refresh` skill to accept validated bare
   consumer names, preserve flags, fail closed on unknowns, and report the
   normalized target before mutation; synchronize its root mirror.
6. Update the template `sd-audit-repo` skill to accept exact bare charter names,
   preserve `depth=`/`follow-up`, and fail closed before reviewer dispatch;
   synchronize its root mirror.
7. Extend the template/root status Python parser and skill so the existing
   `fleet` positional remains reserved and one other positional maps to
   `--repo` with conflict validation.
8. Verify every generated platform adapter forwards raw arguments. Regenerate
   or update only adapters that do not satisfy that thin-wrapper contract.
9. Update `sd-help` catalog/examples, the distributed guide, README usage, and
   adapter guidance with the primary-subject rule and concrete examples.
10. Bump release metadata and changelog according to the shipped-payload
    contract.
11. Run focused tests, `git diff --check`, template/root parity, installer and
    documentation suites, and the canonical full check.

## Validation Plan

- `sd-retro`: bare phrase, explicit topic, mixed rejection, unknown option key.
- `sd-test-gaps`: bare file, quoted path, explicit file, missing coverage path,
  mixed rejection, and `max-gaps=` interaction.
- `sd-fleet-refresh`: one/many/comma-separated consumers, de-duplication,
  explicit form, flags, unknown consumer, typoed flag, and mixed rejection.
- `sd-audit-repo`: one/many/comma-separated dimensions, de-duplication,
  explicit form, depth, follow-up conflict, unknown charter, and typoed option.
- `sd-status`: current repo, `fleet`, positional path, `--repo`, quoted path,
  path/flag combinations, positional/explicit conflict, and extra positional
  rejection.
- Existing no-argument and explicit-form tests remain green.

## Documentation And Spec Updates

- Add a concise adapter guideline: positional values identify primary subjects;
  behavior and safety controls stay explicit.
- Update command help so positional and explicit forms appear together and
  clearly state conflict/error behavior.
- Add examples for each command to `sd-help` and the distributed pack guide.
- Record the additive invocation behavior in the changelog and release ledger.

## Review Notes

- Pay special attention to fail-closed behavior for fleet and audit filters.
- Confirm adapters preserve raw text without shell evaluation.
- Ensure explicit forms remain fully supported and no existing safety option is
  silently reclassified.
- Keep this task separate from autonomous work-loop state and lifecycle changes.

## Follow-Ups

- Reassess other commands only when they acquire a single obvious primary
  subject. Do not generalize positional parsing to lifecycle controls.
