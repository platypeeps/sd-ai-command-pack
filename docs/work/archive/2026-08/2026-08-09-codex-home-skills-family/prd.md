---
title: Retire the codex vendored-retention carve-out on probe evidence
status: done
created: 2026-08-09
branch: feat/retire-codex-vendored-retention
---
# PRD: Retire the codex vendored-retention carve-out on executed probe evidence

The task directory slug (`codex-home-skills-family`) predates this rescope. The
original PRD proposed a sixth machine destination family for `$CODEX_HOME/skills`.
The probe that was supposed to gate that work passed — and then showed the family
is unnecessary, because Codex already reads the destination family the pack ships.
`research/codex-skills-resolution-probe.md` holds the executed evidence.

## Goal

`docs/fleet/surface-partition.json` declares
`platforms.shared.retainVendoredFor: ["codex", "pi"]`. Its stated justification
for the `codex` entry is false: Codex does read `$HOME/.agents/skills`, which is
exactly where the machine installer's `agents-skills` family lands. Remove the
`codex` entry, correct the claims that justified it, and stop the conversion
tooling from raising a blocker whose remedy now changes nothing.

## Background: what the probe established

Executed against `codex-cli 0.147.0` using `codex debug prompt-input`, which
renders the model-visible prompt input list as JSON. Full command lines, decisive
output, and negative controls are in `research/codex-skills-resolution-probe.md`.

1. Codex resolves user-scope skills from `$CODEX_HOME/skills` (negative control 0
   matches, positive 1). This is what the original PRD asked for.
2. Codex **also** resolves `$HOME/.agents/skills`, unconditionally. Probe 1's
   negative control — scratch `CODEX_HOME`, no skills directory, CWD `/tmp` with
   no `.agents` — still listed 38 skills rooted at `$HOME/.agents/skills`,
   including the 19 `sd-*` skills the machine installer placed there.
3. That resolution follows `HOME` and is compiled in. Redirecting `HOME` as well
   moved it: the marker under the scratch `HOME` resolved and `$HOME/.agents`
   disappeared from the output. `~/.agents`, `~/.agents/skills`, and `~/.agents/bin`
   are real directories, not symlinks, and the scratch `CODEX_HOME` held no config.

The machine receipt (`~/.local/state/sd-ai-command-pack/machine/machine-receipt.json`,
schemaVersion 1, 115 entries) records `agents-skills: 49`, `agents-bin: 26`,
`agents-docs: 2`. Those 77 rows are exactly what `retainVendoredFor` retains per
declaring consumer. The `agents-bin` half resolves too, because installed skill
bodies are path-rewritten to absolute machine paths
(`~/.agents/skills/sd-status/SKILL.md:47` invokes `~/.agents/bin/...`).

## Requirements

1. **Drop `codex` from the retention list.**
   `PLATFORM_RETAIN_VENDORED_FOR["shared"]` becomes `("pi",)`. `pi` was not
   probed and no claim is made about it; it stays, and the retention mechanism
   stays live through it.

2. **Keep `codex` dispositioned `repo-native`, for the correct reason.**
   The disposition is right and the recorded rationale is not. `.codex/**` rows
   have no machine destination family — `family_for_target(".codex/config.toml")`
   returns `None` and the payload build fails closed — and Codex reads project-root
   `.codex/`. Neither of those is "never reads `~/.agents/skills`". Correct the
   comment without changing the disposition.

3. **Correct every recorded claim the probe falsifies.** At minimum
   `.github/scripts/partition-surfaces.py` (the codex disposition comment and the
   retention comment) and `scripts/sd-ai-command-pack-thin-resweep.py:659-704`.
   Enumerate the rest by search rather than from this list. Shipped `CHANGELOG.md`
   history is a record of what was released and is not rewritten; a new entry
   supersedes it.

4. **Stop the undeclared-codex marker from blocking.** With retention gone,
   declaring `codex` retains nothing, so the blocker demands a declaration that
   changes nothing — the exact disqualifier `thin-resweep.py:691-694` already
   applies to the empty-directory case. Codex marker hits owned by the consumer
   become advisory; `pi` keeps blocking; pack-defect detection is preserved for
   both.

