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
  inputs       `sd_gate_run.gate_inputs`: the head (or tree), the parsed block of the main
               checkout's untracked `CLAUDE.local.md` (sd:2854, sd:2859) and every pack `bin/` file,
               or only those `sd-check` imports where the tree declares it
               (`pack_files`, `pack_scope`, sd:2722), so a pack upgrade reruns
               the check;
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
  machine      the host name of the machine that ran it (sd:2796).

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

A satellite widens that boundary to a second machine (sd:2704). In a
repository with `repo.satellite_gate = accept`, a satellite's recorded pass
also writes an offload receipt, `sd-gate-offload:v1:<key>`, to the hub's
database, and `sd-ship merge --satellite-gate` on the hub merges on it without
a run. The hub compares what it can recompute: the tree part of the binding,
the offload view (`offload_view`) and the pack digest. The view refuses on
every difference that can decide the result (`offload_differences`, sd:2879):
the interpreter, every bound tool's bytes, uv's user file, the thread caps and
the allowlisted variables but the slot holder's `SD_GATE_` settings.
A docs-only scope that declares `docs_tools` refuses on those tools alone. A rustup
proxy's bytes name no toolchain: the view binds `cargo -vV` and `rustc -vV`,
run in the check's tree, beside them (`tool_version`, sd:2881).
It names `PATH` order and those settings in the merge's `view_differences`. It
never compares the machine part or `environment_sha256`, which hold the
satellite's login. In an opted-in repository every gate, the hub's and the
satellite's, runs its check under `offload_environment`, only the variables
the view compares, so a variable off the allowlist cannot choose what ran on
either machine (sd:2782); a check that needs one fails on both. That
environment also pins one tool configuration and one thread cap
(`offload_pins`), so `~/.gitconfig`, `~/.npmrc`, `~/.cargo/config.toml` and
the core count, which two machines always differ in (sd:2862), reach neither
check. What the
satellite's machine holds beyond the view, and the satellite's honesty, are
trusted as the operator's own node: the trust rule in `sd_local_gate` guards
against a stale head, another pack and a moved base, not against a hostile
satellite.

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

import ast
import dataclasses
import hashlib
import itertools
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time
from contextlib import closing
from typing import Any, Iterable, Mapping

import sd_check_receipts
import sd_check_scope
import sd_gate_cache
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
#: Optional too: `"pack": "sd-check"` says the check runs no pack command but `sd-check`, so the gate binds
#: `sd-check`'s import closure, not every pack `bin/` file (`pack_scope`, sd:2722).
PACK_FIELD = "pack"
#: Names whose bytes an offload view binds (sd:2704): what a check reaches through `make` or a script. Each refuses on a
#: difference, as the check's own names do: `check_names` sees only `make`, not the `npm ci` or `uv sync` it runs (sd:2879).
#: `cargo-nextest` is what `cargo nextest` runs, which `check_names` sees as `cargo` (sd:2921).
OFFLOAD_TOOLS = ("sh", "bash", "make", "python3", "git", "cc", "c++", "clang", "cargo", "cargo-nextest", "rustc", "node",
                 "npm", "uv")
#: Names whose `-vV` build lines a view binds beside their bytes (sd:2881): a rustup proxy's bytes name no toolchain.
#: Only these two: `cargo-clippy -vV` runs clippy, and `rustdoc` and `clippy-driver` answer as `rustc` does.
VERSIONED_TOOLS = ("cargo", "rustc")
#: The `-vV` lines that name a compiler build; `os:` and the library lines follow the machine, not the compiler.
VERSION_KEYS = ("release", "commit-hash", "commit-date", "host", "LLVM version")
#: Tool configuration under `HOME` that an opted-in check still reads, by path relative to `HOME`: a view binds it and
#: refuses on it. uv has no switch that skips the user's file alone; `UV_NO_CONFIG` skips the tree's own too. git, npm,
#: pip and cargo read none (`offload_pins`, sd:2879).
OFFLOAD_HOME_FILES = (".config/uv/uv.toml",)
#: The configuration files a check reads under a folder a variable names, by variable and file, which a view binds as
#: `home_files` `$<variable>/<file>`: the pinned `CARGO_HOME` and npm global file persist in the gate's cache, where an
#: earlier check could leave a cargo `runner`, and uv reads `$XDG_CONFIG_HOME/uv/uv.toml` in place of `~/.config`'s.
OFFLOAD_VARIABLE_FILES = (("CARGO_HOME", "config.toml"), ("CARGO_HOME", "config"), ("NPM_CONFIG_GLOBALCONFIG", ""),
                          ("XDG_CONFIG_HOME", "uv/uv.toml"))
#: The thread cap every opted-in check runs under, on every machine (sd:2879): one gate's share of the cores under the
#: default slot count, so a machine on its default keeps it, and one whose share is lower refuses on `threads`.
OFFLOAD_THREADS = str(sd_gate_slots.CORES_PER_SLOT)
#: Variables an offload view compares, by name (sd:2782): `CI` and `GITHUB_ACTIONS` choose the slot count
#: (`sd_gate_slots.configured`); `LANG` the locale; `MAKEFLAGS`, `MAKEFILES` and `MFLAGS` what `make` runs; `CC` to
#: `DEVELOPER_DIR` the compiler, flags and SDK that `make`'s implicit rules and `xcrun` choose; `TZ` the clock a test
#: reads; `BASH_ENV` and `ENV` what a non-interactive shell sources; the `GIT_` names which repository `git` acts on;
#: the `XDG_` folders where the machine config, slot locks and cargo cache live (`machine_settings`, `directory`,
#: `cache_root`); `NO_COLOR` and `SD_LOCAL_GATE`, which the gate sets itself (`sd_gate_run.NO_COLOUR_ENVIRONMENT`).
OFFLOAD_VARIABLES = ("CI", "GITHUB_ACTIONS", "LANG", "NO_COLOR", "SD_LOCAL_GATE", "MAKEFLAGS", "MAKEFILES", "MFLAGS",
                     "CC", "CXX", "CPP", "AR", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "LDLIBS", "PKG_CONFIG_PATH",
                     "MACOSX_DEPLOYMENT_TARGET", "SDKROOT", "DEVELOPER_DIR", "TZ", "BASH_ENV", "ENV",
                     "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                     "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_EXEC_PATH", "GIT_CEILING_DIRECTORIES",
                     "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME")
