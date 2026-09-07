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
from typing import Any, Callable

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

#: Consent, not policy: the registry entries a repository allows to receive
#: its diff. The installer asks for it once and writes the key; nothing
#: derives the value. Named here so the installer's block, `WORKFLOW.md` and
#: the test that compares them all read one source.
CONSENT_KEY = "reviewers"

GIT_TIMEOUT_SECONDS = 15
GH_TIMEOUT_SECONDS = 20

#: `WORKFLOW.md`'s three questions as the endpoints that ask them; `gh` fills
#: `{owner}` and `{repo}` from the checkout's origin, so no URL parser is needed
#: here. The last is *the* collaborator query criterion 11 asks `bin/` to hold
#: once: both gates reach it through `remote_permits_full` and neither restates.
VIEWER_QUERY = "user"
REPOSITORY_QUERY = "repos/{owner}/{repo}"
COLLABORATOR_QUERY = "repos/{owner}/{repo}/collaborators"
#: How one of those questions is put. Injected, so a test never asks the network.
Asker = Callable[[str, pathlib.Path], tuple[Any, str]]

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
    """Run one `git` command; None when git cannot answer."""
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


def sibling(module_name: str, filename: str):
    """Import a `bin/` tool that has no `.py` suffix, so callers can share it.

    Three callers is what moved it here: `bin/sd-status:97` had one copy and
    `bin/sd_skill.py` a second, and a third would have made copying the policy
    the policy. `spec_from_file_location` infers no loader for a suffixless
    file, so the `SourceFileLoader` is named explicitly.

    Deferred by every caller rather than imported at module load: `bin/sd`
    imports its verb modules for every verb it runs, and a sibling is only
    needed by the ones that talk to GitHub.
    """
    import importlib.machinery  # noqa: PLC0415 - only siblings need it
    import importlib.util  # noqa: PLC0415

    path = str(pathlib.Path(__file__).resolve().parent / filename)
    loader = importlib.machinery.SourceFileLoader(module_name, path)
    spec = importlib.util.spec_from_file_location(module_name, path, loader=loader)
    if spec is None:  # pragma: no cover - a bin/ layout this broken cannot run
        raise ConfigError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def git_output(args: list[str], root: pathlib.Path) -> str | None:
    """`git <args>` in `root`: stripped stdout, or None when git cannot answer.

    The public face of the same call the helpers below use, so a sibling
    tool needing one more `git` fact grows no second subprocess policy
    (timeout, no shell, failure-is-None). Most are reads; `delivered` fetches.
    """
    return _git(args, root)


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


@dataclass(frozen=True)
class RemoteAnswer:
    """What the remote said when asked whether this run may be `full`. Not a
    bool: the demotion note, the merge suspension and the dashboard each show
    *which* answer said no, and a bool throws that away at that moment."""

    #: Three yeses, or the no-remote / no-git case. Never reached from an error.
    full: bool
    #: False when the question could not be put at all -- no `gh`, no network, a
    #: refusing remote. It changes the sentence, never the outcome.
    answered: bool
    #: Empty when `full`; otherwise the sentence naming what said no.
    reason: str = ""


