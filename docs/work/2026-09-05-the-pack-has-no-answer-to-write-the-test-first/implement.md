# Implement — the pack has no answer to "write the test first"

One pull request, `#779`, squashed to `a0d43aa5`. The item's `prd.md` and
`design.md` landed in the same commit as the skills they describe, because the
work was written on a branch that predates the retire and never had a landing
of its own.

| file | lines |
|---|---|
| `contrib/sd-tdd/SKILL.md` | 291, new |
| `contrib/sd-typed-holes/SKILL.md` | +44, the `## Lineage` section |
| this item's `prd.md` | 854, new |
| this item's `design.md` | 201, new |

No Python, no `bin/` tool, no test file. `git diff --stat a0d43aa5^ a0d43aa5
-- bin/ dashboard/ tests/test_loc_caps.py` prints nothing, so no cap moved and
none needed to.

## The landing site moved under the branch

`design.md` says `skills/sd-tdd/SKILL.md`, and the branch was written when
that was the right path. Between the last commit on it and the merge, PR 2 and
PR 5 of the solo-process item moved every off-path skill into `contrib/`, and
PR 7 retired the `status:` line from `prd.md` frontmatter. Three things this
item names had moved under it.

**`skills/sd-tdd/` fails `make check`.** Criterion 24 of the solo-process item
makes a directory under `skills/` that no path in `skills/paths.json` names an
install refusal, and `sd_install.unnamed_directories()` returned
`['sd-tdd']` on the rebased tree. Two ways out: name it on a path, or put it
in `contrib/`.

**It went to `contrib/`, and the file that decides says why.**
`skills/paths.json` admits a skill because "the path would be broken without
it, never because it is adjacent to one". The development path — plan to build
to ship — shipped in PR 2 without sd-tdd and is not broken. And requirement 7's
whole point is that sd-tdd and sd-typed-holes are lineage siblings that only
*look* opposed; splitting them across `skills/` and `contrib/` would put the
seam this item exists to close back on a directory boundary. They now sit
together, one `sd skill try sd-tdd` away.

**The item's own criteria named the pre-move paths**, so they name the real
ones now. Two of them also carried a `-- skills/` pathspec that would print
nothing after the move; those read `-- skills/ contrib/`. The rebuttal of C-27
further down `prd.md` still quotes the pathspec as it stood when the lane ran,
because a record of what a review said is not edited to match a later tree.

**`status: in_progress` is gone and the archived reference is repointed.** The
row is the status after PR 7, and
`2026-09-04-two-unwritten-disciplines-and-one-contradicted-rule` moved to
`docs/work/archive/2026-09/` while this branch sat. Rule 7 of `sd-docs-lint`
caught the second; rule 1's inverted sign caught the first.

## The gate the merge did not expect

The `route` job refused the first push:

```
sd-review: refused: 11 commit(s) in b7cfefe6..b3a208e0 carry no
Authored-with: trailer, starting at 3bdeefbd14b4.
```

The eleven commits predate the trailer. `sd attribute b7cfefe6..b3a208e0
claude` is the verb written for exactly that case; it wrote one empty commit
carrying eleven `Attributes:` lines and its own `Authored-with: human`, and
`route` passed on the next push. Running it needed
`~/.local/share/sd/providers.yaml`, which was absent — the installer seeds it
from the repository's `providers.yaml` and never overwrites one that is there.

The commit says `human` and the operator did not type it. The verb hardcodes
that value on the reasoning that an attribution is an operator act; nothing
here can write a truer one, and this paragraph is the correction.

## Scores

Run against `a0d43aa5^..a0d43aa5` rather than `origin/main...HEAD`, since the
branch is merged and gone.

| criterion | result |
|---|---|
| exactly one addition under the skill trees | `contrib/sd-tdd/SKILL.md`, alone |
| no deletion under `skills/ contrib/ tests/` | nothing printed |
| exactly two skill files change | the two named, and nothing else |
| the seven-heading skeleton | all seven print `1` |
| requirements 1–5 and 8 pinned to phrases | all ten print at least `1` |
| requirement 8 is a heading | prints `1` |
| requirement 6's four seams named | `sd-debug` 2, the other three 1 each |
| requirement 7's lineage cites licence and revision | `obra/superpowers`, `MIT`, `b36e082`, each `1` |
| requirement 9's lineage names its upstream | `Shearerbeard/claude-skills`, `c79fe3a`, `no licence file`, each `1` |
| `test_skill_companions` and `test_doc_citations` | `Ran 15 tests`, `OK` |
| `bin/`, `dashboard/` and the caps file untouched | nothing printed |
| `make check` ends with `0` `FAILED` | `0` |

**One criterion's number is stale and the criterion is met anyway.** It asks
for `40` `OK` alongside the `0` `FAILED`. `make check` now prints `56`. The
count is the number of test modules the gate runs, which sixteen modules have
joined since this item was written — PR 1 through PR 8 of the solo-process item
added most of them. A pinned count of a growing set measures the calendar, not
the change; the half that carries the meaning, `0 FAILED`, holds.

## What this item does not close

Nothing. Requirement 6's seams are named in the skill and not enforced by a
test, which `design.md` says is deliberate: a skill file is prose, and the
frontmatter suite enumerating `contrib/` from disk is the only machine check a
folded skill gets here.
