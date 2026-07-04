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

`install.py` converts each manifest entry into a frozen `PackFile` in
`load_manifest()`. When adding a file, update `manifest.json` first and keep
Python logic generic unless the install semantics really change.

Reference files:

- `manifest.json`
- `install.py`, `PackFile`
- `install.py`, `load_manifest()`

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

- `install.py`, `validate_manifest()`
- `install.py`, `validate_relative_manifest_path()`
- `install.py`, `validate_pack_source()`
- `tests/test_install.py`, `test_manifest_rejects_unsafe_target_paths`
- `tests/test_install.py`, `test_manifest_rejects_unsafe_anchor_paths`
- `tests/test_install.py`, `test_manifest_rejects_unsafe_source_paths`

## Target Validation

The installer requires `.trellis/config.yaml` in the target repository before
copying files. Keep that validation early in `main()` through
`require_trellis_repo()` so invalid targets fail before side effects.

Reference file:

- `install.py`, `require_trellis_repo()`

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

- `install.py`, `selected_files()`
- `tests/test_install.py`, `test_installs_shared_skill_and_existing_platform_adapters`

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

## Provenance

Every non-dry-run install writes `.sd-ai-command-pack/provenance.json`:
pack name, version, and a sorted map of vouched targets to `sha256:` hashes
of the installed content (hashes are computed from the template source, so
dry-run and real runs agree). Never vouched: `FORCE_PRESERVED_TARGETS`
(user-tunable), managed-block targets (shared ownership), generated files
(receipt, gitignore block, provenance itself), and conflict results.
Entries survive for targets still recorded in the receipt so filtered runs
do not shrink coverage. The audit verifies present vouched files and fails
on content drift, naming the recorded pack version; missing files defer to
the structural checks, and a malformed provenance file is a failure.
Absent provenance (pre-0.5.10 installs) keeps the older audit behavior.

Reference files:

- `install.py`, `preserved_receipt_targets()`, `is_gitignored_path()`,
  `provenance_content()`, `install_provenance_file()`
- `templates/scripts/sd-ai-command-pack-install-audit.py`, `is_gitignored()`,
  `audit_provenance()`
- `tests/test_install.py`, `test_install_keeps_receipt_entries_for_gitignored_absent_anchor`
- `tests/test_install.py`, `test_install_audit_downgrades_gitignored_missing_targets`
- `tests/test_install.py`, `test_install_writes_provenance_with_hashed_targets`
- `tests/test_install.py`, `test_install_audit_warns_for_unlisted_gitignored_pack_files`

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
   `install.py` owns `FORCE_PRESERVED_TARGETS`,
   `REVIEW_ARTIFACT_GITIGNORE_PATTERNS`,
   `PLATFORM_LOCAL_GITIGNORE_PATTERNS`, and `trellis_gitignore_block()`.
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
   links by semantic category rather than source folder name, avoids generated
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

## Legacy Adapter Cleanup

When installing `sd` adapter files, remove old pack-generated `/trellis:*`
adapter files whose content still matches a known pack template variant. If a
legacy adapter path exists with other file content, report `legacy-conflict`
and leave it untouched unless `--force` is supplied. With `--force`, remove the
legacy file or symlink so the `sd` replacement becomes the only pack-owned
adapter. Do not introduce a separate keep status for legacy adapter files.
Validate the resolved parent directory before inspecting or unlinking legacy
adapter paths, but do not resolve the final path when it is a symlink slated for
conflict reporting or removal; unlinking the symlink itself is safe when its
parent remains inside the target repo.

Reference files:

- `install.py`, `install_file()`
- `tests/test_install.py`, `test_conflict_requires_force`
- `tests/test_install.py`, `test_dry_run_does_not_write_files`

## Obsolete Adapter Cleanup

When a pack-owned adapter path moves for platform-discovery reasons, remove the
old generated target if it still matches a known pack template variant. If the
old target contains custom content, report `obsolete-conflict` and leave it
untouched unless `--force` is supplied. This currently protects the OpenCode
move from nested `.opencode/commands/sd/<command>.md` files to flat
`.opencode/commands/sd-<command>.md` files, the pack rename from
`docs/TRELLIS_REVIEW_PR_PACK.md` to `docs/SD_AI_COMMAND_PACK.md`, and old
generated `sd-command-pack-*` script filenames replaced by the canonical
`sd-ai-command-pack-*` names.

## Anti-Patterns

- Do not infer installable files by scanning `templates/`.
- Do not hard-code new template paths only in Python.
- Do not preserve mutable installer state between runs.
- Do not overwrite user files without `--force`.
- Do not overwrite `.prism/rules.json` even with `--force`; users commonly tune
  Prism rules per repo after the initial install.
- Do not run repo-wide validation that reports unrelated target work as an
  installer failure.
