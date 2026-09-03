# Research repo conventions

The standard every research repo follows. Written 2026-08-27, when six repos were
aligned onto it; moved into this pack on 2026-09-03, so the standard and the
tooling that enforces it are versioned in one repository rather than two. Each
repo's `CLAUDE.md` points here; where a repo needs something this document does
not cover, it says so in its own `CLAUDE.md` rather than inventing a private
variant.

**Which repos follow it, and where each publishes, is not recorded here.** Those
are per-repo bindings and they live in each repo's own `research.conf.py` — a
table in a shared document has to be edited in a seventh place every time a
seventh repo appears, and it is wrong from the moment one is renamed.

Fan-out and file-tool rules are not here either: they are properties of the
harness rather than of this standard, and live in
`references/subagent-dispatch.md`.

## Layout

| Path | Holds |
|---|---|
| `00-overview/` | `understanding.md`, `open-questions.md`, `next-research.md` — fixed names |
| `10-sources/` | `registry.md` (what was read, when, status), `references.md` (link list) |
| `20-map/` | `MAP-*.md` — structured ledgers, crosswalks, comparisons |
| `30-brief/` | `BRIEF-*` argued positions · `REVIEW-*` assessments · `SUMMARY-*` condensations |
| `40-docs/` | `PRD-` `DESIGN-` `PLAN-` `SPIKE-` `SURVEY-` `DISCOVERY-` `BENCHMARK-` `DECK-` `OUTREACH-` |
| `90-scratch/` | Throwaway and superseded. Never cited. |
| `assets/` | Images the docs reference |
| `build/` | Rendered HTML. Generated — never hand-edit. Gitignored. |
| `vendor/` | Third-party clones. Gitignored. |

Use only the directories the repo needs; do not invent new ones. The numbers are
reading order, not a workflow — `00` is where a newcomer starts, `90` is where
nothing is cited from.

Type prefixes carry meaning:

- `SURVEY-` mirrors an **external** system — a repo, a service, a running app.
  Record what it was read at (commit, or the date for a live surface) in the
  provenance block, and refresh when that system changes materially.
- `SPIKE-` is a measurement plan or a measurement result, with its gates declared
  up front.
- `REVIEW-` assesses something someone else produced; `BRIEF-` argues a position
  of our own.

## Documents

Every document opens with an H1, a provenance paragraph, then `---`:

```markdown
# Title

Compiled 2026-08-27 from `owner/repo` @ `abc1234`, plus <other sources>.

---

## 1. First section
```

The renderer strips everything above `---` and builds the masthead from
`research.conf.py`, so that block is written for readers of the markdown.

- `##` headings become the rail nav. Number them when order matters.
- State what is **verified** and what is **not verified** in a closing Status
  section. A number with its validation status beats an adjective.
- Corrections stay visible — say what changed and why; never silently overwrite a
  claim someone may have already acted on.
- One claim, one source. From code, cite `file:line`; from a repo survey, cite
  the commit; from a tracker, cite the ticket.
- Supersession is stated in the document, not encoded in its filename.

## Rendering

```bash
sd-research-kit render
```

Every verb acts on the repository the caller is standing in and takes no path
argument, so run it from inside the repo. The kit took `render [repo_dir]` before
it moved into this pack; R10-D6 says a command resolves its repository from the
current working directory and nowhere else.

Each repo supplies a `research.conf.py` naming `PROJECT` and a `DOCS` list;
per-doc keys are `src out title h1 eyebrow stand meta vtitle figs legend footer
skip links sibling`. The visual identity is shared and lives in the renderer, so
every repo renders the same way.

Two forms are written per document. `build/<name>.html` is standalone and opens
with `file://`; it is a local reading form, not a publishing surface.
`build/artifact/<name>.html` is content only — the renderer still emits it, but
nothing consumes it, because research is not published as artifacts (see
Publishing). Add or edit pages in `research.conf.py`, never by editing generated
files.

Verify links before publishing:

```bash
sd-research-kit checklinks
```

It resolves markdown links relative to the containing file, and backticked paths
carrying a `NN-dir/` segment against the repo root. A backticked bare filename is
prose, not a link — docs legitimately name files that live in another repo or do
not exist yet.

Check what the documents pin:

```bash
sd-research-kit pins
```

For every `source` @ `sha` the markdown asserts, it says whether upstream has
moved past it. The list is read out of the documents each run, never maintained.

## Adversarial review before publishing

Nothing is published — to Notion or anywhere else — until it has been reviewed
against itself. Two halves, both required: the **information** the document rests
on, and the **product** a reader will actually receive. The mechanical half is a
command:

```bash
sd-research-kit review
```

It checks what a script can decide — every document has a provenance block,
closes with a Status section that separates verified from not verified, and is
not newer than its build — and then prints the checklist for the half no script
can do. Exit 1 means fix it first.

**The information.** Take the review adversarially: the job is to refute the
document, not to confirm it.

1. List the load-bearing claims. A claim is load-bearing if removing it changes
   the conclusion; anything else is context and does not need this treatment.
2. Open the cited source again and read it. Default to refuted — a claim stands
   only if the source *says* it, not merely that it is consistent with it.
   Second-hand support ("the summary says the paper found") is not support.
3. Numbers: check the unit, the date and the denominator, not the digits. A rate
   without its base has not been checked.