def gh_api(endpoint: str, root: pathlib.Path) -> tuple[Any, str]:
    """One read-only `gh api` call: `(payload, error-sentence)`, never raising.
    `gh` is a process and not an import, so stdlib-only holds; it is also the
    seam tests replace, so no test in this repository touches the network."""
    try:
        completed = subprocess.run(  # fixed argv, no shell
            ["gh", "api", endpoint],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"gh could not be run: {error}"
    if completed.returncode != 0:
        said = (completed.stderr or completed.stdout).strip().splitlines()
        return None, said[0] if said else f"gh api {endpoint} exited {completed.returncode}"
    try:
        return json.loads(completed.stdout or "null"), ""
    except json.JSONDecodeError as error:
        return None, f"gh api {endpoint} did not answer in JSON: {error}"


def remote_permits_full(root: pathlib.Path, *, ask: Asker = gh_api) -> RemoteAnswer:
    """Ask the remote the three questions of `WORKFLOW.md`, fresh, every call.

    `full` comes back on three yeses -- you administer it, it is not a fork,
    nobody else may push -- and for a root with no remote or no git at all,
    where there is no one to expose anything to. Never from an error path: a
    question that could not be put is not a permission that was granted, so an
    unanswerable query is `guest` with `answered` false. Nothing is cached; the
    questions are asked again before every artifact write and every push.
    """
    # Case 6, decided on its own rather than caught out of the remote lookup.
    if not (root / ".git").exists():
        return RemoteAnswer(full=True, answered=True)
    # A `.git` git itself cannot read is not the no-git case: it is no answer.
    if git_output(["rev-parse", "--is-inside-work-tree"], root) != "true":
        return RemoteAnswer(False, False, f"git could not be asked about {root}")
    if not git_output(["remote", "get-url", "origin"], root):
        return RemoteAnswer(full=True, answered=True)

    viewer, error = ask(VIEWER_QUERY, root)
    login = viewer.get("login") if isinstance(viewer, dict) else None
    if not login:
        return RemoteAnswer(False, False, f"the remote did not say who you are: {error or 'no login'}")

    repo, error = ask(REPOSITORY_QUERY, root)
    rights = repo.get("permissions") if isinstance(repo, dict) else None
    if not isinstance(repo, dict) or not isinstance(rights, dict):
        return RemoteAnswer(False, False, f"the remote did not say what you may do: {error or 'no permissions'}")
    name = str(repo.get("full_name") or "the remote")
    if not rights.get("admin"):
        return RemoteAnswer(False, True, f"you do not administer {name}")
    if repo.get("fork"):
        parent = repo.get("parent")
        upstream = parent.get("full_name") if isinstance(parent, dict) else None
        return RemoteAnswer(False, True, f"{name} is a fork of {upstream or 'another repository'}")

    people, error = ask(COLLABORATOR_QUERY, root)
    if not isinstance(people, list):
        return RemoteAnswer(False, False, f"the remote did not list who may push to {name}: {error or 'no list'}")
    # Parsing and filtering are separate questions, and doing them in one pass
    # fails open: an entry dropped for being unreadable leaves `others` empty,
    # and an empty `others` is one of only three places `full` is returned. So
    # "nobody I could parse" would arrive as "nobody else may push". Every entry
    # is read first, and the first one that cannot be read is no answer.
    others: list[str] = []
    for index, person in enumerate(people):
        rights = person.get("permissions") if isinstance(person, dict) else None
        who = str(person.get("login") or "") if isinstance(person, dict) else ""
        if not who or not isinstance(rights, dict):
            return RemoteAnswer(
                False, False, f"the list of who may push to {name} has an entry ({index}) this cannot read"
            )
        if who != login and rights.get("push"):
            others.append(who)
    if others:
        return RemoteAnswer(False, True, f"{name} lets {', '.join(sorted(others))} push too")
    return RemoteAnswer(full=True, answered=True)


def mode(root: pathlib.Path, *, ask: Asker = gh_api) -> str:
    """The resolved mode: the local block's `mode:` line, lowered by detection.

    Detection is a ceiling and never a floor. A written `full`, and no line at
    all, are both offered to `remote_permits_full` and come back `guest` unless
    the remote says yes three times. A written `guest` stays `guest`. A written
    `minimal` stays `minimal`: it is set by hand, detection's six cases never
    produce it, and it already writes no artifacts anywhere -- so rewriting it
    to `guest`, which puts a triad on a fork's branch, would raise exposure
    rather than lower it, the one thing detection is forbidden to do.
    """
    value = local_block(root).get("mode", "").strip()
    if value and value not in MODES:
        raise ConfigError(f"mode {value!r} is not one of {', '.join(MODES)}")
    if value in ("minimal", "guest"):
        return value
    return DEFAULT_MODE if remote_permits_full(root, ask=ask).full else "guest"


# --------------------------------------------------------------------------
# Work items: status derived from artifacts and git, never from stored state
# --------------------------------------------------------------------------


#: The tracked marker the retire commit writes beside the lines it removes:
#: `docs/work/.status-source`, one word. It travels in git, so a checkout with
#: no database still knows which question to ask. **No marker is `file`**, and
#: `file` is the path every reader took before rows existed -- the same path,
#: not a new one that happens to agree with it.
STATUS_MARKER = ".status-source"
FROM_FILE, FROM_ROW = "file", "row"

#: How `sd_db` keys an item row. Both halves are read out of
#: `sd_db/sources/docs_work.py` rather than guessed: `source` is the string
#: below and `external_id` is `<registered checkout>::docs/work/<item>/prd.md`.
#: The pair is that table's unique index.
ITEM_ROW_SOURCE = "docs/work"

#: The six words a row may carry, two more than a `status:` line ever said.
#: `ready_to_send` and `blocked` are states the file vocabulary had no word
#: for; they pass through rather than being folded into one of the four,
#: because folding is how `blocked` would become workable.
ROW_STATUSES = ("planning", "ready", "in_progress", "ready_to_send", "blocked", "done")


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
    #: Written by whichever pass parked the item: `<date> age-sweep` from the
    #: 45-day sweep, `<date> bulk-park (D2)` from the one-time fleet-wide park.
    #: Read the value, do not assume the reason -- fleet-wide the split is 65
    #: age-sweep to 172 bulk-park. Set here and nowhere else --
    #: parked is a property of the item, never a row in a separate ledger.
    parked: str = ""
    inconsistencies: tuple[str, ...] = ()


def status_marker(root: pathlib.Path, work_dir: str = WORK_DIR) -> tuple[str, str]:
    """Where this checkout's item statuses come from: `(word, problem)`.

    No marker at all is `file`. A marker that is present and says something
    this cannot read comes back as no word and a sentence, and deliberately
    *not* as `file`: the marker exists only on a checkout whose `status:`
    lines have been removed, so falling back to the line there is answering
    from a line that is not in the file. Every item is then `unknown` with
    the marker named, which is the loud form of the same finding.
    """
    path = pathlib.Path(root) / work_dir / STATUS_MARKER
    try:
        said = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return FROM_FILE, ""
    except (OSError, UnicodeDecodeError) as error:
        return "", f"{path} cannot be read: {error}"
    if said in (FROM_FILE, FROM_ROW):
        return said, ""
    return "", f"{path} says {said!r}, which is neither {FROM_FILE!r} nor {FROM_ROW!r}"


def external_id(root: pathlib.Path | str, item_dir: pathlib.Path) -> str:
    """One item's row key. A writer needs it and no read connection to get it."""
    return (f"{main_worktree_root(pathlib.Path(root).resolve())}::"
            f"{WORK_DIR}/{item_dir.name}/prd.md")


class Rows:
    """This checkout's item rows, read through `sd_db` and through nothing else.

    Opened once for an enumeration rather than once per item: sixty-four
    items would otherwise open the database sixty-four times to draw one
    `sd-status`. `sqlite3` is not imported here and never will be -- item B's
    requirement 2 is that the library owns every connection.

    `opened` is the distinction this class exists to keep. A machine with no
    database is the designed database-free case and asks git instead; a
    machine that *has* one and holds no row for an item has lost that item,
    and reading "no row" as "so the item is open" is how delivered work gets
    picked up and done a second time.

    `installed` is the third state, and it was kept and then thrown away.
    `sd_db` lives in this pack's virtualenv, so one machine has two answers:
    under `.venv/bin/python` the row decides, under the system `python3` the
    import fails and git decides, and until this attribute was read the two
    printed different words for the same item with nothing to say which had
    run. That is how an item whose row has said `planning` since it was opened
    got reported `in_progress`.
    """

    def __init__(self, root: pathlib.Path) -> None:
        # Rows are keyed by the registered checkout, which for a linked
        # worktree is the main one: the migration enumerates the `repo` table
        # and a worktree was never added to it.
        self.base = str(main_worktree_root(pathlib.Path(root).resolve()))
        self.opened = False
        # Two absences, and they are not the same absence. `installed` is
        # whether this interpreter can import the library at all; `opened` is
        # whether it found a database to read. A library that says there is no
        # database is the designed database-free case. A library that is not
        # here has said nothing, and the answer that follows came from a
        # different source than the marker named.
        self.installed = False
        self.problem = ""
        self._connection: Any = None
        self._read: Any = None
        try:
            import sd_db  # noqa: PLC0415 - `make setup` provisions it; absent is a state
        except ImportError as error:
            self.problem = f"sd_db is not installed here: {error}"
            return
        self.installed = True
        try:
            self._connection = sd_db.connect(write=False)
        except Exception as error:  # no file, or a schema this cannot read
            self.problem = f"sd_db could not open the database: {error}"
            return
        self._read = sd_db.writes.item_by_external
        self.opened = True

    def external_id(self, item_dir: pathlib.Path) -> str:
        """The row's key, off the base this instance already resolved."""
        return f"{self.base}::{WORK_DIR}/{item_dir.name}/prd.md"

    def status(self, item_dir: pathlib.Path) -> tuple[str, str]:
        """`(word, problem)` for one item; both empty means no database."""
        if not self.opened:
            return "", ""
        identity = self.external_id(item_dir)
        try:
            row = self._read(self._connection, ITEM_ROW_SOURCE, identity)
        except Exception as error:
            return "", f"the row for {identity} could not be read: {error}"
        if row is None:
            return "", f"the database holds no {ITEM_ROW_SOURCE} row for {identity}"
        said = str(row["status"] or "").strip()
        if said not in ROW_STATUSES:
            return "", (f"the row for {identity} says status {said!r}, which is not "
                        f"one of {', '.join(ROW_STATUSES)}")
        return said, ""

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
        self._connection, self._read, self.opened = None, None, False


@dataclass
class Statuses:
    """One checkout's answer to "where does a status come from", resolved once.

    The marker is a property of the checkout and not of the item, so reading
    it per item puts the same question sixty-four times; the database is
    opened once too, and closed by whoever opened it.
    """

    root: pathlib.Path
    source: str
    problem: str = ""
    rows: Rows | None = None

    @classmethod
    def of(cls, root: pathlib.Path | str, work_dir: str = WORK_DIR) -> "Statuses":
        root = pathlib.Path(root)
        source, problem = status_marker(root, work_dir)
        return cls(root, source, problem, Rows(root) if source == FROM_ROW else None)

    def close(self) -> None:
        if self.rows is not None:
            self.rows.close()


def _root_of(item_dir: pathlib.Path) -> pathlib.Path:
    """The repository root an item sits in, from its own path and no git call.

    `<root>/docs/work/<item>`, or `<root>/docs/work/archive/<month>/<item>`
    two levels deeper. Derived rather than asked, so reading one directory
    stays as cheap as it was before there was a marker to find.
    """
    root = item_dir.resolve()
    for _ in range(5 if root.parent.parent.name == ARCHIVE_DIR else 3):
        root = root.parent
    return root


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


def _from_git(
    root: pathlib.Path,
    item_dir: pathlib.Path,
    prd: pathlib.Path,
    fields: dict[str, str],
    problems: list[str],
) -> StatusReport:
    """What a checkout with no database derives once the marker is present.

    `yes` is `done`. `unknown` is emphatically not `no`: a shallow clone and
    an unreachable remote cannot see the trailer, and reading either as "not
    delivered" hands finished work back to the next reader that picks it.
    What the retire left behind says which kind of open the rest are -- an
    item recording the branch it lives on is being worked, one that records
    none is still being planned.
    """
    answer = delivered(root, item_dir.name)
    if answer == YES:
        return StatusReport("done", False, tuple(problems))
    if answer == UNKNOWN:
        problems.append(
            f"{prd}: this checkout cannot see whether {item_dir.name} was "
            f"delivered; run `{answer.repair}`"
        )
        return StatusReport("unknown", False, tuple(problems))
    branch = fields.get("branch", "").strip()
    return StatusReport("in_progress" if branch else "planning", False, tuple(problems))


def _from_row(
    item_dir: pathlib.Path,
    prd: pathlib.Path,
    fields: dict[str, str],
    problems: list[str],
    statuses: "Statuses",
) -> StatusReport:
    """The status the row says, and the two things it says about the tree.

    *Stale*: the item's `status:` line survived the retire -- on a worktree
    kept across it, on a branch that still carries the line -- and says
    something the row does not. What is checked is what the line says, not
    that there is one: a line that agrees is a leftover for the lint to fail
    on, and calling it stale would report a disagreement that is not there.

    *Unmarked*: the row is `done` and no commit carries a closing trailer for
    the item, so every database-free checkout goes on picking it. `delivered`
    is the one question asked about that, here as everywhere else.
    """
    said, trouble = statuses.rows.status(item_dir) if statuses.rows else ("", "")
    if trouble:
        problems.append(f"{prd}: {trouble}")
        return StatusReport("unknown", False, tuple(problems))
    if not said:
        # Git answers, as it does for any checkout with no database -- but the
        # marker said the row was the authority, so a fall-through has to be
        # audible. Only the not-installed case is named: a library that opened
        # and found no database has answered the question, and saying so on
        # every item of a database-free checkout would be noise about the
        # designed path.
        if statuses.rows is not None and not statuses.rows.installed:
            problems.append(
                f"{prd}: {statuses.rows.problem}, so this status came from git "
                f"and not from the row this checkout's marker names"
            )
        return _from_git(statuses.root, item_dir, prd, fields, problems)
    line = fields.get("status", "").strip()
    if line and line != said:
        problems.append(
            f"{prd}: its `status:` line says {line!r} where the row says {said!r}; "
            f"the line is stale"
        )
    if said == "done" and delivered(statuses.root, item_dir.name) != YES:
        problems.append(
            f"{prd}: the row is done and no commit carries {DELIVERS_TRAILER} or "
            f"{CLOSES_TRAILER} for {item_dir.name}; the item is unmarked"
        )
    return StatusReport(said, False, tuple(problems))


def _status_report(
    item_dir: pathlib.Path,
    fields: dict[str, str],
    problems: list[str],
    statuses: "Statuses",
) -> StatusReport:
    archived = _is_archived(item_dir)
    prd = item_dir / "prd.md"
    if archived:
        return StatusReport("done", True, tuple(problems))

    if not statuses.source:
        problems.append(f"{prd}: {statuses.problem}")
        return StatusReport("unknown", False, tuple(problems))
    if statuses.source == FROM_ROW:
        return _from_row(item_dir, prd, fields, problems, statuses)

    declared = fields.get("status", "").strip()
    if declared not in ITEM_STATUSES:
        problems.append(
            f"{prd}: status {declared!r} is not one of {', '.join(ITEM_STATUSES)}"
        )
        return StatusReport("unknown", False, tuple(problems))
    if declared == "in_progress" and not fields.get("branch", "").strip():
        problems.append(f"{prd}: an in_progress item records the branch it lives on")
    return StatusReport(declared, False, tuple(problems))


def _reported(
    item_dir: pathlib.Path,
    fields: dict[str, str],
    problems: list[str],
    statuses: "Statuses | None",
) -> StatusReport:
    """`_status_report`, resolving and closing its own `Statuses` when given none."""
    if statuses is not None:
        return _status_report(item_dir, fields, problems, statuses)
    own = Statuses.of(_root_of(item_dir))
    try:
        return _status_report(item_dir, fields, problems, own)
    finally:
        own.close()


def status_report(
    item_dir: pathlib.Path, *, statuses: "Statuses | None" = None
) -> StatusReport:
    """Derive a work item's status from its artifacts, or from its row.

    An item under `archive/` is `done` by virtue of where it lives -- the move
    is the record. Anything else answers wherever `docs/work/.status-source`
    says: with no marker, from the `status:` line in `prd.md` frontmatter, and
    with the marker saying `row`, from the item's row in the one database. A
    status that is missing, unknown, or contradicted by the rest of the
    frontmatter is reported as an inconsistency rather than raised: a lint rule
    is the place to fail, and this function is also called by tools that only
    want to show you the tree.
    """
    item_dir = pathlib.Path(item_dir)
    fields, problems = _read_prd(item_dir)
    return _reported(item_dir, fields, problems, statuses)


def derive_status(item_dir: pathlib.Path) -> str:
    """The derived status alone; `unknown` when the artifacts do not say."""
    return status_report(item_dir).status


def work_item(item_dir: pathlib.Path, *, statuses: "Statuses | None" = None) -> WorkItem:
    """Read one work item directory into a `WorkItem`, reading the prd once."""
    item_dir = pathlib.Path(item_dir)
    fields, problems = _read_prd(item_dir)
    report = _reported(item_dir, fields, problems, statuses)
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
    """Every work item, enumerated from the tree rather than from an index.

    The one place the marker is read and the one place the database is
    opened, so every reader that picks an item -- `sd-review`, `sd-plan`,
    `sd-status`, the sweep -- comes through here and none of them restates
    where a status comes from.
    """
    statuses = Statuses.of(root, work_dir)
    try:
        return [
            work_item(path, statuses=statuses)
            for path in work_item_dirs(root, work_dir)
        ]
    finally:
        statuses.close()


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


# --------------------------------------------------------------------------
# Commit trailers: who wrote a change, said by the change itself
# --------------------------------------------------------------------------

#: The scopes that resolve to a commit range. Only these carry trailers.
TRAILER_SCOPES = ("branch", "pr")

#: `Authored-with: <entry>/<vendor>` on the commit that made the change, and
#: `Attributes: <sha> <entry>/<vendor>` on a later commit for one that was made
#: before the convention reached it. `sd-ship` and `sd attribute` write them.
AUTHORED_TRAILER = "Authored-with:"
ATTRIBUTES_TRAILER = "Attributes:"

#: What a commit a person wrote says. Spelled out rather than left implicit,
#: because the absence of a trailer has to keep meaning "nobody said" -- if an
#: untagged commit read as human-authored, an anthropic-written commit would
#: become reviewable by anthropic every time the trailer was forgotten.
HUMAN_AUTHOR = "human"


class TrailerError(Exception):
    """A commit that does not say, or says something unreadable."""


def commit_messages(root: pathlib.Path, base: str, head: str) -> list[tuple[str, str]]:
    """Each commit in the range as `(sha, message)`, newest first.

    Merges are not among them. A merge commit introduces no change of its
    own -- it records that two histories met -- so there is no work for it to
    say who wrote, and asking cost a real branch its review: merging `main` to
    catch up produced one untagged commit, and the whole range refused. The
    commits it brings in are already in the range, each answering for itself.
    """
    raw = git_output(["log", "--no-merges", "--format=%H%x1f%B%x1e", f"{base}..{head}"], root)
    if not raw:
        return []
    records = []
    for chunk in raw.split("\x1e"):
        if "\x1f" not in chunk:
            continue
        sha, _, message = chunk.strip().partition("\x1f")
        records.append((sha.strip(), message))
    return records


def attribution(root: pathlib.Path, base: str, head: str) -> dict[str, str]:
    """`<sha> -> <entry>/<vendor>` for every commit in the range that says.

    A commit says either by carrying its own `Authored-with:` or by being named
    in a later commit's `Attributes:`. Nothing takes a flag for this: a branch
    is a set of commits and each one answers for itself, because a single
    `--author` for the whole range is a claim about work the person making the
    claim may not have done.
    """
    own: dict[str, str] = {}
    claimed: dict[str, str] = {}
    commits = commit_messages(root, base, head)
    shas = [sha for sha, _ in commits]
    for sha, message in commits:
        # Git's trailer block -- the last paragraph -- and unindented, which is
        # what makes a trailer a trailer. Reading the whole message, stripped,
        # reads a trailer quoted inside a commit that was describing one.
        for line in message.rstrip().rsplit("\n\n", 1)[-1].splitlines():
            line = line.rstrip()
            if line.startswith(AUTHORED_TRAILER):
                own.setdefault(sha, line[len(AUTHORED_TRAILER) :].strip())
            elif line.startswith(ATTRIBUTES_TRAILER):
                parts = line[len(ATTRIBUTES_TRAILER) :].split()
                if len(parts) == 2:
                    named = _in_range(parts[0], shas)
                    if named:
                        claimed.setdefault(named, parts[1])
    # A commit's own trailer outranks a later commit's claim about it, and the
    # two dictionaries exist to make that ordering explicit. Merging in one
    # walk let a later `Attributes:` overwrite what a commit said about itself,
    # so relabelling an anthropic-authored commit as an openai one -- and
    # thereby buying it an anthropic reviewer -- took one line in a later
    # message. `Attributes:` is for commits that said nothing.
    return {**claimed, **own}


def _in_range(named: str, shas: list[str]) -> str:
    """The full sha `named` refers to, or "" if the range does not hold it.

    A claim about a commit outside `base..head` says nothing about the work
    under review, and keeping it bought a vendor a place in the author set --
    and so cost that vendor its seat as a reviewer -- for a commit nobody is
    reviewing. Three ways it happens, one answer for all of them: the named
    commit already merged, a rebase moved it, or the line is simply wrong.

    A prefix is enough, the way it is everywhere else in git, but only when it
    picks out one commit. Two matches name nothing in particular.
    """
    if len(named) < 7:
        return ""
    matches = [sha for sha in shas if sha.startswith(named)]
    return matches[0] if len(matches) == 1 else ""


def author_vendors(root: pathlib.Path, base: str, head: str) -> tuple[str, ...]:
    """The vendors this range was written with. Raises when a commit is silent."""
    said = attribution(root, base, head)
    untagged = [sha for sha, _ in commit_messages(root, base, head) if sha not in said]
    if untagged:
        raise TrailerError(
            f"{len(untagged)} commit(s) in {base}..{head} carry no "
            f"{AUTHORED_TRAILER} trailer, starting at {untagged[-1][:12]}. A "
            f"commit that does not say who wrote it cannot be reviewed by "
            f"somebody else on purpose. Record it with "
            f"`sd attribute {untagged[-1][:12]} <entry>`."
        )
    vendors = []
    for sha, value in said.items():
        if value == HUMAN_AUTHOR:
            continue
        entry, separator, vendor = value.partition("/")
        # Stripped and folded, because the comparison this feeds is an exact
        # `in` against the registry's vendor. `claude / anthropic` yielded
        # " anthropic", which matched no entry, so the author's own vendor
        # stayed on the chain and reviewed the branch it had written -- the
        # one thing the trailer exists to stop, failing open and in silence.
        entry, vendor = entry.strip(), vendor.strip().lower()
        if not separator or not entry or not vendor:
            raise TrailerError(
                f"{sha[:12]} says {AUTHORED_TRAILER} {value!r}, which is neither "
                f"{HUMAN_AUTHOR!r} nor an '<entry>/<vendor>' pair. A trailer that "
                f"cannot be read is not a weaker claim than one that is missing."
            )
        if vendor not in vendors:
            vendors.append(vendor)
    return tuple(vendors)


def attribution_value(name: str, registry: Any) -> str:
    """What a trailer says when it names `name`: `<entry>/<vendor>`, or `human`.

    The inverse of the parse in `author_vendors`, so the two cannot drift, and
    folding the vendor to lower case on the way out as well as on the way in,
    so the line `git log` shows is the string the independence check compares.

    Everything else refuses, because a value that does not survive the round
    trip is not read as a weaker claim -- it is read as *no* claim.
    `attribution` drops an `Attributes:` line that does not split into two
    fields, a commit with no claim keeps its vendor out of the author set, and
    the author's own vendor stays on the reviewer chain, open and in silence.
    """
    entry = name.strip()
    provider = registry.providers.get(entry)
    if entry == HUMAN_AUTHOR:
        if provider is not None:
            raise TrailerError(
                f"{HUMAN_AUTHOR!r} is what a commit a person wrote says, so it is "
                f"not a name a registry entry may take, and {registry.path} has "
                f"one. Its trailer would read as the operator and hide its vendor."
            )
        return HUMAN_AUTHOR
    if provider is None:
        known = ", ".join(sorted(registry.providers)) or "nothing"
        raise TrailerError(
            f"no registry entry named {entry!r} in {registry.path}, which holds "
            f"{known}. Name an entry the registry has, or {HUMAN_AUTHOR!r} bare: a "
            f"trailer nothing resolves records no vendor, and a range with no "
            f"vendor is one its own author may review."
        )
    vendor = provider.vendor.strip().lower()
    value = f"{entry}/{vendor}"
    if value.split() != [value] or "/" in entry or "/" in vendor or not vendor:
        raise TrailerError(
            f"entry {entry!r} carries vendor {provider.vendor!r} in {registry.path}, "
            f"and {value!r} is no '<entry>/<vendor>' pair a trailer can carry: a "
            f"space or a second slash makes the line unreadable, and an unreadable "
            f"claim is dropped rather than questioned. Fix the registry."
        )
    return value


def _own_trailer(root: pathlib.Path, sha: str) -> str:
    """Its own `Authored-with:` value, or "" -- last paragraph, unindented,
    `attribution`'s rule, so a commit that quotes a trailer stays repairable.
    """
    message = git_output(["log", "-1", "--format=%B", sha], root) or ""
    for line in message.rstrip().rsplit("\n\n", 1)[-1].splitlines():
        if line.rstrip().startswith(AUTHORED_TRAILER):
            return line.rstrip()[len(AUTHORED_TRAILER) :].strip()
    return ""


def _on_this_branch(root: pathlib.Path, ref: str) -> str:
    """`ref` as a full sha when it names one commit reachable from `HEAD`.

    A claim about a commit off this branch is a line its review never reads:
    written, reported as done, and dropped by `_in_range` just as quietly.
    """
    full = git_output(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], root)
    if not full:
        return ""
    return full if git_output(["merge-base", "--is-ancestor", full, "HEAD"], root) is not None else ""


