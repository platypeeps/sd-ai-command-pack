"""The line-count ceilings, enforced instead of remembered -- and their record.

`migrate-*` tools stay under `MIGRATE_CAP` (R11-D24). The `bin/` ceiling (R11-D48)
and the `dashboard/` ceilings (sd:719 step 7) are retired; `CEILING_HISTORY` keeps
their values as the evidence the retirements were decided on.

**R11-D41, 2026-09-06: the history shows every raise together.** Each raise was
priced alone, and the history found not one fall and not one refusal.

**R11-D49, 2026-09-13: a ceiling may be recorded coming down, on
`DASHBOARD_CODE_CAP` only.** A fall on any other ceiling fails by name, and no
ceiling repeats a value.

No count of moves is written here: `ceiling_moves()` produces it, and the test
prints it when it fails.

Files are enumerated from `git ls-files`, never from a list here: a hand-kept
list misses the next file, and a directory walk counts `__pycache__`.
"""

# This module reads the whole checkout, so no changed-files fast path may
# narrow it away. `.github/scripts/select-tests.py` greps for the line below.
# select-tests: always-run

from __future__ import annotations

import io
import pathlib
import shutil
import subprocess
import sys
import tempfile
import tokenize
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Each cap names the design decision it enforces, so a failure points at the record.
#
# **R11-D48, 2026-09-11: `bin/` has no ceiling.** Every one of its 21 recorded moves was a raise.

MIGRATE_CAP = 1_500        # temporary tools, deleted at steps 7 and 11

# sd:719 step 7, 2026-09-16: the dashboard ceilings are retired with `dashboard/`.
# R11-D49: the code cap fell four times (2,328 to 1,850, 1,183, 866, 0).
# Dates are the day a value landed on `main`. Every ceiling here is closed.
CEILING_HISTORY: dict[str, tuple[tuple[str, int], ...]] = {
    # Closed (R11-D48): the evidence for the retirement; no live value.
    "BIN_CAP": (
        ("2026-08-30", 8_000),
        ("2026-08-31", 14_000),
        ("2026-09-06", 14_700),
        ("2026-09-06", 15_050),
        ("2026-09-06", 15_400),
        ("2026-09-06", 15_750),
        ("2026-09-07", 16_750),
        ("2026-09-07", 17_000),
        ("2026-09-07", 17_050),
        ("2026-09-07", 17_250),
        ("2026-09-07", 18_000),
        ("2026-09-07", 18_550),
        ("2026-09-08", 19_500),
        ("2026-09-08", 20_050),
        ("2026-09-09", 20_231),
        ("2026-09-09", 20_246),
        ("2026-09-09", 20_475),
        ("2026-09-09", 20_731),
        ("2026-09-09", 20_733),
        ("2026-09-10", 20_745),
        ("2026-09-10", 20_803),
    ),
    # Closed (sd:719 step 7): the evidence for the retirement; no live value.
    "DASHBOARD_CAP": (
        ("2026-08-30", 2_500),
        ("2026-08-31", 4_000),
        ("2026-09-01", 4_300),
        ("2026-09-04", 4_350),
        ("2026-09-04", 4_375),
        ("2026-09-06", 4_600),
    ),
    "DASHBOARD_CODE_CAP": (
        ("2026-09-01", 2_300),
        ("2026-09-07", 2_328),
        ("2026-09-13", 1_850),
        ("2026-09-16", 1_183),
        ("2026-09-16", 866),
        ("2026-09-16", 0),
    ),
}


def ceiling_moves() -> tuple[int, int, int]:
    """What `CEILING_HISTORY` records, counted rather than remembered.

    Returns `(values, upward, downward)`: recorded values summed across every
    ceiling in the history, retired ones included, and the transitions between
    consecutive values of the same ceiling by direction. A first value is not a
    move, so `upward + downward` is `values` minus one per ceiling.

    This exists because the count had four answers at once -- the header said
    one number, the table another, the file's git log a third and a review a
    fourth -- and every one was defensible, because none of them said what it
    counted. Saying what it counts is this docstring's job; producing the
    number is the code's. Nothing else in this file restates it, on the same
    reasoning `bin/sd-status` uses for `CLASSES`: one table, and every reader
    of it iterates rather than repeats.
    """

    values = upward = downward = 0
    for history in CEILING_HISTORY.values():
        values += len(history)
        # `strict=False` deliberately: the offset slice is one shorter, which
        # is what makes each pair a transition rather than a value.
        for (_, before), (_, after) in zip(history, history[1:], strict=False):
            if after > before:
                upward += 1
            elif after < before:
                downward += 1
    return values, upward, downward


