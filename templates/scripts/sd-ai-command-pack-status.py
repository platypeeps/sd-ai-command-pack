#!/usr/bin/env python3
"""Report local or fleet SD repository status without mutating state."""

from __future__ import annotations

import argparse
import contextlib
import errno
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

sys.dont_write_bytecode = True

# This import must follow the bytecode guard for direct entrypoint invocation.
from sd_ai_command_pack_lib import CacheSetupError, build_tool_environment  # noqa: E402

SCHEMA_VERSION = 2
COMMAND_TIMEOUT_SECONDS = 20
MAX_ITEMS = 100
HUMAN_ITEM_LIMIT = 5
MAX_ROADMAP_SOURCE_FILES = 100
MAX_ROADMAP_SOURCE_BYTES = 256 * 1024
MAX_ROADMAP_LINE_CHARS = 2_000
MAX_ROADMAP_ITEMS = 500
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
COMMIT_RE = re.compile(r"[0-9a-f]{40,64}")
ANOMALY_CODE_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")
SEVERITY_BLOCKING = "blocking"
SEVERITY_ADVISORY = "advisory"
# Caller anomaly codes -- replayed here through --prior-anomaly -- whose severity
# is advisory. The caller (sd-ai-command-pack-housekeeping.sh) reports the same
# codes through its own typed channel, where
# sd-ai-command-pack-housekeeping-result.py holds the authoritative set; a test
# asserts the two sets are identical, because a code that is advisory in one and
# blocking in the other produces a clean verdict from a run that exited nonzero.
# An unrecognized code is blocking: severity fails closed.
ADVISORY_CALLER_ANOMALY_CODES = frozenset(
    {
        "branch_retained_default_held",
        "default_branch_held_elsewhere",
    }
)
GITHUB_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
# This project publishes releases as annotated tags, not GitHub Releases, so the
# newest release is the highest v<semver> tag on the remote. Anything that does
# not match exactly is skipped rather than coerced: a pre-release or a hand-made
# tag must not participate in the ordering.
RELEASE_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
ROADMAP_SOURCE_EXTENSIONS = frozenset({".md", ".mdx", ".txt"})
ROADMAP_SOURCE_STEMS = (
    "roadmap",
    "backlog",
    "todo",
    "program_design",
    "implementation_plan",
)
ROADMAP_SOURCE_DIRECTORIES = frozenset({"roadmap", "proposals", "rfcs"})
ROADMAP_EXCLUDED_DIRECTORIES = frozenset(
    {
        "git",
        "trellis",
        "venv",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "target",
        "vendor",
    }
)
UNCHECKED_TASK_RE = re.compile(r"^[ \t]*[-*+][ \t]+\[[ \t]\][ \t]+(.+?)\s*$")
CHECKED_TASK_RE = re.compile(r"^[ \t]*[-*+][ \t]+\[[xX]\][ \t]+")
TOP_LEVEL_LIST_RE = re.compile(
    r"^(?:[-*+]|[0-9]{1,4}[.)])[ \t]+(?!\[[ xX]\][ \t]+)(.+?)\s*$"
)
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
MARKDOWN_REFERENCE_LINK_RE = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
MARKDOWN_TAG_RE = re.compile(r"<[^>]+>")
MARKDOWN_OPEN_MARKER_RE = re.compile(
    r"(?<!\w)(?:\*{1,3}|_{1,3}|~{1,2}|`+)(?=\S)"
)
MARKDOWN_CLOSE_MARKER_RE = re.compile(
    r"(?<=\S)(?:\*{1,3}|_{1,3}|~{1,2}|`+)(?!\w)"
)
PARKED_PREFIX_RE = re.compile(r"^PARKED\s*:\s*", re.IGNORECASE)
PR_SEPARATOR = "\x1f"
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
TASK_STATUS_ORDER = {"in_progress": 0, "planning": 1, "completed": 2}
# Schema 2 adds `resolution`: which toolchain the shipped skills' bootstrap
# reaches and whether PATH would have answered with a different install.
MACHINE_SCOPE_SCHEMA_VERSION = 2
# The plugin the machine-scope surfaces ship with; the identity
# sd-ai-command-pack-pack-update.sh updates.
MACHINE_PLUGIN_ID = "sd@sd-ai-command-pack"
# The one file every install roots its helpers at. A directory holding it is a
# pack `bin/`; that is a filesystem test, not a name pattern, so a differently
# named install root is still recognized.
TOOLCHAIN_FILENAME = "sd-ai-command-pack-toolchain.sh"
# The bootstrap's candidate order, recorded in
# templates/.agents/skills/sd-help/references/pack-helper-resolution.md.
TOOLCHAIN_SOURCES = ("override", "checkout", "machine")
TOOLCHAIN_VERDICTS = frozenset({"bound", "shadowed", "unresolved"})
# PATH is unbounded external input; the report keeps the leading pack entries.
MAX_PATH_PACK_ENTRIES = 8
MACHINE_UNAVAILABLE = "unavailable"
# Pack identity for a candidate engine root, under both spellings that ship.
# A checkout carries `manifest.json`; the plugin cache root carries only
# `.claude-plugin/plugin.json`, so requiring the first alone would reject the
# arrangement the PATH rung exists to reach.
PACK_MANIFEST_NAME = "sd-ai-command-pack"
PACK_PLUGIN_NAME = "sd"
# Refused engine roots are reported, not dropped; PATH is unbounded input.
MAX_MACHINE_ENGINE_REFUSALS = 8
# States the machine-install engine reports from the receipt alone. A fourth
# value, MACHINE_UNAVAILABLE, is this collector's own: it means the receipt
# could not be read at all (no engine beside this script), which is neither a
# missing install nor a corrupt one.
MACHINE_RECEIPT_STATES = frozenset({"none", "installed", "invalid"})
WORK_LOOP_TERMINAL_STATUSES = frozenset({"none", "invalid", "unavailable"})
WORK_LOOP_RUN_STATUSES = frozenset({"active", "paused", "stopped", "completed"})
WORK_LOOP_REQUIRED_STRING_FIELDS = (
    "runId",
    "mode",
    "selector",
    "phase",
    "focusMode",
    "heartbeatAt",
)
REVIEW_TOTAL_COUNT_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!){"
    "repository(owner:$owner,name:$name){"
    "pullRequest(number:$number){reviews{totalCount}}}}"
)
FLEET_READY_STEP = (
    "Fleet checkouts are locally ready; no immediate fleet action is required."
)
# Skew rows describe an installation that no longer matches what it pins, so
# they must reach the operator even when the advisory rows outnumber
# HUMAN_ITEM_LIMIT. fleet_next_steps sorts by this rank before truncating and
# derives followUps from the untruncated set.
FLEET_STEP_RANK_SKEW = 0
FLEET_STEP_RANK_ADVISORY = 1
# Mirrors DEFAULT_FLEET_PIN_PATH in sd_ai_command_pack_fleet_lib. Used only as a
# defensive fallback for a FleetConsumer that predates schema 5; a test asserts
# the two constants stay equal.
DEFAULT_CONSUMER_PIN_PATH = ".sd-ai-command-pack/provenance.json"


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str


@contextlib.contextmanager
def suppress_bytecode_writes() -> Iterator[None]:
    """Keep read-only status imports from creating repository-local caches."""
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = previous


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int = COMMAND_TIMEOUT_SECONDS,
) -> CommandResult:
    try:
        environment, _, _ = build_tool_environment(repo=cwd)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            list(argv),
            cwd=cwd,
            env=environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout_seconds,
        )
        return CommandResult(result.returncode, result.stdout)
    except CacheSetupError as error:
        print(f"status cache setup failed: {error}", file=sys.stderr)
        return CommandResult(127, "")
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return CommandResult(127, "")


def safe_text(value: object, *, limit: int = 180) -> str:
    text = CONTROL_RE.sub(" ", str(value)).strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def github_slug_from_url(url: str) -> str | None:
    value = url.strip()
    prefixes = (
        "git@github.com:",
        "ssh://git@github.com/",
        "https://github.com/",
        "http://github.com/",
    )
    for prefix in prefixes:
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    else:
        return None
    value = value.removesuffix(".git").strip("/")
    return value if GITHUB_SLUG_RE.fullmatch(value) else None


