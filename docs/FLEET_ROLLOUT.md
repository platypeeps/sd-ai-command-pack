# Fleet Rollout

This repository tracks the known sd-ai-command-pack consumer fleet in
`docs/fleet/consumers.json`. The manifest is operator-triggered inventory, not
an unattended rollout system.

The schema-version-5 manifest owns rollout order and cohort policy explicitly.
It also carries each consumer's install mode: an optional `mode` of `fat`
(the default) or `thin`, plus an optional `pinPath` that defaults to
`.sd-ai-command-pack/provenance.json` and must stay relative to and contained
inside the consumer checkout. Every consumer is `thin` today, so every row in
the registry is judged by its pin. Read `mode` out of `docs/fleet/consumers.json`
rather than trusting this sentence; a mixed fleet is a supported state, and the
count here is a snapshot, not a contract.

A `fat` consumer is judged by installed-versus-target tree drift. A `thin`
consumer vendors no tree, so fleet status reports its pin — `present` with a
version, `absent`, or `unreadable` — and compares it to the machine install.
When any consumer is thin, the report also collects one machine-scope
inventory per run and raises skew rows for pin versus machine install, machine
install versus target, and plugin versus machine receipt. Skew rows are built
before the human list is truncated, so a long advisory list never hides one.
The current fast-first order is rwbp-coordinator, loadsmith, hoa-manager,
rwbp-website, mezmo_benchmark, se-ai-command-pack, sd-github-review, then
anomaly-metric-creator. The first three are sequential canaries. The next four
form a bounded post-canary cohort with concurrency two. AMC remains a solo
final cohort because its CI feedback loop is materially slower.

Use the read-only fleet status report before or after rollout activity:

```bash
bash templates/scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  templates/scripts/sd-ai-command-pack-status.py fleet
```

The same command can run from an installed consumer after the machine profile
has been created once with `install.py TARGET --configure-fleet`. That profile
only locates this checked-in manifest and applies local checkout path overrides;
it does not replace the versioned fleet policy in this repository.

It preserves the manifest's rollout order and reports checkout availability,
working-tree/upstream state, installed versus target pack versions, GitHub
inventory, Trellis work, and numbered next steps. It does not fetch or modify
consumers, so ref-derived values are labelled `cached`; add `--no-network` for
a local-only snapshot or `--json` for schema-versioned automation output.

## Campaign Controller

Every rollout is planned and advanced through the source-only
`templates/scripts/sd-ai-command-pack-fleet-controller.py`. The controller validates the
immutable pack release, fleet manifest, selected checkout identities, and an
existing campaign before writing private atomic state outside the repositories.
It owns canary/wave order, concurrency, attempts, action identities, receipts,
blockers, exact PR heads, and the next eligible action; it never runs consumer
commands or GitHub mutations itself.

Campaign state is a private atomic file written outside every repository at
`<state-home>/<repo-sha256>/<campaign>.json`, with a sibling `<campaign>.lock`.
`<state-home>` is the shared user-local state root plus `fleet-campaigns`. That
root resolves through one ladder for every pack surface:
`SD_AI_COMMAND_PACK_STATE_HOME` when set to an absolute path, then
`$XDG_STATE_HOME/sd-ai-command-pack`, then the Windows
`%LOCALAPPDATA%\sd-ai-command-pack\state`, then
`~/.local/state/sd-ai-command-pack`. A relative `XDG_STATE_HOME` is still
rejected outright. `<repo-sha256>` is the
SHA-256 of the resolved absolute source root, so the same campaign ID against
two different source checkouts never collides. The hidden `--state-home`
override exists only for tests. If a campaign action ID is lost mid-rollout, it
can be recovered directly from this JSON rather than reconstructed from
conversation history.

`preflight` is not a controller subcommand. It is the fleet-lane stage that
inventories consumers (see **Timing Evidence**) before the controller issues
any consumer action; the controller does not re-run it and exposes no
`preflight` verb of its own.

Create one safe campaign ID and plan once:

