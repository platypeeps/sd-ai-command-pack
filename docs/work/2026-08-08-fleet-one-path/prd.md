---
title: One canonical fleet path for Trellis, pack, GitHub, workflow
status: planning
created: 2026-08-08
---
# One canonical fleet path for Trellis, pack, GitHub, workflow

## Problem

Owner directive (2026-08-08): fleet repos should be as consistent as possible —
"one path for dealing with trellis, this pack, github, and the workflow" —
with deviation only where tech stacks genuinely differ. Today
docs/fleet/consumers.json carries per-consumer bespoke checks/prepares; the 8
consumers drift in Trellis version, pack version, review path, and Copilot
policy. Some consumers are PRIVATE repos where Actions minutes bill (macOS
10x multiplier), so the pack's shipped skill patterns carry real cost there.

## Requirements

1. Define the canonical path: Trellis version + pack version + review lane
   (router-owned Copilot, durable receipt) + CI shape, as a short normative
   doc.
2. Normalize per-consumer checks/prepares in consumers.json toward the
   canonical set; each surviving deviation is annotated with its tech-stack
   reason.
3. Private-repo Actions cost guidance (macOS multiplier; lane advice from
   08-08-ci-lane-cost). **Citation only** — see the 2026-08-17 scope note.
4. Copilot policy propagation (from 08-08-copilot-request-policy).
   **Citation only** — see the 2026-08-17 scope note.
5. Rollout via the existing fleet refresh mechanism; per-repo smoke PR.

**Scope note, 2026-08-17.** The thin migration landed after this PRD was written
and absorbed most of requirement 1: pack surfaces now resolve centrally from the
machine install and each consumer is one pin, so there is no vendored tree left
to normalize. What remains uniquely here is the canonical-path doc, the
`consumers.json` candidate-contract normalization plus the gate that enforces it,
and the rollout checklist and ledger.

Requirements 3 and 4 are **propagation, not decisions**: `08-08-ci-lane-cost`
owns the lane shape and its numbers, `08-08-copilot-request-policy` owns the
request surfaces and the ruleset pass. This task links them from the
canonical-path doc and supplies the eight real PRs that
`08-08-copilot-request-policy`'s one-review-per-head criterion is observed on.
It does not restate their figures, because two artifacts holding the same
number is one artifact going stale.

The Trellis-version leg moved out entirely, to
`08-17-fleet-trellis-version-drift`: all 8 consumers measured at 0.6.7 against
0.6.14 here, which is a bigger and differently-shaped change than a pin bump and
had no owner. The canonical-path doc still names Trellis as a leg and points at
that task.

## Acceptance criteria

- [ ] Canonical-path doc exists and names the owning tasks for each leg.
- [ ] consumers.json deviations each carry a reason or are removed, and a gate in
      this repository fails when a new bespoke entry carries none.
- [ ] Every consumer is either at the target pack pin or carries a recorded
      reason it is not — the ledger is complete, one row per consumer. The Trellis
      version is `08-17-fleet-trellis-version-drift`'s ledger, not this one's.
      *(Amended 2026-08-17; see below.)*
- [ ] No consumer carries a repo-level auto-Copilot ruleset unless opted in.
      Verified by `08-08-copilot-request-policy`, whose requirement 4 owns the
      operator pass; this task cites that result rather than re-deriving it.

**Amendment, 2026-08-17.** The third criterion previously read "All 8 consumers
on target pack + Trellis versions after rollout". It is not satisfiable as
written: at any given moment some consumer checkout is dirty or mid-task, the
rollout procedure stops on such a consumer by design
(`docs/FLEET_ROLLOUT.md:250`), and the standing rule forbids touching another
checkout to clean it. A criterion whose truth depends on other people's working
trees can never be closed, so the uniform-fleet claim is replaced by a complete
per-consumer ledger.

Deliberately no consumer is named here. Three measurements on 2026-08-17 —
15:30, 18:50, and 19:30 — returned three different dirty sets, and one consumer
was dirty, then clean, then dirty again across them; `design.md` carries the
table. A named exclusion list in a PRD is stale the day it is written and reads
as a standing property of those repositories, which it is not.

Measurement to compare against, from
`scripts/sd-ai-command-pack-status.py fleet --json`: pins were 7x 0.71.22 and
1x 0.71.26 against target 0.71.29, and that has held across all three
measurements — the *pins* are stable, only the working trees move. The Trellis
half of the original criterion moved to `08-17-fleet-trellis-version-drift`
with its own ledger.

## Evidence

2026-08-08 review: consumers.json bespoke entries; version drift table;
private-consumer billing exposure.
