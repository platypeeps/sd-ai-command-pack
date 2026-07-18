# Add canonical SD status command

## Goal

Add a read-only `sd-status` command that reports the current repository or the
entire declared fleet, and make housekeeping delegate its final-state report to
that same collector so the two surfaces cannot drift.

## Background

The housekeeping script currently owns Git final-state verification, open
PR/issue inventory, Trellis task inventory, and final report rendering. Those
facts are useful outside cleanup, but there is no direct command for obtaining
them. Fleet status is spread across local worktrees, installed pack receipts,
cached remote refs, GitHub metadata, and Trellis task files.

## Requirements

- Register and ship `sd-status` across the same adapters and installed skill
  roots as other general SD commands. Supported invocations include
  `sd-status`, `/sd:status`, and the positional mode `sd-status fleet`.
- Implement one canonical, read-only status collector. Local mode works in any
  installed consumer. Fleet mode resolves the canonical fleet manifest from an
  explicit argument, an environment override, a machine-local pack profile, or
  the source checkout, in that order.
- Keep fleet topology and rollout policy checked into the pack source. Ship the
  shared fleet parser to consumers, and use a machine-local profile only for
  locating the source manifest and overriding checkout paths on that machine.
- Add an explicit installer option that creates or updates the machine-local
  profile without making ordinary installation mutate user-global state.
- Local output must report repository identity, branch, working-tree state,
  cached upstream divergence and freshness, default branch, local/remote branch
  inventory, installed SD pack and Trellis versions, current/relevant PR,
  repo-wide open PR/issue summaries, the active Trellis task, highest-priority
  planned tasks, anomalies, and concise numbered next steps.
- Fleet output must inspect every declared local checkout in rollout-priority
  order and report path availability, branch, dirty state, cached upstream
  divergence, installed-versus-source pack version, open PR/issue counts when
  GitHub is available, and in-progress/planning Trellis task counts. It must
  provide an attention-first summary and numbered next steps.
- Human output is bounded and summary-first. Keep full structured detail
  available through `--json` schema version 1 rather than expanding prose.
- Status must not fetch, pull, switch branches, stage, commit, push, merge, or
  modify Trellis/GitHub state. Cached Git-ref comparisons must be labelled as
  cached unless the caller explicitly attests that refs were refreshed.
- Best-effort optional data must report `unavailable` or `not configured`
  visibly instead of silently disappearing. Expected tool/network absence does
  not make ordinary report mode fail.
- Ordinary local/fleet status exits zero after a valid report, even when it
  identifies work needing attention. Invalid usage or an unreadable requested
  repository fails. An internal `--expect-clean` mode exits nonzero for cleanup
  invariant failures and prior housekeeping anomalies.
- Housekeeping retains its mutation/action log and safety gate, then invokes
  the status collector for final Git verification, inventory, anomalies, and
  next-step candidates. It must no longer maintain a parallel final-state
  implementation.
- Preserve the current recognizable housekeeping sections and final-answer
  contract while improving the delegated report with explicit freshness,
  versions, current PR, and next-action evidence.
- Add focused tests for human/JSON local output, dirty/detached/diverged and
  unavailable-tool cases, strict cleanup expectations, fleet ordering and
  missing clones, no-write behavior, housekeeping delegation, generated
  adapter parity, install/remove, and script coverage.
- Treat this new shipped command as a minor release and regenerate full-fleet
  candidate evidence before publication.

## Recommended Report Improvements

- Lead with a one-line health summary instead of making users infer status from
  a long inventory.
- Distinguish facts from freshness: local files are live; remote divergence is
  cached unless housekeeping just fetched.
- Show only attention-worthy fleet rows in detail while retaining one compact
  row per member.
- Include installed Trellis/pack versions so update needs are visible without a
  separate audit.
- End with evidence-driven next steps ordered by blockers, active work, then
  highest-priority planned work.
- Offer stable JSON for dashboards and automation; do not make humans parse
  Markdown or shell prose.

## Out Of Scope

- Fetching or refreshing repositories as part of status collection.
- Merging PRs, changing issues, or mutating Trellis tasks.
- Running CI, full-check, Prism, Gito, installation audits, or fleet refreshes.
- Discovering repositories outside the source-owned fleet manifest.
- Moving fleet topology, rollout commands, or release policy out of version
  control and into a per-machine profile.
- Creating or modifying the machine-local profile during status collection.

## Acceptance Criteria

- [x] `sd-status` is registry-backed, generated, installed, documented, and
  discoverable through `sd-help` on all supported command adapters.
- [x] Local human and JSON reports contain the required bounded facts and do
  not modify the repository or external state.
- [x] `sd-status fleet` reports all declared fleet members in rollout order and
  clearly distinguishes missing clones, dirty trees, cached divergence, and
  pack-version drift.
- [x] Consumer invocation of `fleet` resolves the canonical manifest through
  the documented precedence and reports a concise setup remedy when no usable
  source or profile is configured.
- [x] A schema-versioned machine profile can locate the pack source and apply
  per-consumer path overrides while preserving checked-in rollout policy.
- [x] The shared fleet parser is installed and removed like other shipped
  scripts, and `install.py --configure-fleet` creates or updates the profile
  explicitly with dry-run and malformed-config coverage.
- [x] Housekeeping uses the status collector for final-state verification and
  contains no second Git/inventory report implementation.
- [x] Housekeeping's existing merge/cleanup safety behavior and recognizable
  output remain covered and passing.
- [x] Manifest version, changelog, generated adapters, root mirrors, docs,
  coverage floors, and candidate ledger are synchronized.
- [x] Focused tests, `make check`, deterministic full-check, and all seven
  disposable fleet candidate checks pass.

## Notes

- Parent task: `07-17-fleet-candidate-prepare`. Its implementation remains in
  the same unpublished working stream and is included in the eventual PR.
