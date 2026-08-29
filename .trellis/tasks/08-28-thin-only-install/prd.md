# Thin is the only install: remove the fat payload and the conversion path

## Goal

`python3 install.py TARGET` on a repository that has never had the pack writes the thin
tree directly: the repo-native surfaces, the `.claude/settings.json` marketplace and plugin
entries, and the three receipts with the thin pin. Nothing else. The fat payload, the
`--thin` conversion, `--revert-thin`, the resweep verdict and the `mode` distinction in the
fleet registry are deleted, not defaulted.

## Origin

Found on 2026-08-28 adding `answerbook/mezmo-world-simulator` to the fleet (PR #586). The
install sequence a new consumer goes through today:

1. `install.py TARGET` — writes the fat payload (204 targets for four platforms).
2. commit it, because the resweep refuses a dirty worktree.
3. `scripts/sd-ai-command-pack-thin-resweep.py NAME --repo TARGET --out VERDICT` — needs a
   registry row first, so the fleet PR has to be open before the conversion can run.
4. `install.py TARGET --thin --resweep-verdict VERDICT --consumer NAME` — deletes 171 of
   the files step 1 wrote (measured on mezmo-world-simulator: delete 171, retire 0,
   block-strip 1, keep 29, receipts 3).
5. commit the deletion; flip the registry row; regenerate the candidate ledger.

Two commits and a registry round-trip to reach the state every consumer already runs.
Since PR #586 added `answerbook/mezmo-world-simulator`, `docs/fleet/consumers.json` lists
10 consumers and all 10 are `mode: thin`; no consumer is fat, and none has been since the
last wave in `docs/FLEET_ROLLOUT.md`. This task record changes no registry row itself.

The first idea was "make thin the default" — install fat, then convert in the same
invocation. It was rejected before any code was written because it keeps everything the
conversion exists to guard (the verdict binding, the worktree-clean rule, the
plan-before-apply refusals, ~9,250 lines across `installer/thin.py`,
`installer/conversion.py`, the resweep script and `tests/test_thin_*.py`) in service of a
state that no longer exists. The verdict answers "is it safe to *remove* these files from
a consumer that has them", and a fresh install has nothing to remove.

## Scope

Delete:

- `install.py`: `--thin`, `--revert-thin`, `--resweep-verdict`, `--consumer`,
  `_run_thin_conversion`, `_run_thin_revert`, `_thin_refresh_rejection`, the
  `thin_pin_state` guard, and the `is_thin` / `install_gitignore` branching — there is one
  shape, so the flags choosing it go.
- `installer/thin.py`, `installer/conversion.py` (except what the payload selection still
  needs, see below), `scripts/sd-ai-command-pack-thin-resweep.py`, `tests/test_thin_*.py`.
- `mode` in the fleet registry schema (`FLEET_CONSUMER_MODES`, `DEFAULT_FLEET_CONSUMER_MODE`,
  `scripts/sd_ai_command_pack_fleet_lib.py:25-26`), with a schema bump; the "when any
  consumer is thin" branches in the fleet report; `--revert-thin` guidance in the review
  and housekeeping prompts.
- README "`--thin` converts…", "`--revert-thin` puts the payload back…", and the thin-aware
  refresh paragraph; the matching sections of `docs/SD_AI_COMMAND_PACK.md` (45 mentions).

Keep, renamed for what they now are:

- `docs/fleet/surface-partition.json` — it is the definition of the payload. `repo-native`
  and `consumer-config` rows are what the installer writes; `machine-*` rows are what the
  machine plugin serves. Consider folding it into `manifest.json` as a per-file field so
  there is one list, not a list and a classifier over it.
- The thin pin in `provenance.json` and `mode: thin` in the installed manifest — every
  fleet consumer carries them and every reader (`--check`, the fleet report, the
  bookkeeping resolver) keys on them. Keep the bytes, drop the word "thin" from the
  documentation: it is the receipt.
- `.claude/settings.json` merge (`plan_settings_merge`, `render_settings`,
  `settings_additions`) and `pack_repository_reason` — they move from the conversion into
  the install path and run on every fresh install.
- The machine-plugin prerequisite: a fresh install refuses, with the `install.py --machine`
  instruction, when the plugin is not installed on this machine. Today that gap is only
  found when the first command wrapper fails to resolve.

## Open questions

- `--remove` has no thin form today ("`--remove` still refuses and always will"). With one
  shape it needs one: delete the residual, strip the settings entries this install added
  (`additions` is recorded in provenance for exactly this), delete the receipts.
- `--local-only`: does a local-only install still make sense when the payload is 30 files
  and the plugin serves the rest? Decide, do not default.
- Existing consumers: a refresh must be a no-op on all 10 (`install.py TARGET --check`
  exits 0 before and after). The receipts they carry were written by the conversion; the
  fresh path has to write byte-identical ones or the fleet reports `refresh-required`
  everywhere at once.

## Acceptance

- Fresh `install.py TARGET` on a repo with Trellis and the plugin installed produces the
  same tracked tree as fat-then-convert produced on `answerbook/mezmo-world-simulator`
  at 337df5c (29 kept files + 3 receipts + settings entries), and `--check` exits 0.
- `install.py TARGET --check` exits 0 on every consumer in `docs/fleet/consumers.json`
  with no change to their trees.
- `grep -c thin install.py` is small enough to read in one sitting, and no flag on
  `install.py --help` chooses an install shape.
- `make check` passes; the candidate validator passes for all 10 consumers.
