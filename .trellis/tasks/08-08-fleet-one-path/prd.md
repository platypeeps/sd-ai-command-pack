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
   08-08-ci-lane-cost).
4. Copilot policy propagation (from 08-08-copilot-request-policy).
5. Rollout via the existing fleet refresh mechanism; per-repo smoke PR.

## Acceptance criteria

- [ ] Canonical-path doc exists and names the owning tasks for each leg.
- [ ] consumers.json deviations each carry a reason or are removed.
- [ ] All 8 consumers on target pack + Trellis versions after rollout.
- [ ] No consumer carries a repo-level auto-Copilot ruleset unless opted in.

## Evidence

2026-08-08 review: consumers.json bespoke entries; version drift table;
private-consumer billing exposure.
