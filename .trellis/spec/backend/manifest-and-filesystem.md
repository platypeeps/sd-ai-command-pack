# Manifest And Filesystem

> Manifest-driven install behavior and local filesystem conventions.

---

## Overview

There is no database, ORM, migration system, or persistent app state. The
installer reads `manifest.json`, validates the target repo, and writes selected
template files into that target repo.

## Manifest Source Of Truth

`manifest.json` owns the installable file list. Each file record declares:

- `platform`
- `kind`
- `source`
- `target`
- optional `anchor`
- optional `install`

`installer/manifest.py` converts each manifest entry into a frozen `PackFile`
in `load_manifest()`. Manifest-loaded entries always require a real `source`
inside the pack root. Installer-generated entries such as receipt, provenance,
and managed gitignore files may use `source=None`; do not point generated files
at `manifest.json` or another fake template source just to satisfy the type.
When adding a file, update `manifest.json` first and keep Python logic generic
unless the install semantics really change.

Reference files:

- `manifest.json`
- `installer/manifest.py`, `PackFile`
- `installer/manifest.py`, `load_manifest()`

## Release Payload Gate

Any pull request that changes shipped payload must carry the release ledger
with it. Shipped payload means `templates/**`, `docs/SD_AI_COMMAND_PACK.md`, or
`manifest.json`. The local full-check and the CI `Release payload gate` both
run the same pack-source drift gate against the PR base:

- payload changes require a `manifest.json` version bump;
- a version bump requires the top `CHANGELOG.md` heading to match
  `## <version> - YYYY-MM-DD`;
- non-payload changes must pass without a release bump.

Wire any future release-gate changes through the shared
`run_pack_source_drift_gates` implementation in
`scripts/sd-ai-command-pack-full-check.sh` and its template twin. Do not create
a separate CI-only interpretation of shipped-payload paths.

### Release Candidate Fleet Ledger Contract

1. **Scope / Trigger**: When a release changes the installable payload, validate
   the working candidate against disposable clones of every consumer before
   merging or tagging. This catches consumer integration failures without
   writing into active consumer worktrees.
2. **Signatures**:
   - `sd-ai-command-pack-fleet-candidate-check.py [--consumer NAME] [--json]`
     performs validation; `--check-ledger` performs read-only evidence checks.
   - `payload_digest(manifest, source_loader) -> str` binds evidence to every
     unique manifest source's bytes and executable bit plus canonical manifest
     JSON.
   - `validate_candidate_ledger(...) -> list[str]` returns every ledger defect;
     callers fail when the list is non-empty.
   - `create-release-tag.py --base REF --head REF` validates the ledger from the
     exact committed head tree before creating `v<manifest-version>`.
3. **Contracts**:
   - `docs/fleet/consumers.json` schema version 2 requires unique consumer
   names that are safe non-path identifiers, GitHub slugs, rollout priorities,
   bounded positive timeouts,
     platform lists, and `candidateChecks` as non-empty argv arrays.
   - `docs/fleet/candidate-validation.json` schema version 1 records
     `packVersion`, `payloadDigest`, `fleetManifestDigest`, and one passing row
     per consumer with its checked base commit and exact command arrays.
   - Candidate clone commands place `--` before the discovered origin URL so a
     malformed local remote beginning with `-` cannot inject Git options.
   - Candidate subprocess environments prepend the selected Python directory
     without adding an empty `PATH` entry when the inherited value is unset or
     empty.
   - Payload digest records delimit the executable marker on both sides before
     the content hash. Tag-time validation resolves tracked in-repo symlink
     chains from the exact commit tree and hashes the resolved regular blob and
     its executable mode, matching working-tree candidate validation.
   - A full all-pass run replaces the ledger atomically. Filtered or failing
     runs never replace canonical evidence.
4. **Validation & Error Matrix**:
   - Invalid fleet schema, duplicate priority/name, unsafe command shape, or
     unreadable payload source -> configuration error and exit 2.
   - Clone, install, audit, timeout, missing executable, or candidate-check
     failure -> report the consumer failure, continue the fleet, and exit 1.
   - Missing, malformed, partial, failing, or digest-stale ledger -> local/CI
     release gate and tag planner fail; no release tag is created.
   - `--consumer` combined with `--check-ledger` -> usage error; filtered runs
     are diagnostics and cannot certify a release.
5. **Good / Base / Bad Cases**:
   - Good: all disposable clones pass and the committed ledger matches the
     exact release payload, fleet manifest, checks, and consumer set.
   - Base: a filtered diagnostic identifies one consumer issue while leaving
     the prior canonical ledger untouched.
   - Bad: validate or install directly into a developer's active consumer
     checkout, or accept a ledger generated for different payload bytes.
6. **Tests Required**: Cover schema and priority validation, argv execution
   without shell interpolation, disposable origin clones, timeout and command
   failures, full-fleet continuation, atomic ledger preservation, every ledger
   drift dimension, source-only install-audit boundaries, full-check rejection,
   and exact-commit tag-planner rejection. Keep per-file coverage floors for
   the validator and shared fleet library at 90% or higher.
