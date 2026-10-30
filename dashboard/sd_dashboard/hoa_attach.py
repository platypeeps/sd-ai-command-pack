"""HOA map attachments (sd:6690): an asset's documents and pictures, held in the water committee's Drive.

No new store: an asset's attachments are its Drive folder's listing. The design is
`docs/work/2026-10-30-hoa-attachments/design.md`; its failure table names each step's recovery.

- **Where.** The `hoa.water_system_folder` setting holds the Water System folder id, and `hoa.google_account` the
  account workspace-mcp reads it as. Subfolders are found by name (`place`): a valve or hydrant is `Main/<asset id>`,
  made on its first attachment; `WELL-A1` and `WELL-A2` are `Well A1` and `Well A2`; the tank is `Cistern`.
- **List**, `GET /api/hoa/attachments?asset=<id>`: the folder's items. A `.url` file is a Reference; its target is read
  from its text. A missing asset folder is an empty list, and nothing is made.
- **Picture**, `GET /api/hoa/attachments/picture?id=<file id>`: one picture's bytes, through workspace-mcp's download
  URL on its own host, so the page's thumbnails need no third-party image source.
- **Upload**, `POST /api/hoa/attach {"asset", "sha256", "name"}`: a file the page first staged at
  `POST /api/hoa/attach/file` (`source_intake.stage`), written into the folder. Only on the operator's press (hoa sd:6692).
- **Reference**, `POST /api/hoa/attach {"asset", "link", "name"?}`: a small `<name>.url` file naming a Drive link
  (operator ruling, note #36048): workspace-mcp cannot make a Drive shortcut.

Every Drive call goes through workspace-mcp (`research_slides._call`), so the dashboard holds no Google token.
"""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import re
import threading
import urllib.parse
import urllib.request

from . import hoa_screen, notes_screen, research_slides, source_intake

__all__ = ["ACCOUNT_KEY", "FOLDER_KEY", "PICTURE_BYTES", "SUFFIXES", "UPLOAD_BYTES", "listing", "picture", "place",
           "request"]

FOLDER_KEY = "hoa.water_system_folder"
ACCOUNT_KEY = "hoa.google_account"
#: What Upload takes: pictures and documents. The bytes ride base64 in one workspace-mcp call, so the cap is modest.
SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".pdf", ".txt", ".md", ".doc", ".docx", ".xls", ".xlsx")
UPLOAD_BYTES = 20 * 1024 * 1024
#: A picture the page draws as a thumbnail; a larger one is a link only.
PICTURE_BYTES = 10 * 1024 * 1024
FOLDER_MIME = "application/vnd.google-apps.folder"
#: Drive and Docs links only: a Reference names a file in Drive.
LINK = re.compile(r"https://(drive|docs)\.google\.com/[^\s\"'<>]+")
ID = re.compile(r"[\w-]{10,200}")
ITEM = re.compile(r'^- Name: "(?P<name>.*)" \(ID: (?P<id>[\w-]+), Type: (?P<mime>[^,)]+).*?\) Link: (?P<link>\S+)$',
                  re.MULTILINE)
class Unknown(Exception):
    """A write workspace-mcp gave no clear answer to: whether Drive holds the file is not known."""


#: One attachment write at a time, so two first uploads to one valve make one folder, not two.
ATTACHING = threading.Lock()


def place(asset: dict) -> tuple[str, str | None]:
    """`(subfolder, asset folder or None)` under Water System; `ValueError` for an asset with no place."""
    if asset.get("type") in ("valve", "hydrant"):
        return "Main", asset["id"]
    if asset.get("id") in ("WELL-A1", "WELL-A2"):
        return f"Well {asset['id'][-2:]}", None
    if asset.get("type") == "tank":
        return "Cistern", None
    raise ValueError(f"{asset.get('id')} ({asset.get('type')}) has no Water System folder.")


def _call(tool: str, arguments: dict, what: str) -> str:
    """One workspace-mcp call: `ConnectionError` when it did nothing, `LookupError` when that is not known."""
    url, _, _ = notes_screen.workspace()
    return research_slides._call(url, tool, arguments, what)


def _first(parameters: dict, name: str):
    value = parameters.get(name)
    return value[0] if isinstance(value, list) and value else value


