"""A grep of the governed tree for the retired framework's name returns nothing
outside a named exemption set (sd:10, criterion 18).

The three literals are the criterion's own: the framework's name with its
capital, its dot-directory, and its task script. The grep is case-sensitive
for the same reason: an identifier that carries the name in lower case is not
a claim that the framework is still here, and the criterion does not count it.

The exemptions are the lines decision note 1942 on sd:10 named, and nothing
else: the upstream pull-request guard in `AGENTS.md`, exempt while sd:241,
sd:242 and sd:244 are open, and the `.trellis` residue row of `sd-status` with
the test that exercises it, exempt until the gating fleet check passes and the
`RESIDUE` detectors are cut. Each entry is `(path, fragment)`, keyed by the
text of the line rather than its number, so an edit above it does not move
the exemption off the line it names. A fragment that matches no line, or more
than one, fails `test_every_exemption_still_names_exactly_one_line`, so the
set cannot outlive the lines it exempts or quietly widen. Two further rows
carry a word each in files another lane held when the sweep ran; they are
marked as such and are not the criterion's exemptions.
"""

from __future__ import annotations

import pathlib
import subprocess
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

SELF = "tests/test_no_trellis_residue.py"

#: What runs or governs, as `prd.md` criterion 4 of sd:10 defines it.
#: `docs/work/` and `CHANGELOG.md` are history and are excluded by name.
GOVERNED = (
    "bin",
    "skills",
    "agents",
    "dashboard",
    "tests",
    ".claude",
    ".github",
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "docs/spec",
)

#: Criterion 18's three literals, dots escaped, as one alternation.
PATTERN = r"Trellis|\.trellis|task\.py"

#: The exempt lines, each as the path and a fragment unique to that line.
EXEMPT = frozenset({
    # The upstream pull-request guard, `AGENTS.md:7-10,31` at 2eafa78b.
    ("AGENTS.md", "upstream `Trellis` repository"),
    ("AGENTS.md", "a `Trellis`-owned change"),
    ("AGENTS.md", "opening a `Trellis` PR"),
    ("AGENTS.md", "upstream Trellis PRs"),
    # The residue row, `bin/sd-status:1091-1093` at 2eafa78b.
    ("bin/sd-status", '".trellis",'),
    ("bin/sd-status", "the Trellis state directory the pack replaced"),
    ("bin/sd-status", "git rm -r --cached --ignore-unmatch .trellis"),
    # Its test, `tests/test_sd_status.py:1115-1120` at 2eafa78b.
    ("tests/test_sd_status.py", '(self.repo / ".trellis").mkdir()'),
    ("tests/test_sd_status.py", '(self.repo / ".trellis" / "state.json")'),
    ("tests/test_sd_status.py", 'assertIn("rm -rf .trellis"'),
    # Two lines the sweep could not reach: both files were held by another
    # lane's open pull request (#995) when it ran. Neither is a decision-note
    # exemption; each is one word in a list of dot-directories, and the first
    # edit that touches either file removes the word and the row here with it.
    ("bin/sd", "`.makemd`, `.trellis`), so the rule"),
    ("skills/sd-plan/SKILL.md", "`.claude/`, `.trellis/`, hooks, labels"),
})


def governed_rows() -> list[tuple[str, int, str]]:
    """Every `(path, line, text)` in the governed tree matching `PATTERN`.

    This file is excluded: it quotes every literal it searches for, and a test
    that matches itself measures nothing.
    """
    result = subprocess.run(
        ["git", "grep", "-nIE", PATTERN, "--", *GOVERNED, f":(exclude){SELF}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise AssertionError(result.stderr.strip())
    rows = []
    for line in result.stdout.splitlines():
        path, number, text = line.split(":", 2)
        rows.append((path, int(number), text))
    return rows


def exempted(row: tuple[str, int, str]) -> bool:
    path, _, text = row
    return any(path == where and fragment in text for where, fragment in EXEMPT)


class NoResidue(unittest.TestCase):
    def test_no_governed_line_names_the_framework_outside_the_exemptions(self):
        residue = [f"{path}:{number}:{text}" for path, number, text in governed_rows()
                   if not exempted((path, number, text))]
        self.assertEqual([], residue, f"{len(residue)} lines still name the framework")

    def test_every_exemption_still_names_exactly_one_line(self):
        rows = governed_rows()
        for where, fragment in sorted(EXEMPT):
            with self.subTest(path=where, fragment=fragment):
                hits = [number for path, number, text in rows
                        if path == where and fragment in text]
                self.assertEqual(1, len(hits), f"{where}: {fragment!r} names lines {hits}")


if __name__ == "__main__":
    unittest.main()
