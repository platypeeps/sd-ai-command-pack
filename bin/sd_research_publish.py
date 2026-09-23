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
so a re-render overwrites the pending request rather than queueing a second --
and a re-render of an unchanged document writes nothing at all, pending or
drained, because a receipt beside the queue remembers what was last queued.

A request that is never drained stays on disk: the queue does not expire,
because an expiring queue reports a mirror as done that was never written.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from sd_lib import git_output, main_worktree_root

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

#: The environment the folder settings, `SD_MIRROR_REQUEUE` and
#: `SD_PUBLISH_FROM_WORKTREE` are read out of. A module attribute for the same
#: reason `QUEUE` and `VAULT` are: a test points it at a fixture rather than
#: at the machine running the test.
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


def repo_home(repo: Path) -> Path:
    """The checkout that names this repository: `repo`, unless it is a linked
    worktree, in which case the main checkout it was added from.

    Everything derived from a repository's *name* -- the dashboard key, the
    vault folder, a default Notion or Drive container, the queue filename --
    reads it from here and never from the directory the render ran in. A
    worktree is a scratch checkout with a scratch name, and a render from one
    called `tc-pins` wrote `label|tc-pins|TRACE-CLASSIFIER` into the
    dashboard's tracked `documents.conf` and a `Briefs/tc-pins/` folder into
    the vault, both naming a directory that would be gone within the day.

    The files a render reads and writes stay the worktree's own: what was
    rendered is that checkout's content, and the request carries its paths.
    Only the identity comes from the main checkout.
    """
    return main_worktree_root(repo)


def linked_worktree(repo: Path) -> bool:
    """Whether `repo` is a linked worktree of some other checkout."""
    return repo_home(repo).resolve() != Path(repo).resolve()


#: The switch that lets a linked worktree publish. On the invocation and
#: named for what it does, so an operator who sets it is asking, in words,
#: for branch content to become the canonical copy.
PUBLISH_FROM_WORKTREE = "SD_PUBLISH_FROM_WORKTREE"


def publish_refusal(repo: Path, copy: str) -> str:
    """Why this checkout may not publish `copy`, or `""` when it may.

    A linked worktree renders locally and publishes nothing by itself. The
    dashboard key and the vault folder are the *repository's*, which is what
    stopped a worktree called `tc-pins` registering itself -- but the same
    identity would let an unmerged branch overwrite the main checkout's
    pending request, inherit the page id a drain recorded for it, and put
    branch content into the shared vault folder as the canonical document.
    Publication is the main checkout's, and a worktree that wants it says so
    with `SD_PUBLISH_FROM_WORKTREE=1` on the invocation.
    """
    if not linked_worktree(repo) or ENVIRON.get(PUBLISH_FROM_WORKTREE):
        return ""
    return ("%s: not written from a linked worktree; run `sd-research-kit "
            "render` in %s, or set %s=1 to publish this branch's content"
            % (copy, repo_home(repo), PUBLISH_FROM_WORKTREE))


def repo_key(repo: Path) -> str:
    """A short lowercase key from the repository's directory name.

    Derived and not configured: a key the repo chose for itself could collide
    with another repo's, and the collision would surface as one repo's
    documents silently replacing the other's in the listing. The name is the
    main checkout's, whichever worktree is rendering; see `repo_home`.
    """
    stem = repo_home(repo).name.lower()
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
    return Path(VAULT).expanduser() / BRIEFS / repo_home(repo).name


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
    refused = publish_refusal(repo, "obsidian")
    if refused:
        return [refused]
    folder = vault_folder(repo)
    if folder is None:
        return ["obsidian: OBSIDIAN_VAULT is not set; no vault copy written"]

    rev = revision(repo)
    home = repo_home(repo)
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
            "source_repo: %s" % home.name,
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


def mirror_identity(
    request: dict[str, Any], target: dict[str, str], what: str
) -> dict[str, Any]:
    """What a recorded page or file id belongs to.

    The repository and the document, because the queue filename does not say
    either one: it is keyed on the repo's *basename*, so two checkouts both
    called `research` share a path, and both may designate a document called
    `report` into the same default folder. Adopting across that would hand one
    repository's brief the other's page and overwrite it on the next drain.

    Then the container the id was created under, taken from the target so that
    a destination added to `DESTINATIONS` carries its own container fields
    here without anything being remembered.

    Two fields of the target are left out. `what` is the id itself, which is
    what is being looked up. `target` is display text: a Notion folder written
    as a page URL and the same folder written as its bare id resolve to one
    `space_id` and differ only in the wording, and dropping a recorded id over
    a spelling is the duplicate this function exists to prevent. `revision`
    and `title` are not here either -- the revision changes on every render,
    and a renamed document keeps its page, which is exactly when the recorded
    id is the only thing that still finds it.
    """
    fields: dict[str, Any] = {
        field: request.get(field) for field in ("repo", "document")
    }
    fields.update({field: value for field, value in target.items()
                   if field not in (what, "target")})
    return fields


def recorded(path: Path, wanted: dict[str, Any], what: str) -> str:
    """The page or file id a request already sitting at `path` records.

    The contract calls the request the durable record, and the drain's step 4
    is what makes it one: the id goes into the request the moment the
    destination returns it, before the designation is amended. A render
    between those two steps overwrote the request, and the id was then written
    nowhere -- so the next drain enqueued a create and left a second page
    carrying the same title. That is the duplicate steps 4 and 5 exist to
    prevent, arriving by the one route neither of them watches.

    So a render carries the recorded id forward, while the request still names
    the same document in the same repository in the same container -- see
    `mirror_identity`. It never invents one: an absent, unreadable,
    half-written or differently-addressed request records nothing, and the
    drain falls back to adopting by title, which is what it does for a page it
    has never seen.
    """
    try:
        pending = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(pending, dict):
        return ""
    if any(pending.get(field) != value for field, value in wanted.items()):
        return ""
    return str(pending.get(what, "")).strip()


