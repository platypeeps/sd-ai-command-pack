# Stop the map guard passing silently when the structure section is absent

Found by Copilot review on `platypeeps/rwbp-coordinator` PR #225 during the
0.71.6 fleet rollout — a genuine hole in the guard shipped by 0.71.6 itself.

## Problem

`parseGeneratedStructuralMapEntries` returns `{entries: [], parsed: true,
reason: 'no directory-structure section'}` when the map carries no
`# Directory Structure` heading. `checkGeneratedStructuralMapPaths` warns only
when `parsed` is false, and ignores `reason` entirely, so that case falls
through to the success path and reports `checked 0 generated structural map
.trellis/ path(s); all resolve`.

The consequence is the failure mode the guard exists to prevent, one level up:
if repomix changes its output heading, every consumer's guard silently
validates nothing while still printing PASS. Nothing distinguishes "this
repository has no map to check" (correct pass, no file) from "this map's
format is no longer one we can read" (should be loud).

## Goal

A configured map file that exists but yields no parseable
`# Directory Structure` section must not pass silently.

## Requirements

- A map file that exists but has no directory-structure section reports a
  warning naming the file and the reason, not a bare pass.
- The existing genuine passes stay passes: no configured map present, and a
  map whose section parses with all `.trellis/` paths resolving.
- The success message distinguishes zero checked paths from a nonzero count,
  so `checked 0` is never phrased as a validation that happened.
- Decide explicitly whether an existing-but-sectionless map is `warn` or
  `fail`. Recommendation: `warn`, matching the unparseable-indentation case —
  a format change is a pack-side defect, not consumer drift, and failing every
  consumer's gate on it converts an upstream mistake into a fleet-wide outage.

## Second drift case: fence lines carrying an info string

Found by Copilot review on `platypeeps/sd-github-review` PR #79 during the
same rollout, in the same function.

The parser skips a fence line only when it matches ``/^\s*`{3,}\s*$/`` — bare
backticks and nothing else. Repomix currently opens the listing with a bare
four-backtick fence, so no map is misparsed today. If the generator ever emits
```` ```text ```` or a tilde fence, the fence line is taken as a tree entry and
reported as a `.trellis/` path that does not resolve.

That failure is loud, not silent, so it is a lower-severity sibling of the
section-absence case above rather than a second silent pass. It is folded in
here because it is the same function, the same generator-format-drift class,
and the same fix window.

Requirement: a fence line with a language or info string, and a tilde fence of
three or more characters, are skipped like a bare fence; a test covers at
least the info-string form.

## Non-goals

- Broadening the guard past `.trellis/` paths.
- Making the check regenerate or repair a map.

## Acceptance Criteria

- [x] An existing map with no `# Directory Structure` section produces a
      warning naming the file; a test covers it.
- [x] The existing six generated-map tests still pass unchanged in intent,
      with the no-section test updated to assert the warning.
- [x] The zero-checked success message cannot be read as a completed
      validation.
- [x] A fence line with an info string is skipped rather than parsed as a
      tree entry; a test covers it.
- [x] The fix ships in the payload with a manifest bump and CHANGELOG entry.
