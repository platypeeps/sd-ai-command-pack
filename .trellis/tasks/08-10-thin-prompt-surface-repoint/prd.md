# Repoint surviving pack surfaces off removed paths

## Goal

Seven pack-shipped surfaces survive a thin conversion and still cite
paths the conversion removes — four prompts that instruct an agent to run
removed scripts, the managed block inside
`.github/copilot-instructions.md`, the force-preserved
`.github/PULL_REQUEST_TEMPLATE.md`, and the `obsidian-kb` block in
`.gitignore`, which survives while the `trellis-gitignore` block beside it
is stripped. Until they are
repointed, every consumer's resweep returns `packDefects` and no
conversion can proceed. This task fixes the pack side so children 3–5 of
the thin migration can run at all — with one exception it states
explicitly rather than papering over: the PR template is force-preserved,
so the pack can fix what it ships but cannot reach a copy already
installed. See the Evidence section.

## Evidence

Measured 2026-08-10 across all 8 registered consumers: **16 hits in 7
files** for the five that have not edited their PR template, **14 in 6**
for `mezmo_benchmark`, `sd-github-review`, and `anomaly-metric-creator`,
which have — there the template is consumer-owned and its two stale
citations are `blockers` in that consumer's own cleanup, not pack
defects.
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
| `.github/copilot-instructions.md` | 7 hits, consumer-dependent lines | `docs/SD_AI_COMMAND_PACK.md`, `scripts/sd-ai-command-pack-install-audit.py`, and the globs `.agents/skills/sd-*/SKILL.md` and `**/skills/sd-*/**` |
| `.github/PULL_REQUEST_TEMPLATE.md` | 7, 14 (template) | `docs/SD_AI_COMMAND_PACK.md`, `scripts/sd-ai-command-pack-full-check.sh` |
| `.gitignore`, `obsidian-kb` block | 1 hit, consumer-dependent line | `scripts/sd-ai-command-pack-update-spec-kb.py` |

The four prompts are whole-file pack targets, so their line numbers are
stable fleet-wide. The Copilot hits are not: the block sits below whatever
preamble the consumer wrote, so the same seven citations land at
26/27/36/51/54/106/108 in `rwbp-coordinator` and 46/47/56/71/74/126/128 in
`mezmo_benchmark`. The resweep reports the lines; this table does not fix
them.

Two of those seven are **globs**, not paths, and were found only in round
nine: the block's own text names `.agents/skills/sd-*/SKILL.md` as an
entry point and `**/skills/sd-*/**` as a pack-owned tree. A thin
conversion removes that whole population, so both citations name nothing
afterwards. They matter for the repoint because a glob cannot be fixed by
pointing it at a different directory that also does not exist: the block
has to say where skills live in a thin checkout, or detect the mode.

`.github/prompts/sd-help.prompt.md` is deliberately **not** listed, and an
earlier revision of this PRD listed it in error. It tells the agent to
resolve a skill and then read that skill's `references/*.md` — a path
relative to a resolved skill, not to a location in the repository. Nothing
static can tie it to a removed path without guessing, and the guess that
put it here also produced a false blocker in `se-ai-command-pack`.

The first six are `repo-native` partition rows (`platform: github`) that
the conversion **keeps** — verified against
`docs/fleet/surface-partition.json`, not assumed. `repo-native` is exactly
why they survive and therefore exactly why their stale citations matter.

`.gitignore` is the exception and has **no partition row at all**; it
survives because it is a `block_strip` target, not because a partition
slice keeps it. An earlier revision of this PRD said all seven were
partition rows, which is false and mattered: the two survive by different
mechanisms, and only one of them is refreshed by an install.

That is also why the `.gitignore` entry is the subtlest of the seven and
was missed for three rounds. Conversion removes the `trellis-gitignore`
marker pair and leaves the rest of the file. But a consumer's `.gitignore`
also carries an `obsidian-kb` block, written by the KB refresh, whose
header comment names the very script conversion deletes. A rule keyed on
"is this file block-stripped?" calls that hit `scheduled` and loses it;
the span the conversion actually removes is what decides, not the file.

**The `obsidian-kb` block does not reach zero by shipping and refreshing.**
Its text is emitted when
`scripts/sd-ai-command-pack-update-spec-kb.py` *executes*; a pack refresh
installs the corrected script but never rewrites a block the script wrote
on some earlier run. So the seven surfaces clear by three different
routes, not two:

- four prompts and the Copilot managed block — rewritten by a refresh;
- `.gitignore`'s `obsidian-kb` block — cleared only when the consumer runs
  the KB refresh after taking the new pack version. That run is an
  explicit step in each conversion PR for children 3–5, not a consequence
  of refreshing;
- `.github/PULL_REQUEST_TEMPLATE.md` — never rewritten at all, for the
  force-preserved reason below.

Without the explicit KB-refresh step, the block stays a `packDefect` and
`--thin` keeps refusing, with the pack side of the fix already shipped and
apparently complete. That is precisely the failure mode this task exists
to prevent.

Three different ownership proofs are involved, which is why this set was
undercounted twice:

- The four prompts are byte-for-byte the pack's own copy in every
  consumer, and provenance vouches them by digest.
- `.github/copilot-instructions.md` is a **managed-block** target, so
  provenance never records a whole-file digest for it and only the content
  between the pack's `SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START`/`:END`
  markers is ours. All seven of its hits are inside that block. The repoint
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
`templates/.github/copilot-instructions.sd-ai-command-pack.md`,
`templates/.github/PULL_REQUEST_TEMPLATE.md`, and the `obsidian-kb` block
text emitted by `templates/scripts/sd-ai-command-pack-update-spec-kb.py`
are the canonical sources;
`scripts/`, `plugins/sd/bin/`, and `plugins/sd/machine-payload/scripts/`
are byte-verified mirrors, so the edit goes to the template and then
through `make sync` and `make generate`.

## Requirements

1. Each of the seven surfaces resolves its cited path through a location that
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
   after the change ships, consumers refresh, **and** each consumer runs
   the KB refresh. That is the acceptance signal, not a reading of the
   diff. The seven surfaces reach zero by three routes: five are rewritten
   by the refresh; the `obsidian-kb` block is rewritten only when
   `sd-ai-command-pack-update-spec-kb.py` runs; and the force-preserved PR
   template is never rewritten and instead becomes consumer-owned once the
   shipped bytes change, moving to `blockers`. All three must be verified
   against a measurement, not asserted.
3b. The conversion PR checklist for children 3–5 carries the KB-refresh
   step explicitly, next to the template-repoint step. Both are consumer
   actions the pack cannot perform, and both are invisible in a pack diff
   that otherwise looks complete.
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

- [ ] All seven surfaces resolve their cited paths in a thin checkout,
      proven against the converted fixture from
      `08-10-thin-conversion-tooling`, not by inspection.
- [ ] All seven still resolve in a fat checkout — the fat path is the one
      every consumer is on today, and breaking it to fix thin trades one
      outage for another.
- [ ] `fleet-blocker-scan.py` (or the resweep, once it exists — released
      with the pack, source-only, never installed into a consumer)
      reports `packDefects: 0` for a consumer refreshed to the new pack
      version **and** re-run through the KB refresh — five surfaces
      rewritten by the refresh, the `obsidian-kb` block rewritten by the
      KB script, and the PR template leaving the bucket by becoming
      consumer-owned.
- [ ] A consumer refreshed but **not** KB-refreshed still reports the
      `obsidian-kb` hit as a `packDefect`. This is the negative case that
      proves the extra step is load-bearing rather than ceremonial.
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
