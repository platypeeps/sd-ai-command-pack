# Claude Code plugin packaging + private marketplace — Design

Date: 2026-08-09. Child of `08-09-deployment-thin-consumers` (parent
`design.md` section "Plugin packaging (D1)"; capability research in
parent `research/claude-code-plugin-capabilities.md`).

## Overview

Ship the `machine-claude` slice of `docs/fleet/surface-partition.json`
(schema version 1) as a build-generated, committed Claude Code plugin
in this repository, cataloged by a repo-root
`.claude-plugin/marketplace.json`, versioned in lockstep with
`manifest.json["version"]`. Redesign helper-script invocation so the
payload is self-contained in any layout (vendored fat install, plugin
cache, machine dir).

Slice composition today (v0.64.32): 36 `.claude/skills/**` files,
21 `.claude/commands/sd/*.md` files, 26 `scripts/*` rows all flagged
`sharedRuntime: true` (24 executables + `sd_ai_command_pack_lib.py`
+ `sd_ai_command_pack_fleet_lib.py`). No agent or hook rows exist in
the slice today; if future rows of an unmapped kind appear, the
generator fails closed (condition 3 below) until a mapping is
deliberately added — nothing is silently skipped.

## Proposal

### Plugin layout (generated, committed)

```
.claude-plugin/marketplace.json          # catalog, repo root
plugins/sd/
  .claude-plugin/plugin.json             # name "sd", version from manifest.json
  skills/<name>/...                      # from slice targets .claude/skills/<name>/...
  commands/<short>.md                    # from slice targets .claude/commands/sd/<short>.md
  bin/<script>                           # sharedRuntime scripts, exec bit set
```

- **Plugin name `sd`.** Plugin commands are namespaced by plugin name;
  flattening `commands/sd/<short>.md` → `commands/<short>.md` under a
  plugin named `sd` preserves the user-facing `/sd:help` invocation
  surface exactly. Collision risk of the short name is accepted and
  documented (marketplace id remains `platypeeps/sd-ai-command-pack`).
- **`bin/` carries the whole `scripts/` slice**, including the two
  non-executable `sd_*_lib.py` modules, so own-location sibling
  resolution and existing `sys.path` handling keep working. The
  `sharedRuntime: true` flag is the explicit duplication contract with
  `thin-machine-installer`; the generator treats those rows as shared,
  never exclusive.
- **`.claude/rules/**` never enters the plugin**: the generator
  consumes only the `machine-claude` category; rules rows are
  `consumer-config` in the partition. A test asserts the exclusion.

### Generator: `.github/scripts/generate-plugin.py`

Dev-side, wired into `make generate` after
`.github/scripts/partition-surfaces.py` (it consumes the partition
artifact). For each `machine-claude` row it looks up the manifest row
by target to find the template source
(`templates/.agents/skills/...`, `templates/.claude/commands/sd/...`,
`templates/scripts/...`), maps it into the plugin layout, applies the
invocation rewrite (below) to Markdown bodies, and writes
`plugin.json` with `version` read from `manifest.json["version"]`.

Fail-closed conditions (each a hard error):

1. slice row whose target has no manifest source row;
2. missing or unreadable template source file;
3. slice row of an unmapped kind/prefix (e.g. future agent/hook rows
   until the mapping is implemented);
4. rewrite residue, two scopes: (a) generated Markdown — any
   `scripts/sd-ai-command-pack-` or `scripts/sd_ai_command_pack_`
   substring is a hard error, no exceptions; (b) `bin/` contents —
   the same pattern is an error unless the (file, purpose) pair is in
   a per-file semantic-data allowlist with written justification.
   Seeded entries: `sd-ai-command-pack-install-audit.py:74` and
   `sd-ai-command-pack-pr-body-scope.py:249` region globs
   (`scripts/sd-ai-command-pack-*` etc.) are consumer-layout *data*
   describing vendored installs to audit/scope — semantically
   correct in any layout, neither sibling resolution nor prose.
   Functional sibling construction in `bin/` is separately forbidden
   by the boundary test (piece 1) regardless of allowlist;
5. `manifest.json` version missing/empty;
6. dependency-closure failure: a bare pack-command reference in
   rewritten Markdown whose target is not present in `bin/`, unless
   listed in an explicit in-generator allowlist entry carrying a
   written justification (seeded with the pre-existing
   `sd-review-pr` → `sd-ai-command-pack-fleet-review-classify.py`
   fleet-operator reference, which is already absent from vendored
   consumer installs today — the fleet scripts have zero manifest
   rows; a follow-up task fixes that skill text).

