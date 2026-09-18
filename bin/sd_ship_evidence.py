"""Durable disposition evidence for standalone review records.

A temporary file proves nothing later: the operator's rebuttal outlives the
directory it was written in. Preparation copies every cited file into this
repository's own evidence folder, content-addressed, and writes one archive that
lists each member. Later validation reads only those durable copies, and it
refuses a missing or changed archive instead of restoring one.

The folder lives under `.git`, so evidence never enters the worktree, never
appears in `git status`, and never travels with a push.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import tempfile

from sd_ship_dispositions import (
    MAX_EVIDENCE_BYTES,
    digest,
    read_file,
    unique_object,
)
from sd_ship_remote import Refusal

FOLDER = pathlib.Path(".git") / "sd-review-evidence"
MEMBER_FOLDER = "blob"
ARCHIVE_NAME = "archive.json"
ARCHIVE_SCHEMA_VERSION = 1
ARCHIVE_FIELDS = ("schema_version", "review_id", "members")
MEMBER_FIELDS = ("name", "sha256", "bytes")
MAX_ARCHIVE_BYTES = 2_000_000
MAX_MEMBERS = 128


def evidence_folder(root: pathlib.Path, review_id: str) -> pathlib.Path:
    """One folder per record, named by the record, resolved before any write."""
    if not review_id or "/" in review_id or review_id in (".", ".."):
        raise Refusal("durable evidence needs a simple review record identity")
    return root.resolve() / FOLDER / review_id


def archive_file(root: pathlib.Path, review_id: str) -> pathlib.Path:
    return evidence_folder(root, review_id) / ARCHIVE_NAME


def member_file(root: pathlib.Path, review_id: str, sha256: str) -> pathlib.Path:
    """Content-addressed: the same bytes are stored once, under their own digest."""
    if len(sha256) != 64 or any(letter not in "0123456789abcdef" for letter in sha256):
        raise Refusal("durable evidence member names are lowercase SHA256 digests")
    return evidence_folder(root, review_id) / MEMBER_FOLDER / sha256


def canonical_folder(root: pathlib.Path, review_id: str) -> pathlib.Path:
    """Refuse a folder reached through a link; a link can be repointed later."""
    folder = evidence_folder(root, review_id)
    if folder.exists() and folder.resolve(strict=True) != folder:
        raise Refusal(f"durable evidence folder is not a canonical directory: {folder}")
    return folder


def archive_descriptor(root: pathlib.Path, review_id: str) -> dict | None:
    """The archive as it is on disk now, or None when this record has none."""
    path = archive_file(root, review_id)
    if not path.exists() and not path.is_symlink():
        return None
    data = read_file(path, MAX_ARCHIVE_BYTES)
    try:
        value = json.loads(data, object_pairs_hook=unique_object)
    except (ValueError, RecursionError):
        raise Refusal(f"prepared evidence archive is not bounded valid JSON: {path}") from None
    if (not isinstance(value, dict) or set(value) != set(ARCHIVE_FIELDS)
            or value["schema_version"] != ARCHIVE_SCHEMA_VERSION
            or not isinstance(value["members"], list) or not value["members"]):
        raise Refusal(f"prepared evidence archive does not match this adapter's layout: {path}")
    if value["review_id"] != review_id:
        raise Refusal("prepared evidence archive names a different review record")
    for row in value["members"]:
        if not isinstance(row, dict) or set(row) != set(MEMBER_FIELDS):
            raise Refusal("prepared evidence archive lists a member without its name, SHA256 and size")
    return {"schema_version": ARCHIVE_SCHEMA_VERSION, "path": str(path),
            "sha256": hashlib.sha256(data).hexdigest(), "members": value["members"]}


def evidence_entries(proposal: dict) -> list[dict]:
    rows = proposal.get("findings") if isinstance(proposal, dict) else None
    entries: list[dict] = []
    for row in rows if isinstance(rows, list) else []:
        cited = row.get("evidence") if isinstance(row, dict) else None
        entries += [entry for entry in cited if isinstance(entry, dict)] if isinstance(cited, list) else []
    return entries


def declared_archive(root: pathlib.Path, review_id: str, proposal: dict) -> dict:
    bindings = proposal.get("bindings") if isinstance(proposal, dict) else None
    declared = bindings.get("evidence_archive") if isinstance(bindings, dict) else None
    if declared is None:
        raise Refusal(
            "standalone review evidence must be prepared into a durable archive with "
            "--prepare-evidence; a temporary file is never read implicitly and never copied"
        )
    if not isinstance(declared, dict) or set(declared) != {"schema_version", "path", "sha256", "members"}:
        raise Refusal("prepared evidence archive descriptor does not match this adapter's layout")
    if declared["path"] != str(archive_file(root, review_id)):
        raise Refusal("prepared evidence archive path is not this record's durable archive")
    return declared


def check_archive(root: pathlib.Path, review_id: str, proposal: dict) -> None:
    """Every cited file is a member of this record's unchanged durable archive."""
    declared = declared_archive(root, review_id, proposal)
    current = archive_descriptor(root, review_id)
    if current is None:
        raise Refusal(f"prepared evidence archive is missing: {declared['path']}")
    if current["sha256"] != declared["sha256"]:
        raise Refusal("prepared evidence archive changed; its SHA256 no longer matches the accepted descriptor")
    if digest(current) != digest(declared):
        raise Refusal("prepared evidence archive no longer matches the accepted descriptor")
    folder = canonical_folder(root, review_id)
    members = {row["name"]: row for row in current["members"]}
    for entry in evidence_entries(proposal):
        path = pathlib.Path(str(entry.get("path")))
        if not path.is_absolute() or not path.is_relative_to(folder):
            raise Refusal("disposition evidence must name a file inside this record's durable archive folder")
        row = members.get(str(path.relative_to(folder)))
        if row is None or row["sha256"] != entry.get("sha256"):
            raise Refusal("disposition evidence is not a member of the prepared archive")


