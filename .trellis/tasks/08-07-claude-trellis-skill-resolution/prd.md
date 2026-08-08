# Claude skill copies drop the Claude-specific resolution guidance their command adapters carry

## Goal

Make the Claude **skill** copies of `sd-finish-work`, `sd-continue`, and
`sd-start` carry the same Claude-specific resolution guidance their **command**
adapters already carry. Today the guidance exists, is correct, and is
documented — but it reaches only one of the two Claude surfaces, and the surface
it misses is the one an agent loads when it invokes the skill.

## Problem

The pack already solves Claude's missing `trellis-*` skills deliberately. The
generator carries bounded Claude-only rewrites:

- `CLAUDE_COMMAND_ALIAS_REWRITES`
  (`.github/scripts/generate-command-surfaces.py:101`) appends, for `continue`
  and `finish-work`: "On Claude Code this workflow is installed as the
  `trellis:finish-work` command; resolving `trellis:finish-work` counts as
  resolving this skill."
- `OVERRIDE_BODIES[("claude", "start")]` (`:158`) records that "Claude Code
  receives Trellis start context from the SessionStart hook and intentionally
  has no trellis-start skill."
- `templates/docs/SD_AI_COMMAND_PACK.md:194-198` documents both.

None of that is broken. The defect is where it lands.

### The rewrite reaches commands and not skills

`claude_adapter()` (`:593`) applies the rewrites, and it serves only the command
path — `templates/.claude/commands/sd/<short>.md`. Skill emission is a separate,
transform-free copy: `_platform_skill_entry()` (`:744`) maps
`templates/.agents/skills/<name>/SKILL.md` straight to
`<platform>/skills/<name>/SKILL.md` with no rewrite hook.

The result, checked cell by cell in this repository:

| wrapper | Claude **command** adapter | Claude **skill** copy |
|---|---|---|
| `sd-finish-work` | alias sentence, `.claude/commands/sd/finish-work.md:37` | **absent** |
| `sd-continue` | alias sentence, `.claude/commands/sd/continue.md:29` | **absent** |
| `sd-start` | SessionStart guidance, `.claude/commands/sd/start.md:7` | **absent** |

All three Claude skill copies are byte-identical to their neutral sources —
`cmp` reports no difference against `templates/.agents/skills/<name>/SKILL.md` —
and the neutral sources contain neither the alias sentence nor the SessionStart
note, by design, because that text is Claude-specific.

So an agent that loads `.claude/skills/sd-finish-work/SKILL.md` reads:

> 1. Resolve the `trellis-finish-work` skill by name using the agent's trusted
>    skill discovery mechanism for installed skills.
> 2. If that skill is missing … stop and report the exact blocker.

with no mention that `trellis:finish-work` is the installed Claude form. And
`trellis-finish-work` is genuinely not on Claude's skill surface, so step 2
fires on a dependency the pack deliberately satisfies a different way.

### Observed, not hypothetical

Hit on 2026-08-07 in `platypeeps/loadsmith` during a real `sd-finish-work` run
ahead of merging PR #209. The agent loaded the skill, searched `.claude/skills/`,
`.trellis/`, and the plugin caches, concluded the dependency did not exist
anywhere, and improvised a substitute reading of the Trellis workflow — then
reported that substitution to the operator as a deviation.

Both halves were wrong. `.claude/commands/trellis/finish-work.md` held the
workflow, and the command adapter would have said so. The merge was sound (the
deterministic gates ran and passed, and reading the skill afterwards confirmed
every step matched what was done), but the operator was told a blocker that did
not exist.

That is the failure mode to expect, and it is worse than a hard stop: a
confident improvisation around content that was present the whole time. The
alias sentence exists precisely to prevent it, and the skill surface never
receives it.

## Requirements

- The three Claude skill copies convey the same Claude-specific resolution
  guidance as their command adapters. Whether that is achieved by transforming
  skill output or by relocating the guidance is the design question below, not
  a settled decision.
- `trellis_local_only` stays intact — `.claude/skills/trellis-*/`
  (`installer/registry.py:91`) and `.agents/skills/trellis-*/` (`:405`). The
  pack must not begin installing or vendoring Trellis-owned skills.
