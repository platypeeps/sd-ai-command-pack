# Claude Code plugin packaging + private marketplace — Implementation Plan

Companion to `design.md` (same task). One coherent PR. Canonical
direction everywhere: edit `templates/**`, refresh root mirrors with
`make sync` (`CONTRIBUTING.md:143`); never hand-edit root copies.

## Execution Order

1. **Own-location sibling resolution across pack scripts** (smallest
   independent step; behavior-compatible for fat installs).
   a. `templates/scripts/sd-ai-command-pack-toolchain.sh`:
      `run` / `run-python` resolve pack-script arguments (bare or
      `scripts/`-prefixed names matching the pack pattern) against
      `SCRIPT_DIR` only — no CWD probe, no shadowing surface;
      non-pack arguments pass through unchanged.
   b. Audit every shipped script for repo-root `scripts/…` literals
      (2026-08-09 grep: 15 scripts). Convert functional sibling
      construction to own-file-location resolution
      (`Path(__file__)`, `BASH_SOURCE` dir, `import.meta.url`; known
      functional sites include `sd-ai-command-pack-review.py:33-34`,
      `sd-ai-command-pack-full-check.sh:824`); convert usage/help
      prose to layout-neutral bare-command wording (keeps the
      `bin/` residue scope down to the enumerated semantic-data
      allowlist).
   c. Source-side normalization of non-invocation forms:
      skill Markdown existence tests
      (`templates/.agents/skills/sd-create-pr/SKILL.md:212` + grep
      siblings) → layout-neutral probes; command-adapter repo-root
      verification prose → layout-neutral resolvability wording,
      edited in the authored `.github/command-sources/<name>.md`
      (sd-review, sd-review-local, sd-review-learnings,
      sd-audit-repo, sd-housekeeping) and regenerated via
      `generate-command-surfaces.py`.
   d. New boundary test: no shipped script builds sibling paths from
      repo-root `scripts/` literals (AST for Python, grep contract
      for shell/Node; pattern `tests/test_state_root_boundary.py`).
   e. `make sync` to refresh root mirrors; commit canonical + mirror
      together.
2. **Generator** `.github/scripts/generate-plugin.py`: consume
   `docs/fleet/surface-partition.json` `machine-claude` slice joined
   to `manifest.json` by target; build the full tree in a temp dir,
   validate all six fail-closed conditions (missing source row,
   unreadable source, unmapped kind, two-scope residue gate — strict
   Markdown, `bin/` with per-file semantic-data allowlist seeded for
   `install-audit.py`/`pr-body-scope.py` layout globs — empty
   version, dependency closure with justified allowlist seeded for
   the `sd-review-pr` fleet-classifier reference), then atomically
   replace `plugins/sd/**` (deleting files absent from the new set).
   Token rewrite + node-prefix cleanup per design. `--check` mode
   diffs regenerated output against the committed tree including
   extraneous files. `plugin.json` version from
   `manifest.json["version"]`. Deterministic output.
3. **Marketplace catalog**: hand-author
   `.claude-plugin/marketplace.json` (owner `platypeeps`, plugin
   `sd`, `source: "./plugins/sd"`).
4. **Wire build + lint**: Makefile `generate` gains
   `generate-plugin.py` after `partition-surfaces.py`; add the script
   to ruff/mypy inventories (Makefile lint lines + the same list in
   `.github/workflows/tests.yml`). Run `make generate`; commit
   `plugins/sd/**`.
5. **Tests** `tests/test_generate_plugin.py` + step-1 tests: mapping,
   flattening, exec bits, rules exclusion, rewrite forms, residue
   failure, closure failure + allowlist, missing-source failure,
   unmapped-kind failure, version stamp, stale-file removal,
   `--check` against committed tree (CI freshness gate; pattern
   `tests/test_partition_surfaces.py:81`), determinism, toolchain
   resolution (own-location, passthrough, missing → error).
6. **Release integration** in `.github/scripts/prepare-release.py`:
   add `partition-surfaces.py` then `generate-plugin.py` to the
   `prepare_release` chain (it does not call `make generate`);
   fail-closed check `plugins/sd/.claude-plugin/plugin.json` version
   == `manifest.json` version; extend BOTH payload classifiers —
   `_is_payload_path` in `prepare-release.py` AND the
   `payload_singletons`/`templates/` classifier in
   `templates/scripts/sd-ai-command-pack-full-check.sh` (~line 712;
   PR CI reaches it via `run_pack_source_drift_gates`,
   `tests.yml:643`) — to cover `plugins/`,
   `.claude-plugin/marketplace.json`, and
   `.github/scripts/generate-plugin.py`; extend the drift-gate tests
   to prove the new paths trip each gate. Candidate digest
   deliberately NOT extended
   (vendored-payload identity only; design records rationale).