def receipts() -> Path:
    """Where the last-queued fingerprint of every request is kept.

    Beside the queue and not in it: `bin/sd-status` globs `*.json` in the
    queue, and a receipt inside it would read as one more pending mirror.
    Derived from `QUEUE` rather than configured separately, so a test or an
    operator who moves the queue moves the receipts with it and nothing here
    can write beside the machine's real queue by mistake. One file per
    request, under the request's own name, so two repositories rendering at
    once never contend for one file.
    """
    return QUEUE.with_name(QUEUE.name + "-receipts")


def queue_lock_path() -> Path:
    """The sidecar every writer of the queue takes, beside it.

    Beside the queue and not in it, for the reason `receipts()` gives; and
    created once, never removed, because unlinking it would let a writer
    that holds the lock be joined by one that creates a fresh inode and
    locks that instead.
    """
    return QUEUE.with_name(QUEUE.name + ".lock")


@contextlib.contextmanager
def queue_locked() -> Iterator[None]:
    """Hold the queue for one read-compare-write, against writers anywhere.

    A render's enqueue and a drain's acknowledgement are each a read, a
    comparison and a write of the same request file, and nothing serialised
    them: an acknowledgement read generation A, a render wrote B, and the
    acknowledgement's unlink then removed B with A on the receipt -- the
    request lost until somebody rendered again. Under one lock the render
    lands wholly before the acknowledgement's read, where the fingerprint
    comparison keeps it, or wholly after its unlink, where nothing is left to
    remove.

    Blocking, as `bin/sd-review-ack`'s lock is and for the same reason: the
    holder is a render or a drain's last step, nothing a session start waits
    on, and each holds it for one document's worth of work. An `OSError`
    here is the queue being unwritable, which is the caller's to report.
    """
    path = queue_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def mirror_fingerprint(request: dict[str, Any], target: dict[str, str], what: str) -> str:
    """What a drain would write, as one digest: the same digest means the
    same mirror.

    The request's `content`, because that is what the drain mirrors -- the
    Markdown as it stood at enqueue, stored in the request, and not the file
    at `source`, which may have changed by the time a drain reads it. With
    the path hashed instead: queued as A, edited to B before any drain, the
    drain read the path, published B and acknowledged A's fingerprint, and
    restoring A then read as delivered (`MUTABLE_SOURCE: remote=B, source=A,
    queue=False`). Hashing what the request stores keeps the fingerprint and
    the payload from disagreeing. Then the title, because it is what the
    mirror is called; the identity `mirror_identity` compares, because a
    document moved to another container is a new mirror; the designation's
    own page or file id, because a `page=` the user wrote is an instruction
    the drain has to see; and the source path, because the request carries
    it and the mirror's pointer line names it.

    Not the revision: a commit that touches nothing the mirror is made of
    still moves HEAD, and re-queueing on every commit is the defect this
    exists to close. Not a recorded id either: the drain writes one into the
    request after the fact, and it must not make the next render see a
    change.
    """
    named = mirror_identity(request, target, what)
    named.update(title=request.get("title", ""), source=request.get("source", ""),
                 designated=request.get(what, ""))
    digest = hashlib.sha256(json.dumps(named, sort_keys=True).encode("utf-8"))
    digest.update(str(request.get("content", "")).encode("utf-8"))
    return digest.hexdigest()


