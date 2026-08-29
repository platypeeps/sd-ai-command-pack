# Fleet Controller Recovery

Load this reference only after the controller reports reconciliation, blocked
or invalid state, an explicit ownership retry, or a verified corrective-release
need. Normal campaigns do not need it.

## Issued Or Ambiguous Actions

Run the read-only reconciliation report:

```bash
SD_PACK_TOOLCHAIN=""
for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
  "scripts/sd-ai-command-pack-toolchain.sh" \
  "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
  if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
done
[ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }

bash "$SD_PACK_TOOLCHAIN" run-python -- \
  sd-ai-command-pack-fleet-controller.py resume \
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
attempt exhaustion, create or reuse a scoped task and park the lane while the
cause is fixed. Do not relabel product, review, policy, or compatibility
failure as infrastructure failure.

Parking is not permanent. Once the cause is fixed and the fix is proven by the
consumer's own documented gate, reopen only that lane at the stage that
exhausted:

```bash
SD_PACK_TOOLCHAIN=""
for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
  "scripts/sd-ai-command-pack-toolchain.sh" \
  "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
  if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
done
[ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }

bash "$SD_PACK_TOOLCHAIN" run-python -- \
  sd-ai-command-pack-fleet-controller.py resume \
  --repo <absolute-source-root> --campaign <campaign-id> \
  --recover-exhausted-consumer <name> --exhausted-action <action-id> \
  --release <campaign-target-version> --json
```

`--exhausted-action` is the action ID of the attempt that exhausted, and
`--release` is the campaign's own target version, not the current
`manifest.json` version. The transition is valid only for a terminal
`retry-exhausted` lane whose latest receipt is that action's
`retryable-failure` at the lane's stage, attempt, and reason code. It grants
one operator-authorized attempt at the same stage, bounded to two recoveries
per consumer and stage, and it never resumes from `checkout-validation`,
touches `receipts`, or loosens the two automatic attempts. Replaying the same
`--exhausted-action` returns the existing recovery record and changes nothing.

Every recovery is recorded append-only in `recoveries` as a `retry-exhausted`
row, distinct from the `pack-blocker` rows written by `--recover-consumer`.
Exhausting the recovery bound, or a lane whose failure is not genuinely
infrastructure, is a corrective-campaign case, not another recovery.

An `ownership-skip` is terminal for the current attempt. After the recorded
owner clears and the checkout is verifiably clean, explicitly reopen only that
lane:

```bash
SD_PACK_TOOLCHAIN=""
for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
  "scripts/sd-ai-command-pack-toolchain.sh" \
  "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
  if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
done
[ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }

bash "$SD_PACK_TOOLCHAIN" run-python -- \
  sd-ai-command-pack-fleet-controller.py resume \
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
   SD_PACK_TOOLCHAIN=""
   for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
     "scripts/sd-ai-command-pack-toolchain.sh" \
     "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
     if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
   done
   [ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }

   bash "$SD_PACK_TOOLCHAIN" run-python -- \
     sd-ai-command-pack-fleet-candidate-check.py --consumer <name>
   ```

   Partial candidate diagnostics must never replace the canonical candidate
   ledger.
5. After findings and regressions converge, select one corrective version and
   run one canonical full-fleet candidate validation without a consumer filter.
6. Merge and tag through the source lifecycle, then resume the original fleet
   task from fresh preflight evidence. Do not create a duplicate rollout.

For a terminal merge-stage pack blocker caused by missing consumer task
evidence, use the released controller's explicit recovery transition only
after the corrective source version is the current `manifest.json` version:

```bash
SD_PACK_TOOLCHAIN=""
for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
  "scripts/sd-ai-command-pack-toolchain.sh" \
  "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
  if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
done
[ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }

bash "$SD_PACK_TOOLCHAIN" run-python -- \
  sd-ai-command-pack-fleet-controller.py resume \
  --repo <absolute-source-root> --campaign <campaign-id> \
  --recover-consumer <name> --corrective-release <version> --json
