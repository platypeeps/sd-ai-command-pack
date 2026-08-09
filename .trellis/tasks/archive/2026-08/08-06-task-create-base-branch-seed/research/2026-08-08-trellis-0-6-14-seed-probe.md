# Evidence: base_branch seed probe after Trellis 0.6.14 upgrade

Source: task 08-08-trellis-upgrade, branch `chore/trellis-upgrade-0-6-14`,
upgrade commit `d10d4e95` (vendored surface 0.6.7 → 0.6.14 via
`trellis update`).

Probe (2026-08-08): with `chore/trellis-upgrade-0-6-14` checked out,

```
python3 .trellis/scripts/task.py create "probe" --slug probe-base-branch-seed \
  --no-start --description "..." --assignee sdelmas
```

seeded `"base_branch": "main"` — the repository default — not the
checked-out feature branch. The probe directory was deleted immediately
after capture; the full captured `task.json` showed:

```
"branch": null,
"base_branch": "main",
```

Consequence for this task: the upstream >=0.6.8 fix (113cb5fb/9846fe66)
is live in this repository. The remaining scope here is the pack-side
hardening (description refusal and any seed policy beyond the upstream
default-branch resolution), not the seed defect itself — that is fixed by
the upgrade. Re-verify on any consumer repo only after it takes its own
Trellis upgrade.

## Fleet-consumer verification: parked (2026-08-08)

Consumers still run pre-0.6.8 vendored Trellis until their own upgrade, so
the seed fix cannot be observed there yet. Verification is parked per this
task's PRD "Adversarial review dispositions": trigger is each consumer's
Trellis upgrade to >=0.6.8 through the fleet refresh flow; re-run this
probe's create-on-feature-branch check there at that time.
