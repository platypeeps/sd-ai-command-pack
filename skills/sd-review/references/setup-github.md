# Routing workflow installation

Read this only when the operator requests CI routing installation or drift verification.

`sd-review setup-github` installs the routing workflow and its Dependabot guard.
The paths are `.github/workflows/sd-review-route.yml` and `.github/dependabot.yml`.
The workflow holds `contents: read`.
It reports the pull request's routing plan in check output and the job summary.
It requests no reviewer, posts no comment, and cannot approve a merge.

## Refusals

- Modes `minimal` and `guest` cannot install this workflow (R10-D5).
  Do not create it manually to bypass that restriction.
- A legacy sd-github-review footprint requires `--remove-legacy`.
  Avoid running two routers for the same change.
- A dirty pack checkout cannot pin itself.
  An explicit `--pin SHA` selects another commit deliberately.
- Differing workflow or guard contents require `--force`.
  Inspect the diff and authorization before replacing them.

## Dependabot guard

The workflow pins executable pack code by commit.
Updating that pin changes behavior, not merely a version label.
Run the installer; do not reproduce the guard manually.
Its maintained template is `GUARD_LINES` in `bin/sd_setup_guard.py`.

For eligible full-mode consumers, an absent Dependabot file gains a minimal weekly github-actions configuration.
Its open-pull-request limit is five.
For existing configuration, the installer updates only the relevant guard.
The line transformation preserves unrelated comments and entries.

The pack's own workflow uses `$/actions/review-route` without a pin.
Self-installation updates only the workflow and leaves Dependabot configuration unchanged.

## Drift checks

Run `sd-review setup-github --check`.
It compares rendered files against tracked content using the repository's existing pin, or an explicit `--pin`.
In full mode it prints `same <path>` or `DIFFERS <path>`, with a diff for changed content.
There, exit 1 means drift and exit 0 means no drift.
Outside full mode it prints `REMOVE <path>` or `absent <path>` instead, as below.
Exit 1 then means an unwanted lane, not template drift.
The check writes nothing and does not require policy approval.

The check applies the installer's mode guard to the mode the operator wrote.
In a written `guest` or `minimal` mode, a tracked workflow prints `REMOVE <path>` and exits 1.
A remote that lowers a written `full`, or cannot be asked, does not mark the lane for removal.
The check then prints a `note:` naming the demotion and compares the full-mode template.
With no tracked workflow, it prints `absent <path>` and exits 0.
Remove the lane with `sd-review setup-github --remove`, as below.

A repository whose `repo.ci` is `local` runs no GitHub Actions (sd:1843).
There the installer lays nothing and says why, and exits 0.
`--check` prints `absent <path>` and exits 0: absence is the target, not drift.
A tracked workflow prints `REMOVE <path>` and exits 1.

A pin behind pack HEAD is not template drift.
Change a pin deliberately through `--pin <sha> --force`, in its own reviewed commit.

Other flags: `--dry-run`, `--json`, and `--force`.
Dry-run prints planned writes without changing files.

## Removal

`sd-review setup-github --remove` deletes the routing workflow.
It also takes the review-route guard out of `.github/dependabot.yml`.
It works in every mode and under `repo.ci = local`.
Add `--dry-run` to print the plan and write nothing.

- A workflow edited beyond its pin needs `--force`.
- The guard stays while another workflow still pins `actions/review-route`.
- A `dependabot.yml` the installer created whole is deleted.
- In any other file, only the guard lines go, with an `ignore:` key they leave empty.
