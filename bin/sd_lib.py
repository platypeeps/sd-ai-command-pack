"""Shared detection and derivation for the sd-* tools under bin/.

Every question this module answers, it answers from the repository itself: the
git worktree you are standing in, the tracked artifacts under `docs/work`, the
repo's own check entrypoints. Nothing is read from stored state, because stored
state is state that goes stale without telling anyone.

Stdlib only, Python 3.10+, no network. A caller that cannot proceed gets a
`ConfigError` carrying a sentence a human can act on, never a traceback.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shlex
import subprocess
from dataclasses import dataclass, field

LOCAL_FILE_NAME = "CLAUDE.local.md"
LOCAL_BLOCK_START = "<!-- SD-AI-COMMAND-PACK:LOCAL:START -->"
LOCAL_BLOCK_END = "<!-- SD-AI-COMMAND-PACK:LOCAL:END -->"

CONFIG_RELATIVE_PATH = pathlib.Path("sd-ai-command-pack") / "config.json"

WORK_DIR = "docs/work"
ARCHIVE_DIR = "archive"

ITEM_STATUSES = ("planning", "ready", "in_progress", "done")
MODES = ("full", "minimal", "guest")
DEFAULT_MODE = "full"

#: The three names every repository is asked about, in the order they run.
CHECK_NAMES = ("check", "test", "lint")

GIT_TIMEOUT_SECONDS = 15

_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
_MAKE_TARGET_RE = re.compile(r"^(?P<names>[^\t#=:]+):(?!=)")
_TASKFILE_TASKS_RE = re.compile(r"^tasks:\s*$")
_TASKFILE_ENTRY_RE = re.compile(r"^(?P<indent>\s+)(?P<name>[A-Za-z0-9_][A-Za-z0-9_:.\-]*):")


class ConfigError(RuntimeError):
    """A configuration or environment fault a caller reports instead of raising."""


# --------------------------------------------------------------------------
# Flat scalar parsing, shared by prd frontmatter and the local block
# --------------------------------------------------------------------------


def parse_scalars(text: str, *, comments: bool, label: str = "block") -> dict[str, str]:
    """Read flat `key: value` scalars: no nesting, no lists, no anchors.

    Deliberately not a YAML parser. The frontmatter and the local block this
    reads are each a handful of flat scalars, and depending on PyYAML would
    turn a stdlib-only tool into a tool with an install step.

    With ``comments`` a line whose first non-space character is ``#`` is a
    comment, and an unquoted value ends at the first ``#``. A quoted value is
    taken to the end of the line, so a ``#`` inside quotes stays literal.
    """
    fields: dict[str, str] = {}
    for number, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if comments and stripped.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            if comments:
                raise ConfigError(f"{label} line {number}: {stripped!r} is not `key: value`")
            continue
        value = value.strip()
        if comments and value[:1] not in ('"', "'"):
            value = value.split("#", 1)[0].strip()
        fields[key.strip()] = _unquote(value)
    return fields


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\") if value[0] == '"' else inner
    return value


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Read a leading `---` block of flat `key: value` scalars, or None."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return parse_scalars(text[4:end], comments=False)


# --------------------------------------------------------------------------
# Git: which repository am I in, and where does its configuration live
# --------------------------------------------------------------------------


def _git(args: list[str], cwd: pathlib.Path) -> str | None:
    """Run a read-only git query; None when git cannot answer."""
    try:
        completed = subprocess.run(  # fixed argv, no shell
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def repo_root(start: pathlib.Path | str | None = None) -> pathlib.Path | None:
    """The enclosing worktree's own root, or None outside a repository.

    Inside a linked worktree this is that worktree's root, not the main
    checkout's: `--show-toplevel` is per-worktree, which is exactly what a
    command resolving its repo from cwd wants.
    """
    base = pathlib.Path(start) if start is not None else pathlib.Path.cwd()
    base = base if base.is_dir() else base.parent
    if not base.is_dir():
        return None
    answer = _git(["rev-parse", "--show-toplevel"], cwd=base)
    return pathlib.Path(answer).resolve() if answer else None


def main_worktree_root(root: pathlib.Path) -> pathlib.Path:
    """The main checkout's root, so linked worktrees share one local config.

    `--git-common-dir` points at the shared `.git` directory; its parent is the
    main worktree. A layout where that does not hold (a bare or separated git
    directory) falls back to the worktree it was asked about.
    """
    answer = _git(["rev-parse", "--git-common-dir"], cwd=root)
    if not answer:
        return root
    common = pathlib.Path(answer)
    if not common.is_absolute():
        common = root / common
    common = common.resolve()
    return common.parent if common.name == ".git" else root


# --------------------------------------------------------------------------
# Configuration: the per-repo local block and the per-machine config file
# --------------------------------------------------------------------------


def local_block_path(root: pathlib.Path) -> pathlib.Path:
    """Where `CLAUDE.local.md` lives for this worktree: in the main checkout."""
    return main_worktree_root(root) / LOCAL_FILE_NAME


def parse_local_block(text: str, label: str = LOCAL_FILE_NAME) -> dict[str, str]:
    """Extract the marked block's flat scalars. No block is an empty dict."""
    start = text.find(LOCAL_BLOCK_START)
    if start == -1:
        if LOCAL_BLOCK_END in text:
            raise ConfigError(f"{label}: end marker without a start marker")
        return {}
    if text.find(LOCAL_BLOCK_START, start + len(LOCAL_BLOCK_START)) != -1:
        raise ConfigError(f"{label}: duplicate start markers")
    end = text.find(LOCAL_BLOCK_END, start)
    if end == -1:
        raise ConfigError(f"{label}: start marker with no end marker")
    if text.find(LOCAL_BLOCK_END, end + len(LOCAL_BLOCK_END)) != -1:
        raise ConfigError(f"{label}: duplicate end markers")
    body = text[start + len(LOCAL_BLOCK_START) : end]
    return parse_scalars(body, comments=True, label=label)