**Atomicity and staleness**: the generator builds the complete plugin
tree in a temp directory, validates all conditions, then replaces
`plugins/sd/` wholesale (files absent from the new set are deleted).
A `--check` mode regenerates to temp and diffs against the committed
tree — including extraneous committed files — and is exercised by a
unittest (same pattern as `tests/test_partition_surfaces.py`), which
is the actual CI freshness gate; there is no separate `make generate`
CI lane. Output is deterministic (sorted iteration, byte-stable
writes).

### Invocation rewrite + toolchain resolution redesign

Two coordinated pieces make one layout-independent contract:

1. **Runtime — own-location sibling resolution across ALL pack
   scripts** (PRD requirement 2 covers every pack script, not only
   the toolchain). Own-location wins outright; CWD is never
   consulted for pack-sibling resolution, so a consumer repo cannot
   shadow pack helpers (repo-root or `scripts/`-named files alike):
   - `scripts/sd-ai-command-pack-toolchain.sh`: `run-python` (and
     `run`) resolve a script argument that is a bare name or a
     `scripts/`-prefixed pack-script path against the toolchain's own
     `SCRIPT_DIR` (from `BASH_SOURCE`), stripping the `scripts/`
     prefix. In a fat install `SCRIPT_DIR` *is* the consumer
     `scripts/` directory, so existing caller text resolves to the
     identical file — behavior-compatible without CWD precedence.
     Non-pack arguments (paths not matching the pack-script name
     pattern) pass through unchanged.
   - Every other shipped script with a *functional* repo-root sibling
     reference converts to own-file-location resolution: Python
     `Path(__file__).resolve().with_name(...)` (e.g.
     `sd-ai-command-pack-review.py:33-34` `CHECK_SCRIPT`/
     `LOCAL_SCRIPT`), shell `SCRIPT_DIR` from `BASH_SOURCE`, Node
     `import.meta.url` dirname. An audit (2026-08-09 grep) found
     `scripts/…` literals in 15 shipped scripts (functional sites and
     usage/help prose); functional path construction converts, and
     usage/help prose switches to layout-neutral bare-command wording
     so the `bin/` residue scope (condition 4b) needs only the
     enumerated semantic-data allowlist.
   - A new AST/grep boundary test (pattern:
     `tests/test_state_root_boundary.py`) asserts no shipped script
     constructs a sibling path from a repo-root `scripts/` literal;
     imports keep the existing own-location `sys.path` convention.
