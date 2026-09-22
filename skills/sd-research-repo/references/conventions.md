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

## The repo's own `CLAUDE.md`

Every research repo carries a `CLAUDE.md` — the short form of this standard, for
an agent working in the repo with no pack checkout to read. It comes from
`skills/sd-research-repo/templates/CLAUDE.md`, and until 2026-09-12 it came from
there by no written route at all: five repos carried a copy, nothing said to
install one, and nothing re-read them. One divergence sat unnoticed for six
weeks and was reported three separate times as three findings.

**Laying the first copy is a supported operation, and re-laying it is not.**

```bash
sd-research-kit init-claude-md     # from inside a repo that has none
```

That verb writes `CLAUDE.md` and refuses outright if one is already there. The
refusal is the design, not a gap: a research repo legitimately states parts of
the template differently — a repo whose Notion folder is a team space replaces
the template's personal `file:///` Source header, because the page is read by
people who have no such checkout — and a writer that merged the template back
over an existing copy would undo that silently, putting an absolute path on a
team page. There is no re-sync verb and there should not be one.

So after the first copy, the file is managed by being **checked** rather than by
being rewritten. `sd-research-kit review` compares this repo's `CLAUDE.md`
against the template and reports what the repo no longer says. The comparison is
one-directional: the template is a floor, not a ceiling. Anything the repo adds
— a whole local section, an extra paragraph inside a shared one — is the repo
doing its job and is counted, never reported.

### Declare intentional differences

Declare each intentional replacement under this heading:

```markdown
## Local overrides of the shared template

- `the opening`: use STE-Concise sentences without changing the template instructions.
- `## Publishing — the dashboard by default, outward mirrors on designation`: omit
  personal checkout paths from shared pages.
```

Use the exact template heading, including `##`, inside backticks.
Use `the opening` for content before the first H2 heading, including the document title.
Place actual declarations outside code fences.
The parser ignores examples inside triple-backtick fences.

- State a reason for each entry. Missing reasons fail review and leave drift findings active.
- Name an existing template section. Unknown sections fail review.
- Keep overrides narrow. An opening override does not cover H2 sections.
- Read each overridden section again when the template changes. Later changes within that section receive no comparison.

`review` prints each accepted override, its reason, and the count of suppressed drift findings.
The opening declaration follows the same rules as section declarations.
The parser and filtering logic live in `source:bin/sd_research_review.py::declared_overrides` and `source:bin/sd_research_review.py::apply_overrides`.

A repo with no `CLAUDE.md` at all, and a pack install whose `skills/` is missing
from beside its `bin/`, both fail the review rather than passing quietly: a gate
that cannot run has not passed.

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
| `docs/dashboard/` | Rendered HTML, served by the dashboard. Generated — never hand-edit. Gitignored. |
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

## Main document — START HERE

Every research project has exactly one main document for readers entering the document set.
Use the title `START HERE — <descriptive project or decision title>`.
Choose the document that explains scope, current conclusions, decisions, and where supporting evidence lives.
For multiple research tracks, use an overview that directs readers to each track.

- Apply this convention during project setup and the next update to an existing project.
- Use the same title in the Markdown H1, `research.conf.py` `title` and `h1`, and the title of every mirror.
- Put a prominent **Start here** link near the top of the README.
  Link a mirror when the document has one; otherwise, link the Markdown source.
- Identify the main document in the README document table and in each mirror's parent container.
- Keep the existing source filename, type prefix, mirror page or file id, URL, icon, and parent.
  The title identifies the document's role.
- If another document takes this role, move the `START HERE — ` title marker to the
  new one, strike it from the old one, and update all entry links.
  Rename no file and re-parent no mirror: a role change edits titles and
  links only, never a filename, a type prefix, or a mirror's identity.
  Exactly one document carries the `START HERE — ` marker.

`sd-research-kit review` enumerates the configured documents and checks the two
surfaces that are inside the checkout: each document's H1, and the `title` and
`h1` the config renders it under. Missing, duplicate and mismatched all fail it.
Its scope is the configured documents, not the tree — a superseded draft in
`90-scratch/` still carrying an old marker is neither cited nor mirrored, and is
not a duplicate.

