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

Every path in this section is repo-qualified with the consumer's name, because
none of them live here. Four of the five forwarder basenames also exist in this
repository as genuine pack payload, so an unqualified `scripts/` path would name
this repo's file while meaning the consumer's — which is the exact confusion the
task is about.

1. Delete the five forwarders from `platypeeps/anomaly-metric-creator`:
   `anomaly-metric-creator/scripts/sd-ai-command-pack-install-audit.py`,
   `anomaly-metric-creator/scripts/sd-ai-command-pack-pr-body-scope.py`,
   `anomaly-metric-creator/scripts/sd-ai-command-pack-review-preflight.mjs`,
   `anomaly-metric-creator/scripts/sd-ai-command-pack-review-scope.sh`,
   `anomaly-metric-creator/scripts/sd-ai-command-pack-update-spec-kb.py`.
2. Remove what only existed to support them: their receipt entries in
   `anomaly-metric-creator/.sd-ai-command-pack/installed-targets.txt`,
   `anomaly-metric-creator/tests/test_sd_check_helper_forwarders.py`, the shared
   `anomaly-metric-creator/scripts/_sd_pack_forward.py` glue if nothing else
   uses it, and the `anomaly-metric-creator/docs/DEVELOPMENT_CYCLE.md` prose
   explaining why the forwarders exist.

   `anomaly-metric-creator/tools/check_scope_heading_mirrors.py`'s
   forwarder-recognition branch stays.
   Its test synthesizes a forwarder in a temporary directory rather than
   reading the repository's own, so it does not depend on these five files, and
   the branch is what stops a future repo-owned file at that path from being
   mistaken for the scope-guard authority. Deleting a live safeguard because
   its current example went away is not part of this cleanup.
3. Establish that the helpers the consumer actually executes carry `#482`
   before deleting anything.

   The pinned pack **version** does not decide this. `shipped_helper_path`
   gates on mode, not version — `pin_state(repo) != PIN_STATE_THIN` returns the
   vendored path, and anything else resolves through the machine install. So a
   thin consumer runs the machine install's helpers whatever its pin says, and
   this consumer's `0.71.22` pin is not evidence either way.

   Measured on 2026-08-17: `grep -c shipped_helper_path
   ~/.agents/bin/sd-ai-command-pack-check.py` is `2`, and calling
   `shipped_helper_path` against the consumer for all five names resolves every
   one of them to `~/.agents/bin/`, each `exists=True`. The forwarders are
   already bypassed; deleting them removes dead files rather than a live
   resolution path. Re-run that resolution before deleting if the machine
   install has changed since.
4. The work happens in that repository, under its own review and merge gates.
   Never write into an existing consumer checkout from the source repository.

## Acceptance Criteria

- [x] The five forwarders and their supporting glue, tests, and receipt entries
      are gone from `anomaly-metric-creator`'s default branch.
      Landed 2026-08-18 as that repository's PR #389, squash-merged to `main`
      at `334a49e`; 10 files changed, +27/-708.
- [x] The five builtin helper names resolve from the machine install there —
      measured, not assumed. Recorded in requirement 3 above: every name
      resolved under `$HOME/.agents/bin/` with `exists=True`, taken before the
      deletion so it proves the forwarders were already bypassed rather than
      proving only that the deletion did no visible harm.
- [x] `scripts/sd-ai-command-pack-install-audit.py --repo <consumer>` exits zero
      against a fresh clone.
      `SD AI command pack install audit passed: 31 targets checked.` — 31 where
      the pre-change receipt carried 36, the five removed entries being exactly
      the difference.
- [x] `python3 scripts/sd-ai-command-pack-fleet-candidate-check.py` reaches
      all-pass from the `sd-ai-command-pack` source checkout and writes
      `docs/fleet/candidate-validation.json`.
      `CANDIDATE_EXIT=0`, eight of eight consumers `passed`, ledger written at
      `packVersion 0.71.30` / `payloadDigest sha256:a5184b86`. The first
      all-pass run recorded `sha256:8f24dea7`; a later payload correction on the
      same branch changed the digest and the ledger was refreshed again, both
      times to all-pass. The digest is a property of the payload, not of this
      task, so the criterion is the all-pass ledger rather than any one value.
- [x] `make generate` in `sd-ai-command-pack` no longer reports
      `provenance.candidate-stale`.
      `shipped-surface closure: clean; 176 changed path(s), 1164 affected
      node(s)`.

## Notes

- Blocking evidence, from the run on 2026-08-17: eight lanes passed; the ninth
  reported `install audit failed with exit 1` with one
  `error: pack-like file is not listed in installed targets:` line per
  forwarder. The runner refuses to write a partial ledger, so
  `docs/fleet/candidate-validation.json` was left untouched.
- Auditing the consumer checkout as it stands **passes** —
  `SD AI command pack install audit passed: 36 targets checked.` — because the
  consumer's committed `installed-targets.txt` lists all five forwarders at
  lines 32-36. That is not a contradiction of the lane failure and does not
  mean the audit is inconsistent. The candidate lane installs the candidate
  version into a scratch clone first, which rewrites the receipt from the
  manifest; a thin install writes no `scripts/` targets, so on the next line
  the same five files are pack-like and unlisted. Reproducing the failure
  therefore requires the install step, not the audit alone.
- Until this lands, every payload-changing pull request in
  `sd-ai-command-pack` carries one known-red `make check` finding.
