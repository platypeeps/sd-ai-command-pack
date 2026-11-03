"""Studio (sd:6920, sd:6921; slices 2 and 3 of sd:6919): creative projects, each a folder with a `project.json`.

The shape is `docs/work/2026-10-31-studio/design.md`. Slice 2 reads and serves; slice 3 moves a project's stage on its
sd item and pins or hides a file. Nothing else here writes.

**Which projects.** Every `project.json` in a registered repository that sits under `REPO_ROOT`, found by a walk a few
folders deep that skips dot folders and build output. The page names no repository: a machine with no `project.json`
shows an empty list, but a folder the walk cannot list, or a `REPO_ROOT` that does not resolve, is a problem the page
shows first (sd:7151), not an empty list. A repository's key is its folder name; two registered repositories with one name share no key,
so neither is served and the document names the contest, as Documents does.

**What a project says.** `kind` (`shirt`, `song`, `episode`; a file with no `kind` is another tool's), `title`, `brief`, `item` (`sd:<n>`) and `roots`, a map
from a role (`reference`, `candidates`, ...) to a folder relative to the project's. A file that does not parse lists
with its error; a root that leaves the project folder, or names an unknown role, is dropped with its reason.

**The gallery.** Each root's files, listed from disk (the media is untracked: git is never asked), served at
`/studio/files/<repo key>/<path in the repository>` by `designs.resolve`'s rules with `TYPES` here: every segment a
name, the resolved file inside the repository, and inside a root a project names now. A symlink out is a 404. Each
file answers under `POLICY`, a sandbox, so an opened SVG runs nothing.

**Seeking.** `.mp4`, `.mp3` and `.wav` answer `Range: bytes=` with 206 and `Content-Range` (`byte_range`): past the end
is 416, and a header that does not parse, or asks for several ranges, gets the whole file (200).

**The stage.** The item a project names holds its stage, as a Writing piece's does: `STAGES` is each kind's strip, and
`move_stage` moves the item one step along it, at the revision the page read, with a note. A stale revision is a 409
(`StaleItem`); a stage that is not the next one is a 400; neither writes. The page posts `/api/items/<n>/stage`, the
route Writing and Watches post; `server.action_route` sends an item that is no writing piece and that one project names
here. An item at a stage off its strip is refused, so a move never overwrites another tool's stage.

**Pin and hide.** Documents' view state (`writes.set_view`), keyed `studio/<repo key>/<path in the repository>`: a
rejected candidate hides without a delete. `view_request` refuses a file the gallery does not serve. A view store that
does not read pins and hides nothing, and `store.reason` says why.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import designs

#: The tree the projects sit under; the collectors and the Documents scan read the same variable.
REPO_ROOT_DEFAULT = "~/repos"

#: The file that makes a folder a project.
PROJECT = "project.json"

KINDS = ("shirt", "song", "episode")
ROLES = ("reference", "candidates", "selected", "print", "stickers", "previews", "media")

#: The media the gallery serves, each with its type. Anything else is a 404: no page, script or Markdown.
TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}

#: The types a player seeks in, so they answer a Range.
RANGED = (".mp4", ".mp3", ".wav")

#: The most one 206 carries; an open range (`bytes=0-`) gets this much and its Content-Range says so.
CHUNK = 8 * 1024 * 1024

#: How deep below a repository the walk looks for `project.json`, and the folders it never enters.
DEPTH = 4
SKIP = frozenset({"node_modules", "target", "venv", "dist", "build", "__pycache__"})

#: The most files one root lists; `cut` says when it holds more.
FILES = 500

#: A served file's policy, replacing the dashboard's for that response: nothing runs, nothing loads but itself.
POLICY = "sandbox; default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'"

#: The file route's prefix.
FILES_PREFIX = "/studio/files/"

#: Each kind's stage strip, in order (the design's table). A project's item moves one stage at a time along it.
STAGES = {
    "shirt": ("brief", "candidates", "selected", "print_export", "approved", "ordered"),
    "song": ("lyrics", "suno", "selections", "film", "delivered"),
    "episode": ("idea", "outlined", "scripted", "in_production", "published"),
}

#: The first segment of a studio file's view key, so it shares no key with a Documents root.
VIEW_ROOT = "studio"


def _repo_root(repo_root: Path | None = None) -> Path:
    return Path(repo_root if repo_root is not None else os.environ.get("REPO_ROOT", REPO_ROOT_DEFAULT)).expanduser()


def repositories(connection, repo_root: Path | None = None) -> tuple[dict[str, Path], list[str]]:
    """(key -> checkout) for each registered repository under `REPO_ROOT`, and the problems: a `REPO_ROOT` that does not
    resolve, or a contested key."""
    from sd_db import repos

    try:
        base = _repo_root(repo_root).resolve(strict=True)
    except (OSError, RuntimeError) as problem:
        return {}, [f"REPO_ROOT {_repo_root(repo_root)} does not resolve: {problem}"]
    found: dict[str, list[Path]] = {}
    for row in repos.registered(connection):
        path = Path(str(row["path"])).expanduser()
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved == base or not resolved.is_relative_to(base) or not resolved.is_dir():
            continue
        if designs.SEGMENT.fullmatch(resolved.name):
            found.setdefault(resolved.name, []).append(resolved)
    keys = {key: paths[0] for key, paths in found.items() if len(set(paths)) == 1}
    problems = [f"Two registered repositories are named {key}: neither is served." for key, paths in sorted(found.items())
                if len(set(paths)) > 1]
    return dict(sorted(keys.items())), problems


def _project_files(checkout: Path) -> tuple[list[Path], list[OSError]]:
    """Every `project.json` within `DEPTH` folders of the checkout, in path order, and each folder the walk could not
    list (sd:7151: os.walk skips one silently, which read as no project there); dot folders and build output skipped."""
    out, unread = [], []
    for current, folders, files in os.walk(checkout, onerror=unread.append):
        depth = len(Path(current).relative_to(checkout).parts)
        folders[:] = sorted(f for f in folders if designs.SEGMENT.fullmatch(f) and f not in SKIP) if depth < DEPTH else []
        if PROJECT in files:
            out.append(Path(current) / PROJECT)
    return sorted(out), unread


def _files(checkout: Path, root: Path) -> tuple[list[dict], bool]:
    """A root's servable files, as the gallery links them, and whether the list was cut at `FILES`."""
    out, cut = [], False
    for current, folders, names in os.walk(root):
        folders[:] = sorted(f for f in folders if designs.SEGMENT.fullmatch(f))
        for name in sorted(names):
            relative = (Path(current) / name).relative_to(checkout).as_posix()
            found = designs.resolve(relative, checkout, TYPES)
            if found is None or not found[0].is_relative_to(root):
                continue
            if len(out) >= FILES:
                return out, True
            target, kind = found
            try:
                size = target.stat().st_size
            except OSError:
                continue
            out.append({"path": relative, "name": name, "bytes": size, "type": kind.split("/")[0], "ranged": target.suffix.lower() in RANGED})
    return out, cut


