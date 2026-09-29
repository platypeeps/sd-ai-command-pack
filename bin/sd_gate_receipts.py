"""One passing local gate per head: a receipt the next gate at the same head reuses (sd:2041, sd:1912).

`sd-ship prepare` and the `sd-ship merge` local gate each ran the repository's
full check on the same head, so every pull request paid for it twice. Both now
run it the same way -- `sd_gate_run.check_in_worktree`, a clean detached
worktree at the exact head with the gate's environment -- and a pass leaves a
receipt in the workflow database. The next gate run whose binding is equal
reads the receipt instead of running the check again.

The binding is what this module can name about a run, and nothing weaker:

  head, tree   the exact commit the worktree held;
  inputs       `sd_gate_run.gate_inputs`: the head, the copied untracked
               `CLAUDE.local.md` (or its absence) and every pack `bin/` file,
               so a pack upgrade reruns the check;
  scope        the `sd_check_scope` decision, with its merge base;
  commands     the detected entrypoints and the detection source;
  tools        path and bytes of each command's executable on the gate's PATH;
  python       the interpreter that runs `sd-check`;
  environment  every variable the check's child is given, by name and
               value: `sd_gate_run.gate_environment`'s whole output, so a
               `MAKEFLAGS` or a `CARGO_HOME` that chose what ran is bound too.

The environment is bound whole because the gate forwards it whole: any
variable may choose what a check runs, and a hand-kept list of the ones that
matter would miss the next one. The cost is fewer reuses: a prepare and a
merge started from shells that differ in any variable run the check twice.

It does not name what a check reads on its own: a tool its Makefile reaches
through another tool, a network answer, the machine's load. The gate never
claimed those; it is a self-hosted runner, not a hermetic build. So a receipt
also ages out after `MAX_AGE_SECONDS`, and only a success is ever recorded. A
receipt proves that this machine's gate passed this commit with these inputs
recently; it does not prove the check is deterministic.

Every fault here -- no library, no database, an unreadable row, a tool that
does not resolve -- means "no receipt", and the check runs. Evidence that
cannot be read never grants a pass.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import time
from contextlib import closing
from typing import Any, Mapping

import sd_check_receipts
import sd_check_scope
import sd_lib

KEY_PREFIX = "sd-gate-receipt:v1:"
#: How long a receipt stands. The binding cannot name every input a check
#: reads, so time bounds what it misses; a prepare and its merge are hours apart
#: at most, and a receipt older than that is not what saved the second run.
MAX_AGE_SECONDS = 12 * 3600
WRITER = "sd-local-gate"


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def receipt_key(root: pathlib.Path, head: str) -> str:
    """One key per repository and head; every worktree of one repository shares its git directory."""
    common = sd_lib.git_output(["rev-parse", "--path-format=absolute", "--git-common-dir"], root) or str(root)
    return KEY_PREFIX + _digest([str(pathlib.Path(common).resolve()), head])


def gate_binding(tree: pathlib.Path, head: str, inputs: str, base: str | None, env: Mapping[str, str]) -> dict[str, Any] | None:
    """What a run in `tree` would be bound to, or None when something in it cannot be named."""
    try:
        detection = sd_lib.detect_entrypoints(tree)
        scope = sd_check_scope.decide(tree, base, detection)
        commands = [list(scope.command)] if scope.mode == sd_check_scope.DOCS_ONLY else list(detection.commands.values())
        if not commands:
            return None
        tools = [sd_check_receipts.tool_identity(argv[0], env, tree) for argv in commands]
        for tool in tools:  # the worktree is temporary; name a tool inside it by its place in the tree
            path = pathlib.Path(tool["path"])
            if path.is_relative_to(tree.resolve()):
                tool["path"] = "tree:" + str(path.relative_to(tree.resolve()))
        python = pathlib.Path(sys.executable).resolve()
        return {"schema": 2, "head": head, "tree": sd_lib.git_output(["rev-parse", "HEAD^{tree}"], tree),
                "inputs": inputs, "scope": {"mode": scope.mode, "fork": scope.fork, "command": list(scope.command)},
                "detection": {"source": detection.source, "commands": detection.commands},
                "tools": tools, "python": {"path": str(python), "version": sys.version,
                                           "sha256": sd_check_receipts.file_digest(python)},
                "environment_sha256": _digest(dict(env))}
    except Exception:  # an input that cannot be named binds nothing; the check runs
        return None


def _connect(database: pathlib.Path, *, write: bool) -> Any:
    imported = sd_lib.import_sd_db()
    if imported.module is None:
        raise LookupError(imported.problem or "no sd_db library")
    return imported.module.connect(database, write=write)


def lookup(database: pathlib.Path, key: str, identity: Mapping[str, Any], now: float | None = None) -> dict[str, Any] | None:
    """The recorded success for `identity`, or None: absent, foreign, stale, older than the limit, or unreadable."""
    try:
        with closing(_connect(database, write=False)) as connection:
            from sd_db import ship  # noqa: PLC0415
            revision, row = ship.read(connection, key)
        age = (time.time() if now is None else now) - float(row.get("recorded_at", "nan"))
        reading = row.get("reading")
        if (row.get("writer") != WRITER or row.get("binding") != identity or not 0 <= age <= MAX_AGE_SECONDS
                or not isinstance(reading, dict) or reading.get("status") != "success"):
            return None
        return {"reading": reading, "revision": revision, "recorded_at": row["recorded_at"], "age_seconds": round(age)}
    except Exception:
        return None


def record_pass(database: pathlib.Path, key: str, identity: Mapping[str, Any], reading: Mapping[str, Any],
           now: float | None = None) -> int:
    """Store a success under `key`; anything but a success is refused, and raises."""
    if reading.get("status") != "success":
        raise ValueError("only a passing gate run leaves a receipt")
    with closing(_connect(database, write=True)) as connection:
        from sd_db import ship  # noqa: PLC0415
        revision, _ = ship.read(connection, key)
        return int(ship.save(connection, key, revision, {
            "writer": WRITER, "binding": dict(identity), "reading": dict(reading),
            "recorded_at": time.time() if now is None else now}))
