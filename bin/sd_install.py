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
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SKILL_FILE = "SKILL.md"
STATE_DIR = "sd-ai-command-pack"
RECEIPT_NAME = "installed.json"
RECEIPT_SCHEMA = 1

HOOK_COMMAND = "bin/sd-handoff-restore"
HOOK_EVENT_NAME = "SessionStart"
HOOK_MATCHERS = ("startup", "clear")

EXCLUDES_LINE = "CLAUDE.local.md"


# ------------------------------------------------------------------- location


def state_home(environ: dict[str, str]) -> Path:
    """`$XDG_STATE_HOME` when it is absolute, else `~/.local/state`.

    Deliberately identical to `bin/sd-handoff`'s helper rather than imported
    from it: the handoff tools must work with no installer present at all, and
    a shared module would make the installer a dependency of the thing it
    installs.
    """
    configured = environ.get("XDG_STATE_HOME", "")
    if configured and os.path.isabs(configured):
        return Path(configured)
    return Path(os.path.expanduser("~")) / ".local" / "state"


def receipt_path(environ: dict[str, str]) -> Path:
    return state_home(environ) / STATE_DIR / RECEIPT_NAME


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
    config = environ.get("XDG_CONFIG_HOME", "")
    config_root = (
        Path(config) if config and os.path.isabs(config) else home / ".config"
    )
    return [
        PlatformHome("claude", home / ".claude" / "skills", "directory"),
        PlatformHome("codex", home / ".codex" / "skills", "directory"),
        PlatformHome("opencode", config_root / "opencode" / "commands", "flat"),
    ]


# -------------------------------------------------------------------- payload


@dataclass
class Surface:
    """One sd-* skill in the checkout, with any templates it carries."""

    name: str
    skill: Path
    extras: list[Path] = field(default_factory=list)


def discover_surfaces(checkout: Path) -> list[Surface]:
    """Enumerate `skills/sd-*/SKILL.md` from disk, never from a list.

    A written list is the thing that goes stale when a surface is added, and
    the whole point of the rebuild is that inventories are derived.
    """
    root = checkout / "skills"
    if not root.is_dir():
        return []
    surfaces: list[Surface] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or not entry.name.startswith("sd-"):
            continue
        skill = entry / SKILL_FILE
        if not skill.is_file():
            continue
        extras = sorted(
            path for path in (entry / "templates").glob("*.md") if path.is_file()
        )
        surfaces.append(Surface(entry.name, skill, extras))
    return surfaces


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

    def git(*args: str) -> str:
        try:
            done = subprocess.run(  # nosec B603 - fixed argv, no shell
                ["git", "-C", str(checkout), *args],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return ""
        return done.stdout.strip() if done.returncode == 0 else ""

    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
    }


# --------------------------------------------------------------------- render


@dataclass
class Written:
    path: Path
    sha256: str
    kind: str


