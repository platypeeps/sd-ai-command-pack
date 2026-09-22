---
name: sd-review
description: Review the exact current diff with local providers and dispose of the findings locally, never posting them.
disable-model-invocation: true
---

# sd-review

Review locally; report findings without posting them to GitHub.
Read the sd-ai-command-pack checkout's `.claude/rules/sd-operator-defaults.md` before selecting recipients.
Use STE-Concise for findings and reports.
Report only the result, decisive evidence, unresolved findings, and next action.

When the deliverable is a finished document, apply
`references/publication-contract.md`: it publishes to the Obsidian
vault and the dashboard's Documents tab by default, and reaches an
outward destination — Notion, Google Drive — only where the user designated that
document for it.

## Before execution

Inspect `sd-review --explain --json` with the intended scope and modifiers.
Check recipients, every automatic fallback, review depth, author exclusions, consent, and spending limits.
Stop before checks or transmission when that plan conflicts with the operator's instructions.
Name the rejecting boundary: selection, review count, pack consent, or runtime approval.
Pack consent does not grant runtime execution approval.

Explanation keeps `status: explained` and adds a `readiness` object.
Its `status` is `ready` or `blocked`; blockers name `code`, `boundary`, `provider`, and `next_action`.
Explanation makes no check, review, or quota call and performs no durable write.
On a ready `codex-json` lane it starts one local process, the skill-suppression probe below.
`runtime_approval: not_observable` means the agent must still satisfy its execution permissions.
A ready result does not prove remote service health or OS isolation.

Read `sd config get sd.external_reviews`.
`configured` permits scoped review context to eligible configured recipients.
Machine `deny` overrides local consent.
A present repository `reviewers` list restricts recipients; an empty list denies all.
An absent key inherits standing policy; malformed local consent stops execution.
Without a grant, stop before transmission.
Installation does not grant consent.

## Scopes

| `--scope` | Subject |
|---|---|
| `worktree` (default) | Uncommitted changes against `HEAD`, including untracked files. |
| `branch` | `merge-base(HEAD, base)..HEAD`; base defaults to `origin/HEAD`, then `main` or `master`. |
| `pr` | Same local resolution as `branch`; no PR-state lookup. Supply `--draft` when applicable. |
| `planning` | The active item's `prd.md`, `design.md`, and `implement.md`. Use `--item NAME` to disambiguate. |

Planning reviews use the *prd and design* point.
Branch review before publication uses *code, before merge*.
Their caps are on those rows in the sd-ai-command-pack checkout's `.claude/rules/sd-planning-adversarial-review.md`.
Do not substitute another diff or copy a cap into this procedure.

## Ordinary review

1. Run the repository's deterministic gate through `sd-check`.
   A failing gate stops the review before provider dispatch.
   Explicit `--reuse-check` can reuse eligible full-check evidence; missing or stale evidence runs the gate normally.
2. Use the routing decision from `sd_route.route`.
   Repository policy determines risk and depth; the registry determines eligible reviewers.
3. Review the exact resolved subject.
   Only consented, enabled, supported, independent reviewers qualify.
   Automatic fallback follows ranked registry order.
   Rate limits, missing executables, authentication failures, failed runs, and timeouts can advance that chain.
   An exhausted chain with insufficient completed coverage fails.
4. Disposition findings locally against the repository's severity floor.
   Preserve each provider's findings and attempt outcome.
   A completed adverse review counts; it does not trigger replacement.
   A clean fallback cannot erase earlier findings.

Reviewing tiers require one completed independent local review.
Skip requires none, subject to planning and challenge minimums.
Unranked, enabled reviewers require explicit `--provider NAME` selection and the same eligibility checks.
Copilot never fills the local slot.
Shipping may request it afterward through the configured `deep` tier or explicit task direction.

The registry uses read-only database controls when available.
A missing database permits file defaults without creating a database.
An unreadable database stops execution instead of ignoring operator controls.

## Flags and results

| Flag | Meaning |
|---|---|
| `--challenge` | Apply an adversarial design-challenge stance. |
| `--item NAME` | Select the active planning directory. |
| `--provider NAME` | Select one registry entry, without fallback. |
| `--explain` | Explain routing and eligibility without dispatch. |
| `--dry-run` | Print invocations without execution. |
| `--draft` | Apply draft routing. |
| `--json` | Emit structured results. |
| `--reuse-check` | Explicitly reuse eligible full-check evidence; otherwise run the deterministic gate. |
| `--timeout SECONDS` | Set the per-provider timeout; default 1800. |

| Exit | Meaning |
|---|---|
| 0 | Successful operation; inspect its operation and coverage before claiming completed review. |
| 1 | A finding meets the severity floor. |
| 2 | Invalid invocation or policy. |
| 3 | Preflight refusal prevents required coverage. |
| 4 | Rate limits exhaust the eligible chain. |
| 5 | Deterministic gate failure or insufficient completed reviews. |