#: ... and by prefix: `SD_GATE_` the slot holder's and gate cache's own settings, and no other `SD_` name, so a
#: check cannot read an `SD_SKIP_TESTS` on one machine only (sd:2862); `NEXTEST_`, `CARGO_` and `RUST` (`RUSTFLAGS`, `RUSTUP_TOOLCHAIN`,
#: `RUST_TEST_THREADS`) a Rust check; `PYTHON`, `PYTEST_` and `COVERAGE_` a Python one (`PYTEST_ADDOPTS` selects
#: tests); `TASK_` a Taskfile's; `DYLD_` and `LD_` the libraries every tool loads; `LC_` the locale; `UV_`, `PIP_`,
#: `NPM_CONFIG_`, `NODE_` and `GIT_CONFIG` the bound tools, whose configuration `offload_pins` sets. Any other variable,
#: such as a per-login `__CF_USER_TEXT_ENCODING`, `SSH_AUTH_SOCK` or `TMPDIR`, or a cron job's, is neither compared
#: nor stored, and no check in an opted-in repository sees it (`offload_environment`).
OFFLOAD_VARIABLE_PREFIXES = ("SD_GATE_", "NEXTEST_", "CARGO_", "RUST", "PYTHON", "PYTEST_", "COVERAGE_", "TASK_", "DYLD_",
                             "LD_", "LC_", "UV_", "PIP_", "NPM_CONFIG_", "NODE_", "GIT_CONFIG")
#: What an opted-in repository's check keeps beside those: the view binds what `HOME` and `PATH` select, and `USER` names
#: the login, as `HOME` does.
OFFLOAD_KEPT = ("HOME", "USER", "PATH")


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
    return (isinstance(value, dict) and set(value) - {TOOL_FIELD, PACK_FIELD} == REUSE_FIELDS and value["schema_version"] == 1
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


def pack_scope(root: pathlib.Path, head: str) -> bool:
    """True when `head`'s `REUSE_DECLARATION` names `"pack": "sd-check"`: its check runs no other pack command (sd:2722).

    A check may run any pack command, such as `sd-docs-lint` from `PATH`, and the binding names only the
    command it starts. So the gate binds every pack `bin/` file unless the reviewed tree says otherwise;
    anything short of exactly that field, under schema 1, keeps every file.
    """
    try:
        value = json.loads(sd_lib.git_output(["show", f"{head}:{REUSE_DECLARATION}"], root) or "")
    except ValueError:
        return False
    return isinstance(value, dict) and value.get("schema_version") == 1 and value.get(PACK_FIELD) == "sd-check"


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
                 fork: str | None = None, mode: str = "whole") -> dict[str, Any] | None:
    """What a run in `tree` would be bound to, or None when something in it cannot be named.

    `fork` is the merge base's tree under a tree key (`tree_key`); the binding then names it in place of
    `head`, and names the scope's merge base by its tree too. It is the union of `tree_binding`, which a
    hub compares with a satellite's (sd:2704), and `machine_binding`, which it does not, plus
    `environment_mode`, `offload_run`'s `mode`: a pass under one mode never stands for a run under another (sd:2782).
    """
    part = tree_binding(tree, head, inputs, base, fork)
    if part is None:
        return None
    try:
        return {**part, **machine_binding(tree, binding_commands(part), env), "environment_mode": mode}
    except Exception:  # an input that cannot be named binds nothing; the check runs
        return None


#: The binding fields `tree_binding` names: what a hub compares with a satellite's offload receipt.
TREE_FIELDS = ("schema", "reuse", "head", "fork", "tree", "inputs", "scope", "detection")


def tree_binding(tree: pathlib.Path, head: str, inputs: str, base: str | None,
                 fork: str | None = None) -> dict[str, Any] | None:
    """The `TREE_FIELDS` of `gate_binding`: pack code over the tree, no tool resolved; None as there."""
    try:
        detection = sd_lib.detect_entrypoints(tree)
        scope = sd_check_scope.decide(tree, base, detection)
        part = {"schema": 2, "reuse": "tree" if fork else "head", "head": None if fork else head, "fork": fork,
                "tree": sd_lib.git_output(["rev-parse", "HEAD^{tree}"], tree),
                "inputs": inputs, "scope": {"mode": scope.mode, "fork": fork_tree(tree, scope.fork) if fork else scope.fork,
                                             "command": list(scope.command),
                                             **({"tools": list(scope.tools)} if scope.tools is not None else {})},
                "detection": {"source": detection.source, "commands": detection.commands}}
    except Exception:  # an input that cannot be named binds nothing; the check runs
        return None
    return part if binding_commands(part) else None


def binding_commands(part: Mapping[str, Any]) -> list[list[str]]:
    """The argv of each command a binding's run executes: the docs command alone in a docs-only scope."""
    if part["scope"]["mode"] == sd_check_scope.DOCS_ONLY:
        return [list(part["scope"]["command"])]
    return [list(argv) for argv in part["detection"]["commands"].values()]


def check_names(part: Mapping[str, Any]) -> list[str]:
    """The executable each of `part`'s commands names, and a docs-only scope's `docs_tools`: what an offload view binds beside `OFFLOAD_TOOLS`."""
    return [argv[0] for argv in binding_commands(part)] + list(part["scope"].get("tools") or [])


def machine_binding(tree: pathlib.Path, commands: list[list[str]], env: Mapping[str, str]) -> dict[str, Any]:
    """`tools`, `python`, `environment_sha256`, `threads` and `machine`: this machine's half of `gate_binding`; raises when a tool does not resolve.

    `machine` is the host name, as `satellite_identity` writes it: a satellite's own receipts land in the hub's
    database, under the hub's key when the login and checkout path match, and the hub never reuses one (sd:2796).
    """
    tools = [sd_check_receipts.tool_identity(argv[0], env, tree) for argv in commands]
    for tool in tools:  # the worktree is temporary; name a tool inside it by its place in the tree
        path = pathlib.Path(tool["path"])
        if path.is_relative_to(tree.resolve()):
            tool["path"] = "tree:" + str(path.relative_to(tree.resolve()))
    python = pathlib.Path(sys.executable).resolve()
    return {"tools": tools, "python": {"path": str(python), "version": sys.version,
                                       "sha256": sd_check_receipts.file_digest(python)},
            "environment_sha256": _digest(dict(env)), "threads": sd_gate_slots.thread_caps(env),
            "machine": socket.gethostname()}


