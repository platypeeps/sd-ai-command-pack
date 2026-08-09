# Reshape pack deployment: thin consumers, centrally resolved surfaces

Parent task. Owns the requirement set, the child task map, and the
cross-child acceptance criteria for moving the pack from vendored
per-consumer installs to thin consumers with centrally resolved
surfaces. Children carry the independently verifiable deliverables;
this task is not the implementation target.

## Problem

Today `install.py` vendors the pack payload — 776 manifest files
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
pin, repo-specific configuration, and whatever their CI executes —
while agent-side surfaces resolve from a single central installation
per machine. A pack release stops implying N consumer sync PRs, and
fleet status becomes pin inventory instead of tree diffing.

## Requirements

1. **Surface partition is explicit and complete.** Every one of the
   776 payload files is classified as consumer-repo-required
   (CI-executed scripts such as the review preflight, repo-scoped
   config, the pin/provenance receipt), machine-scoped (skills,
   commands, agents, rules, docs), or pack-repo-only (fleet registry,
   release machinery). The classification is enumerable from the
   manifest, not a hand-maintained list.
2. **Agent-side surfaces install once per machine.** The mechanism is
   evaluated in planning (Claude Code plugin vs. user-scope skill
   directory vs. central checkout resolution); the requirement is one
   update action propagating to every repo on the machine, with the
   active version discoverable by `sd-status`.
3. **Consumer-repo-required pieces resolve by pinned fetch, not
   vendoring.** A consumer keeps a one-line version pin; a bootstrap
   fetches the pinned release artifact (releases are already tagged
   `v0.64.x`) and verifies integrity using the existing payload-digest
   machinery before executing anything. Artifacts are cached so CI
   without network reuses a verified copy.
4. **No trust regression.** Nothing executes without digest
   verification against a pinned version; version skew across
   consumers remains visible (`sd-status` fleet mode reports
   pin-vs-latest instead of tree drift); the provenance receipt keeps
   recording what a repo expects.
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

To be created as planning firms up; the expected decomposition:

- **Surface partition + manifest classification** — requirement 1;
  unblocks everything else.
- **Machine-scope packaging** (plugin or equivalent) — requirement 2.
- **Pinned-fetch bootstrap for CI-executed scripts** — requirements 3
  and 4.
- **Fleet/status rework to pin inventory** — requirement 4.
- **Thin-mode install + migration + gate retirement** — requirements 5
  and 6.

Ordering constraints live in each child's PRD; this map is not a
dependency system.

## Cross-child acceptance criteria

- [ ] A pack release reaches every migrated consumer with zero
      consumer-repo commits (machine-scope surfaces) plus at most a
      one-line pin bump where the consumer opts into the new version.
- [ ] A migrated consumer's CI passes with no vendored pack payload
      beyond the pin, bootstrap, and repo config — including a run
      that exercises the cached-artifact path with network disabled.
- [ ] `sd-status` fleet mode reports each consumer's pin, the machine
      installation's version, and latest release, without tree
      diffing; skew is visible, not silent.
- [ ] Digest verification failure of a fetched artifact blocks
      execution with an explicit diagnostic.
- [ ] A migrated consumer reverts to a fat install with one command
      and its CI stays green.
- [ ] After the final consumer migrates, the retired vendoring gates
      (mirror byte-identity, shipped-surface closure on consumers,
      candidate-ledger refresh choreography) are removed or rescoped
      to the pack repo, and no spec still describes consumer vendoring
      as current behavior.

## Open questions (answer in design)

1. Plugin vs. user-scope skills vs. resolved central checkout for
   machine-scope surfaces — evaluate against Claude Code's actual
   plugin capabilities and the non-Claude agent surfaces the pack also
   ships (`.agents`, Codex, Gemini adapters).
2. Where the machine-scope installation lives and how per-repo
   overrides (if any legitimately exist) are expressed.
3. Whether consumer CI fetches from GitHub releases directly or
   through a local artifact cache primed by the bootstrap.
4. How `se-ai-command-pack` (a consumer that is itself a pack) and
   other special-shape consumers fit the thin model.

## Out of scope

- Changing what the pack's surfaces do — this reshapes delivery only.
- The Trellis vendoring relationship (`.trellis/` is Trellis-owned,
  not pack-owned).
- Multi-machine fleet orchestration beyond the existing
  operator-triggered refresh model.