The README entry link and each mirror's title and parent are in no file the kit
reads, so reading those back after publication stays manual. The
review's `ok   main document` line names the surfaces it did check, so that a
pass is not read as a claim about the two it did not.

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
skip links sibling notion drive`. The visual identity is shared and lives in the
renderer, so
every repo renders the same way.

One form is written per document. `docs/dashboard/<name>.html` is standalone,
opens with `file://`, and is the form the dashboard's Documents tab lists and
serves — the published form, not merely a local one. The content-only
`build/artifact/` form is gone: nothing consumed it, and the dashboard folder's
contract is that everything in it is published. Add or edit pages in
`research.conf.py`, never by editing generated files.

Rendering ends by writing each document's Markdown into the Obsidian vault,
registering `docs/dashboard/` with the dashboard, and queueing a sync for every
document that designates an outward destination. Every step is idempotent. See
Publishing, and `references/publication-contract.md`.

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

Nothing is published — to a mirror or anywhere else — until it has been reviewed
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

**The second reader is an independent CLI reviewer**, and its framing is not
written here any more. The stance, the four-part finding format and the
confidence tags live in `local-adversarial-gate/core.md` in the `system` repo,
shared with `sd-writing-pack`, which built the same gate separately and kept its
own copy of the same caveats. `adversarial-gate render --lens research-brief`
prints the focus text; `adversarial-gate run` does the whole pass for a caller
that wants the scripted path.

This pass is the research flow's first review point, *after the brief and
decisions*. Its cap is the one on that row in the sd-ai-command-pack checkout's
`.claude/rules/sd-planning-adversarial-review.md`. The pass over the final
product, before the send box, is the second row and has its own cap. Read the
caps there — in the pack, which is where that file lives; a research repo does
not carry it. This file states none.

**It runs as a CLI, not as a harness plugin.** Which reviewer runs the pass,
and the exact invocation, are not retyped here — the kit's own checklist is the
one place they are written, so nothing here can go stale against it:

```bash
sd-research-kit review
```

Under *The second reader* it prints two commands: the availability check, which
says whether the CLI is installed and logged in, and the pass itself. Run it
first and take the invocation from there. The plugin that supplies the
`/codex:*` slash commands is not a dependency of this kit and may not be
installed, and a research repo that tells its reader to run
`/codex:adversarial-review` sends them to a command that does not exist. Do
not reach for the `/codex:*` slash commands.

Three things to get right:

- **`-s read-only` is not optional.** It is what keeps an adversarial reader
  from editing the work it is reviewing. There is no reason to run this pass
  without it.
- **It reads the repository, not a file path and not a URL**, and the focus text
  below points it at **uncommitted** working-tree changes. So the ordinary case
  is: review before committing. Already committed — on a branch, or merged to
  `main` — `git status` and `git diff` show it nothing, and the pass silently
  reviews an empty diff. For work already committed on a branch, say so in the
  prompt and name the comparison: *"review `git diff main...HEAD`"*. Name the
  documents too when the diff is large.
- **Its default framing is a code review** — auth boundaries, races, migrations,
  rollback. Use the focus text printed by `sd-research-kit review`.
  `CHECKLIST` in `bin/sd_research_review.py` owns that text.
  Do not copy the prompt into a repository guide.

  Run it in the background for anything past a page. It buffers stdout, so it
  prints nothing at all until it exits — silence is normal, not a hang. If you
  background it by appending `> pass.txt 2>&1 &` to the invocation, the same
  applies to the file: empty means still running.

**What it cannot do.** The second reader sees the repository, not the sources.
It cannot discharge step 2 — opening the citation and reading it is yours, and
no second reader substitutes for it. What it does catch is the claim with no
citation behind it, the rate without its base, the assumption doing load-bearing
work off the page, and the conclusion that only follows if you already know the
material.

Record the pass in Status like any other check: which reader ran it and on
`<date>`, what it raised, what was changed and what was rejected with the
reason. If that CLI is missing or not logged in — the availability check the
checklist prints reports it — say *that* in Status. "No independent pass" is a
stated gap; self-review that quietly presents itself as review is the defect
this section exists to prevent.

## Publishing — the dashboard by default, outward mirrors on designation

`references/publication-contract.md` governs this. It applies to every skill in
the pack, not only to research repos; what follows is how a research repo meets
it.

**Superseded 2026-09-20.** Before this date the standard said every overview,
map, brief, report and survey had a Notion page. That is now the exception
rather than the rule: an outward destination is outward-facing, so a document
reaches one only when the user designates it. The designation alone is enough,
because each destination has a default container; naming one overrides that
default.