def _covered(root: pathlib.Path, target: str) -> list[str]:
    """The commits `target` names that still need an author, newest first.

    Commits that already say are left alone rather than restated. After a
    rebase -- the one case that loses an attribution, since neither integration
    path rewrites a branch -- a range holds both the commits whose own trailer
    survived and the one whose claim named a hash that is gone, and a range
    form refusing that mixture could not repair it. A single commit that says
    is refused instead: its own trailer outranks any later claim about it.
    """
    if ".." not in target:
        full = _on_this_branch(root, target)
        if not full:
            raise TrailerError(f"{target!r} names no commit reachable from HEAD")
        if len((git_output(["rev-list", "--parents", "-n", "1", full], root) or "").split()) > 2:
            raise TrailerError(
                f"{full[:12]} is a merge, which wrote nothing to answer for; the "
                f"review skips merges and would skip this claim with them.")
        said = _own_trailer(root, full)
        if said:
            raise TrailerError(
                f"{full[:12]} already says {AUTHORED_TRAILER} {said!r}, which "
                f"outranks any later {ATTRIBUTES_TRAILER} claim about it."
            )
        return [full]
    base, _, head = target.partition("..")
    if not base or not head or ".." in head or not _on_this_branch(root, head):
        raise TrailerError(f"{target!r} is no `<from>..<to>` range ending on this branch")
    commits = [sha for sha, _ in commit_messages(root, base, head)]
    if not commits:
        raise TrailerError(
            f"no commit in {target} carries work to attribute: a merge introduces "
            f"no change of its own, and what it brought in answers for itself."
        )
    covered = [sha for sha in commits if not _own_trailer(root, sha)]
    if not covered:
        raise TrailerError(f"every commit in {target} already names its author")
    return covered


