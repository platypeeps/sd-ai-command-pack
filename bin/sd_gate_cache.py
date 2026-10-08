"""The local gate's Rust build cache (sd:2493): warm `CARGO_TARGET_DIR` folders per repository.

A Rust repository builds into a warm folder the gate owns, not into the
fresh worktree's own `target/`: every merge gate used to compile
every dependency cold. `cargo_target` hands the run one folder of a small
per-repository pool under `<cache>/<repository>/`, as `CARGO_TARGET_DIR`.
Cargo's fingerprints decide what to rebuild, and a fresh worktree's sources
are newer than any recorded build, so the repository's own crates compile
again and only unchanged dependencies are reused. A folder serves one gate
at a time, held by `flock` for the whole run: cargo's own lock covers a
build, but cargo-nextest runs the test binaries after releasing it, so a
second gate's build could replace them mid-run. When every folder is held,
the run builds cold in its worktree, as before. The operator's own
`CARGO_TARGET_DIR` never reaches the check, and which folder a run took does
not bind its receipt: the folder is a cache, not an input.

A warm run also gets `CARGO_INCREMENTAL=0` (`WARM_ENVIRONMENT`). Cargo
prunes nothing in these folders, and each gate still adds about 0.26 GB to
the one it takes. So the gate bounds the whole cache (sd:2598): once it holds
its folder, `prune` removes the least recently used free folders, any
repository's, until the cache fits `sd.gate_cache_gb`. A folder another gate
holds is skipped, since removing it needs its lock; the gate's own folder
goes last, before its run starts. A pruned folder costs its next gate one
cold build, and the gate names each one on stderr.

The gate's worktree is housekeeping of the same kind (sd:2739). A killed gate
never runs the `finally` that removes it, so its entry stays registered.
`worktree_prefix` names each gate's temporary folder after its pid, and first
removes every gate worktree whose named process is gone. Only a worktree
named `tree` in a folder `sd-local-gate-<pid>-<suffix>` directly in the temp
dir counts as a gate's: a checkout elsewhere with a like name is never touched.
A live gate's worktree stays; so does a folder from before this rule. The
dead gate's whole folder goes with its worktree, the check's `TMPDIR` included (sd:3032).
The same start removes what a run outside the gate left in the temp dir (`reap_temporary`): an sd folder whose
named pid is gone. Nothing goes by age, so every other entry stays; macOS purges those.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import pathlib
import re
import shutil
import sys
import tempfile
from typing import Iterator, Mapping, TextIO

import sd_lib

#: Where the gate keeps its build caches; unset reads `${XDG_CACHE_HOME:-~/.cache}/sd/gate`.
CACHE_VARIABLE = "SD_GATE_CACHE_DIR"
#: How many warm Rust build folders one repository keeps; 0 switches the cache off.
CARGO_TARGETS_VARIABLE = "SD_GATE_CARGO_TARGETS"
#: Two: one merge lane per repository, plus one review gate beside it.
DEFAULT_CARGO_TARGETS = 2
#: Set with a warm folder. Each gate's worktree is new, so rustc's incremental sessions never pay off, and on
#: macOS they and their session-named object files grew a folder by about 4 GB a gate; 0.26 GB without.
WARM_ENVIRONMENT = {"CARGO_INCREMENTAL": "0"}
#: The cache's bound in gigabytes for one run; `sd.gate_cache_gb` sets it for the machine, and 0 is no bound.
CACHE_GB_VARIABLE = "SD_GATE_CACHE_GB"
#: Two folders of the one Rust repository gated here measured 9 GB cold and about 18 GB after five builds.
DEFAULT_CACHE_GB = 40
GIB = 1024 ** 3
#: A gate's temporary folder: this prefix, then the pid of the gate that owns it, then `-` (sd:2739).
GATE_PREFIX = "sd-local-gate-"
#: The whole folder name `tempfile` makes from that prefix; nine digits keep a pid within `os.kill`'s range.
GATE_FOLDER = re.compile(r"sd-local-gate-([0-9]{1,9})-[a-z0-9_]+")
#: The check's own `TMPDIR`, beside the gate's worktree: the gate's cleanup removes what the check's tests leave (sd:3032).
TEMPORARY = "tmp.noindex"
#: An sd folder that names its owner's pid: a gate's, or a test run's (`tests/__init__.py`); it goes once the pid is gone.
OWNED = re.compile(r"(?:sd-local-gate|sd-tests)-([0-9]{1,9})-[a-z0-9_]+")


def running(pid: int) -> bool:
    """Whether a process `pid` exists; one owned by another user does."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def reap_temporary(temporary: pathlib.Path) -> int:
    """Remove the user's entries directly in `temporary` that are `OWNED` by a dead pid; how many went.

    Age proves nothing: a live process or the operator may still read an old entry (sd:3032 review). A dead gate's
    folder counts too: its worktree was another repository's, so `worktree_prefix` never saw it.
    """
    try:
        entries = list(os.scandir(temporary))
    except OSError:
        return 0
    removed = 0
    for entry in entries:
        owned = OWNED.fullmatch(entry.name)
        if not owned or running(int(owned[1])):
            continue
        try:
            status = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        if status.st_uid != os.getuid():
            continue
        if entry.is_dir(follow_symlinks=False):
            shutil.rmtree(entry.path, ignore_errors=True)
        else:
            with contextlib.suppress(OSError):
                os.unlink(entry.path)
        removed += not os.path.lexists(entry.path)
    return removed