7. **Wrong vs Correct**:

   ```text
   Wrong: tag the version, then discover compatibility one consumer PR at a time
   Wrong: let a partial diagnostic overwrite the release evidence
   Correct: validate the working payload in disposable origin clones, commit the
            all-pass ledger, merge, let main CI tag that exact commit, then refresh
            consumers in explicit fast-canary priority order
   ```

## Manifest Path Safety

Validate manifest paths before any target-repo writes:

- `source` must stay inside the pack root and must not contain `..` path
  components after it is made relative to the pack root.
- `source` must also resolve inside the pack root so a template symlink cannot
  copy host files from outside the pack.
- `target` must be a relative path and must not contain `..` path components.
- `anchor` must be a relative path and must not contain `..` path components.
- Reject Windows drive and root anchors too, including drive-relative paths such
  as `C:tmp\pwn`, drive-absolute paths such as `C:\tmp\pwn`, UNC paths, and
  backslash-separated `..` traversal.

Keep these checks in `validate_manifest()` so malformed or hostile manifests
fail before target validation, selection, backups, or file copies.

Reference files:

- `installer/manifest.py`, `validate_manifest()`
- `installer/manifest.py`, `validate_relative_manifest_path()`
- `installer/manifest.py`, `validate_pack_source()`
- `tests/test_install_core.py`, `test_manifest_rejects_unsafe_target_paths`
- `tests/test_install_core.py`, `test_manifest_rejects_unsafe_anchor_paths`
- `tests/test_install_core.py`, `test_manifest_rejects_unsafe_source_paths`

## Target Validation

The installer requires `.trellis/config.yaml` in the target repository before
copying files. Keep that validation early in `main()` through
`require_trellis_repo()` so invalid targets fail before side effects.

Reference file:

- `installer/manifest.py`, `require_trellis_repo()`

## Installer Inspection Contract

1. **Scope / Trigger**: Use this contract whenever changing the read-only
   installer inspection path, its receipt parsing, report schema, audit
   delegation, or exit semantics. Inspection compares a consumer checkout
   with the current pack checkout; it must not fetch or mutate either one.
2. **Signatures**:
   - `python3 install.py TARGET --status [--audit] [--json]`
   - `python3 install.py TARGET --check [--json]`
   - `--check` implies the structural install audit. `--status` is
     informational unless receipt validation or an explicitly requested audit
     reports invalid state.
3. **Contracts**:
   - Stable states are `current`, `refresh-required`, `not-installed`, and
     `invalid`.
   - JSON schema version 1 contains pack identity, absolute target, source and
     installed versions, version relation, state, installed and active
     platforms, aggregate result counts, change count, deterministic reasons,
     and audit request/status/exit/output fields.
   - Inspection reuses the existing selection and dry-run planning behavior.
     `installer/inspection.py` owns receipt validation, aggregate
     classification, and human/JSON rendering. The shipped
     `sd-ai-command-pack-install-audit.py` remains the structural audit policy
     authority.
   - Inspection rejects mutation and selection flags: `--remove`,
     `--dry-run`, `--force`, `--backup`, `--local-only`,
     `--skip-trellis-init`, `--skip-diff-check`, `--platform`, and `--all`.
     `--audit` and `--json` require an inspection action.
   - Inspection must not create receipts, provenance, backups, Trellis state,
     managed blocks, or local excludes. It must not persist the source checkout
     path in consumer state or reports intended for tracking.
4. **Validation & Error Matrix**:
   - Current, audit-clean `--check` -> exit 0.
   - Malformed, contradictory, unsafe, or integrity-invalid receipts; failed
     audit; audit timeout; or launch error -> state `invalid`, exit 1.
   - Invalid CLI combination -> argparse exit 2.
   - Valid missing or refresh-required `--check` -> exit 3.
   - Informational `--status` with valid missing or refresh-required state ->
     exit 0. Missing installs mark requested audits `not-applicable` without
     spawning the audit subprocess.
5. **Good / Base / Bad Cases**:
   - Good: a current target reports bounded aggregate output or exactly one
     deterministic JSON document and leaves the complete target tree unchanged.
   - Base: an older valid install reports `refresh-required`; `--status` exits
     0 while `--check` exits 3.
   - Bad: corruption is presented as a routine refresh, inspection modifies a
     consumer receipt, or audit rules are duplicated in the installer module.
6. **Tests Required**: Cover parser combinations, every state/exit-code path,
   deterministic JSON, human output bounds, version relationships, active and
   installed platforms, malformed/partial/unsafe receipts, vouched hash drift,
   audit pass/failure/timeout/launch failure, environment override isolation,
   and complete target-tree snapshots proving no writes. Installer line and
   branch coverage remains 100 percent.
7. **Wrong vs Correct**:

   ```text
   Wrong: parse verbose --dry-run output or reimplement the audit scanner
   Correct: reuse dry-run-safe planning and delegate structural policy to the audit

   Wrong: return success from --check when a valid refresh is needed
   Correct: reserve exit 3 for valid operator action and exit 1 for invalid state
   ```

## Selection Rules

Use `selected_files()` for platform filtering, anchor checks, and active
Trellis platform detection:

- `install: "always"` files are selected by default.
- `install: "always"` files are also selected when `--platform` filters are
  present; adapters depend on the shared skill being installed.
- `--all` selects all adapters even when platform directories or active
  Trellis platform markers are absent.
