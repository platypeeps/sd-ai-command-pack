# Codex Claude review integration research

## Current pack boundary

- `templates/scripts/sd-ai-command-pack-review-local.sh` owns executable Prism,
  Gito, and configured shell-provider behavior. Its default and `all` tool alias
  are intentionally `prism gito`.
- `.github/command-sources/sd-review-local.md` is the authored neutral command
  body. `.github/scripts/generate-command-surfaces.py` generates the guarded
  neutral, Claude, Gemini, and GitHub adapters.
- `templates/.claude/commands/sd/review-local.md` currently has no Claude-only
  provider orchestration.

## Codex plugin contract

The installed marketplace source is a clean Git checkout of
`openai/codex-plugin-cc` at version 1.0.6. The normal review command is
`plugins/codex/commands/review.md` and invokes:

```text
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" review "$ARGUMENTS"
```

The command currently declares `disable-model-invocation: true`, so a parent
Claude workflow cannot call it through the normal Skill mechanism. Its current
instructions also require Codex output to become the user-visible response and
tell background mode not to wait, which prevents a parent review workflow from
reliably joining the result.

The companion supports working-tree and branch review but not full-codebase,
staged-only, or unstaged-only review. `--wait` suppresses the command's
foreground/background question; the companion itself still runs in the
foreground. Claude's background Bash task is what provides detachment.

## Rejected cache-patch boundary

Patching `disable-model-invocation` in Claude's managed plugin cache would be
overwritten by updates, require exact version/hash gates, and still require a
Claude restart before the skill becomes callable. Unknown plugin versions would
need to fail closed, turning routine plugin updates into pack maintenance. This
boundary was rejected.

## Chosen boundary

Codex CLI 0.145.0 exposes the supported native review commands
`codex review --uncommitted` and `codex review --base <branch>`. The Claude
plugin uses the same Codex installation, authentication, configuration, and
built-in reviewer through the app server. The pack can therefore invoke the
native CLI directly without copying plugin internals.

In the pack's Claude adapter, start the existing runner and the matching native
Codex CLI review concurrently, then collect both tasks before finding selection.
This avoids upstream changes, plugin cache discovery, patch maintenance, and a
runtime dependency on the plugin.

When the Codex CLI or required review flags are absent, the adapter keeps the
runner result and reports Codex as skipped. Full-codebase mode skips Codex
visibly because using a working-tree or branch target would mix incomparable
scopes.
