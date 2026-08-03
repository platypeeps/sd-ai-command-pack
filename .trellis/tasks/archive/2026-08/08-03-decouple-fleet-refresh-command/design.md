# Design — Decouple sd:fleet-refresh command from installed-skill resolution

> Reworked 2026-08-03 after adversarial review found the original one-file plan
> infeasible. Four blockers (C-1..C-4) are folded in below; the scope now
> includes a surgical generator change. See "Adversarial review corrections".

## Source of truth (corrected — C-1)

The command surface is **generated**. The authored, editable body is
**`.github/command-sources/sd-fleet-refresh.md`**. `make generate`
(`.github/scripts/generate-command-surfaces.py`) reads that neutral body
(docstring L7; `source = PACK_ROOT / ".github/command-sources/{name}.md"`
L459), **injects the checkout-trust policy** (see below), and writes the
generated adapters in place:

- `templates/.commands/sd-fleet-refresh.md` (neutral adapter, L714)
- `templates/.claude/commands/sd/fleet-refresh.md` (bespoke)
- `templates/.gemini/commands/sd/fleet-refresh.toml` (bespoke)
- `templates/.github/prompts/sd-fleet-refresh.prompt.md` (bespoke)

The generator writes those four template files. The `.opencode` / `.cursor`
command surfaces are **manifest routings** of the neutral adapter
(`_neutral_adapter_entry`, L809/L831), not separately generated templates —
and because fleet-refresh is source-only (no manifest entries), they are not
routed to consumers at all.

`templates/.commands/sd-fleet-refresh.md` (which the original plan named as the
edit target) is a **generated output** and is overwritten by `make generate` —
editing it directly is wrong and would be clobbered. **All body edits happen in
`.github/command-sources/sd-fleet-refresh.md`.**

The `sd-fleet-refresh` **skill** body lives at
`templates/.agents/skills/sd-fleet-refresh/SKILL.md` and is source-only
(`registry.py` `SOURCE_ONLY_COMMAND_NAMES` / source-only skill handling): it is
emitted to `.agents/skills/` in the **pack checkout** (verified present, 16949
bytes) but never to `.claude/skills/` or to consumers.

## The generator coupling that blocks the naive edit (C-4)

`generate-command-surfaces.py` injects the checkout-trust policy by locating a
single **anchor line** and inserting the policy immediately before it
(`inject...`, L549-568). The anchor is a shared regex
`SKILL_RESOLUTION_ANCHOR = ^1\. Resolve (?:the )?` + "`" + `<skill>` + "`" +
` skill by name\b` (L220-222), and the generator **requires exactly one match**
or raises `GenerationError: expected exactly one skill-resolution anchor line`
(L553-557). All 22 command sources currently satisfy this because every step 1
is a "Resolve `<skill>` skill by name" line.

Consequently, rewording fleet-refresh's step 1 away from that phrasing (the
whole point of this task) deletes the anchor and makes `make generate` fail.
The decouple therefore **must** also give the generator an injection point that
survives the reworded step 1.

## Core change

### 1. Generator — per-command injection anchor (new, surgical)

Add an optional `injection_anchor` to `CommandInfo` (`registry.py` L723),
defaulting to `None`. In the injection function, use
`command.injection_anchor or SKILL_RESOLUTION_ANCHOR`. For `sd-fleet-refresh`
only, set a custom anchor regex matching its reworded step 1 (e.g.
`^1\. Load the fleet-refresh procedure by reading ` + "`" + `[^`]+` + "`"). The
other 21 commands keep the default anchor, so their generated surfaces are
**byte-identical** and their drift tests need no change.

- Preserve the exactly-one-match guard against the resolved anchor.
- Keep injecting the policy *before* step 1 (the marker text still reads
  "complete before step 1"), so ordering and content are unchanged.

Alternative considered: broaden the shared `SKILL_RESOLUTION_ANCHOR` to an
alternation accepting both forms (one-line change, no new field). Rejected as
primary because it hardcodes fleet-refresh wording into a "generic" constant;
the per-command field is self-documenting and isolates the special case. Either
keeps the other 21 outputs byte-identical.

### 2. Command body — `.github/command-sources/sd-fleet-refresh.md`

- **Line 7 self-reference (R7):** drop "A skill is a project-installed Markdown
  instruction bundle resolved by the agent's trusted installed-skill resolver";
  state that this command loads the source-checkout skill file directly.
- **Step 1 (L11):** replace "Resolve the `sd-fleet-refresh` skill by name …"
  with "Load the fleet-refresh procedure by reading
  `.agents/skills/sd-fleet-refresh/SKILL.md` from the pack source checkout
  (this skill is source-only and intentionally not resolvable by name)." This
  new wording is exactly what the custom generator anchor matches.
- **Step 2 (L12):** same stop-and-report guard, re-anchored from "that skill" to
  "that file": missing / unreadable / empty / contradictory / needs-unavailable
  tools → stop and report the exact blocker.
