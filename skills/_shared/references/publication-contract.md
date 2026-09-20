# Publication contract

Read this before deciding where a finished document goes.

This contract applies to the pack and to every consumer of it. It states two
default destinations and a set of outward ones, each opt-in per document. It
does not decide whether a document is finished; that is the producing skill's
judgment.

| Destination | When | Format | Written by |
| --- | --- | --- | --- |
| Obsidian | always | Markdown | the render, directly |
| Dashboard | always | HTML | the render, directly |
| Notion | designated | Notion blocks | an agent session, from the queue |
| Google Drive | designated | native Google Doc | an agent session, from the queue |

A document lives in Obsidian. The other three are duplicates of it, each in the
format its destination reads natively — a Markdown file pasted into Drive, or an
HTML blob pasted into Obsidian, is a copy nobody can use where it landed.

## Obsidian is where a document lives

A finished document is written into the vault as Markdown, under
`Briefs/<repo>/<name>.md`. `$OBSIDIAN_VAULT` names the vault; a machine with
none still publishes everywhere else and reports the missing copy by name.

Markdown, because the vault's whole value is that a note is editable, linkable
and searchable in place. The file carries a frontmatter block naming the source
repo, the source path and the revision, so a reader who finds the note knows
which checkout owns it — and knows the note is not the place to edit.

This is a local filesystem write, so a render performs it directly. It needs no
connector, no credential and no drain, which is what lets the primary copy be
the one that never waits.

## The dashboard is the other default

A finished document is also published to the local dashboard's **Documents**
tab, as HTML. Publication is the default, not a step the user requests. A
document nobody can find was not delivered.

The HTML is written to `docs/dashboard/` in the producing repository, and the
dashboard serves **everything it finds there**. That folder is gitignored: it is
regenerated on every commit, and tracking it would put a generated diff in front
of a reader on every render.

The dashboard reads the directory and never writes to it, so the producing
repository owns its own output. A report belongs to the repository that
generates it.

Both default destinations are local. Writing a note into your own vault and
serving a page on loopback are not disclosure, and this contract grants no
authority to send anything outside the machine. Every outward destination below
is opt-in per document, and none is reached by default.

## What publishes, and what does not

Publish the work products a reader is meant to read: reports, briefs, proposals,
reviews, specs, plans, status summaries, research documents.

Do not publish working state. Adjudication ledgers, check receipts, handoff
packets, monitor state, profile artifacts and scratch output stay where they
are. They have readers, but the reader is the next skill, not a person browsing
a list. A Documents tab that lists everything lists nothing.

When a skill is unsure, it publishes. An unwanted page is one line removed from
a conf file. An unpublished finding is a finding nobody read.

## A published page carries its own resources

Served documents run under `default-src 'none'; style-src 'unsafe-inline';
img-src data:; font-src data:`. An external stylesheet, script, font or image is
blocked, and the page renders degraded rather than failing loudly.

So a published page embeds what it needs. Fonts are data: URIs, images are data:
URIs, styles are inline, and there is no script. The same page then opens
identically over `file://` with no network, which is the other way these pages
are read.

`bin/sd_research_fonts.py` holds the vendored faces for the research renderer.
A skill that emits its own HTML meets the same rule by itself.

## Registration

A repository enters the Documents tab through one line in the dashboard's
`documents.conf`:

    root|<key>|<label>|<directory>

Whatever installs the repository's documents writes that line, and writes it
once. For a research repo that is `sd-research-kit render`, which registers
`docs/dashboard/` at the end of every run; `sd-research-kit publish` does the
same without rebuilding. Registration is idempotent, and a key already naming
another directory is reported rather than overwritten.

One exception to "reported rather than overwritten": a row for this repository's
key naming this repository's own `build/` is moved. `build/` was the published
directory before `docs/dashboard/`, and a row left pointing at it serves a tree
nothing renders into any more. A row naming *another* repository's directory is
still a collision, and is still only reported.

It does not belong in the dashboard's source: a fleet dashboard carrying one
repository's path would be wrong in a way that is awkward to undo, which is why
the conf file exists. A machine with no dashboard checkout still renders its
documents — the registration is reported as skipped, and the render succeeds.

`documents.conf` is shared across machines. A root that is absent on this
machine is reported by name rather than hidden, because a silently missing
section looks the same as a report that was never generated.

## Staying current

Rendered output goes stale the moment its source changes, and a stale page is
worse than a missing one because it looks current.

A repository that publishes re-renders on commit. For a research repo,
`sd-research-kit init-hook` installs the post-commit hook that does it; the hook
never fails the commit, because the commit has already been made when it runs.
The dashboard's freshness indicator is then a statement about the render, not
about whether anyone remembered. A verification-only mode that fails on stale
output is acceptable where a write hook is not wanted; silence is not.

## Outward destinations are per document, and opt-in

