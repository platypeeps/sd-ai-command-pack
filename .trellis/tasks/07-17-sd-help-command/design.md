# Design: Discoverable sd-help command

## Overview

`sd-help` is an agent-driven, read-only discovery layer over the released pack
catalog and the shared skills currently visible in a Trellis repository. It
does not add an executable help program or duplicate command workflows. The
shared `sd-help` skill defines how to reconcile catalog and runtime
availability, interpret a user query, and derive a concise explanation from the
selected skill's current text.

The interaction model intentionally parallels the adjacent planned `se-help`
experience: list, explain, compare, recommend, examples, and tour modes;
smallest-fit routing; progressive disclosure; availability labels; and
copy-ready next prompts. The catalog taxonomy and examples remain SD-specific.

The command ships through the existing generated-surface pipeline:

1. Introduce canonical command/family metadata in `installer.registry`, derive
   the compatibility `COMMAND_NAMES` tuple, and register `sd-help`.
2. Author the canonical shared skill at
   `templates/.agents/skills/sd-help/SKILL.md`.
3. Author the neutral adapter at `templates/.commands/sd-help.md`.
4. Generate
   `templates/.agents/skills/sd-help/references/command-catalog.md` from the
   registry, canonical frontmatter, source-only policy, and manifest version;
   author `references/examples.md` separately.
5. Run `make generate` to derive the catalog, Claude/Gemini/GitHub adapters, and
   manifest/reference fanout surfaces.
6. Run the self-installer to refresh root dogfood copies and provenance.

## Canonical Registry Model

Replace the pair-only registry with a frozen command model containing `name`,
`short`, and `family`. Keep `COMMAND_NAMES` as a derived tuple of `(name,
short)` pairs so current generator, installer, and tests retain a stable public
surface while family membership has one authoritative owner.

Declare ordered family ids and labels separately. Registry validation rejects
unknown families, duplicate names/shorts, empty values, missing `sd-` prefixes,
and name-to-family ambiguity. `SOURCE_ONLY_COMMAND_NAMES` continues to own
availability policy; do not duplicate that fact in each command row.

Add a generic shared-skill-reference mapping for generated or authored
references consumed by a skill. The generator fans each reference into the
shared `.agents/skills/` target and every supported platform-specific skill
root, keeping installed skill folders self-contained.

## Discovery Contract

The help workflow discovers the command set available in the current
repository, not the theoretical contents of a particular pack release.

1. Read the bundled generated catalog for released version, canonical family
   order, pack-owned names, descriptions, and source-only labels.
2. Prefer the platform's trusted installed-skill resolver when it can enumerate
   skills and return one unambiguous candidate per name.
3. Use `.agents/skills/sd-*/SKILL.md` as the portable project-local fallback.
4. Reconcile candidates against the catalog as `available now`, `included in
   this installed pack but not discoverable`, `source-checkout-only`, or
   `unknown/external`. Prefix alone never proves pack ownership.
5. Read the complete selected `SKILL.md` only for an exact explanation or
   comparison request.
6. Read `.sd-ai-command-pack/manifest.json` only for optional installed version
   display. Missing or invalid optional metadata does not suppress command help.

This makes consumer-local availability authoritative. `sd-fleet-refresh`
appears only in a source checkout where that skill exists and is labeled
source-checkout-only.

## Family Model

The family map lives in canonical registry metadata, not in the shared skill:

| Family | Commands |
|---|---|
| Orientation and knowledge | `sd-help`, `sd-start`, `sd-continue`, `sd-update-spec`, `sd-finish-work`, `sd-retro` |
| Planning and backlog | `sd-work-designs`, `sd-work-backlog` |
| Verification and improvement | `sd-full-check`, `sd-review-local`, `sd-review-learnings`, `sd-audit-repo`, `sd-test-gaps`, `sd-fix-ci` |
| Pull requests and shipping | `sd-create-pr`, `sd-review-pr`, `sd-watch-pr`, `sd-ship`, `sd-housekeeping` |
| Maintenance and fleet | `sd-update-deps`, `sd-fleet-refresh` |

The generated catalog renders these families in canonical order using
frontmatter descriptions. Runtime output intersects the catalog with discovered
skills while retaining separate labels for catalog-only and external skills.
Registry tests ensure every current pack command is classified exactly once.

## Query Model

The help workflow accepts free-form text rather than defining a fragile CLI
parser. It recognizes these request shapes in priority order:

1. **No query / tour**: concise new-user orientation, family overview,
   common-intent recipes, and examples of deeper queries.
2. **List / `all`**: available skills by default; complete catalog plus explicit
   availability labels when requested.
3. **Exact command / explain**: normalize common forms such as `sd-help`, `/sd:help`,
   `/sd-help`, `$sd-help`, and `sd/help` to a canonical `sd-*` name, then explain
   the selected installed skill.
4. **Family query**: show the available members and explain when to choose each.
5. **Comparison query**: read each named installed skill and compare purpose,
   scope, side effects, and lifecycle placement.
