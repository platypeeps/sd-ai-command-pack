# Roll Out sd-ai-command-pack 0.8.5 To The Fleet Design

Use the pack's checked-in fleet manifest and preflight helper as the rollout
ledger source. The operator loop remains PR-based in each consumer repo; this
task should not create unattended automation.

For each consumer, run the printed install command from this pack checkout,
then immediately run the printed audit command from the same output. The
explicit platform list is required because the audit must catch missing
selected-platform targets even when a faulty install would also omit them from
receipt/provenance.

Record one ledger row per repo with: repo slug, local path, target version,
platforms, refresh PR, merge state, post-merge provenance version, audit result,
and the work-backlog Claude command verification for hoa-manager and
rwbp-coordinator.

Do not treat stale aliases as consumers. `green-button-manager` and
`trellis-review-pr-pack` are excluded by `docs/fleet/consumers.json`.
