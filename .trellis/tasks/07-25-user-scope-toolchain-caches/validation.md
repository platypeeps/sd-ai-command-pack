# Validation — user-scope toolchain caches

Package 7 of the single-merge stabilization umbrella
(`07-28-stabilize-self-hosted-delivery-lifecycle`).

## Disposition

The security defect this task targets — a co-tenant pre-creating the toolchain
resolver's cache/tool directories and planting Python bytecode or tool binaries
executed under the victim's identity — is already remediated in code by the
COMPLETED predecessor `07-24-standardize-sandbox-safe-tool-cache-routing`
(streamline program H06), which centralized all cache/env routing into
`build_tool_environment` in `scripts/sd_ai_command_pack_lib.py`. That code is present
unchanged in `origin/main` (`git diff origin/main -- .../sd_ai_command_pack_lib.py`
is empty). The PRD's cited defect site (`configure_cache_defaults`,
`prepare_gito_uv_env`, the unqualified `${TMPDIR:-/tmp}/sd-ai-command-pack-*`
directory pattern) no longer exists — H06 replaced it. Every surviving
`${TMPDIR:-/tmp}/sd-ai-command-pack-*` reference in the tree is a `mktemp`
random-suffix template, which is not a pre-creatable named path.

This package therefore does not re-route or re-implement (per the PRD
reconciliation note). It closes the two residual gaps on top of H06:
acceptance-criteria regression coverage that was not explicitly pinned, and an
explicit fleet-facing security guarantee in the docs.

## Acceptance criteria mapping

- [x] **All cache/tool paths contain the UID; fresh creation is 0700.**
  - UID embed: `_cache_namespace_name` returns
    `sd-ai-command-pack-{uid}-{digest}`
    (`scripts/sd_ai_command_pack_lib.py:167-170`); every one of the seven cache
    classes in `CACHE_ENV_KEYS` (incl. `PYTHONPYCACHEPREFIX` bytecode,
    `UV_TOOL_DIR` tool binaries, `RUFF_CACHE_DIR`) is created beneath that
    namespace (`build_tool_environment:270-291`).
  - 0700 fresh creation: `_ensure_private_directory` and `_prepare_namespace`
    both `mkdir(mode=0o700, ...)` (`:149`, `:176`) and reject any mode that
    grants group/other access (`:158-161`).
  - Newly pinned by `test_tool_environment_namespace_path_embeds_current_uid`
    (asserts the current UID appears in the namespace name and in every default
    per-tool cache path). The pre-existing
    `test_tool_environment_routes_cache_classes_and_preserves_credentials`
    already pins the 0700 mode of the namespace and every cache path.

- [x] **Foreign-owned pre-existing path is rejected, not used.**
  - `_ensure_private_directory` rejects a path whose `st_uid` differs from the
    current user's with `"{label} is not owned by the current user"`
    (`:155-157`), on the POSIX path only.
  - Newly pinned by `test_ensure_private_directory_rejects_foreign_owned_path`
    (unit branch coverage) and
    `test_tool_environment_rejects_foreign_owned_namespace` (end-to-end: a
    pre-created 0700 namespace whose owner differs from the resolving user is
    rejected before any tool runs). The prior suite covered only the
    permission-bit branch (`chmod 0o755`), not the ownership branch.

- [x] **Docs updated** (changelog + version + fleet rollout deferred — see below).
  - `templates/docs/SD_AI_COMMAND_PACK.md` (root mirror byte-identical via
    `make sync`) now states explicitly that the private namespace embeds the
    current user's UID, is created mode 0700, and that relative,
    repository-contained, symlinked, non-directory, non-private, **or
    foreign-owned** overrides and namespaces fail before the external tool runs,
    naming the co-tenant plant-and-execute threat. The prior text described a
    "per-user private namespace" but did not state the UID-embedding, 0700, or
    foreign-owner-rejection guarantees, and the PRD's premise that the docs
    "bless the unqualified pattern" was already stale after H06.

## Deferred to cumulative integration (campaign plan)

Version bump, changelog entry, and fleet rollout are handled once at the
umbrella's cumulative integration / release-preparation step and the post-STOP
fleet boundary, not per package — consistent with Packages 1–6. No consumer is
touched here.

## Checks

- `tests.test_script_lib` — 27 tests (24 existing + 3 new) green.
- `tests.test_generated_parity` + `tests.test_pack_drift` — 56 green.
- `ruff check tests/test_script_lib.py` — clean.
- `make sync` — `conflicts: none`; `templates/docs/SD_AI_COMMAND_PACK.md` and
  `docs/SD_AI_COMMAND_PACK.md` byte-identical.
- No change to `sd_ai_command_pack_lib.py` (already correct in `origin/main`);
  the candidate-ledger `payloadDigest` stays deferred to release preparation.
