# Research: Claude Code plugin capabilities vs. pack machine-scope needs

Date: 2026-08-09. Sources: https://code.claude.com/docs/en/plugins,
/docs/en/plugins-reference, /docs/en/plugin-marketplaces (fetched live;
docs current as of Claude Code v2.1.22x).

Purpose: answer PRD open question 1 — can a Claude Code plugin carry the
pack's machine-scope surfaces, and what does distribution/versioning look
like.

## What a plugin can ship

| Component | Location | Pack surface it maps to |
|-----------|----------|-------------------------|
| Skills | `skills/<name>/SKILL.md` (+ `references/`, `scripts/`) | every `.claude/skills/sd-*` skill, including nested reference files |
| Commands | `commands/*.md` (flat) | slash-command style skills |
| Agents | `agents/*.md` | subagent definitions; appear as `plugin-name:agent` |
| Hooks | `hooks/hooks.json` | PostToolUse/PreToolUse/etc. hook wiring |
| MCP servers | `.mcp.json` | none today (available if wanted) |
| Executables | `bin/` | **added to Bash tool PATH** — pack helper scripts become bare commands in any repo while plugin enabled |
| Settings | `settings.json` | only `agent` + `subagentStatusLine` keys supported |
| Monitors / LSP / themes / output-styles / workflows | various | not needed |

Not supported / notable limits:

- A CLAUDE markdown instructions file at the plugin root is **not**
  loaded as context. Instructions
  must ship as skills. Pack `.claude/rules/*.md` content has no direct
  plugin equivalent; a skill or hook-injected context replaces it.
- Plugin agents may not set `hooks`, `mcpServers`, or `permissionMode`
  frontmatter (security restriction).
- Installed plugins cannot reference files outside their directory
  (`../` paths break — payload must be self-contained).
- Only Claude Code. The pack's `.agents/`, Codex, Gemini, and other
  adapter surfaces are outside plugin reach and need their own
  machine-scope story (or stay vendored/central-checkout).

## Path + data model

- `${CLAUDE_PLUGIN_ROOT}` — install dir (changes each update; cache dir
  under `~/.claude/plugins/cache`, old version kept ~14 days).
- `${CLAUDE_PLUGIN_DATA}` — persistent `~/.claude/plugins/data/{id}/`,
  survives updates; recommended pattern: SessionStart hook diffs bundled
  manifest vs stored copy and reinstalls deps on change.
- `${CLAUDE_PROJECT_DIR}` — project root; lets plugin scripts operate on
  the consumer repo they run inside.
- Skill/agent content, hook and monitor commands substitute these
  anywhere; MCP/LSP configs in specific fields.

## Install scopes (the machine-scope mechanism)

| Scope | Settings file | Meaning |
|-------|--------------|---------|
| `user` | `~/.claude/settings.json` | one install, every repo on machine — **this is requirement 2's shape** |
| `project` | `.claude/settings.json` | checked into consumer repo; teammates prompted on trust |
| `local` | `.claude/settings.local.json` | gitignored per-checkout |
| `managed` | managed settings | org-forced, read-only |

- `enabledPlugins` honors project/local settings; `pluginConfigs` values
  are read only from user/managed/`--settings` (project values ignored
  for injection safety, v2.1.207+).
- A consumer repo can therefore carry a tiny `.claude/settings.json`
  with `extraKnownMarketplaces` + `enabledPlugins` so any collaborator
  who trusts the repo gets prompted to install — the "pin + config"
  thin footprint.

## Distribution: marketplaces

- Catalog = `marketplace.json` (repo root or `.claude-plugin/`);
  users add via `/plugin marketplace add owner/repo` (or URL / local
  path); update via `/plugin marketplace update`.
- Plugin entry `source` types: relative path, `github`, `url` (any git),
  `git-subdir` (sparse clone of monorepo subdir — fits pack repo
  hosting plugin in a subdirectory), `npm`, `archive` (zip over HTTPS,
  optional `sha256` pin, refuses install on digest mismatch).