def _project(key: str, checkout: Path, manifest: Path, *, listing: bool = True) -> dict | None:
    """One project as the page reads it: its facts, its roots with their files, and what was wrong with it.

    None for a `project.json` that parses to an object with no `kind`: another tool's file of that name (a test
    fixture, a build config) is not a Studio project, and listing it as a problem would be noise. `listing` false
    leaves each root's files out, for `located`, which needs only the roots.
    """
    folder = manifest.parent
    relative = folder.relative_to(checkout).as_posix()
    entry = {"id": key if relative == "." else f"{key}/{relative}", "repo": key, "folder": relative, "kind": "", "title": folder.name, "brief": "", "item": None,
             "roots": [], "problems": [], "error": ""}
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as problem:
        entry["error"] = f"{PROJECT} does not parse: {problem}"
        return entry
    if not isinstance(data, dict):
        entry["error"] = f"{PROJECT} is not an object"
        return entry
    if "kind" not in data:
        return None
    kind = data.get("kind")
    if kind not in KINDS:
        entry["problems"].append(f"kind {kind!r} is not one of {', '.join(KINDS)}")
    else:
        entry["kind"] = kind
    for name in ("title", "brief"):
        if isinstance(data.get(name), str) and data[name].strip():
            entry[name] = data[name].strip()
    item = data.get("item")
    if isinstance(item, str) and re.fullmatch(r"sd:[1-9][0-9]{0,18}", item):
        entry["item"] = int(item[3:])
    elif item is not None:
        entry["problems"].append(f"item {item!r} is not sd:<n>")
    roots = data.get("roots", {})
    if not isinstance(roots, dict):
        entry["problems"].append("roots is not a map of role to folder")
        roots = {}
    try:
        base = folder.resolve(strict=True)
    except (OSError, RuntimeError) as problem:
        entry["error"] = f"the project folder does not resolve: {problem}"
        return entry
    for role, value in roots.items():
        if role not in ROLES:
            entry["problems"].append(f"root {role!r} is not a role: {', '.join(ROLES)}")
            continue
        segments = value.split("/") if isinstance(value, str) else []
        if not segments or not all(designs.SEGMENT.fullmatch(s) for s in segments):
            entry["problems"].append(f"root {role} {value!r} is not a folder name inside the project")
            continue
        try:
            target = base.joinpath(*segments).resolve(strict=True)
        except (OSError, RuntimeError):
            entry["problems"].append(f"root {role} {value} does not exist")
            continue
        if not target.is_relative_to(base) or not target.is_dir():
            entry["problems"].append(f"root {role} {value} leaves the project folder")
            continue
        files, cut = _files(checkout, target) if listing else ([], False)
        entry["roots"].append({"role": role, "path": value, "files": files, "cut": cut})
    entry["roots"].sort(key=lambda r: ROLES.index(r["role"]))
    return entry


