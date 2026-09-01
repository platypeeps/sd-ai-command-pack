---
title: "Reshape pack deployment: thin consumers, centrally resolved surfaces"
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-09
---
# Reshape pack deployment: thin consumers, centrally resolved surfaces

> Known blocker (recorded 2026-08-14): the thin-candidate validation in
> `docs/fleet/candidate-validation.json` reports `anomaly-metric-creator`
> **blocked: 175 consumer-authored reference(s) to removed paths** (the 13
> pack-owned citations are repointed by the conversion's own rewrite and are
> not release defects). Those consumer-authored references must be
> dispositioned — repointed, allowlisted, or accepted as intentionally
> stale — before AMC's conversion child can start; AMC sits in the final
> cohort, so canary and post-canary children are not gated by this.

Parent task. Owns the requirement set, the child task map, and the
cross-child acceptance criteria for moving the pack from vendored
per-consumer installs to thin consumers with centrally resolved
surfaces. Children carry the independently verifiable deliverables;
this task is not the implementation target.

Because of that, **this task stays `planning` for the length of the
program** and is started only if it acquires direct work of its own. It
was started once, in `6e66f38a`, and the resulting `in_progress` state
with a null `branch` made its whole subtree unfinalizable: planning
finalization refuses to leave a linked `in_progress` task outside the
changed closure, so neither this task's artifacts nor any child's could
be shipped through the merge gate. Returned to `planning` 2026-08-12;
see `08-12-thin-parent-status-blocks-finalization`. Every other active
parent in this repository already follows the same rule.

## Problem

Today `install.py` vendors the pack payload — 777 manifest files
(scripts, skills for `.claude`/`.agents`, rules, review-provider
configs, docs) — into every consumer repository, committed there.
The fleet registry (`docs/fleet/consumers.json`, schema 4) lists 8
consumers across canary / post-canary / final cohorts.

Consequences, all observed in normal operation:

1. **Release cadence multiplies into consumer churn.** Every release
   (0.64.x alone has shipped 32+ times, often several per day) implies
   a sync commit, PR, CI run, and Copilot review in each consumer —
   the pack's own code gets re-reviewed 8 times per release by
   consumers that cannot meaningfully reject it.
2. **Heavy machinery exists only to police vendoring.** Byte-identical
   template/root mirror gates, shipped-surface closure checks, payload
   digests, the candidate-validation ledger, fleet refresh cohorts,
   version pins, and installed-vs-target drift reporting are all costs
   of copying the payload around. The candidate ledger alone required
   three refreshes during a single task on 2026-08-09.
3. **Fleet state is tree-diff state.** Knowing whether a consumer is
   current requires comparing installed trees, not reading a version
   pin.

## Goal

Consumers carry only what must live in their repository — a version
pin and genuinely repo-specific configuration —
while agent-side surfaces resolve from a single central installation
per machine. A pack release stops implying N consumer sync PRs, and
fleet status becomes pin inventory instead of tree diffing.

## Requirements

1. **Surface partition is explicit and complete.** Every one of the
   777 payload files is classified into exactly one of FOUR
   categories: machine-scoped Claude (plugin), machine-scoped other
   (machine installer), repo-native (platform surfaces only readable
   from the repository, e.g. GitHub instructions — stay vendored,
   shrunk), or consumer config (repo-scoped config and rules; the
   pin/provenance receipt is an install-time artifact outside the
   manifest). Pack-repo-only files (fleet registry, release
   machinery) are the definitional complement — not in the manifest,
   never shipped, no inventory needed. The classification is
   enumerable from the manifest and the platform registry, not a
   hand-maintained list, and every platform carries an explicit
   machine-vs-repo-native scope disposition.
2. **Agent-side surfaces install once per machine.** The mechanism is
   evaluated in planning (Claude Code plugin vs. user-scope skill
   directory vs. central checkout resolution); the requirement is one
   update action propagating to every repo on the machine, with the
   active version discoverable by `sd-status`.
3. **No pack code executes in consumer CI.** Research
   (`research/consumer-ci-usage.md`) established the fleet's only
   functional execution — `pr-body-scope.py` in
   `anomaly-metric-creator` — is an advisory no-op (no PR body is
   supplied, so it always exits 0); the user decided to drop it.
   Migration deletes every consumer CI pack step (syntax lints of
   vendored code plus that advisory call) along with the payload. No
   pinned-fetch bootstrap mechanism is built. A consumer's footprint
   is the version pin plus genuinely repo-scoped configuration.
4. **No trust regression.** Machine-scope surfaces install only from
   an authenticated clone of this repository's PR-reviewed, CI-gated
   default branch — the same trust root vendoring copies from — and
   update only on an explicit release-version bump; version skew
   remains visible (`sd-status` fleet mode reports pin and
   machine-install version vs. latest instead of tree drift); the
   provenance receipt keeps recording what a repo expects.
5. **Migration is incremental and reversible.** A thin mode coexists
   with the current fat install; consumers migrate one at a time
   (respecting the existing cohort order); a migrated consumer can
   revert to a fat install with one command; vendoring gates retire
   only after the last fat consumer converts.
6. **Existing contracts updated, not orphaned.** The backend
   manifest-and-filesystem spec, fleet specs, CONTRIBUTING release
   flow, and skill docs that describe vendored installs are updated in
   the same child that changes each behavior. Inventories that recite
   the vendored model are found by enumeration (grep of install/fleet
   spec surfaces), not memory.