def offload_view(environment: Mapping[str, str], names: Iterable[str] = (),
                 tree: pathlib.Path | None = None) -> dict[str, Any] | None:
    """The portable view of a gate's `environment` that a hub compares with a satellite's (sd:2704), or None.

    Local reuse never reads it: `gate_binding` binds the whole environment (C-17). The view writes each `$HOME`
    prefix as `~`, so two logins can compare equal, and binds what `HOME` and `PATH` select: `path`, the `PATH`
    entries in order; `tools`, the bytes of each name in `OFFLOAD_TOOLS`
    and `names` resolved on that `PATH`, a `cargo-` name in `$CARGO_HOME/bin` first, as cargo does, or None for one that does not resolve; `python`, the bytes and version of
    `sys.executable`, the interpreter that runs `sd-check` whatever `PATH` says; `home_files`, the bytes of
    each `OFFLOAD_HOME_FILES` entry under `HOME` and of each `OFFLOAD_VARIABLE_FILES` entry, or "absent"; `threads`, `sd_gate_slots.thread_caps`, which
    `machine_binding` binds too; `variables`, the sha256 of each `offload_variable`'s value. A variable outside
    that list is not compared, and neither its value nor its digest reaches the hub (sd:2782).
    `names` are the check's own executables; one with a relative folder lives in the tree, which `inputs` binds.
    A `VERSIONED_TOOLS` name binds `tool_version` in `tree`, the check's worktree, beside its own bytes, and
    `resolution` names its release line, or `path` where `-vV` answered nothing (sd:2881).
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
        cargo_bin = os.path.join(environment["CARGO_HOME"], "bin") if environment.get("CARGO_HOME") else None
        tools, resolution = {}, {}
        for name in (*OFFLOAD_TOOLS, *names):
            if os.path.isabs(name) or not os.path.dirname(name):
                # cargo looks for a subcommand in `$CARGO_HOME/bin` before `PATH` (sd:2921).
                found = os.pathsep.join([cargo_bin, search]) if cargo_bin and name.startswith("cargo-") else search
                tools[name], way = view_tool(name, found, environment, tree)
                if way:
                    resolution[name] = way
        return {"path": [portable(entry) for entry in search.split(os.pathsep) if entry], "tools": tools,
                "resolution": resolution,
                "python": {"sha256": _content_digest(pathlib.Path(sys.executable).resolve()), "version": sys.version},
                "home_files": {**{name: _content_digest(pathlib.Path(home, name)) if home and pathlib.Path(home, name).is_file()
                                  else "absent" for name in OFFLOAD_HOME_FILES},
                               **{f"${variable}" + (f"/{name}" if name else ""): file_state(environment.get(variable), name)
                                  for variable, name in OFFLOAD_VARIABLE_FILES}},
                "threads": sd_gate_slots.thread_caps(environment),
                "variables": {key: hashlib.sha256(portable(value).encode()).hexdigest() for key, value in environment.items()
                              if offload_variable(key)}}
    except Exception:  # a view that cannot be named matches nothing; the hub runs the check
        return None


def file_state(folder: str | None, name: str) -> str:
    """sha256 of `name` under `folder`, or `folder` itself for no `name`; "absent" for no file or no `folder`."""
    path = pathlib.Path(folder, name) if folder else None
    return _content_digest(path) if path is not None and path.is_file() else "absent"


def view_tool(name: str, search: str, environment: Mapping[str, str],
              tree: pathlib.Path | None) -> tuple[str | None, str | None]:
    """`(digest, resolution)` of `name` on `search`: None for one that does not resolve, and `resolution` None outside `VERSIONED_TOOLS`."""
    found = shutil.which(name, path=search)
    if not found:
        return None, None
    digest = _content_digest(found)
    if name not in VERSIONED_TOOLS:
        return digest, None
    version = tool_version(found, environment, tree) if tree else None
    if version is None:
        return digest, "path"
    return f"{digest} {hashlib.sha256(version.encode()).hexdigest()}", version.splitlines()[0]


def tool_version(found: str, environment: Mapping[str, str], tree: pathlib.Path) -> str | None:
    """The first line and `VERSION_KEYS` lines of `found -vV`, run as the gate runs it; None when it fails (sd:2881).

    It runs the `PATH` tool in `tree` under the gate's `environment`, so a wrapper's settings and the tree's
    `rust-toolchain.toml` choose the toolchain as they do for the check; `RUSTUP_AUTO_INSTALL=0` installs nothing.
    Threat model: the hub and the satellite are one operator's machines. This catches accidental toolchain drift,
    such as a Homebrew `cargo` ahead of the rustup proxy on `PATH`; it does not defend against a wrapper built to
    lie. One commit-hash is one compiler source.
    """
    try:
        result = subprocess.run([found, "-vV"], cwd=tree, env={**environment, "RUSTUP_AUTO_INSTALL": "0"}, text=True,
                                capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = result.stdout.splitlines()
    if result.returncode != 0 or not lines:
        return None
    return "\n".join([lines[0], *(line for line in lines[1:] if line.split(":", 1)[0] in VERSION_KEYS)])


def offload_variable(name: str) -> bool:
    """`name` is one an offload view compares: in `OFFLOAD_VARIABLES` or under a prefix, and named like no credential."""
    upper = name.upper()
    # `GIT_CONFIG_KEY_<n>` names a config key, not a credential, and `GIT_CONFIG_COUNT` fails git without it.
    return ((upper in OFFLOAD_VARIABLES or upper.startswith(OFFLOAD_VARIABLE_PREFIXES))
            and not sd_check_receipts.SECRET.search(upper.removeprefix("GIT_CONFIG_KEY_")))


def gate_path(search: str, root: pathlib.Path | None) -> list[str]:
    """`search`'s absolute entries, each resolved, that name a folder outside `root` and no venv `bin`.

    `sd_gate_run.gate_environment` cuts every gate's `PATH` to these, and `link_cargo_subcommands` the caller's cargo `bin`.
    """
    top = root.resolve() if root is not None else None
    resolved = [pathlib.Path(entry).resolve() for entry in search.split(os.pathsep) if entry and os.path.isabs(entry)]
    return [str(path) for path in resolved if path.is_dir() and not (top and path.is_relative_to(top))
            and not (path.parent / "pyvenv.cfg").is_file()]


def offload_environment(environment: Mapping[str, str], root: pathlib.Path | None = None) -> dict[str, str]:
    """`environment` cut to what an offload view compares, plus `OFFLOAD_KEPT` (sd:2782), then `offload_pins`.

    It is the environment of every gate in an opted-in repository (`offload_run`). The view compares an
    allowlist, so a variable off it could choose what a satellite's check ran and still stand for the hub's:
    `SKIP_TESTS=1` skips tests, `RUN_INTEGRATION=1` adds them. Dropped on both machines, it chooses nothing.
    A check that needs a dropped variable, a credential among them, fails on every machine; such a
    repository does not opt in until the variable is allowlisted. It also links the caller's bound cargo
    subcommands into the pinned `CARGO_HOME` (`link_cargo_subcommands`), `root` being the checkout.
    """
    kept = {key: value for key, value in environment.items() if key in OFFLOAD_KEPT or offload_variable(key)}
    pins = offload_pins(kept)
    link_cargo_subcommands(kept, pathlib.Path(pins["CARGO_HOME"], "bin"), root)
    return {**kept, **pins}


def link_cargo_subcommands(environment: Mapping[str, str], pinned: pathlib.Path, root: pathlib.Path | None) -> None:
    """Link each `cargo-` name in `OFFLOAD_TOOLS` from the caller's `CARGO_HOME/bin`, `~/.cargo/bin` by default,
    into `pinned`, the pinned `CARGO_HOME/bin`, where cargo looks first and the view binds it (sd:2921).

    Only bound names: a whole folder on `PATH` would run subcommands the view does not bind, such as
    `cargo-llvm-cov`, which stay unavailable. The caller's folder passes `gate_path`, so one that is relative or
    inside `root` links nothing. A link the caller no longer backs is removed; a link already right is kept.
    """
    own = environment.get("CARGO_HOME") or (os.path.join(environment["HOME"], ".cargo") if environment.get("HOME") else None)
    if not own or pathlib.Path(own, "bin").resolve() == pinned.resolve():  # already pinned: nothing to link
        return
    folders = gate_path(os.path.join(own, "bin"), root)
    # ponytail: one pinned folder per machine, so two concurrent gates from callers with different `CARGO_HOME`s
    # swap each other's link; give each caller its own pinned `bin` if that ever happens.
    for name in (tool for tool in OFFLOAD_TOOLS if tool.startswith("cargo-")):
        target = pathlib.Path(folders[0], name) if folders and pathlib.Path(folders[0], name).is_file() else None
        link = pinned / name
        try:
            if target is None:
                if link.is_symlink():
                    link.unlink()
            elif not (link.is_symlink() and os.readlink(link) == str(target)):
                pinned.mkdir(parents=True, exist_ok=True)
                spare = pinned / f".{name}.{os.getpid()}"
                spare.unlink(missing_ok=True)
                spare.symlink_to(target)
                os.replace(spare, link)  # atomic: a concurrent gate sees the old link or the new one
        except OSError:  # the check then finds no such subcommand and fails, as before sd:2921
            pass


def offload_pins(environment: Mapping[str, str]) -> dict[str, str]:
    """What every opted-in check runs under whatever the caller set: one tool configuration and one thread cap (sd:2879).

    Two machines differ in `~/.gitconfig`, `~/.npmrc` and `~/.cargo/config.toml`, and in their core counts, so a
    view that bound those never matched (sd:2862). git, npm and pip then read no user or system file, and cargo
    reads its configuration from a `CARGO_HOME` in the gate's cache folder, whose files the view binds
    (`OFFLOAD_VARIABLE_FILES`), since a check could write one there: a check that needs
    a git identity sets its own. npm refuses one file as both its user and its global configuration, so the global
    one is a path in that folder too. `sd_gate_slots.CPU_VARIABLES` read `OFFLOAD_THREADS`, which a holder lowers
    only on a machine whose share of the cores is smaller.
    """
    folder = sd_gate_cache.cache_root(environment) / "tool-config"
    return {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "NPM_CONFIG_USERCONFIG": os.devnull,
            "NPM_CONFIG_GLOBALCONFIG": str(folder / "npmrc"), "PIP_CONFIG_FILE": os.devnull,
            "CARGO_HOME": str(folder / "cargo"), **dict.fromkeys(sd_gate_slots.CPU_VARIABLES, OFFLOAD_THREADS)}


def opted_in(database: pathlib.Path | None, root: pathlib.Path) -> bool:
    """`root`'s repository has `repo.satellite_gate = accept` in `database`; no database or any fault is False."""
    if database is None:
        return False
    try:
        with closing(_connect(database, write=False)) as connection:
            return sd_lib.repo_satellite_gate(connection, root) == "accept"
    except Exception:  # the gate runs as before opt-in; `environment_mode` keeps its pass from an opted-in gate
        return False


