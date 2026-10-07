"""The gate's pinned tools (sd:2936): one official release archive per tool, so hub and satellite bind the same bytes.

An opted-in repository (`repo.satellite_gate = accept`) merges on a satellite's
pass only when every tool in `sd_gate_receipts.OFFLOAD_TOOLS` has the hub's
bytes. Two `cargo install`s of one release differ (PR #296), and Homebrew
upgrades each machine on its own day. So the gate runs its own copies of the
tools that publish a release archive: `PINS` names each by version, URL and
sha256, `install` unpacks each into a folder named by that digest under the
gate cache, and `sd_gate_receipts.offload_pins` puts those folders first on
every opted-in check's `PATH`. A missing copy refuses the gate (`missing`); the
gate never downloads. An installed folder is never written again, so a gate
that runs while `install` runs binds and runs one file.

`PINS` is a pack file, so `pack_bin` hashes it and two machines at one pack
revision read one list. docs/work/2026-10-07-gate-pinned-tools/design.md holds
the per-tool sources and the contract with machine-setup (sd:2937).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
from typing import Any, Mapping

import sd_gate_cache

#: One entry per tool and platform: `bin` is the folder in the archive that holds `provides`, the names the gate binds.
PINS: tuple[dict[str, Any], ...] = (
    {"tool": "cargo-nextest", "version": "0.9.146", "platform": "darwin-arm64",
     "url": "https://github.com/nextest-rs/nextest/releases/download/cargo-nextest-0.9.146/"
            "cargo-nextest-0.9.146-universal-apple-darwin.tar.gz",
     "sha256": "39785160b3c2f6ed9a765049cf4fa79f3b39aa02eb7598a5a0e2a1a0b9ffb9a8", "bin": ".",
     "provides": ("cargo-nextest",)},
    {"tool": "node", "version": "26.10.0", "platform": "darwin-arm64",
     "url": "https://nodejs.org/dist/v26.10.0/node-v26.10.0-darwin-arm64.tar.gz",
     "sha256": "751fdf7439f115d87ee2a8f3f18c065b6151852068e3e666ac60ac2996f75ac9",
     "bin": "node-v26.10.0-darwin-arm64/bin", "provides": ("node", "npm")},
    {"tool": "uv", "version": "0.12.22", "platform": "darwin-arm64",
     "url": "https://github.com/astral-sh/uv/releases/download/0.12.22/uv-aarch64-apple-darwin.tar.gz",
     "sha256": "5d714de09501a59393ceca78f4bc232a50478729640d251907160299b2a93ddd",
     "bin": "uv-aarch64-apple-darwin", "provides": ("uv",)},
)
FOLDER = "pinned-tools"
INSTALL = "sd gate tools install"
DOWNLOAD_SECONDS = 300
#: The URL schemes `install` reads: a release over TLS, and a local archive, which tests use.
SCHEMES = ("https", "file")


def this_platform() -> str:
    return f"{sys.platform}-{platform.machine()}"


def pins() -> list[dict[str, Any]]:
    """The `PINS` entries for this machine's platform."""
    return [pin for pin in PINS if pin["platform"] == this_platform()]


def folder(pin: Mapping[str, Any], environment: Mapping[str, str]) -> pathlib.Path:
    """Where `pin` is unpacked: named by its digest, so a new pin is a new folder."""
    return sd_gate_cache.cache_root(environment) / FOLDER / f"{pin['tool']}-{pin['version']}-{pin['sha256'][:12]}"


def path_entries(environment: Mapping[str, str]) -> list[str]:
    """The `PATH` folders an opted-in check starts with, in `PINS` order."""
    return [os.path.normpath(folder(pin, environment) / pin["bin"]) for pin in pins()]


def provided() -> set[str]:
    """Every name a pin for this platform provides."""
    return {name for pin in pins() for name in pin["provides"]}


def installed(pin: Mapping[str, Any], environment: Mapping[str, str]) -> bool:
    """Each of `pin`'s `provides` is an executable file in its folder."""
    bin_folder = folder(pin, environment) / pin["bin"]
    return all(os.path.isfile(bin_folder / name) and os.access(bin_folder / name, os.X_OK) for name in pin["provides"])


