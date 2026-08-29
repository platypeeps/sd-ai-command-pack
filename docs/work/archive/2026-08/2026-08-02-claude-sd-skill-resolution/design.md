# Design: Add Claude to sd-skill fanout (full parity)

Grounded in `research/localonly-skill-mechanism.md` and the live registry
inspection recorded below.

## Chosen mechanism

Add `"claude"` to `SKILL_FANOUT_PLATFORMS` (`installer/registry.py:456`). Nothing
else in the generation pipeline needs new code — Claude joins the existing
skill-fanout machinery that already serves 10 platforms.

### Why this is the whole mechanism

The generator has **two independent surface axes**:

- **Command surface** — emitted if `command_kind` is set (neutral adapters) OR
  the platform is in `BESPOKE_ADAPTER_PLATFORMS = ("claude","gemini","github")`.
  Claude gets its `.claude/commands/sd/<short>.md` via the bespoke branch
  (`generate-command-surfaces.py:799-808`).
- **Skill surface** — emitted for every platform in `SKILL_FANOUT_PLATFORMS`:
  `_platform_skill_entry` (`:736`) writes `{directory}/skills/{name}/SKILL.md`
  and `_skill_reference_entries` (`:747`) writes `{directory}/skills/{name}/
  references/*`, both driven purely by `PLATFORM_REGISTRY[platform].directory`.

These axes are orthogonal. `_platform_skill_entry` never reads `command_kind`, so
`command_kind=None` on Claude is irrelevant — `kiro` and `reasonix` already prove
a `command_kind=None` platform fans out skills cleanly (they are skills-only).
Adding Claude to the fanout tuple emits `.claude/skills/sd-*` **alongside** its
existing bespoke commands, making Claude qoder-shaped (commands + skills).

Live registry confirmation (recorded 2026-08-02):

| platform | command_kind | in fanout | surface |
|---|---|---|---|
| kiro | None | Y | skills-only |
| reasonix | None | Y | skills-only |
| qoder | command | Y | commands + skills |
| **claude (today)** | None (bespoke) | **N** | **commands-only** |
| **claude (after)** | None (bespoke) | **Y** | **commands + skills** |

### Emission path (no new code)

For every command whose `target_families` includes `claude` (all sd commands
except `SOURCE_ONLY_COMMAND_NAMES`), `derived_manifest_entries` (`:838-843`)
already iterates `SKILL_FANOUT_PLATFORMS` guarded by `if platform in
target_families`. Claude is already in each command's `target_families` (its
bespoke command entry is emitted at `:799`), so once Claude is in the fanout
tuple the loop emits its skill + reference manifest entries automatically.
`sd-fleet-refresh` is in `SOURCE_ONLY_COMMAND_NAMES` and is skipped by
`generate_manifest_text` (`:890`) on every platform — so it gains no Claude
skill (parity preserved: it stays command-only everywhere).

Result set: the 21 non-source-only sd skills gain a `manifest.json` row for
`.claude/skills/sd-<n>/SKILL.md` plus their `references/*`, exactly like the
`.kiro`/`.qoder` skill rows. **These are manifest entries, not files placed in
the pack tree by generation** — `.qoder`/`.kiro` directories do not exist in this
repo at all; their skill copies live only in consumers after install. The pack's
own `.claude/` is populated because the pack self-installs its manifest via
`make sync` (that is why `.claude/commands/sd/*` are present and git-tracked).
So the file materialization path is:

- `make generate` → adds the `.claude/skills/sd-*` rows to `manifest.json`
  (source = `templates/.agents/skills/sd-<n>/…`);
- `make sync` (`install.py . --force`) → materializes `.claude/skills/sd-*` into
  **this** repo, byte-identical to source, resolvable by the Skill tool here;
- consumer `install.py` → materializes the same files in each consumer.

(By contrast, `.claude/skills/trellis-*` are hand-committed from `trellis init`
and carry **no** manifest row — that is the pack-local channel we are *not*
using.)

### No target collision

`.claude/skills/sd-<n>/SKILL.md` (new) vs `.claude/commands/sd/<short>.md`
(existing) are distinct manifest targets. `generate_manifest_text`'s duplicate
detector (`:896-904`) stays satisfied.

## Accepted risk — parity, guard dropped (owner option 3)

Claude Code project skills are **model-auto-invocable by description**. The
`/sd:*` command layer performs checkout-trust classification before loading a
skill; **no `SKILL.md` carries that guard** (all 22 sd commands do; zero skills
do — `test_surface_generation.py:496` for the 9 authority skills). So a
side-effecting sd skill in `.claude/skills/` can be auto-invoked, bypassing the
command preflight. This exposure is **not new** — the same guardless skills
already ship to 10 platforms via this fanout.

