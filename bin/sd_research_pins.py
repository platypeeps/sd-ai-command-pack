#!/usr/bin/env python3
"""Report whether the commits a research repo pins are still the commits upstream has.

A research document states what it was read from: ``owner/repo`` @ ``sha``. That pin is
typed by hand and nothing watches it, so a document can go on asserting a commit for weeks
after the source moved. This reads the pins back out of the markdown, finds each source's
checkout, and says which ones have drifted.

The list is never maintained anywhere: it is enumerated from the documents on every run,
so a source added to a brief shows up here without anyone remembering to register it.
Checkouts are matched by git remote URL rather than by directory name, because a vendored
clone is routinely named for its subject and not for its repository.

    sd-research-kit pins        # from inside the research repo

`pins` takes no argument: it reads the repository you are standing in
(R10-D6). Exit 0 always. This reports; it does not gate.
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# `owner/name` @ `sha`  or  `name` @ `sha`
PIN = re.compile(r"`([A-Za-z0-9._/-]+)`\s*@\s*`([0-9a-f]{7,40})`")
FENCE = re.compile(r"^\s*```")
REMOTE = re.compile(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$")

SKIP_DIRS = {"build", ".git", "node_modules", "__pycache__"}
FILE_SUFFIXES = {".md", ".py", ".rs", ".ts", ".js", ".json", ".toml", ".yaml", ".yml"}


def search_root() -> Path:
    """`~/repos` -- the same directory, resolved when it is asked for.

    This was a module constant, and the home it named was frozen into the
    import. A run never noticed: one process, one home, and the answer is the
    same either way. What could not be done was to ask the question of any
    other directory. `build_index` takes no argument for the sibling side, so
    the only tree it would ever walk was whatever the developer happened to
    have cloned, and no test could exercise it against a tree it controls.

    A function is the whole fix. `pins` still reaches the real `~/repos`, and
    a caller that has its own tree can name it.
    """
    return Path(os.path.expanduser("~/repos"))


def checkouts(root):
    """Every git checkout under `root`, one and two levels deep.

    Not `*/*`. Checkouts sit at both depths -- `~/repos/system` is one level,
    `~/repos/<org>/<name>` is two -- and a `*/*` glob alone silently omits the
    first. That omission is not hypothetical: `system` is one of the two
    repositories the fleet pins by SHA, so a walk that cannot see it reports
    every pin of it as having no checkout to check against.
    """
    root = Path(root)
    found = []
    for path in sorted(root.glob("*")):
        if not path.is_dir():
            continue
        if (path / ".git").exists():
            found.append(path)
            continue
        found += [p for p in sorted(path.glob("*")) if (p / ".git").exists()]
    return found


def git(repo, *args):
    """Run git in repo, returning stripped stdout, or None if the command failed."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def slug(checkout):
    """owner/name for a checkout, from its origin URL. Falls back to the directory name."""
    url = git(checkout, "remote", "get-url", "origin")
    if url:
        m = REMOTE.search(url.strip())
        if m:
            return m.group(1).lower()
    return Path(checkout).name.lower()


