# Surface partition: manifest + platform-registry classifier

Child of `08-09-deployment-thin-consumers`. Requirement 1 of the parent
PRD; architecture in parent `design.md` ("Surface partition").

## Deliverable

A classifier script that assigns every `manifest.json` payload file to
exactly one category — `machine-claude`, `machine-other`,
`repo-native`, `consumer-config`, `pack-only` — derived from manifest
rows and `installer/registry.py`, plus a recorded per-platform scope
disposition (`machine` or `repo-native`) for every platform in
`PLATFORM_REGISTRY`, enumerated at runtime (18 today, including
`codex`, which currently ships zero manifest rows but still requires
a disposition).

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
- [ ] CI gate demonstrably fails on a synthetic unclassified path and
      on a registry platform with no disposition.
- [ ] Downstream consumption contract (output schema) documented and
      referenced by the sibling children's PRDs.