def offload_run(database: pathlib.Path | None, root: pathlib.Path, environment: Mapping[str, str], *, record: bool,
                offload: str | None) -> tuple[dict[str, str], str]:
    """`(environment, mode)` for a gate run in `root`; the binding names `mode` (sd:2782).

    In an opted-in repository (`opted_in`) every gate runs under `offload_environment`: the hub's own, the
    merge gate, local reuse and a satellite's. Both machines then run the same check by construction.
    `mode` is `offload` for a recording satellite run, whose pass keeps its view and writes an offload row,
    `allowlist` for any other gate there, and `whole` elsewhere, with the whole environment as before.
    """
    if not opted_in(database, root):
        return dict(environment), "whole"
    try:
        satellite = served_hub(database) is not None
    except Exception:  # `record_offload` reports the fault; this run keeps no view
        satellite = False
    return offload_environment(environment, root), "offload" if record and offload != "require" and satellite else "allowlist"


def start_view(gated: Worktree, identity: dict[str, Any] | None) -> dict[str, Any] | None:
    """The offload view an `offload` run starts from, which its receipts keep; None for any other mode."""
    return gated.view(identity) if gated.mode == "offload" and identity else None


def deciding_tools(part: Mapping[str, Any] | None) -> tuple[str, ...]:
    """The fixed tools a hub refuses on beside `check_names`: none where a docs-only scope declares `docs_tools` (sd:2881).

    Those name every tool its docs command reaches, and `check_names` carries them. A docs scope that declares
    none may reach a compiler through `make`, as `cargo doc` does, so it keeps `OFFLOAD_TOOLS`.
    """
    return () if part is not None and part["scope"].get("tools") is not None else OFFLOAD_TOOLS


