"""`sd skill intake`: judge a GitHub skill against the installed set; install only on approval.

The fetched skill is untrusted data. It is fetched into a fresh empty
directory and read as git blobs: nothing is checked out, so no file of it
runs, no hook of it fires and no link of it is followed. No model reads it:
risk, match and value are scored here by rules a reader can check, and the
verdict is advice to the operator, never an approval.

The pre-screen, lint, name transform and provenance block are
`sd-skill-adopt`'s, loaded as its sibling, so one set of rules guards both
doors. Provenance stays where that tool already writes it, in the skill's own
`## Provenance` section; a re-import reads the URL back from there.

Installing writes `--approve REVISION` only, where the revision is the one the
report printed. It binds the upstream commit, the fetched bytes, the target
and the installed copy, so an approval of one report cannot install what a
later fetch or a local edit changed.
"""

from __future__ import annotations

import argparse
import datetime
import difflib
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unicodedata
from typing import Any

import sd_lib

ADOPT = sd_lib.sibling("sd_skill_adopt", "sd-skill-adopt")

GITHUB = "https://github.com/"
SKILL_FILE = "SKILL.md"
PACK_NAME_RE = re.compile(r"sd-[a-z0-9-]+")
PROVENANCE_RE = re.compile(r"from `(https://github\.com/[^`\s]+)` at revision `([0-9a-f]{40})\b")
TOOL = "sd skill intake"

#: The catalog's own limits (`skills_catalog._snapshot`), so an installed
#: skill never breaks `sd skill list`.
MAX_FILES = 200
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 8 * MAX_FILE
GIT_TIMEOUT = 120

#: Overlap at or above this folds the candidate into the nearest skill.
#: Measured on 2026-10-13: the closest distinct pair among the installed
#: skills scored 0.23, a copy of an installed skill 1.00.
FOLD_AT = 0.35
#: Fewer instruction lines than this teach nothing worth a skill.
MIN_BODY_LINES = 5
DIFF_LINES = 400

#: Where an install stages, beside the skills root rather than in it, so
#: `sd skill list` never reads a half-written skill.
STAGING = ".sd-skill-intake"

SCRIPT_SUFFIXES = frozenset({".sh", ".bash", ".zsh", ".fish", ".py", ".js", ".mjs", ".cjs", ".ts",
                             ".rb", ".pl", ".php", ".ps1", ".bat", ".cmd"})
HOOK_FILES = frozenset({"hooks.json", "settings.json", "settings.local.json"})
#: Variables that point git at another repository; the fetch runs in its own.
GIT_LOCATION = frozenset({"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                          "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE"})
STOPWORDS = frozenset(
    "about after also another any before being can does each else from have into its more must "
    "only other over same should skill than that their them then there these they this those "
    "through under user users wants what when where which while will with without your".split())


class IntakeError(Exception):
    """An intake that cannot answer or may not write. Nothing was installed."""


# --------------------------------------------------------------------------
# Fetch: one fresh directory, blobs only
# --------------------------------------------------------------------------


def parse_url(url: str) -> tuple[str, list[str], str]:
    """`(clone URL, the parts after tree/ or blob/, kind)` for a GitHub skill URL."""

    if not url.startswith(GITHUB) or any(ch.isspace() for ch in url):
        raise IntakeError(f"not a GitHub URL: {url!r}; give https://github.com/<owner>/<repo>/tree/<ref>/<path>")
    parts = [part for part in url[len(GITHUB):].split("?")[0].split("#")[0].split("/") if part]
    if len(parts) < 2 or any(part in (".", "..") for part in parts):
        raise IntakeError(f"no repository in {url}")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    kind = parts[2] if len(parts) > 2 else ""
    if kind not in ("", "tree", "blob") or (kind and len(parts) < 4):
        raise IntakeError(f"cannot read a ref and path from {url}")
    return f"{GITHUB}{owner}/{repo}.git", parts[3:], kind


def _git_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in GIT_LOCATION}
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"})
    return sd_lib.without_fsmonitor(env)


def _git(work: pathlib.Path, *args: str, text: bool = True) -> Any:
    """One git call in the fetch directory. A failure is an error, never an empty answer."""

    try:
        done = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(work), *args],
                              capture_output=True, text=text, timeout=GIT_TIMEOUT, env=_git_env(), check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise IntakeError(f"git {args[0]} did not finish: {error}") from error
    if done.returncode:
        stderr = done.stderr if text else done.stderr.decode("utf-8", "replace")
        raise IntakeError(f"git {args[0]} failed: {_printable(stderr.strip())[:300]}")
    return done.stdout


