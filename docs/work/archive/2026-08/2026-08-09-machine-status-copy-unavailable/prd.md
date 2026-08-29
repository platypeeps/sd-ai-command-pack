---
title: Machine-payload status copy reports plugin version unavailable
status: done
created: 2026-08-09
branch: task/plugin-duplicate-registration-reconcile
---
# PRD: Benign duplicate plugin registrations block the machine update path

Child of `08-09-deployment-thin-consumers`.

> **Priority is recorded as P2 in `task.json` and is wrong.** Treat this as P1
> until the field can be corrected: `task.py` exposes no priority setter, and
> hand-editing `task.json` outside the tool is not something this task does on
> its own authority. The escalation reason is in "Why this is now P1" below.

## The original premise was refuted

This task was filed against a hypothesis that has since been measured false:

> "The status script copy shipped inside `machine-payload/scripts/` always
> reports plugin version `unavailable` when run from a machine install context
> where `claude plugin list` discovery differs from repo context."

There is no machine-versus-repo discovery difference. The failure reproduces
from an ordinary repository checkout, and the installed machine copy is
byte-identical to the source (`diff -q ~/.agents/bin/sd-ai-command-pack-status.py
scripts/sd-ai-command-pack-status.py` reports no difference). The real cause is
that both machine-scope entry points refuse *any* duplicate entry in
`claude plugin list --json`, including duplicates that agree on every field
that matters.

## Goal

Stop refusing benign duplicate plugin registrations. A listing that resolves to
one version and one install path is unambiguous; refusing it withholds a fact
the tool already has, and in the updater's case blocks the only refresh path
the fleet still has.

## Observed state (measured 2026-08-16)

`claude plugin list --json` on this machine returns three entries for
`sd@sd-ai-command-pack`:

| scope | projectPath | version | installPath |
| --- | --- | --- | --- |
| `user` | — | `0.71.22` | `.../plugins/cache/sd-ai-command-pack/sd/0.71.22` |
| `project` | `sd-github-review` | `0.71.22` | same |
| `project` | `anomaly-metric-creator` | `0.71.22` | same |

One distinct version, one distinct install path, all `enabled: true`. The two
project-scope rows carry `installedAt` of `2026-08-16T15:38`, so this shape is
a direct consequence of the thin migration installing the plugin per-project;
it is expected multiplicity, not a broken install.

Consequences today:

1. **`sd-status` cannot report machine currency.** `collect_plugin_version`
   returns `unavailable` at `scripts/sd-ai-command-pack-status.py:1726` purely
   on `len(matches) > 1`, and `machine_comparison`
   (`scripts/sd-ai-command-pack-status.py:1805`) turns any `unavailable` half
   into `comparison: "unknown"`. One machine inventory is collected per run, so
   every consumer row in a fleet report loses its machine-currency answer at
   once.

1a. **The skew alarm is disabled as a side effect.** The next-step generator at
   `scripts/sd-ai-command-pack-status.py:3200` fires only on
   `comparison == "skew"`. Because a duplicate listing forces `unknown` instead,
   a *genuine* disagreement between the plugin and the machine receipt would
   currently produce no next step at all. The refusal does not merely withhold
   an answer; it suppresses the warning that answer exists to raise.

2. **The machine updater refuses to run.** The same condition at
   `scripts/sd-ai-command-pack-pack-update.sh:145` raises `SystemExit(12)` on
   the following line, and `:158` fails with
   "resolve the duplicate install before updating." Replaying that exact
   resolver against the live listing exits `12`. Since the consumer-side
   scheduled refresh was retired, the operator-initiated machine update is the
   *only* refresh path, so this is a stuck fleet, not a cosmetic gap.

## Why this is now P1

The refusal is not merely wrong, it is unactionable. Its remediation text tells
the operator to resolve a duplicate install, but there is no duplicate install
to resolve: all three registrations point at one directory. Following the
instruction would mean uninstalling the plugin from a consumer project that
legitimately declares it. The tool asks for a fix that would be a regression.

## Requirements

1. Reconcile duplicate entries that agree rather than refusing them. Each call
   site reconciles only the field it actually consumes, which is not the same
   field in both:
   - `scripts/sd-ai-command-pack-status.py:1726` reads only `version`. When
     every matching entry carries the same version, that is the version.
   - `scripts/sd-ai-command-pack-pack-update.sh:145` reads only `installPath`.
     When every matching entry resolves to the same install path, that is the
     root.
   Disagreement on the field a site consumes stays a refusal — the existing
   docstring's reasoning ("A guess here would let a broken `claude` masquerade
   as an up-to-date machine", `scripts/sd-ai-command-pack-status.py:1699`) is
   correct for that case and must survive.