def resolve_repo(path: Path) -> Path | None:
    git_path = path.expanduser()
    if not git_path.is_absolute():
        git_path = Path.cwd() / git_path
    if git_path.is_file():
        git_path = git_path.parent
    elif not git_path.is_dir():
        return None
    result = run_command(
        ["git", "-C", str(git_path), "rev-parse", "--show-toplevel"],
        cwd=git_path,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return Path(result.stdout.strip()).resolve(strict=True)
    except OSError:
        return None


def git_output(repo: Path, *args: str) -> str | None:
    result = run_command(["git", *args], cwd=repo)
    return result.stdout.strip() if result.returncode == 0 else None


def parse_porcelain_v2(output: str) -> dict[str, Any]:
    branch: str | None = None
    detached = False
    upstream: str | None = None
    ahead: int | None = None
    behind: int | None = None
    staged = 0
    unstaged = 0
    untracked = 0

    for line in output.splitlines():
        if line.startswith("# branch.head "):
            branch_value = line.removeprefix("# branch.head ").strip()
            detached = branch_value == "(detached)"
            branch = None if detached else branch_value
        elif line.startswith("# branch.upstream "):
            upstream = line.removeprefix("# branch.upstream ").strip() or None
        elif line.startswith("# branch.ab "):
            match = re.fullmatch(r"# branch\.ab \+(\d+) -(\d+)", line)
            if match:
                ahead = int(match.group(1))
                behind = int(match.group(2))
        elif line.startswith(("1 ", "2 ", "u ")):
            fields = line.split(" ", 2)
            xy = fields[1] if len(fields) > 1 else ".."
            if len(xy) == 2:
                if xy[0] not in {".", " "}:
                    staged += 1
                if xy[1] not in {".", " "}:
                    unstaged += 1
        elif line.startswith("? "):
            untracked += 1

    if upstream is None:
        ahead = None
        behind = None
    elif ahead is None or behind is None:
        ahead = 0
        behind = 0

    return {
        "branch": branch,
        "detached": detached,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "workingTree": {
            "state": "clean" if staged + unstaged + untracked == 0 else "dirty",
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
        },
    }


def parse_worktree_porcelain(text: str) -> list[dict[str, Any]]:
    """Parse `git worktree list --porcelain -z` output into raw rows.

    Values are returned unmodified: paths may exceed display bounds and
    contain newlines. Display bounding happens only when the outgoing
    JSON row is composed, because filesystem probes need the raw path.
    """
    rows: list[dict[str, Any]] = []
    entry: dict[str, Any] | None = None
    for record in text.split("\0"):
        if not record:
            if entry is not None:
                rows.append(entry)
                entry = None
            continue
        if record.startswith("worktree "):
            if entry is not None:
                rows.append(entry)
            entry = {
                "path": record.removeprefix("worktree "),
                "branch": None,
                "detached": False,
                "head": None,
                "bare": False,
                "locked": False,
                "prunable": False,
                "reason": None,
            }
            continue
        if entry is None:
            continue
        if record.startswith("HEAD "):
            entry["head"] = record.removeprefix("HEAD ")
        elif record.startswith("branch "):
            entry["branch"] = record.removeprefix("branch ").removeprefix(
                "refs/heads/"
            )
        elif record == "detached":
            entry["detached"] = True
        elif record == "bare":
            entry["bare"] = True
        elif record == "locked":
            entry["locked"] = True
        elif record.startswith("locked "):
            entry["locked"] = True
            entry["reason"] = record.removeprefix("locked ")
        elif record == "prunable":
            entry["prunable"] = True
        elif record.startswith("prunable "):
            entry["prunable"] = True
            entry["reason"] = record.removeprefix("prunable ")
    if entry is not None:
        rows.append(entry)
    return rows


def collect_worktrees(repo: Path) -> dict[str, Any]:
    listing = git_output(repo, "worktree", "list", "--porcelain", "-z")
    if listing is None:
        return {"status": "unavailable"}
    parsed = parse_worktree_porcelain(listing)
    reporting_raw = git_output(
        repo, "rev-parse", "--path-format=absolute", "--show-toplevel"
    )
    reporting: Path | None = None
    if reporting_raw:
        try:
            reporting = Path(reporting_raw).resolve()
        except OSError:
            reporting = None
    common_raw = git_output(
        repo, "rev-parse", "--path-format=absolute", "--git-common-dir"
    )
    common: Path | None = None
    if common_raw:
        try:
            common = Path(common_raw).resolve()
        except OSError:
            common = None
    rows: list[dict[str, Any]] = []
    current_marked = False
    for entry in parsed:
        raw_path = entry["path"]
        current = False
        if not current_marked:
            try:
                current = (
                    reporting is not None
                    and Path(raw_path).resolve() == reporting
                )
            except OSError:
                current = reporting_raw is not None and raw_path == reporting_raw
            current_marked = current
        clean: bool | None = None
        if not entry["bare"] and not entry["prunable"]:
            probe_root = Path(raw_path)
            try:
                probe_ok = probe_root.is_dir()
            except OSError:
                probe_ok = False
            if probe_ok and common is not None:
                probe_common = git_output(
                    probe_root,
                    "rev-parse",
                    "--path-format=absolute",
                    "--git-common-dir",
                )
                identity = False
                if probe_common:
                    try:
                        identity = Path(probe_common).resolve() == common
                    except OSError:
                        identity = False
                if identity:
                    porcelain = git_output(
                        probe_root, "--no-optional-locks", "status", "--porcelain"
                    )
                    if porcelain is not None:
                        clean = porcelain == ""
        rows.append(
            {
                "path": safe_text(raw_path, limit=300),
                "branch": safe_text(entry["branch"]) if entry["branch"] else None,
                "detached": entry["detached"],
                "head": safe_text(entry["head"][:12]) if entry["head"] else None,
                "bare": entry["bare"],
                "locked": entry["locked"],
                "prunable": entry["prunable"],
                "reason": safe_text(entry["reason"]) if entry["reason"] else None,
                "clean": clean,
                "current": current,
            }
        )
    return {"status": "ok", "rows": rows}


def default_branch(repo: Path, remote: str, supplied: str | None) -> str | None:
    if supplied:
        return supplied
    symbolic = git_output(
        repo,
        "symbolic-ref",
        "--quiet",
        "--short",
        f"refs/remotes/{remote}/HEAD",
    )
    if symbolic and symbolic.startswith(f"{remote}/"):
        return symbolic.removeprefix(f"{remote}/")
    for candidate in ("main", "master"):
        if git_output(repo, "show-ref", "--verify", f"refs/remotes/{remote}/{candidate}"):
            return candidate
        if git_output(repo, "show-ref", "--verify", f"refs/heads/{candidate}"):
            return candidate
    return None


def sync_state(upstream: str | None, ahead: int | None, behind: int | None) -> str:
    if upstream is None or ahead is None or behind is None:
        return "no-upstream"
    if ahead and behind:
        return "diverged"
    if ahead:
        return "ahead"
    if behind:
        return "behind"
    return "synchronized"


def collect_git(
    repo: Path,
    *,
    remote: str,
    supplied_default: str | None,
    refs_refreshed: bool,
) -> tuple[dict[str, Any], list[tuple[str, str, str]]]:
    anomalies: list[tuple[str, str, str]] = []
    porcelain = git_output(
        repo,
        "status",
        "--porcelain=v2",
        "--branch",
        "--untracked-files=all",
    )
    if porcelain is None:
        return {}, [
            ("git_status_unavailable", SEVERITY_BLOCKING, "git status is unavailable")
        ]
    state = parse_porcelain_v2(porcelain)
    resolved_default = default_branch(repo, remote, supplied_default)
    state["defaultBranch"] = resolved_default
    state["remote"] = remote
    state["syncState"] = sync_state(
        state["upstream"], state["ahead"], state["behind"]
    )
    state["refsFreshness"] = "refreshed" if refs_refreshed else "cached"
    state["head"] = git_output(repo, "rev-parse", "--short=12", "HEAD")
    state["headSubject"] = safe_text(
        git_output(repo, "log", "-1", "--pretty=%s", "HEAD") or "unavailable"
    )
    local_branches = git_output(
        repo,
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/heads",
    )
    remote_branches = git_output(
        repo,
        "for-each-ref",
        "--format=%(refname)",
        f"refs/remotes/{remote}",
    )
    state["localBranches"] = sorted(local_branches.splitlines()) if local_branches else []
    state["remoteBranches"] = (
        sorted(
            branch.removeprefix("refs/remotes/")
            for branch in remote_branches.splitlines()
        )
        if remote_branches
        else []
    )
    worktrees = collect_worktrees(repo)
    state["worktrees"] = worktrees
    if worktrees["status"] == "ok":
        # A worktree HEAD may symref to a non-branch ref; the held set is
        # scoped to local branches so it stays a subset of localBranches.
        local_branch_names = set(state["localBranches"])
        state["branchesHeldElsewhere"] = sorted(
            {
                row["branch"]
                for row in worktrees["rows"]
                if row["branch"]
                and not row["current"]
                and row["branch"] in local_branch_names
            }
        )
    else:
        state["branchesHeldElsewhere"] = None
    # Merge evidence for the leftover-branch classification. Reachability from
    # the *local* default tip, because status never fetches: a default branch
    # behind its remote is reported as stale evidence rather than silently
    # answering the question wrongly.
    state["mergedIntoDefault"] = None
    if isinstance(resolved_default, str) and resolved_default:
        merged = git_output(
            repo,
            "for-each-ref",
            "--format=%(refname:short)",
            "--merged",
            f"refs/heads/{resolved_default}",
            "refs/heads",
        )
        if merged is not None:
            state["mergedIntoDefault"] = sorted(merged.splitlines())
    stash_list = git_output(repo, "stash", "list", "--format=%gd")
    if stash_list is None:
        state["stashCount"] = None
        anomalies.append(
            (
                "git_stash_unavailable",
                SEVERITY_BLOCKING,
                "git stash inventory is unavailable",
            )
        )
    else:
        state["stashCount"] = len(stash_list.splitlines()) if stash_list else 0
    remote_url = git_output(repo, "remote", "get-url", remote)
    state["remoteConfigured"] = remote_url is not None
    state["github"] = github_slug_from_url(remote_url or "")
    if resolved_default:
        local_default = git_output(repo, "rev-parse", f"refs/heads/{resolved_default}")
        remote_default = git_output(
            repo,
            "rev-parse",
            f"refs/remotes/{remote}/{resolved_default}",
        )
        state["defaultLocalExists"] = local_default is not None
        state["defaultRemoteExists"] = remote_default is not None
        state["defaultMatchesRemote"] = (
            local_default == remote_default
            if local_default is not None and remote_default is not None
            else None
        )
    else:
        state["defaultLocalExists"] = False
        state["defaultRemoteExists"] = False
        state["defaultMatchesRemote"] = None
    if remote_url is None:
        anomalies.append(
            (
                "git_remote_unconfigured",
                SEVERITY_BLOCKING,
                f"remote {safe_text(remote)} is not configured",
            )
        )
    return state, anomalies


def read_version(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8", errors="strict").strip()
    except (OSError, UnicodeError):
        return None
    return safe_text(value, limit=80) if value else None


def collect_versions(repo: Path, target_pack_version: str | None) -> dict[str, Any]:
    provenance = read_json_object(repo / ".sd-ai-command-pack/provenance.json")
    installed_pack = provenance.get("version") if provenance else None
    if not isinstance(installed_pack, str) or not installed_pack.strip():
        installed_manifest = read_json_object(repo / ".sd-ai-command-pack/manifest.json")
        installed_pack = installed_manifest.get("version") if installed_manifest else None
    if not isinstance(installed_pack, str) or not installed_pack.strip():
        installed_pack = None
    else:
        installed_pack = safe_text(installed_pack, limit=80)

    source_manifest = read_json_object(repo / "manifest.json")
    source_pack = None
    if source_manifest and source_manifest.get("name") == "sd-ai-command-pack":
        candidate = source_manifest.get("version")
        if isinstance(candidate, str) and candidate.strip():
            source_pack = safe_text(candidate, limit=80)
    target = target_pack_version or source_pack
    if installed_pack is None:
        pack_state = "not-installed"
    elif target is None:
        pack_state = "installed"
    elif installed_pack == target:
        pack_state = "current"
    else:
        pack_state = "different"

    return {
        "sdAiCommandPack": installed_pack,
        "sourcePack": source_pack,
        "targetPack": target,
        "packState": pack_state,
        "trellis": read_version(repo / ".trellis/.version"),
    }


def task_record(path: Path) -> dict[str, Any] | None:
    payload = read_json_object(path)
    if payload is None:
        return None
    status = payload.get("status")
    parent_value = payload.get("parent")
    if not isinstance(status, str):
        return None
    task_id = safe_text(payload.get("id") or path.parent.name)
    normalized_status = safe_text(status)
    if not task_id or not normalized_status:
        return None
    title = safe_text(payload.get("title") or payload.get("name") or task_id)
    if not title:
        title = task_id
    priority = safe_text(payload.get("priority") or "unprioritized")
    if not priority:
        priority = "unprioritized"
    if parent_value is None:
        parent = None
    elif not isinstance(parent_value, str) or not parent_value.strip():
        return None
    else:
        parent = safe_text(parent_value)
        if not parent:
            return None
    return {
        "id": task_id,
        "title": title,
        "status": normalized_status,
        "priority": priority,
        "path": path.parent.relative_to(path.parents[2]).as_posix(),
        "parent": parent,
    }


def task_sort_key(task: Mapping[str, Any]) -> tuple[int, str, str]:
    return (
        PRIORITY_ORDER.get(str(task.get("priority")), 9),
        str(task.get("title", "")).casefold(),
        str(task.get("id", "")).casefold(),
    )


def task_inventory_sort_key(
    task: Mapping[str, Any],
    *,
    active_identity: tuple[str, str] | None,
) -> tuple[int, int, int, str, str, str]:
    identity = (str(task.get("id", "")), str(task.get("path", "")))
    return (
        0 if identity == active_identity else 1,
        TASK_STATUS_ORDER.get(str(task.get("status")), 9),
        PRIORITY_ORDER.get(str(task.get("priority")), 9),
        str(task.get("title", "")).casefold(),
        identity[0].casefold(),
        identity[1].casefold(),
    )


def select_items(
    items: Sequence[Mapping[str, Any]],
    *,
    prefix: str,
) -> list[dict[str, Any]]:
    return [
        {**dict(item), "selectionId": f"{prefix}-{index}"}
        for index, item in enumerate(items, start=1)
    ]


def collect_trellis(repo: Path) -> dict[str, Any]:
    task_root = repo / ".trellis/tasks"
    tasks: list[dict[str, Any]] = []
    if task_root.is_dir():
        for task_json in sorted(task_root.glob("*/task.json")):
            if (
                task_json.parent.is_symlink()
                or task_json.is_symlink()
                or not task_json.is_file()
            ):
                continue
            task = task_record(task_json)
            if task is not None:
                tasks.append(task)

    active: dict[str, Any] | None = None
    active_stale = False
    active_source = ""
    active_path_text = ""
    task_script = repo / ".trellis/scripts/task.py"
    if task_script.is_file():
        # `current --json` is the one documented interface at the supported
        # vendored-Trellis floor (see
        # .trellis/spec/tooling/vendored-trellis-compatibility.md). A non-zero
        # exit or unparseable stdout means no active task; it is not a reason
        # to fall back to parsing prose.
        result = run_command(
            [sys.executable, str(task_script), "current", "--json"], cwd=repo
        )
        if result.returncode == 0:
            try:
                payload = json.loads(result.stdout)
            except (json.JSONDecodeError, ValueError):
                payload = None
            if isinstance(payload, dict):
                current_task = payload.get("current_task")
                if isinstance(current_task, dict):
                    active_path_text = str(current_task.get("dir") or "").strip()
                # A pointer the runtime itself reports as stale is drift worth
                # surfacing, not a detail to drop on the floor.
                active_stale = bool(payload.get("stale"))
                active_source = safe_text(payload.get("source") or "")
        if active_path_text:
            candidate_path = Path(active_path_text)
            if not candidate_path.is_absolute():
                candidate_path = repo / candidate_path
            active_path: Path | None = candidate_path
            try:
                candidate_path.resolve().relative_to(task_root.resolve())
            except (OSError, ValueError):
                active_path = None
            if active_path is not None:
                active = task_record(active_path / "task.json")

    in_progress = sorted(
        (task for task in tasks if task["status"] == "in_progress"),
        key=task_sort_key,
    )
    planned = sorted(
        (task for task in tasks if task["status"] == "planning"),
        key=task_sort_key,
    )
    completed_outside_archive = sorted(
        (task for task in tasks if task["status"] == "completed"),
        key=task_sort_key,
    )
    scanned_active = None
    if isinstance(active, dict):
        active_identity = (str(active.get("id", "")), str(active.get("path", "")))
        scanned_active = next(
            (
                task
                for task in tasks
                if (str(task.get("id", "")), str(task.get("path", "")))
                == active_identity
            ),
            None,
        )
    inventory_active_identity = (
        (str(scanned_active.get("id", "")), str(scanned_active.get("path", "")))
        if isinstance(scanned_active, dict)
        else None
    )
    inventory = sorted(
        tasks,
        key=lambda task: task_inventory_sort_key(
            task,
            active_identity=inventory_active_identity,
        ),
    )
    return {
        "activeTask": active,
        "activeTaskStale": active_stale,
        "activeTaskSource": active_source,
        # Sanitized at the payload boundary, not at capture: the raw text is
        # what `Path()` above has to resolve, but what reaches the report is
        # another repo's `task.py` output, and a `dir` carrying a newline
        # would otherwise break the human line in two. The limit is generous
        # enough for any real task directory and still bounded.
        "activeTaskPointer": safe_text(active_path_text, limit=512),
        "inProgress": in_progress,
        "planned": planned,
        "completedOutsideArchive": completed_outside_archive,
        "tasks": select_items(inventory, prefix="T"),
    }


def normalize_roadmap_source_component(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def is_roadmap_source(relative: PurePosixPath) -> bool:
    if relative.suffix.casefold() not in ROADMAP_SOURCE_EXTENSIONS:
        return False
    normalized_directories = {
        normalize_roadmap_source_component(part) for part in relative.parts[:-1]
    }
    if normalized_directories & ROADMAP_EXCLUDED_DIRECTORIES:
        return False
    normalized_stem = normalize_roadmap_source_component(relative.stem)
    compact_stem = normalized_stem.replace("_", "")
    if any(
        compact_stem.startswith(prefix.replace("_", ""))
        for prefix in ROADMAP_SOURCE_STEMS
    ):
        return True
    return bool(normalized_directories & ROADMAP_SOURCE_DIRECTORIES)


def path_has_symlink(repo: Path, relative: PurePosixPath) -> bool:
    candidate = repo
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            return True
    return False


def visible_markdown_text(value: str, *, limit: int = 500) -> str:
    text = MARKDOWN_IMAGE_RE.sub(r"\1", value)
    text = MARKDOWN_LINK_RE.sub(r"\1", text)
    text = MARKDOWN_REFERENCE_LINK_RE.sub(r"\1", text)
    text = MARKDOWN_TAG_RE.sub(" ", text)
    text = re.sub(r"\\([\\`*_{}\[\]()#+.!~-])", r"\1", text)
    text = MARKDOWN_OPEN_MARKER_RE.sub("", text)
    text = MARKDOWN_CLOSE_MARKER_RE.sub("", text)
    return safe_text(" ".join(text.split()), limit=limit)


def normalize_roadmap_match_text(value: str) -> str:
    text = PARKED_PREFIX_RE.sub(
        "",
        visible_markdown_text(value, limit=MAX_ROADMAP_LINE_CHARS),
    )
    return " ".join(text.casefold().split())


def bounded_roadmap_reference(
    raw_text: str,
    reference: str,
    *,
    path: bool = False,
) -> bool:
    boundary = r"a-z0-9_./-" if path else r"a-z0-9_-"
    return bool(
        re.search(
            rf"(?<![{boundary}]){re.escape(reference)}(?![{boundary}])",
            raw_text,
        )
    )


def roadmap_task_match_records(
    repo: Path,
    tasks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for task in tasks:
        record = dict(task)
        raw_path = task.get("path")
        if isinstance(raw_path, str):
            relative = PurePosixPath(raw_path)
            if (
                not relative.is_absolute()
                and relative.parts
                and all(part not in {"", ".", ".."} for part in relative.parts)
            ):
                task_json = repo.joinpath(".trellis", *relative.parts, "task.json")
                if not path_has_symlink(repo, PurePosixPath(".trellis") / relative):
                    payload = read_json_object(task_json)
                    if payload is not None:
                        title = payload.get("title") or payload.get("name")
                        if isinstance(title, str):
                            record["title"] = safe_text(
                                title,
                                limit=MAX_ROADMAP_LINE_CHARS,
                            )
        records.append(record)
    return records


def roadmap_task_reference(raw_text: str, tasks: Sequence[Mapping[str, Any]]) -> bool:
    raw_folded = raw_text.casefold()
    normalized = normalize_roadmap_match_text(raw_text)
    for task in tasks:
        title = normalize_roadmap_match_text(str(task.get("title", "")))
        if title and normalized == title:
            return True
        path = str(task.get("path", "")).casefold().strip()
        if path:
            for path_reference in (path, f".trellis/{path}"):
                if bounded_roadmap_reference(
                    raw_folded,
                    path_reference,
                    path=True,
                ):
                    return True
        references = {
            str(task.get("id", "")).casefold().strip(),
            PurePosixPath(path).name if path else "",
        }
        for reference in references:
            if reference and bounded_roadmap_reference(raw_folded, reference):
                return True
    return False


def roadmap_item_text(line: str) -> str | None:
    if CHECKED_TASK_RE.match(line):
        return None
    match = UNCHECKED_TASK_RE.match(line)
    if match is None:
        match = TOP_LEVEL_LIST_RE.match(line)
    if match is None:
        return None
    raw_text = match.group(1).strip()
    if not raw_text or CONTROL_RE.search(raw_text):
        return None
    return raw_text


def collect_roadmap_candidates(
    repo: Path,
    tasks: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    match_tasks = roadmap_task_match_records(repo, tasks)
    result = run_command(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repo,
    )
    if result.returncode != 0:
        return [], ["roadmap source scan incomplete: Git file inventory unavailable"]

    sources: list[tuple[PurePosixPath, Path]] = []
    for raw_path in result.stdout.split("\0"):
        if not raw_path:
            continue
        relative = PurePosixPath(raw_path)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
            or not is_roadmap_source(relative)
            or path_has_symlink(repo, relative)
        ):
            continue
        path = repo.joinpath(*relative.parts)
        if path.is_file():
            sources.append((relative, path))

    sources.sort(key=lambda item: (item[0].as_posix().casefold(), item[0].as_posix()))
    diagnostics: list[str] = []
    if len(sources) > MAX_ROADMAP_SOURCE_FILES:
        diagnostics.append(
            "roadmap source scan incomplete: "
            f"limited {len(sources)} matching files to {MAX_ROADMAP_SOURCE_FILES}"
        )
        sources = sources[:MAX_ROADMAP_SOURCE_FILES]

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    limit_reached = False
    for relative, path in sources:
        try:
            size = path.stat().st_size
        except OSError:
            diagnostics.append(
                "roadmap source scan incomplete: cannot stat " + relative.as_posix()
            )
            continue
        if size > MAX_ROADMAP_SOURCE_BYTES:
            diagnostics.append(
                "roadmap source scan incomplete: skipped oversized file "
                + relative.as_posix()
            )
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
        except (OSError, UnicodeError):
            diagnostics.append(
                "roadmap source scan incomplete: cannot read " + relative.as_posix()
            )
            continue
        overlong_line = False
        for line_number, line in enumerate(lines, start=1):
            if len(line) > MAX_ROADMAP_LINE_CHARS:
                overlong_line = True
                continue
            raw_text = roadmap_item_text(line)
            if raw_text is None or roadmap_task_reference(raw_text, match_tasks):
                continue
            summary = visible_markdown_text(raw_text)
            key = normalize_roadmap_match_text(raw_text)
            if not summary or not key or key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "kind": "roadmap",
                    "summary": summary,
                    "source": f"roadmap:{relative.as_posix()}:{line_number}",
                    "path": relative.as_posix(),
                    "line": line_number,
                }
            )
            if len(candidates) >= MAX_ROADMAP_ITEMS:
                diagnostics.append(
                    "roadmap source scan incomplete: "
                    f"limited emitted items to {MAX_ROADMAP_ITEMS}"
                )
                limit_reached = True
                break
        if overlong_line:
            diagnostics.append(
                "roadmap source scan incomplete: skipped overlong line(s) in "
                + relative.as_posix()
            )
        if limit_reached:
            break
    return candidates, diagnostics


class _UnsafeSiblingPath(OSError):
    """Path-policy rejection for a trusted sibling-module load: symlink, any
    non-regular node (socket / FIFO / directory), a missing path, or a platform
    without ``O_NOFOLLOW``. Distinct from an arbitrary open/read ``OSError`` so a
    caller can route path-policy failures through its own boundary while a real
    I/O fault still reaches the caller's original handler.

    ``reason`` carries the specific policy verdict so a caller can distinguish a
    genuinely absent helper (``missing``) from one that is present but refused
    (``no_o_nofollow`` / ``symlink`` / ``non_regular``). The refusal behavior is
    unchanged either way; only the surfaced diagnostic differs."""

    def __init__(self, message: str, *, reason: str = "unsafe") -> None:
        super().__init__(message)
        self.reason = reason


class _SiblingLoadError(ImportError):
    """The import spec/loader could not be constructed for an already path-safe
    sibling. Subclasses ``ImportError`` so callers whose existing handlers list
    ``ImportError`` classify it exactly as before."""


# errno values where the path itself violates policy: a missing final component,
# a symlinked final component (``ELOOP`` under ``O_NOFOLLOW``), or a non-directory
# in the parent chain. Any other open/read errno is a genuine I/O fault.
_PATH_POLICY_ERRNOS = frozenset(
    value
    for value in (getattr(errno, name, None) for name in ("ENOENT", "ELOOP", "ENOTDIR"))
    if value is not None
)


def _read_trusted_sibling_source(path: Path) -> bytes:
    """Read a sibling module's source with no TOCTOU window.

    Fails closed when ``O_NOFOLLOW`` is unavailable. An advisory ``lstat`` picks
    the caller branch for an unsafe path (missing / symlink / any non-regular
    node) but never authorizes a read; the authoritative gate is the fd-anchored
    ``O_NOFOLLOW`` open plus same-descriptor ``fstat``. ``O_NONBLOCK`` keeps a
    FIFO from blocking the open. Executes nothing. Raises ``_UnsafeSiblingPath``
    for a path-policy failure and lets any other open/read ``OSError`` propagate
    unchanged.
    """
    if not hasattr(os, "O_NOFOLLOW"):
        raise _UnsafeSiblingPath(
            "O_NOFOLLOW unavailable; refusing sibling load", reason="no_o_nofollow"
        )
    try:
        advisory = os.lstat(path)
    except OSError as error:
        if error.errno == errno.ENOENT:
            reason = "missing"
        elif error.errno == errno.ELOOP:
            reason = "symlink"
        elif error.errno == errno.ENOTDIR:
            # A non-directory parent component ⇒ no regular file is resolvable at
            # the computed path ⇒ "not found", not "present but refused".
            reason = "missing"
        else:
            reason = "unsafe"
        raise _UnsafeSiblingPath(str(error), reason=reason) from error
    if stat.S_ISLNK(advisory.st_mode):
        raise _UnsafeSiblingPath(f"{path} is a symlink", reason="symlink")
    if not stat.S_ISREG(advisory.st_mode):
        raise _UnsafeSiblingPath(
            f"{path} is not a regular file", reason="non_regular"
        )
    flags = (
        os.O_RDONLY
        | os.O_NOFOLLOW
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        if error.errno in _PATH_POLICY_ERRNOS:
            if error.errno == errno.ENOENT:
                reason = "missing"
            elif error.errno == errno.ELOOP:
                reason = "symlink"
            elif error.errno == errno.ENOTDIR:
                # Parity with the advisory branch: a non-directory parent means the
                # module is not resolvable ⇒ "missing", not "non_regular".
                reason = "missing"
            else:
                # Defensive: unreachable for the current errno set, safe if it grows.
                reason = "non_regular"
            raise _UnsafeSiblingPath(str(error), reason=reason) from error
        raise
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _UnsafeSiblingPath(
                f"{path} is not a regular file", reason="non_regular"
            )
        chunks = []
        while True:
            block = os.read(descriptor, 65536)
            if not block:
                break
            chunks.append(block)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _exec_sibling_module(source, path, module_name, *, register):
    """Compile and exec already-read (fd-verified) source into a fresh module.

    The module object is built with the real ``spec_from_file_location`` +
    ``module_from_spec`` pair, so its metadata matches the retired loader
    exactly; neither call reads or executes the file. Execution runs on the bytes
    already read from the verified descriptor, never ``loader.exec_module``. When
    ``register`` is true the module is placed in ``sys.modules`` before
    ``compile`` so a compile-time failure leaves the entry registered, matching
    the retired pre-exec registration.
    """
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise _SiblingLoadError(f"cannot construct loader for {path}")
    module = importlib.util.module_from_spec(spec)
    if register:
        sys.modules[module_name] = module
    code = compile(source, str(path), "exec")
    # Trusted sibling; source read from an fd verified regular + non-symlink.
    exec(code, module.__dict__)  # nosec B102
    return module


def collect_work_loop(repo: Path) -> dict[str, Any]:
    """Read the shared user-local loop ledger without mutating it."""
    helper = Path(__file__).resolve().with_name("sd-ai-command-pack-work-loop.py")
    try:
        source = _read_trusted_sibling_source(helper)
        with suppress_bytecode_writes():
            module = _exec_sibling_module(
                source, helper, "sd_ai_command_pack_status_work_loop", register=False
            )
        snapshot = module.status_snapshot(repo)
    except _UnsafeSiblingPath as error:
        if error.reason == "missing":
            return {
                "status": "unavailable",
                "error": "work-loop helper is not installed",
            }
        return {
            "status": "unavailable",
            "error": (
                f"work-loop helper present but refused ({error.reason})"
            ),
        }
    except (
        AttributeError,
        ImportError,
        KeyError,
        OSError,
        RuntimeError,
        SyntaxError,
        TypeError,
        ValueError,
    ) as error:
        return {"status": "invalid", "error": safe_text(error, limit=500)}
    if not isinstance(snapshot, dict):
        return {"status": "invalid", "error": "work-loop helper returned invalid data"}
    return validate_work_loop_snapshot(snapshot)


def validate_work_loop_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Fail closed when a loaded helper does not honor the status contract."""
    status = snapshot.get("status")
    if not isinstance(status, str) or not status:
        return {
            "status": "invalid",
            "error": "work-loop helper returned snapshot without a valid status",
        }
    if status in WORK_LOOP_TERMINAL_STATUSES:
        terminal_snapshot = {"status": status}
        error = snapshot.get("error")
        if status == "none":
            return terminal_snapshot
        if status == "invalid" and error is None:
            return {
                "status": "invalid",
                "error": "work-loop helper reported invalid state without diagnostics",
            }
        if error is None:
            return terminal_snapshot
        if not isinstance(error, str):
            return {
                "status": "invalid",
                "error": "work-loop helper returned invalid terminal snapshot field: error",
            }
        normalized_error = safe_text(error, limit=500)
        if not normalized_error:
            if status == "invalid":
                return {
                    "status": "invalid",
                    "error": "work-loop helper reported invalid state without diagnostics",
                }
            return {
                "status": "invalid",
                "error": "work-loop helper returned invalid terminal snapshot field: error",
            }
        terminal_snapshot["error"] = normalized_error
        return terminal_snapshot
    if status not in WORK_LOOP_RUN_STATUSES:
        return {
            "status": "invalid",
            "error": "work-loop helper returned unsupported status",
        }

    def invalid_field(field: str) -> dict[str, Any]:
        return {
            "status": "invalid",
            "error": f"work-loop helper returned invalid run snapshot field: {field}",
        }

    normalized: dict[str, Any] = {"status": status}
    required_string_limits = {
        "runId": 120,
        "mode": 40,
        "selector": 120,
        "phase": 80,
        "focusMode": 40,
        "heartbeatAt": 80,
    }
    for field in WORK_LOOP_REQUIRED_STRING_FIELDS:
        value = snapshot.get(field)
        if not isinstance(value, str) or not value:
            return invalid_field(field)
        normalized_value = safe_text(value, limit=required_string_limits[field])
        if not normalized_value:
            return invalid_field(field)
        normalized[field] = normalized_value
    iteration = snapshot.get("iteration")
    if (
        isinstance(iteration, bool)
        or not isinstance(iteration, int)
        or iteration < 1
    ):
        return invalid_field("iteration")
    normalized["iteration"] = iteration
    focus = snapshot.get("focus")
    if not isinstance(focus, list) or not all(
        isinstance(value, str) for value in focus
    ):
        return invalid_field("focus")
    if len(focus) > MAX_ITEMS:
        return invalid_field("focus")
    normalized_focus = [safe_text(value, limit=160) for value in focus]
    if any(not value for value in normalized_focus):
        return invalid_field("focus")
    normalized["focus"] = normalized_focus

    counters = snapshot.get("counters")
    if (
        not isinstance(counters, dict)
        or len(counters) > MAX_ITEMS
        or any(
            not isinstance(key, str)
            or not key
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for key, value in counters.items()
        )
    ):
        return invalid_field("counters")
    normalized_counters: dict[str, int] = {}
    for key, value in counters.items():
        normalized_key = safe_text(key, limit=80)
        if not normalized_key or normalized_key in normalized_counters:
            return invalid_field("counters")
        normalized_counters[normalized_key] = value
    normalized["counters"] = normalized_counters

    context_health = snapshot.get("contextHealth")
    if not isinstance(context_health, dict):
        return invalid_field("contextHealth")
    health_level = context_health.get("level")
    if not isinstance(health_level, str) or not health_level:
        return invalid_field("contextHealth.level")
    normalized_health: dict[str, Any] = {
        "level": safe_text(health_level, limit=40)
    }
    if not normalized_health["level"]:
        return invalid_field("contextHealth.level")
    if "epoch" in context_health:
        epoch = context_health["epoch"]
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
            return invalid_field("contextHealth.epoch")
        normalized_health["epoch"] = epoch
    if "reasons" in context_health:
        reasons = context_health["reasons"]
        if (
            not isinstance(reasons, list)
            or len(reasons) > MAX_ITEMS
            or not all(isinstance(value, str) for value in reasons)
        ):
            return invalid_field("contextHealth.reasons")
        normalized_reasons = [safe_text(value, limit=240) for value in reasons]
        if any(not value for value in normalized_reasons):
            return invalid_field("contextHealth.reasons")
        normalized_health["reasons"] = normalized_reasons
    normalized["contextHealth"] = normalized_health

    checkpoint = snapshot.get("checkpoint")
    if not isinstance(checkpoint, dict):
        return invalid_field("checkpoint")
    checkpoint_state = checkpoint.get("state")
    if not isinstance(checkpoint_state, str) or not checkpoint_state:
        return invalid_field("checkpoint.state")
    normalized_checkpoint: dict[str, Any] = {
        "state": safe_text(checkpoint_state, limit=40)
    }
    if not normalized_checkpoint["state"]:
        return invalid_field("checkpoint.state")
    for field, limit in (
        ("target", 240),
        ("reason", 500),
        ("resumePhase", 40),
    ):
        if field not in checkpoint:
            continue
        value = checkpoint[field]
        if value is not None and not isinstance(value, str):
            return invalid_field(f"checkpoint.{field}")
        if value is None:
            normalized_checkpoint[field] = None
            continue
        normalized_value = safe_text(value, limit=limit)
        if not normalized_value:
            return invalid_field(f"checkpoint.{field}")
        normalized_checkpoint[field] = normalized_value
    normalized["checkpoint"] = normalized_checkpoint

    for field, limit in (
        ("until", 40),
        ("task", 160),
        ("branch", 200),
        ("head", 120),
        ("baseBranch", 200),
        ("prUrl", 240),
        ("lastShippedSha", 80),
        ("stopReason", 500),
    ):
        if field not in snapshot:
            continue
        value = snapshot[field]
        if value is not None and not isinstance(value, str):
            return invalid_field(field)
        if value is None:
            normalized[field] = None
            continue
        normalized_value = safe_text(value, limit=limit)
        if not normalized_value:
            return invalid_field(field)
        normalized[field] = normalized_value

    if "prNumber" in snapshot:
        pr_number = snapshot["prNumber"]
        if pr_number is not None and (
            isinstance(pr_number, bool)
            or not isinstance(pr_number, int)
            or pr_number < 1
        ):
            return invalid_field("prNumber")
        normalized["prNumber"] = pr_number

    if "lock" in snapshot:
        lock = snapshot["lock"]
        if not isinstance(lock, dict):
            return invalid_field("lock")
        normalized_lock: dict[str, Any] = {}
        for field in ("present", "stale"):
            if field not in lock:
                continue
            if not isinstance(lock[field], bool):
                return invalid_field(f"lock.{field}")
            normalized_lock[field] = lock[field]
        if "runId" in lock:
            lock_run_id = lock["runId"]
            if lock_run_id is not None and not isinstance(lock_run_id, str):
                return invalid_field("lock.runId")
            if lock_run_id is None:
                normalized_lock["runId"] = None
            else:
                normalized_lock_run_id = safe_text(lock_run_id, limit=120)
                if not normalized_lock_run_id:
                    return invalid_field("lock.runId")
                normalized_lock["runId"] = normalized_lock_run_id
        normalized["lock"] = normalized_lock

    if "terminalReconciliation" in snapshot:
        terminal = snapshot["terminalReconciliation"]
        if terminal is None:
            normalized["terminalReconciliation"] = None
        else:
            if not isinstance(terminal, dict) or set(terminal) != {
                "status",
                "reconciledAt",
                "archivedTask",
                "taskId",
                "delivery",
                "bookkeeping",
                "observed",
            }:
                return invalid_field("terminalReconciliation")
            if terminal.get("status") != "verified":
                return invalid_field("terminalReconciliation.status")
            if status not in {"stopped", "completed"}:
                return invalid_field("terminalReconciliation")
            normalized_terminal: dict[str, Any] = {"status": "verified"}
            for field, limit in (
                ("reconciledAt", 80),
                ("archivedTask", 300),
                ("taskId", 200),
            ):
                value = terminal.get(field)
                if not isinstance(value, str):
                    return invalid_field(f"terminalReconciliation.{field}")
                normalized_value = safe_text(value, limit=limit)
                if not normalized_value:
                    return invalid_field(f"terminalReconciliation.{field}")
                normalized_terminal[field] = normalized_value
            try:
                datetime.fromisoformat(
                    normalized_terminal["reconciledAt"].replace("Z", "+00:00")
                )
            except ValueError:
                return invalid_field("terminalReconciliation.reconciledAt")
            archived_path = normalized_terminal["archivedTask"]
            pure_archived = PurePosixPath(archived_path)
            if (
                "\\" in archived_path
                or pure_archived.as_posix() != archived_path
                or pure_archived.parts[:3] != (".trellis", "tasks", "archive")
                or len(pure_archived.parts) < 5
                or any(part in {"", ".", ".."} for part in pure_archived.parts)
            ):
                return invalid_field("terminalReconciliation.archivedTask")

            def normalize_pr(value: object) -> dict[str, Any] | None:
                if not isinstance(value, dict) or set(value) != {
                    "prNumber",
                    "prUrl",
                    "head",
                    "mergeCommit",
                }:
                    return None
                number = value.get("prNumber")
                url = value.get("prUrl")
                head = value.get("head")
                merge_commit = value.get("mergeCommit")
                if (
                    isinstance(number, bool)
                    or not isinstance(number, int)
                    or number < 1
                    or not isinstance(url, str)
                    or not isinstance(head, str)
                    or COMMIT_RE.fullmatch(head) is None
                    or not isinstance(merge_commit, str)
                    or COMMIT_RE.fullmatch(merge_commit) is None
                ):
                    return None
                safe_url = safe_text(url, limit=500)
                try:
                    split = urlsplit(safe_url)
                    hostname = split.hostname
                    _ = split.port
                    username = split.username
                    password = split.password
                except ValueError:
                    return None
                final_component = split.path.rstrip("/").rsplit("/", 1)[-1]
                if (
                    split.scheme not in {"http", "https"}
                    or not hostname
                    or username is not None
                    or password is not None
                    or split.query
                    or split.fragment
                    or not final_component.isdigit()
                    or int(final_component) != number
                ):
                    return None
                return {
                    "prNumber": number,
                    "prUrl": safe_url,
                    "head": head,
                    "mergeCommit": merge_commit,
                }

            delivery = normalize_pr(terminal.get("delivery"))
            if delivery is None:
                return invalid_field("terminalReconciliation.delivery")
            normalized_terminal["delivery"] = delivery
            bookkeeping = terminal.get("bookkeeping")
            if bookkeeping is None:
                normalized_terminal["bookkeeping"] = None
            else:
                normalized_bookkeeping = normalize_pr(bookkeeping)
                if normalized_bookkeeping is None:
                    return invalid_field("terminalReconciliation.bookkeeping")
                normalized_terminal["bookkeeping"] = normalized_bookkeeping
            observed = terminal.get("observed")
            if (
                not isinstance(observed, dict)
                or set(observed) != {"branch", "head"}
                or not isinstance(observed.get("branch"), str)
                or not safe_text(observed["branch"], limit=200)
                or not isinstance(observed.get("head"), str)
                or COMMIT_RE.fullmatch(observed["head"]) is None
            ):
                return invalid_field("terminalReconciliation.observed")
            normalized_terminal["observed"] = {
                "branch": safe_text(observed["branch"], limit=200),
                "head": observed["head"],
            }
            normalized["terminalReconciliation"] = normalized_terminal

    return normalized


def collect_recovery(repo: Path) -> dict[str, Any]:
    """Classify pack-created recovery artifacts read-only for status.

    Delegates to the recovery-artifacts helper's read-only classifier and
    reduces the result to a bounded summary. Never creates, repairs, or deletes
    a receipt or Git artifact.
    """
    helper = Path(__file__).resolve().with_name(
        "sd-ai-command-pack-recovery-artifacts.py"
    )
    try:
        source = _read_trusted_sibling_source(helper)
        with suppress_bytecode_writes():
            module = _exec_sibling_module(
                source, helper, "sd_ai_command_pack_status_recovery", register=False
            )
        classified = module.classify_repository(repo)
    except _UnsafeSiblingPath as error:
        if error.reason == "missing":
            return {
                "status": "unavailable",
                "error": "recovery-artifacts helper is not installed",
            }
        return {
            "status": "unavailable",
            "error": (
                f"recovery-artifacts helper present but refused ({error.reason})"
            ),
        }
    except (
        AttributeError,
        ImportError,
        KeyError,
        OSError,
        RuntimeError,
        SyntaxError,
        TypeError,
        ValueError,
    ) as error:
        return {"status": "invalid", "error": safe_text(error, limit=500)}
    if not isinstance(classified, dict):
        return {
            "status": "invalid",
            "error": "recovery-artifacts helper returned invalid data",
        }
    expected_schema = getattr(module, "SCHEMA_VERSION", None)
    if expected_schema is None or classified.get("schemaVersion") != expected_schema:
        return {
            "status": "invalid",
            "error": "recovery-artifacts helper returned an unexpected schema version",
        }
    return summarize_recovery(classified)


def summarize_recovery(classified: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce a recovery classification to a bounded, read-only status summary."""
    counts: dict[str, int] = {}
    counts_raw = classified.get("counts")
    if isinstance(counts_raw, Mapping):
        for key, value in counts_raw.items():
            if (
                isinstance(key, str)
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
            ):
                counts[safe_text(key, limit=40)] = value

    actionable: list[dict[str, str]] = []

    def add(kind: object, classification: object, reference: object, detail: object) -> None:
        if len(actionable) >= MAX_ITEMS:
            return
        actionable.append(
            {
                "type": safe_text(kind, limit=40),
                "classification": safe_text(classification, limit=40),
                "reference": safe_text(reference, limit=200),
                "detail": safe_text(detail, limit=200),
            }
        )

    receipts = classified.get("receipts")
    if isinstance(receipts, list):
        for item in receipts:
            if not isinstance(item, Mapping):
                continue
            classification = item.get("classification")
            if classification == "active":
                continue  # in-use artifacts are not actionable
            add(
                item.get("type"),
                classification,
                item.get("reference"),
                item.get("detail"),
            )

    unowned = classified.get("unowned")
    if isinstance(unowned, list):
        for entry in unowned:
            if isinstance(entry, Mapping):
                add(
                    entry.get("type"),
                    "unowned-artifact",
                    entry.get("reference"),
                    entry.get("detail"),
                )

    corrupt = classified.get("corrupt")
    if isinstance(corrupt, list):
        for entry in corrupt:
            if isinstance(entry, Mapping):
                add("receipt", "corrupt", entry.get("reference"), entry.get("reason"))

    return {
        "status": "ok",
        "counts": counts,
        "total": sum(counts.values()),
        "actionable": actionable,
    }


def machine_engine_candidates(
    script: Path, environ: Mapping[str, str]
) -> list[tuple[str, Path]]:
    """Roots that may carry `installer/`, script-adjacent first, then `PATH`.

    Rung one is the arithmetic this function has always used, and it stays
    first so every arrangement that resolves today resolves identically and
    through the same copy. It answers for a pack checkout (`scripts/`), a
    plugin root (`bin/`), and a `~/.agents/bin` that is a symlink into a plugin
    root -- `Path.resolve()` follows the link, so that install needs no rung of
    its own.

    A machine install holding a REAL copy is the arrangement it cannot answer:
    `parent.parent` of `~/.agents/bin/` is `~/.agents`, which ships no
    installer package in any arrangement, so the path the `sd-status` skill
    documents for thin consumers could never resolve the engine (issue #496).

    Rung two is `PATH`, because the pack install whose `bin/` is on `PATH` is a
    root that does carry the package, and `PATH` order is the order in which a
    bare helper invocation would already have reached it. The toolchain
    resolution ladder is deliberately NOT reused here: its rungs are the
    override, `<repo>/scripts`, and `~/.agents/bin`, and the last of those is
    precisely the rung that fails.
    """
    candidates: list[tuple[str, Path]] = [("adjacent", script.resolve().parent.parent)]
    seen = {str(candidates[0][1])}
    for entry in path_pack_bins(environ):
        root = Path(entry["directory"]).resolve().parent
        if str(root) in seen:
            continue
        seen.add(str(root))
        candidates.append(("path", root))
    return candidates


def machine_engine_refusal(root: Path) -> str | None:
    """Why `root` may not supply the engine, or `None` when it may.

    Rung one is exempt from this gate by design: it is the tree already
    executing, and refusing it would make the collector decline to run from a
    checkout the caller trusted enough to invoke. Every other rung names a
    directory an unprivileged process can influence, so a rung that merely
    finds `machinescope.py` would let any writable `PATH` entry choose what
    this collector imports and executes.

    Identity is checked against two markers rather than one because the naive
    choice fails: the plugin cache root -- the arrangement this ladder exists
    to reach -- carries no `manifest.json` at all, only
    `.claude-plugin/plugin.json`. A gate keyed on `manifest.json` alone would
    reject the very root the fix depends on.
    """
    package = root / "installer"
    for required in (package / "__init__.py", package / "machinescope.py"):
        if not required.is_file():
            return f"no {required.name} in {package}"
    if not machine_engine_root_identified(root):
        return (
            "no pack identity: neither manifest.json (name "
            f"{PACK_MANIFEST_NAME!r}) nor .claude-plugin/plugin.json (name "
            f"{PACK_PLUGIN_NAME!r}) is present in {root}"
        )
    # `__init__.py` is in this list because `from installer import machinescope`
    # executes it FIRST. Locking down the module while leaving the package
    # initializer world-writable gates the wrong file: the attacker's code runs
    # before the engine is ever reached.
    for path in (root, package, package / "__init__.py", package / "machinescope.py"):
        try:
            mode = path.stat().st_mode
        except OSError as error:
            return f"cannot inspect {path}: {safe_text(error, limit=120)}"
        if mode & stat.S_IWOTH:
            return f"world-writable: {path}"
    return None


def machine_engine_root_identified(root: Path) -> bool:
    """Whether `root` carries a pack identity marker under either spelling."""
    for relative, expected in (
        (Path("manifest.json"), PACK_MANIFEST_NAME),
        (Path(".claude-plugin") / "plugin.json", PACK_PLUGIN_NAME),
    ):
        path = root / relative
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
        except (OSError, UnicodeError, ValueError):
            continue
        if isinstance(value, dict) and value.get("name") == expected:
            return True
    return False


def machine_scope_api(
    *, environ: Mapping[str, str] | None = None
) -> tuple[Any, str, Path, list[dict[str, str]]]:
    """Load the machine-scope install engine, and say where it came from.

    `installer/` sits next to the directory holding this script in most shipped
    arrangements -- `scripts/` in a pack checkout, `bin/` under a plugin root --
    but NOT in a machine install, which puts this script in `~/.agents/bin/`
    beside no package at all. That third arrangement is why this is a ladder
    rather than one path. A vendored consumer repository reachable by neither
    rung still reports the absence; it is never guessed around.

    The engine resolves the shared helper library through
    ``sys.modules["sd_ai_command_pack_lib"]`` first, and this script has
    already registered that name from its own directory, so the state-root
    ladder in play is the copy beside THIS script rather than the one beside
    the package. Every shipped arrangement ships the same file in both places;
    they diverge only mid-skew (a refreshed package beside stale scripts). The
    loader's first-import-wins rule is deliberate and is not worked around
    here.

    Returns the module, the rung that supplied it, that rung's root, and every
    candidate refused along the way. Refusals are returned rather than dropped:
    a silent skip would degrade to a bare `unavailable`, which is the
    uninformative failure this ladder exists to remove, and would also hide a
    rejected candidate that had no business being on `PATH`.
    """
    env = os.environ if environ is None else environ
    refusals: list[dict[str, str]] = []
    tried: list[str] = []
    for rung, root in machine_engine_candidates(Path(__file__), env):
        tried.append(str(root))
        if rung == "adjacent":
            # Both files, matching the gate below: `machinescope.py` alone is
            # not an importable package, and proceeding on a half-populated
            # root raises out of the loop, so a later rung that would have
            # answered is never tried.
            package = root / "installer"
            if not all(
                (package / name).is_file() for name in ("__init__.py", "machinescope.py")
            ):
                continue
        else:
            refusal = machine_engine_refusal(root)
            if refusal is not None:
                refusals.append(
                    {
                        "root": safe_text(str(root), limit=300),
                        "reason": safe_text(refusal, limit=300),
                    }
                )
                continue
        root_path = str(root)
        inserted = root_path not in sys.path
        if inserted:
            sys.path.insert(0, root_path)
        try:
            with suppress_bytecode_writes():
                from installer import machinescope
        except ImportError as error:
            raise RuntimeError(
                f"machine-scope engine cannot be imported: {safe_text(error, limit=200)}"
            ) from error
        finally:
            if inserted:
                sys.path.remove(root_path)
        return machinescope, rung, root, refusals
    detail = "; ".join(
        f"{entry['root']} ({entry['reason']})" for entry in refusals
    )
    raise RuntimeError(
        "machine-scope engine is not installed beside this script or on PATH "
        f"(tried {', '.join(tried)})" + (f"; refused {detail}" if detail else "")
    )


def collect_plugin_version(repo: Path) -> tuple[str, str | None]:
    """The installed plugin version, or ``unavailable`` and why.

    Every discovery failure -- no CLI, a nonzero exit, unparsable output, a
    missing entry, an entry without a version -- reports ``unavailable``. A
    guess here would let a broken `claude` masquerade as an up-to-date machine.

    Several entries are not a failure. One plugin registered at user scope and
    again per project is the ordinary shape of `claude plugin list --json`, and
    every such entry describes the same install. They are reconciled by the one
    field this function consumes: entries that agree on a version answer with
    it, and only a genuine disagreement is unresolvable. Refusing the agreeing
    case would be the same guess in the other direction -- reporting a machine
    unknowable when it is not.
    """
    if shutil.which("claude") is None:
        return MACHINE_UNAVAILABLE, "the Claude Code CLI is not on PATH"
    result = run_command(["claude", "plugin", "list", "--json"], cwd=repo)
    if result.returncode != 0:
        return (
            MACHINE_UNAVAILABLE,
            f"claude plugin list --json exited {result.returncode}",
        )
    try:
        entries = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return MACHINE_UNAVAILABLE, "claude plugin list --json output is not JSON"
    if not isinstance(entries, list):
        return (
            MACHINE_UNAVAILABLE,
            "claude plugin list --json did not return a plugin array",
        )
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("id") == MACHINE_PLUGIN_ID
    ]
    if not matches:
        return MACHINE_UNAVAILABLE, f"plugin {MACHINE_PLUGIN_ID} is not installed"
    versions: list[str] = []
    for entry in matches:
        version = entry.get("version")
        normalized = safe_text(version, limit=80) if isinstance(version, str) else ""
        if normalized and normalized not in versions:
            versions.append(normalized)
    if not versions:
        return (
            MACHINE_UNAVAILABLE,
            f"no listed {MACHINE_PLUGIN_ID} entry carries a version",
        )
    if len(versions) > 1:
        return (
            MACHINE_UNAVAILABLE,
            f"claude plugin list --json reports {MACHINE_PLUGIN_ID} at "
            f"conflicting versions ({', '.join(sorted(versions))}); reinstall "
            "the plugin so every registration reports one version",
        )
    return versions[0], None


def machine_receipt_state(
    *,
    home: Path | None,
    environ: Mapping[str, str] | None,
    state_home: Path | None,
) -> dict[str, Any]:
    """Receipt state from the engine, without needing a plugin to find it."""

    def unavailable(detail: str) -> dict[str, Any]:
        # Provenance keys are present on every branch, including this one: the
        # caller reads them by name, and a partial shape here would turn a
        # reportable failure into a KeyError inside a read-only status run.
        return {
            "state": MACHINE_UNAVAILABLE,
            "packVersion": None,
            "receiptPath": None,
            "detail": safe_text(detail, limit=300),
            "engineRung": None,
            "engineRoot": None,
            "engineRefusals": [],
        }

    try:
        machinescope, engine_rung, engine_root, engine_refusals = machine_scope_api(
            environ=environ
        )
    except RuntimeError as error:
        return unavailable(str(error))
    try:
        expected_schema = machinescope.STATUS_SCHEMA_VERSION
        report = machinescope.status(
            home=home,
            environ=environ,
            state_home=state_home,
        )
    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        # MachineInstallError (an unresolvable home or state root) subclasses
        # RuntimeError, so a machine the engine cannot reason about reports
        # unavailable instead of raising through a read-only status run.
        return unavailable(f"machine-scope engine failed: {safe_text(error, limit=200)}")
    if not isinstance(report, dict) or report.get("schemaVersion") != expected_schema:
        return unavailable("machine-scope engine returned an unexpected schema version")
    state = report.get("state")
    if state not in MACHINE_RECEIPT_STATES:
        return unavailable("machine-scope engine returned an unsupported state")
    receipt_path = report.get("receiptPath")
    pack_version = report.get("packVersion")
    detail = report.get("detail")
    return {
        "state": state,
        "packVersion": (
            safe_text(pack_version, limit=80)
            if state == "installed" and isinstance(pack_version, str) and pack_version.strip()
            else None
        ),
        "receiptPath": (
            safe_text(receipt_path, limit=500) if isinstance(receipt_path, str) else None
        ),
        "detail": safe_text(detail, limit=300) if isinstance(detail, str) and detail else None,
        # Where the engine came from. The PATH rung's root is version-qualified
        # (`.../sd/<version>/`), so the engine can be a different release from
        # the install it describes -- which is exactly the skew this row exists
        # to surface, and is defensible only while the reader can see it.
        "engineRung": engine_rung,
        "engineRoot": safe_text(str(engine_root), limit=500),
        "engineRefusals": engine_refusals[:MAX_MACHINE_ENGINE_REFUSALS],
    }


def machine_comparison(
    state: object,
    pack_version: object,
    plugin_version: object,
) -> str:
    """Compare the two halves of an update, refusing to guess at either.

    ``unknown`` whenever a version is missing on either side: a broken `claude`
    CLI or an unreadable receipt must never present as ``current``.
    """
    if plugin_version == MACHINE_UNAVAILABLE or state == MACHINE_UNAVAILABLE:
        return "unknown"
    if state == "installed" and pack_version and pack_version == plugin_version:
        return "current"
    return "skew"


def real_path(path: Path) -> str:
    """Compare installs by identity, not by the spelling that reached them.

    A plugin root symlinked into `~/.agents/bin` is one install wearing two
    paths; comparing the spellings would report it as a split it is not.
    """
    try:
        return os.path.realpath(path)
    except OSError:
        return str(path)


def path_pack_bins(environ: Mapping[str, str]) -> list[dict[str, str]]:
    """Every `PATH` entry that holds a toolchain, in `PATH` order.

    Order is the whole point: `PATH` answers with its first match, so the head
    of this list is the install a bare helper name would have reached.
    Duplicate spellings of one directory collapse; two directories that are the
    same install by symlink do not, because both spellings are really on
    `PATH` and the reader is entitled to see that.
    """
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in environ.get("PATH", "").split(os.pathsep):
        if not raw or raw in seen:
            continue
        seen.add(raw)
        candidate = Path(raw) / TOOLCHAIN_FILENAME
        if not candidate.is_file():
            continue
        entries.append(
            {
                "directory": safe_text(raw, limit=500),
                "toolchain": safe_text(str(candidate), limit=500),
            }
        )
        if len(entries) == MAX_PATH_PACK_ENTRIES:
            break
    return entries


def collect_toolchain_resolution(
    repo: Path,
    *,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Which toolchain the shipped bootstrap reaches, and what `PATH` holds.

    This answers a different question from the install-versus-target line above
    it: not which release is installed, but which one a skill's helper
    invocation actually runs, and whether `PATH` disagrees.

    The candidate order mirrors
    ``templates/.agents/skills/sd-help/references/pack-helper-resolution.md``
    exactly. The bootstrap's second candidate is working-directory relative;
    this resolves it against the reported repository, which is the working
    directory of every skill invocation that reports on that repository.

    `shadowed` is advisory. Once every skill reaches its helpers through the
    bootstrap, a stale `PATH` entry runs nothing -- but it is still the thing an
    operator has to remove, and a `PATH` that answers with a different install
    than the bootstrap is worth naming before it becomes load-bearing again.
    """
    env = os.environ if environ is None else environ
    home_root = Path(home) if home is not None else Path.home()
    override = env.get("SD_AI_COMMAND_PACK_TOOLCHAIN") or ""
    candidates: tuple[tuple[str, Path | None], ...] = (
        # `[ -f "" ]` is false in the bootstrap; an empty override is the same
        # miss here rather than a probe of the working directory.
        ("override", Path(override) if override else None),
        ("checkout", repo / "scripts" / TOOLCHAIN_FILENAME),
        ("machine", home_root / ".agents" / "bin" / TOOLCHAIN_FILENAME),
    )
    resolved: Path | None = None
    source = "none"
    for name, candidate in candidates:
        if candidate is not None and candidate.is_file():
            resolved, source = candidate, name
            break

    pack_bins = path_pack_bins(env)
    if resolved is None:
        # The bootstrap's own failure branch: no candidate answered, so the
        # verdict is not about PATH at all.
        verdict = "unresolved"
    elif not pack_bins:
        verdict = "bound"
    elif real_path(Path(pack_bins[0]["toolchain"])) == real_path(resolved):
        verdict = "bound"
    else:
        verdict = "shadowed"

    return {
        "toolchain": safe_text(str(resolved), limit=500) if resolved is not None else None,
        "source": source,
        # The install root, not the directory holding the script: `scripts/` in
        # a source checkout and `bin/` under a machine or plugin root both sit
        # one level below it, so this is the value that names the install.
        "installRoot": (
            safe_text(str(resolved.parent.parent), limit=500)
            if resolved is not None
            else None
        ),
        "pathPackBins": pack_bins,
        "verdict": verdict,
    }


def collect_machine_scope(
    repo: Path,
    *,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    state_home: Path | None = None,
) -> dict[str, Any]:
    """Machine-scope install state against the installed plugin.

    Advisory: this reports on the machine, not the repository, and never
    changes the exit status.
    """
    receipt = machine_receipt_state(home=home, environ=environ, state_home=state_home)
    plugin_version, plugin_detail = collect_plugin_version(repo)
    return {
        "schemaVersion": MACHINE_SCOPE_SCHEMA_VERSION,
        "resolution": collect_toolchain_resolution(repo, home=home, environ=environ),
        "state": receipt["state"],
        "packVersion": receipt["packVersion"],
        "receiptPath": receipt["receiptPath"],
        "detail": receipt["detail"],
        # Carried through, not recomputed: the row a reader sees is the only
        # place the engine's provenance can be seen at all, and a receipt key
        # that stops here renders as an ordinary line that hides a skew.
        "engineRung": receipt["engineRung"],
        "engineRoot": receipt["engineRoot"],
        "engineRefusals": receipt["engineRefusals"],
        "pluginId": MACHINE_PLUGIN_ID,
        "pluginVersion": plugin_version,
        "pluginDetail": plugin_detail,
        "comparison": machine_comparison(
            receipt["state"],
            receipt["packVersion"],
            plugin_version,
        ),
    }


def parse_gh_lines(output: str, *, kind: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in output.splitlines()[:MAX_ITEMS]:
        fields = line.split(PR_SEPARATOR, 2)
        if len(fields) < 2 or not fields[0].isdigit():
            continue
        item = {
            "number": int(fields[0]),
            "title": safe_text(fields[1]),
        }
        if kind == "pr" and len(fields) > 2:
            item["head"] = safe_text(fields[2], limit=120)
        items.append(item)
    return items


def collect_relevant_pr(repo: Path, slug: str, branch: str | None) -> dict[str, Any] | None:
    if not branch:
        return None
    fields = "number,state,mergedAt,url,headRefName,headRefOid"
    jq = (
        "[.number,.state,.mergedAt,.url,.headRefName,.headRefOid] "
        "| map(if . == null then \"\" else tostring end) | join(\"\\u001f\")"
    )
    result = run_command(
        [
            "gh",
            "pr",
            "view",
            "--repo",
            slug,
            "--json",
            fields,
            "--jq",
            jq,
            "--",
            branch,
        ],
        cwd=repo,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    values = result.stdout.strip().split(PR_SEPARATOR)
    if len(values) < 6 or not values[0].isdigit():
        return None
    pr = {
        "number": int(values[0]),
        "state": safe_text(values[1] or "unknown"),
        "mergedAt": safe_text(values[2]) or None,
        "url": safe_text(values[3], limit=240) or None,
        "head": safe_text(values[4], limit=120),
        "headOid": safe_text(values[5], limit=80),
        "checks": "unavailable",
        "reviewCount": None,
    }
    checks = run_command(
        [
            "gh",
            "pr",
            "checks",
            "--repo",
            slug,
            str(pr["number"]),
            "--json",
            "bucket",
            "--jq",
            "[group_by(.bucket)[] | {(.[0].bucket): length}] | add // {}",
        ],
        cwd=repo,
    )
    if checks.returncode == 0 and checks.stdout.strip():
        try:
            parsed_checks = json.loads(checks.stdout)
        except json.JSONDecodeError:
            parsed_checks = None
        if isinstance(parsed_checks, dict):
            pr["checks"] = {
                safe_text(key, limit=40): value
                for key, value in parsed_checks.items()
                if isinstance(value, int)
            }
    owner, separator, name = slug.partition("/")
    if owner and separator and name:
        reviews = run_command(
            [
                "gh",
                "api",
                "graphql",
                "-F",
                f"owner={owner}",
                "-F",
                f"name={name}",
                "-F",
                f"number={pr['number']}",
                "-f",
                f"query={REVIEW_TOTAL_COUNT_QUERY}",
                "--jq",
                ".data.repository.pullRequest.reviews.totalCount",
            ],
            cwd=repo,
        )
        if reviews.returncode == 0 and reviews.stdout.strip().isdigit():
            pr["reviewCount"] = int(reviews.stdout.strip())
    return pr


def collect_release_target(
    pack_source: Path,
    *,
    network: bool,
) -> dict[str, Any]:
    """The newest published pack release tag, or a labeled reason there is none.

    Read-only by construction: `remote get-url` and `ls-remote` are the only
    commands issued, and neither writes the local repository. Every failure is a
    labeled status rather than an exception, because one unreachable remote must
    not cost the operator the whole fleet report.
    """

    def unresolved(status: str, *, tag: str | None = None) -> dict[str, Any]:
        return {"status": status, "version": None, "tag": tag}

    if not network:
        return unresolved("disabled")

    origin = run_command(["git", "remote", "get-url", "origin"], cwd=pack_source)
    if origin.returncode != 0 or not origin.stdout.strip():
        return unresolved("not-configured")

    listing = run_command(
        ["git", "ls-remote", "--tags", "--refs", "origin"],
        cwd=pack_source,
    )
    if listing.returncode != 0:
        return unresolved("unavailable")

    best: tuple[int, int, int] | None = None
    best_tag: str | None = None
    for line in listing.stdout.splitlines():
        _, separator, ref = line.partition("refs/tags/")
        if not separator:
            continue
        match = RELEASE_TAG_RE.match(ref.strip())
        if match is None:
            continue
        # Order on the integer triple, never on the tag string: "v0.9.2" sorts
        # above "v0.71.8" lexicographically, which would report a years-old
        # version as the newest release and read as perfectly well-formed.
        parsed = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if best is None or parsed > best:
            best = parsed
            best_tag = ref.strip()

    if best_tag is None:
        return unresolved("unavailable")
    return {
        "status": "available",
        "version": best_tag.removeprefix("v"),
        "tag": best_tag,
    }


def collect_github(
    repo: Path,
    *,
    slug: str | None,
    branch: str | None,
    network: bool,
) -> dict[str, Any]:
    if not network:
        return {
            "status": "disabled",
            "currentPr": None,
            "openPrs": [],
            "openPrsStatus": "unavailable",
            "openIssues": [],
            "openIssuesStatus": "unavailable",
        }
    if slug is None:
        return {
            "status": "not-configured",
            "currentPr": None,
            "openPrs": [],
            "openPrsStatus": "unavailable",
            "openIssues": [],
            "openIssuesStatus": "unavailable",
        }
    if shutil.which("gh") is None:
        return {
            "status": "gh-unavailable",
            "currentPr": None,
            "openPrs": [],
            "openPrsStatus": "unavailable",
            "openIssues": [],
            "openIssuesStatus": "unavailable",
        }

    pr_result = run_command(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            slug,
            "--state",
            "open",
            "--limit",
            str(MAX_ITEMS),
            "--json",
            "number,title,headRefName",
            "--jq",
            ".[] | [.number,.title,.headRefName] | join(\"\\u001f\")",
        ],
        cwd=repo,
    )
    issue_result = run_command(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            slug,
            "--state",
            "open",
            "--limit",
            str(MAX_ITEMS),
            "--json",
            "number,title",
            "--jq",
            ".[] | [.number,.title] | join(\"\\u001f\")",
        ],
        cwd=repo,
    )
    status = "available"
    if pr_result.returncode != 0 or issue_result.returncode != 0:
        status = "partial"
    return {
        "status": status,
        "currentPr": collect_relevant_pr(repo, slug, branch),
        "openPrs": parse_gh_lines(pr_result.stdout, kind="pr")
        if pr_result.returncode == 0
        else [],
        "openPrsStatus": "available" if pr_result.returncode == 0 else "unavailable",
        "openIssues": parse_gh_lines(issue_result.stdout, kind="issue")
        if issue_result.returncode == 0
        else [],
        "openIssuesStatus": (
            "available" if issue_result.returncode == 0 else "unavailable"
        ),
    }


def classify_local_branches(
    git: Mapping[str, Any],
    github: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Classify every local branch other than the default one.

    Two independent axes. The disposition -- merged, unmerged with an open pull
    request, unmerged without one, or unknown -- answers what the branch is; the
    holding worktree answers whether anyone could act on it. They are orthogonal:
    a branch can be merged and held, or unmerged and PR-less and held, so this
    reports a matrix rather than a set of exclusive labels.

    ``unmerged-without-pull-request`` is the one disposition that is a claim
    about something *not* existing, so it is asserted only from complete
    evidence. Absent, truncated, or stale evidence reports ``unknown`` with the
    reason instead. In particular ``gh pr list`` is bounded at MAX_ITEMS, so a
    full page proves nothing about a branch missing from it. The evidence gates
    guard that absence claim alone: a branch whose open pull request is present
    in the listing is classified from that row, because a present row is direct
    evidence and needs no complete listing behind it.

    Merge evidence is reachability from the local default tip. A branch merged
    by squash or rebase is not reachable and reads unmerged; with its pull
    request closed it then reads PR-less. That is a false positive on an
    advisory row, which is why the row names the branch instead of blocking on
    it -- and why the stale-default gate matters, since it catches the much more
    common case of a default branch that simply has not been pulled.
    """

    default = git.get("defaultBranch")
    local_branches = git.get("localBranches")
    if not isinstance(local_branches, list):
        return {
            "status": "unavailable",
            "evidence": {"pullRequests": "unknown", "defaultBranch": "unknown"},
            "rows": [],
            "truncated": False,
        }

    open_prs: list[Mapping[str, Any]] = []
    pr_evidence = "github_unavailable"
    if isinstance(github, dict):
        raw_prs = github.get("openPrs")
        if github.get("openPrsStatus") == "available" and isinstance(raw_prs, list):
            open_prs = [row for row in raw_prs if isinstance(row, dict)]
            pr_evidence = (
                "pr_evidence_truncated"
                if len(open_prs) >= MAX_ITEMS
                else "available"
            )

    if not git.get("defaultLocalExists"):
        default_evidence = "unknown"
    elif git.get("defaultMatchesRemote") is True:
        default_evidence = "current"
    else:
        default_evidence = "stale"

    merged_value = git.get("mergedIntoDefault")
    merged = set(merged_value) if isinstance(merged_value, list) else None
    held_rows = git.get("worktrees")
    holders: dict[str, str] = {}
    if isinstance(held_rows, dict) and isinstance(held_rows.get("rows"), list):
        for row in held_rows["rows"]:
            if not isinstance(row, dict) or row.get("current"):
                continue
            branch = row.get("branch")
            path = row.get("path")
            if isinstance(branch, str) and branch and isinstance(path, str):
                holders.setdefault(branch, path)

    prs_by_head: dict[str, int] = {}
    for row in open_prs:
        head = row.get("head")
        number = row.get("number")
        if isinstance(head, str) and head and isinstance(number, int):
            prs_by_head.setdefault(head, number)

    extras = sorted(item for item in local_branches if item != default)
    rows: list[dict[str, Any]] = []
    for branch in extras[:MAX_ITEMS]:
        pull_request: int | None = prs_by_head.get(branch)
        if merged is not None and branch in merged:
            disposition = "merged"
            pull_request = None
        elif pull_request is not None:
            # An open pull request is direct evidence that the branch is not
            # merged, on its own authority: it does not derive from the
            # reachability walk, so it survives merge evidence that is stale or
            # missing entirely.
            disposition = "unmerged-with-pull-request"
        elif merged is None or default_evidence != "current":
            # Without trustworthy merge evidence, "unmerged" is not established,
            # so neither is anything that follows from it.
            disposition = "unknown"
        elif pr_evidence == "available":
            disposition = "unmerged-without-pull-request"
        else:
            disposition = "unknown"
        rows.append(
            {
                "branch": safe_text(branch, limit=120),
                "disposition": disposition,
                "pullRequest": pull_request,
                "heldByWorktree": (
                    safe_text(holders[branch], limit=300)
                    if branch in holders
                    else None
                ),
            }
        )
    return {
        "status": "ok",
        "evidence": {
            "pullRequests": pr_evidence,
            "defaultBranch": default_evidence,
        },
        "rows": rows,
        "truncated": len(extras) > MAX_ITEMS,
    }


def branch_classification_anomalies(
    classification: Mapping[str, Any],
) -> list[tuple[str, str]]:
    """Advisory anomalies derived from the branch classification.

    Only the two dispositions that leave a question open produce an entry. A
    merged-but-undeleted branch and a branch with an open pull request are
    ordinary states; reporting them would rebuild the every-run signal this
    classification exists to replace. They stay visible as rows and follow-ups.

    Each message names several branches and the worktree paths holding them,
    all externally controlled, so the assembled string carries the same 500
    character budget every other anomaly source uses. The bound belongs here
    rather than at the append site: the rows survive intact in
    ``localBranchClassification`` for a caller that needs them in full.
    """

    if classification.get("status") != "ok":
        return []
    rows = classification.get("rows")
    if not isinstance(rows, list):
        return []

    def render(row: Mapping[str, Any]) -> str:
        held = row.get("heldByWorktree")
        name = safe_text(row.get("branch"), limit=120)
        return f"{name} [held by {held}]" if held else name

    anomalies: list[tuple[str, str]] = []
    prless = [row for row in rows if row.get("disposition") == "unmerged-without-pull-request"]
    if prless:
        anomalies.append(
            (
                "local_branches_unmerged_without_pr",
                safe_text(
                    f"{len(prless)} local branch(es) are unmerged with no open pull "
                    "request: "
                    + ", ".join(render(row) for row in prless[:HUMAN_ITEM_LIMIT])
                    + (
                        f"; +{len(prless) - HUMAN_ITEM_LIMIT} more"
                        if len(prless) > HUMAN_ITEM_LIMIT
                        else ""
                    ),
                    limit=500,
                ),
            )
        )
    unknown = [row for row in rows if row.get("disposition") == "unknown"]
    if unknown:
        evidence = classification.get("evidence")
        reasons = []
        if isinstance(evidence, dict):
            if evidence.get("pullRequests") != "available":
                reasons.append(str(evidence.get("pullRequests")))
            if evidence.get("defaultBranch") != "current":
                reasons.append(f"default_branch_{evidence.get('defaultBranch')}")
        anomalies.append(
            (
                "local_branches_pr_state_unknown",
                safe_text(
                    f"{len(unknown)} local branch(es) could not be classified "
                    f"({', '.join(reasons) or 'incomplete evidence'}); this is an "
                    "unknown, not a claim that they have no pull request",
                    limit=500,
                ),
            )
        )
    return anomalies


def strict_anomalies(
    git: Mapping[str, Any],
    *,
    default: str | None,
    remote: str,
    source_branch: str | None,
    keep_remote_branch: bool,
    dry_run: bool,
) -> list[tuple[str, str, str]]:
    """Postconditions of a housekeeping run, as (code, severity, message).

    Every entry here is something *this run* was supposed to achieve. Leftover
    local branches the run never touched are deliberately absent: they are
    pre-existing repository state, they are a normal steady state for anyone
    running concurrent worktrees, and blocking on them produced a verdict that
    fired on every successful merge and therefore carried no information. They
    are classified instead, in both modes, by classify_local_branches. What that
    entry incidentally covered -- a source branch that survived deletion -- is
    checked explicitly below.
    """

    anomalies: list[tuple[str, str, str]] = []
    tree = git.get("workingTree")
    if isinstance(tree, dict) and tree.get("state") != "clean":
        anomalies.append(
            (
                "working_tree_dirty",
                SEVERITY_BLOCKING,
                "working tree is dirty after housekeeping",
            )
        )
    if dry_run:
        return anomalies
    branch = git.get("branch")
    if default is None:
        anomalies.append(
            (
                "default_branch_unknown",
                SEVERITY_BLOCKING,
                "default branch is unknown; skipped branch inventory checks",
            )
        )
        return anomalies
    if branch != default:
        anomalies.append(
            (
                "current_branch_unexpected",
                SEVERITY_BLOCKING,
                f"current branch is {safe_text(branch or 'detached HEAD')}, expected {safe_text(default)}",
            )
        )
    if not git.get("defaultLocalExists"):
        anomalies.append(
            (
                "default_branch_local_missing",
                SEVERITY_BLOCKING,
                f"local default branch {safe_text(default)} does not exist",
            )
        )
    elif not git.get("defaultRemoteExists"):
        anomalies.append(
            (
                "default_branch_remote_missing",
                SEVERITY_BLOCKING,
                f"remote default branch {safe_text(remote)}/{safe_text(default)} does not exist",
            )
        )
    elif git.get("defaultMatchesRemote") is not True:
        anomalies.append(
            (
                "default_branch_diverged",
                SEVERITY_BLOCKING,
                f"{safe_text(default)} does not match {safe_text(remote)}/{safe_text(default)}",
            )
        )
    local_branches = git.get("localBranches")
    if (
        source_branch
        and source_branch != default
        and isinstance(local_branches, list)
        and source_branch in local_branches
    ):
        held = git.get("branchesHeldElsewhere")
        holder = None
        if isinstance(held, list) and source_branch in held:
            worktrees = git.get("worktrees")
            if isinstance(worktrees, dict) and isinstance(worktrees.get("rows"), list):
                for row in worktrees["rows"]:
                    if (
                        isinstance(row, dict)
                        and row.get("branch") == source_branch
                        and not row.get("current")
                        and isinstance(row.get("path"), str)
                    ):
                        holder = row["path"]
                        break
        if holder is not None:
            # Held by a live worktree: deletion was impossible, not skipped.
            # Blocking on a condition the operator cannot resolve is what made
            # the old leftover-branch entry useless.
            anomalies.append(
                (
                    "local_source_branch_held_elsewhere",
                    SEVERITY_ADVISORY,
                    f"source branch {safe_text(source_branch)} still exists; it is "
                    f"checked out in worktree {safe_text(holder, limit=300)}",
                )
            )
        else:
            anomalies.append(
                (
                    "local_source_branch_retained",
                    SEVERITY_BLOCKING,
                    f"source branch {safe_text(source_branch)} still exists after housekeeping",
                )
            )
    if source_branch and source_branch != default:
        remote_ref = f"{remote}/{source_branch}"
        remote_branches = git.get("remoteBranches")
        present = isinstance(remote_branches, list) and remote_ref in remote_branches
        if keep_remote_branch and not present:
            anomalies.append(
                (
                    "remote_source_branch_missing",
                    SEVERITY_BLOCKING,
                    f"remote source branch {safe_text(remote_ref)} is absent despite --keep-remote-branch",
                )
            )
        elif not keep_remote_branch and present:
            anomalies.append(
                (
                    "remote_source_branch_retained",
                    SEVERITY_BLOCKING,
                    f"remote source branch still tracked: {safe_text(remote_ref)}",
                )
            )
    return anomalies


def anomaly_details(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Typed anomalies, synthesizing them for a report that predates the key.

    A report without ``anomalyDetails`` is treated as entirely blocking rather
    than as having no anomalies: an unknown severity is a reason to stop, not a
    reason to proceed quietly.
    """

    details = report.get("anomalyDetails")
    if isinstance(details, list):
        return [item for item in details if isinstance(item, dict)]
    messages = report.get("anomalies")
    if not isinstance(messages, list):
        return []
    return [
        {"code": "status_anomaly", "severity": SEVERITY_BLOCKING, "message": message}
        for message in messages
    ]


def blocking_anomalies(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Anomalies that stop a caller, as opposed to ones it should merely see.

    An advisory anomaly is real and reported; it just is not a failure of the
    run that observed it. The exit status, the human attention header, and the
    housekeeping verdict all key on this subset so that a condition nobody can
    act on -- a branch held by another live worktree, say -- stays visible
    without producing a blocked verdict on every successful merge.
    """

    return [
        item
        for item in anomaly_details(report)
        if item.get("severity") != SEVERITY_ADVISORY
    ]


def collect_follow_ups(
    report: Mapping[str, Any],
    *,
    roadmap_candidates: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(
        kind: str,
        summary: str,
        source: str,
        *,
        path: str | None = None,
        line: int | None = None,
    ) -> None:
        normalized_summary = safe_text(summary, limit=500)
        key = (kind, normalized_summary)
        if key in seen:
            return
        seen.add(key)
        candidate: dict[str, Any] = {
            "kind": kind,
            "summary": normalized_summary,
            "source": source,
        }
        if path is not None:
            candidate["path"] = safe_text(path, limit=500)
        if line is not None:
            candidate["line"] = line
        candidates.append(candidate)

    for detail in anomaly_details(report):
        message = detail.get("message")
        if not isinstance(message, str):
            continue
        if detail.get("severity") == SEVERITY_ADVISORY:
            add("recommendation", f"Status advisory: {message}", "anomalies")
        else:
            add("issue", f"Resolve status anomaly: {message}", "anomalies")
    classification = report.get("localBranchClassification")
    if isinstance(classification, dict) and classification.get("status") == "ok":
        deletable = [
            row.get("branch")
            for row in classification.get("rows", [])
            if isinstance(row, dict)
            and row.get("disposition") == "merged"
            and not row.get("heldByWorktree")
        ]
        if deletable:
            shown = ", ".join(str(name) for name in deletable[:HUMAN_ITEM_LIMIT])
            suffix = (
                f"; +{len(deletable) - HUMAN_ITEM_LIMIT} more"
                if len(deletable) > HUMAN_ITEM_LIMIT
                else ""
            )
            add(
                "action",
                f"Delete {len(deletable)} merged local branch(es) no worktree holds: "
                f"{shown}{suffix}",
                "localBranchClassification",
            )

    git_value = report.get("git")
    git: Mapping[str, Any] = git_value if isinstance(git_value, dict) else {}
    tree_value = git.get("workingTree")
    tree: Mapping[str, Any] = tree_value if isinstance(tree_value, dict) else {}
    if tree.get("state") == "dirty":
        add(
            "action",
            "Review and commit or intentionally discard the current working-tree changes.",
            "git.workingTree",
        )
    sync = git.get("syncState")
    if sync == "behind":
        add(
            "action",
            "Fast-forward the current branch from its upstream before new work.",
            "git.syncState",
        )
    elif sync == "ahead":
        add(
            "action",
            "Push the local commits or confirm they are intentionally local-only.",
            "git.syncState",
        )
    elif sync == "diverged":
        add(
            "action",
            "Reconcile the diverged local and upstream histories before publishing.",
            "git.syncState",
        )
    elif sync == "no-upstream":
        add(
            "action",
            "Configure or verify the branch upstream before publishing new work.",
            "git.syncState",
        )

    github = report.get("github")
    if isinstance(github, dict):
        pr = github.get("currentPr")
        if isinstance(pr, dict) and pr.get("state") == "OPEN":
            add(
                "action",
                f"Continue PR #{pr.get('number')} through sd-ship or sd-housekeeping.",
                "github.currentPr",
            )

    work_loop = report.get("workLoop")
    if isinstance(work_loop, dict):
        loop_status = work_loop.get("status")
        run_id = work_loop.get("runId")
        if loop_status == "active":
            add(
                "action",
                f"Resume active SD work loop {run_id} at iteration "
                f"{work_loop.get('iteration')} phase {work_loop.get('phase')}.",
                "workLoop.status",
            )
        elif loop_status == "paused":
            add(
                "action",
                f"Resume paused SD work loop {run_id} from its recorded checkpoint.",
                "workLoop.status",
            )
        terminal_reconciliation = work_loop.get("terminalReconciliation")
        terminal_verified = (
            isinstance(terminal_reconciliation, dict)
            and terminal_reconciliation.get("status") == "verified"
        )
        health = work_loop.get("contextHealth")
        if (
            isinstance(health, dict)
            and health.get("level") == "red"
            and not terminal_verified
        ):
            add(
                "issue",
                "Reconcile the red SD work-loop checkpoint with live Trellis, Git, and PR state.",
                "workLoop.contextHealth",
            )

    trellis = report.get("trellis")
    if isinstance(trellis, dict) and trellis.get("completedOutsideArchive"):
        add(
            "action",
            "Archive completed active-root Trellis tasks with "
            "python3 ./.trellis/scripts/task.py archive <task-dir>.",
            "trellis.completedOutsideArchive",
        )

    versions = report.get("versions")
    if isinstance(versions, dict) and versions.get("packState") == "different":
        add(
            "recommendation",
            "Refresh the installed SD command pack to the source fleet version.",
            "versions.packState",
        )

    if isinstance(github, dict) and github.get("openIssuesStatus") == "available":
        issues = github.get("openIssues")
        if isinstance(issues, list):
            valid_issues = [issue for issue in issues if isinstance(issue, dict)]
            for issue in sorted(
                valid_issues,
                key=lambda item: (
                    item.get("number") if isinstance(item.get("number"), int) else 0,
                    str(item.get("title", "")).casefold(),
                ),
            ):
                add(
                    "issue",
                    f"Review GitHub issue #{issue.get('number')}: {issue.get('title')}",
                    "github.openIssues",
                )

    for candidate in roadmap_candidates:
        path = candidate.get("path")
        line = candidate.get("line")
        if (
            candidate.get("kind") == "roadmap"
            and isinstance(path, str)
            and isinstance(line, int)
            and not isinstance(line, bool)
            and line > 0
        ):
            add(
                "roadmap",
                str(candidate.get("summary", "")),
                str(candidate.get("source", "")),
                path=path,
                line=line,
            )

    return select_items(candidates, prefix="F")


def next_steps(report: Mapping[str, Any]) -> list[str]:
    steps: list[str] = []
    if blocking_anomalies(report):
        steps.append("Resolve the reported anomalies, then rerun sd-status.")
    git_value = report.get("git")
    git: Mapping[str, Any] = git_value if isinstance(git_value, dict) else {}
    tree_value = git.get("workingTree")
    tree: Mapping[str, Any] = tree_value if isinstance(tree_value, dict) else {}
    if tree.get("state") == "dirty":
        steps.append("Review and commit or intentionally discard the current working-tree changes.")
    sync = git.get("syncState")
    if sync == "behind":
        steps.append("Fast-forward the current branch from its upstream before new work.")
    elif sync == "ahead":
        steps.append("Push the local commits or confirm they are intentionally local-only.")
    elif sync == "diverged":
        steps.append("Reconcile the diverged local and upstream histories before publishing.")
    elif sync == "no-upstream":
        steps.append("Configure or verify the branch upstream before publishing new work.")
    versions = report.get("versions")
    if isinstance(versions, dict) and versions.get("packState") == "different":
        steps.append(
            "Refresh the installed SD command pack to the source fleet version."
        )
    github = report.get("github")
    if isinstance(github, dict) and isinstance(github.get("currentPr"), dict):
        pr = github["currentPr"]
        if pr.get("state") == "OPEN":
            steps.append(f"Continue PR #{pr.get('number')} through sd-ship or sd-housekeeping.")
    work_loop = report.get("workLoop")
    if isinstance(work_loop, dict):
        loop_status = work_loop.get("status")
        run_id = work_loop.get("runId")
        if loop_status == "active":
            steps.append(
                f"Resume active SD work loop {run_id} at iteration "
                f"{work_loop.get('iteration')} phase {work_loop.get('phase')}."
            )
        elif loop_status == "paused":
            steps.append(
                f"Resume paused SD work loop {run_id} from its recorded checkpoint."
            )
        terminal_reconciliation = work_loop.get("terminalReconciliation")
        terminal_verified = (
            isinstance(terminal_reconciliation, dict)
            and terminal_reconciliation.get("status") == "verified"
        )
        if isinstance(work_loop.get("contextHealth"), dict) and work_loop[
            "contextHealth"
        ].get("level") == "red" and not terminal_verified:
            steps.append(
                "Reconcile the red SD work-loop checkpoint with live Trellis, Git, and PR state."
            )
    recovery = report.get("recoveryArtifacts")
    if isinstance(recovery, dict) and recovery.get("status") == "ok":
        counts = recovery.get("counts")
        counts = counts if isinstance(counts, dict) else {}
        cleanable = counts.get("safe-cleanable")
        if isinstance(cleanable, int) and cleanable > 0:
            steps.append(
                f"Retire {cleanable} safe-cleanable recovery artifact(s) via sd-housekeeping."
            )
        review = sum(
            value
            for name in ("needs-review", "unowned-artifact")
            if isinstance((value := counts.get(name)), int)
        )
        if review > 0:
            steps.append(
                f"Inspect {review} recovery artifact(s) flagged for review before cleanup."
            )
    trellis = report.get("trellis")
    if isinstance(trellis, dict):
        completed_outside_archive = trellis.get("completedOutsideArchive")
        if completed_outside_archive:
            steps.append(
                "Archive completed active-root Trellis tasks with "
                "python3 ./.trellis/scripts/task.py archive <task-dir>."
            )
        active = trellis.get("activeTask")
        if isinstance(active, dict):
            steps.append(
                f"Resume Trellis task {active.get('id')}: {active.get('title')}."
            )
        elif trellis.get("inProgress"):
            task = trellis["inProgress"][0]
            steps.append(
                f"Resume in-progress Trellis task {task.get('id')}: {task.get('title')}."
            )
        elif trellis.get("planned"):
            task = trellis["planned"][0]
            steps.append(
                f"Consider planned Trellis task {task.get('id')}: {task.get('title')}."
            )
    if not steps:
        steps.append("No immediate repository action is required.")
    return steps[:HUMAN_ITEM_LIMIT]


def collect_local(
    requested_repo: Path,
    *,
    remote: str,
    supplied_default: str | None,
    source_branch: str | None,
    github_repo: str | None,
    network: bool,
    refs_refreshed: bool,
    expect_clean: bool,
    keep_remote_branch: bool,
    dry_run: bool,
    prior_anomalies: Sequence[Sequence[str]],
    target_pack_version: str | None = None,
    include_machine_scope: bool = True,
) -> dict[str, Any] | None:
    repo = resolve_repo(requested_repo)
    if repo is None:
        return None
    git, anomalies = collect_git(
        repo,
        remote=remote,
        supplied_default=supplied_default,
        refs_refreshed=refs_refreshed,
    )
    if not git:
        return None
    slug = github_repo or git.get("github")
    if not isinstance(slug, str) or not GITHUB_SLUG_RE.fullmatch(slug):
        slug = None
    default = git.get("defaultBranch")
    relevant_branch = source_branch
    if relevant_branch is None and git.get("branch") != default:
        relevant_branch = git.get("branch")
    work_loop = collect_work_loop(repo)
    recovery = collect_recovery(repo)
    trellis = collect_trellis(repo)
    roadmap_candidates, roadmap_diagnostics = collect_roadmap_candidates(
        repo,
        trellis.get("tasks", []),
    )
    report: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "mode": "local",
        "repository": {
            "path": str(repo),
            "name": repo.name,
            "github": slug,
        },
        "git": git,
        "versions": collect_versions(repo, target_pack_version),
        "github": collect_github(
            repo,
            slug=slug,
            branch=relevant_branch if isinstance(relevant_branch, str) else None,
            network=network,
        ),
        "trellis": trellis,
        "workLoop": work_loop,
        "recoveryArtifacts": recovery,
        # Machine scope describes the machine, not this checkout: a fleet run
        # would repeat one identical answer per consumer, so it opts out.
        "machineScope": collect_machine_scope(repo) if include_machine_scope else None,
        "cleanupContext": {
            "sourceBranch": source_branch,
            "keepRemoteBranch": keep_remote_branch,
            "dryRun": dry_run,
        }
        if source_branch or dry_run
        else None,
        "anomalies": [],
        "anomalyDetails": [],
        "localBranchClassification": {},
        "followUps": [],
        "nextSteps": [],
    }
    # One construction path for both views, so the parallel invariant between
    # `anomalies` and `anomalyDetails` cannot drift: same length, same order,
    # identical messages. `anomalies` keeps its list-of-strings shape for every
    # existing reader; `anomalyDetails` adds the stable code and the severity
    # that decides the exit status and the housekeeping verdict.
    details: list[tuple[str, str, str]] = []
    # Replayed caller anomalies keep the caller's own code, so severity here
    # matches the severity the caller's typed channel reports. Anything else
    # would let one run exit nonzero while its verdict reads clean.
    for code, message in prior_anomalies:
        normalized = code if ANOMALY_CODE_RE.fullmatch(code) else "prior_anomaly"
        details.append(
            (
                normalized,
                SEVERITY_ADVISORY
                if normalized in ADVISORY_CALLER_ANOMALY_CODES
                else SEVERITY_BLOCKING,
                safe_text(message, limit=500),
            )
        )
    details.extend(anomalies)
    for diagnostic in roadmap_diagnostics:
        details.append(
            (
                "roadmap_source_unreadable",
                SEVERITY_BLOCKING,
                safe_text(diagnostic, limit=500),
            )
        )
    if work_loop.get("status") == "invalid":
        details.append(
            (
                "work_loop_state_invalid",
                SEVERITY_BLOCKING,
                "work-loop state is invalid: "
                + safe_text(work_loop.get("error") or "unknown error", limit=400),
            )
        )
    if recovery.get("status") == "invalid":
        details.append(
            (
                "recovery_state_invalid",
                SEVERITY_BLOCKING,
                "recovery-artifact state is invalid: "
                + safe_text(recovery.get("error") or "unknown error", limit=400),
            )
        )
    machine_scope = report["machineScope"]
    if isinstance(machine_scope, dict) and machine_scope.get("state") == "invalid":
        # Same rule the two user-local ledgers above follow: a corrupt state
        # file is an anomaly, an unreadable one (`unavailable`) is not.
        details.append(
            (
                "machine_receipt_invalid",
                SEVERITY_BLOCKING,
                "machine-scope receipt is invalid: "
                + safe_text(machine_scope.get("detail") or "unknown error", limit=400),
            )
        )
    # A `shadowed` helper-resolution verdict is deliberately not an anomaly. It
    # follows the same rule as this section's `skew` comparison: machine scope
    # describes the machine, not this repository, so it is reported in its own
    # row and never promoted into a repository finding that would gate
    # --expect-clean on which other installs happen to sit on the operator's
    # PATH.
    completed_outside_archive = trellis.get("completedOutsideArchive", [])
    if completed_outside_archive:
        shown = ", ".join(
            safe_text(task.get("path") or task.get("id"), limit=160)
            for task in completed_outside_archive[:HUMAN_ITEM_LIMIT]
        )
        suffix = (
            f"; +{len(completed_outside_archive) - HUMAN_ITEM_LIMIT} more"
            if len(completed_outside_archive) > HUMAN_ITEM_LIMIT
            else ""
        )
        details.append(
            (
                "completed_tasks_outside_archive",
                SEVERITY_BLOCKING,
                f"{len(completed_outside_archive)} completed Trellis task(s) remain "
                f"outside .trellis/tasks/archive/: {shown}{suffix}",
            )
        )
    # The leftover-branch classification is computed in both modes from one
    # code path, which is what lets the advisory and strict surfaces report the
    # same findings instead of disagreeing about the same repository.
    classification = classify_local_branches(git, report["github"])
    report["localBranchClassification"] = classification
    for code, message in branch_classification_anomalies(classification):
        details.append((code, SEVERITY_ADVISORY, message))
    if expect_clean:
        details.extend(
            strict_anomalies(
                git,
                default=default if isinstance(default, str) else None,
                remote=remote,
                source_branch=source_branch,
                keep_remote_branch=keep_remote_branch,
                dry_run=dry_run,
            )
        )
    report["anomalies"] = [message for _, _, message in details]
    report["anomalyDetails"] = [
        {"code": code, "severity": severity, "message": message}
        for code, severity, message in details
    ]
    report["followUps"] = collect_follow_ups(
        report,
        roadmap_candidates=roadmap_candidates,
    )
    report["nextSteps"] = next_steps(report)
    return report


def format_working_tree(tree: Mapping[str, Any]) -> str:
    if tree.get("state") == "clean":
        return "clean"
    return (
        f"dirty (staged {tree.get('staged', 0)}, "
        f"unstaged {tree.get('unstaged', 0)}, untracked {tree.get('untracked', 0)})"
    )


def format_machine_scope(section: object) -> str:
    """One line carrying both halves of the update and their comparison.

    Both diagnostics are spelled out rather than reduced to a bare
    ``unavailable``: the reader has to be able to tell a machine with no
    install from one whose plugin version could not be read.
    """
    if not isinstance(section, dict):
        return "not collected; plugin unavailable; unknown"
    state = section.get("state")
    pack_version = section.get("packVersion")
    machine = (
        f"installed {pack_version}"
        if state == "installed" and pack_version
        else str(state)
    )
    detail = section.get("detail")
    if detail:
        machine += f" ({detail})"
    # Named only when the engine did NOT come from beside this script, so the
    # common arrangement's line is unchanged and the unusual one is legible:
    # an engine loaded from a version-qualified plugin root may describe an
    # install of a different release.
    if section.get("engineRung") not in (None, "adjacent"):
        machine += f" [engine via {section.get('engineRung')}: {section.get('engineRoot')}]"
    refusals = section.get("engineRefusals")
    if isinstance(refusals, list) and refusals:
        rejected = "; ".join(
            f"{entry.get('root')} ({entry.get('reason')})"
            for entry in refusals
            if isinstance(entry, dict)
        )
        if rejected:
            machine += f" [refused {rejected}]"
    plugin = str(section.get("pluginVersion"))
    plugin_detail = section.get("pluginDetail")
    if plugin_detail:
        plugin += f" ({plugin_detail})"
    return f"{machine}; plugin {plugin}; {section.get('comparison')}"


def format_toolchain_resolution(section: object) -> str:
    """The resolved toolchain, the `PATH` entries, and the verdict.

    Its own row, never folded into the line above: that line answers which
    release is installed, and a reader who cannot separate the two questions
    will read a clean install as proof that no split exists.
    """
    if not isinstance(section, dict):
        return "not collected"
    resolution = section.get("resolution")
    if not isinstance(resolution, dict):
        return "not collected"
    verdict = str(resolution.get("verdict"))
    toolchain = resolution.get("toolchain")
    if not toolchain:
        return f"{verdict}; no toolchain found (checked override, scripts/, ~/.agents/bin)"
    bins = resolution.get("pathPackBins")
    entries = bins if isinstance(bins, list) else []
    if entries:
        listed = ", ".join(
            str(entry.get("directory")) for entry in entries if isinstance(entry, dict)
        )
        path_summary = f"PATH pack bins ({len(entries)}, in order): {listed}"
    else:
        path_summary = "no pack bin on PATH"
    return (
        f"{verdict}; {toolchain} (via {resolution.get('source')}, "
        f"root {resolution.get('installRoot')}); {path_summary}"
    )


def format_task(task: object) -> str:
    if not isinstance(task, dict):
        return "none active"
    return f"{task.get('id')} [{task.get('status')}, {task.get('priority')}]: {task.get('title')}"


def format_items(items: object) -> str:
    if not isinstance(items, list) or not items:
        return "none"
    shown = [f"#{item.get('number')}: {item.get('title')}" for item in items[:HUMAN_ITEM_LIMIT]]
    suffix = f"; +{len(items) - HUMAN_ITEM_LIMIT} more" if len(items) > HUMAN_ITEM_LIMIT else ""
    return "; ".join(shown) + suffix


def format_selectable_task(task: Mapping[str, Any]) -> str:
    parent = task.get("parent")
    parent_suffix = f"; parent {parent}" if isinstance(parent, str) else ""
    return (
        f"{task.get('selectionId')} [{task.get('status')}, {task.get('priority')}]: "
        f"{task.get('title')} ({task.get('id')}; {task.get('path')}{parent_suffix})"
    )


def render_selectable_inventory(
    heading: str,
    items: object,
    *,
    task_items: bool,
) -> None:
    print(f"\n==> {heading}")
    if not isinstance(items, list) or not items:
        print("none")
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        if task_items:
            print(format_selectable_task(item))
        else:
            suffix = ""
            if (
                item.get("kind") == "roadmap"
                and isinstance(item.get("path"), str)
                and isinstance(item.get("line"), int)
            ):
                suffix = f" ({item.get('path')}:{item.get('line')})"
            print(
                f"{item.get('selectionId')} [{item.get('kind')}]: "
                f"{item.get('summary')}{suffix}"
            )


def render_local(report: Mapping[str, Any], *, dry_run: bool) -> None:
    repository = report["repository"]
    git = report["git"]
    tree = git["workingTree"]
    attention = (
        bool(blocking_anomalies(report))
        or tree.get("state") != "clean"
        or git.get("syncState") != "synchronized"
    )
    print(f"SD status: {'attention' if attention else 'healthy'}")
    identity = repository.get("github") or repository.get("name")
    print(f"Repository: {safe_text(identity)} ({repository.get('path')})")
    print(f"Ref freshness: {git.get('refsFreshness')}")

    print("\n==> Expected clean state")
    branch = git.get("branch") or f"detached at {git.get('head') or 'unknown'}"
    print(f"- branch: {branch}")
    print(f"- working tree: {format_working_tree(tree)}")
    default = git.get("defaultBranch") or "unknown"
    upstream = git.get("upstream") or "none"
    print(
        f"- upstream: {upstream}; {git.get('syncState')} "
        f"(ahead {git.get('ahead') if git.get('ahead') is not None else 'n/a'}, "
        f"behind {git.get('behind') if git.get('behind') is not None else 'n/a'}; "
        f"{git.get('refsFreshness')} refs)"
    )
    print(f"- default branch: {default}")
    comparison = git.get("defaultMatchesRemote")
    if comparison is True:
        print(f"- default comparison: {default} matches {git.get('remote')}/{default}")
    elif comparison is False:
        print(f"- default comparison: {default} differs from {git.get('remote')}/{default}")
    local_branches = git.get("localBranches") or []
    remote_branches = git.get("remoteBranches") or []
    held_elsewhere = set(git.get("branchesHeldElsewhere") or [])
    branch_labels = [
        f"{name} [worktree]" if name in held_elsewhere else name
        for name in local_branches
    ]
    print(f"- local branches ({len(local_branches)}): {', '.join(branch_labels) or 'none'}")
    print(f"- remote branches ({len(remote_branches)}): {', '.join(remote_branches[:10]) or 'none'}")
    stash_count = git.get("stashCount")
    print(f"- git stashes: {stash_count if isinstance(stash_count, int) else 'unavailable'}")
    cleanup = report.get("cleanupContext")
    if dry_run:
        print(
            "- dry-run preview: skipped final git-state verification because no "
            "fetch, pull, switch, or branch deletion was performed"
        )
    elif isinstance(cleanup, dict):
        source_branch = cleanup.get("sourceBranch")
        if isinstance(source_branch, str) and source_branch and source_branch != default:
            remote_ref = f"{git.get('remote') or 'origin'}/{source_branch}"
            if remote_ref in remote_branches:
                label = "kept" if cleanup.get("keepRemoteBranch") else "still tracked"
                print(f"- remote source branch {label}: {remote_ref}")
            else:
                print(f"- remote source branch absent: {remote_ref}")

    print("\n==> Worktrees")
    worktrees = git.get("worktrees")
    if not isinstance(worktrees, dict) or worktrees.get("status") != "ok":
        print("- worktrees: unavailable")
    else:
        worktree_rows = worktrees.get("rows") or []
        if len(worktree_rows) <= 1:
            print("- linked worktrees: none")
        else:
            worktree_limit = HUMAN_ITEM_LIMIT * 2
            for row in worktree_rows[:worktree_limit]:
                if row.get("branch"):
                    checkout = f"branch {row['branch']}"
                elif row.get("detached"):
                    checkout = f"detached at {row.get('head') or 'unknown'}"
                elif row.get("bare"):
                    checkout = "bare"
                else:
                    checkout = "no branch"
                if row.get("prunable"):
                    state_label = "prunable"
                elif row.get("clean") is True:
                    state_label = "clean"
                elif row.get("clean") is False:
                    state_label = "dirty"
                else:
                    state_label = "unknown"
                if row.get("locked"):
                    state_label += ", locked"
                if row.get("reason"):
                    state_label += f" ({row['reason']})"
                suffix = " (reporting)" if row.get("current") else ""
                print(f"- {row.get('path')}: {checkout}, {state_label}{suffix}")
            if len(worktree_rows) > worktree_limit:
                print(f"- ; +{len(worktree_rows) - worktree_limit} more")

    versions = report["versions"]
    print("\n==> Delivery")
    pack = versions.get("sdAiCommandPack") or "not installed"
    target = versions.get("targetPack")
    target_suffix = f"; target {target}" if target else ""
    print(f"- SD pack: {pack} ({versions.get('packState')}{target_suffix})")
    print(f"- machine scope: {format_machine_scope(report.get('machineScope'))}")
    print(
        "- helper resolution: "
        f"{format_toolchain_resolution(report.get('machineScope'))}"
    )
    print(f"- Trellis: {versions.get('trellis') or 'unknown'}")
    pr = report["github"].get("currentPr")
    if isinstance(pr, dict):
        merged = f"; merged {pr.get('mergedAt')}" if pr.get("mergedAt") else ""
        print(f"- relevant PR: #{pr.get('number')} {pr.get('state')}{merged}")
        print(f"- PR checks: {pr.get('checks')}")
        reviews = pr.get("reviewCount")
        print(f"- PR review rounds: {reviews if reviews is not None else 'unavailable'}")
    else:
        print("- relevant PR: none")

    work_loop = report.get("workLoop")
    print("\n==> Work Loop")
    if not isinstance(work_loop, dict) or work_loop.get("status") == "none":
        print("- state: none")
    elif work_loop.get("status") in {"invalid", "unavailable"}:
        print(f"- state: {work_loop.get('status')}")
        print(f"- detail: {work_loop.get('error') or 'unavailable'}")
    else:
        print(
            f"- run: {work_loop.get('runId')} [{work_loop.get('status')}] "
            f"mode {work_loop.get('mode')}; selector {work_loop.get('selector')}"
        )
        print(
            f"- progress: iteration {work_loop.get('iteration')}; "
            f"phase {work_loop.get('phase')}; task {work_loop.get('task') or 'none'}; "
            f"PR {work_loop.get('prNumber') or 'none'}"
        )
        focus_values = work_loop.get("focus")
        focus_text = ", ".join(focus_values) if isinstance(focus_values, list) else ""
        print(
            f"- focus: {work_loop.get('focusMode') or 'none'}"
            f"{f' ({focus_text})' if focus_text else ''}"
        )
        health = work_loop.get("contextHealth")
        health_level = health.get("level") if isinstance(health, dict) else "unknown"
        checkpoint = work_loop.get("checkpoint")
        checkpoint_state = (
            checkpoint.get("state") if isinstance(checkpoint, dict) else "unknown"
        )
        print(
            f"- heartbeat: {work_loop.get('heartbeatAt') or 'unknown'}; "
            f"context health {health_level}; checkpoint {checkpoint_state}"
        )
        terminal = work_loop.get("terminalReconciliation")
        if isinstance(terminal, dict) and terminal.get("status") == "verified":
            print(
                "- terminal reconciliation: verified historical external completion; "
                f"reconciled {terminal.get('reconciledAt') or 'unknown'}"
            )
            delivery = terminal.get("delivery")
            bookkeeping = terminal.get("bookkeeping")
            external = (
                f"delivery PR #{delivery.get('prNumber')}"
                if isinstance(delivery, dict)
                else "delivery PR unknown"
            )
            if isinstance(bookkeeping, dict):
                external += f"; bookkeeping PR #{bookkeeping.get('prNumber')}"
            print(f"- external completion: {external}")
        print(f"- counters (loop-owned): {work_loop.get('counters') or {}}")
        if work_loop.get("stopReason"):
            print(f"- stop reason: {work_loop.get('stopReason')}")

    recovery = report.get("recoveryArtifacts")
    print("\n==> Recovery Artifacts")
    if not isinstance(recovery, dict) or recovery.get("status") not in {"ok", "invalid"}:
        detail = recovery.get("error") if isinstance(recovery, dict) else None
        print(f"- state: unavailable{f' ({detail})' if detail else ''}")
    elif recovery.get("status") == "invalid":
        print("- state: invalid")
        print(f"- detail: {recovery.get('error') or 'unavailable'}")
    else:
        counts_raw = recovery.get("counts")
        counts = counts_raw if isinstance(counts_raw, dict) else {}
        summary = ", ".join(
            f"{name} {count}"
            for name, count in sorted(counts.items())
            if isinstance(count, int) and count > 0
        )
        if not summary:
            print("- state: no tracked recovery artifacts")
        else:
            print(f"- tracked: {summary}")
            actionable = recovery.get("actionable")
            if isinstance(actionable, list) and actionable:
                for item in actionable[:HUMAN_ITEM_LIMIT]:
                    if not isinstance(item, dict):
                        continue
                    print(
                        f"  · {item.get('type')} {item.get('reference')} "
                        f"[{item.get('classification')}]: {item.get('detail')}"
                    )
                extra = len(actionable) - HUMAN_ITEM_LIMIT
                if extra > 0:
                    print(f"  · +{extra} more")

    github = report["github"]
    trellis = report["trellis"]
    print("\n==> Inventory")
    print(f"- GitHub: {github.get('status')}")
    if github.get("openPrsStatus") == "available":
        print(
            f"- open PRs ({len(github.get('openPrs', []))}): "
            f"{format_items(github.get('openPrs'))}"
        )
    else:
        print("- open PRs: unavailable")
    if github.get("openIssuesStatus") == "available":
        print(
            f"- open issues ({len(github.get('openIssues', []))}): "
            f"{format_items(github.get('openIssues'))}"
        )
    else:
        print("- open issues: unavailable")
    # The runtime calls a pointer stale when its directory is gone, so the
    # common stale case resolves to no task record at all. Suffixing "none
    # active" with "[stale pointer]" would read as a contradiction, and
    # dropping the suffix would hide the drift entirely -- so name the
    # pointer instead, which is the only thing left to act on.
    active_task = trellis.get("activeTask")
    if isinstance(active_task, dict):
        stale_suffix = " [stale pointer]" if trellis.get("activeTaskStale") else ""
        print(f"- current Trellis task: {format_task(active_task)}{stale_suffix}")
    elif trellis.get("activeTaskStale"):
        pointer = trellis.get("activeTaskPointer") or "unknown"
        print(f"- current Trellis task: none active [stale pointer to {pointer}]")
    else:
        print("- current Trellis task: none active")
    print(f"- in-progress Trellis tasks: {len(trellis.get('inProgress', []))}")
    planned = trellis.get("planned", [])
    print(f"- planned Trellis tasks: {len(planned)}")
    completed_outside_archive = trellis.get("completedOutsideArchive", [])
    print(
        "- completed Trellis tasks outside archive "
        f"({len(completed_outside_archive)}): "
        f"{format_task(completed_outside_archive[0]) if completed_outside_archive else 'none'}"
    )

    print("\n==> Anomalies")
    details = anomaly_details(report)
    if details:
        # One heading still holds everything a reader must see; the marking is
        # what distinguishes "this run failed" from "you may want to look".
        for detail in details:
            marker = (
                "[advisory] " if detail.get("severity") == SEVERITY_ADVISORY else ""
            )
            print(f"- {marker}{detail.get('message')}")
    else:
        print("none")

    render_selectable_inventory(
        "Follow-ups",
        report.get("followUps"),
        task_items=False,
    )
    render_selectable_inventory(
        "Tasks",
        trellis.get("tasks"),
        task_items=True,
    )
    print("\n==> Next Steps")
    for index, step in enumerate(report["nextSteps"], start=1):
        print(f"{index}. {step}")


def fleet_api() -> Any:
    scripts_dir = Path(__file__).resolve().parent
    scripts_path = str(scripts_dir)
    inserted = scripts_path not in sys.path
    if inserted:
        sys.path.insert(0, scripts_path)
    try:
        with suppress_bytecode_writes():
            import sd_ai_command_pack_fleet_lib as fleet
    except ImportError as error:
        raise RuntimeError(
            "installed fleet helper is missing; refresh sd-ai-command-pack"
        ) from error
    finally:
        if inserted:
            sys.path.remove(scripts_path)
    return fleet


def runtime_pack_root(cwd: Path | None = None) -> Path:
    """Where the fleet's last-resort pack source checkout is looked for.

    `scripts/../` was the only rung for as long as every install vendored the
    pack, and it is still the right answer inside a source checkout. A machine
    install puts this script at `~/.agents/bin/`, where the same arithmetic
    yields `~/.agents` -- not a pack checkout, so
    `resolve_fleet_configuration`'s last rung refuses and `sd-status fleet`
    reports missing configuration even when it is run from inside the very
    checkout that holds the manifest.

    So the script's own location is still asked first, and the working
    directory is the added rung rather than the new preference: everywhere the
    old arithmetic already answered correctly it keeps answering the same, and
    the search only widens where it used to fail. When the script does live in
    a source checkout, that checkout is the one it belongs to, which is a
    better answer than wherever the caller happened to be standing. The last
    resort is `own` rather than `None` so an unconfigured machine still gets
    `resolve_fleet_configuration`'s refusal instead of a `TypeError` here.
    """

    fleet = fleet_api()
    own = Path(__file__).resolve().parents[1]
    for candidate in (own, Path.cwd() if cwd is None else cwd):
        found = fleet.find_pack_source(candidate)
        if found is not None:
            return found
    return own


def load_fleet(
    pack_root: Path,
    path: Path | None,
    *,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
) -> tuple[list[Any], Any]:
    fleet = fleet_api()
    resolution = fleet.resolve_fleet_configuration(
        pack_root,
        fleet_manifest=path,
        environ=environ,
        cwd=cwd,
        home=home,
    )
    try:
        consumers = fleet.load_fleet_consumers(resolution.manifest_path)
    except ValueError as error:
        raise ValueError(
            f"{resolution.source} fleet configuration is unusable: {error}"
        ) from None
    consumer_names = {consumer.name.casefold() for consumer in consumers}
    unknown_overrides = sorted(set(resolution.path_overrides) - consumer_names)
    if unknown_overrides:
        raise ValueError(
            "machine profile has checkout overrides for unknown fleet members: "
            + ", ".join(unknown_overrides)
        )
    return consumers, resolution


def read_consumer_pin(root: Path, pin_path: str) -> dict[str, Any]:
    """Classify a thin consumer's pin as present, absent, or unreadable.

    ``read_json_object`` collapses a missing file, an I/O error, and invalid
    JSON into one ``None``, and ``collect_versions`` additionally falls back to
    the installed manifest, so neither can express this three-way state. Load
    time already rejects absolute and ``..``-bearing pin paths, but a purely
    relative path can still leave the checkout through a symlink, so the read
    repeats the containment pattern used by ``filesystem_payload_digest``:
    ``resolve(strict=True)`` then ``relative_to`` the consumer root. An escape
    is reported, never followed.
    """

    source = safe_text(pin_path, limit=300)

    def result(
        state: str,
        *,
        version: str | None = None,
        detail: str | None = None,
    ) -> dict[str, Any]:
        return {
            "state": state,
            "version": version,
            "source": source,
            "detail": safe_text(detail, limit=200) if detail else None,
        }

    try:
        resolved = (root / pin_path).resolve(strict=True)
        resolved.relative_to(root.resolve())
    except FileNotFoundError:
        return result("absent", detail="pin file does not exist")
    except (OSError, RuntimeError, ValueError) as error:
        return result(
            "unreadable",
            detail=f"pin path is not readable inside the checkout: {error}",
        )
    payload = read_json_object(resolved)
    if payload is None:
        return result("unreadable", detail="pin file is not a readable JSON object")
    version = payload.get("version")
    if not isinstance(version, str) or not version.strip():
        return result("unreadable", detail="pin file carries no version string")
    return result("present", version=safe_text(version, limit=80))


def machine_install_version(machine_scope: Mapping[str, Any] | None) -> str | None:
    """The machine install's pack version, or ``None`` when unavailable."""
    if not isinstance(machine_scope, Mapping):
        return None
    if machine_scope.get("state") != "installed":
        return None
    version = machine_scope.get("packVersion")
    return version if isinstance(version, str) and version else None


PROVIDER_CONFIG_HISTORY_SOURCE = Path(
    "templates/docs/sd-ai-command-pack-provider-config-history.json"
)


def provider_config_states(pack_root: Path, consumer_root: Path) -> list[dict[str, Any]]:
    """Classify a consumer's `if-not-exists` configs against shipped digests.

    Read entirely from the pack checkout: the record is the pack's, and the
    consumer files are read directly. That is what lets this answer "who is
    behind on a provider config" *before* anything is installed anywhere --
    the consumer's own audit cannot, because the record only reaches it by
    install, and by then the install has already refreshed the file.

    Read-only, and every unreadable input degrades to `unknown` rather than a
    clean row.
    """
    try:
        payload = json.loads(
            (pack_root / PROVIDER_CONFIG_HISTORY_SOURCE).read_text(encoding="utf-8")
        )
        sources = payload["sources"]
        if payload.get("schemaVersion") != 1 or not isinstance(sources, dict):
            raise ValueError("unsupported provider config history")
    except (OSError, ValueError, KeyError, TypeError):
        # The record is what enumerates the targets, so an unreadable one
        # leaves nothing to classify. Returning `[]` would render as a row
        # with no provider configs -- indistinguishable from a clean one --
        # so name the artifact that could not be read instead.
        return [
            {"target": PROVIDER_CONFIG_HISTORY_SOURCE.as_posix(), "state": "unknown"}
        ]

    states: list[dict[str, Any]] = []
    for source, entry in sources.items():
        # A malformed entry is reported, never skipped: dropping it would
        # shrink the list toward the same clean-looking row an unreadable
        # record used to produce.
        label = source if isinstance(source, str) else repr(source)
        if not isinstance(entry, Mapping):
            states.append({"target": label, "state": "unknown"})
            continue
        target = entry.get("target")
        current = entry.get("current")
        digests = entry.get("digests")
        if not isinstance(target, str) or not isinstance(current, str):
            states.append({"target": label, "state": "unknown"})
            continue
        if not isinstance(digests, list):
            digests = []
        path = consumer_root / target
        try:
            if path.is_symlink():
                # A symlink is a deliberate local choice and the installer
                # preserves it, so it belongs with the locally owned files.
                # Calling it `absent` would say the opposite of what it is.
                state = "local"
            elif not path.is_file():
                state = "absent"
            else:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest == current:
                    state = "current"
                elif digest in digests:
                    state = "superseded"
                else:
                    state = "local"
        except OSError:
            state = "unknown"
        states.append({"target": target, "state": state})
    states.sort(key=lambda item: item["target"])
    return states


def fleet_step_records(
    reports: Sequence[Mapping[str, Any]],
    target: str,
    *,
    machine_scope: Mapping[str, Any] | None = None,
    release_target: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Every fleet step, untruncated, ranked so skew outranks advisory rows.

    Fleet-level machine rows are gated on the registry containing at least one
    thin consumer: nothing consumes the machine install while every consumer is
    fat, so an all-fat fleet reports exactly as it did before schema 5.
    """
    missing = [item["name"] for item in reports if item.get("status") == "missing"]
    available = [item for item in reports if item.get("status") == "available"]
    thin = [item for item in available if item.get("installMode") == "thin"]
    fat = [item for item in available if item.get("installMode") != "thin"]
    dirty = [
        item["name"]
        for item in available
        if item["report"]["git"]["workingTree"]["state"] == "dirty"
    ]
    stale = [
        item["name"]
        for item in fat
        if item["report"]["versions"]["sdAiCommandPack"] != target
    ]
    divergent = [
        item["name"]
        for item in available
        if item["report"]["git"]["syncState"] in {"behind", "diverged"}
    ]
    has_thin = any(item.get("installMode") == "thin" for item in reports)
    machine_version = machine_install_version(machine_scope)

    records: list[dict[str, Any]] = []

    def add(summary: str, rank: int) -> None:
        records.append({"summary": summary, "rank": rank})

    # The operator's own checkout versus the newest published release. This is a
    # fleet-level fact, emitted once: it is a property of the operator, not of
    # any consumer, and the fix is pulling the pack source rather than
    # refreshing anyone. It ranks with skew rather than advisory because it
    # invalidates every consumer comparison in the same report -- each of those
    # was scored against a target that is not what is published.
    #
    # "differs from", never "is behind": an unreleased working copy is ahead,
    # and that is one of the two failure modes this exists to surface.
    if release_target is not None and release_target.get("status") == "available":
        release_version = release_target.get("version")
        if isinstance(release_version, str) and release_version != target:
            add(
                f"Pack checkout is at {target} but the newest published release "
                f"is {release_version}; pull the pack source before refreshing "
                "the fleet.",
                FLEET_STEP_RANK_SKEW,
            )

    broken_pins = [
        item["name"]
        for item in thin
        if (item.get("pin") or {}).get("state") != "present"
    ]
    if broken_pins:
        add(
            "Repair missing or unreadable thin consumer pins: "
            + ", ".join(broken_pins)
            + ".",
            FLEET_STEP_RANK_SKEW,
        )
    if machine_version is None:
        if thin:
            add(
                "Machine SD install inventory is unavailable; thin consumer pins "
                "cannot be compared.",
                FLEET_STEP_RANK_SKEW,
            )
    else:
        skewed_pins = [
            item["name"]
            for item in thin
            if (item.get("pin") or {}).get("state") == "present"
            and (item.get("pin") or {}).get("version") != machine_version
        ]
        if skewed_pins:
            add(
                f"Reconcile thin consumer pins against the machine install "
                f"({machine_version}): " + ", ".join(skewed_pins) + ".",
                FLEET_STEP_RANK_SKEW,
            )
    if has_thin:
        if machine_version is None:
            add(
                "Install or repair the machine SD install; thin consumers depend "
                "on it.",
                FLEET_STEP_RANK_SKEW,
            )
        elif machine_version != target:
            add(
                f"Update the machine SD install ({machine_version}) to the target "
                f"pack version ({target}).",
                FLEET_STEP_RANK_SKEW,
            )
        if isinstance(machine_scope, Mapping) and machine_scope.get("comparison") == "skew":
            add(
                "Reconcile the SD plugin "
                f"({machine_scope.get('pluginVersion') or 'unavailable'}) and the "
                f"machine receipt ({machine_scope.get('packVersion') or 'unavailable'}).",
                FLEET_STEP_RANK_SKEW,
            )

    if missing:
        add(
            "Restore or correct missing fleet checkouts: " + ", ".join(missing) + ".",
            FLEET_STEP_RANK_ADVISORY,
        )
    if dirty:
        add(
            "Resolve uncommitted fleet work before rollout: " + ", ".join(dirty) + ".",
            FLEET_STEP_RANK_ADVISORY,
        )
    if divergent:
        add(
            "Reconcile behind or diverged fleet checkouts: " + ", ".join(divergent) + ".",
            FLEET_STEP_RANK_ADVISORY,
        )
    if stale:
        add(
            "Refresh stale SD pack installations: " + ", ".join(stale) + ".",
            FLEET_STEP_RANK_ADVISORY,
        )
    superseded_configs = [
        item["name"]
        for item in reports
        if any(
            state.get("state") == "superseded"
            for state in item.get("providerConfigs") or ()
        )
    ]
    if superseded_configs:
        add(
            "Update superseded provider configs by running install.py against: "
            + ", ".join(superseded_configs)
            + ".",
            FLEET_STEP_RANK_ADVISORY,
        )
    local_configs = [
        item["name"]
        for item in reports
        if any(
            state.get("state") == "local"
            for state in item.get("providerConfigs") or ()
        )
    ]
    if local_configs:
        # Not skew: a locally owned config is a decision the installer will
        # keep honoring. It is listed so a shipped correction that will never
        # reach it is visible to a human who can merge it.
        add(
            "Merge shipped provider config changes by hand where the consumer "
            "owns the file: " + ", ".join(local_configs) + ".",
            FLEET_STEP_RANK_ADVISORY,
        )
    unknown_configs = [
        item["name"]
        for item in reports
        if any(
            state.get("state") == "unknown"
            for state in item.get("providerConfigs") or ()
        )
    ]
    if unknown_configs:
        # An unreadable record or file is this report's own gap, and saying so
        # is the point: a consumer whose currency could not be determined must
        # not read as one that was checked and found clean.
        add(
            "Provider config currency could not be determined for: "
            + ", ".join(unknown_configs)
            + ".",
            FLEET_STEP_RANK_ADVISORY,
        )
    if not records:
        add(FLEET_READY_STEP, FLEET_STEP_RANK_ADVISORY)
    records.sort(key=lambda record: record["rank"])
    return records


def fleet_next_steps(records: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(record["summary"]) for record in records][:HUMAN_ITEM_LIMIT]


def fleet_follow_ups(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Derive ``F-*`` rows from the complete record set.

    Deriving them from the truncated human list would let a skew row vanish
    once enough advisory rows exist, which PRD requirement 3 forbids.
    """
    actionable = [
        str(record["summary"])
        for record in records
        if record["summary"] != FLEET_READY_STEP
    ]
    return select_items(
        [
            {"kind": "action", "summary": step, "source": "fleet"}
            for step in actionable
        ],
        prefix="F",
    )


def collect_fleet(
    pack_root: Path,
    *,
    fleet_path: Path | None,
    network: bool,
    refs_refreshed: bool,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    consumers, resolution = load_fleet(
        pack_root,
        fleet_path,
        environ=environ,
        cwd=cwd,
        home=home,
    )
    target = resolution.target_version
    # Once per fleet run, deliberately outside the consumer pool below: the pack
    # has one release regardless of how many consumers the manifest lists, and a
    # per-consumer lookup would multiply one remote round trip by the fleet size.
    release_target = collect_release_target(resolution.pack_source, network=network)

    def collect_consumer(consumer: Any) -> dict[str, Any]:
        path = resolution.path_overrides.get(
            consumer.name.casefold(),
            Path(consumer.path_hint).expanduser(),
        )
        install_mode = getattr(consumer, "mode", "fat")
        pin_path = getattr(consumer, "pin_path", DEFAULT_CONSUMER_PIN_PATH)
        if not path.is_dir():
            return {
                "name": consumer.name,
                "github": consumer.github,
                "priority": consumer.rollout_priority,
                "path": str(path),
                "status": "missing",
                "installMode": install_mode,
                "pin": None,
                "providerConfigs": [],
                "report": None,
            }
        try:
            report = collect_local(
                path,
                remote="origin",
                supplied_default=None,
                source_branch=None,
                github_repo=consumer.github,
                network=network,
                refs_refreshed=refs_refreshed,
                expect_clean=False,
                keep_remote_branch=False,
                dry_run=False,
                prior_anomalies=(),
                target_pack_version=target,
                include_machine_scope=False,
            )
        except Exception:
            # One unreachable or misbehaving consumer must not abort the whole
            # fleet run. Render it as a degraded row exactly as an empty
            # collect_local result does (status "unavailable", no report) so the
            # remaining consumers still report. KeyboardInterrupt is a
            # BaseException and is deliberately left to propagate.
            report = None
        return {
            "name": consumer.name,
            "github": consumer.github,
            "priority": consumer.rollout_priority,
            "path": str(path),
            "status": "available" if report else "unavailable",
            "installMode": install_mode,
            "pin": (
                read_consumer_pin(path, pin_path)
                if report and install_mode == "thin"
                else None
            ),
            "providerConfigs": provider_config_states(pack_root, path),
            "report": report,
        }

    # Fleet status is subprocess-bound (git/gh per consumer) and consumers are
    # independent, so collect them concurrently in a bounded pool instead of
    # stacking each consumer's subprocess and network-timeout latency serially.
    # The useful worker ceiling tracks git/gh concurrency rather than CPU cores;
    # cap at 8 so a large fleet does not open one subprocess tree per consumer
    # at once. ThreadPoolExecutor.map yields in input order, so registry
    # rollout order is preserved without re-sorting.
    reports: list[dict[str, Any]]
    if consumers:
        worker_count = min(8, len(consumers))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            reports = list(executor.map(collect_consumer, consumers))
    else:
        reports = []
    # One machine probe per fleet run, never one per consumer: each consumer
    # row keeps include_machine_scope=False, so no extra `claude plugin list`
    # subprocess is spawned per member.
    machine_scope = collect_machine_scope(
        pack_root,
        home=home,
        environ=environ,
    )
    records = fleet_step_records(
        reports,
        target,
        machine_scope=machine_scope,
        release_target=release_target,
    )
    steps = fleet_next_steps(records)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "mode": "fleet",
        "targetPackVersion": target,
        "releaseTarget": release_target,
        "machineScope": machine_scope,
        "refsFreshness": "refreshed" if refs_refreshed else "cached",
        "configuration": {
            "source": resolution.source,
            "manifest": str(resolution.manifest_path),
            "profile": (
                str(resolution.profile_path) if resolution.profile_path else None
            ),
        },
        "repositories": reports,
        "followUps": fleet_follow_ups(records),
        "nextSteps": steps,
    }


def render_fleet(report: Mapping[str, Any]) -> None:
    repositories = report["repositories"]
    available = sum(item.get("status") == "available" for item in repositories)
    missing = sum(item.get("status") == "missing" for item in repositories)
    unavailable = len(repositories) - available - missing
    machine_version = machine_install_version(report.get("machineScope"))
    attention = 0
    for item in repositories:
        local = item.get("report")
        if not isinstance(local, dict):
            attention += 1
            continue
        if (
            local["git"]["workingTree"]["state"] != "clean"
            or local["git"]["syncState"] in {"behind", "diverged"}
        ):
            attention += 1
            continue
        # Version attention follows the mode split, so the human counter and the
        # JSON skew rows cannot disagree: a thin consumer has no meaningful
        # installed tree to compare against the target.
        if item.get("installMode") == "thin":
            pin = item.get("pin") or {}
            if pin.get("state") != "present" or pin.get("version") != machine_version:
                attention += 1
        elif local["versions"]["sdAiCommandPack"] != report["targetPackVersion"]:
            attention += 1
    print(
        f"SD fleet status: {len(repositories)} repositories, "
        f"{available} available, {attention} need attention, {missing} missing, "
        f"{unavailable} unavailable"
    )
    print(f"Target pack: {report['targetPackVersion']}")
    # Reported, never counted in `attention` above: an unreachable remote or a
    # deliberate --no-network run must not make a healthy fleet read as broken.
    release_target = report.get("releaseTarget") or {}
    if release_target.get("status") == "available":
        print(
            f"Release target: {release_target['version']} "
            f"({release_target['tag']})"
        )
    else:
        print(f"Release target: {release_target.get('status', 'unavailable')}")
    configuration = report.get("configuration", {})
    print(f"Fleet config: {configuration.get('source', 'unknown')}")
    if any(item.get("installMode") == "thin" for item in repositories):
        print(f"Machine scope: {format_machine_scope(report.get('machineScope'))}")
    print(f"Ref freshness: {report['refsFreshness']}")
    print("\n==> Fleet")
    for item in repositories:
        prefix = f"P{item['priority']:02d} {item['name']}"
        local = item.get("report")
        if not isinstance(local, dict):
            print(f"- {prefix}: {item['status']} ({item['path']})")
            continue
        git = local["git"]
        versions = local["versions"]
        github = local["github"]
        trellis = local["trellis"]
        stash_count = git.get("stashCount")
        stash_label = stash_count if isinstance(stash_count, int) else "unavailable"
        pr_count = (
            str(len(github.get("openPrs", [])))
            if github.get("openPrsStatus") == "available"
            else "unavailable"
        )
        if item.get("installMode") == "thin":
            pin = item.get("pin") or {}
            pin_state = pin.get("state") or "unreadable"
            pack_label = (
                f"pin {pin.get('version')}"
                if pin_state == "present"
                else f"pin {pin_state}"
            )
        else:
            pack_label = f"pack {versions.get('sdAiCommandPack') or 'none'}"
        # Trellis drifts independently of the pack pin, and the JSON has always
        # carried it while this row did not -- an operator reading only the
        # human report concluded the fleet was consistent on a version it had
        # never been shown.
        trellis_label = f"trellis {versions.get('trellis') or 'unknown'}"
        print(
            f"- {prefix}: {git['workingTree']['state']}; "
            f"{git.get('branch') or 'detached'}; "
            f"{report['refsFreshness']}:{git['syncState']}; "
            f"{pack_label}; "
            f"{trellis_label}; "
            f"stashes {stash_label}; "
            f"PRs {pr_count}; "
            f"tasks {len(trellis.get('inProgress', []))}/{len(trellis.get('planned', []))}"
        )
    render_selectable_inventory(
        "Follow-ups",
        report.get("followUps"),
        task_items=False,
    )
    print("\n==> Next Steps")
    for index, step in enumerate(report["nextSteps"], start=1):
        print(f"{index}. {step}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report read-only SD repository or fleet status."
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="Reserved word 'fleet' or a local repository path.",
    )
    parser.add_argument("--repo", type=Path)
    parser.add_argument(
        "--fleet-manifest",
        type=Path,
        help=(
            "Use this canonical fleet manifest instead of environment, "
            "machine-profile, or source-checkout discovery."
        ),
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-network", action="store_true")
    parser.add_argument("--expect-clean", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--refs-refreshed", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--remote", default="origin", help=argparse.SUPPRESS)
    parser.add_argument("--default-branch", help=argparse.SUPPRESS)
    parser.add_argument("--source-branch", help=argparse.SUPPRESS)
    parser.add_argument("--github-repo", help=argparse.SUPPRESS)
    parser.add_argument("--keep-remote-branch", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--prior-anomaly",
        action="append",
        nargs=2,
        metavar=("CODE", "MESSAGE"),
        default=[],
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    if args.target == "fleet":
        if args.repo is not None:
            parser.error("fleet cannot be combined with --repo")
        args.mode = "fleet"
        args.repo = Path.cwd()
    elif args.target is not None:
        if args.repo is not None:
            parser.error("a positional repository path cannot be combined with --repo")
        args.mode = None
        args.repo = Path(args.target)
    else:
        args.mode = None
        args.repo = args.repo if args.repo is not None else Path.cwd()
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.mode == "fleet":
        pack_root = runtime_pack_root()
        try:
            report = collect_fleet(
                pack_root,
                fleet_path=args.fleet_manifest,
                network=not args.no_network,
                refs_refreshed=args.refs_refreshed,
            )
        except (RuntimeError, ValueError) as error:
            print(f"error: {safe_text(error, limit=500)}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=False))
        else:
            render_fleet(report)
        return 0

    local_report = collect_local(
        args.repo,
        remote=args.remote,
        supplied_default=args.default_branch,
        source_branch=args.source_branch,
        github_repo=args.github_repo,
        network=not args.no_network,
        refs_refreshed=args.refs_refreshed,
        expect_clean=args.expect_clean,
        keep_remote_branch=args.keep_remote_branch,
        dry_run=args.dry_run,
        prior_anomalies=args.prior_anomaly,
    )
    if local_report is None:
        print(f"error: unable to inspect Git repository: {args.repo}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(local_report, indent=2, sort_keys=False))
    else:
        render_local(local_report, dry_run=args.dry_run)
    # Advisory anomalies are reported but do not fail the run: a successful
    # merge whose only leftover is a branch another worktree holds is not a
    # failed housekeeping run, and a nonzero exit there is what made the signal
    # unreadable. Every other strict anomaly still exits 1.
    return 1 if args.expect_clean and blocking_anomalies(local_report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
