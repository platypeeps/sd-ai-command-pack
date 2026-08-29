---
title: Close the two latent gaps left by the .claude/ and charter-root work
status: done
created: 2026-08-21
branch: fix/close-latent-preflight-conversion-gaps
---
# Close the two latent gaps left by the `.claude/` and charter-root work

## Goal

Two gaps were named and deliberately deferred while shipping 0.71.43 and
0.71.44. Close them, and correct the framing of the second — measurement says
it is not what the earlier note claimed.

## Gap 1: `.gemini/settings.local.json` has no exemption

0.71.43 exempted `.claude/settings.local.json` in `optionalReferencePaths`
because it is per-checkout machine state, gitignored at `.gitignore:66`. The
`.gemini/` twin at `.gitignore:104` got nothing, and `.gemini/` is checked.

The asymmetry is complete and small — exactly two platforms have a gitignored
`settings.local.json`:

| prefix | checked | `settings.local.json` gitignored | exempt |
| --- | --- | --- | --- |
| `.claude/` | yes | yes (`:66`) | yes |
| `.gemini/` | yes | yes (`:104`) | **no** |
| `.codex/`, `.opencode/`, `.cursor/`, `.agents/` | yes | no such file | n/a |

Nothing cites the Gemini file today, so it cannot fail yet. One line closes it.

## Gap 2: the thin conversion's rewrite scope — the earlier claim was wrong

The 0.71.44 note said "directory-shaped `.agents/` tokens are not in the
rewrite map", implying a file/directory distinction. Measured with
`rewrite_text` across three keys and five probe shapes, the real rule is
simpler and broader:

| written as | thin conversion |
| --- | --- |
| `scripts/<pack-script>` | rewritten to `~/.agents/bin/<pack-script>` |
| anything under `.agents/bin/`, `.agents/skills/`, or `.agents/docs/` | **left alone**, file or directory alike |

So the conversion repoints one spelling, and anything already written under
`.agents/` passes through untouched. That is a coherent rule, not an
oversight — but nothing states or tests it, which is exactly how the `.claude/`
contradiction survived a year.

**This is not a live defect.** Measured in a thin consumer (hoa-manager):

- repo-root `.agents/skills/` does exist there (15 repo-owned and Trellis
  skills), so a generic `.agents/skills/` mention is true;
- the only pack-owned file citations under `.agents/` are in
  `.trellis/tasks/archive/**`, which the checker skips by design;
- the one directory citation that made a false root claim,
  `.agents/skills/sd-audit-repo/charters/`, was fixed in 0.71.44.

And the failure mode is already covered: `.agents/` is in `referencePrefixes`,
so a new file-shaped pack citation under `.agents/` would fail the gate in a
thin consumer rather than mislead silently.

## Requirements

- Add `.gemini/settings.local.json` to `optionalReferencePaths`, with the same
  shape of comment as its Claude twin, naming `.gitignore:104`.
- Pin the conversion's actual scope with a test: a `scripts/<name>` reference
  is repointed into `~/.agents/bin/`, and a reference already written under
  `.agents/` — bin, skills, and docs, file and directory — survives unchanged.
- Do not build rewrite machinery for tokens already under `.agents/`. Nothing needs it, the
  gate covers the risk, and speculative rewrites would repoint citations that
  are already true.
- Ship both together; they are one release.

## Acceptance Criteria

- [ ] `shouldCheckDocumentationPathReference('.gemini/settings.local.json')` is
      `false` and `('.gemini/settings.json')` is `true`, asserted as a pair.
- [ ] A test fails against today's code if the conversion is ever taught to
      rewrite tokens under `.agents/`, or stops rewriting `scripts/<name>`.
- [ ] `make check` passes; whole-tree preflight stays at 0 failures.
- [ ] Version bump with a `CHANGELOG.md` entry that states the corrected rule,
      not the file/directory framing.

## Out Of Scope

- Rewriting the 0.71.44 CHANGELOG entry. Its fix and reasoning are right; only
  the parenthetical mechanism was imprecise, and this entry supersedes it.
- The fleet refresh.