4. A claim no source supports is cut, or moved into Status as explicitly
   unverified. It never stays in the body, where a reader assumes it was checked.
5. Say what you could not check and why. A stated gap is useful; a silent one is
   a defect.

**The product.** Read what the reader gets, not what you meant.

6. Read the rendered page as someone who has not seen the source material. Does
   the conclusion follow from what is on the page, or only from what you happen
   to know?
7. Find the load-bearing assumption the document never states. There is usually
   one.
8. After mirroring, check the published page against the source, and that
   handling restrictions survived the mirror — a document that may not be shared
   externally may not become a shared page.

The outcome goes in the Status section: what was verified and how, what was not,
what was cut. A review that found nothing says so, and says what it checked —
"reviewed" without a record of what was examined is indistinguishable from not
reviewing.

Reviewing your own work is the weak form; it is the one that ships most often, so
it is the one to be disciplined about. Where the document carries a decision
someone will act on, get a second reader who was not involved in writing it.

**The second reader is Codex**, and its framing is not written here any more.
The stance, the four-part finding format and the confidence tags live in
`local-adversarial-gate/core.md` in the `system` repo, shared with
`sd-writing-pack`, which built the same gate separately and kept its own copy of
the same caveats. `adversarial-gate render --lens research-brief` prints the
focus text for the command below; `adversarial-gate run` does the whole pass for
a caller that wants the scripted path.

**The second reader is the `codex` CLI, not a Claude plugin.** This is the same
position `docs/planning-adversarial-review-codex.md` takes for the pack's own
review lane, and it holds here for the same reason: the `codex@openai-codex`
plugin is not a dependency of this kit, it may not be installed, and a research
repo that tells its reader to run `/codex:adversarial-review` sends them to a
command that does not exist. Do not reach for the `/codex:*` slash commands.

```
codex doctor                              # is it installed, is it logged in
codex exec -s read-only "<focus>"         # the pass itself
```

Three things to get right:

- **`-s read-only` is not optional.** It is what keeps an adversarial reader
  from editing the work it is reviewing. There is no reason to run this pass
  without it.
- **It reads the working tree, not a file path and not a URL.** The document has
  to be *in* the working tree or a branch diff against `main` — review before
  committing, or on a branch. A document already merged to `main` gives it
  nothing to look at. Name the documents in the prompt when the diff is large.
- **Its default framing is a code review** — auth boundaries, races, migrations,
  rollback. Prose needs the focus text to redirect it:

  ```
  codex exec -s read-only "This is a markdown research repository, not code.
    Review the uncommitted working-tree changes (git status, git diff, plus
    untracked new files) as an adversarial reader. Attack the argument, not the
    syntax: which load-bearing claims does the cited source not actually
    support; which numbers are missing a unit, a date or a denominator; what
    does the conclusion depend on that the document never states; where does a
    document assert something as verified that the repo shows was not checked.
    Cite file and line. Do not modify any files."
  ```

  Run it in the background for anything past a page. It buffers its output, so
  an empty output file means still running, not hung.

**What it cannot do.** Codex sees the repository, not the sources. It cannot
discharge step 2 — opening the citation and reading it is yours, and no second
reader substitutes for it. What it does catch is the claim with no citation
behind it, the rate without its base, the assumption doing load-bearing work off
the page, and the conclusion that only follows if you already know the material.

Record the pass in Status like any other check: reviewed by Codex on `<date>`,
what it raised, what was changed and what was rejected with the reason. If
`codex` is missing or not logged in — `codex doctor` reports it — say *that* in
Status. "No independent pass" is a stated gap; self-review that quietly presents
itself as review is the defect this section exists to prevent.

## Publishing — Notion, not artifacts

**Research is not published as Claude artifacts.** Notion is the publishing
surface. Pages published as artifacts before 2026-08-27 stay where they are as
historical record; nothing new goes there, and updates go to Notion.

Every overview, map, brief, report, and survey has a Notion page under the
repo's own folder, mirroring the repo's layout. Which folder that is belongs to
the repo, not to this standard: record it in the repo's `research.conf.py` and
its README, not in a table here.

The markdown file is the source of truth; the Notion page is the readable,
shareable mirror, and is updated whenever the source document changes.
`90-scratch/` is not mirrored.

Mirror shape — the full document minus its H1, opening with a pointer back to the
file so a reader who lands in Notion knows where to edit:

```markdown
*Source: **`<absolute path to the markdown>`** — edit there, then update this page.*

<the document's provenance line>

---

## 1. First section
```

Notion round-trips tables, fenced code blocks (ASCII diagrams included),
blockquotes, and nested lists faithfully; write an empty table cell as a single
space. A document too large for one `notion-create-pages` call is created with
its first half, then extended with `notion-update-page` / `insert_content` at
`position: end`.

Give each page an icon and keep it stable across updates — a changed icon reads
as a different page. Record every page in the README's **Notion pages** table:
document, page title, URL. Handling restrictions survive the mirror: a document
that may not be shared externally may not be mirrored to a shared Notion page
either.

## Style

- Absolute paths when pointing at a local file: `file:///Users/...`, never a bare
  path — a bare path gets linkified into a URL that cannot resolve.
- Every repo is a git repo, and every restructure moves files with `git mv` so
  history follows.
