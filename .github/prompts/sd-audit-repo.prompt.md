---
# description is shown by GitHub prompt pickers; mode: agent means the prompt can use tools and run an interactive workflow.
description: Run a formal multi-dimension repository audit that produces a canonical report and updates the committed findings ledger.
mode: agent
---

# SD Audit Repo

In this pack, SD means Software Delivery. A skill is a project-installed Markdown instruction bundle resolved by the agent's trusted installed-skill resolver.

Run the Software Delivery (SD) audit-repo workflow. Audit the current repository across the pack's audit dimensions with read-only reviewers, verify and synthesize the findings, reconcile them against the Trellis backlog, then produce the canonical audit report and update the committed findings ledger.

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

1. Resolve the `sd-audit-repo` skill by name using the agent's trusted skill discovery mechanism for installed skills.
2. Verify that the charter directory `.agents/skills/sd-audit-repo/charters/` exists and is non-empty relative to the repository root. If the skill or charter directory is missing, unreadable, empty, resolves to more than one candidate, fails validation, defines contradictory steps that violate this command's safety rules, or requires unavailable tools, stop and report the exact blocker.
3. Use the skill as the primary instructions. It defines the fixed audit pipeline: fingerprint, per-dimension reviewer dispatch, adversarial verification, synthesis, Trellis reconciliation, and report plus ledger update. Pass the user's invocation arguments through unchanged; the skill accepts bare charter names plus the explicit controls `dimensions=...`, `depth=quick|standard|deep`, and `follow-up`.
4. Keep every dimension reviewer read-only. Do not modify repository files except the audit report output and the `.trellis/audit/ledger.md` ledger, and do not create Trellis tasks from findings without explicit user consent for those specific tasks.
5. If any charter read, reviewer dispatch, verification pass, ledger read or write, git command, or final validation fails, stop and report the command, exit status, and complete stdout/stderr output.
6. End with the audit report in the skill's mandatory final-report format, with every mandatory section present.
