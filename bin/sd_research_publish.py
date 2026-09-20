#!/usr/bin/env python3
"""Register a research repo with the dashboard, and queue its outward mirrors.

The publication contract is
`skills/_shared/references/publication-contract.md`; this is the half of it a
script can carry out. Two jobs, both run at the end of `render`:

1. **Register.** Append this repo's `root|key|label|directory` line to the
   dashboard's `documents.conf`, once. The dashboard reads that file and never
   writes it, so nothing here touches the dashboard's own source.

2. **Enqueue.** For each document designated for a destination in
   `DESTINATIONS`, write a sync request naming the document, its container, the
   page or file to update and the source revision. Rendering runs in a git hook
   and in CI, neither of which can reach an MCP server, and the pack holds no
   credential for any destination -- so a render never calls one and does not
   try. An agent session drains the queue.

One queue for every destination rather than one queue each, and one request
file per document *per destination*: a document designated for two places is
two independent pieces of outstanding work, and either can drain while the
other waits. The filename carries the repo, the document and the destination,
so a re-render overwrites the pending request rather than queueing a second.

A request that is never drained stays on disk: the queue does not expire,
because an expiring queue reports a mirror as done that was never written.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple

from sd_lib import git_output

#: Where the dashboard checkout lives. Overridable because a fleet machine may
#: hold it elsewhere; not discovered by searching, because a search that found
#: two checkouts would have to guess which one the browser is serving.
DASHBOARD_HOME = Path(
    os.environ.get("SD_DASHBOARD_HOME", "~/repos/system/local-project-dashboard")
).expanduser()

#: Durable, outside any repo, and beside the vault-write queue that already
#: works this way. `~/.claude/` and not `/tmp`: a request that a reboot deletes
#: is a mirror nobody knows went missing. One queue for every destination:
#: `bin/sd-status` reads it, and a queue per destination would mean a producer
#: and a status class per destination, which `actionable_inventory` already
#: refuses for the same reason (C-3, one producer and not three).
QUEUE = Path(
    os.environ.get("SD_MIRROR_QUEUE", "~/.claude/pending-mirror-syncs")
).expanduser()


class Destination(NamedTuple):
    """One place a document may be designated for, and what naming it takes.

    The dashboard is deliberately absent: it is the default, it takes no
    designation, and a render writes it rather than queueing it.

    `where` is required because a mirror with no container has nowhere to go.
    `what` is optional: absent, the drain creates the page or file and the
    designation can be amended with the id it got; present, the drain updates
    that one rather than creating a second copy on every render.
    """

    #: The DOCS key the user writes, and the `destination` field of a request.
    name: str
    #: The required field: the container the mirror is written into.
    where: str
    #: The optional field: the existing page or file to update in place.
    what: str
    #: How a report and a status row name the container, in words.
    noun: str


#: Adding a destination is a row here plus a drain step in the contract. It is
#: deliberately not open-ended: an unknown key in a DOCS entry is a typo, and a
#: table that accepted anything would queue a mirror to a place nothing drains.
DESTINATIONS = (
    Destination("notion", "space", "page", "Notion space"),
    Destination("drive", "folder", "file", "Drive folder"),
)

#: The dashboard builds a URL from the key, so the key is what a URL may carry.
#: Mirrored from `sd_dashboard/documents.py`, which rejects anything else.
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def documents_conf() -> Path:
    return DASHBOARD_HOME / "documents.conf"


def repo_key(repo: Path) -> str:
    """A short lowercase key from the directory name.

    Derived and not configured: a key the repo chose for itself could collide
    with another repo's, and the collision would surface as one repo's
    documents silently replacing the other's in the listing.
    """
    stem = repo.name.lower()
    stem = re.sub(r"[^a-z0-9._-]+", "-", stem).strip("-.")
    return stem or "docs"


def register_root(repo: Path, label: str, directory: Path) -> str:
    """Add this repo's root line to `documents.conf` if it is not there.

    Returns a one-line report. Never raises on a missing dashboard: a machine
    without the dashboard checked out still renders its documents, and failing
    the render would make the reading form hostage to the listing.
    """
    conf = documents_conf()
    if not conf.is_file():
        return "dashboard not registered: no %s" % conf

    key = repo_key(repo)
    if not KEY.fullmatch(key):
        return "dashboard not registered: %r is not a usable key" % key

    # `~` and not the absolute path: `documents.conf` is shared across machines,
    # and an absolute path under one machine's home is wrong on the next.
    home = str(Path.home())
    shown = str(directory)
    if shown == home or shown.startswith(home + os.sep):
        shown = "~" + shown[len(home) :]

    line = "root|%s|%s|%s" % (key, label, shown)
    text = conf.read_text(encoding="utf-8")
    for existing in text.splitlines():
        parts = [p.strip() for p in existing.strip().split("|")]
        if len(parts) == 4 and parts[0] == "root" and parts[1] == key:
            if existing.strip() == line:
                return "dashboard: already registered as %s" % key
            return "dashboard: %s already names %s; left alone" % (key, parts[3])

    with conf.open("a", encoding="utf-8") as handle:
        if not text.endswith("\n"):
            handle.write("\n")
        handle.write(line + "\n")
    return "dashboard: registered %s -> %s" % (key, shown)


def revision(repo: Path) -> str:
    """The commit the render was made from, or `unknown` outside a checkout.

    Through `sd_lib.git_output` rather than a subprocess call of its own:
    `tests/test_git_policy.py` allows one git policy in `bin/`, and a second
    would mean a second timeout and a second answer to what a failure means.
    """
    return git_output(["rev-parse", "HEAD"], repo) or "unknown"


def mirror_targets(cfg: dict[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    """The destinations this DOCS entry designates, and what was wrong.

    A document publishes to the dashboard and nowhere else until one of these
    keys exists. The user designates a document and names its container at that
    time; nothing here infers a destination from a title, a path or a neighbour,
    and nothing promotes a document because it looks finished.

    Returns a list because a document may be designated for several places at
    once. `notion=` and `drive=` on one entry are two mirrors, not a choice.

    Problems are returned rather than raised, and returned *per destination*.
    A malformed designation is the user's to fix, and one bad key must not cost
    the other destination its request: the dashboard copy is written either way,
    so withholding a valid mirror would punish the destination that was fine.
    """
    targets: list[dict[str, str]] = []
    problems: list[str] = []
    for dest in DESTINATIONS:
        raw = cfg.get(dest.name)
        if not raw:
            continue
        if not isinstance(raw, dict):
            problems.append(
                "%s= must be a dict, not %s" % (dest.name, type(raw).__name__)
            )
            continue
        where = str(raw.get(dest.where, "")).strip()
        if not where:
            problems.append("%s= needs a %s" % (dest.name, dest.where))
            continue
        targets.append({
            "destination": dest.name,
            dest.where: where,
            dest.what: str(raw.get(dest.what, "")).strip(),
            # Worded here rather than by whoever reads the request. `sd-status`
            # prints this verbatim, so it never has to carry a second copy of
            # the destination table to say which place a row is waiting on.
            "target": "the %s %s" % (where, dest.noun),
        })
    return targets, problems


def enqueue(repo: Path, docs: list[dict[str, Any]]) -> list[str]:
    """Write one sync request per document per designated destination."""
    reports: list[str] = []
    wanted: list[tuple[dict[str, Any], dict[str, str]]] = []
    for cfg in docs:
        targets, problems = mirror_targets(cfg)
        reports += ["mirror: %s in %s" % (p, cfg.get("out", "?")) for p in problems]
        wanted += [(cfg, target) for target in targets]
    if not wanted:
        return reports

    QUEUE.mkdir(parents=True, exist_ok=True)
    rev = revision(repo)
    key = repo_key(repo)
    for cfg, target in wanted:
        out = str(cfg.get("out", "")).strip()
        src = str(cfg.get("src", "")).strip()
        request = {
            "repo": str(repo),
            "revision": rev,
            "document": out,
            "title": cfg.get("title", out),
            "source": str(repo / src) if src else "",
            "rendered": str(repo / "build" / (out + ".html")),
        }
        request.update(target)
        path = QUEUE / ("%s.%s.%s.json" % (key, out or "doc", target["destination"]))
        path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
        reports.append("mirror: queued %s -> %s" % (out, target["target"]))
    return reports


def publish(repo: Path, project: str, docs: list[dict[str, Any]]) -> list[str]:
    """Both jobs, in the order the contract states them."""
    build = repo / "build"
    reports = [register_root(repo, project or repo.name, build)]
    reports += enqueue(repo, docs)
    return reports


#: The hook that keeps `build/` current, as text rather than as a file beside
#: the skill. Two rules put it here, both pinned by
#: `tests/test_no_shipped_shell.py`: `skills/` is the render surface and is
#: markdown only, because a file there is payload copied onto a platform home;
#: and the pack ships no shell outside `.github/scripts/`. So the hook is
#: Python, stdlib only, and it lives in the module that installs it. It carries
#: `#` comments rather than a docstring because it is itself inside one.
HOOK = '#!/usr/bin/env python3\n# Re-render this research repo after a commit that touched a document.\n#\n# Installed by `sd-research-kit init-hook`. Post-commit and not pre-commit:\n# `build/` is generated and not committed, so there is nothing to stage, and\n# the commit is the revision a queued mirror should name.\n#\n# Rendered output goes stale the moment its source changes, and a stale page is\n# worse than a missing one because it looks current. This is what keeps the\n# dashboard\'s Documents tab a statement about the render rather than about who\n# remembered to run it.\n#\n# Never fails the commit. The commit is already made when this runs, so exiting\n# non-zero would report a failure for work that succeeded. A render that cannot\n# run says so and leaves the commit alone.\n#\n# `SD_SKIP_RENDER=1 git commit` skips it.\n\nimport os\nimport shutil\nimport subprocess\nimport sys\n\n\ndef main():\n    if os.environ.get("SD_SKIP_RENDER"):\n        return 0\n    try:\n        root = subprocess.run(\n            ["git", "rev-parse", "--show-toplevel"],\n            capture_output=True, text=True, timeout=30, check=True,\n        ).stdout.strip()\n        if not os.path.isfile(os.path.join(root, "research.conf.py")):\n            return 0\n        # Only when the commit carried a document. A commit touching nothing\n        # but the config or a script still renders: both change the output.\n        changed = subprocess.run(\n            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],\n            cwd=root, capture_output=True, text=True, timeout=30, check=True,\n        ).stdout.split()\n    except (OSError, subprocess.SubprocessError):\n        return 0\n    if not any(name.endswith((".md", ".py")) for name in changed):\n        return 0\n\n    kit = shutil.which("sd-research-kit")\n    if kit is None:\n        print("post-commit: sd-research-kit not on PATH; build/ is now stale",\n              file=sys.stderr)\n        return 0\n    try:\n        subprocess.run([kit, "render"], cwd=root, timeout=600, check=True)\n    except (OSError, subprocess.SubprocessError):\n        print("post-commit: render failed; build/ is now stale", file=sys.stderr)\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'


def init_hook_main() -> int:
    """Install the post-commit re-render hook in this repo.

    Written and not symlinked: a research repo is not a worktree of the pack,
    and a symlink into a checkout the repo does not own breaks the moment the
    pack moves. A file already at the path is refused by name and left alone --
    the same rule `make hooks` follows for the pack's own hook.
    """
    repo = Path.cwd()
    if not (repo / "research.conf.py").is_file():
        print("no research.conf.py in %s" % repo, file=sys.stderr)
        return 2
    # The common directory, not `.git`: a linked worktree's hooks live in the
    # main checkout's, and installing into the worktree's own would give one
    # branch a hook every other branch does not have.
    common = git_output(["rev-parse", "--path-format=absolute", "--git-common-dir"], repo)
    if not common:
        print("not a git repository: %s" % repo, file=sys.stderr)
        return 1

    target = Path(common) / "hooks" / "post-commit"
    wanted = HOOK
    if target.exists():
        if target.read_text(encoding="utf-8", errors="replace") == wanted:
            print("hook: already installed at %s" % target)
            return 0
        print("error: %s exists and is not this hook; move it aside first" % target, file=sys.stderr)
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(wanted, encoding="utf-8")
    target.chmod(0o755)
    print("hook: installed %s" % target)
    return 0


def publish_main() -> int:
    """The `publish` verb. Named like `init_hook_main` and
    `sd_research_review.init_main`, not `main`: every `bin/` module carrying a
    `main` puts one more name the dead-code check cannot speak for into
    `tests/test_code_health.py`'s ambiguous set, and that ceiling is downward
    only.
    """
    repo = Path.cwd()
    conf = repo / "research.conf.py"
    if not conf.is_file():
        print("no research.conf.py in %s" % repo, file=sys.stderr)
        return 2
    ns: dict[str, Any] = {}
    # nosec B102 - same trust level as the render it mirrors; see sd_research_render.
    exec(compile(conf.read_text(encoding="utf-8"), str(conf), "exec"), ns)  # nosec B102
    project = ns.get("PROJECT", repo.name)
    for line in publish(repo, project, ns.get("DOCS", [])):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(publish_main())