2. **Source-side normalization of non-invocation forms.** Two
   classes, both fixed at the authored source so the build-time
   rewrite stays purely token-based; grep enumerates every
   occurrence and none may remain unconverted:
   - Skill Markdown existence tests (e.g.
     `templates/.agents/skills/sd-create-pr/SKILL.md:212`
     `[ ! -f scripts/sd-ai-command-pack-review-preflight.mjs ]` and
     its error string) → layout-neutral probe (`command -v` against
     the bare name, falling back to the `scripts/` path).
   - Command-adapter semantic instructions binding scripts to the
     repository root (e.g. "verify … are regular readable files
     relative to the repository root" in the `/sd:review` adapter).
     These adapters are GENERATED — the authored sources are
     `.github/command-sources/<name>.md` (2026-08-09 grep: sd-review,
     sd-review-local, sd-review-learnings, sd-audit-repo,
     sd-housekeeping) — so the fix lands in the command sources and
     regenerates through `generate-command-surfaces.py`, changing
     the verification wording to a layout-neutral resolvability
     check (toolchain resolvable via PATH or `scripts/`).
3. **Build-time rewrite in plugin Markdown only** (template Markdown
   payload bytes unchanged; the rewrite exists only in generated
   plugin copies). One token rule, applied everywhere in skill and
   command bodies: any token matching
   `scripts/sd-ai-command-pack-<name>.<ext>` or
   `scripts/sd_ai_command_pack_<name>.py` → the bare basename.
   One runner-prefix cleanup accompanies it: `node <bare>.mjs` →
   bare `<bare>.mjs`, because node does not PATH-search script
   operands while bash does (`bash X.sh` PATH-searches slash-free
   operands, so `bash`-prefixed results stay valid as-is; `bin/`
   entries carry shebangs and exec bits and sit on the Bash tool
   PATH). Anything
   still matching the residue pattern after rewriting fails the
   build (condition 4), and every rewritten reference must satisfy
   the closure gate (condition 6).

### Marketplace + docs

`.claude-plugin/marketplace.json`: owner `platypeeps`, one plugin
entry `{name: "sd", source: "./plugins/sd", description, category}`.
Consumers add once via `/plugin marketplace add
platypeeps/sd-ai-command-pack`. New doc section (in
`templates/docs/SD_AI_COMMAND_PACK.md` + repo docs) covers:
private-repo auth via `gh auth setup-git` (or SSH remotes), the
background-auto-update credential caveat and
`CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1`, and CI cache
pre-seeding via `CLAUDE_CODE_PLUGIN_CACHE_DIR`.

### Version stamping and release signal

- `make generate` stamps `plugin.json` from `manifest.json["version"]`
  on every run. `prepare-release.py` does NOT call `make generate` —
  its chain invokes generators directly (`prepare-release.py:284`
  onward runs `generate-command-surfaces.py`, self-sync, KB refresh),
  so `partition-surfaces.py` and `generate-plugin.py` are added to
  that chain explicitly, in that order (plugin consumes the partition
  artifact). Lockstep then holds structurally in both entry points.
- `prepare-release.py` gains a fail-closed consistency check:
  `plugins/sd/.claude-plugin/plugin.json` version ==
  `manifest.json` version.
- **Release-signal reach — BOTH payload classifiers**: two
  independent classifiers decide "shipped payload changed":
  `_is_payload_path` (`prepare-release.py:217`) and the drift-gate
  classifier inside
  `sd-ai-command-pack-full-check.sh` (~line 712,
  `payload_singletons` + `templates/` prefix), which PR CI invokes
  via `run_pack_source_drift_gates` (`tests.yml:643`). Both extend
  to cover `plugins/`, `.claude-plugin/marketplace.json`, and
  `.github/scripts/generate-plugin.py` (full-check edit lands in
  the canonical `templates/scripts/` copy, mirror refreshed via
  `make sync`; existing drift-gate tests extend to prove the new
  paths trip the gate), making such changes demand a manifest
  version bump through the existing gates. The fleet
  candidate digest (`sd_ai_command_pack_fleet_lib.py:683`) is NOT
  extended: it hashes the vendored payload identity, which the plugin
  is not part of; plugin freshness is owned by the version gate above
  plus the `--check` unittest. If `thin-fleet-status-pins` needs
  plugin identity in fleet evidence, that task owns it.

### CI gates

- Freshness: the generator's `--check` mode runs as a unittest (the
  repo's existing pattern for generated artifacts —
  `tests/test_surface_generation.py:44`,
  `tests/test_partition_surfaces.py:81`); there is no `make generate`
  drift lane in CI and none is added.
- New step in `.github/workflows/tests.yml` lint lane: install the
  Claude Code CLI (pinned), run
  `claude plugin validate plugins/sd --strict` (exit 0 required).
  Single lane to bound CI cost.
- Residue + closure gates run inside the generator (conditions 4 and
  6) and are exercised by the unittest, so `python -m unittest`
  proves them without CI.

## Boundaries And Non-Goals

- No consumer repo changes, no migration, no `enabledPlugins`
  seeding — `thin-migration` owns those.
- No non-Claude surfaces (`.agents/`, Codex, Gemini, machine-other) —
  `thin-machine-installer` owns them; the shared `bin/` duplication
  contract is the only overlap.
- No fleet/status reporting changes — `thin-fleet-status-pins`.
- Template *Markdown* payload bytes are unchanged except the
  enumerated source-side normalization of Proposal piece 2 — both
  classes: skill existence-test forms AND the five command adapters
  regenerated from their edited `.github/command-sources/` files;
  template *scripts* change deliberately
  (own-location resolution + prose neutralization) and ship to fat
  consumers on the next release as behavior-compatible payload — the
  canonical edits happen in `templates/scripts/**`, with root
  `scripts/**` refreshed as mirrors via `make sync`
  (`CONTRIBUTING.md:143`: templates are the source of truth).
- No archive/sha256 distribution channel (documented upgrade path in
  parent design; out of scope here).

## Affected Files

New:
- `.github/scripts/generate-plugin.py` (generator)
- `.claude-plugin/marketplace.json`
- `plugins/sd/**` (committed generated output)
- `tests/test_generate_plugin.py`

Modified (canonical edits in `templates/scripts/**`; root `scripts/`
mirrors refreshed via `make sync` — never the reverse):
- `templates/scripts/sd-ai-command-pack-toolchain.sh` — argument
  resolution
