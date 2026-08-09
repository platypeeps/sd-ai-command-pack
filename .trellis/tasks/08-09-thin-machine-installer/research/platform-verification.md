# Research: user-level (machine-scope) surface resolution per non-Claude platform

- **Query**: For Gemini CLI, OpenCode, and Codex (`.agents`/`.codex`), does USER-LEVEL
  surface resolution actually work for the surface kinds this pack ships to that
  platform today, or does the platform only read repo-local files?
- **Scope**: mixed (repo evidence + local machine evidence + tool-embedded docs)
- **Date**: 2026-08-09
- **Requirement**: `prd.md` requirement 1 ("Per-platform verification FIRST")

## Method and evidence grades

Three evidence lanes were used, strongest first:

1. **Binary/bundle inspection** — the installed CLI's own path-resolution code or
   its embedded documentation. Cited as `<file>:<line>` or byte offset. This is
   the authoritative lane: it is what the running tool actually does.
2. **Live command output** — running the installed CLI read-only.
3. **On-disk state** — which user-level directories exist and are populated.

Nothing was installed, and no file outside this `research/` directory was written.
All three CLIs are installed on this machine:

```
/opt/homebrew/bin/gemini    -> gemini-cli 0.46.0
/opt/homebrew/bin/codex     -> codex 0.147.0
/opt/homebrew/bin/opencode  -> opencode 1.18.15
```

## What the pack actually ships per platform today

From `manifest.json` (grouped by `platform` + `kind`) and
`docs/fleet/surface-partition.json` `files[]`:

| Platform id | Rows | Surface kinds shipped | Target paths |
|---|---|---|---|
| `gemini` | 21 | `command` only | `.gemini/commands/sd/<name>.toml` |
| `opencode` | 21 | `command` only | `.opencode/commands/sd-<name>.md` (flat) |
| `codex` | **0** | none | none |
| `shared` | 82 | `skill` (51), `script` (26), `doc` (1), `config` (4) | `.agents/skills/**`, `scripts/*`, `docs/`, `.gito/`, `.prism/` |

The zero-row `codex` entry is not an oversight. `install.py:601-606` prints, for a
requested platform with no manifest rows:

> `note: platform {platform} has no dedicated manifest files; its commands are
> provided by the shared .agents skills`

So **Codex is served entirely by the `shared` platform's `.agents/skills/**`
surface**, not by any `codex`-owned row. `installer/registry.py:123-143` registers
`.codex` as a directory with `trellis_local_only` patterns and an
`agent_target_pattern` of `.codex/agents/{filename}`, but the pack ships nothing
into it.

Current partition dispositions (`.github/scripts/partition-surfaces.py:126-133`):

```python
PLATFORM_DISPOSITIONS: dict[str, tuple[str, bool]] = {
    "claude": (MACHINE, False),
    # Provisional pending the machine-installer per-platform verification.
    "shared": (MACHINE, True),
    "gemini": (MACHINE, True),
    "opencode": (MACHINE, True),
    "codex": (MACHINE, True),
    ...
```

---

## Gemini CLI — verdict: `machine` (VERIFIED)

**Surface kind covered**: commands (the only kind the pack ships to `gemini`).

**User-level path that works**: `~/.gemini/commands/sd/<name>.toml`

### Evidence 1 (binary, decisive): the user commands dir is a first-class source

`/opt/homebrew/Cellar/gemini-cli/0.46.0/libexec/lib/node_modules/@google/gemini-cli/bundle/chunk-G33JEOEV.js:249964`

```js
  static getUserCommandsDir() {
    return path4.join(_Storage.getGlobalGeminiDir(), "commands");
  }
  static getUserSkillsDir() {
    return path4.join(_Storage.getGlobalGeminiDir(), "skills");
  }
  static getUserAgentSkillsDir() {
    return path4.join(_Storage.getGlobalAgentsDir(), "skills");
  }
```

with (same file, `:249929`):

