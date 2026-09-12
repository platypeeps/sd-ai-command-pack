"""Every test in `tests/` is reachable however the file is run.

`unittest discover` imports a module and collects from it afterwards, so a
`if __name__ == "__main__": unittest.main()` block sitting halfway down the
file is invisible to CI. Run that same file directly and `unittest.main()`
executes at the line it appears on -- before the classes below it exist -- and
those tests are silently skipped. Two files in this suite had drifted into
that shape, hiding 32 and 70 tests respectively from direct execution.

The check enumerates `tests/` and parses each module rather than naming the
files that were wrong when it was written; the next file to grow a class after
its runner block is the one a hand-kept list would miss.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import tempfile
import unittest
import warnings

TESTS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TESTS.parent


def main_guard_line(tree: ast.Module) -> int | None:
    """The line of the module's `if __name__ == "__main__":`, if it has one.

    The operator and the comparand are both checked, not just the left-hand
    name. A predicate matching any top-level `if` that mentions `__name__`
    would also claim `if __name__ != "__main__"` and `if __name__ in NAMES`,
    which run in the opposite case or in no particular case -- and reporting a
    guard line for a block that is not a guard would fail modules that are
    shaped correctly.
    """

    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Eq)
                and len(test.comparators) == 1):
            continue
        right = test.comparators[0]
        if isinstance(right, ast.Constant) and right.value == "__main__":
            return node.lineno
    return None


class SuiteShapeTests(unittest.TestCase):
    def test_no_module_defines_anything_after_its_runner_block(self) -> None:
        offenders = []
        for path in sorted(TESTS.glob("test_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            guard = main_guard_line(tree)
            if guard is None:
                continue
            after = [n.name for n in tree.body
                     if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.lineno > guard]
            if after:
                offenders.append(f"{path.name}: {', '.join(after)} defined after line {guard}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_the_predicate_recognises_a_guard_and_rejects_near_misses(self) -> None:
        """The control, as a fixture rather than as a count.

        `main_guard_line` returning `None` for every module would make the test
        above pass over an entire suite of offenders without comparing
        anything. Asserting that against the repository's own file count made
        the control brittle in the ordinary direction -- reorganising the suite
        would fail it while the invariant still held -- so the predicate is
        exercised directly instead. The near-misses are the ones the earlier,
        looser predicate wrongly claimed.
        """

        self.assertEqual(
            main_guard_line(ast.parse('if __name__ == "__main__":\n    main()\n')), 1)
        for near_miss in ('if __name__ != "__main__":\n    main()\n',
                          'if __name__ in NAMES:\n    main()\n',
                          'if __name__ == "__test__":\n    main()\n',
                          'def f():\n    if __name__ == "__main__":\n        main()\n'):
            self.assertIsNone(main_guard_line(ast.parse(near_miss)), near_miss)

    def test_the_scan_reaches_the_real_suite(self) -> None:
        """The other half: a live predicate pointed at nothing proves nothing.

        Separate from the fixture above because they fail for different
        reasons. This one goes wrong when the glob or the directory moves, and
        it asserts the tree was found rather than anything about the shape of
        what is in it.
        """

        self.assertNotEqual(list(TESTS.glob("test_*.py")), [], "the suite was not reached")


def tracked_sources(root: pathlib.Path = REPO_ROOT) -> list[pathlib.Path]:
    """Every tracked Python source under `root`, found by asking git.

    `-z` and a NUL split rather than `.split()` on whitespace. Git prints a
    path containing a space *unquoted* -- `has space.py` arrives verbatim, not
    as `"has space.py"` -- so splitting on whitespace tore it into `has` and
    `space.py`. Neither of those is a file, the `is_file()` guard below dropped
    both, and the source left the scan with nothing printed and the run still
    green. That is the failure worth naming: not a wrong answer but a check
    that had quietly stopped covering a file while continuing to report
    success. No tracked path in this repository holds whitespace today, so this
    was latent rather than live; what it cost was that the first one added
    would have been skipped in silence.

    `--deduplicate` because the index holds an unmerged path once per merge
    stage and plain `ls-files` prints it once per stage, so a file being merged
    was parsed three times and named three times in one failure message. The
    verdict was never wrong here -- results are collected into lists and
    compared -- which is precisely why nothing ever surfaced it.

    `root` is the test seam and is kept off the callers below deliberately: the
    cases point the enumeration at a throwaway repository, because nothing
    about a clean checkout tells any of these behaviours apart.
    """

    listed = subprocess.run(
        ["git", "ls-files", "-z", "--deduplicate"],
        cwd=root, capture_output=True, text=True, check=True)
    found = []
    for name in listed.stdout.split("\0"):
        if not name:
            continue
        path = root / name
        if not path.is_file():
            continue
        if path.suffix == ".py":
            found.append(path)
            continue
        # The `bin/sd-*` commands carry no suffix; a shebang naming python
        # is what makes them python, and reading it is how the check finds
        # a command added later without being told about it.
        head = path.read_bytes()[:64]
        if head.startswith(b"#!") and b"python" in head:
            found.append(path)
    return found


class SourceWarningTests(unittest.TestCase):
    """No tracked source emits a `SyntaxWarning` when Python reads it.

    Found the ordinary way -- running `bin/sd` by hand printed an invalid
    escape sequence warning on every invocation, from a docstring written
    earlier the same day. The suite was green throughout, because warnings do
    not fail tests, and no reviewer saw it, because a warning appears when the
    tool is used rather than when the diff is read. Python 3.12 raised this
    class from DeprecationWarning and 3.15 makes it a SyntaxError, so the same
    docstring that only prints noise today stops the program later.

    Enumerated from `git ls-files` rather than from a list of the files that
    were wrong once.
    """

    def test_no_tracked_source_warns_when_python_reads_it(self) -> None:
        noisy = []
        for path in tracked_sources():
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                try:
                    ast.parse(path.read_text(encoding="utf-8"))
                except (SyntaxError, UnicodeDecodeError):
                    continue
            for warning in caught:
                if issubclass(warning.category, SyntaxWarning):
                    noisy.append(f"{path.relative_to(REPO_ROOT)}: {warning.message}")
        self.assertEqual(noisy, [], "\n".join(noisy))

    def test_the_source_scan_reaches_the_commands(self) -> None:
        """The control: an empty list would make the test above vacuous."""

        found = tracked_sources()
        self.assertNotEqual(found, [], "no tracked source was scanned")
        self.assertIn(REPO_ROOT / "bin" / "sd", found, "the main entry point was not scanned")


def _git(root: pathlib.Path):
    """A git runner bound to `root`.

    Identity and signing are passed per invocation rather than read from the
    machine, so neither fixture fails on a host with no `user.email` or one
    that signs every commit.
    """

    def run(*argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-c", "user.email=shape@example.invalid",
             "-c", "user.name=suite shape", "-c", "commit.gpgsign=false", *argv],
            cwd=root, capture_output=True, text=True, check=check)

    return run


def _repo_with_a_source_being_merged(root: pathlib.Path) -> None:
    """Leave `root` holding `f.py` unmerged in the index, resolved on disk.

    A real merge rather than a hand-built index: the three stages have to come
    from git's own conflict machinery, or the fixture restates the belief under
    test instead of evidencing it.

    The working tree is then repaired and deliberately not staged, because that
    is the state this is actually met in -- the conflict has been fixed in the
    editor, the file on disk is valid Python again so nothing warns about it,
    and the index still carries three stages until somebody runs `git add`.
    """

    git = _git(root)
    source = root / "f.py"
    git("init", "-q", "-b", "main", ".")
    source.write_text("VALUE = 0\n")
    git("add", "f.py")
    git("commit", "-qm", "base")
    git("checkout", "-q", "-b", "other")
    source.write_text("VALUE = 1\n")
    git("commit", "-qam", "other")
    git("checkout", "-q", "main")
    source.write_text("VALUE = 2\n")
    git("commit", "-qam", "mine")
    git("merge", "other", check=False)
    source.write_text("VALUE = 3\n")  # resolved in the editor, left unstaged


def _repo_with_a_spaced_path(root: pathlib.Path) -> None:
    """Leave `root` tracking `has space.py` beside an ordinary source.

    The second file is the point of the pair: it is what keeps the scan
    looking healthy while the first one is being dropped.
    """

    git = _git(root)
    (root / "has space.py").write_text("SPACED = True\n")
    (root / "plain.py").write_text("PLAIN = True\n")
    git("init", "-q", "-b", "main", ".")
    git("add", "-A")
    git("commit", "-qm", "base")


class EnumerationTests(unittest.TestCase):
    """What `tracked_sources` reports when a name or an index is unusual.

    Nothing about a clean checkout separates the fixed behaviour from the
    broken one, so each case builds a real repository and asserts its premise
    before its conclusion. Drop a premise and the conclusion would pass against
    any ordinary repository, which is how both of these survived.
    """

    def test_a_path_with_a_space_arrives_once_and_whole(self) -> None:
        """The unconditional defect of the two, and the one that loses a file.

        Splitting git's output on whitespace turns one real path into two that
        do not exist. The `is_file()` guard then drops both, so the source is
        not reported wrongly -- it is not reported at all, while the scan goes
        on looking healthy because the other file is still in the list.
        """

        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            _repo_with_a_spaced_path(root)

            raw = subprocess.run(
                ["git", "ls-files"], cwd=root,
                capture_output=True, text=True, check=True).stdout
            self.assertIn(
                "has space.py\n", raw,
                "this git quoted the spaced path instead of printing it "
                "plainly, so the defect is not reproduced here; say so rather "
                "than deleting the case")
            self.assertEqual(
                raw.split(), ["has", "space.py", "plain.py"],
                "whitespace splitting no longer tears the path in two, so the "
                "assertion below would prove nothing")
            self.assertFalse(
                (root / "has").exists() or (root / "space.py").exists(),
                "both fragments must be nonexistent paths; that is what makes "
                "the file's disappearance silent rather than an error")

            self.assertEqual(
                tracked_sources(root=root),
                [root / "has space.py", root / "plain.py"],
                "a tracked path containing a space was split into two "
                "nonexistent paths and dropped, so the source left the scan "
                "with nothing printed and the run still green")

    def test_a_source_being_merged_arrives_once(self) -> None:
        """An unmerged path must arrive once, not once per merge stage.

        Cosmetic, and recorded as such: these results are collected into lists
        and compared, so no verdict moves. What moves is the failure message,
        which names the file being merged three times to a reader who is
        already looking for what they just broke.
        """

        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            _repo_with_a_source_being_merged(root)

            stages = subprocess.run(
                ["git", "ls-files", "-u", "--", "f.py"], cwd=root,
                capture_output=True, text=True, check=True).stdout
            self.assertEqual(
                [line.split("\t")[0].split()[-1] for line in stages.splitlines()],
                ["1", "2", "3"],
                "the fixture did not leave an unmerged index, so the case "
                "below proves nothing")

            repeated = subprocess.run(
                ["git", "ls-files", "-z", "--", "f.py"], cwd=root,
                capture_output=True, text=True, check=True).stdout
            self.assertEqual(
                [name for name in repeated.split("\0") if name],
                ["f.py", "f.py", "f.py"],
                "this git no longer repeats an unmerged path; if that is now "
                "the default, say so here rather than deleting the case")

            self.assertEqual(
                tracked_sources(root=root), [root / "f.py"],
                "a file being merged joined the scan once per merge stage, so "
                "it is parsed three times and named three times in one report")

    def test_the_seam_reads_the_repository_it_is_pointed_at(self) -> None:
        """`root` must move the enumeration, not merely be accepted.

        A seam that were ignored would let both cases above read this
        repository, find neither a spaced path nor a conflict, and pass
        whatever the helper does.
        """

        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            _repo_with_a_spaced_path(root)
            self.assertEqual(tracked_sources(root=root),
                             [root / "has space.py", root / "plain.py"])
            self.assertNotIn(root / "plain.py", tracked_sources())


# -- tests that cannot fail ------------------------------------------------
#
# A second shape problem, found the same way the first one was: by accident.
# `test_the_build_is_reproducible` built a wheel twice and asserted the two
# artifacts matched. Both builds landed inside the same second, so the clock
# the builder was wrongly stamping into the archive read the same both times
# and the artifacts agreed -- while the defect the test is named for was
# present throughout. A concurrent run that straddled a second boundary found
# it; the test never could.
#
# The heuristic that catches this by eye is in `skills/sd-review/SKILL.md`:
# for any assertion that two things are equal, name what would have to differ
# for it to fail. If the answer is "a clock tick", "a filesystem ordering" or
# "nothing", the test is decorative.
#
# What follows mechanises the "nothing" answer only, and says so rather than
# implying more. Whether two *different* expressions can differ at run time is
# not decidable from the source -- that is the wheel case, and no check here
# would have caught it. What is decidable is an assertion whose two operands
# are the same expression, an assertion whose operands are all literals, and a
# test that reaches no assertion at all. Those are the flagrant forms, the
# corpus carries none of the first two today, and a gate that is empty on the
# day it lands is a guard rather than a negotiation.

#: Every assertion `unittest.TestCase` defines, read off the class instead of
#: listed. A list would drift from the standard library, and it would also have
#: to be kept from matching this suite's own `assert_fails` and
#: `assert_refused` helpers -- real assertions, but ones whose operands are the
#: helper's arguments rather than the two things being compared, so reading
#: them the way this does would report fifty-six false alarms. It does not
#: catch `fail`, which takes a message and compares nothing.
TESTCASE_ASSERTIONS = frozenset(
    name for name in dir(unittest.TestCase) if name.startswith("assert"))

#: The assertions that take their subject in a `with` block or behind a
#: callable, so their first two arguments are not two things being compared.
#: `assertRaises(ValueError, f, f)` hands `f` over twice for reasons that have
#: nothing to do with equality, and `assertLogs("pkg", "INFO")` takes two
#: literals as a matter of course.
CONTEXTUAL_ASSERTIONS = frozenset({
    "assertRaises", "assertRaisesRegex", "assertWarns", "assertWarnsRegex",
    "assertLogs", "assertNoLogs"})

COMPARING_ASSERTIONS = TESTCASE_ASSERTIONS - CONTEXTUAL_ASSERTIONS

#: Tests whose only claim is that the call under them did not raise. That is a
#: real claim and these two are making it deliberately -- an installer that
#: survives a missing `git`, a ledger write that stays silent when its
#: destination is unwritable -- so this is a register, not a debt list. It
#: earns its place by making the claim explicit: a test arrives here by a
#: change that says in its commit message why it asserts nothing, and
#: `test_every_registered_silent_test_is_still_silent` deletes the entry's
#: cover the moment somebody gives the test a real assertion.
ASSERTS_ONLY_THAT_IT_RAN = frozenset({
    "test_sd_install.py::ExcludesTests::test_a_missing_git_binary_is_survivable",
    "test_sd_ledger.py::LedgerAppend::test_an_unwritable_destination_is_silent",
})


def _self_call(node: ast.AST) -> str | None:
    """The method name in a `self.NAME(...)` call, if `node` is one."""

    if not isinstance(node, ast.Call):
        return None
    function = node.func
    if (isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "self"):
        return function.attr
    return None


def _assertion_call(node: ast.AST) -> str | None:
    """The name of any `*.assert*(...)` call, whatever it is called on.

    Wider than `self.assert...` on purpose. A mock's
    `assert_called_once_with` is an assertion by any reading, and a test
    carrying nothing else is asserting something real -- reading only `self`
    reported three such tests as claimless.
    """

    if not isinstance(node, ast.Call):
        return None
    function = node.func
    if isinstance(function, ast.Attribute) and function.attr.startswith("assert"):
        return function.attr
    return None


def _is_literal(node: ast.AST) -> bool:
    """Whether `node` is a constant, or a container built only of constants."""

    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_literal(element) for element in node.elts)
    if isinstance(node, ast.Dict):
        # `strict=True`: an `ast.Dict` holds one key per value, with `None` in
        # the key slot for a `**spread`, so a length mismatch is a malformed
        # tree rather than something to silently read the shorter half of.
        return all(_is_literal(part)
                   for pair in zip(node.keys, node.values, strict=True)
                   for part in pair if part is not None)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return _is_literal(node.operand)
    return False


def methods(tree: ast.Module):
    """Every method of every class in `tree`, as `(class name, node)`.

    `ast.walk` rather than `tree.body`, so a class nested inside another one
    is reached. Nesting is how a harness gets hidden from `unittest discover`,
    and a test that cannot fail is no better for being hard to find.
    """

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for member in node.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield node.name, member


def decorative_assertions(tree: ast.Module) -> list[str]:
    """Assertions in `tree` whose verdict its own source already fixes.

    Two shapes. The same expression on both sides of a comparison -- the
    answer to "what would have to differ for this to fail" is "nothing", and
    that holds whichever way the assertion points: `assertEqual(x, x)` can
    never fail and `assertNotEqual(x, x)` can never pass. And an assertion all
    of whose arguments are literals, which asks the source about itself and
    reaches no code under test at all.
    """

    found = []
    for class_name, function in methods(tree):
        for node in ast.walk(function):
            name = _assertion_call(node)
            if name not in COMPARING_ASSERTIONS or not isinstance(node, ast.Call):
                continue
            where = f"{class_name}.{function.name} line {node.lineno}"
            operands = [ast.unparse(argument) for argument in node.args]
            if len(operands) >= 2 and operands[0] == operands[1]:
                found.append(f"{where}: {name} compares {operands[0]} with itself")
            elif node.args and all(_is_literal(argument) for argument in node.args):
                found.append(f"{where}: {name} compares only literals")
    return found


def asserting(tree: ast.Module) -> frozenset[str]:
    """Method names in `tree` that reach an assertion, directly or through one.

    Resolution is by name across the whole module rather than up a class's
    bases, which over-approximates: two classes with a same-named helper,
    one of which asserts, clear each other. That direction is deliberate.
    This is looking for the test that claims nothing whatever, and a check
    that cried wolf at every harness delegating to `self.case(...)` would be
    turned off long before it caught one.
    """

    direct: set[str] = set()
    delegates: dict[str, set[str]] = {}
    for _class_name, function in methods(tree):
        targets = delegates.setdefault(function.name, set())
        for node in ast.walk(function):
            helper = _self_call(node)
            # `self.fail(...)` is the most explicit assertion there is and it
            # is the one `TESTCASE_ASSERTIONS` cannot see, because the name
            # does not begin with `assert`. Leaving it out reported two tests
            # that fail on purpose as tests that claim nothing.
            if (isinstance(node, ast.Assert)
                    or _assertion_call(node) is not None
                    or helper == "fail"):
                direct.add(function.name)
            if helper is not None:
                targets.add(helper)
    growing = True
    while growing:
        growing = False
        for name, targets in delegates.items():
            if name not in direct and targets & direct:
                direct.add(name)
                growing = True
    return frozenset(direct)


def claimless_tests(path: pathlib.Path, tree: ast.Module) -> list[str]:
    """Keys of the `test_*` methods in `tree` that reach no assertion at all."""

    reached = asserting(tree)
    return [f"{path.name}::{class_name}::{function.name}"
            for class_name, function in methods(tree)
            if function.name.startswith("test") and function.name not in reached]


def suite_modules() -> list[pathlib.Path]:
    """The test modules this check reads: `tests/test_*.py` on disk.

    The filesystem, not `git ls-files`, and the difference matters here in the
    opposite direction to everywhere else in this file. `tracked_sources`
    above asks the index because it is measuring what the repository ships.
    This is measuring what *runs*, and what runs is what discovery finds on
    disk: a module that is present but untracked executes and would otherwise
    be exempt from the one check asking whether its tests can fail. A tracked
    module that is missing from the checkout runs nowhere and is nothing this
    can speak for. Its neighbour
    `test_no_module_defines_anything_after_its_runner_block` globs for the
    same reason.
    """

    return sorted(TESTS.glob("test_*.py"))


#: Parsed once and shared by the three checks below, which would otherwise
#: read and parse every module in the suite three times over for one answer.
_PARSED: dict[pathlib.Path, ast.Module] = {}


def parsed(path: pathlib.Path) -> ast.Module:
    """`path`, parsed, from the cache if it has been read already."""

    if path not in _PARSED:
        _PARSED[path] = ast.parse(path.read_text(encoding="utf-8"))
    return _PARSED[path]


#: The claimless set, computed once. Two checks below want it -- one asks
#: whether anything new has arrived, the other whether anything registered has
#: left -- and they are separate tests because they fail for opposite reasons,
#: not because the sweep is worth running twice.
_CLAIMLESS: set[str] = set()


def claimless_suite() -> frozenset[str]:
    """Every test in `tests/` that reaches no assertion, keyed and cached."""

    if not _CLAIMLESS:
        for path in suite_modules():
            _CLAIMLESS.update(claimless_tests(path, parsed(path)))
    return frozenset(_CLAIMLESS)


class AssertionsCanFail(unittest.TestCase):
    """No test in this suite is satisfied by its own source.

    The narrow half of the concern behind `sd:434`, mechanised. Claiming more
    than that would be the same defect one level up, so: the wide half is an
    assertion satisfied by the *environment* rather than by the code under
    test, and neither this nor any static check reaches it.

    It is not merely a reading task either, which is the part worth writing
    down because it is the part that sounds wrong. The instance this
    repository actually has -- a process-group test that passed against a
    mutant replacing `os.killpg` with `proc.kill()`, printing `Ran 1 test in
    10.992s / OK` while the child it was supposed to have killed kept running
    -- was found by mutation, and looked correct by every other method. It
    passed, it was named well, it exercised the right module, and its
    operands came from the code under test. Nothing here would have flagged
    it and nor would a careful reader.

    So what these three checks are is the cheap sweep that runs on every
    change, not the instrument. `skills/sd-review/SKILL.md` carries the
    instrument: when a test exists to catch a specific defect, put that defect
    in and watch it go red.
    """

    def test_no_assertion_is_settled_by_its_own_operands(self) -> None:
        decorative = []
        for path in suite_modules():
            decorative += [f"{path.name}: {finding}"
                           for finding in decorative_assertions(parsed(path))]
        self.assertEqual(decorative, [], "\n".join([
            "Assertions whose verdict the source already fixes:",
            *decorative,
            "Give each one an operand that comes from the code under test. "
            "This is not a list to append to."]))

    def test_every_test_reaches_an_assertion(self) -> None:
        unregistered = sorted(claimless_suite() - ASSERTS_ONLY_THAT_IT_RAN)
        self.assertEqual(unregistered, [], "\n".join([
            "Tests that reach no assertion, so the only thing they claim is "
            "that the call did not raise:",
            *unregistered,
            "Assert what the call produced. If not raising really is the "
            "whole claim, add the key to ASSERTS_ONLY_THAT_IT_RAN and say why "
            "in the commit message."]))

    def test_every_registered_silent_test_is_still_silent(self) -> None:
        """The register may only shrink, which is what keeps it from rotting.

        An entry that has since grown a real assertion is cover nobody needs,
        and cover nobody needs is what a later claimless test inherits.
        """

        stale = sorted(ASSERTS_ONLY_THAT_IT_RAN - claimless_suite())
        self.assertEqual(stale, [], "\n".join([
            "These now assert something, or have moved. Delete the entries:",
            *stale]))

    def test_the_predicates_recognise_the_shapes_and_reject_the_near_misses(self) -> None:
        """The control, as fixtures: the suite being clean proves nothing.

        Predicates that answered "no finding" to everything would pass the two
        checks above over a suite of offenders. The near-misses are the ones
        the first draft got wrong: `self.fail("...")` and the helpers named
        `assert_fails` and `assert_refused`, all of which take literals as a
        matter of course, and `assertRaises`, which repeats a callable.
        """

        def findings(statement: str) -> list[str]:
            return decorative_assertions(ast.parse(
                f"class T:\n    def test_x(self):\n        {statement}\n"))

        for settled in ("self.assertEqual(built(), built())",
                        "self.assertNotEqual(value, value)",
                        "self.assertEqual(1, 1)",
                        "self.assertTrue(True)",
                        "self.assertIn('a', ('a', 'b'))"):
            self.assertEqual(len(findings(settled)), 1, settled)
        for near_miss in ("self.fail('never posts')",
                          "self.assert_fails('every work item has a prd.md')",
                          "self.assert_refused('{\"rank\": 1}', 'what')",
                          "self.assertRaises(ValueError, build, build)",
                          "self.assertLogs('sd', 'INFO')",
                          "self.assertEqual(read(path), 'x')",
                          "self.assertEqual(left, right, 'message')"):
            self.assertEqual(findings(near_miss), [], near_miss)

    def test_the_reachability_predicate_follows_helpers_and_mocks(self) -> None:
        """The other control, for the other check, failing for other reasons."""

        def claimless(source: str) -> list[str]:
            return claimless_tests(pathlib.Path("fixture.py"), ast.parse(source))

        self.assertEqual(
            claimless("class T:\n    def test_x(self):\n        do_the_thing()\n"),
            ["fixture.py::T::test_x"])
        for asserting_somehow in ("self.assertEqual(f(), 1)",
                                  "assert f()",
                                  "self.launchd.restart.assert_called_once_with(1)",
                                  "self.branch_mark_case('origin.git')"):
            self.assertEqual(claimless(
                "class T:\n"
                f"    def test_x(self):\n        {asserting_somehow}\n"
                "    def branch_mark_case(self, remote):\n"
                "        self.assertTrue(remote)\n"), [], asserting_somehow)

    def test_the_assertion_scan_reaches_the_real_suite(self) -> None:
        """The third control: live predicates pointed at nothing prove nothing.

        Separate from the fixtures because it fails for a different reason --
        this one goes wrong when the glob or the directory moves, and it
        asserts that test methods were found rather than anything about them.
        """

        counted = 0
        for path in suite_modules():
            counted += sum(1 for _class_name, function in methods(parsed(path))
                           if function.name.startswith("test"))
        self.assertNotEqual(suite_modules(), [], "the suite was not reached")
        self.assertGreater(counted, 500,
                           "far fewer test methods were parsed than this suite "
                           "holds, so the checks above swept almost nothing")


if __name__ == "__main__":
    unittest.main()
