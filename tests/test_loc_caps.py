"""The three line-count ceilings, enforced instead of remembered.

The design fixes a ceiling for each part of the replacement world -- `bin/` at
14,000 lines (R11-D15, re-derived from built code after 8,000 was busted with
six of the eleven commands still unwritten -- `sd-plan`, `sd-ship`, `sd-spec`,
`sd-deps`, `sd-suggest`, `sd-map`), the temporary `migrate-*` tools at 1,500
outside it, `dashboard/` at 4,350 with 2,300 of it carrying code (R11-D24, with the total
re-derived at R11-D29) -- and says in as many words that "caps are
CI tests; a cap is never raised in the PR that busts it". That rule survives
every re-derivation: 14,000, 4,000 and 4,300 were each set in their own
decision record by a change that fit under the ceiling it replaced, not in a
pull request that did not fit. 4,350 was set the same way at R11-D29, by a
change touching this file and one design record and nothing under `dashboard/`,
while the directory stood at 4,190 against the 4,300 it replaced.

**Downward-only now attaches to the code cap, not to the dashboard total.**
R11-D17 said 4,000 could only fall; R11-D24 raised it anyway, and said so in
its own record rather than in the change that crossed it. The reason is the
thing this file measures: 46% of `dashboard/` is comments, docstrings and
blanks, which is house style, and one ceiling over both halves means a branch
and a paragraph bid for the same line -- the paragraph loses, because the
branch is what the change is for. So the total may be re-derived with an
itemisation, and `DASHBOARD_CODE_CAP` is the one that may only move downward.
`bin/`'s 14,000 keeps the original clause, untouched and nowhere near binding.

Until now they were prose. The retired stack this repository is replacing
reached 95,000 lines one defensible commit at a time, and no single one of
those commits looked like the problem, which is
exactly why the bound has to be mechanical: a number in a design document is
checked by whoever remembers to check it.

Landing the test while every cap passes is deliberate. A cap introduced in the
change that breaks it is a negotiation; a cap introduced with headroom is a
guard, and the next pull request that would cross the line meets a red check
instead of a reviewer's memory.

**Enumerated from `git ls-files`, never from a list here.** Two reasons, both
learned rather than assumed. A hand-written list of files cannot see the
thirteenth one somebody adds next month -- the same trap the Makefile's lint
paths still carry. And walking the directory instead would count whatever is
lying in it: `find bin -type f` once reported this repository at 8,862 lines,
over its own cap, because it swept up `__pycache__/*.pyc`. The index holds
tracked source and nothing else, so it answers the question actually being
asked.
"""

from __future__ import annotations

import io
import pathlib
import shutil
import subprocess
import tempfile
import tokenize
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Each cap names the design decision it enforces, so a failure points at the
# record rather than at a bare number.
BIN_CAP = 14_000           # R11-D15: derived from built code, not from unwritten scope
MIGRATE_CAP = 1_500        # temporary tools, outside the bin/ cap, deleted at steps 7 and 11
# R11-D29, re-derived 2026-09-03 with the itemisation R11-D24's clause asks
# for: 4,190 measured on `main`, 158 measured on the branch that carries the
# dashboard ack-and-mutation-count item, 2 unclaimed. Both figures came off
# `line_count(tracked("dashboard"))` below rather than out of an estimate.
#
# It is a plain number, and one round of review was spent finding out why it
# has to be. The clause forbids raising a cap in the pull request that needs
# it, which leaves a window where capacity exists that no landed change has
# claimed; the attempt to close that window made this constant conditional on
# a work item's `implement.md` being present, so that an abandoned item took
# its reservation with it. That is worse. `sd-plan` sweeps merged items to
# `docs/work/archive/YYYY-MM/`, so the routine archive commit would have moved
# the file, dropped the ceiling back to 4,300 under a directory holding 4,348
# lines in total, and turned a bookkeeping commit into a red build. A ceiling that
# depends on where a document currently lives is not a ceiling.
#
# So the window stays open and is named instead: 2 lines, on `main`, until the
# reserved branch lands -- 14 when this was first written, narrowed by the
# branch's own remediation. That is the price of the clause, and it is smaller
# than the cost of the mechanism that tried to remove it.
DASHBOARD_CAP = 4_350


