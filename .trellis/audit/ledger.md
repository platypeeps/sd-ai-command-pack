# Audit ledger
Findings recorded by sd-audit-repo; managed by sd-audit-repo — humans may edit notes: lines.

## A-001 — Release version-bump/CHANGELOG gate is never enforced against a real PR diff in CI
- status: open
- severity: P1 · effort: M · confidence: Plausible
- dimension: tooling
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: dependencies
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- notes: tracked → .trellis/tasks/07-15-opencode-plugin-dependency-review

## A-005 — PackFile.install policy is an unvalidated open string; a typo silently changes install selection
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: design
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: release-hygiene
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P2 · effort: S · confidence: Plausible
- dimension: testing
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: architecture
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: design
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: design
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: improvements
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P2 · effort: M · confidence: Plausible
- dimension: testing
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: bloat
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- notes:

## A-017 — review-preflight.mjs spawnSync default 1MiB maxBuffer silently under-reports large diffs
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: correctness
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - scripts/sd-ai-command-pack-review-preflight.mjs:780 gitStdout, :858
    currentDiffStats, :887 currentChangedPaths pass no maxBuffer
  - on overflow result.error is treated as empty (:785, :863, :892)
- why: Oversized change sets — the ones most needing review — can preflight as
  clean/empty: a failure that reports success.
- fix: Pass an explicit larger maxBuffer and treat result.error as a hard
  failure.
- notes:

## A-018 — Dependabot does not monitor the .opencode npm/bun ecosystem
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: dependencies
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - .github/dependabot.yml:3-17 covers only pip (:4) and github-actions (:11)
  - no npm entry for /.opencode
- why: The tree with the widest supply-chain surface (native prebuilds, a
  prerelease) has zero automated CVE/freshness monitoring.
- fix: Add an npm-ecosystem entry for /.opencode (moot if the dependency is
  removed).
- notes: tracked → .trellis/tasks/07-15-opencode-plugin-dependency-review (folded)

## A-019 — .opencode manifest pins a loose caret while the lockfile drifted a minor ahead
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: dependencies
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - .opencode/package.json:3 ^1.14.39 vs bun.lock resolving 1.18.0
  - nothing enforces --frozen-lockfile
- why: Declared intent is ambiguous and resolution rests on discipline rather
  than the manifest.
- fix: Pin the exact version or raise the caret floor; enforce frozen lockfile
  (moot if removed).
- notes: tracked → .trellis/tasks/07-15-opencode-plugin-dependency-review (folded)

## A-020 — generated_pack_file overloads PackFile.source with MANIFEST_PATH for template-less files
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: design
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - installer/fileops.py:63-72 sets source=MANIFEST_PATH for generated targets
  - installer/provenance.py:56-62 + :139 must maintain
    PROVENANCE_EXCLUDED_KINDS to compensate
- why: The source field's contract is untrue for generated kinds; correctness
  relies on remembering an exclusion set.
- fix: Make source Optional[Path] (None for generated) or split a GeneratedFile
  type.
- notes:

## A-021 — SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER_LABEL missing from all structured config references
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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
- notes:

## A-022 — Core installer entry points and every installer/ module lack meaningful docstrings
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: documentation
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - installer/manifest.py:43 load_manifest, :101 validate_manifest,
    installer/fileops.py:154 selected_files have no docstrings
  - all six submodules share the identical boilerplate module docstring
- why: Responsibility boundaries between
  fileops/manifest/provenance/registry/removal are discoverable only by reading
  bodies.
- fix: One-line responsibility docstring per module; short docstrings on the
  primary public functions.
- notes:

## A-023 — Post-payload dogfood-sync and KB-refresh steps are manual with no wrapping make target
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: improvements
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - CONTRIBUTING.md:59-71 instructs manual install.py --force + update- spec-
    kb.py runs
  - Makefile:7 target set has no sync/release-prep
  - only rejection-side gates exist (test_pack_drift.py:243, :309)