## Child task map

Created 2026-08-09 and linked in task.json:

- **08-09-thin-surface-partition** — requirement 1; unblocks
  everything else.
- **08-09-thin-plugin-packaging** — requirement 2, Claude-side
  surfaces (Claude Code plugin + private marketplace).
- **08-09-thin-machine-installer** — requirement 2, remainder:
  machine-scope installer for non-Claude surfaces + unified update
  action.
- **08-09-thin-fleet-status-pins** — requirement 4.
- **08-09-thin-migration** — requirements 3, 5, and 6: thin-mode
  install, migration, consumer CI cleanup, gate retirement.

Added after the initial map, as defects and questions surfaced during
implementation:

- **08-09-plugin-closure-size** — requirement 2 follow-up: shrink the
  generated plugin's `installer/**` import closure so machine bootstrap
  ships only what the machine engine needs.
- **08-09-machine-status-copy-unavailable** — requirement 4 follow-up:
  the machine-payload status copy reports plugin version `unavailable`;
  make that discovery correct or its scope documented and tested.
- **08-09-codex-home-skills-family** — investigated whether Codex needs
  its own machine destination family. Completed 2026-08-12 and archived
  at `.trellis/tasks/archive/2026-08/08-09-codex-home-skills-family/`; the probe
  falsified the premise and the outcome was retiring `codex` from
  `retainVendoredFor` (see the retention criterion below).

Ordering constraints live in each child's PRD; this map is not a
dependency system.

## Cross-child acceptance criteria

- [ ] A pack release reaches every migrated consumer with zero
      consumer-repo commits: machine-scope surfaces update via the
      machine update action. The consumer pin is an expectation
      record for fleet reporting, not a control over what executes;
      bumping it is optional bookkeeping.
- [ ] A migrated consumer's CI passes with no vendored pack payload
      beyond the partition's `repo-native` and `consumer-config`
      slices, the `retainVendoredFor` carve-out below, and the pin
      receipt — no pack CI steps, and CI never executes pack code.
- [ ] Pi retention holds: a machine-dispositioned platform whose
      partition entry carries `retainVendoredFor` keeps its rows
      vendored in any consumer whose `docs/fleet/consumers.json`
      `platforms` array intersects that list. `shared` carries `["pi"]`
      because Pi reads the `.agents` layer repo-locally — evidence in
      `.trellis/tasks/archive/2026-08/08-09-thin-machine-installer/research/platform-verification.md`.
      The fleet registry is the single authority for "serves a
      platform"; no consumer declares pi today, so today's conversions
      delete those rows, and conversion is blocked when a consumer shows
      pi usage markers it has not declared.

      `codex` was carried in that list on the claim that Codex resolves
      `.agents` against the project root and never reads
      `~/.agents/skills`, its user root being `$CODEX_HOME/skills`. An
      executed probe falsified it: Codex merges the project-root layer
      with `$HOME/.agents/skills`, which the machine installer already
      writes, so the carve-out retained 77 rows per declaring consumer
      for nothing. Retired in 0.71.2 — evidence in
      `.trellis/tasks/archive/2026-08/08-09-codex-home-skills-family/research/codex-skills-resolution-probe.md`.
      An undeclared-codex marker is now an advisory, not a blocker,
      because the declaration it asks for changes no conversion plan.
- [ ] Vendored `scripts/` removal from a consumer happens only where
      the machine payload's reference rewrite is in effect: non-Claude
      surfaces execute pack scripts from `~/.agents/bin` and read the
      relocated contract doc from `~/.agents/docs`, so a consumer whose
      retained `.agents/**` still points at repo-root `scripts/` is not
      convertible until that rewrite ships
      (`08-09-thin-machine-installer`).
- [ ] `sd-status` fleet mode reports each consumer's pin, the machine
      installation's version, and latest release, without tree
      diffing; skew is visible, not silent.
- [ ] A migrated consumer reverts to a fat install with one command
      and its CI stays green.
- [ ] After the final consumer migrates, the retired vendoring gates
      (mirror byte-identity, shipped-surface closure on consumers,
      candidate-ledger refresh choreography) are removed or rescoped
      to the pack repo, and no spec still describes consumer vendoring
      as current behavior.

## Decision log (2026-08-09, user decisions)

All planning questions are resolved and folded into the requirements
above and `design.md` (D1-D3): Claude Code plugin for Claude
surfaces; machine-scope installer for non-Claude surfaces with the
same update action; no consumer CI bootstrap (the sole executing
script was an advisory no-op and is dropped); per-repo override
expression, installation locations, and the `se-ai-command-pack`
special shape are specified in `design.md`. Evidence:
`research/consumer-ci-usage.md`,
`research/claude-code-plugin-capabilities.md`.

## Out of scope

- Changing what the pack's surfaces do — this reshapes delivery only.
- The Trellis vendoring relationship (`.trellis/` is Trellis-owned,
  not pack-owned).
- Multi-machine fleet orchestration beyond the existing
  operator-triggered refresh model.

## References

Research notes that lived beside this item's Trellis record and were not carried
into docs/work. Recover the bodies from git history under `.trellis/tasks/08-09-deployment-thin-consumers`:

- research/claude-code-plugin-capabilities.md
- research/consumer-ci-usage.md
