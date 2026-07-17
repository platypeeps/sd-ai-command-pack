# Onboard se-ai-command-pack: install SD workflow + fleet enroll

## Problem

The sibling pack repo se-ai-command-pack (platypeeps/se-ai-command-pack, a
Trellis repo with its own install.py/manifest.json and se-* skill product)
does not use the SD delivery workflow and is not tracked in the sd fleet, so
it neither dogfoods SD nor receives pack refreshes.

## Requirements

- R1. Install the current sd-ai-command-pack payload (0.15.6) into
  se-ai-command-pack on a clean branch off its origin/main (it is currently
  parked on a foreign CI branch). Conflict-aware install (no --force).
- R2. Verify with the target's own PYTHON_BIN=".venv/bin/python" bash .github/scripts/run-tests.sh
...................................................................sd-ai-command-pack 0.15.6
target: /private/var/folders/49/lgq0px596nq4sf2vmcwbl2bh0000gn/T/sd-ai-command-pack-test-_1lb6co2
created     .gitignore
created     .agents/skills/sd-audit-repo/charters/architecture.md
created     .agents/skills/sd-audit-repo/charters/design.md
created     .agents/skills/sd-audit-repo/charters/correctness.md
created     .agents/skills/sd-audit-repo/charters/security.md
created     .agents/skills/sd-audit-repo/charters/testing.md
created     .agents/skills/sd-audit-repo/charters/documentation.md
created     .agents/skills/sd-audit-repo/charters/bloat.md
created     .agents/skills/sd-audit-repo/charters/performance.md
created     .agents/skills/sd-audit-repo/charters/dependencies.md
created     .agents/skills/sd-audit-repo/charters/tooling.md
created     .agents/skills/sd-audit-repo/charters/release-hygiene.md
created     .agents/skills/sd-audit-repo/charters/improvements.md
created     .agents/skills/sd-audit-repo/charters/consumer-impact.md
created     .agents/skills/sd-audit-repo/charters/observability.md
created     .agents/skills/sd-audit-repo/charters/accessibility-i18n.md
created     scripts/sd-ai-command-pack-full-check.sh
created     scripts/sd-ai-command-pack-shell-lib.sh
created     scripts/sd-ai-command-pack-toolchain.sh
created     scripts/sd_ai_command_pack_lib.py
created     scripts/sd-ai-command-pack-housekeeping.sh
created     scripts/sd-ai-command-pack-record-session.py
created     scripts/sd-ai-command-pack-review-scope.sh
created     scripts/sd-ai-command-pack-review-preflight.mjs
created     scripts/sd-ai-command-pack-review-local.sh
created     scripts/sd-ai-command-pack-review-learnings.py
created     scripts/sd-ai-command-pack-install-audit.py
created     scripts/sd-ai-command-pack-pr-body-scope.py
created     scripts/sd-ai-command-pack-update-spec-kb.py
preserved   .prism/rules.json
created     .prism/rules.schema.json
created     .gito/config.toml
created     .gito/sd-ai-command-pack.env
created     docs/SD_AI_COMMAND_PACK.md
created     .agents/skills/sd-continue/SKILL.md
created     .agents/skills/sd-start/SKILL.md
created     .agents/skills/sd-finish-work/SKILL.md
created     .agents/skills/sd-create-pr/SKILL.md
created     .agents/skills/sd-work-backlog/SKILL.md
created     .agents/skills/sd-work-designs/SKILL.md
created     .agents/skills/sd-audit-repo/SKILL.md
created     .agents/skills/sd-watch-pr/SKILL.md
created     .agents/skills/sd-fix-ci/SKILL.md
created     .agents/skills/sd-update-deps/SKILL.md
created     .agents/skills/sd-test-gaps/SKILL.md
created     .agents/skills/sd-retro/SKILL.md
created     .agents/skills/sd-ship/SKILL.md
created     .agents/skills/sd-review-pr/SKILL.md
created     .agents/skills/sd-review-local/SKILL.md
created     .agents/skills/sd-review-learnings/SKILL.md
created     .agents/skills/sd-full-check/SKILL.md
created     .agents/skills/sd-housekeeping/SKILL.md
created     .agents/skills/sd-update-spec/SKILL.md
created     .sd-ai-command-pack/manifest.json
created     .sd-ai-command-pack/provenance.json
created     .sd-ai-command-pack/installed-targets.txt
skipped     .github/copilot-instructions.md (anchor .github not present)
skipped     .github/PULL_REQUEST_TEMPLATE.md (anchor .github not present)
skipped     .claude/commands/sd/continue.md (anchor .claude not present)
skipped     .cursor/commands/sd-continue.md (anchor .cursor not present)
skipped     .gemini/commands/sd/continue.toml (anchor .gemini not present)
skipped     .github/prompts/sd-continue.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-continue.md (anchor .opencode not present)
skipped     .agent/workflows/sd-continue.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/continue.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-continue.md (anchor .devin not present)
skipped     .factory/commands/sd/continue.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-continue.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-continue.md (anchor .pi not present)
skipped     .qoder/commands/sd-continue.md (anchor .qoder not present)
skipped     .trae/commands/sd-continue.md (anchor .trae not present)
skipped     .zcode/commands/sd/continue.md (anchor .zcode not present)
skipped     .agent/skills/sd-continue/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-continue/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-continue/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-continue/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-continue/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-continue/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-continue/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-continue/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-continue/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-continue/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/start.md (anchor .claude not present)
skipped     .cursor/commands/sd-start.md (anchor .cursor not present)
skipped     .gemini/commands/sd/start.toml (anchor .gemini not present)
skipped     .github/prompts/sd-start.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-start.md (anchor .opencode not present)
skipped     .agent/workflows/sd-start.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/start.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-start.md (anchor .devin not present)
skipped     .factory/commands/sd/start.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-start.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-start.md (anchor .pi not present)
skipped     .qoder/commands/sd-start.md (anchor .qoder not present)
skipped     .trae/commands/sd-start.md (anchor .trae not present)
skipped     .zcode/commands/sd/start.md (anchor .zcode not present)
skipped     .agent/skills/sd-start/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-start/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-start/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-start/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-start/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-start/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-start/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-start/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-start/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-start/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/finish-work.md (anchor .claude not present)
skipped     .cursor/commands/sd-finish-work.md (anchor .cursor not present)
skipped     .gemini/commands/sd/finish-work.toml (anchor .gemini not present)
skipped     .github/prompts/sd-finish-work.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-finish-work.md (anchor .opencode not present)
skipped     .agent/workflows/sd-finish-work.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/finish-work.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-finish-work.md (anchor .devin not present)
skipped     .factory/commands/sd/finish-work.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-finish-work.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-finish-work.md (anchor .pi not present)
skipped     .qoder/commands/sd-finish-work.md (anchor .qoder not present)
skipped     .trae/commands/sd-finish-work.md (anchor .trae not present)
skipped     .zcode/commands/sd/finish-work.md (anchor .zcode not present)
skipped     .agent/skills/sd-finish-work/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-finish-work/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-finish-work/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-finish-work/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-finish-work/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-finish-work/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-finish-work/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-finish-work/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-finish-work/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-finish-work/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/create-pr.md (anchor .claude not present)
skipped     .cursor/commands/sd-create-pr.md (anchor .cursor not present)
skipped     .gemini/commands/sd/create-pr.toml (anchor .gemini not present)
skipped     .github/prompts/sd-create-pr.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-create-pr.md (anchor .opencode not present)
skipped     .agent/workflows/sd-create-pr.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/create-pr.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-create-pr.md (anchor .devin not present)
skipped     .factory/commands/sd/create-pr.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-create-pr.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-create-pr.md (anchor .pi not present)
skipped     .qoder/commands/sd-create-pr.md (anchor .qoder not present)
skipped     .trae/commands/sd-create-pr.md (anchor .trae not present)
skipped     .zcode/commands/sd/create-pr.md (anchor .zcode not present)
skipped     .agent/skills/sd-create-pr/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-create-pr/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-create-pr/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-create-pr/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-create-pr/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-create-pr/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-create-pr/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-create-pr/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-create-pr/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-create-pr/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/work-backlog.md (anchor .claude not present)
skipped     .cursor/commands/sd-work-backlog.md (anchor .cursor not present)
skipped     .gemini/commands/sd/work-backlog.toml (anchor .gemini not present)
skipped     .github/prompts/sd-work-backlog.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-work-backlog.md (anchor .opencode not present)
skipped     .agent/workflows/sd-work-backlog.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/work-backlog.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-work-backlog.md (anchor .devin not present)
skipped     .factory/commands/sd/work-backlog.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-work-backlog.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-work-backlog.md (anchor .pi not present)
skipped     .qoder/commands/sd-work-backlog.md (anchor .qoder not present)
skipped     .trae/commands/sd-work-backlog.md (anchor .trae not present)
skipped     .zcode/commands/sd/work-backlog.md (anchor .zcode not present)
skipped     .agent/skills/sd-work-backlog/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-work-backlog/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-work-backlog/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-work-backlog/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-work-backlog/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-work-backlog/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-work-backlog/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-work-backlog/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-work-backlog/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-work-backlog/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/work-designs.md (anchor .claude not present)
skipped     .cursor/commands/sd-work-designs.md (anchor .cursor not present)
skipped     .gemini/commands/sd/work-designs.toml (anchor .gemini not present)
skipped     .github/prompts/sd-work-designs.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-work-designs.md (anchor .opencode not present)
skipped     .agent/workflows/sd-work-designs.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/work-designs.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-work-designs.md (anchor .devin not present)
skipped     .factory/commands/sd/work-designs.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-work-designs.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-work-designs.md (anchor .pi not present)
skipped     .qoder/commands/sd-work-designs.md (anchor .qoder not present)
skipped     .trae/commands/sd-work-designs.md (anchor .trae not present)
skipped     .zcode/commands/sd/work-designs.md (anchor .zcode not present)
skipped     .agent/skills/sd-work-designs/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-work-designs/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-work-designs/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-work-designs/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-work-designs/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-work-designs/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-work-designs/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-work-designs/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-work-designs/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-work-designs/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/audit-repo.md (anchor .claude not present)
skipped     .cursor/commands/sd-audit-repo.md (anchor .cursor not present)
skipped     .gemini/commands/sd/audit-repo.toml (anchor .gemini not present)
skipped     .github/prompts/sd-audit-repo.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-audit-repo.md (anchor .opencode not present)
skipped     .agent/workflows/sd-audit-repo.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/audit-repo.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-audit-repo.md (anchor .devin not present)
skipped     .factory/commands/sd/audit-repo.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-audit-repo.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-audit-repo.md (anchor .pi not present)
skipped     .qoder/commands/sd-audit-repo.md (anchor .qoder not present)
skipped     .trae/commands/sd-audit-repo.md (anchor .trae not present)
skipped     .zcode/commands/sd/audit-repo.md (anchor .zcode not present)
skipped     .agent/skills/sd-audit-repo/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-audit-repo/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-audit-repo/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-audit-repo/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-audit-repo/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-audit-repo/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-audit-repo/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-audit-repo/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-audit-repo/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-audit-repo/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/watch-pr.md (anchor .claude not present)
skipped     .cursor/commands/sd-watch-pr.md (anchor .cursor not present)
skipped     .gemini/commands/sd/watch-pr.toml (anchor .gemini not present)
skipped     .github/prompts/sd-watch-pr.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-watch-pr.md (anchor .opencode not present)
skipped     .agent/workflows/sd-watch-pr.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/watch-pr.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-watch-pr.md (anchor .devin not present)
skipped     .factory/commands/sd/watch-pr.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-watch-pr.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-watch-pr.md (anchor .pi not present)
skipped     .qoder/commands/sd-watch-pr.md (anchor .qoder not present)
skipped     .trae/commands/sd-watch-pr.md (anchor .trae not present)
skipped     .zcode/commands/sd/watch-pr.md (anchor .zcode not present)
skipped     .agent/skills/sd-watch-pr/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-watch-pr/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-watch-pr/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-watch-pr/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-watch-pr/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-watch-pr/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-watch-pr/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-watch-pr/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-watch-pr/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-watch-pr/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/fix-ci.md (anchor .claude not present)
skipped     .cursor/commands/sd-fix-ci.md (anchor .cursor not present)
skipped     .gemini/commands/sd/fix-ci.toml (anchor .gemini not present)
skipped     .github/prompts/sd-fix-ci.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-fix-ci.md (anchor .opencode not present)
skipped     .agent/workflows/sd-fix-ci.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/fix-ci.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-fix-ci.md (anchor .devin not present)
skipped     .factory/commands/sd/fix-ci.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-fix-ci.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-fix-ci.md (anchor .pi not present)
skipped     .qoder/commands/sd-fix-ci.md (anchor .qoder not present)
skipped     .trae/commands/sd-fix-ci.md (anchor .trae not present)
skipped     .zcode/commands/sd/fix-ci.md (anchor .zcode not present)
skipped     .agent/skills/sd-fix-ci/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-fix-ci/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-fix-ci/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-fix-ci/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-fix-ci/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-fix-ci/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-fix-ci/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-fix-ci/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-fix-ci/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-fix-ci/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/update-deps.md (anchor .claude not present)
skipped     .cursor/commands/sd-update-deps.md (anchor .cursor not present)
skipped     .gemini/commands/sd/update-deps.toml (anchor .gemini not present)
skipped     .github/prompts/sd-update-deps.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-update-deps.md (anchor .opencode not present)
skipped     .agent/workflows/sd-update-deps.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/update-deps.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-update-deps.md (anchor .devin not present)
skipped     .factory/commands/sd/update-deps.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-update-deps.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-update-deps.md (anchor .pi not present)
skipped     .qoder/commands/sd-update-deps.md (anchor .qoder not present)
skipped     .trae/commands/sd-update-deps.md (anchor .trae not present)
skipped     .zcode/commands/sd/update-deps.md (anchor .zcode not present)
skipped     .agent/skills/sd-update-deps/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-update-deps/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-update-deps/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-update-deps/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-update-deps/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-update-deps/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-update-deps/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-update-deps/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-update-deps/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-update-deps/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/test-gaps.md (anchor .claude not present)
skipped     .cursor/commands/sd-test-gaps.md (anchor .cursor not present)
skipped     .gemini/commands/sd/test-gaps.toml (anchor .gemini not present)
skipped     .github/prompts/sd-test-gaps.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-test-gaps.md (anchor .opencode not present)
skipped     .agent/workflows/sd-test-gaps.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/test-gaps.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-test-gaps.md (anchor .devin not present)
skipped     .factory/commands/sd/test-gaps.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-test-gaps.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-test-gaps.md (anchor .pi not present)
skipped     .qoder/commands/sd-test-gaps.md (anchor .qoder not present)
skipped     .trae/commands/sd-test-gaps.md (anchor .trae not present)
skipped     .zcode/commands/sd/test-gaps.md (anchor .zcode not present)
skipped     .agent/skills/sd-test-gaps/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-test-gaps/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-test-gaps/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-test-gaps/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-test-gaps/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-test-gaps/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-test-gaps/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-test-gaps/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-test-gaps/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-test-gaps/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/retro.md (anchor .claude not present)
skipped     .cursor/commands/sd-retro.md (anchor .cursor not present)
skipped     .gemini/commands/sd/retro.toml (anchor .gemini not present)
skipped     .github/prompts/sd-retro.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-retro.md (anchor .opencode not present)
skipped     .agent/workflows/sd-retro.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/retro.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-retro.md (anchor .devin not present)
skipped     .factory/commands/sd/retro.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-retro.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-retro.md (anchor .pi not present)
skipped     .qoder/commands/sd-retro.md (anchor .qoder not present)
skipped     .trae/commands/sd-retro.md (anchor .trae not present)
skipped     .zcode/commands/sd/retro.md (anchor .zcode not present)
skipped     .agent/skills/sd-retro/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-retro/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-retro/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-retro/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-retro/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-retro/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-retro/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-retro/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-retro/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-retro/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/ship.md (anchor .claude not present)
skipped     .cursor/commands/sd-ship.md (anchor .cursor not present)
skipped     .gemini/commands/sd/ship.toml (anchor .gemini not present)
skipped     .github/prompts/sd-ship.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-ship.md (anchor .opencode not present)
skipped     .agent/workflows/sd-ship.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/ship.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-ship.md (anchor .devin not present)
skipped     .factory/commands/sd/ship.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-ship.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-ship.md (anchor .pi not present)
skipped     .qoder/commands/sd-ship.md (anchor .qoder not present)
skipped     .trae/commands/sd-ship.md (anchor .trae not present)
skipped     .zcode/commands/sd/ship.md (anchor .zcode not present)
skipped     .agent/skills/sd-ship/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-ship/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-ship/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-ship/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-ship/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-ship/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-ship/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-ship/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-ship/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-ship/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/review-pr.md (anchor .claude not present)
skipped     .cursor/commands/sd-review-pr.md (anchor .cursor not present)
skipped     .gemini/commands/sd/review-pr.toml (anchor .gemini not present)
skipped     .github/prompts/sd-review-pr.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-review-pr.md (anchor .opencode not present)
skipped     .agent/workflows/sd-review-pr.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/review-pr.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-review-pr.md (anchor .devin not present)
skipped     .factory/commands/sd/review-pr.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-review-pr.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-review-pr.md (anchor .pi not present)
skipped     .qoder/commands/sd-review-pr.md (anchor .qoder not present)
skipped     .trae/commands/sd-review-pr.md (anchor .trae not present)
skipped     .zcode/commands/sd/review-pr.md (anchor .zcode not present)
skipped     .agent/skills/sd-review-pr/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-review-pr/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-review-pr/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-review-pr/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-review-pr/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-review-pr/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-review-pr/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-review-pr/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-review-pr/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-review-pr/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/review-local.md (anchor .claude not present)
skipped     .cursor/commands/sd-review-local.md (anchor .cursor not present)
skipped     .gemini/commands/sd/review-local.toml (anchor .gemini not present)
skipped     .github/prompts/sd-review-local.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-review-local.md (anchor .opencode not present)
skipped     .agent/workflows/sd-review-local.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/review-local.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-review-local.md (anchor .devin not present)
skipped     .factory/commands/sd/review-local.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-review-local.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-review-local.md (anchor .pi not present)
skipped     .qoder/commands/sd-review-local.md (anchor .qoder not present)
skipped     .trae/commands/sd-review-local.md (anchor .trae not present)
skipped     .zcode/commands/sd/review-local.md (anchor .zcode not present)
skipped     .agent/skills/sd-review-local/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-review-local/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-review-local/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-review-local/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-review-local/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-review-local/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-review-local/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-review-local/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-review-local/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-review-local/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/review-learnings.md (anchor .claude not present)
skipped     .cursor/commands/sd-review-learnings.md (anchor .cursor not present)
skipped     .gemini/commands/sd/review-learnings.toml (anchor .gemini not present)
skipped     .github/prompts/sd-review-learnings.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-review-learnings.md (anchor .opencode not present)
skipped     .agent/workflows/sd-review-learnings.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/review-learnings.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-review-learnings.md (anchor .devin not present)
skipped     .factory/commands/sd/review-learnings.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-review-learnings.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-review-learnings.md (anchor .pi not present)
skipped     .qoder/commands/sd-review-learnings.md (anchor .qoder not present)
skipped     .trae/commands/sd-review-learnings.md (anchor .trae not present)
skipped     .zcode/commands/sd/review-learnings.md (anchor .zcode not present)
skipped     .agent/skills/sd-review-learnings/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-review-learnings/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-review-learnings/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-review-learnings/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-review-learnings/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-review-learnings/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-review-learnings/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-review-learnings/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-review-learnings/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-review-learnings/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/full-check.md (anchor .claude not present)
skipped     .cursor/commands/sd-full-check.md (anchor .cursor not present)
skipped     .gemini/commands/sd/full-check.toml (anchor .gemini not present)
skipped     .github/prompts/sd-full-check.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-full-check.md (anchor .opencode not present)
skipped     .agent/workflows/sd-full-check.md (anchor .agent not present).......................................................
----------------------------------------------------------------------
Ran 122 tests in 13.135s

