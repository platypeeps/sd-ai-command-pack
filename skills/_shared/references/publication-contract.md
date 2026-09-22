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

The dashboard finds `docs/dashboard/` by itself: every checkout under its
`REPO_ROOT` holding that directory is a document root, enumerated from disk.
So a repository publishing to the default location enters the Documents tab
by having the directory, and the only thing left to say is what to call it:

    label|<key>|<label>

`root|<key>|<label>|<directory>` stays for a directory the dashboard cannot
find — somewhere outside `docs/dashboard/`, as `hoa` publishes into `reports`.
It is the one form that can say something the disk does not, so it is the one
form that should carry a path. **Do not write a `root|` row for the default
location.** It is the default written down a second time, and it goes stale the
moment the repository moves while still looking authoritative — which is the
drift the enumeration removed.

Whatever installs the repository's documents writes that line, and writes it
once. For a research repo that is `sd-research-kit render`, which registers
`docs/dashboard/` at the end of every run; `sd-research-kit publish` does the
same without rebuilding. Registration is idempotent, and a key already naming
another directory is reported rather than overwritten.

One exception to "reported rather than overwritten": a row for this
repository's key naming a directory *inside this repository* is this
repository's row, and is rewritten in place rather than duplicated. That
retires a `build/` row — the published directory before `docs/dashboard/` —
and it retires a `root|` row for the default location that an earlier renderer
wrote, replacing it with the `label|` row and keeping the label it carried. A
row naming *another* repository's directory is still a collision, and is still
only reported.

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

A repository that publishes re-renders when git changes a document. For a
research repo, `sd-research-kit init-hook` installs the hook that does it, as
post-commit, post-merge and post-checkout, so a pull or a branch switch renders
too; the hook never fails the git command, because the change has already been
made when it runs.
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
| Notion | `notion=` | a configured page id per scope, `<folder>/<repo>`; `space=` overrides it | `page=` |
| Google Drive | `drive=` | defaults to `Briefs/<repo>`; `folder=` overrides | `file=` |

    notion=dict()                    # private briefs folder, <repo> page
    notion=dict(team=True)           # team briefs folder, <repo> page
    drive=dict()                     # My Drive, Briefs/<repo> folder
    drive=dict(folder="<name or id>", file="<file id or url>")

Both keys on one entry are two mirrors, not a choice. Until one of these keys
exists, the document publishes locally and nowhere else.

### A Notion mirror is private unless it asks for the team

`notion=dict()` mirrors to the folder `$SD_NOTION_PRIVATE_FOLDER` names.
`notion=dict(team=True)` mirrors to the one `$SD_NOTION_TEAM_FOLDER` names.

The default is private because the two mistakes are not symmetric. A brief the
team cannot see is repaired by adding `team=True` and draining again. A private
brief in a shared team space has already been read by the team, and deleting it
does not undo that. So the direction that happens by accident is the recoverable
one.

`space=` overrides the folder, never the scope: naming a folder says where
inside a space, not which space. A document that must reach the team says so
with `team=True` and nothing else does it.

**Each default folder is a configured Notion page id, not a folder name.** A
name lookup that finds nothing returns an empty result rather than an error, so
a rename would move every default mirror to nowhere and tell no one. A page id
belongs to one Notion account, so no id ships with the pack either. Each
operator sets their own, beside `$OBSIDIAN_VAULT`:

    SD_NOTION_PRIVATE_FOLDER=<notion page id>
    SD_NOTION_TEAM_FOLDER=<notion page id>

A page URL is accepted in place of a bare id. An unset variable, or one holding
a folder name rather than an id, refuses that mirror and names the variable to
set. The render still writes the local copies; only the outward request is
withheld. Nothing falls back to a folder name or to a page some other account
owns.

**A default lands in the repo's own page under that folder**, the way a Drive
default lands in `Briefs/<repo>`. The request carries the repo in `subfolder`,
and the drain creates that page under `space_id` when it is missing. Without
it, every repository's briefs pile into the folder itself, beside the per-repo
pages already there.

A `space=` override is pinned by id too when it is written as a page id or a
page URL, and it replaces the whole container — no `subfolder` is appended to
what the user named. Written as a plain name it cannot be pinned, so the
request says which of the two it is: `resolve: "id"` with the folder in
`space_id`, or `resolve: "name"` with `space_id` empty and the name in `space`.

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

