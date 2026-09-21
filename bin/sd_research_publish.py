#!/usr/bin/env python3
"""Register a research repo with the dashboard, and queue its outward mirrors.

The publication contract is
`skills/_shared/references/publication-contract.md`; this is the half of it a
script can carry out. Two jobs, both run at the end of `render`:

1. **Register.** Append this repo's `label|key|label` line to the dashboard's
   `documents.conf`, once. The dashboard finds `docs/dashboard/` on disk, so
   the line says what to call it and carries no path; `root|` stays for a
   directory the dashboard cannot find. The dashboard reads that file and
   never writes it, so nothing here touches the dashboard's own source.

2. **Enqueue.** For each document designated for a destination in
   `DESTINATIONS`, write a sync request naming the document, its container, the
   page or file to update and the source revision. Rendering runs in a git hook
   and in CI, neither of which can reach an MCP server, and the pack holds no
   credential for any destination -- so a render never calls one and does not
   try. An agent session drains the queue.

One queue for every destination rather than one queue each, and one request
file per document *per destination*: a document designated for two places is
two independent pieces of outstanding work, and either can drain while the
other waits. The filename carries the repo, the document and the destination,
so a re-render overwrites the pending request rather than queueing a second.

A request that is never drained stays on disk: the queue does not expire,
because an expiring queue reports a mirror as done that was never written.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from sd_lib import git_output

#: Where the dashboard checkout lives. Overridable because a fleet machine may
#: hold it elsewhere; not discovered by searching, because a search that found
#: two checkouts would have to guess which one the browser is serving.
DASHBOARD_HOME = Path(
    os.environ.get("SD_DASHBOARD_HOME", "~/repos/system/local-project-dashboard")
).expanduser()

#: Durable, outside any repo, and beside the vault-write queue that already
#: works this way. `~/.claude/` and not `/tmp`: a request that a reboot deletes
#: is a mirror nobody knows went missing. One queue for every destination:
#: `bin/sd-status` reads it, and a queue per destination would mean a producer
#: and a status class per destination, which `actionable_inventory` already
#: refuses for the same reason (C-3, one producer and not three).
QUEUE = Path(
    os.environ.get("SD_MIRROR_QUEUE", "~/.claude/pending-mirror-syncs")
).expanduser()

#: What `QUEUE` was called before one queue carried every destination. A
#: machine that rendered between the queue landing and the rename holds
#: requests here, and nothing has read this path since -- so the upgrade left
#: them durable and invisible, which is the one thing a durable queue must
#: never be. `migrate_legacy_queue` empties it; nothing writes it.
LEGACY_QUEUE = Path(
    os.environ.get("SD_NOTION_QUEUE", "~/.claude/pending-notion-syncs")
).expanduser()


#: The vault the Obsidian copy is written into, and the folder inside it that
#: holds briefs. `$OBSIDIAN_VAULT` is the same variable `bin/sd`'s vault driver
#: reads, and it is deliberately not defaulted here: `store_root` refuses an
#: unset one rather than guessing, and a second spelling of that path is how a
#: write lands in somebody else's vault layout.
VAULT = os.environ.get("OBSIDIAN_VAULT", "")
BRIEFS = "Briefs"

#: Where the dashboard's HTML is written, relative to the repo. Gitignored:
#: it is generated on every commit, and a generated tree in history turns each
#: render into a diff nobody reads. It replaces `build/`, which was both the
#: rendering scratch space and the published directory -- one of which belongs
#: in the repo's own layout and the other of which is a publication surface.
DASHBOARD_DIR = Path("docs") / "dashboard"


class Destination(NamedTuple):
    """One outward place a document may be designated for.

    The dashboard and Obsidian are deliberately absent: both are local writes a
    render performs itself, so neither takes a queue, a connector or a drain.
    This table is what leaves the machine.

    `what` is optional: absent, the drain creates the page or file and writes
    the id it got back into the designation, which the contract's drain step 4
    requires; present, the drain updates that one rather than creating a second
    copy on every render.
    """

    #: The DOCS key the user writes, and the `destination` field of a request.
    name: str
    #: The field naming the container the mirror is written into.
    where: str
    #: The optional field: the existing page or file to update in place.
    what: str
    #: How a report and a status row name the container, in words.
    noun: str
    #: The container a designation that names none falls back to, as a format
    #: string over the repo name. Every destination has one, so no designation
    #: has to name a container to be valid. Notion resolves its own per scope
    #: in `notion_target`, so its entry here is empty.
    default: str = ""


#: Adding a destination is a row here plus a drain step in the contract. It is
#: deliberately not open-ended: an unknown key in a DOCS entry is a typo, and a
#: table that accepted anything would queue a mirror to a place nothing drains.
DESTINATIONS = (
    # `space` is the key a designation writes, and the label a request carries.
    # The container a Notion drain resolves is `space_id`, set by
    # `notion_target`; this row never resolves one.
    Destination("notion", "space", "page", "Notion folder"),
    Destination("drive", "folder", "file", "Drive folder",
                default=BRIEFS + "/%s"),
)

#: The row a request's `destination` field names. Derived rather than written
#: twice, so a destination added to the table above is reachable from a queued
#: request without anything else being remembered.
BY_NAME = {dest.name: dest for dest in DESTINATIONS}

class NotionScope(NamedTuple):
    """One Notion default destination: the setting that names it, in words.

    The folder itself is neither a name nor an id written here. A name cannot
    be: a lookup that finds nothing returns an empty result rather than an
    error, so a rename would move every default mirror to nowhere and tell no
    one -- and both of this maintainer's folders have been renamed once
    already. An id cannot be either: a page id belongs to one Notion account,
    and a default shipped in this file would send another operator's brief to
    a page they do not own. So the id is the operator's to configure, and this
    table holds the key it is configured under.
    """

    #: `private` or `team`: which Notion space the mirror may reach.
    scope: str
    #: The environment variable holding this operator's folder page id.
    #: Beside `OBSIDIAN_VAULT`, `SD_DASHBOARD_HOME` and `SD_MIRROR_QUEUE`,
    #: which is where this module's other per-machine destinations live. Not
    #: `sd config`: that namespace holds standing authorization, and a folder
    #: is a destination rather than a permission.
    setting: str
    #: How a report and a status row name the folder, over the repo name. The
    #: configured folder's own name is not knowable here, and guessing one
    #: would print a label no operator's Notion has to agree with.
    phrase: str


#: Where a Notion mirror goes when the designation names no folder.
#:
#: Private is the default and the team space is the opt-in, because the two
#: mistakes are not symmetric. A brief the team cannot see is repaired by
#: adding `team=True` and draining again. A private brief in a shared team
#: space has already been seen by the team, and deleting it does not undo that.
#: So the direction that is recoverable is the one that happens by accident.
NOTION_SCOPES = {
    False: NotionScope("private", "SD_NOTION_PRIVATE_FOLDER",
                       "your private Notion briefs folder, under %s"),
    True: NotionScope("team", "SD_NOTION_TEAM_FOLDER",
                      "your team Notion briefs folder, under %s"),
}

#: The environment the folder settings are read out of. A module attribute for
#: the same reason `QUEUE` and `VAULT` are: a test points it at a fixture
#: rather than at the machine running the test.
ENVIRON: dict[str, str] = dict(os.environ)

#: A Notion page id: 32 hex digits, dashed or not, alone or ending a page's
#: URL path. `space=` may be written either way, and so may the configured
#: default, so naming a folder never costs the designation its id resolution.
NOTION_ID = re.compile(
    r"(?:^|[/-])([0-9a-fA-F]{8}-?(?:[0-9a-fA-F]{4}-?){3}[0-9a-fA-F]{12})$")


def notion_id(value: str) -> str:
    """The Notion page id `value` names, or `""` when it names none.

    Read off the URL *path*, so a query string and a fragment are both gone
    before the id is looked for. A copied link often carries `#<block id>`,
    and matching against the whole link found no id at all -- which read as
    "this is a folder name" and sent the drain looking for a folder called
    `https://...`.

    Returned verbatim rather than normalised: the id goes to a connector, and
    rewriting the operator's spelling of it is a second thing that can be wrong.
    """
    found = NOTION_ID.search(urlsplit(value.strip()).path.rstrip("/"))
    return found.group(1) if found else ""

#: The dashboard builds a URL from the key, so the key is what a URL may carry.
#: Mirrored from `sd_dashboard/documents.py`, which rejects anything else.
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def documents_conf() -> Path:
    return DASHBOARD_HOME / "documents.conf"


def repo_key(repo: Path) -> str:
    """A short lowercase key from the directory name.

    Derived and not configured: a key the repo chose for itself could collide
    with another repo's, and the collision would surface as one repo's
    documents silently replacing the other's in the listing.
    """
    stem = repo.name.lower()
    stem = re.sub(r"[^a-z0-9._-]+", "-", stem).strip("-.")
    return stem or "docs"


def _shown(directory: Path) -> str:
    """`~` and not the absolute path: `documents.conf` is shared across
    machines, and an absolute path under one machine's home is wrong on the
    next."""
    home = str(Path.home())
    shown = str(directory)
    if shown == home or shown.startswith(home + os.sep):
        shown = "~" + shown[len(home) :]
    return shown


def _own_row(repo: Path, path: str) -> bool:
    """Whether a row's directory is inside this repository, so ours to rewrite.

    A row naming another repository's directory is a collision to report, not
    a row to take. `build/` and `docs/dashboard/` are both inside this one.
    """
    try:
        return Path(path).expanduser().is_relative_to(repo)
    except (OSError, ValueError):
        return False


def register_root(repo: Path, label: str, directory: Path) -> str:
    """Register this repo with the dashboard, once.

    The dashboard finds `docs/dashboard/` by itself, so registering the default
    location means saying what to call it and nothing more:

        label|<key>|<label>

    A path here would be the default location written down a second time, and
    it goes stale the moment the repository moves while still looking
    authoritative. `root|<key>|<label>|<directory>` stays for a directory the
    dashboard cannot find -- somewhere outside `docs/dashboard/` -- which is
    the only thing a row can say that the disk does not.

    Returns a one-line report. Never raises on a missing dashboard: a machine
    without the dashboard checked out still renders its documents, and failing
    the render would make the reading form hostage to the listing.
    """
    conf = documents_conf()
    if not conf.is_file():
        return "dashboard not registered: no %s" % conf

    key = repo_key(repo)
    if not KEY.fullmatch(key):
        return "dashboard not registered: %r is not a usable key" % key

    found = directory == repo / DASHBOARD_DIR
    shown = _shown(directory)
    line = ("label|%s|%s" % (key, label) if found
            else "root|%s|%s|%s" % (key, label, shown))
    named = label if found else shown

    text = conf.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    for index, existing in enumerate(lines):
        parts = [p.strip() for p in existing.strip().split("|")]
        form = parts[0] if parts else ""
        if form == "label" and len(parts) == 3 and parts[1] == key:
            pass
        elif form == "root" and len(parts) == 4 and parts[1] == key:
            # A row naming a directory outside this repository belongs to
            # something else, whatever it calls itself.
            if not _own_row(repo, parts[3]):
                return "dashboard: %s already names %s; left alone" % (key, parts[3])
        else:
            continue
        if existing.strip() == line:
            return "dashboard: already registered as %s" % key
        # Ours, and saying the wrong thing. Rewritten in place rather than
        # appended, because two rows for one key is the drift twice over.
        lines[index] = line + "\n"
        conf.write_text("".join(lines), encoding="utf-8")
        if form == "label":
            return "dashboard: relabelled %s -> %s" % (key, named)
        return "dashboard: moved %s off %s -> %s" % (key, parts[3], named)

    with conf.open("a", encoding="utf-8") as handle:
        if not text.endswith("\n"):
            handle.write("\n")
        handle.write(line + "\n")
    return "dashboard: registered %s -> %s" % (key, named)


def revision(repo: Path) -> str:
    """The commit the render was made from, or `unknown` outside a checkout.

    Through `sd_lib.git_output` rather than a subprocess call of its own:
    `tests/test_git_policy.py` allows one git policy in `bin/`, and a second
    would mean a second timeout and a second answer to what a failure means.
    """
    return git_output(["rev-parse", "HEAD"], repo) or "unknown"


def notion_target(
    raw: dict[str, Any], repo: Path
) -> tuple[dict[str, str] | None, str]:
    """One Notion designation resolved to a container, or what was missing.

    `team=True` is the only way a brief reaches the shared space; see
    `NOTION_SCOPES` for why that direction is the one that must be asked for.
    An explicit `space=` overrides the folder but never the scope: naming a
    folder says where inside a space, not which space.

    The container is carried as `space_id`, a Notion page id, and `resolve`
    says how it was arrived at. `id` is every configured default and any
    `space=` written as an id or a page URL; a rename cannot touch those.
    `name` is a `space=` written as a plain name, which no id can be derived
    from -- there the drain does look the folder up by name, and the contract
    makes an empty lookup a failure to report rather than a folder to create.

    A default also carries `subfolder`, the repo's own page under that folder,
    the way a Drive default carries `Briefs/<repo>`. An explicit `space=` does
    not: naming a container says where the document goes, and appending to
    what the user named would put it somewhere they did not ask for.

    A default with nothing configured returns no target and says so, naming
    the variable to set. Falling back would mirror the document into whichever
    page this file happened to name, which is another account's page on every
    machine but one. A setting that is not a page id is not configured: an
    operator who pasted a folder's name has not named a folder this can reach.
    """
    scope, setting, phrase = NOTION_SCOPES[bool(raw.get("team"))]
    named = str(raw.get("space", "")).strip()
    if named:
        override = notion_id(named)
        return {
            "destination": "notion",
            "scope": scope,
            "space_id": override,
            "resolve": "id" if override else "name",
            "space": "" if override else named,
            "subfolder": "",
            "page": str(raw.get("page", "")).strip(),
            "target": "the %s folder in your %s space" % (named, scope),
        }, ""

    configured = notion_id(str(ENVIRON.get(setting, "")))
    if not configured:
        return None, (
            "notion= has no %s folder configured: set %s to the Notion page "
            "id of that folder, or name one with space=" % (scope, setting)
        )
    return {
        "destination": "notion",
        "scope": scope,
        "space_id": configured,
        "resolve": "id",
        "space": "",
        "subfolder": repo.name,
        "page": str(raw.get("page", "")).strip(),
        "target": phrase % repo.name,
    }, ""


def mirror_targets(
    cfg: dict[str, Any], repo: Path
) -> tuple[list[dict[str, str]], list[str]]:
    """The outward destinations this DOCS entry designates, and what was wrong.

    A document publishes to the dashboard and to Obsidian whatever this
    returns; these are the copies that leave the machine. Nothing here infers a
    destination from a title, a path or a neighbour, and nothing promotes a
    document because it looks finished.

    Returns a list because a document may be designated for several places at
    once. `notion=` and `drive=` on one entry are two mirrors, not a choice.

    A designation that names no container gets its destination's default, and
    both defaults name the repo: `Briefs/<repo>` for Drive, and for Notion the
    repo's own page under the configured briefs folder. That is the shape the
    vault already uses, so a reader who knows where one brief is knows where
    all of them are, whichever copy they found first. Notion's default used to
    stop at the folder, which dropped every repo's briefs into one page
    alongside the per-repo pages already there.

    Problems are returned rather than raised, and returned *per destination*.
    A malformed designation is the user's to fix, and one bad key must not cost
    the other destination its request: the local copies are written either way,
    so withholding a valid mirror would punish the destination that was fine.
    """
    targets: list[dict[str, str]] = []
    problems: list[str] = []
    for dest in DESTINATIONS:
        raw = cfg.get(dest.name)
        if raw is None or raw is False:
            continue
        # `notion=dict()` is a designation, and an empty dict is falsy -- so
        # presence is what counts here, not truth. `notion=True` is the same
        # designation written shorter.
        if raw is True:
            raw = {}
        if not isinstance(raw, dict):
            problems.append(
                "%s= must be a dict, not %s" % (dest.name, type(raw).__name__)
            )
            continue
        if dest.name == "notion":
            target, problem = notion_target(raw, repo)
            if target is None:
                problems.append(problem)
            else:
                targets.append(target)
            continue
        # Notion returned above, so this is the destination whose default is
        # a path the drain resolves rather than a container it is handed.
        where = str(raw.get(dest.where, "")).strip() or dest.default % repo.name
        targets.append({
            "destination": dest.name,
            dest.where: where,
            dest.what: str(raw.get(dest.what, "")).strip(),
            # Worded here rather than by whoever reads the request. `sd-status`
            # prints this verbatim, so it never has to carry a second copy of
            # the destination table to say which place a row is waiting on.
            "target": "the %s %s" % (where, dest.noun),
        })
    return targets, problems


def vault_folder(repo: Path) -> Path | None:
    """`<vault>/Briefs/<repo>`, or None when no vault is configured.

    None rather than a raise: a machine with no vault still renders and still
    publishes to the dashboard, the same way one with no dashboard checkout
    does. The copy that is missing is reported by name.
    """
    if not VAULT:
        return None
    return Path(VAULT).expanduser() / BRIEFS / repo.name


def write_obsidian(repo: Path, docs: list[dict[str, Any]]) -> list[str]:
    """Write every document's Markdown into the vault, under its repo folder.

    Obsidian is where these documents live, so this is not a mirror of the
    published form -- it is the Markdown itself, carried across with a
    frontmatter block naming where it came from. Markdown and not HTML: the
    vault's whole value is that a note is editable and linkable, and an HTML
    blob in it is neither.

    A local filesystem write, so a render performs it rather than queueing it.
    Nothing here reaches the network and nothing needs a credential, which is
    what lets the primary copy be the one that never waits for a drain.
    """
    folder = vault_folder(repo)
    if folder is None:
        return ["obsidian: OBSIDIAN_VAULT is not set; no vault copy written"]

    rev = revision(repo)
    reports: list[str] = []
    written = 0
    for cfg in docs:
        src = str(cfg.get("src", "")).strip()
        out = str(cfg.get("out", "")).strip()
        if not src or not out:
            continue
        source = repo / src
        try:
            body = source.read_text(encoding="utf-8")
        except OSError as problem:
            reports.append("obsidian: cannot read %s (%s)" % (src, problem))
            continue
        # Frontmatter, not a prose header: Obsidian reads these as properties,
        # so the provenance is queryable in the vault rather than being a line
        # a reader has to notice. Written by this tool on every render, so it
        # is replaced wholesale and never merged with a hand-edited one --
        # which is also why the vault copy is not the place to edit.
        front = "\n".join([
            "---",
            "source_repo: %s" % repo.name,
            "source_path: %s" % src,
            "revision: %s" % rev,
            "rendered_by: sd-research-kit",
            "---",
            "",
        ])
        try:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / (out + ".md")).write_text(front + body, encoding="utf-8")
        except OSError as problem:
            reports.append("obsidian: cannot write %s.md (%s)" % (out, problem))
            continue
        written += 1
    if written:
        reports.append("obsidian: wrote %d document(s) to %s" % (written, folder))
    return reports


def ignore_dashboard(repo: Path) -> str:
    """Keep `docs/dashboard/` out of the repo's history, idempotently.

    The folder is a publication surface, regenerated on every commit. Tracking
    it would put a generated diff in front of a reader on every render, and the
    hook that re-renders after a commit would make the working tree dirty the
    moment it finished.
    """
    entry = "docs/dashboard/"
    path = repo / ".gitignore"
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as problem:
        return "gitignore: cannot read .gitignore (%s)" % problem
    if any(line.strip().rstrip("/") == entry.rstrip("/") for line in text.splitlines()):
        return "gitignore: docs/dashboard/ already ignored"
    try:
        with path.open("a", encoding="utf-8") as handle:
            if text and not text.endswith("\n"):
                handle.write("\n")
            handle.write("%s\n" % entry)
    except OSError as problem:
        return "gitignore: cannot write .gitignore (%s)" % problem
    return "gitignore: added docs/dashboard/"


def migrate_legacy_queue() -> list[str]:
    """Move any request left under the queue's former name into `QUEUE`.

    Migration rather than reading both for ever. Two directories mean every
    reader has to know both names, and a reader written later knows one -- the
    defect being closed here is exactly that. Moving once leaves one queue,
    and this function then finds nothing and says nothing on every later run.

    Nothing is created by looking. A machine that never used the old name has
    no legacy directory, and this neither makes one nor makes `QUEUE` to
    receive an empty migration.

    The emptied directory is left standing. Removing it would buy tidiness at
    the price of a new deletion path, and `tests/test_archive_untouched.py`
    enumerates and freezes every one under `bin/` precisely so that no new
    sweep appears for a reason that small. An empty directory strands nothing:
    the requests were what was stranded, and they have moved.

    The current queue wins a name collision. Both directories hold one request
    per document per destination under the same filename, and the rename is
    what stopped the old name being written -- so a file in `QUEUE` was
    written after its legacy twin, and keeping the older one would replace a
    current request with a stale revision.

    The requests move verbatim. An old request may predate a field a reader
    now expects; `bin/sd-status` already falls back for the one it reads, and
    rewriting somebody's queued work to a schema it was not written under is a
    worse answer than handing it over as it stands.
    """
    if not LEGACY_QUEUE.is_dir() or LEGACY_QUEUE == QUEUE:
        return []
    try:
        found = sorted(LEGACY_QUEUE.glob("*.json"))
    except OSError as problem:
        return ["mirror: cannot read %s (%s)" % (LEGACY_QUEUE, problem)]

    reports: list[str] = []
    moved = 0
    for path in found:
        target = QUEUE / path.name
        try:
            if target.exists():
                path.unlink()
                continue
            QUEUE.mkdir(parents=True, exist_ok=True)
            path.replace(target)
        except OSError as problem:
            reports.append(
                "mirror: cannot migrate %s (%s)" % (path.name, problem))
            continue
        moved += 1
    if moved:
        reports.append(
            "mirror: migrated %d request(s) from %s" % (moved, LEGACY_QUEUE))
    return reports


def recorded(path: Path, target: dict[str, str], what: str) -> str:
    """The page or file id a request already sitting at `path` records.

    The contract calls the request the durable record, and the drain's step 4
    is what makes it one: the id goes into the request the moment the
    destination returns it, before the designation is amended. A render
    between those two steps overwrote the request, and the id was then written
    nowhere -- so the next drain enqueued a create and left a second page
    carrying the same title. That is the duplicate steps 4 and 5 exist to
    prevent, arriving by the one route neither of them watches.

    So a render carries the recorded id forward. It never invents one: an
    absent, unreadable or half-written request records nothing, and the drain
    falls back to adopting by title, which is what it does for a page it has
    never seen.

    Carried only while the *container* still matches. A page id belongs to the
    folder it was created under, so a designation moved to another folder --
    or to the other Notion scope -- has made the recorded page the wrong one,
    and the drain must resolve the new container afresh. Every field of the
    target except the id itself is compared, which is the whole container and
    nothing about the document: a renamed document keeps its page, and a
    rename is exactly when the recorded id is the only thing that still finds
    it.
    """
    try:
        pending = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(pending, dict):
        return ""
    if any(pending.get(field) != value
           for field, value in target.items() if field != what):
        return ""
    return str(pending.get(what, "")).strip()


def enqueue(repo: Path, docs: list[dict[str, Any]]) -> list[str]:
    """Write one sync request per document per designated destination."""
    reports: list[str] = []
    wanted: list[tuple[dict[str, Any], dict[str, str]]] = []
    for cfg in docs:
        targets, problems = mirror_targets(cfg, repo)
        reports += ["mirror: %s in %s" % (p, cfg.get("out", "?")) for p in problems]
        wanted += [(cfg, target) for target in targets]
    if not wanted:
        return reports

    QUEUE.mkdir(parents=True, exist_ok=True)
    rev = revision(repo)
    key = repo_key(repo)
    vault = vault_folder(repo)
    for cfg, target in wanted:
        out = str(cfg.get("out", "")).strip()
        src = str(cfg.get("src", "")).strip()
        request = {
            "repo": str(repo),
            "revision": rev,
            "document": out,
            "title": cfg.get("title", out),
            "source": str(repo / src) if src else "",
            "rendered": str(repo / DASHBOARD_DIR / (out + ".html")),
            "markdown": str(vault / (out + ".md")) if vault else "",
        }
        request.update(target)
        path = QUEUE / ("%s.%s.%s.json" % (key, out or "doc", target["destination"]))
        # The designation is the answer where it gives one; the queue records
        # what a drain did, and never overrides what the document says.
        what = BY_NAME[target["destination"]].what
        carried = "" if request[what] else recorded(path, target, what)
        request[what] = request[what] or carried
        path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
        reports.append("mirror: queued %s -> %s%s" % (
            out, target["target"],
            ", updating the %s already recorded" % what if carried else ""))
    return reports


def publish(repo: Path, project: str, docs: list[dict[str, Any]]) -> list[str]:
    """Every job, in the order the contract states them.

    Local copies first, outward queue last. The order is the contract's: the
    copies that cannot leak are written before the ones that can, so a run that
    stops halfway has published locally and disclosed nothing.
    """
    reports = write_obsidian(repo, docs)
    reports.append(ignore_dashboard(repo))
    reports.append(register_root(repo, project or repo.name, repo / DASHBOARD_DIR))
    # Before enqueueing, and here rather than inside `enqueue`: a repo that
    # designates nothing still runs on the machine holding the stranded queue,
    # and `enqueue` returns before touching the directory when it has no
    # request of its own to write.
    reports += migrate_legacy_queue()
    reports += enqueue(repo, docs)
    return reports


#: The hook that keeps `build/` current, as text rather than as a file beside
#: the skill. Two rules put it here, both pinned by
#: `tests/test_no_shipped_shell.py`: `skills/` is the render surface and is
#: markdown only, because a file there is payload copied onto a platform home;
#: and the pack ships no shell outside `.github/scripts/`. So the hook is
#: Python, stdlib only, and it lives in the module that installs it. It carries
#: `#` comments rather than a docstring because it is itself inside one.
HOOK = '#!/usr/bin/env python3\n# Re-render this research repo after a commit that touched a document.\n#\n# Installed by `sd-research-kit init-hook`. Post-commit and not pre-commit:\n# `build/` is generated and not committed, so there is nothing to stage, and\n# the commit is the revision a queued mirror should name.\n#\n# Rendered output goes stale the moment its source changes, and a stale page is\n# worse than a missing one because it looks current. This is what keeps the\n# dashboard\'s Documents tab a statement about the render rather than about who\n# remembered to run it.\n#\n# Never fails the commit. The commit is already made when this runs, so exiting\n# non-zero would report a failure for work that succeeded. A render that cannot\n# run says so and leaves the commit alone.\n#\n# `SD_SKIP_RENDER=1 git commit` skips it.\n\nimport os\nimport shutil\nimport subprocess\nimport sys\n\n\ndef main():\n    if os.environ.get("SD_SKIP_RENDER"):\n        return 0\n    try:\n        root = subprocess.run(\n            ["git", "rev-parse", "--show-toplevel"],\n            capture_output=True, text=True, timeout=30, check=True,\n        ).stdout.strip()\n        if not os.path.isfile(os.path.join(root, "research.conf.py")):\n            return 0\n        # Only when the commit carried a document. A commit touching nothing\n        # but the config or a script still renders: both change the output.\n        changed = subprocess.run(\n            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],\n            cwd=root, capture_output=True, text=True, timeout=30, check=True,\n        ).stdout.split()\n    except (OSError, subprocess.SubprocessError):\n        return 0\n    if not any(name.endswith((".md", ".py")) for name in changed):\n        return 0\n\n    kit = shutil.which("sd-research-kit")\n    if kit is None:\n        print("post-commit: sd-research-kit not on PATH; build/ is now stale",\n              file=sys.stderr)\n        return 0\n    try:\n        subprocess.run([kit, "render"], cwd=root, timeout=600, check=True)\n    except (OSError, subprocess.SubprocessError):\n        print("post-commit: render failed; build/ is now stale", file=sys.stderr)\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'


def init_hook_main() -> int:
    """Install the post-commit re-render hook in this repo.

    Written and not symlinked: a research repo is not a worktree of the pack,
    and a symlink into a checkout the repo does not own breaks the moment the
    pack moves. A file already at the path is refused by name and left alone --
    the same rule `make hooks` follows for the pack's own hook.
    """
    repo = Path.cwd()
    if not (repo / "research.conf.py").is_file():
        print("no research.conf.py in %s" % repo, file=sys.stderr)
        return 2
    # The common directory, not `.git`: a linked worktree's hooks live in the
    # main checkout's, and installing into the worktree's own would give one
    # branch a hook every other branch does not have.
    common = git_output(["rev-parse", "--path-format=absolute", "--git-common-dir"], repo)
    if not common:
        print("not a git repository: %s" % repo, file=sys.stderr)
        return 1

    target = Path(common) / "hooks" / "post-commit"
    wanted = HOOK
    if target.exists():
        if target.read_text(encoding="utf-8", errors="replace") == wanted:
            print("hook: already installed at %s" % target)
            return 0
        print("error: %s exists and is not this hook; move it aside first" % target, file=sys.stderr)
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(wanted, encoding="utf-8")
    target.chmod(0o755)
    print("hook: installed %s" % target)
    return 0


def publish_main() -> int:
    """The `publish` verb. Named like `init_hook_main` and
    `sd_research_review.init_main`, not `main`: every `bin/` module carrying a
    `main` puts one more name the dead-code check cannot speak for into
    `tests/test_code_health.py`'s ambiguous set, and that ceiling is downward
    only.
    """
    repo = Path.cwd()
    conf = repo / "research.conf.py"
    if not conf.is_file():
        print("no research.conf.py in %s" % repo, file=sys.stderr)
        return 2
    ns: dict[str, Any] = {}
    # nosec B102 - same trust level as the render it mirrors; see sd_research_render.
    exec(compile(conf.read_text(encoding="utf-8"), str(conf), "exec"), ns)  # nosec B102
    project = ns.get("PROJECT", repo.name)
    for line in publish(repo, project, ns.get("DOCS", [])):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(publish_main())
