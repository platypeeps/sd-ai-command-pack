# Verify or remove the @opencode-ai/plugin dependency

## Problem

Audit finding A-004 (P2·S, dependencies), 2026-07-15 @ f6f3932: the deleted
OpenCode package manifest declared `@opencode-ai/plugin: ^1.14.39` but no code
imports it — `.opencode/plugins/*.js` and `.opencode/lib/*.js` use Node builtins
only. The deleted Bun lockfile resolved ~30 packages including
`effect@4.0.0-beta.83` and `@msgpackr-extract` native binaries. Caveat from the
audit: 0.7.3 pinned this dependency deliberately, and OpenCode's plugin loader
may require the SDK to be resolvable even without imports — must be verified
before removal. Related P3s fold in: no Dependabot npm coverage for
`.opencode/` (A-018) and caret/lockfile drift `^1.14.39` vs resolved 1.18.0
(A-019).

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

- [x] Loader requirement answered with evidence (doc link or repro).
- [x] Dependency removed OR documented+pinned+Dependabot-covered.
- [x] OpenCode dogfood surface still functions (session-start plugin runs).

## Implementation Notes

OpenCode's plugin docs state that local `.opencode/plugins/` files are loaded
automatically at startup, while an OpenCode package manifest is only needed
when local plugins or custom tools import external packages:
<https://github.com/anomalyco/opencode/blob/dev/packages/web/src/content/docs/plugins.mdx>.

The loader source matches that contract. File plugins resolve directly through
the path resolver and dynamic import path, package metadata is optional for file
plugins, and compatibility handling is scoped to npm-sourced plugins:
<https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/plugin/loader.ts>
and
<https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/plugin/shared.ts>.

The local OpenCode dogfood plugins import only Node builtins and sibling helper
files, so `@opencode-ai/plugin` is not required. Removed the OpenCode package
manifest and Bun lockfile; this also makes the folded Dependabot and loose-caret
audit findings moot for this repo.

OpenCode dogfood verification loaded `.opencode/plugins/session-start.js` with
Node's ESM importer and confirmed it returns a `chat.message` hook without
resolving `@opencode-ai/plugin`.

Upstream Trellis ownership note: Trellis still templates the OpenCode package
manifest with `@opencode-ai/plugin`. Future `trellis update` runs may reintroduce
the dependency until Trellis drops it or documents why it is required. Do not
open a Trellis PR without explicit maintainer consent; use this paste-ready
handoff:

```markdown
Task: remove or justify Trellis' default OpenCode @opencode-ai/plugin dependency.

Context: sd-ai-command-pack verified that local `.opencode/plugins/*.js` files
that import only Node builtins and sibling helpers do not require
`@opencode-ai/plugin` to be installed. OpenCode's docs describe
the OpenCode package manifest as the mechanism for external packages used by
local plugins/tools, and the loader resolves file plugins directly with
optional package metadata.

Request: Update Trellis' OpenCode template/install path so it does not seed
the OpenCode package manifest or Bun lockfile with `@opencode-ai/plugin` unless
a generated plugin actually imports it, or document the loader requirement and
add package update coverage.
```