def write_once(path: pathlib.Path, data: bytes) -> None:
    """Replace by rename, and leave identical content exactly as it is.

    Rewriting an unchanged member would change its timestamp, and a timestamp
    that moves without its content is indistinguishable from tampering.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not path.is_symlink() and path.read_bytes() == data:
        return
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".partial-")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        pathlib.Path(temporary).unlink(missing_ok=True)
        raise
    if path.lstat().st_nlink != 1:
        raise Refusal(f"durable evidence must keep one hard link: {path}")


def prepare_archive(root: pathlib.Path, review_id: str, proposal: dict) -> dict:
    """Copy each cited file into the record's folder and write one archive.

    The sources are left untouched. The returned proposal cites the durable
    copies and binds the archive, so the operator accepts what will be read
    back, not what happened to exist in a temporary directory.
    """
    prepared = json.loads(json.dumps(proposal), object_pairs_hook=unique_object)
    folder = canonical_folder(root, review_id)
    members: dict[str, dict] = {}
    for entry in evidence_entries(prepared):
        source = pathlib.Path(str(entry["path"]))
        data = read_file(source, MAX_EVIDENCE_BYTES)
        sha256 = hashlib.sha256(data).hexdigest()
        if sha256 != entry["sha256"]:
            raise Refusal("disposition evidence changed or its SHA256 is wrong")
        target = member_file(root, review_id, sha256)
        write_once(target, data)
        name = str(target.relative_to(folder))
        members[name] = {"name": name, "sha256": sha256, "bytes": len(data)}
        entry["path"] = str(target)
    if not members:
        raise Refusal("--prepare-evidence needs at least one cited evidence file")
    if len(members) > MAX_MEMBERS:
        raise Refusal(f"durable evidence exceeds this adapter's documented limit of {MAX_MEMBERS} members")
    payload = {"schema_version": ARCHIVE_SCHEMA_VERSION, "review_id": review_id,
               "members": sorted(members.values(), key=lambda row: row["name"])}
    write_once(archive_file(root, review_id), (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode())
    prepared["bindings"]["evidence_archive"] = archive_descriptor(root, review_id)
    return prepared
