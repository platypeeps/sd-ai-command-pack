# Repoint surviving pack surfaces off removed paths

## Goal

Six pack-shipped files survive a thin conversion and still cite paths the
conversion removes — four prompts that instruct an agent to run removed
scripts, the managed block inside `.github/copilot-instructions.md`, and
the force-preserved `.github/PULL_REQUEST_TEMPLATE.md`. Until they are
repointed, every consumer's resweep returns `packDefects` and no
conversion can proceed. This task fixes the pack side so children 3–5 of
the thin migration can run at all — with one exception it states
explicitly rather than papering over: the PR template is force-preserved,
so the pack can fix what it ships but cannot reach a copy already
installed. See the Evidence section.

## Evidence

Measured 2026-08-10 across all 8 registered consumers: **12 hits in 6
files** for the five that have not edited their PR template, **11 in 5**
for `mezmo_benchmark`, `sd-github-review`, and `anomaly-metric-creator`,
which have — there the template is consumer-owned and its stale command
is a `blocker` in that consumer's own cleanup, not a pack defect.
Reproduce with the scanner committed under the sibling task:

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
| `.github/copilot-instructions.md` | 5 hits, consumer-dependent lines | `docs/SD_AI_COMMAND_PACK.md`, `scripts/sd-ai-command-pack-install-audit.py` |
| `.github/PULL_REQUEST_TEMPLATE.md` | 14 (template) | `scripts/sd-ai-command-pack-full-check.sh` |

The four prompts are whole-file pack targets, so their line numbers are
stable fleet-wide. The Copilot hits are not: the block sits below whatever
preamble the consumer wrote, so the same five citations land at 27/51/54/
106/108 in `rwbp-coordinator` and 47/71/74/126/128 in `mezmo_benchmark`.
The resweep reports the lines; this table does not fix them.

`.github/prompts/sd-help.prompt.md` is deliberately **not** listed, and an
earlier revision of this PRD listed it in error. It tells the agent to
resolve a skill and then read that skill's `references/*.md` — a path
relative to a resolved skill, not to a location in the repository. Nothing
static can tie it to a removed path without guessing, and the guess that
put it here also produced a false blocker in `se-ai-command-pack`.

Every listed file is a `repo-native` partition row (`platform: github`)
that the conversion **keeps** — verified against
`docs/fleet/surface-partition.json`, not assumed. `repo-native` is exactly
why they survive and therefore exactly why their stale citations matter.

Three different ownership proofs are involved, which is why this set was
undercounted twice:

- The four prompts are byte-for-byte the pack's own copy in every
  consumer, and provenance vouches them by digest.
- `.github/copilot-instructions.md` is a **managed-block** target, so
  provenance never records a whole-file digest for it and only the content
  between the pack's `SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START`/`:END`
  markers is ours. All five of its hits are inside that block. The repoint
  must stay inside the markers; editing outside them would rewrite
  consumer content.
- `.github/PULL_REQUEST_TEMPLATE.md` is **force-preserved**
  (`installer/registry.py:2265`), so provenance never vouches it either
  and an install never overwrites it. Ownership is decided by comparing
  the consumer's bytes against the pack's shipped template.

That last one bounds this task's reach much harder than it first appears,
and an earlier revision of this PRD got it wrong. Fixing the shipped
template does **not** fix the five consumers carrying it verbatim.
`install_file()` returns `PRESERVED` for a force-preserved target whenever
the existing bytes differ from the newly shipped ones, and it does so even
under `force=True` (`installer/fileops.py:366`). The moment the pack
template changes, all five existing copies differ from it and are
preserved — forever, by design. A force-preserved file is only ever
written on a *fresh* install.

So the pack edit fixes future installs and nothing else, and the fix for
the eight repositories that exist today is necessarily consumer-side. The
classification follows the same logic rather than fighting it: once the
new template ships, no consumer's copy matches the pack's shipped bytes,
so every copy is judged consumer-authored and its stale command is a
`blocker` in that consumer's own conversion PR. That is the correct owner.
It is also the reason this task cannot claim "packDefects: 0 everywhere"
for the template — the pack genuinely does not control it after install.

The alternative — teaching the installer to overwrite a force-preserved
target whose bytes match a *known previous* shipped template — is a
change to install semantics for a file class explicitly designed to be
user-tunable. It is not in this task's scope and would need its own
task and its own review.

`templates/.github/prompts/**`,
`templates/.github/copilot-instructions.sd-ai-command-pack.md`, and
`templates/.github/PULL_REQUEST_TEMPLATE.md` are the canonical sources;
`scripts/`, `plugins/sd/bin/`, and `plugins/sd/machine-payload/scripts/`
are byte-verified mirrors, so the edit goes to the template and then
through `make sync` and `make generate`.

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
2c. The `PULL_REQUEST_TEMPLATE.md` edit is made to the shipped template,
   for fresh installs only. It must not attempt to reach existing
   consumers, and this task must not claim it does. The task instead
   records, in the conversion PR checklist for children 3–5, that **all
   eight** consumers repoint their own template as part of converting.
3. The resweep reports zero `packDefects` for every registered consumer
   after the change ships and consumers refresh. That is the acceptance
   signal, not a reading of the diff. The PR template reaches zero by a
   different route than the other five surfaces: those are rewritten by
   the refresh, while the template is force-preserved and instead becomes
   consumer-owned once the shipped bytes change, moving to `blockers`.
   Both routes must be verified against a measurement, not asserted.
4. The change carries a `manifest.json` version bump and a CHANGELOG
   entry — it is a shipped-payload change, and the release gate fails
   otherwise.

## Non-goals

- Repointing any **consumer-authored** execution surface, including a
  consumer-owned PR template. That is the per-consumer work in children
  3–5 and needs per-cohort authorization.
- Changing what the thin conversion deletes. The delete set is contract
  C-B and is not up for renegotiation here.
- Changing `sd-help.prompt.md`. It cites skill-relative references, not
  repository paths, and is not a defect.

## Acceptance criteria

- [ ] All six surfaces resolve their cited paths in a thin checkout,
      proven against the converted fixture from
      `08-10-thin-conversion-tooling`, not by inspection.
- [ ] All six still resolve in a fat checkout — the fat path is the one
      every consumer is on today, and breaking it to fix thin trades one
      outage for another.
- [ ] `fleet-blocker-scan.py` (or the shipped resweep, once it exists)
      reports `packDefects: 0` for a consumer refreshed to the new pack
      version — the five refreshed surfaces are rewritten, and the PR
      template leaves the bucket by becoming consumer-owned.
- [ ] A **fresh** install into an empty target writes the corrected PR
      template. This is the only path on which the template fix reaches a
      repository, so it is the only path that proves the fix shipped.
- [ ] A refresh of an existing consumer reports the PR template as
      `PRESERVED` and its stale line as a `blocker`, for all eight — the
      task must not claim to have fixed a file the installer refuses to
      write.
- [ ] Template edited first, then `make sync` and `make generate`; the
      mirror gate passes with no manual mirror edits.
- [ ] `manifest.json` bumped, CHANGELOG entry added, `make check` green.

## Blocking relationship

This blocks children 3–5 of `08-09-thin-migration`. A `packDefects`
entry blocks `--thin` by design, so no consumer conversion can proceed
until this lands. It does not block
`08-10-thin-conversion-tooling` itself: that task builds the resweep
that detects this condition, and detecting it correctly is the point.