```js
  static getGlobalGeminiDir() {
    const homeDir = homedir();
    if (!homeDir) { return path4.join(os3.tmpdir(), GEMINI_DIR); }
    return path4.join(homeDir, GEMINI_DIR);          // ~/.gemini
  }
  static getGlobalAgentsDir() {
    const homeDir = homedir();
    if (!homeDir) { return ""; }
    return path4.join(homeDir, AGENTS_DIR_NAME);      // ~/.agents
  }
```

### Evidence 2 (binary): the command loader enumerates the user dir before the project dir

`bundle/chunk-SCXTH56Q.js:53989-54016` (identical in `chunk-T55FPMGN.js` and
`chunk-XWSJWBAL.js`):

```js
   * User commands → Project commands → Extension commands
   * This order ensures extension commands can detect all conflicts.
  getCommandDirectories() {
    const dirs = [];
    const storage = this.config?.storage ?? new Storage(this.projectRoot);
    const userCommandsDir = Storage.getUserCommandsDir();
    dirs.push({ path: userCommandsDir, kind: "user-file" /* USER_FILE */ });
    if (!storage.isWorkspaceHomeDir()) {
      dirs.push({ path: storage.getProjectCommandsDir(), kind: "workspace-file" });
    }
    ...
```

### Evidence 3 (binary): the shipped file shape is exactly what the loader parses

Same file, `parseAndAdaptFile` (`:54026-54070`): reads the file, `import_toml.default.parse`,
validates against `TomlCommandDefSchema`, strips the trailing 5 chars (`.toml`),
and joins path segments with `":"`:

```js
    const baseCommandName = relativePath.split(path20.sep).map((segment) => {
      let sanitized = segment.replace(/[^a-zA-Z0-9_\-.]/g, "_");
      ...
    }).join(":");
```

So `~/.gemini/commands/sd/help.toml` resolves to `/sd:help` — byte-identical
behavior to the repo-local copy the pack installs today at
`.gemini/commands/sd/help.toml`.

### Evidence 4 (live output): Gemini also resolves user-level `~/.agents/skills`

`gemini skills list` (run in this repo):

```
Skill conflict detected: "caveman-stats" from "/Users/sven/.agents/skills/caveman-stats/SKILL.md" is overriding the same skill from "/Users/sven/.gemini/extensions/caveman/skills/caveman-stats/SKILL.md".
...
archify [Enabled]
  Location:    /Users/sven/.agents/skills/archify/SKILL.md
```

This is live proof of `getUserAgentSkillsDir()` — Gemini reads `~/.agents/skills/`
and it even wins over extension-provided skills of the same name. It matters for
the `shared` row, not for the `gemini` row (the pack ships no skills to `gemini`).

### Open risks — Gemini

- `~/.gemini/commands/` **does not exist on this machine** (`ls: /Users/sven/.gemini/commands: No such file or directory`). `~/.gemini/` itself exists with `GEMINI.md`, `settings.json`, `extensions/`, `hooks/`, `skills/`. The installer must create `commands/` rather than assume it.
- **Precedence between user and project scope was not pinned down.** The loader enumerates user first and project second and emits conflict diagnostics; which scope wins on a duplicate name was not verified. During migration a consumer repo that still vendors `.gemini/commands/sd/*.toml` will collide with the machine copy; the acceptance test for the installer should assert the resulting `/sd:*` command actually comes from the intended scope rather than assuming it.
- `GEMINI_CLI_TRUSTED_FOLDERS_PATH`-style env overrides exist for other paths; `getGlobalGeminiDir()` has no env override, but it does fall back to `os.tmpdir()/.gemini` when `homedir()` is empty. Installer should resolve the same way rather than hardcoding `$HOME`.

---

## OpenCode — verdict: `machine` (VERIFIED, doc-from-binary)

**Surface kind covered**: commands (the only kind the pack ships to `opencode`).

**User-level path that works**: `~/.config/opencode/command/<name>.md` — plural
`commands/` is also accepted.

### Evidence 1 (binary-embedded docs, decisive): the scope table

