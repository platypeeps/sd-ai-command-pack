# Design: machine-scope installer for non-Claude surfaces + unified update

Child of `08-09-deployment-thin-consumers` (parent design "Machine-scope
installer for non-Claude surfaces (D3)"). Platform verdicts come from
`research/platform-verification.md` (verified against installed CLI
binaries gemini-cli 0.46.0, codex 0.147.0, opencode 1.18.15). Revised
after adversarial review round 1 (concern ledger in the task journal /
completion report).

## Platform dispositions (requirement 1 outcome)

| Platform | Verdict | Partition change |
|---|---|---|
| `gemini` | machine: `~/.gemini/commands/sd/*.toml` loads as `kind: "user-file"` (binary loader trace); executed probe required before flip | `provisional -> false` only after the step-1 executed probe passes |
| `opencode` | machine: global `commands/*.md` under the XDG config root per the binary's own scope table; doc-based so far — executed probe required before flip | `provisional -> false` only after the step-1 executed probe passes |
| `codex` | repo-native as shipped: `.agents` resolves against the PROJECT root; the binary never reads `~/.agents/skills`; its user root is `$CODEX_HOME/skills` (default `~/.codex/skills`), a target family the pack does not ship | disposition `machine -> repo-native` (rule: re-disposition, never force-fit) |
| `shared` (`.agents/**`) | machine for OpenCode (auto-loads `~/.agents/skills/<name>/SKILL.md` per its binary scope table — doc-based so far); codex and pi still read the same layer repo-locally | `provisional -> false` ONLY after its OWN step-1 executed skills-autoload probe passes (a gemini/opencode COMMAND probe pass proves nothing about this surface), WITH the machine-readable retention rule below |

**Verification gate (PRD requirement 1).** `provisional` flips are not
design decisions; they are step-1 outputs. The step-1 probes execute
each CLI against a scratch home (`HOME`/`XDG_CONFIG_HOME` overridden)
containing one pack-shaped probe artifact, and assert the CLI actually
resolves it from the user scope (provenance, not mere existence —
research risk 3). Probes gate per SURFACE, one probe per flipped row
set — no surface flips on another surface's evidence:

- `gemini` command probe (`~/.gemini/commands/sd/probe.toml`) gates
  the `gemini` rows only.
- `opencode` command probe (XDG `opencode/commands/sd-probe.md`) gates
  the `opencode` rows only.
- `shared` skills-autoload probe (`~/.agents/skills/sd-probe/
  SKILL.md`, OpenCode enumerating/resolving it from the user scope)
  gates the `shared` rows only — this is the surface's first executed
  evidence; the research verdict is documentation-based.

A failing (or headless-infeasible) probe keeps that surface
`provisional: true`; the payload build excludes it fail-closed and the
task records the shrunken scope rather than shipping unverified
writes.

**Codex/pi retention rule (machine-readable).** Partition schema v1
gains one additive optional field:
`platforms.<id>.retainVendoredFor: [<platform-id>...]` — set on
`shared` to `["codex", "pi"]`. Contract: migration tooling must keep
this platform's rows vendored in any consumer repo that still serves a
listed platform, even though the primary category is `machine-other`.

**Executable detection rule** (so the parent migration can actually
apply it): a consumer "still serves a listed platform" iff its
`docs/fleet/consumers.json` `platforms` array intersects
`retainVendoredFor`. The fleet registry is the single authority — no
heuristic repo sniffing. Because no current consumer declares `codex`
or `pi`, today's conversions delete `shared` vendored rows; the
parent's conversion-time resweep gains one mandatory check: grep the
consumer for codex/pi usage markers (`.codex/`, `$CODEX_HOME`
references, pi adapter files) and BLOCK conversion until the consumer
either declares the platform in its registry row or removes the
usage. Parent artifacts updated in step 1: the parent design's
migration deletion bullet ("deletes the vendored payload minus
`repo-native` + `consumer-config`") gains the retention carve-out, and
the resweep checklist gains the marker grep.

Additive and backward-compatible (existing consumers read `files` and
`platforms.scope/provisional` only); documented in the spec's Surface
Partition Artifact section. A `$CODEX_HOME/skills` target family is a
filed follow-up task, not part of this child; when it ships, `codex`
leaves the retention list.

## Script-reference rewrite (the machine payload must be self-contained)

The `.agents/skills/**` Markdown invokes pack scripts repo-relatively
(`bash scripts/sd-ai-command-pack-toolchain.sh run-python -- scripts/…`,
e.g. `templates/.agents/skills/sd-check/SKILL.md:24`). Copied verbatim
to `~/.agents/skills`, those references only resolve while the consumer
repo still vendors `scripts/` — the thin end-state breaks them. The
Script Sibling Resolution contract covers script→sibling-script
resolution after invocation, not the skill→first-script hop, so it does
not save this.

Fix, mirroring the plugin generator's existing Markdown rewrite for the
`machine-claude` slice (`generate-plugin.py` rewrite + residue gate):

- Machine-payload generation rewrites `scripts/<pack-script>` operands
  in `.agents/**` Markdown to `~/.agents/bin/<pack-script>` (literal
  `~` in instruction text; agents expand it). The gemini/opencode
  command adapters are thin skill-name resolvers and carry no script
  paths of their own; the rewrite still runs over them with the same
  residue gate so a future adapter regression fails the build.
- The 26 `sharedRuntime` scripts install to `~/.agents/bin/`, keeping
  their executable bit. Sibling resolution inside that flat directory
  is exactly the shipped own-location contract.
- Relocated-DOC rewrite (same pipeline, second pattern): the machine
  payload relocates `docs/SD_AI_COMMAND_PACK.md` to `~/.agents/docs/`,
  but shipped skills reference it repo-relatively
  (`templates/.agents/skills/sd-full-check/SKILL.md:82,94`). The
  rewrite maps `docs/SD_AI_COMMAND_PACK.md` ->
  `~/.agents/docs/SD_AI_COMMAND_PACK.md` in `.agents/**` (and adapter)
  Markdown/TOML, exactly like the script rewrite.
- Dependency-closure gate: every pack-script reference in the rewritten
  machine payload must name a file present in the installed
  `~/.agents/bin` set (the `sharedRuntime` rows), and every rewritten
  doc reference must name a payload docs-family row. An unmatched
  reference is a build error, mirroring the plugin's closure condition;
  a justified allowlist requires the same per-file justification the
  plugin's `BIN_LITERAL_ALLOWLIST` carries.
- Residue gate: zero repo-root `scripts/sd-ai-command-pack-*`
  references AND zero repo-root `docs/SD_AI_COMMAND_PACK.md`
  references in the final machine payload.

Migration constraint recorded for `thin-migration`: vendored
`scripts/` removal from a consumer additionally requires the machine
payload rewrite shipped here (non-Claude surfaces execute from
`~/.agents/bin`), and `.agents/**` stays vendored per the retention
rule while codex/pi depend on it.

## Components

### 1. Machine-scope module in the EXISTING `installer/` package

`installer/` already exists as install.py's implementation package
(registry, fileops, provenance, …) with `install.py` as the executable
entry point (`installer/__init__.py:1-4`). Machine scope joins it as
`installer/machinescope.py` (+ small helpers), reusing the package's
fileops safety primitives rather than duplicating them. No
`python3 -m installer` entry is added.

Engine behavior (`machinescope.py`):

- **Destination families**, resolved via `Path.home()` /
  `os.path.expanduser` (never a raw `$HOME` env read; a machine whose
  homedir cannot resolve is an error, matching Gemini's own homedir
  resolution — research notes its tmpdir fallback, which the installer
  treats as unsupported rather than writable):
  - `.agents/**` -> `<home>/.agents/**`
  - `.gemini/commands/**` -> `<home>/.gemini/commands/**`
  - `.opencode/commands/**` ->
    `${XDG_CONFIG_HOME:-<home>/.config}/opencode/commands/**`
    (XDG-derived; never `~/opencode/`, which is an unrelated artifact)
  - `sharedRuntime` `scripts/*` -> `<home>/.agents/bin/*` (executable)
  - `docs/SD_AI_COMMAND_PACK.md` -> `<home>/.agents/docs/`
  A payload row matching no family is a build-time error (generator)
  and a fail-closed runtime error (installer), so the two inventories
  cannot drift silently.
- **Plan-before-apply.** Phase 1 scans every target and classifies:
  `owned-current` (in receipt AND matches new payload digest+mode),
  `owned-stale` (matches old receipt entry), `absent`, `drifted`
  (owned path, matches neither), `unowned` (exists, not in receipt).
  Any `drifted`/`unowned` conflict refuses the whole run before the
  first write, naming every conflicting path; `--force` proceeds and
  writes a `.bak` sibling backup for each overwritten conflict
  (precedent: `install.py --backup`), recording the backup in the
  receipt (below). Phase 2 applies via temp-file + atomic rename with
  the package's existing symlink-parent and traversal defenses. Phase
  3 writes the receipt atomically.
- **Intent journal (interrupted-run recovery without file adoption).**
  Byte-identity alone never proves installer authorship: a
  pre-existing user file identical to the payload must not be claimed
  (a later `remove` would delete it). Before its first write the
  engine atomically writes `machine-install.intent.json`
  (`schemaVersion`, `payloadDigest`, planned target paths) beside the
  receipt in the state root, and deletes it after the receipt commits.
  On rerun, a receipt-absent existing path that matches the new
  payload classifies `owned-current` ONLY when a valid intent journal
  with the same `payloadDigest` lists that path — proof a prior
  interrupted run wrote it. No journal (or digest mismatch) -> the
  path is `unowned` and refuses without `--force`. A dangling journal
  with no matching paths is cleaned up with a diagnostic.
- **Receipt.** Private state root uses the repository's shared state
  ladder exactly (explicit override, `SD_AI_COMMAND_PACK_STATE_HOME`,
  `XDG_STATE_HOME`, Windows local-app-data, `~/.local/state/
  sd-ai-command-pack`), non-symlink directory, mode `0700` — the same
  contract the work-loop helper implements; the module reuses that
  resolution helper rather than re-implementing it. File:
  `machine-receipt.json`, schema v1: `schemaVersion`, `packVersion`,
  `payloadDigest`, `installedAt`, `files[{family, path, digest,
  executable, backup?}]`, `sourceRoot`. `backup` (present only for
  `--force` overwrites) records `{path, digest}` of the `.bak` sibling
  holding the displaced pre-existing content, making restoration a
  receipt fact rather than a filename convention. `payloadDigest` reuses the canonical
  generator digest algorithm (sorted target paths + content bytes +
  executable bit) so plugin, payload, and receipt agree byte-for-byte.
- **Receipt trust.** The receipt authorizes overwrites/deletes, so it
  is validated on load: `family` must be a known destination family,
  `path` must be relative, normalized, traversal-free, and inside that
  family root after resolution; symlinked parents refuse; any invalid
  entry fails the whole receipt closed (no partial trust). A receipt
  edited to point elsewhere cannot direct a write or delete outside
  the family roots.
- **Row removal.** Paths in the old receipt absent from the new
  payload are deleted only when byte+mode-identical to their receipt
  entry; otherwise left in place with a diagnostic.
- **`remove` subcommand** (rollback commitment): deletes receipt-owned,
  unmodified files and prunes empty family directories; drifted files
  refuse without `--force`. For entries carrying a `backup` record it
  RESTORES the backed-up original in place (backup digest verified
  first; mismatch refuses without `--force`) and deletes the `.bak`.
  It restores nothing the receipt did not record a backup for — the
  "clean machine" claim is precise: installer-created files removed,
  force-displaced pre-existing files restored from recorded backups.
- **`status` subcommand**: receipt vs a given payload root (version,
  payloadDigest, per-file digest+mode drift). `--json` stable schema.
  Malformed receipt is a typed `invalid` status, never `none`.

### 2. `install.py --machine` (pack-checkout entry)

`install.py` gains `--machine` (mutually exclusive with a repo target
and platform flags): stages the machine payload from the checkout
manifest (applying the same rewrite pipeline the generator uses — one
shared implementation, not two), then runs the engine. `--dry-run`,
`--force`, `--json` pass through. This is the developer path;
machines with only the plugin use `sd-pack-update`.

### 3. Plugin bundling (generator extension)

`generate-plugin.py` additionally emits into `plugins/sd/`:

- `installer/**` — the package, verbatim (code only).
- `machine-payload/**` — machine-other slice + `sharedRuntime` rows in
  target-relative layout, with the script-reference rewrite applied at
  generate time (payload is committed, so the rewrite is reviewable
  and `--check`-pinned).
- `machine-payload/partition.json` — bundled partition copy so the
  engine enforces `provisional` fail-closed without a checkout.
- `bin/sd-machine-install` — small bootstrap: inserts its plugin root
  on `sys.path`, imports `installer.machinescope`, runs the CLI. This
  is how code inside a plugin root becomes importable without pip.

New fail-closed build conditions: unmapped destination family,
dependency-closure violation, residue-gate hit. `--check` byte-compare
extends over the new trees.

### 4. `sd-pack-update` (plugin `bin/`, the one update action)

Portable bash, shipped like existing bin scripts:

1. `claude plugin update sd@sd-ai-command-pack` (flags can override
   plugin/marketplace names).
2. Resolve the NEW plugin root from `claude plugin list --json` (never
   its own location — the running copy lives in the OLD root). Missing
   or ambiguous entry: fail with diagnostic, no install.
3. Run `<new-root>/bin/sd-machine-install install` from the resolved
   root.
4. Report plugin version (new root's `plugin.json`) and machine
   receipt version; divergence prints as skew.

Both halves idempotent; the receipt only advances on success, so an
interrupted update is visible as skew and a rerun converges (the
plan-before-apply classification makes the rerun safe).

### 5. `sd-status` skew line (minimal)

The local status collector reads the machine receipt directly through
the shared state-ladder helper — no plugin needed to find it. Plugin
version comes from `claude plugin list --json`; ANY discovery failure
— CLI absent, nonzero exit, malformed JSON, plugin missing or listed
twice — reports `pluginVersion: "unavailable"` (never a guess, never a
crash). Machine state from the receipt alone: `none` (no receipt),
`installed` (valid receipt), or `invalid` (malformed receipt — an
anomaly, not `none`). The version comparison is a separate field:
`current` / `skew` when both versions are known, `unknown` when the
plugin version is unavailable — so a broken `claude` CLI can never
masquerade as `current`. Human line spells out the unavailable case.
Advisory only; exit stays zero. The fleet/pin rework stays in
`thin-fleet-status-pins`.

### 6. Partition changes

`partition-surfaces.py` `PLATFORM_DISPOSITIONS`: `codex` ->
`(REPO_NATIVE, False)`. `gemini`, `opencode`, `shared` ->
`(MACHINE, False)` only after their step-1 probes pass (a failing probe
keeps `(MACHINE, True)` and excludes the platform from the payload
build). `shared` gains `retainVendoredFor: ["codex", "pi"]`. Codex's
re-disposition changes zero `files[]` rows (it has none) but flips its
`platforms` entry, which the engine honors fail-closed.

## Compatibility / rollout

- Fat installs unchanged; machine mode is additive. Vendored copies
  keep working during migration (project scope precedes/shadows user
  scope; the manual acceptance probe records which scope actually wins
  per platform — research risk 3).
- Rollback: `remove` subcommand per receipt; force-overwrite backups
  restore previously unowned files; partition flips revert with one
  commit. Parent's per-child reversibility holds.
- Parent PRD's manifest count (776) moves to 777 when the
  `sd-pack-update` manifest row lands; the same commit updates the
  parent count references so no artifact recites a stale figure.
- No consumer-repo changes in this task.

## Testing strategy

- `tests/test_machine_installer.py` (scratch home + XDG fixtures):
  fresh install per family; receipt version/digest/mode correctness;
  rerun no-op; interrupted-run recovery (inject failure between
  apply and receipt write, rerun converges — the exact PRD AC);
  unowned and drifted refusal naming paths; `--force` with `.bak`
  backups; malicious receipt entries (traversal, absolute, unknown
  family, symlink parent) fail closed; removed-row cleanup; mode-drift
  detected by `status`; provisional-platform payload refused;
  XDG honored; `remove` behavior.
- `tests/test_generate_plugin.py`: bundled `installer/**`,
  `machine-payload/**` parity, rewrite + residue + closure gates,
  determinism.
- `tests/test_partition_surfaces.py`: dispositions, additive
  `retainVendoredFor` field.
- `sd-pack-update` with a stub `claude` on PATH: happy path, update
  fails, list missing/ambiguous, install fails (skew visible), rerun
  converges.
- Step-1 executed platform probes (gemini, opencode) are recorded in
  task research with command + output; they gate the flag flips.
- Manual acceptance (human): real-session resolution check per
  platform recording which scope won; interrupted-update skew +
  converge.