def missing(environment: Mapping[str, str]) -> str | None:
    """Why an opted-in gate refuses: a pinned copy that is not installed, else None."""
    absent = [pin for pin in pins() if not installed(pin, environment)]
    if not absent:
        return None
    named = ", ".join(f"{pin['tool']} {pin['version']} at {folder(pin, environment)}" for pin in absent)
    return f"the gate's pinned {named} is not installed: run `{INSTALL}`"


def pin_status(environment: Mapping[str, str]) -> list[dict[str, Any]]:
    """Each pin for this platform, with its `folder` and whether it is `installed`."""
    return [{**pin, "provides": list(pin["provides"]), "folder": str(folder(pin, environment)),
             "installed": installed(pin, environment)} for pin in pins()]


def install(environment: Mapping[str, str]) -> list[dict[str, Any]]:
    """Install each missing pin for this platform; never touch an installed one. Each result names an `error` or none."""
    results = []
    for pin in pins():
        result = {"tool": pin["tool"], "version": pin["version"], "folder": str(folder(pin, environment))}
        if installed(pin, environment):
            results.append({**result, "action": "present"})
            continue
        try:
            unpack(pin, environment)
        except (OSError, ValueError, tarfile.TarError) as error:
            results.append({**result, "action": "failed", "error": f"{type(error).__name__}: {error}"[:500]})
            continue
        results.append({**result, "action": "installed"})
    return results


def unpack(pin: Mapping[str, Any], environment: Mapping[str, str]) -> None:
    """Download `pin`, check its sha256, unpack it beside its folder and rename it into place; raises on any fault."""
    final = folder(pin, environment)
    final.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{final.name}.", dir=final.parent) as scratch:
        archive, staging = pathlib.Path(scratch, "archive"), pathlib.Path(scratch, "folder")
        digest = hashlib.sha256()
        if urllib.parse.urlsplit(pin["url"]).scheme not in SCHEMES:
            raise ValueError(f"{pin['url']} is not an {' or '.join(SCHEMES)} URL")
        with urllib.request.urlopen(pin["url"], timeout=DOWNLOAD_SECONDS) as source, open(archive, "wb") as target:  # nosec B310 - scheme checked above
            while chunk := source.read(1 << 20):
                digest.update(chunk)
                target.write(chunk)
        if digest.hexdigest() != pin["sha256"]:
            raise ValueError(f"{pin['url']} has sha256 {digest.hexdigest()}, not the pinned {pin['sha256']}")
        with tarfile.open(archive) as tar:
            tar.extractall(staging, filter="data")
        absent = [name for name in pin["provides"] if not os.access(staging / pin["bin"] / name, os.X_OK)]
        if absent:
            raise ValueError(f"{pin['url']} holds no executable {', '.join(absent)} in {pin['bin']}")
        try:
            staging.rename(final)
        except OSError:
            if not installed(pin, environment):  # another install finished first: keep its folder
                raise


def add_tools_verb(gating: Any) -> None:
    """`sd gate tools status|install`."""
    tools = gating.add_parser("tools", help="the gate's pinned tool copies: show them, or install the missing ones")
    verbs = tools.add_subparsers(dest="tools_verb", required=True)
    shower = verbs.add_parser("status", help="each pin for this platform and whether it is installed; exit 1 if one is not")
    shower.add_argument("--json", action="store_true", help="machine-readable")
    verbs.add_parser("install", help="download, check and unpack each missing pin; exit 1 if one fails")


def tools_verb(args: argparse.Namespace, environment: Mapping[str, str]) -> int:
    if args.tools_verb == "install":
        results = install(environment)
        for result in results:
            print(f"{result['tool']} {result['version']}: {result['action']} {result['folder']}"
                  + (f": {result['error']}" if "error" in result else ""), file=sys.stderr if "error" in result else sys.stdout)
        return 1 if any("error" in result for result in results) else 0
    rows = pin_status(environment)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            print(f"{row['tool']} {row['version']}: {'installed' if row['installed'] else 'missing'} {row['folder']}")
        print(f"{len(rows)} pin(s) for {this_platform()}")
    return 0 if all(row["installed"] for row in rows) else 1