Extracted from the opencode 1.18.15 binary at byte offset ~71666000
(`/opt/homebrew/Cellar/opencode/1.18.15/libexec/lib/node_modules/opencode-ai/bin/opencode.exe`,
a Bun-compiled Mach-O with the docs embedded as a markdown table):

```
| Global agents                 | `~/.config/opencode/agent(s)/<name>.md`
| Project commands              | `.opencode/command/<name>.md` or `.opencode/commands/<name>.md`
| Global commands               | `~/.config/opencode/command(s)/<name>.md`
| Project skills                | `.opencode/skill(s)/<name>/SKILL.md`
| Global skills                 | `~/.config/opencode/skill(s)/<name>/SKILL.md`
| External skills (auto-loaded) | `~/.claude/skills/<name>/SKILL.md`, `~/.agents/skills/<name>/SKILL.md`
```

followed by: *"Configs from each scope are deep-merged. Project overrides global."*

Two things fall out. First, **global commands are a supported scope**, and the
`(s)` notation means the pack's existing plural `commands/` naming works at both
scopes — no rename needed. Second, **OpenCode auto-loads `~/.agents/skills/`**,
which independently supports machine scope for the `shared` skills row.

### Evidence 2 (binary): the command loader contract

Same region, offset ~71673890:

> "opencode's command loader scans for `**/*.md` inside command directories. The
> file is named after the command, and lives directly inside the `command` folder"

The pack's flat `sd-<name>.md` layout matches; nested layout would also work
(`**/*.md`), so the shipped shape needs no change.

### Evidence 3 (on-disk): the global root exists but the command dir does not

```
/Users/sven/.config/opencode/opencode.json
/Users/sven/.config/opencode/AGENTS.md
/Users/sven/.config/opencode/plugins/
ls: /Users/sven/.config/opencode/command: No such file or directory
ls: /Users/sven/.config/opencode/commands: No such file or directory
```

### Open risks — OpenCode

- **The global root is XDG-derived, not `~/.config` literal.** The binary's own
  strings are `.config/opencode/{agent,command,skill,tui}`; the installer must
  honor `XDG_CONFIG_HOME` rather than hardcoding `$HOME/.config/opencode`, or it
  will write to a directory OpenCode never reads on machines that set it.
- **`~/opencode/` is a decoy.** This machine has `/Users/sven/opencode/` containing
  `commands/`, `skills/`, `agents/`, `AGENTS.md`, and an `opencode.json` that only
  registers `./plugins/caveman/plugin.js`. It is not a documented OpenCode
  resolution root and does not appear in the binary's scope table. Do not target it.
- **"Project overrides global"** is stated explicitly. Same migration hazard as
  Gemini: a consumer repo still vendoring `.opencode/commands/sd-*.md` shadows the
  machine copy, so a stale repo copy silently wins until migration removes it.
- Evidence grade is *binary-embedded documentation*, not executed code paths. It is
  the tool's own shipped doc for the exact installed version, which is much
  stronger than upstream web docs, but it was not confirmed by placing a file and
  seeing OpenCode load it (that would require writing outside `research/`).

---

## Codex — verdict: `repo-native` for the surface as shipped

**Surface kinds covered**: none owned by `codex`. Codex consumes the `shared`
`.agents/skills/**` rows.

**The blocking finding**: Codex reads `.agents/skills` as a **repository** skills
root only. It has a user-level skills root, but it is `$CODEX_HOME/skills`
(`~/.codex/skills`), not `~/.agents/skills`.

### Evidence 1 (binary, decisive): `.agents` is the *repo* skills root

From the codex 0.147.0 binary
(`/opt/homebrew/Caskroom/codex/0.147.0/bin/codex`), Rust string table at offsets
167023782 / 167112201 / 167242237 (three sites, identical text):

```
failed to stat project root marker ..: . ..`. failed to stat repo skills root ..: . ..`..agentsskills_for_config
```

and at offset 167009897:

