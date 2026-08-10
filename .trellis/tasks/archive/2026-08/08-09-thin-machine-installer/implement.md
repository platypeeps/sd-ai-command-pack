# Implementation plan: thin-machine-installer

Ordered steps; each lands with its tests green before the next starts.
Branch: `feat/thin-machine-installer` off `main`. Validation commands
per step; full gate at the end.

## Step 1 — executed platform probes, then partition dispositions

- Probes FIRST (PRD requirement 1's verification gate). THREE probes,
  one per flipped surface — no surface flips on another's evidence.
  Scratch home (`HOME`, `XDG_CONFIG_HOME` overridden) for each:
  1. gemini command: `~/.gemini/commands/sd/probe.toml`, gemini CLI
     enumerates/resolves it from USER scope -> gates `gemini` rows.
  2. opencode command: XDG `opencode/commands/sd-probe.md`, opencode
     CLI resolves it from USER scope -> gates `opencode` rows.
  3. shared skills autoload: `~/.agents/skills/sd-probe/SKILL.md`,
     opencode CLI enumerates/resolves the skill from USER scope ->
     gates `shared` rows (first EXECUTED evidence; research verdict is
     doc-based).
  Persist command lines + decisive output to
  `research/platform-probes.md`.
- Partition flips reflect probe outcomes only: passing surface ->
  `(MACHINE, False)`; failing or headless-infeasible surface stays
  `(MACHINE, True)` and is excluded from the payload build (record the
  scope change). `codex -> (REPO_NATIVE, False)` regardless (evidence
  already executed). `shared` additionally gains
  `retainVendoredFor: ["codex", "pi"]`.
- `partition-surfaces.py`: disposition table + additive
  `retainVendoredFor` emission; regenerate artifact via
  `make generate`; update `tests/test_partition_surfaces.py`
  (dispositions + new field shape + backward-compat: field absent
  everywhere else).
- Spec: document `retainVendoredFor` in the Surface Partition Artifact
  section (additive v1 field, migration contract).
- Parent bookkeeping (BEFORE any implementation step consumes the
  retention rule): parent `prd.md` cross-child criteria gain the
  codex/pi retention + vendored-`scripts/` constraints; parent
  `design.md` migration section updated — the deletion bullet retains
  vendored rows whose platform's `retainVendoredFor` intersects the
  consumer's `docs/fleet/consumers.json` `platforms` array (the single
  executable authority), and the conversion-time resweep checklist
  gains the codex/pi usage-marker grep that blocks conversion until
  the consumer declares or removes the usage. Cite
  `research/platform-verification.md`.
- Validate: `.venv/bin/python -m unittest tests.test_partition_surfaces`;
  `python3 .github/scripts/partition-surfaces.py --check`.

## Step 2 — machine-scope engine in the existing `installer/` package

- `installer/machinescope.py`: destination families
  (homedir/expanduser + XDG resolution), plan-before-apply
  classification, intent journal (`machine-install.intent.json`
  written before first write, deleted after receipt commit;
  receipt-absent payload-identical paths adopt as `owned-current`
  ONLY via a matching journal entry, else `unowned`), conflict
  refusal naming every path, `--force` with `.bak` backups recorded
  as receipt `backup {path, digest}` entries, atomic temp+rename
  writes reusing the package's fileops symlink/traversal defenses,
  receipt schema v1 with per-file `digest` + `executable` +
  optional `backup`, canonical
  `payloadDigest` (same algorithm as the plugin generator — shared
  helper, single implementation), receipt-trust validation (family
  allowlist, relative normalized traversal-free paths, fail-closed on
  any invalid entry), removed-row cleanup, `remove` and `status`
  subcommands, provisional-platform fail-closed via bundled partition,
  state root via the shared state-ladder helper (0700, non-symlink).
- CLI surface exposed through a callable `main(argv)` (used by
  `install.py --machine`, the plugin bootstrap, and tests directly).
- New `tests/test_machine_installer.py` covering the design test list,
  including: injected mid-apply failure + rerun convergence (journal
  present -> adoption); pre-existing byte-identical user file WITHOUT
  journal -> refused as `unowned` (the adoption hole); force-overwrite
  -> receipt `backup` recorded -> `remove` restores the original
  (digest-verified) and deletes the `.bak`; malicious-receipt shapes
  incl. forged `backup` paths outside family roots.
- Validate: `.venv/bin/python -m unittest tests.test_machine_installer`;
  `make lint`.