- `--platform` selects only requested platforms and bypasses anchor and active
  marker detection for those selected platforms.
- Default adapter installation depends on both the target anchor directory,
  such as `.cursor`, `.gemini`, `.github`, or `.opencode`, and a Trellis-owned
  marker for that platform. A generic `.github` directory used only for Actions
  must not cause GitHub Copilot prompt files or managed instruction blocks to
  install.

Reference files:

- `installer/fileops.py`, `selected_files()`
- `tests/test_generated_parity.py`,
  `test_installs_shared_skill_and_existing_platform_adapters`

## Receipt Stability Across Checkouts

The installed-targets receipt is declared installed state and can be
git-tracked while some recorded targets (and the markers/anchors that select
them) are gitignored — the claude adapter's markers all live under
`.claude/`. A refresh run from a checkout where a platform is merely not
visible must not erase what another checkout legitimately installed:

- Keep existing receipt entries for manifest files skipped by marker
  detection or by a `--platform` filter, and report each kept entry as
  `kept-in-receipt`.
- Keep entries for anchor-skipped files only when `git check-ignore`
  confirms the file path is ignored in the target; check the file path, not
  the anchor directory, because trailing-slash directory ignore patterns do
  not match a bare nonexistent directory path. A tracked-but-removed anchor
  is an intentional platform removal and still drops its entries.
- Fail closed: when git is missing or the target is not a repository,
  preservation does not apply.
- Intentional platform removal is a manual receipt edit; the installer does
  not guess.

