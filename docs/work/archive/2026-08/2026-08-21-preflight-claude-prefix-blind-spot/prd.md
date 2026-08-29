---
title: Stop ignoring .claude/ path citations in the review preflight
status: done
created: 2026-08-21
branch: fix/preflight-claude-prefix-blind-spot
---
# Stop ignoring `.claude/` path citations in the review preflight

## Goal

`scripts/sd-ai-command-pack-review-preflight.mjs` never checks whether a
`.claude/...` path citation resolves. Make it check, without turning
machine-local Claude state into false failures.

## Context

The checker holds two lists that disagree about this prefix:

- `referencePrefixes` (line 375) lists `.claude/` among the trees whose
  citations are checked, alongside `.agents/`, `.codex/`, `.cursor/`,
  `.gemini/` and the rest.
- `ignoredReferencePrefixes` (line 434) lists it too, alongside
  `.build/`, `.local/`, and `node_modules/`.

`shouldCheckDocumentationPathReference` consults both, and the ignore wins. So
the prefix that one list declares checkable is unconditionally skipped.

The entry arrived in `34ea5d87` (2026-07-05, "feat: expand sd command pack
workflows"), a broad commit. It carries no comment and no test, so there is no
recorded rationale — unlike its three neighbours, which are all generated or
machine-local trees. `.claude/` is neither: it is an authored adapter tree the
pack installs into and which other rules treat as first-class.

### How it surfaced

Copilot found a dangling `.claude/skills/sd-work-backlog/SKILL.md` citation in
se-ai-command-pack that the gate had passed. Enumerating the four path shapes
that file's header names turned up four such `.claude/skills/sd-*` citations,
none of which the checker can see by construction. The gate cannot find this
class, so it can only ever be found by hand.

### Measured blast radius

The ignore was removed on a scratch copy and both checkers were run over every
cloned consumer:

| repository | before | after | new |
| --- | --- | --- | --- |
| sd-ai-command-pack | 0 | 5 | +5 |
| se-ai-command-pack | 0 | 1 | +1 |
| sd-github-review | 0 | 0 | 0 |
| people-profiles | 0 | 0 | 0 |
| hoa-manager | 0 | 0 | 0 |
| anomaly-metric-creator | 0 | 0 | 0 |
| loadsmith | 24 | 24 | 0 |

Six findings fleet-wide. `rwbp-coordinator` and `rwbp-website` are not cloned
here and are unmeasured.

Classified, they are not one defect but four:

1. **A tokenizer false positive.** `.trellis/tasks/07-25-agent-artifacts/research/cross-platform-agent-support.md:48`
   wrote a slash-joined shorthand for five platform directories — Claude,
   Codex, Gemini, OpenCode, GitHub — which tokenizes as one path. It is not a
   path, and no rule change makes it one.
2. **Two forward-looking citations** in `.trellis/tasks/08-07-plugin-review-provider-lanes/prd.md`
   naming a provider lane that was never built.
3. **One upstream path**, `.claude/hooks/statusline.py` [absent: upstream Claude Code path, not a file in this repository],
   in a research note about a fix to Claude Code itself rather than to this
   repository.
4. **One genuinely machine-local file.** `.claude/settings.local.json` is
   gitignored at `.gitignore:66`. This one is the same family as `.local/`,
   and it is why the blanket ignore was not simply wrong — it was over-broad.

## Requirements

- **Check `.claude/` citations.** Remove the prefix from
  `ignoredReferencePrefixes` so the two lists stop contradicting each other.
- **Keep machine-local Claude state out of the failure set**, by the narrowest
  mechanism that works, and state why each exemption is there. The checker
  already has `optionalReferencePaths` for exactly this shape.
- **Do not fix a citation by deleting the claim it supports.** Forward-looking
  and upstream citations are marked `[absent: <reason>]`; the false positive is
  reworded so it stops reading as a path.
- **Cover the change with a test.** The entry survived because nothing asserted
  it either way. Whatever the new behaviour is, a test must pin it.
- **Ship it**, so the gate reaches consumers on their next refresh.

## Acceptance Criteria

- [ ] `.claude/` is absent from `ignoredReferencePrefixes`.
- [ ] A dangling `.claude/skills/sd-*/SKILL.md` citation is reported as a
      failure; this is asserted by a test, not only observed.
- [ ] `.claude/settings.local.json` does not fail, and the reason is stated in
      the source next to the exemption.
- [ ] The pack repository's whole-tree preflight reports 0 failures under the
      new rule.
- [ ] `make check` passes and the version ships with a `CHANGELOG.md` entry.
- [ ] se-ai-command-pack's single newly-visible citation is corrected in that
      repository, so its next refresh does not red on this change.

## Out Of Scope

- **loadsmith's 24 pre-existing failures.** Unrelated to this rule — the delta
  there is 0 — and separately tracked.
- `rwbp-coordinator` and `rwbp-website`, not cloned here. Their delta is
  unmeasured; if either reds on refresh it is the same six-shape classification
  applied again.
- Refreshing consumers onto the shipped version.
