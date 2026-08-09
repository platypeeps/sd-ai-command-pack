# Design: surface partition classifier

Child of `08-09-deployment-thin-consumers`; parent design fixes the
category set and the registry-driven disposition requirement. This
design fixes the mechanism.

## Shape

A pack-repo-only generator + checker,
`.github/scripts/partition-surfaces.py`, following the existing
partition-regenerate pattern (`generate-command-surfaces.py`): it
reads `manifest.json` and `PLATFORM_REGISTRY` from
`installer/registry.py`, and emits a committed artifact
`docs/fleet/surface-partition.json`. `--check` mode regenerates and
diffs; any drift, unclassified file, or undispositioned platform
exits nonzero.

## Classification rules

Evaluation order per manifest row (first match wins; exactly one rule
class must claim every row — a fall-through is a hard error, not a
default):

1. **Target-path overrides** (small, reviewed rule table in the
   script), verified against current manifest rows:
   - `.claude/rules/**` (1 row) and `.claude/sd-ai-command-pack/**`
     (1 row — the contract document the rule links as a repo-relative
     sibling) → `consumer-config`;
   - review-provider repo configs `.prism/**` (2 rows) and
     `.gito/**` (2 rows, platform `shared`) → `consumer-config`;
   - `scripts/**` (26 rows, platform `shared`) → `machine-claude`
     (shipped as plugin `bin/`/payload executables), each row
     additionally flagged `"sharedRuntime": true`: non-Claude
     surfaces invoke these scripts at runtime (e.g. the shared
     `sd-create-pr` skill and the Gemini `sd/review` command call
     the toolchain wrapper), so the machine installer consumes the
     `machine-other` slice PLUS all `sharedRuntime` rows. Primary
     category stays exclusive; `sharedRuntime` is the explicit
     dependency/duplication contract.
   The provenance receipt has NO manifest row (it is created at
   install time), so it needs no override; the consumer-config
   category covers shipped files only.
2. **Platform disposition** (from the per-platform table): rows of a
   `machine`-dispositioned platform → `machine-claude` (claude) or
   `machine-other` (any other machine platform); rows of a
   `repo-native` platform → `repo-native`.
3. **Fail-closed exhaustiveness** — platform disposition alone would
   be a catch-all, so three independent error conditions keep the
   gate reachable: (a) a row whose `platform` is not a
   `PLATFORM_REGISTRY` key; (b) a row whose `kind` is outside the
   recognized set (`skill`, `command`, `prompt`, `workflow`,
   `script`, `config`, `doc`, `managed-block` today — a new manifest
   kind must be classified deliberately, not absorbed); (c) a
   target-path override pattern that matches zero manifest rows
   (stale override). Each is a distinct nonzero-exit diagnostic.

The manifest partition has exactly FOUR categories
(`machine-claude`, `machine-other`, `repo-native`,
`consumer-config`). `pack-only` is not a manifest category: it is
the definitional complement — repo files not in the manifest are
never shipped, so they need no inventory (the parent PRD is worded
accordingly).

Expected snapshot split (current manifest, for review sanity):
`consumer-config` 6, `machine-claude` 83 (57 claude + 26 scripts),
`machine-other` ≈ 92-94 (shared remainder + gemini + opencode +
codex), `repo-native` 593. The repo-native bulk is platforms **no
fleet consumer installs** (per `docs/fleet/consumers.json`
`platforms`); the only repo-native slice consumers actually carry is
`github` (23 files).

## Per-platform disposition table

Encoded in the script, one entry required per `PLATFORM_REGISTRY` key
(enumerated at runtime — 18 today; a registry key without an entry
fails, a stale entry for a removed key fails):

| Disposition | Platforms (initial) |
|-------------|--------------------|
| `machine` | `claude` (plugin); `shared`, `gemini`, `opencode`, `codex` — **provisional** pending the machine-installer child's per-platform verification |
| `repo-native` | `github` (by construction) and the remaining repo-local-only platforms (`antigravity`, `codebuddy`, `cursor`, `devin`, `droid`, `kilo`, `kiro`, `pi`, `qoder`, `reasonix`, `trae`, `zcode`) |

Provisional entries carry `"provisional": true` in the output, and
the schema contract makes them **fail closed downstream**: a
consumer of the artifact (machine installer, migration tooling) must
treat a provisional platform as not yet installable machine-scope —
effectively repo-native — until the machine-installer child's
verification flips `provisional` to `false` (or the disposition to
`repo-native`) via a one-line table change (parent design
contingency). `claude` is non-provisional from the start: the plugin
mechanism is itself the verification.

## Output schema (`docs/fleet/surface-partition.json`)

```json
{
  "schemaVersion": 1,
  "manifestVersion": "<manifest.json version at generation>",
  "platforms": {"claude": {"scope": "machine", "provisional": false}},
  "counts": {"machine-claude": 0, "machine-other": 0,
              "repo-native": 0, "consumer-config": 0},
  "files": [{"target": "...", "platform": "...", "category": "...",
              "sharedRuntime": false}]
}
```

Schema semantics for consumers: `provisional: true` platforms are
not installable machine-scope until verified; `sharedRuntime: true`
rows are consumed by the machine installer in addition to the
`machine-other` slice.

Downstream consumers (plugin build, machine installer payload,
migration tooling) read `files`/`platforms`; `counts` +
`manifestVersion` make drift reviewable in diffs.

## Gates

- `make generate` runs the generator; the existing mirror/idempotence
  discipline applies (regenerating twice is byte-identical).
- CI enforcement follows the repository's actual generated-surface
  pattern: a live-tree unittest (like
  `tests/test_surface_generation.py`) that runs the classifier in
  `--check` mode against the committed tree — CI runs the test
  suite; there is no separate workflow lane. Failures name the
  offending path, platform, kind, or stale override.
- Unit tests (`tests/test_partition_surfaces.py`, unittest): full
  coverage of rule order, fall-through error, registry/table
  mismatch in both directions, schema shape, idempotence.

## Non-goals

- No behavior change to install/generate flows beyond the new
  artifact + gate.
- No disposition verification (machine-installer child owns that).
- No consumption wiring (plugin-packaging child reads the artifact).
