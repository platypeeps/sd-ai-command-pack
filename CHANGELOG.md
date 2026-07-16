# Changelog

## 0.13.3 - 2026-07-16

- Hardened pack text writes: generated installer text files now report
  symlink conflicts instead of replacing in-repo symlinks, and the shipped
  recorder, review-learnings, and update-spec KB helpers write user-facing
  markdown/ignore files through temp-file + `os.replace` atomic writes. The KB
  refresh reports symlinked ignore files as partial refresh conflicts instead
  of silently writing through or replacing them.

## 0.13.2 - 2026-07-16

- Batched install-audit `git check-ignore` probes so each audit phase resolves
  candidate ignored paths with one `git check-ignore --stdin -z` subprocess
  instead of one subprocess per missing or unlisted pack-shaped path. Existing
  fail-closed behavior is preserved for missing git, non-repo roots, git
  errors, and the `check-ignore` exit-code-1 no-match case.

## 0.13.1 - 2026-07-16

- P3 polish batch from the 2026-07-15 audit (nine items). Shipped-payload
  changes: the review preflight's git subprocess calls now set an explicit
  64 MiB buffer and fail hard when git cannot run instead of proceeding with
  an empty diff; the preflight also caches its documentation file list and
  file reads per run; typing-only fixes in the session recorder and install
  audit. Repo-side: the install.py facade drops 42 unused re-exports, the
  installer modules gain responsibility docstrings, the REVIEW_PR_REMOTE_*
  variables are documented in the configuration references, review-learnings
  gains git-failure and untracked-diff tests, `make sync` wraps the dogfood
  install and KB refresh, `STRICT=1 make lint` turns missing-tool skips into
  errors, and mypy now covers install.py and the shipped scripts.

## 0.13.0 - 2026-07-16

- Generated the bespoke Claude/Gemini/GitHub command adapters and all derived
  manifest command entries from a single registry command list
  (`make generate` + a drift test); adding a command is now a skill, a neutral
  body, and one list entry. One-time canonical manifest reordering; entry set
  unchanged.
- Merged `sd-review-local-all` into `sd-review-local` behind the `all`
  argument (same runner, `--full-codebase`). The old command is removed;
  refreshes delete the retired installed files automatically when their
  content is vouched by prior provenance (drifted copies are preserved unless
  `--force`). Invoke `sd-review-local` with `all` for the full-codebase loop.
- Added `sd-ship`: a composite orchestrator sequencing the sd-create-pr flow,
  the sd-review-pr loop, the sd-watch-pr settle watcher, and the
  sd-housekeeping merge gate with `until=pr|review|merge` stop-points. It adds
  no new gate logic; every stage's own gates remain authoritative.

## 0.12.0 - 2026-07-16

- Added six distributed SDLC edge-loop commands, each with the full adapter
  surface and format-drift tests: `sd-watch-pr` (bounded PR settle watcher
  handing off to the housekeeping merge gate), `sd-fix-ci` (red-CI triage that
  classifies real/flake/infra failures and never weakens tests), `sd-update-deps`
  (sequential gated triage of dependency-bot PRs; majors always manual),
  `sd-fleet-refresh` (consumer fleet rollout per the documented procedure, one
  consumer at a time), `sd-test-gaps` (coverage-driven test authoring, test
  files only), and `sd-retro` (structured debug retrospectives recorded to the
  journal with consent-gated prevention proposals). All tuning is via command
  arguments — no new environment variables — and merge-affecting behavior
  defers to the existing housekeeping gate criteria.

## 0.11.0 - 2026-07-15

- Added the distributed `sd-audit-repo` command and shared skill: a formal
  multi-dimension repository audit that dispatches one read-only reviewer per
  charter (12 always-on dimensions plus fingerprint-selected consumer-impact,
  observability, and accessibility-i18n), adversarially verifies findings,
  reconciles them against the Trellis backlog, and produces a canonical report
  with mandatory sections backed by a committed findings ledger at
  `.trellis/audit/ledger.md`. Supports `dimensions=` filtering,
  `depth=quick|standard|deep`, and a `follow-up` mode that re-verifies open
  ledger items instead of re-sweeping the repository. The review preflight
  treats `.trellis/audit/ledger.md` as an optional documented path so repos
  that have not yet run their first audit pass the documentation path check.

## 0.10.5 - 2026-07-15

