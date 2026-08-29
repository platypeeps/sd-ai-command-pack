# Design: an inline, line-scoped marker for a deliberately absent path

## Boundary

One check changes: `checkDocumentationPathReferences` and the extraction it
depends on, in `templates/scripts/sd-ai-command-pack-review-preflight.mjs` with
the root mirror `scripts/sd-ai-command-pack-review-preflight.mjs` synchronized
(`AGENTS.md:36`). Nothing else in the preflight, the installer, or the fleet
path is touched.

Eligibility is not touched. `shouldCheckDocumentationPathReference` keeps its
current prefix/top-level-file rules exactly; widening them is
`08-06-preflight-bare-filename-references`, absorbed into this PRD as an
explicitly sequenced phase 2. `optionalReferencePaths` is not touched either,
in code or in its default array.

## The marker

A reference is exempt when a marker follows it **immediately** on the same
line, separated by nothing but spaces or tabs:

```
`scripts/check_review_readiness.sh` [absent: lives in loadsmith, not distributed by this pack]
```

The marker is `[absent: <reason>]`. The reason is required and must be
non-empty; it may not contain `]` or a newline.

Formally, a reference match ending at offset `end` is exempt when the text at
`end` matches:

```js
/^[ \t]*\[absent:[^\]\r\n\u2028\u2029]*[^\]\s][^\]\r\n\u2028\u2029]*\]/
```

The reason class is `[^\]\s]`, not `\S`. `\S` matches `]` itself, so
`[absent:]]` would satisfy a `\S`-based pattern with an empty reason — a
suppression with no stated cause, which is the one thing the required reason
exists to prevent.

The surrounding classes exclude `\r`, U+2028, and U+2029 as well as `\n`.
Excluding only `\n` lets a reason swallow a bare-CR or Unicode line separator
and close its bracket on what a reader sees as the next line, which is a
suppression that spans a line boundary the contract says it cannot cross.

### Why this shape

- **Visible.** `[absent: …]` is literal text in CommonMark — a bracket span
  with no following `(` or `[` is not an inline or collapsed link, and it is a
  shortcut reference link only if a matching link reference definition exists,
  which nothing here defines and the rendering test asserts stays true — so it
  renders in GitHub's Markdown view, in an editor preview, and in the raw
  file. Requirement 2 is satisfied by the rendered document itself, not by a
  config file the reader would have to go find. An HTML comment was rejected for exactly this: it is
  invisible in rendered prose, which is the failure mode requirement 2 names.
- **Line-scoped, in fact reference-scoped.** The marker exempts the single
  reference it directly follows. A second reference to the same path elsewhere
  in the same file — or later on the same line — is unaffected. This is what
  makes requirement 5 mechanically true rather than a promise.
- **Carries its reason.** The author must say why the path is absent. That is
  the sentence a future reader needs, and requiring it makes a reflexive
  silencing marker more work than fixing a genuinely rotted path.
- **The path stays a path.** The reference keeps its code span or Markdown
  link, so it still reads as a path and, for a link, still resolves for a
  reader. Removing the backticks — the workaround on `main` today — is exactly
  what this replaces.

### Rejected alternatives

| Alternative | Why not |
| --- | --- |
| `<!-- preflight-ignore -->` comment | Invisible in rendered prose; fails requirement 2. |
| A per-file declaration block (`## Deliberately absent paths`) | File-scoped, so it exempts *every* reference to that path in the file. Directly contradicts requirement 5 and the acceptance criterion that an unmarked reference to the same path in the same file still fails. |
| Marker anywhere on the line, applying to the last reference | Reads more naturally mid-sentence, but silently picks a reference when a line carries several. A wrong pick is a silent false pass, which is the defect class this task exists to shrink. |
| Extending `optionalReferencePaths` | Repository-wide and permanent; requirement 1 rejects it and requirement 3 reserves that list for paths that are optional everywhere. |
| Bare `[absent]` with no reason | Cheaper to write, and cheaper to write is the problem: nothing records why, so the next author cannot tell a deliberate absence from a silenced defect. |

A reason is prose, and prose in this repository sometimes contains code spans.
A backticked path inside a reason is collected and checked like any other
reference — the marker exempts the reference it follows, not the text it
carries. That is deliberate: a reason citing a path that has since moved should
still fail.

Prose sometimes needs light rewording so the reference sits at a natural pause
before the marker. That is a deliberate cost of unambiguous scoping.

## Where it applies in the code

`extractDocumentationPathReferences` already filters at collection time through
`shouldCheckDocumentationPathReference`. The marker test joins it there: a
marked match is not collected, so `findMissingDocumentationPathReferences` and
`checkDocumentationPathReferences` need no change beyond their pass message.

The test cannot live in `shouldCheckDocumentationPathReference`, which receives
only a target string and has no view of the surrounding text. That predicate
stays a pure function of the path, which is also what keeps its existing tests
meaningful.

Both extraction passes — `markdown-link` and `code-span` — apply the same test
against `match.index + match[0].length`.

### The code-formatted link, which one anchor gets wrong

