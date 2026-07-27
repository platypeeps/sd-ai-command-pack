# Design: reverse claude gitignore to commit-by-default

## Design Summary

Today `.claude/` is deliberately treated as local Claude Code state: the managed
block ignores `.claude/**` and negates back only SD-owned files, and a
supporting layer (provenance preservation + audit downgrade) exists so that
gitignored claude markers do not fail installs. We reverse this so `.claude/`
behaves like every other platform directory — ignore only a known-local
deny-list, commit everything else — while keeping the accommodation layer for
`--local-only` installs. This makes Trellis-on-Claude, repo-authored skills, and
shared settings reproducible from the committed tree.

## Why reverse a deliberate design

The current design's cost outweighs its benefit: it makes Trellis-on-Claude the
only platform not reproducible from a clone, silently drops repo-authored
`.claude/skills/` (e.g. loadsmith's `loadsmith-swift-app`), hides
Trellis-generated `.claude/settings.json`, and contradicts how the pack treats
the other 15 platforms. An allow-list cannot fix the authored-skill case because
the generator cannot predict per-repo skill names; only commit-by-default can.
The blanket's stated benefit (avoid committing personal Claude state) is
preserved by the known-local deny-list, since personal/global Claude state lives
under `~/.claude/`, not the repo's `.claude/`.

## Generator change

`installer/registry.py` claude `local_gitignore_patterns` →

```
.claude/settings.local.json
.claude/**/*.local.*
.claude/**/.cache/
.claude/**/cache/
.claude/**/logs/
.claude/**/tmp/
.claude/**/*.log
```

plus R2 defensive local denies. No `.claude/**`, no `!` negations. This mirrors
the codex/gemini/codebuddy groups (adds the `tmp/` line claude currently lacks).

## Shared-vs-local policy (C-2)

- Committed: SD files, Trellis runtime (`commands/trellis/`, `hooks/`, `agents/`,
  `skills/trellis-*/`), repo-authored `.claude/skills/*`, and `.claude/settings.json`.
- Ignored (the complete in-repo local set — nothing else):
  `.claude/settings.local.json`, `.claude/**/*.local.*`, `.claude/**/.cache/`,
  `.claude/**/cache/`, `.claude/**/logs/`, `.claude/**/tmp/`, `.claude/**/*.log`.
  Claude Code keeps personal/session state (projects, todos, history,
  shell-snapshots, statsig, sessions) under `~/.claude/`, not the repo, so no
  further denies are needed.
- `.claude/settings.json` is committed because it is Trellis-generated shared
  config (hook wiring; source repo's `env` holds only
  `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`), and machine-specific permissions
  belong in the ignored `settings.local.json` (CONTRIBUTING.md:141). Because a
  consumer `settings.json` `env` block or an authored skill could in principle
  contain a secret, the rollout gate (below) mandates a secret scan before any
  consumer commit.

## Accommodation layer stays (C-3 correctness)

`installer/provenance.py` `is_gitignored_path()`/`preserved_receipt_targets()`
and both install-audit twins keep their gitignored handling because it still
serves `--local-only` installs and receipt-stripping repos (rwbp-website). Under
this change, in a NORMAL claude install `is_gitignored_path()` simply returns
False for claude markers, so entries are tracked normally rather than
"kept-as-gitignored". Only the claude-specific docstrings/comments/examples and
the tests that used claude as the gitignored fixture change; the fixtures move to
a `--local-only` case that is still genuinely gitignored.

## Dependent registries and classifiers

Changing what `.claude/` commits ripples into three data sets that encode the
old boundary and must move together:

- `trellis_local_only` for claude (`installer/registry.py:80`) currently lists
  `commands/trellis/`, `hooks/`, `skills/trellis-*/` but omits
  `.claude/agents/trellis-*.md` and `.claude/settings.json`. Under commit-by-
  default those are now committed in a normal install, so `--local-only` must
  still exclude them — add both. This set drives `LOCAL_ONLY_TRELLIS_EXCLUDES`
  and `LOCAL_ONLY_TRACKED_CHECK_PATHS`.
- The two generated-file classifiers — `sd-ai-command-pack-review-scope.sh` and
  `sd-ai-command-pack-review-preflight.mjs` (each with a `templates/` twin) — recognize claude
  agents/hooks as copied adapter surface but omit `.claude/settings.json`, even
  though they recognize other platforms' settings. Add `.claude/settings.json`
  so review-scope classification treats it as copied surface, keeping both twins
  byte-consistent, with regression tests.

## Migration behaviour

A normal install/refresh always rewrites the managed `.gitignore` block
(`install.py:458` → `installer/fileops.py:531`), replacing the marker block
in place; the old `.claude/**` block is thereby removed on refresh. The
`_LEGACY_CLAUDE_GITIGNORE_SEQUENCE` migration (`fileops.py:49`) that strips the
old unmarked 4-line claude blanket is retained (it still cleans ancient
pre-marker installs) and its test is updated to reflect the new end state.

## R5 regression test design

Create an isolated temp git repo, write the generated managed block, then use
real `git check-ignore` (not pattern-compilation, which cannot model git's
ignored-parent/negation/`**` semantics). Assert an explicit expected-tracked set
(markers, `commands/trellis/x.md`, `hooks/x.py`, `agents/trellis-check.md`,
`settings.json`, `skills/trellis-meta/SKILL.md`, `skills/authored-x/SKILL.md`)
and expected-ignored set (`settings.local.json`, `foo.local.json`, `x/.cache/y`,
`x/logs/y`). Add the cross-platform invariant that no platform's declared `markers` are
ignored — also via real `git check-ignore` against each platform's generated
managed block, not pattern comparison. Both assertions must fail on the
pre-change config and pass after — because the manifest's claude targets are
SD-only, the expected set is declared explicitly in the test, not derived from
the manifest.

## Rollout and rollback (C-6, accurate)

- Rollout trigger: ANY normal consumer refresh (not only `--force`) rewrites the
  consumer `.gitignore` and exposes previously-ignored `.claude/` files;
  `install_trellis_gitignore` is unconditional in `_install_payload`. The
  separate `sd-fleet-refresh` (I3) must therefore inventory and secret-scan every
  newly-unignored `.claude/` path per consumer, then produce a reviewed commit.
- Rollback: reverting the registry patterns restores the old block on the next
  refresh, but it does NOT untrack files already committed during a rollout —
  those require an explicit `git rm --cached` + re-ignore. This task itself
  touches no consumer, so its own rollback (revert registry + source `.gitignore`
  + tests/docs/specs + version) is clean; the rollout's rollback is the
  non-trivial one and is owned by I3.

## Docs/spec parity (C-4)

Edit the SHIPPED sources: `templates/docs/SD_AI_COMMAND_PACK.md` (then `make sync`
regenerates `docs/SD_AI_COMMAND_PACK.md`), `README.md`, `CONTRIBUTING.md`, and
the two specs. Editing the installed `docs/` mirror directly would be overwritten
by `make sync` and break template parity.

## Release (C-5)

Minor `manifest.json` bump (consumer-visible installer behavior), `CHANGELOG.md`
heading, and a regenerated `docs/fleet/candidate-validation.json` via the fleet
candidate-check against the exact new payload; the release/tag gate verifies that
ledger against the payload digest, so a stale record blocks release.
