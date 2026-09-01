---
title: Review the Gemini and Codex retirements and their impact on distribution/install
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-23
---
# Review the Gemini and Codex retirements and their impact on distribution/install

## Problem

Two upstream retirements landed in Homebrew and were acted on locally on
2026-08-23; this repo distributes platform files for both ecosystems and has
not yet reacted:

- **Gemini CLI is going away.** The `gemini-cli` formula is deprecated
  ("not supported upstream") and will be **disabled on 2026-12-18**. Google
  folded the CLI into Antigravity; Homebrew's stated replacement is the
  `antigravity-cli` cask, which installs an `agy` binary — it does NOT
  provide a `gemini` command. Anything this repo installs or documents for
  the `gemini` CLI stops working for fresh installs after the disable date.
- **The Codex desktop app is discontinued.** The `codex-app` cask is
  deprecated ("discontinued upstream", disabled 2027-07-12) and has been
  uninstalled locally. The **codex CLI is unaffected** — the `codex` formula
  is alive and maintained. Only desktop-app assumptions are stale.

## Requirements

R1. Inventory every place this repo's distribution/install path targets the
    gemini CLI or the codex desktop app (configs shipped, manifests,
    registry/platform enumerations, install docs, CI).

R2. Decide the gemini strategy and record it: retarget to Antigravity
    (`agy`), keep-until-broken with a documented sunset, or drop the
    platform. Include what happens to already-installed users.

R3. Confirm the codex CLI path is desktop-app-free: nothing in install or
    docs should require or mention the retired `codex-app`.

R4. Apply the resulting changes (or file follow-up tasks per change) so a
    fresh install after 2026-12-18 does not reference a formula Homebrew
    refuses to install.

## Context

Pack-specific surfaces to review:
- `.gemini/settings.json` shipped in the repo — who consumes it after the
  gemini CLI goes away, and does Antigravity's `agy` read it at all?
- `generated/registry-snapshot.json`, `.sd-ai-command-pack/manifest.json` and
  `provenance.json` — platform lists that may enumerate gemini/codex targets.
- `plugins/sd/bin/sd-ai-command-pack-shell-lib.sh` and
  `machine-payload/` scripts — codex references there are about the codex
  CLI (still supported); confirm none assume the retired desktop app.
- Install/marketplace docs: anywhere that tells a user to install the pack
  for Gemini needs a decision (drop, or retarget to Antigravity).

## Acceptance criteria

- [ ] Written inventory of gemini/codex-desktop touchpoints in this repo
- [ ] Gemini decision recorded (retarget / sunset / drop) with rationale
- [ ] Codex CLI path confirmed free of desktop-app assumptions
- [ ] Changes applied or follow-up tasks filed for each touchpoint
