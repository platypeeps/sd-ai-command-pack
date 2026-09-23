"""The governed tree, read off the repository instead of typed out.

Criterion 4 of sd:10 calls it "what runs or governs", and two whole-tree greps
scan it: `tests/test_cut_symbols.py` and `tests/test_no_trellis_residue.py`.
Each used to declare its own ten-name tuple. The two were identical, nothing
compared them, and neither named `contrib/`, `hooks/` or `actions/` -- all
three tracked, all three things that run. `contrib/` holds `SKILL.md` files
that `sd skill try` installs and a model then executes; `hooks/pre-commit`
gates every commit. A cut symbol in either was invisible to both greps while
the comment above the tuple said the pathspec was what runs or governs.

Adding the three names would have fixed those three and left the next
directory. So the pathspec is enumerated: every top-level entry git tracks is
governed unless it is named here as history. A directory added to this
repository joins the greps by existing.

`HISTORY` is the whole of the judgment, and it is small on purpose:

* `CHANGELOG.md` and `docs/` record what happened. A grep that fails on a
  changelog entry naming a cut symbol is asking for the record to be
  falsified, which is the one thing a record must not permit.
* `docs/spec` is the exception inside the exception: a specification governs,
  so it comes back by name. It is the only subtree of `docs/` that does.

The exclusion is by top-level name rather than by pattern because that is what
a reader of the greps can check: `git ls-files | cut -d/ -f1 | sort -u` beside
`HISTORY` is the whole argument.
"""

from __future__ import annotations

import pathlib
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Top-level entries that record rather than govern. See the module docstring.
HISTORY = ("CHANGELOG.md", "docs")

#: Governed subtrees living inside a `HISTORY` entry, added back by name.
GOVERNED_INSIDE_HISTORY = ("docs/spec",)


def top_level(root: pathlib.Path | None = None) -> list[str]:
    """Every top-level entry git tracks in `root`, sorted."""

    base = REPO_ROOT if root is None else pathlib.Path(root)
    result = subprocess.run(
        ["git", "-C", str(base), "ls-files", "--deduplicate"],
        capture_output=True, text=True, check=True,
    )
    return sorted({line.split("/", 1)[0] for line in result.stdout.splitlines() if line})


def governed(root: pathlib.Path | None = None) -> tuple[str, ...]:
    """The governed pathspec: everything tracked except history.

    Returned as pathspecs for `git grep -- ...`, so a directory stands for
    every file under it and a file that lands there tomorrow is scanned
    without anyone editing a list.
    """

    base = REPO_ROOT if root is None else pathlib.Path(root)
    kept = [name for name in top_level(base) if name not in HISTORY]
    inside = [path for path in GOVERNED_INSIDE_HISTORY if (base / path).exists()]
    return tuple(kept + inside)


#: The pathspec both whole-tree greps scan. One object, so the two cannot
#: diverge: there is no second copy to drift from.
GOVERNED = governed()
