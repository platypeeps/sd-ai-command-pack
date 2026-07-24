# Claude project-rule integration research

## Repository evidence

- The pack currently ships no `.claude/rules/` files.
- `sd-work-backlog` owns autonomous planning, while direct
  `trellis-brainstorm` and the planning start gate are upstream Trellis-owned.
- The existing native Codex local-review lane already establishes the desired
  plugin-independent pattern: check the CLI, run a Claude-owned background
  task, collect it alongside the host lane, and degrade visibly when absent.
- `codex exec --help` on the current supported CLI exposes custom prompts,
  `--cd`, `--sandbox read-only`, and `--ephemeral`, which are sufficient for a
  review-only planning pass without the Claude plugin runtime.

## Claude Code evidence

Official Claude Code documentation states that project instructions under
`.claude/rules/*.md` are additive to Claude's root memory instructions, are
distributable as committed project files, and may be unconditional or
path-scoped. Path-scoped rules load when matching files are read, while
unconditional rules load for the session.

Source: https://code.claude.com/docs/en/memory#organize-rules-with-claude-rules

## Decision

Ship a concise unconditional Claude rule that activates only when the current
run creates or materially updates Trellis planning artifacts. It resolves a
canonical pack-owned reference for the detailed workflow. This avoids changing
or shadowing upstream Trellis, covers direct and SD-owned brainstorming paths,
and is more reliable for brand-new artifact creation and post-compaction work
than relying only on a path-read trigger.