def attribute(
    root: pathlib.Path, target: str, name: str, registry: Any
) -> tuple[str, str, list[str]]:
    """Record `name` as the author of `target`, as one empty commit on `HEAD`.

    `target` is one commit or a `<from>..<to>` range. What lands is a single
    empty commit carrying an `Attributes:` line per repaired commit and its own
    `Authored-with: human`, because the operator made it and a repair that
    needs repairing is not one (C-40). Returns the new sha, the value written
    and the commits covered.

    A commit rather than a note: a notes ref is one mutable ref a repository
    shares, and two clones attributing different commits of one branch diverge
    on it. A commit is branch-local, pushes with the branch, and squashes away
    at the merge with everything else.
    """
    value = attribution_value(name, registry)
    covered = _covered(root, target)
    trailers = [f"{ATTRIBUTES_TRAILER} {sha} {value}" for sha in covered]
    trailers.append(f"{AUTHORED_TRAILER} {HUMAN_AUTHOR}")
    written = subprocess.run(  # fixed argv, no shell
        ["git", "commit", "--allow-empty", "--quiet",
         "-m", f"chore(attribution): {len(covered)} commit(s) written with {value}",
         "-m", "Recorded by the operator, after the fact, for commits that predate "
               "the trailer or lost it to a rewrite.",
         "-m", "\n".join(trailers)],
        cwd=str(root), capture_output=True, text=True,
        timeout=GIT_TIMEOUT_SECONDS, check=False,
    )
    if written.returncode != 0:
        raise TrailerError(
            f"git refused the attributing commit: "
            f"{(written.stderr or written.stdout).strip() or 'no reason given'}"
        )
    return git_output(["rev-parse", "HEAD"], root) or "", value, covered


