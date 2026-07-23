# Fleet Controller Recovery

Load this reference only after the controller reports reconciliation, blocked
or invalid state, an explicit ownership retry, or a verified corrective-release
need. Normal campaigns do not need it.

## Issued Or Ambiguous Actions

Run the read-only reconciliation report:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-controller.py resume \
  --repo <absolute-source-root> --campaign <campaign-id> --json
```

An issued action is durable evidence that the side effect may already have
happened. Inspect the returned checkout/head/branch/clean evidence plus the
known PR through read-only commands. Record the original action as `passed`
only when exact evidence proves completion, or as `ambiguous` with a stable
reason code when it cannot yet be reconciled. After evidence becomes decisive,
use `resume --resolve-action <original-action-id> --release <version>
[--consumer <name>] --result <result>` plus the exact head/PR evidence required
by the stage. The controller appends a distinct reconciliation receipt and
advances the original stage without replaying it. Never call `next` to
manufacture a replacement action and never dispatch a second install, PR,
review request, or merge.

If local and GitHub evidence contradict, pause the campaign. Preserve the
checkout, branch, PR, receipts, and controller state for diagnosis.

## Retryable And Ownership Stops

`retryable-failure` receives one new attempt only through the controller. After
attempt exhaustion, create or reuse a scoped task and leave the lane parked.
Do not relabel product, review, policy, or compatibility failure as
infrastructure failure.

An `ownership-skip` is terminal for the current attempt. After the recorded
owner clears and the checkout is verifiably clean, explicitly reopen only that
lane:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-controller.py resume \
  --repo <absolute-source-root> --campaign <campaign-id> \
  --retry-consumer <name> --json
```

This creates a new checkout-validation attempt. It never cleans, resets, or
reuses the prior owner's work.

## Corrective Campaign

When the finding gate returns `pause-corrective-release`:

1. Immediately pause consumer mutation. Keep the original fleet task and
   controller campaign available to resume later.
2. Reuse or create one source-owned Trellis task. Record classifier owner rows
   in one ledger:

   `ID | Contract family | Evidence | Severity | Disposition | Fix | Regression`

   Exact duplicates reuse the owning row; every observation still receives its
   own reply and allowed thread resolution.
3. Run a bounded contract-surface sweep across equivalent producers/consumers,
   mutation paths, persisted/dynamic data, normalization/nullability, CLI and
   report exposure, failure behavior, and generated/template mirrors. Record
   excluded adjacent surfaces.
4. Iterate with focused source tests and optional partial candidate diagnostics:

   ```bash
   bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
     scripts/sd-ai-command-pack-fleet-candidate-check.py --consumer <name>
   ```

   Partial candidate diagnostics must never replace the canonical candidate
   ledger.
5. After findings and regressions converge, select one corrective version and
   run one canonical full-fleet candidate validation without a consumer filter.
6. Merge and tag through the source lifecycle, then resume the original fleet
   task from fresh preflight evidence. Do not create a duplicate rollout.

An urgent independent security defect may ship first only when waiting would
increase risk. Record the exception and keep the remaining corrective campaign
open.

## Invalid Or Changed State

Run controller `validate`. Do not hand-edit, delete, downgrade, or copy state
between campaigns. A release, manifest, checkout identity, action, receipt,
head, consumer, schema, or transition mismatch fails closed.

If the recorded fleet manifest changed, finish or consciously abandon the old
campaign before planning a new immutable release campaign. If the state file
or lock cannot be safely read, preserve it and report the exact controller
diagnostic; do not replace it with prompt memory.

## Operator Decisions

Use the portable structured-question contract only when mutually exclusive
policy choices remain after evidence gathering. Recommend the lowest-risk
option, state the tradeoff, and bind the answer to the exact campaign,
consumer, head/PR, and action. Noninteractive execution records
`operator-decision` and parks safely instead of inferring consent.

## Timing Anomalies

A timing failure never changes controller or delivery evidence. Pause new
mutation, resume the last valid timing record, and reconcile its stage against
controller receipts. If timing cannot be recovered, report the anomaly and
retain the authoritative delivery result unchanged.
