# Planning adversarial review — the native Codex lane

This appendix extends section 2 of the shipped planning contract,
[`../.claude/sd-ai-command-pack/planning-adversarial-review.md`](../.claude/sd-ai-command-pack/planning-adversarial-review.md).
That contract is the entry point; read it first. This file adds a second
review lane on top of it.

**This document is not part of the shipped payload.** The installer renders
`skills/**/SKILL.md` and nothing else, so a file under `docs/` reaches no
consumer and applies only to planning work done in this repository. That is deliberate:
the lane it describes invokes the `codex` CLI, and a shipped file saying so
registers as undeclared codex usage in every consumer that never declared the
platform — which is all of them. Keeping the lane here removes that marker
without weakening the detector or degrading the contract.

The consequence is a real capability loss for consumers, accepted on
2026-08-11: developers there whose machines have the `codex` CLI on PATH ran
this lane until now and no longer will. There is no per-consumer opt-in to
restore it; the lane is a practice of the pack repository alone.

## The lane

On Claude Code, capability-check the optional native Codex lane with both
`command -v codex` and `codex exec --help`. When both succeed, launch one
review-only `codex exec` command in a separate background Bash task before
starting the host review. Use:

- `--cd <repo-root>`
- `--sandbox read-only`
- `--ephemeral`
- **`< /dev/null`** — required; see below
- a focused prompt naming the active task directory and the changed planning
  artifacts, requiring evidence-backed concerns only and forbidding writes

**Redirect stdin from `/dev/null`.** In a background Bash task stdin is not a
TTY, so `codex exec` treats it as piped input, prints `Reading additional input
from stdin...`, and blocks forever waiting for a write that never comes. It
consumes no CPU while hung — observed at 0:00.07 CPU over 29 minutes — so it
looks like a slow review rather than a stuck one, and it produces no output at
all because output is fully buffered until the run ends. Without the redirect
this lane cannot complete in the background task this section requires, and the
failure mimics a timeout. With it, a normal review finishes in roughly 5-10
minutes.

Do not diagnose this as a missing CLI, an auth problem, or an oversized prompt.
A foreground `codex exec` succeeds under the same configuration, so a working
foreground probe does not clear the background lane.

Consider `-o <file>` (`--output-last-message`) to capture the final review text
directly instead of parsing it out of the full transcript.

Retain the task ID and collect the result with `BashOutput` even if the host
lane finds blockers. The host and Codex reviews should overlap; do not wait for
Codex before beginning the host review.

This lane uses the installed `codex` CLI directly. Do not inspect, install,
patch, or invoke the OpenAI Codex Claude plugin, its cache, a companion script,
or `/codex:adversarial-review`.

If the executable is missing, the help probe is incompatible, authentication
is unavailable, or execution fails, report `Codex: skipped` or `Codex: failed`
with the concrete reason. Continue the host review and planning convergence.
Never describe the skipped or failed lane as approval, and never make the
plugin a fallback dependency.

Before reporting `Codex: failed` for a run that hung or returned nothing, check
the stdin redirect above and check the process's accumulated CPU time. A hang at
near-zero CPU is the stdin trap, not a failed review — rerun it correctly rather
than degrading the convergence to a single lane. Reporting a lane failed when it
was never actually invoked correctly is worse than reporting it skipped: it
records an absent second opinion as an attempted one.

## How this lane changes the host contract's sections 3 to 5

The host contract stands alone wherever this appendix is absent, which is
everywhere but this repository. Here, these amendments apply:

- **Section 3, concern disposition.** The ledger merges and deduplicates both
  lanes rather than recording one.
- **Section 4, convergence limit.** A remediation round reruns a fresh Codex
  review alongside the host review, and the "two lanes in material conflict"
  stop condition is reachable.
- **Section 5, completion report.** Report Codex status as completed, skipped,
  or failed. A consumer omits that line rather than reporting it skipped: a
  lane the consumer never had was not skipped, it was never available.
