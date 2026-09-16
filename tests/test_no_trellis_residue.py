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
`RESIDUE` detectors are cut. Each entry is `(path, line text)`, the whole line
stripped of its indentation, so an edit above it does not move the exemption
off the line it names and an edit to the line itself -- a second literal
appended to an exempt one, say -- is not covered by it. A row that matches
no line, or more than one, fails `test_every_row_still_names_exactly_one_line`,
so neither set can outlive the lines it names or quietly widen.

`HELD` is a second, separate set: lines the sweep could not reach because
another lane's open pull request held the file. They are not the criterion's
exemptions and the docstring on the set says which pull request held them.
The criterion is closed when `HELD` is empty; until then
`test_the_held_set_is_named_and_shrinking` says what is left.
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

#: The exempt lines of decision note 1942, each as its path and its whole
#: text, stripped.
EXEMPT = frozenset({
    # The upstream pull-request guard, `AGENTS.md:7-10,31` at 2eafa78b.
    ("AGENTS.md",
     "- Do not create pull requests in the upstream `Trellis` repository without"),
    ("AGENTS.md",
     "`sd-ai-command-pack` work uncovers a `Trellis`-owned change, document the"),
    ("AGENTS.md",
     "finding and provide a paste-ready handoff instead of opening a `Trellis` PR."),
    ("AGENTS.md",
     "This scope exception does not authorize unrelated work or remove specific "
     "approval requirements for destructive actions or upstream Trellis PRs."),
    # The residue row, `bin/sd-status:1091-1093` at 2eafa78b.
    ("bin/sd-status", '".trellis",'),
    ("bin/sd-status", '"the Trellis state directory the pack replaced with docs/work",'),
    ("bin/sd-status", '"git rm -r --cached --ignore-unmatch .trellis && rm -rf .trellis",'),
    # Its test, `tests/test_sd_status.py:1115-1120` at 2eafa78b.
    ("tests/test_sd_status.py", '(self.repo / ".trellis").mkdir()'),
    ("tests/test_sd_status.py",
     '(self.repo / ".trellis" / "state.json").write_text("{}", encoding="utf-8")'),
    ("tests/test_sd_status.py", 'self.assertIn("rm -rf .trellis", found["trellis"]["remove"])'),
})

#: Lines the sweep of 2026-09-16 could not reach: both files were held by
#: #995 when it ran. Neither is a decision-note exemption; each is one word in
#: a list of dot-directories. The first edit that touches either file removes
#: the word and the row here with it, and the criterion is closed when this
#: set is empty.
HELD = frozenset({
    ("bin/sd", "`.makemd`, `.trellis`), so the rule is the generalisation rather than the"),
    ("skills/sd-plan/SKILL.md",
     "No unrelated rows, `.claude/`, `.trellis/`, hooks, labels, managed gitignore"),
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
        rows.append((path, int(number), text.strip()))
    return rows


def named_by(rows: list[tuple[str, int, str]], entries: frozenset[tuple[str, str]]) -> list[int]:
    """The line numbers of the rows an entry set names, one entry per row."""
    return [number for path, number, text in rows if (path, text) in entries]


class NoResidue(unittest.TestCase):
    def test_no_governed_line_names_the_framework_outside_the_exemptions(self):
        residue = [f"{path}:{number}:{text}" for path, number, text in governed_rows()
                   if (path, text) not in EXEMPT and (path, text) not in HELD]
        self.assertEqual([], residue, f"{len(residue)} lines still name the framework")

    def test_every_row_still_names_exactly_one_line(self):
        rows = governed_rows()
        for where, text in sorted(EXEMPT | HELD):
            with self.subTest(path=where, text=text):
                hits = [number for path, number, found in rows
                        if path == where and found == text]
                self.assertEqual(1, len(hits), f"{where}: {text!r} names lines {hits}")

    def test_the_held_set_is_named_and_shrinking(self):
        """At most the two files #995 held, and no row in both sets."""

        self.assertLessEqual({path for path, _ in HELD}, {"bin/sd", "skills/sd-plan/SKILL.md"})
        self.assertTrue(EXEMPT.isdisjoint(HELD))


if __name__ == "__main__":
    unittest.main()
