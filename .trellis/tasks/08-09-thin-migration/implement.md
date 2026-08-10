# Implementation plan: thin-mode migration (parent)

This task is a parent. It carries no direct implementation; each child
below is planned, implemented, checked, and archived on its own. What
this file owns is the **order**, the **gate between children**, and the
**integration validation** that only makes sense across all six.

## Ordered children

1. `08-10-thin-conversion-tooling` — pack-internal. Ships the resweep
   verdict, `install.py TARGET --thin`, `install.py TARGET
   --revert-thin`, the `.claude/settings.json` marketplace/enable
   writer, and the pin receipt writer.
2. `08-10-thin-candidate-loop-rescope` — pack-internal. Contract C-F.
2b. `08-10-thin-prompt-surface-repoint` — pack-internal. Repoints the
   pack-shipped surfaces that survive conversion but cite paths it
   removes: measured 16 hits in 7 files (14 in 6 where the consumer has
   taken over its PR template).
   These are `packDefects` in the resweep verdict, which blocks `--thin`,
   so **no child 3-5 conversion can run until this ships**. It is listed
   as 2b rather than renumbering because children 3-5 are referenced by
   number throughout this task tree.
3. `08-10-thin-canary-conversion` — converts rwbp-coordinator,
   loadsmith, hoa-manager sequentially; executes the revert proof.
4. `08-10-thin-post-canary-conversion` — converts rwbp-website,
   mezmo_benchmark, se-ai-command-pack, sd-github-review at
   `maxConcurrency: 2`.
5. `08-10-thin-final-conversion-gate-retirement` — converts
   anomaly-metric-creator, then retires the gates per contract C-E.

## Gate between children

A child is not done — and the next child does not start — until:

- its own acceptance criteria are checked;
- the right gate passes on this repo at that child's merge commit
  (contract C-G): `make release-prep` whenever the child's merge-boundary
  fleet-manifest bytes differ from the ones pinned in the candidate
  ledger — which every forward `fat` → `thin` edit causes — or whenever
  it changed the payload; `make check` otherwise. Running only
  `make check` after such a change asserts something that cannot be
  true; and
- if that child touched `templates/**` or
  `docs/SD_AI_COMMAND_PACK.md`, `manifest.json` is bumped with a
  matching top `CHANGELOG.md` heading. `make check` is
  `test lint audit full-check` and does **not** run the release payload
  gate — that gate is a separate CI job
  (`.github/workflows/tests.yml:639`), so a green `make check` is not
  evidence the release obligation was met; and
- for children 3–5, `sd-status fleet --json` satisfies these exact
  predicates for every consumer that child converted:
  `installMode == "thin"`, `pin.state == "present"`, and
  `pin.version == machineScope.packVersion`; plus, once per run,
  `machineScope.state == "installed"` and
  `machineScope.comparison == "current"`.

  "No skew row" is deliberately **not** the criterion. Fleet `followUps`
  rows carry prose summaries and no typed skew field, fleet mode exits
  zero on skew because machine scope is advisory, and the
  plugin-vs-receipt skew row is global and names no consumer — so "no
  skew row names them" is neither machine-checkable nor capable of
  failing when it should.

Children 3, 4, and 5 additionally require child 2b shipped. That is not
a bookkeeping preference: a `packDefects` entry makes the resweep verdict
`blocked`, and `--thin` refuses without a `clear` verdict, so the
dependency is enforced by the tool rather than by this list.

They also require **explicit user authorization for that cohort** before
any mutation of a consumer repository. That
authorization is per cohort, not once for the task: authorizing the
canary cohort does not authorize post-canary.

## Integration validation (this parent's own check)

Runs once, after child 5 merges. Each item names the command and the
result that means failure.

1. **Fleet is uniformly thin.**
   `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
     scripts/sd-ai-command-pack-status.py fleet --json`
   — all 8 consumers report `installMode == "thin"`,
   `pin.state == "present"`, and `pin.version == machineScope.packVersion`;
   `machineScope.state == "installed"` and
   `machineScope.comparison == "current"`. Any other value is failure.
   These are exact JSON predicates because fleet mode exits zero on skew
   and its follow-up rows are untyped prose.
2. **No consumer runs pack CI.** For each consumer, grep its
   `.github/workflows/` for pack script references and for
   `sd-ai-command-pack-sync.yml`. Any hit is failure. This enumerates
   from each consumer's filesystem, not from a list written here.
3. **No vendoring described as current behavior.** Grep the install and
   fleet spec surfaces plus `docs/` for descriptions of consumer
   vendoring in the present tense. Expected count: 0. Historical or
   explicitly past-tense text is allowed and must be recognisable as
   such.
