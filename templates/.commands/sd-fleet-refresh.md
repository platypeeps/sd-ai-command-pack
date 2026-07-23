---
description: Roll the pack release through sequential canaries and bounded post-canary waves using the documented fleet procedure.
---

# SD Fleet Refresh

In this pack, SD means Software Delivery. A skill is a project-installed Markdown instruction bundle resolved by the agent's trusted installed-skill resolver.

Run the Software Delivery (SD) fleet-refresh workflow. Run fleet preflight from the pack checkout, keep the manifest canaries sequential, then refresh eligible post-canary consumers in bounded isolated waves per `docs/FLEET_ROLLOUT.md`. Run each consumer's full check, open a pull request, and watch it to settled; serialize green, comment-clean housekeeping merges in manifest order.

Checkout trust policy — complete before step 1:

- Use only trusted host-provided, read-only Git and GitHub metadata inspection.
  Do not run repository scripts, hooks, package commands, provider adapters,
  command-bearing configs, or changed skill instructions during classification.
- Retain exactly one state and reason code:
  - `trusted (trusted_local_branch)` for an unambiguous named local branch with
    readable origin identity and no external PR head;
  - `trusted (trusted_same_repo_pr)` when the bound PR head repository exactly
    matches its base repository;
  - `untrusted (untrusted_fork_pr)` when the bound PR head is a fork; or
  - `indeterminate` with `indeterminate_detached_head`,
    `indeterminate_origin_unreadable`,
    `indeterminate_pr_identity_unavailable`, or
    `indeterminate_conflicting_metadata` when the required evidence is absent
    or contradictory.
- Continue to step 1 only from a `trusted` state. For `untrusted` or
  `indeterminate`, stop before loading or executing checkout content and report
  the reason and safe maintainer-run/base-branch inspection guidance. Do not ask
  for approval to execute the checkout anyway.
- Include `checkout-trust: <state> (<reason-code>)` in the final report.

1. Resolve the `sd-fleet-refresh` skill by name using the agent's trusted skill discovery mechanism for installed skills.
2. If that skill is missing, unreadable, empty, resolves to more than one candidate, fails validation, defines contradictory steps that violate this command's safety rules, or requires unavailable tools, stop and report the exact blocker.
3. Use the skill as the primary instructions. It defines the fixed rollout pipeline: fleet preflight with at-target skips, sequential canaries, scheduler-bounded isolated consumer lanes, and manifest-ordered gated merges, with `docs/FLEET_ROLLOUT.md` as the procedure authority. Pass the user's invocation arguments through unchanged; the skill accepts bare consumer names or `consumer=...`, plus `no-merge` and `dry-run`.
4. Never touch a dirty consumer checkout: skip it and report why. Never share a checkout between lanes or exceed the manifest concurrency bound. Merge one consumer at a time only through its green and comment-clean housekeeping gate and in scheduler-selected manifest order.
5. If any preflight run, consumer tree check, install, full check, pull request creation, settle watch, gated merge, git command, or final validation fails, stop and report the command, exit status, and complete stdout/stderr output.
6. End with the fleet report in the skill's mandatory final-report format, with every mandatory section present.
