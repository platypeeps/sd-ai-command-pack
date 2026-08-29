# Add Codex adversarial planning review design

## Overview

Use a pack-installed Claude project rule to add one planning-artifact review
contract without changing upstream Trellis. The rule remains thin and points
to a canonical pack-owned reference that defines trigger detection, host and
Codex review lanes, concern disposition, rerun bounds, and fallback behavior.

This works with direct `trellis-brainstorm` because Claude Code project rules
are additive instructions loaded independently from the Trellis skill. It also
applies when `sd-work-backlog` or `sd-continue` creates or updates the same
artifacts.

## Ownership and installed surfaces

- New Claude-only rule source:
  `templates/.claude/rules/sd-planning-adversarial-review.md`.
- Canonical cross-workflow contract:
  `templates/.claude/sd-ai-command-pack/planning-adversarial-review.md`.
- The manifest installs both the rule and its reference only for Claude.
  Keeping the reference Claude-scoped avoids the repository's all-platform
  `sd-help` reference fanout and preserves the non-Claude isolation contract.
  Keeping it outside `.claude/rules` also prevents Claude from eagerly loading
  the long contract before the thin rule's material-change trigger applies.
- Root dogfood mirrors remain byte-identical to their template sources.
- Upstream `trellis-brainstorm`, Trellis workflow templates, and the OpenAI
  Codex Claude plugin remain untouched.

The rule should be short and unconditional rather than path-scoped. Claude's
documented path rules load when matching files are read, which can miss the
earliest creation step for a brand-new artifact and can be summarized during
compaction. A concise unconditional rule avoids that reliability gap while
adding little standing context; its trigger still limits paid work to actual
planning-artifact changes.

## Trigger and cost boundary

At the start of a planning edit batch, record whether the active task's
`prd.md`, `design.md`, and `implement.md` exist and retain content hashes. At
the planning convergence boundary, compare the same files.

Run the review only when at least one artifact is new or materially changed.
Skip with a recorded reason when:

- all three hashes are unchanged;
- the diff is whitespace/format-only and preserves meaning;
- only generated manifests or task metadata changed; or
- no active Trellis task owns the files.

One coherent batch produces one initial review, not one review per write. This
keeps normal brainstorming interactive and bounds paid Codex use.

## Review lanes

The host lane performs an adversarial pass over the converged artifacts and
the minimum repository evidence needed to test their assumptions. On Claude
Code, capability-check `command -v codex` and `codex exec --help`. If both are
usable, launch a native Codex peer lane in a separate background Bash task
while the host performs its own pass, then collect the Codex result.

Codex runs directly through `codex exec` with:

- the repository root supplied through `--cd`;
- `--sandbox read-only`;
- `--ephemeral`;
- a focused prompt naming the active task directory and the changed artifacts;
  and
- an explicit instruction to review only, report material grounded concerns,
  and make no edits.

The invocation must pass resolved paths as quoted arguments and must not embed
untrusted artifact content into shell syntax. It must not invoke plugin
commands, inspect plugin caches, or require plugin state.

## Concern lifecycle

Combine host and Codex concerns and deduplicate by affected artifact, section,
and underlying decision. Give each material concern a stable `C-1`, `C-2`, ...
identifier and verify it against the artifacts and repository evidence.

Each concern receives exactly one disposition:

- `addressed`: update the owning artifact and record the change;
- `rebutted`: retain the artifact and record concrete contrary evidence;
- `parked`: record the external/product dependency and why implementation can
  or cannot proceed; or
- `unresolved`: stop before implementation approval or `task.py start`.

A parked item that invalidates requirements, design safety, sequencing, or
validation remains blocking. Low-risk non-blocking follow-up may be captured
explicitly, but it cannot silently disappear.

After any `addressed` artifact changes, rerun the host lane and, when initially
available, Codex once against the complete converged artifact set. If a
substantive concern repeats, stop for user judgment. No automatic third round
is allowed.

## Failure matrix

| State | Behavior |
| --- | --- |
| Codex executable/help unavailable | Host review continues; report Codex skipped with setup guidance |
| Codex authentication/runtime failure | Preserve host concerns; mark Codex failed and planning review degraded |
| Codex output is empty or malformed | Treat the lane as failed, never approved |
| Host review finds a blocker | Stop before implementation regardless of Codex result |
| Codex finds a supported blocker | Address it or stop before implementation |
| Only unsupported Codex concerns remain | Rebut with evidence and allow the host gate to decide readiness |
| Material artifact fix after review | Run one regression round |
| Concern repeats after regression | Stop and ask the user; do not loop |

Missing Codex does not block planning by itself because the lane is optional;
the host adversarial review is always required.

## Compatibility and rollback

Non-Claude platforms receive no project rule and no implicit Codex call.
Existing SD commands and Trellis skills keep their public arguments. The
OpenAI Codex Claude plugin may remain installed or be uninstalled independently.

Rollback removes the Claude rule, shared reference, manifest entries, docs,
tests, and matching release metadata. No Trellis or user-level plugin state
needs restoration.

## Validation

- Assert the Claude rule is installed only for Claude and resolves the shared
  contract.
- Assert the contract contains the exact artifact set, trigger exclusions,
  read-only native command, peer-lane concurrency, concern dispositions,
  blocker gate, and one-rerun limit.
- Assert no installed content references plugin cache paths or plugin command
  invocation.
- Preserve generator parity and template/root byte identity.
- Run focused installer/parity tests, fleet candidate validation, and
  `make check`.
