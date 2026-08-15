# Fleet status: compare against the newest published release

Filed 2026-08-10 from `08-09-thin-fleet-status-pins` (PR #416), which recorded
it explicitly as out of scope.

## Problem

The fleet "target pack version" is the **resolved pack checkout's**
`manifest.json` version — `_pack_identity` returns `manifest_version`
(`scripts/sd_ai_command_pack_fleet_lib.py:192-200`) and every resolution sets
`target_version=version` (`:251, 268, 284`). There is no GitHub release lookup
anywhere in the fleet library.

That makes "stale" mean *behind the operator's local checkout*, which is not
the same as *behind the newest published release*. An operator on an old
checkout sees a healthy-looking fleet; an operator on an unreleased working
copy sees the whole fleet flagged stale against a version nobody can install.

## Requirements

1. Fleet mode can compare consumer versions against the newest published
   `sd-ai-command-pack` release, not only the resolved checkout's manifest.
2. Both targets stay distinguishable in the report; a reader must be able to
   tell which comparison produced a stale row.
3. A release lookup that does not produce a version is **labeled with the
   reason it did not**, never silently downgraded to the checkout target and
   never rendered as agreement.

   Filed as "labeled `unavailable`". Design D5 splits that into the vocabulary
   `collect_github` already uses — `disabled` when `--no-network` suppressed
   the lookup, `not-configured` when the pack checkout has no remote,
   `unavailable` when the lookup ran and failed. The requirement is the
   labeling; one word versus three was incidental, and three tell an operator
   which fix applies.

## Constraint that makes this non-trivial

`sd-status` is strictly read-only *and* currently makes no network call for the
fleet target; `--no-network` must keep working. Adding a release lookup puts a
network dependency into a collector whose contract is "read-only, works
offline". Decide deliberately whether it is opt-in (a flag), cached, or
resolved outside status entirely — do not just add a call.

## Acceptance criteria

- [x] The release target is available and clearly distinguished from the
      checkout target in both JSON and human output.

      `releaseTarget` is a top-level sibling of `targetPackVersion`, never
      nested in it, and `render_fleet` prints its own `Release target:` line.
      Proven by `test_release_target_reports_the_newest_tag` and
      `test_fleet_report_keeps_every_key_when_the_release_is_unavailable`.

- [x] `--no-network` still produces a complete report, with the release target
      explicitly labeled (`disabled`) rather than absent or silently
      substituted, and with no subprocess spawned for the lookup.

      `test_release_target_is_disabled_without_network` asserts the status is
      `disabled` and `run_command.call_count == 0`, so the no-subprocess clause
      is checked, not assumed.

- [x] Status remains read-only: no fetch, install, or write is added.

      `test_release_target_issues_only_read_only_commands` captures every argv
      `run_command` receives and asserts the set is exactly
      `git remote get-url origin` and `git ls-remote --tags --refs origin`. An
      argv assertion, so a later edit slipping in `git fetch` fails the test.
