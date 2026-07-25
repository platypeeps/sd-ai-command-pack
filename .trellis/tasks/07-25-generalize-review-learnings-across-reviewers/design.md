# Reviewer-Neutral sd-review-learnings Design

One shared evidence parser resolves reviewer provenance and trusted
adjudication before the existing recurrence classifier. The classifier consumes
one normalized underlying issue per plan/head, with a list of contributing
reviewers.

Current unresolved findings remain a separate actionable section. Historical
recurrence promotion uses trusted valid evidence only. Invalid, disputed, and
insufficient-trust rows contribute to coverage/limitations, not guidance
thresholds.

The existing managed-block, target containment, dry-run/update, planning
receipt, private-cache, and atomic-write boundaries remain unchanged.