def source_text(path: Path) -> str:
    """The Markdown a request carries: the file's text as it stands now.

    Read once, at enqueue, and stored in the request, so the drain mirrors
    what was queued and not what the path holds when the drain gets to it.
    Decoded with replacement rather than refused: a stray byte in a brief is
    a brief with one odd character, not a brief that does not publish.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def load_record(path: Path) -> dict[str, Any]:
    """The object at `path`, or `{}` for anything that is not one.

    A missing file is the ordinary case -- no request queued, no receipt yet
    -- and is answered without raising; the `try` is for the file that is
    there and unreadable or not JSON.
    """
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def already_queued(path: Path, receipt: Path, wanted: str,
                   identity: dict[str, Any]) -> str:
    """`pending` when the request at `path` already asks for exactly this,
    `delivered` when nothing is pending and the destination already holds
    it, or `""` when the request must be written.

    The queue is read before the receipt, and a request that asks for a
    different generation is overwritten whatever the receipt says. The
    receipt describes the destination; the queue describes what the next
    drain will do to it, and a request left asking for something the source
    no longer says is a drain about to write it: deliver title A, queue the
    rename to B, revert to A before any drain ran -- with the receipt read
    first, A read as delivered and B stayed queued, and the next drain
    renamed the page the source called A. Overwriting costs one rewrite of a
    mirror that already matches; leaving it costs a wrong one.

    Two records, and neither is inferred from the other. `delivered` is what
    a drain wrote, recorded by `mirror_delivered()` at the moment it finished; the
    request's absence is not that record. A drain reads a request, writes
    the mirror, and deletes the file -- and a render that queued newer content
    between the read and the delete had its request deleted too, with nothing
    written for it. Treating the empty slot as "delivered" then suppressed
    that content for ever: remote A, source B, queue empty. So absence says
    nothing, and content the receipt does not name as delivered is queued.

    `pending` is read off the request itself, which carries its own
    fingerprint: a readable file naming the same identity and the same
    content is already asking for exactly this. A truncated or hand-edited
    file is not a request anyone will drain, and is rewritten.
    """
    if path.exists():
        pending = load_record(path)
        if pending.get("fingerprint") != wanted:
            return ""
        if any(pending.get(field) != value for field, value in identity.items()):
            return ""
        return "pending"
    if load_record(receipt).get("delivered") == wanted:
        return "delivered"
    return ""


def mirror_delivered(name: str, fingerprint: str) -> str:
    """Record that the drain wrote the generation `fingerprint` of request
    `name`, and remove the request only while it is still that generation.

    The drain's last step, replacing a hand deletion. Deleting the file
    acknowledged whatever it held at that moment, and after a render that
    ran during the drain that was content the drain had not written. This
    acknowledges the generation the drain read -- the `fingerprint` field
    of the request, as it stood in step 1 -- and leaves a newer request in
    place for the next drain.

    Returns a one-line report. Recording comes before removing: a receipt
    that says `delivered` with the request still present costs one skipped
    re-render at worst, while a removed request with nothing recorded is the
    defect this exists to close.

    The read, the comparison and the unlink happen under the queue lock. The
    comparison against a record read before the lock, or before the receipt
    write, is the window a render fits in: it wrote B after the read, and
    the unlink took B with A's fingerprint on the receipt.
    """
    try:
        with queue_locked():
            return acknowledge_request(name, fingerprint)
    except OSError as problem:
        return "delivered: cannot lock the queue at %s (%s); request left in place" % (
            queue_lock_path(), problem)


def acknowledge_request(name: str, fingerprint: str) -> str:
    """The acknowledgement itself, for a caller holding the queue lock.

    Read here, under the lock, and compared here: the record this reads is
    the one the unlink acts on, because nothing can write the file between
    the two while the lock is held.
    """
    path = QUEUE / name
    pending = load_record(path)
    if not pending:
        return "delivered: no readable request at %s" % path
    receipt = receipts() / name
    record = load_record(receipt)
    record.update(delivered=fingerprint)
    try:
        receipts().mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    except OSError as problem:
        return "delivered: cannot write receipt for %s (%s); request left in place" % (
            name, problem)
    if pending.get("fingerprint") != fingerprint:
        return ("delivered: recorded %s for %s; a newer request is pending and "
                "stays" % (fingerprint[:12], name))
    try:
        path.unlink()
    except OSError as problem:
        return "delivered: recorded %s for %s; cannot remove the request (%s)" % (
            fingerprint[:12], name, problem)
    return "delivered: recorded %s for %s; request removed" % (fingerprint[:12], name)


def delivered_main(argv: list[str]) -> int:
    """The `delivered` verb: `<request file name> <fingerprint>`.

    The one verb that takes arguments. R10-D6 forbids a *checkout* argument,
    because a command that can be pointed at a repository can act on one the
    caller is not standing in; this verb acts on the machine's one queue and
    names a request in it, which no working directory could resolve.
    """
    if len(argv) != 2 or not argv[0] or not argv[1]:
        print("usage: sd-research-kit delivered <request file name> <fingerprint>",
              file=sys.stderr)
        return 2
    name = Path(argv[0]).name
    print(mirror_delivered(name, argv[1]))
    return 0


def enqueue(repo: Path, docs: list[dict[str, Any]]) -> list[str]:
    """Write one sync request per document per designated destination, for
    every document whose mirror would differ from the one last queued.

    Unchanged documents are skipped, and said to be. Every render used to
    re-queue every designated document -- eight requests per commit in one
    repository -- and each drain then rewrote eight mirrors nobody had
    touched. `SD_MIRROR_REQUEUE=1` queues them all regardless, for a mirror
    that was lost on the far side and has to be written again.

    A linked worktree queues nothing unless `SD_PUBLISH_FROM_WORKTREE=1`
    says to; see `publish_refusal`.
    """
    reports: list[str] = []
    refused = publish_refusal(repo, "mirror")
    if refused:
        return [refused]
    home = repo_home(repo)
    wanted: list[tuple[dict[str, Any], dict[str, str]]] = []
    for cfg in docs:
        targets, problems = mirror_targets(cfg, home)
        reports += ["mirror: %s in %s" % (p, cfg.get("out", "?")) for p in problems]
        wanted += [(cfg, target) for target in targets]
    if not wanted:
        return reports

    QUEUE.mkdir(parents=True, exist_ok=True)
    rev = revision(repo)
    key = repo_key(home)
    vault = vault_folder(home)
    force = bool(ENVIRON.get("SD_MIRROR_REQUEUE"))
    with queue_locked():
        for cfg, target in wanted:
            out = str(cfg.get("out", "")).strip()
            src = str(cfg.get("src", "")).strip()
            request = {
                # The repository, not the checkout: this is what `sd-status`
                # resolves a row against and what a carried id is compared on.
                # The three paths below are the checkout's, because that is where
                # the rendered files are.
                "repo": str(home),
                "revision": rev,
                "document": out,
                "title": cfg.get("title", out),
                "source": str(repo / src) if src else "",
                "rendered": str(repo / DASHBOARD_DIR / (out + ".html")),
                "markdown": str(vault / (out + ".md")) if vault else "",
                # What the drain mirrors, read once here. The three paths
                # above say where it came from and where the copies sit;
                # none of them is what gets published.
                "content": source_text(repo / src) if src else "",
            }
            request.update(target)
            name = "%s.%s.%s.json" % (key, out or "doc", target["destination"])
            path = QUEUE / name
            what = BY_NAME[target["destination"]].what
            identity = mirror_identity(request, target, what)
            digest = mirror_fingerprint(request, target, what)
            state = "" if force else already_queued(path, receipts() / name, digest, identity)
            if state == "pending":
                reports.append("mirror: %s: already queued -> %s (unchanged since %s)"
                               % (out, target["target"], rev[:12]))
                continue
            if state == "delivered":
                reports.append("mirror: %s: unchanged since it was last mirrored; "
                               "not queued again" % out)
                continue
            # The designation is the answer where it gives one; the queue records
            # what a drain did, and never overrides what the document says.
            carried = "" if request[what] else recorded(path, identity, what)
            request[what] = request[what] or carried
            # The generation this request is: what `mirror_delivered()` acknowledges.
            request["fingerprint"] = digest
            path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
            try:
                receipts().mkdir(parents=True, exist_ok=True)
                record = load_record(receipts() / name)
                record.update(queued=digest, revision=rev, repo=str(home),
                              document=out, destination=target["destination"])
                record.pop("fingerprint", None)
                (receipts() / name).write_text(
                    json.dumps(record, indent=2) + "\n", encoding="utf-8")
            except OSError as problem:
                # The request is written; only the memory of it is not, and the
                # cost of that is one more queue of this document next time.
                reports.append("mirror: cannot write receipt for %s (%s)" % (out, problem))
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
    reports.append(register_root(
        repo, project or repo_home(repo).name, repo / DASHBOARD_DIR))
    # Before enqueueing, and here rather than inside `enqueue`: a repo that
    # designates nothing still runs on the machine holding the stranded queue,
    # and `enqueue` returns before touching the directory when it has no
    # request of its own to write.
    reports += migrate_legacy_queue()
    reports += enqueue(repo, docs)
    return reports


#: The git triggers the re-render hook installs under. A commit is not the only
#: way a document changes: a pull rewrites the working tree, a branch switch
#: replaces it outright, and `git checkout <rev> -- doc.md` rewrites one
#: document in place without moving HEAD at all. A `docs/dashboard/` left from
#: the old tree is the stale render this hook exists to prevent. One source under three
#: names, because three copies of one script drift; the script reads its own
#: `argv[0]` to know which trigger fired and how to ask git what moved.
HOOK_TRIGGERS = ("post-commit", "post-merge", "post-checkout")

#: The hook that keeps `docs/dashboard/` current, as text rather than a file beside
#: the skill. Two rules put it here, both pinned by
#: `tests/test_no_shipped_shell.py`: `skills/` is the render surface and is
#: markdown only, because a file there is payload copied onto a platform home;
#: and the pack ships no shell outside `.github/scripts/`. So the hook is
#: Python, stdlib only, and it lives in the module that installs it. It carries
#: `#` comments rather than docstrings because it is itself a string literal
#: here, and a `"""` inside one would end it.
HOOK = '''#!/usr/bin/env python3
# Re-render this research repo when git changes a document.
#
# Installed by `sd-research-kit init-hook` under three names at once:
# post-commit, post-merge and post-checkout. A pull, a branch switch and a
# checkout of one path change the documents as surely as a commit does, and
# a `docs/dashboard/` left from the old tree is the stale render this exists
# to prevent. Post-commit and not pre-commit: `docs/dashboard/` is generated
# and not committed, so there is nothing to stage, and the commit is the
# revision a queued mirror should name.
#
# One source, three names, and the trigger is read from `argv[0]`, because each
# one has to ask git a different question. `diff-tree ... HEAD` is
# commit-shaped: it prints nothing at all for a merge commit, and a checkout's
# HEAD says nothing about what the checkout moved. So a copy of the
# post-commit body under the other two names would never render.
#
# Rendered output goes stale the moment its source changes, and a stale page is
# worse than a missing one because it looks current. This is what keeps the
# dashboard's Documents tab a statement about the render rather than about who
# remembered to run it.
#
# Never fails the git command. The commit, the merge or the checkout is already
# made when this runs, so exiting non-zero would report a failure for work that
# succeeded. A render that cannot run says so and leaves git alone.
#
# `SD_SKIP_RENDER=1` skips it, for all three.

import os
import shutil
import subprocess
import sys

# What `diff_argv` answers for a trigger that renders without asking git
# anything. Not an empty list: "git named nothing" is a statement about the
# tree, and this is the refusal to make one.
ALWAYS = "always"


def diff_argv(trigger, argv):
    # The git command that names what this trigger moved; ALWAYS to render
    # without asking; None for an invocation that renders nothing. Three
    # answers and not two, because "ask git nothing" and "git answered
    # nothing" are different, and only the second is a statement about the
    # tree.
    if trigger == "post-commit":
        # Only when the commit carried a document. A commit touching nothing
        # but the config or a script still renders: both change the output.
        return ["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"]
    if trigger == "post-merge":
        # HEAD is the merge commit and `diff-tree` prints nothing for one, so
        # the post-commit question is unusable here. ORIG_HEAD is where this
        # branch stood before the merge, which is what the pull changed from.
        return ["diff", "--name-only", "ORIG_HEAD", "HEAD"]
    if trigger == "post-checkout":
        # git passes the previous HEAD, the new HEAD, and 1 for a branch
        # checkout or 0 for a file checkout.
        #
        # All zeros for the previous HEAD is a fresh clone or a
        # `git worktree add`: nothing is rendered there yet and nothing
        # has been committed to it, so a render would publish a checkout
        # nobody has worked in. Said here rather than left to the `git
        # diff 0000000 <new>` below failing into the caller's error arm:
        # that arm returns 0 for any failure of that command, so the day
        # something else throws in it a fresh clone stops rendering and
        # the test that pins this goes on passing.
        if len(argv) >= 2 and argv[1] and set(argv[1]) <= {"0"}:
            return None
        # A branch checkout has a range, and the range is the only thing
        # that names what it moved.
        if len(argv) >= 4 and argv[3] == "1" and argv[1] != argv[2]:
            return ["diff", "--name-only", argv[1], argv[2]]
        # Everything else this trigger fires for moved no branch, so its two
        # revisions are equal and there is no range -- and it renders anyway,
        # without a question, because there is no question worth asking here.
        #
        # Do not reintroduce `diff --name-only HEAD` as an optimisation. It
        # looks like the right guard and it is the wrong one: it asks whether
        # the tree differs from HEAD, and what a mirror needs to know is
        # whether the tree differs from what was published. Those agree only
        # while the published copy tracks HEAD, and a file checkout is exactly
        # what breaks that. `git checkout <rev> -- doc.md` publishes the older
        # text; `git checkout HEAD -- doc.md` then restores a clean tree, the
        # guard sees no diff, and the published copy keeps the reverted text
        # for good. Comparing against what was published instead would be a
        # second record of the same fact, which is the failure this contract
        # exists to close.
        #
        # So it renders on an unchanged tree too. That is the price, and it is
        # small: a render that finds nothing changed is cheap, and a mirror
        # holding text nobody can see is not.
        return ALWAYS
    # An unrecognised name is not this hook's trigger. Guessing would run a
    # render on a git event nobody installed it for.
    return None


