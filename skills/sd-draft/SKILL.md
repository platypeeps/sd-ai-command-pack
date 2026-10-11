---
name: sd-draft
description: Use when the user wants to write, continue, or revise the draft of a registered piece in a writing content repository, and move it through the drafting, review, and ready stages.
---

# sd-draft

Write or revise the `## Draft` of one registered piece, scrub it, run its gates, and move its stage forward.
Run from the root of a content repository (it holds `content/`, `profile/` and `templates/`).
If the current directory has no `content/`, stop and say so.
`pack` below means `python3 scripts/pack.py`, which only sd-writing has: in another content repository, skip a `pack` step and say so.
`.claude/reference/pipeline.md` and `.claude/reference/database-workflow.md` in that repository hold the reasons and the record format; this file holds the steps.

## Workflow

1. Resolve the piece with `sd writing get --piece <year>/<slug> --json` and use its registered `item.path`. A revived piece may stay under `content-parked/`. If no piece is registered, stop and suggest `sd-research piece=<year>/<slug>`.
2. Read `research.md` beside it, and the `Outline` section of `index.md`.
3. Read `profile/brand-voice/VOICE.md` (how it sounds) and `profile/personality-profile/PROFILE.md` (what position it takes, and its boundaries). If either is missing, say so and continue.
   Entity profiles that the repository's `CLAUDE.md` names are background only: a claim from one needs a re-verified public source in `research.md` first.
4. Before the first edit to `index.md`, run `sd-rules --for <item.path>/index.md` from the repository root and follow the printed rule IDs. Then write or revise prose under `## Draft` in `index.md`. Match `VOICE.md`, stay inside `PROFILE.md`, and keep every claim traceable to `research.md`.
   - **Keep each claim at the strength `research.md` gives it.** A note that says *appears to*, *vendor-reported* or *search summary only* keeps that hedge in the prose. To make the sentence firmer, verify the claim at its primary source and upgrade the note first. An unmarked claim is the weaker reading, not a confirmed one.
   - **Source the prescription.** Find the sentence that tells the reader what to do, and find evidence in `research.md` for that remedy: someone ran it, what it cost, what it beat, how it fails. Evidence for the problem does not carry the fix. Without remedy evidence, change the register: write it as what the author does and why, or as a proposal with its untested parts named. Or go back with `sd-research` for the evidence.
5. After every full write or large revision, run both scrubbers on the `## Draft` prose: `sd-humanizer` in file mode, then `no-ai-slop` in Edit mode. Calibrate both against `VOICE.md` (`Core identity`, `Always`, `Never`, `Signature sentence patterns`). `VOICE.md` wins a conflict.
6. A voice or position question the profiles do not answer goes into that profile's `## Gaps / open questions`, and into the report. `sd-profile` resolves it later. Do not guess.
7. Read the stage with `sd writing get --piece <year>/<slug> --json` (`writing.stage`). Move it with `sd writing stage --piece <year>/<slug> --stage <new>`; it moves forward only.
   - First full draft: `drafting`.
   - Ready for feedback: `review`. Run the step 4 prescription check before this move. If a person should comment, mention `sd-draft-review push`; do not run it unasked, because it writes outside the repository.
   - Feedback addressed: `ready`. Run these first, in order:
     1. **Fact-check gate.** Run it as an `Agent` sub-agent with `model: opus`, pointed at the installed `sd-fact-check` skill and its `references/source-standards.md` and `references/verification-protocol.md`. Pass `input=` the `## Draft` prose plus `research.md`, `scope=material`, `as_of=` today, `format=ledger`. Effort is inherited, so say in the report which effort it ran at. Resolve every unverified or contradicted claim, or flag it. The gate never counts as passed without a claim ledger.
     2. **Adversarial gate.** `sd writing adversarial --piece <year>/<slug>` runs a model from another vendor against the draft in a read-only sandbox and writes `adversarial.md`. Its remit is argument and citations; discard any style finding. Treat each finding as a hypothesis: verify its "what would have to be true" line at the primary source before you change a word. A rebutted finding is a good result. A new fact needs its source in `research.md` first. It also reads `profile/guardrails.md` when the repository has one. If the CLI that `sd writing adversarial` calls or the shared adversarial gate is missing, report the gate as skipped, never as passed.
     3. Save the ledger as `fact-check.md`. Record both verdicts and every finding disposition with `sd writing gate --piece <year>/<slug> --artifact fact-check|adversarial`. sd-writing's `.claude/reference/database-workflow.md` gives the record format.
     4. **Drift check.** `sd writing readiness --piece <year>/<slug> --json` reports `current`, `stale`, `unstamped` or `missing` for `adversarial.md` and `research.md` under `companions`. Run it after every revision pass. `sd writing stage` refuses `ready` and `published` while either is stale. Clear it by re-running the gate, or with `sd writing reconcile --piece <year>/<slug> --artifact adversarial|research --note-file <path>`. The note says what became of each finding (confirmed, conceded, rebutted, with its source), or which claims the revision added and where each is sourced. An unstamped `adversarial.md` needs a re-run. Use `--note-file`: a backtick in a shell argument is a command substitution.
   - In sd-writing, `pack review status` also reports `publish=`, a re-render of the optional export. It blocks nothing. A piece that is not being published has no `publish/` folder.
8. In sd-writing, `pack review tics [--show]` counts the assert-then-narrow move across every draft. Warn when more than three pieces carry it, and name them; which pieces keep it is the author's call.
9. Bump frontmatter `updated` when prose changes. Never hand-edit publication state.

## Final report

Current stage, word count, the piece's prescription and what in `research.md` sources it, new profile gaps, fact-check findings, adversarial findings with which you verified and which you rebutted, the companion states from `readiness`, the `review tics` warning if any, and what is still missing.