- **Step 3 (L13):** "Use that file's contents as the primary instructions …"
  (rest unchanged: fixed rollout pipeline, `docs/FLEET_ROLLOUT.md` authority,
  arg passthrough incl. `resume`).
- Steps 4-6 unchanged.

The checkout-trust block is **generator-injected**, not present in the neutral
source, so R3 ("preserved verbatim") holds automatically — the body edit cannot
touch it.

## Shipping / consumer behavior (corrected — C-2)

The fleet-refresh **command is source-only**: `registry.py`
`SOURCE_ONLY_COMMAND_NAMES = {"sd-fleet-refresh"}` (L1170) and its former
consumer targets are recorded retired (`fleet-refresh-consumer-targets`,
L1300-1307). `manifest.json` has **zero** entries whose source or target
contains `fleet-refresh` (command or skill). Therefore neither the command nor
the skill is installed into consumers — the original design's "the command twin
is installed into consumers, so a consumer run hits step-2 stop-and-report" is
**false** and is removed. There is no consumer-side runtime behavior to
preserve; the operation is pack-checkout-only by construction. (See AC changes
in prd.md: old AC6 is replaced by a manifest/registry non-installation
assertion.)

## Release / versioning (corrected — C-3)

A version bump is **mandatory, not conditional**. `prepare-release.py`
`_is_payload_path` (L217-218) treats **any** changed path under `templates/` as
shipped payload; the regenerated `templates/**` adapters trip the version gate
regardless of the manifest-sources `filesystem_payload_digest` (which, because
fleet-refresh has no manifest entries, would not itself move). So the release
requires, same as any surface change:

- bump `manifest.json` `version` 0.64.1 → **0.64.2** (by hand);
- add the top `CHANGELOG.md` 0.64.2 heading + entry;
- `make sync` to refresh provenance + `.sd-ai-command-pack/manifest.json`;
- regenerate `docs/fleet/candidate-validation.json` (packVersion + payloadDigest
  move once the manifest version changes) via the fleet candidate check.

## What is preserved

- The entire generator-injected **checkout-trust policy** (states, reason codes,
  stop rules, mandatory `checkout-trust:` report line), injected before step 1.
- Rules 4-6 (dirty-skip, concurrency bound / no shared checkout, manifest-order
  gated merges, fail-stop with full stdout/stderr, mandatory final-report
  format).
- Argument grammar (bare names, `consumer=…`, `no-merge`, `dry-run`, `resume`)
  and GitHub authority semantics (owned by the skill body, unchanged).

## Security analysis

Unchanged from the sound part of the original: source-only status defends
against **auto-invocation** on untrusted checkouts (C-8 Threat B). This change
keeps the skill absent from `.claude/skills/` and from `manifest.json`, so the
resolver never auto-loads it. The command reads the file only after the
checkout-trust gate passes, on an explicit user invocation — the same gated,
deliberate action the command already is. Threat surface unchanged; no guard is
embedded or removed. The generator anchor change is mechanical (where to insert
the policy) and does not alter the policy content or its ordering.

## Boundaries / blast radius

- **Touched:** `.github/command-sources/sd-fleet-refresh.md` (body);
  `.github/scripts/generate-command-surfaces.py` + `installer/registry.py`
  (per-command anchor); regenerated `templates/**` fleet-refresh adapters;
  `manifest.json` version; `CHANGELOG.md`; regenerated provenance +
  `.sd-ai-command-pack/manifest.json` + candidate ledger; surface-generation /
  parity tests (a fleet-refresh injection case).
- **Untouched:** the other 21 commands' generated surfaces (byte-identical under
  the default anchor); the fleet controller, `docs/FLEET_ROLLOUT.md`, consumer
  set; install-audit's source-only treatment (no manifest add).

## Alternatives considered

- **Ship the skill resolvable with the checkout-trust guard embedded**
  (original option b). Restores by-name resolution but reopens the C-8/W1
  auto-invocation guard-embed work. Heavier, security-sensitive. Rejected.
- **Inline the ~16KB procedure into the command.** Duplicated across adapters,
  a second copy to keep in sync with the skill. Rejected.
- **Generic `^1\.` step-1 anchor** for all commands (see §1 alt). Viable and
  keeps outputs identical, but broadens shared matching; kept as fallback.

## Rollback

Single feature branch; revert restores by-name resolution and the shared-anchor
generator. No data migration, no manifest state to unwind; version bump is
reversible pre-merge.

## Adversarial review corrections (folded in)

- **C-1** wrong edit target → true source is `.github/command-sources/…`.
- **C-2** command not shipped to consumers → consumer-behavior claim removed.
- **C-3** version bump conditional → mandatory (0.64.2 + ledger).
- **C-4** generator anchor coupling → per-command injection anchor added.
