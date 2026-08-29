---
title: Surface sd skills to Claude Code Skill resolver (M1)
status: done
created: 2026-08-02
---
# PRD: Add Claude to sd-skill fanout (full platform parity)

## Problem

`/sd:*` slash commands instruct the agent to "Resolve the `sd-<name>` skill via
the trusted installed-skill resolver" and HALT if it does not resolve. In Claude
Code that resolver (the Skill tool) indexes `.claude/skills/`, which holds only
`trellis-*` — **zero `sd-*`**. So `sd:*` commands halt at skill resolution
(`/sd:fleet-refresh` triggered this).

Root cause: Claude is deliberately excluded from `SKILL_FANOUT_PLATFORMS`
(`installer/registry.py:456`) — it is treated as command-first and receives
`.claude/commands/sd/<short>.md` but no `.claude/skills/sd-*`. Every other
skill-fanout platform (`.kiro` skills-only; `.qoder` commands + skills; 10 total)
receives the full sd skill set. Claude is the outlier.

## Goal

Bring Claude to **parity with the other skill-fanout platforms**: add `claude`
to `SKILL_FANOUT_PLATFORMS` so the sd skill set fans out to `.claude/skills/sd-*`
exactly as it does for `.kiro`/`.qoder`/etc — generated from the canonical
sources, shipped to consumers via `manifest.json`, alongside Claude's existing
`.claude/commands/sd/*`. This makes `sd:*` skills resolvable by Claude Code's
Skill tool in the pack AND in every consumer.

## Accepted risk (explicit owner decision — option 3, "drop guard")

Claude Code project skills are **model-auto-invocable by description**. Placing
side-effecting sd skills (9 carry "Standing GitHub authority" — self-authorize
commits/pushes/merges "without another prompt") in `.claude/skills/` creates an
auto-invocable path that bypasses the `/sd:*` command's checkout-trust preflight
(no `SKILL.md` carries that guard; all guards live in the command layer).

The pack **already ships these guardless side-effecting skills to 10 platforms**
via this exact fanout; Claude's command-first exclusion was the lone divergence.
Owner chose **parity, no guard-embed** (option 3): accept the same auto-invoke
exposure on Claude that the other 10 platforms already carry. Guard-embed was
evaluated and **dropped** — a guard inside a skill body cannot stop a checkout
that modified the skill body (Claude loads project skills from the checkout, so
the body is in context before any guard runs; a fork PR could omit the guard),
so it was defense-in-depth at best, not a real close. Command-triggered runs stay
safe (the command guard runs before loading the skill); auto-invoked runs carry
the accepted exposure. Recorded, not silent.

## Scope

In scope:
- Add `claude` to `SKILL_FANOUT_PLATFORMS`, producing `.claude/skills/sd-*` (21
  skills + references; `sd-fleet-refresh` stays excluded — `SOURCE_ONLY`
  everywhere). Generator emits manifest rows; `make sync` materializes files;
  update every gate/test that pins the fanout set or footprint counts (see
  implement.md C-1..C-5, C-14).
- Version bump + CHANGELOG (ships to consumers).

Out of scope:
- **Guard-embed into skill bodies** — evaluated, dropped (owner option 3).
- Surfacing `sd-fleet-refresh` as a skill (source-only everywhere; stays
  command-only — so the original trigger remains command-only, by parity).
- Any change to command semantics, trust-policy text, or the fleet-refresh
  pipeline.

## Constraints

- C1. **Genuine parity.** Claude's sd-skill set + generation + manifest treatment
  match the existing fanout platforms (no bespoke pack-local channel). Claude
  keeps its existing `.claude/commands/sd/*` (ends up commands + skills, like
  `.qoder`).
- C2. **Single source of truth.** `.claude/skills/sd-*` are byte-identical twins
  of `templates/.agents/skills/sd-*`, generated — not hand-authored.
- C3. **Source-only intact.** `sd-fleet-refresh` remains excluded from fanout and
  manifest on Claude as elsewhere; the drift check's `generated_registry_mismatch`
  must not fire.
- C4. **Green gates.** `make generate` idempotent, `make sync` propagates,
  `make check` exits 0 (parity, closure, audit, surface-drift, candidate ledger).
- C5. **Consumer parity verified.** A fresh consumer install now DOES produce
  `.claude/skills/sd-*` (this is the intended change), matching other platforms.

## Acceptance criteria

- AC1. `claude` is in `SKILL_FANOUT_PLATFORMS`; `make generate` adds
  `manifest.json` rows for `.claude/skills/sd-*` (21 non-source-only sd skills +
  references); `make sync` materializes those files into this repo, byte-identical
  to sources, resolvable by the Skill tool.
- AC2 (C-5, C-10). Resolution verified same-session after sync WITHOUT executing
  any side-effecting workflow:
  (a) `Skill("sd-help")` (read-only) resolves and can be invoked;
  (b) a side-effecting sd skill (e.g. `sd-ship`) is confirmed **resolvable** by
  inspection only — the resolver lists it / its `SKILL.md` is present with valid
  frontmatter. Do **NOT** invoke it (invocation = commit/push/merge authority);
  (c) a `/sd:*` command run proceeds past its skill-resolution step.
  Fresh-session is the fallback for (a),(c).
- AC3. `sd-fleet-refresh` has **no** `.claude/skills/` entry and no manifest row
  (SOURCE_ONLY intact); drift check green.
- AC4. Consumer install parity: fresh `install.py` into a temp consumer produces
  `.claude/skills/sd-*` matching the `.kiro`/`.qoder` sd-skill set.
- AC5. `make check` exits 0; version bumped + CHANGELOG entry added.

## References

Research notes that lived beside this item's Trellis record and were not carried
into docs/work. Recover the bodies from git history under `.trellis/tasks/archive/2026-08/08-02-claude-sd-skill-resolution`:

- research/localonly-skill-mechanism.md
- research/skill-readonly-classification.md
- review-ledger.md
