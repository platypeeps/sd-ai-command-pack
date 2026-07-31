# Design — classify the shipped script surface, then document it

## Scope boundary

`docs/SD_AI_COMMAND_PACK.md` and its template mirror, `CONTRIBUTING.md:135`, and
one new coverage gate. No script is renamed, moved, or removed — a manifest target
path is a compatibility event under the very sentence this task is reconciling.

## The contradiction

`CONTRIBUTING.md:135` makes "shipped script paths and CLIs" stable public
surface. Three of 26 manifest `scripts/` targets appear nowhere in the installed
guide, so the repo promises compatibility on interfaces it never describes. Both
statements cannot stand.

## Classification is the design, not a preliminary

The three gaps are three different cases, and a single "write three doc sections"
fix is wrong for at least two:

| target | shape | reachable by | classification |
|---|---|---|---|
| `pr-eligibility.py` | argparse CLI | operator; referenced from `sd-housekeeping/SKILL.md` | **public** — documented in a skill but not the guide |
| `review-local.py` | argparse CLI, 2,232 lines | only `review.py:34` (`LOCAL_SCRIPT`) | **internal** — a stage of routed `sd-review`, not an entry point |
| `sd_ai_command_pack_lib.py` | shared library + `__main__` at `:704-705` | imported by 31 files; CLI dispatches `_cache_env_main:673` | **internal** — documenting it as an operator tool misrepresents it |

If any target is internal, `CONTRIBUTING.md:135` must gain an internal category
(PRD R2). The alternative — declaring all 26 public and documenting all 26 — is
coherent but commits the pack to compatibility on a 2,232-line internal stage and
a library `__main__`. **Recommendation: add the internal category.**

## The name collision is the sharp half

`scripts/sd-ai-command-pack-review-local.sh` (771 lines) and
`scripts/sd-ai-command-pack-review-local.py` (2,232 lines) are **both** shipped
manifest targets (`manifest.json:264-265`, `:271-272`), both live, and **neither
invokes the other**. The `.sh` is documented in six places
(`docs/SD_AI_COMMAND_PACK.md:121`, `:549`, `:550`, `:895`, `:2179`;
`README.md:621`); the `.py` is documented nowhere. A reader who finds
`review-local.py` in the tree has no way to learn which one `sd-review` actually
runs — it runs the `.py`.

Renaming would be the clean fix and is out of scope: it moves a manifest target
path. The guide must instead name both and say which is which (PRD R4).

## The gate is the durable half

No doc-coverage gate exists. A *test*-coverage gate does
(`.github/scripts/check-shipped-script-coverage.sh:50`, which lists
`review-local.py 70`), which is why the absence is easy to miss — the script
surface looks gated. Without a doc gate this finding reopens on the next added
script.

Shape: enumerate `scripts/` targets from `manifest.json`; assert each is either
named in `docs/SD_AI_COMMAND_PACK.md` or present on an explicit internal
allowlist. **The allowlist is the R1 classification made executable** — that is
the point, not an escape hatch. Adding a script then forces a deliberate choice
instead of silent omission.

Follow the existing gate's placement and invocation style rather than inventing a
new lane.

## Compatibility and rollout

Docs-only plus one gate. No runtime behavior changes. `CONTRIBUTING.md:135` is
*narrowed*, which relaxes a promise rather than tightening one, so no consumer
can be broken by it. Template parity applies — the mirror moves in the same
change (PRD R6), and the symlink-root passage sits at `:1065` in both copies.

Rollback is a plain revert.

## Risk

The classification can be wrong in one direction that matters: marking something
internal that operators actually invoke silently removes a compatibility promise
they were relying on. `pr-eligibility.py` is the one at risk — it is already
referenced from a shipped skill, which is weak evidence of operator use. Default
it to public.

## Classification record (implement.md step 1, recorded 2026-07-31)

Enumerated 26 manifest `scripts/` targets; guide grep confirms exactly 3
basenames absent from `docs/SD_AI_COMMAND_PACK.md` (matches PRD Evidence).

**Public — documented (23).** Every target already named in the guide keeps its
public classification; the guide entry is the compatibility contract. This
includes the two support libraries the guide describes as libraries
(`sd-ai-command-pack-shell-lib.sh` at `:89`, `sd_ai_command_pack_fleet_lib.py`
at `:106`): they are documented as shared internals, and that description is
the stable surface.

**Public — undocumented (1).** `sd-ai-command-pack-pr-eligibility.py`: argparse
CLI ("Evaluate exact-head pull-request eligibility without mutation", flags
`--input/--repo/--branch/--dependency-pr-number/--remote/--default-branch/
--finish-work-receipt/--github-repository/--format`), referenced from
`sd-housekeeping/SKILL.md:74` as an operator-visible step. Gets a guide entry.

**Internal — allowlisted (2).**
- `sd-ai-command-pack-review-local.py`: pipeline stage invoked only by
  `sd-ai-command-pack-review.py` (`LOCAL_SCRIPT`); not an operator entry
  point. Its manifest path stays stable; its CLI does not become public
  surface.
- `sd_ai_command_pack_lib.py`: shared library imported by 31 files; its
  `__main__` dispatches the private cache-env helper. Documenting it as an
  operator tool would misrepresent it.

Consequence: CONTRIBUTING gains the internal category (R2); the doc-coverage
gate's allowlist is seeded with exactly the two internal targets.
