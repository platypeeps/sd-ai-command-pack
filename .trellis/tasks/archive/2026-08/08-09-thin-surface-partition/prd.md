# Surface partition: manifest + platform-registry classifier

Child of `08-09-deployment-thin-consumers`. Requirement 1 of the parent
PRD; architecture in parent `design.md` ("Surface partition").

## Deliverable

A classifier script that assigns every `manifest.json` payload file to
exactly one of FOUR categories — `machine-claude`, `machine-other`,
`repo-native`, `consumer-config` — derived from manifest rows and
`installer/registry.py`, plus a recorded per-platform scope
disposition (`machine` or `repo-native`) for every platform in
`PLATFORM_REGISTRY`, enumerated at runtime (18 today, including
`codex`, which currently ships zero manifest rows but still requires
a disposition). `pack-only` is the definitional complement (repo
files outside the manifest are never shipped) and is not a manifest
row category.

## Requirements

1. Classification is computed by rule from manifest + registry, never
   a hand-maintained path list.
2. Exhaustiveness gate in pack CI: an unclassified manifest path or a
   platform without a scope disposition fails.
3. Output is machine-readable and consumed downstream by the plugin
   build, the machine installer payload, and migration tooling (three
   consumers, one enumeration).
4. Known dispositions encoded: `github` is repo-native by
   construction; `.claude/rules` is consumer-config (parent design
   decisions); fleet-installed platforms are `claude`, `gemini`,
   `github`, `opencode`, `shared`.

## Ordering constraints

- First child; blocks `thin-plugin-packaging`,
  `thin-machine-installer`, and `thin-migration`, which all consume
  its output.

## Acceptance criteria

- [ ] Classifier over current manifest covers all 776 files with zero
      unclassified paths; category counts published in task research.
- [ ] CI gate demonstrably fails on each fail-closed condition:
      unknown platform, unknown manifest `kind`, registry platform
      with no disposition, stale disposition entry, and stale
      target-path override (design fixes these as distinct
      diagnostics — platform disposition alone is a catch-all, so
      kind/override checks keep the gate reachable).
- [ ] Downstream consumption contract (output schema) documented and
      referenced by the sibling children's PRDs.