def main(argv):
    if os.environ.get("SD_SKIP_RENDER"):
        return 0
    trigger = os.path.basename(argv[0]) if argv else ""
    query = diff_argv(trigger, argv)
    if query is None:
        return 0
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        if not os.path.isfile(os.path.join(root, "research.conf.py")):
            return 0
        if query != ALWAYS:
            changed = subprocess.run(
                ["git"] + query,
                cwd=root, capture_output=True, text=True, timeout=30, check=True,
            ).stdout.split()
            if not any(name.endswith((".md", ".py")) for name in changed):
                return 0
    except (OSError, subprocess.SubprocessError):
        return 0

    kit = shutil.which("sd-research-kit")
    if kit is None:
        print("%s: sd-research-kit not on PATH; docs/dashboard/ is now stale"
              % trigger, file=sys.stderr)
        return 0
    try:
        subprocess.run([kit, "render"], cwd=root, timeout=600, check=True)
    except (OSError, subprocess.SubprocessError):
        print("%s: render failed; docs/dashboard/ is now stale" % trigger,
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
'''

#: Every earlier body this module released, byte for byte, so that an
#: installation made by one of them can be recognised and replaced rather than
#: refused. Without this the fix above reaches nobody: every repository that
#: has the hook has one of these, `init-hook` would read it as somebody else's
#: file, and the only installations that could ever get three triggers are the
#: ones that do not exist yet.
#:
#: Exact bodies and not a "looks like ours" test, because the whole value of
#: refusing a foreign file is that the refusal cannot be talked out of. A
#: single byte that this pack did not write is still foreign and still refused.
#:
#: The list is the whole population, read out of this file's own history --
#: `git rev-list --all --full-history -- bin/sd_research_publish.py`, every
#: blob parsed for its `HOOK` assignment. Two bodies were released: the one
#: `05d4b9d3` shipped, and the one `fa5f5576` replaced it with and `47d4d147`
#: still carried. They differ in one comment word.
#:
#: The other two are this branch's own. A branch owns the predecessors it
#: creates: each of its commits is a revision somebody can check out and run
#: `init-hook` from, and each is history the moment the branch lands, so a
#: body left off here is an installation this verb refuses for the rest of its
#: life. "Released as of today" is the wrong reading and does not survive its
#: own criterion -- it is the reading that left `4d20574b`'s body off, and the
#: review that caught it ran the installer against the body of the very
#: revision it was reviewing. A body from a branch that has not landed belongs
#: to that branch, which adds it when it does -- and the fifth body below is
#: sd:1352's, added by the merge that brought that branch in. The rule is the
#: same one read from the other side: a merge inherits the predecessors of
#: what it merges, because those revisions are checkouts here too. The sixth
#: is this branch's merge commit's own body, superseded by the commit that
#: gave the hook `docs/dashboard/` and an explicit all-zeros guard.
#:
#: Measured rather than assumed, because "released" is the tempting reading
#: and it is not this one: `4d20574b` and `dd14d501` are in here and neither
#: ever reached `main`. What puts a body on a machine is a checkout, and an
#: ancestor commit is a checkout.
#:
#: Downward only in one direction: a body leaves this tuple when no machine can
#: still be carrying it, which is not a thing this repository can know. Assume
#: it never happens, and add to it whenever `HOOK` changes.
SUPERSEDED_HOOKS = (
    # `05d4b9d3`, the body the hook shipped with.
    '''#!/usr/bin/env python3
# Re-render this research repo after a commit that touched a document.
#
# Installed by `sd-research-kit init-hook`. Post-commit and not pre-commit:
# `build/` is generated and not committed, so there is nothing to stage, and
# the commit is the revision a queued Notion sync should name.
#
# Rendered output goes stale the moment its source changes, and a stale page is
# worse than a missing one because it looks current. This is what keeps the
# dashboard's Documents tab a statement about the render rather than about who
# remembered to run it.
#
# Never fails the commit. The commit is already made when this runs, so exiting
# non-zero would report a failure for work that succeeded. A render that cannot
# run says so and leaves the commit alone.
#
# `SD_SKIP_RENDER=1 git commit` skips it.

import os
import shutil
import subprocess
import sys


def main():
    if os.environ.get("SD_SKIP_RENDER"):
        return 0
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        if not os.path.isfile(os.path.join(root, "research.conf.py")):
            return 0
        # Only when the commit carried a document. A commit touching nothing
        # but the config or a script still renders: both change the output.
        changed = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=30, check=True,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return 0
    if not any(name.endswith((".md", ".py")) for name in changed):
        return 0

    kit = shutil.which("sd-research-kit")
    if kit is None:
        print("post-commit: sd-research-kit not on PATH; build/ is now stale",
              file=sys.stderr)
        return 0
    try:
        subprocess.run([kit, "render"], cwd=root, timeout=600, check=True)
    except (OSError, subprocess.SubprocessError):
        print("post-commit: render failed; build/ is now stale", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
''',
    # `fa5f5576`, one comment word later: the queue stopped being Notion's.
    '''#!/usr/bin/env python3
# Re-render this research repo after a commit that touched a document.
#
# Installed by `sd-research-kit init-hook`. Post-commit and not pre-commit:
# `build/` is generated and not committed, so there is nothing to stage, and
# the commit is the revision a queued mirror should name.
#
# Rendered output goes stale the moment its source changes, and a stale page is
# worse than a missing one because it looks current. This is what keeps the
# dashboard's Documents tab a statement about the render rather than about who
# remembered to run it.
#
# Never fails the commit. The commit is already made when this runs, so exiting
# non-zero would report a failure for work that succeeded. A render that cannot
# run says so and leaves the commit alone.
#
# `SD_SKIP_RENDER=1 git commit` skips it.

import os
import shutil
import subprocess
import sys


def main():
    if os.environ.get("SD_SKIP_RENDER"):
        return 0
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        if not os.path.isfile(os.path.join(root, "research.conf.py")):
            return 0
        # Only when the commit carried a document. A commit touching nothing
        # but the config or a script still renders: both change the output.
        changed = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=30, check=True,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return 0
    if not any(name.endswith((".md", ".py")) for name in changed):
        return 0

    kit = shutil.which("sd-research-kit")
    if kit is None:
        print("post-commit: sd-research-kit not on PATH; build/ is now stale",
              file=sys.stderr)
        return 0
    try:
        subprocess.run([kit, "render"], cwd=root, timeout=600, check=True)
    except (OSError, subprocess.SubprocessError):
        print("post-commit: render failed; build/ is now stale", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
''',
    # `4d20574b`, this branch: one source under three names, with the
    # trigger read from `argv[0]`.
    '''#!/usr/bin/env python3
# Re-render this research repo when git changes a document.
#
# Installed by `sd-research-kit init-hook` under three names at once:
# post-commit, post-merge and post-checkout. A pull and a branch switch change
# the documents as surely as a commit does, and a `build/` left from the old
# tree is the stale render this exists to prevent. Post-commit and not
# pre-commit: `build/` is generated and not committed, so there is nothing to
# stage, and the commit is the revision a queued mirror should name.
#
# One source, three names, and the trigger is read from `argv[0]`, because each
# one has to ask git a different question. `diff-tree ... HEAD` is
# commit-shaped: it prints nothing at all for a merge commit, and a checkout's
# HEAD says nothing about what the checkout moved. So a copy of the
# post-commit body under the other two names would never render.
#
# Rendered output goes stale the moment its source changes, and a stale page is
# worse than a missing one because it looks current. This is what keeps the
# dashboard's Documents tab a statement about the render rather than about who
# remembered to run it.
#
# Never fails the git command. The commit, the merge or the checkout is already
# made when this runs, so exiting non-zero would report a failure for work that
# succeeded. A render that cannot run says so and leaves git alone.
#
# `SD_SKIP_RENDER=1` skips it, for all three.

import os
import shutil
import subprocess
import sys


def diff_argv(trigger, argv):
    # The git command that names what this trigger moved, or None for an
    # invocation that renders nothing. None rather than an empty list: "ask
    # git nothing" and "git answered nothing" are different, and only the
    # second is a statement about the tree.
    if trigger == "post-commit":
        # Only when the commit carried a document. A commit touching nothing
        # but the config or a script still renders: both change the output.
        return ["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"]
    if trigger == "post-merge":
        # HEAD is the merge commit and `diff-tree` prints nothing for one, so
        # the post-commit question is unusable here. ORIG_HEAD is where this
        # branch stood before the merge, which is what the pull changed from.
        return ["diff", "--name-only", "ORIG_HEAD", "HEAD"]
    if trigger == "post-checkout":
        # git passes the previous HEAD, the new HEAD, and 1 for a branch
        # checkout or 0 for a file checkout. A file checkout restores paths
        # inside one tree and moves no branch, and `git checkout <current>`
        # moves nothing at all; neither can have changed a document.
        if len(argv) < 4 or argv[3] != "1" or argv[1] == argv[2]:
            return None
        return ["diff", "--name-only", argv[1], argv[2]]
    # An unrecognised name is not this hook's trigger. Guessing would run a
    # render on a git event nobody installed it for.
    return None


def main(argv):
    if os.environ.get("SD_SKIP_RENDER"):
        return 0
    trigger = os.path.basename(argv[0]) if argv else ""
    query = diff_argv(trigger, argv)
    if query is None:
        return 0
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        if not os.path.isfile(os.path.join(root, "research.conf.py")):
            return 0
        changed = subprocess.run(
            ["git"] + query,
            cwd=root, capture_output=True, text=True, timeout=30, check=True,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return 0
    if not any(name.endswith((".md", ".py")) for name in changed):
        return 0

    kit = shutil.which("sd-research-kit")
    if kit is None:
        print("%s: sd-research-kit not on PATH; build/ is now stale" % trigger,
              file=sys.stderr)
        return 0
    try:
        subprocess.run([kit, "render"], cwd=root, timeout=600, check=True)
    except (OSError, subprocess.SubprocessError):
        print("%s: render failed; build/ is now stale" % trigger, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
''',
    # `dd14d501`, this branch: a file checkout measured against the
    # working tree, which `8b575695` replaced with an unconditional
    # render.
    '''#!/usr/bin/env python3
# Re-render this research repo when git changes a document.
#
# Installed by `sd-research-kit init-hook` under three names at once:
# post-commit, post-merge and post-checkout. A pull, a branch switch and a
# checkout of one path change the documents as surely as a commit does, and a
# `build/` left from the old tree is the stale render this exists to prevent.
# Post-commit and not pre-commit: `build/` is generated and not committed, so
# there is nothing to stage, and the commit is the revision a queued mirror
# should name.
#
# One source, three names, and the trigger is read from `argv[0]`, because each
# one has to ask git a different question. `diff-tree ... HEAD` is
# commit-shaped: it prints nothing at all for a merge commit, and a checkout's
# HEAD says nothing about what the checkout moved. So a copy of the
# post-commit body under the other two names would never render.
#
# Rendered output goes stale the moment its source changes, and a stale page is
# worse than a missing one because it looks current. This is what keeps the
# dashboard's Documents tab a statement about the render rather than about who
# remembered to run it.
#
# Never fails the git command. The commit, the merge or the checkout is already
# made when this runs, so exiting non-zero would report a failure for work that
# succeeded. A render that cannot run says so and leaves git alone.
#
# `SD_SKIP_RENDER=1` skips it, for all three.

import os
import shutil
import subprocess
import sys


def diff_argv(trigger, argv):
    # The git command that names what this trigger moved, or None for an
    # invocation that renders nothing. None rather than an empty list: "ask
    # git nothing" and "git answered nothing" are different, and only the
    # second is a statement about the tree.
    if trigger == "post-commit":
        # Only when the commit carried a document. A commit touching nothing
        # but the config or a script still renders: both change the output.
        return ["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"]
    if trigger == "post-merge":
        # HEAD is the merge commit and `diff-tree` prints nothing for one, so
        # the post-commit question is unusable here. ORIG_HEAD is where this
        # branch stood before the merge, which is what the pull changed from.
        return ["diff", "--name-only", "ORIG_HEAD", "HEAD"]
    if trigger == "post-checkout":
        # git passes the previous HEAD, the new HEAD, and 1 for a branch
        # checkout or 0 for a file checkout. A branch checkout has a range,
        # and the range is the only thing that names what it moved.
        if len(argv) >= 4 and argv[3] == "1" and argv[1] != argv[2]:
            return ["diff", "--name-only", argv[1], argv[2]]
        # Everything else this trigger fires for moved no branch, so its two
        # revisions are equal and there is no range to ask about --  but
        # `git checkout <rev> -- doc.md` replaces a document's contents all
        # the same, which is exactly the render this hook exists for. The
        # honest question is then the working tree against HEAD, which names
        # what the checkout just wrote. It also names unrelated uncommitted
        # edits, so this renders slightly more often than it must; a render
        # that finds nothing changed is cheap, and a mirror that silently
        # keeps the superseded text is not.
        return ["diff", "--name-only", "HEAD"]
    # An unrecognised name is not this hook's trigger. Guessing would run a
    # render on a git event nobody installed it for.
    return None


def main(argv):
    if os.environ.get("SD_SKIP_RENDER"):
        return 0
    trigger = os.path.basename(argv[0]) if argv else ""
    query = diff_argv(trigger, argv)
    if query is None:
        return 0
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        if not os.path.isfile(os.path.join(root, "research.conf.py")):
            return 0
        changed = subprocess.run(
            ["git"] + query,
            cwd=root, capture_output=True, text=True, timeout=30, check=True,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return 0
    if not any(name.endswith((".md", ".py")) for name in changed):
        return 0

    kit = shutil.which("sd-research-kit")
    if kit is None:
        print("%s: sd-research-kit not on PATH; build/ is now stale" % trigger,
              file=sys.stderr)
        return 0
    try:
        subprocess.run([kit, "render"], cwd=root, timeout=600, check=True)
    except (OSError, subprocess.SubprocessError):
        print("%s: render failed; build/ is now stale" % trigger, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
''',
    # `e65d1ec4`, sd:1352's `rewrite/research-publish-loop`, which this
    # branch merges: the same three triggers reached independently, with
    # `HOOK_NAMES` for the tuple and an upgrade keyed on a marker line.
    # Its resolution of a file checkout -- render nothing -- is the one
    # this branch replaces, and its shape is gone from the merged tree;
    # the body stays, because those revisions are now ancestors here and
    # a checkout of any of them can install it. A branch owns the
    # predecessors it creates, and a merge inherits the other branch's.
    '''#!/usr/bin/env python3
# Re-render this research repo after git changes a document in it.
#
# Installed by `sd-research-kit init-hook` as post-commit, post-merge and
# post-checkout: one file under three names, and the name git called it by
# says what to compare. A commit is compared with its parent; a merge -- and
# so a pull, which is a fetch and a merge -- compares ORIG_HEAD with HEAD; a
# branch checkout compares the two revisions git hands it. Post-commit alone
# missed every pulled change, and the page then went stale while looking
# current, until a review demanded a render nobody had been told to run.
#
# After the fact and not before: `docs/dashboard/` is generated and not
# committed, so there is nothing to stage, and the new HEAD is the revision a
# queued mirror should name.
#
# Rendered output goes stale the moment its source changes, and a stale page is
# worse than a missing one because it looks current. This is what keeps the
# dashboard's Documents tab a statement about the render rather than about who
# remembered to run it.
#
# Never fails the git command. It is already done when this runs, so exiting
# non-zero would report a failure for work that succeeded. A render that cannot
# run says so and leaves the repository alone.
#
# `SD_SKIP_RENDER=1 git commit` (or pull, or checkout) skips it.

import os
import shutil
import subprocess
import sys


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        timeout=30, check=True,
    ).stdout.split()


def changed(root, hook, args):
    # The paths this git command changed. Every branch here compares two
    # revisions, so an uncommitted edit is never what triggers a render.
    if hook == "post-commit":
        return git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    if hook == "post-merge":
        return git(root, "diff", "--name-only", "ORIG_HEAD", "HEAD")
    if hook == "post-checkout":
        # <previous HEAD> <new HEAD> <1 for a branch checkout, 0 for a file>.
        # A file checkout moves no ref, so there is nothing to compare; and a
        # previous HEAD of all zeros is a fresh clone or `git worktree add`,
        # which has nothing rendered yet and nothing committed to it, so a
        # render there would publish a checkout nobody has worked in.
        if len(args) < 3 or args[2] != "1" or args[0] == args[1]:
            return []
        if set(args[0]) <= {"0"}:
            return []
        return git(root, "diff", "--name-only", args[0], args[1])
    return []


def main(argv):
    if os.environ.get("SD_SKIP_RENDER"):
        return 0
    hook = os.path.basename(argv[0]) if argv else "post-commit"
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        if not os.path.isfile(os.path.join(root, "research.conf.py")):
            return 0
        # Only when a document moved. A change touching nothing but the
        # config or a script still renders: both change the output.
        paths = changed(root, hook, argv[1:])
    except (OSError, subprocess.SubprocessError):
        return 0
    if not any(name.endswith((".md", ".py")) for name in paths):
        return 0

    kit = shutil.which("sd-research-kit")
    if kit is None:
        print("%s: sd-research-kit not on PATH; docs/dashboard/ is now stale"
              % hook, file=sys.stderr)
        return 0
    try:
        subprocess.run([kit, "render"], cwd=root, timeout=600, check=True)
    except (OSError, subprocess.SubprocessError):
        print("%s: render failed; docs/dashboard/ is now stale" % hook,
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
''',
    # This branch's merge of sd:1352, as it stood before the commit that
    # added the body above: `build/` still in its comments and its two
    # stderr lines, and an all-zeros previous HEAD left to the error arm.
    # One commit changed both, so one body is superseded rather than two.
    '''#!/usr/bin/env python3
# Re-render this research repo when git changes a document.
#
# Installed by `sd-research-kit init-hook` under three names at once:
# post-commit, post-merge and post-checkout. A pull, a branch switch and a
# checkout of one path change the documents as surely as a commit does, and a
# `build/` left from the old tree is the stale render this exists to prevent.
# Post-commit and not pre-commit: `build/` is generated and not committed, so
# there is nothing to stage, and the commit is the revision a queued mirror
# should name.
#
# One source, three names, and the trigger is read from `argv[0]`, because each
# one has to ask git a different question. `diff-tree ... HEAD` is
# commit-shaped: it prints nothing at all for a merge commit, and a checkout's
# HEAD says nothing about what the checkout moved. So a copy of the
# post-commit body under the other two names would never render.
#
# Rendered output goes stale the moment its source changes, and a stale page is
# worse than a missing one because it looks current. This is what keeps the
# dashboard's Documents tab a statement about the render rather than about who
# remembered to run it.
#
# Never fails the git command. The commit, the merge or the checkout is already
# made when this runs, so exiting non-zero would report a failure for work that
# succeeded. A render that cannot run says so and leaves git alone.
#
# `SD_SKIP_RENDER=1` skips it, for all three.

import os
import shutil
import subprocess
import sys

# What `diff_argv` answers for a trigger that renders without asking git
# anything. Not an empty list: "git named nothing" is a statement about the
# tree, and this is the refusal to make one.
ALWAYS = "always"


def diff_argv(trigger, argv):
    # The git command that names what this trigger moved; ALWAYS to render
    # without asking; None for an invocation that renders nothing. Three
    # answers and not two, because "ask git nothing" and "git answered
    # nothing" are different, and only the second is a statement about the
    # tree.
    if trigger == "post-commit":
        # Only when the commit carried a document. A commit touching nothing
        # but the config or a script still renders: both change the output.
        return ["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"]
    if trigger == "post-merge":
        # HEAD is the merge commit and `diff-tree` prints nothing for one, so
        # the post-commit question is unusable here. ORIG_HEAD is where this
        # branch stood before the merge, which is what the pull changed from.
        return ["diff", "--name-only", "ORIG_HEAD", "HEAD"]
    if trigger == "post-checkout":
        # git passes the previous HEAD, the new HEAD, and 1 for a branch
        # checkout or 0 for a file checkout. A branch checkout has a range,
        # and the range is the only thing that names what it moved.
        if len(argv) >= 4 and argv[3] == "1" and argv[1] != argv[2]:
            return ["diff", "--name-only", argv[1], argv[2]]
        # Everything else this trigger fires for moved no branch, so its two
        # revisions are equal and there is no range -- and it renders anyway,
        # without a question, because there is no question worth asking here.
        #
        # Do not reintroduce `diff --name-only HEAD` as an optimisation. It
        # looks like the right guard and it is the wrong one: it asks whether
        # the tree differs from HEAD, and what a mirror needs to know is
        # whether the tree differs from what was published. Those agree only
        # while the published copy tracks HEAD, and a file checkout is exactly
        # what breaks that. `git checkout <rev> -- doc.md` publishes the older
        # text; `git checkout HEAD -- doc.md` then restores a clean tree, the
        # guard sees no diff, and the published copy keeps the reverted text
        # for good. Comparing against what was published instead would be a
        # second record of the same fact, which is the failure this contract
        # exists to close.
        #
        # So it renders on an unchanged tree too. That is the price, and it is
        # small: a render that finds nothing changed is cheap, and a mirror
        # holding text nobody can see is not.
        return ALWAYS
    # An unrecognised name is not this hook's trigger. Guessing would run a
    # render on a git event nobody installed it for.
    return None


def main(argv):
    if os.environ.get("SD_SKIP_RENDER"):
        return 0
    trigger = os.path.basename(argv[0]) if argv else ""
    query = diff_argv(trigger, argv)
    if query is None:
        return 0
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        if not os.path.isfile(os.path.join(root, "research.conf.py")):
            return 0
        if query != ALWAYS:
            changed = subprocess.run(
                ["git"] + query,
                cwd=root, capture_output=True, text=True, timeout=30, check=True,
            ).stdout.split()
            if not any(name.endswith((".md", ".py")) for name in changed):
                return 0
    except (OSError, subprocess.SubprocessError):
        return 0

    kit = shutil.which("sd-research-kit")
    if kit is None:
        print("%s: sd-research-kit not on PATH; build/ is now stale" % trigger,
              file=sys.stderr)
        return 0
    try:
        subprocess.run([kit, "render"], cwd=root, timeout=600, check=True)
    except (OSError, subprocess.SubprocessError):
        print("%s: render failed; build/ is now stale" % trigger, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
''',
)


def init_hook_main() -> int:
    """Install the re-render hook in this repo, under every trigger at once.

    Written and not symlinked: a research repo is not a worktree of the pack,
    and a symlink into a checkout the repo does not own breaks the moment the
    pack moves. A file already at one of the paths is refused by name and left
    alone -- the same rule `make hooks` follows for the pack's own hook --
    unless it is byte-for-byte a body this pack released, in which case it is
    this hook and is replaced. Every existing installation is an older body on
    `post-commit` alone; without that reading, the one verb that upgrades them
    would refuse every repository that already has the hook and serve only the
    ones that do not exist yet.

    All or nothing. Every target is inspected before any is written, so a
    refusal leaves the repository exactly as it found it. A repo installed on
    one trigger and not the others renders on a commit and silently not on a
    pull, which is worse than no hook at all: `docs/dashboard/` then looks
    maintained.
    A partial install from an earlier run is completed rather than refused.
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

    targets = [Path(common) / "hooks" / name for name in HOOK_TRIGGERS]
    held = {t: t.read_text(encoding="utf-8", errors="replace")
            for t in targets if t.exists()}
    ours = (HOOK,) + SUPERSEDED_HOOKS
    foreign = [t for t, text in held.items() if text not in ours]
    if foreign:
        for target in foreign:
            print("error: %s exists and is not this hook; move it aside first"
                  % target, file=sys.stderr)
        return 1
    write = [t for t in targets if held.get(t) != HOOK]
    if not write:
        print("hook: already installed at %s"
              % ", ".join(str(t) for t in targets))
        return 0
    for target in write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(HOOK, encoding="utf-8")
        target.chmod(0o755)
        print("hook: %s %s"
              % ("upgraded" if target in held else "installed", target))
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
