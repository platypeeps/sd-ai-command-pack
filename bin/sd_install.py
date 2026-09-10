"""Machine-scope renderer for the sd-* surfaces.

The old installer targeted eighteen platforms and a repository at a time. This
one targets a machine and three platforms, and the difference in kind matters
more than the difference in size: nothing it writes lands inside a tracked
repository, so the framework has no footprint to keep in sync and nothing to
re-render after a payload edit.

Two rules constrain every write here, and both are load-bearing:

  * **It owns only names it renders.** `installed.json` records each written
    path with the digest of what was written. `--uninstall` removes exactly
    those, and refuses a path whose digest no longer matches unless forced, so
    a file someone edited by hand is never silently deleted.
  * **It never edits a tracked repository file.** The single exception outside
    a platform home is the one SessionStart stanza in `~/.claude/settings.json`
    for `sd-handoff-restore`, which is recorded in `owned` like any other write
    and removed on uninstall.

Antigravity is deliberately not rendered. Its skill format is byte-identical to
Claude's, so the renderer would be a fourth destination and nothing more, but
which of three candidate roots `agy` actually loads is unresolved (probe P1,
R9b-D1). Rendering into the wrong one would produce surfaces that appear
installed and never load, which is worse than not rendering. The parity test
asserts the Antigravity count is zero or twelve, never partial.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

SKILL_FILE = "SKILL.md"
STATE_DIR = "sd-ai-command-pack"
RECEIPT_NAME = "installed.json"
RECEIPT_SCHEMA = 1

# Every hook the pack registers, as data. It was three constants naming one
# hook until 2026-09-07, which was right while there was one; `skill_use` needs
# two more on two more events, and criterion 29 adds two after that. A table is
# the difference between adding a row and editing four functions.
#
# `matchers` is per event and its meaning is the event's, not ours. SessionStart
# matches a start reason. PreToolUse matches a tool name, so the pattern names
# the only two tools `bin/sd-skill-use` can act on rather than `*`: a hook that
# fires on every tool call to decide it has nothing to do is a cost paid on
# every tool call. UserPromptSubmit has nothing to match on, and the empty
# matcher is how that is spelled.
HOOK_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("bin/sd-handoff-restore", "SessionStart", ("startup", "clear")),
    ("bin/sd-skill-use", "PreToolUse", ("Skill|Read",)),
    ("bin/sd-skill-use", "UserPromptSubmit", ("",)),
)

EXCLUDES_LINE = "CLAUDE.local.md"


def sibling(name: str):
    """A module out of this file's own `bin/`, which is not a package.

    The installer is loaded by path as often as it is run as a script, so a
    plain `import` finds a neighbour only when the process happened to start
    in `bin/`. Reserved for the case that earns it: a rule somebody else owns.
    `sd_lib` owns the local block's markers and its grammar, and the installer
    used to keep its own copy of both -- which is why it spent its life
    writing a block the reader parsed as `{}`.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    return importlib.import_module(name)


# ------------------------------------------------------------------- location


def sandboxed(home: Path) -> bool:
    """True whenever `home` is somewhere other than the real home directory.

    Derived from the home itself rather than passed alongside it, because
    every caller that has to remember a flag is a caller that can forget one,
    and forgetting this one writes into the developer's real dotfiles.
    """
    return home != Path(os.path.expanduser("~"))


def xdg_root(var: str, home: Path, environ: dict[str, str], *parts: str) -> Path:
    """An absolute `$XDG_*_HOME`, or `home/<parts>` when there is none to use.

    `--home DIR` says "treat DIR as $HOME", but an XDG variable holds an
    absolute path into the *real* home, so honouring one under a scratch
    install sends part of that install outside the directory the caller named.

    That leak used to be patched at the entrypoint: `main()` rewrote both XDG
    roots whenever `--home` was given. Which worked, for callers that came
    through `main()`. CI found the gap on the third attempt at this class of
    bug -- `RendererParityTests` asks `platform_homes(scratch_home, os.environ)`
    where the surfaces should be, and on a runner with
    `XDG_CONFIG_HOME=/home/runner/.config` set it was told `/home/runner`,
    while the install (through `main()`, with the roots rewritten) had put them
    in the scratch home. The install stayed contained; the question about it
    did not, and the parity assertion failed against a path in the runner's
    real home. On this developer's machine both variables are unset, so both
    sides agreed and the escape was invisible.

    The fix is the one the two earlier `--home` escapes converged on: resolve
    it where it is asked rather than where it is convenient. Under a sandbox an
    override is honoured only while it stays inside the given home. Outside a
    sandbox it is honoured as set, including the unusual but legitimate case of
    an XDG root outside `$HOME` -- redirecting that would be this helper
    inventing a policy rather than closing a leak.
    """
    configured = environ.get(var, "")
    if configured and os.path.isabs(configured):
        root = Path(configured)
        if not sandboxed(home) or _is_within(root, home):
            return root
    return home.joinpath(*parts)


def _is_within(path: Path, parent: Path) -> bool:
    """Containment by path parts, not by string prefix.

    `/tmp/home-2` is not inside `/tmp/home` however much it looks like it.
    """
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def state_home(home: Path, environ: dict[str, str]) -> Path:
    """`$XDG_STATE_HOME` when usable, else `<home>/.local/state`.

    Deliberately identical in shape to `bin/sd-handoff`'s helper rather than
    imported from it: the handoff tools must work with no installer present at
    all, and a shared module would make the installer a dependency of the
    thing it installs. It differs in taking the home explicitly, because this
    one has to honour `--home` and that one has no such flag.
    """
    return xdg_root("XDG_STATE_HOME", home, environ, ".local", "state")


def config_home(home: Path, environ: dict[str, str]) -> Path:
    """`$XDG_CONFIG_HOME` when usable, else `<home>/.config`."""
    return xdg_root("XDG_CONFIG_HOME", home, environ, ".config")


def receipt_path(home: Path, environ: dict[str, str]) -> Path:
    return state_home(home, environ) / STATE_DIR / RECEIPT_NAME


@dataclass(frozen=True)
class PlatformHome:
    """Where one platform's surfaces live, and how they are named there."""

    key: str
    root: Path
    layout: str  # "directory" -> <name>/SKILL.md ; "flat" -> <name>.md

    def target_for(self, name: str) -> Path:
        if self.layout == "directory":
            return self.root / name / SKILL_FILE
        return self.root / f"{name}.md"


def platform_homes(home: Path, environ: dict[str, str]) -> list[PlatformHome]:
    """The three rendered platforms, in a stable order.

    OpenCode is flat because its command surface is one file per command; the
    P1 checklist counts them with `grep -c '^sd-'`, which only works if the
    names are the filenames.
    """
    config_root = config_home(home, environ)
    return [
        PlatformHome("claude", home / ".claude" / "skills", "directory"),
        PlatformHome("codex", home / ".codex" / "skills", "directory"),
        PlatformHome("opencode", config_root / "opencode" / "commands", "flat"),
    ]


def agent_homes(home: Path) -> list[PlatformHome]:
    """Where agents are rendered. Claude only, and that is a stated limit.

    Codex keeps its agents as TOML with the instructions embedded in a triple-
    quoted string. Producing that is a translation layer -- the exact thing
    `render` refuses to be -- and a translated agent could not be checked by the
    parity test's byte-compare, only by asserting the translation ran. So v1
    renders agents to Claude, where the format is the same file the checkout
    holds, and says plainly that Codex agents are not rendered rather than
    shipping a converter nothing verifies.
    """
    return [PlatformHome("claude", home / ".claude" / "agents", "flat")]


# -------------------------------------------------------------------- payload


@dataclass(frozen=True)
class Extra:
    """One file that ships beside a skill, and where it lands under it.

    `relative` rather than just a path because the source is not always inside
    the skill directory: a reference cited by twenty skills is stored once and
    copied into each, so the destination has to be stated separately from where
    it was read.
    """

    relative: str
    source: Path


@dataclass
class Surface:
    """One sd-* skill in the checkout, with the files it carries."""

    name: str
    skill: Path
    extras: list[Extra] = field(default_factory=list)


# A skill cites a companion file by the path it will have once installed --
# `references/source-standards.md` -- so this is what a citation looks like,
# not what a file is called.
CITATION = re.compile(r"(?<![\w/])references/([\w.-]+\.md)")
SHARED_DIR = "_shared"


