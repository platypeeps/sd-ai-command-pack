# Design — stop ignoring `.claude/` path citations

## Current behaviour

`shouldCheckDocumentationPathReference` (`scripts/sd-ai-command-pack-review-preflight.mjs:5180`)
consults three config lists in order: a citation must start with a
`referencePrefixes` entry (or be a `topLevelReferenceFiles` name, or a bare
filename), must not start with an `ignoredReferencePrefixes` entry, and must not be
listed in `optionalReferencePaths`. All three answers are the same shape: the
function returns `false` and the citation is skipped.

`.claude/` appears in both lists — at line 378 under `referencePrefixes`
(line 375), and again at line 436 under `ignoredReferencePrefixes` (line 434).
The ignore is unconditional, so the prefix the first list declares checkable is
never checked. No test asserts either behaviour, which is why the contradiction
outlived every edit to both lists since 2026-07-05.

The other three ignored prefixes — `.build/`, `.local/`, `node_modules/` — are
whole trees that are generated or never committed. `.claude/` is neither: it is
an authored adapter tree the installer writes into, and every other pack rule
treats it as first-class.

## Change

Two edits to the config block, both in
`templates/scripts/sd-ai-command-pack-review-preflight.mjs`. `templates/**` is
the source of truth for shipped files (`CONTRIBUTING.md:153`); the `scripts/`,
`plugins/sd/bin/`, and `plugins/sd/machine-payload/scripts/` copies are
byte-identical mirrors. Editing the `scripts/` mirror is silently undone —
`make sync` reinstalls it from `templates/`.

1. Delete the `'.claude/',` entry from `ignoredReferencePrefixes` (line 436).
   The entry at line 378 stays.
2. Add `'.claude/settings.local.json'` to `optionalReferencePaths`, with a
   comment naming `.gitignore:66` as the reason — the file is per-checkout
   machine state, so "missing" is its normal condition in a clean clone.

Nothing else in the checker changes. No new mechanism is introduced:
`optionalReferencePaths` already means exactly "this path may legitimately not
exist", and already carries six `.sd-ai-command-pack/` entries of the same
shape.

### Why `optionalReferencePaths` and not a narrower ignore

A tempting alternative is to keep an ignore entry and narrow it to
`.claude/settings.local.json`. Behaviourally the two are the same — both make
`shouldCheckDocumentationPathReference` return `false`, and
`ignoredReferencePrefixes` is read nowhere else in the checker (its only other
mentions are the list itself and the config-key allow-list at line 498). The
difference is expressive and matching-shaped, and both cut the same way:

- `ignoredReferencePrefixes` is prefix-matched, so an entry there also silences
  every sibling that merely starts with the string — a `settings.local.json.bak`
  or a `settings.local.json/` tree. `optionalReferencePaths` is exact.
- The list names its own reason. A reader auditing `ignoredReferencePrefixes`
  sees three generated-or-never-committed trees and one file; a reader auditing
  `optionalReferencePaths` sees six `.sd-ai-command-pack/` runtime artifacts and
  one Claude settings file, which is the company it belongs in.

### Rejected: exempt the whole machine-local family

`.gitignore` ignores six more `.claude/` patterns at lines 67-72
(`**/*.local.*`, `**/.cache/`, `**/cache/`, `**/logs/`, `**/tmp/`, `**/*.log`)
and mirrors the whole family under `.gemini/` at lines 104-110.
None of them is cited anywhere in the fleet today, and `optionalReferencePaths`
is an exact-path set with no glob support, so covering them means either new
matching machinery or six speculative entries.

`.gemini/` settles it: today it sits in `referencePrefixes`, is absent from
`ignoredReferencePrefixes`, and has no exemption for its own
`settings.local.json` — and the pack repository reports zero failures, because
nothing cites that file. A tree-wide grep finds no citation of it anywhere in
this checkout. The exemption list stays evidence-driven. If a
`.gemini/settings.local.json` citation ever appears it will fail loudly and get
the same one-line entry then.