### Obsidian and the dashboard are the defaults

`sd-research-kit render` ends by writing each document's Markdown into
`$OBSIDIAN_VAULT/Briefs/<repo>/<name>.md`. That vault copy is where the document
lives; everything else is a duplicate of it in another format. The note carries
frontmatter naming the source repo, path and revision, so a reader knows which
checkout owns it and that the note is not the place to edit.

`render` also registers `docs/dashboard/` with the local dashboard's Documents
tab, and the tab lists and serves **everything it finds there**. That folder is
gitignored — it is regenerated on every commit — and `render` adds the ignore
entry itself. Registration is one line in the dashboard's `documents.conf`,
`label|<key>|<label>`, written once and idempotent. It carries no path: the
dashboard enumerates `docs/dashboard/` from disk, so a path in the row would
be the default location written down a second time and would go stale the
moment the repo moved. The dashboard reads that file and never writes it, so
the repo keeps owning its own output.

The Documents tab serves under `default-src 'none'; style-src 'unsafe-inline';
img-src data:; font-src data:`. The renderer already meets it — fonts are
embedded as data: URIs by `bin/sd_research_fonts.py`, styles are inline, and
there is no script. Do not add a `<link>`, a `<script>` or a remote image to a
rendered page: it will not load, and the page will render degraded rather than
fail visibly.

`90-scratch/` is not published. Neither is working state — ledgers, receipts,
handoff packets. Publish what a reader is meant to read.

### Outward destinations are per document

The user designates a document. Each destination has a default container, so
the designation alone is enough; the user names a container only to override
the default. Record the designation in that document's `DOCS` entry, where the
document is already described:

```python
notion=dict()                    # private briefs folder, <repo> page
notion=dict(team=True)           # team briefs folder, <repo> page
drive=dict()                     # My Drive, Briefs/<repo> folder
drive=dict(folder="Research deliverables", file="https://docs.google.com/document/d/...")
```

| Destination | Key | Container | Existing page or file (optional) |
| --- | --- | --- | --- |
| Notion | `notion=` | a configured page id per scope, `<folder>/<repo>`; `space=` overrides it | `page=` |
| Google Drive | `drive=` | defaults to `Briefs/<repo>`; `folder=` overrides | `file=` |

Both keys on one entry are two mirrors, not a choice. Until one of these keys
exists, the document publishes locally and nowhere else. Do not infer a target
from a title, a folder or a neighbouring document.

`notion=True` is the same designation as `notion=dict()`, written shorter, and
a write-back amends it into `notion=dict(page="<id>")`. `None` and `False` are
the off position: they designate nothing, enqueue nothing, and never receive a
written-back id.

**A Notion mirror is private unless it asks for the team.** `notion=dict()`
goes to the folder `$SD_NOTION_PRIVATE_FOLDER` names;
`notion=dict(team=True)` goes to the one `$SD_NOTION_TEAM_FOLDER` names.
Private is the default because the two mistakes are not symmetric: a
brief the team cannot see is repaired by adding `team=True` and draining again,
and a private brief in a shared team space has already been read. `space=`
overrides the folder, never the scope.

**Each default folder is a configured page id.** Set it per operator, beside
`$OBSIDIAN_VAULT`:

```sh
SD_NOTION_PRIVATE_FOLDER=<notion page id>
SD_NOTION_TEAM_FOLDER=<notion page id>
```

A page id and not a folder name, because a name lookup that finds nothing
returns an empty result rather than an error, so a rename would move every
default mirror to nowhere in silence. Configured and not shipped, because a
page id belongs to one Notion account. A page URL works in place of a bare id.
An unset variable, or one holding a name rather than an id, refuses that mirror
and names the variable to set; the local copies are written either way.

**A default lands in the repo's own page under that folder**, the way a Drive
default lands in `Briefs/<repo>`. The request names the repo in `subfolder`,
and the drain creates that page when it is missing.

A `space=` override written as a page id or page URL is pinned by id too, and
it replaces the whole container, so no `subfolder` is appended to it. Written
as a plain name it cannot be pinned, and the request says which by carrying
`resolve: "id"` with `space_id` or `resolve: "name"` with the name in `space`.

**A Drive mirror lands beside its siblings.** `drive=dict()` goes to
`Briefs/<repo>` in My Drive, the same shape the vault uses, so the two copies
agree on where a brief lives. The drain resolves the path and creates the repo
folder when it is missing. `folder=` overrides it for a document that belongs
somewhere a reader already looks.