def local_block(root: pathlib.Path) -> dict[str, str]:
    """The repo's local configuration block; missing file or block is `{}`."""
    path = local_block_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (IsADirectoryError, NotADirectoryError):
        return {}
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from None
    return parse_local_block(text, str(path))


def machine_config_path() -> pathlib.Path:
    """`~/.config/sd-ai-command-pack/config.json`, honouring `XDG_CONFIG_HOME`."""
    base = os.environ.get("XDG_CONFIG_HOME") or ""
    home = pathlib.Path(base) if base else pathlib.Path.home() / ".config"
    return home / CONFIG_RELATIVE_PATH


def machine_config(path: pathlib.Path | None = None) -> dict[str, object]:
    """The per-machine config. Missing is `{}`; malformed is a `ConfigError`."""
    target = path if path is not None else machine_config_path()
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (IsADirectoryError, NotADirectoryError):
        return {}
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigError(f"cannot read {target}: {error}") from None
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(f"{target} is not valid JSON: {error}") from None
    if not isinstance(loaded, dict):
        raise ConfigError(f"{target} holds a {type(loaded).__name__}, not a JSON object")
    return loaded


def mode(root: pathlib.Path) -> str:
    """`full` (default), `minimal` or `guest`, from the local block's `mode:`."""
    value = local_block(root).get("mode", "").strip()
    if not value:
        return DEFAULT_MODE
    if value not in MODES:
        raise ConfigError(f"mode {value!r} is not one of {', '.join(MODES)}")
    return value


# --------------------------------------------------------------------------
# Work items: status derived from artifacts and git, never from stored state
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StatusReport:
    """A derived status plus every inconsistency found while deriving it."""

    status: str
    archived: bool
    inconsistencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkItem:
    """One work item directory, as the filesystem describes it."""

    path: pathlib.Path
    slug: str
    title: str
    status: str
    created: str
    branch: str
    archived: bool
    #: The frontmatter's `parked:` line verbatim, empty when the item is live.
    #: The age sweep writes `parked: <date> age-sweep` here and nowhere else --
    #: parked is a property of the item, never a row in a separate ledger.
    parked: str = ""
    inconsistencies: tuple[str, ...] = ()


def _is_archived(item_dir: pathlib.Path) -> bool:
    return ARCHIVE_DIR in item_dir.resolve().parts


