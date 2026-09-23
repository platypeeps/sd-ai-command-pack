#!/usr/bin/env python3
"""Fail when the enumerated installer surface is not traced by `.coveragerc`.

`check-installer-coverage.sh` enumerates what it measures from git, with a
pathspec, at run time. What `coverage` actually traced was decided earlier and
somewhere else: the `[run] include` globs in `.coveragerc`, read by
`coverage run` and by `tests/coverage_sitecustomize/sitecustomize.py` for
subprocesses. One side is a glob resolved against the index; the other is a
list of patterns in a file nobody re-reads when a module lands.

Today they agree because the surface is one file. Land a second one --
`bin/sd_install_hooks.py` -- and git enumerates it, the gate announces "2
tracked file(s)", `[run] include` does not match it, so it is never traced, so
it carries no data, so it never reaches the report. The report covers the one
file it did trace at 100% and the gate is green: a 100% line-and-branch gate
certifying a file it never executed, while announcing it measured two.

Making `.coveragerc` carry the same glob would not close it. Git's default
pathspec matching runs wildmatch without WM_PATHNAME, so `bin/sd_install*.py`
reaches `bin/sd_install_core/helpers.py` -- which
`tests/test_installer_coverage_gate.py` pins on purpose. Coverage matches
`include` with `fnmatch`, where the same text also crosses `/`, but the two
dialects are not one text and nothing would keep them in step. So the two
sides stay as they are and this compares them: every enumerated path must be
matched by `[run] include`, and by `[report] include`, or the run fails naming
the path and the section that does not reach it.

`fnmatchcase` over absolute paths is the comparison because that is what both
readers do: `coverage.files.prep_patterns` makes a relative pattern absolute
against the working directory, and the lazy `sitecustomize` anchors the same
patterns against the directory holding the config file.
"""

from __future__ import annotations

import argparse
import configparser
import os
import pathlib
import sys

SECTIONS = ("run", "report")


def anchored(root: pathlib.Path, text: str) -> str:
    """`text` as an absolute, normalised path or pattern under `root`."""

    return os.path.normpath(os.path.join(str(root), text))


def patterns(parser: configparser.RawConfigParser, section: str) -> list[str] | None:
    """The `include` entries of `section`, or None when the section has none."""

    if not parser.has_section(section) or not parser.has_option(section, "include"):
        return None
    raw = parser.get(section, "include")
    return [line.strip() for line in raw.splitlines() if line.strip()]


def check(root: pathlib.Path, paths: list[str]) -> list[str]:
    """Every complaint about `paths` against `root/.coveragerc`, in order."""

    from fnmatch import fnmatchcase

    config = root / ".coveragerc"
    parser = configparser.RawConfigParser()
    try:
        read = parser.read(config)
    except (configparser.Error, OSError, UnicodeError) as exc:
        return [f"{config} could not be read: {exc}"]
    if not read:
        return [f"{config} does not exist, so nothing pins what coverage traces"]

    problems = []
    for section in SECTIONS:
        entries = patterns(parser, section)
        if entries is None:
            problems.append(
                f"[{section}] include is missing from {config.name}; the gate "
                "measures a surface nothing declares")
            continue
        globs = [anchored(root, entry) for entry in entries]
        for path in paths:
            target = anchored(root, path)
            if not any(fnmatchcase(target, glob) for glob in globs):
                problems.append(
                    f"{path} is in the enumerated installer surface and no "
                    f"[{section}] include pattern in {config.name} matches it "
                    f"({', '.join(entries)})")
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None,
                        help="repository root (default: this script's repository)")
    parser.add_argument("--paths-from", required=True,
                        help="file holding the enumerated surface, one path per line")
    args = parser.parse_args(argv[1:])

    root = (pathlib.Path(args.root) if args.root
            else pathlib.Path(__file__).resolve().parents[2])
    listed = pathlib.Path(args.paths_from).read_text(encoding="utf-8").splitlines()
    paths = [line.strip() for line in listed if line.strip()]
    if not paths:
        print("error: the enumerated installer surface is empty, so there is "
              "nothing to compare against .coveragerc.", file=sys.stderr)
        return 1

    problems = check(root, paths)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    if problems:
        print("A 100% gate over a file coverage never traced certifies a file "
              "it never executed. Add the path to .coveragerc [run] include "
              "(and [report] include) in the same pull request.", file=sys.stderr)
        return 1
    print(f"diagnostic: .coveragerc traces all {len(paths)} enumerated "
          f"installer path(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
