---
name: sd-update-spec
description: Use when the user wants the SD/Codex-visible update-spec command to run Trellis update-spec and the pack's extended spec-refresh features.
---

# SD Update Spec

Run the Trellis update-spec workflow for the current repository, then run the SD
AI command pack extensions.

1. Read `.agents/skills/trellis-update-spec/SKILL.md` first.
2. If that file is missing or unreadable, read the first existing Trellis
   update-spec instruction file in this fallback order:
   - `.claude/skills/trellis-update-spec/SKILL.md`
   - `.cursor/skills/trellis-update-spec/SKILL.md`
   - `.github/skills/trellis-update-spec/SKILL.md`
   - `.opencode/skills/trellis-update-spec/SKILL.md`
   Stop and report the missing skill if none of these files exists.
3. Follow the Trellis update-spec skill exactly. Do not modify, replace, fork,
   or reinterpret it. It is responsible for deciding what `.trellis/spec/`
   content should change.
4. After the Trellis update-spec pass, run the SD AI command pack extensions:
   - Check whether the repo has infrastructure for maintaining a repospec
     artifact. Look for existing repo docs, scripts, package tasks, make
     targets, or other checked-in commands that describe how the repospec is
     generated or refreshed. If that infrastructure exists, use it to refresh
     the repospec artifact instead of hand-editing generated output. Do not
     create new repospec infrastructure or a new repospec artifact unless the
     user asks. When the repospec refresh uses Repomix or another
     repository-map tool, follow the target repo's documented output path. If no
     path is documented, prefer `docs/repomix-map.md` and report the chosen
     path.
   - Check whether the repo already has an architectural overview. Search
     existing files, especially `ARCHITECTURE.md`, `ARCHITECTURE_OVERVIEW.md`,
     `docs/ARCHITECTURE.md`, `docs/ARCHITECTURE_OVERVIEW.md`, and
     `.trellis/spec/**/architecture*.md`. Do not create a new overview unless
     the user asks for one.
   - If an overview exists and the completed work changes high-level
     architecture such as packages, services, command surfaces, data flow,
     persistence, external integrations, config/env, or runtime/deployment
     topology, update the overview too. If no overview exists, or if the change
     does not warrant an architecture update, leave it untouched.
   - Rebuild the repo-local Obsidian knowledge-base folder:
     - Run `python3 scripts/sd-ai-command-pack-update-spec-kb.py` from the repo
       root. If the helper is missing, stop and report that the pack should be
       reinstalled; do not rebuild `.obsidian-kb/` manually from this wrapper.
     - Ensure `.obsidian-kb/` is listed in the repo root `.gitignore`. Add it if
       missing while preserving existing entries.
     - Create `.obsidian-kb/` in the repo root. Treat it as generated local
       state; do not commit it.
     - Link every relevant existing repo-knowledge file into `.obsidian-kb/`
       with symlinks, preserving relative folder names when practical. Include
       files that explain how the repo works, such as README, AGENTS,
       contributing, development, architecture, roadmap, decision, handoff,
       `.trellis/workflow.md`, `.trellis/config.yaml`, `.trellis/spec/**/*.md`,
       repo-owned repospec or Repomix outputs such as `docs/repomix-map.md`, and
       project manifests that explain package structure when present.
     - Treat that list as a floor, not a ceiling: search repo docs for other
       source-of-truth files that provide repository insight and link them too.
     - Refresh existing KB symlinks when their targets changed, and remove stale
       symlinks that point to files no longer relevant. Do not delete or
       overwrite non-symlink files in `.obsidian-kb/`; report them as conflicts.
     - Create and maintain `.obsidian-kb/Dashboard.md` as a generated Markdown
       landing page that groups and links to the current KB symlinks. If a
       user-owned file already exists at that path, do not overwrite it; report a
       conflict.
     - Do not link dependency/vendor directories, build output, caches, logs,
       secrets, `.git/`, `.trellis/workspace/`, or broad source trees unless a
       specific source entrypoint is intentionally maintained as repo
       documentation.
     - Prefer relative symlinks when possible so the repo can move.
5. Final report:
   - `Update-spec skill`: path read
   - `Spec updates`: paths changed, or `none`
   - `Repospec`: refreshed path/tool, `not present`, or `no infrastructure`
   - `Architectural overview`: updated path, `not present`, or `not warranted`
   - `Obsidian KB`: `.obsidian-kb` created/refreshed, symlink count, dashboard
     state, gitignore state, and any conflicts
   - `Obsidian vault link`: example command for linking this repo's
     `.obsidian-kb` folder into a vault, such as
     `ln -s /absolute/path/to/repo/.obsidian-kb /absolute/path/to/vault/Repo-KB`
   - `Validation`: checks run, or why checks were not run