def tracked(*pathspecs: str, root: pathlib.Path = REPO_ROOT) -> list[pathlib.Path]:
    """Tracked files matching `pathspecs`, as the index reports them.

    `--deduplicate` because the index holds an unmerged path once per merge
    stage, and plain `ls-files` prints it once per stage. The consumers here
    are `line_count` and `code_line_count`, which iterate and **sum**, so a
    conflicted file charges its lines to a cap three times.

    That is a worse failure than the one the same missing flag caused in
    `tests/test_code_health.py`, which shares this call's argv and which is
    where the defect was found. There the tripling surfaces as a countable
    contradiction -- two functions sharing one key -- and the message says so.
    Here it surfaces as a larger number against a ceiling, in a file whose
    ceilings are famously argued over one raise at a time, with nothing to
    distinguish the inflation from real growth. The reader's next move is to
    derive a raise for a cap that was never crossed.

    `root` is the test seam, kept off every caller's signature deliberately:
    the suite injects a throwaway repository to build an index this repository
    will not hold on demand.
    """

    output = subprocess.run(
        ["git", "ls-files", "-z", "--deduplicate", "--", *pathspecs],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [root / name for name in output.split("\0") if name]


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
    error can only tighten this cap, never loosen it. `dashboard/app.js` held
    no block comment while it was in the tree (retired at sd:719 step 6), and
    the measure was checked, not assumed.

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

    def test_the_migration_tools_stay_under_their_own_ceiling(self) -> None:
        """`migrate-*` has a ceiling of its own because it is deleted, not kept.

        An empty result is correct rather than suspicious here: steps 7 and 11
        delete these tools, and a cap on nothing is satisfied. It is asserted
        rather than skipped so the transition is visible in the test output.
        """

        paths = [p for p in tracked("bin") if p.name.startswith("migrate-")]
        if not paths:
            self.assertEqual(paths, [], "no migrate-* tools remain; the cap has no subject")
            return
        self.assert_cap("bin/migrate-*", paths, MIGRATE_CAP)

    def test_the_recorded_history_is_raises_only(self) -> None:
        """R11-D41's name, R11-D49's assertions.

        R11-D41's finding was that nothing ever looked at the raises together.
        This is the looking. Until R11-D49 it failed the day a ceiling came
        down; now a fall is legal on the one ceiling that record names, and a
        fall anywhere else fails with the ceiling, its date and both values,
        so an undecided fall surfaces as a row rather than as a count.

        Either way no ceiling repeats a value: every recorded row after a
        ceiling's first moves the number, up or down. The message carries the
        live figures so the number lives in output rather than in prose that
        goes stale between readings.
        """

        values, upward, downward = ceiling_moves()
        # R11-D49 names this one ceiling, and the module docstring says why
        # `DASHBOARD_CAP` is not beside it.
        may_fall = {"DASHBOARD_CODE_CAP"}
        undecided = [
            f"{name} {before} -> {after} on {date}"
            for name, history in CEILING_HISTORY.items() if name not in may_fall
            # `strict=False` for the reason `ceiling_moves` gives.
            for (_, before), (date, after) in zip(history, history[1:], strict=False)
            if after < before
        ]
        self.assertEqual(
            undecided,
            [],
            f"CEILING_HISTORY records a fall on a ceiling R11-D49 does not "
            f"name: {values} recorded values, {upward} up, {downward} down "
            f"across {len(CEILING_HISTORY)} ceilings. A fall is legal on "
            f"{sorted(may_fall)} only; any other ceiling coming down needs its "
            f"own record first.",
        )
        self.assertEqual(
            upward + downward,
            values - len(CEILING_HISTORY),
            f"a ceiling repeats a value: {values} recorded values across "
            f"{len(CEILING_HISTORY)} ceilings leaves "
            f"{values - len(CEILING_HISTORY)} moves, but only "
            f"{upward + downward} of them changed the number ({upward} up, "
            f"{downward} down). A row that moves nothing is a move nobody made.",
        )

    def test_the_three_retired_ceilings_are_history_and_not_constants(self) -> None:
        """sd:719 step 7: the dashboard ceilings retired the way `BIN_CAP` did.

        `CEILING_HISTORY` holds exactly the three closed records -- `BIN_CAP`
        from R11-D48, `DASHBOARD_CAP` and `DASHBOARD_CODE_CAP` from step 7 --
        and none of the three names, nor `DASHBOARD_CODE_SLACK`, is a
        module-level constant any more. Read off this module rather than
        recited, so a constant restored beside its history is red here, and
        a history row dropped with its constant is red too: the history is
        the evidence each retirement was argued from.
        """

        self.assertEqual(
            sorted(CEILING_HISTORY), ["BIN_CAP", "DASHBOARD_CAP", "DASHBOARD_CODE_CAP"])
        module = sys.modules[__name__]
        live = [name for name in ("BIN_CAP", "DASHBOARD_CAP", "DASHBOARD_CODE_CAP",
                                  "DASHBOARD_CODE_SLACK") if hasattr(module, name)]
        self.assertEqual(
            live, [],
            f"a retired ceiling is a constant again: {live}. Its history stays in "
            f"CEILING_HISTORY as a closed record; the constant does not come back.")

    def test_the_code_measure_does_not_count_prose_as_code(self) -> None:
        """The measure is the cap, so a measure that drifts is a cap that lies.

        Checked against a file whose answer is known by construction rather
        than against a tracked tree, whose answer changes with every commit.
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

#: What `_unmerged_index_repo` leaves in the working tree once the conflict is
#: resolved: four lines, of which two carry code. Small enough that the
#: expected sums below are read rather than computed, which is the point --
#: a case that derived its own expectation from the same helper it is testing
#: would agree with the defect as readily as with the fix.
RESOLVED = '"""Resolved."""\n\nx = 1\ny = 2\n'
RESOLVED_LINES = 4
RESOLVED_CODE_LINES = 2


def _unmerged_index_repo(root: pathlib.Path) -> pathlib.Path:
    """A repository whose index holds `bin/panel.py` unmerged.

    The conflict is a real merge, not a hand-written index: the three stages
    have to come from git's own machinery or the fixture merely restates the
    belief under test.

    The working tree is then **resolved and left unstaged**, which is the
    state this defect is actually met in. A person fixes the conflict in their
    editor and runs the suite before `git add`; the file on disk is valid
    Python again, so nothing warns them, while the index still carries three
    stages. Leaving the conflict markers in place instead would make
    `code_line_count` raise on a tokenise error -- a different failure, and a
    louder one than the silent inflation this guards.
    """

    def git(*argv: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            # Identity and signing are passed per invocation rather than read
            # from the machine, so the fixture does not fail on a host with no
            # `user.email` or one that signs every commit.
            ["git", "-c", "user.email=caps@example.invalid",
             "-c", "user.name=loc caps", "-c", "commit.gpgsign=false", *argv],
            cwd=root, capture_output=True, text=True, check=check)

    panel = root / "bin" / "panel.py"
    panel.parent.mkdir(parents=True)
    git("init", "-q", "-b", "main", ".")
    panel.write_text('"""Base."""\n\nx = 0\n')
    git("add", "bin/panel.py")
    git("commit", "-qm", "base")
    git("checkout", "-q", "-b", "other")
    panel.write_text('"""Other."""\n\nx = 2\n')
    git("commit", "-qam", "other")
    git("checkout", "-q", "main")
    panel.write_text('"""Mine."""\n\nx = 1\n')
    git("commit", "-qam", "mine")
    git("merge", "other", check=False)
    panel.write_text(RESOLVED)
    return panel


class AnUnmergedIndex(unittest.TestCase):
    """What the caps measure while a merge is still being resolved."""

    def setUp(self) -> None:
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.root = pathlib.Path(home.name)
        self.panel = _unmerged_index_repo(self.root)

    def assert_the_index_is_unmerged(self) -> None:
        """The premise every case below rests on, asserted rather than assumed.

        Without this the cases would pass against any ordinary repository,
        which is exactly how the defect survived: nothing about a clean
        checkout tells the two behaviours apart.
        """

        stages = subprocess.run(
            ["git", "ls-files", "-u", "--", "bin/panel.py"],
            cwd=self.root, capture_output=True, text=True, check=True).stdout
        self.assertEqual(
            [line.split("\t")[0].split()[-1] for line in stages.splitlines()],
            ["1", "2", "3"],
            "the fixture did not leave an unmerged index, so nothing below "
            "proves anything")
        raw = subprocess.run(
            # ls-files-form: plain -- the repetition is what this asserts
            ["git", "ls-files", "-z", "--", "bin/panel.py"],
            cwd=self.root, capture_output=True, text=True, check=True).stdout
        self.assertEqual(
            [name for name in raw.split("\0") if name],
            ["bin/panel.py"] * 3,
            "this git no longer repeats an unmerged path; if that is now the "
            "default, say so here rather than deleting these cases")

    def test_a_conflicted_file_charges_the_total_cap_once(self) -> None:
        """The measure, not the path list.

        Deduplicating the paths is the mechanism; the thing that breaks is the
        sum. Asserting only that `tracked` returns one path would leave the
        case passing for a reason next to the one that matters, and would not
        fail if somebody later reintroduced the tripling further down the
        pipe.
        """

        self.assert_the_index_is_unmerged()
        self.assertEqual(self.panel.read_text(), RESOLVED,
                         "the working tree is resolved; only the index is not")
        self.assertEqual(
            line_count(tracked("bin", root=self.root)), RESOLVED_LINES,
            "a file being merged charged its lines to the total cap once per "
            "merge stage")

    def test_a_conflicted_file_charges_the_code_cap_once(self) -> None:
        """`code_line_count` sums over the same list and inflates the same way.

        Both consumers are named because they are separate loops over
        `tracked`, and a fix applied to one of them would leave the other
        wrong -- which is the shape of the defect being fixed here in the
        first place.
        """

        self.assert_the_index_is_unmerged()
        self.assertEqual(
            code_line_count(tracked("bin", root=self.root)),
            RESOLVED_CODE_LINES,
            "a file being merged charged its code lines to the code cap once "
            "per merge stage")

    def test_the_seam_reads_the_repository_it_is_pointed_at(self) -> None:
        """`root` must move the enumeration, not merely be accepted.

        A seam that is ignored would let the cases above read this repository,
        find no conflict, and agree with whatever `tracked` does.
        """

        self.assertEqual(tracked("bin", root=self.root), [self.panel])
        self.assertNotIn(self.panel, tracked("bin"))


class DeletedArchitectureResidue(unittest.TestCase):
    """sd:601. A generated file nothing reads can only ever be wrong.

    `generated/registry-snapshot.json` listed 20 skills. Fourteen existed in
    neither `skills/` nor `contrib/`, and it omitted 76 that did -- last
    written 2026-08-17, before the rename that made it wrong, and read by no
    code in the tree. The pack was pointing outward at drift in a consumer's
    CLAUDE.md while shipping the same drift itself.

    It is not refreshed, because a refreshed list is stale again on the next
    rename; that is how it reached fourteen. sd:10's own prd.md calls it
    residue from a deleted architecture, and acceptance criterion 17 requires
    it absent, so this asserts the criterion rather than restating a judgement.

    The criterion's other two paths, `tests/test_selector_contract_drift.py`
    and `plugins/sd`, have since been removed too. They are still
    deliberately NOT asserted here: a list naming paths this file does not
    enforce is the same unread recitation sd:601 is about.
    """

    def test_the_registry_snapshot_does_not_come_back(self) -> None:
        path = "generated/registry-snapshot.json"
        self.assertEqual([], tracked(path), f"{path} is tracked again")
        self.assertFalse((REPO_ROOT / path).exists(), f"{path} is on disk again")

    def test_nothing_in_the_tree_reads_the_registry_snapshot(self) -> None:
        """Enumerated from the index, not from a list of directories."""
        readers = [
            path for path in tracked("bin", "tests", "skills",
                                     ".github", "Makefile")
            if path.is_file() and path.name != pathlib.Path(__file__).name
            and "registry-snapshot" in path.read_text(
                encoding="utf-8", errors="replace")
        ]
        self.assertEqual([], readers)


if __name__ == "__main__":
    unittest.main()