```bash
bash templates/scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  templates/scripts/sd-ai-command-pack-fleet-controller.py plan \
  --repo <absolute-source-root> --campaign <campaign-id> \
  --release <version> [--consumer <name> ...] [--no-merge] --json
```

Call `next`, execute each returned action exactly once through its documented
owner, and record the normalized result against that action ID. Identical
receipt replay is a no-op; a conflicting receipt, wrong release/consumer,
skipped stage, stale PR head, changed fleet manifest, or invalid concurrent
start fails closed. `status` and `validate` are read-only. After interruption,
`resume` exposes reconciliation evidence for issued actions rather than
reissuing install, PR, review, or merge side effects.

When the lane's own finalization advances the PR — the journal commit that
finish-work writes before merge, which happens on every lane — record the issued
action at the new head and pass the finish-work receipt that produced it:

```bash
bash templates/scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  templates/scripts/sd-ai-command-pack-fleet-controller.py record \
  --repo <absolute-source-root> --campaign <campaign-id> \
  --release <version> --action-id <issued-action-id> \
  --consumer <name> --result passed --head <successor-full-sha> \
  --finalization-receipt <finish-work-receipt.json> --json
```

The controller accepts the advance only from the receipt itself: schema 1,
`status: valid`, `mode: completion`, `evidence.baseOid` equal to the lane's
recorded head, `evidence.headOid` equal to the head being recorded, and every
`evidence.changedPaths` entry under `.trellis/`. The accepted pair stays on the
receipt as `finalizationAdvance`, so the chain still shows which head each stage
validated. This is the ordinary path and costs one record.

If the head advanced for any other reason — an outside push to the PR branch —
there is no such receipt. Do not record the successor SHA against the old
publication epoch. Record the issued action against its published SHA and PR as
a bounded republication retry:

```bash
bash templates/scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  templates/scripts/sd-ai-command-pack-fleet-controller.py record \
  --repo <absolute-source-root> --campaign <campaign-id> \
  --release <version> --action-id <issued-action-id> \
  --consumer <name> --result retryable-failure \
  --reason-code pr-head-advanced --head <published-full-sha> \
  --pr-number <existing-pr-number> --json
```

The first eligible retry returns the lane to `pr-publication`. Reclassify the
new exact head, reuse the existing PR, and record the issued publication action
with that successor SHA. This starts a new exact-head epoch. Generic transient
retries remain on their current stage; a second head advance at the same stage
parks as retry-exhausted. For a merge-stage finish-work successor, retain the
valid finish-work receipt, stop before housekeeping, publish and re-review the
already-pushed successor, then pass that receipt to housekeeping on the new
merge action if its head remains unchanged. This ordinary successor path is
separate from corrective-release recovery, which remains restricted to
terminal merge-stage pack blockers such as missing task evidence.

The controller composes the existing wave planner internally. It issues only
manifest-policy `canStart` lanes, never exceeds `maxConcurrency`, and issues at
most one manifest-ordered merge action. A pack blocker stops new starts and
holds unsettled merges after a verified `packBlocker` receipt. `no-merge` turns successful merge eligibility
into terminal PR-open evidence without issuing a merge.

Operator ergonomics, none of which mutate a repository:

- `status --show-issued` adds each lane's already-issued `issuedActionId` to the
  read-only status output, so a recorded action ID can be re-read without
  re-issuing it or re-deriving it from the state file.
- Status output surfaces merge-queue transparency: a lane whose merge is held
  behind a lower-priority candidate reports `heldBehind` and a `queueNote`, so
  "nothing is happening" is distinguishable from "waiting its turn". This is
  display-only and never rewrites a persisted blocker.
- An `operator-decision` result parks one lane in the terminal `blocked` state
  with a recorded `--reason-code` (and, for a canary, a validated
  `--provenance`). By default a parked canary halts the whole campaign
  (`stopStarting`). The explicit `plan --allow-parked-canary` opt-in instead
  treats a parked canary as settled for wave progression, letting the operator
  defer exactly one canary without a full restart while every other guard stays
  in force.

## Refresh Shape

For each `refresh-needed` or `residual-damaged` repo (the second is a converted
consumer that is already at the target version but has lost a recorded target;
the refresh reinstalls its residual):

