# Design — fleet status compares against the newest published release

## What the code actually does today

`collect_fleet` (`scripts/sd-ai-command-pack-status.py:3197-3313`) binds one
scalar, `target = resolution.target_version` (`:3214`), and uses it twice: as
`target_pack_version` for every consumer row (`:3245`) and as the comparison
basis in `fleet_step_records` (`:3294`, stale test at `:3026-3030`). It reaches
the JSON as `targetPackVersion` (`:3301`). `resolution.target_version` is the
pack checkout's `manifest.json` version in all three resolution paths
(`scripts/sd_ai_command_pack_fleet_lib.py:251, 268, 284`, via `_pack_identity`
at `:234-241`).

## D1 — The PRD's stated constraint is weaker than it looks, and that changes the shape

The PRD says status "currently makes no network call for the fleet target" and
warns against putting a network dependency into an offline-capable collector.
The first half is true; the conclusion does not follow, because fleet mode is
already a networked collector:

- `collect_fleet` takes `network: bool` (`:3201`) and threads it into every
  consumer's `collect_local` (`:3242`);
- `collect_github` (`:1944-1975`) is the gate, and with `network=False` it
  returns `{"status": "disabled", ...}` — a labeled sentinel, never an absent
  key and never a substituted value.

So `--no-network` already exists as the toggle, already reaches the right
function, and the repo already has the exact sentinel vocabulary requirement 3
asks for. **Decision: no new flag.** The release lookup rides the existing
`network` parameter and returns a labeled status object exactly as
`collect_github` does. Adding an opt-in flag would be a second switch for the
same axis, and an operator who ran `--no-network` expecting offline behavior
would be surprised by whichever one they forgot.

Rejected alternatives:

- **Cache the release on disk.** Status is read-only (criterion 3). A cache is
  a write. Ruled out by the acceptance criteria, not by taste.
- **Resolve it outside status entirely** (e.g. only in `fleet-preflight`). That
  is the status quo and is what filed this task: preflight already knows about
  releases, and status — the thing an operator reads to decide whether the
  fleet is healthy — does not.

## D2 — Source of truth: `git ls-remote --tags`, because this project publishes tags, not GitHub Releases

The obvious reading of "newest published release" is `gh release view`. It is
wrong here, and measurably so:

```
$ gh release view --repo platypeeps/sd-ai-command-pack --json tagName
release not found
$ gh release list --repo platypeeps/sd-ai-command-pack --limit 3
(empty)
$ git ls-remote --tags --refs origin | wc -l
218
```

**This repository has zero GitHub Releases.** Publication is an annotated tag
pushed by the `Auto-tag release` job (`.github/workflows/tests.yml:745-753`).
A `gh release view` implementation would return `unavailable` on every run
forever, and every test would have to fake the one condition that never holds.

**Decision: `git ls-remote --tags --refs <remote>`,** filtered to
`refs/tags/v<semver>`. This is what the project actually publishes, it is
read-only, and it needs no `gh` and no GitHub authentication — strictly fewer
failure modes than the `gh` path, not more. `gh-unavailable` therefore does not
appear in D5's status vocabulary.

`.github/scripts/release_identity.py:348-364` already reaches the remote this
way for a neighbouring question, so the transport is established.

`verify_release_identity` itself is deliberately **not** reused. It requires the
local tag to exist, to match the remote byte for byte, and to be an ancestor of
HEAD (`release_identity.py:407-433`) — it raises on precisely the situation this
task exists to report, an operator whose checkout is not the newest release.

### D2a — "Newest" is a semver comparison; lexicographic max is wrong

`ls-remote` output is unordered and tag names sort lexicographically, where
`v0.9.2` is greater than `v0.71.8`. The checkout is at `0.71.8` and the tag list
contains both, so a `max()` over strings — or a `tail -1` over sorted output —
picks a version from a year ago and reports the fleet as ahead of a release it
is far behind. This is silent: the report is well-formed and wrong.

Parse each `v<major>.<minor>.<patch>` into an integer tuple and take the max of
those. Reject anything that does not match that exact shape rather than
coercing it, so a stray `v1.0-rc1` cannot participate in the ordering.

This does not conflict with D6. **Selecting** the newest tag requires ordering;
**comparing** it to the checkout stays equality.

## D3 — Which repository is asked, and where the remote comes from

`ls-remote` runs against the **pack source checkout**, not a consumer.
`resolution.pack_source` is bound on `FleetResolution`
(`sd_ai_command_pack_fleet_lib.py:118`) by every resolution path, so the pack
root is never re-derived from `__file__`.

The remote name is `origin`, matching `verify_release_identity`'s default
(`release_identity.py:399`) and `sd-status`'s `--remote` default (`:3424`).
No new configuration surface.

A checkout with no `origin`, or whose `ls-remote` fails, is `not-configured` and
`unavailable` respectively (D5) — mirroring `collect_github`'s vocabulary at
`:1959-1967`. Neither is an error: a pack checkout with no remote is a
legitimate offline configuration, and the fleet report must still render.