**Guard-embed was evaluated and dropped** (round 2, C-8): a guard inside a skill
body cannot stop a checkout that MODIFIED the skill body. Claude loads project
skills from the checkout, so the body is in context before any guard line runs; a
fork PR could simply omit the guard. It would protect only the "canonical skill,
untrusted data checkout" case, not the "attacker-modified skill file" case — the
latter needs a guard that runs *before* skill resolution, i.e. the command/host
layer, which is not something the pack can add inside a skill. Owner accepted
**parity without guard-embed**: command-triggered runs stay safe (command guard
runs first); auto-invoked runs carry the same accepted exposure the other 10
platforms already have.

## Gate / test changes

Adding a platform to the fanout tuple shifts several pinned expectations. All
are byte-stable list/set updates, no logic changes:

1. **`tests/test_surface_generation.py`** — any assertion enumerating
   `SKILL_FANOUT_PLATFORMS` or the per-skill fanout target set (e.g. "each sd
   skill fans out to exactly these directories") must add `.claude/skills/…`.
   The 9-authority-skill assertion (`:496`) is unaffected (source-side).
2. **`tests/test_help_command.py`** — if it pins the platform/skill surface
   counts, update to include Claude's new skill copies.
3. **`.github/scripts/check-command-surface-drift.py`** — `SKILL_PUBLIC_ROOTS` /
   `PUBLIC_PATH_PATTERNS`: `.claude/skills/sd-*` must now be recognized as a
   fanned-out public root (it becomes manifest-backed). Confirm
   `generated_registry_mismatch` stays green (source-only set unchanged).
4. **`.github/scripts/generate-command-surfaces.py`** — no code change; but any
   inline expectation/comment listing fanout platforms should be updated for
   accuracy.
5. **`scripts/sd-ai-command-pack-surface-check.py`** — `.claude/skills/sd-*` now
   arrive as **manifest-backed installable** nodes (not pack-local), so
   `_node_kind` classifies them as `installable` with no change; `_graph` builds
   them from the new manifest rows automatically. Verify closure is clean (no
   orphan / no missing source).
6. **`install-audit` / `pr-body-scope.py`** — `.claude/skills/sd-*/**` already
   listed pack-owned in `pr-body-scope.py:142`; `PACK_FILE_PATTERNS` may need
   `.claude/skills/sd-*` if audit must scan the new shipped files (verify).
7. **`tests/test_generated_parity.py`** — the standard twin-parity assertion now
   covers `.claude/skills/sd-*` automatically once manifest-listed; confirm
   `make generate --check` fails on any drift and prunes removed twins (same as
   every other fanout dir — no Claude-specific code).

## Consumer impact (intended)

Fresh `install.py` into a consumer now materializes `.claude/skills/sd-*` (21
skills + refs), because they are manifest rows. AC4 verifies this against the
`.kiro`/`.qoder` sd-skill set. This is the goal, not a regression — it is what
"full parity, ship to consumers" means. Version bump + CHANGELOG required
(consumer-visible surface change).

## Risks

- **R1 resolver fit** — LOW. Every sd `SKILL.md` already carries valid
  `name`+`description` frontmatter (same shape as resolving `trellis-*`). Claude
  Code live-loads `.claude/skills/` additions in-session, so `Skill("sd-help")`
  is verifiable same-session after **`make sync`** (generation adds only manifest
  rows; sync materializes the files) — C-16; fresh-session is the fallback.
- **R2 auto-invoke exposure** — **accepted** (owner option 3, guard dropped).
  Side-effecting sd skills become auto-invocable without a trust gate, same as the
  10 existing fanout platforms. Command-triggered runs remain gated by the command
  preflight. Not mitigated in this task by design.
- **R3 twin drift** — LOW, mitigated by the existing parity/generate --check gate
  that already covers all fanout dirs.
- **R4 pinned-test churn** — LOW; mechanical set/count updates (gates §1-7).

## Rejected alternatives

- **Pack-local `.claude/skills/sd-*` (manifest-omitted) channel** — the prior
  design. Rejected: the owner chose full consumer parity, not a Claude-only
  dev-tree surface. A bespoke pack-local channel would need a new node kind in
  surface-check, new drift recognizers, and asymmetry with every other platform —
  more code for a narrower outcome.
- **Read-only allow-list only** (`sd-check`/`sd-help`/`sd-status`) — rejected:
  leaves `sd:*` side-effecting commands unresolved on Claude, diverging from the
  10 platforms that surface the full set. Owner chose parity.
- **Guard-embed into skill bodies** — evaluated across two review rounds and
  **dropped** (owner option 3, C-8): an in-skill guard cannot stop a checkout that
  modified the skill body (the body loads before the guard runs), so it is
  defense-in-depth at best, not a real close; only the command/host layer closes
  the auto-invoke gap. Parity-without-guard is the chosen approach.

## Rollback

Single-line revert of the `SKILL_FANOUT_PLATFORMS` tuple + `git checkout` the
regenerated `.claude/skills/sd-*`, `manifest.json`, and updated tests, then
`make generate`. Because the change is manifest-backed, revert also removes the
consumer rows — no lingering pack-local tree to `git rm` (unlike the rejected
pack-local design).