1. Record the exact default-branch commit, then create a PR-only branch in that
   consumer repo. During checkout validation, create or activate one dedicated
   Trellis task with substantive release, ownership, validation, and completion
   criteria before installing. Stop when an unrelated active task or dirty
   Trellis state makes ownership ambiguous.
2. Run the printed `python3 install.py <repo> --force [--platform ...]` command
   from this pack checkout, exactly as printed. A converted consumer's command
   carries no `--platform`: its platform set is owned by its thin pin, and a
   thin-aware refresh rejects the flag rather than re-deriving the residual
   from the registry's list. Changing a converted consumer's platform set is a
   `--revert-thin` plus a reviewed reconversion, never a fleet sweep.
3. Run the printed `python3 templates/scripts/sd-ai-command-pack-install-audit.py --repo
   <repo> --expected-platform ...` command from this pack checkout, like step 2
   and unlike step 4 — the script path is relative to this repository, and
   `--repo` is what points the audit at the consumer. Record it that way in any
   consumer-side note: the same relative path resolves to nothing inside a thin
   install. This audit vouches pack-owned
   receipt targets only — the files recorded in `installed-targets.txt` and
   hashed in `provenance.json`. A consumer that relaxes its ignore policy to
   newly track a Trellis-owned platform adapter does not thereby add that
   adapter to the pack receipt or provenance; it stays outside the pack-vouched
   set.
4. Run each printed `candidatePrepare` command from the consumer checkout, then
   run the consumer's deterministic full-check and stage only the refresh.
5. Commit and push through `sd-finish-work`, which folds the work commit, the
   post-archive structural-map regeneration, the real `task.py archive`, and
   the recorded journal into the single head it pushes: regenerate the map
   after the archive move and before the push, never in a commit appended to a
   pushed head.
6. Open the PR through the normal configured remote-review loop, inspect
   existing feedback, and classify every verified finding with the source
   finding-severity gate before watch or merge. In the PR body's verification
   summary, attribute each ownership class to the check that validates it: the
   install audit and `provenance.json` for pack-owned receipt targets, and the
   consumer's own integration and readiness checks for any newly tracked
   Trellis-owned adapter or consumer-owned path. Do not describe a
   Trellis-owned adapter as covered by the pack install audit.
7. Wait for required checks and merge through the consumer housekeeping gate
   only when finding disposition permits the rollout to continue.
8. Confirm post-merge provenance reads the target version and the audit passes.

Process only actions issued by the controller. Run the canary cohort strictly
sequentially and do not start later work until every selected canary has the
required terminal evidence. After that gate, independent consumer lanes may
overlap only within the active cohort's configured bound. Each lane owns one
checkout, branch, and PR; never interleave writes to the same checkout. Review
and CI may settle concurrently, but controller-issued housekeeping merges
remain one at a time in manifest order. Do not move AMC first merely because it
appears in an operator's local list, and never rebuild scheduler state from
conversation history.

## Timing Evidence

Every `sd-fleet-refresh` run records a local, resumable timing baseline with
the source-only helper. This is observability around the existing gates, not a
new pass/fail authority and not a hosted telemetry service. The record lives
under the user's platform state directory, keyed by a digest of this source
checkout and a safe run ID; it never dirties either the source or consumer
repository.

Initialize one run before preflight using the target version and the selected
consumer names plus rollout priorities:

```bash
bash templates/scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  templates/scripts/sd-ai-command-pack-fleet-timing.py --repo <absolute-source-root> \
  init --run-id <run-id> --target-version <version> \
  --consumer <name>:<priority> [...]
```

`<priority>` accepts either a raw integer or a case-insensitive cohort label —
`canary` (10), `post-canary` (50), or `final` (90) — so the common three-wave
shape can be written `--consumer amc:canary --consumer rwbp-website:post-canary`
without memorizing the numbers. Raw integers still work and mix freely with
labels; an unknown token is rejected with a message naming the valid labels.