def offload_differences(theirs: Any, ours: Any, names: Iterable[str] = (),
                        tools: Iterable[str] = OFFLOAD_TOOLS) -> list[dict[str, Any]]:
    """Every difference between a satellite's offload view (`theirs`) and the hub's (`ours`), as `{"part", "name", "refuses"}`.

    Parts compare in the order `path`, `tools`, `python`, `home_files`, `threads`, `variables`. Every difference
    refuses (sd:2879) but two that choose nothing the check runs: the `PATH` order, whose tools compare by bytes, and
    the slot holder's `SD_GATE_` settings; and a tool outside `tools` (`deciding_tools`) and `names` (the check's own
    executables). `name` is the first differing `PATH` entry (the satellite's, or the
    hub's past the satellite's end), tool, `python` field, file, thread variable or variable. A tool the hub cannot
    resolve is not compared. A view that is not one, or a part of the wrong shape or missing, differs with no name.
    """
    if not (isinstance(theirs, dict) and isinstance(ours, dict)):
        return [{"part": "view", "name": None, "refuses": True}]
    deciding = {*tools, *names}

    def refuses(part: str, name: str | None) -> bool:
        if part == "tools":
            return name is None or name in deciding
        if part == "variables":
            return name is None or not name.startswith("SD_GATE_")
        return part != "path"

    found = []
    for part in ("path", "tools", "python", "home_files", "threads", "variables"):
        other: Any = theirs.get(part)
        mine: Any = ours.get(part)
        if not isinstance(other, (list, dict)) or not isinstance(other, type(mine)):
            found.append({"part": part, "name": None, "refuses": refuses(part, None)})
        elif isinstance(other, list):
            if other != mine:
                found.append({"part": part, "name": next(entry if entry is not None else own for entry, own
                                                         in itertools.zip_longest(other, mine) if entry != own),
                              "refuses": False})
        else:
            found += [{"part": part, "name": name, "refuses": refuses(part, name)} for name in sorted(set(other) | set(mine))
                      if not (part == "tools" and mine.get(name) is None) and other.get(name) != mine.get(name)]
    return found


def offload_miss(theirs: Any, ours: Any, names: Iterable[str] = (),
                 tools: Iterable[str] = OFFLOAD_TOOLS) -> dict[str, Any] | None:
    """None when a satellite's offload view (`theirs`) stands for the hub's (`ours`), else its first refusing difference."""
    return next(({"part": miss["part"], "name": miss["name"]} for miss in offload_differences(theirs, ours, names, tools)
                 if miss["refuses"]), None)


# The offload receipt (sd:2704): a satellite's pass, keyed so the hub computes the same key.

OFFLOAD_PREFIX = "sd-gate-offload:v1:"
OFFLOAD_WRITER = "sd-satellite-gate"
#: How long an offload receipt stands, under either key (ruling Q3).
OFFLOAD_WINDOW_SECONDS = TREE_REUSE_WINDOW_SECONDS
#: How far ahead of the hub's clock a satellite's `recorded_at` may be.
OFFLOAD_SKEW_SECONDS = 300
#: The pack digest the hub's lane publishes, which a satellite compares before its run; `<slug>` follows.
PACK_PREFIX = "sd-lane-pack:v1:"
#: The published row's `pack_bins` keys, each `pack_bin`'s `closure` argument (`pack_scope`'s answer) (sd:2823).
PACK_SCOPES = {"every": False, "closure": True}


@dataclasses.dataclass(frozen=True)
class Worktree:
    """A gate's worktree `tree` of `head` in `root`, and what keys and binds its receipts.

    `content` and `fork` are `tree_key`'s answer, `own` is `gates_itself`'s, `inputs` is `gate_inputs`'s,
    `environment` is the gate's own (`sd_gate_run.gate_environment`), and `mode` is `offload_run`'s.
    """

    root: pathlib.Path
    tree: pathlib.Path
    head: str
    base: str | None
    environment: Mapping[str, str]
    content: str | None
    fork: str | None
    own: bool
    inputs: str
    mode: str = "whole"

    def view(self, part: Mapping[str, Any]) -> dict[str, Any] | None:
        """This environment's offload view, binding the executables of `part`'s commands too."""
        return offload_view(self.environment, check_names(part), self.tree)


def repository_slug(root: pathlib.Path) -> str | None:
    """`owner/name` of `root`'s origin, lower case, as `sd-ship` names the repository; None off GitHub."""
    match = sd_lib.GITHUB_ORIGIN.fullmatch(sd_lib.git_output(["config", "--get", "remote.origin.url"], root) or "")
    return f"{match[1]}/{match[2]}".lower() if match else None


def offload_key(slug: str, head: str, tree: str | None = None) -> str:
    """One key per repository slug and head, or slug and `tree` under a tree key: the same on every machine."""
    return OFFLOAD_PREFIX + _digest([slug, head] if tree is None else [slug, "tree", tree])


def pack_bin(own: bool = False, closure: bool = False) -> str:
    """sha256 of the pack `bin/` files `gate_inputs` hashes, or "tree" when the run gates its own tree (sd:2613).

    `closure` is `pack_scope`'s answer for the gated head.
    """
    import sd_gate_run  # noqa: PLC0415 -- it imports this module

    if own:
        return "tree"
    digest = hashlib.sha256()
    for path in pack_files(sd_gate_run.BIN, closure):
        digest.update(f"pack {path.name}\n".encode() + path.read_bytes())
    return digest.hexdigest()


#: Where `pack_files`' closure starts: `sd-check`, which runs the check, and `sd_gate_run`, the gate that sets up
#: its worktree and environment (`cargo_environment`) through `sd_gate_receipts` and `sd_gate_cache` (sd:2722).
CLOSURE_ROOTS = ("sd-check", "sd_gate_run.py")


def pack_files(folder: pathlib.Path, closure: bool = False) -> list[pathlib.Path]:
    """The pack `bin/` files in `folder` a run depends on; `gate_inputs` and `pack_bin` hash these.

    Every one, or with `closure` (`pack_scope`) only what each of `CLOSURE_ROOTS` imports, at any depth, or loads
    with `sd_lib.sibling` (sd:2722): the run then executes nothing else from the pack, so a landing elsewhere in
    `bin/` voids no receipt. A closure that cannot be read, such as a file that does not parse, is every pack file.
    """
    every = [path for path in sorted(folder.iterdir()) if path.is_file() and (path.suffix == ".py" or path.name.startswith("sd-"))]
    if not closure:
        return every
    found: set[pathlib.Path] = set()
    todo = [folder / name for name in CLOSURE_ROOTS]
    try:
        while todo:
            path = todo.pop()
            if path not in found:
                found.add(path)
                todo += [folder / name for name in loaded_names(path) if (folder / name).is_file()]
    except (OSError, SyntaxError, ValueError):
        return every
    return [path for path in every if path in found]