def shared_references(checkout: Path) -> dict[str, Path]:
    """Companion files stored once and copied into every skill that cites them.

    Ninety citations of one file across the folded skills, and three files carry
    most of them. Storing a copy per skill would put the same paragraph in the
    repository fifty-four times, which is the exact shape ("four copies of every
    shipped script") this rebuild exists to remove. One copy in the checkout,
    fanned out at render time, keeps the skill's own relative citation working
    without making the tree the place the duplication lives.
    """

    root = checkout / "skills" / SHARED_DIR / "references"
    if not root.is_dir():
        return {}
    return {path.name: path for path in sorted(root.iterdir()) if path.is_file()}


PATHS_FILE = "paths.json"
CONTRIB_DIR = "contrib"


class PathsRefused(Exception):
    """The paths file is missing, unreadable, or does not name three paths."""


def paths_path(checkout: Path) -> Path:
    return checkout / "skills" / PATHS_FILE


def read_paths(checkout: Path) -> dict[str, dict]:
    """The three paths and the skills on each.

    Refuses rather than defaulting to disk. The whole point of requirement 10
    is that a skill installs because a path names it; an installer that fell
    back to enumerating `skills/` when the file was missing would render the
    old set and report success, which is the one failure this file exists to
    make impossible.
    """
    path = paths_path(checkout)
    if not path.is_file():
        raise PathsRefused(f"no {path}; requirement 10 says a path names what installs")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as problem:
        raise PathsRefused(f"{path} is not readable JSON: {problem}") from problem
    paths = data.get("paths")
    if not isinstance(paths, dict) or len(paths) != 3:
        found = len(paths) if isinstance(paths, dict) else 0
        raise PathsRefused(f"{path} names {found} paths; criterion 24 wants three")
    return paths


def named_skills(checkout: Path) -> set[str]:
    """Every skill any path names, as one set. A skill may be on two paths."""
    return {
        skill
        for path in read_paths(checkout).values()
        for skill in path.get("skills", [])
    }


def unnamed_directories(checkout: Path) -> list[str]:
    """Directories under `skills/` that no path names. Criterion 24's check.

    The direction matters. This answers "what is on disk that nothing names",
    which is the drift a new skill directory creates; the reverse question,
    "what is named that is not on disk", is answered by `missing_skills`. A
    check that asked only one of them would pass while the other was true.
    """
    root = checkout / "skills"
    if not root.is_dir():
        return []
    named = named_skills(checkout)
    return sorted(
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and entry.name.startswith("sd-") and entry.name not in named
    )


def missing_skills(checkout: Path) -> list[str]:
    """Skills a path names that are not under `skills/` or `contrib/`."""
    root = checkout / "skills"
    contrib = checkout / CONTRIB_DIR
    return sorted(
        name
        for name in named_skills(checkout)
        if not (root / name / SKILL_FILE).is_file()
        and not (contrib / name / SKILL_FILE).is_file()
    )


def discover_surfaces(
    checkout: Path, trials: Iterable[str] | None = None
) -> list[Surface]:
    """The union of what the paths name and what is on trial.

    Requirement 10: a skill installs because a path names it, or because it
    was used. `trials` is the second half -- the skills with an unexpired
    trial row, read from the library by the caller, because this function
    knows about files and the database is not one of its concerns.

    A trial's skill lives in `contrib/`, so both directories are searched and
    `skills/` wins when a name is in both. The order is not arbitrary: a
    promotion moves the directory from `contrib/` to `skills/` and a stale
    trial row for the promoted skill would otherwise keep rendering the copy
    that is no longer the one under review.
    """
    root = checkout / "skills"
    if not root.is_dir():
        return []
    wanted = named_skills(checkout) | set(trials or ())
    shared = shared_references(checkout)
    surfaces: list[Surface] = []
    for name in sorted(wanted):
        entry = root / name
        if not entry.is_dir():
            entry = checkout / CONTRIB_DIR / name
        if not entry.is_dir():
            continue
        skill = entry / SKILL_FILE
        if not skill.is_file():
            continue
        # Everything beside the skill, at the path it already has. Wider than
        # the `templates/*.md` this used to look for, and derived rather than
        # named: a skill that grows a `references/` or a `scripts/` directory
        # ships it without the installer needing to learn the word.
        extras = [
            Extra(str(path.relative_to(entry)), path)
            for path in sorted(entry.rglob("*"))
            if path.is_file() and path != skill
        ]
        local = {extra.relative for extra in extras}
        for cited in sorted(set(CITATION.findall(skill.read_text(encoding="utf-8")))):
            relative = f"references/{cited}"
            if relative in local or cited not in shared:
                continue
            extras.append(Extra(relative, shared[cited]))
        surfaces.append(Surface(entry.name, skill, sorted(extras, key=lambda e: e.relative)))
    return surfaces


def missing_citations(surfaces: list[Surface]) -> list[str]:
    """Citations that resolve to no file, as `<skill>: <path>`.

    A skill telling the model to read `references/x.md` that was never shipped
    is broken in the way nobody notices: the instruction is followed, the read
    fails, and the run continues with whatever the model remembered instead.
    Reported by the installer rather than left to be found in a session.
    """

    problems: list[str] = []
    for surface in surfaces:
        shipped = {extra.relative for extra in surface.extras}
        text = surface.skill.read_text(encoding="utf-8")
        for name in sorted(set(CITATION.findall(text))):
            relative = f"references/{name}"
            if relative not in shipped:
                problems.append(f"{surface.name}: {relative}")
    return problems


def discover_agents(checkout: Path) -> list[Surface]:
    """Enumerate `agents/sd-*.md` from disk, for the same reason skills are.

    Agents reuse `Surface` because they are the narrower case of one: a name and
    a file, with no templates beside them. A second dataclass differing by an
    always-empty field would buy nothing.
    """
    root = checkout / "agents"
    if not root.is_dir():
        return []
    return [
        Surface(path.stem, path)
        for path in sorted(root.glob("sd-*.md"))
        if path.is_file()
    ]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# -------------------------------------------------------------------- receipt


def read_receipt(path: Path) -> dict:
    """Load `installed.json`, or an empty receipt when there is none.

    A receipt that will not parse is treated as absent rather than fatal: the
    installer's job is to converge the machine on the checkout, and refusing to
    run because its own bookkeeping is corrupt would leave no way out but
    deleting the file by hand. What it must never do is *delete* on the basis
    of a receipt it could not read, and it does not -- `owned` comes back empty,
    so uninstall removes nothing it cannot account for.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def owned_entries(receipt: dict) -> list[dict]:
    entries = receipt.get("owned")
    if not isinstance(entries, list):
        return []
    return [item for item in entries if isinstance(item, dict) and "path" in item]


def write_receipt(path: Path, payload: dict) -> None:
    """Write the receipt atomically, so an interrupted run leaves the old one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(path.name + ".tmp")
    scratch.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(scratch, path)


# ---------------------------------------------------------------- git context


def git_context(checkout: Path) -> dict:
    """Commit, branch, and dirtiness of the serving checkout.

    Recorded for diagnosis only -- nothing refuses on it. `--pull` is the
    command that cares whether the checkout is clean and on main, and it checks
    at the moment it matters rather than trusting a field written earlier.
    """
    git = sibling("sd_lib").git_output
    return {
        "commit": git(["rev-parse", "HEAD"], checkout) or "",
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], checkout) or "",
        "dirty": bool(git(["status", "--porcelain"], checkout)),
    }


# --------------------------------------------------------------------- render


@dataclass
class Written:
    path: Path
    sha256: str
    kind: str


def render(
    surfaces: list[Surface],
    homes: list[PlatformHome],
    *,
    kind: str = "skill",
    dry_run: bool = False,
) -> list[Written]:
    """Copy every surface into every platform home, verbatim.

    Verbatim is the whole design. A renderer that rewrote frontmatter per
    platform would be a translation layer with its own bugs and its own drift,
    and the parity test could then only assert that the translation ran, not
    that the platforms agree. Byte-identical files let the test assert the
    strong thing: same digest everywhere.
    """
    written: list[Written] = []
    for home in homes:
        for surface in surfaces:
            body = surface.skill.read_bytes()
            target = home.target_for(surface.name)
            written.append(Written(target, digest(body), f"{kind}:{home.key}"))
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
            if home.layout != "directory":
                # Flat homes have nowhere to put a template beside its skill,
                # and OpenCode's command loader would read one as a command.
                continue
            for extra in surface.extras:
                data = extra.source.read_bytes()
                dest = target.parent / extra.relative
                # `companion`, not `template`: these are a skill's references
                # and scripts as well as its templates now, and a receipt kind
                # that names one of the three reads as a bug in the other two.
                # Kind is metadata -- prune keys on the path -- so an existing
                # receipt rewrites its rows without touching a single file.
                written.append(Written(dest, digest(data), f"companion:{home.key}"))
                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
    return written