OK

skipped     .codebuddy/commands/sd/full-check.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-full-check.md (anchor .devin not present)
skipped     .factory/commands/sd/full-check.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-full-check.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-full-check.md (anchor .pi not present)
skipped     .qoder/commands/sd-full-check.md (anchor .qoder not present)
skipped     .trae/commands/sd-full-check.md (anchor .trae not present)
skipped     .zcode/commands/sd/full-check.md (anchor .zcode not present)
skipped     .agent/skills/sd-full-check/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-full-check/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-full-check/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-full-check/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-full-check/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-full-check/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-full-check/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-full-check/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-full-check/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-full-check/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/housekeeping.md (anchor .claude not present)
skipped     .cursor/commands/sd-housekeeping.md (anchor .cursor not present)
skipped     .gemini/commands/sd/housekeeping.toml (anchor .gemini not present)
skipped     .github/prompts/sd-housekeeping.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-housekeeping.md (anchor .opencode not present)
skipped     .agent/workflows/sd-housekeeping.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/housekeeping.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-housekeeping.md (anchor .devin not present)
skipped     .factory/commands/sd/housekeeping.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-housekeeping.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-housekeeping.md (anchor .pi not present)
skipped     .qoder/commands/sd-housekeeping.md (anchor .qoder not present)
skipped     .trae/commands/sd-housekeeping.md (anchor .trae not present)
skipped     .zcode/commands/sd/housekeeping.md (anchor .zcode not present)
skipped     .agent/skills/sd-housekeeping/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-housekeeping/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-housekeeping/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-housekeeping/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-housekeeping/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-housekeeping/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-housekeeping/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-housekeeping/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-housekeeping/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-housekeeping/SKILL.md (anchor .trae not present)
skipped     .claude/commands/sd/update-spec.md (anchor .claude not present)
skipped     .cursor/commands/sd-update-spec.md (anchor .cursor not present)
skipped     .gemini/commands/sd/update-spec.toml (anchor .gemini not present)
skipped     .github/prompts/sd-update-spec.prompt.md (anchor .github not present)
skipped     .opencode/commands/sd-update-spec.md (anchor .opencode not present)
skipped     .agent/workflows/sd-update-spec.md (anchor .agent not present)
skipped     .codebuddy/commands/sd/update-spec.md (anchor .codebuddy not present)
skipped     .devin/workflows/sd-update-spec.md (anchor .devin not present)
skipped     .factory/commands/sd/update-spec.md (anchor .factory not present)
skipped     .kilocode/workflows/sd-update-spec.md (anchor .kilocode not present)
skipped     .pi/prompts/sd-update-spec.md (anchor .pi not present)
skipped     .qoder/commands/sd-update-spec.md (anchor .qoder not present)
skipped     .trae/commands/sd-update-spec.md (anchor .trae not present)
skipped     .zcode/commands/sd/update-spec.md (anchor .zcode not present)
skipped     .agent/skills/sd-update-spec/SKILL.md (anchor .agent not present)
skipped     .codebuddy/skills/sd-update-spec/SKILL.md (anchor .codebuddy not present)
skipped     .devin/skills/sd-update-spec/SKILL.md (anchor .devin not present)
skipped     .factory/skills/sd-update-spec/SKILL.md (anchor .factory not present)
skipped     .kilocode/skills/sd-update-spec/SKILL.md (anchor .kilocode not present)
skipped     .kiro/skills/sd-update-spec/SKILL.md (anchor .kiro not present)
skipped     .pi/skills/sd-update-spec/SKILL.md (anchor .pi not present)
skipped     .qoder/skills/sd-update-spec/SKILL.md (anchor .qoder not present)
skipped     .reasonix/skills/sd-update-spec/SKILL.md (anchor .reasonix not present)
skipped     .trae/skills/sd-update-spec/SKILL.md (anchor .trae not present)
.............................
----------------------------------------------------------------------
Ran 29 tests in 4.174s