2. Apply the change at **both** call sites and nowhere else. They are
   independent implementations of the same rule, and a grep of `scripts/`,
   `install.py`, and `installer/` for `claude plugin list --json` returns no
   third reader, so the blast radius is exactly these two. The updater's
   exit-code contract is documented at
   `scripts/sd-ai-command-pack-pack-update.sh:20`.
   `scripts/sd-ai-command-pack-review.py:1297` also tests `len(matches) > 1` but
   is unrelated — it deduplicates routed-review receipts — and is out of scope.
3. Keep the exit-code contract meaningful. Exit `12` should still exist for a
   genuine conflict; decide in design whether its documented description at
   `:20` needs rewording once benign duplicates no longer reach it.
4. Update the tests that currently assert the refusal, and add coverage for the
   agreeing-duplicate case:
   - `tests/test_status.py:3219` supplies a `"plugin duplicated"` case whose two
     entries carry *different* versions (`9.9.9` and `9.9.8`); that case is
     still correct and must keep asserting refusal.
   - `tests/test_pack_update.py:320` `test_duplicate_entries_are_refused`
     duplicates the identical entry (`dict(listing[-1])`), which is exactly the
     benign shape now occurring in production. That assertion inverts.
5. Propagate through the generated surfaces. The rule is mirrored in
   `templates/scripts/`, the root mirror `scripts/`, `plugins/sd/bin/`, and
   `plugins/sd/machine-payload/scripts/`. A `templates/**` change also requires
   a `manifest.json` bump and a matching top `CHANGELOG.md` heading, because
   `make check` does not run the release payload gate.

## Acceptance criteria

- [x] With the live three-entry listing, `sd-status fleet --json` reports a real
      `machineScope.pluginVersion` and a `comparison` that is not `unknown`. The
      before and after JSON are both recorded. Both halves read `0.71.22` today,
      so `current` is the expected value; the criterion is written as "not
      `unknown`" because the receipt half is independent of this fix and a
      truthful `skew` would also satisfy it.
- [x] `collect_machine_scope`, run against a duplicate-but-agreeing listing and
      a receipt that disagrees, returns `comparison: "skew"` — proving the alarm
      at `scripts/sd-ai-command-pack-status.py:3200` is reachable from a real
      machine again. The existing row tests inject that comparison through a
      fixture, so the seam this criterion covers is `collect_machine_scope`
      itself.
- [x] Replaying the `pack-update.sh` resolver against the same listing exits
      `0` and prints the single install path, where it previously exited `12`.
- [x] A listing whose matching entries disagree on version still reports
      `unavailable`, and the updater still exits `12`. Proven by test, not by
      reading the diff.
- [x] The claim that the machine copy is byte-identical to the source is
      re-measured at implementation time rather than trusted from this record.
- [x] Every one of the four mirrored copies carries the change, enumerated by
      re-running the `len(matches) > 1` grep across the tree and confirming no
      stale copy remains.
- [x] `make check` and `make release-prep` pass.

## Evidence recorded at completion

Measured 2026-08-16 on the developer machine that reproduced the failure, at
branch `task/plugin-duplicate-registration-reconcile`.

| criterion | evidence |
| --- | --- |
| 1 | before: `pluginVersion: unavailable`, `pluginDetail: "...more than once"`, `comparison: unknown`. After: `pluginVersion: 0.71.22`, `pluginDetail: null`, `comparison: skew`. Live listing: 3 entries, 1 distinct version, 1 distinct `installPath` |
| 2 | `tests/test_status.py` `test_agreeing_duplicate_entries_still_reach_a_skew_verdict` — agreeing listing plus a disagreeing receipt, computed through `collect_machine_scope`, not injected |
| 3 | same resolver extraction replayed against the same captured listing: exit `12` at `HEAD`, exit `0` with one path after |
| 4 | `test_conflicting_install_paths_are_refused` (exit `12`, both paths named) and the `"plugin listed at conflicting versions"` row of the discovery-failure table |
| 5 | `diff -q` of both `~/.agents/bin/` copies against `scripts/` at Step 0: no difference, so the installed copies carried the bug |
| 6 | enumerated from the filesystem, not from the edit list: all four `status.py` copies and all four `pack-update.sh` copies carry the reconciliation; zero carry the old refusal |
| 7 | `make check` exit `0`, `make release-prep` exit `0` |

`comparison` reads `skew` rather than `current` because the machine receipt is
at `0.71.26` while the plugin cache is at `0.71.22`. That is a real machine
divergence this bug was suppressing, and the criterion was written to accept it.

Two records in `implement.md` were stale by the time it ran: the manifest was
at `0.71.26`, not `0.71.22` (bumped to `0.71.27` here), and the pre-change
`len(matches) > 1` count was 10 rather than 12, because two of the twelve sites
were the source files already edited when the count was taken. The post-change
count of four is as predicted.

One defect escaped local validation and was caught by the macOS CI leg: an
apostrophe in a comment inside a `$( ... )` command substitution, which bash
3.2 mis-scans as an unterminated quote. Fixed in `09c21bd1`; the gotcha and a
local reproduction sweep are recorded in
`.trellis/spec/backend/quality-guidelines.md`.
