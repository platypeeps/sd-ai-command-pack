"""The 'why' search (pack sd:6019): a file path or a rule's text leads to the items that explain it.

Operator ruling (grill Q40): the item page answers "why is it like this?", and this search finds the item. Two kinds:

- A path (no space, and a `/` or a file suffix): `git log` over it in each managed checkout that holds it, then the items
  each commit cites in its trailer block (`Closes:`, `Delivers:` and `Item:`, the block `sd_lib.trailer_block` reads, as
  pack sd:5999 does) or as `sd:N` in its subject, and the items whose `Code delivery` note names the commit. Prose in a
  commit body cites nothing.
- Anything else is rule text: each line of a rule file (`CLAUDE.md`, `AGENTS.md`, `.claude/rules/*.md` in each managed
  checkout, and the operator's `~/.claude/CLAUDE.md`) that holds it, and the `sd:N` the line cites.

No new store: the commits, the notes and the rule files are the links. A `git log` that fails is named in `errors`, never
read as "no item".
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from sd_db import repos

__all__ = ["LOG_COMMITS", "MAX_ITEMS", "MIN_QUERY", "search"]

#: The commits `git log` reads per checkout, newest first.
LOG_COMMITS = 200
#: The items one search lists.
MAX_ITEMS = 50
#: The shortest query searched: shorter text matches most rule lines.
MIN_QUERY = 3

_CITES = re.compile(r"^(?:Closes|Delivers|Item): sd:([0-9]+)[ \t]*$")
_DELIVERY = re.compile(r"Code delivery (\S+) at ([0-9a-f]{40,64})\b")
_SD = re.compile(r"\bsd:([0-9]{1,18})\b")
_PATH = re.compile(r"\S*(?:/\S*|\.[A-Za-z0-9]{1,8})")


def _checkouts(connection) -> list[tuple[str, Path]]:
    """Each managed repository's name and its checkout on this machine, when it has one."""
    out = []
    for row in repos.registered(connection):
        folder = Path(str(row["path"])).expanduser()
        if row["managed"] and (folder / ".git").exists():
            out.append((repos.short(row["path"]) or str(folder), folder))
    return out


def _trailer_block(message: str) -> str:
    from . import pack_module

    return pack_module("sd_lib").trailer_block(message)


def _commits(folder: Path, relative: str) -> list[tuple[str, str]]:
    """Each `(sha, message)` that touched `relative` in `folder`, newest first. Raises `OSError` when git fails."""
    done = subprocess.run(["git", "-C", str(folder), "log", "-n", str(LOG_COMMITS), "--format=%H%x1f%B%x1e", "--",
                           relative], capture_output=True, text=True, timeout=20, check=False)
    if done.returncode:
        raise OSError((done.stderr.strip() or f"exit {done.returncode}").splitlines()[0])
    return [tuple(entry.strip("\n").split("\x1f", 1)) for entry in done.stdout.split("\x1e") if "\x1f" in entry]


def _deliveries(connection) -> dict[str, list[tuple[int, str]]]:
    """Each merge commit a `Code delivery` note names, to its items and pull request."""
    out: dict[str, list[tuple[int, str]]] = {}
    for row in connection.execute("SELECT item, body FROM note WHERE kind = 'comment' AND body LIKE 'Code delivery %'"):
        found = _DELIVERY.match(row["body"])
        if found:
            out.setdefault(found[2], []).append((row["item"], found[1]))
    return out


def _by_path(connection, query: str, checkouts) -> tuple[list[tuple[int, str]], list[str]]:
    hits: list[tuple[int, str]] = []
    errors: list[str] = []
    wanted = Path(query).expanduser()
    delivered = None
    for name, folder in checkouts:
        if wanted.is_absolute():
            try:
                relative = str(wanted.resolve().relative_to(folder.resolve()))
            except ValueError:
                continue
        elif (folder / query).exists():
            relative = query
        else:
            continue
        try:
            commits = _commits(folder, relative)
        except (OSError, subprocess.SubprocessError) as error:
            errors.append(f"git log in {name} failed: {error}")
            continue
        delivered = _deliveries(connection) if delivered is None else delivered
        for sha, message in commits:
            subject = message.splitlines()[0] if message.strip() else ""
            trailers = [found[1] for line in _trailer_block(message.rstrip()).split("\n") if (found := _CITES.match(line))]
            hits.extend((int(item), f"{name} commit {sha[:9]}: {subject}") for item in [*trailers, *_SD.findall(subject)])
            for item, pull in delivered.get(sha, ()):
                hits.append((item, f"{name} commit {sha[:9]} delivered it ({pull})"))
    return hits, errors


def _rule_files(checkouts, home: Path) -> list[tuple[str, Path]]:
    files = [("~/.claude/CLAUDE.md", home / ".claude" / "CLAUDE.md")]
    for name, folder in checkouts:
        for path in [folder / "CLAUDE.md", folder / "AGENTS.md", *sorted((folder / ".claude" / "rules").glob("*.md"))]:
            files.append((f"{name}/{path.relative_to(folder)}", path))
    return files


def _by_text(query: str, checkouts, home: Path) -> tuple[list[tuple[int, str]], list[str], list[str]]:
    hits: list[tuple[int, str]] = []
    uncited: list[str] = []
    errors: list[str] = []
    wanted = " ".join(query.lower().split())
    for where, path in _rule_files(checkouts, home):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError) as error:
            errors.append(f"{where} was not read: {error}")
            continue
        for number, line in enumerate(lines, start=1):
            if wanted in " ".join(line.lower().split()):
                cited = _SD.findall(line)
                hits.extend((int(item), f"{where}:{number}: {line.strip()}") for item in cited)
                if not cited:
                    uncited.append(f"{where}:{number}")
    return hits, uncited, errors


def search(connection, query: str, *, home: Path | None = None) -> dict:
    """The items `query` leads to, each once with the first thing that cites it; see the module docstring."""
    query = query.strip()
    kind = "path" if _PATH.fullmatch(query) else "text"
    found = {"query": query, "kind": kind, "items": [], "uncited": [], "errors": []}
    if len(query) < MIN_QUERY:
        return found
    checkouts = _checkouts(connection)
    if kind == "path":
        hits, found["errors"] = _by_path(connection, query, checkouts)
    else:
        hits, found["uncited"], found["errors"] = _by_text(query, checkouts, home or Path.home())
    seen: dict[int, str] = {}
    for item, why in hits:
        seen.setdefault(item, why)
    numbers = list(seen)[:MAX_ITEMS]
    rows = {row["id"]: row for row in connection.execute(
        f"SELECT id, title, status, repo FROM item WHERE id IN ({','.join('?' * len(numbers))})", numbers)} if numbers else {}
    found["items"] = [{"item": n, "title": rows[n]["title"] if n in rows else None,
                       "status": rows[n]["status"] if n in rows else None,
                       "repo": repos.short(rows[n]["repo"]) if n in rows else None, "why": seen[n]} for n in numbers]
    return found