7. **CI**: in `.github/workflows/tests.yml` lint lane, install the
   Claude Code CLI (pinned) and run
   `claude plugin validate plugins/sd --strict`.
8. **Docs + spec**: marketplace/private-auth section in
   `templates/docs/SD_AI_COMMAND_PACK.md` and repo docs
   (`gh auth setup-git`,
   `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1`, cache
   pre-seed); plugin-generation contract subsection in
   `.trellis/spec/backend/manifest-and-filesystem.md`; CHANGELOG
   entry under the next release block (manifest version bump rides
   the shipped-script changes from step 1).

Dependency note: step 2 needs step 1's contract fixed first (rewrite
and closure targets depend on the resolution rules). Steps 3–8 follow
2.

## Validation Plan

Focused:
- `.venv/bin/python -m unittest tests.test_generate_plugin -v` (and
  step-1 test modules)
- `make generate && git status --porcelain` → empty
- `claude plugin validate plugins/sd --strict` → exit 0
- grep gate: `grep -rE "scripts/sd[-_]ai[-_]command[-_]pack"
  plugins/sd/skills plugins/sd/commands` → no hits (strict Markdown
  scope); `bin/` hits must exactly match the semantic-data allowlist
  (generator `--check` proves it)

Broad (last-iteration full gate):
- `make release-prep` — exit 0 (includes the new chain + payload gate)
- `.venv/bin/python -m unittest` — full suite green
- `node scripts/sd-ai-command-pack-review-preflight.mjs` — 0 failures

Acceptance mapping (PRD):
- AC1 (`--plugin-dir` smoke in payload-free repo): manual smoke during
  implementation; end-to-end install pass stays with the parent's
  integration validation.
- AC2 (`validate --strict` in CI): step 7.
- AC3 (version lockstep): steps 2 + 6.
- AC4 (grep gate, two scopes per PRD): generator condition 4 + test
  + focused grep above.

## Documentation And Spec Updates

- `templates/docs/SD_AI_COMMAND_PACK.md` + generated doc mirror.
- `.trellis/spec/backend/manifest-and-filesystem.md`: "Plugin
  generation" subsection citing the partition artifact contract and
  the closure/allowlist rule.
- CHANGELOG: plugin dir, marketplace, script-resolution change
  (behavioral note: own-location sibling resolution; fat installs
  behavior-compatible), payload-path gate extension.

## Review Notes

- Reviewer-sensitive: own-location resolution with no CWD probe
  (shadowing removed by construction; fat compatibility argued via
  SCRIPT_DIR == consumer scripts/), token rewrite + closure
  allowlist (the seeded `sd-review-pr` fleet-classifier entry is a
  pre-existing consumer-install gap — fleet scripts have zero
  manifest rows), plugin name `sd` (preserves `/sd:help`; collision
  tradeoff documented in design).
- The committed `plugins/sd/**` diff is large but 100% generated;
  review the generator, not the output.
- `sharedRuntime` duplication with `thin-machine-installer` is
  intentional contract, not an accident to "fix".

## Rollback Points

- After step 1 alone: revert = the audited template-script set +
  both source-normalization classes (skill existence tests AND the
  five edited `.github/command-sources/` files with their
  regenerated command adapters) + mirrors (one commit). Normal fat
  layouts remain
  compatible; removing CWD/shadowing resolution is an intentional,
  observable hardening change (current `run-python` passes relative
  arguments through unchanged, `toolchain.sh:477`).
- Before step 4's commit of `plugins/sd/**`: no generated output in
  tree; revert = delete new generator/tests/catalog.
- Full revert: delete `plugins/sd/`, `.claude-plugin/`, generator,
  tests, CI step, Makefile lines, prepare-release additions. Step-1
  script changes may stay (behavior-compatible) or revert with the
  rest; fat consumers see them only via a released version bump, and
  no consumer converts to thin before `thin-migration`.

## Follow-Ups (outside this PR)

- Fix `sd-review-pr` SKILL fleet-classifier reference (fleet-operator
  path invoking a script with no manifest row — already broken in
  vendored consumer installs); retire the closure-allowlist entry
  when done.
- `enabledPlugins` consumer seeding + payload removal → `thin-migration`.
- Machine installer consuming the same `sharedRuntime` rows →
  `thin-machine-installer`.
- `sd-status` plugin-version skew reporting → `thin-fleet-status-pins`.
- Archive/sha256 distribution channel: only if a stronger end-to-end
  digest is wanted later (parent design records the upgrade path).