The folder `sdw.drive_publishing_folder` names is not this default. That one is
the Mezmo blog's gate, and a brief placed in it would read as cleared for
publication.

The page or file is optional everywhere. Without it the drain creates the page
or file and writes the id it got back into the designation, before it deletes
the request. With it the drain updates that one, which is what stops a re-render
leaving a second copy behind. `references/publication-contract.md` holds the
drain's step order, and this page states no second version of it.

Recording it in `research.conf.py` is what makes the mirror machine-readable.
The README's **Notion pages** table stays, for the human reader, but it is no
longer the only place the target is written; a Drive mirror is listed there too.

### How a mirror is updated

A render does not call Notion or Drive. It runs in a git hook and in CI, neither
of which reaches an MCP server, and the pack holds no credential for either.
Instead it writes a sync request per designated document per destination under
`~/.claude/pending-mirror-syncs/`, naming the destination, the document, its
container, the page or file to update and the source revision.

An agent session drains that queue through the connector the request names, in
that destination's native format: the Notion connector for
`destination: notion`, as Notion blocks; the Google Workspace connector for
`destination: drive`, as a native Google Doc. A Notion request also carries a
`scope`, `private` or `team`, and a `private` request never reaches the team
space whatever its folder is called. It carries `resolve` too: with `id`, write
under the page `space_id` names and never search by name; with `name`, a lookup
that finds nothing is a failure to report, not a folder to create. Where it
names a `subfolder`, the document goes in that page under the container, which
the drain creates when it is missing. The source for every mirror is the
Markdown, never the rendered HTML. One request file per document per destination, so a
re-render replaces the pending request rather than queueing a second one; a
request that is never drained stays on disk. A document whose Markdown, title
and container have not changed since it was last queued is not queued again,
whether that request is still pending or the drain has recorded it as
delivered: `render` keeps a receipt beside the queue, the drain's last step
(`sd-research-kit delivered`) writes the delivered half of it, and
`SD_MIRROR_REQUEUE=1` queues every designated document regardless. A render
from a linked worktree writes that worktree's `docs/dashboard/` and nothing
else -- no vault copy, no request -- unless `SD_PUBLISH_FROM_WORKTREE=1` is on
the invocation; the refusal names the main checkout to run in.
`references/publication-contract.md` says how the status report surfaces one.

Mirror shape — the full document minus its H1, opening with a pointer back to
the file so a reader who lands in the mirror knows where to edit:

```markdown
*Source: **`<absolute path to the markdown>`** — edit there, then update this page.*

<the document's provenance line>

---

## 1. First section
```

**Notion.** It round-trips tables, fenced code blocks (ASCII diagrams
included), blockquotes, and nested lists faithfully; write an empty table cell
as a single space. A document too large for one `notion-create-pages` call is
created with its first half, then extended with `notion-update-page` /
`insert_content` at `position: end`. Give each page an icon and keep it stable
across updates — a changed icon reads as a different page.

**Google Drive.** Mirror as a Google Doc, not as an uploaded `.md` or `.html`
file: the point of the mirror is that someone can read and comment on it in
place. Create it with the Workspace connector's Markdown import so headings,
tables and code blocks survive, then record the resulting file id in `file=`.
Update that file in place on later drains. Keep the document's name equal to its
title, since Drive search is by name and a renamed copy reads as a second
document. Resolve the folder to an id once and prefer the id thereafter
— two folders may share a name, and a mirror written into the wrong one is a
disclosure rather than a mistake. `Briefs/<repo>` resolves under My Drive's
root, and the repo folder is created when it is missing; a `Briefs` folder
found anywhere else is a different folder and not this one.

Handling restrictions survive the mirror, at every destination: a document that
may not be shared externally may not be mirrored to a shared Notion space or a
shared Drive folder either, and designating one does not lift the restriction.

### Artifacts

Research is still not published as artifacts — the hosted single-page surface
the renderer's retired `build/artifact/` form was written for. Pages published
as artifacts before 2026-08-27 stay where they are as historical record.

## Style

- Absolute paths when pointing at a local file: `file:///Users/...`, never a bare
  path — a bare path gets linkified into a URL that cannot resolve.
- Every repo is a git repo, and every restructure moves files with `git mv` so
  history follows.
