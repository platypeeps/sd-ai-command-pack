# Verify or remove the @opencode-ai/plugin dependency

## Problem

Audit finding A-004 (P2·S, dependencies), 2026-07-15 @ f6f3932:
`.opencode/package.json:3` declares `@opencode-ai/plugin: ^1.14.39` but no
code imports it — `.opencode/plugins/*.js` and `.opencode/lib/*.js` use
Node builtins only; `bun.lock` resolves ~30 packages including
`effect@4.0.0-beta.83` and `@msgpackr-extract` native binaries. Caveat from
the audit: 0.7.3 pinned this dependency deliberately, and OpenCode's plugin
loader may require the SDK to be resolvable even without imports — must be
verified before removal. Related P3s fold in: no Dependabot npm coverage
for `.opencode/` (A-018) and caret/lockfile drift `^1.14.39` vs resolved
1.18.0 (A-019).

## Goal

The `.opencode` dependency tree is either removed or explicitly justified,
pinned, and monitored — no unaudited supply-chain surface.

## Requirements

- Verify against OpenCode's plugin-loader behavior whether the SDK must be
  resolvable (check upstream docs/source; test in a consumer repo).
- If not required: remove the dependency and lockfile churn.
- If required: document the intentional declaration in package.json, pin
  the exact resolved version (or raise the caret floor), and add a
  Dependabot npm entry for `/.opencode`.

## Acceptance Criteria

- [ ] Loader requirement answered with evidence (doc link or repro).
- [ ] Dependency removed OR documented+pinned+Dependabot-covered.
- [ ] OpenCode dogfood surface still functions (session-start plugin runs).
