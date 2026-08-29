---
title: Decouple sd:fleet-refresh command from installed-skill resolution
status: done
created: 2026-08-03
---
# PRD — Decouple sd:fleet-refresh command from installed-skill resolution

## Problem

The `sd:fleet-refresh` command (source `templates/.commands/sd-fleet-refresh.md`)
step 1 requires resolving the `sd-fleet-refresh` skill **by name** via the
agent's installed-skill resolver. That skill is **source-only** — deliberately
excluded from the manifest and self-install (for the C-8 security reason: an
unguarded, dangerous, auto-invocable skill), so it is never materialized under
`.claude/skills/`. Consequently `Skill("sd-fleet-refresh")` returns
`Unknown skill: sd-fleet-refresh` in every checkout, including the pack's own.
The command's step 2 then correctly halts — so the fleet-refresh workflow
**cannot start via its intended path at all**.

This is structural, not transient: it persists as long as (a) the skill stays
source-only and (b) the command insists on by-name resolution. The 0.64.0
release (which made the *other* sd skills resolvable) intentionally left
fleet-refresh out, so it does not fix this.

## Goal

Make the command self-contained: it loads the fleet-refresh procedure by
**reading the source-checkout file** `.agents/skills/sd-fleet-refresh/SKILL.md`
directly (the skill is explicitly "source-checkout-only"), instead of resolving
it by name — while preserving every safety rail and the skill's source-only
status.

Because the command surface is generated and the generator injects the
checkout-trust policy by anchoring on the current "Resolve … skill by name"
step-1 phrasing, this task also makes a **surgical generator change** (a
per-command injection anchor) so the reworded step 1 keeps its injected safety
block. The authored edit is in `.github/command-sources/sd-fleet-refresh.md`,
not the generated `templates/**` adapters. See `design.md`.

## Why reading the file is safe (not a security regression)

The source-only decision exists to prevent **auto-invocation** — the resolver
auto-loading the skill body when a consumer checkout is merely opened
(C-8 Threat B). An explicit, user-initiated `/sd:fleet-refresh` command that
reads a known file **after** the checkout-trust classification passes is not
auto-invocation; it is exactly the gated, deliberate action the command already
represents. Same safety posture, no need to ship the skill resolvable.

## Requirements

- R1: In the pack source checkout, `/sd:fleet-refresh` proceeds past step 1
  without a skill-resolution failure, loading the procedure from the checkout
  file.
- R2: The skill remains **source-only** — no manifest/fanout addition, no change
  to install-audit's source-only treatment; `Skill("sd-fleet-refresh")` stays
  unresolvable.
- R3: The checkout-trust policy block (states + reason codes + stop rules) is
  preserved **verbatim**; file loading happens only from a `trusted` state.
- R4: Step-2 safety is preserved, re-pointed at the file: if the source skill
  file is missing / unreadable / empty / ambiguous, stop and report the exact
  blocker.
- R5: Argument passthrough unchanged (bare consumer names, `consumer=...`,
  `no-merge`, `dry-run`, `resume`); rules 4-6 (dirty-skip, concurrency bound,
  gated merges, fail-stop, mandatory final-report format) unchanged.
- R6: The edit is made in the **authored source**
  `.github/command-sources/sd-fleet-refresh.md`; the four generated adapters
  (neutral `templates/.commands/…`, and the claude/gemini/github bespoke
  adapters) regenerate consistently via `make generate` (`.opencode`/`.cursor`
  are neutral-adapter routings, not generated templates, and are not routed for
  this source-only command); parity/drift tests and `make check` pass.
- R7: The self-reference line ("A skill is a project-installed Markdown
  instruction bundle resolved by the agent's trusted installed-skill resolver")
  is corrected so it does not claim a resolution path this command no longer
  uses.
- R8: The generator's checkout-trust policy **injection is preserved** for
  fleet-refresh even though step 1 no longer says "Resolve … skill by name".
  `generate-command-surfaces.py` anchors the injection on that exact phrasing
  (`SKILL_RESOLUTION_ANCHOR`, requires exactly one match), so the command's
  reworded step 1 needs a matching per-command injection anchor; the other 21
  commands' generated surfaces stay byte-identical.
- R9: Because any `templates/**` change trips the release version gate
  (`prepare-release.py` `_is_payload_path`), the change ships as a **version
  bump to 0.64.2** with a CHANGELOG entry, refreshed provenance/dogfood
  manifest, and a regenerated fleet candidate ledger.

## Non-goals

- Shipping `sd-fleet-refresh` as a resolvable/auto-invocable skill, guarded or
  not (the alternative "embed the checkout-trust guard" path — out of scope;
  reintroduces C-8/W1 work).
- Inlining the ~16KB procedure into the command surface (duplication + drift).
- Any change to the fleet controller, `docs/FLEET_ROLLOUT.md`, or consumer set.

## Acceptance criteria

- AC1: From the pack source checkout, invoking the command reaches the rollout
  procedure by reading `.agents/skills/sd-fleet-refresh/SKILL.md`; no
  `Unknown skill` halt (verify by dry-run walkthrough).
- AC2: `Skill("sd-fleet-refresh")` still errors `Unknown skill`; the skill is
  still absent from `manifest.json` and `.claude/skills/`; install-audit green.
- AC3: Diff of the checkout-trust block vs current is empty (verbatim preserved).
- AC4: With the source skill file renamed/removed in a scratch copy, the command
  stops-and-reports per step 2 (no silent proceed).
- AC5: `make check` / `make release-prep` green; command parity/drift and
  surface-generation tests pass; the four generated fleet-refresh adapters match
  the regenerated source and still contain the injected checkout-trust block;
  the other 21 commands' surfaces are unchanged (byte-identical).
- AC6 (corrected): The command is **source-only and not installed to
  consumers** — `manifest.json` has zero fleet-refresh command/skill entries and
  `registry.py` keeps `sd-fleet-refresh` in `SOURCE_ONLY_COMMAND_NAMES`. There
  is no consumer-side run path to preserve; verify the non-installation rather
  than a consumer step-2 halt. (In the pack checkout, a scratch copy with the
  skill file removed exercises the step-2 file-not-found halt — see AC4.)
- AC7: `manifest.json` `version` is **0.64.2**; `prepare-release.py` version +
  changelog gate passes; provenance and the candidate ledger are consistent at
  0.64.2.