def collect_pins(repo):
    """Every (source, sha) the markdown asserts outside code fences, and who asserts it."""
    found: dict[tuple[str, str], set[str]] = {}
    for path in sorted(Path(repo).rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        in_fence = False
        for line in text.splitlines():
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for name, sha in PIN.findall(line):
                # A pin names a repository, not a path inside one.
                if (name.endswith("/") or name.count("/") > 1
                        or Path(name).suffix in FILE_SUFFIXES):
                    continue
                found.setdefault((name, sha), set()).add(
                    path.relative_to(repo).as_posix()
                )
    return found


def build_index(repo, siblings=None):
    """Map owner/name and bare name to a checkout, for vendored and sibling clones.

    `siblings` is the tree the sibling clones live under, `~/repos` when the
    caller does not say. It is a parameter so that the tree can be one a test
    built, rather than one the machine happens to carry.
    """
    index: dict[str, Path] = {}
    roots = list((Path(repo) / "vendor").glob("*"))
    outside = search_root() if siblings is None else Path(siblings)
    if outside.is_dir():
        roots += checkouts(outside)
    for path in roots:
        if not (path / ".git").exists():
            continue
        full = slug(path)
        index.setdefault(full, path)
        index.setdefault(full.split("/")[-1], path)
        index.setdefault(path.name.lower(), path)
    return index


def fetch_note(checkout):
    fh = Path(checkout) / ".git" / "FETCH_HEAD"
    if not fh.exists():
        return "never fetched"
    days = int((time.time() - fh.stat().st_mtime) // 86400)
    return "fetched today" if days == 0 else f"fetched {days}d ago"


def describe(checkout, sha):
    """Status of one pin against its checkout."""
    if checkout is None:
        return "no checkout", ""
    if git(checkout, "cat-file", "-e", f"{sha}^{{commit}}") is None:
        return "unknown commit", "not in this checkout — never fetched, or the wrong repo"

    tip = next(
        (r for r in ("origin/HEAD", "origin/main", "origin/master")
         if git(checkout, "rev-parse", "--verify", "-q", r)),
        "HEAD",
    )
    behind = git(checkout, "rev-list", "--count", f"{sha}..{tip}")
    note = f"{tip}, {fetch_note(checkout)}"
    if behind is None:
        return "unknown", note
    if behind == "0":
        return "current", note
    return f"behind {behind}", note


def report(repo):
    repo = Path(repo).resolve()
    print(f"== {repo.name}")
    pins = collect_pins(repo)
    if not pins:
        print("  no pinned commits found")
        return

    index = build_index(repo)

    # Collapse `ext-apps` and `modelcontextprotocol/ext-apps` onto one row.
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for (name, sha), files in pins.items():
        checkout = index.get(name.lower()) or index.get(name.split("/")[-1].lower())
        # Resolved sources key on their real repo; unresolved ones key on the bare
        # name, so `x` and `owner/x` still merge. The fuller name wins the label.
        key = slug(checkout) if checkout else name.split("/")[-1].lower()
        entry = merged.setdefault((key, sha), {"checkout": checkout, "files": set(), "label": ""})
        entry["files"] |= files
        label = slug(checkout) if checkout else name.lower()
        if len(label) > len(entry["label"]):
            entry["label"] = label

    rows = []
    for (_key, sha), entry in sorted(merged.items(), key=lambda kv: kv[1]["label"]):
        status, note = describe(entry["checkout"], sha)
        where = (
            str(entry["checkout"]).replace(os.path.expanduser("~"), "~")
            if entry["checkout"] else ""
        )
        rows.append((entry["label"], sha[:8], status, len(entry["files"]), where, note))

    w_id = max(len(r[0]) for r in rows)
    w_st = max(len(r[2]) for r in rows)
    for identity, sha, status, n, where, note in rows:
        cited = f"{n} doc" + ("s" if n != 1 else "")
        print(f"  {identity:<{w_id}}  {sha:<8}  {status:<{w_st}}  {cited:<7}  {where}")
        if note:
            print(f"  {'':<{w_id}}  {'':<8}  {'':<{w_st}}  {'':<7}  {note}")

    stale = [r for r in rows if r[2].startswith("behind")]
    missing = [r for r in rows if r[2] in ("no checkout", "unknown commit")]
    unfetched = [r for r in rows if "never fetched" in r[5]]
    if unfetched:
        print()
        print(f"  {len(unfetched)} checkout(s) have never been fetched. For those, \"current\"")
        print("  means current as of the clone, not as of upstream. Fetch before trusting it:")
        for _identity, _sha, _st, _n, where, _note in unfetched:
            print(f"    git -C {where} fetch")
    if stale:
        print()
        for identity, sha, status, _n, _w, _note in stale:
            print(f"  {identity} is {status}: documents assert {sha}, which is no longer the tip.")
        print("  Re-read the source, or say in Status that the pin is deliberate and dated.")
    if missing:
        print(f"\n  {len(missing)} pin(s) have no checkout here to check against.")


# ---------------------------------------------------------------------------
# The fleet side: the same question asked of CI, not of prose.
#
# A research document pins a source in backticks. CI pins the same way and in
# four more forms, none of which any ecosystem can see: `uses: owner/repo@sha`
# is invisible to Dependabot once the pack is told to ignore it, and `ref:`,
# `<NAME>_REVISION:` and a committed tarball's `"source_commit"` are invisible
# to every ecosystem by construction. Nothing reported staleness, and the cost
# was paid on 2026-09-11: this pack's own tests.yml pins `platypeeps/system` at
# a commit predating a function the tests import, and CI failed on an
# ImportError that no staleness report existed to predict.
# ---------------------------------------------------------------------------

USES = re.compile(r"uses:\s*([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)(?:/\S*?)?@([0-9a-f]{7,40})\b")
REPOSITORY = re.compile(r"^\s*repository:\s*['\"]?([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)")
REF = re.compile(r"^\s*ref:\s*['\"]?([0-9a-f]{7,40})['\"]?\s*$")
REF_ENV = re.compile(r"^\s*ref:\s*\$\{\{\s*env\.([A-Za-z0-9_]+)\s*\}\}")
REVISION = re.compile(r"^\s*([A-Za-z0-9_]*REVISION):\s*['\"]?([0-9a-f]{7,40})['\"]?\s*$")
SOURCE_COMMIT = re.compile(r'"source_commit"\s*:\s*"([0-9a-f]{7,40})"')

WORKFLOW_SUFFIXES = {".yml", ".yaml"}


def workflow_sites(text):
    """(hint, sha, form, line) for every pin in one workflow file.

    `uses:` names its repository on the line. `ref:` does not — it belongs to
    the `repository:` of the same `with:` block, so the file is read in order
    and the last `repository:` seen carries the ref. A `ref:` that reads an env
    var is that link one hop further out: it says which repository the
    `<NAME>_REVISION` at the top of the file is a revision *of*, which is how
    `PACK_REVISION` resolves without anyone having written down that "PACK"
    means the command pack. The bare name is only the fallback.
    """
    sites, repository, by_env = [], None, {}
    lines = text.splitlines()
    for line in lines:
        found = REPOSITORY.match(line)
        if found:
            repository = found.group(1)
            continue
        found = REF_ENV.match(line)
        if found and repository:
            by_env[found.group(1)] = repository

    repository = None
    for number, line in enumerate(lines, 1):
        found = REPOSITORY.match(line)
        if found:
            repository = found.group(1)
        found = USES.search(line)
        if found:
            sites.append((found.group(1), found.group(2), "uses", number))
            continue
        found = REF.match(line)
        if found and repository:
            sites.append((repository, found.group(1), "ref", number))
            continue
        found = REVISION.match(line)
        if found:
            name = found.group(1)
            hint = by_env.get(name) or name[: -len("REVISION")].strip("_").lower()
            sites.append((hint, found.group(2), "env", number))
    return sites


def manifest_sites(path, text):
    """A committed tarball manifest pins its source in `"source_commit"`.

    Nothing inside the manifest says which repository it came from. The file is
    named for it -- `system-source.json` -- which is the only handle there is.
    """
    name = Path(path).stem
    for suffix in ("-source", "_source", "-manifest", "_manifest"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return [
        (name.lower(), m.group(1), "manifest", text[: m.start()].count("\n") + 1)
        for m in SOURCE_COMMIT.finditer(text)
    ]


def pin_sites(checkout):
    """Every pin site under one checkout's `.github/`, enumerated from disk."""
    sites: list[tuple[Path, int, str, str, str]] = []
    github = Path(checkout) / ".github"
    if not github.is_dir():
        return sites
    for path in sorted(github.rglob("*")):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in WORKFLOW_SUFFIXES and path.suffix != ".json":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        read = workflow_sites(text) if path.suffix in WORKFLOW_SUFFIXES \
            else manifest_sites(path, text)
        for hint, sha, form, number in read:
            sites.append((path, number, hint, sha, form))
    return sites


def fleet(root=None):
    """Resolve every fleet pin site against the checkouts beside it.

    Only pins resolving to a checkout under the same root are reported. That is
    not a shortcut, it is what makes the report readable: the fleet's workflows
    carry hundreds of third-party action pins, and a report listing
    `actions/checkout` beside the pack would bury the rows anyone acts on. What
    we clone is what we own.
    """
    root = search_root() if root is None else Path(root)
    trees = checkouts(root)
    index: dict[str, Path] = {}
    for path in trees:
        full = slug(path)
        index.setdefault(full, path)
        index.setdefault(full.split("/")[-1], path)
        index.setdefault(path.name.lower(), path)

    rows = []
    for checkout in trees:
        for path, number, hint, sha, form in pin_sites(checkout):
            target = index.get(hint.lower()) or index.get(hint.split("/")[-1].lower())
            if target is None or Path(target).resolve() == Path(checkout).resolve():
                # Unresolved is third-party; self-pinned is not a fleet pin.
                continue
            status, note = describe(target, sha)
            rows.append({
                "repo": slug(checkout),
                "where": f"{path.relative_to(checkout).as_posix()}:{number}",
                "form": form,
                "target": slug(target),
                "sha": sha,
                "status": status,
                "note": note,
            })
    return rows


def fleet_report(root=None):
    rows = fleet(root)
    if not rows:
        print("no fleet pins found")
        return 0
    width = {k: max(len(str(r[k])) for r in rows) for k in ("repo", "where", "form", "target")}
    for row in sorted(rows, key=lambda r: (r["repo"], r["where"])):
        print(f"  {row['repo']:<{width['repo']}}  {row['where']:<{width['where']}}  "
              f"{row['form']:<{width['form']}}  {row['target']:<{width['target']}}  "
              f"{row['sha'][:8]}  {row['status']}")
    behind = [r for r in rows if r["status"].startswith("behind")]
    print(f"\n  {len(rows)} pin site(s) across {len({r['repo'] for r in rows})} "
          f"repo(s); {len(behind)} behind.")
    if behind:
        print("  Report only — the repin stays a hand decision.")
    return 0


def main() -> int:
    # R10-D6: the repository is the one the caller is standing in. This took
    # `pins [repo_dir ...]` before the kit moved into the pack.
    report(os.getcwd())
    return 0


def fleet_main() -> int:
    """`sd-research-kit fleet-pins`. Reports; never gates."""
    fleet_report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