- why: Exactly the steps maintainers forget, causing late-failing gate round-
  trips (this audit's own branch hit both, twice).
- fix: Add a make sync target running the dogfood install and KB refresh.
- notes:

## A-024 — review-preflight recomputes the documentation file list and re-reads docs across checks
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - review-preflight.mjs:759-777 documentationGuardFiles() walks per call (:327
    and :352)
  - readText (:1200) unmemoized
  - docs re-read at :336, :361, :594
- why: The doc-tree walk runs twice and every doc file is read multiple times
  per preflight run.
- fix: Compute the file list once; memoize readText with a Map.
- notes:

## A-025 — Backfilled changelog release dates disagree with tag dates and are internally out of order
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: release-hygiene
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - CHANGELOG.md:162 (0.7.4 - 2026-07-08) sits above :167 (0.7.3 - 2026-07-09)
  - git tag creatordates invert this
  - 0.7.1/0.7.2 likewise (from the 0.9.2 backfill)
- why: A reader reconstructing the release timeline gets contradictory dates
  and an impossible ordering.
- fix: Correct the 0.7.1-0.7.4 heading dates to the tag creation dates.
- notes: tracked → .trellis/tasks/07-15-docs-accuracy-batch (optional fold)

## A-026 — Deprecated env var REVIEW_PREFLIGHT_PR_BODY names no removal version or window
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: release-hygiene
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - scripts/sd-ai-command-pack-review-scope.sh:186 warn
  - README.md:213
  - guide :948-949 and :968-969 label it deprecated with no sunset
- why: An open-ended deprecation leaves consumers unable to plan migration and
  the shim accumulates indefinitely.
- fix: State a removal target next to the deprecation, or declare it
  permanently supported.
- notes: tracked → .trellis/tasks/07-15-docs-accuracy-batch (optional fold)

## A-027 — Trellis lifecycle hooks execute config-sourced commands via shell=True (upstream-owned)
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: security
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - .trellis/scripts/common/task_utils.py:262-271 subprocess.run(cmd,
    shell=True, ...)
  - cmd from .trellis/config.yaml hooks lists
    (.trellis/scripts/common/config.py:275-292)
- why: A repo shipping a malicious .trellis/config.yaml gains code execution
  when a developer runs a Trellis task command; matches the git-hooks/npm-
  scripts trust model, hence P3. Trellis-owned runtime — upstream concern.
- fix: Upstream: document full-shell semantics as trusted repo config and/or
  first-use opt-in gate.
- notes:

## A-028 — review-learnings git error/edge branches are untested (script at 69%)
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: testing
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - scripts/sd-ai-command-pack-review-learnings.py:497-501 returncode!=0 raise
    + untracked-diff path ~503-520 in coverage Missing
  - tests cover clean git states only
- why: Exactly the branches that break in real consumer repos would regress
  silently.
- fix: Add tests forcing git failures (stubbed git on PATH) and one staging an
  untracked file.
- notes:

## A-029 — Green local make check does not predict green CI: node and shellcheck lanes silently skip when tools are absent
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: tooling
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - Makefile:27-33 (node skip), :34-38 (shellcheck skip)
  - make setup (Makefile:9-12) installs neither
  - CI runs both unconditionally (tests.yml:101-107, :142-143)
- why: A clean-machine contributor gets green make check and red CI on ~6k
  lines of shell plus the .mjs preflight.
- fix: Make shellcheck+node hard setup prerequisites, or a STRICT=1 mode
  turning skips into errors.
- notes:

## A-030 — Type-check gate covers only installer/; shipped Python scripts get no mypy
- status: open
- severity: P3 · effort: S · confidence: Plausible
- dimension: tooling
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - tests.yml:98-99 and Makefile:26 run mypy installer only
  - install.py and scripts/*.py (update-spec-kb ~47KB, review-learnings ~31KB,
    install-audit ~32KB, pr-body-scope ~25KB) are ruff-only
- why: The type gate leaves most of the shipped Python payload uncovered.
- fix: Extend mypy to install.py and scripts/, or document the exclusion.
- notes:

## A-031 — Default install re-reads and re-hashes every source and destination in preflight then apply
- status: open
- severity: P3 · effort: M · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - install.py:617-640 (dry-run pass :618, apply :633)
  - installer/fileops.py:228 + :249 read both sides in each pass across 384
    targets
- why: Doubled read I/O on every default install, growing with payload size.
- fix: Have preflight return per-file conflict decisions (and bytes) threaded
  into apply.
- notes:

## A-032 — Provenance hashing re-reads sources the apply pass just read
- status: open
- severity: P3 · effort: M · confidence: Plausible
- dimension: performance
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - installer/provenance.py:150-153 sha256(file.source.read_bytes()) after
    fileops.py:228 read the same bytes
  - memoized per-source but still a third full read
- why: Redundant I/O over the distinct pack sources on every install.
- fix: Carry source bytes or their sha256 from install_file into InstallResult.
- notes:

## A-033 — Coverage gate omits all shipped shell (~90KB incl. destructive housekeeping) and .github/scripts release automation
- status: open
- severity: P3 · effort: M · confidence: Plausible
- dimension: testing
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
- evidence:
  - .coveragerc:6-10 includes Python only
  - housekeeping.sh (33KB), full- check.sh (27KB), review-local.sh, create-
    release-tag.py, check-main-push- scope.sh have no coverage floor
- why: The most destructive shipped code (git branch/worktree cleanup) has no
  measurement of which branches its subprocess tests reach.
- fix: Add kcov/bashcov with a floor, or document the exemption and add
  targeted error-branch subprocess tests.
- notes:

## A-034 — Command adapters use two divergent authoring models; transform rules live in a test rather than a generator
- status: open
- severity: P3 · effort: L · confidence: Plausible
- dimension: architecture
- first-seen: 2026-07-15 @ f6f3932
- last-seen: 2026-07-15 @ f6f3932
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