- The fix does not point wrappers at `.agents/skills/trellis-*/`. Those copies
  are bootstrap artifacts owned by neither installer, so resolving against them
  would canonize an unowned path — and unlike `.agents/skills/sd-ship/SKILL.md`,
  which is a pack-owned manifest target, they are not guaranteed present in a
  consumer. `tests/test_sdlc_commands.py:453` already forbids that exact path in
  `sd-review-pr` step 8.
- The wrappers keep failing closed. This removes a false blocker; a genuinely
  absent dependency must still stop the run.
- Claude-only text stays single-sourced in the generator's bounded transform
  dicts. Hand-editing a generated adapter, or duplicating the sentence into the
  neutral body without deciding the cross-platform question, reintroduces the
  drift these dicts exist to prevent.

### The design question implementation must answer first

Skill entries fan out to eleven platforms from one neutral source
(`installer/registry.py:475-487`). Three options, with different blast radii:

1. Give skill emission a Claude transform mirroring `claude_adapter()` — keeps
   the text Claude-only, adds a second transform path to keep in sync.
2. Move the guidance into the neutral body — simplest, but ships Claude-specific
   prose to ten other platforms.
3. Stop emitting the redundant Claude skill copies and let the command adapters
   be the Claude surface — smallest surface, but changes what `/sd-finish-work`
   resolves to and needs the skill-discovery implications worked out.

This is a real fork, not an implementation detail, which is why this task is
not PRD-only-and-go.

## Acceptance criteria

- [ ] The full affected set is enumerated from the generator rather than from
      this PRD's table: every entry in `CLAUDE_COMMAND_ALIAS_REWRITES`,
      `CLAUDE_COMMAND_BODY_INSERTIONS`, and `OVERRIDE_BODIES` keyed to `claude`
      is listed, and each is checked against both the command adapter and the
      skill copy. The table lists three; the enumeration is what proves there is
      no fourth.
- [ ] The chosen option from the fork above is recorded with its rejected
      alternatives and the reason, before implementation starts.
- [ ] On a Claude Code consumer checkout, loading each affected
      `.claude/skills/sd-*/SKILL.md` yields guidance sufficient to resolve its
      dependency without searching, demonstrated by quoting the located text.
- [ ] A parity test asserts the Claude skill copy and the Claude command adapter
      agree on resolution guidance for every affected wrapper, and it fails
      against the current tree. A test that passes today has not captured this
      defect.
- [ ] `sd-review-pr` is verified as transitive-only, not a fourth resolver: it
      resolves `sd-finish-work` (`.claude/skills/sd-review-pr/SKILL.md:738`),
      and `tests/test_sdlc_commands.py:452-453` still forbids direct
      `trellis-finish-work` resolution in step 8 after the change.
- [ ] The `trellis_local_only` exclusions at `installer/registry.py:91` and
      `:405` are unchanged, confirmed by diff.
- [ ] A genuinely missing dependency still stops the wrapper, with the blocker
      naming every location searched, and that output is quoted.
- [ ] The generator's own parity tests and the repo readiness gate pass, and
      regenerated surfaces are byte-stable for unaffected commands.

## Notes

Found while surveying `platypeeps/loadsmith` after merging PR #209, from a real
`sd-finish-work` failure rather than from reading the generator.

The first draft of this PRD misdiagnosed it as "three Trellis skills are missing
and nobody owns them," and proposed resolving against
`.agents/skills/trellis-*/`. Adversarial review refuted that: the pack's Claude
bridge is deliberate and documented, and the proposed fallback path is both
unowned and already forbidden by test. The surviving defect is narrower — a
transform that reaches one surface and not the other — and the recorded
misdiagnosis is kept here because the wrong version was plausible enough to
reach a PRD.

Scope boundary: this fixes where existing guidance lands. It does not change
what any `trellis-*` skill does and does not touch Trellis's packaging policy.

Two consumers were inspected, this repository and `platypeeps/loadsmith`, and
both show the identical split, so it is a shipped property rather than one
broken install.