A path is commonly written as both at once:

```
[`docs/missing.md`](docs/missing.md)
```

Extraction returns **two** references for that — verified 2026-08-19, one
`markdown-link` and one `code-span`, both targeting `docs/missing.md`. A marker
placed after the link ends immediately follows only the link match; the code
span ends at its closing backtick, followed by `](…)`, so a single end-offset
anchor leaves the second reference checked and the marked line still fails.

So a reference has two acceptable anchors: the end of its own match, and — for
a code span wholly contained inside a Markdown link match **whose target is the
same path** — the end of that link. The `markdown-link` pass already runs
first, so its match spans and targets are available to the `code-span` pass
without a second scan.

The same-target condition is not decoration. In `` [`docs/display.md`](docs/target.md) ``
the two references name different paths, and a link-end anchor without the
condition would suppress both from one marker — silencing a path the author
never marked, which is requirement 5's failure mode reappearing one level
down. With the condition, the marker exempts the link and leaves the code span
checked.

There is no reverse case: a Markdown link cannot be nested inside a code span,
because a code span's content is literal.

## Fail-closed behavior

Every malformed or misplaced marker leaves the reference checked:

- `[absent:]` or `[absent:   ]` — empty reason, no suppression.
- `[absent lives elsewhere]` — missing colon, no suppression.
- A marker on the next line, or before the reference, no suppression.
- An unclosed `[absent: …` running to end of line, no suppression.
- Anything between the reference and the marker other than spaces or tabs, no
  suppression.

There is no configuration surface, so there is no config to parse, fail open
on, or fail closed on. This is the deliberate difference from the sibling task
`08-18-preflight-path-refs-ignore-aware`, whose declaration-file shape has to
answer "what does an unreadable declaration mean" — a question this design
never asks.

## Pass message

The current message claims more than the code did and will claim less than it
does after this change:

```
documentation path references resolve to existing repo files or documented external/local-only paths.
```

It becomes accurate about all three accepted outcomes: resolved, optional by
configuration, or marked absent at the point of use. This also settles
requirement 6 of `08-18-preflight-path-refs-ignore-aware`, whose residual
scope shrinks to whatever a tracked declaration would still buy over an inline
marker.

## Compatibility and shipped surfaces

A consumer running an older installed preflight does not understand the marker
and will fail on a marked reference. That matters only for content this pack
ships or that a consumer copies:

- Task PRDs are not shipped, so markers in `.trellis/tasks/**` here reach no
  consumer.
- The documentation change in `templates/docs/SD_AI_COMMAND_PACK.md` must
  illustrate the marker with a path that is **not eligible** for the check
  under any pack version — a path matching no `referencePrefixes` entry and no
  `topLevelReferenceFiles` entry. Otherwise the example itself fails the
  installed preflight in every consumer that has not yet refreshed.

Note that a fenced code block is no protection here: extraction runs a raw
regex over the whole file, so a backticked path inside a fence is still
collected. Eligibility, not fencing, is what makes the example safe.

The marker is additive: no existing document changes meaning, and a repository
that never writes one sees identical behavior.

## Shipped-payload consequences

`templates/scripts/sd-ai-command-pack-review-preflight.mjs` is a manifest
payload row (`manifest.json:278`), so changing it is a release-payload change,
not an ordinary edit. Three obligations follow, none of which are optional:

- `manifest.json` bumps and `CHANGELOG.md` gains a matching top heading. CI
  runs a `Release payload gate` against the PR base and blocks a payload change
  without both (`CONTRIBUTING.md:146-152`).
- `make generate` refreshes the plugin `bin/` and `machine-payload/` copies;
  the committed-tree test fails on drift and names that command
  (`tests/test_generate_plugin.py:827`).
- `make sync` re-runs `install.py . --force`, which is what actually
  synchronizes the root mirror, plus the spec KB refresh
  (`CONTRIBUTING.md:157-160`). A hand-copied mirror is not the sanctioned path.

A version bump additionally requires the all-pass
`docs/fleet/candidate-validation.json` that `make release-prep` produces or
reuses, matching the exact payload and fleet manifest.

## Rollback

Reverting the code commit restores the old behavior, and any marker already
written degrades to literal text that renders harmlessly. It does **not**
restore the two references on `main`, which this task re-backticks: a revert
must also revert that content change, or the preflight fails again on the same
two lines it failed on 2026-08-08. The two belong in one commit for that
reason.

## Sequencing against 08-06 (absorbed phase 2)

The absorbed eligibility widening lands strictly after this, as the PRD
requires. Widening first would grow the false-positive class while the only
escape hatch is still the repository-wide list.

That sequencing means phase 2 is **not** in this change. The PRD says both
that eligibility is out of scope and that R1-R4 are carried here as a phase-2
requirement; the acceptance criteria settle which reading governs, since none
of the seven mentions bare filenames. Phase 2 becomes a successor Trellis task
created when this one merges, carrying R1-R4 verbatim. Leaving it implicit is
how an absorbed requirement quietly disappears.
