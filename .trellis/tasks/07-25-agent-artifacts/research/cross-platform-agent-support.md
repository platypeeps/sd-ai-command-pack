# Cross-platform custom-agent support (settled research input)

Date: 2026-07-25. Method: verified against official platform docs via web research; local
evidence from this repo and the sibling `se-ai-command-pack`. This document is a settled
input to the agent-artifacts design: the final design MUST honor the findings and the
recommendation recorded here. A tailored twin lives in the SE repo task
`.trellis/tasks/07-25-agent-artifacts/`.

## Verdict

1. Custom agent definition files are now supported by roughly 10 of SD's 17 target
   platforms. The Claude subagent format (Markdown + YAML frontmatter `name`,
   `description`, `tools`, `model`; body = system prompt) is the de facto standard dialect;
   Codex (TOML) and Kiro (JSON) are the only format outliers among supporters.
2. No new install layer is needed. The existing registry -> generator -> manifest ->
   installer chain is the cross-platform layer; agents are a fifth manifest kind plus a
   `PlatformInfo` capability flag, modeled on the existing `structured_question_tool` gate.

## Platform support matrix (SD's 17 targets)

| Platform | Agent files | Location & format | Status (2026-07) |
|---|---|---|---|
| claude | Yes | `.claude/agents/*.md`, MD + YAML | Stable |
| codex | Yes | `.codex/agents/*.toml`, TOML (`name`, `description`, `developer_instructions`, opt. `model`, `model_reasoning_effort`, `sandbox_mode`, `mcp_servers`) | GA 2026-03; project agents load only in TRUSTED projects; open issue openai/codex#15250 (not visible from SDK/exec sessions) |
| gemini | Yes | `.gemini/agents/*.md`, MD + YAML (`tools` wildcards, `model`, `max_turns`, `timeout_mins`, inline `mcpServers`) | On by default; kill-switch still under `experimental.enableAgents`; subagents run WITHOUT per-tool confirmation |
| github (Copilot) | Yes | `.github/agents/*.agent.md`, MD + YAML (`description` required, `tools`, `model`, `target`, `disable-model-invocation`, `user-invocable`) | GA on github.com/CLI/VS Code; preview JetBrains/Eclipse/Xcode; prompt body max 30,000 chars |
| opencode | Yes | `.opencode/agents/*.md` (PLURAL dir; older docs show singular), `mode: subagent`, `permission` allow/deny/ask maps | Stable |
| cursor | Yes | `.cursor/agents/*.md`; ALSO auto-loads `.claude/agents/` and `.codex/agents/` (`.cursor` wins conflicts) | Stable since 2.4; nested subagents since 2.5 |
| kiro | Yes | `.kiro/agents/*.json`, JSON (`prompt`, `tools`, `allowedTools`, `resources`) | Stable |
| droid (Factory) | Yes | `.factory/droids/*.md`, MD, top-level files only; Task-tool `subagent_type` targets | Default-on (Experimental toggle) |
| codebuddy | Yes | `.codebuddy/agents/*.md`, Claude-style + `permissionMode`, `skills`, `mcpServers` | Stable |
| antigravity | Yes | `.agents/agents/<name>.md` (workspace), MD + YAML (`commandExecutionPolicy`, `mcpServers`) | Core shipped; adjacent features preview |
| devin | No | Cloud Playbooks/Knowledge only; no droppable file | n/a |
| trae | No (UI only) | Custom agents created via IDE UI; no file convention | n/a |
| qoder | Partial | SDK `options.agents` programmatic only; `.qoder/` refs unofficial | n/a |
| zcode (Zed) | No | Agent Profiles (settings presets) and ACP external agents; no subagent definitions | n/a |
| pi / reasonix | Unknown/No | No documented file convention found | treat as unsupported |
| shared (`.agents/`) | No (as agent target) | `.agents/` is the skills tree; note Antigravity claims `.agents/agents/` - watch for collision | n/a |

## De facto standard

