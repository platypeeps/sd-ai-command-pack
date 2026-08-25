# Handoff — 2026-08-25, before a Claude Code restart

The restart was needed because `claude plugin update` moved the `sd` plugin from
0.71.33 to 0.71.51 and reported "Restart to apply changes": the on-disk runner is
current but the session's loaded `sd-review` skill instructions were not.

## Shipped

Pack **0.71.51** — PR #541, merged. Five commits:

| | |
| --- | --- |
| `3d3d7731` | planning artifacts + adversarial review |
| `181933da` | the stage implementation |
| `07d508de` | the coordinator fix — the feature did not work without it |
| `11a045cd` | the stale gate-reason inventories |
| `3804cbae` | candidate ledger refresh |

Verified: 2720 tests 0 failures, ruff + mypy clean, `make check` complete,
candidate ledger 9/9 consumers.

Three guards were falsified rather than observed passing — family-evidence stays
closed (`FAILED (failures=1)`), branch order in `_disposition_counts`
(`FAILED (failures=4)`), controller forwarding (`FAILED (errors=1)`).

## In flight

- **sd-github-review PR #148** — adoption of 0.71.51. Manifest + provenance only;
  this repo installs no runner. Open, unmerged.
- **Release tag `v0.71.51`** had not cut when this was written; pack `main`'s Tests
  run was still in progress and auto-tag follows it. Latest tag was `v0.71.50`.
  Check `git tag --sort=-v:refname | head -1` before assuming a release exists.
- The other **eight consumers are deliberately not rolled yet**. Two integration
  defects surfaced today that a fully green stage suite did not catch, both at the
  coordinator/stage boundary. The replay is the first thing that exercises that
  boundary, so it runs against one repo before eight more see the release.

## The one open item: criterion 6

`sd-github-review` task `08-09-review-gate-advisory-convergence` is PARKED on
criterion 6 — the PR #70 replay reaching `remoteGate: eligible`.

**Do not treat the PRD's numbers as a fixture.** It records
`"advisory": 30, "dispositioned": 4, "outstanding": 3` from one run, and its own
history shows three replays returning 37, 35, and 27 findings against different
providers and models. Criterion 6 should be restated structurally before the
replay runs, or any result can be rationalised: *findings verified true and
deliberately accepted are dispositionable on the new ground and the gate reaches
`eligible`, with `remoteGate.reason == "local-findings-accepted"`.*

**No stored receipt survives** to redispose for free. The artifact roots were
transient. The replay is a live provider run: `prism-chunked` (1800s timeout) plus
`gito` (600s), roughly 50-82s and $0.04-$0.20 in prior runs.

**Acceptance is the operator's judgement, not the assistant's.** Verify each
blocking finding against the checkout and report which are true, which are
rebuttable, which are miscited — then the user decides which are accepted and with
what reason. That attribution is the entire safety case for the ground.

## Still open elsewhere

- Pack unstarted: `08-24-advisory-classification-per-finding`,
  `08-25-aggregate-outcome-masks-provider-failure`,
  `08-25-controller-ignores-remote-and-family-gate` (worth bumping — same
  controller that held two live defects today).
- Pack in_progress, predating today: `08-21-port-integration-only-profile`,
  `08-24-local-gate-advisory-severity`.
- `08-08-merge-commit-policy` unresolved.
- hoa-manager Dependabot: `~/.npmrc` `allow-scripts` vs npm 11. User decision.
  Unaffected by today's CLI install, which went in natively rather than via npm.

## Standing constraints

- Always a PR; no admin branch-protection override, including docs-only commits.
- `install.py --force` never against a consumer. `make sync` uses it for the pack's
  own dogfood install, which is a different thing.
- No changes pushed to `dshills/prism`; `upstream` push URL is literally DISABLED.
- `gh pr merge` is classifier-blocked for the assistant. The user runs merges.
