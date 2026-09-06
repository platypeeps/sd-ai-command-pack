# SD planning adversarial review

Adversarial review runs at four points, each with a cap on automatic passes.
When the cap is spent no further pass starts on its own. The artifact moves on,
to the send box, to implementation, to merge, once every blocking finding is
addressed or rebutted with evidence on the item. A blocking finding still open
past the cap marks the item `blocked`; non-blocking findings hold nothing.

| Flow | Point | What it checks | Cap |
|---|---|---|---|
| Research | After the brief and decisions | Claims against sources, gaps, wrong calls | 2 |
| Research | Final product, before the send box | The piece, page or ticket as a reader sees it | 1 |
| Development | prd and design | Scope, missing requirements, wrong assumptions | 5 |
| Development | Code, before merge | Defects a second reader finds | 1, plus one verification of the fix |

This file and `WORKFLOW.md` hold the only two copies of that table, and they
are identical. A skill that runs a review names its point here and reads its
cap from that row; no skill carries a cap of its own.

This file is also the one place the planning review rule is stated. When the
current run creates or materially updates an active work item's `prd.md`,
`design.md`, or `implement.md` under `docs/work/`, capture the pre-edit
existence and content hashes for those files. At the planning
convergence boundary, before requesting implementation approval or moving the
item to `in_progress`, read and follow
[`../sd-ai-command-pack/planning-adversarial-review.md`](../sd-ai-command-pack/planning-adversarial-review.md).

Apply that contract once per coherent planning edit batch. Do not claim
approval from a review lane that was skipped or failed, and do not proceed past
an unresolved blocking concern.