OK
.........................................................
----------------------------------------------------------------------
Ran 57 tests in 19.113s

OK
...............................
----------------------------------------------------------------------
Ran 31 tests in 19.401s

OK
.................................
----------------------------------------------------------------------
Ran 33 tests in 10.325s

OK
........................
----------------------------------------------------------------------
Ran 24 tests in 14.104s

OK
.......................
----------------------------------------------------------------------
Ran 23 tests in 9.360s

OK
...............
----------------------------------------------------------------------
Ran 15 tests in 8.919s

OK
.....................
----------------------------------------------------------------------
Ran 21 tests in 4.907s

OK
pack 1.0.0
target: /var/folders/49/lgq0px596nq4sf2vmcwbl2bh0000gn/T/sd-ai-command-pack-test-fbi5y7pv
mode: remove
removed        .gitignore
missing        .github/copilot-instructions.md
removed        .agents/skills/sd-audit-repo/SKILL.md
removed        .agents/skills/sd-audit-repo/charters/accessibility-i18n.md
removed        .agents/skills/sd-audit-repo/charters/architecture.md
removed        .agents/skills/sd-audit-repo/charters/bloat.md
removed        .agents/skills/sd-audit-repo/charters/consumer-impact.md
removed        .agents/skills/sd-audit-repo/charters/correctness.md
removed        .agents/skills/sd-audit-repo/charters/dependencies.md
removed        .agents/skills/sd-audit-repo/charters/design.md
removed        .agents/skills/sd-audit-repo/charters/documentation.md
removed        .agents/skills/sd-audit-repo/charters/improvements.md
removed        .agents/skills/sd-audit-repo/charters/observability.md
removed        .agents/skills/sd-audit-repo/charters/performance.md
removed        .agents/skills/sd-audit-repo/charters/release-hygiene.md
removed        .agents/skills/sd-audit-repo/charters/security.md
removed        .agents/skills/sd-audit-repo/charters/testing.md
removed        .agents/skills/sd-audit-repo/charters/tooling.md
removed        .agents/skills/sd-continue/SKILL.md
removed        .agents/skills/sd-create-pr/SKILL.md
removed        .agents/skills/sd-finish-work/SKILL.md
removed        .agents/skills/sd-fix-ci/SKILL.md
removed        .agents/skills/sd-full-check/SKILL.md
removed        .agents/skills/sd-housekeeping/SKILL.md
removed        .agents/skills/sd-retro/SKILL.md
removed        .agents/skills/sd-review-learnings/SKILL.md
removed        .agents/skills/sd-review-local/SKILL.md
removed        .agents/skills/sd-review-pr/SKILL.md
removed        .agents/skills/sd-ship/SKILL.md
removed        .agents/skills/sd-start/SKILL.md
removed        .agents/skills/sd-test-gaps/SKILL.md
removed        .agents/skills/sd-update-deps/SKILL.md
removed        .agents/skills/sd-update-spec/SKILL.md
removed        .agents/skills/sd-watch-pr/SKILL.md
removed        .agents/skills/sd-work-backlog/SKILL.md
removed        .agents/skills/sd-work-designs/SKILL.md
removed        .gito/config.toml
removed        .gito/sd-ai-command-pack.env
removed        .prism/rules.json
removed        .prism/rules.schema.json
removed        .sd-ai-command-pack/installed-targets.txt
missing        .sd-ai-command-pack/local-only.txt
removed        .sd-ai-command-pack/manifest.json
removed        .sd-ai-command-pack/provenance.json
removed        docs/SD_AI_COMMAND_PACK.md
removed        scripts/sd-ai-command-pack-full-check.sh
removed        scripts/sd-ai-command-pack-housekeeping.sh
removed        scripts/sd-ai-command-pack-install-audit.py
removed        scripts/sd-ai-command-pack-pr-body-scope.py
removed        scripts/sd-ai-command-pack-record-session.py
removed        scripts/sd-ai-command-pack-review-learnings.py
removed        scripts/sd-ai-command-pack-review-local.sh
removed        scripts/sd-ai-command-pack-review-preflight.mjs
removed        scripts/sd-ai-command-pack-review-scope.sh
removed        scripts/sd-ai-command-pack-shell-lib.sh
removed        scripts/sd-ai-command-pack-toolchain.sh
removed        scripts/sd-ai-command-pack-update-spec-kb.py
removed        scripts/sd_ai_command_pack_lib.py
......................
----------------------------------------------------------------------
Ran 22 tests in 14.923s