The install audit mirrors this: a receipt target that is missing but
gitignored in the current checkout is a warning with a reinstall hint, not a
failure. The reverse policy is equally supported: a pack-like file that
exists but is not recorded in the receipt warns instead of failing when the
file is gitignored, so repo-local guards that strip local-only adapters
from the receipt (rwbp-website's policy) pass the audit alongside the
installer's record-and-warn default. Tracked-but-unlisted pack-like files
remain failures. Receipt lines normalize Windows-style separators to `/` at
load time, after the unsafe-path rejection. This does not contradict the
"no mutable installer state" rule — the receipt is the explicit, reviewable
state file, and preservation only refuses to destroy entries the current
checkout cannot verify.

Manifest completeness closes the newly-added-target gap during a two-version
refresh. When older receipt entries identify a platform, the audit requires all
current manifest targets for that platform, including targets that did not
exist in the older receipt. `--expected-platform PLATFORM` must remain the
fleet contract because it declares the expected platform independently of
receipt history; it also catches a wholly absent first install or a receipt
that has lost every entry for that platform.

## Provenance

Every non-dry-run install writes `.sd-ai-command-pack/provenance.json`:
pack name, version, and a sorted map of vouched targets to `sha256:` hashes
of the installed content. For normal source-backed files, `install_file()`
records `source_digest`, `source_content`, and `source_executable` on
`InstallResult`; provenance must prefer that carried digest instead of
re-reading the source file. Legacy/narrow tests that construct results without
a digest may still fall back to hashing `file.source`, but source-less
generated files are skipped by shape. Never vouched: `FORCE_PRESERVED_TARGETS`
(user-tunable), managed-block targets (shared ownership), generated files
(receipt, gitignore block, provenance itself), and conflict results.
Entries survive for targets still recorded in the receipt so filtered runs
do not shrink coverage. The audit ignores stale provenance claims for those
never-vouched targets from older installs, then fails on content drift (naming the
recorded pack version), on a vouched target that is missing while not
gitignored (even when the receipt no longer lists it — provenance is the
tamper-evidence of last resort), on any symlink or non-regular node at a
vouched path, on a vouched path whose real path escapes the repository
root (symlinked parent directories), on inspection failures (per-target
`os.lstat`, reported with the exception text), and on a provenance file
that is itself not a regular file or is malformed, including an empty
`files` map. Gitignored-absent vouched targets skip, consistent with the
structural policy; structural `path_exists` is lstat-based so unreadable
parents degrade to missing-target reports instead of crashing. Absent
provenance (pre-0.5.10 installs) keeps the older audit behavior. When
provenance is present and the audit passes, the command reports the installed
payload provenance version and confirms vouched hashes match; that version can
intentionally be older than the source checkout manifest when a newer release
did not change installed payload bytes.

Reference files:

- `installer/provenance.py`, `preserved_receipt_targets()`, `is_gitignored_path()`,
  `provenance_content()`, `install_provenance_file()`
- `templates/scripts/sd-ai-command-pack-install-audit.py`, `is_gitignored()`,
  `audit_provenance()`
- `tests/test_install_audit.py`,
  `test_install_keeps_receipt_entries_for_gitignored_absent_anchor`
- `tests/test_install_audit.py`,
  `test_install_audit_downgrades_gitignored_missing_targets`
- `tests/test_install_audit.py`, `test_install_writes_provenance_with_hashed_targets`
- `tests/test_install_audit.py`,
  `test_install_audit_reports_installed_payload_provenance_version`
- `tests/test_install_audit.py`,
  `test_install_audit_warns_for_unlisted_gitignored_pack_files`

## Remove Mode Preserve-And-Continue Contract

1. Scope and trigger: use this contract whenever changing `install.py
   --remove`, `installed_target_candidates()`, `remove_pack_file()`,
   `remove_text_block_file()`, `remove_local_only_exclude()`, receipt reads,
   provenance reads, or managed-block marker cleanup.
2. Signatures: `python3 install.py TARGET --remove [--force] [--backup]
   [--dry-run]` must return `0` when unsafe or drifted target state is
   preserved and all other safe targets are processed. Preservation is a normal
   uninstall result, not a fatal CLI validation failure.
3. Contracts: remove mode treats target-repo state as user-owned unless the
   specific target is both manifest-recognized and proven safe to delete or
   update. Unsafe/unreadable `.sd-ai-command-pack/installed-targets.txt` or
   `provenance.json` state is treated as absent for uninstall candidate
   discovery, then removal falls back to manifest-selected targets plus
   generated state targets. Normal install/update paths may remain stricter
   because they are establishing controlled state.
   Receipt/provenance entries are candidate discovery only; a hash match must
   not authorize removal for a path absent from the current manifest target
   set or generated pack state. Root `.git/` paths are never whole-file remove
   candidates, regardless of receipts, provenance, manifest state, or
   `--force`.
4. Validation and error matrix: unsafe candidate path -> `preserved` with the
   validation detail; parent directory resolving outside the target repo ->
   `preserved`; unreadable target file -> `preserved`; invalid UTF-8 in a
   preserve-invalid-UTF-8 path -> `preserved`; incomplete or duplicated managed
   markers -> `preserved`; backup copy failure after a target is considered
   removable -> fatal clean `SystemExit` because the requested destructive
   action cannot be made reversible.
5. Good, base, and bad cases: a generated pack file with matching content is
   removed; a drifted file without `--force` is preserved; a receipt with
   unsafe paths does not abort the run; a receipt/provenance entry for
   `.git/config` or `USER_DATA.txt` is reported as ignored and preserved even
   with a matching hash and `--force`; `.git/info/exclude` with malformed
   local-only markers remains untouched; aborting the whole uninstall because a
   single user-owned file cannot be parsed is wrong.
6. Tests required: cover unsafe receipt/provenance fallback, unsafe regular
   candidate paths, symlinked parent directories, unreadable targets, malformed
   managed markers, `.git/info/exclude` parse failures, backup-copy failures,
   and CLI-level remove output that continues after preservation.
7. Wrong vs correct:

   ```text
   Wrong: remove_marked_block() raises SystemExit and aborts install.py --remove
   Correct: remove_text_block_file() returns preserved with the marker error detail

   Wrong: unsafe receipt/provenance paths stop all uninstall candidate discovery
   Correct: remove mode ignores unsafe receipt state and falls back to manifest targets
   ```

## File Writes

Use `install_file()` for copy behavior:

- Before reading, backing up, or writing a target path, validate that the
  resolved destination stays inside the resolved target repository. This
  catches existing symlinks in the target repo that would otherwise redirect a
  relative manifest path outside the repo.
- If the target path is already occupied by a directory, broken symlink,
  symlink to a directory, or other non-file path, fail with a controlled error.
  Do not let `read_bytes()` or `copyfile()` raise a traceback for expected
  target-repo state.
- Return `unchanged` when the target already has identical bytes.
- Return `conflict` and leave the target untouched when content differs and
  `--force` is absent.
- Return `preserved` and leave the target untouched when content differs and
  the target is `.prism/rules.json` or `.gito/config.toml`, regardless of
  `--force`; repo-local review-tool policy is intentionally protected during
  pack refreshes and must not be reported as a conflict.
- Keep `.gito/sd-ai-command-pack.env` updateable like scripts and docs. That
  file carries pack-owned runtime defaults, while credentials, model choices,
  and user-specific Gito settings belong in `~/.gito/.env` or the process
  environment.
- With `--force --backup`, copy the previous target file next to the original
  with a `.bak` suffix before overwriting it. Do not create backups for
  preserved review-tool policy files because they are not overwritten.
- Backup candidates must also resolve inside the target repo, and an existing
  symlinked `.bak` path counts as occupied even when the symlink is broken.
- Copy with `shutil.copyfile()` only after creating the target parent
  directory.
- In `--dry-run` mode, report the planned status without creating files.

Generated text writers follow the same safety model:

- `.gitignore`, `.github/copilot-instructions.md`,
  `.sd-ai-command-pack/manifest.json`, `.sd-ai-command-pack/provenance.json`,
  and `.sd-ai-command-pack/installed-targets.txt` are regular-file targets. If
  the final path is an in-repo symlink, report `symlink-conflict` and leave the
  link plus its target untouched. If the final path is another non-file node,
  report `conflict` and leave it untouched. Symlinks that resolve outside the
  target repo still fail target-path validation before any write.
- Use temp-file + `os.replace` writes for generated text and shipped helper
  rewrites of user-facing files. A failed replace, ENOSPC, or interrupted write
  must leave the previous complete file in place and clean up the temporary
  file.
- Standalone shipped scripts cannot import the installer package in consumer
  repos. Shared Python behavior for consumer-shipped scripts belongs in
  `scripts/sd_ai_command_pack_lib.py` and its `templates/scripts/` twin; keep
  that module stdlib-only and manifest-installed with the scripts that import
  it.

## Shipped Python Helper Library

1. Scope and trigger: use this contract when adding or changing shared Python
   helpers consumed by installed `scripts/sd-ai-command-pack-*.py` files, or
   when moving repeated subprocess, git, gh, path, or error-formatting behavior
   out of individual scripts.
2. Signatures: `scripts/sd_ai_command_pack_lib.py` exposes
   `CommandError`, `DEFAULT_COMMAND_TIMEOUT`, `DEFAULT_GIT_TIMEOUT`,
   `DEFAULT_GH_TIMEOUT`, `DEFAULT_TRELLIS_TIMEOUT`, `command_display(args)`,
   `command_detail(process, fallback)`, `run_command(args, *, timeout,
   context, check, cwd, allowed_returncodes, capture_output, stdout, stderr,
   text, encoding, errors)`, `run_git(args, *, cwd, timeout, check,
   allowed_returncodes, errors, context)`, `run_gh(args, *, cwd, timeout,
   check, allowed_returncodes, errors, context)`, `git_stdout(args, *, cwd,
   timeout, errors, context, required)`, and
   `repo_root(*, fallback_to_cwd=False)`.
3. Contracts: the helper is copied from `templates/scripts/` into the same
   installed `scripts/` directory as its consumers, so scripts import it by
   module name and must not mutate `sys.path` at runtime. The helper must remain
   dependency-free, must not import `installer.*`, must preserve UTF-8
   replacement decoding for captured output, and must apply bounded subprocess
   execution by default: 60 seconds for generic/git commands and 120 seconds
   for GitHub or Trellis operations unless a caller supplies a narrower
   timeout.
4. Validation and error matrix: empty command -> `CommandError`; missing binary
   -> `CommandError` naming the command and context; timeout ->
   `CommandError` naming the command, context, and timeout seconds; checked
   nonzero exit -> `CommandError` with stderr/stdout detail; unchecked nonzero
   exit -> returned `CompletedProcess`; repository-root lookup outside git ->
   `CommandError`.
5. Good, base, and bad cases: good scripts call `run_git(["status"], context=...)`
   or `run_gh(["pr", "view"], context=...)` and report the helper's
   user-facing error; a base successful command returns the original completed
   process; a bad script reimplements `subprocess.run(..., timeout=...)` with
   different messages or imports installer modules that do not exist in
   consumer repos.
6. Tests required: add focused helper tests for success, empty command, missing
   binary, timeout, checked failure, git/gh timeout defaults, stdout stripping,
   and repo-root failure. Any migrated script must keep focused tests for its
   previous CLI behavior plus root/template byte parity, manifest selection,
   install-audit provenance, and shipped-script coverage floor updates.
7. Wrong vs correct:

   ```text
   Wrong: subprocess.run(["git", "rev-parse"], check=True)
   Correct: run_git(["rev-parse", "--show-toplevel"], context="resolve repository root")

   Wrong: from installer.fileops import run_diff_check
   Correct: from sd_ai_command_pack_lib import run_command
   ```

## Plan-Before-Apply And Concurrency

For a normal tracked install without `--force` or `--dry-run`, run the selected
payload once in dry-run mode before the first pack-owned write. If any selected
target conflicts, report every conflict and exit `2` without partially applying
the refresh. Local-only Trellis bootstrap is outside this boundary because it
invokes the external Trellis installer before pack files exist.

When that preflight succeeds, thread the preflight `InstallResult`s into the
apply pass for unchanged, created, and preserved source-backed files. The apply
pass should reuse the planned source bytes, executable bit, and digest instead
of re-reading the pack source, but only after revalidating that the destination
still matches the planned status. If the destination appeared, disappeared,
changed content, or became a symlink between preflight and apply, fall through
to the normal install path so conflict and symlink-conflict handling remains
authoritative. Do not reuse preflight results for force overwrites, conflicts,
generated files, or a mismatched `PackFile`.

Installer runs are not serialized. Atomic file replacement must keep each
individual file parseable, while the last completed writer determines the
final receipt and provenance. Tests must exercise two concurrent installer
processes and verify that both state files parse and that every vouched hash
matches the final installed content. Operators should still run one refresh at
a time because output, backups, and selected-platform intent are not merged.

## Diff Checks

Run the final `git diff --check` only against manifest-selected target paths.
The installer should not fail because an unrelated tracked file in the target
repo already has whitespace errors.

## Trellis Gitignore Maintenance

For normal tracked installs, maintain a repo root `.gitignore` block between
`# sd-ai-command-pack trellis-gitignore start` and
`# sd-ai-command-pack trellis-gitignore end`. The block must ignore Trellis
local/runtime paths such as `.trellis/.developer`, `.trellis/.runtime/`,
`.trellis/.cache/`, `.trellis/.backup-*`, `.trellis/worktrees/`, and
`.trellis/.template-hashes.json` without blanket-ignoring `.trellis/`. It must
also ignore local AI-tool state under `.claude/`, `.codex/`, `.gemini/`, and
`.opencode/` without blanket-ignoring those platform directories, so shared
Trellis and SD command-pack adapters remain trackable.

When adding the block, migrate exact unmarked `.trellis`, `.trellis/`,
`/.trellis`, and `/.trellis/` entries into the managed block so Trellis specs,
tasks, workflow, scripts, and shared runtime files remain trackable. Keep
`--local-only` installs on `.git/info/exclude`; local-only mode must not modify
tracked `.gitignore`.

### Review Tool Config And Ignore Hygiene

1. Scope and trigger: use this contract whenever adding or changing
   distributed review-tool config, review runner temp files, generated review
   reports, or AI-tool local-state ignore rules.
2. Entry points and data: `manifest.json` owns `.prism/rules.json`,
   `.gito/config.toml`, `.gito/sd-ai-command-pack.env`, and review scripts.
   `installer/registry.py` owns `FORCE_PRESERVED_TARGETS`,
   `REVIEW_ARTIFACT_GITIGNORE_PATTERNS`,
   and `PLATFORM_LOCAL_GITIGNORE_PATTERNS`; `installer/fileops.py` owns
   `trellis_gitignore_block()`.
3. Contracts: preserve existing `.prism/rules.json` and `.gito/config.toml`
   files even with `--force`; install or update `.gito/sd-ai-command-pack.env`
   from the pack. Never ignore the whole `.gito/`, `.prism/`, `.claude/`,
   `.codex/`, `.gemini/`, or `.opencode/` directories because pack-owned
   adapters and config must remain trackable.
4. Ignore matrix: the managed `trellis-gitignore` block must ignore
   `.build/`, root `code-review-report.json` and `code-review-report.md`, pack
   temp files such as `sd-ai-command-pack-gito.*`,
   `sd-ai-command-pack-review-paths.*`,
   `sd-ai-command-pack-review-filters.*`,
   `sd-ai-command-pack-prism-codebase.*`, `sd-ai-command-pack-ci-paths.*`,
   `sd-ai-command-pack-uv-cache/`, `sd-ai-command-pack-uv-tools/`, and
   Gito-local state patterns such as `.gito/**/.cache/`, `.gito/**/cache/`,
   `.gito/**/logs/`, `.gito/**/tmp/`, `.gito/**/*.local.*`, and
   `.gito/**/*.log`.
5. Good, base, and bad cases: a fresh install adds the managed block and
   trackable review config; an update replaces the marker block without
   duplicating entries; local-only writes equivalent ignores to
   `.git/info/exclude`; a repo-custom `.gito/config.toml` is reported
   `preserved`; a blanket `.gito/` or `.prism/` ignore is wrong.
6. Tests required: cover fresh block creation, marker-block replacement,
   migration away from blanket Trellis ignores, local-only exclude behavior,
   negative `git check-ignore` expectations for `.gito/config.toml` and
   `.prism/rules.json`, and positive `git check-ignore` expectations for
   generated review reports, temp files, and Gito cache/log/tmp files.
7. Common failure mode: treating review config and review output as the same
   class of file. Correct behavior is to track distributed defaults and
   adapters, preserve user-tuned policy files, and ignore generated reports,
   caches, logs, temp files, secrets, and local state.

### Obsidian KB Copy Folder Contract

1. Scope and trigger: use this contract whenever changing
   `scripts/sd-ai-command-pack-update-spec-kb.py`, the matching template script,
   or documentation for `.obsidian-kb/` generation.
2. Signatures: `python3 scripts/sd-ai-command-pack-update-spec-kb.py`,
   `--dry-run`, and `--check` are the stable entry points. The normal command
   writes `.obsidian-kb/`, the managed ignore block,
   `.obsidian-kb/Dashboard - <repo>.md`, and
   `.obsidian-kb/LLM-KB - <repo>.md`; `--dry-run` prints the planned copy count
   without writing; `--check` exits nonzero when copies, dashboard, LLM
   overview, stale generated entries, or ignore state are not current.
3. Contracts: generated KB entries are real file copies, not symlinks. The
   helper copies selected repository knowledge files into visible semantic
   category paths under `.obsidian-kb/` instead of mirroring hidden source
   folders, writes dashboard and LLM overview links to those copied paths,
   includes one-line document descriptions in the dashboard, includes a GitHub
   repository link when `origin` is a GitHub remote, groups generated index
   links by semantic category rather than source folder name, normalizes
   platform-root `agents.md`/`AGENTS.md` guidance filenames case-insensitively
   to the same stable destination such as `codex-agents.md`, avoids generated
   KB file/folder names that start with `.` or use Trellis-specific naming, and
   keeps `.obsidian-kb/` ignored through the managed
   `obsidian-kb` block in `.gitignore` or `.git/info/exclude` for local-only
   installs.
4. Validation and error matrix: user-owned symlinks that point outside the repo
   are conflicts and must not be overwritten; legacy tool-created relative
   symlinks that resolve inside the repo are replaced by copies; occupied
   non-file paths are conflicts; stale generated files and legacy generated
   symlinks not in the current source set are pruned; user-owned dashboard or
   LLM overview files without the matching marker are conflicts. Existing
   `.obsidian-kb/` folders from the older symlink helper are migrated in place:
   pack-owned relative symlinks are replaced by category-layout copies, old
   mirrored generated paths and the legacy generated `LLM-KB.md` filename are
   removed, and the report includes the count of legacy symlinks converted or
   waiting to be converted.
5. Good, base, and bad cases: a fresh run creates copies plus a generated
   dashboard and LLM overview; a second run reports the copies as present; a
   modified source doc updates the copied file and generated indexes; deleting
   a selected source removes the stale generated copy and its index entry;
   renaming the dashboard leaves the legacy generated `Dashboard.md` stale and
   removable; leaving symlinks as the durable KB format is wrong because copying
   `.obsidian-kb/` into an Obsidian vault would break those links.
6. Tests required: cover fresh copy generation, dry-run no writes, check mode
   stale detection and acceptance after refresh, local-only exclude behavior,
   custom dashboard conflicts, unmarked gitignore entry migration, invalid
   gitignore byte preservation, and replacement of legacy generated symlinks
   with real file copies, including nested existing symlink trees from the old
   mirrored layout. Also cover the generated `LLM-KB - <repo>.md` overview,
   legacy generated `LLM-KB.md` pruning, and GitHub remote parsing/linking in
   the dashboard. Assert category headings
   such as repository overview, agent guidance, specs, repository maps,
   project manifests, and package documentation instead of folder-name
   headings such as `docs` or `.trellis/spec/backend`; assert dashboard
   one-line descriptions, the repo-specific dashboard filename, and generated
   KB paths with no leading-dot components or Trellis-specific names.
7. Wrong vs correct:

   ```text
   Wrong: .obsidian-kb/README.md -> ../README.md
   Wrong: .obsidian-kb/.trellis/spec/backend/index.md mirrors the hidden source path
   Correct: .obsidian-kb/Repository Overview/README.md contains the copied README bytes
   Correct: .obsidian-kb/Backend Specs/index.md contains the copied backend spec bytes
   ```

## Manifest Schema Contract

`manifest.json` carries `schemaVersion` (currently 1). `load_manifest()`
rejects manifests with a newer major schema, converts JSON parse errors and
missing entry fields to single-line `error:` messages (no tracebacks), and
`validate_manifest()` enforces the closed `KNOWN_MANIFEST_KINDS` set so a
misspelled kind can never silently downgrade a managed-block entry to a plain
file copy. `requiresTrellis` is wired: when a manifest sets it false, the
installer skips the Trellis-repo precondition.

Reference files:

- `installer/manifest.py`, `load_manifest` / `validate_manifest`
- `tests/test_install_core.py`, `test_load_manifest_rejects_malformed_manifests`
- `tests/test_install_core.py`, `test_validate_manifest_rejects_unknown_kind`
- `tests/test_install_core.py`,
  `test_install_skips_trellis_requirement_when_manifest_opts_out`

## Legacy And Obsolete Artifact Advisories

Since pack 0.4.0 the installer performs no broad or heuristic legacy cleanup:
the `legacy-conflict` and `obsolete-conflict` install statuses no longer exist,
and install-time retirement is limited to the explicit `RETIRED_TARGETS`
footprints in `installer/removal.py`. Those targets are removed only when
provenance vouches for their current bytes (or the user passes `--force`);
drifted or unvouched files are preserved. Other cleanup responsibility lives in
the install audit, which emits advisory warnings (never failures) when known
legacy or obsolete artifacts remain in a consumer repo:

- legacy `trellis-*` and `sd-refresh-specs` adapter, skill, and script names
  replaced by their `sd-*` equivalents
- the pack rename family: `docs/TRELLIS_REVIEW_PR_PACK.md` replaced by
  `docs/SD_AI_COMMAND_PACK.md`, old generated `sd-command-pack-*` script
  filenames replaced by the canonical `sd-ai-command-pack-*` names, and the
  OpenCode nested `.opencode/commands/sd/` command layout replaced by flat
  `sd-<command>` files
- stale references to those legacy names inside repo docs, configs, and
  scripts (boundary-aware token scan; needles cover the `trellis-*` command
  names, `sd-refresh-specs`, the legacy env-var prefixes, the old
  `TRELLIS_REVIEW_PR_PACK.md` guide name, and each rename-era
  `sd-command-pack-*` script filename)

Generated `docs/repomix-map.md` aggregates are excluded from the reference
scan. Their source documentation is scanned directly, so scanning the generated
copy adds duplicate or self-referential warnings without expanding coverage.

Consumers remove advisory-only artifacts manually; the audit keeps warning
until they do, and the warnings never block an otherwise clean audit. Add an
automatic retirement only for a bounded, enumerated former pack footprint and
cover its provenance, force, dry-run, source-checkout, and removal behavior.

Reference files:

- `scripts/sd-ai-command-pack-install-audit.py`, `LEGACY_PACK_PATHS`
- `scripts/sd-ai-command-pack-install-audit.py`, `LEGACY_PACK_REFERENCES`
- `tests/test_install_audit.py`, `test_install_audit_warns_about_legacy_pack_names`
- `tests/test_install_audit.py`,
  `test_install_audit_warns_about_rename_era_legacy_paths`
- `tests/test_install_audit.py`,
  `test_install_audit_legacy_advisories_cover_all_pack_scripts`

## Scenario: Source-Checkout-Only Commands

### 1. Scope / Trigger

Use this contract when a command is useful to pack maintainers but depends on
operator files that are intentionally absent from consumer repositories.

### 2. Signatures

- `COMMAND_NAMES: tuple[tuple[str, str], ...]` remains the complete source
  command catalog used by command-surface generation.
- `SOURCE_ONLY_COMMAND_NAMES: frozenset[str]` declares the catalog names that
  must not be added to the consumer manifest.
- `SOURCE_ONLY_COMMAND_TARGETS: tuple[str, ...]` enumerates the former consumer
  footprint that refreshes may retire.

### 3. Contracts

- `make generate` writes source templates/adapters for every `COMMAND_NAMES`
  row, but adds derived manifest entries only when the name is not source-only.
- Command-shape recognition still covers every catalog row so regeneration
  removes stale manifest entries for newly source-only commands.
- Consumer refreshes retire vouched source-only target copies. Drifted or
  unvouched copies remain preserved unless `--force` is explicit.
- A self-install whose target resolves to `ROOT` skips source-only retirement,
  preserving the pack checkout's generated command surfaces.
- The install audit allows those target paths only when all
  `SOURCE_REPO_MARKERS` prove the checkout is the pack source repository.

### 4. Validation & Error Matrix

- Source-only name absent from `COMMAND_NAMES` -> import-time `RuntimeError`
  from `validate_source_only_command_names()` naming the unknown command.
- Source-only target present in a consumer manifest -> parity/drift test
  failure.
- Vouched former target in a consumer -> `retired` during refresh.
- Drifted former target without force -> `retired-preserved`.
- Source-only root copy in the pack checkout -> preserved and accepted by the
  source audit.
- Any other unlisted pack-like source file -> install-audit failure.

### 5. Good / Base / Bad Cases

- Good: `sd-fleet-refresh` remains invocable in this checkout and disappears
  from a refreshed consumer's receipts, provenance, and filesystem.
- Base: a fresh consumer install never receives the command.
- Bad: filtering `COMMAND_NAMES` itself, which would stop source adapter
  generation and leave the operator command stale.

### 6. Tests Required

- Generator/parity: source templates and root surfaces exist while all
  source-only targets are absent from `manifest.json`.
- Retirement: exact former footprints are unique, consumer copies retire, and
  source-root copies remain.
- Drift/audit: tracked templates equal manifest sources plus declared
  source-only templates; source-only audit allowances equal the retirement
  footprint and apply only in a verified source checkout.
- Documentation: consumer command inventories omit the source-only command and
  the operator section labels it source-checkout-only.

### 7. Wrong vs Correct

```text
Wrong: ship the sd-fleet-refresh skill while omitting docs/FLEET_ROLLOUT.md
Wrong: delete sd-fleet-refresh from COMMAND_NAMES and hand-maintain root copies
Correct: generate it from COMMAND_NAMES, exclude it via SOURCE_ONLY_COMMAND_NAMES,
         retire vouched consumer copies, and preserve the verified source checkout
```

## Source Checkout Dogfood Drift Gates

The `sd-ai-command-pack` source checkout dogfoods installed pack payloads at
the repository root. For every platform directory that exists in this source
repo, every non-managed-block manifest target for that platform must also exist
at the root and byte-match its manifest source. Shared manifest targets are
always required. This catches missing installed twins, not only content drift in
twins that happen to be present.

The full-check must establish source identity before running these SD-specific
assumptions. `install.py`, `manifest.json`, and `templates/` identify only an
installer-repo candidate. The parsed root manifest is authoritative: its name
must equal `sd-ai-command-pack`, its version must be a non-empty string, and its
files field must be a list. Valid manifests for other packs skip the gate. A
malformed manifest that textually asserts the SD identity, or a parsed SD
manifest missing those required fields, fails with a controlled diagnostic.
The source-hook advisory must reuse the same classifier.

Keep these checks in the pack-source drift tests:

- The dogfood target set is derived from `manifest.json`, `PLATFORM_REGISTRY`,
  and root platform directories; do not maintain a hand-written allowlist.
- Missing dogfood targets fail before comparison, so adding a command to
  `templates/` plus `manifest.json` requires refreshing the root installed copy
  with `install.py . --force --platform <platform>`.
- `git ls-files templates` must equal manifest sources plus the templates for
  registry-declared source-only commands. No other orphaned template files are
  allowed, and every manifest source must remain tracked.
- Manifest targets must be unique under `casefold()` to avoid collisions on
  case-insensitive filesystems.
- Source-checkout install state such as `.sd-ai-command-pack/provenance.json`
  and `.sd-ai-command-pack/installed-targets.txt` remains local/ignored here;
  consumer repos should track normal install state unless they use
  `--local-only`.

Reference files:

- `tests/test_pack_drift.py`,
  `test_tracked_pack_targets_match_templates`
- `tests/test_pack_drift.py`,
  `test_dogfood_drift_gate_detects_missing_existing_platform_targets`
- `tests/test_pack_drift.py`,
  `test_tracked_template_sources_match_manifest_sources`
- `tests/test_pack_drift.py`, `test_manifest_targets_are_casefold_unique`

## Anti-Patterns

- Do not infer installable files by scanning `templates/`.
- Do not hard-code new template paths only in Python.
- Do not preserve mutable installer state between runs.
- Do not overwrite user files without `--force`.
- Do not overwrite `.prism/rules.json` even with `--force`; users commonly tune
  Prism rules per repo after the initial install.
- Do not run repo-wide validation that reports unrelated target work as an
  installer failure.
