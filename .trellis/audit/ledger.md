# Audit ledger
Findings recorded by sd-audit-repo; managed by sd-audit-repo — humans may edit notes: lines.

## A-001 — Release version-bump/CHANGELOG gate is never enforced against a real PR diff in CI
- status: fixed
- severity: P1 · effort: M · confidence: Plausible
- dimension: tooling
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - .github/workflows/tests.yml:18-217 (no job runs the gate)
  - gate only in scripts/sd-ai-command-pack-full-check.sh:609 via main() :852
  - CI exercises it on synthetic fixtures only
    (tests/test_pack_drift.py:243-264)
  - .github/scripts/create-release-tag.py:72-73 silently no-ops when
    manifest.json unchanged
- why: A PR editing templates/**, scripts/**, or docs/** without a manifest
  bump passes every required lane and merges; auto-tag no-ops, so fleet
  consumers pinning releases never see the change.
- fix: Add a PR job running the real gate with
  SD_AI_COMMAND_PACK_FULL_CHECK_RELEASE_BASE_REF=origin/main (env var exists
  per tests/test_pack_drift.py:351); wire into ci-result needs.
- notes: tracked → .trellis/tasks/07-15-ci-release-gate-job

## A-002 — Managed-block/gitignore/receipt writers silently clobber symlinked targets
- status: fixed
- severity: P2 · effort: S · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - installer/fileops.py:390 install_trellis_gitignore, :406
    install_managed_block, installer/provenance.py:163
    _install_generated_text_file lack is_symlink() guards
  - _require_file_destination (fileops.py:196) follows symlinks
  - diverges from install_file (fileops.py:230) and remove_text_block_file
    (:533)
- why: A symlinked .gitignore or copilot-instructions.md is silently converted
  to a regular file; the symlink's original target is orphaned with stale
  content.
- fix: Apply the same is_symlink() conflict/preserve handling used by
  install_file and remove_text_block_file to the three writers.
- notes: tracked → .trellis/tasks/07-15-installer-write-safety

## A-003 — External subprocess calls have no timeout; a hung trellis init or git blocks the run unbounded
- status: fixed
- severity: P2 · effort: S · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - installer/localonly.py:163 (trellis init), :51, :224
  - installer/fileops.py:608, :634
  - installer/provenance.py:253
  - scripts install- audit.py:508, pr-body-scope.py:256, update-spec-kb.py:136,
    record- session.py:52
  - housekeeping.sh has zero timeout usage on gh/git network calls while shell-
    lib.sh:61 provides run_command_with_timeout
  - review- learnings.py:438/:495/:574 already set timeouts (journal-1.md:629
    records that failure class firing)
- why: A stalled external call (credential prompt, index.lock, network hang)
  blocks installs and automated cleanup/merge flows indefinitely with no
  diagnostic; the failure class already fired once per the journal.
- fix: Route git/gh subprocess calls through one guarded wrapper with default
  timeout + clear TimeoutExpired handling; source run_command_with_timeout in
  housekeeping.
- notes: tracked → .trellis/tasks/07-15-subprocess-timeout-hardening

## A-004 — @opencode-ai/plugin is declared but apparently never imported, dragging in a heavy unused tree
- status: fixed
- severity: P2 · effort: S · confidence: Plausible
- dimension: dependencies
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - .opencode/package.json:3 declares ^1.14.39
  - no imports found (.opencode/plugins/*.js + lib/*.js use Node builtins only)
  - bun.lock resolves ~30 packages incl. effect@4.0.0-beta.83 and @msgpackr-
    extract native binaries
- why: An unused dependency expands the supply-chain surface (native prebuilds
  + a beta upstream). Caveat: 0.7.3 pinned it deliberately and OpenCode's
  plugin loader may require the SDK to be resolvable — verify before removing.
- fix: Verify the loader requirement; remove the dep + lockfile, or document
  the intentional declaration in package.json.
- notes: resolved by .trellis/tasks/07-15-opencode-plugin-dependency-review;
  local OpenCode plugins do not import external packages, so
  .opencode/package.json and .opencode/bun.lock were removed. Upstream Trellis
  still templates the dependency; the task captures a consent-gated handoff.

## A-005 — PackFile.install policy is an unvalidated open string; a typo silently changes install selection
- status: fixed
- severity: P2 · effort: S · confidence: Plausible
- dimension: design
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - installer/manifest.py:85 accepts any string
  - validate_manifest (manifest.py:101-110) checks platform/kind but never
    install
  - registry.py:456-457 defines ALWAYS_INSTALL/IF_NOT_EXISTS but no
    IF_ANCHOR_EXISTS
  - fileops.py:165 falls through on unknown values
- why: A mistyped install value passes validation and silently flips selection
  behavior across 384 manifest entries.
- fix: Add IF_ANCHOR_EXISTS constant + KNOWN_INSTALL_MODES frozenset; validate
  file.install in validate_manifest.
- notes: tracked → .trellis/tasks/07-15-manifest-validation-tightening

## A-006 — Backend directory-structure spec predates the installer/ package split and misdirects contributors
- status: fixed
- severity: P2 · effort: S · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - .trellis/spec/backend/directory-structure.md:62 says PLATFORM_REGISTRY
    lives in install.py (:40, :71 similar
  - layout tree :16-36 omits installer/)
  - reality installer/registry.py:27 + 7-module package
  - contradicts sibling manifest-and-filesystem.md:307
- why: AGENTS.md and CONTRIBUTING.md point contributors at this spec as the
  canonical code map; it names the wrong module and contradicts its sibling
  spec.
- fix: Add installer/ to the layout and module organization; correct the
  PLATFORM_REGISTRY pointers.
- notes: tracked → .trellis/tasks/07-15-docs-accuracy-batch

## A-007 — Versioning scheme and public-surface stability boundary are undocumented
- status: fixed
- severity: P2 · effort: S · confidence: Plausible
- dimension: release-hygiene
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - CONTRIBUTING.md:52-63 documents only when to bump, never what
    major/minor/patch mean
  - zero hits for semver/breaking-change/public-surface docs
  - de-facto scheme (new command = minor) applied consistently but written
    nowhere
- why: Fleet consumers cannot tell from a version bump whether an upgrade is
  additive or breaking; 0.x semver permits breaks in any bump.
- fix: Add a Versioning section to CONTRIBUTING.md naming the scheme and the
  stable public surface vs internal helpers.
- notes: tracked → .trellis/tasks/07-15-docs-accuracy-batch

## A-008 — Shipped-scripts coverage floor is aggregate-only; individual scripts sit far below the nominal 76%
- status: fixed
- severity: P2 · effort: S · confidence: Plausible
- dimension: testing
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - .github/workflows/tests.yml:73 (--fail-under=76 on pooled TOTAL)
  - per-file reality: fleet-preflight.py 62%, review-learnings.py 69%, record-
    session.py 80% with TOTAL=79% passing
- why: A single script can regress toward 0% while CI stays green; the floor
  floors nothing per-file.
- fix: Enforce per-file floors (loop coverage report --include=<file> --fail-
  under=N per script).
- notes: tracked → .trellis/tasks/07-15-coverage-gate-per-file

## A-009 — Platform path layout re-encoded in 5+ components, reconciled only at directory granularity
- status: fixed
- severity: P2 · effort: M · confidence: Plausible
- dimension: architecture
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - installer/registry.py:27 PLATFORM_REGISTRY (dev-side authority) vs hand-
    copies in shipped scanners: install-audit.py:31 PACK_FILE_PATTERNS + :173
    REFERENCE_SCAN_BASES, pr-body-scope.py:97 DEFAULT_RULES, review-scope.sh:80
  - only guard tests/test_install_core.py:1331-1341 checks directory-prefix
    coverage, not subpath matches
- why: Refactoring a platform command subpath passes the coarse guard while
  silently desyncing install-audit and pr-body-scope in every consumer repo.
- fix: Strengthen the reconciliation test to fnmatch every non-shared manifest
  target against shipped-scanner patterns, or derive scanner tables from the
  manifest.
- notes: tracked → .trellis/tasks/07-15-scanner-manifest-reconciliation

## A-010 — Sibling scripts rewrite pre-existing files with non-atomic write_text, truncating data if the write fails midway
- status: fixed
- severity: P2 · effort: M · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - record-session.py:200 rewrites the entire journal (all history in text)
  - update-spec-kb.py:486 rewrites the user's .gitignore/.git/info/exclude,
    :1157/:1160
  - review-learnings.py:773
  - contrast installer/fileops.py:88 atomic_write_bytes
- why: O_TRUNC + crash/ENOSPC leaves session history or the user's .gitignore
  truncated or empty — the exact destroy-on-failed-write mode the installer
  package was built to avoid.
- fix: Route these writes through the installer's temp-file + os.replace atomic
  helper.
- notes: tracked → .trellis/tasks/07-15-installer-write-safety

## A-011 — Result status is a stringly-typed ad-hoc enum shared across module boundaries
- status: fixed
- severity: P2 · effort: M · confidence: Plausible
- dimension: design
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - installer/fileops.py:50-60 keeps status: str with membership frozensets
  - producers emit bare literals (fileops.py:237-271, removal.py, localonly.py)
  - consumers hard-code them (install.py:436 =='symlink-conflict', :676,
    removal.py:306)
- why: Renaming a producer status silently breaks cross-module consumers; only
  some sites use the centralized frozensets.
- fix: Model status as StrEnum/Literal per result type; replace inline literals
  with enum members.
- notes: tracked → .trellis/tasks/07-15-result-status-vocabulary

## A-012 — Adding a platform requires editing three parallel structures synced only by convention
- status: fixed
- severity: P2 · effort: M · confidence: Plausible
- dimension: design
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - installer/registry.py:452-453
    _LOCAL_GITIGNORE_GROUP_ORDER/_LOCAL_ONLY_GROUP_ORDER hand-list platforms
  - __pack__ sentinel special-cased at :475-502
  - invariant enforced only by tests/test_install_core.py:1279-1285
- why: A new registry row omitted from the order tuples silently drops its
  patterns from installed .gitignore/local-only output.
- fix: Derive ordering from PLATFORM_REGISTRY insertion order or assert set-
  equality at import time.
- notes: tracked → .trellis/tasks/07-15-manifest-validation-tightening

## A-013 — Shipped Python scripts have no shared helper module, unlike the shell scripts' shell-lib.sh
- status: fixed
- severity: P2 · effort: M · confidence: Plausible
- dimension: improvements
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - git shim re-implemented in record-session.py:50, pr-body- scope.py:255,
    review-learnings.py:423, update-spec-kb.py:135
  - repo-root detection duplicated (record-session.py:246, update-spec-
    kb.py:153)
  - shell have() copy-pasted in 4 scripts and absent from shell-lib
  - cross-refs architecture finding on platform tables
- why: Cross-cutting concerns (timeouts, encoding, error handling) drift per-
  copy — the timeout gap demonstrates it. A cross-script shared module was
  assessed as not viable in the July 2026 optimization pass; this audit adds
  concrete drift evidence for reopening that decision.
- fix: Ship scripts/sd_ai_command_pack_lib.py (twinned) housing the guarded git
  runner + repo-root resolver; move have() into shell-lib.sh.
- notes: tracked → .trellis/tasks/07-15-shared-python-script-lib

## A-014 — install-audit spawns one git check-ignore per absent/unrecorded target instead of batching
- status: fixed
- severity: P2 · effort: M · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - scripts/sd-ai-command-pack-install-audit.py:507-516 is_gitignored
    subprocess, called per-item at :535, :552, :627
  - gitignored-adapter checkouts fork ~1 git per absent target across 384
    targets
- why: Dozens of serial process spawns per routine audit, scaling linearly with
  pack size. Previously surfaced in the July 2026 optimization pass and
  deliberately declined as risky/low-gain; reopening requires a user decision.
- fix: Batch into a single git check-ignore --stdin -z call with set-membership
  lookup.
- notes: tracked → .trellis/tasks/07-15-install-audit-checkignore-batching
  (reopened by maintainer 2026-07-16 after prior July 2026 decline)

## A-015 — fleet-preflight CLI entrypoint has zero coverage
- status: fixed
- severity: P2 · effort: M · confidence: Plausible
- dimension: testing
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - scripts/sd-ai-command-pack-fleet-preflight.py:190-282 missing in coverage
  - tests/test_fleet_preflight.py calls helpers only, never main() or the
    script as a subprocess
- why: JSON/text rendering, --consumer selection, unknown-consumer SystemExit,
  and --fail-on-refresh-needed exit codes (which fleet automation keys on) are
  unexercised.
- fix: Add a main()/subprocess-level test against a temp fleet manifest
  asserting stdout and exit codes.
- notes: tracked → .trellis/tasks/07-15-coverage-gate-per-file

## A-016 — install.py re-export facade carries 42 dead forwards to a test-only seam
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: bloat
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - install.py:12-155 imports 135 names, :157-293 re-exports all via __all__
    (incl. private tuples and os/shutil)
  - sole consumer tests/install_test_support.py:21
  - 42 of 135 reached by nothing
  - parity test :1003 pins only existence + 3 symbols
- why: Double bookkeeping on a ~280-line surface that overstates what anything
  consumes; ruff cannot flag re-exports. Merged with the design finding on the
  same facade.
- fix: Delete the 42 unreferenced names from the import block and __all__, or
  narrow the facade to the test-reached symbols.
- notes: fixed in 0.13.1 via .trellis/tasks/07-15-p3-polish-batch —
  facade trim (42 dead forwards removed; reached set re-derived) (status flip owned by the next audit run)

## A-017 — review-preflight.mjs spawnSync default 1MiB maxBuffer silently under-reports large diffs
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - scripts/sd-ai-command-pack-review-preflight.mjs:780 gitStdout, :858
    currentDiffStats, :887 currentChangedPaths pass no maxBuffer
  - on overflow result.error is treated as empty (:785, :863, :892)
- why: Oversized change sets — the ones most needing review — can preflight as
  clean/empty: a failure that reports success.
- fix: Pass an explicit larger maxBuffer and treat result.error as a hard
  failure.
- notes: fixed in 0.13.1 via .trellis/tasks/07-15-p3-polish-batch —
  preflight spawnSync maxBuffer + hard-fail on result.error (status flip owned by the next audit run)

## A-018 — Dependabot does not monitor the .opencode npm/bun ecosystem
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: dependencies
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - .github/dependabot.yml:3-17 covers only pip (:4) and github-actions (:11)
  - no npm entry for /.opencode
- why: The tree with the widest supply-chain surface (native prebuilds, a
  prerelease) has zero automated CVE/freshness monitoring.
- fix: Add an npm-ecosystem entry for /.opencode (moot if the dependency is
  removed).
- notes: folded into .trellis/tasks/07-15-opencode-plugin-dependency-review;
  moot after removing the .opencode dependency manifest and lockfile.

## A-019 — .opencode manifest pins a loose caret while the lockfile drifted a minor ahead
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: dependencies
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - .opencode/package.json:3 ^1.14.39 vs bun.lock resolving 1.18.0
  - nothing enforces --frozen-lockfile
- why: Declared intent is ambiguous and resolution rests on discipline rather
  than the manifest.
- fix: Pin the exact version or raise the caret floor; enforce frozen lockfile
  (moot if removed).
- notes: folded into .trellis/tasks/07-15-opencode-plugin-dependency-review;
  moot after removing the .opencode dependency manifest and lockfile.

## A-020 — generated_pack_file overloads PackFile.source with MANIFEST_PATH for template-less files
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: design
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - installer/fileops.py:63-72 sets source=MANIFEST_PATH for generated targets
  - installer/provenance.py:56-62 + :139 must maintain
    PROVENANCE_EXCLUDED_KINDS to compensate
- why: The source field's contract is untrue for generated kinds; correctness
  relies on remembering an exclusion set.
- fix: Make source Optional[Path] (None for generated) or split a GeneratedFile
  type.
- notes: fixed in .trellis/tasks/07-16-audit-roadmap-cleanup — generated
  pack files now use source=None and provenance skips source-less generated
  results by shape instead of by a generated-kind exclusion list.

## A-021 — SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER_LABEL missing from all structured config references
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - Consumed at .agents/skills/sd-review-pr/SKILL.md:171
  - present once in guide prose (:192) but absent from the guide Configuration
    section (:716-1002) and the README table (:172-211) which lists its five
    siblings
- why: The reviewer display label looks unconfigurable to anyone scanning the
  references; it slips the env-var drift gate because that gate greps whole
  files.
- fix: Add a README table row and a guide Configuration bullet for the
  REVIEW_PR_REMOTE_* family.
- notes: fixed in 0.13.1 via .trellis/tasks/07-15-p3-polish-batch —
  REVIEW_PR_REMOTE_* family documented in guide config + README (status flip owned by the next audit run)

## A-022 — Core installer entry points and every installer/ module lack meaningful docstrings
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - installer/manifest.py:43 load_manifest, :101 validate_manifest,
    installer/fileops.py:154 selected_files have no docstrings
  - all six submodules share the identical boilerplate module docstring
- why: Responsibility boundaries between
  fileops/manifest/provenance/registry/removal are discoverable only by reading
  bodies.
- fix: One-line responsibility docstring per module; short docstrings on the
  primary public functions.
- notes: fixed in 0.13.1 via .trellis/tasks/07-15-p3-polish-batch —
  installer module + entry-point docstrings (status flip owned by the next audit run)

## A-023 — Post-payload dogfood-sync and KB-refresh steps are manual with no wrapping make target
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: improvements
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - CONTRIBUTING.md:59-71 instructs manual install.py --force + update- spec-
    kb.py runs
  - Makefile:7 target set has no sync/release-prep
  - only rejection-side gates exist (test_pack_drift.py:243, :309)
- why: Exactly the steps maintainers forget, causing late-failing gate round-
  trips (this audit's own branch hit both, twice).
- fix: Add a make sync target running the dogfood install and KB refresh.
- notes: fixed in 0.13.1 via .trellis/tasks/07-15-p3-polish-batch —
  make sync target wrapping dogfood install + KB refresh (status flip owned by the next audit run)

## A-024 — review-preflight recomputes the documentation file list and re-reads docs across checks
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - review-preflight.mjs:759-777 documentationGuardFiles() walks per call (:327
    and :352)
  - readText (:1200) unmemoized
  - docs re-read at :336, :361, :594
- why: The doc-tree walk runs twice and every doc file is read multiple times
  per preflight run.
- fix: Compute the file list once; memoize readText with a Map.
- notes: fixed in 0.13.1 via .trellis/tasks/07-15-p3-polish-batch —
  preflight guard-file list + readText memoized (status flip owned by the next audit run)

## A-025 — Backfilled changelog release dates disagree with tag dates and are internally out of order
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: release-hygiene
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - CHANGELOG.md:162 (0.7.4 - 2026-07-08) sits above :167 (0.7.3 - 2026-07-09)
  - git tag creatordates invert this
  - 0.7.1/0.7.2 likewise (from the 0.9.2 backfill)
- why: A reader reconstructing the release timeline gets contradictory dates
  and an impossible ordering.
- fix: Correct the 0.7.1-0.7.4 heading dates to the tag creation dates.
- notes: fixed in .trellis/tasks/07-16-audit-roadmap-cleanup — corrected
  0.7.1-0.7.3 to 2026-07-08 and 0.7.4 to 2026-07-09 to match tag dates.

## A-026 — Deprecated env var REVIEW_PREFLIGHT_PR_BODY names no removal version or window
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: release-hygiene
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - scripts/sd-ai-command-pack-review-scope.sh:186 warn
  - README.md:213
  - guide :948-949 and :968-969 label it deprecated with no sunset
- why: An open-ended deprecation leaves consumers unable to plan migration and
  the shim accumulates indefinitely.
- fix: State a removal target next to the deprecation, or declare it
  permanently supported.
- notes: fixed in .trellis/tasks/07-16-audit-roadmap-cleanup — docs and
  warnings state the fallback is honored through 0.15.x and scheduled for
  removal in 0.16.0.

## A-027 — Trellis lifecycle hooks execute config-sourced commands via shell=True (upstream-owned)
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: security
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .trellis/scripts/common/task_utils.py:260 — iterates repo-configured hook
    commands.
  - .trellis/scripts/common/task_utils.py:262 — invokes each command through
    subprocess.run.
  - .trellis/scripts/common/task_utils.py:264 — explicitly enables shell=True.
  - .trellis/scripts/common/config.py:285 — loads hook configuration from the
    repository.
  - .trellis/scripts/common/config.py:289 — accepts hook entries as a list.
- why: Repository configuration can execute shell strings when a developer runs
  Trellis task commands; this matches a trusted-repo hook model but remains an
  upstream contract and consent concern.
- fix: Upstream Trellis should document trusted full-shell semantics, add a
  first-use consent gate, or support argv-list hook execution.
- notes: upstream-owned; do not edit `.trellis/scripts/**` in this pack or open
  an upstream Trellis PR without explicit user approval. Handoff:
  "Trellis task-command lifecycle hooks run config-sourced hook commands with
  `subprocess.run(..., shell=True, ...)` in
  `.trellis/scripts/common/task_utils.py`. Please decide whether to document
  full-shell semantics as trusted repo config, add a first-use opt-in gate, or
  change hook config to argv-list execution. This was found from
  sd-ai-command-pack audit A-027 and intentionally left upstream-owned."
  Parked as `.trellis/tasks/07-16-upstream-trellis-hook-shell-semantics/`.
  Follow-up 2026-07-19 @ e4b10b3: still open; evidence remains present in
  Trellis 0.6.7 runtime and the parked task remains accurate.

## A-028 — review-learnings git error/edge branches are untested (script at 69%)
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: testing
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - scripts/sd-ai-command-pack-review-learnings.py:497-501 returncode!=0 raise
    + untracked-diff path ~503-520 in coverage Missing
  - tests cover clean git states only
- why: Exactly the branches that break in real consumer repos would regress
  silently.
- fix: Add tests forcing git failures (stubbed git on PATH) and one staging an
  untracked file.
- notes: fixed in 0.13.1 via .trellis/tasks/07-15-p3-polish-batch —
  review-learnings error-branch tests (coverage 51%->57%) (status flip owned by the next audit run)

## A-029 — Green local make check does not predict green CI: node and shellcheck lanes silently skip when tools are absent
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: tooling
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - Makefile:27-33 (node skip), :34-38 (shellcheck skip)
  - make setup (Makefile:9-12) installs neither
  - CI runs both unconditionally (tests.yml:101-107, :142-143)
- why: A clean-machine contributor gets green make check and red CI on ~6k
  lines of shell plus the .mjs preflight.
- fix: Make shellcheck+node hard setup prerequisites, or a STRICT=1 mode
  turning skips into errors.
- notes: fixed in 0.13.1 via .trellis/tasks/07-15-p3-polish-batch —
  STRICT=1 make mode for node/shellcheck parity (status flip owned by the next audit run)

## A-030 — Type-check gate covers only installer/; shipped Python scripts get no mypy
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: tooling
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - tests.yml:98-99 and Makefile:26 run mypy installer only
  - install.py and scripts/*.py (update-spec-kb ~47KB, review-learnings ~31KB,
    install-audit ~32KB, pr-body-scope ~25KB) are ruff-only
- why: The type gate leaves most of the shipped Python payload uncovered.
- fix: Extend mypy to install.py and scripts/, or document the exclusion.
- notes: fixed in 0.13.1 via .trellis/tasks/07-15-p3-polish-batch —
  mypy extended to install.py + scripts (trivial typing fixes) (status flip owned by the next audit run)

## A-031 — Default install re-reads and re-hashes every source and destination in preflight then apply
- status: fixed
- severity: P3 · effort: M · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - install.py:617-640 (dry-run pass :618, apply :633)
  - installer/fileops.py:228 + :249 read both sides in each pass across 384
    targets
- why: Doubled read I/O on every default install, growing with payload size.
- fix: Have preflight return per-file conflict decisions (and bytes) threaded
  into apply.
- notes: fixed in .trellis/tasks/07-16-audit-roadmap-cleanup — default
  non-force installs now pass preflight InstallResult source bytes/digests
  into apply.

## A-032 — Provenance hashing re-reads sources the apply pass just read
- status: fixed
- severity: P3 · effort: M · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - installer/provenance.py:150-153 sha256(file.source.read_bytes()) after
    fileops.py:228 read the same bytes
  - memoized per-source but still a third full read
- why: Redundant I/O over the distinct pack sources on every install.
- fix: Carry source bytes or their sha256 from install_file into InstallResult.
- notes: fixed in .trellis/tasks/07-16-audit-roadmap-cleanup — InstallResult
  carries source_digest/source_content/source_executable and provenance
  prefers the digest captured during install.

## A-033 — Coverage gate omits all shipped shell (~90KB incl. destructive housekeeping) and .github/scripts release automation
- status: fixed
- severity: P3 · effort: M · confidence: Plausible
- dimension: testing
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - .coveragerc:6-10 includes Python only
  - housekeeping.sh (33KB), full- check.sh (27KB), review-local.sh, create-
    release-tag.py, check-main-push- scope.sh have no coverage floor
- why: The most destructive shipped code (git branch/worktree cleanup) has no
  measurement of which branches its subprocess tests reach.
- fix: Add kcov/bashcov with a floor, or document the exemption and add
  targeted error-branch subprocess tests.
- notes: fixed in .trellis/tasks/07-16-audit-roadmap-cleanup — CONTRIBUTING
  and README document shell/GitHub automation as coverage.py-exempt with
  compensating subprocess tests, syntax checks, ShellCheck, workflow
  assertions, and live CI.

## A-034 — Command adapters use two divergent authoring models; transform rules live in a test rather than a generator
- status: fixed
- severity: P3 · effort: L · confidence: Plausible
- dimension: architecture
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-16 @ 7d0172e
- evidence:
  - 11 platforms fan from templates/.commands/*
  - claude/gemini/github hand-authored with materially different bodies
  - no generator
  - parity pinned by tests/test_generated_parity.py:36
    CLAUDE_COMMAND_ALIAS_REWRITES + :55 BESPOKE_BODY_PARITY_EXEMPTIONS
- why: One command change requires coordinated hand-edits across four trees
  plus the manifest; a verifier without a producer makes parity only partially
  enforceable.
- fix: Promote the rewrite rules into an adapter-generation step; the test then
  verifies generator output.
- notes: tracked → .trellis/tasks/07-15-surface-generation (implemented in
  0.13.0: make generate + drift test; transform rules moved from parity tests
  into the generator)

## A-035 — Post-review task lifecycle changes leave the generated knowledge base stale
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: tooling
- first-seen: 2026-07-19 @ e4b10b3
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - templates/.agents/skills/sd-ship/SKILL.md:93 — Stage 1 refreshes specs and
    generated knowledge before PR review.
  - templates/.agents/skills/sd-ship/SKILL.md:114 — Stage 4 archives the task
    after that final refresh.
  - scripts/sd-ai-command-pack-update-spec-kb.py:307 — active and archived
    Trellis task Markdown is part of the generated knowledge source set.
  - templates/scripts/sd-ai-command-pack-full-check.sh:517 — stale generated
    knowledge fails the canonical full check when `.obsidian-kb` exists.
- why: The normal ship lifecycle moves task documents after the last knowledge
  refresh; post-merge follow-up tasks add another path, leaving an expected
  local knowledge package stale and `make check` red on clean main.
- fix: Give post-review task archive/follow-up mutations a final conditional KB
  refresh owner, then add an end-to-end regression that finishes with
  `update-spec-kb.py --check` green when `.obsidian-kb` already exists.
- notes: `make check` on 2026-07-19 passed 650 tests, coverage, Ruff, mypy,
  Bandit, Zizmor, and source drift, then failed only on missing/stale task
  copies created by the PR #169 archive and the 0.21.6 fleet follow-up task.
  Tracked by `.trellis/tasks/07-19-post-finish-kb-refresh/` after user consent.

## A-036 — Removed review-body fallback remains documented in the shipped full-check skill
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-19 @ e4b10b3
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - templates/.agents/skills/sd-full-check/SKILL.md:110 — still documents
    REVIEW_PREFLIGHT_PR_BODY as a supported deprecated fallback.
  - CHANGELOG.md:220 — records that the fallback was removed in 0.16.0.
  - tests/test_review_scope.py:248 — retirement coverage checks only the two
    installed guide copies, not shipped skill documentation.
- why: Consumers following the shipped skill can set a variable that no longer
  affects full-check PR-body resolution, producing avoidable scope failures.
- fix: Remove the stale skill entry and extend the retirement regression across
  every shipped documentation and skill surface.
- notes: Tracked by
  `.trellis/tasks/07-19-remove-retired-review-body-skill-doc/` after user
  consent.

## A-037 — Completed Trellis tasks remain stranded in the active task root
- status: fixed
- severity: P3 · effort: S · confidence: Plausible
- dimension: bloat
- first-seen: 2026-07-19 @ e4b10b3
- last-seen: 2026-07-19 @ e4b10b3
- evidence:
  - .trellis/tasks/07-19-fleet-refresh-0-21-0/task.json:6 — completed task is
    still outside the archive.
  - .trellis/tasks/07-19-status-read-only-bytecode/task.json:6 — completed task
    is still outside the archive.
  - .trellis/tasks/07-19-status-repository-path-validation/task.json:6 —
    completed task is still outside the archive.
  - .trellis/tasks/07-19-work-loop-best-effort-oserror-handling/task.json:6 —
    completed task is still outside the archive.
  - scripts/sd-ai-command-pack-status.py:411 — status inventory emits only
    in-progress and planning task lists, so stranded completed tasks are hidden.
- why: Trellis reports these directories as active inventory while SD status
  reports a healthy task state, allowing completed artifacts to accumulate and
  making backlog counts disagree across tools.
- fix: Archive the four completed tasks and surface active-root completed tasks
  as a bounded status/preflight anomaly so the state cannot silently recur.
- notes: Resolved by `.trellis/tasks/07-19-completed-task-root-cleanup/` in the
  0.21.7 working tree. The four records moved to the 2026-07 archive;
  `sd-status` now reports the invariant and shared review preflight enforces it.
  All seven fleet candidates and `make check` passed.

## A-038 — Bookkeeping CI scope decided by classifier code read from unverified BEFORE_SHA
- status: open
- severity: P0 · effort: M · confidence: Verified
- dimension: tooling
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .github/workflows/tests.yml:148 — `git show "$BEFORE_SHA:.github/scripts/bookkeeping_ci_scope.py"` materializes the classifier.
  - .github/workflows/tests.yml:145 — guards only mode `100644`, type `blob`, exact path; no blob identity check.
  - .github/workflows/tests.yml:151 — `py_compile` is the only other check before execution at :189.
  - .github/workflows/tests.yml:47 — on `synchronize`, `BEFORE_SHA` is the PR's previous head, i.e. the PR branch itself.
  - .github/scripts/bookkeeping_ci_scope.py:26 — every fail-closed reason, incl. `ALLOWED_PATH_PREFIXES`, lives inside the untrusted file.
  - .github/workflows/tests.yml:260 — `mode == 'full'` gates unittest; :318 lint, :358 security, :397 release-payload-gate.
  - .github/scripts/check-ci-result.sh:52 — accepts `(pull_request, success, bookkeeping, skipped×5)` as green.
  - .github/workflows/tests.yml:105 — jq accepts any positive integer as `evidenceRunId`; no consumer resolves it.
  - .github/workflows/tests.yml:9 — `concurrency` cancels the in-progress run, so the tamper commit is never linted or tested.
  - .github/workflows/tests.yml:461 — "CI Result" is the only required context; README.md:889 confirms.
- why: A two-push PR (tamper commit, then payload) gets the payload judged by the
  tampered classifier; every heavy lane skips and the sole required check goes green.
- fix: Compare `rev-parse "$BEFORE_SHA:<classifier>"` against the base blob and select
  full on mismatch; resolve the claimed evidence run IDs via API in the trusted step.
- notes: Prerequisite relationship: A-100 subsumes this if the fast lane is retired. tracked -> .trellis/tasks/07-28-pin-bookkeeping-ci-classifier-trust (created 2026-07-28 with explicit user consent via audit.followups).

## A-039 — .github/scripts static analysis uses a hand-maintained per-file allowlist drifted three ways
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: tooling
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - Makefile:54 — lints surface-drift, bookkeeping, prepare-release only.
  - .github/workflows/tests.yml:339 — CI lint scope omits prepare-release.py.
  - .github/scripts/generate-command-surfaces.py:1 — 994 lines, linted nowhere.
  - .github/scripts/create-release-tag.py:1 — runs with `contents:write` (tests.yml:511), linted nowhere.
  - tests/test_generated_parity.py:990 — asserts the CI lint strings verbatim, locking the drift in.
- why: Two of six `.github/scripts` modules — the surface generator and the release
  tagger — get no lint or type checking anywhere.
- fix: Pass directory arguments to ruff/mypy in both lanes; make the parity test compare
  Makefile and workflow scopes to each other rather than to literals.
- notes: untracked in the active Trellis backlog as of 2026-07-28. Cross-ref A-030 (fixed): related mypy-scope work; this is allowlist drift in a different lane.

## A-040 — `make audit` degrades to warnings with no STRICT escape, so `make check` is green with zero security scanning
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: tooling
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - Makefile:75 — bandit and zizmor fall through to a warning printf, no STRICT branch.
  - Makefile:60 — lint has the STRICT exit-1 arm the audit lane lacks.
  - Makefile:94 — `check: test lint audit full-check` inherits the soft failure.
  - CONTRIBUTING.md:33 — claims `STRICT=1` gives parity with CI.
  - .github/workflows/tests.yml:381 — the CI security job hard-fails.
- why: A stale `.venv` yields a fully green `STRICT=1 make check` while CI's security job
  is the only real backstop, breaking the documented local/CI parity claim.
- fix: Add the same STRICT exit-1 arm to both audit branches and pass STRICT through from
  `check`.
- notes: untracked in the active Trellis backlog as of 2026-07-28. Cross-ref A-029 (fixed): the lint and typecheck lanes gained STRICT there; the audit lane did not.

## A-041 — Chore-scope path allowlist triplicated and already drifted on .trellis/audit/**
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: tooling
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .githooks/pre-push:54 — three prefixes including `.trellis/audit/*`.
  - .github/scripts/check-main-push-scope.sh:71 — the same three prefixes.
  - .github/scripts/bookkeeping_ci_scope.py:26 — only two; `.trellis/audit` absent.
  - .trellis/audit/ledger.md:1 — the path is live and written by this very command.
- why: An audit-ledger chore push satisfies both push guards but classifies as
  `changed_path_not_bookkeeping`, paying the full matrix and defeating the fast lane.
- fix: Derive one allowlist from a single source (a `--print-allowed-prefixes` mode) and
  decide `.trellis/audit/**` validation mode deliberately.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-042 — zizmor --offline in CI disables the network-backed workflow audits CI is best placed to run
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: tooling
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .github/workflows/tests.yml:385 — `zizmor --offline`.
  - .github/workflows/tests.yml:356 — no `GH_TOKEN` in the security job env.
  - Makefile:84 — the same flag locally, where offline is appropriate.
- why: `--offline` skips known-vulnerable and stale action-ref audits, so SHA-pinned
  actions are never checked against advisories.
- fix: Keep `--offline` in the Makefile, drop it in CI, and add `GH_TOKEN`.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-043 — Roughly a quarter of full-check.sh can never execute in this repo's own canonical gate
- status: open
- severity: P3 · effort: M · confidence: Plausible
- dimension: tooling
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - Makefile:92 — hard-disables the AI review lanes with `PRISM=0 GITO=0`.
  - scripts/sd-ai-command-pack-full-check.sh:296 — ~125 lines of prism lane, unreachable locally.
  - scripts/sd-ai-command-pack-full-check.sh:935 — CI-classification block (resolver at :923) targets `scripts/classify-ci-changes.sh`, which has zero commits in `git log --all`.
  - scripts/sd-ai-command-pack-full-check.sh:978 — legacy `check-review-preflight.mjs` fallback is dead.
  - scripts/sd-ai-command-pack-full-check.sh:1038 — package-script block never runs; no root package.json exists.
- why: `make full-check` exercises well under 75% of the 1073-line script it ships, so
  regressions in those lanes are invisible to the owners.
- fix: Delete the never-instantiated legacy fallbacks and fold the optional lanes into one
  explicitly optional section.
- notes: owner filed 2026-08-10: `08-09-retire-review-pr-surface`, which deletes `scripts/sd-ai-command-pack-full-check.sh` and recomposes `make check` around `sd-check`. 07-24-remove-retired-review-surfaces was narrowed to the `sd-full-check` and `sd-review-local` command surfaces and left the script in place, so 0.65.0 does not change this finding. If 08-09 keeps any lane of the script alive, that lane inherits this cleanup.

## A-044 — Pack-repo fleet-refresh command adapters are frozen, so the only surface that can run fleet-refresh lacks the checkout-trust gate
- status: open
- severity: P1 · effort: S · confidence: Verified
- dimension: architecture
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - installer/registry.py:1176 — `SOURCE_ONLY_COMMAND_NAMES = frozenset({"sd-fleet-refresh"})`.
  - templates/.claude/commands/sd/fleet-refresh.md:7 — checkout-trust policy present in the shipped twin.
  - .claude/commands/sd/fleet-refresh.md:5 — dev-tree twin has no trust block; it is the only dev command that differs from its template.
  - .agents/skills/sd-fleet-refresh/SKILL.md:1 — zero `checkout-trust` hits; the gate lives only in the adapter.
  - installer/removal.py:272 — source-only targets are skipped in source checkouts, so install.py neither refreshes nor prunes them.
  - .github/scripts/generate-command-surfaces.py:568 — the generator writes adapters only under `templates/`.
  - tests/test_pack_drift.py:144 — the twin-parity gate iterates `load_manifest()`, which excludes source-only targets.
- why: Every real fleet campaign runs from a body frozen at the 0.20.0 era, missing the
  fork/untrusted-checkout gate and describing the retired serial pipeline.
- fix: Have the generator emit source-only adapters into the dev tree too, and add the four
  frozen paths to the surface-drift gate.
- notes: tracked -> .trellis/tasks/07-28-regenerate-fleet-refresh-adapters (created 2026-07-28 with explicit user consent via audit.followups).

## A-045 — Two complete review lifecycles ship at once and the composite orchestrator wires the predecessor
- status: open
- severity: P2 · effort: L · confidence: Plausible
- dimension: architecture
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .agents/skills/sd-review/SKILL.md:14 — successor declares itself self-contained.
  - .agents/skills/sd-ship/SKILL.md:129 — Stage 2 calls sd-review-pr, never the successor.
  - scripts/sd-ai-command-pack-review-local.sh:1 — 771 lines of bash prism/gito orchestration (manifest.json:264).
  - scripts/sd-ai-command-pack-review-local.py:1375 — 2232 lines of Python doing the same orchestration.
  - .agents/skills/sd-help/references/command-catalog.md:40 — sd-review-pr row reads "included in installed pack", identical to sd-review's.
  - README.md:274 — prose calls the surfaces transitional; no removal version exists anywhere.
  - CONTRIBUTING.md:142 — mandates removal-release documentation that these surfaces do not have.
  - docs/SD_AI_COMMAND_PACK.md:194 — the "recommended review loop" interleaves successor and transitional steps across 18 steps with no decision point.
- why: Provider orchestration has two implementations in two languages behind two commands,
  and the main delivery path runs the predecessor, so successor guarantees never apply.
- fix: Pick one lifecycle, pre-register `RetiredCommandSurface` rows with a removal version,
  and repoint sd-ship Stage 2 at `sd-review scope=pr`.
- notes: tracked -> .trellis/tasks/08-09-retire-review-pr-surface (re-owned 2026-08-09). 0.65.0 removed the `sd-full-check` and `sd-review-local` surfaces; `sd-review-pr` is the remaining predecessor lifecycle and 08-09 owns its retirement. Prior ownership: .trellis/tasks/07-28-retire-transitional-review-surfaces (schedule + interim), 07-24-remove-retired-review-surfaces R8 (binding deletion to the pre-registered removed_version), and 07-24-simplify-review-shipping-composition R7 (sole owner of the sd-ship Stage 2 repoint).

## A-046 — User-local state-root and private-directory helpers are implemented three to four times with divergent semantics
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: architecture
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-work-loop.py:295 — `resolve_state_root()` honors env override, XDG, LOCALAPPDATA.
  - scripts/sd-ai-command-pack-recovery-artifacts.py:123 — near byte-identical copy; the file's own comment admits it "mirrors the work-loop patterns" (:119).
  - scripts/sd-ai-command-pack-fleet-timing.py:371 — same ladder minus the documented `SD_AI_COMMAND_PACK_STATE_HOME` branch.
  - scripts/sd-ai-command-pack-fleet-controller.py:212 — honors only `XDG_STATE_HOME`.
  - scripts/sd-ai-command-pack-work-loop.py:334 — `ensure_private_directory` raises `StatePersistenceError` with evidence.
  - scripts/sd-ai-command-pack-recovery-artifacts.py:155 — the twin lets raw `OSError` escape.
  - scripts/sd_ai_command_pack_lib.py:149 — the shared lib already owns `_ensure_private_directory` but not the state root.
- why: With the documented override set, work-loop ledgers relocate while fleet state stays
  behind; recovery then classifies a tree the fleet components never write.
- fix: Move `STATE_HOME_ENV`, `resolve_state_root`, and `ensure_private_directory` into the
  shared lib with one blocked-write contract; callers keep only their subdirectory name.
- notes: tracked -> .trellis/tasks/07-28-consolidate-shared-script-helpers (created 2026-07-28 with explicit user consent via audit.followups).

## A-047 — Cross-script dependencies bypass the module system via path + exec_module because the shipped naming convention forbids imports
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: architecture
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-status.py:804 — `spec_from_file_location` loads work-loop.py, then re-validates the contract defensively.
  - scripts/sd-ai-command-pack-status.py:1202 — same pattern for recovery-artifacts.py.
  - scripts/sd-ai-command-pack-fleet-controller.py:100 — executes fleet-wave-plan.py at module import time.
  - scripts/sd-ai-command-pack-surface-check.py:212 — a third loader variant.
  - scripts/sd-ai-command-pack-fleet-preflight.py:14 — the same 3-line sys.path shim repeated across nine scripts.
  - pyproject.toml:1 — no `[project]` table, so no package namespace exists.
- why: The real dependency graph is invisible to mypy and cycle detection, each edge costs
  ~20 lines of loader plus revalidation, and every new script pays the import tax.
- fix: Promote reusable entry points into underscore-named importable modules under
  `scripts/`; leave the hyphenated files as thin argv shims.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-048 — Pack-maintainer-only source gates are shipped to every consumer and neutralized at runtime by an identity check
- status: open
- severity: P3 · effort: M · confidence: Plausible
- dimension: architecture
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - manifest.json:138 — ships `scripts/sd-ai-command-pack-surface-check.py` (756 lines) to every consumer.
  - scripts/sd-ai-command-pack-surface-check.py:228 — requires `installer.registry`, which is not shipped.
  - scripts/sd-ai-command-pack-surface-check.py:204 — requires `templates/**`, which is not shipped.
  - scripts/sd-ai-command-pack-full-check.sh:569 — `run_pack_source_drift_gates()` early-returns unless the source identity is this pack.
- why: The payload boundary does not separate consumer runtime from maintainer tooling, so
  consumers carry and re-verify code that cannot execute there.
- fix: Move source-repo-only gates into `.github/scripts/` and call them from the checkout;
  the consumer full-check loses the identity-gated branch.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-049 — sd-check's read-only git guard has no test
- status: open
- severity: P1 · effort: S · confidence: Verified
- dimension: testing
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-check.py:513 — the `READ_ONLY_GIT_SUBCOMMANDS` branch; :514-519 are in the coverage missing list.
  - tests/test_check.py:94 — `command_entry` is the only argv construction site and never emits a `git` argv.
  - tests/test_check.py:315 — the invalid-config table has no `git push`/`git commit` entry.
  - .sd-ai-command-pack/check.json:1 — the repo's own config has no git entry either.
  - .github/scripts/check-shipped-script-coverage.sh:32 — the floor for check.py is 70% and the file sits at 73%, so deleting the guard lands green.
- why: "Deterministic read-only" is sd-check's headline guarantee and the sole enforcing
  branch is never executed by any test.
- fix: Add mutating-git entries to the invalid-values table; also cover the uncovered
  `perl -e` branch at check.py:501.
- notes: tracked -> .trellis/tasks/07-28-test-sd-check-read-only-git-guard (created 2026-07-28 with explicit user consent via audit.followups).

## A-050 — Half the shipped runtime surface has no coverage measurement at all
- status: open
- severity: P1 · effort: L · confidence: Verified
- dimension: testing
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .coveragerc:6 — the include list is nine patterns, all Python; no `.sh`, `.mjs`, `.github/`, or `.githooks`.
  - .github/scripts/check-shipped-script-coverage.sh:33 — the per-file floor table's 25 entries are all `scripts/*.py`.
  - scripts/sd-ai-command-pack-review-preflight.mjs:1 — 4,547 lines; the only check is `node --check` (tests.yml:350).
  - .github/scripts/bookkeeping_ci_scope.py:1 — 477 lines deciding whether CI runs, unmeasured.
  - scripts/sd-ai-command-pack-full-check.sh:610 — a ~262-line Python program run via `python3 -`, structurally unmeasurable.
  - tests/test_full_check.py:1576 — asserts `assertIn("run_pack_source_drift_gates", script)`; passes if the function is merely mentioned.
  - tests/coverage_sitecustomize/sitecustomize.py:22 — subprocess coverage plumbing exists, so the omission is configuration, not capability.
- why: ~12,600 unmeasured lines versus 16,064 measured statements, and without a coverage
  signal a source-text assertion is indistinguishable from a behavioral test.
- fix: Add `.github/scripts/*.py` to `.coveragerc` (one line), then adopt c8 for the Node
  preflight and a shell coverage tool, publishing before gating.
- notes: Cross-ref A-033 (fixed): re-opens the coverage-exemption decision that entry closed by documenting, and adds surfaces the exemption never covered. tracked -> .trellis/tasks/07-28-measure-unmeasured-runtime-surface (created 2026-07-28 with explicit user consent via audit.followups).

## A-051 — sd-review's routed-receipt backend validation is entirely unexercised
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: testing
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-review.py:1055 — `_decode_receipt_check`; all eight `raise ReviewError` paths are in the coverage missing list.
  - scripts/sd-ai-command-pack-review.py:1116 — the validation body with no test reaching it.
  - .github/scripts/check-shipped-script-coverage.sh:51 — review.py sits at the table's joint-lowest floor (70, tied with check.py:35 and review-local.py:50) at 73% actual.
- why: This is exactly the receipt and tracking machinery under complexity scrutiny; its
  failure modes are never tested, so load-bearing and dead defensive code look identical.
- fix: Add a table-driven malformed-receipt test through `_decode_receipt_check`, and delete
  the branches unreachable from real payloads rather than testing them.
- notes: tracked -> .trellis/tasks/07-22-integrate-routed-review-backends R38 (prd updated 2026-07-28): table-driven malformed-receipt coverage through _decode_receipt_check, with unreachable branches deleted rather than tested.

## A-052 — Per-file coverage floors are static, not ratcheted, leaving up to 17 points of silent regression headroom
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: testing
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .github/scripts/check-shipped-script-coverage.sh:20 — aggregate `--fail-under=76` against 85% actual.
  - .github/scripts/check-shipped-script-coverage.sh:34 — audit-inventory floor 85 against 99% actual.
  - .github/scripts/check-shipped-script-coverage.sh:34 — audit-route floor 77 against 94% actual.
- why: Floors were set once and never followed the suite up, so a test-deleting refactor
  reports green across roughly 1,275 statements of slack.
- fix: Regenerate the floor table from measured coverage minus one or two points, and fail
  when actual exceeds floor by more than ~3 to force the ratchet.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-053 — Test suite pins documentation and build-config prose by literal substring
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: testing
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - tests/test_generated_parity.py:1044 — hardcodes eight coverage-floor literals.
  - tests/test_pack_drift.py:478 — already derives the same floors structurally.
  - tests/test_generated_parity.py:1028 — pins the node-warning prose string.
- why: A floor ratchet or a README rewording breaks tests that detect no behavioral defect,
  training contributors to edit assertions instead of code.
- fix: Delete the duplicated floor literals and replace prose `assertIn` checks with
  structural assertions that parse the workflow as YAML.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-054 — Test subprocesses inherit the developer's ambient environment
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: testing
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - tests/install_test_support.py:1170 — `{**os.environ, ...}` builds the child environment.
  - .github/scripts/run-tests.sh:36 — exports several `SD_AI_COMMAND_PACK_*` variables before the suite.
  - Makefile:92 — exports `PRISM=0 GITO=0` for full-check in the same shell.
- why: Maintainers dogfood in the same checkout, so an exported behavior variable silently
  changes what the suite exercises and the run stays green with a gate disabled.
- fix: Add a `pack_subprocess_env()` allowlist helper and route the ~104 call sites through
  it.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-055 — Signal-cancellation test races a 5s startup deadline against a 5s provider timeout
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: testing
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - tests/test_review_stage.py:1084 — a 5s config timeout polled against a 5s monotonic deadline.
  - tests/test_check.py:367 — a `sleep(5)` helper used under a 1s timeout.
  - .github/scripts/run-tests.sh:1 — shards across cores-1, so a 2-core runner leaves one worker.
- why: Startup contention on a small runner pushes past the log deadline and produces a
  spurious cancellation-assertion failure.
- fix: Raise the startup deadline to ~30s and drive readiness off a stub-written file rather
  than a fixed budget.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-056 — Documented .sd-ai-command-pack/review.json makes the shipped install audit fail in any consumer that adopts it
- status: open
- severity: P1 · effort: S · confidence: Verified
- dimension: consumer-impact
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - templates/scripts/sd-ai-command-pack-review.py:30 — `CONFIG_PATH = .sd-ai-command-pack/review.json`.
  - templates/docs/SD_AI_COMMAND_PACK.md:865 — documents the file as supported configuration.
  - scripts/sd-ai-command-pack-install-audit.py:558 — collection walks the filesystem, so an untracked file is still collected.
  - scripts/sd-ai-command-pack-install-audit.py:78 — `LOCAL_ALLOWED_PACK_FILES` holds exactly check.json, pr-body-scope.json, review-preflight.json.
  - scripts/sd-ai-command-pack-install-audit.py:668 — an unlisted, non-ignored pack file becomes a failure, exiting 1 at :1021.
  - installer/registry.py:1759 — no managed gitignore pattern covers `.sd-ai-command-pack/review.json`.
  - templates/scripts/sd-ai-command-pack-check.py:917 — registers `pack.install-audit` as an sd-check gate, so three gates break.
  - tests/test_bookkeeping_validator.py:1386 — the pack's own fixture already classifies review.json as tracked configuration.
- why: A consumer following the shipped docs turns its own sd-full-check, sd-check, and
  sd-review red with a bare error and no remediation hint.
- fix: Add review.json to `LOCAL_ALLOWED_PACK_FILES`, and add a test asserting every
  `CONFIG_PATH` read by a shipped script is allowlisted.
- notes: tracked -> .trellis/tasks/07-28-allowlist-review-json-install-audit (created 2026-07-28 with explicit user consent via audit.followups) owns the review.json fix; .trellis/tasks/07-22-integrate-routed-review-backends R36 (prd updated 2026-07-28) owns the recurrence invariant, decided 2026-07-28: one registry of every shipped .sd-ai-command-pack/ path constant with a declared tracked/ignored disposition, plus its test. Not a CONFIG_PATH-name test — pr-body-scope.py:69 uses DEFAULT_CONFIG_PATH and :70 INSTALLED_TARGETS_FILE, so a name-based assertion would leave the hole open.

## A-057 — Candidate-validation gate binds the whole payload digest, so doc-only edits force a full eight-consumer revalidation
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: consumer-impact
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd_ai_command_pack_fleet_lib.py:663 — `payload_digest` hashes all 754 sources including `kind:"doc"`.
  - scripts/sd_ai_command_pack_fleet_lib.py:731 — `validate_candidate_ledger` hard-rejects any mismatch.
  - docs/fleet/candidate-validation.json:1 — restamped twice in 90 minutes (38502b11, fe69f4dc) for a doc reword.
- why: The strongest release gate is triggered by content that cannot affect any consumer
  check; a typo fix costs a cross-repo revalidation before fleet refresh.
- fix: Split a behavior digest (scripts, config, managed blocks, topology) from an
  informational content digest and gate on behavior only.
- notes: tracked -> .trellis/tasks/07-28-split-payload-behavior-digest (created 2026-07-28 with explicit user consent via audit.followups); .trellis/tasks/07-28-roll-out-stabilized-pack-release-to-fleet updated 2026-07-28 to cross-reference it and stop assuming whole-payload digest semantics.

## A-058 — Nothing detects a manifest target dropped without a retirement entry, and an orphan hard-fails consumer audits
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: consumer-impact
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - installer/removal.py:69 — `RETIRED_TARGETS` is a fixed splat of three surfaces.
  - installer/registry.py:1187 — `command_installed_targets` cannot express `references/**`.
  - manifest.json:1 — ships 154 `references/` sub-files across 11 platforms.
  - scripts/sd-ai-command-pack-surface-check.py:340 — graphs the current tree only, with no prior-release diff.
  - scripts/sd-ai-command-pack-install-audit.py:668 — an orphaned file becomes a hard consumer failure.
- why: The simplification this audit recommends is exactly the trigger: dropping one
  reference file leaves 11 stale files per consumer and turns eight repo audits red.
- fix: Add a release-time lint diffing the previous tag's manifest targets against the
  current set, failing unless each dropped path is covered by a retirement row.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-059 — Shipped sd-review-pr skill embeds source-only fleet instructions naming a script consumers never receive
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: consumer-impact
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - templates/.agents/skills/sd-review-pr/SKILL.md:196 — an integration-only recheck block invoking fleet-review-classify.py.
  - scripts/sd-ai-command-pack-install-audit.py:115 — that script is explicitly source-only.
  - manifest.json:1 — the block ships in 11 platform copies.
- why: Roughly 22 lines of unreachable procedure per consumer skill send an agent chasing a
  script that does not exist there.
- fix: Move the fleet recheck into the source-only sd-fleet-refresh skill and leave a
  one-line pointer.
- notes: tracked -> .trellis/tasks/08-09-retire-review-pr-surface (re-owned 2026-08-09). The finding is about the shipped `sd-review-pr` skill, which 07-24 no longer touches after its narrowing; relocating the fleet recheck into the source-only sd-fleet-refresh skill before deletion travels with the sd-review-pr retirement.

## A-060 — SOURCE_ONLY_ALLOWED_PACK_FILES lists a file that is actually shipped
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: consumer-impact
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-install-audit.py:117 — lists `scripts/sd_ai_command_pack_fleet_lib.py` as source-only.
  - manifest.json:1 — ships that file unconditionally because shipped status.py and install-audit.py import it.
- why: Inert today, but it asserts the opposite of the manifest, so a future source-only trim
  could remove a file two shipped scripts import.
- fix: Delete the entry and add a test asserting the source-only set and the manifest target
  set are disjoint.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-061 — The autonomous work-loop's stage handoff is unparsed free text while every peer boundary uses a validated JSON receipt
- status: open
- severity: P1 · effort: M · confidence: Verified
- dimension: improvements
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .agents/skills/sd-ship/SKILL.md:202 — the `SD_SHIP_MERGE_RESULT` block carrying merge state, final head, review rounds, anomalies.
  - tests/test_sdlc_commands.py:724 — the only code reference is a presence assertion.
  - .agents/skills/sd-work-backlog/SKILL.md:274 — the consuming instruction is prose with no command block and no `--json`.
  - scripts/sd-ai-command-pack-work-loop.py:2105 — `record_result` validates only enum membership and non-negative counts.
  - scripts/sd-ai-command-pack-work-loop.py:2131 — increments `mergedPrs` purely on the agent-typed outcome.
  - scripts/sd-ai-command-pack-work-loop.py:2148 — forces `phase = "complete"`, bypassing `transition_state` at :1618.
  - scripts/sd-ai-command-pack-work-loop.py:65 — `CURRENT_FIELD_ORDER` has no destination for merge-state, finish-work, housekeeping, or anomalies.
  - tests/test_work_loop.py:3257 — the repo's own test passes a different PR URL than the validated one and it is accepted.
  - .agents/skills/sd-housekeeping/SKILL.md:28 — the peer boundary uses `--finish-work-receipt --json` with independent recompute.
- why: The one unattended-loop boundary with no parser carries outcome, counters, and four
  destination-less fields into the ledger through an LLM transcription step.
- fix: Emit the ship result as a schema-v1 JSON receipt and add `result --from-receipt` that
  parses and validates it; keep the human block display-only.
- notes: tracked -> .trellis/tasks/07-28-add-ship-result-receipt (created 2026-07-28 with explicit user consent via audit.followups).

## A-062 — No lint lane covers agent-executed shell embedded in SKILL.md, and it has already diverged from the pack's own portability rule
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: improvements
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .agents/skills/sd-finish-work/SKILL.md:120 — ships a bare `$(mktemp)`.
  - .agents/skills/sd-create-pr/SKILL.md:282 — uses the correct portable idiom, proving the rule.
  - Makefile:67 — ShellCheck runs only on tracked `.sh` files.
  - scripts/sd-ai-command-pack-review-learnings.py:736 — the pack's own mktemp rule is gated on `_is_shell_like`, which never matches `.md`.
- why: The 172 bash fences under `.agents/skills/` are shipped runtime shell executed
  verbatim by agents in consumer repos, with none of the linting.
- fix: Extract fenced bash from the template skills into temp files for ShellCheck and the
  pack's own shell rules, and wire it into `make lint` and CI.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-063 — The pack's own static rules have no deterministic lane and no baseline sweep, so pre-existing violations never surface
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: improvements
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-review-learnings.py:2494 — accepts only diff inputs.
  - scripts/sd-ai-command-pack-review-learnings.py:780 — iterates added lines only.
  - .github/scripts/run-tests.sh:101 — a bare `mktemp -d` violating the pack's own portability rule, undetected.
- why: A rule that fires only on agent-diffed lines is advisory, and the repo silently
  violates the portability contract it ships.
- fix: Add a `--baseline` full-tree mode scanning tracked shell and workflow files, run it
  from `make lint` and CI, and ratchet from the current set.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-064 — Nine skills hand-maintain near-duplicate "Standing GitHub authority" blocks that have already drifted
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: improvements
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .agents/skills/sd-create-pr/SKILL.md:16 — the canonical block.
  - .agents/skills/sd-fix-ci/SKILL.md:18 — the same block omitting "scope or risk expansion".
  - .agents/skills/sd-housekeeping/SKILL.md:38 — a third variant with a different ending.
  - tests/test_surface_generation.py:527 — the only guard is a presence check.
  - .github/scripts/generate-command-surfaces.py:365 — the shared-reference generator already exists and serves 12 skills.
- why: The invariant half of a safety contract is copy-pasted nine times with no consistency
  check, so future tightening lands unevenly.
- fix: Generate a shared `standing-authority.md` reference, keep the per-skill grant inline,
  and assert the link in the surface test.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-065 — Spec docs tell agents to run raw unittest, bypassing the test runner's flake guards, and no filtered entry point exists
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: improvements
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .trellis/spec/backend/index.md:47 — instructs `python3 -m unittest discover -s tests`.
  - .trellis/spec/frontend/quality-guidelines.md:66 — the same instruction.
  - .github/scripts/run-tests.sh:61 — sets the coverage and `GIT_CONFIG_*` maintenance overrides those invocations skip.
  - Makefile:41 — `make test` offers no module filter, so agents route around it.
- why: These spec files are injected into implement and check agents, sending them onto a
  known-flaky unguarded invocation whenever they want less than the full suite.
- fix: Add a module/pattern argument to run-tests.sh and `make test MODULE=...`, then
  repoint the four spec snippets.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-066 — Parked-backlog state is encoded in human task titles though a typed field exists and is honored
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: improvements
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .trellis/tasks/07-09-actionlint-workflow-linting/task.json:1 — title prefixed `PARKED:`, reason only in free-text notes.
  - scripts/sd-ai-command-pack-work-loop.py:800 — supports `blocked`, `blockedReason`, and `blockedOn`.
- why: Machine selector state rides in a display string across 18 of 43 active tasks, so a
  title edit silently un-parks an item and the blocking reason stays unstructured.
- fix: Write the typed fields when parking, render `PARKED:` as a prefix only, and have the
  work loop flag title-only parks.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-067 — sd-review-pr grants standing act-on-comment authority with no instruction-versus-data boundary
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: security
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .agents/skills/sd-review-pr/SKILL.md:119 — bot comments are "actionable by default" with standing permission to reply and resolve.
  - .agents/skills/sd-review-pr/SKILL.md:3 — invocation is pre-approval for review-fix commits and PR-branch pushes.
  - .agents/skills/sd-review-pr/SKILL.md:425 — comment bodies are fetched wholesale via `gh api ... --paginate`.
  - .agents/skills/sd-fix-ci/SKILL.md:72 — the same gap for CI logs.
  - .agents/skills/sd-help/SKILL.md:82 — the correct "data, not instructions" language already exists elsewhere in the pack.
- why: Any account can post PR comments and any fork PR can print arbitrary text into CI
  logs, and the skill pre-authorizes the resulting commits and pushes.
- fix: Add a trust-boundary bullet to both skills declaring comment and log bodies to be
  data, and surface out-of-diff requests to the user.
- notes: owned by `.trellis/tasks/07-28-skill-untrusted-content-boundary` (created 2026-07-28,
  planning). Scope widened to three skills, not two: computing standing-authority ∩
  external-text-ingestion over `.agents/skills/*/SKILL.md` gives `sd-review-pr`, `sd-fix-ci`,
  and `sd-create-pr`. The existing mitigation at `sd-review-pr/SKILL.md:119-120` ("verify
  against the current diff, project specs, and tests") is a correctness test, not a provenance
  test, so it does not close this. The wording to reuse already ships at
  `sd-help/SKILL.md:82`.

## A-068 — Repo-supplied review.json executes arbitrary argv and the anti-shell guard is name-based and trivially bypassed
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: security
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-review-local.py:473 — reads provider argv from `repo/.sd-ai-command-pack/review.json`.
  - scripts/sd-ai-command-pack-review-local.py:1666 — executes it via `shutil.which` plus `Popen(cwd=repo)`.
  - scripts/sd-ai-command-pack-review-local.py:400 — the guard checks executable names and `-c`, so `["/usr/bin/env","sh","-c",…]` and `["python3","-m",…]` pass.
  - scripts/sd-ai-command-pack-review-local.py:2131 — `main()` has no confirmation gate and no provider allowlist.
- why: The tool's job includes reviewing untrusted checkouts, so checkout plus review runs
  attacker-chosen commands, and a partial guard makes the surface look bounded.
- fix: Either document the adapter as full local code execution behind an explicit
  operator-scoped opt-in, or pin argv[0] to a resolved allowlist with a config-digest ack.
- notes: tracked -> .trellis/tasks/07-22-integrate-routed-review-backends R37 (prd updated 2026-07-28): requires either a resolved argv[0] allowlist with config-digest ack or a documented operator-scoped opt-in, and rejects the name-based guard as a third option.

## A-069 — The environment-blocked diagnostic redactor misses most common secret shapes while a stronger sibling already exists
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: security
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd_ai_command_pack_lib.py:497 — `_ENVIRONMENT_SECRET_RE` covers only bearer, token, and `gh[pousr]_`.
  - scripts/sd-ai-command-pack-fleet-timing.py:28 — the sibling covers `github_pat_`, `xox[baprs]-`, `sk-`, PEM, and key-value forms.
  - scripts/sd-ai-command-pack-work-loop.py:160 — the weak redactor feeds every environment-blocked fragment.
  - docs/SD_AI_COMMAND_PACK.md:1154 — those fragments are surfaced into agent-visible reports.
  - tests/test_script_lib.py:670 — the test table asserts only the three shapes already caught.
- why: Diagnostics are built from git and gh error text that echoes environment values, and
  a fine-grained PAT (`github_pat_`, which `gh[pousr]_` does not match) passes through
  verbatim into agent-visible diagnostics.
- fix: Promote the fleet-timing pattern set into one shared **pattern set** and extend the
  test table to the uncovered shapes. Corrected 2026-07-28: not one shared *redactor* —
  `sd_ai_command_pack_lib.py:519` substitutes `[redacted]` while
  `sd-ai-command-pack-fleet-timing.py:172` raises `FleetTimingError`, and neither policy is
  safe at the other's call site. Also corrected: the original `why:` said "PR-visible
  summaries"; a repo-wide search found no GitHub or PR publication path for these
  fragments. The exposure is agent-visible and local.
- notes: tracked -> .trellis/tasks/07-28-consolidate-secret-redactors (created 2026-07-28 with user consent) owns this as R1-R4: one shared pattern set, two preserved consumption policies (substitute in the lib, reject in fleet-timing), an over-redaction bound, and the extended test table. Residue of .trellis/tasks/07-28-analyze-recurring-trellis-workflow-instability, whose design package B specified only "bounded human text without secrets".

## A-070 — The .obsidian-kb root symlink is followed with no containment check, so KB refresh writes and prunes outside the repo
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: security
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-update-spec-kb.py:267 — `ensure_kb_root` accepts any symlink to a directory and returns it unvalidated.
  - scripts/sd-ai-command-pack-update-spec-kb.py:682 — the same file enforces containment for per-entry links via its own `is_within` helper.
  - scripts/sd-ai-command-pack-update-spec-kb.py:1315 — creates directories and writes Markdown under that root.
  - scripts/sd-ai-command-pack-update-spec-kb.py:655 — deletes marker-matched entries under it.
  - .agents/skills/sd-update-spec/references/obsidian-kb.md:9 — documents the symlink as intentional with no stated boundary.
- why: **Headline rebutted 2026-07-28 — see notes.** The root symlink escaping the repo is
  documented, intended behavior, and a hostile symlink cannot arrive through the repository.
  The surviving defect is narrower: the prune's third branch deletes any regular file under a
  managed category title with no ownership check, so a folder-name collision inside an
  operator's symlinked vault causes data loss.
- fix: **Superseded.** The filed fix — resolve the root and reject a git-tracked symlink —
  targets a vector that cannot occur and would break a documented feature. Instead, require a
  generated marker in `is_stale_generated_kb_entry`'s `:256` branch, matching the ownership
  checks its own `:247` and `:250` branches already apply.
- notes: owned by `.trellis/tasks/07-28-harden-kb-prune-marker-check` (created 2026-07-28,
  planning). Three facts rebut the headline: `docs/SD_AI_COMMAND_PACK.md:1065-1071` documents
  the root symlink resolving outside the repository as intended; `tests/test_update_spec_kb.py:138`
  asserts that documentation exists, so the proposed containment check would fail the suite; and
  `/.obsidian-kb` is gitignored at `.gitignore:172`, so it cannot be committed and no clone or PR
  can plant it. The evidence line claiming `is_within` is unused is also wrong — it has three
  callers (`update-spec-kb.py:615`, `:682`, `:1335`) guarding symlinks *inside* the KB. Reclassify
  the residual as P2 · correctness/data-loss, not security: no attacker and no privilege boundary
  are involved.

## A-071 — A CI run block interpolates ${{ }} directly into shell while every other step uses env indirection
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: security
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .github/workflows/tests.yml:457 — passes `"${{ github.event.before }}"` and `"${{ github.sha }}"` into a script.
  - .github/workflows/tests.yml:408 — the hardened pattern used everywhere else, via step `env:`.
- why: Both contexts are GitHub-generated SHAs today, but this is the one place a future
  context swap becomes template injection in a job holding `github.token`.
- fix: Move both into step `env:` and pass the shell variables.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-072 — The release payload gate checks changelog heading presence, not content coverage, so payload landing after the entry is authored ships undocumented
- status: open
- severity: P2 · effort: L · confidence: Verified
- dimension: release-hygiene
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-full-check.sh:745 — asserts payload changed implies version bumped.
  - scripts/sd-ai-command-pack-full-check.sh:770 — asserts a bumped version has a matching top heading; nothing checks coverage.
  - CHANGELOG.md:3 — the 0.56.0 entry's six bullets mention none of the gates below.
  - templates/scripts/sd-ai-command-pack-review-preflight.mjs:1038 — `bundle_unsupported_file_mode` ships in the tag, added after the bump.
  - templates/scripts/sd-ai-command-pack-review-preflight.mjs:1588 — `planning_active_task_outside_closure`, same.
  - docs/fleet/candidate-validation.json:1 — the digest gate did fire and restamp, while the changelog gate stayed silent.
- why: Two new consumer-facing rejection codes ship inside v0.56.0 with no changelog and no
  shipped-doc mention; a consumer bundle that passed can now be blocked.
- fix: Require a payload commit landing after the version-set commit to touch CHANGELOG.md,
  or check entry content against the PR's payload commits.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-073 — Six CHANGELOG releases have no git tag and five never existed as main-branch manifest state
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: release-hygiene
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - CHANGELOG.md:232 — the 0.42.0 heading, untagged.
  - CHANGELOG.md:735 — the 0.19.7 through 0.19.4 headings, untagged.
  - .github/scripts/release_identity.py:300 — `_remote_tag_object` hard-requires `refs/tags/vX.Y.Z` for fleet refresh.
- why: The changelog advertises versions that are neither reproducible nor installable, and
  the most recent occurrence is five days old, so the process defect is active.
- fix: Add a `make check` lint asserting every semver heading below the top has a matching
  tag, and reconcile the six orphans.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-074 — install.py and installer/** sit outside the release payload gate that CONTRIBUTING says covers installer behavior
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: release-hygiene
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-full-check.sh:712 — the payload set is `templates/**` plus manifest and guides.
  - .github/scripts/prepare-release.py:22 — the same set in the release-prep gate.
  - CONTRIBUTING.md:129 — requires a minor bump for new required installer behavior.
- why: The installer is the consumer-facing delivery mechanism, yet eleven first-parent
  merges changed it with neither a manifest nor a changelog change.
- fix: Add `install.py` and `installer/` to the payload set in both gates, or document the
  exclusion explicitly in CONTRIBUTING.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-075 — The release payload path rule is duplicated in two independently maintained gates with no shared constant or pinning test
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: release-hygiene
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-full-check.sh:712 — the `payload_singletons` heredoc used by the CI gate.
  - .github/scripts/prepare-release.py:22 — `PAYLOAD_SINGLETONS` used by `make release-prep`.
  - .github/scripts/prepare-release.py:218 — `_is_payload_path`, the second predicate; no test pins either list.
- why: The maintainer gate and the merge-blocking gate can silently diverge, so release-prep
  can pass what CI blocks.
- fix: Extract one importable payload-path predicate, have the shell gate shell out to it,
  and add a test pinning the list.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-076 — Git invocation has three lib-bypassing implementations plus five divergent adapter shapes over one operation
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: design
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd_ai_command_pack_lib.py:369 — `run_git` is the canonical runner with cache-environment isolation.
  - scripts/sd-ai-command-pack-work-loop.py:202 — builds the tool environment itself and never calls the lib.
  - scripts/sd-ai-command-pack-review-local.py:541 — raw `subprocess.run`, bypassing the lib.
  - scripts/sd-ai-command-pack-surface-check.py:124 — raw `subprocess.run`, bypassing the lib.
  - scripts/sd-ai-command-pack-record-session.py:102 — a delegating adapter that shadows the imported lib name.
  - scripts/sd-ai-command-pack-pr-body-scope.py:277 — a delegating adapter returning a tuple with a fabricated 124 exit code.
  - scripts/sd-ai-command-pack-update-spec-kb.py:142 — a delegating adapter returning `str | None`.
  - scripts/sd-ai-command-pack-review.py:303 — a delegating adapter returning `str`.
- why: Three scripts bypass the lib's cache-environment isolation entirely, and the five
  adapters expose five return and failure contracts for one concept.
- fix: Migrate the three bypassing callers onto the lib, then collapse the adapters to two
  lib shapes with a per-script error adapter passed via `context=`.
- notes: Cross-ref A-013 (fixed): the shared lib did land and five sites adopt it; this is the residue, not a regression of that fix. tracked -> .trellis/tasks/07-28-consolidate-shared-script-helpers (created 2026-07-28 with explicit user consent via audit.followups).

## A-077 — `outcome` and `status` mean structurally different things in sibling scripts composing one payload
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: design
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-housekeeping-result.py:358 — `"status"` is a whole sd-status document beside `"outcome"`.
  - scripts/sd-ai-command-pack-housekeeping-result.py:258 — but `classify_outcome()` itself returns `{"status": enum, …}`.
  - scripts/sd-ai-command-pack-work-loop.py:2844 — emits a bare-string outcome.
  - scripts/sd-ai-command-pack-pr-eligibility.py:1257 — reads the enum out of `result["status"]`.
  - scripts/sd-ai-command-pack-review-local.py:58 — a six-value outcome vocabulary that disagrees with housekeeping's four.
- why: A consumer cannot tell from the key whether `status` is a verdict or a document, and
  no single helper answers "how did it go" across commands.
- fix: Standardize on top-level `outcome: {status, reasonCodes}`, reserve `status` for the
  embedded sd-status document, and share one verdict enum in the lib.
- notes: tracked -> .trellis/tasks/07-28-unify-outcome-status-vocabulary (created 2026-07-28 with user consent). Evidence sharpened there: the single-payload collision is housekeeping-result.py:358 (status = document) against :359/:258 (outcome.status = enum); review-local.py:2035 and :2064 emit the same value as both names; five verdict vocabularies exist, not two. Its R5/R6 make backward compatibility and consumer enumeration blocking, so effort exceeds the audit's M.

## A-078 — The finish-work receipt schema is declared twice in two languages with no shared definition, and one kind covers two shapes
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: design
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-review-preflight.mjs:35 — `BOOKKEEPING_SCHEMA_VERSION` and the payload builder at :596.
  - scripts/sd-ai-command-pack-pr-eligibility.py:23 — restates the version, then every field, enum, and regex from :219.
  - scripts/sd-ai-command-pack-pr-eligibility.py:236 — rejects the pre-archive shape while sharing its `kind` tag.
- why: The trust boundary between finish-work and PR eligibility exists only as two
  hand-mirrored implementations, so a version bump is discovered at runtime.
- fix: Load one machine-readable schema on both sides, and split the kind into pre-archive
  and final-bundle so the shape follows from the tag.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-079 — SystemExit is the installer library's error channel, forcing `_for_remove` twin functions
- status: open
- severity: P2 · effort: L · confidence: Plausible
- dimension: design
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - installer/manifest.py:171 — `system_exit_detail` formalizes the pattern across 62 raise sites.
  - installer/provenance.py:81 — `_for_remove` twin that wraps the fatal call in `except SystemExit: return {}`.
  - installer/provenance.py:240 — the second twin.
  - install.py:698 — `main()` is the only place that should own process termination.
- why: A caller cannot distinguish "receipt missing" from "terminate process", so the API
  doubles for every reader with both fatal and tolerant callers.
- fix: Introduce an `InstallerError` exception, confine `SystemExit` to `main()`, and
  collapse the twins into a `missing_ok` parameter.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-080 — The cache-environment contract is re-declared in four places and enforced by a magic arity constant
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: design
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd_ai_command_pack_lib.py:38 — `CACHE_ENV_KEYS` and `CACHE_DIRECTORY_NAMES`, the producer.
  - scripts/sd-ai-command-pack-shell-lib.sh:194 — the keys hard-coded again.
  - scripts/sd-ai-command-pack-toolchain.sh:425 — a third copy, plus a partial fourth in the doctor heredoc at :308.
  - scripts/sd-ai-command-pack-shell-lib.sh:210 — asserts `count -ne 7`; toolchain.sh:435 asserts `count -eq 7`.
- why: Adding an eighth cache variable breaks every shell caller, so the producer cannot
  extend its own contract without a four-file lockstep edit.
- fix: Have cache-env emit the key set as data the shell validates generically, or generate
  one file both sides source.
- notes: tracked -> .trellis/tasks/07-28-consolidate-shared-script-helpers (created 2026-07-28 with explicit user consent via audit.followups).

## A-081 — run_command's name and docstring hide a filesystem-mutating cache bootstrap on every call
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: design
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd_ai_command_pack_lib.py:329 — the docstring says only "Run a command with a timeout".
  - scripts/sd_ai_command_pack_lib.py:331 — it calls `build_tool_execution_plan`, reaching `build_tool_environment` at :239.
  - scripts/sd_ai_command_pack_lib.py:149 — which mkdirs seven cache directories at 0o700 and can raise `CacheSetupError`.
  - scripts/sd_ai_command_pack_lib.py:433 — `repo_root()` reaches the same path, so asking for the repo root creates directories.
- why: The surface is hard to use correctly in read-only or sandboxed contexts, which is
  exactly where audit and inspection scripts run.
- fix: Split an explicit `prepare_tool_environment()` from a thin `run_command(env=…)`, or
  rename and document the mkdir side effect.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-082 — routedReview is a permanently constant field leaking an internal task reference into a published schema, with no reader
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: design
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-pr-eligibility.py:750 — the identical deferred literal.
  - scripts/sd-ai-command-pack-pr-eligibility.py:922 — the second producer.
  - scripts/sd-ai-command-pack-pr-eligibility.py:1241 — the third; no consumer exists anywhere.
- why: A field that can never take a second value is a comment, not a contract, and it goes
  stale as soon as the referenced task is renamed or closed.
- fix: Drop `routedReview` until routed review populates it, and keep the deferral note as a
  code comment.
- notes: tracked -> .trellis/tasks/07-22-integrate-routed-review-backends R39 (prd updated 2026-07-28): the routed lifecycle either populates routedReview or removes it from the published schema.

## A-083 — capture_output shadows the stdlib name with inverted semantics
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: design
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd_ai_command_pack_lib.py:320 — `capture_output=True` overwrites the caller's stdout and stderr.
  - scripts/sd_ai_command_pack_lib.py:344 — it passes a hard-coded `capture_output=False` to `subprocess.run`.
  - scripts/sd-ai-command-pack-record-session.py:434 — a caller needing merged streams must pass three arguments to work around it.
- why: A parameter borrowed from the stdlib that behaves oppositely is a trap; a forgotten
  third argument silently discards the merged stderr.
- fix: Rename it `merge_streams=False`, or drop the flag and let explicit stream arguments
  win.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-084 — The reviewer finding schema is duplicated verbatim in sixteen files
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: design
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .agents/skills/sd-audit-repo/SKILL.md:143 — the canonical 5-line schema block.
  - .agents/skills/sd-audit-repo/charters/security.md:1 — the same block, repeated in all 15 charters.
  - .agents/skills/sd-audit-repo/SKILL.md:207 — a second, richer report shape with a `confidence` field the reviewer schema lacks.
- why: This is the wire format between reviewers and the orchestrator, so a field rename is
  16 dev-tree edits plus 16 template edits and a missed file yields unparseable output.
- fix: State the schema once in a `charters/_shared-output.md`, have charters reference it,
  and carry the text in the dispatch prompt.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-085 — Hardened atomic_write_text landed in only one of three byte-identical copies
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: bloat
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-review-learnings.py:290 — hardened with a cross-device guard, directory fsync, and TOCTOU re-check.
  - scripts/sd-ai-command-pack-record-session.py:71 — the byte-identical unhardened copy.
  - scripts/sd-ai-command-pack-update-spec-kb.py:393 — the second unhardened copy.
  - scripts/sd-ai-command-pack-record-session.py:61 — `default_text_file_mode` is triplicated alongside it.
- why: Deliberate durability hardening was applied to one copy of a verbatim-duplicated
  routine, so session receipts and the KB still write without fsync or guards.
- fix: Move `atomic_write_text` and `default_text_file_mode` into the shared lib — all three
  scripts already import it — and delete the locals.
- notes: tracked -> .trellis/tasks/07-28-consolidate-shared-script-helpers (created 2026-07-28 with explicit user consent via audit.followups).

## A-086 — 2.0 MB of generated installed mirrors are committed alongside their templates/ sources and policed by ~210 KB of guard machinery
- status: open
- severity: P2 · effort: L · confidence: Plausible
- dimension: bloat
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - templates/scripts/sd-ai-command-pack-review-preflight.mjs:1 — 156,959 bytes duplicated at scripts/.
  - manifest.json:1 — 163,553 bytes duplicated verbatim at `.sd-ai-command-pack/manifest.json`.
  - tests/test_generated_parity.py:1 — 94,825 bytes of drift enforcement.
  - tests/test_pack_drift.py:1 — 25,841 bytes more.
  - scripts/sd-ai-command-pack-surface-check.py:1 — 29,730 bytes more.
  - .github/scripts/check-command-surface-drift.py:1 — 23,219 bytes more.
  - Makefile:31 — `make sync` regenerates the mirrors from the sources on demand.
- why: 175 duplicate groups totalling 1.97 MB double every payload diff and review surface,
  and four independent checkers exist only to prove the copies still match.
- fix: Gitignore the installed mirrors and make `install.py --force` a CI step, turning the
  parity suites into a "regeneration is clean" check; at minimum drop the duplicate manifest.
- notes: tracked -> .trellis/tasks/07-28-stop-committing-generated-mirrors (created 2026-07-28 with explicit user consent via audit.followups).

## A-087 — 396 of 546 committed Trellis context .jsonl files carry zero information
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: bloat
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .trellis/tasks/07-09-actionlint-workflow-linting/implement.jsonl:1 — placeholder-only content, one of 206 sharing the same blob.
  - .trellis/tasks/07-09-actionlint-workflow-linting/check.jsonl:1 — one of 190 empty files.
- why: 72% of per-task context artifacts are seeded boilerplate committed unmodified,
  recording nothing while the placeholder text itself instructs deletion.
- fix: Have finish-work or archive drop information-free jsonl files before archival, keeping
  the ~150 that carry real manifests.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-088 — Three dead helper functions are shipped to every consumer
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: bloat
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-install-audit.py:606 — `is_gitignored` is definition-only; the batch helper at :596 covers real use.
  - scripts/sd-ai-command-pack-housekeeping.sh:250 — `run_mutating_git` has zero call sites.
  - scripts/sd-ai-command-pack-housekeeping.sh:362 — `gh_issue_list` has zero call sites.
- why: Dead code is installed fleet-wide and counts against coverage floors, and an unused
  mutating-git wrapper beside a live dry-run wrapper implies a guard that does not exist.
- fix: Delete all three from `templates/` and run `make sync`.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-089 — Dead module constant in the fleet candidate checker
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: bloat
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-fleet-candidate-check.py:45 — `INSTALL_AUDIT` is defined and never used.
- why: It implies the candidate check invokes the install auditor when it does not, which
  misleads dependency tracing.
- fix: Remove the constant, or wire the call if it was intended.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-090 — The audit ledger accumulates resolved findings forever and re-injects them verbatim into every reviewer
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: bloat
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .trellis/audit/ledger.md:1 — 708 lines and 37 entries, of which 34 were already fixed.
  - .agents/skills/sd-audit-repo/SKILL.md:247 — fixed entries are kept forever by rule.
  - .agents/skills/sd-audit-repo/SKILL.md:107 — the whole ledger goes into the scope brief given verbatim to every reviewer.
- why: 92% closed history is carried by every reviewer on every run, so context cost grows
  monotonically while decision value stays with the open items.
- fix: Keep open and regressed entries in ledger.md, move fixed ones to
  `ledger-history.md`, and inject only the open-item summary.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-091 — 77% of the install manifest fans 58 sources out to twelve platforms with no declared consumer
- status: open
- severity: P3 · effort: L · confidence: Plausible
- dimension: bloat
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - manifest.json:1 — 754 entries from 174 unique sources; 580 target platforms no consumer requests.
  - docs/fleet/consumers.json:1 — eight consumers whose platform union is claude, gemini, github, opencode.
- why: Four-fifths of the manifest, the generator fan-out, and the parity assertions serve
  adapters nothing installs, and every command change pays the multiplier.
- fix: Put speculative platforms behind an opt-in generation flag, or record explicit
  external demand per platform.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-092 — Work-loop lock recovery destroys the competitor's lock when the restore link fails
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-work-loop.py:1057 — `os.link(aside, lock_path)` failure is captured as `restore_error`.
  - scripts/sd-ai-command-pack-work-loop.py:1072 — `aside.unlink()` runs regardless.
- why: On exFAT, SMB, or NFS state roots, EXDEV or EPERM means the unlink deletes a live
  run's lock and mutual exclusion is silently voided.
- fix: Unlink the aside file only when restore succeeded or a newer lock is proven; fall back
  to `os.replace`, otherwise leave it and raise.
- notes: owned by `.trellis/tasks/07-28-fix-work-loop-lock-restore` (created 2026-07-28,
  planning). Wording correction: "silently voided" overstates it for the recovering process —
  `work-loop.py:1070-1073` does raise `WorkLoopError`, so that process aborts loudly. The
  silence is on the other two sides: the original holder keeps running believing it holds a
  lock that no longer exists, and the next process acquires cleanly. The defect is the
  destroyed aside at `:1065`, not a missing raise. The fix must also preserve the
  `FileExistsError` branch (`:1061-1062`), where unlinking the aside is correct because a
  newer lock already won.

## A-093 — Recovery-artifact receipt scans truncate silently at MAX_RECEIPTS with no flag in the report
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-recovery-artifacts.py:53 — `MAX_RECEIPTS = 500`.
  - scripts/sd-ai-command-pack-recovery-artifacts.py:635 — `_iter_receipts` breaks at the cap.
  - scripts/sd-ai-command-pack-recovery-artifacts.py:706 — `classify_repository` breaks at the cap.
  - scripts/sd-ai-command-pack-recovery-artifacts.py:1159 — `_select_targets` breaks at the cap.
- why: Past 500 receipts, classification under-reports to sd-status and cleanup never reaches
  the tail, yet both report as complete.
- fix: Return truncated and scanned counts and propagate them into the classify and cleanup
  payloads.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-094 — Terminal reconciliation unlinks the run lock before persisting terminal state
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-work-loop.py:1588 — the unlink precedes `atomic_write_json`.
  - scripts/sd-ai-command-pack-work-loop.py:1590 — the unlink is unguarded, unlike the guarded reclaim paths.
- why: A write failure — the blocked-state path this file explicitly models — leaves the lock
  gone while state claims the run is live.
- fix: Write the state first, then unlink with `missing_ok=True`.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-095 — Cleanup lock swallows a payload write error and self-inflicts a stale lock it can never release
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-recovery-artifacts.py:960 — `os.write`/`fsync` `OSError` is passed, leaving a zero-byte lock while `_try_create` returns True.
  - scripts/sd-ai-command-pack-recovery-artifacts.py:1013 — release requires a token match, and `{}` never matches.
- why: On ENOSPC or EIO the process holds a lock it believes it released, so later cleanups
  are refused until the stale window expires.
- fix: On write failure, close the descriptor, unlink it, and raise `RecoveryError`.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-096 — allowed_returncodes is inert at every call site because check=True is never passed
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd_ai_command_pack_lib.py:357 — the gate requires `check`, which defaults False at :318.
  - scripts/sd-ai-command-pack-recovery-artifacts.py:284 — a call site that does not pass `check=True`.
  - scripts/sd-ai-command-pack-recovery-artifacts.py:379 — `allowed_returncodes={0}` reads as a guarantee that cannot fire.
- why: The sites read as though the listed exit codes are a contract, but the parameter can
  never take effect.
- fix: Pass `check=True` at the three sites, or drop the argument.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-097 — Housekeeping JSON workspace leaks on signal and rmdir can mask the real result status
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-housekeeping.sh:1170 — `mktemp -d` cleanup exists only on the straight-line path.
  - scripts/sd-ai-command-pack-housekeeping.sh:2 — `set -euo pipefail` with no `trap EXIT` anywhere in the file.
  - scripts/sd-ai-command-pack-housekeeping.sh:1184 — `rmdir` failure aborts before `return "$result_status"`.
- why: SIGINT and SIGTERM are routine for agent runs and leak the workspace, and an
  unexpected file replaces the computed status with an unrelated exit code.
- fix: Add `trap 'rm -rf -- "$temp_dir"' EXIT INT TERM` after the mktemp and use `rm -rf`.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-098 — Review state temp file name collides with a same-PID stale temp
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-review.py:518 — names the temp `.<name>.<pid>.tmp` and opens it `O_CREAT|O_EXCL`.
  - scripts/sd-ai-command-pack-recovery-artifacts.py:187 — the pack's other writers use `mkstemp`.
- why: PIDs recycle, so a killed run's leftover temp makes a later run fail with "cannot
  write review state" when nothing is actually wrong.
- fix: Use `tempfile.mkstemp(dir=…, prefix=…, suffix=…)` and chmod 0600.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-099 — The environment_blocked evidence schema has no machine consumer; all interpretation is agent prose
- status: open
- severity: P3 · effort: M · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd_ai_command_pack_lib.py:444 — the composer, validator, and tables span ~226 of the lib's 705 lines.
  - scripts/sd_ai_command_pack_lib.py:618 — the only reader of the discriminating fields is the lib's own validator.
  - scripts/sd_ai_command_pack_lib.py:606 — `validate_environment_blocked_evidence` has no caller outside tests.
  - scripts/sd_ai_command_pack_lib.py:641 — `cache_setup_blocked_evidence` is reachable only via `--json`.
  - scripts/sd-ai-command-pack-toolchain.sh:417 — the production caller uses plain mode and discards stderr.
  - .agents/skills/sd-help/references/environment-blocked-recovery.md:19 — `retryable` and `mutationState` semantics are decided in prose.
- why: A five-field typed schema with enums, a redactor, and a round-trip validator is
  maintained so an LLM can read it, and no code branches on any of it.
- fix: Collapse to `{reasonCode, boundary, operation, diagnostic}` with a prose retry policy,
  or add one programmatic consumer that honors `retryable` and `mutationState`.
  Resolved 2026-07-28 — split verdict. The headline claim is **rebutted**: agent-as-consumer
  is the deliberate design of work package B in
  `07-28-analyze-recurring-trellis-workflow-instability`, so collapsing the schema would undo
  a shipped decision. Do **not** take the first branch. The orphaned validation the finding
  uncovered is real and is taken as the second branch, narrowed:
  `sd_ai_command_pack_lib.py:606` has no non-test caller and the
  `sd_ai_command_pack_lib.py:687-691` `--json` branch is unreachable because
  `sd-ai-command-pack-toolchain.sh:417-418` invokes `cache-env` without `--json` and with
  stderr discarded. Scope moved from "remove ~226 lines" to "wire ~2 lines".
- notes: partly rebutted, residual tracked -> decided 2026-07-28. The schema-collapse recommendation is REBUTTED: agent-as-consumer is the deliberate design of work package B in .trellis/tasks/07-28-analyze-recurring-trellis-workflow-instability, which mandates exactly these fields. The residual orphaned validation is owned by .trellis/tasks/07-28-consolidate-secret-redactors R5: wire toolchain.sh:417-418 to pass --json so validate_environment_blocked_evidence (scripts/sd_ai_command_pack_lib.py:606) and the scripts/sd_ai_command_pack_lib.py:687-691 blocked branch stop being test-only. Wiring is preferred over deletion because toolchain.sh:419 restates the same remediation as hardcoded prose that the structured recoveryAction already carries.

## A-100 — The bookkeeping CI-skip classifier is a three-layer trust stack built for a narrow optimization
- status: open
- severity: P3 · effort: L · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .github/workflows/tests.yml:57 — ~200 lines of inline bash and multi-clause jq receipt validation, covered by no unit test.
  - .github/scripts/bookkeeping_ci_scope.py:1 — 477 lines of classifier.
  - .github/scripts/check-ci-result.sh:1 — a 73-line eight-argument acceptance gate.
- why: Roughly 600 lines of security-sensitive glue exist to skip lanes on `.trellis`-only
  commits, with the correctness risk concentrated in the hardest-to-test layer.
- fix: Move the receipt validation and ls-tree guard into the classifier as one testable
  entry point, or drop the skip if the saved minutes do not repay the surface. Prerequisite
  for A-038.
- notes: Doing this subsumes A-038 and A-041. tracked -> .trellis/tasks/07-28-consolidate-ci-fast-lane-trust-stack (created 2026-07-28 with explicit user consent via audit.followups).

## A-101 — sd-check re-hashes the entire worktree after every single check row
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-check.py:805 — the before snapshot.
  - scripts/sd-ai-command-pack-check.py:841 — `run_and_guard` re-snapshots after each row.
  - scripts/sd-ai-command-pack-check.py:253 — `_tracked_worktree_digest` SHA-256s every tracked and untracked file.
  - scripts/sd-ai-command-pack-check.py:311 — plus an rglob over eight guarded paths, at 5 git spawns each.
- why: Measured at 113 ms per snapshot over 2,155 files, nine snapshots cost ~1.0 s — about
  the rest of the check surface combined, and it scales linearly with configured checks.
- fix: Avoid re-hashing per row. (The originally proposed cheap per-row inventory digest —
  path, size, mtime_ns, mode — with a full-content fallback was rejected in planning: it
  weakens the mutation guard. See the owning task's R2.)
- notes: tracked -> .trellis/tasks/07-28-reduce-review-hashing-and-classifier-cost R1/R2 (split out of 07-25 on 2026-07-28). R2 constrains the fix: the metadata-only digest in the `fix` line above is NOT sufficient on its own — a same-size rewrite with mtime_ns restored, or a symlink retarget, evades it. The replacement must stay content-authoritative.

## A-102 — The gito review filter is built as one comma-joined argv element that grows with the whole repo
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-full-check.sh:231 — the fallback path is `git ls-files`, i.e. everything tracked.
  - scripts/sd-ai-command-pack-full-check.sh:261 — a per-path bash loop with a temp file, sort, and join.
  - scripts/sd-ai-command-pack-full-check.sh:454 — passes the joined string as `--filter`.
  - scripts/sd-ai-command-pack-full-check.sh:256 — `review_filter_pattern_for_path` is an identity printf.
- why: Measured at 142,524 bytes joined, past Linux `MAX_ARG_STRLEN`, so the fallback
  degrades and then hard-fails at exec.
- fix: Cap or skip the fallback filter and let `--vs` bound the scope; collapse the pipeline
  and delete the identity function.
- notes: owner filed 2026-08-10: `08-09-retire-review-pr-surface`, which deletes `scripts/sd-ai-command-pack-full-check.sh`. 0.65.0 removed the `sd-full-check` command surface but kept the script as the pack-source gate, so the joined `--filter` argv is still live until 08-09 lands. If that task keeps the gito lane in any form, the argv cap moves with it.

## A-103 — review-local digests changed files with unbounded whole-file reads though a streaming hasher already exists
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-review-local.py:603 — `read_bytes()` with no size cap, under a 20k path limit.
  - scripts/sd-ai-command-pack-check.py:136 — the same repo already hashes in 1 MB chunks.
- why: Peak RSS becomes the largest file in scope, so a large asset in the diff causes a
  proportional memory spike for no benefit.
- fix: Reuse the chunked shape, lift it into the shared lib, and call it from all four digest
  sites.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-104 — review-preflight spawns two to three git processes per commit in bookkeeping validation loops
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-review-preflight.mjs:1284 — per-commit `rev-list` plus `log`, bounded at 50.
  - scripts/sd-ai-command-pack-review-preflight.mjs:1818 — per-commit `merge-base`, `rev-list`, and changed-entries, bounded at 100.
  - scripts/sd-ai-command-pack-review-preflight.mjs:1918 — the batched `ls-tree` idiom the file already uses elsewhere.
- why: At ~8.8 ms per spawn this adds ~0.9 s and ~2.6 s against a 0.75 s whole-preflight
  baseline, and preflight runs inside both sd-check and full-check.
- fix: Replace the loops with a single `git rev-list --format='%H %P %s'` over the range,
  parsed once.
- notes: tracked -> .trellis/tasks/07-25-reduce-review-tooling-spawns R3 (prd updated 2026-07-28): batches the per-commit loops at review-preflight.mjs:1284 and :1818 that R1's memoizations do not reach.

## A-105 — The PR-body scope classifier fnmatches ~180 literal installed-target paths per changed path per rule
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-pr-body-scope.py:509 — the triple loop (a second one at :553).
  - scripts/sd-ai-command-pack-pr-body-scope.py:467 — appends the full installed-targets tuple to every rule.
  - scripts/sd-ai-command-pack-pr-body-scope.py:347 — pushes exact literals through `fnmatchcase`.
- why: O(1) set membership is performed as an O(n) glob scan, so classifier cost grows with
  payload size rather than with the diff.
- fix: Split the patterns into a literal set and a glob tuple at construction, checking the
  set first.
- notes: tracked -> .trellis/tasks/07-28-reduce-review-hashing-and-classifier-cost R3 (split out of 07-25 on 2026-07-28): literal set plus glob tuple at construction.

## A-106 — The installer probes gitignore status with one `git check-ignore` process per preserved receipt entry
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - installer/provenance.py:281 — the loop over preserved entries.
  - installer/provenance.py:289 — each iteration calls `is_gitignored_path`, which spawns `git check-ignore -q` at :247.
- why: 178 entries here and 753 in the worst case, at ~8.8 ms per spawn, for a question one
  batched query answers. Same pattern as the fixed A-014, in a different file.
- fix: Replace with a single `git check-ignore --stdin -z` call and a set lookup.
- notes: untracked in the active Trellis backlog as of 2026-07-28. Cross-ref A-014 (fixed): same batched check-ignore pattern, different file.

## A-107 — Base-ref discovery is recomputed from scratch at every call site in full-check
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-full-check.sh:192 — uncached command substitutions.
  - scripts/sd-ai-command-pack-full-check.sh:408 — one of five call sites; also :410, :439, :609, :909.
  - scripts/sd-ai-command-pack-shell-lib.sh:253 — each hop spawns `symbolic-ref` and `rev-parse` per candidate.
- why: The base ref is stable for the whole run, so the duplicated ceremony costs spawns and
  makes the script harder to reason about.
- fix: Resolve it once in `main`, export it readonly, and have the call sites read the
  variable.
- notes: tracked -> .trellis/tasks/07-25-reduce-review-tooling-spawns R4 (prd updated 2026-07-28): full-check.sh added to the file list; base ref resolved once in main.

## A-108 — Node.js is a required, undeclared, and unpinned dependency of the CI bookkeeping gate and every shipped consumer install
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: dependencies
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .github/workflows/tests.yml:204 — runs `node review-preflight.mjs` with no `setup-node` in any workflow.
  - docs/SD_AI_COMMAND_PACK.md:810 — the only version contract is prose naming Node 16.9, EOL 2023-09.
  - scripts/sd-ai-command-pack-full-check.sh:990 — checks for node presence only, not version.
- why: A 4,547-line JS gate is required in the CI fast path and vendored to every consumer,
  so a runner Node bump is an unreviewed dependency change.
- fix: Add `actions/setup-node` with an explicit version in both jobs, assert
  `process.versions.node` in the `.mjs`, and document a supported-LTS floor.
- notes: tracked -> .trellis/tasks/07-28-declare-pin-build-dependencies (created 2026-07-28 with explicit user consent via audit.followups).

## A-109 — pyproject.toml declares no [project] metadata, so the Python floor is duplicated in five unlinked places and tooling invents a conflicting one
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: dependencies
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - pyproject.toml:1 — only `[tool.ruff]` and `[tool.mypy]`; no `requires-python`.
  - pyproject.toml:24 — the floor restated as a mypy setting.
  - scripts/sd-ai-command-pack-toolchain.sh:54 — the floor restated again, and again at :193.
  - .gitignore:175 — ignores the `uv.lock` whose `requires-python >=3.13` contradicts the 3.10 floor.
- why: With no machine-readable floor, tools derive their own — uv picked 3.13 — and five
  hand-maintained copies drift undetected behind a gitignore.
- fix: Add a minimal `[project]` table with `requires-python >=3.10`, drop the uv.lock
  ignore, and check the CI matrix against that single source.
- notes: tracked -> .trellis/tasks/07-28-declare-pin-build-dependencies (created 2026-07-28 with explicit user consent via audit.followups).

## A-110 — Direct pins only: no lockfile, no hashes, and ~11 unpinned transitives resolve fresh on every CI run
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: dependencies
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - requirements-dev.txt:3 — direct pins with no transitive constraints.
  - requirements-security.txt:2 — the same.
  - .github/workflows/tests.yml:1 — a bare `pip install -r` with no `--require-hashes`.
- why: Yesterday's CI environment cannot be reproduced, and ten-plus transitives re-resolve
  unreviewed each run, so lint and type flakes read as workflow instability.
- fix: Commit hash-pinned compiled requirements, install with `--require-hashes`, and point
  Dependabot at the compiled files.
- notes: tracked -> .trellis/tasks/07-28-declare-pin-build-dependencies (created 2026-07-28 with explicit user consent via audit.followups).

## A-111 — No dependency vulnerability scan exists anywhere; CVE coverage rests on GitHub-side settings not visible in the repo
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: dependencies
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .github/workflows/tests.yml:381 — the security job runs only bandit and zizmor.
  - .github/dependabot.yml:3 — monthly pip version updates, the only advisory path.
- why: Nothing in-repo checks the resolved tree against advisories; exposure is limited
  because the shipped runtime is pure stdlib, so the risk is build-time only.
- fix: Add a `pip-audit` step over both requirements files in the security job.
- notes: owned by `.trellis/tasks/07-28-add-dependency-vulnerability-scan` (created
  2026-07-28, planning). The pure-stdlib claim in `why:` was independently confirmed by
  AST-parsing every file under `scripts/`, `templates/scripts/`, `installer/`, and
  `install.py` against `sys.stdlib_module_names`: zero third-party imports, so P3 is correct
  and the exposure is the CI runner only. Partial correction to the framing: `.github/dependabot.yml`
  **is** present and covers pip and github-actions, so CVE handling is not purely an opaque
  GitHub setting — but it is monthly with `open-pull-requests-limit: 2`, so the real gap is
  latency plus the absence of any CI signal. Dependabot *security* alerts remain a repo-level
  toggle with no in-repo representation.

## A-112 — Prism and Gito are hard-coded default third-party CLIs with no version contract, no install documentation, and config shipped to every consumer
- status: open
- severity: P3 · effort: M · confidence: Plausible
- dimension: dependencies
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - scripts/sd-ai-command-pack-review-local.py:1375 — fixed argv against bare PATH executables.
  - scripts/sd-ai-command-pack-full-check.sh:454 — `run_gito_command` with the same assumption.
  - manifest.json:1 — installs `templates/.gito/*` and `templates/.prism/*` to every consumer.
- why: The default review stack couples to two upstream flag sets with no version floor and
  no documented install path, so an upstream rename breaks review everywhere.
- fix: Record a minimum supported version per tool, probe `--version` before building argv,
  and document the install commands in README prerequisites.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-113 — Shipped onboarding docs pin the foundational upstream to a floating tag while the repo vendors a frozen version
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: dependencies
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - README.md:27 — instructs `npm install -g @mindfoldhq/trellis@latest`.
  - templates/docs/SD_AI_COMMAND_PACK.md:9 — the same instruction, shipped downstream.
  - .trellis/.version:1 — pins 0.6.7; .trellis/.template-hashes.json carries 114 template hashes against it.
- why: Consumers are told to install a floating `@latest` of an upstream whose 0.6.7
  contracts the vendored tree assumes.
- fix: Change the shipped doc to a `@^0.6` range, or warn in the install audit when the
  installed Trellis differs from `.trellis/.version`.
- notes: tracked -> .trellis/tasks/07-09-trellis-version-compatibility R5/R6 (prd updated 2026-07-28): trigger recorded as partially fired and the bounded doc-pin/audit-warning scope unparked; the full version-range contract stays parked for lack of an observed incompatibility.

## A-114 — The sd-full-check skill's "What It Does" is stale against the script it documents
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - .agents/skills/sd-full-check/SKILL.md:32 — claims `check-review-preflight.mjs` is the default.
  - scripts/sd-ai-command-pack-full-check.sh:977 — the default is the pack's own preflight; the legacy one is additional.
  - .agents/skills/sd-full-check/SKILL.md:104 — documents a KB lane that appears in no step and in no Expected Report row.
  - scripts/sd-ai-command-pack-full-check.sh:1029 — the step list omits the kb_freshness and pack_source_drift lanes entirely.
  - docs/SD_AI_COMMAND_PACK.md:686 — the shipped guide is correct, so two shipped docs contradict each other.
- why: This is an agent-facing contract shipped to every consumer, so the agent reports a
  preflight that did not run and drops KB skips the same file requires it to report.
- fix: Regenerate the step list from `main()`, add the KB lane to the Expected Report, and
  mirror to the template twin.
- notes: resolved by deletion in 0.65.0 (.trellis/tasks/07-24-remove-retired-review-surfaces): the `sd-full-check` skill and every generated copy of it are removed, so the stale "What It Does" section no longer ships. Left open for the next `sd-audit-repo` pass to confirm and close.

## A-115 — Five shipped scripts are missing from the installed guide inventory and one has no documentation anywhere
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - docs/SD_AI_COMMAND_PACK.md:81 — lists 21 of the 26 manifest `scripts/` targets.
  - scripts/sd-ai-command-pack-review-local.py:1 — 2,232 lines with an argparse CLI, mentioned in no README, doc, or skill.
  - CONTRIBUTING.md:135 — declares shipped script CLIs to be stable public surface.
- why: A consumer receives a 2,200-line executable described as stable with nothing saying
  what it is, which reads as unexplained cruft during a consumer audit.
- fix: Add the missing entries marking coordinator-internal helpers as internal, note that
  intent in CONTRIBUTING, and add a gate so the gap cannot silently reopen.
- notes: owned by `.trellis/tasks/07-28-document-remaining-shipped-scripts` (created
  2026-07-28, planning). **Figures corrected 2026-07-28: 3 of 26 manifest `scripts/` targets
  are undocumented, not 5, and the guide covers 23 of 26, not 21.** The three are
  `pr-eligibility.py`, `review-local.py`, and `sd_ai_command_pack_lib.py`. "Mentioned in no
  README, doc, or skill" is true of `review-local.py` exactly but misleading: a separate,
  live, shipped `sd-ai-command-pack-review-local.**sh**` (`manifest.json:264-265`) is
  documented at `docs/SD_AI_COMMAND_PACK.md:121`, `:549`, `:550`, `:895`, `:2179` and
  `README.md:621`, and does not invoke the `.py`. Two same-named tools, one documented. Also
  note `sd_ai_command_pack_lib.py` is a library imported by 31 files; documenting it as an
  operator tool would misrepresent it.

## A-116 — The README Overview omits 9 of 23 documented commands and names a nonexistent workflow
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - README.md:13 — omits sd-help, sd-audit-repo, sd-watch-pr, sd-fix-ci, sd-update-deps, sd-test-gaps, sd-ship, sd-retro, sd-fleet-refresh.
  - README.md:105 — those commands have their own sections further down.
  - docs/SD_AI_COMMAND_PACK.md:227 — "backlog design workflows" is a `selector=needs-design` argument, not a command.
- why: The first paragraph undersells the pack by nine commands and implies a command that is
  actually an argument.
- fix: Replace with a one-line scope statement plus a pointer to the Commands table, or
  generate it from the catalog source.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-117 — The README "for environments without make" verify block no longer mirrors the Makefile
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - README.md:729 — claims the block mirrors the Makefile.
  - README.md:747 — omits `bookkeeping_ci_scope.py` from the Ruff paths that Makefile:54 includes.
  - README.md:747 — has no mypy step, unlike Makefile:55, and no ShellCheck, unlike Makefile:66.
  - CONTRIBUTING.md:29 — its mypy scope sentence omits `.github/scripts`.
- why: A contributor without make believes the gate is mirrored and ships a mypy or Ruff
  failure that CI catches later.
- fix: Regenerate the block from the Makefile recipes or replace it with `make -n`, and
  correct the CONTRIBUTING scope sentence.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-118 — Troubleshooting misstates the Codex command shape and covers 5 of 17 adapters
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - docs/SD_AI_COMMAND_PACK.md:2186 — says Codex uses flat `/sd-<command>`.
  - docs/SD_AI_COMMAND_PACK.md:162 — the same file says Codex uses `$sd-review` skill mentions.
  - README.md:695 — the adapter matrix lists 17 platforms while the troubleshooting bullet names 5.
- why: The bullet a Codex user reads when a command is missing points at a slash entry the
  installer never creates.
- fix: Correct the Codex clause to the skill-mention form and point at the Supported Adapters
  matrix.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-119 — docs/review-learnings.md "Recent Copilot Review Signals" contains no recent signals
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - docs/review-learnings.md:15 — last updated 2026-07-21, seven days stale.
  - docs/review-learnings.md:1 — all 68 rows under "Recent" are prefixed **historical**, covering PRs #154–#206 while work has reached #272.
- why: The only human value is a single curated bullet, and the "Recent" block contains
  nothing current, so a reader cannot tell which signals apply.
- fix: Refresh via `review-learnings.py --update`, and rename the heading to Historical or
  cap it to a window.
- notes: untracked in the active Trellis backlog as of 2026-07-28.

## A-120 — install.py --skip-trellis-init is documented only in --help
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-28 @ 49b43afd
- last-seen: 2026-07-28 @ 49b43afd
- evidence:
  - install.py:394 — the flag definition.
  - README.md:576 — the "Useful options" list carries every sibling flag but not this one.
- why: The only escape hatch for `--local-only` installs that must not auto-run trellis init
  is invisible outside `--help`.
- fix: Add one line to the README `--local-only` paragraph and to the installed guide.
- notes: untracked in the active Trellis backlog as of 2026-07-28.