5. **Regenerate the derived artifacts.** `docs/fleet/surface-partition.json` and
   `plugins/sd/machine-payload/partition.json` are generated; `--check` byte-compares
   them and must pass.

6. **Update the spec.** `.trellis/spec/backend/manifest-and-filesystem.md:125-133`
   documents `retainVendoredFor` and its detection rule.

## Acceptance criteria

- Probe evidence persisted with command lines, decisive output, and negative
  controls. *(Done: `research/codex-skills-resolution-probe.md`.)*
- `docs/fleet/surface-partition.json` emits
  `platforms.shared.retainVendoredFor: ["pi"]`; `partition-surfaces.py --check`
  exits zero against both generated artifacts.
- **The load-bearing one:** for a consumer whose declared platforms differ only by
  `codex`, the two conversion plans are identical — same keep set, same removal
  set, same counts. A test asserts this directly rather than pinning a row count.
- `installer/conversion.py`'s `classify_target` and `expected_residual_targets`
  still agree in both directions on a retained target, via `pi`. The R17-C1
  regression test survives the change rather than being deleted with `codex`.
- A consumer with undeclared codex usage is not blocked; the same consumer with
  undeclared `pi` usage still is. Pack-defect classification is unchanged for both.
- No claim that Codex cannot read `~/.agents/skills` survives in live code, specs,
  docs, or active task artifacts. Shipped `CHANGELOG.md` entries and
  `.trellis/tasks/archive/**` are historical records of what was true when
  written and are **not** rewritten.
- `make check` passes.

## Non-goals

- Adding the `$CODEX_HOME/skills` destination family. Probe 1 says it would work;
  it would duplicate reach the `agents-skills` family already has. Requirement 1
  is what unblocks the canaries. If a future need appears, the probe evidence for
  it is already recorded.
- Any claim about `pi`. Probing it is separate work.
- Any consumer-repository mutation. This task changes the pack only.

## Risks

- **Fail-open direction.** Removing a blocker means a wrong conclusion strands
  real Codex users silently rather than loudly. Probe 3 sharpens this: Codex
  merges project-root `.agents/skills` with `$HOME/.agents/skills`, so the
  vendored copy **is serving Codex today**. Conversion does not make it
  redundant, it transfers the job to the machine copy. The canary conversion
  independently requires machine scope `installed` before the first consumer
  mutation, and that precondition is the actual handoff — not a formality.
  Converting on a machine without the pack installed loses the skills silently.
- **Codex version dependence.** `$HOME/.agents/skills` resolution is behavior of
  `codex-cli 0.147.0`. The pack cannot pin a user's Codex version, and a
  regression upstream would strand skills. Accepted, not mitigated; recorded here
  so a future failure is diagnosable.
- **Retention coverage.** Deleting the only exercised retention platform would
  silently retire a tested mechanism. `pi` remains, and the acceptance criteria
  require the existing retention tests to keep executing through it.
- **`packDefects` still blocks, and this task does not change that.**
  `decide()` builds `blocked` from `blockers`, `packDefects`, `missingFiles`, and
  a dirty worktree; `advisories` and `scheduled` do not contribute. Requirement 4
  moves only *consumer-owned* codex hits to `advisories`. A consumer whose
  `.codex/` is entirely **pack-owned** routes to `packDefects` and stays blocked
  — correctly, since that is the pack having shipped files for a platform the
  registry omits, which retention never had anything to do with. So this task
  clears the codex blocker for the consumer-owned case only; whether that is
  sufficient for any given canary is measured during the canary conversion, not
  assumed here.

## Downstream

`.trellis/tasks/08-10-thin-canary-conversion` is blocked partly on this. All three
canaries (`rwbp-coordinator`, `loadsmith`, `hoa-manager`) reported *runs codex*.
No consumer's registry row declares `codex` or `pi` today, so retention is inert
and this change keeps it inert instead of activating it. That task's own PRD edits,
its R17 codex-declaration gate, and its cohort authorization stay its own work.

## References

Research notes that lived beside this item's Trellis record and were not carried
into docs/work. Recover the bodies from git history under `.trellis/tasks/archive/2026-08/08-09-codex-home-skills-family`:

- research/codex-skills-resolution-probe.md