### Rejected: drop `.claude/` from `referencePrefixes` instead

This resolves the contradiction the other way and keeps the gate blind on
purpose. It contradicts the installer, which writes `.claude/` as a primary
target, and it would silently stop checking the adapter tree most likely to
carry stale skill paths — the exact class Copilot had to find by hand.

## Test surface

The checker's unit assertions live in the node harness embedded in
`tests/test_review_preflight.py`; the `shouldCheckDocumentationPathReference`
block is at lines 810–824. Three assertions go there:

- `shouldCheckDocumentationPathReference('.claude/skills/sd-work-backlog/SKILL.md')`
  is `true`. Against the pre-change checker this is `false`, so the assertion
  fails without the fix — it pins the new behaviour rather than describing it.
- `shouldCheckDocumentationPathReference('.claude/settings.local.json')` is
  `false`. On its own this passes vacuously against the old checker, which
  answers `false` for every `.claude/` path.
- `shouldCheckDocumentationPathReference('.claude/settings.json')` is `true` —
  the pair the convention stated at line 826 requires. It is what distinguishes
  "exempt because it is machine-local" from "exempt because the whole tree is
  ignored"; without it the previous assertion pins nothing.

## Data repair

Removing the ignore makes five existing citations in this repository visible,
plus one in se-ai-command-pack. They are four distinct kinds and get four
treatments (`prd.md` classifies them; `implement.md` lists the exact lines):

| kind | treatment |
| --- | --- |
| prose shorthand `.claude/.codex/.gemini/.opencode/.github` | reword so it stops parsing as a path |
| forward-looking lane citations (2) | `[absent: <reason>]` |
| upstream `.claude/hooks/statusline.py` | `[absent: <reason>]` |
| `.claude/settings.local.json` | no edit; the config entry covers it |

**Self-reference hazard.** This task's own `prd.md` quotes all four shapes, so
it becomes a failure the moment the rule lands — a patched-checker run reported
four failures inside it. `design.md` and `implement.md` are exempt by an
existing rule (line 3236): task design/implement artifacts are forward-looking
and reference files the task proposes to create, so a path-existence check on
them would be wrong. That exemption is why only `prd.md` and research notes
need the sweep. The repair pass must cover the task
directory, not only the five pre-existing sites — and the shorthand in
`prd.md:57` cannot be marked, only reworded, because a marker after it would
still leave a token that reads as a path.

## Propagation and rollout

`templates/scripts/…-review-preflight.mjs` is the source; three mirrors follow
it (`scripts/`, `plugins/sd/bin/`, `plugins/sd/machine-payload/scripts/`).
`make sync` runs `install.py . --force`, which installs `templates/` into this
repo's own `scripts/` and adapter trees; `make generate` rebuilds `plugins/` and
runs the surface-closure check. Sync first, then generate: generate compares the
mirrors against `templates/` and fails `mirror.stale` if they have not been
installed yet.

Ships as a patch version with a `CHANGELOG.md` entry. Consumers pick it up on
their next refresh; refreshing them is out of scope.

## Rollback

Re-adding the one line to `ignoredReferencePrefixes` restores the old
behaviour exactly. The data repairs are independently correct — a marked
forward-looking citation and a reworded shorthand are improvements whether or
not the rule is in force — so a rollback does not have to revert them.

## Risk

The measured fleet-wide delta is six findings, all classified, none of them a
real dangling path in shipped surface. All six measured consumers are
`mode=thin`, and five of them moved by zero — partly explained rather than
lucky, since the thin profile repoints prose to `~/.agents/...` and the checker
skips any citation starting with `~`. The exception is se-ai-command-pack,
which is thin and still carried one `.claude/skills/` citation, so thinness
suppresses this class without eliminating it. The unmeasured exposure is
`rwbp-coordinator` and `rwbp-website`, not cloned here. Loadsmith's 24
pre-existing failures are unaffected (delta 0); they gate nothing new that this
change introduces.
