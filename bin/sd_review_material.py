"""Complete review input accounting and advisory split plans; never dispatch."""

from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import subprocess
from typing import Any

import sd_lib


def read_git_material(root: pathlib.Path, args: list[str]) -> str:
    """Keep NUL-delimited names and whitespace intact."""
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
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


def file_material(root: pathlib.Path, name: str) -> str:
    path = root / name
    if path.is_symlink():
        content = "symlink -> " + os.readlink(path)
    else:
        data = path.read_bytes()
        try:
            content = data.decode("utf-8")
        except UnicodeError:
            content = "[binary, base64]\n" + base64.b64encode(data).decode("ascii")
    return f"\n--- {json.dumps(name)} ---\n{content}"


def collect_review_material(root: pathlib.Path, subject: Any) -> tuple[str, list[dict[str, Any]]]:
    """One entry per literal path; renames retain deletion and addition sides."""
    extra = set(untracked(root)) if subject.scope == "worktree" else set()
    patches = {} if subject.scope == "planning" else tracked_material(root, subject)
    parts: list[str] = []
    inventory: list[dict[str, Any]] = []
    for name in subject.paths:
        if subject.scope == "planning" or name in extra:
            part = file_material(root, name)
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
    patch = read_git_material(root, ["diff", "--binary", *args])
    pieces = list(filter(None, re.split(r"(?m)(?=^diff --git )", patch)))
    if len(names) != len(pieces):
        raise ValueError("review patch and path inventory disagree; no partial subject sent")
    return dict(zip(names, pieces, strict=True))


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
