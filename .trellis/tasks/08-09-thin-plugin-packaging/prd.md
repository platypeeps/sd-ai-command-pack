# Claude Code plugin packaging + private marketplace

Child of `08-09-deployment-thin-consumers`. Requirement 2 (Claude
side) of the parent PRD; architecture in parent `design.md` ("Plugin
packaging"); capability research in parent
`research/claude-code-plugin-capabilities.md`.

## Deliverable

A generated, committed plugin directory in this repo carrying the
`machine-claude` partition slice (skills, agents, hooks, `bin/`
executables), a `.claude-plugin/marketplace.json` catalog, and
release-prep integration stamping `plugin.json` `version` from
`manifest.json["version"]`.

## Requirements

1. Plugin dir is build-generated from templates via the partition
   output, never hand-edited; mirror-style CI gate keeps it fresh.
2. Helper-script resolution redesign: pack scripts resolve sibling
   helpers relative to their own file location (layout-independent);
   plugin-shipped skills invoke entry points as `bin/` bare commands
   or `${CLAUDE_PLUGIN_ROOT}` paths. Fat installs keep working.
3. CI gates: `claude plugin validate --strict` passes; grep gate
   proves zero consumer-repo-root script references in plugin output.
4. `.claude/rules` content is NOT in the plugin (consumer-config per
   parent design).
5. Marketplace docs cover private-repo auth (`gh auth setup-git`) and
   `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1`.

## Ordering constraints

- Requires `thin-surface-partition` output.
- Blocks `thin-migration` (no consumer converts before the plugin
  ships) and the plugin-validation piece of the rescoped candidate
  loop.

## Acceptance criteria

- [ ] `claude --plugin-dir <built-plugin>` session exposes the pack
      skills/agents/bin commands in a repo with no vendored payload.
- [ ] `claude plugin validate <dir> --strict` exits 0 in CI.
- [ ] Release-prep bumps `plugin.json` version in lockstep with
      `manifest.json["version"]`.
- [ ] Grep gate: zero `scripts/sd-ai-command-pack-*` repo-root
      references in plugin output.
