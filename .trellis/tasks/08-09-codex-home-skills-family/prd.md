# PRD: Add CODEX_HOME skills destination family to machine installer

## Goal
Codex resolves user-scope skills from `$CODEX_HOME/skills` (default `~/.codex/skills`). Evaluate adding a sixth destination family so codex machine-scope rows can ship once an executed probe passes.

## Requirements
- Executed probe: codex CLI resolves a user-scope skill from `$CODEX_HOME/skills` in a scratch home; persist command lines and decisive output with a negative control.
- Only on a passing probe: add the family to `installer/machinepayload.py`, partition dispositions, and receipt family allowlist; fail-closed otherwise (codex rows stay repo-native).
- Retention interaction: revisit `retainVendoredFor: ["codex", ...]` for consumers once codex rows ship machine-scope.

## Acceptance criteria
- Probe evidence persisted; partition/validation gates updated with tests; codex stays repo-native if the probe fails.
