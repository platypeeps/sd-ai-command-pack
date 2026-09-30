"""Complete review input accounting and advisory split plans; never dispatch."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
from typing import Any

import sd_lib


def read_git_material(root: pathlib.Path, args: list[str], stdin: str | None = None) -> str:
    """Keep NUL-delimited names and whitespace intact."""
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, input=stdin,
                            check=False, timeout=sd_lib.GIT_TIMEOUT_SECONDS)
    if result.returncode:
        raise ValueError("cannot read the complete review subject")
    return result.stdout


def changed(root: pathlib.Path, args: list[str]) -> tuple[list[str], int]:
    rows = read_git_material(root, ["diff", "--numstat", "-z", "--no-renames", "--no-ext-diff", "--no-textconv", *args]).split("\0")
    paths, lines = [], 0
    for row in filter(None, rows):
        added, removed, name = row.split("\t", 2)
        paths.append(name)
        lines += sum(int(value) for value in (added, removed) if value.isdigit())
    return paths, lines


def untracked(root: pathlib.Path) -> list[str]:
    return list(filter(None, read_git_material(root, ["ls-files", "--others", "--exclude-standard", "-z"]).split("\0")))


# sd:2181: binaries are summarized, never encoded. Binary is git's rule: its diff marker for a tracked
# change, else its no-attribute test (a NUL in the first 8000 bytes); non-UTF-8 bytes are summarized too.
BINARY_MARKER = re.compile(r"(?m)^Binary files .* differ\n?")


def content_summary(data: bytes) -> str:
    return f"{len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()}"


def file_material(root: pathlib.Path, name: str, change: str) -> str:
    path = root / name
    if path.is_symlink():
        content = "symlink -> " + os.readlink(path)
    else:
        data = path.read_bytes()
        binary = b"\0" in data[:8000]
        try:
            content = "" if binary else data.decode("utf-8")
        except UnicodeError:
            binary = True
        if binary:
            content = f"[binary, not sent] {change}; {content_summary(data)}"
    return f"\n--- {json.dumps(name)} ---\n{content}"


def collect_review_material(root: pathlib.Path, subject: Any) -> tuple[str, list[dict[str, Any]]]:
    """One entry per literal path; renames retain deletion and addition sides."""
    extra = set(untracked(root)) if subject.scope == "worktree" else set()
    patches = {} if subject.scope == "planning" else tracked_material(root, subject)
    parts: list[str] = []
    inventory: list[dict[str, Any]] = []
    for name in subject.paths:
        if subject.scope == "planning" or name in extra:
            part = file_material(root, name, "current" if subject.scope == "planning" else "added (untracked)")
        else:
            part = patches[name]
        part = ("\n" if parts else "") + part
        parts.append(part)
        inventory.append({"path": name, "bytes": len(part.encode("utf-8")),
                          "boundary": name.split("/", 1)[0] if "/" in name else "repository-root"})
    return "".join(parts), inventory


def tracked_material(root: pathlib.Path, subject: Any) -> dict[str, str]:
    args = ["--no-renames", "--no-ext-diff", "--no-textconv", "--no-color", "--submodule=short", subject.base,
            *([] if subject.head == "worktree" else [subject.head]), "--"]
    names = list(filter(None, read_git_material(root, ["diff", "--name-only", "-z", *args]).split("\0")))
    patch = read_git_material(root, ["diff", *args])
    pieces = list(filter(None, re.split(r"(?m)(?=^diff --git )", patch)))
    if len(names) != len(pieces):
        raise ValueError("review patch and path inventory disagree; no partial subject sent")
    material = dict(zip(names, pieces, strict=True))
    binary = {name: piece for name, piece in material.items() if BINARY_MARKER.search(piece)}
    return {**material, **binary_summaries(root, subject, binary)} if binary else material


def binary_summaries(root: pathlib.Path, subject: Any, pieces: dict[str, str]) -> dict[str, str]:
    """Keep git's header lines; replace the binary marker with sizes and hashes."""
    sides = {name: (re.findall(r"(?m)^index ([0-9a-f]+)\.\.([0-9a-f]+)", piece) or [("", "")])[0] for name, piece in pieces.items()}
    wanted = sorted({oid for old, new in sides.values() for oid in (old, new) if oid.strip("0")})
    rows = read_git_material(root, ["cat-file", "--batch-check"], "".join(f"{oid}\n" for oid in wanted)).splitlines() if wanted else []
    blobs = {oid: f"{row.split()[2]} bytes, blob {row.split()[0]}" for oid, row in zip(wanted, rows, strict=True)
             if row.split()[1:2] == ["blob"]}
    summaries = {}
    for name, piece in pieces.items():
        old, new = (blobs.get(oid, f"size unknown, blob {oid}") if oid.strip("0") else "absent" for oid in sides[name])
        if subject.head == "worktree":
            path = root / name
            new = content_summary(path.read_bytes()) if path.is_file() and not path.is_symlink() else "absent"
        change = "added" if "\nnew file mode " in piece else "deleted" if "\ndeleted file mode " in piece else "modified"
        summaries[name] = f"{BINARY_MARKER.split(piece, 1)[0]}[binary, not sent] {change}; old {old}; new {new}\n"
    return summaries


def input_manifest(inventory: list[dict[str, Any]], prompt: str, overheads: dict[str, str | None], limit: int,
             context: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    context = context or []
    paths = {row["path"]: dict(row) for row in inventory}
    for row in context:
        current = paths.setdefault(row["path"], dict(row, bytes=0))
        current["bytes"] += row["bytes"]
    inventory = list(paths.values())
    context_bytes = sum(row["bytes"] for row in context)
    prompt_bytes = len(prompt.encode("utf-8")) - sum(row.get("included_bytes", row["bytes"]) for row in context)
    material_bytes = sum(row["bytes"] for row in inventory)
    # None means native repository access: only the complete prompt is transmitted.
    transports = {name: prompt_bytes + (context_bytes if overhead is None else material_bytes + len(overhead.encode()))
                  for name, overhead in overheads.items()}
    measured = max(transports.values(), default=prompt_bytes + material_bytes)
    allowance = max(0, limit - prompt_bytes - max((len((value or "").encode()) for value in overheads.values()), default=0))
    groups: list[dict[str, Any]] = []
    for row in inventory:
        if not groups or groups[-1]["bytes"] + row["bytes"] > allowance or groups[-1]["boundary"] != row["boundary"]:
            groups.append({"paths": [], "bytes": 0, "boundary": row["boundary"]})
        groups[-1]["paths"].append(row["path"])
        groups[-1]["bytes"] += row["bytes"]
    return {"status": "oversized" if measured > limit else "within_limit", "limit_bytes": limit,
            "measured_bytes": measured, "prompt_bytes": prompt_bytes, "material_bytes": material_bytes, "context_bytes": context_bytes,
            "transport_bytes": transports, "paths": inventory, "suggested_groups": groups,
            "oversized_paths": [row["path"] for row in inventory if row["bytes"] > allowance],
            "next_action": "split_input_for_oversized_providers" if measured > limit else None,
            "advisory_only": False, "split_plan_advisory_only": True,
            "dependency_boundaries": "directory hints; semantic dependencies require operator review",
            "cross_branch_concerns": ["Keep shared interfaces, imports, migrations, and their tests coordinated."],
            "review_complete": False}
