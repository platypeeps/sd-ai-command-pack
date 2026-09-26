"""Opt-in local check receipts. Dependency declarations are not sandbox enforcement."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
from contextlib import closing
from typing import Any, Mapping

import sd_lib

CONTRACT = ".github/sd-check-reuse.json"
FIELDS = {"schema_version", "complete", "network", "dependencies", "tools", "environment"}
BASE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
SECRET = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|COOKIE|AUTH", re.I)
BIN = pathlib.Path(__file__).resolve().parent


class Unavailable(ValueError):
    """The available evidence cannot establish reusable check identity."""


def receipt_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def file_digest(path: pathlib.Path) -> str:
    hasher = hashlib.sha256()
    hasher.update(str(path.stat().st_mode).encode())
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def reuse_contract(root: pathlib.Path) -> dict[str, Any]:
    value = json.loads((root / CONTRACT).read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or set(value) != FIELDS or type(value["schema_version"]) is not int
            or value["schema_version"] != 1 or value["complete"] is not True or value["network"] != "none"):
        raise Unavailable("reuse requires a complete local-only dependency declaration")
    for name in ("dependencies", "tools", "environment"):
        entries = value[name]
        if not isinstance(entries, list) or any(not isinstance(v, str) or not v for v in entries) or len(set(entries)) != len(entries):
            raise Unavailable(f"invalid reuse {name}")
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name) or SECRET.search(name) for name in value["environment"]):
        raise Unavailable("receipt environments cannot declare credential variables")
    return value


def receipt_environment(value: Mapping[str, Any], env: Mapping[str, str]) -> dict[str, str]:
    """Checks recorded for reuse run only with this declared environment."""
    return {key: env[key] for key in (*BASE_ENV, *value["environment"]) if key in env}


def dependency_files(root: pathlib.Path, names: list[str]) -> dict[str, str]:
    files = {}
    for name in names:
        relative = pathlib.Path(name)
        path = root / relative
        if (relative.is_absolute() or ".." in relative.parts or path.resolve() != path
                or not path.exists() or ".git" in relative.parts or SECRET.search(relative.name)):
            raise Unavailable(f"unsupported dependency path: {name}")
        entries = [path, *sorted(path.rglob("*"))] if path.is_dir() else [path]
        for entry in entries:
            if entry.is_symlink() or SECRET.search(entry.name) or entry.name == ".git" or not (entry.is_file() or entry.is_dir()):
                raise Unavailable(f"unsupported dependency entry: {entry.relative_to(root)}")
            if entry.is_file():
                files[str(entry.relative_to(root))] = file_digest(entry)
            else:
                files[str(entry.relative_to(root)) + "/"] = f"directory:{entry.stat().st_mode}"
    return files


def tool_identity(name: str, env: Mapping[str, str], root: pathlib.Path) -> dict[str, str]:
    # subprocess resolves argv and every PATH component from its repository cwd.
    search_path = os.pathsep.join(str(root / component) for component in os.get_exec_path(env))
    command = str(root / name) if os.path.dirname(name) else name
    target = shutil.which(command, path=search_path)
    if not target:
        raise Unavailable(f"unresolved check tool: {name}")
    path = pathlib.Path(target)
    if not path.is_absolute():
        path = root / path
    return {"invocation": name, "path": str(path.resolve()), "sha256": file_digest(path)}


def check_binding(root: pathlib.Path, env: Mapping[str, str]) -> dict[str, Any]:
    root = root.resolve()
    if sd_lib.git_output(["status", "--porcelain", "--untracked-files=all"], root) != "":
        raise Unavailable("reuse requires a clean committed checkout")
    if sd_lib.git_output(["ls-files", "--error-unmatch", "--", CONTRACT], root) != CONTRACT:
        raise Unavailable("reuse requires a tracked dependency declaration")
    value = reuse_contract(root)
    controlled = receipt_environment(value, env)
    detection = sd_lib.detect_entrypoints(root)
    if not detection.commands:
        raise Unavailable("there is no full check to record")
    tools = sorted(set(value["tools"]) | {argv[0] for argv in detection.commands.values()})
    files = dependency_files(root, value["dependencies"])
    for name in ("sd-check", "sd_check_receipts.py", "sd_lib.py"):
        files["pack:" + name] = file_digest(BIN / name)
    for name in ("CLAUDE.local.md", ".github/sd-review.json", CONTRACT):
        path = sd_lib.local_block_path(root) if name == "CLAUDE.local.md" else root / name
        files["policy:" + name] = file_digest(path) if path.exists() else "absent"
    return {"schema_version": 1, "checkout": str(root), "head": sd_lib.git_output(["rev-parse", "HEAD"], root),
            "tree": sd_lib.git_output(["rev-parse", "HEAD^{tree}"], root),
            "argv": [sys.executable, str(BIN / "sd-check"), "--json"],
            "detection": {"source": detection.source, "commands": detection.commands, "origin": str(detection.origin)},
            "files": files, "tools": [tool_identity(name, controlled, root) for name in tools],
            "python": {"executable": str(pathlib.Path(sys.executable).resolve()), "sha256": file_digest(pathlib.Path(sys.executable)),
                       "version": sys.version, "prefix": sys.prefix},
            "environment_sha256": receipt_digest(controlled)}


def full_success(result: Any, expected: Mapping[str, Any]) -> bool:
    if not isinstance(result, dict):
        return False
    if (result.get("status"), result.get("dry_run") is False, result.get("tool"), result.get("schema")) != ("pass", True, "sd-check", 1):
        return False
    checks = result.get("checks")
    if not isinstance(checks, list) or len(checks) != len(sd_lib.CHECK_NAMES):
        return False
    commands = expected["detection"]["commands"]
    for name, row in zip(sd_lib.CHECK_NAMES, checks, strict=True):
        if not isinstance(row, dict) or row.get("name") != name or row.get("command") != commands.get(name):
            return False
        wanted = "absent" if name not in commands else "skipped" if "check" in commands and name != "check" else "pass"
        if row.get("status") != wanted:
            return False
        if wanted == "pass" and (type(row.get("exit_code")) is not int or row["exit_code"] != 0):
            return False
        if wanted == "skipped" and row.get("reason") != "covered by the check entrypoint":
            return False
    return result.get("repo") == expected["checkout"]


def storage(env: Mapping[str, str], database: pathlib.Path | None, *, write: bool) -> Any:
    imported = sd_lib.import_sd_db()
    if imported.module is None:
        raise Unavailable("receipt storage requires the shared database library")
    return imported.module.connect(database or imported.module.default_path(env.get("HOME")), write=write)


def check_receipt_key(root: pathlib.Path) -> str:
    return "sd-check-receipt:v1:" + receipt_digest(str(root.resolve()))


def prepare_check_receipt(root: pathlib.Path, env: Mapping[str, str], database: pathlib.Path | None) -> tuple[dict[str, Any], int]:
    identity = check_binding(root, env)
    with closing(storage(env, database, write=True)) as connection:
        from sd_db import ship
        revision, _ = ship.read(connection, check_receipt_key(root))
        revision = ship.save(connection, check_receipt_key(root), revision, {"writer": "sd-check", "binding": identity, "state": "running"})
    return identity, revision


def store_check_receipt(root: pathlib.Path, env: Mapping[str, str], database: pathlib.Path | None,
         before: tuple[dict[str, Any], int], result: dict[str, Any]) -> int:
    identity, revision = before
    if not full_success(result, identity) or check_binding(root, env) != identity:
        raise Unavailable("check failed, was partial, or its inputs changed; no reusable receipt stored")
    with closing(storage(env, database, write=True)) as connection:
        from sd_db import ship
        return int(ship.save(connection, check_receipt_key(root), revision, {"writer": "sd-check", "binding": identity, "result": result}))


def reuse_checked_result(root: pathlib.Path, env: Mapping[str, str], database: pathlib.Path | None) -> dict[str, Any] | None:
    try:
        identity = check_binding(root, env)
        with closing(storage(env, database, write=False)) as connection:
            from sd_db import ship
            revision, row = ship.read(connection, check_receipt_key(root))
        if (set(row) != {"protocol", "writer", "binding", "result"} or row.get("writer") != "sd-check" or row.get("binding") != identity
                or not full_success(row.get("result"), identity) or check_binding(root, env) != identity):
            return None
        return {"status": "pass", "exit_code": 0, "detail": "", "checks": row["result"]["checks"],
                "source": "receipt", "receipt_revision": revision, "binding_sha256": receipt_digest(identity)}
    except Exception:
        return None  # Unverifiable evidence runs the check; it never grants a pass.
