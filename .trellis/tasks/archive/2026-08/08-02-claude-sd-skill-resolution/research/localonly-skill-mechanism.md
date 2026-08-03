# Research: pack-local `.claude/skills/sd-*` surfacing mechanism + gates

- **Query**: Map the precise mechanism and every gate a change must satisfy to surface `sd-*` skills into `.claude/skills/sd-<name>/` **pack-local only** (present + resolvable in the pack's own checkout, NOT shipped into consumer repos), mirroring how `trellis-*` skills already appear under `.claude/skills/`.
- **Scope**: internal
- **Date**: 2026-08-02

---

## TL;DR structured map

| Fact | Evidence |
|---|---|
| `--local-only` does **not** write skills. It writes only `.git/info/exclude` block + `.sd-ai-command-pack/local-only.txt` marker. Pack payload is still installed to disk by the normal install flow; the exclude keeps it untracked. | `installer/localonly.py`; `install.py:733-757` |
| Trellis `.claude/skills/trellis-*` files at consumer install time come from **`trellis init`** (external Trellis CLI), not this pack. | `installer/localonly.py:135-205` (`trellis_init_command`, `ensure_trellis_for_local_only`) |
| `trellis_local_only` is a per-platform **consumer git-exclude glob list**, NOT a pack generation source. claude row already lists `.claude/skills/trellis-*/`. | `installer/registry.py:73-79` |
| Pack's own `.claude/skills/trellis-*` (40+ files) are **git-tracked dogfood**, written by `trellis init --claude` and committed manually. No template, no generator produces them. | `git ls-files .claude/skills/`; grep shows only registry *references* |
| SD skills currently fan out only to `.agents/skills/sd-*/` (shared) + `SKILL_FANOUT_PLATFORMS` dirs. **claude is NOT in `SKILL_FANOUT_PLATFORMS`**; claude gets `.claude/commands/sd/<short>.md` instead. So `.claude/skills/sd-*/` does not exist today. | `registry.py:456-467`, `1196-1215`; `git ls-files .claude/skills \| grep sd-` → empty |
| `sd-fleet-refresh` is source-only: excluded from `manifest.json`/consumer fanout, but its dev-tree adapters (incl. `.claude/commands/sd/fleet-refresh.md`) ARE generated + committed → it already resolves as `/sd:fleet-refresh` in the Claude pack checkout. | `registry.py:1169`; `generate-command-surfaces.py:910-928`; `git ls-files \| grep fleet-refresh` |
| `manifest.json` contains **zero** trellis / `.claude/skills` entries. Pack-local sd skills, to stay pack-local, must likewise stay OUT of manifest (manifest == consumer fanout). | `grep -c "trellis\|.claude/skills" manifest.json` → `0` |

---

## 1. localonly mechanism (`installer/localonly.py`)

`--local-only` is a set of **pre-steps** layered onto the normal install; it never
writes skill files itself. In `install.py:733-757` the local-only branch runs, in order:

1. `require_git_repo_for_local_only(target)` — `localonly.py:83-102` — target must be the git repo root.
2. `selected_files(...)` then `reject_tracked_local_only_paths(target, selected)` — see below.
3. `ensure_trellis_for_local_only(...)` — runs `trellis init` (this is where trellis `.claude/skills/trellis-*` come from).
4. `ensure_local_only_exclude(target, selected, ...)` — writes the `.git/info/exclude` block.

The pack's own payload files are then written by the ordinary install path; the
exclude block is what keeps them (and the trellis files) untracked in the consumer clone.

### What writes the trellis `.claude/skills` files at install time
`ensure_trellis_for_local_only` (`localonly.py:147-205`) shells out to
`trellis_init_command` (`localonly.py:135-144`):
```
trellis init --yes --skip-existing --codex [--claude ...]
```
Platform flags come from `TRELLIS_INIT_PLATFORM_FLAGS` (`registry.py:1857-1861`, derived
from each `PlatformInfo.init_flag`; claude's is `--claude`, `registry.py:63`). So
**Trellis' own CLI** materializes `.claude/skills/trellis-*/`. This pack contributes
nothing to those files' content — it only later *excludes* them from git.

### `reject_tracked_local_only_paths` (`localonly.py:266-277`)
Runs `git ls-files --` over `local_only_tracked_check_specs(selected)`
(`localonly.py:227-237` = `LOCAL_ONLY_TRACKED_CHECK_PATHS` + each selected pack target +
`installed-targets.txt` + marker). If **any** are already tracked → prints them and
`SystemExit`. Enforces the invariant: `--local-only` may only manage paths that are NOT
already committed. `LOCAL_ONLY_TRACKED_CHECK_PATHS` (`registry.py:1881-1889`) is the
`trellis_local_only` globs (trailing `/` stripped) across all platforms, incl.
`.claude/skills/trellis-*`.

### git exclude block management (all in `localonly.py`)
- `local_only_exclude_patterns(selected)` (216-224) = `LOCAL_ONLY_TRELLIS_EXCLUDES` +
  `local_only_pack_excludes(selected)` (208-213: the selected pack targets +
  `installed-targets.txt` + marker + `.sd-ai-command-pack/`).
- `local_only_exclude_block(patterns)` (280-288) — renders the text bracketed by
  `LOCAL_ONLY_EXCLUDE_START`/`END` (`registry.py:1902-1903`).
- `merge_local_only_exclude_block(current, block)` (291-311) — replaces an existing
  marked block in place, else appends with a blank-line separator.
- `ensure_local_only_exclude(target, selected, *, dry_run)` (314-339) — resolves
  `.git/info/exclude` via `git_info_exclude_path` (105-119, `git rev-parse --git-path
  info/exclude`), validates path, merges, `atomic_write_text`.
- `remove_local_only_exclude(target, *, dry_run)` (374-402) — strips the marked block
  on uninstall.
- `write_local_only_marker(target, *, dry_run)` (342-364) — writes
  `.sd-ai-command-pack/local-only.txt` (`LOCAL_ONLY_MARKER_FILE`, `registry.py:1901`).

**Source of the trellis `.claude/skills` files at install time = the external
`trellis init` command, not this pack.** The exclude patterns for those files come from
`LOCAL_ONLY_TRELLIS_EXCLUDES` (`registry.py:1871-1880`).

---

## 2. registry wiring (`installer/registry.py`)

### The field
`PlatformInfo.trellis_local_only: tuple[str, ...]` (`registry.py:24`). claude row
(`registry.py:73-79`):
```python
trellis_local_only=(
    ".claude/agents/trellis-*.md",
    ".claude/commands/trellis/",
    ".claude/hooks/",
    ".claude/settings.json",
    ".claude/skills/trellis-*/",
),
```
This is the **per-platform local-only glob list** you would extend. Despite the
`trellis_` name it is simply "the paths `--local-only` excludes for this platform." To
surface pack-local `.claude/skills/sd-*/` while keeping them out of consumer commits,
adding `.claude/skills/sd-*/` here would extend the consumer git-exclude — but note this
tuple only affects the CONSUMER `--local-only` exclude/tracked-check; it does **not**
create or generate any file.

### How it is consumed
- `_ordered_platform_groups_with_local_only()` (`registry.py:1795-1800`) = set of
  platforms whose `trellis_local_only` is non-empty.
- Validated against the byte-stability order tuple `_LOCAL_ONLY_GROUP_ORDER`
  (`registry.py:1759-1778`) by `_validate_registry_group_orders()` (`1837-1850`). **A
  registry row with local-only entries that is missing from this order tuple raises at
  import.** (claude is already present.)
- `LOCAL_ONLY_TRELLIS_EXCLUDES` (`1871-1880`) and `LOCAL_ONLY_TRACKED_CHECK_PATHS`
  (`1881-1889`) flatten every platform's `trellis_local_only` in that order. These are
  imported by `localonly.py:30-31`.
- `install.py` imports `_ordered_platform_groups_with_local_only`
  (`install.py:118`) but uses it only for validation/reporting, not for a fanout loop.

**There is no separate "local_only skill globs" concept distinct from
`trellis_local_only`.** That tuple *is* the per-platform local-only glob set. It governs
consumer git-exclude only; it is not a pack-side generator input.

---

## 3. Are pack `.claude/skills/trellis-*` files git-tracked, and where's their source?

**Yes, tracked.** `git ls-files .claude/skills/` returns 40+ files (all `trellis-*`,
e.g. `.claude/skills/trellis-before-dev/SKILL.md`, `trellis-meta/...`, etc.). Zero
`sd-*` entries under `.claude/skills/`.

**Source: not generated by this pack.** Grep evidence:
- `grep -rn ".claude/skills" .github/scripts/ installer/ Makefile` → only two hits, both
  *references* in `registry.py` (`:61` marker, `:78` local-only glob). No writer.
- `find templates -path '*skills/trellis*'` → empty; `find templates -path
  '*.claude/skills*'` → empty. **No trellis-skill template and no `.claude/skills`
  template exist.**
- The generator (`generate-command-surfaces.py`) writes only into `templates/…` and
  `manifest.json` (see `write_surfaces` / `generate_surfaces` `:931-990`). It never
  touches `.claude/skills/`.

So the pack's `.claude/skills/trellis-*` are **dogfood artifacts written by `trellis
init --claude` and committed manually** into the pack repo.

**Reconciliation (tracked-in-pack vs local-only-in-consumer):**
- Pack repo: trellis files are committed (dogfooding Trellis in the pack's own checkout).
- Consumer via `--local-only`: the *same globs* (`.claude/skills/trellis-*/`) are added to
  `.git/info/exclude` (§1) so the consumer's `trellis init`-generated copies stay
  untracked. `reject_tracked_local_only_paths` even forbids `--local-only` if they are
  already tracked.
- These are two independent facts; `trellis_local_only` is only the consumer-exclude
  side. Nothing syncs `.agents/skills/trellis-*` → `.claude/skills/trellis-*` (the pack
  has no trellis skill sources at all).

**How analogous `.claude/skills/sd-*` would get created / kept in sync:** there is
currently **no path that produces them**. Options implied by the codebase:
- (a) Mirror the trellis dogfood pattern: commit hand/tool-authored `.claude/skills/sd-*`
  files directly into the pack (but nothing generates them, so they would drift from the
  canonical `.agents/skills/sd-*/SKILL.md`).
- (b) Add a **new generation/sync step** in `generate-command-surfaces.py` that emits
  `.claude/skills/sd-*/SKILL.md` from `templates/.agents/skills/sd-*/SKILL.md` into the
  dev tree — analogous to `generate_source_only_dev_adapters` (`:910-928`), which already
  emits dev-tree-only adapters that are excluded from `manifest.json`.
- Note `make sync` = `install.py . --force` (`Makefile:31-33`) installs strictly from
  `manifest.json`; since manifest has no `.claude/skills/sd-*` rows, **sync will never
  create them.** A pack-local surface must therefore be produced by the generator
  (option b) or committed directly (option a), not by the installer.

---

## 4. SOURCE_ONLY interaction

`SOURCE_ONLY_COMMAND_NAMES = frozenset({"sd-fleet-refresh"})` (`registry.py:1169`).

### Every consumer
- **registry.py**: `validate_source_only_command_names` (`:1675-1684`, called `:1717`);
  `SOURCE_ONLY_SKILL_REFERENCES = {"sd-fleet-refresh": ("references/controller-recovery.md",)}`
  (`:1175-1177`, validated `:1687-1720`); `source_only_adapter_twins(...)` (`:1219-1268`)
  returns `(template source, dev-tree target)` pairs per platform (incl. claude →
  `.claude/commands/sd/fleet-refresh.md`) gated on anchor-dir existence.
- **generate-command-surfaces.py**: import (`:82`); command catalog marks them
  `source-checkout-only` (`:355-356`); `generate_manifest_text` **excludes** source-only
  names from the derived manifest (`:889-894`); `generate_source_only_dev_adapters`
  (`:910-928`) emits their dev-tree adapters (this is why they resolve pack-local without
  a manifest row).
- **check-command-surface-drift.py**: import (`:28`); `_manifest_findings` flags a
  source-only command that STILL has a manifest target as
  `generated_registry_mismatch` (`:415-427`) — i.e. source-only must have **zero**
  manifest entries.
- **scripts/sd-ai-command-pack-surface-check.py**: `_source_only_paths` (`:302-312`)
  collects source-only template paths; `_graph` marks them `source-only` with an
  `excluded-from` edge to the manifest node (`:367-369`); `_node_kind` maps them to
  `source-only` (`:315-317`).
- **scripts/sd-ai-command-pack-install-audit.py**: `SOURCE_ONLY_ALLOWED_PACK_FILES`
  (`:85-90`, includes `.agents/skills/sd-fleet-refresh/references/controller-recovery.md`)
  allow-lists source-only files in the *source* repo (`:636`); consumer audit does not
  require them.
- **installer/removal.py**: `SOURCE_ONLY_COMMAND_TARGETS =
  retired_surface_targets("fleet-refresh-consumer-targets")` (`:66`) drives removal of
  any stray consumer fanout (`:276`). Retired surface `fleet-refresh-consumer-targets`
  (`registry.py:1299-1308`, `source_paths_must_be_absent=False`) declares the consumer
  footprint that must be absent from the consumer manifest.
- **tests**: `test_surface_generation.py:506-550`, `test_surface_closure.py:238-360`,
  `test_help_command.py:506-610`, `test_install_audit.py:73-131`,
  `test_generated_parity.py:389`.

### What must change for pack-local sd skills incl. `sd-fleet-refresh`
Today `sd-fleet-refresh` already resolves pack-local as the **command**
`.claude/commands/sd/fleet-refresh.md` (tracked; generated by
`source_only_adapter_twins` → claude). To surface sd skills as `.claude/skills/sd-*/`
with `sd-fleet-refresh` INCLUDED pack-local but excluded from consumer fanout, the
pack-local skill surface must follow the **same source-only shape**:
- The `.claude/skills/sd-fleet-refresh/` files must be produced into the **dev tree only**
  (like `generate_source_only_dev_adapters`), and must **not** appear in `manifest.json`
  (or the drift check's `generated_registry_mismatch` fires, `:415-427`).
- Surface-check must classify `.claude/skills/sd-fleet-refresh/*` as `source-only` (not
  `installable`), else the closure graph flags it (`_node_kind` returns `installable` for
  any non-`templates/`, non-provenance path, `surface-check.py:315-328`).
- For the **non**-source-only sd skills, the pack-local `.claude/skills/sd-*` copies must
  also be produced pack-local-only and excluded from manifest (otherwise they become
  consumer fanout). So the whole `.claude/skills/sd-*` surface should be a pack-local /
  dev-tree-only channel, with `sd-fleet-refresh` simply included in it rather than
  filtered out.

---

## 5. Gates / tests that assert skill surfaces

| Gate | Currently asserts about `.claude/skills` / sd skills | Break/risk from pack-local `.claude/skills/sd-*` |
|---|---|---|
| `.github/scripts/check-command-surface-drift.py` | `SKILL_PUBLIC_ROOTS = .agents + SKILL_FANOUT_PLATFORMS dirs` (`:58-69`); **claude NOT included**. `.claude/skills/sd-*/SKILL.md` matches NO `PUBLIC_PATH_PATTERNS` (`:98-121`) → `_path_command` returns None → **not flagged**. | Neutral today (ignored). **Trap:** if you add claude to `SKILL_FANOUT_PLATFORMS` to generate them, the pattern would then require registry rows + manifest targets → consumer fanout (exactly what we must avoid). Must NOT route through `SKILL_FANOUT_PLATFORMS`. |
| `scripts/sd-ai-command-pack-surface-check.py` (`make generate` + `surface-check`) | Builds a closure graph; `_node_kind` (`:315-328`) classifies any non-`templates/` path not in source-only/provenance/check-only as **`installable`**. `.claude/skills/sd-*` would be graphed as `installable` with a manifest `declares` edge expected. | Would need `.claude/skills/sd-*` classified as source-only/pack-local, or added to a pack-local node kind, else closure/coverage assertions in `test_surface_closure.py` fail. |
| `tests/test_surface_closure.py` | `test_live_surface_is_clean_and_json_is_versioned` (`:65`); source-only graph tests (`:113,218-360`). | New `.claude/skills/sd-*` nodes must be classified so the live surface stays "clean". |
| `tests/test_generated_parity.py` | Enumerates installed shared skills `.agents/skills/sd-*/SKILL.md` (`:238-263`) and claude **commands** `.claude/commands/sd/*.md` (`:362+`). No `.claude/skills` expectation. | If the generator emits `.claude/skills/sd-*`, parity expectations must be extended; if committed by hand, parity won't see them but generator `--check` drift still applies to any generated set. |
| `tests/test_install_audit.py` | `SOURCE_ONLY_ALLOWED_PACK_FILES` handling (`:73-131`); asserts source-only fleet files allowed in source repo, not required in consumer. | `.claude/skills/sd-*` are not in `PACK_FILE_PATTERNS`, so audit ignores them today. If they should be recognized/protected, add to `PACK_FILE_PATTERNS` and possibly `SOURCE_ONLY_ALLOWED_PACK_FILES`; that then pulls them into audit assertions. |
| `scripts/sd-ai-command-pack-install-audit.py` | `PACK_FILE_PATTERNS` (`:38+`) has `.claude/commands/sd/*` but **NOT** `.claude/skills/sd-*`. `collect_pack_like_files` (`:559-572`) only scans derived bases → won't see `.claude/skills/sd-*`. | Neutral today. To make them audited/uninstallable, add the pattern (and they'd then be expected against manifest — conflicts with pack-local-only unless allow-listed like source-only). |
| fleet candidate ledger (`scripts/sd-ai-command-pack-fleet-candidate-check.py` + `docs/fleet/candidate-validation.json`) | Validates a release candidate against disposable consumer checkouts via `validate_candidate_ledger`; runs consumer install + install-audit. Does not directly assert skills, but a consumer that unexpectedly received `.claude/skills/sd-*` would fail consumer install-audit. | Ensures the pack-local surface truly stays out of consumer fanout; a leak into manifest would surface here. |
| `make generate` / `make sync` / `make check` | `generate` = `generate-command-surfaces.py` (writes `templates/` + `manifest.json`) then `surface-check.py` (`Makefile:17-24`). `sync` = `install.py . --force` from manifest (`:31-33`). `check` = `test lint audit full-check` (`:95`). | `generate` must be the producer of any pack-local `.claude/skills/sd-*` (sync can't, manifest can't). `surface-check` inside `generate` will fail unless the new surface is classified. `pr-body-scope.py` already lists `.claude/skills/sd-*/**` as a pack surface glob (`:142`), so PR scope classification is pre-wired. |

Additional note: `scripts/sd-ai-command-pack-pr-body-scope.py:142` (and its
`templates/` twin) **already** enumerate `.claude/skills/sd-*/**` (and every platform's
`skills/sd-*/**`) as pack-owned surfaces for PR-body scope classification — so that gate
anticipates the surface and would not need changes to recognize it.

---

## 6. Manifest impact

- **Trellis `.claude/skills` in manifest: none.** `grep -c "trellis\|.claude/skills"
  manifest.json` → `0`. Manifest holds only sd/pack files. Trellis files never appear
  because they are produced by `trellis init`, not by pack install, and consumer
  `--local-only` git-excludes them.
- **`install` field semantics** (`registry.py:1781-1784`,
  `KNOWN_INSTALL_MODES = {always, if-anchor-exists, if-not-exists}`):
  - `install: always` — 80 entries; all shared skills `.agents/skills/sd-*/…`
    (`generate-command-surfaces.py:789-798, 756-765`). Installed unconditionally.
  - `install: if-not-exists` — 2 entries.
  - No `install` field (658 entries) — carry an `anchor` (e.g. `.claude`) → installed
    only when the anchor directory exists (if-anchor-exists). All claude command rows use
    this (`generate-command-surfaces.py:799-808`).
- **Would pack-local sd skills add manifest entries?** To stay pack-local (like trellis
  local-only and like `sd-fleet-refresh` source-only), they should **stay OUT of
  `manifest.json`**. Any manifest row = consumer fanout (the installer installs every
  manifest file gated only by anchor/install mode). There is no manifest flag that means
  "install in the pack checkout but never in consumers" — the source-only pattern
  achieves that by **omitting** the entry from manifest while the generator still emits
  the dev-tree file (`generate_manifest_text` skips `SOURCE_ONLY_COMMAND_NAMES`,
  `:889-894`; `generate_source_only_dev_adapters` writes the dev copy, `:910-928`).
- **Therefore:** pack-local `.claude/skills/sd-*` should mirror the **source-only /
  dogfood** model — produced into the dev tree, **absent from `manifest.json`** — not a
  new `install:` flag. The `install` enum has no "local/pack-only" value, and adding one
  would require installer + audit + drift changes; the existing omit-from-manifest
  channel is the established mechanism.

---

## Caveats / Not Found

- I did not find any existing generator, template, or sync step that writes
  `.claude/skills/*` (trellis or sd). Confirmed by grep across `.github/scripts/`,
  `installer/`, `Makefile`, and `find templates`. If a design assumes a generator will
  produce `.claude/skills/sd-*`, that generator does **not exist yet** and must be added
  (likely in `generate-command-surfaces.py`, following the
  `generate_source_only_dev_adapters` precedent).
- I did not exhaustively read `installer/removal.py` uninstall paths for how a pack-local
  `.claude/skills/sd-*` set would be removed on `install.py --uninstall`; only the
  source-only target retirement wiring (`:66,72,276`) was traced.
- The exact content/frontmatter a Claude Code `.claude/skills/sd-*/SKILL.md` needs to be
  *discoverable/resolvable* by Claude Code was not researched here (this doc maps the
  pack's surfacing/gate mechanics, not Claude Code's skill-loader requirements).