The page or file is optional at every destination. Absent, the drain creates it
and writes the id back, which steps 4 and 5 of the drain require. Present, the
drain updates that one rather than leaving a fresh copy behind on every render. The two halves are one mechanism: the write-back is what lets the
next render's request name a page, and naming one is what stops a second copy.

Recording the target makes it machine-readable for the first time. Before this,
the page title and parent lived in no file the kit read, so verifying a mirror
against its source was manual and therefore skipped.

## How an outward mirror is updated

A render does not call any outward destination. Rendering runs in a git hook and
in CI, neither of which can reach an MCP server, and the pack holds no
credential for any of them.

So a render enqueues. It writes one sync request per document per destination,
naming the document, its container, the page or file to update, the source
revision and a `fingerprint` -- the digest of what this generation of the
request would write. An agent session drains the queue through that
destination's connector and records the result. The request is durable: an
enqueue that is never drained stays visible rather than expiring.

A render queues a document only when that fingerprint differs from the one a
drain last recorded as delivered, and from the one a still-pending request
carries. A receipt beside the queue holds both; `SD_MIRROR_REQUEUE=1` on the
invocation queues every designated document regardless.

A render from a linked worktree queues nothing and writes no vault copy. Its
`docs/dashboard/` is rendered, and the dashboard row it would register is the
repository's own, but publication is the main checkout's: an unmerged branch
that queued under the repository's name would replace the pending request,
inherit the page id a drain recorded for it, and become the canonical mirror.
The refusal names the checkout to run in. `SD_PUBLISH_FROM_WORKTREE=1` on the
invocation is the operator saying, in words, that this branch's content is the
canonical copy.

One queue carries every destination, and `bin/sd-status` reports a pending
request as `mirror-sync-pending`. A document designated for two places is two
requests, and either can drain while the other waits.

That queue was once `~/.claude/pending-notion-syncs`, before one queue carried
every destination. A render moves anything left there into the current queue,
and the status report covers both names, so the rename costs no request its
row either side of the move. Neither directory is created by looking, an
emptied one is left standing rather than swept, and a request moves verbatim
rather than being rewritten to a schema it was not written under.

This makes the mirror reliable without giving a hook a long-lived write
credential to a shared space. It also keeps the outward-facing step in a place
where a person is present.

Draining is six steps per request, and the order matters:

1. Read the request. It names the destination, the document, its Markdown,
   rendered and source paths, its container, the page or file to update, the
   revision the render was made from and its `fingerprint`, which step 6
   hands back. A Notion request also names its `scope`,
   `private` or `team`, how its container was resolved — `resolve: "id"` with
   the folder's page id in `space_id`, or `resolve: "name"` with the folder's
   name in `space` — and `subfolder`, the page under that container the
   document belongs in.
2. Check the document's handling restrictions first. One that may not be shared
   externally is not mirrored to a shared destination, and designating it did
   not lift that. Report it and leave the request in place.
3. Mirror the document to the named container, in that destination's **native
   format**, updating the page or file the request names rather than creating a
   second one:

   - `notion` — the Notion connector, as Notion blocks. With `resolve: "id"`,
     write under the page `space_id` names and never search for that folder by
     name. With `resolve: "name"`, look the folder up by the name in `space`,
     and treat a lookup that finds nothing as a failure to report rather than
     an empty result — do not create a folder to make the name resolve. Where
     the request names a `subfolder`, the document goes in that page under the
     container and not in the container itself; create it when it is missing,
     the way a Drive drain creates `Briefs/<repo>`. Honour `scope` either way:
     a `private` request goes to your private space and never to the team
     space, whatever the folder is called.
   - `drive` — the Google Workspace connector, as a native Google Doc. Not an
     uploaded `.md` or `.html` file: the point of the mirror is that someone can
     read and comment on it in place. Import the Markdown so headings, tables
     and code blocks survive. A `folder` of the form `Briefs/<repo>` resolves
     under My Drive's root; create the repo folder when it is missing, and do
     not adopt a `Briefs` folder found somewhere else.

   Never convert a document into a format its destination does not read
   natively. The source for every mirror is the Markdown, not the rendered
   HTML.

   **Look before creating.** Where the request names no page or file, search
   the named container for one already carrying this document's title, and
   adopt the match instead of creating a second. A drain that creates
   unconditionally makes a duplicate out of every interrupted earlier drain.
   Two matches is an ambiguity, not a choice: report it and leave the request
   in place.
