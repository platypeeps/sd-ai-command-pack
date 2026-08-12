# Design: thin consumers, centrally resolved surfaces

Parent-level design. Fixes the architecture and cross-child contracts;
each child refines its own slice. Decisions below were made by the user
on 2026-08-09 against `research/consumer-ci-usage.md` and
`research/claude-code-plugin-capabilities.md`.

## Decisions (fixed)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Machine-scope mechanism for Claude surfaces | Claude Code plugin, user-scope install, distributed via private marketplace hosted in this repo |
| D2 | Sole consumer-CI pack execution (`pr-body-scope.py` in anomaly-metric-creator) | Drop the CI step; it is an advisory no-op (no PR body supplied → always exit 0). No pinned-fetch bootstrap exists anywhere |
| D3 | Non-Claude surfaces (Codex, Gemini, `.agents`, OpenCode) | Machine-scope installer writing user-level config locations, driven by the same update action as the plugin |

## Target architecture

```
sd-ai-command-pack repo (single source of truth)
├── templates/ …               unchanged source surfaces
├── plugin build output        generated from templates at release time
│   ├── .claude-plugin/plugin.json   version = pack VERSION
│   ├── skills/  agents/  hooks/  bin/
├── .claude-plugin/marketplace.json  catalog entry pointing at plugin dir
└── docs/fleet/consumers.json  pin inventory (schema bump)

per machine
├── ~/.claude/plugins/cache/…  plugin install (user scope)
└── ~/.agents ~/.gemini <xdg>/opencode  machine installer output

per consumer repo (thin)
├── .claude/settings.json      extraKnownMarketplaces + enabledPlugins
├── pack pin + provenance receipt (one small file)
├── repo-native platform slice (e.g. GitHub surfaces, 23 files)
└── genuinely repo-scoped config only (e.g. .prism rules)
```

### Plugin packaging (D1)

- Plugin directory is **generated**, not hand-maintained: a build step
  maps manifest-classified machine-scope surfaces (see partition) into
  plugin layout. Skills `.claude/skills/sd-*` → `skills/`; shared
  helper scripts → `bin/` (bare-command invocation on Bash PATH) and/or
  skill-local `scripts/`; agents → `agents/`; hook wiring →
  `hooks/hooks.json`.
- `plugin.json` `version` is stamped from the release authority,
  `manifest.json["version"]` (read by
  `.github/scripts/prepare-release.py`), during `make release-prep`.
  Explicit-version mode means machines update only on release bumps —
  the release remains the single update signal.
- Marketplace: `.claude-plugin/marketplace.json` in this repo; plugin
  entry `source` is a relative path (same repo). Users add once:
  `/plugin marketplace add platypeeps/sd-ai-command-pack`. Private-repo
  auth rides existing git credential helpers (`gh auth setup-git`);
  document `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1` for
  background-update flakiness.
- **Integrity/trust contract:** installs resolve from an authenticated
  git clone of this repository's default branch — the same
  PR-reviewed, CI-gated trust root the vendoring model copies from —
  and the plugin cache updates only when the release-stamped version
  bumps. This is transport-plus-provenance integrity (authenticated
  clone of reviewed main), not an independent artifact digest; the
  PRD requirement is worded to match. An `archive`-source entry with
  `sha256` pin remains a documented upgrade path if a stronger
  end-to-end digest is ever wanted.
- **Helper-script resolution is redesigned, not just re-pointed.**
  Today skills invoke `bash scripts/sd-ai-command-pack-toolchain.sh
  run-python -- scripts/...` and coordinator scripts resolve sibling
  helpers under the consumer repo root, reporting them unavailable
  when absent (e.g. `templates/scripts/sd-ai-command-pack-check.py`).
  The plugin-packaging child changes the resolution contract: every
  pack script resolves siblings relative to its **own file location**
  (payload is self-contained in any install layout — vendored repo,
  plugin cache, or machine dir), and plugin-shipped skills invoke
  entry points as `bin/` bare commands or via
  `${CLAUDE_PLUGIN_ROOT}`. Fat installs keep working because
  own-location resolution is layout-independent. CI verifies zero
  consumer-repo-root script references remain in plugin output
  (`claude plugin validate --strict` plus a grep gate).
- `.claude/rules/*.md` has no plugin equivalent (plugin CLAUDE.md is
  not loaded). Rules content either becomes skill-carried instructions
  or remains a small consumer-repo config file; the plugin-packaging
  child decides per rule, with the partition child classifying each.

### Machine-scope installer for non-Claude surfaces (D3)