def worktree_prefix(root: pathlib.Path) -> str:
    """This gate's temporary folder prefix, after removing `root`'s gate worktrees whose gate process is gone
    and the temp dir's leftovers (`reap_temporary`)."""
    temporary = pathlib.Path(tempfile.gettempdir()).resolve()
    if removed := reap_temporary(temporary):
        print(f"sd gate: removed {removed} temp entries from {temporary} (sd:3032)", file=sys.stderr)
    listing = sd_lib.git_output(["worktree", "list", "--porcelain"], root) or ""
    for line in listing.splitlines():
        tree = pathlib.Path(line.removeprefix("worktree "))
        named = GATE_FOLDER.fullmatch(tree.parent.name)
        if line.startswith("worktree ") and named and tree.name == "tree" \
                and tree.parent.parent.resolve() == temporary and not running(int(named[1])):
            sd_lib.git_output(["worktree", "remove", "--force", str(tree)], root)
            shutil.rmtree(tree.parent, ignore_errors=True)  # and the check's `TMPDIR` beside it (sd:3032)
    return f"{GATE_PREFIX}{os.getpid()}-"


def check_temporary(parent: str) -> str:
    """The check's `TMPDIR`, made empty in the gate's folder `parent` (sd:3032)."""
    (folder := pathlib.Path(parent) / TEMPORARY).mkdir()
    return str(folder)


def cache_root(environ: Mapping[str, str]) -> pathlib.Path:
    """The folder that holds every repository's gate build cache."""
    if named := environ.get(CACHE_VARIABLE):
        return pathlib.Path(named)
    cache = environ.get("XDG_CACHE_HOME") or str(pathlib.Path(environ.get("HOME", "~")).expanduser() / ".cache")
    return pathlib.Path(cache) / "sd" / "gate"


def cargo_pool(environ: Mapping[str, str]) -> int:
    """The pool size `SD_GATE_CARGO_TARGETS` names; a value that is not a count switches the cache off."""
    text = environ.get(CARGO_TARGETS_VARIABLE)
    if text is None:
        return DEFAULT_CARGO_TARGETS
    return int(text) if text.isascii() and text.isdigit() else 0


def cache_bound(environ: Mapping[str, str]) -> int:
    """The cache's bound in bytes: `SD_GATE_CACHE_GB`, then `sd.gate_cache_gb`, then 40 GB; 0 is no bound."""
    text = environ.get(CACHE_GB_VARIABLE)
    if text is None:
        try:
            text = sd_lib.core_setting("gate_cache_gb", dict(environ))
        except sd_lib.ConfigError:
            text = None
    try:
        return int(float(text) * GIB) if text is not None else DEFAULT_CACHE_GB * GIB
    except ValueError:
        return DEFAULT_CACHE_GB * GIB


def folder_bytes(folder: pathlib.Path) -> int:
    """The bytes of every file under `folder`."""
    total = 0
    for base, _, names in os.walk(folder):
        for name in names:
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(base, name)).st_size
    return total


def folder_lock(folder: pathlib.Path) -> pathlib.Path:
    """The lock file that guards a warm folder; its mtime is the folder's last use."""
    return folder.parent / f"{folder.name}.lock"


