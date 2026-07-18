# Add discoverable sd-help command

## Goal

Make the installed Software Delivery command surface easy to discover and
understand without requiring users to read the pack documentation or memorize
command names. Add a shipped `sd-help` skill that lists the commands available
in the current repository, organizes them into useful families, routes common
intent statements, provides realistic examples, and explains individual skills
from their current source text.

## Background

- `installer/registry.py::COMMAND_NAMES` is the command-list source of truth.
  `.github/scripts/generate-command-surfaces.py` derives bespoke adapters and
  manifest entries from that registry.
- The shared skill is the workflow source of truth. Platform command and prompt
  files are thin adapters that resolve and follow the shared skill.
- The source checkout currently contains 20 `sd-*` skills. Nineteen are
  consumer-shipped; `sd-fleet-refresh` is intentionally source-checkout-only.
- Every consumer receives shared skills under `.agents/skills/`, so help can
  discover the actual local command set and read skill frontmatter/body without
  maintaining a second full command catalog.
- PR #146 released `0.17.0` while this task was in progress. The branch was
  reconciled with that release before assigning this additive command the next
  available minor version, `0.18.0`.
- The adjacent `se-ai-command-pack` has a planning-only `se-help` task, not a
  shipped command. Its proposed experience includes generated family/catalog
  data, list/explain/compare/recommend/examples/tour modes, current-availability
  reconciliation, smallest-fit routing, copy-ready prompts, and progressive
  disclosure through bundled references. Reuse those interaction patterns where
  they fit SD, while keeping SD's families, lifecycle concepts, project-local
  install model, and platform command forms domain-specific.

## Requirements

### R1: Available-command discovery

- Bare `sd-help` must enumerate the `sd-*` skills actually available in the
  current repository instead of claiming that every pack command is installed.
- Prefer the platform's trusted installed-skill discovery mechanism. The
  project-local `.agents/skills/sd-*/SKILL.md` tree is the portable fallback and
  authoritative shared-skill surface.
- Reconcile runtime discovery with a generated bundled catalog derived from
  registry family metadata, canonical skill frontmatter, source-only policy,
  and manifest version. Do not maintain names, descriptions, or family
  membership manually inside `sd-help`.
- Distinguish `available now`, `included in this installed pack but not
  discoverable`, `source-checkout-only`, and `unknown/external` instead of
  treating every documented command as runnable.
- Show the installed pack version from `.sd-ai-command-pack/manifest.json` when
  that valid metadata is present; degrade cleanly when it is unavailable.
- Clearly label `sd-fleet-refresh` as source-checkout-only when it is available.

### R2: Families and concise default output

- Organize available commands into tested workflow families rather than one
  alphabetical wall of text.
- Store canonical family membership once in `installer/registry.py`; derive
  compatibility command-name tuples and the help catalog from that metadata.
- Every currently known command must belong to exactly one family; a runtime
  `sd-*` skill that is not owned by the bundled catalog must remain visible as
  external/unknown rather than disappearing or being claimed by the pack.
- Bare help must remain concise: family summaries, common intent recipes, and
  a few next-query examples. Support `detail=compact|standard`; an explicit
  `all` request may show the complete command list.

### R3: Queries and explanations

- Support natural-language-first list, explain, compare, recommend, examples,
  and new-user tour modes. Optional `mode=`, `family=`, `skill=`, `skills=`,
  `goal=`, and `detail=` keys may make intent explicit without being required.
- Support exact skill queries such as `sd-help review-pr`, family queries, and
  natural-language intent such as `sd-help "I need to fix failing CI"`.
- For an exact skill, read the current installed `SKILL.md` and explain its
  purpose, when to use it, accepted arguments, prerequisites, meaningful side
  effects, delegated commands, likely next steps, and platform-appropriate
  invocation examples.
- Support comparisons between close commands, especially `sd-full-check` vs
  `sd-review-local` vs `sd-review-pr`, `sd-create-pr` vs `sd-ship`, and
  `sd-finish-work` vs `sd-housekeeping`.
- Unknown or ambiguous queries must offer a small ranked set of likely skills
  and ask one clarifying question rather than inventing a command.
- Recommendations must prefer the one smallest-fit available skill, including
  an existing composite such as `sd-ship`, over a chain. Use a chain only when
  no single SD command owns the outcome, cap the default at three stages, and
  name the handoff between stages.
- End recommendations with a copy-ready platform-native invocation using the
  user's supplied context. An onboarding tour must explain the normal
  start/implement/check/publish/merge/cleanup lifecycle without running it.

