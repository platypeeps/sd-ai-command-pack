---
description: Roll the pack release through sequential canaries and bounded post-canary waves using the documented fleet procedure.
---

# SD Fleet Refresh

In this pack, SD means Software Delivery. The fleet-refresh procedure is a source-only skill that this command loads by reading its checkout file directly; it is intentionally not resolvable by the agent's installed-skill resolver.

Run the Software Delivery (SD) fleet-refresh workflow. Run fleet preflight from the pack checkout, keep the manifest canaries sequential, then refresh eligible post-canary consumers in bounded isolated waves per `docs/FLEET_ROLLOUT.md`. Run each consumer's full check, open a pull request, and watch it to settled; serialize green, comment-clean housekeeping merges in manifest order.

1. Load the fleet-refresh procedure by reading `.agents/skills/sd-fleet-refresh/SKILL.md` from the pack source checkout. This skill is source-only and intentionally not resolvable by name, so do not use installed-skill resolution.
2. If that file is missing, unreadable, empty, defines contradictory steps that violate this command's safety rules, or requires unavailable tools, stop and report the exact blocker.
3. Use that file's contents as the primary instructions. They define the fixed rollout pipeline: fleet preflight with at-target skips, sequential canaries, scheduler-bounded isolated consumer lanes, and manifest-ordered gated merges, with `docs/FLEET_ROLLOUT.md` as the procedure authority. Pass the user's invocation arguments through unchanged; the procedure accepts bare consumer names or `consumer=...`, plus `no-merge` and `dry-run`.
4. Never touch a dirty consumer checkout: skip it and report why. Never share a checkout between lanes or exceed the manifest concurrency bound. Merge one consumer at a time only through its green and comment-clean housekeeping gate and in scheduler-selected manifest order.
5. If any preflight run, consumer tree check, install, full check, pull request creation, settle watch, gated merge, git command, or final validation fails, stop and report the command, exit status, and complete stdout/stderr output.
6. End with the fleet report in the skill's mandatory final-report format, with every mandatory section present.