- Git-based plugin sources accept `ref` and `sha`; `sha` wins as the
  effective pin. Marketplace source itself supports `ref` only.
- **Private repos work** through normal git credential helpers
  (`gh auth setup-git`, ssh-agent). Caveat: background auto-update
  disables credential helpers for its `git pull`; mitigations:
  `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1`, or a global git
  URL rewrite embedding a token, or SSH remotes.
- CI: export token, `gh auth setup-git` before installing; or pre-seed
  the cache via `CLAUDE_CODE_PLUGIN_CACHE_DIR`.
- Admin controls: `strictKnownMarketplaces`, `blockedMarketplaces`,
  `pluginSuggestionMarketplaces`, `disableSideloadFlags` (managed
  settings) — not needed for us but available.

## Version management (the fleet-skew story)

Update signal resolution order: `plugin.json` `version` → marketplace
entry `version` → source commit SHA → archive sha256 → `unknown`.

- **Explicit version** (`plugin.json` version, semver): users update
  only when the field bumps. The pack's release authority is
  `manifest.json` `version` (read by prepare-release) — release-prep
  can stamp `plugin.json` from it, making plugin updates track pack
  releases exactly.
- One installed version per machine per scope (cache keyed by version).
  There is **no per-project version selection** of a shared plugin —
  which matches requirement 2 (one update action propagates machine-
  wide). The consumer-repo "pin" is therefore an expectation record
  for fleet reporting, not a control over what executes (final
  semantics in the parent PRD; no CI-fetched pieces exist per the
  consumer-CI research). Fleet skew across machines remains
  possible and must be surfaced by `sd-status` (compare plugin
  installed version vs latest release).
- `claude plugin update <name>` / auto-update apply bumps;
  `claude plugin details <name>` shows component inventory + token
  cost; `claude plugin list --json` gives machine-readable installed
  state — good `sd-status` input. Verified live (2026-08-09, local
  CLI): each entry carries `id`, `version`, `scope`, `enabled`,
  `installPath` (absolute cache path), `installedAt`, `lastUpdated`.
  `installPath` is not in the published docs, so consumers of it
  should keep a fallback that derives the root from the cache layout
  (`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>`).

## Dev loop + validation

- `claude --plugin-dir <dir>` / `--plugin-url` load a plugin for one
  session without installing — pack-repo CI can smoke-test the built
  plugin.
- `claude plugin validate <dir> --strict` validates manifest, skill/
  agent frontmatter, hooks JSON; `--strict` fails on warnings — CI
  gate candidate in the pack repo.
- Skills-directory plugins (`~/.claude/skills/<name>/.claude-plugin/`)
  load in place with no install step (`name@skills-dir`) — convenient
  for local development of the plugin itself.
- `/reload-plugins` picks up non-skill component changes mid-session;
  `SKILL.md` edits are live immediately.
- `Setup` hook event (`claude --init-only` / `-p --init`) exists for
  one-time CI preparation.

## Fit assessment against PRD requirement 2

Plugin (user scope, private-marketplace distributed, explicit semver
from pack release) satisfies: one update action machine-wide, version
discoverable (`claude plugin list --json`), integrity for archive
sources via sha256 or git sources via commit identity, skills/agents/
hooks/bin coverage of the Claude-side payload.

Gaps to resolve in design:

1. Non-Claude surfaces (`.agents/`, Codex, Gemini adapters) — plugin
   does not carry them; need central-checkout or per-tool equivalent,
   or accept vendoring only for those (much smaller than 776 files).
2. `.claude/rules/` project-context semantics — plugin has no CLAUDE.md
   injection; decide skill-based replacement or keep rules as thin
   consumer config.
3. Scripts invoked by repo-relative path (`scripts/sd-ai-command-pack-
   *.sh`) — plugin `bin/` exposes bare commands instead; skills that
   hardcode `scripts/...` paths need rewrites to `${CLAUDE_PLUGIN_ROOT}`
   or bin-name invocation.
