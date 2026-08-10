# Repoint surviving pack surfaces off removed paths

## Goal

Six pack-shipped files survive a thin conversion and still cite paths the
conversion removes — five prompts that instruct an agent to run removed
scripts, plus the managed block inside `.github/copilot-instructions.md`.
Until they are repointed, every consumer's resweep returns `packDefects`
and no conversion can proceed. This task fixes the pack side so children
3–5 of the thin migration can run at all.

## Evidence

Measured 2026-08-10 across all 8 registered consumers, identically in
each — 13 hits in 6 files. Reproduce with the scanner committed under the
sibling task:

```bash
.venv/bin/python .trellis/tasks/08-10-thin-conversion-tooling/research/\
fleet-blocker-scan.py --out /tmp/scan.json
```

| Surviving file | Line | Cites |
|---|---|---|
| `.github/prompts/sd-housekeeping.prompt.md` | 37, 38 | `scripts/sd-ai-command-pack-housekeeping.sh` |
| `.github/prompts/sd-review-learnings.prompt.md` | 44, 46 | `scripts/sd-ai-command-pack-review-learnings.py` |
| `.github/prompts/sd-review.prompt.md` | 43 | `scripts/sd-ai-command-pack-review.py`, `scripts/sd-ai-command-pack-toolchain.sh` |
| `.github/prompts/sd-status.prompt.md` | 43 | `scripts/sd-ai-command-pack-toolchain.sh` |
| `.github/prompts/sd-help.prompt.md` | 31, 32 | `references/command-catalog.md`, `references/examples.md` under the removed `.agents/skills/sd-help/` |
| `.github/copilot-instructions.md` | 27, 51, 54, 106, 108 | `docs/SD_AI_COMMAND_PACK.md`, `scripts/sd-ai-command-pack-install-audit.py` |

Every one is a `repo-native` partition row (`platform: github`) that the
conversion **keeps** — verified against `docs/fleet/surface-partition.json`,
not assumed. `repo-native` is exactly why they survive and therefore
exactly why their stale citations matter.

The five prompts are byte-for-byte the pack's own copy in every consumer.
`.github/copilot-instructions.md` is different in kind: it is a
**managed-block** target, so provenance never records a whole-file digest
for it and only the content between the pack's
`SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START`/`:END` markers is ours. All
five of its hits are inside that block. The repoint must stay inside the
markers; editing outside them would rewrite consumer content.

`templates/.github/prompts/**` and
`templates/.github/copilot-instructions.sd-ai-command-pack.md` are the
canonical sources; `scripts/`, `plugins/sd/bin/`, and
`plugins/sd/machine-payload/scripts/` are byte-verified mirrors, so the
edit goes to the template and then through `make sync` and
`make generate`.

## Requirements

1. Each of the six surfaces resolves its cited path through a location that
   exists in **both** a fat and a thin checkout, or it detects the mode
   and branches explicitly. A prompt that silently assumes one layout
   fails on the other, and the failure surfaces as an agent following an
   instruction that cannot execute.
2. The instruction text keeps its existing verify-then-run shape. These
   prompts already tell the agent to confirm the script exists before
   running it; a repoint must not turn that into an unguarded call.
2b. The `copilot-instructions` edit stays within the pack's managed-block
   markers, and `make check`'s block-integrity handling still treats the
   file as `UPDATED` rather than `PRESERVED` on a consumer refresh.
3. The resweep reports zero `packDefects` for every registered consumer
   after the change ships and consumers refresh. That is the acceptance
   signal, not a reading of the diff.
4. The change carries a `manifest.json` version bump and a CHANGELOG
   entry — it is a shipped-payload change, and the release gate fails
   otherwise.

## Non-goals

- Repointing any **consumer-authored** execution surface. That is the
  per-consumer work in children 3–5 and needs per-cohort authorization.
- Changing what the thin conversion deletes. The delete set is contract
  C-B and is not up for renegotiation here.

## Acceptance criteria

- [ ] All six surfaces resolve their cited paths in a thin checkout,
      proven against the converted fixture from
      `08-10-thin-conversion-tooling`, not by inspection.
- [ ] All six still resolve in a fat checkout — the fat path is the one
      every consumer is on today, and breaking it to fix thin trades one
      outage for another.
- [ ] `fleet-blocker-scan.py` (or the shipped resweep, once it exists)
      reports `packDefects: 0` for a consumer refreshed to the new pack
      version.
- [ ] Template edited first, then `make sync` and `make generate`; the
      mirror gate passes with no manual mirror edits.
- [ ] `manifest.json` bumped, CHANGELOG entry added, `make check` green.

## Blocking relationship

This blocks children 3–5 of `08-09-thin-migration`. A `packDefects`
entry blocks `--thin` by design, so no consumer conversion can proceed
until this lands. It does not block
`08-10-thin-conversion-tooling` itself: that task builds the resweep
that detects this condition, and detecting it correctly is the point.