- Made the `sd-housekeeping` skill always report the current Trellis task and a
  `Next Steps` section listing the next high-value Trellis tasks / roadmap items,
  including on verification-only clean runs. Previously the report could end with
  "No follow-up needed for this cleanup stream." and omit the task inventory, so
  the end-of-run handoff format was inconsistent across repos. Documentation only
  — no command, flag, or script behavior change.

## 0.10.4 - 2026-07-15

- Internal micro-refactors of shipped helpers (no behavior change): unified the
  review-learnings git-command wrappers behind one runner, and precompute the
  PR-body scope rule's normalized glob patterns at rule-build time instead of
  re-normalizing them on every path match. Byte-identical output and exit codes.

## 0.10.3 - 2026-07-15

- Internal consolidation of shipped helpers (no behavior change): deduplicated
  the three inline git wrappers in the update-spec KB tool behind one helper,
  compute the source→destination mapping once per run instead of four times, and
  simplified the review-learnings GraphQL response walk. Byte-identical output
  and exit codes.

## 0.10.2 - 2026-07-14

- Trimmed the installed guide's verbatim per-platform `.gitignore` example to a
  single representative block plus a note that the installer regenerates the
  full per-platform set, and removed README prose that duplicated the guide's
  "Updating the pack" and "What is installed" sections. Documentation only — no
  command, flag, or behavior change; ~240 fewer lines across README and the guide.

## 0.10.1 - 2026-07-14

- Replaced the update-spec KB dry-run/`--check` conflict classification — which
  matched human-readable message suffixes — with structured issue kinds, so
  editing a display string can no longer silently change which entries count as
  conflicts. Emitted text and exit codes are unchanged.
- Micro-efficiency in shipped helpers (no behavior change): hoisted the KB
  category-title lookup out of the directory-walk loop, removed a duplicate
  `git status` on the session recorder's no-new-journal fallback, and made the
  review-learnings shell-shebang probe split once and cache its verdict per path.

## 0.10.0 - 2026-07-14

- Made remote PR review rounds use GitHub's documented Copilot request identity
  and require author-matched review activity before counting a request as
  materialized.
- Added plan-before-apply installer conflict handling, concurrent-run coverage,
  rollback guidance, and an optional fail-soft consumer version comparison.
- Hardened CI with SHA-pinned actions, bounded dependency updates, installer
  mypy coverage, OpenCode syntax checks, and a server-side direct-main scope
  backstop.
- Closed shell and housekeeping reliability gaps around disjoint histories,
  interrupt cleanup, delimiter parsing, default-branch detection, and per-user
  review-tool caches; refreshed contributor and security documentation.

## 0.9.2 - 2026-07-14

- Backfilled the missing release ledger and historical version tags since
  `v0.6.0`.
- Required every manifest version bump to add a matching top changelog release
  heading, and added post-CI automation that creates the corresponding tag on
  `main`.

## 0.9.1 - 2026-07-14

- Migrated the exact legacy Claude adapter ignore sequence into the managed
  `.gitignore` block without changing later project-owned overrides.
- Excluded generated Repomix maps from legacy-reference scans while retaining
  scans of their source documentation.

## 0.9.0 - 2026-07-11

- Added a distributed, Bash 3.2-compatible toolchain preflight that selects and
  verifies a supported Python once, reports project-check candidates without
  executing them, and provides deterministic JSON diagnostics.
- Updated SD workflow guidance to separate project checks, pack full-checks,
  and optional AI review while avoiding nested Git writes during finish-work.
- Reduced the default remote PR review loop from five rounds to two while
  retaining the environment-variable override for exceptional review cycles.

## 0.8.7 - 2026-07-09

- Bounded Prism and Gito provider calls, capped repeated Prism fallback
  failures, and tightened empty-response detection and Prism rules validation.
- Hardened the direct-main pre-push guard for rename and unusual-filename
  handling with NUL-delimited Git paths and behavioral coverage.
- Replaced installer wildcard imports with explicit public surfaces, restored
  Ruff import checks, and enabled import-order and Bugbear lint rules.

## 0.8.6 - 2026-07-09

- Fixed rollout CI blockers by classifying the installed pack manifest as
  generated SD command-pack state in review preflight and scope checks.
- Reworded shipped Copilot guidance and remove-mode docs to avoid optional
  directory/glob examples tripping consumer narrow-glob preflight checks.

## 0.8.5 - 2026-07-09

- Added a generated installed manifest snapshot and manifest-backed audit
  completeness checks, including explicit `--expected-platform` support for
  fleet refreshes.