def _resolve(work: pathlib.Path, remote: str, parts: list[str]) -> tuple[str, list[str]]:
    """The ref to fetch and the path inside it. A branch name may hold slashes."""

    if not parts:
        return "HEAD", []
    if re.fullmatch(r"[0-9a-f]{40}", parts[0]):
        return parts[0], parts[1:]
    refs = set()
    for line in _git(work, "ls-remote", "--heads", "--tags", remote).splitlines():
        name = line.split("\t", 1)[-1]
        refs.add(name.removeprefix("refs/heads/").removeprefix("refs/tags/"))
    for cut in range(len(parts), 0, -1):
        if "/".join(parts[:cut]) in refs:
            return "/".join(parts[:cut]), parts[cut:]
    raise IntakeError(f"no branch or tag of {remote} starts {'/'.join(parts)}")


def _listing(work: pathlib.Path, path: str) -> list[tuple[str, str, str, str]]:
    """`(mode, oid, size, path)` for every entry under `path` at the fetched commit."""

    raw = _git(work, "ls-tree", "-r", "-l", "-z", "--full-tree", "FETCH_HEAD", "--", path or ".")
    entries = []
    for record in raw.split("\0"):
        if record:
            meta, name = record.split("\t", 1)
            mode, _kind, oid, size = meta.split()
            if not path or name == path or name.startswith(path + "/"):
                entries.append((mode, oid, size, name))
    return entries


def fetch_skill(url: str) -> dict[str, Any]:
    """The skill at `url`: its commit, its path and every file as `(mode, bytes)`."""

    remote, parts, kind = parse_url(url)
    with tempfile.TemporaryDirectory(prefix="sd-skill-intake-") as scratch:
        work = pathlib.Path(scratch) / "fetch"
        _git(pathlib.Path(scratch), "init", "-q", "--template=", str(work))
        ref, rest = _resolve(work, remote, parts)
        if kind == "blob" and rest and rest[-1] == SKILL_FILE:
            rest = rest[:-1]
        _git(work, "fetch", "-q", "--depth", "1", "--no-tags", "--no-recurse-submodules", remote, ref)
        commit = _git(work, "rev-parse", "FETCH_HEAD^{commit}").strip()
        prefix = "/".join(rest)
        entries = _listing(work, prefix)
        sizes = [int(size) for _m, _o, size, _n in entries if size.isdigit()]
        if len(entries) > MAX_FILES or sum(sizes) > MAX_TOTAL or any(size > MAX_FILE for size in sizes):
            raise IntakeError(f"the skill at {url} exceeds {MAX_FILES} files, {MAX_FILE} bytes a file "
                              f"or {MAX_TOTAL} bytes in all")
        files = {}
        for mode, oid, _size, name in entries:
            # A link or submodule has no blob worth reading; `risk` refuses it by mode.
            linked = mode in ("120000", "160000")
            files[name[len(prefix) + 1:] if prefix else name] = (
                mode, b"" if linked else _git(work, "cat-file", "blob", oid, text=False))
    if SKILL_FILE not in files:
        raise IntakeError(f"no {SKILL_FILE} at {prefix or 'the repository root'} of {url}")
    return {"url": url, "commit": commit, "path": prefix, "files": files}


# --------------------------------------------------------------------------
# Score: risk, match, value
# --------------------------------------------------------------------------


def _finding(severity: str, rule: str, file: str, line: int = 0) -> dict[str, Any]:
    return {"severity": severity, "rule": rule, "file": file, "line": line}