- `install.py` gains a machine-scope mode (working name
  `install.py --machine`) that writes the user-level surface
  equivalents for the `machine-other` partition slice plus rows the
  partition flags `sharedRuntime: true` (shared helper scripts that
  non-Claude surfaces invoke at runtime) — the non-Claude platforms
  dispositioned `machine` (verified per platform; fleet-relevant
  candidates: Gemini, OpenCode, Codex/`.agents`). The rest of the
  `machine-claude` slice belongs exclusively to the plugin. Idempotent,
  versioned by a receipt file in the target (records pack version +
  payload digest, mirroring the existing provenance receipt shape).
  Ownership contract: the installer touches only receipt-owned paths
  and refuses to overwrite files it does not own without an explicit
  force flag.
- **Self-containment:** the plugin bundles the machine-installer code
  (`installer/` package) and the `machine-other` payload under the
  plugin root — installed plugins cannot reference paths outside
  their directory, so `sd-pack-update` must find everything in
  `${CLAUDE_PLUGIN_ROOT}`. No pack checkout is required on the
  machine.
- One update action: `sd-pack-update` (plugin `bin/`). Executable
  sequence, accounting for the fact that the running copy lives in
  the OLD plugin root and roots change on update:
  1. `claude plugin update <plugin-name>@<marketplace-name>` (the
     command requires the plugin argument);
  2. resolve the NEW plugin root from `claude plugin list --json`
     (never from the running script's own location);
  3. execute the machine install from that resolved new root, so the
     machine payload can never come from a stale version;
  4. report both resulting versions.
  Partial failure is safe by construction: each half is idempotent
  and re-runnable, the receipt only advances on success, and any
  plugin-vs-receipt version divergence is exactly the skew
  `sd-status` reports. No rollback choreography — rerun converges.
- Per-repo overrides: the thin consumer keeps only genuinely
  repo-scoped config (review-provider rules, repo-specific settings).
  No consumer may override machine-scope surface content; if a repo
  needs divergent behavior, that is a pack feature request, not an
  override file. This keeps "what runs" a function of (machine
  version, repo config), never a third vendored copy.

### Surface partition (requirement 1)

- Partition is computed from `manifest.json` by rule, not by list:
  every payload path classifies into exactly one of four categories —
  `machine-claude` (→ plugin), `machine-other` (→ machine
  installer), `repo-native` (inherently repository-scoped platform
  surfaces that stay vendored, shrunk), or `consumer-config`
  (repo-scoped configuration, stays). `pack-only` is the
  definitional complement: repo files outside the manifest never
  ship and need no inventory.
- **Platform scope disposition is registry-driven.** Every manifest
  row carries a `platform`; the authoritative platform set is
  `PLATFORM_REGISTRY` in `installer/registry.py`, enumerated at
  runtime (18 entries today, including `codex`, which currently ships
  zero manifest rows — a registry platform with no rows still needs a
  disposition). The partition child records one scope disposition per
  registry platform: `machine` (a working user-level surface location
  exists and is verified) or `repo-native` (the platform only reads
  repository-local files). Known already: `github` surfaces (23
  files) are repo-native by construction — GitHub itself reads them
  from the repository; they stay as a shrunk vendored slice or are
  dropped per consumer choice at migration. Fleet reality bounds the
  work: every current consumer installs only `claude`, `gemini`,
  `github`, `opencode` (+ `shared`) per `docs/fleet/consumers.json`
  `platforms`; dispositions for uninstalled platforms are recorded
  but exercise no consumer.
- **`.claude/rules` disposition (decided):** rules remain
  `consumer-config` — repository-scoped instruction files, kept
  small; they are project-context by design and a plugin cannot
  inject them (plugin CLAUDE.md is not loaded). Pack-owned rule text
  keeps shipping to consumers as part of the residual config slice.
- The classifier is a script with an exhaustiveness gate: an
  unclassified manifest path or a platform without a recorded scope
  disposition fails CI. Output feeds the plugin build, the machine
  installer payload, and the migration tooling — three consumers of
  one enumeration, no hand lists.

### Fleet/status rework (requirement 4)

- `consumers.json` schema bump: per-consumer `mode: fat|thin`, pin
  source location for thin consumers.
- `sd-status` local mode adds machine-install inventory: plugin
  version via `claude plugin list --json`, machine-installer receipt
  version. Fleet mode compares consumer pin vs. machine version vs.
  latest release; skew is a follow-up row, never silent. Tree diffing
  retires with the last fat consumer.

### Migration (requirements 3, 5, 6)

- Thin mode coexists with fat: `mode` field drives per-consumer
  behavior of install/refresh/status tooling.
- Per-consumer conversion (cohort order preserved), gated by a
  **conversion-time resweep** of that consumer at its exact HEAD: the
  2026-08-09 fleet sweep is a dated snapshot, so each conversion PR
  re-greps workflows, git hooks, Make targets, and docs for pack
  references before deleting anything. The resweep additionally greps
  for **codex/pi usage markers** (`.codex/` directories, `$CODEX_HOME`
  references, pi adapter files). Which of those markers blocks is
  derived from `retainVendoredFor`, not restated in the scanner: an
  undeclared marker for a retained platform **blocks conversion** until
  the consumer declares the platform (turning retention on) or removes
  the usage, while an undeclared marker for a platform carrying no
  retention is an advisory, because the declaration it would ask for
  changes no conversion plan. Since 0.71.2 that makes pi blocking and
  codex advisory.
  One PR then: deletes the vendored payload (minus the `repo-native` +
  `consumer-config` slices, **and minus any platform's rows whose
  partition entry carries `retainVendoredFor` intersecting this
  consumer's declared `platforms`** — `shared` carries
  `["pi"]`, so a consumer serving pi keeps its `.agents/**` rows
  vendored; `codex` was in that list until 0.71.2 retired it on probe
  evidence that Codex reads `$HOME/.agents/skills`, which the machine
  installer already writes; the fleet registry is the single
  authority, never repo sniffing; evidence in
  `archive/2026-08/08-09-thin-machine-installer/research/platform-verification.md`),
  deletes all pack CI steps (lints +
  the anomaly-metric-creator advisory call per D2), **deletes consumer-
  side sync automation** (anomaly-metric-creator's
  `sd-ai-command-pack-sync.yml`, which would otherwise recreate the
  vendored state), and adds `.claude/settings.json`
  marketplace/enable entries plus the pin receipt.
- Vendored `scripts/` deletion has one extra precondition: retained
  `.agents/**` invokes pack scripts and the contract doc
  repo-relatively, so it is only safe once the machine payload's
  reference rewrite (`~/.agents/bin`, `~/.agents/docs`) ships in
  `08-09-thin-machine-installer`. A consumer retaining `.agents/**`
  for a retained platform (pi today) keeps whatever those rewritten
  references name.
- Revert is a single command that actually reverses conversion
  (working name `install.py TARGET --revert-thin`): restores the fat
  payload, removes the thin artifacts it added (marketplace/enable
  entries, pin receipt), and flips the consumer's `mode` back to
  `fat`. The machine-wide plugin may stay installed; the revert
  writes a per-repo `enabledPlugins` disable so the repo does not see
  duplicate surfaces. Kept until retirement.
- Vendoring gates (mirror byte-identity on consumers, shipped-surface
  closure over consumer installs) retire only after the final
  consumer converts; pack-repo-internal template/root mirror gates
  stay. **Candidate validation is rescoped, not dropped:** the
  release-prep candidate loop (disposable consumer checkouts +
  repo-owned `candidateChecks`) switches from installing the fat
  payload to exercising the thin shape — build the plugin,
  `claude plugin validate --strict`, load it with
  `claude --plugin-dir` in smoke mode, and run the machine installer
  into a scratch prefix — so a pre-release full-fleet compatibility
  gate still exists before any machine-wide update ships.
- Spec/doc updates ride each child by enumeration (grep of
  install/fleet spec surfaces), per requirement 6.

### se-ai-command-pack (special shape)

Its relationship to this pack is source derivation, not runtime
consumption: it vendors pack code to re-ship it. It migrates for its
*agent-side* surfaces like any consumer (plugin + machine installer),
but its derivation pipeline is out of scope here and continues from
pack releases; its `candidateChecks` entry carries into the rescoped
thin-shape candidate loop (see Migration) rather than being dropped.

## Tradeoffs accepted

- **Per-machine, not per-repo, agent-surface versioning.** Plugin cache
  holds one active version per machine; a consumer repo can no longer
  hold agent surfaces at an older pack version. Accepted: this is the
  point of the reshape; CI-side behavior no longer depends on pack
  code at all (D2), so version skew only affects interactive agent
  behavior and is surfaced by `sd-status`.
- **Marketplace background auto-update flakiness on private repos** is
  a documented operational caveat, not something we engineer around
  (manual `sd-pack-update` is the sanctioned path).
- **Non-Claude platforms lack a plugin system**; the machine installer
  is bespoke by necessity, kept minimal by reusing install.py payload
  and receipt machinery.
- **A platform may lack a usable user-scope location.** The
  machine-installer child must verify per platform (Codex, Gemini,
  `.agents` consumers, OpenCode) that user-level surface resolution
  actually works; any platform that only reads repo-local surfaces
  falls back to a shrunk vendored slice for that platform only, with
  the partition classifier marking those paths so the migration child
  keeps them. This contingency narrows the thin model; it does not
  block it.

## Rollout / rollback shape

Children land in order: partition → plugin packaging → machine
installer → fleet/status → migration. Each is independently
verifiable and reversible; no consumer migrates before the first four
ship. Fat mode remains fully supported until the last consumer
converts, and reverting any consumer is one command throughout.
