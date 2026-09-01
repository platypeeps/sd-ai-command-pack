# Manifest And Filesystem

> [!important]
> **Partly stale as of 2026-09-01.**
> This is the longest page in the tree (2,998 lines) and almost all of it
> specifies things that were deleted. `manifest.json` -- the source of truth the
> first section names, and the file the other twenty-nine sections are written
> around -- and the whole `installer/` package (`manifest.py`, `machinescope.py`,
> `machinepayload.py`, `machinestage.py`, `fileops.py`, `references.py`,
> `registry.py`, `removal.py`, `thin.py`), `install.py`, `templates/`,
> `scripts/`, `.github/scripts/generate-plugin.py`,
> `.github/scripts/partition-surfaces.py` and the tests
> `tests/test_install_core.py`, `tests/test_install_audit.py`,
> `tests/test_pack_drift.py`, `tests/test_generate_plugin.py` and
> `tests/test_partition_surfaces.py` were all deleted on 2026-08-30 by step 3e
> (`43170716`, #610). The Release Payload Gate section describes a gate deleted
> at step 0 with the release train (2026-08-29, #597), and the three fleet
> campaign scenarios describe a fleet walk decision R10-D6 dropped.
> A mechanical check of the page's own citations: of 377 backticked paths in it,
> **302 name something that is not in `git ls-files`**.
>
> Two things here are still load-bearing and should be read before this page is
> acted on. The **Machine-Scope Installer** section describes the
> *design* that `bin/sd_install.py` implements, but by way of files that no
> longer exist -- `installer/machinescope.py`, `bin/sd-machine-install`,
> `install.py --machine` -- so it is a design record, not a map of the code.
> And the **Trellis Gitignore Maintenance** section is the only reason the
> vestigial `SD-AI-COMMAND-PACK` markers in `.gitignore` are still there:
> `CONTRIBUTING.md` says they are left in place because this section still
> specifies them. Whatever happens to this page has to settle that too.
>
> The text below is unedited. It is the record of what that machinery
> specified, not guidance for the repository as it stands. The triage that
> produced this notice is recorded under step 7 in
> `docs/work/2026-08-29-artifacts-as-product/implement.md`.

> Manifest-driven install behavior and local filesystem conventions.

---

## Overview

There is no database, ORM, migration system, or persistent app state. The
installer reads `manifest.json`, validates the target repo, and writes selected
template files into that target repo.

## Manifest Source Of Truth

`manifest.json` owns the installable file list. Each file record declares:

- `platform`
- `kind`
- `source`
- `target`
- optional `anchor`
- optional `install`

`installer/manifest.py` converts each manifest entry into a frozen `PackFile`
in `load_manifest()`. Manifest-loaded entries always require a real `source`
inside the pack root. Installer-generated entries such as receipt, provenance,
and managed gitignore files may use `source=None`; do not point generated files
at `manifest.json` or another fake template source just to satisfy the type.
When adding a file, update `manifest.json` first and keep Python logic generic
unless the install semantics really change.

Reference files:

- `manifest.json`
- `installer/manifest.py`, `PackFile`
- `installer/manifest.py`, `load_manifest()`

### Subagent Artifact Kind

The `agent` kind is a first-class artifact gated by a per-platform capability,
modeled on the `command_kind` / `command_target_pattern` pair (not on
`structured_question_tool`). A platform supports agents only when its
`PlatformInfo` row carries both `agent_kind` (`"markdown"` | `"toml"` |
`"json"`) and `agent_target_pattern`; the pair-gate
`if not info.agent_kind or not info.agent_target_pattern` yields zero rows by
construction for every other platform. Adding a platform is an additive
registry row, never an edit to the generator — the capable set is read from the
registry (`agent_capable_platforms()`). Wave 1 is claude + codex + gemini.

Kinds are descriptive, not dispatching: `agent` rows flow through install,
status, check, audit, and remove with no per-kind branch, exactly like `skill`.
The kind is registered in three places that must stay in sync —
`installer/manifest.py` `KNOWN_MANIFEST_KINDS` and the byte-identical
`known_kinds` set in both `templates/scripts/sd-ai-command-pack-surface-check.py` and its
`templates/` mirror.

Generation rules (`.github/scripts/generate-command-surfaces.py`):

- Canonical sources live at `templates/.agents/agents/<name>.md` (neutral
  Markdown + YAML frontmatter). Every pack agent name **must** start with `sd-`;
  a `trellis-*` name lands inside the Trellis-local agent glob and stops being
  pack-managed. The generator raises `GenerationError` on a non-`sd-` name.
- Markdown platforms (claude, gemini) install the canonical source verbatim; the
  gemini emitter also asserts the agent's tools are within a fixed allowlist,
  because gemini runs subagents without per-tool confirmation.
- The `toml` dialect (codex) renders a twin at `templates/.codex/agents/<name>.toml`
  with the body as a `developer_instructions` string (default
  `sandbox_mode = "read-only"`).
- Agent paths are **not** added to `trellis_local_only`; pack agents must stay
  pack-managed and removable.

Shipping zero agent sources is a valid state — the derivation returns no rows
and no rendered twins, and the manifest is byte-identical. The first named
agents belong to `07-25-worker-agents`, which consumes this kind, field, and
naming rule.

## Surface Partition Artifact

`.github/scripts/partition-surfaces.py` [absent: removed with the release train in 0.72.0] assigns every `manifest.json` row
exactly one deployment category and writes the committed artifact
`docs/fleet/surface-partition.json` (schema version 1). It runs from
`make generate` after command-surface generation, because it reads the manifest
that generator rewrites. `--check` regenerates in memory and byte-compares
against the committed artifact; `tests/test_partition_surfaces.py` [absent: removed with the release train in 0.72.0] runs that
check against the live tree, so drift fails the normal test lane rather than a
separate CI job.

The four categories are `machine-claude` (installed once per machine via the
Claude Code plugin), `machine-other` (installed once per machine for non-Claude
surfaces), `repo-native` (stays vendored per consumer repository), and
`consumer-config` (small per-repo configuration a consumer keeps wherever the
payload lives). `pack-only` is not a category: repository files outside the
manifest are never shipped, so they need no inventory.

Classification is computed by rule and never hand-maintained as a path list.
Target-path overrides (`TARGET_OVERRIDES`) win first, then the per-platform
disposition table (`PLATFORM_DISPOSITIONS`, one `machine` or `repo-native`
entry per `PLATFORM_REGISTRY` key, checked in both directions at runtime).
Because platform disposition alone would be a catch-all that can never fail,
three independent conditions keep the gate reachable, each with its own
diagnostic: a row whose platform is not a registry key, a row whose `kind` is
outside `KNOWN_KINDS`, and an override pattern matching zero rows.

`KNOWN_KINDS` is deliberately independent of `KNOWN_MANIFEST_KINDS`: the
installer set is what install accepts, the partition set is what has been given
a deployment category. `agent` is registered for install and ships zero rows,
so the first agent row fails the partition gate until it is classified. That is
the intended behavior, not a defect — it is one line to resolve.

Three schema flags carry contracts for downstream consumers (the plugin build,
the machine installer payload, and migration tooling):

- `platforms.<id>.provisional: true` means the machine disposition is not
  verified yet. Consumers **fail closed**: treat the platform as not
  installable machine-scope — effectively repo-native — until verification
  flips the flag. `claude` is non-provisional because the plugin mechanism is
  itself the verification. Every other machine platform became
  non-provisional through an **executed** user-scope probe against the
  installed CLI (scratch `HOME` and `XDG_CONFIG_HOME`, empty working
  directory, negative control), never through documentation alone.
- `files[].sharedRuntime: true` means non-Claude surfaces invoke the file at
  runtime even though its primary category is `machine-claude`. The machine
  installer consumes the `machine-other` slice **plus** every `sharedRuntime`
  row; primary categories stay mutually exclusive.
- `platforms.<id>.retainVendoredFor: [<platform-id>...]` (optional, additive
  in schema version 1) names the platforms that still read this platform's
  rows **repo-locally**, even though the platform itself installs
  machine-scope. Migration tooling must keep those rows vendored in any
  consumer that serves a listed platform. `shared` carries `["pi"]`: OpenCode
  autoloads `~/.agents/skills` and Pi reads the same layer repo-locally.

  `codex` was carried here until an executed probe retired it. The entry rested
  on the claim that Codex reads `.agents` only against the project root; Codex
  in fact merges the project-root layer with `$HOME/.agents/skills` and
  `$CODEX_HOME/skills`, so the machine install already serves it and the
  carve-out retained 77 rows per declaring consumer for nothing. Codex remains
  `repo-native` — the pack ships no `.codex/**` rows at all — but that is a
  statement about its own adapter surface, not about the `shared` rows it
  reads. `pi` is unprobed and stays.

The detection rule for `retainVendoredFor` is executable, not a judgement
call: a consumer **still serves** a listed platform iff its
`docs/fleet/consumers.json` `platforms` array intersects the list. The fleet
registry is the single authority — no heuristic sniffing of consumer
repositories decides retention. Because no consumer declares `pi` today,
current conversions delete the `shared` vendored rows; a consumer that starts
serving it changes its registry row first, and that edit is what turns
retention on.

Conversion-time resweeps additionally grep the consumer for codex/pi usage
markers. **Which of those markers blocks is derived from `retainVendoredFor`,
not restated in the scanner.** Undeclared usage of a *retained* platform is a
blocker, because the missing declaration is what deletes a surface that
platform reads; undeclared usage of a platform nothing retains is recorded as
an advisory, because the declaration it demands would change no plan. Deriving
the set means retiring a platform's retention retires its blocker in the same
edit, and the scanner cannot disagree with the classifier about what a
declaration is worth. Ownership is unaffected: a pack-owned `.codex/`
directory is a pack defect either way, and a marker inside a stripped managed
block stays scheduled.

The field is optional and absent everywhere else, so consumers reading only
`scope` and `provisional` keep working unchanged. The generator fails closed
on a retention list that names an unknown platform, sits on a `repo-native`
platform (where it would be meaningless), is empty, or repeats an entry.

`counts` and `manifestVersion` exist to make the diff reviewable; downstream
tooling reads `files` and `platforms`.

Reference files:

- `.github/scripts/partition-surfaces.py` [absent: removed with the release train in 0.72.0]
- `docs/fleet/surface-partition.json`
- `tests/test_partition_surfaces.py` [absent: removed with the release train in 0.72.0]

## Plugin Generation

`.github/scripts/generate-plugin.py` [absent: removed with the release train in 0.72.0] builds the committed Claude Code plugin at
`plugins/sd/` from the `machine-claude` slice of the partition artifact joined
to `manifest.json` by `target`. It runs from `make generate` after
`partition-surfaces.py` (it consumes that artifact) and from the
`prepare-release.py` chain in the same order. The plugin tree is never
hand-edited: `--check` regenerates into a temp directory and byte-compares the
committed tree including extraneous files, and `tests/test_generate_plugin.py` [absent: removed with the release train in 0.72.0]
runs that check against the live tree, so drift fails the normal test lane.

Slice targets map to plugin destinations by manifest `kind`: `skill` rows to
`skills/<name>/...`, `command` rows to a flattened `commands/<short>.md` (the
plugin is named `sd`, so `/sd:<short>` is preserved), and `scripts/` rows to
`bin/`. Rows carrying `sharedRuntime: true` are shared with the machine
installer, not exclusive to the plugin; the generator must keep shipping them.
`.claude/rules/**` is `consumer-config` and never enters the plugin.

Three further trees make the plugin the only thing a machine needs in order to
install the non-Claude surfaces too: `installer/**` (the modules
`installer.machinescope` imports, enumerated from the import graph rather than
a hand-kept list), `machine-payload/**` (the machine-scope payload with its
bundled `partition.json`), and the `bin/sd-machine-install` bootstrap. See
Machine-Scope Installer below; the two trees are siblings at the plugin root
because that is where the engine looks for its default payload.

Eight conditions fail the build closed rather than shipping a broken plugin: a
slice row with no manifest source row; an unreadable template source (including
a command's authored source or its frontmatter description); a slice row whose
kind has no plugin destination; rewrite residue; an empty pack
version; a dependency-closure gap; an installer module the bootstrap imports
that has no file or that imports a sibling relatively (the bundle loads the
package by absolute name); and any machine-payload failure raised by
`installer.machinestage`. The residue gate has two scopes —
generated Markdown may keep no repository-root script path at all (any
`sd-ai-command-pack-` or `sd_ai_command_pack_` name prefixed with the
`scripts/` directory), while `bin/` contents may keep
only the consumer-layout *data* globs listed in the per-file allowlist with a
written justification (`install-audit` and `pr-body-scope` region globs
describing vendored installs). Closure means every bare pack-command reference
in rewritten Markdown resolves to a file present in `bin/`, except entries in
the justified allowlist. Rewrite rules and both gates live in
`installer/references.py` and are parameterized per payload, so the plugin and
the machine payload share one judgement about what is a reference; neither
`installer/**` nor `machine-payload/**` is rewritten again on the way in, the
first because it is code and the second because it already passed the machine
profile's own gates.

Two further contract points exist because `claude plugin validate --strict`
rejects the alternative:

- `plugin.json` carries an `author` object alongside `name`, `version`, and
  `description`. `version` is stamped from `manifest.json["version"]`, and
  `prepare-release.py` fails closed when the two disagree.
- Every generated `commands/<short>.md` gets a frontmatter `description`
  injected from the authored neutral command source
  `.github/command-sources/sd-<short>.md`. A missing source file, missing
  frontmatter, or missing/blank `description` is a hard generator error, not a
  default; command adapters themselves stay generated from those same sources.

Plugin paths are shipped payload for release gating: `plugins/**`,
`.claude-plugin/marketplace.json`, and `.github/scripts/generate-plugin.py` [absent: removed with the release train in 0.72.0]
are classified by both payload classifiers (see Release Payload Gate below), so
changing them requires a manifest version bump and a matching changelog
heading. The fleet candidate digest is deliberately not extended — it binds
vendored-payload identity, which the plugin is not part of.

Reference files:

- `.github/scripts/generate-plugin.py` [absent: removed with the release train in 0.72.0]
- `.claude-plugin/marketplace.json`
- `plugins/sd/.claude-plugin/plugin.json`
- `tests/test_generate_plugin.py` [absent: removed with the release train in 0.72.0]

### Script Sibling Resolution

Shipped pack scripts resolve sibling pack scripts from their own file
location, never from repo-root `scripts/` literals: `SCRIPT_DIR` (from
`BASH_SOURCE`) in shell, `Path(__file__).resolve().parent` in Python, and
`import.meta.url` in Node. The toolchain's `run`/`run-python` handlers
route pack-named operands (basename matching `sd-ai-command-pack-*` or
`sd_ai_command_pack_*`, bare or `scripts/`-prefixed) through
`resolve_pack_script_operand`, which probes `SCRIPT_DIR` only — no CWD
probe, so a same-named file in the working directory can never shadow the
installed script — and fails with exit 127 naming the missing resolved
path. Non-pack operands pass through unchanged. This keeps one script set
valid in both layouts: fat installs (`SCRIPT_DIR` equals the consumer's
`scripts/`) and the plugin's `bin/` (resolved via PATH).

`tests/test_script_sibling_resolution.py` enforces the boundary: no
shipped script may build a sibling path from a repo-root `scripts/`
literal outside its per-file justified `ALLOWED_LITERALS` allowlist
(semantic data only — layout globs, changed-path classifiers, doctor
repository probes, static-analysis annotations — never invocation). The
`BIN_LITERAL_ALLOWLIST` in `installer/references.py` — one allowlist
shared by the plugin generator and the machine payload build, not a
generator-local copy — must stay set-for-set identical to that
allowlist; `tests/test_generate_plugin.py` [absent: removed with the release train in 0.72.0] pins the parity and fails on
stale entries in either direction.

## Machine-Scope Installer

`installer/machinescope.py` installs the `machine-other` partition slice plus
every `sharedRuntime` row into user-level destinations, so Gemini CLI and
OpenCode resolve the pack without a vendored copy. It is the non-Claude half of
the same release the plugin carries: the plugin bundles the engine, the payload,
and the `bin/sd-machine-install` bootstrap, so a machine needs no pack checkout.
`install.py --machine` is the checkout-side entry point — it stages the payload
from the working tree through `installer/machinestage.py` and hands the staged
root to the same engine, so a developer install and a plugin install converge on
the same tree. `--machine` is mutually exclusive with a repo target and the
platform flags, and `--home`/`--state-home` are only meaningful with it.

### Destination families

`installer/machinepayload.py` owns the family table, shared by the engine and by
the generator that bundles the payload, so the two inventories cannot drift. A
payload root is target-relative, and each target prefix maps to exactly one
family root:

| Family | Payload prefix | Destination root |
|--------|----------------|------------------|
| `agents-skills` | `.agents/skills/` | `<home>/.agents/skills` |
| `agents-bin` | `scripts/` | `<home>/.agents/bin` (executable) |
| `agents-docs` | `docs/` | `<home>/.agents/docs` |
| `gemini-commands` | `.gemini/commands/` | `<home>/.gemini/commands` |
| `opencode-commands` | `.opencode/commands/` | `${XDG_CONFIG_HOME:-<home>/.config}/opencode/commands` |

A target matching no family is a build error in the generator and a fail-closed
runtime refusal in the engine — never a guess. OpenCode reads its global
commands from the XDG config root, so `XDG_CONFIG_HOME` is honored when it is
absolute rather than hardcoding `~/.config`; `~/opencode/` is an unrelated
artifact and is never a destination. The home directory comes from `Path.home()`
(or the explicit `--home`), never a raw `$HOME` read, and an unresolvable home
is an error: Gemini's own fallback to a temporary directory is treated as
unsupported rather than writing a payload that vanishes on reboot. Executability
is derived from the family, not from the source file's mode, so a checkout that
lost its mode bits still produces the same payload digest, and
`sd_ai_command_pack_*.py` library modules stay non-executable exactly as they do
in the plugin's `bin/`.

`--home` means "treat this directory as the home directory". An ambient
`XDG_CONFIG_HOME`/`XDG_STATE_HOME`/`SD_AI_COMMAND_PACK_STATE_HOME`/`LOCALAPPDATA`
describes the *real* home, so the CLI drops any such override that does not
already resolve inside the given home; otherwise a scratch-prefix install would
scatter commands or its receipt outside the prefix it was told to use. An
explicit `--state-home` outranks the ladder and is never dropped.

### Plan before apply, and the intent journal

Phase 1 classifies every payload target against the receipt and the disk, phase
2 applies, phase 3 commits the receipt. Nothing is written until every conflict
is known, so a refusal can never leave a machine half-installed. The
classification is `owned-current` (receipt-owned and already matching the new
payload), `owned-stale` (matches the old receipt entry), `absent`, `drifted`
(receipt-owned, matching neither), `unowned` (exists, not in the receipt), or
one of `symlink` / `symlink-parent` / `not-a-file`. Any `drifted` or `unowned`
path refuses the whole run before the first write, naming every conflicting
path; `--force` displaces those after copying each one to a `.bak` sibling that
the receipt records. A file whose receipt entry already carries a backup keeps
that first one: a second copy would record the payload a previous forced run
wrote and strand the user's own content under a name nothing explains.
`--force` never displaces the symlink and non-file statuses: those cannot be
backed up and restored faithfully, so allowing them would make `remove`'s
restoration promise a lie.

Byte identity alone never proves authorship. A pre-existing user file identical
to the payload must not be adopted, because a later `remove` would delete
something the installer never wrote. The only evidence that admits a
receipt-absent path is the **intent journal**: `machine-install.intent.json`,
written atomically beside the receipt before the first write and deleted after
the receipt commits. On rerun, a receipt-absent path that matches the new
payload classifies `owned-current` only when a journal carrying the same
`payloadDigest` lists it — the signature of an interrupted run of this exact
payload. No journal, an unreadable journal, or a journal for a different payload
means `unowned`, and the run refuses without `--force`. A journal written for a
different payload is discarded with a diagnostic rather than partially trusted.

### Receipt

The receipt is `machine-receipt.json`, schema version 1: `schemaVersion`,
`packVersion`, `payloadDigest`, `installedAt`, `sourceRoot`, and `files[]` of
`{family, path, digest, executable}` plus an optional
`backup: {path, digest}` recorded when `--force` displaced a pre-existing file.
`payloadDigest` is the canonical, domain-separated payload identity from
`installer/machinepayload.py` (sorted targets, executable bits, contents). It is
computed from whichever payload root is being read, never stamped into one, so a
payload staged from a checkout and the payload the plugin bundles yield the same
value exactly when their bytes agree — which is what makes `status --payload` a
real comparison rather than a version-string check. It is deliberately *not* the
release-candidate payload digest in `sd_ai_command_pack_fleet_lib`, which
identifies a manifest and its sources; the domains differ so the two can never
be compared by accident.

The receipt authorizes overwrites and deletes, so it is validated like untrusted
input on every load: `family` must be a known family, `path` must be relative,
normalized, and traversal-free, and it must still resolve inside that family
root; recorded backup paths are validated the same way; a receipt file that is
itself a symlink is refused before it is read. One invalid entry invalidates the
whole receipt — there is no partial trust, because a receipt half-honored is a
receipt that can direct a write outside the family roots. A parent directory
that turned into a symlink after install can still satisfy containment — one
pointing back inside the root does — so it is caught a step later, by the
planner, which neither writes nor deletes through it.

The receipt and the intent journal live in the `machine/` subdirectory of the
shared private state root (`SD_AI_COMMAND_PACK_STATE_HOME`, `XDG_STATE_HOME`,
the Windows local-app-data path, then `~/.local/state/sd-ai-command-pack`),
resolved through the shipped helper library's `resolve_state_root` rather than a
second implementation, and created `0700` and non-symlink through
`ensure_private_directory`. The engine loads that helper by path from `scripts/`
or `bin/` beside the package, because it is a shipped script library and not an
`installer` module.

### Provisional platforms fail closed

Every payload root carries a `partition.json` copy, and the engine gates the
payload through it: a target belonging to a platform whose `platforms.<id>`
entry is `provisional: true`, or that is not `machine` scope at all, is refused
by name rather than installed. The gate travels with the payload, so a plugin
install enforces the same dispositions as a checkout install with no partition
lookup of its own. `load_payload` reports every refusal at once instead of
stopping at the first.

### Row removal and `remove`

Paths in the old receipt that the new payload no longer ships are deleted only
when they still match their receipt entry byte-for-byte and mode-for-mode;
anything else is left in place with a diagnostic. A removed row carrying a
verifiable backup restores its displaced original instead of being deleted,
because the new receipt is about to forget that backup.

`sd-machine-install remove` is the rollback commitment, and its "clean machine"
claim is precise: it deletes the files this receipt recorded installing, and it
restores the files this receipt recorded displacing, from digest-verified
backups. It restores nothing it has no backup record for. Every refusal is
decided before the first deletion; a drifted or missing-backup path refuses
without `--force`, a path whose parent became a symlink after install is never
deleted through with or without `--force`, and restoration renames the `.bak`
back into place so bytes and mode return together. Emptied directories are
pruned up to and including each family root, and no further: `~/.agents` is the
shared parent of three families and other tools' territory, so it stays even
when every family under it is gone.

### Update sequence

`sd-ai-command-pack-pack-update.sh` (shipped in the plugin's `bin/`) is the one
machine update action: `claude plugin update <plugin>@<marketplace>`, then
resolve the **new** plugin root from `claude plugin list --json` — never the
running script's own location, because that copy lives in the old root — then
run `<new-root>/bin/sd-machine-install install` from the resolved root, then
report the plugin version and the receipt version. A missing, duplicated, or
path-less plugin entry fails with its own exit code and runs no install. Both
halves are idempotent and the receipt only advances on success, so an update
interrupted between them is visible as version skew and a rerun converges.

### `sd-status` machine-scope line

The status collector reads the receipt directly through the engine — the shared
state ladder finds it, no plugin required — and reports `machineScope` with
`state`, `packVersion`, `pluginVersion`, and a separate `comparison`. `state` is
`none` (the engine positively reports no install), `installed`, `invalid` (a
malformed receipt, which is an anomaly rather than an absence), or `unavailable`
(the collector could not consult the engine at all: no rung of the engine
ladder below yielded a usable `installer/` package, an engine that raised, or
a schema it does not recognize) —
the same name, meaning, and missing-helper trigger the `workLoop` and
`recoveryArtifacts` ledgers already use. `pluginVersion` is `unavailable` on
*any* discovery failure: no `claude` on PATH, a nonzero exit, unparsable output,
a missing or duplicated entry, or an entry without a version. `comparison` is
`current` only when both versions are known and equal, `skew` when they are
known and differ, and `unknown` whenever either side is unavailable — a broken
CLI can never masquerade as an up-to-date machine. The line is advisory and does
not change the exit status; `invalid` is promoted into `anomalies` like the two
ledgers above it, so `--expect-clean` gates on it.

### Machine-scope engine resolution

#### 1. Scope / Trigger

`machine_scope_api()` imports the machine-scope engine. It used to look in
exactly one place — `installer/machinescope.py` beside the directory holding
the running script — which is an infra-integration contract, so this carries
code-spec depth. That single rung is wrong for one shipped arrangement: a
machine install puts the collector at `~/.agents/bin/`, so the arithmetic
yields `~/.agents`, which ships no `installer/` at all. Because the `sd-status`
skill routes thin consumers to precisely that copy, the row was permanently
`unavailable` for the documented path (issue #496), hiding a real version skew.

#### 2. Signatures

```python
def machine_scope_api(
    *, environ: Mapping[str, str] | None = None
) -> tuple[Any, str, Path, list[dict[str, str]]]:  # module, rung, root, refusals

def machine_engine_candidates(
    script: Path, environ: Mapping[str, str]
) -> list[tuple[str, Path]]                        # ordered, deduped

def machine_engine_refusal(root: Path) -> str | None   # None means accepted
```

The return type is a tuple, not a module. Any caller — including a test that
patches `machine_scope_api` — must supply the whole tuple; a bare module
raises `TypeError: cannot unpack non-iterable type object`.

#### 3. Contracts

Rungs, in order. The first accepted candidate wins:

| rung | root | gated |
| --- | --- | --- |
| `adjacent` | `Path(__file__).resolve().parent.parent` | no |
| `path` | parent of each `path_pack_bins()` entry, in `PATH` order | yes |

`machine_receipt_state()` and `collect_machine_scope()` both carry
`engineRung` (`"adjacent" | "path" | None`), `engineRoot` (string or `None`),
and `engineRefusals` (bounded list of `{root, reason}`). All three keys are
present on **every** branch, including the `unavailable` one — the caller
reads them by name, and a partial shape turns a reportable failure into a
`KeyError` inside a read-only status run. The keys are additive; an older
reader that ignores them is unaffected.

No new CLI flag, configuration key, or environment variable. The ladder is
discovery, not policy; `environ` is read, never mutated.

#### 4. Validation & Error Matrix

The `path` rung imports executable Python from a directory `PATH` names, so it
is gated. Refusal conditions, each reported rather than silently skipped:

| condition | result |
| --- | --- |
| `installer/__init__.py` or `installer/machinescope.py` missing or not a regular file | refused — a lone dropped module is not a package |
| neither `manifest.json` naming `sd-ai-command-pack` nor `.claude-plugin/plugin.json` naming `sd` | refused: `no pack identity` |
| root, `installer/`, or `machinescope.py` carries `stat.S_IWOTH` | refused: `world-writable` |
| no rung accepted | `RuntimeError` naming every candidate tried and each refusal |

The `adjacent` rung is deliberately **not** gated: it is the tree already
executing, and gating it would make the collector refuse to run from a checkout
the user already trusts enough to have invoked.

A refusal is never swallowed. Skipping one silently degrades to the same bare
`unavailable` this ladder exists to remove, and hides a directory that had no
business being on `PATH`.

#### 5. Good/Base/Bad Cases

- **Good**: pack checkout or plugin root — resolves through `adjacent`, and the
  rendered line is byte-identical to before this change.
- **Base**: machine install at `~/.agents/bin` with a trusted pack `bin/` on
  `PATH` — resolves through `path`; the line gains `[engine via path: <root>]`.
- **Bad**: a world-writable or unvouched root on `PATH` — refused, recorded in
  `engineRefusals`, and rendered as `[refused <root> (<reason>)]`.

#### 6. Tests Required

In `tests/test_status.py`, with assertion points:

- machine-install arrangement resolves — **must fail before the fix**;
- checkout resolves through `adjacent`, asserted on the *resolved path*, not on
  success alone;
- symlinked `~/.agents/bin` still served by `adjacent` (`resolve()` follows it);
- **both** identity spellings accepted — see the gotcha below;
- unvouched and world-writable roots refused, with the reason asserted;
- candidates tried in `PATH` order;
- the no-rung `RuntimeError` names every candidate;
- `sys.path` restored on the success **and** the import-failure exit — evict
  `installer*` from `sys.modules` first, or a cached module makes the broken
  fixture import cleanly and the test asserts nothing;
- end to end: `collect_machine_scope` over the thin-consumer arrangement
  renders a real row, not `unavailable`. The unit tests prove the ladder
  resolves; only this one proves the row a reader sees changed.

#### 7. Wrong vs Correct

> **Warning**: the plugin cache root — the one arrangement the `path` rung
> exists to reach — carries **no** `manifest.json`. Measured 2026-08-25:
> `~/.claude/plugins/cache/sd-ai-command-pack/sd/<version>/` has
> `.claude-plugin/plugin.json` and `installer/`, and no `manifest.json`. A gate
> keyed on `manifest.json` alone rejects the target root and ships a fix that
> fixes nothing, while every test written against a checkout still passes.

##### Wrong

```python
if not (root / "manifest.json").is_file():
    return "no pack identity"   # rejects the plugin cache root
```

##### Correct

```python
if not machine_engine_root_identified(root):   # manifest.json OR plugin.json
    return "no pack identity"
```

##### Wrong

```python
return {..., "detail": receipt["detail"], "pluginId": MACHINE_PLUGIN_ID, ...}
# provenance stops at the receipt; the row renders as an ordinary line
```

##### Correct

```python
"engineRung": receipt["engineRung"],
"engineRoot": receipt["engineRoot"],
"engineRefusals": receipt["engineRefusals"],
```

`collect_machine_scope()` rebuilds its dict field by field rather than
spreading the receipt, so a new receipt key that is not named here is dropped
between the receipt and the section — which renders as a normal report that
silently hides the very skew the key was added to expose.

### `sd-status fleet` install modes, pins, and skew

Fleet mode collects `collect_machine_scope` **once per run** against the pack
root — never once per consumer; each consumer row keeps
`include_machine_scope=False`, so no extra `claude plugin list --json`
subprocess is spawned per member. The result is published under the same
`machineScope` key local mode uses, and a call-count test, not convention,
holds the once-per-run property.

Each consumer row gains two additive fields. `installMode` is the registry's
`mode` value; the row field is deliberately *not* spelled `mode`, because the
fleet payload already carries a top-level `"mode": "fleet"` discriminator.
`pin` is `null` for a fat consumer and `{state, version, source, detail}` for a
thin one, where `state` is `present`, `absent`, or `unreadable` — never
silently empty. `read_json_object` collapses a missing file, an I/O error, and
invalid JSON into one `None`, and `collect_versions` additionally falls back to
`.sd-ai-command-pack/manifest.json`, so the pin reader does its own read rather
than reusing either. It resolves the path with `resolve(strict=True)` and
`relative_to(<consumer root>)` before parsing, so a relative `pinPath` that
leaves the checkout through a symlink is `unreadable` with a reason, never
followed.

Version judgement follows the mode split, in both the JSON rows and the human
attention counter: a fat consumer keeps installed-versus-target tree drift, and
a thin consumer is judged by pin versus machine install, because it vendors no
tree to diff. Three further comparisons produce **fleet-level** rows — pin
versus machine install, machine install versus target, and
`machineScope.comparison` for plugin versus receipt — and *every* fleet-level
row is gated on the registry containing at least one thin consumer. An all-fat
registry therefore emits no machine rows at all, which is what makes a schema-5
registry naming no `mode` report identically to the schema-4 registry it
replaced. An unavailable machine inventory with thin consumers present reports
`unavailable` plus a follow-up; it is never rendered as agreement.

Follow-ups are derived from the **complete** row set and only the human
`nextSteps` list is truncated to `HUMAN_ITEM_LIMIT`, with skew rows ranked ahead
of advisory rows. Deriving `F-*` rows from the truncated list — the prior
behavior — could silently drop a skew row once enough missing/dirty/divergent
consumers existed.

The status payload's own `SCHEMA_VERSION` stays **2**: this is a hard
constraint, not a convenience.
`templates/scripts/sd-ai-command-pack-housekeeping-result.py:43,173` requires exactly 2
by equality, so every fleet addition is an optional field or an extra row.
Removing or retyping a field would require coordinating that consumer first.

Reference files:

- `installer/machinescope.py`
- `installer/machinepayload.py`
- `installer/machinestage.py`
- `installer/references.py`
- `templates/scripts/sd-ai-command-pack-status.py`
- `templates/scripts/sd_ai_command_pack_fleet_lib.py`
- `templates/scripts/sd-ai-command-pack-pack-update.sh`
- `tests/test_machine_installer.py`, `tests/test_machine_stage.py`,
  `tests/test_references.py`, `tests/test_pack_update.py`

## Release Payload Gate

Any pull request that changes shipped payload must carry the release ledger
with it. Shipped payload means `templates/**`, `plugins/**`,
`docs/SD_AI_COMMAND_PACK.md`, `manifest.json`,
`.claude-plugin/marketplace.json`, or `.github/scripts/generate-plugin.py` [absent: removed with the release train in 0.72.0].
The local full-check and the CI `Release payload gate` both
run the same pack-source drift gate against the PR base:

- payload changes require a `manifest.json` version bump;
- a version bump requires the top `CHANGELOG.md` heading to match
  `## <version> - YYYY-MM-DD`;
- `make release-prep` is the canonical maintainer entry point. It generates
  before self-sync because generated command surfaces embed the pack version,
  permits only the expected stale-ledger state to reach fleet validation,
  reuses current exact-payload evidence, and finishes with `make check`;
- non-payload changes must pass without a release bump.

### Release Preparation Contract

1. **Scope / Trigger**: Before publishing a pack release, use one maintainer
   entry point to generate and synchronize local surfaces, refresh derived
   knowledge, reject cheap release defects, refresh fleet evidence only when
   necessary, and then run the authoritative full check.
2. **Signatures**:
   - `make release-prep` is the public maintainer command and invokes the
     source-only `.github/scripts/prepare-release.py` [absent: removed with the release train in 0.72.0] with `$(VENV_PYTHON)`.
   - `prepare_release(root: Path = ROOT, python: str = sys.executable) -> None`
     performs preparation; the Make target invokes `$(MAKE) check` only after
     it exits successfully.
3. **Contracts**:
   - Run command-surface generation, surface partitioning, plugin generation,
     the plugin/pack version consistency check, forced self-install, spec-KB
     refresh, and shipped-surface inspection in that order. The chain invokes
     each generator directly; it never shells out to `make generate`.
   - Consume schema-version-1 shipped-surface JSON with exact scalar and
     container types, complete findings, a consistent status/exit pair, and a
     string-array `changedPaths` field.
   - Permit fleet validation only for one `provenance.candidate-stale` finding
     whose path is `docs/fleet/candidate-validation.json` [absent: removed with the release train in 0.72.0] and whose relation is
     `requires-release-evidence`. Clean evidence skips fleet validation.
   - A shipped-payload diff requires a manifest version change relative to the
     report's resolved base and a matching top `CHANGELOG.md` heading. The
     optional `SD_AI_COMMAND_PACK_FULL_CHECK_RELEASE_BASE_REF` selects the base
     when automatic base resolution is unavailable.
   - After fleet validation, shipped-surface closure must be clean. Final
     `make check` remains authoritative.
4. **Validation & Error Matrix**:
   - Generator, self-install, KB refresh, fleet validation, or final check
     nonzero/missing/timeout -> stop immediately with a controlled failure.
   - Malformed JSON, wrong types including boolean-as-integer, truncation,
     status/exit disagreement, inconsistent counts, or any extra finding ->
     fail before fleet validation.
   - Missing release base, unchanged version, malformed manifest, symlink or
     oversized release input, or mismatched changelog heading -> fail before
     fleet validation.
   - Candidate refresh succeeds but closure remains stale -> fail; never run
     final `make check` on unresolved evidence.
5. **Good / Base / Bad Cases**:
   - Good: shipped payload and version ledger are aligned, stale candidate
     evidence is refreshed once, closure becomes clean, and `make check`
     passes.
   - Base: no shipped payload changed and candidate evidence is already
     current, so the expensive fleet validator is skipped before `make check`.
   - Bad: run fleet validation despite unrelated closure findings, accept a
     boolean count as an integer, or treat preparation as the final verdict.
6. **Tests Required**: Assert exact step order and fail-fast behavior; current
   and stale candidate branches; failed and still-stale candidate refreshes;
   malformed, inconsistent, truncated, extra, and wrong-type surface reports;
   missing, nonzero, and timed-out subprocesses; regular, symlinked, and
   oversized release inputs; version/base/changelog gates; and Make target
   ordering with recursive `$(MAKE) check` after the orchestrator.
7. **Wrong vs Correct**:

   ```text
   Wrong: run the full fleet for every documentation-only change, then discover
          a missing version bump or unrelated closure defect afterward
   Correct: prepare deterministic local surfaces, fail closed on cheap gates,
            refresh only stale exact-payload fleet evidence, then run make check
   ```

Wire any future release-gate changes through the shared
`run_pack_source_drift_gates` implementation in
`templates/scripts/sd-ai-command-pack-full-check.sh` and its template twin. Do not create
a separate CI-only interpretation of shipped-payload paths. Keep the
source-only preparation preflight's payload boundary aligned with that
authoritative final gate; preparation is an early cost guard, not a weaker
release verdict.

### Release Candidate Fleet Ledger Contract

1. **Scope / Trigger**: When a release changes the installable payload, validate
   the working candidate against disposable clones of every consumer before
   merging or tagging. This catches consumer integration failures without
   writing into active consumer worktrees.
2. **Signatures**:
   - `sd-ai-command-pack-fleet-candidate-check.py [--consumer NAME] [--json]`
     performs validation; `--check-ledger` performs read-only evidence checks.
   - `payload_digest(manifest, source_loader) -> str` binds evidence to every
     unique manifest source's bytes and executable bit plus canonical manifest
     JSON.
   - `validate_candidate_ledger(...) -> list[str]` returns every ledger defect;
     callers fail when the list is non-empty.
   - `create-release-tag.py --base REF --head REF` validates the ledger from the
     exact committed head tree before creating `v<manifest-version>`.
3. **Contracts**:
   - `docs/fleet/consumers.json` schema version 5 requires unique consumer
   names that are safe non-path identifiers, GitHub slugs, rollout priorities,
   bounded positive timeouts,
     platform lists, explicit `candidatePrepare` argv arrays that may be empty,
     and `candidateChecks` as non-empty argv arrays.
   - Schema version 5 adds two optional per-consumer fields. `mode` is
     `fat` (default) or `thin`; any other value is a `FleetConfigError` naming
     the consumer. `pinPath` (default `.sd-ai-command-pack/provenance.json`) is
     a non-empty relative path inside the consumer checkout; POSIX-absolute,
     Windows-absolute, and `..`-bearing values are rejected at parse time. Both
     defaults reproduce schema-4 behavior exactly, so a schema-5 registry that
     names neither field reports identically to the schema-4 registry it
     replaces. Parsing still demands exact `schemaVersion` equality, so a
     schema-4 file is rejected after the bump by design, as it was for 3 -> 4.
   - Schema version 5 also requires `rolloutPolicy`: a bounded default
     concurrency, a first sequential `canary` cohort, and ordered cohorts that
     include every consumer exactly once in rollout-priority order.
   - `docs/fleet/candidate-validation.json` [absent: removed with the release train in 0.72.0] schema version 4 records
     `packVersion`, `payloadDigest`, `fleetManifestDigest`, `validatorDigest`,
     and one row per consumer with its checked base commit, exact preparation
     and check command arrays, and a `reasons` array.
   - **Consumer status is a three-value enum: `passed`, `failed`, `blocked`**
     (schema 4). A consumer-owned precondition — references the pack does not
     own, a dirty worktree, a manifest file missing from the checkout — must
     neither fail the pack's release nor be recorded as a pass, because both
     answers are lies in opposite directions. Failing on them makes every pack
     release hostage to eight consumer backlogs (207 such references in
     `anomaly-metric-creator` alone), and the first thing anyone does with a
     release gate that cannot be satisfied is turn it off. Recording them as
     `passed` puts a row in the ledger certifying a thin validation the
     consumer's own repository cannot yet support.
     - `passed` — every step ran and succeeded. Release-prep continues.
     - `failed` — a step ran and failed, or the pack itself is defective.
       Release-prep exits nonzero.
     - `blocked` — a consumer-owned precondition stopped the lane; nothing was
       falsely certified. Release-prep continues, with the reasons recorded.
     - `blocked` **requires a non-empty `reasons` array of non-empty strings**.
       `validate_candidate_ledger` rejects a `blocked` row with an absent,
       empty, or non-string-bearing `reasons`. An unexplained skip is the exact
       failure mode the third value exists to prevent, so a `blocked` row that
       does not say why is a validation error rather than a lenient pass.
   - **The lane branches on the clone's pin, never on the registry's `mode`.**
     `conversion.thin_pin_state(clone)` is the same predicate `install.py`
     itself branches on. The registry records what the pack *believes*; the pin
     records what the checkout *is*, and they disagree by design during the
     window between a consumer's conversion PR merging and the registry flip
     landing — a skew `flip_registry_mode` documents as accepted. Branching on
     the registry would aim a `--platform` install at a genuinely thin checkout
     during precisely that window, and `install.py`'s thin-refresh branch
     rejects `--platform` outright. A `malformed` pin fails rather than
     guessing a shape, matching `install.py`, which refuses in both directions
     for that state. A pin/registry disagreement is recorded as a note.
   - **A pack defect is measured after the conversion's rewrite, not before.**
     The resweep's `packDefects` bucket is a *pre-rewrite* count: it records
     pack-owned content that cites a removed path and never calls
     `rewrite_text`. The conversion does — every kept text file passes through
     `rewrite_text(text, profile=THIN_PROFILE, key=entry)`, which repoints
     `scripts/sd-ai-command-pack-<name>` to `~/.agents/bin/<name>` and the pack
     docs to `~/.agents/docs`. So the raw count is not evidence of a release
     defect. The gate rewrites each flagged file under `THIN_PROFILE` and fails
     only on what `check_text_residue` still rejects; the raw count is recorded
     as a note so it stays visible without being a verdict. Measured on the
     real fleet: 14-16 pre-rewrite citations per consumer, **zero** surviving.
     A glob such as `scripts/sd-ai-command-pack-*.py` is not a path the rewrite
     can repoint and does still fail — which is why the check is residue rather
     than "no citations at all".
   - **The resweep runs after the install, on a committed clone.** A pristine
     clone carries whatever pack version that consumer last installed, so a
     resweep there measures the previous release and attributes its defects to
     the candidate. Installing dirties the worktree and a dirty worktree is a
     blocker, so the disposable clone is committed first (`git add --all`, then
     a `--allow-empty` commit under an explicit non-user identity). The clone
     exists to be thrown away; committing is what makes "this tree contains the
     candidate" a fact the resweep can read rather than noise it must ignore.
   - **The thin artifact lane runs once per candidate run, before the
     per-consumer loop.** Three steps, all against the pack rather than any
     consumer: `generate-plugin.py --check --root <pack>`, which builds the
     plugin and compares it against the committed tree offline and writes
     nothing — catching both a generator failure and drift, and the reason the
     lane needs no scratch copy of the checkout; `claude plugin validate
     <pack>/plugins/sd --strict`; and `install.py --machine` into
     `<work_root>/home` with `--state-home <work_root>/state`. Once, not once
     per consumer: the plugin and the machine payload do not vary by consumer.
     Its failure is likewise not attributed to a consumer, because nothing
     about a consumer caused it.
     - An unresolvable `claude` is reported as `unavailable` and **fails**. A
       release gate that reports success where it did not run is the defect the
       gate exists to prevent, so there is no skip flag and no degrade-to-fat.
     - `claude --plugin-dir` is not a substitute for any of this. Measured,
       `claude --plugin-dir /nonexistent/plugin/path -p "say ok"` answers
       normally and exits 0, so it has no failure channel at all, and its only
       non-interactive form requires a billable, credentialed model call.
     - A failed machine install hands back no prefix. Reporting one would point
       the thin lane's `HOME` at an empty directory, where every lookup
       resolves nothing.
   - **A thin clone's registered commands run with `HOME` set to the run's
     scratch prefix; a fat clone's run with the inherited `HOME` unchanged.**
     A converted consumer's pack helpers resolve through `~/.agents/bin`, so
     without the redirect its checks would silently exercise whatever pack the
     invoking machine already has installed and the run would certify someone
     else's release. `Path.home()` honors `HOME`, which is what makes the
     redirect work without a raw environment read in the resolver. The
     override belongs to the thin lane alone — a shared builder that set `HOME`
     for both lanes would pass any test written against outcomes, so the
     contract is asserted on the child environment.
   - **A thin clone whose registered check names a manifest-declared path the
     conversion removes is `blocked`, not `failed`.** The `agents-bin` family
     relocates `scripts/` targets to `<home>/.agents/bin`, so a registry row
     still invoking `scripts/sd-ai-command-pack-<name>` by repository-relative
     path names a file the conversion deleted. The pack built correctly and the
     install succeeded; what is stale is that consumer's registry record, and
     the fix belongs to its conversion PR. A missing path the pack does *not*
     own is a different thing entirely — the consumer's own check is broken,
     and that stays a failure.
   - **The loop never converts a consumer and never writes this pack's
     registry.** `install.py --thin --consumer <name>` calls
     `flip_registry_mode` on success, which would mutate
     `docs/fleet/consumers.json` in the source checkout. A validator that
     mutates the source is not a validator. No install the loop issues carries
     `--consumer`, and the property is checked as **byte-identity** of
     `docs/fleet/consumers.json` across a full run: no record carries a `mode`
     key, so a parsed comparison would compare eight reader-supplied defaults
     and pass whatever the run did to the file.
   - `validatorDigest` (added in schema 3) exists because ledger currency
     decides whether `make release-prep` runs the fleet validation at all
     (`prepare-release.py:338` [absent: removed with the release train in 0.72.0] returns before `CANDIDATE_CHECK`), and the other
     three fields cannot see the validator itself:
     `scripts/sd-ai-command-pack-fleet-candidate-check.py` [absent: removed with the release train in 0.72.0] has no `manifest.json`
     row and no `templates/` twin, so `payload_digest` — which reads each row's
     `source` — is blind to it. Editing the validator moved nothing, the ledger
     stayed current, and release-prep skipped the very code the edit changed.
     `CANDIDATE_VALIDATOR_SOURCES` names exactly the sources in that gap;
     `sd_ai_command_pack_fleet_lib.py` is deliberately excluded because its
     manifest row's `source` is its authoritative `templates/` twin, so
     `payloadDigest` already covers it. Naming it would hash the `make sync`
     mirror instead — a weaker answer to a question already answered.
   - The validator digest is composed like `payload_digest` — sorted,
     path-qualified, one `sha256` per source under a distinct domain separator —
     **minus the executable marker**. That asymmetry is deliberate: the
     validator is invoked as `sys.executable <path>` (`surface-check.py:679`),
     never as a bare executable, so hashing its permission bit would let
     `chmod +x` invalidate a ledger whose validator is byte-identical.
     `payload_digest` is right to include it for files that *are* executed
     directly.
   - Signatures: `candidate_validator_digest(source_loader: Callable[[str],
     bytes]) -> str` takes a loader, not a root, so a caller validating a ledger
     recorded at some commit supplies that commit's blobs;
     `filesystem_candidate_validator_digest(root: Path) -> str` is the
     working-tree loader and resolves `root` itself before its containment
     check, because comparing a resolved source path against an unresolved root
     rejects every symlinked prefix (`/var` on macOS).
     `validate_candidate_ledger` takes a required keyword-only
     `expected_validator_digest`.
   - **Wrong vs correct at the commit-scoped site.** `release_identity.py`'s
     `verify_candidate_ledger_at_commit` reads its ledger from a commit, so it
     must pair that ledger with `candidate_validator_digest_at_commit`, never
     the working tree. Feeding it the working tree reports an ordinary
     post-release edit to the validator as tampered release evidence — a
     failure that reads as a security event rather than the design error it is.
     The two working-tree call sites correctly use the filesystem loader.
   - Validation and error matrix for ledger currency: a `schemaVersion` other
     than the current constant, an absent `validatorDigest`, or a differing one
     each mark the ledger stale, which makes the validator run — the intended
     outcome, not a failure. An unreadable or absent validator source in the
     working tree raises `FleetConfigError`; one absent at a historical commit
     raises a `ReleaseIdentityError` naming the validator specifically, and
     never falls back to the working tree. Both fail closed: "assume unchanged"
     is the one behavior that would reintroduce the defect.
   - **Rename the subject, do not re-wrap the exception.** The commit-scoped
     loader reuses `payload_source_at_commit`, whose diagnostics all name a
     *pack manifest source* — a row that has never existed for the validator.
     It is corrected by passing a `subject` through to each raise
     (`MANIFEST_SOURCE_SUBJECT` / `VALIDATOR_SOURCE_SUBJECT`), not by catching
     `ReleaseIdentityError` at the call site: absence is one of six failure
     modes there — the others are an invalid symlink, a non-UTF-8 symlink
     target, a non-directory traversal, a non-regular file, and a symlink cycle
     — and a single catch can assert only one reason for all of them. Reporting
     a path occupied by a regular file as "absent" sends a reader after the
     wrong defect. `test_commit_digest_keeps_a_non_absent_reason_for_the_validator`
     pins it: the wrapping form fails it, the subject form passes.
   - A stale ledger surfaces through the existing `provenance.candidate-stale`
     finding against `docs/fleet/candidate-validation.json` [absent: removed with the release train in 0.72.0], not a new code.
     `_candidate_refresh_required` (`prepare-release.py:109-160` [absent: removed with the release train in 0.72.0]) validates that
     finding's exact shape and raises on anything else, so a new code would fail
     release-prep with "surface closure contains a non-candidate finding"
     instead of triggering validation. Reusing the code is a compatibility
     requirement, not a shortcut.
   - Candidate execution orders clone, install, audit, preparation, then
     checks. Preparation may mutate only the disposable clone; candidate checks
     remain read-only. Repositories without a preparation step declare `[]`
     rather than relying on auto-detection.
   - When onboarding a consumer, derive its declarations from the repository's
     clean-clone CI contract. Put deterministic prerequisites such as a locked
     dependency install in `candidatePrepare`, then declare the repository's
     CI-equivalent read-only gates in `candidateChecks`; do not infer or inherit
     another consumer's preparation command.
   - Candidate clone commands place `--` before the discovered origin URL so a
     malformed local remote beginning with `-` cannot inject Git options.
   - Candidate subprocess environments prepend the selected Python directory
     without adding an empty `PATH` entry when the inherited value is unset or
     empty.
   - Payload digest records delimit the executable marker on both sides before
     the content hash. Tag-time validation resolves tracked in-repo symlink
     chains from the exact commit tree and hashes the resolved regular blob and
     its executable mode, matching working-tree candidate validation.
   - A full all-pass run replaces the ledger atomically. Filtered or failing
     runs never replace canonical evidence.
4. **Validation & Error Matrix**:
   - Invalid fleet schema, duplicate priority/name, unsafe command shape, or
     unreadable payload source -> configuration error and exit 2.
   - Clone, install, audit, preparation, timeout, missing executable, or
     candidate-check failure -> report the consumer failure, continue the
     fleet, and exit 1.
   - Missing, malformed, partial, failing, or digest-stale ledger -> local/CI
     release gate and tag planner fail; no release tag is created.
   - `--consumer` combined with `--check-ledger` -> usage error; filtered runs
     are diagnostics and cannot certify a release.
5. **Good / Base / Bad Cases**:
   - Good: all disposable clones prepare and pass, and the committed ledger
     matches the exact release payload, fleet manifest, preparation, checks,
     and consumer set.
   - Base: a filtered diagnostic identifies one consumer issue while leaving
     the prior canonical ledger untouched.
   - Bad: prepare, validate, or install directly into a developer's active
     consumer checkout, hide a generator in `candidateChecks`, or accept a
     ledger generated for different payload bytes.
6. **Tests Required**: Cover schema and priority validation, argv execution
   without shell interpolation, disposable origin clones, timeout and command
   failures, full-fleet continuation, atomic ledger preservation, every ledger
   drift dimension, source-only install-audit boundaries, full-check rejection,
   and exact-commit tag-planner rejection. For each newly onboarded consumer,
   assert its exact identity, platforms, priority, cohort, timeout, preparation,
   and checks in the checked-in inventory regression. Keep per-file coverage
   floors for the validator and shared fleet library at 90% or higher.
7. **Wrong vs Correct**:

   ```text
   Wrong: tag the version, then discover compatibility one consumer PR at a time
   Wrong: let a mutating generator masquerade as a candidate check
   Wrong: let a partial diagnostic overwrite the release evidence
   Correct: prepare and validate the working payload in disposable origin clones,
            commit the all-pass ledger, merge, let main CI tag that exact commit,
            then refresh consumers in explicit fast-canary priority order
   ```

### Fleet Release Identity Guard

1. **Scope / Trigger**: Before fleet preflight reports any consumer as mutable,
   prove the current source checkout is the published release named by
   `manifest.json`.
2. **Signature**:
   `sd-ai-command-pack-fleet-preflight.py [--remote REMOTE] [--json]`.
3. **Contracts**:
   - The local `v<version>` raw tag object must equal the exact tag ref
     advertised by the release remote, and the resolved tag commit must be an
     ancestor of the current checkout.
   - Tagged manifest version and exact-tree payload digest must equal the
     current manifest version and filesystem payload digest.
   - Candidate evidence validates at the tagged commit and again for the
     current payload and fleet manifest.
   - Later non-payload bookkeeping commits are allowed; `HEAD` need not equal
     the tag.
   - Preflight is read-only and does not fetch, create, move, or delete tags.
   - JSON schema version 1 wraps `releaseIdentity` and `consumers`; no consumer
     rows are emitted when identity verification fails.
4. **Validation & Error Matrix**: missing local or remote tag, local/remote tag
   mismatch, non-ancestor tag, version mismatch, payload mismatch, or stale
   tagged/current ledger -> controlled exit `1` before consumer inventory.
5. **Good / Base / Bad Cases**:
   - Good: local and remote raw tag objects agree, the resolved tag is an
     ancestor, and tagged/current manifest, payload, and candidate evidence all
     verify before consumer classification.
   - Base: the checkout contains later bookkeeping-only commits whose payload
     and candidate evidence still match the published tag.
   - Bad: a manifest version alone is treated as proof of release identity, or
     preflight fetches or mutates tag state while attempting verification.
6. **Tests Required**: cover valid identity, missing and rewritten tags,
   tagged version and payload mismatch, stale evidence, and post-release
   bookkeeping commits.
7. **Wrong vs Correct**:

   ```text
   Wrong: trust manifest.json or silently fetch tags before classifying consumers
   Correct: compare existing local and remote raw refs, then verify exact tagged and current evidence
   ```

### Fleet Consumer Review Classification

1. **Scope / Trigger**: After `sd-fleet-refresh` commits a consumer refresh and
   before it chooses the PR review profile, prove whether the exact head is a
   pure installer-managed integration update. Source-pack PRs and consumer
   branches containing repo-owned work remain on the normal remote-review
   path.
2. **Signatures**:
   - `sd-ai-command-pack-fleet-review-classify.py --consumer NAME --repo PATH
     --base-commit SHA [--remote REMOTE] [--json]` is a source-only, read-only
     classifier. Exit `0` means `integration-only`; exit `1` means
     `remote-review-required`.
   - The trusted fleet invocation of `sd-review` carries consumer, source
     root, full base SHA, release remote, and classified full head SHA as
     internal orchestration context. It is not a public adapter argument or an
     environment variable. `sd-review`'s `key=value` enum stays closed, so a
     `caller=` token on the command line is an unknown key rejected before the
     first gate. `sd-review-pr` accepts the same context until that surface is
     removed.
3. **Contracts**:
   - Reuse the release-identity guard, canonical fleet consumer/path/platform
     data, and authoritative `install.py --check --json` inspection with a
     passed exact audit before inspecting the diff.
   - Require a clean consumer tree, full base object ID, exact resolved head,
     and base ancestry. Read safe UTF-8 installed-target receipts at the base
     and current checkout; the allowlist is their union plus receipt,
     provenance, and installed manifest metadata.
   - Collect the committed diff with rename detection disabled, require it to
     be non-empty, and require every path to belong to the allowlist.
   - JSON schema version 1 records eligibility, exact base/head, release
     identity, installed version/platforms, sorted changed/allowed/disallowed
     paths, and bounded deterministic reasons.
   - The recheck procedure lives in `sd-fleet-refresh`, which owns the profile
     end to end; no shipping surface inlines the classifier, so it stays out of
     every payload closure. `sd-review` reruns classification through it and
     requires classified, local, and PR heads to match before suppressing a new
     configured remote-review request. It still runs local gates, advisory
     disposition, existing review and thread inspection, CI, learning, and
     watch. It does not run housekeeping or finish-work: under
     `defer-finish-work` it returns a typed deferral disposition and
     `sd-fleet-refresh` owns the call, including when the PR turns out to be
     already merged. A changed head must be reclassified.
   - Public `remote-review` forces the normal profile. No public
     `integration-only` switch exists.
4. **Validation & Error Matrix**:
   - Missing, malformed, stale, unsafe, dirty, non-ancestor, mismatched, or
     unavailable evidence -> controlled `remote-review-required`, never
     permission to skip review.
   - Any consumer-owned or unclassified changed path -> normal remote review.
   - A valid trusted context whose head no longer matches -> rerun or fall back
     to normal remote review; a user imitation of internal context -> argument
     error before review gates.
   - Existing actionable comments or unresolved threads block both profiles.
5. **Good / Base / Bad Cases**:
   - Good: a verified release refresh changes only paths vouched by safe base
     or current receipts, remains current under exact audit, and records zero
     new remote-review rounds while all integration gates still run.
   - Base: a retired managed target is deleted; the historical base receipt
     keeps that deletion eligible.
   - Bad: trust a scope label, current receipt alone, shortened SHA, collapsed
     rename, stale candidate ledger, or caller-provided integration-only flag.
6. **Tests Required**: Cover qualifying refreshes, retired targets,
   consumer-owned paths, dirty trees, unsafe and duplicate receipts,
   non-ancestor bases, stale release/candidate evidence, inspection and audit
   failures, missing commands and timeouts, deterministic JSON/exit behavior,
   source-only install-audit policy, generated mirror parity, and fail-closed
   skill orchestration bound to exact heads. Keep classifier coverage at 80% or
   higher.
7. **Wrong vs Correct**:

   ```text
   Wrong: skip Copilot because a refresh PR looks generated or carries a scope label
   Wrong: rerun source implementation review on every unchanged installed payload
   Correct: prove the exact head is receipt-bounded and release-current, skip only
            the new remote request, and retain every integration and merge gate
   ```

### Fleet Finding Interruption Classification

1. **Scope / Trigger**: After any verified finding appears during a fleet
   install, audit, consumer gate, review, or existing-feedback pass, classify
   rollout timing before watch, merge, or another consumer mutation. This gate
   chooses corrective-release timing; it never dismisses feedback or replaces
   thread settlement.
2. **Signatures**:
   - `sd-ai-command-pack-fleet-finding-classify.py --input PATH [--json]` is a
     source-only, read-only classifier. Input is strict schema-version-1 JSON
     with a non-empty `findings` array.
   - Each finding has unique safe ID, contract family, summary, evidence,
     reviewer, optional repository-relative path and positive line, optional
     blocker impact plus evidence, and optional explicit override plus
     rationale.
   - Exit `0` means `continue-with-follow-ups`; exit `1` means
     `pause-corrective-release`; exit `2` means `invalid-pause`.
3. **Contracts**:
   - Correctness, security, install/audit, and compatibility block by default.
     Hardening, style, test implementation, documentation, diagnostics, and
     consumer-unrelated findings defer by default. Concrete blocker impact may
     escalate; only explicit override data with rationale may replace the
     computed disposition.
   - Normalize reviewer, path, line, and summary into an exact-duplicate
     signature. The first observation owns timing and task identity. Duplicate
     observations inherit that policy but each remains visible for reply and
     allowed thread resolution.
   - JSON schema version 1 records owner rows, observation-to-owner mapping,
     default/computed/final dispositions, rationale, escalation and override
     evidence, counts, decision, and deterministic exit code.
   - Exit `0` still requires feedback replies, allowed thread resolution, and
     one follow-up per deferred owner when work remains. Exit `1` feeds blocker
     owners into one corrective campaign. The final fleet report records both
     owner classes, duplicates, overrides, and follow-up task identifiers.
   - The classifier never creates tasks, mutates repositories, posts replies,
     or writes candidate evidence. It remains outside the install manifest and
     is allowlisted only for source-checkout audit.
4. **Validation & Error Matrix**:
   - Unknown fields or families, empty or oversized text, unsafe IDs or paths,
     invalid lines, duplicate IDs, missing paired evidence/rationale, more than
     200 observations, malformed JSON, symlink input, or conflicting duplicate
     policy -> exit `2` and pause.
   - Any blocker owner -> exit `1`, including an explicitly upgraded default-
     deferred owner. All-deferred owners -> exit `0`, including an explicitly
     downgraded blocker whose rationale remains visible.
   - Missing command or malformed classifier output -> orchestration pauses;
     it never guesses a deferred result.
5. **Good / Base / Bad Cases**:
   - Good: three equivalent diagnostics observations map to one deferred owner
     and one follow-up while all three review threads receive replies.
   - Base: a documentation issue with proven destructive install impact
     escalates to a blocker and joins the single corrective campaign.
   - Bad: keyword-match reviewer prose, silently downgrade a blocker, create a
     patch release for every duplicate, or continue after invalid input.
6. **Tests Required**: Cover every family default, escalation, explicit
   upgrade and downgrade, exact duplicate ownership, conflicting duplicates,
   strict schema and path boundaries, symlink and malformed input, stable JSON
   and human output, exit codes, source-only audit policy, skill ordering, and
   generated mirror parity. Keep classifier coverage at 85% or higher.
7. **Wrong vs Correct**:

   ```text
   Wrong: every reviewer observation forces another fleet-wide patch release
   Wrong: deferred timing means ignore or auto-resolve the review thread
   Correct: classify canonical owners, settle every observation, and interrupt
            only for blocker owners or invalid evidence
   ```

## Manifest Path Safety

Validate manifest paths before any target-repo writes:

- `source` must stay inside the pack root and must not contain `..` path
  components after it is made relative to the pack root.
- `source` must also resolve inside the pack root so a template symlink cannot
  copy host files from outside the pack.
- `target` must be a relative path and must not contain `..` path components.
- `anchor` must be a relative path and must not contain `..` path components.
- Reject Windows drive and root anchors too, including drive-relative paths such
  as `C:tmp\pwn`, drive-absolute paths such as `C:\tmp\pwn`, UNC paths, and
  backslash-separated `..` traversal.

Keep these checks in `validate_manifest()` so malformed or hostile manifests
fail before target validation, selection, backups, or file copies.

Reference files:

- `installer/manifest.py`, `validate_manifest()`
- `installer/manifest.py`, `validate_relative_manifest_path()`
- `installer/manifest.py`, `validate_pack_source()`
- `tests/test_install_core.py`, `test_manifest_rejects_unsafe_target_paths`
- `tests/test_install_core.py`, `test_manifest_rejects_unsafe_anchor_paths`
- `tests/test_install_core.py`, `test_manifest_rejects_unsafe_source_paths`

## Target Validation

The installer requires `.trellis/config.yaml` [absent: target-repo Trellis path] in the target repository before
copying files. Keep that validation early in `main()` through
`require_trellis_repo()` so invalid targets fail before side effects.

Reference file:

- `installer/manifest.py`, `require_trellis_repo()`

## Installer Inspection Contract

1. **Scope / Trigger**: Use this contract whenever changing the read-only
   installer inspection path, its receipt parsing, report schema, audit
   delegation, or exit semantics. Inspection compares a consumer checkout
   with the current pack checkout; it must not fetch or mutate either one.
2. **Signatures**:
   - `python3 install.py TARGET --status [--audit] [--json]`
   - `python3 install.py TARGET --check [--json]`
   - `--check` implies the structural install audit. `--status` is
     informational unless receipt validation or an explicitly requested audit
     reports invalid state.
3. **Contracts**:
   - Stable states are `current`, `refresh-required`, `not-installed`, and
     `invalid`.
   - JSON schema version 1 contains pack identity, absolute target, source and
     installed versions, version relation, state, installed and active
     platforms, aggregate result counts, change count, deterministic reasons,
     and audit request/status/exit/output fields.
   - Inspection reuses the existing selection and dry-run planning behavior.
     `installer/inspection.py` owns receipt validation, aggregate
     classification, and human/JSON rendering. The shipped
     `sd-ai-command-pack-install-audit.py` remains the structural audit policy
     authority.
   - Inspection rejects mutation and selection flags: `--remove`,
     `--dry-run`, `--force`, `--backup`, `--local-only`,
     `--skip-trellis-init`, `--skip-diff-check`, `--platform`, and `--all`.
     `--audit` and `--json` require an inspection action.
   - Inspection must not create receipts, provenance, backups, Trellis state,
     managed blocks, or local excludes. It must not persist the source checkout
     path in consumer state or reports intended for tracking.
4. **Validation & Error Matrix**:
   - Current, audit-clean `--check` -> exit 0.
   - Malformed, contradictory, unsafe, or integrity-invalid receipts; failed
     audit; audit timeout; or launch error -> state `invalid`, exit 1.
   - Invalid CLI combination -> argparse exit 2.
   - Valid missing or refresh-required `--check` -> exit 3.
   - Informational `--status` with valid missing or refresh-required state ->
     exit 0. Missing installs mark requested audits `not-applicable` without
     spawning the audit subprocess.
5. **Good / Base / Bad Cases**:
   - Good: a current target reports bounded aggregate output or exactly one
     deterministic JSON document and leaves the complete target tree unchanged.
   - Base: an older valid install reports `refresh-required`; `--status` exits
     0 while `--check` exits 3.
   - Bad: corruption is presented as a routine refresh, inspection modifies a
     consumer receipt, or audit rules are duplicated in the installer module.
6. **Tests Required**: Cover parser combinations, every state/exit-code path,
   deterministic JSON, human output bounds, version relationships, active and
   installed platforms, malformed/partial/unsafe receipts, vouched hash drift,
   audit pass/failure/timeout/launch failure, environment override isolation,
   and complete target-tree snapshots proving no writes. Installer line and
   branch coverage remains 100 percent.
7. **Wrong vs Correct**:

   ```text
   Wrong: parse verbose --dry-run output or reimplement the audit scanner
   Correct: reuse dry-run-safe planning and delegate structural policy to the audit

   Wrong: return success from --check when a valid refresh is needed
   Correct: reserve exit 3 for valid operator action and exit 1 for invalid state
   ```

## Thin Install Conversion Contract

1. **Scope / Trigger**: Use this contract when changing conversion to or from
   a thin install, the thin pin, the residual payload, thin-aware refresh, or
   how any fleet reader routes a converted consumer. A thin install is a
   consumer whose machine-provided surfaces were deleted because a machine-
   scope plugin serves them; the pack keeps the repo-native, consumer-config,
   and vendored-retained surfaces plus its three bookkeeping files.
2. **Signatures**:
   - `python3 install.py TARGET --thin --resweep-verdict PATH --consumer NAME
     [--dry-run]`
   - `python3 install.py TARGET --revert-thin [--dry-run]`
   - `python3 install.py TARGET` against a thin consumer — the thin-aware
     refresh, which is what `sd-fleet-refresh` runs.
   - `installer/conversion.py` owns classification and receipt reading;
     `installer/thin.py` owns the settings merge, the write phase, and the
     registry flip. Neither module ships to `plugins/sd/`.
3. **Contracts**:
   - **The delete set is derived, never listed.** Start from the consumer's
     installed-targets receipt, classify each entry through
     `docs/fleet/surface-partition.json`, and delete only the
     `machine-claude` / `machine-other` rows. Never from a list stored in code
     or in a task, and never from the partition alone — the partition says
     what the pack ships, the receipt says what this consumer has.
   - **The verdict binds two things.** A resweep verdict is accepted only when
     it names this consumer *and* carries the current `classifierDigest` over
     the partition, the registry entry, `RETIRED_TARGETS`,
     `MANAGED_BLOCK_REMOVAL_TARGETS`, both plugin manifests, and pack HEAD.
     Binding the consumer alone lets a verdict outlive the rules that produced
     it.
   - **All three `.sd-ai-command-pack/` bookkeeping files survive and are
     rewritten** to the residual payload. Inspection treats the footprint as
     incomplete unless all three are occupied, and the audit requires a
     non-empty provenance `files` map, so replacing them with a single pin
     makes every converted consumer read as damaged.
   - **Two thin witnesses, ordered.** The installed `manifest.json` carries
     `mode: "thin"` and `thin_pin_state` reads it *first*; provenance is the
     fallback. Conversion writes the manifest before provenance, and revert
     relies on the same order, so an interruption anywhere in the write phase
     leaves a consumer that reads thin and re-runs cleanly.
   - **`PIN_KEYS` is one list with two roles** (`installer/provenance.py`): a
     thin-aware refresh carries every key forward unchanged (updating only
     `version`), and `thin_pin_state` treats any survivor on an otherwise fat
     receipt as evidence of a hand edit. A key missing from it is silently
     dropped by the first refresh.
   - **`retired` is written even when empty.** An absent key and an empty list
     are the same to a reader that defaults, and revert's promise depends on
     telling "nothing was unrestorable" from "this receipt predates the field".
   - **The revert guarantee is narrowed, not absolute.** Revert restores the
     payload the pinned version ships and *names* what it cannot: a file the
     conversion deleted that the pack no longer ships is reported
     `not-restored`, because provenance keeps hashes rather than bytes.
   - **A thin consumer's platform set is owned by its pin**, in both
     directions. Revert passes the pinned set explicitly rather than
     re-detecting (detection answers "what is active now"; revert asks "what
     was taken away"), and the refresh rejects `--platform` / `--all` rather
     than re-deriving the residual.
   - **Fleet preflight routes on the receipt, not on the version alone.** For
     a thin consumer at the target version, every path in
     `installed-targets.txt` must still exist; otherwise the status is
     `residual-damaged`. The install audit skips its manifest-derived
     completeness check for a thin install, so preflight is the only place a
     missing residual file is distinguishable from a deliberately removed
     machine surface. Its printed repair command omits `--platform`.
4. **Validation & Error Matrix**:
   - Any drifted or unvouched file in the delete set -> refuse before any
     write. Unlike `--remove`, conversion fails closed at preflight: a partial
     conversion is a consumer that is neither fat nor thin.
   - Verdict missing, stale, or bound to another consumer/classifier -> exit 2.
   - `--thin` on an already-thin consumer, or `--revert-thin` on a fat one ->
     exit 2 naming the pin state.
   - A malformed pin (`PIN_STATE_MALFORMED`) -> refuse in *both* directions and
     route to `install.py TARGET --check` for the diagnosis.
   - `--remove` against a thin consumer -> refuse; it has no thin form, and
     running it leaves a live plugin, no receipts, and a registry saying thin.
   - Registry write fails after the payload landed -> report which half landed
     and exit nonzero. Never claim a clean run, and never advertise a recovery
     command the current pin state would reject.
   - Unwritable pack checkout or consumer root -> refuse before the target is
     touched (revert restores from the pack, so both roots matter).
5. **Good / Base / Bad Cases**:
   - Good: convert, then revert, and the tree is byte-identical to the
     pre-conversion tree except for paths named in `retired`.
   - Base: a thin consumer a version behind refreshes to the new version with
     the machine payload still absent, the `.gitignore` block still stripped,
     and every pin key carried forward.
   - Bad: a refresh silently re-creates the machine payload (de-thinning the
     consumer while the registry still says thin), revert re-detects platforms
     and restores a payload the pre-conversion tree never had, or a dry run
     announces only the deletions.
6. **Tests Required**: A convert/revert round trip asserting the whole tree,
   not selected paths — every narrower assertion has a version that passes
   while the payload comes back subtly wrong. Settings ownership (only the
   conversion's own additions are removed, including an empty container it
   created). Restore-path collisions. Consumer-identity disagreement between
   flag, receipt, and registry. Version mismatch. Partial-completion
   reporting. Dry-run parity: the announced set must equal the executed set in
   all six categories. Refresh rejections for `--platform`, `--all`,
   `--local-only`, and `--remove`. A fat consumer's refresh proven
   byte-identical with no pin key added — the thin branch sits inside the one
   code path every consumer in the fleet runs. `install.py` and `installer/*`
   stay at 100 percent line and branch coverage.
7. **Wrong vs Correct**:

   ```text
   Wrong: derive the residual from the partition's kept rows
   Correct: derive it from the pre-conversion receipt minus the plan's removals

   Wrong: record only the settings key/value pairs the conversion added
   Correct: record the created containers and created-file flags too, or revert
            cannot tell an adopted container from one it made

   Wrong: refuse an ordinary install against a thin consumer
   Correct: refresh it — a consumer a fleet sweep cannot refresh is a consumer
            that cannot receive a security fix

   Wrong: skip a thin consumer in fleet preflight because its version matches
   Correct: also require every recorded target to still exist; for a thin
            install the receipt is the allowlist and nothing else sees the gap
   ```

## Selection Rules

Use `selected_files()` for platform filtering, anchor checks, and active
Trellis platform detection:

- `install: "always"` files are selected by default.
- `install: "always"` files are also selected when `--platform` filters are
  present; adapters depend on the shared skill being installed.
- `--all` selects all adapters even when platform directories or active
  Trellis platform markers are absent.
- `--platform` selects only requested platforms and bypasses anchor and active
  marker detection for those selected platforms.
- Default adapter installation depends on both the target anchor directory,
  such as `.cursor`, `.gemini`, `.github`, or `.opencode`, and a Trellis-owned
  marker for that platform. A generic `.github` directory used only for Actions
  must not cause GitHub Copilot prompt files or managed instruction blocks to
  install.

Reference files:

- `installer/fileops.py`, `selected_files()`
- `tests/test_generated_parity.py`,
  `test_installs_shared_skill_and_existing_platform_adapters`

### Don't: give a marker-less registered platform a manifest row

**Problem.** `codex` is in `install.PLATFORMS` and has a `.codex` directory,
so a manifest row for it looks routine. It is not:

```json
{ "platform": "codex", "kind": "doc",
  "source": "templates/.codex/...", "target": ".codex/...", "anchor": ".codex" }
```

Measured: `PLATFORM_REGISTRY["codex"].markers == ()` and `.init_flag is None`,
where every peer carries three markers and a flag.
`ACTIVE_TRELLIS_PLATFORM_MARKERS` has no `codex` entry, so
`has_active_trellis_platform(target, "codex")` iterates an empty tuple and
returns `False` even in a repository with a fully populated `.codex/`.

**Why it's bad.** Three independent tests encode "a registered platform with
no markers ships no files", and one row breaks all three at once:

- `tests/test_install_core.py::test_platform_registry_derives_consistent_tables`
  — *"codex has manifest files but no markers"*. A platform that ships files
  must be selectable by an ordinary install.
- `tests/test_generated_parity.py::test_manifest_declares_current_trellis_platform_adapters`
  — a hardcoded set of platforms permitted manifest entries, with `codex`
  excluded and `assertIn("codex", install.PLATFORMS)` on the next line. The
  exclusion is deliberate.
- `tests/test_pack_drift.py::test_tracked_pack_targets_match_templates` — the
  dogfood gate selects platforms by *directory* existence while installation
  selects by *marker*. The two agree for every other platform and disagree
  here.

**Instead.** Decide which of the two the payload actually needs:

- *It must reach repositories.* Give the platform real markers and an init
  flag, as a change to install semantics carrying its own review. Check what
  the markers select before adding them: `.codex/agents/trellis-*.toml` exist
  wherever Trellis installed its own Codex adapter, so marking on those files
  auto-selects `codex` in essentially every consumer.
- *It is a practice of this repository.* Ship nothing. Put the file outside
  `templates/`, give it no manifest row, and point at it from `AGENTS.md` —
  inside the link checker's `documentationRoots`, so the reference is gated.
  `docs/planning-adversarial-review-codex.md` is the worked example.

The second is not a lesser form of the first. A pack-shipped file that names
a platform's CLI registers as undeclared usage in every consumer that never
declared it, which is what the thin resweep's `packDefect` reports; not
shipping is sometimes the only answer that neither weakens the detector nor
degrades the document.

## Receipt Stability Across Checkouts

The installed-targets receipt is declared installed state and can be
git-tracked while some recorded targets (and the markers/anchors that select
them) are gitignored — for example a `--local-only` install, whose adapter
files are excluded through `.git/info/exclude`. A refresh run from a checkout
where a platform is merely not visible must not erase what another checkout
legitimately installed:

- Keep existing receipt entries for manifest files skipped by marker
  detection or by a `--platform` filter, and report each kept entry as
  `kept-in-receipt`.
- Keep entries for anchor-skipped files only when `git check-ignore`
  confirms the file path is ignored in the target; check the file path, not
  the anchor directory, because trailing-slash directory ignore patterns do
  not match a bare nonexistent directory path. A tracked-but-removed anchor
  is an intentional platform removal and still drops its entries.
- Fail closed: when git is missing or the target is not a repository,
  preservation does not apply.
- Intentional platform removal is a manual receipt edit; the installer does
  not guess.

The install audit mirrors this: a receipt target that is missing but
gitignored in the current checkout is a warning with a reinstall hint, not a
failure. The reverse policy is equally supported: a pack-like file that
exists but is not recorded in the receipt warns instead of failing when the
file is gitignored, so repo-local guards that strip local-only adapters
from the receipt (rwbp-website's policy) pass the audit alongside the
installer's record-and-warn default. Tracked-but-unlisted pack-like files
remain failures. Receipt lines normalize Windows-style separators to `/` at
load time, after the unsafe-path rejection. This does not contradict the
"no mutable installer state" rule — the receipt is the explicit, reviewable
state file, and preservation only refuses to destroy entries the current
checkout cannot verify.

Manifest completeness closes the newly-added-target gap during a two-version
refresh. When older receipt entries identify a platform, the audit requires all
current manifest targets for that platform, including targets that did not
exist in the older receipt. `--expected-platform PLATFORM` must remain the
fleet contract because it declares the expected platform independently of
receipt history; it also catches a wholly absent first install or a receipt
that has lost every entry for that platform.

## Provenance

Every non-dry-run install writes `.sd-ai-command-pack/provenance.json`:
pack name, version, and a sorted map of vouched targets to `sha256:` hashes
of the installed content. For normal source-backed files, `install_file()`
records `source_digest`, `source_content`, and `source_executable` on
`InstallResult`; provenance must prefer that carried digest instead of
re-reading the source file. Legacy/narrow tests that construct results without
a digest may still fall back to hashing `file.source`, but source-less
generated files are skipped by shape. Never vouched: `FORCE_PRESERVED_TARGETS`
(user-tunable), managed-block targets (shared ownership), generated files
(receipt, gitignore block, provenance itself), and conflict results.
Entries survive for targets still recorded in the receipt so filtered runs
do not shrink coverage. The audit ignores stale provenance claims for those
never-vouched targets from older installs, then fails on content drift (naming the
recorded pack version), on a vouched target that is missing while not
gitignored (even when the receipt no longer lists it — provenance is the
tamper-evidence of last resort), on any symlink or non-regular node at a
vouched path, on a vouched path whose real path escapes the repository
root (symlinked parent directories), on inspection failures (per-target
`os.lstat`, reported with the exception text), and on a provenance file
that is itself not a regular file or is malformed, including an empty
`files` map. Gitignored-absent vouched targets skip, consistent with the
structural policy; structural `path_exists` is lstat-based so unreadable
parents degrade to missing-target reports instead of crashing. Absent
provenance (pre-0.5.10 installs) keeps the older audit behavior. When
provenance is present and the audit passes, the command reports the installed
payload provenance version and confirms vouched hashes match; that version can
intentionally be older than the source checkout manifest when a newer release
did not change installed payload bytes.

Reference files:

- `installer/provenance.py`, `preserved_receipt_targets()`, `is_gitignored_path()`,
  `provenance_content()`, `install_provenance_file()`
- `templates/scripts/sd-ai-command-pack-install-audit.py`, `is_gitignored()`,
  `audit_provenance()`
- `tests/test_install_audit.py`,
  `test_install_keeps_receipt_entries_for_gitignored_absent_anchor`
- `tests/test_install_audit.py`,
  `test_install_audit_downgrades_gitignored_missing_targets`
- `tests/test_install_audit.py`, `test_install_writes_provenance_with_hashed_targets`
- `tests/test_install_audit.py`,
  `test_install_audit_reports_installed_payload_provenance_version`
- `tests/test_install_audit.py`,
  `test_install_audit_warns_for_unlisted_gitignored_pack_files`

## Remove Mode Preserve-And-Continue Contract

1. Scope and trigger: use this contract whenever changing `install.py
   --remove`, `installed_target_candidates()`, `remove_pack_file()`,
   `remove_text_block_file()`, `remove_local_only_exclude()`, receipt reads,
   provenance reads, or managed-block marker cleanup.
2. Signatures: `python3 install.py TARGET --remove [--force] [--backup]
   [--dry-run]` must return `0` when unsafe or drifted target state is
   preserved and all other safe targets are processed. Preservation is a normal
   uninstall result, not a fatal CLI validation failure.
3. Contracts: remove mode treats target-repo state as user-owned unless the
   specific target is both manifest-recognized and proven safe to delete or
   update. Unsafe/unreadable `.sd-ai-command-pack/installed-targets.txt` or
   `provenance.json` state is treated as absent for uninstall candidate
   discovery, then removal falls back to manifest-selected targets plus
   generated state targets. Normal install/update paths may remain stricter
   because they are establishing controlled state.
   Receipt/provenance entries are candidate discovery only; a hash match must
   not authorize removal for a path absent from the current manifest target
   set or generated pack state. Root `.git/` paths are never whole-file remove
   candidates, regardless of receipts, provenance, manifest state, or
   `--force`.
4. Validation and error matrix: unsafe candidate path -> `preserved` with the
   validation detail; parent directory resolving outside the target repo ->
   `preserved`; unreadable target file -> `preserved`; invalid UTF-8 in a
   preserve-invalid-UTF-8 path -> `preserved`; incomplete or duplicated managed
   markers -> `preserved`; backup copy failure after a target is considered
   removable -> fatal clean `SystemExit` because the requested destructive
   action cannot be made reversible.
5. Good, base, and bad cases: a generated pack file with matching content is
   removed; a drifted file without `--force` is preserved; a receipt with
   unsafe paths does not abort the run; a receipt/provenance entry for
   `.git/config` or `USER_DATA.txt` is reported as ignored and preserved even
   with a matching hash and `--force`; `.git/info/exclude` with malformed
   local-only markers remains untouched; aborting the whole uninstall because a
   single user-owned file cannot be parsed is wrong.
6. Tests required: cover unsafe receipt/provenance fallback, unsafe regular
   candidate paths, symlinked parent directories, unreadable targets, malformed
   managed markers, `.git/info/exclude` parse failures, backup-copy failures,
   and CLI-level remove output that continues after preservation.
7. Wrong vs correct:

   ```text
   Wrong: remove_marked_block() raises SystemExit and aborts install.py --remove
   Correct: remove_text_block_file() returns preserved with the marker error detail

   Wrong: unsafe receipt/provenance paths stop all uninstall candidate discovery
   Correct: remove mode ignores unsafe receipt state and falls back to manifest targets
   ```

## File Writes

Use `install_file()` for copy behavior:

- Before reading, backing up, or writing a target path, validate that the
  resolved destination stays inside the resolved target repository. This
  catches existing symlinks in the target repo that would otherwise redirect a
  relative manifest path outside the repo.
- If the target path is already occupied by a directory, broken symlink,
  symlink to a directory, or other non-file path, fail with a controlled error.
  Do not let `read_bytes()` or `copyfile()` raise a traceback for expected
  target-repo state.
- Return `unchanged` when the target already has identical bytes.
- Return `conflict` and leave the target untouched when content differs and
  `--force` is absent.
- Return `preserved` and leave the target untouched when content differs and
  the target is `.prism/rules.json` or `.gito/config.toml`, regardless of
  `--force`; repo-local review-tool policy is intentionally protected during
  pack refreshes and must not be reported as a conflict.
- Keep `.gito/sd-ai-command-pack.env` updateable like scripts and docs. That
  file carries pack-owned runtime defaults, while credentials, model choices,
  and user-specific Gito settings belong in `~/.gito/.env` or the process
  environment.
- With `--force --backup`, copy the previous target file next to the original
  with a `.bak` suffix before overwriting it. Do not create backups for
  preserved review-tool policy files because they are not overwritten.
- Backup candidates must also resolve inside the target repo, and an existing
  symlinked `.bak` path counts as occupied even when the symlink is broken.
- Copy with `shutil.copyfile()` only after creating the target parent
  directory.
- In `--dry-run` mode, report the planned status without creating files.

Generated text writers follow the same safety model:

- `.gitignore`, `.github/copilot-instructions.md`,
  `.sd-ai-command-pack/manifest.json`, `.sd-ai-command-pack/provenance.json`,
  and `.sd-ai-command-pack/installed-targets.txt` are regular-file targets. If
  the final path is an in-repo symlink, report `symlink-conflict` and leave the
  link plus its target untouched. If the final path is another non-file node,
  report `conflict` and leave it untouched. Symlinks that resolve outside the
  target repo still fail target-path validation before any write.
- Use temp-file + `os.replace` writes for generated text and shipped helper
  rewrites of user-facing files. A failed replace, ENOSPC, or interrupted write
  must leave the previous complete file in place and clean up the temporary
  file.
- Standalone shipped scripts cannot import the installer package in consumer
  repos. Shared Python behavior for consumer-shipped scripts belongs in
  `templates/scripts/sd_ai_command_pack_lib.py` and its `templates/scripts/` twin; keep
  that module stdlib-only and manifest-installed with the scripts that import
  it.

## Shipped Python Helper Library

1. Scope and trigger: use this contract when adding or changing shared Python
   helpers consumed by installed `scripts/sd-ai-command-pack-*.py` files, or
   when moving repeated subprocess, git, gh, path, or error-formatting behavior
   out of individual scripts.
2. Signatures: `templates/scripts/sd_ai_command_pack_lib.py` exposes
   `CommandError`, `CacheSetupError`, `ToolExecutionPlan`, `CACHE_ROOT_ENV`,
   `CACHE_ENV_KEYS`, `DEFAULT_COMMAND_TIMEOUT`, `DEFAULT_GIT_TIMEOUT`,
   `DEFAULT_GH_TIMEOUT`, `DEFAULT_TRELLIS_TIMEOUT`, `command_display(args)`,
   `command_detail(process, fallback)`, `run_command(args, *, timeout,
   context, check, cwd, allowed_returncodes, capture_output, stdout, stderr,
   text, encoding, errors, env)`,
   `build_tool_environment(*, repo, environ) -> (environment, cache_paths,
   namespace)`, `build_tool_execution_plan(args, *, cwd, environ) ->
   ToolExecutionPlan`, `run_git(args, *, cwd, timeout, check,
   allowed_returncodes, errors, context)`, `run_gh(args, *, cwd, timeout,
   check, allowed_returncodes, errors, context)`, `git_stdout(args, *, cwd,
   timeout, errors, context, required)`, `repo_root(*, fallback_to_cwd=False)`,
   `default_text_file_mode(path)`, `atomic_write_text(destination, content,
   *, errors="strict", revalidate=None, mode=None)`, `STATE_HOME_ENV`,
   `resolve_state_root(*, environ=None, home=None, os_name=None,
   state_home=None)`, and `ensure_private_directory(path, *, label, reference=None)`.
   `templates/scripts/sd-ai-command-pack-toolchain.sh cache-env` emits the fixed
   allowlisted cache key/value set, while `... run -- COMMAND [ARG]...`
   executes one external argv through that environment and preserves the
   command's exit status.
3. Contracts: the helper is copied from `templates/scripts/` into the same
   installed `scripts/` directory as its consumers, so scripts import it by
   module name and must not mutate `sys.path` at runtime. The helper must remain
   dependency-free, must not import `installer.*`, must preserve UTF-8
   replacement decoding for captured output, and must apply bounded subprocess
   execution by default: 60 seconds for generic/git commands and 120 seconds
   for GitHub or Trellis operations unless a caller supplies a narrower
   timeout. Every pack-owned subprocess that may write tool cache state must
   use the shared execution plan. The plan begins with the inherited
   environment, preserves credentials and `GH_CONFIG_DIR`, and routes
   `XDG_CACHE_HOME`, `PYTHONPYCACHEPREFIX`, `UV_CACHE_DIR`, `UV_TOOL_DIR`,
   `PIP_CACHE_DIR`, `RUFF_CACHE_DIR`, and `NPM_CONFIG_CACHE` to private
   deterministic per-user/per-repository directories. Root precedence is a
   valid `SD_AI_COMMAND_PACK_CACHE_ROOT`, then a valid inherited XDG cache
   root, then a validated system temporary root. Valid explicit individual
   cache paths retain precedence. Shell entry points obtain the same fixed
   allowlisted key/value set from `sd-ai-command-pack-toolchain.sh cache-env`;
   they must parse it without `eval` or constructed shell commands. Reusable
   pack-created caches remain after success and ordinary housekeeping does not
   delete them. `atomic_write_text` is the single shared durable-write path for
   installed scripts: it refuses to follow a symlink at the destination, writes
   through a same-directory temporary file, fsyncs the file and its directory,
   guards against a cross-filesystem replace (raising rather than a non-atomic
   copy), and supports an optional `revalidate` callback to re-check the
   destination just before `os.replace`. Scripts must not reimplement a
   temp-file/`os.replace` writer of their own. `resolve_state_root` is likewise
   the single user-local state-root ladder: explicit `state_home`, then an
   absolute `SD_AI_COMMAND_PACK_STATE_HOME`, then an absolute `XDG_STATE_HOME`
   plus `sd-ai-command-pack`, then the Windows `LOCALAPPDATA` branch plus
   `sd-ai-command-pack/state`, then `~/.local/state/sd-ai-command-pack`. That
   one variable therefore moves every private state surface — work-loop ledgers,
   recovery receipts, fleet timing state, and fleet campaign state — and each
   consumer appends only its own subdirectory. `ensure_private_directory`
   refuses a symlink before and after `mkdir(mode=0o700, parents=True,
   exist_ok=True)`, tightens the mode best-effort, and never lets a raw
   `OSError` escape. Its `reference` argument is the caller-chosen path
   rendering appended to the symlink and unusable diagnostics, so each consumer
   keeps its own redaction posture: full path, `path.name` for modules that never
   put a host absolute path in a diagnostic, or omitted entirely. The library
   never picks a rendering of its own. Scripts must not re-fork either function:
   they bind a
   private wrapper to the module-level name by assignment, restating
   `CommandError` in their own error type, so exactly one `def` of each exists
   across `scripts/*.py`.
4. Validation and error matrix: empty command -> `CommandError`; missing binary
   -> `CommandError` naming the command and context; timeout ->
   `CommandError` naming the command, context, and timeout seconds; checked
   nonzero exit -> `CommandError` with stderr/stdout detail; unchecked nonzero
   exit -> returned `CompletedProcess`; repository-root lookup outside git ->
   `CommandError`; relative, repository-contained, symlinked, non-directory,
   non-private, wrong-owner, or unwritable explicit cache location ->
   `CacheSetupError` before the provider command runs; unsafe inherited XDG or
   temporary candidate -> try the next safe candidate; no safe candidate ->
   controlled cache-setup diagnostic naming `SD_AI_COMMAND_PACK_CACHE_ROOT` as
   the corrective option. Cache paths must be absolute and outside the
   repository, private namespace creation must be concurrency-safe, and raw
   repository paths must never appear in namespace names. For state roots: a
   relative `state_home` or `SD_AI_COMMAND_PACK_STATE_HOME` -> `CommandError`
   restated by the caller; a relative `XDG_STATE_HOME` -> skipped by the ladder,
   so a consumer that must reject it (fleet-controller) checks it itself and
   keeps raising its own error; a non-absolute home -> `CommandError`; a symlink
   or unusable state directory -> `CommandError`; a blocked `mkdir` ->
   `CommandError` chaining the originating `OSError` as `__cause__`, which the
   work-loop wrapper recovers to keep raising `StatePersistenceError` with its
   structured `environment_blocked` evidence.
5. Good, base, and bad cases: good scripts call `run_git(["status"], context=...)`
   or `run_gh(["pr", "view"], context=...)` and report the helper's
   user-facing error; a base successful command returns the original completed
   process; a bad script reimplements `subprocess.run(..., timeout=...)` with
   different messages or imports installer modules that do not exist in
   consumer repos. A good sandboxed `gh run view --log-failed` receives a
   writable private `XDG_CACHE_HOME` while the inherited `GH_CONFIG_DIR` and
   token remain byte-for-byte unchanged; a base invocation reuses its stable
   repository namespace; a bad caller redirects GitHub configuration to solve
   a cache failure, writes caches under the repository, or adds a one-off uv
   environment fragment.
6. Tests required: add focused helper tests for success, empty command, missing
   binary, timeout, checked failure, git/gh timeout defaults, stdout stripping,
   and repo-root failure. Any migrated script must keep focused tests for its
   previous CLI behavior plus root/template byte parity, manifest selection,
   install-audit provenance, and shipped-script coverage floor updates. Cache
   changes additionally require fixtures for unwritable home state, all
   supported cache variables, credential preservation, relative/repository/
   symlink/non-directory/private-permission rejection, concurrent creation,
   fixed shell export keys, provider non-invocation after setup failure, and a
   stubbed GitHub CLI cache write outside the repository. State-root changes
   additionally require an AST boundary test asserting exactly one `def` of each
   consolidated function across `scripts/*.py`, plus per-consumer error-type
   preservation and exact resolved paths for the injected and default roots.
7. Wrong vs correct:

   ```text
   Wrong: subprocess.run(["git", "rev-parse"], check=True)
   Correct: run_git(["rev-parse", "--show-toplevel"], context="resolve repository root")

   Wrong: from installer.fileops import run_diff_check
   Correct: from sd_ai_command_pack_lib import run_command

   Wrong: GH_CONFIG_DIR=/tmp/gh gh run view --log-failed
   Correct: build_tool_execution_plan(["gh", "run", "view", "--log-failed"], cwd=repo)

   Wrong: export UV_CACHE_DIR="$REPO_ROOT/.cache/uv"
   Correct: prepare_tool_cache_env

   Wrong: def resolve_state_root(...): <a fourth copy of the ladder>
   Correct: def _state_root(...): return lib.resolve_state_root(...)
            resolve_state_root = _state_root
   ```

## Plan-Before-Apply And Concurrency

For a normal tracked install without `--force` or `--dry-run`, run the selected
payload once in dry-run mode before the first pack-owned write. If any selected
target conflicts, report every conflict and exit `2` without partially applying
the refresh. Local-only Trellis bootstrap is outside this boundary because it
invokes the external Trellis installer before pack files exist.

An `install: always` target whose bytes differ from the new payload is not a
conflict when `provenance.json` records those exact bytes for that target. The
recorded digest proves the previous release wrote them and nobody edited them
since, so installing the new release displaces no decision anyone made: the
target reports `updated` and is written without `--force` and without a
backup, since the displaced content is a published release recoverable from
the pack. This is the repository-scope counterpart of machine-scope
`owned-stale`, and it is decided from the same evidence `remove` already
accepts as authority to delete a pack file. Anything else still conflicts:
bytes provenance does not record, a target absent from provenance, and a
provenance file that is missing, symlinked, or malformed — its reader
normalizes all three to no evidence, and absent evidence fails closed. A run
interrupted before its provenance rewrite therefore conflicts rather than
upgrading. The `if-not-exists` and force-preserved branch is decided ahead of
this one, so a vouched digest can never silently overwrite a consumer-tunable
file. Read provenance once per run and thread it into every classification, so
the preflight and the apply pass cannot disagree; `--check` and `--status`
report the same `updated` classification and still require a refresh.

When that preflight succeeds, thread the preflight `InstallResult`s into the
apply pass for unchanged, created, and preserved source-backed files. The apply
pass should reuse the planned source bytes, executable bit, and digest instead
of re-reading the pack source, but only after revalidating that the destination
still matches the planned status. If the destination appeared, disappeared,
changed content, or became a symlink between preflight and apply, fall through
to the normal install path so conflict and symlink-conflict handling remains
authoritative. Do not reuse preflight results for force overwrites, conflicts,
generated files, or a mismatched `PackFile`.

This is the repository-install boundary. The machine-scope engine runs a
stricter variant of the same idea against user-level destinations — every
target classified before the first write, and no `--force`-less run proceeding
past an unowned or drifted path — described under Machine-Scope Installer
above.

Installer runs are not serialized. Atomic file replacement must keep each
individual file parseable, while the last completed writer determines the
final receipt and provenance. Tests must exercise two concurrent installer
processes and verify that both state files parse and that every vouched hash
matches the final installed content. Operators should still run one refresh at
a time because output, backups, and selected-platform intent are not merged.

## Diff Checks

Run the final `git diff --check` only against manifest-selected target paths.
The installer should not fail because an unrelated tracked file in the target
repo already has whitespace errors.

## Trellis Gitignore Maintenance

For normal tracked installs, maintain a repo root `.gitignore` block between
`# sd-ai-command-pack trellis-gitignore start` and
`# sd-ai-command-pack trellis-gitignore end`. The block must ignore Trellis
local/runtime paths such as `.trellis/.developer`, `.trellis/.runtime/`,
`.trellis/.cache/`, `.trellis/.backup-*`, `.trellis/worktrees/`, and
`.trellis/.template-hashes.json` without blanket-ignoring `.trellis/`. It must
also ignore local AI-tool state under `.claude/`, `.codex/`, `.gemini/`, and
`.opencode/` without blanket-ignoring those platform directories, so shared
Trellis and SD command-pack adapters remain trackable.

When adding the block, migrate exact unmarked `.trellis`, `.trellis/`,
`/.trellis`, and `/.trellis/` entries into the managed block so Trellis specs,
tasks, workflow, scripts, and shared runtime files remain trackable. Keep
`--local-only` installs on `.git/info/exclude`; local-only mode must not modify
tracked `.gitignore`.

### Platform Runtime-Classifier Parity

1. **Scope / Trigger**: apply this contract whenever a platform's
   `PlatformInfo.trellis_local_only` entries change or a shipped review-scope
   classifier is added or edited.
2. **Signatures**: `PLATFORM_REGISTRY[platform].trellis_local_only` is the
   canonical tuple; `is_trellis_runtime_path()` in the shipped shell scanner
   and the copied-runtime path set in the JavaScript preflight are consumers.
3. **Contracts**: every exact registry file and every directory/glob-equivalent
   registry entry must be recognized by each shipped runtime classifier. Keep
   templates authoritative and regenerate root mirrors with `make sync`.
4. **Validation & Error Matrix**: a registry path absent from a classifier is a
   test failure; a template/root mismatch is a shipped-surface failure; an
   invalid platform key or unsafe path remains an installer validation error.
5. **Good / Base / Bad Cases**: adding `.gemini/settings.json` [absent: target-repo install path] to the registry,
   shell scanner, and JavaScript classifier is good; an unchanged registry and
   classifiers is the base case; updating only one consumer is invalid drift.
6. **Tests Required**: registry-coverage tests must assert representative exact
   settings files and iterate every `trellis_local_only` entry against shipped
   scanners; template-twin checks must compare generated root mirrors.
7. **Wrong vs Correct**: wrong: hand-edit the root scanner or add a path only
   to the registry. Correct: update the registry and canonical template,
   regenerate mirrors, then pass registry coverage and shipped-surface checks.

### Review Tool Config And Ignore Hygiene

1. Scope and trigger: use this contract whenever adding or changing
   distributed review-tool config, review runner temp files, generated review
   reports, or AI-tool local-state ignore rules.
2. Entry points and data: `manifest.json` owns `.prism/rules.json`,
   `.gito/config.toml`, `.gito/sd-ai-command-pack.env`, and review scripts.
   `installer/registry.py` owns `FORCE_PRESERVED_TARGETS`,
   `REVIEW_ARTIFACT_GITIGNORE_PATTERNS`,
   and `PLATFORM_LOCAL_GITIGNORE_PATTERNS`; `installer/fileops.py` owns
   `trellis_gitignore_block()`.
3. Contracts: preserve existing `.prism/rules.json` and `.gito/config.toml`
   files even with `--force`; install or update `.gito/sd-ai-command-pack.env`
   from the pack. Never ignore the whole `.gito/`, `.prism/`, `.claude/`,
   `.codex/`, `.gemini/`, or `.opencode/` directories because pack-owned
   adapters and config must remain trackable.
4. Ignore matrix: the managed `trellis-gitignore` block must ignore
   `.build/`, root `code-review-report.json` and `code-review-report.md`, pack
   temp files such as `sd-ai-command-pack-gito.*`,
   `sd-ai-command-pack-review-paths.*`,
   `sd-ai-command-pack-review-filters.*`,
   `sd-ai-command-pack-prism-codebase.*`, `sd-ai-command-pack-ci-paths.*`,
   `sd-ai-command-pack-uv-cache/`, `sd-ai-command-pack-uv-tools/`, and
   Gito-local state patterns such as `.gito/**/.cache/`, `.gito/**/cache/`,
   `.gito/**/logs/`, `.gito/**/tmp/`, `.gito/**/*.local.*`, and
   `.gito/**/*.log`.
5. Good, base, and bad cases: a fresh install adds the managed block and
   trackable review config; an update replaces the marker block without
   duplicating entries; local-only writes equivalent ignores to
   `.git/info/exclude`; a repo-custom `.gito/config.toml` is reported
   `preserved`; a blanket `.gito/` or `.prism/` ignore is wrong.
6. Tests required: cover fresh block creation, marker-block replacement,
   migration away from blanket Trellis ignores, local-only exclude behavior,
   negative `git check-ignore` expectations for `.gito/config.toml` and
   `.prism/rules.json`, and positive `git check-ignore` expectations for
   generated review reports, temp files, and Gito cache/log/tmp files.
7. Common failure mode: treating review config and review output as the same
   class of file. Correct behavior is to track distributed defaults and
   adapters, preserve user-tuned policy files, and ignore generated reports,
   caches, logs, temp files, secrets, and local state.

### Obsidian KB Copy Folder Contract

1. Scope and trigger: use this contract whenever changing
   `templates/scripts/sd-ai-command-pack-update-spec-kb.py`, the matching template script,
   the full-check KB freshness lane, or documentation for `.obsidian-kb/`
   generation.
2. Signatures: `python3 templates/scripts/sd-ai-command-pack-update-spec-kb.py`,
   `--dry-run`, and `--check` are the stable entry points. The normal command
   writes `.obsidian-kb/`, the managed ignore block,
   `.obsidian-kb/Dashboard - <repo>.md`, and
   `.obsidian-kb/LLM-KB - <repo>.md`; `--dry-run` prints the planned copy count
   without writing; `--check` exits nonzero when copies, dashboard, LLM
   overview, stale generated entries, or ignore state are not current.
3. Contracts: generated KB entries are real file copies, not symlinks. The
   root `.obsidian-kb` path may be either a real directory or a symlink to an
   existing directory, including one outside the repository. A valid root
   symlink is preserved and writes traverse it. An absent root is created only
   by normal refresh, not by `--dry-run`, `--check`, or guarded
   `--if-present`. A broken root symlink, a root symlink to a non-directory, or
   an occupied non-directory root fails before KB or ignore writes. The
   full-check freshness lane in auto mode skips only when the root is truly
   absent; broken root symlinks and occupied non-directory roots must reach the
   helper so its validation failure remains visible. The helper copies selected
   repository knowledge files into visible semantic category paths under
   `.obsidian-kb/` instead of mirroring hidden source folders, writes dashboard
   and LLM overview links to those copied paths,
   includes one-line document descriptions in the dashboard, includes a GitHub
   repository link when `origin` is a GitHub remote, groups generated index
   links by semantic category rather than source folder name, normalizes
   platform-root `agents.md`/`AGENTS.md` guidance filenames case-insensitively
   to the same stable destination such as `codex-agents.md`, avoids generated
   KB file/folder names that start with `.` or use Trellis-specific naming, and
   keeps the root path ignored with `/.obsidian-kb` through the managed
   `obsidian-kb` block in `.gitignore` or `.git/info/exclude` for local-only
   installs. The root-anchored rule covers both a real directory and a root
   symlink without ignoring nested paths with the same name.
4. Validation and error matrix: user-owned symlinks that point outside the repo
   are conflicts and must not be overwritten; legacy tool-created relative
   symlinks that resolve inside the repo are replaced by copies; occupied
   non-file paths are conflicts; stale generated files and legacy generated
   symlinks not in the current source set are pruned; user-owned dashboard or
   LLM overview files without the matching marker are conflicts. Existing
   `.obsidian-kb/` folders from the older symlink helper are migrated in place:
   pack-owned relative symlinks are replaced by category-layout copies, old
   mirrored generated paths and the legacy generated `LLM-KB.md` filename are
   removed, and the report includes the count of legacy symlinks converted or
   waiting to be converted.
5. Good, base, and bad cases: a fresh run creates copies plus a generated
   dashboard and LLM overview; a second run reports the copies as present; a
   modified source doc updates the copied file and generated indexes; deleting
   a selected source removes the stale generated copy and its index entry;
   renaming the dashboard leaves the legacy generated `Dashboard.md` stale and
   removable; leaving symlinks as the durable KB format is wrong because copying
   `.obsidian-kb/` into an Obsidian vault would break those links.
6. Tests required: cover fresh copy generation, dry-run no writes, check mode
   stale detection and acceptance after refresh, local-only exclude behavior,
   real-root and valid root-directory-symlink refreshes, root-symlink
   preservation, anchored ignore behavior for both root forms, full-check auto
   mode for truly absent and invalid existing roots, broken root symlinks, root
   symlinks to files, and occupied root files before writes,
   custom dashboard conflicts, unmarked gitignore entry migration, invalid
   gitignore byte preservation, and replacement of legacy generated symlinks
   with real file copies, including nested existing symlink trees from the old
   mirrored layout. Also cover the generated `LLM-KB - <repo>.md` overview,
   legacy generated `LLM-KB.md` pruning, and GitHub remote parsing/linking in
   the dashboard. Assert category headings
   such as repository overview, agent guidance, specs, repository maps,
   project manifests, and package documentation instead of folder-name
   headings such as `docs` or `docs/spec/backend`; assert dashboard
   one-line descriptions, the repo-specific dashboard filename, and generated
   KB paths with no leading-dot components or Trellis-specific names.
7. Wrong vs correct:

   ```text
   Wrong: .obsidian-kb/README.md -> ../README.md
   Wrong: .obsidian-kb/docs/spec/backend/index.md mirrors the hidden source path
   Correct: .obsidian-kb/Repository Overview/README.md contains the copied README bytes
   Correct: .obsidian-kb/Backend Specs/index.md contains the copied backend spec bytes
   ```

## Manifest Schema Contract

`manifest.json` carries `schemaVersion` (currently 1). `load_manifest()`
rejects manifests with a newer major schema, converts JSON parse errors and
missing entry fields to single-line `error:` messages (no tracebacks), and
`validate_manifest()` enforces the closed `KNOWN_MANIFEST_KINDS` set so a
misspelled kind can never silently downgrade a managed-block entry to a plain
file copy. `requiresTrellis` is wired: when a manifest sets it false, the
installer skips the Trellis-repo precondition.

Reference files:

- `installer/manifest.py`, `load_manifest` / `validate_manifest`
- `tests/test_install_core.py`, `test_load_manifest_rejects_malformed_manifests`
- `tests/test_install_core.py`, `test_validate_manifest_rejects_unknown_kind`
- `tests/test_install_core.py`,
  `test_install_skips_trellis_requirement_when_manifest_opts_out`

## Legacy And Obsolete Artifact Advisories

Since pack 0.4.0 the installer performs no broad or heuristic legacy cleanup:
the `legacy-conflict` and `obsolete-conflict` install statuses no longer exist,
and install-time retirement is limited to the canonical
`RETIRED_COMMAND_SURFACES` footprints in `installer/registry.py`.
`installer/removal.py` exposes compatibility tuple views derived from those
rows; it must not maintain a second target list. Those targets are removed only when
provenance vouches for their current bytes (or the user passes `--force`);
drifted or unvouched files are preserved. Other cleanup responsibility lives in
the install audit, which emits advisory warnings (never failures) when known
legacy or obsolete artifacts remain in a consumer repo:

- legacy `trellis-*` and `sd-refresh-specs` adapter, skill, and script names
  replaced by their `sd-*` equivalents
- the pack rename family: `docs/TRELLIS_REVIEW_PR_PACK.md` replaced by
  `docs/SD_AI_COMMAND_PACK.md`, old generated `sd-command-pack-*` script
  filenames replaced by the canonical `sd-ai-command-pack-*` names, and the
  OpenCode nested `.opencode/commands/sd/` command layout replaced by flat
  `sd-<command>` files
- stale references to those legacy names inside repo docs, configs, and
  scripts (boundary-aware token scan; needles cover the `trellis-*` command
  names, `sd-refresh-specs`, the legacy env-var prefixes, the old
  `TRELLIS_REVIEW_PR_PACK.md` guide name, and each rename-era
  `sd-command-pack-*` script filename)

Generated `docs/repomix-map.md` aggregates are excluded from the reference
scan. Their source documentation is scanned directly, so scanning the generated
copy adds duplicate or self-referential warnings without expanding coverage.

Consumers remove advisory-only artifacts manually; the audit keeps warning
until they do, and the warnings never block an otherwise clean audit. Add an
automatic retirement only for a bounded, enumerated former pack footprint and
cover its provenance, force, dry-run, source-checkout, and removal behavior.

Reference files:

- `templates/scripts/sd-ai-command-pack-install-audit.py`, `LEGACY_PACK_PATHS`
- `templates/scripts/sd-ai-command-pack-install-audit.py`, `LEGACY_PACK_REFERENCES`
- `tests/test_install_audit.py`, `test_install_audit_warns_about_legacy_pack_names`
- `tests/test_install_audit.py`,
  `test_install_audit_warns_about_rename_era_legacy_paths`
- `tests/test_install_audit.py`,
  `test_install_audit_legacy_advisories_cover_all_pack_scripts`

## Scenario: Source-Checkout-Only Commands

### 1. Scope / Trigger

Use this contract when a command is useful to pack maintainers but depends on
operator files that are intentionally absent from consumer repositories.

### 2. Signatures

- `COMMAND_NAMES: tuple[tuple[str, str], ...]` remains the complete source
  command catalog used by command-surface generation.
- `SOURCE_ONLY_COMMAND_NAMES: frozenset[str]` declares the catalog names that
  must not be added to the consumer manifest.
- `SOURCE_ONLY_COMMAND_TARGETS: tuple[str, ...]` enumerates the former consumer
  footprint that refreshes may retire.

### 3. Contracts

- `make generate` writes source templates/adapters for every `COMMAND_NAMES`
  row, but adds derived manifest entries only when the name is not source-only.
- Command-shape recognition still covers every catalog row so regeneration
  removes stale manifest entries for newly source-only commands.
- Consumer refreshes retire vouched source-only target copies. Drifted or
  unvouched copies remain preserved unless `--force` is explicit.
- A self-install whose target resolves to `ROOT` skips source-only retirement,
  preserving the pack checkout's generated command surfaces.
- The install audit allows those target paths only when all
  `SOURCE_REPO_MARKERS` prove the checkout is the pack source repository.

### 4. Validation & Error Matrix

- Source-only name absent from `COMMAND_NAMES` -> import-time `RuntimeError`
  from `validate_source_only_command_names()` naming the unknown command.
- Source-only target present in a consumer manifest -> parity/drift test
  failure.
- Vouched former target in a consumer -> `retired` during refresh.
- Drifted former target without force -> `retired-preserved`.
- Source-only root copy in the pack checkout -> preserved and accepted by the
  source audit.
- Any other unlisted pack-like source file -> install-audit failure.

### 5. Good / Base / Bad Cases

- Good: `sd-fleet-refresh` remains invocable in this checkout and disappears
  from a refreshed consumer's receipts, provenance, and filesystem.
- Base: a fresh consumer install never receives the command.
- Bad: filtering `COMMAND_NAMES` itself, which would stop source adapter
  generation and leave the operator command stale.

### 6. Tests Required

- Generator/parity: source templates and root surfaces exist while all
  source-only targets are absent from `manifest.json`.
- Retirement: exact former footprints are unique, consumer copies retire, and
  source-root copies remain.
- Drift/audit: tracked templates equal manifest sources plus declared
  source-only templates; source-only audit allowances equal the retirement
  footprint and apply only in a verified source checkout.
- Documentation: consumer command inventories omit the source-only command and
  the operator section labels it source-checkout-only.

### 7. Wrong vs Correct

```text
Wrong: ship the sd-fleet-refresh skill while omitting docs/FLEET_ROLLOUT.md
Wrong: delete sd-fleet-refresh from COMMAND_NAMES and hand-maintain root copies
Correct: generate it from COMMAND_NAMES, exclude it via SOURCE_ONLY_COMMAND_NAMES,
         retire vouched consumer copies, and preserve the verified source checkout
```

## Scenario: Source-Only Fleet Timing Evidence

### 1. Scope / Trigger

Use this contract when `sd-fleet-refresh` measures a rollout's sequential
baseline or resumes timing after an interruption. Timing observes the existing
release, install, audit, review, CI, finding, and housekeeping gates; it never
owns or changes their outcomes.

### 2. Signatures

- `templates/scripts/sd-ai-command-pack-fleet-timing.py` is source-only and remains
  absent from `manifest.json`.
- Operations are `init`, `stage-start`, `stage-end`, `consumer-end`, and
  `report`; all accept internal `--repo`, and tests/recovery may use internal
  `--state-home`.
- `system_reading() -> ClockReading` reads wall nanoseconds plus an elapsed-time
  clock. Prefer `time.clock_gettime_ns(time.CLOCK_MONOTONIC)` where those
  symbols exist and the read succeeds; use `time.monotonic_ns()` as the
  cross-platform fallback when the API is absent or rejects the clock read.
- Schema version 1 owns one safe run ID, repository digest, target version,
  fleet stages, rollout-priority consumers, sequential stage attempts, and
  final consumer outcomes.
- Fixed stages are `preflight`, `checkout-validation`, `install`, `audit`,
  `local-gate`, `commit-push`, `pr-creation`, `reviewer-wait`, `ci-wait`,
  `housekeeping`, and `post-merge-audit`.

### 3. Contracts

- State lives in the user's platform state directory under a repository digest
  and safe run ID. It is owner-private, size-bounded, schema-validated before
  and after mutation, protected by a bounded operation lock, and atomically
  replaced.
- Durable state and normal output never contain an absolute repository path,
  remote URL, command output, review body, credential, private key, or arbitrary
  environment value. Reasons are bounded and reject control characters,
  absolute/home-relative paths, remote URLs, and common secret forms.
- Stage elapsed time uses process-independent platform monotonic nanoseconds
  when available, falls back to the runtime monotonic clock when the platform
  API is absent or rejects the read, and rejects a backwards clock. Wall-clock
  nanoseconds preserve boundaries and calculate interval union, critical path,
  and reviewer/CI overlap without double-counting concurrency.
- `preflight` is fleet-scoped; every other stage is consumer-scoped. Reviewer
  and CI waits may be active together. Retry count derives from attempts after
  the first rather than a second persisted counter.
- Repeating initialization, an already-active start, an identical stage end,
  or an identical consumer end is a no-op. A new attempt requires a new start
  after the prior attempt closed. Completion requires no active attempts and a
  final outcome for every selected consumer.
- A telemetry error is visible and pauses new fleet mutation for correction;
  it does not overwrite, erase, or reinterpret an authoritative delivery result.

### 4. Validation & Error Matrix

- Unknown fields, wrong types/schema, unsafe IDs, duplicate consumer names or
  priorities, unordered consumers, duplicate stages, non-sequential attempts,
  mismatched end fields, or an active attempt in completed state -> controlled
  exit `2` with no traceback and no state replacement.
- Failure-like stage/consumer outcome without a reason, success outcome with a
  forbidden reason, secret/path/remote-URL/control content, or oversized state
  -> reject.
- A live lock -> bounded wait then busy error; a stale lock is recoverable only
  when its owner process is absent. Symlinked state/lock paths -> reject.
- Reinitialized run whose target or consumer identity differs -> reject rather
  than overwrite. Missing/malformed state or repository mismatch -> reject.
- Negative monotonic elapsed or completion with active/incomplete consumers ->
  reject while retaining the last valid partial record.
- Platform monotonic API absent or raising `OSError`/`ValueError` -> use the
  runtime monotonic fallback without exposing a traceback.

### 5. Good / Base / Bad Cases

- Good: reviewer wait spans seconds 10-30 and CI wait spans 20-40; critical
  path and active wall are 30 seconds, summed stage elapsed is 40 seconds, and
  overlap is 10 seconds.
- Base: a dry run records preflight, marks every selected consumer outcome,
  completes, and performs no consumer stage mutation.
- Bad: persist a process-relative monotonic reading, then attempt to close the
  stage from an isolated process whose clock origin is lower.
- Bad: sum reviewer and CI durations and report 40 seconds as critical path, or
  copy a consumer checkout path into a failure reason.

### 6. Tests Required

- Fake-clock coverage for process-independent monotonic-clock selection and
  absent/rejected-read fallback, init/resume, active and completed attempts,
  retries, skips/failures, overlap, interval union, critical path, slowest rows,
  partial report, completion, and backwards monotonic time.
- Strict schema/privacy matrices plus missing/malformed/symlinked state,
  private permissions, atomic-write errors, live/stale locks, and stable CLI
  JSON/human errors.
- Orchestration pins prove timing initializes before preflight, reviewer and CI
  start after PR creation and end independently, completion is last, and no
  public adapter exposes run ID or state controls.
- Install-audit parity proves the helper is source-only; shipped-script
  coverage keeps an explicit per-file floor of at least 88 percent.

### 7. Wrong vs Correct

```text
Wrong: add fleet-timing.py to manifest.json and install it into every consumer
Wrong: treat a telemetry write error as permission to ignore a failed install gate
Wrong: persist time.monotonic_ns() when an isolated runtime resets it per process
Correct: prefer clock_gettime_ns(CLOCK_MONOTONIC) for persisted stage boundaries
Wrong: reviewer 20s + CI 20s = 40s critical path when they overlap by 10s
Correct: keep private source-only state, preserve the gate result, and report
         30s critical path, 30s active wall, 40s summed time, and 10s overlap
```

Reference files:

- `templates/scripts/sd-ai-command-pack-fleet-timing.py`
- `templates/.agents/skills/sd-fleet-refresh/SKILL.md`
- `docs/FLEET_ROLLOUT.md`
- `tests/test_fleet_timing.py`
- `tests/test_sdlc_commands.py`

## Scenario: Controlled Post-Canary Fleet Waves

### 1. Scope / Trigger

Use this contract after release preflight identifies stale consumers. It
reduces rollout critical path by overlapping independent post-canary work while
preserving the existing release, review, finding, CI, and housekeeping gates.

### 2. Signatures

- Fleet manifest schema version 4 added `rolloutPolicy.defaultConcurrency` and
  ordered cohorts with `name`, `strategy`, optional `maxConcurrency`, and
  `consumers`.
- `parse_fleet_rollout_policy(...) -> FleetRolloutPolicy` is the shared strict
  parser.
- `sd-ai-command-pack-fleet-wave-plan.py --fleet PATH --state PATH
  [--no-merge] [--json]` reads one schema-version-1 observation snapshot and
  emits one plan.

### 3. Contracts

- The first cohort is a sequential `canary`; later cohorts remain locked until
  every canary is `at-target` or `merged`. Explicit `--no-merge` mode also
  accepts `pr-open`, holds merges, and suppresses merge candidates; normal mode
  does not.
- Cohorts include every manifest consumer exactly once and preserve canonical
  rollout-priority order. Sequential concurrency is one; bounded-parallel
  concurrency is at least two and no greater than the configured default or
  global maximum four.
- `canStart` fills only the active cohort's remaining slots. `mergeCandidate`
  is at most the first non-terminal manifest-order consumer and only when it is
  `ready`. A later ready PR waits.
- Each concurrent lane owns one checkout, branch, and PR. The controller owns
  scheduler calls, finding classification, serialized housekeeping merges,
  timing, resume observations, and the final manifest-order report.
- A verified `packBlocker` stops starts and holds unsettled merges. Terminal
  consumers are not restarted when live evidence reconstructs an interrupted
  run.

### 4. Validation & Error Matrix

- Missing/unknown policy fields, invalid strategy/concurrency, unsafe or
  duplicate cohort names, missing/repeated/unknown/reordered consumers ->
  controlled configuration error.
- Wrong state schema or fields, unknown/duplicate/missing consumers, invalid
  state, non-boolean blocker, unsafe input file, or active count above the
  cohort bound -> exit `2` without traceback or mutation.
- Canary terminal state other than the active mode's accepted states -> stop
  starts and hold merges with a bounded canary-health reason.

### 5. Good / Base / Bad Cases

- Good: sequential canaries merge; two post-canary lanes start; the remaining
  lane starts when one slot clears; ready PRs merge in manifest order; the solo
  final cohort starts last.
- Base: on resume one wave consumer is merged, one is in flight, and one is
  pending; only the pending consumer may fill the free slot.
- Bad: dispatch every stale consumer, share a checkout, or merge whichever CI
  completes first.

### 6. Tests Required

- Parser matrices cover schema, concurrency, strategy, cohort identity,
  complete membership, and order.
- Scheduler and CLI tests cover normal and `--no-merge` canary gating, bounded
  starts, deterministic merge hold, partial failure, blocker propagation,
  completion, resume, controlled errors, privacy, and human/JSON output.
- Skill, adapter, install-audit, generated-parity, and per-file coverage tests
  prove the helper stays source-only and public adapters expose no state knob.

### 7. Wrong vs Correct

```text
Wrong: start every stale consumer and merge in CI completion order
Wrong: infer a pack blocker from an unclassified consumer failure
Correct: start only canStart, set packBlocker from verified classification,
         and merge only mergeCandidate through housekeeping
```

Reference files:

- `docs/fleet/consumers.json`
- `templates/scripts/sd-ai-command-pack-fleet-wave-plan.py`
- `templates/scripts/sd_ai_command_pack_fleet_lib.py`
- `templates/.agents/skills/sd-fleet-refresh/SKILL.md`
- `tests/test_fleet_wave_plan.py`

## Scenario: Resumable Fleet Campaign Controller

### 1. Scope / Trigger

Use this contract for every `sd-fleet-refresh` rollout. Prompt text selects
action owners and explains exceptions; executable state alone decides campaign
identity, order, concurrency, attempts, receipts, blockers, and next actions.

### 2. Signatures

- `templates/scripts/sd-ai-command-pack-fleet-controller.py` is source-only and supports
  `plan`, `next`, `record`, `status`, `resume`, and `validate` with JSON output.
- Schema version 2 binds campaign, immutable pack release, source repository,
  fleet-manifest digest, selected checkout identities, no-merge mode, preflight,
  ordered lanes, attempts, exact heads/PRs, blockers, actions, receipts, and
  kind-tagged recovery rows. Loading migrates schema-version-1 state forward.
- `next` atomically issues action IDs derived from campaign, release, consumer,
  stage, and attempt. `record` accepts only the matching current action.
- `resume --recover-consumer NAME --corrective-release VERSION` is the sole
  transition from a terminal merge-stage pack blocker into a new
  `pr-publication` attempt after the named corrective release is current.
- `resume --recover-exhausted-consumer NAME --exhausted-action ID --release
  VERSION` is the sole transition from a terminal `retry-exhausted` lane into a
  new attempt at the stage that exhausted. `--release` names the campaign's own
  target version, not the current `manifest.json` version.

### 3. Contracts

- State is owner-private, lock-protected, size-bounded, schema-validated, and
  atomically replaced outside source and consumer repositories.
- `plan` is idempotent only for the same immutable identity and selection.
  Release, manifest, checkout, consumer, or mode drift fails closed.
- An issued action is never reissued. After interruption, `resume` reports
  read-only checkout/head/branch/clean evidence so the caller records the
  original action or an ambiguous result without duplicating a side effect.
- Results distinguish retryable infrastructure failure, product failure,
  review finding, ownership skip, permanent incompatibility, operator decision,
  ambiguity, at-target state, and success through stable reason codes.
- The controller composes the canonical wave planner. Canary failures gate
  later waves, active lanes cannot exceed cohort concurrency, and only the
  single manifest-order merge candidate may advance. `no-merge` terminates at
  PR-open evidence.
- A PR publication receipt establishes a full head SHA and PR number. Review,
  eligibility, merge, and post-merge receipts must name that exact head.
- When remediation advances an existing PR during review or merge eligibility,
  or required finish-work advances it before housekeeping, record the issued
  old-head action as `retryable-failure` with reason `pr-head-advanced`, the
  published full head, and the existing PR number. The first such retry routes
  back to `pr-publication`; only its passed receipt may establish the successor
  head and start a new publication epoch. A merge-stage successor retains its
  valid finish-work receipt, stops before housekeeping, and consumes that
  receipt only after the successor head passes review and eligibility. Generic
  retries stay on their current stage, and attempt-two head churn parks as
  `retry-exhausted`.
- Before a new lane installs the pack, checkout validation creates or activates
  one dedicated consumer Trellis task with substantive release, ownership,
  validation, and completion criteria. A conflicting active task or dirty
  Trellis state stops the lane before installer mutation.
- Loading migrates schema-version-1 state: an absent `recoveries` key becomes an
  empty list, every untagged recovery row gains `kind: "pack-blocker"`, and the
  caller's mapping and rows are left unmutated. Every recovery row binds a
  `kind`, the consumer, the source action with its attempt and blocker, and the
  destination stage and attempt. A `pack-blocker` row additionally binds the
  blocking head, the PR, and the corrective release, and moves `merge` to
  `pr-publication`; a `retry-exhausted` row carries none of those three and its
  destination stage equals its source stage. Historical receipts remain
  immutable under both kinds.
- A recovered lane starts a new publication epoch. Head equality is required
  within each epoch, while a later publication receipt may establish the new
  exact head used by its review, eligibility, merge, and post-merge receipts.
- Recovery of an already-published taskless lane is append-only: preserve its
  journal commit, add a substantive planning task artifact, validate the
  original planning bundle from the implementation head through the new head,
  then push and reuse the PR only after that bundle is valid. Do not weaken the
  bookkeeping validator or replay the failed merge action.
- Ownership skip is terminal for its attempt. Only explicit `resume
  --retry-consumer` after the owner clears creates a new checkout-validation
  attempt; it never mutates or discards the prior owner's work.

### 4. Validation & Error Matrix

- Wrong schema/field/type, unsafe identity, release mismatch, manifest drift,
  unknown/out-of-scope consumer, checkout mismatch, action mismatch, skipped
  stage, conflicting replay, stale PR head, or concurrent-policy violation ->
  exit `2` without state replacement or consumer mutation.
- `pr-head-advanced` outside review, merge eligibility, or merge, with a
  non-retryable result, missing old head or PR, blocker evidence, or a
  mismatched old head -> exit `2` without state replacement.
- Identical `plan` or receipt replay -> successful no-op.
- Retryable failure -> one new attempt; exhaustion parks with a stable reason.
  That park is reversible only through explicit `resume
  --recover-exhausted-consumer`, which grants one operator-authorized attempt at
  the stage that exhausted, is bounded to two recoveries per consumer and stage,
  and never widens the two automatic attempts.
- Ambiguous result or issued action on resume -> reconciliation; never repeat
  install, PR publication, review dispatch, or merge blindly.
- Verified pack blocker -> stop starts and hold unsettled merges.
- Recovery with the campaign release, an unreleased or non-current corrective
  version, a nonterminal lane, a non-merge blocker, mismatched head/PR, or a
  non-pack-blocker result -> exit `2` without changing campaign state.
- Exhaustion recovery with a release other than the campaign release, an
  out-of-scope consumer, a lane that is not terminal `retry-exhausted`, an action
  that is not the lane's latest receipt, a receipt whose stage, attempt, or
  reason code disagrees with the lane, or a consumer and stage that already hold
  two recoveries -> exit `2` without changing campaign state. Replaying the same
  exhausted action returns the existing record and changes nothing.
- Recovery selectors combined with ownership retry or issued-action
  reconciliation selectors -> usage error before state mutation. Each recovery
  mode also rejects the other mode's evidence flag.

### 5. Good / Base / Bad Cases

- Good: interruption after PR creation preserves the issued action; resume
  proves the PR/head, records the original receipt, and advances to review.
- Base: preflight passes, sequential canaries settle, two wave lanes issue,
  ready PRs merge in manifest order, and the receipt report completes.
- Base: an existing schema-version-1 campaign has no `recoveries` key, loads as
  an empty recovery history at schema version 2, and leaves its state file
  byte-for-byte unchanged until the next mutating command writes it.
- Good: a corrective release is current, the exact terminal blocker matches,
  and recovery creates publication attempt two while retaining every attempt-
  one receipt and blocker.
- Bad: a restarted prompt calls install again because it does not remember the
  prior side effect, records a review receipt for a successor head without a
  publication receipt, or deletes the invalid journal tail to make recovery
  appear clean.

### 6. Tests Required

- Transition/idempotency matrices cover wrong release/consumer, skipped stages,
  duplicate/conflicting receipts, retries, terminal results, and stale heads.
- Head-republication coverage proves review, merge-eligibility, and
  merge-finalization routing, immutable old-head receipts, successor
  publication epochs, retained finish-work evidence, invalid-use no-mutation
  behavior, generic retry preservation, and bounded exhaustion.
- Scheduler composition covers canary failure, bounded wave starts, pack
  blocker propagation, no-merge completion, and serialized merge order.
- Persistence/recovery covers private atomic files, manifest drift, locks,
  issued action reconciliation, explicit ownership retry, and concise reports.
- Corrective recovery covers legacy schema normalization, strict release and
  terminal-blocker preconditions, mutually exclusive resume modes, idempotent
  source actions, collision-free stage attempts, and multiple exact-head
  publication epochs.
- Exhaustion recovery covers schema-version-1 migration with its read-only
  no-mutation boundary, per-kind recovery-row validation, release comparison
  against the campaign target rather than the current manifest, refusal for every
  other terminal result, attempt numbering across repeated recoveries, the
  per-stage cap, receipt immutability, and all three `resume` dispatch sites.
- Skill/docs/parity tests prove the controller remains source-only, public
  adapters expose no campaign/state controls, rare recovery is conditionally
  loaded, and prompt text no longer owns the lane/timing state machines.

### 7. Wrong vs Correct

```text
Wrong: install into a taskless consumer lane and hope finish-work can archive it
Wrong: reset or amend an invalid journal commit, or replay the blocked merge
Correct: create the lane task before install; for a legacy blocked lane, publish
         an append-only planning task under an explicit corrective-release
         transition, validate the bundle, and run review through merge again
```

Reference files:

- `templates/scripts/sd-ai-command-pack-fleet-controller.py`
- `templates/.agents/skills/sd-fleet-refresh/SKILL.md`
- `templates/.agents/skills/sd-fleet-refresh/references/controller-recovery.md`
- `docs/FLEET_ROLLOUT.md`
- `tests/test_fleet_controller.py`

## Scenario: Refreshing A Superseded `if-not-exists` Default

### 1. Scope / Trigger

Use this contract when changing any `install: if-not-exists` template, the
installer's preserve path, or the provider-config history artifact.
`if-not-exists` writes once and never again, so before this contract a
correction to a broken shipped default reached nobody: `install.py --force`
reported `preserved` for an untouched stale default and a hand-customized file
alike. Separating those two needs one fact the installer cannot otherwise
learn — whether the bytes on disk are something this pack shipped.

### 2. Signatures

- `docs/sd-ai-command-pack-provider-config-history.json`, schema version 1:
  `{"schemaVersion": 1, "sources": {<manifest source>: {"target": str,
  "current": str, "digests": [str, ...]}}}`. Generated at
  `templates/docs/...`; the root copy comes from the self-sync install.
- `.github/scripts/generate-provider-config-history.py` — release-prep
  generator, ordered strictly **before** `install.py . --force`.
- `installer/providerhistory.load_provider_config_history(root=ROOT) ->
  ProviderConfigHistory(digests_by_target, unavailable_reason)`, with
  `.shipped(target: Path, digest: str) -> bool`. `lru_cache`d per root.
- `installer/fileops.is_previously_shipped_default(file, current, *, source,
  installed_content) -> bool`.
- `InstallStatus.REFRESHED = "refreshed"`, a member of `VOUCHABLE_STATUSES`
  and of the audit's change statuses.

### 3. Contracts

- The predicate keys on `file.install == IF_NOT_EXISTS` **alone**.
  `FORCE_PRESERVED_TARGETS` is not an additional exclusion: both shipped
  `if-not-exists` configs are also members of that set, so excluding it makes
  the feature inert for its entire population.
- The comparison uses mode-correct payload bytes — what *this* install mode
  would have written — not the raw template.
- The refresh is not gated on `--force`. A missing, unreadable, malformed,
  empty, or newer-schema history yields `preserved` with a named reason;
  every failure resolves toward preserving consumer content.
- `current` is stated, never inferred from the tail of `digests`: a template
  that reverts to bytes it shipped before adds no new digest.
- `digests` is append-only. Removing one silently re-arms the trap for
  whoever still holds those bytes; a source dropped from the manifest keeps
  its entry for the same reason.
- Seeding a source derives its digests from `git log --follow` and refuses on
  a shallow clone rather than seeding a partial list, which would report the
  holders of missing versions as customized.
- The symlink branch stays `PRESERVED`: provenance vouches regular files only.
- Two readers, one file — `install.py` reads it from the pack source tree;
  the vendored install audit reads it from the consumer, which is why it is a
  `shared` / `doc` / `always` manifest record.
- `installer/providerhistory.py` must import siblings absolutely
  (`from installer.registry import ROOT`); the plugin bundler rejects relative
  sibling imports.

### 4. Validation & Error Matrix

- installed bytes equal current payload -> `unchanged`, no write.
- bytes match a recorded shipped digest -> write payload, `refreshed`, vouched.
- bytes match no recorded digest -> `preserved`, reported as locally owned.
- history missing/malformed/empty/unknown schema -> `preserved` plus reason;
  the audit says `cannot check provider config currency for N target(s)`.
- manifest unreadable, or no installed `if-not-exists` target -> the audit
  returns no claim rather than a guess.
- shallow clone during seeding -> release-stopping `GenerateError`.

### 5. Good / Base / Bad Cases

- Good: consumer holds an older shipped `.gito/config.toml`; install reports
  `refreshed` and the file is byte-identical to the template; a second run
  reports `unchanged`.
- Base: consumer's `.prism/rules.json` carries its own rules; install reports
  `preserved` and the local rules survive; `sd-status fleet` classifies it
  `local`.
- Bad: gating the refresh on `--force`, excluding `FORCE_PRESERVED_TARGETS`,
  treating an unreadable history as "nothing shipped", or converting the
  target to `install: always`.

### 6. Tests Required

- Predicate: shipped digest, unmatched digest, unavailable history,
  non-`if-not-exists` target, `FORCE_PRESERVED_TARGETS` membership (named
  regression), and the thin-payload rewrite comparison.
- End-to-end install: refresh, preserve, idempotence, and vouchability.
- Artifact reader: every malformed shape yields a reason and an empty map.
- Generator: seeds once from history, appends, never removes, idempotent.
- Release prep: the generator precedes the self-sync install in the chain.
- Audit: superseded, locally owned, malformed entry, unreadable target, and
  unreadable record.

### 7. Wrong vs Correct

```python
# Wrong -- --force now discards local customization
if file.install == IF_NOT_EXISTS and force:
    write(new_content)

# Correct -- provenance, not a flag: replace only what this pack put there
if file.install == IF_NOT_EXISTS:
    if is_previously_shipped_default(file, current, source=source,
                                     installed_content=new_content):
        write(new_content)
        return InstallResult(file, InstallStatus.REFRESHED, ...)
    return InstallResult(file, InstallStatus.PRESERVED, ...)
```

Reference files:

- `.github/scripts/generate-provider-config-history.py`
- `installer/providerhistory.py`
- `installer/fileops.py`
- `templates/docs/sd-ai-command-pack-provider-config-history.json`
- `templates/scripts/sd-ai-command-pack-install-audit.py`
- `templates/scripts/sd-ai-command-pack-status.py`
- `tests/test_provider_config_history.py`

## Scenario: Managed Blocks And The Skip-When-Absent Target

### 1. Scope / Trigger

A *managed block* is a marker-delimited region the installer owns inside a file
the consumer otherwise owns. There are three: `.gitignore`'s Trellis block,
`.github/copilot-instructions.md`, and `AGENTS.md`'s canonical-entry-point
routing block. Every one is an infra-integration contract, so this carries
code-spec depth.

Before 0.71.56 each behaviour lived where it was needed: markers in
`installer/registry.py`, a strip table in `installer/thin.py`, a removal list
and two hand-written calls in `installer/removal.py`, a label map in the thin
re-sweep. Four copies of one fact. `AGENTS.md` is the target that made that
untenable, because it differs from the other two on two axes at once.

### 2. Signatures

```python
@dataclass(frozen=True)
class ManagedBlockSpec:
    start: str
    end: str
    label: str
    preserve_invalid_utf8_on_strip: bool = False
    adopt_on_thin: bool = False
    create_if_absent: bool = True
    strip_on_thin: bool = True

MANAGED_BLOCK_SPECS: dict[str, ManagedBlockSpec]   # keyed by target as_posix()

def managed_block_spec(target: Path) -> ManagedBlockSpec   # SystemExit if absent
```

`managed_block_spec` raises rather than returning `None`. An unregistered
managed-block target is a manifest/registry disagreement, and the only safe
response to being asked to write markers nobody declared is to stop.

### 3. Contracts

| target | `create_if_absent` | `strip_on_thin` | `adopt_on_thin` | `preserve_invalid_utf8_on_strip` |
| --- | --- | --- | --- | --- |
| `.gitignore` (Trellis block) | yes | yes | yes | no |
| `.github/copilot-instructions.md` | yes | yes | no | yes |
| `AGENTS.md` (routing block) | **no** | **no** | no | no |

`installer/fileops.py`, `installer/thin.py`, `installer/removal.py`, and
`templates/scripts/sd-ai-command-pack-thin-resweep.py` all read this table.
`thin.py`'s `BLOCK_MARKERS` and the re-sweep's `STRIPPED_BLOCK_LABEL` are
*derived views* filtered on `strip_on_thin`, so `AGENTS.md` is absent from them
by construction rather than by a maintainer remembering to omit it.

`preserve_invalid_utf8_on_strip` is named for its scope, and the name is the
fix for a real ambiguity: `install_managed_block` round-trips undecodable bytes
through surrogateescape for **every** target regardless of the field. That is
not an oversight to correct by making installs strict — merging a block into a
consumer file the pack cannot fully decode should succeed, and a strict read
would turn a working install into a `UnicodeDecodeError` on any consumer whose
`.gitignore` or `AGENTS.md` carries stray bytes. Stripping is the asymmetric
half: with the field False, `read_text_strict` fails and the file is reported
`PRESERVED` and left untouched, which is the right default for a destructive
edit and the wrong one for an additive merge.

`adopt` is deliberately not passed by the removal loop. Adoption is a
thin-conversion behaviour; an ordinary uninstall removes every managed block,
`.gitignore`'s included. The field is named `adopt_on_thin` to make the leak
visible if someone wires it up.

The routing block itself carries this statement, and it is the contract a
reader should rely on:

> The pack verifies that this block matches the version it shipped — `install.py
> <repo> --check` reports `refresh-required` if the text between the markers
> drifts. It does **not** verify the routing against this repository's installed
> skills, and deliberately names none: the block routes by intent so that there
> is nothing in it that a later release or a thin conversion could make false.

### 4. Validation & Error Matrix

**The skip belongs in `selected_files`, not at write time.** A row whose target
the pack may not create is dropped from the selection when that target is
absent — before every install-mode branch, keyed on `path_is_occupied()` rather
than `.exists()`, so a dangling symlink stays a conflict for the writer to
report instead of an absent file to skip.

It cannot be a `PRESERVED` result instead. `installed_targets_content()` is
built from `selected`, so a preserved row still lands in the receipt, and
`audit_structural_state()` then reports the target as missing — the same audit
failure, arrived at from the opposite direction. `install_managed_block` keeps
a defence-in-depth guard, but the selection is what makes the receipt correct.

**A marker-less platform needs `install: "always"`.** The `AGENTS.md` row
declares `platform: "shared"`, which has no activation markers, so an
`if-anchor-exists` row is never selected in a normal install. The absent-file
skip is the gate; the install mode is not.

**The audit expects every `shared` row.** `expected_targets_from_manifest`
is unconditional, so a legitimately skipped target fails `--check` unless it is
named. `OPTIONAL_INSTALL_TARGETS` in the install audit is that list, and it
mirrors the pre-existing `.gitignore` precedent rather than inventing a
mechanism.

| condition | result |
| --- | --- |
| `AGENTS.md` absent | row dropped from selection; `<target> not present; block not created`; not in receipt |
| `AGENTS.md` present, no block | block appended; target enters the receipt |
| block text drifts from the shipped template | `--check` reports `refresh-required` |
| unregistered managed-block target | `SystemExit: unsupported managed block target: <target>` |

### 5. Good / Base / Bad Cases

- **Good**: a repository with an `AGENTS.md` — the block installs, prose outside
  the markers survives, a second install is a no-op.
- **Base**: a repository without one — install succeeds, the file is not
  created, `--check` reports `state: current` and `audit: passed`.
- **Bad**: a hand-edited block — `--check` reports `refresh-required`, and a
  re-install replaces the block and nothing else.

### 6. Tests Required

`tests/test_install_core.py` (`AgentsRoutingBlockTests`),
`tests/test_remove.py`, `tests/test_conversion_plan.py`,
`tests/test_partition_surfaces.py` [absent: removed with the release train in 0.72.0], `tests/test_install_audit.py`,
`tests/test_review_preflight.py`.

Two of these tests were written, observed to pass, and found to prove nothing —
worth naming, because both failure modes recur:

- a test written against `install_managed_block` asserts the wrong layer;
  `_require_file_destination` fires before the skip guard, so the guard can be
  deleted and the test still passes. Assert against `selected_files`.
- `tests/test_install_audit.py` runs the **consumer's** installed copy of the
  audit (`[sys.executable, "scripts/..."], cwd=root`), which is installed from
  `templates/`. `install.py --check` runs the **pack's** own `scripts/` copy
  (`installer/inspection.py:342`). Patching one and testing the other proves
  nothing. Demonstrate every guard failing without itself.

### 7. Wrong vs Correct

> **Warning**: a marker sweep does not find every site a new managed-block
> target must touch. Three of them hold the target path as a plain string and
> match no marker, no `MANAGED_BLOCK_SPECS` reference, and no `installer/`
> import. This is the durable lesson: enumerate the *classification* sites, not
> the marker sites.

The sites, measured rather than reasoned about:

- `.github/scripts/partition-surfaces.py` [absent: removed with the release train in 0.72.0] — `TARGET_OVERRIDES`, which
  fail-closed-errors if it names zero manifest rows;
- `templates/scripts/sd-ai-command-pack-install-audit.py` —
  `PROVENANCE_NEVER_VOUCHED_TARGETS` **and** `OPTIONAL_INSTALL_TARGETS`;
- `templates/scripts/sd-ai-command-pack-review-learnings.py` —
  `GENERATED_SIGNAL_PATHS`, compared against a **lowercased** path, so the entry
  is `agents.md`.

##### Wrong

```python
if file.install in {ALWAYS_INSTALL, IF_NOT_EXISTS}:
    ...
spec = MANAGED_BLOCK_SPECS.get(file.target.as_posix())
if spec is not None and not spec.create_if_absent:
    ...   # too late: the ALWAYS_INSTALL branch already selected the row
```

##### Correct

```python
spec = MANAGED_BLOCK_SPECS.get(file.target.as_posix())
if spec is not None and not spec.create_if_absent:
    if not path_is_occupied(target / file.target):
        skipped.append((file, f"{file.target} not present; block not created"))
        continue
if file.install in {ALWAYS_INSTALL, IF_NOT_EXISTS}:
```

##### Wrong

```js
function isSdCommandPackCopiedPath(path) {
  return (
    packInstalledTargets().has(path) ||     // AGENTS.md matches here, first
    ...
    path === 'AGENTS.md' ||                 // never reached; changes nothing
```

A new managed-block target does **not** need a literal beside
`.github/copilot-instructions.md`'s: the receipt lookup already classifies it,
because it is an installed target. An exemption placed after that lookup is
dead code, and one placed nowhere leaves the file classified `copied` — which
tells reviewers not to line-comment the wording of a file that is mostly the
consumer's own agent instructions plus another installer's block. The pack owns
about thirty lines of it. That trade runs the wrong way: a missed comment on
pack prose is cheaper than a skipped review of a repository's agent
instructions.

##### Correct

```js
function isSdCommandPackCopiedPath(path) {
  if (path === 'AGENTS.md') {
    return false;                            // before the receipt lookup
  }

  return (
    packInstalledTargets().has(path) || ...
```

`.github/copilot-instructions.md` keeps its existing classification. Changing it
would move every consumer's review scope, which is a separate decision from
adding a row.

**A consumer that mirrors this classification locally must be updated with it.**
The pack's preflight is not the only reader: a consumer can carry its own
review-scope script, and such a script typically asserts the inverse over the
receipt — every installed target must classify as copied — so a pack-side
exemption turns that assertion into a guaranteed failure the moment the row
ships. The fleet candidate check is what surfaces this, because it installs the
candidate into a clone of each consumer and runs that consumer's own checks:

```
failed      P20 platypeeps/loadsmith
error: review preflight fixture mismatch for AGENTS.md: copied=true, expected false
```

The gate is all-pass and has no waiver mechanism, so the consumer-side change
lands **before** the pack row does. Treat a new exemption as a fleet change, not
a local one.

## Read-Only Status And Housekeeping Delegation

`templates/scripts/sd-ai-command-pack-status.py` is the canonical collector for
repository delivery status. Its root `scripts/` twin must remain byte-identical
and the manifest ships it to consumers. The shared
`sd_ai_command_pack_fleet_lib.py` template and root twin are also shipped so
manifest parsing and machine-profile resolution remain one contract. Local and
positional `fleet` modes are available in every installed repository.

Fleet topology, rollout policy, candidate commands, and release evidence stay
checked into the canonical source checkout. Machine-specific discovery uses a
schema-versioned profile at `$XDG_CONFIG_HOME/sd-ai-command-pack/config.json`
or `~/.config/sd-ai-command-pack/config.json`, with
`SD_AI_COMMAND_PACK_FLEET_CONFIG` as an advanced path override. Profile schema
version 1 contains required `packSource`, optional `fleetManifest`, and optional
string `pathOverrides` keyed by consumer name. It must not duplicate rollout
policy.

Fleet resolution precedence is public `--fleet-manifest`,
`SD_AI_COMMAND_PACK_FLEET_MANIFEST`, the machine profile, then the current
canonical source checkout. The resolved pack manifest must identify
`sd-ai-command-pack` and provide the target version. Missing, malformed, moved,
or stale configuration fails with a controlled remedy rather than silently
using a guessed fleet. Unknown checkout overrides fail as stale profile data.

`install.py --configure-fleet` is the only pack-owned writer for this profile.
It is opt-in, validates existing configuration before repository writes,
preserves checkout overrides, writes atomically with owner-only permissions,
honors `--dry-run`, and is incompatible with inspection or removal modes.
Ordinary installs and all status modes must not mutate user-global state.

The collector is read-only: it may inspect Git, optional GitHub metadata,
Trellis task JSON, and local version receipts, but must never fetch, pull,
switch, stage, commit, push, merge, delete branches, or modify task state.
It inventories the repository's Git worktrees from `git worktree list
--porcelain -z` (additive `git.worktrees` and `git.branchesHeldElsewhere`
keys plus a human `==> Worktrees` section); per-worktree cleanliness probes
run `git --no-optional-locks status --porcelain` only after a common-dir
identity check, and an unavailable inventory is reported explicitly, never
as an empty healthy result. Ref-derived remote facts are labelled `cached`
unless the trusted housekeeping caller supplies the internal refreshed-ref
attestation. Human output stays bounded; `--json` exposes schema version 2
for complete structured detail (additive keys do not bump the version).
Ordinary dirty, stale, missing, behind, or diverged observations are advisory
and do not change a successful report's exit status. Invalid repositories or
fleet configuration fail, and internal `--expect-clean` fails when cleanup
invariants or prior housekeeping anomalies remain.

Housekeeping owns mutation and merge safety only. After its action log, it must
invoke the sibling status collector through the sibling toolchain resolver and
pass cleanup context as argv values. Status owns final Git comparison,
GitHub/Trellis inventory, anomalies, and numbered next steps. Do not reintroduce
parallel expected-state or inventory collectors in the Bash script.

Required tests cover clean, dirty, detached, diverged, unavailable-tool,
strict-cleanup, no-write, fleet-order, stale-version, missing-checkout, source
identity, explicit/environment/profile/source precedence, path overrides,
missing/malformed/moved profiles, atomic profile updates, adapter parity,
installer lifecycle, and housekeeping merge/cleanup integration behavior.

## Source Checkout Dogfood Drift Gates

The `sd-ai-command-pack` source checkout dogfoods installed pack payloads at
the repository root. For every platform directory that exists in this source
repo, every non-managed-block manifest target for that platform must also exist
at the root and byte-match its manifest source. Shared manifest targets are
always required. This catches missing installed twins, not only content drift in
twins that happen to be present.

The full-check must establish source identity before running these SD-specific
assumptions. `install.py`, `manifest.json`, and `templates/` identify only an
installer-repo candidate. The parsed root manifest is authoritative: its name
must equal `sd-ai-command-pack`, its version must be a non-empty string, and its
files field must be a list. Valid manifests for other packs skip the gate. A
malformed manifest that textually asserts the SD identity, or a parsed SD
manifest missing those required fields, fails with a controlled diagnostic.
The source-hook advisory must reuse the same classifier.

Keep these checks in the pack-source drift tests:

- The dogfood target set is derived from `manifest.json`, `PLATFORM_REGISTRY`,
  and root platform directories; do not maintain a hand-written allowlist.
- Missing dogfood targets fail before comparison, so adding a command to
  `templates/` plus `manifest.json` requires refreshing the root installed copy
  with `install.py . --force --platform <platform>`.
- `git ls-files templates` must equal manifest sources plus the templates for
  registry-declared source-only commands. No other orphaned template files are
  allowed, and every manifest source must remain tracked.
- Authored neutral command bodies live outside the install payload under
  `.github/command-sources/`; generator `--check` proves that every guarded
  `templates/.commands/` payload matches those sources plus registry capability
  policy.
- Manifest targets must be unique under `casefold()` to avoid collisions on
  case-insensitive filesystems.
- Source-checkout install state such as `.sd-ai-command-pack/provenance.json`
  and `.sd-ai-command-pack/installed-targets.txt` remains local/ignored here;
  consumer repos should track normal install state unless they use
  `--local-only`.

Reference files:

- `tests/test_pack_drift.py`,
  `test_tracked_pack_targets_match_templates`
- `tests/test_pack_drift.py`,
  `test_dogfood_drift_gate_detects_missing_existing_platform_targets`
- `tests/test_pack_drift.py`,
  `test_tracked_template_sources_match_manifest_sources`
- `tests/test_pack_drift.py`, `test_manifest_targets_are_casefold_unique`

## Anti-Patterns

- Do not infer installable files by scanning `templates/`.
- Do not hard-code new template paths only in Python.
- Do not preserve mutable installer state between runs.
- Do not overwrite user files without `--force`.
- Do not overwrite `.prism/rules.json` even with `--force`; users commonly tune
  Prism rules per repo after the initial install.
- Do not run repo-wide validation that reports unrelated target work as an
  installer failure.
