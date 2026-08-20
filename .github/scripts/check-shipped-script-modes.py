#!/usr/bin/env python3
"""Enforce the executable bit on shipped pack helper scripts.

``sd-ai-command-pack-toolchain.sh run --`` ends in ``exec "$RUN_COMMAND"``, so a
helper the toolchain resolves must carry the executable bit or the invocation
dies with ``Permission denied``. Three generators already conclude
"executable" for exactly this set -- ``installer/machinepayload.py``,
``.github/scripts/generate-plugin.py``, and the repo-install path in
``installer/fileops.py`` -- so every installed copy is ``755``. Only the
repository's own tracked modes were left behind, and a mode is invisible in
diff review, which is why this is a gate rather than a matter of care.

Two properties, enforced in both directions:

* a tracked file whose blob starts ``#!`` is ``100755``;
* unless its basename starts with ``LIBRARY_PREFIX``, in which case it is an
  importable module and is ``100644``.

``LIBRARY_PREFIX`` is imported, not restated. The defect this gate exists to
prevent is one bit with two derivations; a third copy of the constant would
re-create it. It is a *basename* prefix, matched with ``PurePosixPath().name``:
a substring match would also exempt any future directory containing the string.

Scope is the three trees that carry shipped helpers. It is deliberately not the
repository: ``.github/workflows/tests.yml`` reads the prior revision's mode for
``.github/scripts/bookkeeping_ci_scope.py`` and treats anything but ``100644``
as untrusted, falling back to the full lane. That guard fails *open*, so making
those files executable would silently disable fast-lane selection while CI
stayed green.

Modes are read from ``git ls-files -s`` -- the index, not the filesystem. A
checkout with ``core.fileMode`` disabled lets the two disagree, and the index is
what ships.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
from pathlib import PurePosixPath
from typing import NamedTuple

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from installer.machinepayload import LIBRARY_PREFIX  # noqa: E402

TREES: tuple[str, ...] = (
    "scripts",
    "templates/scripts",
    ".sd-ai-command-pack/bin",
)

EXECUTABLE_MODE = "100755"
REGULAR_MODE = "100644"
SHEBANG = b"#!"


class Finding(NamedTuple):
    label: str
    mode: str
    path: str
    remedy: str

    def __str__(self) -> str:
        return f"{self.label} {self.mode} {self.path} -- {self.remedy}"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def is_script(oid: str) -> bool:
    blob = subprocess.run(
        ["git", "cat-file", "blob", oid],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return blob[:2] == SHEBANG


def main(argv: list[str]) -> int:
    findings: list[Finding] = []
    scanned = 0
    for line in git("ls-files", "-s", *TREES).splitlines():
        meta, _, path = line.partition("\t")
        mode, oid, _stage = meta.split()
        if not is_script(oid):
            continue
        scanned += 1
        if PurePosixPath(path).name.startswith(LIBRARY_PREFIX):
            if mode != REGULAR_MODE:
                findings.append(Finding(
                    "LIB-EXEC", mode, path,
                    f"an importable {LIBRARY_PREFIX}* module is executable; "
                    f"repair with: git update-index --chmod=-x {path}",
                ))
        elif mode != EXECUTABLE_MODE:
            findings.append(Finding(
                "NOT-EXEC", mode, path,
                "a shipped helper is not executable, so `run --` dies with "
                f"Permission denied; repair with: chmod +x {path} && "
                f"git update-index --chmod=+x {path}",
            ))
    if findings:
        print(
            f"error: {len(findings)} shipped-script mode violation(s) "
            f"across {scanned} tracked script(s):",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1
    print(
        f"shipped script modes: {scanned} tracked script(s) clean across "
        f"{len(TREES)} tree(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