```
failed to walk skills root ..: . ..`.agents
```

The literals `.agents` and `skills_for_config` sit adjacent to the *"repo skills
root"* / *"project root marker"* diagnostics. `.agents` is resolved relative to a
discovered project root, not the home directory.

### Evidence 2 (binary, decisive by absence): `~/.agents/skills` is never referenced

A byte search of the full 220 MB binary for `~/.agents/skills` returns **NOT
FOUND**. Every `.agents` occurrence in the binary is either the repo skills root
above, the plugin-marketplace manifests (`.agents/plugins/marketplace.json`,
`.agents/plugins/api_marketplace.json`), or unrelated serde field names
(`.agentsconnection`, `.agentssettings`, `.agentsstruct`).

### Evidence 3 (binary): the real user-level skills root is `$CODEX_HOME/skills`

Offset 170062137 and 170064274 (Codex's own bundled skill-authoring instructions):

> "Where should I create this skill? If you do not have a preference, I will place
> it in `$CODEX_HOME/skills` (or `~/.codex/skills` when `CODEX_HOME` is unset) so
> Codex can discover it automatically."

Offset 170112470 (skill install command docs):

> "Installs into `$CODEX_HOME/skills/<skill-name>` (defaults to `~/.codex/skills`)"

### Evidence 4 (on-disk + live): that root is real and in use

`~/.codex/skills/` exists and is populated (`migrate-to-codex`, `playwright`,
`se-action-inbox`, `se-agenda`, … ~40 entries). `~/.codex/agents/` holds
user-level subagents (`se-claim-verifier.toml`, `se-source-reader.toml`).

`codex doctor` confirms the home resolution:

```
  ✓ state        databases healthy
      CODEX_HOME               ~/.codex (dir)