def projects(connection, repo_root: Path | None = None, *, listing: bool = True) -> tuple[list[dict], list[str]]:
    """Every project under `REPO_ROOT`, by repository then folder, and the scan's own problems; `listing` false leaves
    each root's files out."""
    keys, problems = repositories(connection, repo_root)
    found = []
    for key, checkout in keys.items():
        manifests, unread = _project_files(checkout)
        for problem in unread:
            folder = Path(problem.filename or checkout).relative_to(checkout, walk_up=True).as_posix()
            problems.append(f"{key}{'' if folder == '.' else ': ' + folder} could not be read: {problem.strerror or problem}")
        found.extend(entry for entry in (_project(key, checkout, manifest, listing=listing) for manifest in manifests)
                     if entry is not None)
    return found, problems


def document(connection, *, now: str = "", repo_root: Path | None = None) -> dict:
    """`/api/studio`: the projects, each with its roots' files, and `attention`, the projects that list an error."""
    from .documents_screen import views
    from .v2.pages import attention

    found, problems = projects(connection, repo_root)
    kept, unread = views(connection)
    for entry in found:
        _stage(connection, entry)
        for root in entry["roots"]:
            for file in root["files"]:
                state = kept.get(view_key(f"{entry['repo']}/{file['path']}"), {})
                file["pinned"], file["hidden"] = bool(state.get("pinned")), bool(state.get("hidden"))
    return {
        "read": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(_repo_root(repo_root)), "projects": found, "problems": problems,
        "store": {"available": not unread, "reason": unread},
        "attention": attention(("caution" if p["error"] or p["problems"] else "ok" for p in found),
                               {"caution": "projects whose project.json lists a problem"}),
    }


def view_key(file: str) -> str:
    """The view key of `/studio/files/<file>`: `studio/<repo key>/<path in the repository>`."""
    return f"{VIEW_ROOT}/{file}"


def next_stage(kind: str, current: str | None) -> str | None:
    """The stage after `current` on the kind's strip: the first for an item with none, None at the end or off the strip."""
    strip = STAGES[kind]
    if not current:
        return strip[0]
    if current not in strip:
        return None
    at = strip.index(current) + 1
    return strip[at] if at < len(strip) else None


def _stage(connection, entry: dict) -> None:
    """`entry` with its item's `stage`, the `next` one, the `strip` and the `revision` a move posts; a problem when the
    item is missing, or at a stage off its kind's strip."""
    from sd_db import workflow

    entry.update(strip=list(STAGES.get(entry["kind"], ())), stage="", next="", revision="")
    if entry["item"] is None or not entry["kind"]:
        return
    try:
        state = workflow.item_state(connection, entry["item"])
    except workflow.MissingItem:
        entry["problems"].append(f"item sd:{entry['item']} does not exist")
        return
    current = state["item"]["stage"] or ""
    entry.update(stage=current, next=next_stage(entry["kind"], current) or "", revision=state["revision"])
    if current and current not in STAGES[entry["kind"]]:
        entry["problems"].append(f"item sd:{entry['item']} is at stage {current!r}, which is not on the {entry['kind']} strip")