# --------------------------------------------------------------------------
# Delivery: the one question a checkout with no database puts to git
# --------------------------------------------------------------------------

#: The closing trailers. `Delivers:` rides the merge that delivers the item;
#: `Closes:` a later merge in the same repository, or an empty commit on the
#: item's own branch, for a delivery or a cancellation whose own merge went
#: out without one. `Item:` is deliberately not here: it ties a merge to an
#: item and closes nothing, so a slice shipped without `--deliver` carries it
#: alone, and the item stays open.
DELIVERS_TRAILER = "Delivers:"
CLOSES_TRAILER = "Closes:"

#: `no` is a positive finding from history the checkout actually has;
#: `unknown` is what a checkout that cannot see far enough says instead.
#: Swapping the two silently reopens delivered work, since every reader that
#: picks an item excludes a `yes` and treats an `unknown` as not selectable.
YES, NO, UNKNOWN = "yes", "no", "unknown"


class Answer(str):
    """One of those three words, plus the repair an `unknown` asks for.

    A string, so `delivered(...) == "yes"` is the whole of it for a caller
    that wants only the word; `repair` rides along for the reader that has to
    refuse by name, since a boundary and an unreachable remote differ.
    """

    repair: str

    def __new__(cls, word: str, repair: str = "") -> "Answer":
        answer = super().__new__(cls, word)
        answer.repair = repair
        return answer