Report completed versus requested coverage, `reviewed_by`, and every failed attempt.
Keep `rate_limited` distinct from `unavailable`.
Malformed or oversized responses do not count as completed reviews.
Retain usable findings, including unknown locations and blockers beyond output limits.

Oversized input returns measured bytes, the existing limit, and the complete path inventory before checks or provider dispatch.
Its suggested split-branch groups are advisory.
They run no review partitions and provide no aggregate approval.
Do not truncate input or count the advisory plan as completed review coverage.

## Local conventions reach the prompt

The ordinary review prompt includes this checkout's `CLAUDE.local.md` block through `local_conventions` (R10-D7).
The receipt reports `local_block_prepended`.
Synthetic provider preflight excludes that block.
When findings contradict a convention, check the supplied wording before assigning blame.
Use `sd-rules --for <path>` for applicable repository rules.

## The `codex-json` entry is subscription-only (R10-D4)

`codex_preflight` requires `auth_mode == chatgpt` and no stored `OPENAI_API_KEY` field (R10-D4).
The child environment removes `CODEX_API_KEY` and `CODEX_ACCESS_TOKEN`.
Never export credentials or invoke the provider directly to bypass this refusal.
Fallback requires separately authorized, eligible entries.

Children receive only `PATH`, `HOME`, `LANG`, `TERM`, `TMPDIR`, actual OS `USER`, and registry-declared variables.
A `codex-json` entry receives the exact `CODEX_HOME` that passed authentication checks.
Environment filtering is not filesystem isolation.
Providers still run as the operator and can read accessible files.

The `claude-json` reader permits only Read, Grep, and Glob tools, with safe mode and no custom MCP servers.
It saves no session.
The `opencode-json` reader attaches that review file with `--file`, runs as a private agent whose permission map is default-deny with a read-only allow-list, so inherited MCP tools and every write, command and fetch are refused without being named, and takes its model from the registry entry, which must pin one.
Its temporary review file contains the exact diff and required untracked or planning contents.
URL providers receive equivalent material in the request.
Neither these arguments nor protocol fixtures prove OS read confinement.

## The skill-suppression key is measured, not assumed

The `codex-json` argv carries `-c skills.include_instructions=false`.
A build that does not know the key ignores it and exits 0.
So `sd-review` probes the binary with its `debug prompt-input` subcommand, offline, at about 1.4 seconds.
Read `codex_skill_suppression` in `--explain --json`, beside `codex_preflight`.
Its `state` is `suppressed`, `unsuppressed`, `unknown`, or `not_probed`.
The probe keeps the entry's start line whole and replaces its final `exec`.
Only a render in the measured shape, a list of `message` items, counts as an answer.
`unknown` means the binary could not be asked; never read it as either answer.
`not_probed` means no `codex-json` process started, and the `reason` says why.
An actual `codex-json` run carries its own measurement in that outcome's `diagnostic.skill_suppression`.
An inert key warns and never refuses; decide whether to review on that binary.

## Policy

Read the repository's `.github/sd-review.json`, or use the built-in policy when absent.
Policy names paths, risk, and severity; it names no provider chain.
Retired `tiers`, `challenge_providers`, and `planning_providers` keys require removal.
The `never_skip` deny-list overrides docs-skip rules.

## setup-github

This is a separate, explicitly requested installation operation, not part of local review.
Modes `minimal` and `guest` cannot install the routing workflow (R10-D5).
Before installation or drift checks, read `skills/sd-review/references/setup-github.md` in the sd-ai-command-pack checkout.
The workflow reports routing only; it requests no reviewer and posts no comment.

## Conditional procedures

Read only the applicable reference in the sd-ai-command-pack checkout:

- Before `--reuse-check`, read `skills/sd-check/references/check-receipts.md`.
  Reuse requires a tracked complete local-only declaration and a clean committed checkout.
  Legacy receipts always rerun; an unchanged HEAD alone is insufficient evidence.
- For URL-provider diagnostics, read `skills/sd-review/references/provider-recovery.md`.
  Synthetic preflight is a provider call, not a code review or an authorization shortcut.
- When judging regression evidence, read `skills/sd-review/references/test-evidence.md`.
  A passing test must fail when its target defect is introduced.

Ship fix verification uses `--scope branch --base <full ancestor SHA> --verify-report <prior JSON>`.
It reviews the committed fix range and current source for prior blockers.
The report must name that exact base; original and fix-author vendors remain excluded.
Changed default-branch code remains within the reviewed tree diff.
This evidence does not authorize replacing a ship receipt with a claimed reviewed head.

## Never

- Never post findings, comments, labels, reviews, or check updates.
- Never review a different subject than the scope selected.
- Never invoke providers directly to bypass routing, authentication, consent, or severity checks.
- Never count an incomplete attempt as completed coverage.
- Never discard adverse findings during fallback.
- Never accept a repository path; cwd determines the checkout (R10-D6).