4. **Retired gates are gone, kept gates remain.** `make check` passes.
   Consumer fat installation and audit — `validate_consumer` in
   `scripts/sd-ai-command-pack-fleet-candidate-check.py` — no longer
   runs in its fat form. `scripts/sd-ai-command-pack-surface-check.py`
   still runs through `scripts/sd-ai-command-pack-full-check.sh:612`
   **and still fails** on a deliberately introduced template/root mirror
   drift (execute that falsification, then revert it). Child 5's
   enumeration of removed functions and tests is checked against what
   actually disappeared, not against its own list.
5. **Rescoped candidate loop blocks on failure.** `make release-prep`
   exercises the thin shape and exits nonzero when a deliberately broken
   plugin build is introduced (execute that falsification, then revert
   it).

Items 4 and 5 are stated as falsification checks on purpose: a gate that
is present but no longer capable of failing is the exact defect this
retirement risks introducing, and only a deliberate break detects it.

## Rollback points

- After any child 3–5 conversion: `install.py TARGET --revert-thin` on
  that consumer. Per contract C-D that one command also flips the
  consumer's `mode` back to `fat` in the pack checkout it runs from,
  after preflighting both roots — if either is unwritable it refuses
  before any write rather than half-reverting. The resulting pack-side
  diff still needs a normal reviewed PR, and `make release-prep` — the
  flip moves the fleet-manifest digest.
- After child 5's gate retirement: `git revert` of the retirement
  commit restores the gates; it does not un-convert consumers, and the
  restored consumer-facing gates would then fail against a thin fleet.
  So retirement is the one step whose rollback requires reverting
  conversions too — noted here rather than discovered later.

## Planning adversarial review (round 1, 2026-08-10)

Trigger: `design.md` and `implement.md` created, `prd.md` materially
updated, and five child `prd.md` files created in one planning batch.
Host lane completed. Codex lane completed
(`codex exec --cd . --sandbox read-only --ephemeral`, 11 concerns).

| ID | Lane | Severity | Concern | Disposition |
|----|------|----------|---------|-------------|
| C-1 | Codex | blocking | Resweep blocks on pack references inside files the conversion itself deletes; `docs/SD_AI_COMMAND_PACK.md` is a `machine-other` row present in every consumer, so no consumer could ever return `clear` | addressed — C-A splits hits by whether a *removed path* is cited, into `scheduled`, `packDefects`, `blockers`, `advisories`; child 1 req 1. **Superseded 2026-08-10:** the original two-class split (*scheduled for removal* / *external callers*) was itself measured wrong during child 1 step 3 and replaced with the four-class rule now in C-A; see child 1's `implement.md` round 4 ledger and `research/fleet-blocker-scan.json` |
| C-2 | Codex | blocking | Candidate loop named as `fleet_lib` + `fleet-preflight.py`; it is really `validate_consumer` in `fleet-candidate-check.py` (`prepare-release.py:342`), and `prepare-release.py:338` skips it when the ledger is current. All 8 entries omit `mode`, so "run each in its declared mode" exercises zero thin checkouts | addressed — design evidence corrected, C-F rewritten to require a shadow-thin run regardless of declared modes and to depend on child 1; child 2 rewritten |
| C-3 | Codex | blocking | Drift preservation (`removal.py:185`, `:408`) lets conversion succeed with vendored surfaces still present under a thin pin | addressed — C-B requires plan-then-mutate; unforced drift aborts with an unchanged tree; child 1 AC inverted from preserve-and-continue to abort |
| C-4 | Codex | blocking | C-D says `--revert-thin` flips the registry; `implement.md` rollback said command *plus* a manual flip; child 1 omitted the flip entirely | addressed — one contract chosen: the command flips the registry in the pack checkout it runs from and does not commit. C-D, `implement.md` rollback, and child 1 req 4 + AC now agree |
| C-5 | Codex | blocking | Child 5 retires "shipped-surface closure" by name, but `surface-check.py` (reached via `full-check.sh:612`) is also the template/root mirror gate `AGENTS.md:29` requires | addressed — C-E and child 5 retire by enumerating exact functions/tests; the surviving mirror gate must still fail on injected drift |
| C-6 | Codex | material | 167 is current-partition arithmetic, not the per-checkout deletion count (166); "all consumers sit at the same pin" is false (0.64.3–0.64.33) | addressed — design evidence corrected with measured per-consumer figures; the same-pin claim was mine and was wrong |
| C-7 | Codex | material | Receipt-based verification misses tracked pack-like files the receipt never listed | addressed — C-B requires the structural install audit before mutating and a post-conversion scan; child 1 AC added |
| C-8 | Codex | material | Verdict keyed to `HEAD` only; a file can change without `HEAD` moving | addressed — C-A binds the verdict to a worktree digest and a clean tree; child 1 AC proves refusal with an unchanged tree |
| C-9 | Codex | material | Every `mode` flip moves the fleet-manifest digest pinned into the candidate ledger (`fleet_lib.py:766`), so children claiming "`make check` passes" assert something impossible | addressed — new contract C-G; parent gate and children 1, 3, 4 now require `make release-prep` when the payload or fleet manifest changed |
| C-10 | Codex | material | "No skew row" is not machine-verifiable: follow-up rows are untyped prose, fleet exits zero on skew, plugin-vs-receipt skew names no consumer | addressed — replaced everywhere with exact JSON predicates on `installMode`, `pin.state`, `pin.version`, `machineScope.state`, `machineScope.comparison` |
| C-11 | Codex | material | Child 3 let later canaries proceed past a blocked one, contradicting the wave planner (`fleet-wave-plan.py:200`) and the spec's canary progression rule | addressed — child 3 stops the whole cohort; continuing requires the explicit parked-canary override |
| C-12 | host | material | Delete set enumerated from the current partition would leave orphans *and* pass a partition-based check. Measured: all 8 receipts hold 210 entries, 17 unclassified by the current partition (13 `RETIRED_TARGETS`, 3 bookkeeping files, `.gitignore` managed block) | addressed — C-B rewritten receipt-first with the four special cases named; verification compares against the pre-conversion receipt |
| C-13 | host | material | `.claude/settings.json` has zero partition rows — it is entirely consumer-owned, so a writer that overwrites it destroys unrelated keys | addressed — C-C requires merge semantics and recorded additions so revert removes exactly what conversion added |
| C-14 | host | material | No child covered the operator prerequisite: conversion removes agent surfaces assuming the machine supplies them | addressed — new contract C-C2; children 3 and 4 verify machine scope before mutating |
| C-15 | host | minor | Ancestor `08-09-deployment-thin-consumers/design.md` says `github` is 23 files; the shipped partition has 21 | addressed — correction recorded in this task's design evidence; the artifact is the authority |