6. **Natural-language intent / recommend**: rank a small set of matching skills using names,
   descriptions, family context, and the compact intent examples in `sd-help`.
   Ask one clarifying question when the top choice is ambiguous.
7. **Examples**: load the authored examples reference and return realistic,
   copy-ready prompts filtered by family, command, or goal.

Optional explicit keys mirror SE where useful: `mode=list|explain|compare|
recommend|examples|tour`, `family=`, `skill=`, `skills=`, `goal=`, and
`detail=compact|standard`. Ordinary language remains the primary interface.

An exact explanation includes:

- what the skill does and when to use it;
- accepted arguments or modes documented by that skill;
- prerequisites and meaningful side effects;
- delegated skills and likely lifecycle neighbors;
- one or two platform-appropriate invocation examples;
- the exact suggested next invocation using the user's real context, without
  executing it.

The workflow should call out common distinctions:

- `sd-full-check` vs `sd-review-local` vs `sd-review-pr`;
- `sd-create-pr` vs `sd-ship`;
- `sd-finish-work` vs `sd-housekeeping`;
- `sd-work-designs` vs `sd-work-backlog`.

## Output Contract

Bare help is intentionally bounded and scan-friendly:

1. installed version when available;
2. family headings with available names and one-line descriptions;
3. a short "I want to..." routing table;
4. three examples for exact, comparison, and natural-language help.

Detailed workflow reproduction is forbidden. `all` is the explicit escape hatch
for a complete catalog. Exact explanations remain concise and link their claims
to the selected skill text conceptually rather than quoting large sections.

Recommendations choose one smallest-fit command by default. Existing composite
commands such as `sd-ship` count as one command and are preferred over manually
reconstructing their stages. A chain is valid only when no single command owns
the outcome; default chains contain at most three commands and identify the
handoff artifact/state between each stage.

## Safety And Trust

- Help is read-only and never delegates execution to the selected skill.
- Inspected skill text is data for explanation during this request, not an
  instruction stream to execute.
- The workflow does not modify files, create tasks, run checks, call GitHub, or
  install/update the pack.
- A user who wants to proceed must issue a separate command/request. The final
  line may provide that invocation verbatim.
- When a candidate is duplicated or malformed, fail that candidate closed and
  report the exact path/problem instead of choosing silently.

## Compatibility And Release

The normal command generator supplies every supported adapter and skill fanout;
no platform-specific help implementation is introduced. The neutral adapter
contains only the resolver/delegation wrapper, and generated bespoke adapters
remain parity checked.

The catalog reference follows progressive disclosure: its complete released
inventory stays outside `SKILL.md` and is loaded for list/routing work. The
authored examples reference is loaded only for examples, tour, or richer
recommendation requests. Tests validate every named command in examples against
the registry.

Because PR #146 currently reserves version `0.17.0`, the final release version
must be selected after reconciling this branch with the then-current `main`.
The expected version is `0.18.0` when #146 lands first. Candidate fleet evidence
must be regenerated from the final reconciled payload before publication.

Rollback is a normal manifest-driven payload removal: remove the registry row,
canonical skill, and neutral adapter; regenerate surfaces; and retain the
release history. No consumer state migration is required.

## Testing Strategy

- Add focused contract tests for every query mode, read-only safety language,
  version behavior, source-only labeling, command-form normalization, bounded
  output rules, and the exact-once family map.
- Add generator tests for deterministic catalog content, frontmatter parsing,
  family ordering, Markdown escaping, source-only labels, version binding,
  shared-reference fanout, check-mode drift, and temp-path isolation.
- Reuse generator tests to prove adapters and manifest are derived and clean.
- Extend install/parity snapshots to prove the shared skill and active-platform
  adapters install, update, audit, and remove normally.
- Test that a future runtime skill absent from the bundled catalog remains
  visible as external/unknown and that unavailable pack skills are not
  advertised as locally runnable.
- Run `make generate`, focused tests, the full installer suite, `make check`,
  self-install/audit, KB refresh, and deterministic full-check.

## SD And SE Alignment

Keep these experience contracts parallel where useful:

- the six natural-language-first modes and optional explicit keys;
- compact/standard detail;
- generated registry/frontmatter catalog plus authored examples;
- current-availability reconciliation and honest limitations;
- smallest-fit recommendation, one-question maximum, bounded chains, and named
  handoffs;
- copy-ready prompts and a read-only execution boundary;
- aliases, unique minor misspellings, ambiguity, and unknown handling.

Keep these intentionally different:

- SD uses software-delivery lifecycle families; SE uses knowledge-work outcome
  families.
- SD installs project-local commands/prompts and shared skills across many
  platform adapters; SE currently plans user-scope skill installs on three
  skill platforms.
- SD explanations emphasize prerequisites, side effects, delegated gates, and
  lifecycle neighbors; SE emphasizes source material, output artifacts,
  depth/time horizon, and external mutation boundaries.
- SD should recommend composite delivery commands when available; SE may compose
  up to three distinct artifact-producing skills.