def _write(tool: str, arguments: dict, what: str) -> str:
    """The id of the file the one write made: an answer naming no such file is `Unknown`, as is no answer."""
    try:
        said = _call(tool, arguments, what)
    except LookupError as error:
        raise Unknown(str(error)) from None
    # Only workspace-mcp's success line, for this file name, confirms the write; any other text may hide an error.
    made = re.search(rf"Successfully created file '{re.escape(arguments['file_name'])}' \(ID: ([\w-]+)\)", said)
    if not made:
        raise Unknown(f"workspace-mcp answered without a created file: {said[:200]}")
    return made[1]


def _settings(connection) -> tuple[str, str]:
    from sd_db import writes

    held = writes.read_settings(connection, [FOLDER_KEY, ACCOUNT_KEY])
    folder, account = held.get(FOLDER_KEY), held.get(ACCOUNT_KEY)
    if not folder or not account:
        missing = " and ".join(key for key, value in ((FOLDER_KEY, folder), (ACCOUNT_KEY, account)) if not value)
        raise LookupError(f"{missing} is not set: run sd config set {missing.split(' and ')[0]} <value>.")
    return folder, account


def _asset(connection, ident: object) -> dict:
    if not isinstance(ident, str) or not ident:
        raise ValueError("Name the asset by its id.")
    found = hoa_screen._geojson(hoa_screen._paths(hoa_screen.checkout(connection)[1])["assets"], hoa_screen.ASSET_KEYS,
                                "assets")
    if found.get("error"):
        raise LookupError(f"The asset map was not read: {found['error']}")
    for asset in found["features"]:
        if asset["id"] == ident:
            return asset
    raise ValueError(f"No asset {ident} on the map.")


def _children(account: str, folder: str) -> list[dict]:
    said = _call("list_drive_items", {"user_google_email": account, "folder_id": folder, "page_size": 200}, "the listing")
    return [match.groupdict() for match in ITEM.finditer(said)]


def _one(account: str, parent: str, name: str) -> str | None:
    """The id of the one folder named `name` in `parent`; None for none, `LookupError` for two."""
    found = [row["id"] for row in _children(account, parent) if row["mime"] == FOLDER_MIME and row["name"] == name]
    if len(found) > 1:
        raise LookupError(f"Drive holds {len(found)} folders named {name}: {', '.join(found)}. Merge them in Drive.")
    return found[0] if found else None


def _folder(connection, ident: object, *, make: bool) -> tuple[dict, str, str | None]:
    """`(asset, account, folder id)`: the asset's folder, made when `make` and missing; None when missing."""
    asset = _asset(connection, ident)
    sub, own = place(asset)
    root, account = _settings(connection)
    parent = _one(account, root, sub)
    if parent is None:
        raise LookupError(f"The Water System folder has no folder named {sub}.")
    if own is None:
        return asset, account, parent
    folder = _one(account, parent, own)
    if folder is None and make:
        said = _call("create_drive_folder", {"user_google_email": account, "folder_name": own,
                                             "parent_folder_id": parent}, "the folder")
        made = re.search(r"ID:\s*([\w-]+)", said)
        if not made:
            raise LookupError(f"workspace-mcp answered without a folder id: {said[:200]}")
        folder = made[1]
    return asset, account, folder


def _kind(row: dict) -> str:
    if row["mime"] == FOLDER_MIME:
        return "folder"
    if row["name"].lower().endswith(".url"):
        return "link"
    return "picture" if row["mime"].startswith("image/") else "document"


def listing(connection, parameters: dict):
    """`GET /api/hoa/attachments?asset=<id>`: `{"asset", "folder", "files"}`, or `(status, {"error"})`."""
    try:
        asset, account, folder = _folder(connection, _first(parameters, "asset"), make=False)
        files = []
        for row in _children(account, folder) if folder else []:
            entry = {**row, "kind": _kind(row)}
            if entry["kind"] == "link":
                text = _call("get_drive_file_content", {"user_google_email": account, "file_id": row["id"]}, "the link")
                target = re.search(r"^URL=(\S+)", text, re.MULTILINE)
                entry["target"] = target[1] if target and LINK.fullmatch(target[1]) else ""
            files.append(entry)
    except ValueError as error:
        return 400, {"error": str(error)}
    except (LookupError, ConnectionError) as error:
        return 503, {"error": f"The attachments were not read: {error}"}
    return {"asset": asset["id"], "folder": f"https://drive.google.com/drive/folders/{folder}" if folder else "",
            "files": files}


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=research_slides.SLIDES_TIMEOUT) as answer:  # noqa: S310 - checked host
        data = answer.read(PICTURE_BYTES + 1)
    if len(data) > PICTURE_BYTES:
        raise LookupError(f"the picture is over {PICTURE_BYTES // (1024 * 1024)} MB")
    return data