Record the run ID in the active rollout task or session and reuse it after an
interruption. Repeating `init`, an already-active start, an identical end, or
an identical consumer outcome is a no-op. A retry is explicit: close the prior
attempt, then start the same stage again. Atomic private writes and a bounded
operation lock preserve the last valid record if the process is interrupted.

Use `stage-start` and `stage-end` around these exact boundaries:

| Scope | Stage | Boundary |
| --- | --- | --- |
| Fleet | `preflight` | Consumer inventory before the first consumer action |
| Consumer | `checkout-validation` | Clean-tree check, base capture, and refresh branch creation |
| Consumer | `install` | Installer mutation only |
| Consumer | `audit` | Printed structural install audit |
| Consumer | `local-gate` | Consumer full-check |
| Consumer | `commit-push` | Refresh commit, review classification, and push |
| Consumer | `pr-creation` | Consumer PR publication |
| Consumer | `reviewer-wait` | `sd-review-pr` convergence |
| Consumer | `ci-wait` | Required-check settle through the read-only watch coordinator |
| Consumer | `housekeeping` | Merge gate and branch cleanup |
| Consumer | `post-merge-audit` | Installed-version and audit confirmation |

Start `reviewer-wait` and `ci-wait` together immediately after PR creation.
End reviewer wait when review returns and CI wait when watch settles. GitHub
checks run independently of review work, so these intervals overlap naturally;
serially summing them would exaggerate cycle time. Finish each selected
consumer with `consumer-end` using `at-target`, `refreshed-merged`, `pr-open`,
`skipped`, `failed`, or `blocked` as appropriate.

Failure-like stage and consumer outcomes require a short reason. Reasons reject
control characters, absolute or home-relative paths, common credential forms,
remote URLs, and private keys. The durable schema stores no repository path, remote URL,
command output, review body, environment dump, or credential. The normal
report exposes only a short repository digest key; do not publish or paste the
local state path.

Render a partial report after an interruption:

```bash
bash templates/scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  templates/scripts/sd-ai-command-pack-fleet-timing.py --repo <absolute-source-root> \
  report --run-id <run-id>
```

After all selected consumers have final outcomes, add `--complete`. The shared
JSON and human summary reports per-stage attempt duration, retries, per-
consumer critical path, interval-union active wall time, reviewer/CI overlap,
slowest consumer, slowest stage, and aggregate fleet critical path. Elapsed
durations come from a process-independent platform monotonic clock when the
platform exposes one and the read succeeds, with the runtime monotonic clock as
a fallback when that API is absent or rejects the read; wall time is retained
only for auditable boundaries and overlap math. An active partial record uses
the current clock for a provisional summary.

A telemetry command error is reported separately and pauses new fleet mutation
until the last valid record or input is corrected. It must never erase,
reinterpret, or turn an install, audit, review, CI, finding, or housekeeping
failure into success. `dry-run` records preflight, marks current consumers
`at-target`, marks the remaining selected consumers skipped without mutation,
then completes the record.

Treat the first sequential full-fleet result as the baseline. Compare later
integration-only review and post-canary wave runs using critical path and
overlap, not summed stage time alone. This distinguishes real waiting removed
from work merely shifted into a concurrent interval.

## Interruption Policy

Stop a rollout for a correctness, security, installation/audit, or
compatibility defect in the pack. Fix it at the source before resuming the
rollout.

Do not interrupt a healthy rollout for low-risk hardening, style, or an
unrelated consumer finding. Address a small consumer-owned migration in that
consumer PR when appropriate, or record a Trellis follow-up for the next pack
release. This keeps useful review feedback without turning every observation
into another fleet-wide patch cycle.

The source-owned gate makes this policy executable. After any verified finding
from install, audit, full-check, review, or existing feedback, create a
temporary schema-version-1 JSON document and run:

```bash
bash templates/scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  templates/scripts/sd-ai-command-pack-fleet-finding-classify.py \
  --input <temporary-findings.json> --json
```