```

### Evidence 5 (binary): Codex *does* read global agent instructions

Offset 166069160 — the module path plus its error string:

```
codex-home/src/instructions/mod.rs
Failed to read global AGENTS.md instructions from `..`
```

`~/.codex/AGENTS.md` exists on this machine. So Codex has genuine machine-scope
**agent instructions** even though it has no machine-scope `.agents/skills`.

### Why `codex` cannot simply have its flag flipped

1. **The flip would be vacuous.** `platforms.codex` has **zero rows** in
   `docs/fleet/surface-partition.json` `files[]`. Setting
   `"codex": (MACHINE, False)` asserts a verified machine disposition for a
   platform that ships nothing, so no test can catch it being wrong.
2. **The surface Codex actually uses belongs to `shared`.** Machine-installing
   `.agents/skills/**` to `~/.agents/skills/` serves Gemini and OpenCode and
   **not** Codex. If the consumer repo also stops vendoring `.agents/skills/`
   (which is the whole point of `thin-migration`), Codex loses the pack entirely.

Two dispositions are defensible; both are more than a flag flip:

- **(a) Re-disposition `codex` → `repo-native`** (`PLATFORM_DISPOSITIONS["codex"] =
  (REPO_NATIVE, False)`), and keep `.agents/skills/**` vendored per repo for
  Codex's benefit. This conflicts with machine-installing the same paths for
  Gemini/OpenCode unless both copies are allowed to coexist (they can — repo copy
  and `~/.agents/skills` copy are different roots and different platforms read
  each).
- **(b) Keep `codex` as `machine`, but add real manifest rows** targeting
  `$CODEX_HOME/skills/sd-*/SKILL.md`. This is a new target family that does not
  exist in `manifest.json` today, so it needs generator + manifest work, not a
  flag edit. Codex would then get genuine machine-scope skills, and the global
  `~/.codex/AGENTS.md` instruction lane becomes available as a bonus.

---

## `shared` — verdict: `machine` for its own consumers, but gated on the Codex decision

`shared` carries 82 rows: 51 `skill` + 1 `doc` = 52 `machine-other`, 26 `script`
rows flagged `machine-claude` + `sharedRuntime: true`, and 4 `consumer-config`
(`.gito/config.toml`, `.gito/sd-ai-command-pack.env`, `.prism/rules.json`,
`.prism/rules.schema.json`).

- **`.agents/skills/**` at `~/.agents/skills/`** — user-level resolution is
  **proven live for Gemini** (`gemini skills list` prints
  `Location: /Users/sven/.agents/skills/archify/SKILL.md`) and **documented in the
  OpenCode binary** ("External skills (auto-loaded) … `~/.agents/skills/<name>/SKILL.md`").
  The directory already exists and is populated on this machine, and
  `~/.claude/skills/archify` is a symlink into it
  (`/Users/sven/.claude/skills/archify -> ../../.agents/skills/archify`) — that
  symlink is a user convention, not a Claude Code behavior, so it is not evidence
  that Claude reads `~/.agents`.
- **`scripts/*` sharedRuntime rows** — machine scope for these is invocation by
  absolute path, and the enabling contract already exists:
  `.trellis/spec/backend/manifest-and-filesystem.md:191` ("Shipped pack scripts
  resolve sibling pack scripts from their own file location"), enforced by
  `tests/test_script_sibling_resolution.py` (`:204-205`: no shipped script may
  build a sibling path from a repo-root `scripts/`). That is what lets the whole
  script set relocate under a plugin/machine prefix.

**The gate**: flipping `shared` to non-provisional means the pack's skills move to
`~/.agents/skills/`. That is correct for Gemini and OpenCode and wrong for Codex,
whose only surface those skills are. So `shared` should not be flipped until
`codex` is re-dispositioned per option (a) or (b) above. Flipping `shared` first
silently breaks Codex.

---

## Summary table

| Platform | Shipped surface kinds | User-level path | Verdict | Flag action for the implementation |
|---|---|---|---|---|
| `gemini` | commands (21 × `.toml`) | `~/.gemini/commands/sd/*.toml` | **`machine` — verified** | Flip `provisional: true` → `false`; keep `MACHINE` |
| `opencode` | commands (21 × `.md`) | `$XDG_CONFIG_HOME/opencode/command(s)/*.md`, default `~/.config/opencode/` | **`machine` — verified** | Flip `provisional: true` → `false`; keep `MACHINE`; resolve XDG, do not hardcode |
| `codex` | **none** (served by `shared` `.agents/skills`) | `~/.agents/skills` is **not read**; user-level root is `$CODEX_HOME/skills` (`~/.codex/skills`) | **`repo-native` as shipped** | **Cannot flip.** Re-disposition to `(REPO_NATIVE, False)`, or add new `$CODEX_HOME/skills` manifest rows and keep `MACHINE` |
| `shared` | skills (51), scripts (26 `sharedRuntime`), doc, 4 consumer-config | `~/.agents/skills/**` + a machine script prefix | **`machine` — verified for Gemini + OpenCode** | Flip only **after** the `codex` re-disposition; flipping first removes Codex's only surface |

### Flags the implementation can flip vs must re-disposition

- **Can flip now**: `gemini`, `opencode`.
- **Can flip after the Codex decision**: `shared`.
- **Must re-disposition (not a flip)**: `codex`.

## Caveats / not found

- OpenCode's global-command behavior is established from the installed binary's
  embedded documentation table and loader description, not from an executed load.
  Confirming it requires creating `~/.config/opencode/command/` and a probe file,
  which is outside this task's write scope. Recommend the installer's acceptance
  test do that against a scratch `XDG_CONFIG_HOME` prefix.
- Gemini user-vs-project precedence on duplicate command names is **not**
  established; only the enumeration order is. This matters during migration.
- No verdict is claimed for `pi`, which also consumes `.agents/skills` per
  `.opencode/skills/trellis-meta/references/platform-files/platform-map.md:76`
  ("Codex, Gemini CLI, Pi Agent, and Kimi Code write the shared `.agents/skills/`
  layer"). `pi` is currently `repo-native` in the partition and was out of scope
  here, but it is a second consumer of the `shared` skills row and should be
  checked before `shared` flips.
- `.trellis/scripts/task.py current` reports the active task as
  `08-09-review-pr-fleet-classifier-ref`, not `08-09-thin-machine-installer`. This
  file was written to the task directory named in the assignment.
