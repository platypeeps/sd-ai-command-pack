# Fix SD pack source-drift identity detection

## Goal

Ensure SD-only source-drift checks run only in the canonical
`sd-ai-command-pack` source repository and cannot produce SD environment-variable
failures in another installer repository such as `se-ai-command-pack`.

## Background

- Commit `7e97f71` already introduced the canonical manifest-identity classifier
  in both full-check script twins and shipped it in pack version `0.16.1`.
- Current `main` is `0.16.2`; the template and installed script twins are
  byte-identical.
- The local `se-ai-command-pack` checkout is still provenance-managed by pack
  version `0.15.6`, which predates the fix. Its stale installed script explains
  the reported false `0 in skills` failures.
- Existing tests cover true SD identity, SE identity skipping, malformed
  asserted SD identity, and invalid required SD manifest fields.

## Requirements

1. Preserve the root-manifest identity classifier in
   `templates/scripts/sd-ai-command-pack-full-check.sh` and its synchronized
   `scripts/` twin.
2. Preserve `templates/.agents/skills/*/SKILL.md` as the SD source checkout's
   environment-variable scan path.
3. Strengthen the SE-shaped regression test so it explicitly proves the drift
   body never runs: no environment-variable count and no stale documented
   environment-variable diagnostic may appear.
4. Keep malformed manifests that assert `sd-ai-command-pack` conservative and
   failing; valid manifests for other pack names must skip cleanly.
5. Do not manually modify provenance-managed files in `se-ai-command-pack`.
   Consumer remediation is a normal installer/fleet refresh from pack
   `0.16.1` or newer.
6. Do not bump the manifest or changelog for a test-only clarification. If
   validation reveals that shipped payload must change, follow the release
   ledger and candidate-validation rules before completion.

## Acceptance Criteria

- [x] An SD-shaped fixture runs the source-drift body and reports template twin
      comparisons.
- [x] An SE-shaped fixture with `install.py`, `manifest.json`, and `templates/`
      skips the SD-specific body based on `name: se-ai-command-pack`.
- [x] The SE-shaped fixture emits neither `env vars checked:` nor a stale
      documented environment-variable error, including the prior `0 in skills`
      symptom.
- [x] A malformed manifest that textually asserts the SD identity still fails
      with a controlled diagnostic.
- [x] The canonical template and installed full-check scripts remain
      byte-identical.
- [x] Focused pack-drift tests and the repository full-check pass.
- [x] No provenance-managed file in `se-ai-command-pack` is edited.

## Validation

- `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest tests.test_pack_drift`
  passed 24 tests.
- `cmp -s templates/scripts/sd-ai-command-pack-full-check.sh scripts/sd-ai-command-pack-full-check.sh`
  passed.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh`
  passed, including 129 template twins and environment-variable coverage of 70
  script variables, 35 skill variables, and 79 documented variables.
- The local SE checkout was inspected read-only and remains on installed pack
  `0.15.6`; no consumer file was modified.

## Out Of Scope

- Replacing the SD source scan path with `.agents/skills`.
- Refreshing or committing the consumer checkout as part of this source task.
- Reworking unrelated source-drift, release, or environment-variable policy.