The document has a non-empty `findings` array. Each row supplies a unique safe
`id`, one `contractFamily`, non-empty `summary`, `evidence`, and `reviewer`,
plus optional repository-relative `path` and positive `line`. Families are
`correctness`, `security`, `install-audit`, `compatibility`, `hardening`,
`style`, `test-implementation`, `documentation`, `diagnostics`, and
`consumer-unrelated`. The first four block by default; the remaining six defer
to follow-up by default. Concrete `impact: blocker` plus `impactEvidence`
escalates a deferred family. An explicit `overrideDisposition` requires an
`overrideRationale` and remains visible in output; there is no public flag or
environment-variable override.

Exit `0` (`continue-with-follow-ups`) means every canonical owner is deferred.
Reply to every observation with evidence, resolve each thread only when policy
permits, and create or reuse one Trellis follow-up per owner when work remains
before continuing. Exit `1` (`pause-corrective-release`) pauses before watch,
merge, or another consumer mutation and sends all blocker owners into one
corrective campaign. Exit `2` (`invalid-pause`), malformed output, or an
unavailable command fails closed for operator correction.

Duplicate reviewer observations with the same normalized reviewer, path,
line, and summary share the first row's owner, timing disposition, follow-up,
and release trigger. They never share feedback bookkeeping: reply to and settle
every observation separately. Conflicting family, impact, or override policy
on an exact duplicate is invalid input. Delete the temporary input after
capturing the result.

## Corrective Campaign

When the severity gate returns `pause-corrective-release` for a verified
pack-owned blocker, pause consumer mutation before selecting or preparing
another release. Retain the original fleet task so it can resume after the
correction; reuse or create one source-owned Trellis corrective task instead of
creating a replacement fleet task for every finding.

Record the campaign findings in the corrective task with this ledger shape:

```text
ID | Contract family | Evidence | Severity | Disposition | Fix | Regression
```

Every canonical blocker owner owns one row. Exact duplicates reuse the owning row.
Before selecting the corrective version, run a bounded contract-surface sweep
around the failure. Cover equivalent producers and consumers, mutation paths,
persisted and dynamically loaded data, normalization and nullability, CLI
exposure, human and JSON output, failure behavior, and generated or template
mirrors where they apply. Record excluded adjacent surfaces so the sweep cannot
expand without a reason.

Iterate with focused source tests. After the finding ledger and regressions
converge, freeze the payload and update the release surfaces once.

Merge the corrective change through the source lifecycle, then resume the
original fleet task from a fresh preflight. A terminal merge-stage
`packBlocker` caused by a taskless finish-work lane must first use the explicit
controller transition:

```bash
bash templates/scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  templates/scripts/sd-ai-command-pack-fleet-controller.py resume \
  --repo . --campaign <campaign-id> \
  --recover-consumer <consumer> --corrective-release <version> --json
```

Use that transition only when the corrective release is published and current
and the exact blocked head and PR still match. For the issued publication
action, preserve the consumer's existing implementation and journal commits,
append a substantive planning task without activating it, and validate the
original planning bundle from the implementation head through the new head.
Push and reuse the PR only after that bundle is valid. The new publication
receipt establishes a second exact-head epoch; review, CI, eligibility,
housekeeping, and post-merge audit run again, while the failed merge action is
never replayed. Do not weaken the bookkeeping validator or rewrite the
preserved journal history.

**Fresh-campaign redo recovery.** The controller has no in-place verb to relink
a lane onto a redone PR after its recorded head is abandoned; that redo-lane
relink is deliberately out of scope (its typed-recovery-record design is filed
as a controller follow-up). When a lane's published head must be discarded
outright — the PR was closed, the branch was force-rewound, or the recorded
exact head no longer exists — do not try to splice the new work into the old
campaign state. Recover by starting a **fresh campaign** over the still-unmerged
consumers from a fresh `preflight`: pick a new campaign ID, `plan` with the
`--consumer` set narrowed to the repos that still need the refresh, and let each
lane republish and re-review from a clean epoch. Already-merged consumers are
reported `at-target` by preflight and skipped, so a fresh campaign never redoes
completed work. The abandoned campaign's state file can be left in place or
removed; it is keyed by its own campaign ID and never consulted by the new one.

