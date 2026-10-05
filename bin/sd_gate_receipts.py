"""One passing local gate per head: a receipt the next gate at the same head reuses (sd:2041, sd:1912).

`sd-ship prepare` and the `sd-ship merge` local gate each ran the repository's
full check on the same head, so every pull request paid for it twice. Both now
run it the same way -- `sd_gate_run.check_in_worktree`, a clean detached
worktree at the exact head with the gate's environment. Prepare's pass leaves a
receipt in this machine's workflow database, and the merge gate at the same
head, with an equal binding, within `REUSE_WINDOW_SECONDS`, reads it instead of
running the check again. Prepare reads one as well (sd:1912): a pass that
`sd gate check` or an earlier prepare left at the head stands, so a head that
passed once runs no second check. The merge gate never writes one, and the
window counts from the run that passed, never from a reuse.

The binding is what this module can name about a run, and nothing weaker:

  reuse        "head", or "tree" for a declared tree key (below);
  head, tree   the exact commit the worktree held; head is None under a tree key;
  fork         under a tree key, the tree of the merge base with the base branch;
  inputs       `sd_gate_run.gate_inputs`: the head (or tree), the copied untracked
               `CLAUDE.local.md` (or its absence) and every pack `bin/` file,
               so a pack upgrade reruns the check;
  scope        the `sd_check_scope` decision, with its merge base (its tree under a tree key);
  commands     the detected entrypoints and the detection source;
  tools        path and bytes of each command's executable on the gate's PATH;
  python       the interpreter that runs `sd-check`;
  environment  every variable the check's child is given, by name and
               value: `sd_gate_run.gate_environment`'s whole output, so a
               `MAKEFLAGS` or a `CARGO_HOME` that chose what ran is bound too;
  threads      the thread counts `sd-check` sets for its checks under the
               machine's slot count (`sd_gate_slots.thread_caps`, sd:2726).
               The precheck runs on the environment as given, so both bind:
               a new slot count that changes the caps runs the check once more.

The environment is bound whole because the gate forwards it whole: any
variable may choose what a check runs, and a hand-kept list of the ones that
matter would miss the next one. The cost is fewer reuses: a prepare and a
merge started from shells that differ in any variable run the check twice.

The trust boundary: inputs outside the repository are not bound. An external
makefile named by an unchanged `MAKEFILES`, a file a tool reads, a tool its
Makefile reaches through another tool, a network answer, machine state: any of
these can change between prepare and merge and the binding stays equal. The
gate never claimed them; it is a self-hosted runner, not a hermetic build. The
short same-head window is the accepted residual risk, and only a success is
ever recorded. A receipt proves that this machine's gate passed this commit
with these inputs minutes ago; it does not prove the check is deterministic.
A repository that needs more uses the explicit dependency contract,
`sd-check --record-receipt` with a declared inventory (sd:1912).

A repository whose check reads no commit history may key its receipts by tree
instead of head, in its reviewed tree:

    .github/sd-gate-reuse.json
    {"schema_version": 1, "key": "tree", "reason": "the check reads no commit message, range or tag"}

Two heads with one tree -- an `sd attribute` commit, a reworded message, a
rebase that changed nothing -- then share one receipt: the key and the binding
name the tree and the merge base with the base branch, and `inputs` hashes the
tree in place of the head. The merge base is named by its tree, not its commit
(sd:2586, operator ruling 2026-10-04): `sd-ship lane run` gates the next item
on a predicted landing of the item ahead, and the real squash merge is another
commit with the same tree, which a check that reads no history cannot tell
apart. A run with no base keeps the head key: the merge base is what binds
the content below the branch. Without the
declaration a new head runs again, because a commit-message lint or a version
stamp from `git describe` can pass at one head and fail at the next. A
declaration that does not parse, or names another key, keeps the head key; the
file is in the tree, so changing it is a new tree and runs the check. A
tree-keyed receipt stands for `TREE_REUSE_WINDOW_SECONDS` (6 hours, ruling
D2'), long enough for a builder's pass to serve the lane's prepare and merge;
the head key keeps `REUSE_WINDOW_SECONDS`.

Every fault here -- no library, no database, an unreadable row, a tool that
does not resolve -- means "no receipt", and the check runs. Evidence that
cannot be read never grants a pass.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import pathlib
import shutil
import sys
import time
from contextlib import closing
from typing import Any, Iterable, Mapping

import sd_check_receipts
import sd_check_scope
import sd_gate_slots
import sd_lib

KEY_PREFIX = "sd-gate-receipt:v1:"
#: How long a receipt stands: one prepare-to-merge handoff on this machine.
#: The binding cannot name inputs outside the repository -- an external
#: makefile, a tool's own files, machine state -- so a change there inside this
#: window is the accepted residual risk; a repository that needs more declares
#: the explicit `sd-check --record-receipt` contract instead (sd:1912).
REUSE_WINDOW_SECONDS = 30 * 60
#: How long a tree-keyed receipt stands (ruling D2', sd:1912): a builder's pass
#: serves the lane's later prepare and merge of the same tree and merge base.
TREE_REUSE_WINDOW_SECONDS = 6 * 60 * 60
WRITER = "sd-local-gate"
#: The reviewed file that keys a repository's receipts by tree instead of head.
REUSE_DECLARATION = ".github/sd-gate-reuse.json"
REUSE_FIELDS = {"schema_version", "key", "reason"}
#: Optional in the declaration: `"tool": "tree"` says the gate runs this tree's own `bin/sd-check` (sd:2613).
TOOL_FIELD = "tool"
#: Names whose bytes an offload view binds (sd:2704): what a check reaches through `make` or a script.
OFFLOAD_TOOLS = ("sh", "bash", "make", "python3", "git", "cc", "c++", "clang", "cargo", "rustc", "node", "npm", "uv")
#: Tool configuration under `HOME` that an offload view binds, by path relative to `HOME`.
OFFLOAD_HOME_FILES = (".gitconfig", ".config/git/config", ".cargo/config.toml", ".npmrc", ".config/pip/pip.conf",
                      ".config/uv/uv.toml")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _content_digest(path: str | pathlib.Path) -> str:
    """sha256 of the bytes at `path`; unlike `sd_check_receipts.file_digest`, not of its mode."""
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def keyed_by_tree(tree: pathlib.Path) -> bool:
    """True when `tree` declares, in `REUSE_DECLARATION`, that its check reads no commit history.

    Anything short of exactly that declaration -- no file, a file that does not
    parse, another key, an empty reason -- keeps the head key.
    """
    try:
        value = json.loads((tree / REUSE_DECLARATION).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (isinstance(value, dict) and set(value) - {TOOL_FIELD} == REUSE_FIELDS and value["schema_version"] == 1
            and value["key"] == "tree" and isinstance(value["reason"], str) and bool(value["reason"].strip()))


def gates_itself(root: pathlib.Path, tree: pathlib.Path, pack: pathlib.Path) -> bool:
    """True when the run in `tree` is the pack gating itself (sd:2613), so the gate runs and binds the tree's own code.

    `tree` must declare the tree key with `"tool": "tree"` and carry `bin/sd-check`, and `pack`, the running
    pack's `bin/`, must belong to `root`'s repository. A foreign repository's field is ignored: its gate keeps
    running, and binding, the checkout's pack.
    """
    try:
        value = json.loads((tree / REUSE_DECLARATION).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not (keyed_by_tree(tree) and value.get(TOOL_FIELD) == "tree" and (tree / "bin" / "sd-check").is_file()):
        return False
    common = ["rev-parse", "--path-format=absolute", "--git-common-dir"]
    mine = sd_lib.git_output(common, pack)
    theirs = sd_lib.git_output(common, root)
    if not mine or not theirs:
        return False
    return pathlib.Path(mine).resolve() == pathlib.Path(theirs).resolve()


def tree_key(tree: pathlib.Path, base: str | None) -> tuple[str, str] | tuple[None, None]:
    """`(tree id, the merge base's tree id)` for a run in `tree` under a tree key, or `(None, None)` for the head key.

    The tree key needs a `base`: the merge base binds the content below the
    branch, which a docs-only scope diffs against. Its tree, not its commit,
    binds it (sd:2586), as the declaration says the check reads no history.
    """
    if base is None or not keyed_by_tree(tree):
        return None, None
    content = sd_lib.git_output(["rev-parse", "HEAD^{tree}"], tree)
    fork = fork_tree(tree, sd_lib.git_output(["merge-base", base, "HEAD"], tree))
    return (content, fork) if content and fork else (None, None)


def fork_tree(tree: pathlib.Path, fork: str | None) -> str | None:
    """The tree of the merge base `fork`, or None without one."""
    return sd_lib.git_output(["rev-parse", "--verify", "--quiet", f"{fork}^{{tree}}"], tree) if fork else None


def receipt_key(root: pathlib.Path, head: str, tree: str | None = None) -> str:
    """One key per repository and head, or per repository and `tree` under a tree key.

    Every worktree of one repository shares its git directory.
    """
    common = str(pathlib.Path(sd_lib.git_output(["rev-parse", "--path-format=absolute", "--git-common-dir"], root)
                              or str(root)).resolve())
    return KEY_PREFIX + _digest([common, head] if tree is None else [common, "tree", tree])


def gate_binding(tree: pathlib.Path, head: str, inputs: str, base: str | None, env: Mapping[str, str],
                 fork: str | None = None) -> dict[str, Any] | None:
    """What a run in `tree` would be bound to, or None when something in it cannot be named.

    `fork` is the merge base's tree under a tree key (`tree_key`); the binding then names it in place of
    `head`, and names the scope's merge base by its tree too.
    """
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
        return {"schema": 2, "reuse": "tree" if fork else "head", "head": None if fork else head, "fork": fork,
                "tree": sd_lib.git_output(["rev-parse", "HEAD^{tree}"], tree),
                "inputs": inputs, "scope": {"mode": scope.mode, "fork": fork_tree(tree, scope.fork) if fork else scope.fork,
                                             "command": list(scope.command)},
                "detection": {"source": detection.source, "commands": detection.commands},
                "tools": tools, "python": {"path": str(python), "version": sys.version,
                                           "sha256": sd_check_receipts.file_digest(python)},
                "environment_sha256": _digest(dict(env)), "threads": sd_gate_slots.thread_caps(env)}
    except Exception:  # an input that cannot be named binds nothing; the check runs
        return None


def offload_view(environment: Mapping[str, str], names: Iterable[str] = ()) -> dict[str, Any] | None:
    """The portable view of a gate's `environment` that a hub compares with a satellite's (sd:2704), or None.

    Local reuse never reads it: `gate_binding` binds the whole environment (C-17). The view leaves out `HOME`
    and `USER` and writes each `$HOME` prefix as `~`, so two logins can compare equal, and binds what they
    select instead: `path`, the `PATH` entries in order; `tools`, the bytes of each name in `OFFLOAD_TOOLS`
    and `names` resolved on that `PATH`, or None for one that does not resolve; `home_files`, the bytes of
    each `OFFLOAD_HOME_FILES` entry under `HOME`, or "absent"; `variables`, every other variable by value.
    `names` are the check's own executables; one with a relative folder lives in the tree, which `inputs` binds.
    """
    try:
        home = os.path.normpath(environment["HOME"]) if environment.get("HOME") else None
        prefixes = sorted({home, str(pathlib.Path(home).resolve())}, key=len, reverse=True) if home else []

        def portable(value: str) -> str:
            for prefix in prefixes:
                if value == prefix or value.startswith(prefix + os.sep):
                    return "~" + value[len(prefix):]
            return value

        search = environment.get("PATH", "")
        tools = {}
        for name in (*OFFLOAD_TOOLS, *names):
            if os.path.isabs(name) or not os.path.dirname(name):
                found = shutil.which(name, path=search)
                tools[name] = _content_digest(found) if found else None
        return {"path": [portable(entry) for entry in search.split(os.pathsep) if entry], "tools": tools,
                "home_files": {name: _content_digest(pathlib.Path(home, name)) if home and pathlib.Path(home, name).is_file()
                               else "absent" for name in OFFLOAD_HOME_FILES},
                "variables": {key: portable(value) for key, value in environment.items()
                              if key not in ("PATH", "HOME", "USER")}}
    except Exception:  # a view that cannot be named matches nothing; the hub runs the check
        return None


def offload_miss(theirs: Any, ours: Any) -> dict[str, Any] | None:
    """None when a satellite's offload view (`theirs`) stands for the hub's (`ours`), else the first difference.

    The difference is `{"part", "name"}`: parts compare in the order `path`, `tools`, `home_files`, `variables`,
    and `name` is the first differing `PATH` entry (the satellite's, or the hub's past the satellite's end), tool,
    file or variable. A tool the hub cannot resolve is recorded, not compared; one only the hub resolves
    misses. A view that is not one, or a part of the wrong shape, misses with no name.
    """
    if not (isinstance(theirs, dict) and isinstance(ours, dict)):
        return {"part": "view", "name": None}
    for part in ("path", "tools", "home_files", "variables"):
        other: Any = theirs.get(part)
        mine: Any = ours.get(part)
        if not isinstance(other, (list, dict)) or not isinstance(other, type(mine)):
            return {"part": part, "name": None}
        if isinstance(other, list):
            if other != mine:
                return {"part": part, "name": next(entry if entry is not None else own for entry, own
                                                   in itertools.zip_longest(other, mine) if entry != own)}
            continue
        for name in sorted(set(other) | set(mine)):
            if part == "tools" and mine.get(name) is None:
                continue
            if other.get(name) != mine.get(name):
                return {"part": part, "name": name}
    return None


def record_unless_moved(database: pathlib.Path, key: str, identity: Mapping[str, Any], after: Mapping[str, Any] | None,
                        reading: dict[str, Any], head: str) -> None:
    """Record `reading`'s pass when the binding held from before the run (`identity`) to after it (`after`).

    Otherwise `reading["receipt_skipped"]` names what moved (sd:2612), so a
    pass that leaves no receipt says why; a failed write sets `receipt_error`.
    """
    scope = (reading["report"] or {}).get("scope") or {}
    moved = [name for name in identity if after.get(name) != identity[name]] if after else ["the binding"]
    moved += ["scope mode"] if scope.get("mode") != identity["scope"]["mode"] else []
    if moved:
        reading["receipt_skipped"] = "moved during the run: " + ", ".join(moved)
        return
    try:
        reading["receipt_revision"] = record_pass(database, key, identity, reading, head)
    except Exception as error:  # the pass stands; only its reuse is lost
        reading["receipt_error"] = str(error)


def _connect(database: pathlib.Path, *, write: bool) -> Any:
    imported = sd_lib.import_sd_db()
    if imported.module is None:
        raise LookupError(imported.problem or "no sd_db library")
    return imported.module.connect(database, write=write)


def lookup(database: pathlib.Path, key: str, identity: Mapping[str, Any], now: float | None = None) -> dict[str, Any] | None:
    """The recorded success for `identity`, or None: absent, foreign, stale, older than the limit, or unreadable."""
    return examine(database, key, identity, now)[0]


def examine(database: pathlib.Path, key: str, identity: Mapping[str, Any] | None,
            now: float | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """`(found, None)` for a reusable success, else `(None, miss)` naming why (sd:2602).

    A merge gate that ran in full said nothing of why, so a binding that moved
    between prepare and merge read as a gate that never reuses. `miss` is
    `{"reason": ...}`: `no-receipt`, `failed`, `binding` with the top-level
    binding `fields` that differ, `expired` with the age and the window,
    `unbound` when `gate_binding` could not name the run, or `unreadable`.
    """
    if identity is None:
        return None, {"reason": "unbound"}
    try:
        with closing(_connect(database, write=False)) as connection:
            from sd_db import ship  # noqa: PLC0415
            revision, row = ship.read(connection, key)
        age = (time.time() if now is None else now) - float(row.get("recorded_at", "nan"))
        reading, stored = row.get("reading"), row.get("binding")
        window = TREE_REUSE_WINDOW_SECONDS if identity.get("reuse") == "tree" else REUSE_WINDOW_SECONDS
        if row.get("writer") != WRITER:
            return None, {"reason": "no-receipt"}
        if not isinstance(reading, dict) or reading.get("status") != "success":
            return None, {"reason": "failed"}
        if stored != identity:
            stored = stored if isinstance(stored, dict) else {}
            return None, {"reason": "binding", "fields": sorted(name for name in set(stored) | set(identity)
                                                                if stored.get(name) != identity.get(name))}
        if not 0 <= age <= window:
            return None, {"reason": "expired", "age_seconds": round(age), "window_seconds": window}
        return {"reading": reading, "revision": revision, "recorded_at": row["recorded_at"], "age_seconds": round(age),
                "head": row.get("head")}, None
    except Exception as error:
        return None, {"reason": "unreadable", "error": str(error)[:200]}


def record_pass(database: pathlib.Path, key: str, identity: Mapping[str, Any], reading: Mapping[str, Any],
                head: str | None = None, now: float | None = None) -> int:
    """Store a success under `key`; anything but a success is refused, and raises.

    `head` is the commit that passed, kept for provenance: under a tree key the binding does not name it.
    """
    if reading.get("status") != "success":
        raise ValueError("only a passing gate run leaves a receipt")
    with closing(_connect(database, write=True)) as connection:
        from sd_db import ship  # noqa: PLC0415
        revision, _ = ship.read(connection, key)
        return int(ship.save(connection, key, revision, {
            "writer": WRITER, "binding": dict(identity), "reading": dict(reading), "head": head,
            "recorded_at": time.time() if now is None else now}))