OK
.......................
----------------------------------------------------------------------
Ran 23 tests in 1.606s

OK
.....candidate ledger error: stale
candidate validation error: --check-ledger cannot be combined with --consumer
........
----------------------------------------------------------------------
Ran 13 tests in 1.185s

OK
candidate ledger: valid for the current pack payload and fleet
..........
----------------------------------------------------------------------
Ran 10 tests in 9.392s

OK
...................
----------------------------------------------------------------------
Ran 19 tests in 7.398s

OK
........
----------------------------------------------------------------------
Ran 8 tests in 0.278s

OK
.................
----------------------------------------------------------------------
Ran 17 tests in 4.660s

OK
.........
----------------------------------------------------------------------
Ran 9 tests in 4.175s

OK
..........
----------------------------------------------------------------------
Ran 10 tests in 3.086s

OK
.......
----------------------------------------------------------------------
Ran 7 tests in 0.011s

OK
......
----------------------------------------------------------------------
Ran 6 tests in 0.014s

OK
.........
----------------------------------------------------------------------
Ran 9 tests in 0.010s

OK
.........
----------------------------------------------------------------------
Ran 9 tests in 0.032s

OK
...
----------------------------------------------------------------------
Ran 3 tests in 0.150s

OK
".venv/bin/python" -m coverage combine
".venv/bin/python" -m coverage report --include="install.py,installer/*" --fail-under=100
Name                      Stmts   Miss Branch BrPart  Cover   Missing
---------------------------------------------------------------------
install.py                  151      0     64      0   100%
installer/__init__.py         0      0      0      0   100%
installer/fileops.py        394      0    154      0   100%
installer/localonly.py      182      0     66      0   100%
installer/manifest.py       141      0     40      0   100%
installer/provenance.py     125      0     40      0   100%
installer/registry.py        87      0     14      0   100%
installer/removal.py        136      0     64      0   100%
installer/status.py          40      0      0      0   100%
---------------------------------------------------------------------
TOTAL                      1256      0    442      0   100%
PYTHON_BIN=".venv/bin/python" bash .github/scripts/check-shipped-script-coverage.sh
Name                                                  Stmts   Miss Branch BrPart  Cover   Missing
-------------------------------------------------------------------------------------------------
scripts/sd-ai-command-pack-fleet-candidate-check.py     187     12     48      3    94%   102->104, 295-296, 338-343, 357-358, 418, 491
scripts/sd-ai-command-pack-fleet-preflight.py           103      8     28      4    91%   16, 40-41, 55-56, 60, 94, 174
scripts/sd-ai-command-pack-install-audit.py             428     40    196     23    90%   286, 311-312, 316-317, 319, 322, 331, 334-335, 340-343, 345-346, 349-353, 383, 393, 397, 443, 531->525, 574, 584, 694-697, 700-703, 740-741, 791, 842, 844-845, 893, 906, 908, 938-939, 989-991
scripts/sd-ai-command-pack-pr-body-scope.py             259     48    110     18    79%   258->253, 265-273, 277-291, 301-310, 317-320, 349, 352-355, 361, 367, 369, 375, 380, 386, 398, 400, 417-418, 477, 483, 512->514, 562, 570, 574, 614, 665->667
scripts/sd-ai-command-pack-record-session.py            257     45    102     22    80%   62-66, 76, 96-97, 120, 153->155, 166-167, 179, 197-198, 202, 205, 219, 231, 235-238, 242, 291-292, 297-298, 303, 329, 343-348, 376->378, 389-395, 410-411, 412->414, 415-420, 426-427, 455-457, 467-468
scripts/sd-ai-command-pack-review-learnings.py          474     93    180     41    74%   79-83, 93, 113-114, 185->187, 197->199, 200-203, 211, 222-226, 249, 259, 279, 315, 326, 337, 348, 359-387, 400-404, 420-424, 439-443, 490, 495, 516, 523, 571->573, 598, 622-624, 634, 639, 642, 698, 724-739, 764, 770, 790->792, 806->808, 810, 814, 817, 871-872, 874-875, 877-878, 887->894, 933, 944, 948-949, 955-956
scripts/sd-ai-command-pack-update-spec-kb.py            735     98    328     53    84%   146-147, 154-159, 188, 227, 259-260, 324, 328, 330, 332, 338, 344, 377, 397-398, 426, 440, 475, 481->483, 489, 490->492, 504, 539, 541->543, 549, 565, 575-578, 583-585, 650, 656-674, 682, 691, 715, 772, 774, 776, 786-790, 794-796, 799, 806, 938-942, 947-949, 985, 1025-1028, 1104-1110, 1157, 1177-1179, 1193, 1195, 1221, 1223, 1228-1233, 1306-1314, 1409, 1411, 1446, 1448, 1452, 1494-1497, 1527-1529
scripts/sd_ai_command_pack_fleet_lib.py                 205     10     90      5    95%   46-49, 51, 177, 278-279, 299, 306
scripts/sd_ai_command_pack_lib.py                        57      0     18      1    99%   59->61
-------------------------------------------------------------------------------------------------
TOTAL                                                  2705    354   1100    170    84%