def _file_risk(name: str, mode: str, body: bytes) -> list[dict[str, Any]]:
    if mode in ("120000", "160000"):
        return [_finding(ADOPT.REFUSE, "link-or-submodule", name)]
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = ""
    if "\0" in text or (body and not text):
        return [_finding(ADOPT.REFUSE, "unscreenable-binary", name)]
    found = [_finding(f.severity, f.rule, name, f.line) for f in ADOPT.prescreen(text)]
    if mode == "100755" or text.startswith("#!") or pathlib.PurePosixPath(name).suffix in SCRIPT_SUFFIXES:
        found.append(_finding(ADOPT.WARN, "ships-script", name))
    if pathlib.PurePosixPath(name).name in HOOK_FILES:
        found.append(_finding(ADOPT.REFUSE, "ships-hook-config", name))
    return found


def risk(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Scripts, network calls, secrets, hooks and text aimed at the agent, file by file."""

    found = []
    for name, (mode, body) in sorted(candidate["files"].items()):
        found += _file_risk(name, mode, body)
    text = candidate["files"][SKILL_FILE][1].decode("utf-8", "replace")
    head = text.split("\n---", 1)[0] if text.startswith("---\n") else ""
    if re.search(r"(?m)^hooks\s*:", head):
        found.append(_finding(ADOPT.REFUSE, "declares-hooks", SKILL_FILE, 1))
    fields = sd_lib.parse_frontmatter(text) or {}
    name = fields.get("name", "")
    found += [_finding(f.severity, f.rule, SKILL_FILE, f.line) for f in ADOPT.lint(name, text)]
    if fields.get(ADOPT.MARKER) == "true":
        found.append(_finding(ADOPT.REFUSE, "adopted-surface-claims-command-authority", SKILL_FILE, 1))
    return found


def _words(text: str) -> set[str]:
    head = text.split("\n---", 1)[0] if text.startswith("---\n") else text[:600]
    head = re.sub(r"(?m)^[A-Za-z_-]+:", " ", head)
    return {word for word in re.findall(r"[a-z][a-z0-9]{3,}", head.lower()) if word not in STOPWORDS}


def installed_skills(root: pathlib.Path, home: pathlib.Path) -> dict[str, str]:
    """Name to SKILL.md text for the pack's two roots and the user's skills."""

    found: dict[str, str] = {}
    for directory in (root / "skills", root / "contrib", home / ".claude" / "skills"):
        for path in sorted(directory.glob(f"*/{SKILL_FILE}")) if directory.is_dir() else []:
            found.setdefault(path.parent.name, path.read_text(encoding="utf-8", errors="replace"))
    return found


def match(text: str, installed: dict[str, str], *, skip: set[str]) -> list[dict[str, Any]]:
    """The three installed skills whose name and description share the most words with this one."""

    mine = _words(text)
    scores: list[tuple[float, str]] = []
    for name, other in installed.items():
        theirs = _words(other)
        if name not in skip and mine & theirs:
            scores.append((round(len(mine & theirs) / len(mine | theirs), 2), name))
    ranked = sorted(scores, key=lambda score: (-score[0], score[1]))[:3]
    return [{"skill": name, "overlap": overlap} for overlap, name in ranked]


def _body(text: str) -> str:
    body = text.split("\n---", 1)[1] if text.startswith("---\n") and "\n---" in text else text
    return body.split("\n" + ADOPT.PROVENANCE_HEADING, 1)[0]


def value(text: str, matches: list[dict[str, Any]]) -> dict[str, Any]:
    lines = [line for line in _body(text).splitlines()[1:] if line.strip()]
    nearest = matches[0]["overlap"] if matches else 0.0
    return {"instruction_lines": len(lines), "novelty": round(1 - nearest, 2)}


def verdict(findings: list[dict[str, Any]], matches: list[dict[str, Any]], worth: dict[str, Any]) -> dict[str, str]:
    refused = sorted({f["rule"] for f in findings if f["severity"] == ADOPT.REFUSE})
    if refused:
        return {"action": "decline", "reason": "refused: " + ", ".join(refused)}
    if worth["instruction_lines"] < MIN_BODY_LINES:
        return {"action": "decline", "reason": f"value: under {MIN_BODY_LINES} instruction lines"}
    if matches and matches[0]["overlap"] >= FOLD_AT:
        return {"action": "fold", "reason": f"into {matches[0]['skill']}: overlap {matches[0]['overlap']}"}
    return {"action": "install", "reason": "no refusal, enough instructions, no close match"}


# --------------------------------------------------------------------------
# Where it goes, and what is there now
# --------------------------------------------------------------------------


def source_of(skill_dir: pathlib.Path) -> tuple[str, str] | None:
    """`(URL, commit)` from an installed skill's Provenance line, or None."""

    path = skill_dir / SKILL_FILE
    if path.is_symlink() or not path.is_file():
        return None
    found = PROVENANCE_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    return (found[1], found[2]) if found else None


def scope_roots(scope: str, root: pathlib.Path, home: pathlib.Path) -> list[pathlib.Path]:
    """Where a skill of this scope may live, the install root first."""

    return [root / "contrib", root / "skills"] if scope == "pack" else [home / ".claude" / "skills"]


def locate(name: str, scope: str | None, root: pathlib.Path, home: pathlib.Path) -> tuple[str, pathlib.Path, str]:
    """`(scope, directory, URL)` of an installed skill that records a GitHub source."""

    for each in ([scope] if scope else ["pack", "user"]):
        for directory in scope_roots(each, root, home):
            recorded = source_of(directory / name)
            if recorded:
                return each, directory / name, recorded[0]
    raise IntakeError(f"no installed skill {name} records a GitHub source; give its URL")


def installed_digests(directory: pathlib.Path) -> dict[str, str]:
    """Relative path to content digest for what is installed; a link is named, never followed."""

    if not directory.is_dir():
        return {}
    files = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():
            files[relative] = "symlink"
        elif path.is_file():
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def transform(candidate: dict[str, Any], claimed: str, target: str, today: str) -> dict[str, bytes]:
    """What lands on disk: the name moved to the target and the Provenance section written."""

    text = candidate["files"][SKILL_FILE][1].decode("utf-8", "replace")
    if target != claimed:
        text = text.replace(f"name: {claimed}", f"name: {target}", 1).replace(f"# {claimed}", f"# {target}", 1)
    digest = hashlib.sha256(candidate["files"][SKILL_FILE][1]).hexdigest()[:16]
    text = ADOPT.with_provenance(text, candidate["url"], f"{candidate['commit']} (sha256:{digest})", today, tool=TOOL)
    files = {name: body for name, (_mode, body) in candidate["files"].items()}
    files[SKILL_FILE] = text.encode("utf-8")
    return files


def _printable(text: str) -> str:
    """Text with control and format characters escaped, so a diff cannot drive the terminal."""

    return "".join(ch if ch in "\n\t" or unicodedata.category(ch) not in ("Cc", "Cf", "Co", "Cs")
                   else f"\\u{ord(ch):04x}" for ch in text)


def _lines(name: str, data: bytes | None) -> list[str]:
    if data is None:
        return []
    text = data.decode("utf-8", "replace")
    if name == SKILL_FILE:
        text = text.split("\n" + ADOPT.PROVENANCE_HEADING, 1)[0].rstrip("\n") + "\n"
    return text.splitlines(keepends=True)


def installed_diff(directory: pathlib.Path, files: dict[str, bytes]) -> list[str]:
    """Installed against upstream, file by file, Provenance left out of both sides."""

    names = sorted(set(installed_digests(directory)) | set(files))
    out: list[str] = []
    for name in names:
        path = directory / name
        installed = path.read_bytes() if path.is_file() and not path.is_symlink() else None
        out += difflib.unified_diff(_lines(name, installed), _lines(name, files.get(name)),
                                    f"installed/{name}", f"upstream/{name}")
    return [_printable(line.rstrip("\n")) for line in out]


def approval_revision(candidate: dict[str, Any], destination: pathlib.Path) -> str:
    """What an approval binds: the commit, the fetched bytes, the target and the installed copy."""

    bound = {"url": candidate["url"], "commit": candidate["commit"], "target": str(destination),
             "files": {name: [mode, hashlib.sha256(body).hexdigest()] for name, (mode, body) in candidate["files"].items()},
             "installed": installed_digests(destination)}
    return hashlib.sha256(json.dumps(bound, sort_keys=True).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------
# Install in steps, and finish or undo a stopped one
# --------------------------------------------------------------------------


def staging(destination: pathlib.Path) -> pathlib.Path:
    return destination.parent.parent / STAGING / destination.parent.name / destination.name


def _stage(stage: pathlib.Path, files: dict[str, bytes]) -> None:
    new = stage / "new"
    for name, body in files.items():
        path = new / name
        if not path.resolve().is_relative_to(new.resolve()):
            raise IntakeError(f"{name} resolves outside the skill")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        path.chmod(0o644)


def _swap_out(destination: pathlib.Path, stage: pathlib.Path) -> None:
    if destination.exists():
        os.replace(destination, stage / "old")


def _swap_in(destination: pathlib.Path, stage: pathlib.Path) -> None:
    os.replace(stage / "new", destination)


def _drop(stage: pathlib.Path) -> None:
    shutil.rmtree(stage)
    for parent in (stage.parent, stage.parent.parent):
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()


def install(destination: pathlib.Path, files: dict[str, bytes]) -> None:
    """Stage beside the root, move the old copy aside, move the new one in, drop the old.

    A stop between any two steps leaves state `recover` finishes or undoes.
    """

    stage = staging(destination)
    stage.mkdir(parents=True, exist_ok=True)
    _stage(stage, files)
    _swap_out(destination, stage)
    _swap_in(destination, stage)
    _drop(stage)


def recover(roots: list[pathlib.Path]) -> list[str]:
    """Finish or undo every install a stop left behind under these roots."""

    done = []
    for root in roots:
        base = root.parent / STAGING / root.name
        for stage in sorted(base.iterdir()) if base.is_dir() else []:
            destination = root / stage.name
            if (stage / "old").exists() and not destination.exists():
                os.replace(stage / "old", destination)
                done.append(f"undid a stopped install of {destination}: the previous copy is back")
            elif (stage / "old").exists():
                done.append(f"finished a stopped install of {destination}: dropped the previous copy")
            elif (stage / "new").exists():
                done.append(f"dropped an unfinished stage of {destination}")
            _drop(stage)
    return done


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


def _target(claimed: str, scope: str, url: str, root: pathlib.Path, home: pathlib.Path) -> tuple[pathlib.Path, list[dict[str, Any]]]:
    """Where the candidate lands, and any refusal of that name."""

    roots = scope_roots(scope, root, home)
    taken = {path.parent.name for each in roots for path in ADOPT.skill_files(each)}
    name = claimed if scope == "user" or claimed.startswith(ADOPT.PREFIX) else ADOPT.PREFIX + claimed
    destination = next((each / name for each in roots if (each / name).exists()), roots[0] / name)
    own = source_of(destination)
    if own and own[0] == url:
        taken.discard(name)
    _name, collisions = ADOPT.canonical_name(claimed, scope, taken)
    found = [_finding(f.severity, f.rule, SKILL_FILE, f.line) for f in collisions]
    if scope == "pack" and not PACK_NAME_RE.fullmatch(name):
        found.append(_finding(ADOPT.REFUSE, "pack-name-shape", SKILL_FILE, 1))
    return destination, found


def evaluate(source: str, scope: str | None, root: pathlib.Path, home: pathlib.Path, today: str) -> dict[str, Any]:
    """The report. Reads only, apart from finishing or undoing a stopped install."""

    recovered = recover(scope_roots("pack", root, home) + scope_roots("user", root, home))
    if source.startswith(GITHUB):
        url, scope = source, scope or "pack"
    else:
        scope, _directory, url = locate(source, scope, root, home)
    candidate = fetch_skill(url)
    text = candidate["files"][SKILL_FILE][1].decode("utf-8", "replace")
    claimed = (sd_lib.parse_frontmatter(text) or {}).get("name", "")
    if not ADOPT.SAFE_NAME_RE.match(claimed):
        # Checked before the name becomes a path: the report reads and diffs
        # what is installed there, and `../..` would name somewhere else.
        raise IntakeError(f"{url} declares no name that is one path segment; nothing to judge")
    findings = risk(candidate)
    destination, collisions = _target(claimed, scope, url, root, home)
    findings += collisions
    previous = source_of(destination)
    # A collision names someone else's skill: a diff against it would read as an update.
    files = {} if collisions else transform(candidate, claimed, destination.name, today)
    lines = installed_diff(destination, files) if files else []
    matches = match(text, installed_skills(root, home), skip={claimed, destination.name})
    worth = value(text, matches)
    mode = ("blocked" if collisions else "new" if not destination.exists()
            else "re-import" if lines else "unchanged")
    return {"url": url, "commit": candidate["commit"], "scope": scope, "skill": destination.name,
            "destination": str(destination), "mode": mode, "installed_commit": previous[1] if previous else None,
            "files": {name: mode_ for name, (mode_, _b) in sorted(candidate["files"].items())},
            "risk": findings, "match": matches, "value": worth, "verdict": verdict(findings, matches, worth),
            "diff": lines, "revision": approval_revision(candidate, destination), "recovered": recovered,
            "_files": files}


def intake(source: str, *, scope: str | None, approve: str | None, root: pathlib.Path,
           home: pathlib.Path, today: str) -> dict[str, Any]:
    """Evaluate; with `approve`, install the exact revision that report printed."""

    report = evaluate(source, scope, root, home, today)
    files = report.pop("_files")
    report["installed"] = False
    if approve is None:
        return report
    if approve != report["revision"]:
        raise IntakeError(f"approved revision {approve} is not this report's {report['revision']}: "
                          "the source, the target or the installed copy changed; nothing written")
    refused = [f["rule"] for f in report["risk"] if f["severity"] == ADOPT.REFUSE]
    if refused:
        raise IntakeError(f"a refusal blocks the install ({', '.join(sorted(set(refused)))}); nothing written")
    if report["mode"] in ("new", "re-import"):
        install(pathlib.Path(report["destination"]), files)
        report["installed"] = True
    return report


def report_text(report: dict[str, Any]) -> str:
    out = [f"skill: {report['skill']} ({report['scope']}) -> {report['destination']}",
           f"source: {report['url']} at {report['commit']}", f"mode: {report['mode']}"]
    out += [f"recovered: {line}" for line in report["recovered"]]
    out.append(f"risk: {len(report['risk'])} finding(s)")
    out += [f"  {f['severity']}: {f['rule']} in {f['file']}" + (f" line {f['line']}" if f["line"] else "")
            for f in report["risk"]]
    out.append("match: " + (", ".join(f"{m['skill']} {m['overlap']}" for m in report["match"]) or "none"))
    out.append(f"value: {report['value']['instruction_lines']} instruction lines, novelty {report['value']['novelty']}")
    out.append(f"verdict: {report['verdict']['action']} ({report['verdict']['reason']})")
    shown = report["diff"][:DIFF_LINES]
    out += ["diff:", *shown] if shown else ["diff: none"]
    if len(report["diff"]) > DIFF_LINES:
        out.append(f"... {len(report['diff']) - DIFF_LINES} more diff lines; --json holds them all")
    out.append(f"revision: {report['revision']}")
    if report["installed"]:
        out.append(f"installed: {report['destination']}")
    elif any(f["severity"] == ADOPT.REFUSE for f in report["risk"]):
        out.append("blocked: a refusal stops any install; nothing was written")
    elif report["mode"] == "unchanged":
        out.append("unchanged: the installed copy matches upstream; nothing to approve")
    elif report["mode"] in ("new", "re-import"):
        out.append(f"approve: sd skill intake {report['url']} --scope {report['scope']} --approve {report['revision']}")
    return "\n".join(out)


def run_intake(args: argparse.Namespace, root: pathlib.Path, home: pathlib.Path) -> int:
    report = intake(args.source, scope=args.scope, approve=args.approve, root=root, home=home,
                    today=datetime.date.today().isoformat())
    print(json.dumps(report, ensure_ascii=False) if args.json else report_text(report))
    return 0

