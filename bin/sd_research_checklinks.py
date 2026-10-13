#!/usr/bin/env python3
"""Verify every relative markdown link and backticked in-repo path resolves.

A backticked bare filename is prose, not a link: docs legitimately name files that
live in another repo or do not exist yet. Only backticked paths carrying a
`NN-dir/` segment are treated as claims about this repo.

Usage:  sd-research-kit checklinks        # from inside the research repo

`checklinks` takes no argument: it walks the repository you are standing in
(R10-D6). Exit 1 if anything is broken. Skips build/, vendor/, and .git/.
In a git repository it reads the tracked Markdown only, so an ignored
folder's notes never fail it (sd:3705).
"""
import os
import re
import sys
from pathlib import Path

from sd_lib import git_output

SKIP = ("build/", "vendor/", ".git/", "node_modules/", "__pycache__/")
LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+)")
PATH = re.compile(r"`([0-9]{2}-[a-z]+/[A-Za-z0-9._-]+\.md)`")


def markdown(repo):
    """The Markdown files to read: git's tracked ones, or every one on disk outside git."""
    listed = git_output(["ls-files", "--deduplicate", "-z", "--", "*.md"], Path(repo))
    if listed is not None:
        return [os.path.join(repo, name) for name in listed.split("\0") if name]
    found: list[str] = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if not any((d + "/").startswith(s) for s in SKIP)]
        found.extend(os.path.join(root, fn) for fn in files if fn.endswith(".md"))
    return found


def check(repo):
    repo = os.path.abspath(repo)
    bad = []
    for p in markdown(repo):
        root = os.path.dirname(p)
        if any(s.rstrip("/") in os.path.relpath(p, repo).split(os.sep) for s in SKIP) or not os.path.isfile(p):
            continue
        text = open(p).read()
        for m in list(LINK.finditer(text)) + list(PATH.finditer(text)):
            t = m.group(1)
            if t.startswith(("http://", "https://", "mailto:", "~", "/")):
                continue
            if m.re is LINK:
                if not os.path.exists(os.path.normpath(os.path.join(root, t))):
                    bad.append((os.path.relpath(p, repo), t))
            elif not os.path.exists(os.path.join(repo, t)):
                bad.append((os.path.relpath(p, repo), t))
    name = os.path.basename(repo)
    if bad:
        print("%-24s %d broken" % (name, len(bad)))
        for f, t in bad:
            print("   %s  ->  %s" % (f, t))
    else:
        print("%-24s ok" % name)
    return len(bad)


def main() -> int:
    # R10-D6: the repository is the one the caller is standing in. This took
    # `checklinks [repo_dir ...]` before the kit moved into the pack.
    return 1 if check(os.getcwd()) else 0


if __name__ == "__main__":
    sys.exit(main())