# ------------------------------------------------------- the one settings edit


def hook_specs(checkout: Path) -> list[tuple[str, str, tuple[str, ...]]]:
    """`HOOK_SPECS` with each command resolved against this checkout."""
    return [(str(checkout / command), event, matchers)
            for command, event, matchers in HOOK_SPECS]


def install_hook(settings: Path, specs, *, dry_run: bool = False) -> bool:
    """Register every spec in `specs` on its own event and matchers.

    This is the only file outside a platform home the installer ever writes,
    and it is somebody else's file: `~/.claude/settings.json` holds hooks from
    the machine's other installers. So the edit is surgical -- the settings are
    loaded, each command is added under exactly its own matchers, everything
    else is written back untouched -- and it is idempotent, because a second
    `--user` run must not leave a hook registered twice.

    One read and one write for the whole table, not one per spec. Three
    sequential read-modify-writes of a file we do not own is three chances to
    interleave with another installer doing the same.

    Returns True when the file changed.
    """
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except (OSError, ValueError):
        # Refuse rather than overwrite: a settings file that will not parse is
        # a file whose contents we would be destroying, not converging.
        raise SystemExit(
            f"error: {settings} exists but is not readable JSON; "
            "fix or move it, then re-run."
        ) from None
    if not isinstance(data, dict):
        raise SystemExit(f"error: {settings} is not a JSON object.")

    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SystemExit(f"error: {settings} has a non-object 'hooks' key.")

    changed = False
    for command, event, matchers in specs:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise SystemExit(
                f"error: {settings} has a non-list '{event}' hook list."
            )
        for matcher in matchers:
            group = None
            for candidate in groups:
                if isinstance(candidate, dict) and candidate.get("matcher") == matcher:
                    group = candidate
                    break
            if group is None:
                group = {"matcher": matcher, "hooks": []}
                groups.append(group)
                changed = True
            entries = group.setdefault("hooks", [])
            if not isinstance(entries, list):
                raise SystemExit(
                    f"error: {settings} {event}/{matcher} has a non-list 'hooks'."
                )
            if any(
                isinstance(entry, dict) and entry.get("command") == command
                for entry in entries
            ):
                continue
            entries.append({"type": "command", "command": command})
            changed = True

    if changed and not dry_run:
        settings.parent.mkdir(parents=True, exist_ok=True)
        scratch = settings.with_name(settings.name + ".sd-tmp")
        scratch.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(scratch, settings)
    return changed


def remove_hook(settings: Path, commands, *, dry_run: bool = False) -> bool:
    """Drop our hook entries, and any matcher group we thereby emptied.

    `commands` comes off the receipt, so an uninstall run by a newer pack
    against an older receipt removes exactly what that older run registered
    and leaves alone what it never wrote.

    Only entries whose command is one of ours are removed; another installer's
    hook under the same matcher survives, which is why a group is deleted only
    when it ends up empty.
    """
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False

    wanted = set(commands)
    ours = {
        (event, matcher)
        for command, event, matchers in HOOK_SPECS
        for matcher in matchers
        if any(held.endswith(command) for held in wanted)
    }

    changed = False
    for event in {event for event, _ in ours}:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        surviving = []
        for group in groups:
            if not isinstance(group, dict) or (event, group.get("matcher")) not in ours:
                surviving.append(group)
                continue
            entries = group.get("hooks")
            if not isinstance(entries, list):
                surviving.append(group)
                continue
            kept = [
                entry
                for entry in entries
                if not (isinstance(entry, dict) and entry.get("command") in wanted)
            ]
            if len(kept) != len(entries):
                changed = True
            if kept:
                group["hooks"] = kept
                surviving.append(group)
            elif not entries:
                surviving.append(group)
        if surviving:
            hooks[event] = surviving
        else:
            # Leaving `"SessionStart": []` behind would be residue of exactly
            # the kind uninstall exists to remove: an empty key in someone
            # else's file that only we ever put there.
            hooks.pop(event, None)
    if not changed:
        return False
    if not hooks:
        data.pop("hooks", None)
    if not dry_run:
        scratch = settings.with_name(settings.name + ".sd-tmp")
        scratch.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(scratch, settings)
    return True


# ------------------------------------------------------------ global excludes