An outward mirror is the durable shareable copy. Outward destinations are
outward-facing by definition, so no document reaches one by default and no skill
infers a target from a title, a path or a neighbour.

The user designates a document at that time. The designation is recorded where
the document is already described — a destination key on that document's entry
in `research.conf.py`:

| Destination | Key | Container | Existing page or file (optional) |
| --- | --- | --- | --- |
| Notion | `notion=` | defaulted per scope; `space=` overrides the folder | `page=` |
| Google Drive | `drive=` | defaults to `Briefs/<repo>`; `folder=` overrides | `file=` |

    notion=dict()                    # private space, Briefs folder
    notion=dict(team=True)           # R&D team space, R&D Briefs folder
    drive=dict()                     # My Drive, Briefs/<repo> folder
    drive=dict(folder="<name or id>", file="<file id or url>")

Both keys on one entry are two mirrors, not a choice. Until one of these keys
exists, the document publishes locally and nowhere else.

### A Notion mirror is private unless it asks for the team

`notion=dict()` mirrors to **your private space, `Briefs` folder**.
`notion=dict(team=True)` mirrors to the **R&D team space, `R&D Briefs` folder**.

The default is private because the two mistakes are not symmetric. A brief the
team cannot see is repaired by adding `team=True` and draining again. A private
brief in a shared team space has already been read by the team, and deleting it
does not undo that. So the direction that happens by accident is the recoverable
one.

`space=` overrides the folder, never the scope: naming a folder says where
inside a space, not which space. A document that must reach the team says so
with `team=True` and nothing else does it.

### A Drive mirror lands beside its siblings

`drive=dict()` mirrors to **`Briefs/<repo>` in My Drive** — the same shape the
vault uses, so the two copies agree on where a brief lives. A reader who knows
where one brief is knows where all of them are, whichever copy they found first.

The drain resolves that path and creates the repo folder when it is missing, so
a new repo publishes without anyone provisioning a folder first. `folder=`
overrides the default with a folder name or id, for a document that belongs
somewhere a reader already looks.

The Drive folder that `sdw.drive_publishing_folder` names is a different thing
and is not this default. That folder is the Mezmo blog's gate: a piece sitting
in it has cleared every publishing check. A brief mirrored into it would read as
approved for publication, which no designation here claims.

The page or file is optional at every destination: absent, the drain creates it
and the designation can be amended with the id it got; present, the drain
updates that one rather than leaving a fresh copy behind on every render.

Recording the target makes it machine-readable for the first time. Before this,
the page title and parent lived in no file the kit read, so verifying a mirror
against its source was manual and therefore skipped.

## How an outward mirror is updated

A render does not call any outward destination. Rendering runs in a git hook and
in CI, neither of which can reach an MCP server, and the pack holds no
credential for any of them.

So a render enqueues. It writes one sync request per document per destination,
naming the document, its container, the page or file to update and the source
revision. An agent session drains the queue through that destination's connector
and records the result. The request is durable: an enqueue that is never drained
stays visible rather than expiring.

One queue carries every destination, and `bin/sd-status` reports a pending
request as `mirror-sync-pending`. A document designated for two places is two
requests, and either can drain while the other waits.

This makes the mirror reliable without giving a hook a long-lived write
credential to a shared space. It also keeps the outward-facing step in a place
where a person is present.

Draining is four steps per request, and the order matters:

1. Read the request. It names the destination, the document, its Markdown,
   rendered and source paths, its container, the page or file to update and the
   revision the render was made from. A Notion request also names its `scope`,
   `private` or `team`.
2. Check the document's handling restrictions first. One that may not be shared
   externally is not mirrored to a shared destination, and designating it did
   not lift that. Report it and leave the request in place.
3. Mirror the document to the named container, in that destination's **native
   format**, updating the page or file the request names rather than creating a
   second one:

   - `notion` — the Notion connector, as Notion blocks. Honour `scope`: a
     `private` request goes to your private space and never to the team space,
     whatever the folder is called.
   - `drive` — the Google Workspace connector, as a native Google Doc. Not an
     uploaded `.md` or `.html` file: the point of the mirror is that someone can
     read and comment on it in place. Import the Markdown so headings, tables
     and code blocks survive. A `folder` of the form `Briefs/<repo>` resolves
     under My Drive's root; create the repo folder when it is missing, and do
     not adopt a `Briefs` folder found somewhere else.

   Never convert a document into a format its destination does not read
   natively. The source for every mirror is the Markdown, not the rendered
   HTML.
4. Delete the request file. Deleting it is what records that the mirror is
   current; a request left behind says the sync still owes work, which is the
   safe thing for it to say if step 3 half-finished.

Never drain a request into a container the request does not name, never create a
page or file in a container the user has not named for that document, and never
drain a request to a destination other than the one it names.

## Order

Redaction and source standards run before publication, not after. A document
that fails `source-standards.md` is not published anywhere, including locally.
Publication never launders an unverified claim into a page that looks finished.
