# Fleet registry

> [!important]
> **Stale as of 2026-09-01.** Both files in this directory describe a fleet of
> consumer checkouts that the pack no longer walks, and a payload it no longer
> ships. This notice is a separate file rather than a header inside them
> because JSON cannot carry one; the two files below are unedited.
>
> `consumers.json` (schema version 5, 330 lines) is the rollout order, cohort
> policy and per-consumer install mode for ten repositories. Decision R10-D6
> dropped the fleet walk that read it -- `bin/sd-status` opens with "There is
> no repo-path argument and no fleet walk (R10-D6)" -- and the tools that
> consumed it (`templates/scripts/sd-ai-command-pack-status.py fleet`,
> `install.py --configure-fleet`) were deleted on 2026-08-30 by step 3e
> (`43170716`, #610). Two of its ten rows name repositories that are now
> archived: `sd-github-review`, archived by step 4 on 2026-08-31, and
> `se-ai-command-pack`, archived on 2026-09-01 once its fold was verified
> complete -- agents and skills diffed both directions from the filesystem,
> with the only three skills lacking an `sd-*` counterpart confirmed as the
> recorded retirements at
> `docs/work/2026-08-29-artifacts-as-product/implement.md:1074-1077` rather
> than drops.
>
> **The rows stay as written, and that is the point of this notice.** A
> registry nothing reads is a record, and correcting a record in place is how
> a repository loses the ability to say what it once believed. Neither file
> below is edited; what changes is what this page says about them.
>
> `surface-partition.json` (schema version 1, 4,529 lines) partitions the
> `manifest.json` payload of release 0.72.0 into machine, repo-native and
> consumer-config scopes across eighteen platforms. It carries
> `"manifestVersion": "0.72.0"`, which was the terminal release; `manifest.json`
> itself was deleted at step 3e, and so was `.github/scripts/partition-surfaces.py`,
> which generated this file. Of the 740 target paths it lists, **731 do not
> exist in the tree**; the nine that do (`AGENTS.md`, `.prism/rules.json`,
> `.gito/config.toml`, `.github/copilot-instructions.md` and five like them) are
> files this repository keeps for itself, not payload the pack still installs.
> The 562 `repo-native` rows are targets inside consumer repositories, which
> R10-D6 forbids the pack from writing at all.
>
> Nothing reads either file. Outside `docs/work/archive/`, the only references
> to `docs/fleet/**` are `CONTRIBUTING.md`, `CHANGELOG.md` (history),
> `docs/review-learnings.md` (historical PR entries),
> `docs/spec/backend/manifest-and-filesystem.md` (itself stale, and carrying its
> own notice) and the rollout journal. No code path in `bin/`, `dashboard/`,
> `skills/`, `tests/`, `.github/`, `actions/` or `agents/` names them, and no
> file in any other repository under `~/repos/` or in `~/.claude` does either.
>
> The triage that produced this notice is recorded under step 7 in
> `docs/work/2026-08-29-artifacts-as-product/implement.md`.

## What these files were

`consumers.json` was the operator-triggered inventory that ordered fleet
refreshes: cohorts, concurrency, and each consumer's `fat`/`thin` install mode
with the pin path fleet status compared against. `docs/FLEET_ROLLOUT.md` is the
procedure that read it, and carries its own stale notice.

`surface-partition.json` was generated from `manifest.json` and answered one
question per payload file: does this surface belong on the machine, in the
repository, or in a consumer's config? It is what the machine-scope installer's
design argued from before that installer was written.