def naming(connection, item: int, repo_root: Path | None = None) -> dict | None:
    """The one project whose `project.json` names `item` and a kind, or None; ValueError when two name it."""
    found = [p for p in projects(connection, repo_root, listing=False)[0] if p["item"] == item and p["kind"]]
    if len(found) > 1:
        raise ValueError(f"Two projects name sd:{item}: {', '.join(p['id'] for p in found)}. Name it in one project.json.")
    return found[0] if found else None


def move_stage(connection, item: int, project: dict, target: str, *, who: str, expected_revision: str) -> dict:
    """Move `item` to `target`, the next stage on `project`'s strip, at `expected_revision`, with a comment note; the
    item's state after. A stale revision raises `StaleItem` (409); any other stage raises `WorkflowError` (400). The
    stage and the note are one transaction, so a failure writes neither."""
    from sd_db import workflow
    from sd_db.database import transaction
    from sd_db.writes import add_note, set_item_fields

    kind = project["kind"]
    with transaction(connection):
        state = workflow.item_state(connection, item)
        if state["revision"] != expected_revision:
            raise workflow.StaleItem(f"item {item} changed; reload it before applying this change")
        current = state["item"]["stage"] or None
        if current == target:
            return state
        if current and current not in STAGES[kind]:
            raise workflow.WorkflowError(f"sd:{item} is at stage {current!r}, which is not on the {kind} strip; "
                                         "move it from the shell")
        following = next_stage(kind, current)
        if target != following:
            raise workflow.WorkflowError(f"A {kind} moves one stage at a time: {current or 'no stage'} goes to "
                                         f"{following or 'nothing; it is at the end of its strip'}, not {target}.")
        set_item_fields(connection, item, stage=target)
        add_note(connection, item, "comment", f"Studio stage {current or 'none'} -> {target} by {who} ({project['id']})",
                 session=who)
    return workflow.item_state(connection, item)


def view_request(payload: dict):
    """`POST /api/studio/view`: `{"file", "pinned" | "hidden"}`, `file` as `/studio/files/<file>` names it; the write as
    `action_route` returns one. A file the gallery does not serve now is refused, so a stale page writes nothing."""
    from sd_db import writes

    fields = {name: payload[name] for name in ("pinned", "hidden") if name in payload}
    if (not isinstance(payload.get("file"), str) or set(payload) - {"file", "pinned", "hidden"} or not fields
            or not all(type(value) is bool for value in fields.values())):
        raise ValueError("Send the file, and pinned or hidden, true or false.")
    file = payload["file"]

    def write(connection):
        if located(connection, file) is None:
            raise ValueError(f"No studio file {file} is served: read the projects again.")
        return {"file": file, **writes.set_view(connection, view_key(file), **fields)}
    return write


def located(connection, tail: str, repo_root: Path | None = None) -> tuple[Path, str] | None:
    """The file `/studio/files/<tail>` names and its type, or None: in a registered repository, inside a root a project
    of that repository names now, and passing `designs.resolve` with `TYPES`."""
    key, _, rest = tail.partition("/")
    checkout = repositories(connection, repo_root)[0].get(key)
    if checkout is None or not rest:
        return None
    found = designs.resolve(rest, checkout, TYPES)
    if found is None:
        return None
    target = found[0]
    for manifest in _project_files(checkout)[0]:
        entry = _project(key, checkout, manifest, listing=False)
        for root in entry["roots"] if entry else ():
            base = (manifest.parent / root["path"]).resolve()
            if target.is_relative_to(base):
                return found
    return None


def byte_range(header: str | None, size: int) -> tuple[int, int, int]:
    """(status, start, length) for a `Range` header on a file of `size` bytes.

    200 and the whole file for no header, a malformed one or several ranges; 416 (start and length 0) for a range
    that starts past the end; 206 otherwise, at most `CHUNK` bytes.
    """
    whole = (200, 0, size)
    if not header:
        return whole
    match = re.fullmatch(r"\s*bytes=(\d*)-(\d*)\s*", header)
    if match is None or match[1] == match[2] == "":
        return whole
    if match[1] == "":
        suffix = int(match[2])
        if suffix == 0 or size == 0:
            return 416, 0, 0
        start, end = max(size - suffix, 0), size - 1
    else:
        start = int(match[1])
        end = int(match[2]) if match[2] else size - 1
        if match[2] and end < start:
            return whole
        if start >= size:
            return 416, 0, 0
        end = min(end, size - 1)
    return 206, start, min(end - start + 1, CHUNK)