If an urgent independent
security defect would become riskier while waiting for the bounded sweep, it
may ship immediately with that reason recorded; keep the remaining campaign
open rather than silently discarding it.

## Review Ownership

Pack-owned implementation is reviewed in the sd-ai-command-pack source PR.
Consumer refresh PRs review the installed result: selected-platform wiring,
receipt and provenance integrity, secrets, documentation accuracy, and any
repo-owned migration or integration change. Do not repeat line-level review of
unchanged vendored pack implementation in every consumer.

Every consumer refresh PR uses the configured reviewer through the normal
remote-review loop. Existing reviewer feedback blocks the merge until it is
dispositioned.

### Requesting the Copilot reviewer

When a consumer refresh PR takes the `remote` profile, request the Copilot
reviewer directly through the REST endpoint. This is the only invocation
observed to attach Copilot reliably:

```bash
gh api --method POST \
  repos/<owner>/<repo>/pulls/<pr-number>/requested_reviewers \
  -f "reviewers[]=Copilot"
```

Failure modes to expect, none of which should block the rollout:

- `gh pr edit --add-reviewer Copilot` and the GitHub MCP
  `request_copilot_review` tool have both silently no-op'd against these repos —
  the PR shows no requested Copilot reviewer afterward. Fall back to the `gh api`
  form above and confirm with `gh pr view <pr-number> --json reviewRequests`.
- A `422` from the endpoint means Copilot is not enabled for the repository or
  the account lacks the seat; record it as an override with rationale and
  proceed with the configured human reviewer rather than retrying.
- Copilot's review is advisory. Its findings still pass through the source
  finding-severity gate like any other reviewer feedback; an empty or pending
  Copilot review never gates the merge.

The final rollout report records blocker owners, deferred owners, duplicate
observation counts, explicit overrides with rationale, and follow-up task IDs;
every empty category is reported as `none`.

Do not include stale aliases such as `green-button-manager` or historical
predecessors such as `trellis-review-pr-pack`; they are explicitly excluded in
the fleet manifest.

## Thin conversion: the order a cohort must follow

A consumer's own guards reference pack scripts by path. Everything under
`scripts/` is machine-scope, so conversion removes it and the resweep counts
every surviving reference as a blocker — and one blocker blocks as hard as
ninety. Since 0.71.11 the layout resolver also installs to
`.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py` [absent: target-repo install path], which is
`consumer-config` and therefore survives conversion. That is the path a guard
should name.

The five steps, and why each precedes the next:

1. **Ship** the resolver row (done in 0.71.11). The kept path exists in the
   pack.
2. **Refresh** the consumer to that version or later. The kept path now exists
   *in the consumer*, committed. Nothing before this point may reference it.
3. **Rewrite** the consumer's guards to call the kept path instead of any
   `templates/scripts/sd-ai-command-pack-*` literal, using `--resolve NAME` for the
   scripts they used to name directly. Safe only after step 2: a rewrite that
   lands first names a file that is not there.

   Cite the kept path **as a plain path**, in every file that passes a `NAME`.
   Since 0.71.14 that citation is what tells the resweep the file has adopted
   the resolver contract, which is what stops `NAME` — the bare basename of a
   removed script — from reading as a stale path citation. A citation the
   tokenizer cannot see does not count: measured on `rwbp-coordinator`, a test
   asserting the resolver through a hand-escaped regex
   (`/\.sd-ai-command-pack\/bin\/…\.py$/`) left the file blocked until the
   assertion became an `endsWith` on the literal.
4. **Resweep** (`templates/scripts/sd-ai-command-pack-thin-resweep.py <consumer>`). What
   remains is the residue no runtime resolver reaches — glob patterns in
   instructions prose and change-classifier fixture lists. Each needs
   rewriting or a recorded acceptance; a resolver cannot rewrite a glob.
5. **Convert.**

Doing step 3 without step 1 is the trap worth naming: adopting `--resolve`
while still naming the resolver under `scripts/` trades many blockers for one
per calling file, and one is still blocked. Measured before the resolver
shipped, the fleet's 288 resolve-reachable references were spread across 68
files, not one bootstrap site per consumer.