```

The transition is valid only for a terminal `review-finding` with
`packBlocker: true` at `merge`, an exact PR/head, and a matching blocker
receipt. It records the corrective release and returns the lane to a new
`pr-publication` attempt. It never deletes the blocker receipt, changes the
campaign target release, or replays the prior merge action.

Execute the newly issued publication action append-only. Preserve the failed
finish-work journal commit. Create one substantive planning task with
`task.py create --no-start --description "<why this corrective task exists>"`,
leave its lifecycle at `planning` with no branch,
and commit only those task artifacts after the journal. Rerun the original
`final-bundle --mode planning` command with the failed receipt's exact base and
the new full head. Require `planning_bundle_valid`, retain that receipt, then
push the new head and reuse the PR. Classification, remote review, CI,
merge-eligibility, and housekeeping all run again. If the reviewed head stays
unchanged, pass the retained receipt to housekeeping instead of recording
another journal.

Any different result/stage, missing or stale PR/head, unrelated dirty path,
invalid task bundle, corrective-version mismatch, or second unresolved pack
blocker remains paused. Do not widen ordinary journal-only recovery or rewrite
consumer history to make it pass.

An urgent independent security defect may ship first only when waiting would
increase risk. Record the exception and keep the remaining corrective campaign
open.

## Ordinary Merge-Finalization Successor

A valid `sd-finish-work` completion receipt that advances the existing PR head
is not a terminal corrective-recovery case. On a controller version that
accepts `pr-head-advanced` at merge, record the issued merge action against its
old published full head and existing PR number as `retryable-failure` with that
reason. Preserve the new finish-work commit and receipt; do not call
housekeeping or replay the merge action. Execute the controller-issued
`pr-publication` action by verifying and classifying the already-pushed
successor head, then rerun review and merge eligibility. If the head stays
unchanged, the next merge action passes the retained receipt to housekeeping
without running finish-work again.

If the released controller rejects merge-stage `pr-head-advanced`, record the
verified contradiction as a terminal merge-stage pack blocker and follow the
corrective-campaign procedure. Never label the successor head as the result of
the old merge action or record the old head as a successful merge.

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

Once the operator has decided, record the decision against the exact head it
was made on. This is the only supported way a parked lane rejoins a campaign:

```bash
SD_PACK_TOOLCHAIN=""
for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
  "scripts/sd-ai-command-pack-toolchain.sh" \
  "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
  if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
done
[ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }

bash "$SD_PACK_TOOLCHAIN" run-python -- \
  sd-ai-command-pack-fleet-controller.py resume \
  --repo <absolute-source-root> --campaign <campaign-id> \
  --decide-consumer <name> --decision <proceed|decline> \
  --decided-by <who-or-what-decided> \
  --decision-head <full-sha the decision was made against> \
  --release <campaign-target-version> --json
```

`--release` is the campaign's own target version, not the current
`manifest.json` version, for the same reason exhaustion recovery uses it: this
transition has no corrective release, and a manifest comparison would make
every campaign undecidable as soon as the installed pack moved on.

The transition is valid only for a terminal `operator-decision` lane whose
latest receipt is that stage's `operator-decision` at the lane's attempt and
reason code, and whose published head equals `--decision-head`. A lane that
moved after the operator looked at it cannot inherit their answer.

`proceed` re-enters the lane at the stage it parked on, on a fresh attempt, and
the campaign leaves `complete` because a lane is no longer terminal. It stamps
nothing terminal by itself: the remaining stages are issued and recorded
through the ordinary receipt chain, so a decided lane cannot become `merged`
without the receipts every other lane needs.

`decline` leaves the lane exactly where it is and records that this was chosen,
so a declined lane is distinguishable from one nobody ever answered. One
parking takes one answer: replaying the identical decision returns the existing
record and changes nothing, while a different decision for the same parked
action is refused rather than silently overwriting it.

Every decision is recorded append-only in `recoveries` as an `operator-decision`
row carrying `decidedBy`, `decision`, and `decisionHead`, alongside the
`retry-exhausted` and `pack-blocker` rows.

## Timing Anomalies

A timing failure never changes controller or delivery evidence. Pause new
mutation, resume the last valid timing record, and reconcile its stage against
controller receipts. If timing cannot be recovered, report the anomaly and
retain the authoritative delivery result unchanged.
