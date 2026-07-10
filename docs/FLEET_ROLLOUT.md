# Fleet Rollout

This repository tracks the known sd-ai-command-pack consumer fleet in
`docs/fleet/consumers.json`. The manifest is operator-triggered inventory, not
an unattended rollout system.

## Preflight

Run the source-owned preflight before opening consumer refresh PRs:

```bash
python3 scripts/sd-ai-command-pack-fleet-preflight.py
```

The target version is read from `manifest.json`. Repos already at that version
are reported as `at-target` and should be skipped, which prevents duplicate
empty refresh PRs.

For each repo that needs a refresh, the preflight prints the exact install and
audit commands. The audit command passes the fleet manifest's explicit platform
set through `--expected-platform` so missing selected-platform files are caught
even when a faulty install also omitted them from receipts or provenance.

## Refresh Shape

For each `refresh-needed` repo:

1. Create a PR-only branch in that consumer repo.
2. Run the printed `python3 install.py <repo> --force --platform ...` command
   from this pack checkout.
3. Run the printed `python3 scripts/sd-ai-command-pack-install-audit.py --repo
   <repo> --expected-platform ...` command.
4. Commit, push, review, merge, and run housekeeping in the consumer repo.
5. Confirm post-merge provenance reads the target version and the audit passes.

Do not include stale aliases such as `green-button-manager` or historical
predecessors such as `trellis-review-pr-pack`; they are explicitly excluded in
the fleet manifest.