==> scripts/sd-ai-command-pack-fleet-preflight.py coverage floor 82%
Name                                            Stmts   Miss Branch BrPart  Cover   Missing
-------------------------------------------------------------------------------------------
scripts/sd-ai-command-pack-fleet-preflight.py     103      8     28      4    91%   16, 40-41, 55-56, 60, 94, 174
-------------------------------------------------------------------------------------------
TOTAL                                             103      8     28      4    91%

==> scripts/sd-ai-command-pack-fleet-candidate-check.py coverage floor 90%
Name                                                  Stmts   Miss Branch BrPart  Cover   Missing
-------------------------------------------------------------------------------------------------
scripts/sd-ai-command-pack-fleet-candidate-check.py     187     12     48      3    94%   102->104, 295-296, 338-343, 357-358, 418, 491
-------------------------------------------------------------------------------------------------
TOTAL                                                   187     12     48      3    94%

==> scripts/sd-ai-command-pack-install-audit.py coverage floor 89%
Name                                          Stmts   Miss Branch BrPart  Cover   Missing
-----------------------------------------------------------------------------------------
scripts/sd-ai-command-pack-install-audit.py     428     40    196     23    90%   286, 311-312, 316-317, 319, 322, 331, 334-335, 340-343, 345-346, 349-353, 383, 393, 397, 443, 531->525, 574, 584, 694-697, 700-703, 740-741, 791, 842, 844-845, 893, 906, 908, 938-939, 989-991
-----------------------------------------------------------------------------------------
TOTAL                                           428     40    196     23    90%