def _closes(message: str, item: str) -> bool:
    """True when this message's trailer block -- its last paragraph, which is
    what makes a trailer a trailer -- closes `item`. Reading the whole message
    would let a commit that quoted a trailer close the item it named."""
    for line in message.rstrip().rsplit("\n\n", 1)[-1].splitlines():
        name, _, value = line.rstrip().partition(" ")
        if name in (DELIVERS_TRAILER, CLOSES_TRAILER) and value.strip() == item:
            return True
    return False


def _closed_by(root: pathlib.Path, ref: str, item: str) -> bool:
    """Whether a commit reachable from `ref` closes `item`; a ref git cannot
    resolve closes nothing. `--grep` only narrows the walk; `_closes` decides."""
    grep = f"{DELIVERS_TRAILER}|{CLOSES_TRAILER}"
    raw = git_output(["log", "--format=%H%x1f%B%x1e", "-E", "--grep", grep, ref], root) or ""
    return any(_closes(c.partition("\x1f")[2], item) for c in raw.split("\x1e"))


def upstream(root: pathlib.Path) -> tuple[str, str]:
    """The remote this checkout can be behind, and that remote's default branch:
    HEAD's upstream then `origin`, and what the remote publishes then the first
    of `main` and `master` this checkout resolves. A checkout with no remote is
    never behind, and gets `""` -- it answers from what it has."""
    names = (git_output(["remote"], root) or "").split()
    head = git_output(["rev-parse", "--abbrev-ref", "HEAD"], root) or ""
    tracked = git_output(["config", "--get", f"branch.{head}.remote"], root)
    fallback = "origin" if "origin" in names else (names[0] if names else "")
    remote = tracked if tracked in names else fallback
    published = git_output(["symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD"], root)
    if published:
        return remote, published.partition("/")[2] or published
    for name in ("main", "master"):
        if git_output(["rev-parse", "--verify", "--quiet", name], root) is not None:
            return remote, name
    return remote, "main"


