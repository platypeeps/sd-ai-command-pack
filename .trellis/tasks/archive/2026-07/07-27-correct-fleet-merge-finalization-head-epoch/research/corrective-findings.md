# Corrective finding ledger

| ID | Contract family | Evidence | Severity | Disposition | Fix | Regression |
| --- | --- | --- | --- | --- | --- | --- |
| merge-finalization-head-epoch | correctness | PR #180 was reviewed at `24da9cb62cbcf8cbc8003cce6a3659d3a6d5b63e`; required finish-work produced valid completion head `607c8ad62759764ccb55280347ab32c69ebe60b2`; controller permits `pr-head-advanced` only at review or merge eligibility, so issued merge action `311c775981ba8edc5d66c64afabab0a8b9b341a3f58dbe2d87cc3b12c33b948f` cannot be truthfully completed | blocker | patch release; original campaign paused | permit bounded merge-stage republication and document retained receipt handoff | controller transition/idempotency tests plus skill/docs parity and full-fleet candidate validation |

## Surface sweep

- Equivalent consumers: every merge-capable fleet lane uses the same
  `sd-finish-work` then `sd-housekeeping` owner, so all eight configured
  consumers are affected.
- Mutation paths: first publication, review remediation, eligibility
  remediation, merge finalization, terminal corrective recovery, and resume
  reconciliation were inspected.
- Persisted/dynamic evidence: issued action, immutable receipts, current lane
  head/PR, live GitHub head, and retained finish-work receipt were compared.
- Failure behavior: stale successor heads remain rejected; second head churn
  remains bounded; missing task evidence remains a terminal pack blocker.
- CLI/report exposure: controlled error wording and operator guidance require
  updates; no public campaign/state option is added.
- Generated/template mirrors: `templates/**` remains authoritative and the
  installed `.agents` mirror must be synchronized.

## Excluded adjacent surfaces

- No changes to Trellis, the finish-work receipt schema, housekeeping merge
  eligibility, or consumer product code are needed.
- No head republication is added after merge or during post-merge
  verification.