==> scripts/sd-ai-command-pack-pr-body-scope.py coverage floor 78%
Name                                          Stmts   Miss Branch BrPart  Cover   Missing
-----------------------------------------------------------------------------------------
scripts/sd-ai-command-pack-pr-body-scope.py     259     48    110     18    79%   258->253, 265-273, 277-291, 301-310, 317-320, 349, 352-355, 361, 367, 369, 375, 380, 386, 398, 400, 417-418, 477, 483, 512->514, 562, 570, 574, 614, 665->667
-----------------------------------------------------------------------------------------
TOTAL                                           259     48    110     18    79%

==> scripts/sd-ai-command-pack-record-session.py coverage floor 79%
Name                                           Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------------------------
scripts/sd-ai-command-pack-record-session.py     257     45    102     22    80%   62-66, 76, 96-97, 120, 153->155, 166-167, 179, 197-198, 202, 205, 219, 231, 235-238, 242, 291-292, 297-298, 303, 329, 343-348, 376->378, 389-395, 410-411, 412->414, 415-420, 426-427, 455-457, 467-468
------------------------------------------------------------------------------------------
TOTAL                                            257     45    102     22    80%

==> scripts/sd-ai-command-pack-review-learnings.py coverage floor 73%
Name                                             Stmts   Miss Branch BrPart  Cover   Missing
--------------------------------------------------------------------------------------------
scripts/sd-ai-command-pack-review-learnings.py     474     93    180     41    74%   79-83, 93, 113-114, 185->187, 197->199, 200-203, 211, 222-226, 249, 259, 279, 315, 326, 337, 348, 359-387, 400-404, 420-424, 439-443, 490, 495, 516, 523, 571->573, 598, 622-624, 634, 639, 642, 698, 724-739, 764, 770, 790->792, 806->808, 810, 814, 817, 871-872, 874-875, 877-878, 887->894, 933, 944, 948-949, 955-956
--------------------------------------------------------------------------------------------
TOTAL                                              474     93    180     41    74%

