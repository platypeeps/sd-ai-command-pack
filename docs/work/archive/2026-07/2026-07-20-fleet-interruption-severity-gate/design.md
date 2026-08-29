# Fleet interruption severity gate design

## Boundary

The gate classifies verified findings surfaced while `sd-fleet-refresh` is
running. It decides whether consumer mutation pauses for one source corrective
release or whether the finding is recorded as follow-up work. It does not
dismiss feedback, resolve threads automatically, alter source review quality,
or bypass the consumer housekeeping requirement that every thread be settled.

Classification is deterministic and source-owned. The fleet skill gathers the
verified finding evidence, writes a temporary schema-versioned JSON document,
and invokes a read-only source script. Free-form prose alone never silently
changes rollout state.

## Finding contract

Add `scripts/sd-ai-command-pack-fleet-finding-classify.py` as a source-only
command. Its input schema version 1 contains a non-empty `findings` array. Each
finding has:

- a unique safe `id`;
- `contractFamily`, one of `correctness`, `security`, `install-audit`,
  `compatibility`, `hardening`, `style`, `test-implementation`,
  `documentation`, `diagnostics`, or `consumer-unrelated`;
- non-empty `summary` and `evidence` text;
- reviewer identity plus optional repository-relative `path` and positive
  `line`, used with the normalized summary to identify exact duplicate review
  findings;
- optional `impact: blocker` plus non-empty `impactEvidence`, which escalates a
  normally deferred family when concrete evidence shows blocker impact; and
- optional `overrideDisposition` plus `overrideRationale`, which explicitly
  replaces the computed outcome for an operator decision.

Default blocking families are correctness, security, install/audit, and
compatibility. The remaining families default to follow-up. A blocker impact
signal may only escalate; an override may choose either outcome but always
requires a rationale and remains visible in output.

## Duplicate ownership

The classifier normalizes reviewer, path, summary whitespace, and line into a
canonical signature. The first input row owns that signature. Later exact
matches point to the owner, inherit its computed and final disposition, and do
not create another corrective release or follow-up task. Duplicate rows may
not supply conflicting family, escalation, or override data; disagreement is
invalid input rather than order-dependent policy.

The JSON result includes all observations plus one canonical `owners` row per
signature. Reports and task creation use only owner rows, while duplicate
observation IDs remain visible for replies and thread resolution.

## Output and exit model

JSON schema version 1 records counts, final rollout decision, blocker and
deferred owner summaries, and observation rows containing owner ID, duplicate
state, default/computed/final dispositions, rationale, escalation, and override
evidence. Human output is derived from the same result.

- exit `0`: every owner is `defer-follow-up`; the rollout may continue after
  feedback is replied to, resolved, and recorded once;
- exit `1`: at least one owner is `block-corrective-release`; pause before the
  next consumer mutation and use one corrective campaign; and
- exit `2`: input, path, duplicate, escalation, or override validation failed;
  fail closed and pause for operator correction.

The command never creates tasks, posts replies, changes branches, or writes the
canonical candidate ledger.

## Fleet orchestration

After any verified finding, `sd-fleet-refresh` invokes the classifier before
another consumer may be installed or merged. A blocking result pauses the
fleet and feeds its owner rows into the existing single corrective-task
campaign. A deferred result requires one source or consumer follow-up per owner
when work remains, an evidence-backed reply for every observation, and thread
resolution only when the repository's review policy permits it.

The final fleet report always includes blocker and deferred owner summaries,
duplicate observation counts, overrides, and follow-up task identifiers or
explicit `none`. Existing integration-only review classification is unchanged.

## Safety and compatibility

- Invalid input is a pause, never a deferred result.
- IDs and paths reject traversal, Windows drive/root forms, option-like values,
  control characters, and non-string coercion.
- Evidence and rationale are whitespace-normalized and bounded in output.
- Overrides are explicit data with rationale; no environment variable or
  adapter argument can silently downgrade a blocker.
- Exact duplicates share timing disposition but every review observation still
  receives a reply or documented resolution.
- The classifier remains out of the install manifest and is allowlisted only
  in source-checkout audit policy.

## Rejected alternatives

- Infer severity from reviewer prose with keywords: unstable text would make
  rollout timing nondeterministic.
- Put the policy only in skill prose: duplicate ownership, override evidence,
  and reports would remain untestable.
- Treat every finding as a release blocker: this recreates the cycle-time
  failure the task exists to fix.
- Auto-resolve deferred threads: timing disposition is not feedback dismissal.
