# Planning adversarial review — concern ledger

Task: 08-09-thin-machine-installer. Contract:
`.claude/sd-ai-command-pack/planning-adversarial-review.md`.
Pre-edit prd.md hash:
`8c3998d67335f5b1e30c8542024daec906780aebf4710b4beba072bce7e618d5`.
Two remediation rounds used (contract maximum).

## Round 1 (host + Codex CLI lane)

Host: C-1 (script-reference self-containment in machine payload) —
resolved: generate-time rewrite + residue/closure gates.
Codex: 10 blocking + 2 non-blocking (C-2..C-13), all resolved by full
rewrite of design.md + implement.md. Highlights: existing `installer/`
package collision (machinescope.py joins it instead of new package);
probe-gated provisional flips; codex re-disposition to repo-native;
plan-before-apply conflict model; receipt-trust validation; canonical
payloadDigest shared with plugin generator. Raw output:
scratchpad/codex-review.md (session-scoped).

## Round 2 (host + Codex CLI lane) — final round

Host: no new blockers; two fail-closed residuals (headless probe
feasibility; XDG root drift) — now explicit in design (headless-
infeasible surface stays provisional; family-relative resolution
documented).

Codex round 2 (scratchpad/codex-review-r2.md), verified against repo
before disposition:

- C-14 (blocking) retainVendoredFor not executable from parent
  migration model — VERIFIED (parent design deletes all but
  repo-native/consumer-config; no consumer declares codex/pi).
  RESOLVED: executable detection rule = consumers.json `platforms` ∩
  `retainVendoredFor`; parent design deletion bullet + resweep
  marker-grep updated in Step 1 before implementation consumes the
  rule.
- C-15 (blocking) shared surface flip gated on command probes only —
  VERIFIED. RESOLVED: three per-surface probes; shared flips only on
  its own opencode skills-autoload probe; fail-closed otherwise.
- C-16 (blocking) interrupted-run recovery adopts byte-identical
  unowned files — VERIFIED (owned-current included receipt-absent
  payload matches). RESOLVED: intent journal
  `machine-install.intent.json` written before first write, deleted
  after receipt commit; adoption only via matching journal entry;
  otherwise unowned/refuse. Test added for the adoption hole.
- C-17 (blocking) docs/SD_AI_COMMAND_PACK.md relocated without
  reference rewrite — VERIFIED (sd-full-check SKILL.md:82,94).
  RESOLVED: rewrite pipeline gains the doc pattern; residue + closure
  gates cover both patterns.
- C-18 (blocking) --force backups unrecorded, remove cannot restore —
  VERIFIED (receipt schema had no backup field). RESOLVED: receipt
  `files[].backup {path, digest}`; remove restores digest-verified
  backups; manual acceptance reworded to the precise contract; forged
  backup paths added to malicious-receipt tests.
- C-19 (non-blocking) sd-status undefined on plugin discovery failure
  — RESOLVED: any discovery failure -> pluginVersion `unavailable`;
  machine state none/installed/invalid; separate comparison field
  current/skew/unknown; tests per failure shape.

Codex round 2 also confirmed the 776 -> 777 count transition is
consistent with the current inventory.

## Status

All blocking concerns resolved in-artifact; none outstanding.
Implementation unblocked.