==> scripts/sd-ai-command-pack-update-spec-kb.py coverage floor 83%
Name                                           Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------------------------
scripts/sd-ai-command-pack-update-spec-kb.py     735     98    328     53    84%   146-147, 154-159, 188, 227, 259-260, 324, 328, 330, 332, 338, 344, 377, 397-398, 426, 440, 475, 481->483, 489, 490->492, 504, 539, 541->543, 549, 565, 575-578, 583-585, 650, 656-674, 682, 691, 715, 772, 774, 776, 786-790, 794-796, 799, 806, 938-942, 947-949, 985, 1025-1028, 1104-1110, 1157, 1177-1179, 1193, 1195, 1221, 1223, 1228-1233, 1306-1314, 1409, 1411, 1446, 1448, 1452, 1494-1497, 1527-1529
------------------------------------------------------------------------------------------
TOTAL                                            735     98    328     53    84%

==> scripts/sd_ai_command_pack_lib.py coverage floor 88%
Name                                Stmts   Miss Branch BrPart  Cover   Missing
-------------------------------------------------------------------------------
scripts/sd_ai_command_pack_lib.py      57      0     18      1    99%   59->61
-------------------------------------------------------------------------------
TOTAL                                  57      0     18      1    99%

==> scripts/sd_ai_command_pack_fleet_lib.py coverage floor 90%
Name                                      Stmts   Miss Branch BrPart  Cover   Missing
-------------------------------------------------------------------------------------
scripts/sd_ai_command_pack_fleet_lib.py     205     10     90      5    95%   46-49, 51, 177, 278-279, 299, 306
-------------------------------------------------------------------------------------
TOTAL                                       205     10     90      5    95%; land via PR + gated merge in
  the target repo.
- R3. Enroll in the fleet: add a consumers.json entry (name
  se-ai-command-pack, github platypeeps/se-ai-command-pack, pathHint
  ~/repos/platypeeps/se-ai-command-pack, platforms [claude,gemini,github,
  opencode], rolloutPriority 60, candidateChecks [["make","test"]]).
- R4. Regenerate docs/fleet/candidate-validation.json via
  scripts/sd-ai-command-pack-fleet-candidate-check.py so the ledger digests
  and the new consumer's pass status are current.
- R5. Land the fleet change via PR + gated merge in the sd repo; fleet tests
  green. No manifest version bump (docs/fleet/** is source inventory, not
  shipped payload).

## Acceptance Criteria

- [ ] se-ai-command-pack main contains the installed SD payload; its
  make test passes; install-audit clean.
- [ ] consumers.json + candidate-validation.json include se-ai-command-pack
  with status passed; fleet schema/consistency tests green.
- [ ] Both PRs merged; both repos clean.
