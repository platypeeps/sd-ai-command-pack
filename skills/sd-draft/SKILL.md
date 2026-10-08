---
name: sd-draft
description: Use when the user wants to write, continue, or revise the draft of a registered piece in a writing content repository, and move it through the drafting, review, and ready stages.
---

# sd-draft

Write or revise the `## Draft` of one registered piece, scrub it, run its gates, and move its stage forward.
Run from the root of the writing content repository: the checkout that holds `scripts/pack.py`, `content/` and `profile/`.
If the current directory has no `scripts/pack.py`, stop and say so.
`pack` below means `python3 scripts/pack.py`.
`.claude/reference/pipeline.md` and `.claude/reference/database-workflow.md` in that repository hold the reasons and the record format; this file holds the steps.

## Workflow

1. Resolve the piece with `pack pieces get --piece <year>/<slug> --json` and use its registered `item.path`. A revived piece may stay under `content-parked/`. If no piece is registered, stop and suggest `sd-research piece=<year>/<slug>`.
2. Read `research.md` beside it, and the `Outline` section of `index.md`.
3. Read `profile/brand-voice/VOICE.md` (how it sounds) and `profile/personality-profile/PROFILE.md` (what position it takes, and its boundaries). If either is missing, say so and continue.
   Entity profiles that the repository's `CLAUDE.md` names are background only: a claim from one needs a re-verified public source in `research.md` first.
4. Write or revise prose under `## Draft` in `index.md`. Match `VOICE.md`, stay inside `PROFILE.md`, and keep every claim traceable to `research.md`.
   - **Keep each claim at the strength `research.md` gives it.** A note that says *appears to*, *vendor-reported* or *search summary only* keeps that hedge in the prose. To make the sentence firmer, verify the claim at its primary source and upgrade the note first. An unmarked claim is the weaker reading, not a confirmed one.
   - **Source the prescription.** Find the sentence that tells the reader what to do, and find evidence in `research.md` for that remedy: someone ran it, what it cost, what it beat, how it fails. Evidence for the problem does not carry the fix. Without remedy evidence, change the register: write it as what the author does and why, or as a proposal with its untested parts named. Or go back with `sd-research` for the evidence.
5. After every full write or large revision, run both scrubbers on the `## Draft` prose: `sd-humanizer` in file mode, then `no-ai-slop` in Edit mode. Calibrate both against `VOICE.md` (`Core identity`, `Always`, `Never`, `Signature sentence patterns`). `VOICE.md` wins a conflict.
6. A voice or position question the profiles do not answer goes into that profile's `## Gaps / open questions`, and into the report. `sd-profile` resolves it later. Do not guess.
7. Read the stage with `pack pieces get --piece <year>/<slug> --json` (`writing.stage`). Move it with `pack pieces set-status --piece <year>/<slug> --status <new>`; it moves forward only.
   - First full draft: `drafting`.
   - Ready for feedback: `review`. Run the step 4 prescription check before this move. If a person should comment, mention `sd-draft-review push`; do not run it unasked, because it writes outside the repository.
   - Feedback addressed: `ready`. Run these first, in order:
     1. **Fact-check gate.** Run it as an `Agent` sub-agent with `model: opus`, pointed at the installed `sd-fact-check` skill and its `references/source-standards.md` and `references/verification-protocol.md`. Pass `input=` the `## Draft` prose plus `research.md`, `scope=material`, `as_of=` today, `format=ledger`. Effort is inherited, so say in the report which effort it ran at. Resolve every unverified or contradicted claim, or flag it. The gate never counts as passed without a claim ledger.
     2. **Adversarial gate.** `pack review adversarial --piece <year>/<slug>` runs a non-Anthropic model against the draft in a read-only sandbox and writes `adversarial.md`. Its remit is argument and citations; discard any style finding. Treat each finding as a hypothesis: verify its "what would have to be true" line at the primary source before you change a word. A rebutted finding is a good result. A new fact needs its source in `research.md` first. If the `codex` CLI is missing, report the gate as skipped, never as passed.
     3. Save the ledger as `fact-check.md`. Record both verdicts and every finding disposition with `pack review record-gate`, per `database-workflow.md`.
     4. **Drift check.** `pack review status [--piece <year>/<slug>]` reports `current`, `stale`, `unstamped` or `missing` for `adversarial.md` and `research.md`. Run it after every revision pass. `set-status` refuses `ready` and `published` while either is stale. Clear it by re-running the gate, or with `pack review reconcile --piece <year>/<slug> --artifact adversarial|research --note-file <path>`. The note says what became of each finding (confirmed, conceded, rebutted, with its source), or which claims the revision added and where each is sourced. An unstamped `adversarial.md` needs a re-run. Use `--note-file`: a backtick in a shell argument is a command substitution.
   - `review status` also reports `publish=`, a re-render of the optional export. It blocks nothing. A piece that is not being published has no `publish/` folder.
8. `pack review tics [--show]` counts the assert-then-narrow move across every draft. Warn when more than three pieces carry it, and name them; which pieces keep it is the author's call.
9. Bump frontmatter `updated` when prose changes. Never hand-edit publication state.

## Final report

Current stage, word count, the piece's prescription and what in `research.md` sources it, new profile gaps, fact-check findings, adversarial findings with which you verified and which you rebutted, the `review status` result, the `review tics` warning if any, and what is still missing.