## Step 3 — shared rewrite pipeline + `install.py --machine`

- Extract/extend the reference rewrite so ONE implementation serves
  both the plugin generator and machine-payload staging, over TWO
  relocated-resource patterns in `.agents/**` (and adapter)
  Markdown/TOML: `scripts/<pack-script>` ->
  `~/.agents/bin/<pack-script>` AND `docs/SD_AI_COMMAND_PACK.md` ->
  `~/.agents/docs/SD_AI_COMMAND_PACK.md`. Residue gate: zero repo-root
  `scripts/sd-ai-command-pack-*` AND zero `docs/SD_AI_COMMAND_PACK.md`
  references in the final payload. Dependency-closure gate: every
  rewritten script reference names a `sharedRuntime` row, every
  rewritten doc reference names a payload docs row; justified
  allowlist only.
- `install.py --machine`: stage payload from checkout manifest through
  the rewrite pipeline into a temp root, run the engine; mutually
  exclusive with repo target / `--platform` / `--all`; `--dry-run`,
  `--force`, `--json` pass through.
- Tests: rewrite unit tests (rewrite, residue, closure, allowlist
  justification), install.py flag exclusivity, scratch-home
  end-to-end.
- Validate: focused unittest modules; `make lint`.

## Step 4 — plugin bundling

- `generate-plugin.py`: emit `installer/**` (code), rewritten
  `machine-payload/**`, `machine-payload/partition.json`,
  `bin/sd-machine-install` bootstrap (sys.path insert + engine main);
  new fail-closed conditions (unmapped family, closure violation,
  residue hit); extend `--check`.
- Regenerate `plugins/sd`; update `tests/test_generate_plugin.py`
  (inventory, determinism, gates).
- Validate: `python3 .github/scripts/generate-plugin.py --check`;
  `.venv/bin/python -m unittest tests.test_generate_plugin`;
  `claude plugin validate plugins/sd --strict`.

## Step 5 — `sd-pack-update`

- `templates/scripts/sd-ai-command-pack-pack-update.sh` -> plugin
  `bin/`: update -> resolve new root via `claude plugin list --json`
  (missing/ambiguous fails, no install) -> `<new-root>/bin/
  sd-machine-install install` -> report both versions + skew.
- Manifest row + partition classification (machine-claude); update the
  parent PRD manifest count (776 -> 777) in the same commit.
- Stub-`claude` test module: happy path, update-fails, list-missing,
  install-fails (skew), rerun converges.
- Validate: new shell/unittest module; `make sync`; lint.

## Step 6 — `sd-status` skew line

- Status collector: read machine receipt via the shared state-ladder
  helper; plugin version via `claude plugin list --json` — ANY
  discovery failure (CLI absent, nonzero exit, malformed JSON, plugin
  missing/duplicated) reports `unavailable`. Machine state
  `none` / `installed` / `invalid` (malformed receipt = anomaly);
  separate comparison field `current` / `skew` / `unknown` (unknown
  whenever plugin version unavailable — never masquerades as
  current). One human line + JSON fields; advisory exit zero.
- Extend status tests: all machine states, comparison states, and
  each discovery-failure shape mapping to `unavailable`+`unknown`.
- Validate: focused unittest module.

## Step 7 — docs, spec, release chain

- `manifest-and-filesystem.md`: "Machine-Scope Installer" section
  (families, plan-before-apply, receipt schema + trust rules, state
  ladder reuse, provisional fail-closed, update sequence, remove).
- `CHANGELOG.md` + `manifest.json` version bump (payload gate); fleet
  candidate ledger refresh if the payload digest moved.
- Validate: `make generate` clean; `make test` (full gate);
  `node scripts/sd-ai-command-pack-review-preflight.mjs` 0 failures;
  `make release-prep` exit 0.

## Review gates

- trellis-check after each step's diff; planning adversarial review
  applied at convergence (2 rounds; ledger in completion report).
- Rollback points: one commit per step; step 1 (partition) and step 4
  (shipped payload shape) are the externally visible ones and revert
  independently.

## Manual acceptance (human)

- Machine install to a scratch prefix; per passing platform, in a real
  session, resolve the user-scope command and record WHICH scope won
  (shadowing evidence); interrupted-update skew visible in `sd-status`
  and converged by rerunning `sd-pack-update`; `remove` deletes
  installer-created files and restores force-displaced originals from
  receipt-recorded backups (precise "clean machine" contract — it
  restores nothing without a recorded backup).
