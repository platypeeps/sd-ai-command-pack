# Retire the obsolete sd-check forwarders in anomaly-metric-creator

## Goal

`platypeeps/anomaly-metric-creator` carries five repo-owned files named
`scripts/sd-ai-command-pack-*`. They are not pack payload — they are forwarders
that resolve a same-named helper **by name on `PATH`** and `exec` it. They were
added on 2026-08-17 (`6b909d7`, "chore: restore the sd-check review-gate helper
forwarders") to work around a pack defect that no longer exists.

They now block the source repository: `install-audit` fails any
`sd-ai-command-pack-*` file in a consumer that is not listed in its
`.sd-ai-command-pack/installed-targets.txt`, so that consumer's lane in
`scripts/sd-ai-command-pack-fleet-candidate-check.py` fails, and a failed lane
means no ledger is written at all. `docs/fleet/candidate-validation.json` is
therefore stale for every subsequent payload change in `sd-ai-command-pack`,
and `make generate` / `make check` fail on `provenance.candidate-stale` until
it can be refreshed.

## Background: why the workaround is obsolete

The defect it worked around was real. `sd-check` resolved its five builtin
helper rows only at `<repo>/scripts/sd-ai-command-pack-<name>`, a thin install
places none of them there, so all five rows reported `unavailable` — and
`unavailable` outranks `passed` in `AGGREGATE_PRECEDENCE`, so `sd-check` could
never pass and `sd-review scope=pr` failed closed ahead of dispatch.

`sd-ai-command-pack` fixed it in `#482` (`c5673c3`, 2026-08-16 22:47Z):
`shipped_helper_path` in `scripts/sd-ai-command-pack-check.py` reads the
repository's own receipt and, when it is pinned thin, resolves the helper from
the machine install instead. `repo/scripts/` still wins everywhere else. The
consumer's commit landed 2026-08-17 04:09Z, after that fix shipped.

The forwarders are also the exact mechanism `08-17-plugin-path-version-split`
exists to remove: resolution by `PATH` means the answering install has nothing
to do with the pack the caller came from.

## Requirements

1. Delete the five forwarders from `platypeeps/anomaly-metric-creator`:
   `scripts/sd-ai-command-pack-install-audit.py`,
   `scripts/sd-ai-command-pack-pr-body-scope.py`,
   `scripts/sd-ai-command-pack-review-preflight.mjs`,
   `scripts/sd-ai-command-pack-review-scope.sh`,
   `scripts/sd-ai-command-pack-update-spec-kb.py`.
2. Remove what only existed to support them: their receipt entries in
   `.sd-ai-command-pack/installed-targets.txt`, `tests/test_sd_check_helper_forwarders.py`,
   the shared `scripts/_sd_pack_forward.py` glue if nothing else uses it, and
   the `check_scope_heading_mirrors.py` forwarder-recognition branch.
3. Confirm the pack the consumer is pinned to actually contains `#482` before
   deleting anything. If its pin predates that fix, the correct order is to
   refresh the pin first — deleting the forwarders against an older pack would
   restore the original review-gate failure.
4. The work happens in that repository, under its own review and merge gates.
   Never write into an existing consumer checkout from the source repository.

## Acceptance Criteria

- [ ] The five forwarders and their supporting glue, tests, and receipt entries
      are gone from `anomaly-metric-creator`'s default branch.
- [ ] `sd-check` passes there with all five builtin rows resolving from the
      machine install — measured, not assumed, and recorded with the row output.
- [ ] `scripts/sd-ai-command-pack-install-audit.py --repo <consumer>` exits zero
      against a fresh clone.
- [ ] `python3 scripts/sd-ai-command-pack-fleet-candidate-check.py` reaches
      all-pass from the `sd-ai-command-pack` source checkout and writes
      `docs/fleet/candidate-validation.json`.
- [ ] `make generate` in `sd-ai-command-pack` no longer reports
      `provenance.candidate-stale`.

## Notes

- Blocking evidence, from the run on 2026-08-17: eight lanes passed; the ninth
  reported `install audit failed with exit 1` with one
  `error: pack-like file is not listed in installed targets:` line per
  forwarder. The runner refuses to write a partial ledger, so
  `docs/fleet/candidate-validation.json` was left untouched.
- Until this lands, every payload-changing pull request in
  `sd-ai-command-pack` carries one known-red `make check` finding.