4. Write the id into the request file, the moment the destination returns it.
   The request is the durable record, because it is the one file the drain is
   certain it can write and the one the next drain is certain to read. A
   request that already named a page or file created nothing, so steps 4 and 5
   have nothing to record.

   This step exists for the gap between creating a page and recording it. A
   created page whose id is written nowhere is the duplicate this procedure
   exists to prevent: the next render enqueues a create again, and the next
   drain makes a second copy. Both copies carry the same title and the same
   content, so nothing reads as wrong and no reader can tell which is stale.

   **A re-render carries a recorded id forward rather than overwriting it.**
   A render rewrites the request for every designated document, and the
   post-commit hook renders on every commit touching a document — so without
   this, any commit landing between step 4 and step 5 erased the only record
   of the created page, and the gap step 4 exists to close reopened by the
   one route neither step watches. An id is carried only while the request
   still names the same document, in the same repository, in the same
   container. A page id belongs to the folder it was created under, so a
   designation moved to another folder, or to the other Notion scope, drops it
   and the drain resolves the new container afresh. The document and the
   repository are compared because the queue filename says neither: it is keyed
   on a repository's basename, and two checkouts of that name may designate a
   document of the same name into the same default folder. How the container
   was *spelled* is not compared — a folder written as a page URL and the same
   folder written as its bare id are one container — and neither is the
   document's title, since a renamed document keeps its page.
5. Write the id into the document's designation, as `page=` for Notion and
   `file=` for Drive. In a research repo that designation is a key on the
   document's `research.conf.py` entry, and it is what the *next render* reads
   — step 4 only carries the id as far as the current request.

   A designation written as the bare `True` shorthand is amended into the dict
   that records the id: `notion=True` becomes `notion=dict(page="<id>")`, which
   is the same designation with the same private scope. A designation written
   `None` or `False` is switched off, so it enqueues nothing, and no drain ever
   reaches it. Never add a key to a document that designates no mirror.

   If this write fails — an unwritable file, a config the drain cannot amend —
   report it and stop, leaving the request in place with its id. The queue then
   still says work is owed, and the next drain updates the page it names rather
   than creating one.
6. Run `sd-research-kit delivered <request file name> <fingerprint>`, with the
   fingerprint read in step 1, once steps 4 and 5 have both succeeded. It
   records that fingerprint as delivered beside the queue and removes the
   request only while the file is still that generation. A render that queued
   newer content while steps 2 to 5 ran leaves its request in place, and the
   next drain writes it. Do not delete the file by hand: that acknowledged
   whatever the file held at that moment, which after such a render was
   content the drain had not written -- and the next render, reading the
   empty slot as delivered, then never queued it again. A request left behind
   says the sync still owes work, which is the safe thing for it to say if
   any earlier step half-finished.

**What each failure leaves behind.** This is stated, not implied, because a
procedure whose failure mode is the bug it prevents is not a fix.

| Interrupted after | State | What the next drain does |
| --- | --- | --- |
| step 3, before step 4 | a created page, its id recorded nowhere | adopts it by title under step 3 and carries on |
| step 4, before step 5 | id in the request, not in the designation | updates that page, retries step 5 |
| step 5, before step 6 | id recorded in both | updates that page, runs step 6 |
| a render during steps 2–5 | a newer request under the same name | step 6 leaves it; the next drain writes it |

Every row survives a render in between, because a render carries a recorded id
forward under step 4 rather than overwriting the request.

One state is not covered: a page created in step 3 whose title then changes
before the next drain runs, *and* whose id reached neither the request nor the
designation. Nothing matches it, so the next drain creates a second page and
the first is orphaned. That is the first row of the table and a rename
together; a rename alone is covered, since a carried id finds the page
whatever it is now called. A destination that creates a page and returns an
error instead of an id lands in the first row and recovers there — by title,
so rename a mirrored document whose drain errored and check its mirror by
hand.

Never drain a request into a container it does not resolve to, never create a
page or file outside that container -- the one the document names, or the
configured default for its destination when the document names none -- and
never drain a request to a destination other than the one it names.

## Order

Redaction and source standards run before publication, not after. A document
that fails `source-standards.md` is not published anywhere, including locally.
Publication never launders an unverified claim into a page that looks finished.
