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
prunes nothing in these folders; deleting one reclaims its space and costs
the next gate that takes it one cold build.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import pathlib
from typing import Iterator, Mapping

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


def uses_cargo(tree: pathlib.Path) -> bool:
    """Whether the commit tracks a `Cargo.toml`, at the top or below it."""
    listed = sd_lib.git_output(["ls-files", "-z", "--", "*Cargo.toml"], tree) or ""
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
            handle = open(folder / f"cargo-target.{number}.lock", "a")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                handle.close()
                continue
            held = handle, folder / f"cargo-target.{number}"
            break
    except OSError:
        held = None
    if held is None:
        yield None
        return
    handle, target = held
    try:
        yield str(target)
    finally:
        handle.close()


@contextlib.contextmanager
def cargo_environment(root: pathlib.Path, tree: pathlib.Path, env: Mapping[str, str]) -> Iterator[dict[str, str]]:
    """`env`, plus `CARGO_TARGET_DIR` naming the folder `cargo_target` holds for the block, when it holds one."""
    with cargo_target(root, tree, env) as target:
        yield {**env, "CARGO_TARGET_DIR": target, **WARM_ENVIRONMENT} if target else dict(env)