def delivered(root: pathlib.Path, item: str) -> Answer:
    """`yes`, `no` or `unknown`: is `item` delivered, asked of git and nothing else.

    `yes` when a commit reachable from the remote's default branch as just
    fetched, from the checkout's branch as just fetched from its upstream, or
    from `HEAD`, carries `Delivers: <item>` or `Closes: <item>`. `no` when
    none does *and* the history is whole *and* it is current; `unknown` when
    it is neither, because a shallow clone's trailer may sit past the boundary
    and a clone retained while another machine delivered or cancelled the item
    holds neither trailer -- both would answer `no` for finished work.

    The default branch is fetched first and answers `yes` alone when it carries
    the trailer; only otherwise is the checkout's branch fetched, because the
    mark for a branch-only cancel and for a guest delivery lives on that branch
    and on no other. A branch the remote no longer has, deleted at its own
    merge, is nothing to be behind and the answer comes from the default branch
    and `HEAD`; a branch fetch that fails while the ref is still published is
    `unknown`, since the tip it lacks may carry the mark.
    """
    # "false" is the one answer meaning a repository, and a whole one: None is
    # no git at all, "true" a boundary the trailer may be sitting past.
    if git_output(["rev-parse", "--is-shallow-repository"], root) != "false":
        return Answer(UNKNOWN, "git fetch --unshallow")
    remote, default = upstream(root)
    if not remote:
        return Answer(YES if any(_closed_by(root, r, item) for r in ("HEAD", default)) else NO)
    if git_output(["fetch", remote, default], root) is None:
        return Answer(UNKNOWN, f"git fetch {remote} {default}")
    if _closed_by(root, "FETCH_HEAD", item):
        return Answer(YES)
    branch = git_output(["rev-parse", "--abbrev-ref", "HEAD"], root) or ""
    if branch not in ("", "HEAD", default):
        if git_output(["fetch", remote, branch], root) is None:
            # The remote answered a moment ago, so a refusal here is about the
            # ref -- unless it is still published, and then the tip is missing.
            listed = git_output(["ls-remote", "--heads", remote, branch], root)
            if listed is None or listed:
                return Answer(UNKNOWN, f"git fetch {remote} {branch}")
        elif _closed_by(root, "FETCH_HEAD", item):
            return Answer(YES)
    return Answer(YES if _closed_by(root, "HEAD", item) else NO)