def configured_excludes() -> str | None:
    """`core.excludesFile` from the global config; `None` when git cannot answer.

    `""` says nothing is set, and invites writing the config -- `--get` exits 1
    on an unset key, so a non-zero exit is that answer, not a failure. `None`
    says a machine with no usable git, whose global config we may not guess at.
    """
    try:
        done = subprocess.run(  # nosec B603 - fixed argv, no shell
            ["git", "config", "--global", "--get", "core.excludesFile"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else ""


def excludes_file(
    home: Path, environ: dict[str, str], *, sandboxed: bool = False
) -> Path:
    """Where git keeps the user's global excludes, honouring what is set.

    If `core.excludesFile` is already configured we use it, because writing our
    line into a different file would leave it configured and ignored. Only when
    nothing is configured do we fall back to git's own default location, and
    only then do we set the config.

    `sandboxed` is what makes `--home` mean what it says. Git's global config
    is per-user, not per-`$HOME`-argument, so consulting it under a scratch
    install would resolve to the real `~/.gitignore_global` and append a line
    to the machine's actual excludes -- an install told to stay in a temporary
    directory reaching outside it. Under a sandbox the lookup is skipped
    entirely and the path is derived from the given home.
    """
    if sandboxed:
        return config_home(home, environ) / "git" / "ignore"
    configured = configured_excludes()
    if configured:
        return Path(os.path.expanduser(configured))
    return config_home(home, environ) / "git" / "ignore"


def ensure_excludes_line(path: Path, *, dry_run: bool = False) -> bool:
    """Ensure exactly one `CLAUDE.local.md` line in the global excludes.

    One line, appended, never rewritten: this file is the user's, and every
    other line in it belongs to them. Returns True when the file changed.
    """
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError:
        existing = ""
    if any(line.strip() == EXCLUDES_LINE for line in existing.splitlines()):
        return False
    if dry_run:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{prefix}{EXCLUDES_LINE}\n")
    return True


def set_excludes_config(
    path: Path, *, dry_run: bool = False, sandboxed: bool = False
) -> None:
    """Point `core.excludesFile` at `path` when nothing points anywhere yet.

    Never under a sandbox: the config it would write is the real user's, and a
    scratch install has no business naming a temporary directory as the
    machine's global excludes file.
    """
    if sandboxed:
        return
    if configured_excludes() != "":  # `None` is git unavailable, not "unset"
        return
    if dry_run:
        return
    subprocess.run(  # nosec B603 - fixed argv, no shell
        ["git", "config", "--global", "core.excludesFile", str(path)],
        capture_output=True,
        check=False,
    )


# ------------------------------------------------------------------ reconcile


def prune_stale(
    previous: list[dict], current: set[str], *, dry_run: bool = False
) -> list[tuple[str, str]]:
    """Delete renders this checkout no longer produces.

    This is what makes a renamed or retired surface actually disappear instead
    of lingering as an installed command that no longer exists in the payload.
    The receipt is the authority: a path is removed only if a previous run
    recorded writing it, and only if its digest still matches what was written,
    so a file edited by hand survives and is reported rather than deleted.

    Returns `(path, reason)` for everything skipped, so the caller can say what
    it left behind rather than leave the user to discover it.
    """
    skipped: list[tuple[str, str]] = []
    for entry in previous:
        raw = entry.get("path")
        if not isinstance(raw, str) or raw in current:
            continue
        if entry.get("kind") == "hook":
            continue
        target = Path(raw)
        if not target.exists():
            continue
        recorded = entry.get("sha256")
        try:
            actual = digest(target.read_bytes())
        except OSError as exc:
            skipped.append((raw, f"unreadable ({exc.strerror or exc})"))
            continue
        if recorded != actual:
            skipped.append((raw, "modified since it was installed"))
            continue
        if not dry_run:
            try:
                target.unlink()
            except OSError as exc:
                skipped.append((raw, f"could not remove ({exc.strerror or exc})"))
                continue
            prune_empty_dirs(target.parent)
    return skipped


def prune_empty_dirs(start: Path) -> None:
    """Walk up removing directories we emptied, stopping at the first that is not.

    Bounded by `rmdir` refusing a non-empty directory: the loop cannot escape
    into a populated tree, because the first directory holding anything else
    ends it.
    """
    current = start
    for _ in range(3):
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


# ------------------------------------------------------------- legacy receipt

LEGACY_RECEIPT = ("machine", "machine-receipt.json")
LEGACY_FAMILY_ROOTS = {
    "agents-skills": (".agents", "skills"),
    "agents-bin": (".agents", "bin"),
    "agents-docs": (".agents", "docs"),
    "gemini-commands": (".gemini", "commands"),
}


def legacy_receipt_path(home: Path, environ: dict[str, str]) -> Path:
    """Where the old fleet installer left its receipt."""
    return state_home(home, environ) / STATE_DIR / Path(*LEGACY_RECEIPT)


def legacy_targets(home: Path, environ: dict[str, str]) -> list[tuple[Path, str]]:
    """Enumerate what the old fleet installer wrote, from its own receipt.

    Enumeration comes from the receipt rather than from a list written here,
    for the reason the whole rebuild exists: a list would be a second copy of
    the truth, and the copy is what goes stale. Entries whose family we no
    longer recognise are skipped rather than guessed at.

    Returns `(path, sha256)` pairs; the digest is what lets `--adopt-legacy`
    refuse to delete a file somebody has since edited.
    """
    data = read_receipt(legacy_receipt_path(home, environ))
    rows = data.get("files")
    if not isinstance(rows, list):
        return []
    config_root = config_home(home, environ)
    roots = {
        family: home.joinpath(*parts)
        for family, parts in LEGACY_FAMILY_ROOTS.items()
    }
    roots["opencode-commands"] = config_root / "opencode" / "commands"

    found: list[tuple[Path, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        family = row.get("family")
        root = roots.get(family) if isinstance(family, str) else None
        relative = row.get("path")
        if root is None or not isinstance(relative, str) or not relative:
            continue
        recorded = row.get("digest", "")
        if isinstance(recorded, str) and recorded.startswith("sha256:"):
            recorded = recorded[len("sha256:") :]
        found.append((root / relative, recorded if isinstance(recorded, str) else ""))
    return found


# ------------------------------------------------------- the per-repo block

LOCAL_BLOCK_FILE = "CLAUDE.local.md"

# Taken from the reader, not retyped beside it. The installer kept its own
# lower-case pair, so `parse_local_block` found no start marker and returned
# `{}` for every block this file has ever written -- `mode`, `check`, `test`,
# `lint`, and now `reviewers`, which is consent, all unread. It stayed
# invisible because `mode`'s fallback is the value it failed to read, and
# because the reader's own tests hand-write the reader's markers rather than
# producing a block with the installer. Two hand-maintained copies of one
# format is the whole cause, so there is now one copy and `sd_lib` holds it.
BLOCK_BEGIN = sibling("sd_lib").LOCAL_BLOCK_START
BLOCK_END = sibling("sd_lib").LOCAL_BLOCK_END

#: What this installer wrote until 2026-09-06, and what a repository set up
#: before then still carries.
LEGACY_BLOCK_MARKERS = (
    ("<!-- sd-ai-command-pack:begin -->", BLOCK_BEGIN),
    ("<!-- sd-ai-command-pack:end -->", BLOCK_END),
)

# Commented, because the body is the reader's grammar and not prose with keys
# in it: `parse_scalars` refuses a line that is neither blank, a comment, nor
# `key: value`. Unmarked, these three lines raised `ConfigError` on every read
# -- a second way the same block was unreadable, and one the marker fix alone
# would have left standing.
DEFAULT_BLOCK_BODY = """\
# sd-ai-command-pack, machine-scope. Work items live under `docs/work/`; nothing
# else in this repo belongs to the framework. The workflow these keys override
# is `WORKFLOW.md` in the pack checkout; the one page that states the policy.

    mode: full
    check: <the command that verifies this repo, e.g. `make check`>
    test: <optional, when this repo spells its tests separately>
    lint: <optional, same>
    reviewers: <registry entries allowed to receive this repo's diff>
"""


def migrated(text: str) -> str:
    """`text` with an unreadable block's markers rewritten to the reader's.

    In place, and not beside it. Switching the pair without this would find no
    block, append a second one, and leave the operator's answers -- the
    `reviewers` line among them -- in the copy nothing reads. Nothing else can
    do this instead: `--adopt-legacy` enumerates the old fleet installer's
    renders from its own receipt, and no receipt anywhere lists the
    repositories that have a block, so the only moment a repository's markers
    can be corrected is the next `--repo` run inside it.
    """
    for old, new in LEGACY_BLOCK_MARKERS:
        text = text.replace(old, new)
    return text


def write_local_block(
    repo: Path, *, dry_run: bool = False, consent: str | None = None
) -> str:
    """Create or refresh the marked block in the repo's `CLAUDE.local.md`.

    The file is untracked by construction -- `CLAUDE.local.md` is the one line
    the installer puts in the global excludes -- so this is not an exception to
    "never edits a tracked repo file". If it somehow *is* tracked here, that is
    a repo that has committed its local config, and we refuse rather than
    quietly change a file under version control.

    Everything outside the markers is the user's and is preserved byte for
    byte; only a pre-existing block of ours is replaced.
    """
    target = repo / LOCAL_BLOCK_FILE
    if path_is_tracked(repo, LOCAL_BLOCK_FILE):
        raise SystemExit(
            f"error: {LOCAL_BLOCK_FILE} is tracked in {repo}; refusing to edit a "
            "tracked file. Untrack it (git rm --cached) and re-run."
        )
    try:
        original = target.read_text(encoding="utf-8")
    except OSError:
        original = ""
    existing = migrated(original)
    block = f"{BLOCK_BEGIN}\n{consent_body(consent)}{BLOCK_END}\n"
    start = existing.find(BLOCK_BEGIN)
    end = existing.find(BLOCK_END)
    if start != -1 and end > start:
        updated = existing[:start] + block + existing[end + len(BLOCK_END) + 1 :]
        action = "refreshed"
    elif start != -1 or end != -1:
        raise SystemExit(
            f"error: {target} has a half-open sd-ai-command-pack block; "
            "fix the markers by hand, then re-run."
        )
    else:
        separator = "" if not existing or existing.endswith("\n\n") else "\n"
        updated = f"{existing}{separator}{block}"
        action = "added"
    # Against `original`, not against the migrated copy: a file whose only
    # change is the marker pair is byte-identical to `existing` and would not
    # be written, leaving the repository on the markers nothing reads.
    if not dry_run and updated != original:
        target.write_text(updated, encoding="utf-8")
    return action


def path_is_tracked(repo: Path, relative: str) -> bool:
    try:
        done = subprocess.run(  # nosec B603 - fixed argv, no shell
            ["git", "-C", str(repo), "ls-files", "--error-unmatch", "--", relative],
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return done.returncode == 0


# ----------------------------------------------------------------- consent

# Local answers restrict standing machine authorization. Render every pair
# through the canonical parser; malformed or unknown answers must not inherit.
CONSENT_KEY = "reviewers"
CONSENT_LINE = re.compile(rf"^[ \t]*{CONSENT_KEY}:(?P<value>.*)\n?", re.MULTILINE)


def consent_body(consent: str | None) -> str:
    """Quote an answer using the reader's grammar; None inherits, empty denies.

    Quoting preserves # and backslashes in recipients. Callable replacement
    prevents re.sub from treating recipient backslashes as group references.
    """
    if consent is None:
        return CONSENT_LINE.sub(lambda _: "", DEFAULT_BLOCK_BODY)
    quoted = consent.replace("\\", "\\\\").replace('"', '\\"')
    return CONSENT_LINE.sub(lambda _: f'    {CONSENT_KEY}: "{quoted}"\n', DEFAULT_BLOCK_BODY)


def standing_consent(repo: Path) -> str | None:
    """Read local consent through its canonical grammar, preserving empty denial."""
    lib = sibling("sd_lib")
    try:
        text = migrated((repo / LOCAL_BLOCK_FILE).read_text(encoding="utf-8"))
        value = lib.parse_local_block(text).get(CONSENT_KEY)
    except FileNotFoundError:
        if (repo / LOCAL_BLOCK_FILE).is_symlink():
            raise lib.ConfigError("cannot read dangling local configuration link") from None
        return None
    return None if value == lib.parse_scalars(DEFAULT_BLOCK_BODY, comments=True).get(CONSENT_KEY) else value


def consent_offers(ctx: Context) -> list:
    """Every enabled reviewer entry beside the recipient it reaches today."""
    sd_registry = sibling("sd_registry")
    found, _ = sd_registry.read_or_report(sd_registry.registry_path(ctx.home))
    return [sd_registry.recipient(entry) for entry in found.order("reviewer")]


def reads_back(line: str, chosen: list) -> bool:
    """Whether the block this line goes into reads back as exactly `chosen`.

    The whole chain, run before anything is written: the body the block will
    carry, through `sd_lib`, through `parse_consent`. Composed by the writer,
    checked by the reader.

    The defect that first justified this guard is now fixed at its source:
    `Allowance.__str__` quoted through `shlex.quote`, whose safe set *includes*
    the comma `consent_parts` splits on, so an executable holding one rendered
    bare and came back as two pairs -- `entry@x,y@z` read as `entry -> x`, a
    host nobody named, beside a fabricated `y -> z`. `sd_registry._one_word`
    now quotes on that module's own rule and the comma round-trips.

    The guard stays, because quoting cannot separate every shape. A recipient
    ending in `+` and exactly `FINGERPRINT_LENGTH` hex characters is spelled
    identically to recipient-plus-fingerprint, and the split happens after the
    quotes are gone: `host.example+abcdef12` reads back as the bare
    `host.example`. Only a `url` entry reaches it, a `start` entry having a
    real fingerprint appended after. Refusing to be the thing that writes such
    a line is still this function's job, whether the read comes back different
    or does not come back at all.
    """
    try:
        block = sibling("sd_lib").parse_local_block(
            f"{BLOCK_BEGIN}\n{consent_body(line)}{BLOCK_END}"
        )
        found = sibling("sd_registry").parse_consent(block.get(CONSENT_KEY))
        return found == {pair.entry: pair for pair in chosen}
    except Exception:
        return False


def chosen_consent(offers: list, answer: str, out) -> str | None:
    """The line allowing the offered entries `answer` names, or None.

    Names only, in the prompt and in `--reviewers` alike: a recipient comes
    off the registry and never off a keyboard, so what lands parses back as
    the pair that was offered. A name nobody offered is refused whole rather
    than guessed at, because the guess would be at where the diff may go.
    """
    wanted = set(re.split(r"[\s,]+", answer.strip())) - {""}
    unknown = sorted(wanted - {pair.entry for pair in offers})
    if unknown:
        print(f"no {CONSENT_KEY} line written: this registry offers no entry named "
              f"{', '.join(unknown)}, and half an answer consents to nothing", file=out)
        return None
    if not wanted:
        print(f"no {CONSENT_KEY} line written: this repository consents to nobody",
              file=out)
        return None
    chosen = [pair for pair in offers if pair.entry in wanted]
    line = ", ".join(str(pair) for pair in chosen)
    if not reads_back(line, chosen):
        print(f"no {CONSENT_KEY} line written: {line!r} does not read back as the "
              f"entries it was built from, so it consents to nobody it names", file=out)
        return None
    return line


def repo_consent(ctx: Context, repo: Path, answer: str | None, out) -> str | None:
    """Keep local restrictions; otherwise inherit explicit user policy or ask once."""
    standing = standing_consent(repo)
    if standing is not None:
        sibling("sd_registry").parse_consent(standing)
        print(f"{CONSENT_KEY} already answered here, kept as it stands", file=out)
        return standing
    if answer is not None and not answer.strip():
        print("this repository consents to nobody; explicit empty denial written", file=out)
        return ""
    env = dict(ctx.environ, HOME=str(ctx.home), XDG_CONFIG_HOME=str(config_home(ctx.home, ctx.environ)))
    if answer is None and sibling("sd_lib").core_setting("external_reviews", env) is not None:
        print("repository inherits the operator's external review policy", file=out)
        return None
    offers = consent_offers(ctx)
    if not offers:
        print(f"no enabled reviewer entry to offer; no {CONSENT_KEY} line", file=out)
        if answer is not None:
            raise sibling("sd_lib").ConfigError("no offered reviewer matches; local block left unchanged")
        return None
    if answer is None:
        print("which of these may receive this repository's diff?", file=out)
        for pair in offers:
            print(f"  {pair}", file=out)
        print("names, space- or comma-separated; empty for none:", file=out)
        if not sys.stdin.isatty():
            print("no answer supplied; this repository consents to nobody", file=out)
            return None
        answer = sys.stdin.readline()
    chosen = chosen_consent(offers, answer, out)
    if chosen is None and answer.strip():
        raise sibling("sd_lib").ConfigError("invalid reviewer answer; local block left unchanged")
    return chosen if chosen is not None else ""


# ------------------------------------------------------------- the library

# The provider registry. `bin/sd_registry.py` reads it and states the same two
# constants; they are restated here rather than imported for the reason
# `state_home` is -- the installer is loaded by path and must run on a machine
# where nothing else in `bin/` is importable yet, and importing a sibling would
# make one of the things it installs a dependency of the installer.
# `tests/test_sd_install.py` asserts the two agree, which is what a restatement
# owes.
REGISTRY_NAME = "providers.yaml"
REGISTRY_RELATIVE = Path(".local/share/sd") / REGISTRY_NAME


def seed_registry(ctx: Context) -> tuple[bool, str]:
    """Put the checkout's registry in the home, once and never again.

    The file is identity: pins, bills, and the reason an entry ships disabled.
    It is edited by hand and read by both `sd_db` and the pack, so a reinstall
    that refreshed it would silently roll back a pin the operator changed this
    morning. Copied when absent, left alone when present, and the report says
    which -- an install that quietly did nothing is the same output as one that
    quietly overwrote.
    """
    source = ctx.checkout / REGISTRY_NAME
    target = ctx.home / REGISTRY_RELATIVE
    if target.exists():
        return False, f"provider registry already at {target}, left as it is"
    if not source.is_file():
        return False, f"no provider registry at {source}; no reviewer resolves"
    if ctx.dry_run:
        return True, f"would seed the provider registry at {target}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return True, f"provider registry seeded at {target}"


# One installer, one place that knows the path. Item B's settled open question
# 3 puts `sd_db` into this pack's virtualenv from the system checkout, as a
# built copy and never editable, so that a branch switch in that checkout
# cannot change what this pack imports. This is that place; nothing else in
# the pack may name the path.
SYSTEM_CHECKOUT_ENV = "SD_SYSTEM_CHECKOUT"
SYSTEM_CHECKOUT_DEFAULT = "~/repos/system"
LIBRARY_RELATIVE = Path("local-sd-db")
#: Tags that name a release *of the library*, not of some other project
#: sharing the monorepo. The pin uses one only when it matches this.
LIBRARY_TAGS = "sd-db-v*"
VENV_RELATIVE = Path(".venv") / "bin" / "python"


def system_checkout(environ: dict[str, str]) -> Path:
    """Where the library's source lives. Read from the environment, expanded.

    Expanded whether it came from the environment or the default: a quoted
    `SD_SYSTEM_CHECKOUT="~/repos/system"` arrives with the tilde intact, and
    an unexpanded one names a directory that does not exist, which would be
    reported as "the library is not installable here" rather than as a bad
    setting.
    """
    return Path(os.path.expanduser(environ.get(SYSTEM_CHECKOUT_ENV) or SYSTEM_CHECKOUT_DEFAULT))


def library_source(environ: dict[str, str]) -> Path:
    return system_checkout(environ) / LIBRARY_RELATIVE


def library_pin(checkout: Path) -> tuple[str, str]:
    """The immutable ref to install `sd_db` from, or a reason there is none.

    A path install takes the *working tree*, so two machines standing on the
    same commit with different uncommitted edits install different libraries
    and call them one version. The ref is what makes the copy reproducible.

    An `sd-db-v*` tag when the checkout stands on one, else the commit.
    Matched by pattern and not by "any tag here", because `system` is a
    monorepo: a bare `--exact-match` would return a tag cut for
    `local-ha-mcp` and record it as the version of `sd_db`, which names a
    release that is not about the thing installed. There are no tags at all
    today, and a rule that refuses without one makes `sd_db` uninstallable
    on the only machine that has it. Both refs are immutable, which is the
    property requirement 13 is about; the tag is only the nicer name, and
    cutting a first `sd-db-v0.1` starts working with no change here.

    Uncommitted work is *not* installed, and the caller says so rather than
    refusing, because refusing would strand an operator mid-edit.
    """
    git = sibling("sd_lib").git_output
    ref = git(
        ["describe", "--tags", "--exact-match", "--match", LIBRARY_TAGS], checkout
    ) or git(["rev-parse", "HEAD"], checkout)
    if not ref:
        return "", f"{checkout} is not a git checkout, so there is nothing to pin to"
    return ref, ""


def provision_library(ctx: Context, out) -> tuple[bool, str]:
    """Install `sd_db` into this pack's virtualenv, as a copy.

    Returns whether it worked and a one-line report, rather than raising. A
    machine with no system checkout still gets its skills: the paths render
    without the library, and only the trials are unavailable, which the caller
    says out loud. Refusing the whole install because a second repository is
    absent would make the pack undeployable anywhere the operator has not
    cloned everything.

    The flag is separate from the line because the line is prose and prose is
    not a status. The caller read one for a while -- `"installed" in report`
    -- and `"sd_db not installed, trials unavailable"` contains it, so the one
    machine the exit code exists for, the one with no library, exited zero.
    """
    del out
    python = ctx.checkout / VENV_RELATIVE
    source = library_source(ctx.environ)
    if not python.is_file():
        return False, f"no virtualenv at {python}; run `make setup` for sd_db"
    if not (source / "pyproject.toml").is_file():
        return False, f"no library at {source}; sd_db is absent, trials unavailable"
    checkout = system_checkout(ctx.environ)
    ref, why = library_pin(checkout)
    if not ref:
        return False, f"sd_db not installed, trials unavailable: {why}"
    refusal = sibling("sd_library_guard").downgrade_refusal(
        ctx.checkout, checkout, ref, sibling("sd_lib").git_output)
    if refusal:
        return False, refusal
    target = f"git+file://{checkout}@{ref}#subdirectory={LIBRARY_RELATIVE}"
    dirty = " (uncommitted work in that checkout is not installed)" if sibling(
        "sd_lib"
    ).git_output(["status", "--porcelain"], checkout) else ""
    if ctx.dry_run:
        return True, f"would install sd_db from {source} at {ref}{dirty}"
    try:
        done = subprocess.run(  # nosec B603 - fixed argv, no shell
            [str(python), "-m", "pip", "install", "--quiet", "--upgrade", "--force-reinstall", target],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as problem:
        return False, f"sd_db install failed: {problem}"
    if done.returncode != 0:
        last = done.stderr.strip().splitlines()[-1:] or ["no output"]
        return False, f"sd_db install failed: {last[0]}"
    return True, f"sd_db installed from {source} at {ref}{dirty}"


def open_library(ctx: Context):
    """The pack's connection to the one database, or None with a reason.

    Imported here rather than at module scope. The installer is the thing that
    provisions `sd_db`, so it has to run on a machine where the import fails,
    and a top-level import would make the installer unable to fix the problem
    it exists to fix.
    """
    try:
        import sd_db  # noqa: PLC0415 - see the docstring
    except ImportError as problem:
        return None, f"sd_db not importable ({problem}); trials unavailable"
    path = sd_db.default_path(ctx.home)
    if not path.exists():
        return None, f"no database at {path}; run `sd-db.sh init` for trials"
    try:
        return sd_db.connect(path), ""
    except Exception as problem:  # pragma: no cover - a corrupt file
        return None, f"sd_db could not open {path}: {problem}"


def expire_trials(connection, out) -> list[str]:
    """Remove every expired trial that earned no use, and say which.

    Criterion 25's second half. The window is the trial's own `started`, not
    all of history: a use from before the trial began is not evidence the
    trial earned anything, and counting it would keep a skill installed on the
    strength of the very usage that made somebody trial it in the first place.
    """
    import sd_db  # noqa: PLC0415 - only reached when the import already worked

    removed: list[str] = []
    now = sd_db.writes.now()
    for row in sd_db.trials(connection):
        if row["expires"] > now:
            continue
        if sd_db.skill_use_since(connection, row["skill"], row["started"]):
            continue
        sd_db.end_trial(connection, row["skill"])
        removed.append(row["skill"])
        print(
            f"removed {row['skill']}: trial expired {row['expires'][:10]} with no use",
            file=out,
        )
    return removed


# ------------------------------------------------------------------- commands


@dataclass
class Context:
    checkout: Path
    home: Path
    environ: dict[str, str]
    dry_run: bool = False

    @property
    def sandboxed(self) -> bool:
        """True whenever this run targets somewhere other than the real home.

        Derived rather than passed, because the one thing that can escape a
        scratch install is git's global config: it is per-user, not
        per-`$HOME`-argument, so an unsandboxed lookup finds the real
        `~/.gitignore_global` no matter which home the renders are going to.
        Deriving it from the home itself means a Context built anywhere -- the
        CLI, a test, a future caller -- cannot get this wrong by forgetting a
        flag. An earlier version took it as a field and a test promptly built a
        Context without it, appending a line to the developer's actual global
        excludes.
        """
        return sandboxed(self.home)

    @property
    def homes(self) -> list[PlatformHome]:
        return platform_homes(self.home, self.environ)

    @property
    def agents(self) -> list[PlatformHome]:
        return agent_homes(self.home)

    @property
    def receipt(self) -> Path:
        return receipt_path(self.home, self.environ)

    @property
    def settings(self) -> Path:
        return self.home / ".claude" / "settings.json"


def cmd_user(ctx: Context, out) -> int:
    """Render what the paths name plus what is on trial, and converge.

    This reads the library; it does not install it. Provisioning is
    `--provision-library`, which `make setup` runs, and the two are separate
    on purpose: an ordinary skill install must not rebuild the virtualenv it
    is running from. Made them one call first, and the suite found why -- the
    render happens in every fixture and in parallel, so a `pip install` here
    replaced `sd_db` in site-packages underneath whichever other shard was
    importing it, which fails as `No module named 'sd_db.testing.home'` in a
    test that has nothing to do with either. A machine with no library is
    told so and gets its skills; `make setup` is the remedy, and the path to
    the source is still spelled in this file only.
    """
    connection, reason = open_library(ctx)
    if reason:
        print(f"warning: {reason}", file=out)
    trials: list[str] = []
    if connection is not None:
        expire_trials(connection, out)
        import sd_db  # noqa: PLC0415 - only reached when the import worked

        trials = [row["skill"] for row in sd_db.active_trials(connection)]

    try:
        surfaces = discover_surfaces(ctx.checkout, trials)
        unnamed = unnamed_directories(ctx.checkout)
        absent = missing_skills(ctx.checkout)
    except PathsRefused as problem:
        # One boundary for all three, because they read the same file. Catching
        # each separately would report the same missing file three times, and a
        # checkout with no `skills/` at all reaches the surfaces refusal below
        # without ever needing the paths.
        if (ctx.checkout / "skills").is_dir():
            print(f"error: {problem}", file=out)
            return 1
        surfaces, unnamed, absent = [], [], []
    if unnamed:
        # Refused, not warned. A directory under `skills/` that no path names
        # is a skill somebody added without deciding it belongs on a path, and
        # rendering the rest would install a set nobody chose while reporting
        # success. Criterion 24 asserts this failure from `make check`.
        print(
            "error: under skills/ and on no path: "
            + ", ".join(unnamed)
            + f" -- add each to {PATHS_FILE} or move it to {CONTRIB_DIR}/",
            file=out,
        )
        return 1
    if absent:
        print(
            f"error: {PATHS_FILE} names skills that are in neither skills/ nor "
            f"{CONTRIB_DIR}/: " + ", ".join(absent),
            file=out,
        )
        return 1
    if not surfaces:
        print(
            f"error: no skills/sd-*/{SKILL_FILE} under {ctx.checkout}; "
            "is this the pack checkout?",
            file=out,
        )
        return 1

    # Reported, not fatal, on the same reasoning `sd-dashboard` uses for a
    # tracker it cannot reach: every other skill on the paths installs
    # correctly, and refusing all of them because one cites a file nobody
    # shipped would make the installer withhold what it can still do. CI keeps
    # it at zero -- `tests/test_sd_install.py` fails on any citation this
    # cannot resolve -- so the warning is for a checkout in the middle of an
    # edit, not a licence.
    #
    # `uncited` and not `problem`: the paths refusal above binds `problem` in
    # an `except` clause, and Python unbinds it at the end of that clause, so
    # reusing the name here is a read of a deleted variable on every path that
    # took the refusal.
    for uncited in missing_citations(surfaces):
        print(f"warning: {uncited} is cited but not shipped", file=out)

    agents = discover_agents(ctx.checkout)
    written = render(surfaces, ctx.homes, dry_run=ctx.dry_run)
    # Rendered after the skills and into their own homes, so a machine with no
    # `agents/` in its checkout converges exactly as before rather than failing
    # on an absent directory.
    written += render(agents, ctx.agents, kind="agent", dry_run=ctx.dry_run)
    current = {str(item.path) for item in written}

    previous = owned_entries(read_receipt(ctx.receipt))
    skipped = prune_stale(previous, current, dry_run=ctx.dry_run)

    specs = hook_specs(ctx.checkout)
    hook_changed = install_hook(ctx.settings, specs, dry_run=ctx.dry_run)

    excludes = excludes_file(ctx.home, ctx.environ, sandboxed=ctx.sandboxed)
    excludes_changed = ensure_excludes_line(excludes, dry_run=ctx.dry_run)
    set_excludes_config(excludes, dry_run=ctx.dry_run, sandboxed=ctx.sandboxed)

    # Seeded here rather than at `--provision-library`, because the registry is
    # what a machine with no library still needs: the file-only reader answers
    # from it, and `sd-db.sh init` seeds its rows from it when the library does
    # arrive. Not recorded in `owned`: the installer removes what it owns on
    # uninstall, and this file is the operator's the moment it lands.
    seeded_registry, registry_report = seed_registry(ctx)

    owned = [
        {"path": str(item.path), "sha256": item.sha256, "kind": item.kind}
        for item in written
    ]
    # One receipt entry per command and not per spec: two events share
    # `bin/sd-skill-use`, and an uninstall that saw it twice would report a
    # file count one higher than the number of files it touched.
    for command in sorted({command for command, _, _ in specs}):
        owned.append(
            {"path": str(ctx.settings), "kind": "hook", "command": command})
    # Sorted, so the receipt is canonical rather than merely repeatable. Render
    # order is platform-major and stable today, which makes two runs agree by
    # accident; reordering `platform_homes` or nesting the render loop the other
    # way would churn every row without changing a single installed file, and a
    # diff that noisy is a diff nobody reads.
    owned.sort(key=lambda row: (row["path"], row.get("kind", "")))
    payload = {
        "schema": RECEIPT_SCHEMA,
        "checkout": str(ctx.checkout),
        **git_context(ctx.checkout),
        "platformHomes": {home.key: str(home.root) for home in ctx.homes},
        "owned": owned,
    }
    if not ctx.dry_run:
        write_receipt(ctx.receipt, payload)

    prefix = "would render" if ctx.dry_run else "rendered"
    print(
        f"{prefix} {len(surfaces)} surfaces to {len(ctx.homes)} platforms "
        f"({len(written)} files)",
        file=out,
    )
    for home in ctx.homes:
        print(f"  {home.key}: {home.root}", file=out)
    if agents:
        print(f"{prefix} {len(agents)} agents", file=out)
        for home in ctx.agents:
            print(f"  {home.key}: {home.root}", file=out)
    if hook_changed:
        events = sorted({event for _, event, _ in specs})
        print(f"  hooks registered: {', '.join(events)}", file=out)
    if excludes_changed:
        print(f"  global excludes: {EXCLUDES_LINE} -> {excludes}", file=out)
    # Printed whichever way it went. `seed_registry` says its report "says
    # which -- an install that quietly did nothing is the same output as one
    # that quietly overwrote", and printing only the seeding case made the
    # sentence false for the two outcomes it was written for. The one that
    # cost most was the missing source: no registry, no reviewer resolves, and
    # nothing on screen to say so.
    print(f"  {registry_report}", file=out)
    for path, reason in skipped:
        print(f"  left in place ({reason}): {path}", file=out)
    return 0


def command_report(checkout: Path, environ: dict[str, str]) -> str:
    """One line on how this checkout's commands, `bin/sd` and `bin/sd-*`, are reached.

    The installer renders surfaces -- skills, agents, companions, hooks -- and
    links no executable anywhere. A receipt is therefore not evidence that
    `sd-handoff` resolves, and it never was: `bin/` is invoked by path, the way
    the two installed hooks invoke it. Leaving that to be inferred from an
    absence reads as a partial install, and has been read that way.

    Enumerated at runtime from `bin/` (its extensionless executables; the
    `sd_*.py` beside them are modules) and from `PATH`, never from a list here.
    """
    binaries = sorted(
        entry.name
        for entry in (checkout / "bin").glob("sd*")
        if entry.suffix == "" and entry.is_file() and os.access(entry, os.X_OK)
    )
    if not binaries:
        return "commands: none in bin/"

    own = (checkout / "bin").resolve()
    entries = [Path(part) for part in environ.get("PATH", "").split(os.pathsep) if part]
    on_path = any(_resolves_to(entry, own) for entry in entries)

    # A command that resolves somewhere else is worse than one that does not
    # resolve at all: it runs, and it runs another checkout's code.
    #
    # Resolve the executable, not the directory holding it. A hand-made symlink
    # in some other `bin` pointing back into this checkout is this checkout's
    # command reached by another name, not a competing install -- and its
    # parent directory resolves to that other `bin`, so testing the directory
    # calls it a shadow when it is not.
    elsewhere = sorted(
        name
        for name in binaries
        if (found := shutil.which(name, path=environ.get("PATH", "")))
        and not _resolves_to(Path(found), own / name)
    )

    if on_path:
        report = f"commands: {len(binaries)} in bin/, on PATH from this checkout"
    else:
        report = (
            f"commands: {len(binaries)} in bin/, not on PATH -- "
            f"invoke by path (bin/{binaries[0]})"
        )
    if elsewhere:
        report += f"  [{len(elsewhere)} shadowed by another install: {elsewhere[0]}]"
    return report


def _resolves_to(candidate: Path, target: Path) -> bool:
    """Same path once symlinks on both sides are followed, as far as they go."""
    return candidate.resolve() == target.resolve()


def cmd_status(ctx: Context, out) -> int:
    """Report what is installed, what drifted, and what legacy residue remains."""
    receipt = read_receipt(ctx.receipt)
    if not receipt:
        print(f"not installed (no receipt at {ctx.receipt})", file=out)
    else:
        print(f"checkout: {receipt.get('checkout', '?')}", file=out)
        live = git_context(ctx.checkout)
        recorded_commit = receipt.get("commit", "")
        print(
            f"commit:   {recorded_commit or '?'}"
            + ("" if recorded_commit == live["commit"] else f"  (now {live['commit']})"),
            file=out,
        )
        if live["dirty"]:
            print("checkout is dirty", file=out)

    surfaces = discover_surfaces(ctx.checkout)
    expected = {
        str(item.path): item.sha256
        for item in render(surfaces, ctx.homes, dry_run=True)
    }
    missing = 0
    drifted = 0
    for path, sha in expected.items():
        target = Path(path)
        if not target.exists():
            missing += 1
        elif digest(target.read_bytes()) != sha:
            drifted += 1
    print(
        f"surfaces: {len(surfaces)} in checkout, {len(expected)} rendered files, "
        f"{missing} missing, {drifted} modified",
        file=out,
    )
    print(command_report(ctx.checkout, ctx.environ), file=out)

    legacy = [
        path
        for path, _ in legacy_targets(ctx.home, ctx.environ)
        if path.exists() and str(path) not in expected
    ]
    if legacy:
        print(
            f"legacy: {len(legacy)} file(s) from the old fleet installer remain "
            "-- run --adopt-legacy to reconcile",
            file=out,
        )
    return 0


def cmd_pull(ctx: Context, out) -> int:
    """Fast-forward the serving checkout, then re-render.

    Refuses off main and refuses dirty, because the serving checkout is what
    every rendered surface points at: fast-forwarding a branch someone is
    working on, or one with uncommitted edits, would change what is installed
    on the machine as a side effect of an update.
    """
    live = git_context(ctx.checkout)
    if live["branch"] != "main":
        print(
            f"error: serving checkout is on {live['branch'] or '(detached)'}, not main; "
            "--pull refuses to move it.",
            file=out,
        )
        return 1
    if live["dirty"]:
        print("error: serving checkout has uncommitted changes; --pull refuses.", file=out)
        return 1
    if ctx.dry_run:
        print(f"would fast-forward {ctx.checkout} and re-render", file=out)
        return 0
    done = subprocess.run(  # nosec B603 - fixed argv, no shell
        ["git", "-C", str(ctx.checkout), "pull", "--ff-only"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        print(f"error: git pull --ff-only failed:\n{done.stderr.strip()}", file=out)
        return 1
    print(done.stdout.strip(), file=out)
    return cmd_user(ctx, out)


def cmd_uninstall(ctx: Context, out) -> int:
    """Remove exactly what the receipt says we wrote, and nothing else."""
    previous = owned_entries(read_receipt(ctx.receipt))
    if not previous:
        print(f"nothing to remove (no receipt at {ctx.receipt})", file=out)
        return 0
    skipped = prune_stale(previous, set(), dry_run=ctx.dry_run)
    held = [
        entry.get("command") for entry in previous if entry.get("kind") == "hook"
    ]
    if held:
        remove_hook(ctx.settings, held, dry_run=ctx.dry_run)
    removed = len(previous) - len(skipped) - len(held)
    prefix = "would remove" if ctx.dry_run else "removed"
    print(f"{prefix} {removed} file(s)", file=out)
    for path, reason in skipped:
        print(f"  left in place ({reason}): {path}", file=out)
    if not ctx.dry_run:
        try:
            ctx.receipt.unlink()
        except OSError:
            pass
    print(
        "note: the global excludes line and any CLAUDE.local.md blocks are left "
        "alone; they are yours, not ours.",
        file=out,
    )
    return 0


def cmd_adopt_legacy(ctx: Context, out) -> int:
    """Reconcile the old fleet installer's renders against the new ones (M1).

    Colliding names are simply overwritten by `--user`, so this command's only
    job is the other half: deleting the renders that have no successor. Each
    deletion is digest-gated against the legacy receipt, so a file edited since
    it was installed is reported and kept.
    """
    entries = legacy_targets(ctx.home, ctx.environ)
    if not entries:
        print("no legacy receipt found; nothing to adopt", file=out)
        return 0
    surfaces = discover_surfaces(ctx.checkout)
    current = {
        str(item.path) for item in render(surfaces, ctx.homes, dry_run=True)
    }
    previous = [
        {"path": str(path), "sha256": sha, "kind": "legacy"}
        for path, sha in entries
    ]
    # Counted before pruning, because pruning is what changes it: reading the
    # disk afterwards would report the survivors as though they were the whole
    # population and turn a 112-file removal into "removed 5".
    present = [path for path, _ in entries if path.exists()]
    collisions = [path for path in present if str(path) in current]
    skipped = prune_stale(previous, current, dry_run=ctx.dry_run)
    prefix = "would remove" if ctx.dry_run else "removed"
    print(
        f"legacy: {len(entries)} recorded, {len(present)} still present, "
        f"{prefix} {len(present) - len(collisions) - len(skipped)}",
        file=out,
    )
    if collisions:
        print(
            f"  {len(collisions)} kept for --user to overwrite (same name, "
            "new content)",
            file=out,
        )
    for path, reason in skipped:
        print(f"  left in place ({reason}): {path}", file=out)
    if not ctx.dry_run and not skipped:
        # Adoption has latched: everything the receipt records is either gone
        # or a name this checkout now owns. Leaving the receipt behind would
        # make --status advise a migration that has already happened, forever.
        try:
            legacy_receipt_path(ctx.home, ctx.environ).unlink()
        except OSError as exc:
            print(
                f"  could not retire the legacy receipt ({exc.strerror or exc}); "
                "--status will keep advising --adopt-legacy",
                file=out,
            )
        else:
            print("legacy receipt retired; nothing left to reconcile", file=out)
    return 0


def cmd_repo(ctx: Context, repo: Path, out, reviewers: str | None = None) -> int:
    repo = sibling("sd_lib").main_worktree_root(repo)
    try:
        consent = repo_consent(ctx, repo, reviewers, out)
    except (OSError, sibling("sd_lib").ConfigError, sibling("sd_registry").ConsentRefusal) as error:
        print(f"error: {error}", file=out)
        return 2
    action = write_local_block(repo, dry_run=ctx.dry_run, consent=consent)
    prefix = "would have " if ctx.dry_run else ""
    print(f"{prefix}{action} the sd block in {repo / LOCAL_BLOCK_FILE}", file=out)
    return 0


# ------------------------------------------------------------------------ CLI

USAGE = """\
usage: install.py (--user | --status | --pull | --uninstall | --adopt-legacy
                   | --repo [PATH]) [--dry-run] [--home DIR]

  --user           render every sd-* surface into this machine's platform homes
  --status         report what is installed, what drifted, what legacy remains
  --pull           fast-forward the serving checkout (main, clean) and re-render
  --uninstall      remove exactly what the receipt records having written
  --adopt-legacy   delete the old fleet installer's successor-less renders (M1)
  --repo [PATH]    write the marked block into PATH/CLAUDE.local.md (default: .)
  --provision-library
                   install sd_db into this pack's virtualenv and stop

  --reviewers NAMES
                   with --repo, the registry entries this repo consents to
                   receive its diff; the answer a prompt would have asked for

  --dry-run        print what would happen; write nothing
  --home DIR       treat DIR as the home directory (tests and scratch installs)
"""

MODES = ("user", "status", "pull", "uninstall", "adopt-legacy", "repo",
         "provision-library")


def main(argv: list[str], environ: dict[str, str] | None = None, out=None) -> int:
    out = sys.stdout if out is None else out
    environ = dict(os.environ if environ is None else environ)

    mode = None
    repo_arg = None
    reviewers = None
    dry_run = False
    home_arg = None
    index = 0
    while index < len(argv):
        token = argv[index]
        name = token[2:] if token.startswith("--") else ""
        if name in MODES:
            if mode is not None:
                print(f"error: --{mode} and {token} are mutually exclusive", file=out)
                return 2
            mode = name
            if name == "repo" and index + 1 < len(argv) and not argv[index + 1].startswith("-"):
                index += 1
                repo_arg = argv[index]
        elif token == "--dry-run":
            dry_run = True
        elif token == "--home":
            index += 1
            if index >= len(argv):
                print("error: --home needs a directory", file=out)
                return 2
            home_arg = argv[index]
        elif token == "--reviewers":
            # Taken positionally: an empty string is a real answer, nobody.
            index += 1
            if index >= len(argv):
                print("error: --reviewers needs the entry names to allow", file=out)
                return 2
            reviewers = argv[index]
        elif token in ("-h", "--help"):
            print(USAGE, file=out, end="")
            return 0
        else:
            print(f"error: unknown argument {token}\n\n{USAGE}", file=out, end="")
            return 2
        index += 1

    if mode is None:
        print(USAGE, file=out, end="")
        return 2

    home = Path(home_arg).expanduser().resolve() if home_arg else Path(
        os.path.expanduser("~")
    )
    if home_arg:
        # `HOME` is exported for the git subprocesses, which read it themselves
        # and cannot be told a home any other way. The XDG roots used to be
        # rewritten here as well; they no longer are, because doing it at the
        # entrypoint only protected callers that came through the entrypoint --
        # and the tests, which build a Context directly, did not. `xdg_root`
        # now enforces containment wherever the roots are resolved, so this is
        # one rule in one place instead of the same rule in two.
        environ["HOME"] = str(home)

    checkout = Path(__file__).resolve().parent.parent
    ctx = Context(checkout=checkout, home=home, environ=environ, dry_run=dry_run)

    if mode == "provision-library":
        # `make setup` calls this so the test suite can import `sd_db` without
        # a second file learning the path to the system checkout. It is the
        # only door: `--user` reads the library and never installs it, because
        # rendering skills must not rebuild the virtualenv it renders from.
        installed, report = provision_library(ctx, out)
        print(report, file=out)
        return 0 if installed else 1
    if mode == "user":
        return cmd_user(ctx, out)
    if mode == "status":
        return cmd_status(ctx, out)
    if mode == "pull":
        return cmd_pull(ctx, out)
    if mode == "uninstall":
        return cmd_uninstall(ctx, out)
    if mode == "adopt-legacy":
        return cmd_adopt_legacy(ctx, out)
    return cmd_repo(ctx, Path(repo_arg or ".").resolve(), out, reviewers)


if __name__ == "__main__":  # pragma: no cover - exercised via install.py
    import sys

    raise SystemExit(main(sys.argv[1:]))