def _read_prd(item_dir: pathlib.Path) -> tuple[dict[str, str], list[str]]:
    """The prd's frontmatter fields, and what went wrong reading them."""
    prd = item_dir / "prd.md"
    try:
        parsed = parse_frontmatter(prd.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return {}, [f"{prd} is missing or unreadable"]
    if parsed is None:
        return {}, [f"{prd} has no --- frontmatter block"]
    return parsed, []


def _status_report(
    item_dir: pathlib.Path, fields: dict[str, str], problems: list[str]
) -> StatusReport:
    archived = _is_archived(item_dir)
    prd = item_dir / "prd.md"
    if archived:
        return StatusReport("done", True, tuple(problems))

    declared = fields.get("status", "").strip()
    if declared not in ITEM_STATUSES:
        problems.append(
            f"{prd}: status {declared!r} is not one of {', '.join(ITEM_STATUSES)}"
        )
        return StatusReport("unknown", False, tuple(problems))
    if declared == "in_progress" and not fields.get("branch", "").strip():
        problems.append(f"{prd}: an in_progress item records the branch it lives on")
    return StatusReport(declared, False, tuple(problems))


def status_report(item_dir: pathlib.Path) -> StatusReport:
    """Derive a work item's status from its own artifacts.

    An item under `archive/` is `done` by virtue of where it lives -- the move
    is the record. Anything else states its status in `prd.md` frontmatter. A
    status that is missing, unknown, or contradicted by the rest of the
    frontmatter is reported as an inconsistency rather than raised: a lint rule
    is the place to fail, and this function is also called by tools that only
    want to show you the tree.
    """
    item_dir = pathlib.Path(item_dir)
    fields, problems = _read_prd(item_dir)
    return _status_report(item_dir, fields, problems)


def derive_status(item_dir: pathlib.Path) -> str:
    """The derived status alone; `unknown` when the artifacts do not say."""
    return status_report(item_dir).status


def work_item(item_dir: pathlib.Path) -> WorkItem:
    """Read one work item directory into a `WorkItem`, reading the prd once."""
    item_dir = pathlib.Path(item_dir)
    fields, problems = _read_prd(item_dir)
    report = _status_report(item_dir, fields, problems)
    name = item_dir.name
    return WorkItem(
        path=item_dir,
        slug=_DATE_PREFIX_RE.sub("", name),
        title=fields.get("title", ""),
        status=report.status,
        created=fields.get("created", ""),
        branch=fields.get("branch", ""),
        archived=report.archived,
        parked=fields.get("parked", "").strip(),
        inconsistencies=report.inconsistencies,
    )


def work_item_dirs(root: pathlib.Path, work_dir: str = WORK_DIR) -> list[pathlib.Path]:
    """Every work item directory, active and archived, from the filesystem."""
    work_root = pathlib.Path(root) / work_dir
    if not work_root.is_dir():
        return []
    found = [
        path for path in work_root.iterdir() if path.is_dir() and path.name != ARCHIVE_DIR
    ]
    archive = work_root / ARCHIVE_DIR
    if archive.is_dir():
        for month in archive.iterdir():
            if month.is_dir():
                found.extend(path for path in month.iterdir() if path.is_dir())
    return sorted(found)


def work_items(root: pathlib.Path, work_dir: str = WORK_DIR) -> list[WorkItem]:
    """Every work item, enumerated from the tree rather than from an index."""
    return [work_item(path) for path in work_item_dirs(root, work_dir)]


# --------------------------------------------------------------------------
# Entrypoints: the repo's own check commands, however it happens to spell them
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Detection:
    """What was detected and how, so a caller can explain itself."""

    source: str | None
    origin: pathlib.Path | None
    commands: dict[str, list[str]] = field(default_factory=dict)
    reason: str = ""


def _local_block_entrypoints(root: pathlib.Path) -> Detection | None:
    block = local_block(root)
    commands: dict[str, list[str]] = {}
    for name in CHECK_NAMES:
        raw = block.get(name, "").strip()
        if not raw:
            continue
        try:
            argv = shlex.split(raw)
        except ValueError as error:
            raise ConfigError(
                f"{LOCAL_FILE_NAME}: {name}: {raw!r} does not parse: {error}"
            ) from None
        if not argv:
            raise ConfigError(f"{LOCAL_FILE_NAME}: {name}: is empty")
        commands[name] = argv
    if not commands:
        return None
    return Detection(
        source="local-block",
        origin=local_block_path(root),
        commands=commands,
        reason=f"{LOCAL_FILE_NAME} declares {', '.join(commands)}",
    )


def _makefile_targets(path: pathlib.Path) -> set[str]:
    targets: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return targets
    for line in text.split("\n"):
        if not line or line[:1].isspace():
            continue
        match = _MAKE_TARGET_RE.match(line)
        if not match:
            continue
        for name in match.group("names").split():
            if name.startswith(".") or "%" in name or "$" in name:
                continue
            targets.add(name)
    return targets


def _makefile_entrypoints(root: pathlib.Path) -> Detection | None:
    for candidate in ("Makefile", "makefile", "GNUmakefile"):
        path = root / candidate
        if path.is_file():
            break
    else:
        return None
    targets = _makefile_targets(path)
    commands = {name: ["make", name] for name in CHECK_NAMES if name in targets}
    if not commands:
        return None
    return Detection(
        source="makefile",
        origin=path,
        commands=commands,
        reason=f"{path.name} defines {', '.join(commands)}",
    )


def _taskfile_tasks(path: pathlib.Path) -> list[str]:
    """Top-level task names under `tasks:`, read line-wise.

    A YAML parser is not stdlib, so this reads exactly the shape a Taskfile
    conventionally has: a `tasks:` mapping whose keys sit one indent in.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    names: list[str] = []
    indent: str | None = None
    inside = False
    for line in text.split("\n"):
        if not line.strip():
            continue
        if _TASKFILE_TASKS_RE.match(line):
            inside = True
            continue
        if not inside:
            continue
        if not line[:1].isspace():
            break
        match = _TASKFILE_ENTRY_RE.match(line)
        if not match:
            continue
        if indent is None:
            indent = match.group("indent")
        if match.group("indent") == indent:
            names.append(match.group("name"))
    return names


def _taskfile_entrypoints(root: pathlib.Path) -> Detection | None:
    for candidate in ("Taskfile.yml", "Taskfile.yaml"):
        path = root / candidate
        if path.is_file():
            break
    else:
        return None
    tasks = _taskfile_tasks(path)
    commands = {name: ["task", name] for name in CHECK_NAMES if name in tasks}
    if not commands:
        return None
    return Detection(
        source="taskfile",
        origin=path,
        commands=commands,
        reason=f"{path.name} defines {', '.join(commands)}",
    )


def _package_json_entrypoints(root: pathlib.Path) -> Detection | None:
    path = root / "package.json"
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from None
    scripts = loaded.get("scripts") if isinstance(loaded, dict) else None
    if not isinstance(scripts, dict):
        return None
    commands = {name: ["npm", "run", name] for name in CHECK_NAMES if name in scripts}
    if not commands:
        return None
    return Detection(
        source="package.json",
        origin=path,
        commands=commands,
        reason=f"package.json scripts define {', '.join(commands)}",
    )


def _cargo_entrypoints(root: pathlib.Path) -> Detection | None:
    path = root / "Cargo.toml"
    if not path.is_file():
        return None
    return Detection(
        source="cargo",
        origin=path,
        commands={"check": ["cargo", "check"], "test": ["cargo", "test"]},
        reason="Cargo.toml: cargo check and cargo test",
    )


def _pyproject_entrypoints(root: pathlib.Path) -> Detection | None:
    path = root / "pyproject.toml"
    if not path.is_file():
        return None
    return Detection(
        source="pyproject",
        origin=path,
        commands={"test": ["python3", "-m", "pytest"]},
        reason="pyproject.toml: python3 -m pytest",
    )


#: Autodetection order. The first probe that finds a runnable check wins; a
#: probe that finds its file but no usable target is not a hit, so a Makefile
#: with no check/test/lint target does not stop the search.
DETECTORS = (
    _local_block_entrypoints,
    _makefile_entrypoints,
    _taskfile_entrypoints,
    _package_json_entrypoints,
    _cargo_entrypoints,
    _pyproject_entrypoints,
)


def detect_entrypoints(root: pathlib.Path) -> Detection:
    """Resolve the repo's check commands, reporting which probe answered."""
    root = pathlib.Path(root)
    for detector in DETECTORS:
        found = detector(root)
        if found is not None:
            return found
    return Detection(source=None, origin=None, commands={}, reason="no check entrypoint detected")


def entrypoints(root: pathlib.Path) -> dict[str, list[str]]:
    """The repo-native check commands, keyed by name, in `CHECK_NAMES` order."""
    return detect_entrypoints(root).commands