def picture(connection, parameters: dict):
    """`GET /api/hoa/attachments/picture?id=<file id>`: `(200, bytes, mime)` for a picture, else `(status, {"error"})`."""
    ident = _first(parameters, "id")
    if not isinstance(ident, str) or not ID.fullmatch(ident):
        return 400, {"error": "Name the picture by its Drive file id."}
    try:
        _, account = _settings(connection)
        said = _call("get_drive_file_download_url", {"user_google_email": account, "file_id": ident}, "the download")
        found, mime = re.search(r"Download URL:\s*(http\S+)", said), re.search(r"MIME Type:\s*(image/[\w.+-]+)", said)
        if not mime:
            return 415, {"error": "That file is not a picture."}
        server = urllib.parse.urlsplit(notes_screen.workspace()[0])
        # Only workspace-mcp's own host: the URL comes back in a tool's text, and the server fetches it.
        if not found or urllib.parse.urlsplit(found[1]).netloc != server.netloc:
            return 502, {"error": "workspace-mcp gave no download URL on its own host."}
        return 200, _fetch(found[1]), mime[1]
    except (LookupError, ConnectionError, OSError) as error:
        return 503, {"error": f"The picture was not read: {error}"}


def _upload(connection, values: dict) -> dict:
    sha, name = values.get("sha256"), values.get("name")
    if not isinstance(sha, str) or not source_intake.SHA.fullmatch(sha) or not isinstance(name, str):
        raise ValueError("Upload names a staged file by its sha256 and its name.")
    staged = source_intake._state() / "staged" / sha
    try:
        data = staged.read_bytes()
    except FileNotFoundError:
        raise ValueError(f"{name} is no longer staged: choose it again.") from None
    if len(data) > UPLOAD_BYTES or hashlib.sha256(data).hexdigest() != sha:
        raise ValueError(f"{name} is over {UPLOAD_BYTES // (1024 * 1024)} MB or changed since it was staged.")
    stored = source_intake._name(name, SUFFIXES)
    mime = mimetypes.guess_type(stored)[0] or "application/octet-stream"
    with ATTACHING:
        asset, account, folder = _folder(connection, values.get("asset"), make=True)
        made = _write("create_drive_file", {"user_google_email": account, "file_name": stored, "folder_id": folder,
                                           "base64_content": base64.b64encode(data).decode("ascii"), "base64_sha256": sha,
                                           "content_mime_type": mime, "mime_type": mime}, "the upload")
    staged.unlink(missing_ok=True)
    return {"asset": asset["id"], "name": stored, "id": made}


def _reference(connection, values: dict) -> dict:
    link, name = values.get("link"), values.get("name") or "Drive link"
    if not isinstance(link, str) or not LINK.fullmatch(link.strip()):
        raise ValueError("Reference takes a drive.google.com or docs.google.com link.")
    if not isinstance(name, str):
        raise ValueError("A Reference's name is text.")
    stored = re.sub(r"[^A-Za-z0-9._ -]+", "-", name).strip(" -._")[:100] or "Drive link"
    with ATTACHING:
        asset, account, folder = _folder(connection, values.get("asset"), make=True)
        made = _write("create_drive_file", {"user_google_email": account, "file_name": f"{stored}.url",
                                           "folder_id": folder, "content": f"[InternetShortcut]\nURL={link.strip()}\n",
                                           "mime_type": "text/plain"}, "the reference")
    return {"asset": asset["id"], "name": f"{stored}.url", "id": made}


def request(values: dict):
    """`POST /api/hoa/attach`'s checks; the write runs on the operator's press only."""
    if set(values) - {"asset", "sha256", "name", "link"} or not isinstance(values.get("asset"), str):
        raise ValueError('Send {"asset", "sha256", "name"} to upload or {"asset", "link", "name"} to reference.')
    if ("sha256" in values) == ("link" in values):
        raise ValueError("Attach either a staged file (sha256) or a link, not both.")
    act = _upload if "sha256" in values else _reference

    def write(connection):
        try:
            return 200, act(connection, values)
        except Unknown as error:
            return 504, {"error": f"Whether Drive holds the file is not known ({error}). Look in the asset's folder "
                                  "before you press again."}
        except (LookupError, ConnectionError) as error:
            return 503, {"error": f"Nothing was written: {error}"}

    return write
