# Pack paper cuts: write_json newline, set-meta floor, cache-env allowlist

Batch task for three small, independent fixes relayed from consumer evidence.
Each is under an hour; batching avoids three lifecycle rounds. If any one
grows past that, split it out rather than stretching this task.

## 1. Trellis write_json trailing newline (issue #413)

`.trellis/scripts/common/io.py` `write_json` omits the trailing newline that
`active_task.py` appends, so the same `task.json` has two byte
representations depending on the last writer, and hand-corrections revert
within a day. Fix: append `"\n"` in `write_json`, matching
`active_task.py`. This is vendored Trellis code — apply in the pack's
vendored copy and relay upstream per the vendored-artifact route; no bulk
rewrite of existing files.

## 2. set-meta diagnostic states no Trellis version floor (issue #410)

`validateTrellisRootTaskBaseBranch`'s diagnostic recommends
`task.py set-meta` unconditionally; the command exists only from Trellis
v0.6.9. On 0.6.7/0.6.8 the recommended escape hatch is unreachable. Fix
(issue's shape 2, smallest): the diagnostic names the floor — "requires
Trellis >= v0.6.9; upgrade or set the base branch before deletion" — either
statically or by reading `.trellis/.version` when present.

## 3. cache-env consumers enforce membership again (issue #398)

Since A-080, `toolchain.sh` and `shell-lib.sh` export any all-caps pair the
cache-env emitter prints — shape-validated, membership-unchecked. Restore
membership enforcement without losing the single-authority property: the
consumers obtain the current key set from the library at runtime (a
`cache-env --keys` mode or a leading `KEYS=` line) and reject names outside
it. Adding a cache variable still requires no shell edit; unexpected names
fail loudly.

## Acceptance Criteria

- [ ] `write_json` output ends with a newline; a test covers one mutating
      `task.py` command round-trip.
- [ ] The base-branch exemption diagnostic states the v0.6.9 floor; a test
      asserts the message content.
- [ ] Both shell consumers reject a cache-env pair whose name is outside the
      emitted key set, proven by a test injecting a foreign name.
- [ ] Issues #413, #410, and #398 are closed by the shipping PR.