No concern is `parked` or `unresolved`. Every blocking concern was
verified against repository code before acting, and C-6's correction
overturned a claim of mine rather than Codex's.

### Round 2 (2026-08-10)

Host lane: cross-artifact value sweep — found two stale copies of the
round-1 `167` figure (child 1's problem statement, and this task's
tradeoff bullet) and corrected both to the measured `166`.

Codex lane: the first round-2 invocation **failed** — it returned a
review of `08-09-thin-machine-installer`, an archived task, with
citations to paths that do not exist. That output was discarded, not
counted as approval, and the lane was re-invoked with an explicit scope
restriction. The re-run completed and independently reproduced the
measured figures (`{machine: 166, kept: 27, retired: 13, special: 4} =
210` for all eight receipts; 21 `github` partition rows; all four pins).

| ID | Lane | Severity | Concern | Disposition |
|----|------|----------|---------|-------------|
| C-16 | Codex | blocking | C-2's remediation names the release-prep skip but ships no mechanism against it. `fleet-candidate-check.py` has no `manifest.json` payload row and the payload digest hashes only manifest-declared sources (`fleet_lib.py:744`), so editing the validator moves neither digest, the ledger stays current, and `prepare-release.py:335` returns without running the new code — a skip `tests/test_release_prep.py:90` tests explicitly | addressed — child 2 gains requirement 6 (force-validation option or a validator digest bound into the ledger) and the exact criterion "current ledger + changed validator source still executes validation" |
| C-17 | Codex | blocking | C-C2 requires machine provisioning before *every* cohort, but only children 3 and 4 stated it; child 5's machine predicate was post-conversion only, and "same sequence as children 3 and 4" does not inherit a separately stated requirement | addressed — child 5 gains requirement 1a and a pre-mutation acceptance item |
| C-18 | Codex | blocking | C-D specified only the unwritable-pack-checkout failure; the mirror case (writable pack checkout, unwritable target) was unspecified, while the parent PRD, child 1, and the rollback plan promised both writes unconditionally | addressed — C-D now carries a two-root write-order matrix, preflights both roots before either write, and child 1 gains a both-directions failure-injection criterion |
| C-19 | Codex | material, non-blocking | C-G's "every `mode` flip invalidates the ledger" is too absolute: the checker keeps no transition history, so restoring the pinned bytes makes the old ledger current again, and ledger consumer rows do not bind the validated mode (`fleet_lib.py:823`) | addressed — C-G restated as differing fleet-manifest bytes at a merge boundary; the parent gate wording follows |
| C-20 | Codex | minor | Four citations were wrong or imprecise: `removal.py:397` (drift refusal is `:185`, the zero return is `:408`), `fleet_lib.py:53` (default at `:26`, applied at `:55`), `full-check.sh:605` (invocation at `:612`), spec `:1002` (`:1008`) | addressed — every occurrence corrected across all six artifacts and verified by grep returning no stale citation |

Codex confirmed C-1, C-3, C-5–C-13, and C-15 as honestly remediated.
Two automatic rounds used; none of the permitted third round was needed
for a persisting substantive concern. No concern is `parked` or
`unresolved`.
