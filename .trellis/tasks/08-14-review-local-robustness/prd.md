# Review-local robustness: rules file delivery and stale-disposition recovery

Consolidates issues #409 and #405 — two defects in the same
`review-local.py` lane, fixed together so the lane is tested once.

## Defect 1: repository prism rules are inert (issue #409)

The built-in prism adapter never passes `--rules`, so every rule in
`.prism/rules.json` is silently undelivered in exactly the lane that gates
shipping (`sd-review`, run by `sd-ship` Stage 2). The shell lane passes
`--rules`/`--fail-on`/`--exclude`; the python adapter passes none. Observed:
a rule written to suppress a known-generated finding, and the lane reporting
exactly that finding, with no error or limitation entry.

Requirements (from the issue, kept verbatim in spirit):

- Pass `--rules <path>` only for a validated repository-relative regular
  file, not a symlink, resolved-contained in the checkout. No argv
  interpolation from configuration text.
- Distinguish "not configured" (no rules file — current behaviour) from
  "configured but missing/invalid" (visible failure or limitation entry,
  never silent omission).
- No degradation case converts a findings outcome into a clean one.
- Decide explicitly whether `--exclude`/`--fail-on` travel with `--rules`
  into the adapter; document the decision either way.

## Defect 2: stale --local-disposition id strands the run (issue #405)

`_apply_local_dispositions` runs after providers but before the durable
receipt write, so a disposition id matching no finding aborts the run with an
unusable run dir; the coordinator then caches the `invalid` outcome and
replays it on every disposition-less rerun. Recovery today is hand-deleting
the run dir and the coordinator's private state file.

Requirements: persist the receipt before applying dispositions (stale-id
failure leaves a reusable exact receipt), or treat a cached `invalid` local
outcome as re-runnable. Either way, no hand-deletion recovery remains.

## Acceptance Criteria

- [ ] A repository `.prism/rules.json` suppressing a finding suppresses it in
      the built-in adapter lane, proven by a test with a fixture rule.
- [ ] A configured-but-invalid rules file produces a visible failure or
      limitation entry, and never a silently rule-less clean pass.
- [ ] A stale disposition id no longer requires manual state deletion: the
      retry path succeeds without hand-editing, proven by a test.
- [ ] Issues #409 and #405 are closed by the shipping PR.