def loaded_names(path: pathlib.Path) -> list[str]:
    """The `bin/` file names the Python file at `path` imports or loads with `sd_lib.sibling`; raises when it does not parse."""
    names = []
    for node in ast.walk(ast.parse(path.read_bytes(), str(path))):
        if isinstance(node, ast.Import):
            names += [f"{alias.name.partition('.')[0]}.py" for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names.append(f"{node.module.partition('.')[0]}.py")
        elif (isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", None)) == "sibling"
              and len(node.args) == 2 and isinstance(node.args[1], ast.Constant)):
            names.append(str(node.args[1].value))
    return names


def pack_rev() -> str | None:
    """The running pack checkout's commit, for a refusal's text only."""
    return sd_lib.git_output(["rev-parse", "HEAD"], pathlib.Path(__file__).resolve().parent)


def served_hub(database: pathlib.Path | None) -> str | None:
    """The hub serving `database` to this satellite as `host:port`, or None on the hub or with an older `sd_db`.

    Raises what `served_by` raises, such as on a malformed hub configuration; each caller keeps its pass (sd:2776).
    """
    served_by = getattr(getattr(sd_lib.import_sd_db().module, "database", None), "served_by", None)
    return served_by(database) if served_by is not None and database is not None else None


def satellite_identity() -> dict[str, Any]:
    """This machine as an offload row names it: the tailnet owner login and IPv4 address, and the host name."""
    node: dict[str, Any] = {"hostname": socket.gethostname()}
    try:
        sd_lib.import_sd_db()
        from sd_db.tailnet import this_node  # noqa: PLC0415

        this = this_node()
        node.update(login=this.login, address=str(this.address))
    except Exception as error:  # the row still stands; it says why it names no node
        node["error"] = f"{type(error).__name__}: {error}"[:300]
    return node


def read_offload(database: pathlib.Path | None, key: str) -> tuple[int, dict[str, Any]]:
    """`(revision, row)` at `key`; the row is empty when none was written. Raises on a read fault."""
    with closing(_connect(database, write=False)) as connection:
        from sd_db import ship  # noqa: PLC0415
        revision, row = ship.read(connection, key)
    return revision, row if isinstance(row, dict) else {}


def pack_warning(database: pathlib.Path | None, root: pathlib.Path, head: str, own: bool) -> str | None:
    """On an opted-in satellite, warn on stderr why the hub's merge would refuse this run's receipt as another pack.

    It compares with the digest the hub's lane last published. A warning only: the hub's pack can still
    move after the run, and its merge compares again (clause 6). Any fault warns of nothing.
    """
    try:
        if served_hub(database) is None or (slug := repository_slug(root)) is None:
            return None
        with closing(_connect(database, write=False)) as connection:
            if sd_lib.repo_satellite_gate(connection, root) != "accept":
                return None
            from sd_db import ship  # noqa: PLC0415
            _, published = ship.read(connection, PACK_PREFIX + slug)
    except Exception:
        return None
    published = published if isinstance(published, dict) else {}
    closure = pack_scope(root, head)
    # The hub's digest under this head's scope, as its merge compares (sd:2823); an older hub publishes one, under its own.
    bins = published.get("pack_bins")
    theirs = bins.get("closure" if closure else "every") if isinstance(bins, dict) else published.get("pack_bin")
    ours = pack_bin(own, closure)
    if not theirs or theirs == ours:
        return None
    warning = (f"this pack's bin/ digest {ours[:12]} (rev {str(pack_rev())[:12]}) is not the hub's {str(theirs)[:12]} "
               f"(rev {str(published.get('pack_rev'))[:12]}, published {published.get('published_at')}): the hub will refuse "
               "this receipt as satellite_pack_mismatch. Bring both packs to one revision, then run sd gate check again")
    print(f"sd gate: warning: {warning}", file=sys.stderr)
    return warning


def record_offload(database: pathlib.Path | None, run: Worktree, identity: Mapping[str, Any], reading: Mapping[str, Any],
                   view: dict[str, Any] | None, recorded_at: float | None = None) -> dict[str, Any]:
    """On a satellite, write this pass's offload row to the hub; the fields the gate's result carries.

    Nothing on the hub, `{"offload_skipped"}` where `repo.satellite_gate` is not `accept`, `{"offload"}`
    naming the row, or `{"offload_error"}` when the hub did not take it: the pass stands either way.
    `view` is the offload view the pass started from (`start_view`), never one taken now: a reuse writes the
    one its receipt kept. `recorded_at` is a reused pass's own time; a reuse leaves alone only the same row.
    """
    import sd_gate_run  # noqa: PLC0415 -- it imports this module

    try:
        if (hub := served_hub(database)) is None:
            return {}
        slug = repository_slug(run.root)
        if slug is None:
            raise LookupError("origin names no github.com repository, so no hub can compute the key")
        key, local = offload_key(slug, run.head, run.content), sd_gate_run.untracked_local_block(run.root)
        with closing(_connect(database, write=True)) as connection:
            if sd_lib.repo_satellite_gate(connection, run.root) != "accept":
                return {"offload_skipped": "repo.satellite_gate is not accept for this repository"}
            if view is None:
                raise LookupError("the pass kept no offload view, so it stands for no hub; run the check again")
            from sd_db import ship  # noqa: PLC0415
            revision, existing = ship.read(connection, key)
            row = {"writer": OFFLOAD_WRITER, "satellite": satellite_identity(), "hub": hub, "binding": dict(identity),
                   "offload_view": view, "pack_bin": pack_bin(run.own, pack_scope(run.root, run.head)), "pack_rev": pack_rev(),
                   "local_block": sd_lib.local_policy_digest(local), "reading": dict(reading),
                   "head": run.head, "recorded_at": time.time() if recorded_at is None else recorded_at}
            # Only the same row stands; any other is one the hub may refuse. The store adds `protocol`.
            if recorded_at is not None and isinstance(existing, dict) and {name: existing.get(name) for name in row} == row:
                return {"offload": {"key": key, "revision": revision, "hub": hub, "written": False}}
            written = int(ship.save(connection, key, revision, row))
    except Exception as error:  # the pass stands; only the hub's use of it is lost
        return {"offload_error": f"{type(error).__name__}: {error}"[:300]}
    return {"offload": {"key": key, "revision": written, "hub": hub, "written": True}}


def examine_offload(database: pathlib.Path | None, run: Worktree,
                    now: float | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """The hub's clauses 3 to 7 of the trust rule (design.md), in order: `(accepted, None)` or `(None, refusal)`.

    `refusal` is `{"code", "reason"}`. The hub compares the tree part of the binding, the offload view and
    the pack digest, never the satellite's machine part or its `environment_sha256` (C-17), and runs nothing.
    """
    slug = repository_slug(run.root)
    try:
        revision, row = read_offload(database, offload_key(slug or "", run.head, run.content))
    except Exception as error:
        return None, {"code": "satellite_receipt_missing", "reason": f"the offload receipt could not be read: {error}"[:300]}
    if slug is None or not row:
        return None, {"code": "satellite_receipt_missing", "reason": f"no offload receipt at {run.head[:12]} for {slug}"}
    part = tree_binding(run.tree, run.head, run.inputs, run.base, run.fork)
    view = run.view(part) if part else None
    hub_now = time.time() if now is None else now
    refused = (invalid_offload(row, revision) or pack_mismatch(row, run.own, pack_scope(run.root, run.head)) or binding_mismatch(row, part, view, run.mode)
               or expired_offload(row, hub_now))
    if refused:
        return None, refused
    unresolved = sorted(name for name, digest in (view or {})["tools"].items()
                        if digest is None and row["offload_view"]["tools"].get(name) is not None)
    recorded = [{"part": miss["part"], "name": miss["name"]} for miss in offload_differences(row["offload_view"], view)]
    return {"reading": row["reading"], "revision": revision, "satellite": row["satellite"], "hub": row.get("hub"),
            "recorded_at": row["recorded_at"], "age_seconds": round(hub_now - float(row["recorded_at"])),
            "head": row.get("head"), "unresolved_tools": unresolved, "view_differences": recorded,
            "pack_bin": row["pack_bin"]}, None


def standing_offload(database: pathlib.Path | None, root: pathlib.Path, head: str,
                     now: float | None = None) -> tuple[str, int, dict[str, Any]]:
    """On a satellite, the offload row its prepare may post `sd/local-gate` from: `(key, revision, row)`.

    The row stands when it is a success (clause 4), made by this pack (clause 6), within its window
    (clause 7), and bound to the inputs of `root` at `head`, which carry `CLAUDE.local.md` and the pack.
    The tree key counts only while `root` declares it. Raises LookupError naming why no row stands.
    """
    import sd_gate_run  # noqa: PLC0415 -- it imports this module

    slug = repository_slug(root)
    if slug is None:
        raise LookupError("origin names no github.com repository")
    tree = sd_lib.git_output(["rev-parse", f"{head}^{{tree}}"], root) if keyed_by_tree(root) else None
    reasons = []
    for content in (None, tree) if tree else (None,):
        key = offload_key(slug, head, content)
        revision, row = read_offload(database, key)
        own = row.get("pack_bin") == "tree"
        binding = row.get("binding")
        binding = binding if isinstance(binding, dict) else {}
        inputs = sd_gate_run.gate_inputs(root, head, content, own)
        refused = (({"reason": f"no row at {key}"} if not row else None) or invalid_offload(row, revision)
                   or pack_mismatch(row, own, pack_scope(root, head)) or expired_offload(row, time.time() if now is None else now)
                   or (None if binding.get("inputs") == inputs else
                       {"reason": f"the row binds inputs {binding.get('inputs')}, not this checkout's {inputs}"}))
        if refused is None:
            return key, revision, row
        reasons.append(refused["reason"])
    raise LookupError("; ".join(reasons))


def names_node(satellite: Any) -> bool:
    """`satellite`, as `satellite_identity` writes it, names a host and its tailnet login and address (sd:2782)."""
    return isinstance(satellite, dict) and all(isinstance(satellite.get(name), str) and satellite[name]
                                               for name in ("hostname", "login", "address"))


def invalid_offload(row: Mapping[str, Any], revision: int) -> dict[str, str] | None:
    """Clause 4: the row is a `sd-satellite-gate` success that names its satellite's host and tailnet identity."""
    reading, satellite = row.get("reading"), row.get("satellite")
    if not (row.get("writer") == OFFLOAD_WRITER and isinstance(reading, dict) and reading.get("status") == "success"):
        return {"code": "satellite_receipt_invalid",
                "reason": f"the offload receipt at revision {revision} is not a {OFFLOAD_WRITER} success"}
    if names_node(satellite):
        return None
    error = satellite.get("error") if isinstance(satellite, dict) else None
    return {"code": "satellite_unidentified", "reason": f"the offload receipt at revision {revision} names no satellite "
            f"host with a tailnet login and address{f': {error}' if error else ''}"[:300]}


def pack_mismatch(row: Mapping[str, Any], own: bool, closure: bool = False) -> dict[str, str] | None:
    """Clause 6, the named case of clause 5: the satellite's pack `bin/` digest is the hub's."""
    ours, theirs = pack_bin(own, closure), row.get("pack_bin")
    if theirs == ours:
        return None
    return {"code": "satellite_pack_mismatch", "reason": f"the satellite's pack bin/ digest {theirs} "
            f"(rev {row.get('pack_rev')}) is not the hub's {ours} (rev {pack_rev()})"}


def binding_mismatch(row: Mapping[str, Any], part: Mapping[str, Any] | None,
                     view: Mapping[str, Any] | None, mode: str) -> dict[str, str] | None:
    """Clause 5: both runs had the offload environment, each of `TREE_FIELDS` equals the hub's `part`, and the views match.

    `mode` is the hub run's `environment_mode`. `whole` refuses: the hub's check would see variables the
    satellite's never did, and an opt-in read fault answers `whole` too (sd:2782). The row's binding must
    name `offload`, the mode of the run that wrote it.
    """
    stored = row.get("binding")
    stored = stored if isinstance(stored, dict) else {}
    if mode == "whole":
        return {"code": "satellite_binding", "reason": "the hub's gate ran under the whole environment, not the offload "
                "environment: on the hub, repo.satellite_gate read as off or could not be read"}
    if stored.get("environment_mode") != "offload":
        return {"code": "satellite_binding",
                "reason": f"the satellite's receipt binds environment_mode {stored.get('environment_mode')}, not offload"}
    fields = list(TREE_FIELDS) if part is None else [name for name in TREE_FIELDS if stored.get(name) != part.get(name)]
    miss = offload_miss(row.get("offload_view"), view, check_names(part) if part else (), deciding_tools(part))
    if fields:
        named = f"binding fields {', '.join(fields)}"
    elif miss is not None:
        named = f"offload view part {miss['part']} at {miss['name']}"
        ways = [side.get("resolution", {}).get(miss["name"]) if isinstance(side, dict) and isinstance(side.get("resolution"), dict)
                else None for side in (row.get("offload_view"), view)]
        if miss["part"] == "tools" and ways != [None, None]:  # how each side found it (sd:2881)
            named += f" (satellite via {ways[0] or 'unrecorded'}, hub via {ways[1] or 'unrecorded'})"
    else:
        return None
    return {"code": "satellite_binding", "reason": f"the satellite's receipt differs from the hub's in {named}"}


def expired_offload(row: Mapping[str, Any], now: float) -> dict[str, str] | None:
    """Clause 7: the row's age on the hub's clock is within the window, and at most the skew in the future."""
    try:
        age = now - float(row.get("recorded_at", "nan"))
    except (TypeError, ValueError):
        age = float("nan")
    if -OFFLOAD_SKEW_SECONDS <= age <= OFFLOAD_WINDOW_SECONDS:
        return None
    return {"code": "satellite_receipt_expired", "reason": f"the offload receipt was recorded at {row.get('recorded_at')} "
            f"on the satellite's clock and it is {now:.0f} on the hub's: {age:.0f} s, outside "
            f"-{OFFLOAD_SKEW_SECONDS} to {OFFLOAD_WINDOW_SECONDS} s"}


def from_receipts(database: pathlib.Path | None, gated: Worktree, identity: dict[str, Any] | None, *,
                  reuse: bool, record: bool, offload: str | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """`(answer, None)` when a receipt answers `check_in_worktree` instead of a run, else `(None, miss)`: why none stood (sd:2602).

    This machine's own receipt first; a reuse on a satellite writes the offload row it lacks (sd:2704).
    Then `offload`, the hub's: `require` answers from a satellite's offload receipt or with
    `offload_refused`, and never runs; `fallback` tries one after its own receipt and names its miss.
    An accepted one carries `satellite`. A recorded pass writes the offload row too (`record_gate_pass`).
    """
    import sd_gate_run  # noqa: PLC0415 -- it imports this module

    key = receipt_key(gated.root, gated.head, gated.content)
    found, miss = examine(database, key, identity) if reuse and database and offload != "require" else (None, None)
    if found is not None:
        reading = dict(found["reading"], summary=f"{found['reading']['summary']} (reused)"[:sd_gate_run.DESCRIPTION_LIMIT],
                       reused={"revision": found["revision"], "recorded_at": found["recorded_at"],
                               "age_seconds": found["age_seconds"], "head": found["head"]})
        if record and identity:
            reading.update(record_offload(database, gated, identity, found["reading"], found["view"], found["recorded_at"]))
        return reading, None
    if not offload:
        return None, miss
    accepted, refused = examine_offload(database, gated)
    if accepted is not None:
        return satellite_reading(accepted), None
    if offload == "require":
        return {"status": "refused", "offload_refused": refused}, None
    return None, {**(miss or {}), "offload": refused}


def record_gate_pass(database: pathlib.Path, gated: Worktree, identity: dict[str, Any],
               reading: dict[str, Any], before: dict[str, Any] | None = None) -> None:
    """Record a pass at the head it ran on, and on a satellite its offload row, unless the binding or `before` moved."""
    import sd_gate_run  # noqa: PLC0415 -- it imports this module

    after = gate_binding(gated.tree, gated.head, sd_gate_run.gate_inputs(gated.root, gated.head, gated.content, gated.own),
                                          gated.base, gated.environment, gated.fork, gated.mode)
    key = receipt_key(gated.root, gated.head, gated.content)
    # Any part, refusing or not: the row keeps the view the run started from, and records it whole (sd:2862).
    moved = next(iter(offload_differences(before, gated.view(identity))), None) if before is not None else None
    record_unless_moved(database, key, identity, after, reading, gated.head, None if moved else before)  # no reuse exports it
    if "receipt_skipped" in reading:
        return
    if moved:
        reading["offload_error"] = f"the offload view moved during the run: {moved['part']} {moved['name']}"
        return
    reading.update(record_offload(database, gated, identity, {
        name: value for name, value in reading.items() if name not in ("receipt_revision", "receipt_error")}, before))


def satellite_reading(accepted: dict[str, Any]) -> dict[str, Any]:
    """A satellite's pass the hub accepted (sd:2704), as a gate result: its reading, and `satellite` provenance."""
    import sd_gate_run  # noqa: PLC0415 -- it imports this module

    satellite = accepted["satellite"]
    summary = f"{accepted['reading'].get('summary')} (satellite {satellite.get('hostname')})"[:sd_gate_run.DESCRIPTION_LIMIT]
    return dict(accepted["reading"], summary=summary, satellite={
        "revision": accepted["revision"], "login": satellite.get("login"), "address": satellite.get("address"),
        "hostname": satellite.get("hostname"), "hub": accepted["hub"], "head": accepted["head"],
        "recorded_at": accepted["recorded_at"], "age_seconds": accepted["age_seconds"],
        "unresolved_tools": accepted["unresolved_tools"], "view_differences": accepted["view_differences"],
        "pack_bin": accepted["pack_bin"]})


def record_unless_moved(database: pathlib.Path, key: str, identity: Mapping[str, Any], after: Mapping[str, Any] | None,
                        reading: dict[str, Any], head: str, view: dict[str, Any] | None = None) -> None:
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
        reading["receipt_revision"] = record_pass(database, key, identity, reading, head, view=view)
    except Exception as error:  # the pass stands; only its reuse is lost
        reading["receipt_error"] = str(error)


def _connect(database: pathlib.Path | None, *, write: bool) -> Any:
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
                "head": row.get("head"), "view": row.get("offload_view")}, None
    except Exception as error:
        return None, {"reason": "unreadable", "error": str(error)[:200]}


def record_pass(database: pathlib.Path, key: str, identity: Mapping[str, Any], reading: Mapping[str, Any],
                head: str | None = None, now: float | None = None, view: dict[str, Any] | None = None) -> int:
    """Store a success under `key`; anything but a success is refused, and raises.

    `head` is the commit that passed, kept for provenance: under a tree key the binding does not name it.
    `view` is a satellite run's starting offload view (sd:2704); local reuse never compares it.
    """
    if reading.get("status") != "success":
        raise ValueError("only a passing gate run leaves a receipt")
    with closing(_connect(database, write=True)) as connection:
        from sd_db import ship  # noqa: PLC0415
        revision, _ = ship.read(connection, key)
        return int(ship.save(connection, key, revision, {
            "writer": WRITER, "binding": dict(identity), "reading": dict(reading), "head": head,
            "recorded_at": time.time() if now is None else now, **({"offload_view": view} if view else {})}))