- shipped scripts with functional repo-root sibling references or
  repo-root usage prose (audited set; e.g.
  `sd-ai-command-pack-review.py`, `sd-ai-command-pack-full-check.sh`,
  `sd-ai-command-pack-housekeeping.sh`,
  `sd-ai-command-pack-review-preflight.mjs`,
  `sd-ai-command-pack-install-audit.py`,
  `sd-ai-command-pack-pr-body-scope.py`,
  `sd-ai-command-pack-surface-check.py`) — own-location sibling
  resolution + layout-neutral prose
- shipped skill Markdown with existence-test forms
  (`templates/.agents/skills/sd-create-pr/SKILL.md` and any grep
  siblings) — layout-neutral probes
- `.github/command-sources/{sd-review,sd-review-local,sd-review-learnings,sd-audit-repo,sd-housekeeping}.md`
  + their regenerated command adapters — layout-neutral
  resolvability wording
- `tests/` — new sibling-resolution boundary test
- `.github/scripts/prepare-release.py` — generator chain additions,
  version consistency check, `_is_payload_path` extension
- `Makefile` — generate chain + lint inventory for the new script
- `.github/workflows/tests.yml` (the single existing workflow; its
  lint lane) — CLI install + `claude plugin validate --strict`
- `templates/docs/SD_AI_COMMAND_PACK.md` + docs — marketplace/auth
  section
- `.trellis/spec/backend/manifest-and-filesystem.md` — plugin
  generation contract subsection

## Data And Command Contracts

- Input contract: `docs/fleet/surface-partition.json` schema v1
  (`files[].{target, platform, category, sharedRuntime}`), joined to
  `manifest.json` rows by `target` for source paths.
- Output contract: plugin layout above; `plugin.json`
  `{name: "sd", version: <manifest version>, description}`.
- `claude plugin list --json` on an installed machine shows
  `id`/`version` — consumed later by `thin-fleet-status-pins` (its
  contract, not built here).
- Toolchain resolution order is a documented public contract (spec
  update) because both fat and plugin layouts depend on it.

## Risks And Edge Cases

- **Rewrite under-match** (a skill invokes a script in a form the
  rule list misses): caught fail-closed by the residue gate, build
  fails rather than shipping a broken skill.
- **Rewrite over-match** (prose mentioning paths rewritten
  misleadingly): rules anchor on the `scripts/sd-ai-command-pack-`
  and `scripts/sd_ai_command_pack_` prefixes, which only ever name
  pack payload; worst case is cosmetic prose change in plugin copies.
- **Shadowing**: own-location-first resolution with no CWD probe
  means a consumer repo cannot shadow pack helpers with same-named
  files at its root or under `scripts/` — the contract the parent
  design requires; no collision surface remains by construction.
- **`claude` CLI availability/cost in CI**: pinned install in one
  lane; if the CLI install flakes, the step fails visibly (no soft
  skip). Bounded by existing CI-cost concerns (`08-08-ci-lane-cost`
  tracks lane budgets).
- **Marketplace `source` path correctness** is only fully proven by
  an end-to-end `/plugin marketplace add` against a pushed branch;
  CI proves `validate --strict` + `--plugin-dir` shape instead, and
  the parent's acceptance-level integration validation owns the
  end-to-end pass.
- **Future slice growth** (agents/hooks rows): fail-closed condition
  3 forces a deliberate mapping change instead of silent omission.

## Validation

- `tests/test_generate_plugin.py`: slice→layout mapping (skills,
  commands flattening, bin exec bits), rules exclusion, rewrite rules
  (token + node-prefix forms), two-scope residue gate failure cases
  (strict Markdown; `bin/` beyond allowlist),
  dependency-closure failure case and allowlist behavior,
  missing-source failure, unmapped-kind failure, version stamping,
  stale-file removal, `--check` mode against the committed tree
  (the CI freshness gate), determinism (two runs byte-identical).
- Toolchain resolution: Python subprocess tests covering pack-script
  arg → own-location resolution (bare and `scripts/`-prefixed forms),
  non-pack arg passthrough, and missing target → error.
- `make generate` then `git status --porcelain` empty (drift gate).
- `claude plugin validate plugins/sd --strict` exit 0 locally and in
  CI; `claude --plugin-dir plugins/sd` smoke in a payload-free temp
  repo (manual/acceptance, PRD AC 1).
- Full gate: `make release-prep` (self-sync + exact fleet ledger +
  `make check`), `node scripts/sd-ai-command-pack-review-preflight.mjs`.