No slug parsing is needed. `github_slug_from_url` (`:184-199`) stays unused
here; it exists for the `gh` path this design rejected.

## D4 — Two targets, one comparison basis

Requirement 2 says both targets stay distinguishable and a reader must be able
to tell which comparison produced a stale row. The tempting reading is
per-consumer dual comparison — every row scored against both targets. Rejected:
it doubles every skew row, and `fleet_step_records` feeds `fleet_next_steps`
and `fleet_follow_ups`, so a consumer behind on both axes would emit two
next-step lines that an operator resolves with one action.

**Decision:** the checkout target remains the sole per-consumer comparison
basis. Consumer rows, `targetPackVersion`, and every existing skew row are
byte-identical to today. The release target is reported as a sibling fact and
produces **one** new fleet-level record when the checkout disagrees with it:
the operator's own checkout is not the published version.

This is the honest decomposition. "Consumer C is behind my checkout" and "my
checkout is behind the newest release" are different problems with different
fixes — refresh the consumer versus pull the pack — and the second is a
property of the operator, not of any consumer, so it belongs at fleet level
exactly once.

The reader can tell them apart because the new record names the release
version and the checkout version in the same sentence, and no consumer row
mentions the release target at all.

## D5 — Shape of the new field

```json
"releaseTarget": {
  "status": "available|disabled|not-configured|unavailable",
  "version": "0.71.8",
  "tag": "v0.71.8"
}
```

`version` is `null` for every non-`available` status. Three of the four
statuses are `collect_github`'s own vocabulary (`:1953`, `:1962`); `unavailable`
covers an `ls-remote` that ran and failed — unreachable remote, timeout, or a
remote with no `v<semver>` tags at all. There is no `gh-unavailable`: this path
never invokes `gh` (D2).

`releaseTarget` is a sibling of `targetPackVersion` at the top level, not nested
inside it, so an existing JSON reader that indexes `targetPackVersion` is
unaffected.

`tag` is carried alongside `version` because the ref is the published artifact
and the version is derived from it by stripping the leading `v`. Keeping both
means a malformed ref is visible rather than silently producing a wrong
`version`. A tag that does not match
`v<version>` yields `status: "unavailable"` with the raw tag retained.

## D6 — Comparison is string equality, not semver ordering

`fleet_step_records` compares versions with `!=` (`:3029`). The new record uses
the same test. Introducing ordering here would be a second, inconsistent
version-comparison policy in one function, and it is not needed: "checkout
differs from newest release" is the actionable fact whether the checkout is
behind or ahead, and an unreleased working copy — the PRD's second failure
case — is exactly the *ahead* direction that an ordering test would hide.

The record's wording must therefore say "differs from", not "is behind".

## D7 — Schema version stays at 2

`SCHEMA_VERSION` is `2` (`:31`). `releaseTarget` is purely additive: no
existing key changes name, type, or value, and `targetPackVersion` keeps its
current meaning. The precedent commit for this file (`450c0a95`) added fields
without bumping it.

Note the `fleet_step_records` docstring's "before schema 5" (`:3013-3016`) is
not this constant — no schema-5 value exists in the file. Leave the wording
alone; correcting it is unrelated scope, and this design does not rely on it.

## Risk

An operator behind a proxy, or on a checkout whose `origin` is unreachable,
gets `unavailable` on every run. That is noise if rendered as an anomaly.
Mitigation: the release target is rendered as a status line, and only the
`available`-and-differing case produces a next-step record. `unavailable` and
`not-configured` are reported, never counted as attention.

Second risk, specific to `ls-remote`: it is a network round trip inside a
collector that already spawns one subprocess tree per consumer. It runs
**once** per fleet run, outside the consumer thread pool, and inherits
`run_command`'s existing `COMMAND_TIMEOUT_SECONDS`; no new timeout constant is
introduced. A timeout is `unavailable`, not a hang.

## Rollout and rollback

Unlike the `fleet-*` family, this script is payload: it exists at four paths
that must stay byte-identical, confirmed by `git show --name-only 450c0a95`, the
last change to it —

- `templates/scripts/sd-ai-command-pack-status.py` (source)
- `scripts/sd-ai-command-pack-status.py`
- `plugins/sd/bin/sd-ai-command-pack-status.py`
- `plugins/sd/machine-payload/scripts/sd-ai-command-pack-status.py`

Edit the template, then run **both** generators: `make sync`
(`install.py . --force` plus the KB refresh, `Makefile:37-39`) writes
`scripts/`, and `make generate` (`Makefile:19-30`) writes the two
`plugins/sd/**` copies. Neither covers the other's paths.

`make generate` then fails its closing `surface-check` with
`provenance.candidate-stale`, because a changed payload has a new digest and
`docs/fleet/candidate-validation.json` still records the old one. Refresh it
with `scripts/sd-ai-command-pack-fleet-candidate-check.py` and commit it. That
is why the precedent commit touched that file.

Rollback is reverting the commit. Status writes nothing, so no consumer state
persists.