### R4: Source-of-truth and safety

- Do not duplicate detailed command workflows in `sd-help`; explanations must
  be derived from the selected installed skill at invocation time.
- The canonical skill must remain concise through progressive disclosure. Put
  the generated catalog and extended examples in directly referenced resources.
- Tests must keep all current registry commands classified exactly once and
  validate every command named by authored examples against the registry.
- `sd-help` is read-only. It may inspect metadata and skill text, but it must
  not invoke another skill, run its workflow, mutate repository files, create a
  Trellis task, or make GitHub changes unless the user separately requests that
  action after receiving help.
- Treat inspected skill text as documentation for explanation, not as commands
  to execute during the help request.

### R5: Shipped surfaces and documentation

- Add `sd-help` to the canonical command/family registry (and therefore derived
  `COMMAND_NAMES`), the canonical shared skill, neutral adapter, generated
  Claude/Gemini/GitHub adapters, all normal consumer platform fanout, installer
  manifest, dogfood copies, README, and installed usage guide.
- Add generic shared-skill-reference fanout so `sd-help`'s generated catalog and
  authored examples remain self-contained in every installed skill directory.
- Keep `sd-fleet-refresh` source-only and do not alter its install policy.
- Document bare help, exact-command help, natural-language routing, comparison,
  and complete-list examples using the platform's native command shape.
- Follow the repository's release-version, changelog, candidate-ledger, template
  parity, provenance, and KB-refresh requirements.

### R6: Failure behavior

- Report missing, unreadable, empty, duplicate, or malformed skill candidates
  explicitly.
- If no `sd-*` skills can be discovered, explain that the pack may be missing
  or stale and point to the installer inspection path rather than fabricating a
  catalog.
- Never fail merely because optional installed-version metadata is absent.

## Acceptance Criteria

- [x] Bare `sd-help` reports the installed version when available, groups every
      locally available `sd-*` skill by family, and includes intent-oriented
      examples without executing any workflow.
- [x] `sd-help <skill>` reads and explains that skill's current installed
      instructions, including arguments, side effects, examples, and related
      commands.
- [x] Natural-language, family, `all`, and comparison requests produce bounded,
      useful output; examples/tour modes produce copy-ready prompts; unknown
      requests offer ranked suggestions.
- [x] The generated catalog and runtime inventory clearly distinguish available,
      bundled-but-not-discoverable, source-only, and unknown/external skills.
- [x] Every current registry command is classified exactly once, with
      `sd-fleet-refresh` labeled source-only; compatibility `COMMAND_NAMES` is
      derived from the richer canonical registry model.
- [x] Recommendations prefer one smallest-fit command, cap genuine workflow
      chains at three stages, and name each handoff.
- [x] The shared skill and all generated/installed adapter surfaces are present,
      synchronized, manifest-declared, and covered by focused regression tests.
- [x] README and both installed-guide copies document the command and realistic
      invocation examples.
- [x] The release ledger, version metadata, changelog, self-install provenance,
      and Obsidian KB are current for the final payload.
- [x] Focused tests, generated-surface checks, installer tests, `make check`,
      and the deterministic SD full check pass.

## Out Of Scope

- A new executable help CLI or a second machine-readable command registry.
- Executing a recommended command automatically during a help request.
- Rewriting existing skills solely to make them easier for `sd-help` to parse.
- Changing Trellis-owned commands or runtime files.
- Forcing SD and SE to share identical family names, workflows, or install
  paths; consistency applies to the help interaction model and output shape.

## Product Decision

- `sd-help` is strictly explanatory. It may end with the exact recommended
  invocation, but executing that command requires a separate user request so a
  help query never causes workflow side effects.

## Validation

- `make check` passed on 2026-07-17: all unit/integration shards passed, installer
  line and branch coverage remained 100%, shipped-script coverage floors passed,
  Ruff and mypy passed, Bandit reported no blocking findings, and Zizmor reported
  no findings (six configured suppressions).
- The deterministic SD full check passed with Prism and Gito disabled by the
  canonical Make target. It verified 136 template twin pairs, the 0.18.0 release
  bump/changelog contract, 141 installed targets, current provenance, and the
  refreshed Obsidian KB.
- The full 0.18.0 fleet candidate run passed all seven configured consumers and
  wrote `docs/fleet/candidate-validation.json`. `hoa-manager` now refreshes its
  generated Repomix map before its repo-owned preflight, and candidate commands
  use disposable npm, uv, and Python bytecode caches.