def render(
    surfaces: list[Surface], homes: list[PlatformHome], *, dry_run: bool = False
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
            written.append(Written(target, digest(body), f"skill:{home.key}"))
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
            if home.layout != "directory":
                # Flat homes have nowhere to put a template beside its skill,
                # and OpenCode's command loader would read one as a command.
                continue
            for extra in surface.extras:
                data = extra.read_bytes()
                dest = target.parent / "templates" / extra.name
                written.append(Written(dest, digest(data), f"template:{home.key}"))
                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
    return written


# ------------------------------------------------------- the one settings edit


def hook_stanza_command(checkout: Path) -> str:
    return str(checkout / HOOK_COMMAND)


def install_hook(settings: Path, command: str, *, dry_run: bool = False) -> bool:
    """Register `sd-handoff-restore` on SessionStart `startup` and `clear`.

    This is the only file outside a platform home the installer ever writes,
    and it is somebody else's file: `~/.claude/settings.json` holds hooks from
    the machine's other installers. So the edit is surgical -- the settings are
    loaded, this one command is added under exactly two matchers, everything
    else is written back untouched -- and it is idempotent, because a second
    `--user` run must not leave the hook registered twice.

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
    groups = hooks.setdefault(HOOK_EVENT_NAME, [])
    if not isinstance(groups, list):
        raise SystemExit(
            f"error: {settings} has a non-list '{HOOK_EVENT_NAME}' hook list."
        )

    changed = False
    for matcher in HOOK_MATCHERS:
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
                f"error: {settings} SessionStart/{matcher} has a non-list 'hooks'."
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


def remove_hook(settings: Path, command: str, *, dry_run: bool = False) -> bool:
    """Drop our hook entry, and any matcher group we thereby emptied.

    Only entries whose command is exactly ours are removed; another
    installer's hook under the same matcher survives, which is why the group
    is deleted only when it ends up empty.
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
    groups = hooks.get(HOOK_EVENT_NAME)
    if not isinstance(groups, list):
        return False

    changed = False
    surviving = []
    for group in groups:
        if not isinstance(group, dict) or group.get("matcher") not in HOOK_MATCHERS:
            surviving.append(group)
            continue
        entries = group.get("hooks")
        if not isinstance(entries, list):
            surviving.append(group)
            continue
        kept = [
            entry
            for entry in entries
            if not (isinstance(entry, dict) and entry.get("command") == command)
        ]
        if len(kept) != len(entries):
            changed = True
        if kept:
            group["hooks"] = kept
            surviving.append(group)
        elif not entries:
            surviving.append(group)
    if not changed:
        return False
    if surviving:
        hooks[HOOK_EVENT_NAME] = surviving
    else:
        # Leaving `"SessionStart": []` behind would be residue of exactly the
        # kind uninstall exists to remove: an empty key in someone else's file
        # that only we ever put there.
        hooks.pop(HOOK_EVENT_NAME, None)
        if not hooks:
            data.pop("hooks", None)
    if not dry_run:
        scratch = settings.with_name(settings.name + ".sd-tmp")
        scratch.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(scratch, settings)
    return True


# ------------------------------------------------------------ global excludes


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
        config = environ.get("XDG_CONFIG_HOME", "")
        root = Path(config) if config and os.path.isabs(config) else home / ".config"
        return root / "git" / "ignore"
    try:
        done = subprocess.run(  # nosec B603 - fixed argv, no shell
            ["git", "config", "--global", "--get", "core.excludesFile"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        done = None
    if done is not None and done.returncode == 0:
        configured = done.stdout.strip()
        if configured:
            return Path(os.path.expanduser(configured))
    config = environ.get("XDG_CONFIG_HOME", "")
    root = Path(config) if config and os.path.isabs(config) else home / ".config"
    return root / "git" / "ignore"


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
    try:
        done = subprocess.run(  # nosec B603 - fixed argv, no shell
            ["git", "config", "--global", "--get", "core.excludesFile"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return
    if done.returncode == 0 and done.stdout.strip():
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


def legacy_targets(home: Path, environ: dict[str, str]) -> list[tuple[Path, str]]:
    """Enumerate what the old fleet installer wrote, from its own receipt.

    Enumeration comes from the receipt rather than from a list written here,
    for the reason the whole rebuild exists: a list would be a second copy of
    the truth, and the copy is what goes stale. Entries whose family we no
    longer recognise are skipped rather than guessed at.

    Returns `(path, sha256)` pairs; the digest is what lets `--adopt-legacy`
    refuse to delete a file somebody has since edited.
    """
    receipt = state_home(environ) / STATE_DIR / Path(*LEGACY_RECEIPT)
    data = read_receipt(receipt)
    rows = data.get("files")
    if not isinstance(rows, list):
        return []
    config = environ.get("XDG_CONFIG_HOME", "")
    config_root = (
        Path(config) if config and os.path.isabs(config) else home / ".config"
    )
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
BLOCK_BEGIN = "<!-- sd-ai-command-pack:begin -->"
BLOCK_END = "<!-- sd-ai-command-pack:end -->"

DEFAULT_BLOCK_BODY = """\
sd-ai-command-pack, machine-scope. Work items live under `docs/work/`; nothing
else in this repo belongs to the framework.

    mode: full
    check: <the command that verifies this repo, e.g. `make check`>
"""


def write_local_block(repo: Path, *, dry_run: bool = False) -> str:
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
        existing = target.read_text(encoding="utf-8")
    except OSError:
        existing = ""

    block = f"{BLOCK_BEGIN}\n{DEFAULT_BLOCK_BODY}{BLOCK_END}\n"
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
    if not dry_run and updated != existing:
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


# ------------------------------------------------------------------- commands


@dataclass
class Context:
    checkout: Path
    home: Path
    environ: dict[str, str]
    dry_run: bool = False
    sandboxed: bool = False

    @property
    def homes(self) -> list[PlatformHome]:
        return platform_homes(self.home, self.environ)

    @property
    def receipt(self) -> Path:
        return receipt_path(self.environ)

    @property
    def settings(self) -> Path:
        return self.home / ".claude" / "settings.json"


def cmd_user(ctx: Context, out) -> int:
    """Render every surface, converge the machine, write the receipt."""
    surfaces = discover_surfaces(ctx.checkout)
    if not surfaces:
        print(
            f"error: no skills/sd-*/{SKILL_FILE} under {ctx.checkout}; "
            "is this the pack checkout?",
            file=out,
        )
        return 1

    written = render(surfaces, ctx.homes, dry_run=ctx.dry_run)
    current = {str(item.path) for item in written}

    previous = owned_entries(read_receipt(ctx.receipt))
    skipped = prune_stale(previous, current, dry_run=ctx.dry_run)

    hook = hook_stanza_command(ctx.checkout)
    hook_changed = install_hook(ctx.settings, hook, dry_run=ctx.dry_run)

    excludes = excludes_file(ctx.home, ctx.environ, sandboxed=ctx.sandboxed)
    excludes_changed = ensure_excludes_line(excludes, dry_run=ctx.dry_run)
    set_excludes_config(excludes, dry_run=ctx.dry_run, sandboxed=ctx.sandboxed)

    owned = [
        {"path": str(item.path), "sha256": item.sha256, "kind": item.kind}
        for item in written
    ]
    owned.append({"path": str(ctx.settings), "kind": "hook", "command": hook})
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
    if hook_changed:
        print(f"  SessionStart hook registered: {hook}", file=out)
    if excludes_changed:
        print(f"  global excludes: {EXCLUDES_LINE} -> {excludes}", file=out)
    for path, reason in skipped:
        print(f"  left in place ({reason}): {path}", file=out)
    return 0


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

    legacy = [path for path, _ in legacy_targets(ctx.home, ctx.environ) if path.exists()]
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
    hook = next(
        (entry.get("command") for entry in previous if entry.get("kind") == "hook"), None
    )
    if hook:
        remove_hook(ctx.settings, hook, dry_run=ctx.dry_run)
    removed = len(previous) - len(skipped) - (1 if hook else 0)
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
    skipped = prune_stale(previous, current, dry_run=ctx.dry_run)
    present = sum(1 for path, _ in entries if path.exists())
    prefix = "would remove" if ctx.dry_run else "removed"
    print(
        f"legacy: {len(entries)} recorded, {present} still present, "
        f"{prefix} {present - len(skipped)}",
        file=out,
    )
    for path, reason in skipped:
        print(f"  left in place ({reason}): {path}", file=out)
    return 0


def cmd_repo(ctx: Context, repo: Path, out) -> int:
    action = write_local_block(repo, dry_run=ctx.dry_run)
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

  --dry-run        print what would happen; write nothing
  --home DIR       treat DIR as the home directory (tests and scratch installs)
"""

MODES = ("user", "status", "pull", "uninstall", "adopt-legacy", "repo")


def main(argv: list[str], environ: dict[str, str] | None = None, out=None) -> int:
    import sys

    out = sys.stdout if out is None else out
    environ = dict(os.environ if environ is None else environ)

    mode = None
    repo_arg = None
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

    # A `--home` override has to move the state root too, or a scratch install
    # would write its receipt into the real one and a test run would clobber
    # the machine's actual installation.
    home = Path(home_arg).expanduser().resolve() if home_arg else Path(
        os.path.expanduser("~")
    )
    if home_arg:
        environ["HOME"] = str(home)
        environ["XDG_STATE_HOME"] = str(home / ".local" / "state")
        environ["XDG_CONFIG_HOME"] = str(home / ".config")

    checkout = Path(__file__).resolve().parent.parent
    ctx = Context(
        checkout=checkout,
        home=home,
        environ=environ,
        dry_run=dry_run,
        sandboxed=home_arg is not None,
    )

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
    return cmd_repo(ctx, Path(repo_arg or ".").resolve(), out)


if __name__ == "__main__":  # pragma: no cover - exercised via install.py
    import sys

    raise SystemExit(main(sys.argv[1:]))