# The half that cannot be paid for with prose. R11-D24 split the dashboard
# ceiling in two because a single total let a docstring and a branch compete
# for the same line, and 6b-7 was spent deleting rationale to fit a write path
# -- which is the cap working against the comment convention it was explicitly
# widened to hold. This one bounds what the other cannot: code.
DASHBOARD_CODE_CAP = 2_300 # R11-D24: the half a docstring cannot buy back


def tracked(*pathspecs: str) -> list[pathlib.Path]:
    """Tracked files matching `pathspecs`, as the index reports them."""

    output = subprocess.run(
        ["git", "ls-files", "-z", "--", *pathspecs],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / name for name in output.split("\0") if name]


# Everything that is not a line of code: a comment, a docstring, a blank. The
# string tokens are the load-bearing exclusion -- roughly half of every Python
# file here is docstring, which is house style and the reason a code-only
# measure had to exist at all.
NOT_CODE = frozenset({
    tokenize.COMMENT, tokenize.STRING, tokenize.NL, tokenize.NEWLINE,
    tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER,
})


def code_line_count(paths: list[pathlib.Path]) -> int:
    """Lines carrying code, with comments, docstrings and blanks left out.

    Python is tokenised rather than pattern-matched, because the alternative
    is a regex that cannot tell `# a comment` from `url = "http://x/#frag"`
    and would drift in whichever direction its author was hoping for.

    JavaScript has no tokeniser in the standard library, so it is measured by
    the crude rule -- a non-blank line that does not open with `//`. That is
    **conservative on purpose**: it counts a `/* */` block as code, so the
    error can only tighten this cap, never loosen it. `dashboard/app.js` holds
    no block comment today and the measure is checked, not assumed.

    Every other suffix carries no code and is not counted. The rule is stated
    by extension rather than as "not Python", because a `README.md` measured
    by the JavaScript rule is every line of prose counted as code, failing
    this cap for a reason that has nothing to do with what it protects. Such a
    file still charges the total cap, which is where a large one belongs; and
    should `dashboard/` ever hold a third language, this returns too low until
    somebody adds it, so the omission surfaces as headroom that does not
    behave, not as a silent pass. Found in review.
    """

    total = 0
    for path in paths:
        # The suffix decides before the file is opened. Reading first would
        # make "every other suffix counts nothing" fail on the one case it
        # most obviously covers -- an icon or a font under `dashboard/`, which
        # is not text and would raise rather than be ignored. Found in review.
        if path.suffix not in {".py", ".js"}:
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".js":
            total += sum(
                1 for line in text.splitlines()
                if line.strip() and not line.strip().startswith("//")
            )
            continue
        seen = set()
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type not in NOT_CODE and token.string.strip():
                seen.add(token.start[0])
        total += len(seen)
    return total


def line_count(paths: list[pathlib.Path]) -> int:
    total = 0
    for path in paths:
        # A tracked path can be absent from the working tree during a partial
        # checkout. Counting it as zero would understate the total and let a
        # cap pass for the wrong reason, so it is an error, not a skip.
        with path.open(encoding="utf-8") as handle:
            total += sum(1 for _ in handle)
    return total