- MD + YAML frontmatter with body-as-system-prompt is used in near-identical dialects by
  claude, gemini, github, opencode, cursor, droid, codebuddy, antigravity.
- No formal cross-vendor spec exists (AGENTS.md = instructions only; SKILL.md = skills).
  Transpiling one canonical MD source is mostly renames + frontmatter dialect mapping,
  plus TOML (codex) and JSON (kiro) transforms.
- Trellis already demonstrates 5-platform agent generation from neutral sources in this
  checkout (`.trellis/agents/` -> per-platform agent dirs for Claude, Codex, Gemini,
  OpenCode, and GitHub).

## Implications for SD (the recommendation)

1. Author canonical agents once (neutral MD + frontmatter) in `templates/`; render
   per-platform in `generate-command-surfaces.py`.
2. Add `agent` as a manifest kind and a `subagent_support` (or similar) capability field on
   `PlatformInfo` - exactly the shape of the existing `structured_question_tool` gate.
   Platforms without support simply get no agent rows; `if-anchor-exists` semantics and
   gitignore-tuple invariants extend naturally.
3. Graceful degradation stays in command bodies: the `sd-audit-repo` dispatch-protocol
   pattern ("on sub-agent dispatch platforms, run reviewers in parallel; on inline
   platforms, work sequentially") is the house template for every dispatching command.
4. Trust model: sub-agents MUST inherit the checkout-trust preflight classification
   (fork PRs -> untrusted; indeterminate stays indeterminate). Structured answers cannot
   override safety gates; dispatch prompts restate the classification.
5. Wrinkles the design must handle:
   - Cursor auto-reads `.claude/agents/` and `.codex/agents/`: an SD install writing agent
     files to multiple platform dirs in ONE repo produces duplicate picker entries in
     Cursor. Naming must be collision-safe; consider whether Cursor gets its own rows at all.
   - Copilot 30k-char body cap constrains charter content embedded in agent definitions
     (charters should be read at runtime, not inlined).
   - Gemini subagents run with no per-tool confirmation - scope their tools tightly.
   - Codex project-scope agents require project trust; document this in install output.
   - Class-2 platforms (no hook injection) need dispatch prompts to carry context
     explicitly (Trellis `Active task:` first-line convention).
6. First candidates for named agents where enforced tool restriction pays:
   sd-audit-reviewer / sd-audit-refuter (read-only; 15 charters become their payloads),
   sd-ci-triager (read logs, no push). Deliberate serializations stay untouched:
   sd-update-deps merges, sd-work-backlog task loop, sd-housekeeping collector.

## Sources

- Codex subagents: https://learn.chatgpt.com/docs/agent-configuration/subagents (GA 2026-03-16); openai/codex issue #15250
- Gemini CLI subagents: https://github.com/google-gemini/gemini-cli/blob/main/docs/core/subagents.md ; announcement https://developers.googleblog.com/subagents-have-arrived-in-gemini-cli/
- Copilot custom agents: https://docs.github.com/en/copilot/reference/custom-agents-configuration ; CLI how-to https://github.blog/ai-and-ml/github-copilot/from-one-off-prompts-to-workflows-how-to-use-custom-agents-in-github-copilot-cli/
- OpenCode agents: https://opencode.ai/docs/agents/
- Cursor subagents: https://cursor.com/docs/subagents.md (2.4/2.5 changelogs)
- Amp manual (context for SE sibling): https://ampcode.com/manual
- Kiro: https://kiro.dev/docs/cli/custom-agents/ ; Factory: https://docs.factory.ai/cli/configuration/custom-droids ; CodeBuddy: https://www.codebuddy.ai/docs/cli/sub-agents ; Antigravity: https://antigravity.google/docs/subagents ; Zed: https://zed.dev/docs/ai/agent-profiles ; Qoder: https://docs.qoder.com/en/cli/sdk/agents ; Trae: https://docs.trae.ai/ide/agent ; Devin: https://docs.devin.ai/release-notes/2026