def last_used(folder: pathlib.Path) -> float:
    """When a gate last took `folder`; never, for a folder without its lock file."""
    try:
        return folder_lock(folder).stat().st_mtime
    except OSError:
        return 0.0


def hold_unless_held(path: pathlib.Path) -> TextIO | None:
    """An open handle holding `path`'s lock, or None when another gate holds it."""
    handle = open(path, "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def prune(root: pathlib.Path, held: pathlib.Path, bound: int) -> list[tuple[pathlib.Path, int]]:
    """Remove the least recently used free folders under `root` until it fits `bound` bytes; `held` goes last.

    The caller holds `held`'s lock. Every other folder is removed only under its
    own lock, so a folder another gate is using stays. 0 is no bound.
    """
    if bound <= 0:
        return []
    sizes = {folder: folder_bytes(folder) for folder in root.glob("*/cargo-target.*") if folder.is_dir()}
    total = sum(sizes.values())
    order = sorted((folder for folder in sizes if folder != held), key=last_used)
    pruned: list[tuple[pathlib.Path, int]] = []
    for folder in order + ([held] if held in sizes else []):
        if total <= bound:
            break
        handle = None if folder == held else hold_unless_held(folder_lock(folder))
        if folder != held and handle is None:
            continue
        shutil.rmtree(folder, ignore_errors=True)
        if handle is not None:
            handle.close()
        total -= sizes[folder]
        pruned.append((folder, sizes[folder]))
    return pruned


def uses_cargo(tree: pathlib.Path) -> bool:
    """Whether the commit tracks a `Cargo.toml`, at the top or below it."""
    listed = sd_lib.git_output(["ls-files", "-z", "--deduplicate", "--", "*Cargo.toml"], tree) or ""
    return any(pathlib.PurePosixPath(name).name == "Cargo.toml" for name in listed.split("\0") if name)


@contextlib.contextmanager
def cargo_target(root: pathlib.Path, tree: pathlib.Path, environ: Mapping[str, str]) -> Iterator[str | None]:
    """The first free warm build folder of `root`'s repository, held until the block ends; None for a cold build.

    None when `tree` tracks no `Cargo.toml`, the pool is 0, every folder is
    held by another gate, or the cache cannot be made. The repository is named
    by its git common directory, so every worktree of one repository shares
    the pool.
    """
    pool = cargo_pool(environ)
    if pool <= 0 or not uses_cargo(tree):
        yield None
        return
    common = sd_lib.git_output(["rev-parse", "--path-format=absolute", "--git-common-dir"], root) or str(root)
    common_path = pathlib.Path(common).resolve()
    name = common_path.parent.name if common_path.name == ".git" else common_path.name
    folder = cache_root(environ) / f"{name}-{hashlib.sha256(str(common_path).encode()).hexdigest()[:12]}"
    held = None
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for number in range(1, pool + 1):
            if (handle := hold_unless_held(folder / f"cargo-target.{number}.lock")) is not None:
                held = handle, folder / f"cargo-target.{number}"
                break
    except OSError:
        held = None
    if held is None:
        yield None
        return
    handle, target = held
    try:
        report_pruned(target, environ)
        yield str(target)
    finally:
        handle.close()


def report_pruned(target: pathlib.Path, environ: Mapping[str, str]) -> None:
    """Mark `target` used, bound the cache around it, and name each pruned folder on stderr."""
    try:
        os.utime(folder_lock(target))
        bound = cache_bound(environ)
        for folder, size in prune(target.parent.parent, target, bound):
            print(f"sd gate: pruned {folder} ({size / GIB:.1f} GB, least recently used) to keep the gate cache "
                  f"under {bound / GIB:g} GB (sd.gate_cache_gb)", file=sys.stderr)
    except OSError as error:
        print(f"sd gate: cache not pruned: {error}", file=sys.stderr)


@contextlib.contextmanager
def cargo_environment(root: pathlib.Path, tree: pathlib.Path, env: Mapping[str, str]) -> Iterator[dict[str, str]]:
    """`env`, plus `CARGO_TARGET_DIR` naming the folder `cargo_target` holds for the block, when it holds one."""
    with cargo_target(root, tree, env) as target:
        yield {**env, "CARGO_TARGET_DIR": target, **WARM_ENVIRONMENT} if target else dict(env)