class LineCountCaps(unittest.TestCase):
    def assert_cap(self, label: str, paths: list[pathlib.Path], cap: int) -> int:
        total = line_count(paths)
        self.assertLessEqual(
            total,
            cap,
            f"{label} is {total} lines against a cap of {cap}. The cap is a design "
            f"decision, not a lint setting: raise it in its own change with its own "
            f"record, never in the pull request that crossed it. Files counted: "
            f"{', '.join(sorted(str(p.relative_to(REPO_ROOT)) for p in paths))}",
        )
        return total

    def test_bin_stays_under_its_ceiling(self) -> None:
        """`bin/` minus the temporary migration tools, which have their own cap."""

        paths = [p for p in tracked("bin") if not p.name.startswith("migrate-")]
        # The enumeration is asserted non-empty before the cap. A pathspec that
        # stopped matching -- a rename, a move, a typo -- would count zero lines
        # and report a clean pass, which is the one way a cap test can fail at
        # its job while looking like it worked. Non-empty is the whole check: a
        # directory pathspec matches everything under it or nothing, so there is
        # no partial-match case for a file-count floor to catch, and a floor
        # would instead fail on a legitimate consolidation.
        self.assertTrue(paths, "bin/ enumeration matched no tracked files")
        self.assert_cap("bin/", paths, BIN_CAP)

    def test_the_migration_tools_stay_under_their_own_ceiling(self) -> None:
        """`migrate-*` is outside the `bin/` cap because it is deleted, not kept.

        An empty result is correct rather than suspicious here: steps 7 and 11
        delete these tools, and a cap on nothing is satisfied. It is asserted
        rather than skipped so the transition is visible in the test output.
        """

        paths = [p for p in tracked("bin") if p.name.startswith("migrate-")]
        if not paths:
            self.assertEqual(paths, [], "no migrate-* tools remain; the cap has no subject")
            return
        self.assert_cap("bin/migrate-*", paths, MIGRATE_CAP)

    def test_the_dashboard_stays_under_its_ceiling(self) -> None:
        """`dashboard/` only.

        `bin/sd-dashboard` is the CLI in front of it and counts against `bin/`,
        where the design's own itemisation puts the dashboard glue. Counting it
        in both places would make the two caps overlap and neither one mean
        what it says.
        """

        paths = tracked("dashboard")
        self.assertTrue(paths, "dashboard/ enumeration matched no tracked files")
        self.assert_cap("dashboard/", paths, DASHBOARD_CAP)

    def test_the_dashboard_code_stays_under_its_own_ceiling(self) -> None:
        """The half a docstring cannot buy back (R11-D24).

        The total above may be paid for in prose; this one may not. It is the
        cap that binds when code grows, so that fitting a change never means
        deleting the reasoning for a different one -- which is what 6b-7 spent
        its last hour doing under a single combined ceiling.
        """

        paths = tracked("dashboard")
        self.assertTrue(paths, "dashboard/ enumeration matched no tracked files")
        total = code_line_count(paths)
        self.assertLessEqual(
            total,
            DASHBOARD_CODE_CAP,
            f"dashboard/ carries {total} lines of code against a cap of "
            f"{DASHBOARD_CODE_CAP}. Prose is not what busted this one, so prose "
            f"is not what fixes it: the cap is a design decision (R11-D24), "
            f"raised only in its own record and never in the pull request that "
            f"crossed it.",
        )

    def test_the_code_measure_does_not_count_prose_as_code(self) -> None:
        """The measure is the cap, so a measure that drifts is a cap that lies.

        Checked against a file whose answer is known by construction rather
        than against `dashboard/`, whose answer changes with every commit.
        """

        scratch = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, True)
        module = scratch / "sample.py"
        module.write_text(
            '"""A docstring.\n\nSpanning several lines, none of them code.\n"""\n'
            "\n"
            "# A comment.\n"
            "VALUE = 1  # code, despite the comment\n"
            'TEXT = """\nstill an assignment, and only its first line is code\n"""\n',
            encoding="utf-8",
        )
        self.assertEqual(code_line_count([module]), 2)

        script = scratch / "sample.js"
        script.write_text(
            "// a comment\n\nconst x = 1; // trailing\n  // indented comment\n",
            encoding="utf-8",
        )
        self.assertEqual(code_line_count([script]), 1)

        # Prose in a file the measure has no rule for is not code, and is not
        # counted by the rule for a language it is not written in.
        prose = scratch / "notes.md"
        prose.write_text("# Heading\n\nA paragraph about the design.\n", encoding="utf-8")
        self.assertEqual(code_line_count([prose]), 0)

    def test_no_javascript_under_the_cap_hides_prose_in_a_block_comment(self) -> None:
        """The JS measure cannot see `/* */`, so it is checked that none opens a line.

        Without this the conservative direction is only an assumption: a file
        that started using block comments would have them counted as code,
        and the first person to notice would be whoever the cap failed on.

        A line *opening* one is the whole check, and deliberately not every
        `/*` in the file: `const glob = "src/*.js"` holds the substring and no
        comment. A block opened mid-line after real code leaves that line
        counted as code, which it is, and its continuation lines counted as
        code, which is the conservative direction this measure already
        accepts. Narrowed in review, with the gap stated rather than implied.
        """

        for path in tracked("dashboard"):
            if path.suffix != ".js":
                continue
            # A line that *opens* with `/*`, not the substring anywhere: a
            # regex or a string may hold `/*` mid-line without a byte of it
            # being a comment, and failing on that would be a false positive
            # about comment style. Found in review.
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                self.assertFalse(
                    line.strip().startswith("/*"), f"{path}:{number} opens a block comment")


if __name__ == "__main__":
    unittest.main()
