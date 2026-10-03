"""Sessions call pack commands by their PATH name, never by the checkout's absolute path (sd:1609).

On 2026-09-26 a session ran `sd-ship` through the pack checkout's absolute
path. The operator's permission rule `Bash(sd-ship:*)` matches the bare name
only, so every such call prompted. A session copies the form it reads, so the
guard is on the text it reads: no file in this repository may spell a command
as `<somewhere>/sd-ai-command-pack/bin/<command>`.

The files are enumerated from git, tracked and untracked alike, so a new page
is covered the day it is written. These places are exempt, each for a reason a
reader can check:

- `tests/`: fixtures that plant the form to prove this guard and its kin.
- `bin/sd_install.py`: the installer writes the absolute link targets that
  make the bare names resolve.
- `CHANGELOG.md` and `docs/work/archive/`: they record earlier statements,
  and AGENTS.md § What a Document Owns forbids rewriting them.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: A pack command named by the checkout's path rather than by its PATH name.
ABSOLUTE_INVOCATION = re.compile(r"sd-ai-command-pack/bin/[A-Za-z0-9_.-]+")

#: Path prefixes the guard does not read; the module docstring gives each reason.
EXEMPT = ("tests/", "bin/sd_install.py", "CHANGELOG.md", "docs/work/archive/")


def files(root: pathlib.Path) -> list[str]:
    """Every tracked or untracked, not ignored, file under `root`, relative to it."""
    listed = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            cwd=root, check=True, capture_output=True).stdout.decode()
    return sorted({name for name in listed.split("\0") if name})


def absolute_invocations(root: pathlib.Path) -> list[str]:
    """`path:line: match` for each absolute pack-command spelling outside the exempt places."""
    hits = []
    for name in files(root):
        if name.startswith(EXEMPT):
            continue
        path = root / name
        if path.is_symlink() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            hits.extend(f"{name}:{number}: {match}" for match in ABSOLUTE_INVOCATION.findall(line))
    return hits


class PackCommandsByName(unittest.TestCase):
    def test_no_page_calls_a_pack_command_by_the_checkouts_path(self) -> None:
        hits = absolute_invocations(REPO_ROOT)
        self.assertEqual(hits, [], "call these by their PATH name, as `sd-ship` and not "
                         "`.../sd-ai-command-pack/bin/sd-ship`; see tests/test_pack_bin_by_name.py")

    def test_the_guard_reads_new_pages_and_honours_only_its_exemptions(self) -> None:
        planted = "Run /Users/x/repos/platypeeps/sd-ai-command-pack/bin/sd-ship merge --item 1\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            for name in ("skills/sd-ship/SKILL.md", "README.md", *[f"{prefix}x.md" if prefix.endswith("/")
                                                                  else prefix for prefix in EXEMPT]):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(planted, encoding="utf-8")
            # Untracked, never added: a page is covered before its first commit.
            self.assertEqual(absolute_invocations(root), [
                "README.md:1: sd-ai-command-pack/bin/sd-ship",
                "skills/sd-ship/SKILL.md:1: sd-ai-command-pack/bin/sd-ship",
            ])
            (root / "README.md").write_text("Run sd-ship merge --item 1 from the checkout.\n", encoding="utf-8")
            self.assertEqual(absolute_invocations(root), ["skills/sd-ship/SKILL.md:1: sd-ai-command-pack/bin/sd-ship"])


if __name__ == "__main__":
    unittest.main()