- Added checked-in fleet inventory and a source-owned fleet preflight helper
  so at-target repos are skipped before opening refresh PRs.

## 0.8.4 - 2026-07-09

- Single-sourced OpenCode command adapters from the neutral command templates
  and added registry-derived parity coverage for thin command fan-out.
- Reconciled GitHub prompt body drift against the neutral command source and
  strengthened bespoke adapter body-parity tests.

## 0.8.3 - 2026-07-09

- Hardened `install.py --remove` so consumer-editable receipts and provenance
  can discover prior pack files but cannot authorize deletion of `.git/*` or
  arbitrary non-pack repository files, even when hashes match and `--force` is
  set.

## 0.8.2 - 2026-07-09

- Fixed session recorder retry safety for local-only or fresh workspaces where
  `.trellis/workspace/` is still untracked, so reruns patch the pending journal
  entry instead of appending duplicate sessions.

## 0.8.1 - 2026-07-09

- Made the session recorder retry-safe after a post-append staging or commit
  failure, so rerunning finish-work patches the pending journal entry instead
  of appending a duplicate session.
- Reconciled the closed fleet-refresh loop, archived stale rollout acceptance
  criteria, and the duplicate Session 29/30 journal entry.

## 0.8.0 - 2026-07-09

- Added the distributed `sd-work-designs` command and shared skill for working
  through Trellis tasks that still need `design.md` or `implement.md` planning
  artifacts.

## 0.7.5 - 2026-07-09

- Moved shared command adapter bodies to neutral templates and generated the
  OpenCode command surface from those sources.

## 0.7.4 - 2026-07-08

- Consolidated common shell helpers used by the local review runners while
  preserving the shipped script interfaces.

## 0.7.3 - 2026-07-09

- Added maintainer contributor workflow docs and a Makefile for setup, tests,
  linting, audits, and the SD full-check gate.
- Made the shipped full-check script warn in the pack source checkout when the
  `.githooks` pre-push guard is not armed.
- Pinned the OpenCode plugin dependency used by the dogfood platform files.

## 0.7.2 - 2026-07-09

- Fixed installed-guide quick links, documented
  `SD_AI_COMMAND_PACK_REVIEW_PR_SELECTOR`, and made the pack-source full-check
  env-var documentation gate cover shipped skill-only variables.
- Added maintainer guidance that `templates/**` are the shipped payload source
  of truth and replaced stale-prone README per-command platform lists with
  references to the supported adapter mapping.

## 0.7.1 - 2026-07-09

- Hardened `sd-ai-command-pack-review-preflight.mjs`: symlink invocation now
  runs the preflight instead of silently exiting, Node versions below 16.9 get
  a clear error, copied-surface checks include untracked files, workspace index
  parsing tolerates trailing whitespace, and the regular-file-only
  documentation scan behavior is documented.

## 0.7.0 - 2026-07-08

- Added the distributed `sd-work-backlog` command and shared skill for
  sequentially selecting implementation-ready Trellis backlog tasks, completing
  them through the normal `sd-create-pr`/`sd-housekeeping` flow, and recording
  or addressing follow-ups before moving to the next task.

## 0.6.1 - 2026-07-08

- Hardened the `sd-review-pr` wait-for-review step against a remote-review race:
  the completion signal (a reviewer request clearing / a review event) can fire
  before the reviewer's inline review-thread comments are queryable, so an
  immediate thread read can report a false "clean". The skill now waits a short
  settle interval before reading threads and treats the pre-merge unresolved-thread
  re-check (the housekeeping merge guard) as the authoritative clean check, never a
  single post-completion read.

## 0.6.0 - 2026-07-08

- Added the full-check Obsidian KB freshness lane
  (`SD_AI_COMMAND_PACK_FULL_CHECK_KB`) for repos that maintain generated
  `.obsidian-kb/` knowledge folders.
- Made `sd-ai-command-pack-update-spec-kb.py` return exit code 3 when a KB
  refresh is blocked by conflicts that need manual reconciliation.
- Hardened shipped scripts and audits across Bash 3.2 compatibility,
  all-platform install-audit coverage, PR-body scope matching, review-runner
  robustness, recorder/housekeeping behavior, and KB runtime exclusions.
- Added a release guard in full-check so shipped payload changes under
  `templates/**`, the installed usage guide, or `manifest.json` must include a
  manifest version bump.
- Started the release log and tag process at `v0.6.0`; earlier versions remain
  traceable through git history but are not retroactively changelogged here.
