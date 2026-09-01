"""Skills: what this pack ships, and what is actually installed for the agent.

Two directories and the difference between them. The pack's `skills/` is what
the repository offers; `~/.claude/skills` is what the agent will actually
find. Nothing keeps them in step -- installation is a deliberate act -- so the
gap is a fact worth rendering rather than a bug to prevent.

**Enumerated from the filesystem, both sides.** A manifest listing which
skills exist would go stale the first time one was added, which is the same
argument `discover_checkouts` and `work.py` already make. The directory is the
index.

Named without reading the body: a `SKILL.md` is a document, there are hundreds
across the two trees, and the frontmatter answers everything this view asks.
"""

from __future__ import annotations

from pathlib import Path

# Far enough to clear the frontmatter of a file whose body is prose.
FRONTMATTER_LINES = 20
INSTALLED = Path.home() / ".claude" / "skills"


def described(path: Path) -> dict:
    """`name` and `description` from a SKILL.md, or empty strings.

    Not a YAML parser: these are `sd` templates, the values are scalars, and
    a nested key is not a field this view has any use for.
    """
    fields = {"name": "", "description": ""}
    try:
        with (path / "SKILL.md").open(encoding="utf-8", errors="replace") as handle:
            if handle.readline().strip() != "---":
                return fields
            for _ in range(FRONTMATTER_LINES):
                line = handle.readline()
                if not line or line.strip() == "---":
                    break
                key, sep, value = line.partition(":")
                if sep and key.strip() in fields and not key[:1].isspace():
                    fields[key.strip()] = value.strip()
    except OSError:
        return fields
    return fields


def names(root: Path) -> set[str]:
    """Directories holding a SKILL.md. A directory alone is not a skill here.

    The opposite of `work.py`'s rule, and deliberately: an unfinished work
    item is the thing that view exists to surface, while a directory under
    `skills/` with no SKILL.md is invisible to the agent and so is not
    something the agent can be said to have.
    """
    if not root.is_dir():
        return set()
    return {item.name for item in root.iterdir()
            if item.is_dir() and (item / "SKILL.md").is_file()}


def collect_skills(pack: Path, installed: Path | None = None) -> dict:
    """What ships here, what is installed, and which way each gap runs."""
    target = INSTALLED if installed is None else installed
    shipped, live = names(pack / "skills"), names(target)
    rows = []
    for name in sorted(shipped | live):
        rows.append({
            "name": name,
            "shipped": name in shipped,
            "installed": name in live,
            "description": described(
                (pack / "skills" if name in shipped else target) / name
            )["description"],
        })
    return {
        "skills": rows,
        # Counted rather than derived in the page: a view showing a hundred
        # rows without saying how many of them agree is an inventory again.
        "counts": {
            "shipped": len(shipped),
            "installed": len(live),
            "unadopted": len(shipped - live),
            "foreign": len(live - shipped),
        },
        "installedAt": str(target),
        "installedExists": target.is_dir(),
    }
