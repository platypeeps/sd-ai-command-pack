# Design: installer module decomposition

## Shape

`install.py` stays the executable entry point (`python3 install.py <target>`
from any cwd, including other repos pointing at this checkout). Implementation
moves into a sibling `installer/` package. Direct script execution puts the
script's directory on `sys.path[0]`, so `import installer.<module>` resolves
without installation, satisfying the PRD's fresh-clone constraint.

## Modules and one-way dependency order

1. `installer/registry.py` — foundation, no intra-package imports. `ROOT`,
   `PlatformInfo`, `PLATFORM_REGISTRY`, the derived per-platform tables and
   order tuples, and every pack-wide constant (receipt/provenance paths,
   gitignore block markers and pattern groups, copilot managed-block markers,
   install-mode names, force-preserved targets, Trellis docs URL).
2. `installer/manifest.py` — `PackFile`, manifest load/validation, path
   safety (`validate_relative_manifest_path`, `validate_pack_source`,
   `validate_resolved_target_path`, `target_destination`,
   `removal_target_destination`), strict readers, `system_exit_detail`,
   `manifest_cli_identity`.
3. `installer/fileops.py` — `InstallResult`, atomic writes and file modes,
   backup/unlink/prune helpers, `install_file`, managed-block and gitignore
   merge/install/remove, platform detection (`has_active_trellis_platform`)
   and `selected_files`.
4. `installer/provenance.py` — receipt and provenance content, vouching
   rules (`PROVENANCE_EXCLUDED_KINDS`, `never_vouched_targets`), readers for
   install and remove flows, `preserved_receipt_targets`, gitignore-aware
   receipt policy, the receipt/provenance installers.
5. `installer/localonly.py` — `LocalOnlyResult`, git helpers for the
   local-only flow, Trellis init composition, exclude-block management,
   tracked-path rejection, marker writer, and local-only removal.
6. `installer/removal.py` — `RemoveResult`, removal candidacy/safety
   (`may_remove_pack_file`), `remove_pack_file`, `remove_installed_pack`.
7. `install.py` (thin) — argparse (`parse_args`, `ManifestVersionAction`),
   target/Trellis preconditions, `run_diff_check`, `display_path`, `main`,
   process exit; plus a re-export aggregator (`from installer.<module>
   import *` and the two underscore order tuples explicitly) so the existing
   test suite's `install.<name>` references keep working unchanged — the
   PRD's no-test-churn requirement.

## Behavior contract

Purely mechanical movement: no function bodies change. The suite (310 tests)
must pass without edits other than infrastructure config:

- `.coveragerc` `include` widens to `install.py` + `installer/*` so the 100%
  gate covers the moved code instead of silently shrinking to the thin entry.
- CI bandit target list gains `installer`.

## Verification plan

Extract in dependency order, running the full suite after each module lands.
Finish with the coverage battery (`--fail-under=100` across entry + package),
full-check (KB refreshed — this design.md is a KB source), and shellcheck via
the security lane.

## Explicitly out of scope

Behavioral changes of any kind; manifest schema changes (the registry's
manifest-section variant stays deferred); moving `main` out of install.py
(the PRD wants CLI parsing and exit handling to stay in the entry file).
