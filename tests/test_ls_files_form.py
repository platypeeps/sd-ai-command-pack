"""Every call to git's index lister in this repository says what its form is.

sd:841. The index holds an unmerged path once per merge stage, so a plain
listing prints that path three times while somebody is resolving a conflict.
Whether that matters at a given call site ranges from nothing at all to a
wrong answer, and the way to find out is to read the site -- which is the
problem: there are three dozen of them, and nothing made a new one announce
itself.

`Makefile:67` has claimed since item 481 that "every `ls-files` in this
repository now says what it means". It was false by the time sd:823 found two
calls that did not, and sd:823's fix removed the count from the comment
without leaving anything that would fail when the next one landed. The review
of that change re-derived the inventory by hand and found the author's had
missed two sites. That is the whole argument for this file: the inventory is
not something a person can keep, so it is enumerated here instead, from the
index, every time the suite runs.

**What a site must carry.** One of the options that fixes git's output shape
-- `--deduplicate` for a list of paths, `-u`/`-s` for merge stages,
`--error-unmatch` for a probe, `--others` for what the index does not hold --
written on the same line as the subcommand. A call that is deliberately plain,
because plain output is what it is testing, says so in a comment and says why.

**What this does not do**, stated rather than left to be discovered. It does
not decide whether a site chose the right form; a reader does that. It reads
source text, so a call whose subcommand arrives in a variable -- `argv =
["git", name]` -- is invisible to it, and a reviewer is the only thing
standing behind that; no site in this repository is written that way, and the
one place that would have been, `surface` below, is written out instead. It
covers tracked, non-prose files, so an untracked scratch file and a page under
`docs/` are both out of scope. What it does is make the choice visible and
refuse the absence of one, which is the part that was drifting.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import subprocess
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# This module is inside the surface it scans, so the subcommand's name is
# spelled in two pieces and joined here. Written whole, it would be a bare
# call in this file's own source -- the scan below would find it, and the
# guard would fail on the guard. Every pattern in this file is built from
# this one constant, so the spelling exists once and the trick is stated once.
SUBJECT = "ls-" + "files"

#: The subcommand as a whole word. `-` is in the excluded class on both sides,
#: so `ls-files-form` -- the marker's own name, three constants down -- is not
#: a match. Without that, the marker would be a site and would need a marker.
TOKEN = re.compile(rf"(?<![\w-]){re.escape(SUBJECT)}(?![\w-])")

#: The command form: the subcommand as a shell word after `git`. The leading
#: class refuses `mygit ` and `path/to/git ` without refusing `! git ` or
#: `$(shell git `.
AFTER_GIT = re.compile(r"(?:^|[^\w./-])git\s+$")

#: What may follow the subcommand in something that runs: an option, a quoted
#: pathspec, a redirect, a pipe, a separator, the end of the line. A word
#: follows it in prose and in an error message -- "git ls-files failed;" --
#: and those are the two false positives this refuses.
ARGUMENT = tuple("-'\"|>;)&$\\")

#: The options that fix the output's shape, and therefore say what the caller
#: asked for. `-s`/`--stage` is here beside `-u`/`--unmerged` because they are
#: the same answer -- one row per stage, on purpose -- and a site that grows
#: one should not have to argue for it separately.
FORM_OPTIONS = ("--deduplicate", "--unmerged", "--error-unmatch", "--others",
                "--stage", "-u", "-s")
OPTION = re.compile(r"(?<![\w-])(?:" + "|".join(FORM_OPTIONS) + r")(?![\w-])")

#: The escape hatch, and it is built to cost something. A site whose subject
#: is plain output declares that in a comment, and the declaration is not
#: complete until it says why -- otherwise the marker becomes the thing a new
#: bare call copies to get past this file, which is the hand-written exemption
#: list again wearing a comment. `REASON_WORDS` is low on purpose: writing the
#: sentence is the toll, not its length.
PLAIN = re.compile(re.escape(SUBJECT) + r"-form: plain -- +(\S.*)$")
REASON_WORDS = 4

#: Documentation is not the subject. `CHANGELOG.md`, `CONTRIBUTING.md` and the
#: pages under `docs/` discuss this command in prose and quote whole command
#: lines a person types; the invariant here is about code that runs, and prose
#: about code is `bin/sd-docs-lint`'s to police.
PROSE_SUFFIX = ".md"

#: Floors, not counts. They fail when the scan stops reaching the repository
#: -- a moved directory, a recogniser that matches nothing -- and they do not
#: move when a call site is added or deleted, which is the drift that put a
#: number in `Makefile:67` and made it wrong.
SITE_FLOOR = 20
FILE_FLOOR = 8


@dataclasses.dataclass(frozen=True)
class Site:
    """One call, as a reader would cite it, and whether it said what it is."""

    path: str
    line: int
    text: str
    declared: bool

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.text.strip()}"


def is_call(line: str, start: int, end: int) -> bool:
    """Whether the match at `[start:end]` in `line` is a call and not prose.

    Three questions, in the order that makes the cheap one first:

    * Inside a code span? An odd number of backticks before the match means
      the reader is inside one, which is how every page and docstring in this
      repository writes the command when it is talking about it.
    * Written as an argv element -- `"ls-files"` in a list handed to
      `subprocess` -- which is unambiguous, since nothing quotes a lone
      subcommand for any other reason.
    * Written as a shell word after `git`, and followed by something an
      argument can start with.
    """

    before, after = line[:start], line[end:]
    if before.count("`") % 2:
        return False
    if before.endswith(('"', "'")) and after.startswith(before[-1]):
        return True
    if not AFTER_GIT.search(before):
        return False
    rest = after.lstrip()
    return rest == "" or rest.startswith(ARGUMENT)


def calls(text: str) -> list[tuple[int, str]]:
    """Every call in `text`, as `(line number, line)`."""

    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in TOKEN.finditer(line):
            if is_call(line, match.start(), match.end()):
                found.append((number, line))
    return found


def declares_form(lines: list[str], number: int) -> bool:
    """Whether the call on line `number` of `lines` says what its form is.

    The option must be on the call's own line: every site in this repository
    writes it there, an argv list that wraps puts the subcommand and its
    options on the first line, and "somewhere in the same statement" is not a
    place a reader can check at a glance.

    The plain marker may also sit on the line directly above, because the line
    holding the subcommand is often already the longest one in the call. One
    line of reach and no more, so the marker cannot be mistaken for the
    neighbouring call's.
    """

    line = lines[number - 1]
    if OPTION.search(line):
        return True
    for candidate in (line, lines[number - 2] if number >= 2 else ""):
        marker = PLAIN.search(candidate)
        if marker and len(marker.group(1).split()) >= REASON_WORDS:
            return True
    return False


def surface(root: pathlib.Path = REPO_ROOT) -> list[str]:
    """Every tracked path that is code rather than prose.

    From the index, so an untracked scratch file cannot fail the suite and a
    file somebody adds next month cannot escape it by not being listed here.

    `--deduplicate`: this call is itself a site, and the form it wants is a
    list of paths naming each one once. Written out rather than built from
    `SUBJECT`, so that this call is itself one of the sites the scan finds --
    a guard with an exemption for its own source is not one.
    """

    listed = subprocess.run(
        ["git", "ls-files", "-z", "--deduplicate"],
        cwd=root, capture_output=True, text=True, check=True).stdout
    return [name for name in listed.split("\0")
            if name and not name.endswith(PROSE_SUFFIX)]


def scan(root: pathlib.Path = REPO_ROOT) -> tuple[list[Site], list[str]]:
    """Every call in the tracked, non-prose surface, and what could not be read.

    The unreadable files come back rather than being swallowed. A walk that
    quietly covers less than it should reports success forever, and that is
    the failure this whole file exists to refuse -- it would be a poor place
    to commit it.
    """

    found, unreadable = [], []
    for name in surface(root):
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            unreadable.append(f"{name}: {error}")
            continue
        lines = text.splitlines()
        found.extend(Site(name, number, line, declares_form(lines, number))
                     for number, line in calls(text))
    return found, unreadable


def sites(root: pathlib.Path = REPO_ROOT) -> list[Site]:
    """Every call in the tracked, non-prose surface of `root`."""

    return scan(root)[0]


def undeclared(root: pathlib.Path = REPO_ROOT) -> list[str]:
    """Every call in `root` that does not say what its form is."""

    return sorted(str(site) for site in sites(root) if not site.declared)


class EveryCallSaysWhatItIs(unittest.TestCase):
    """The guard itself, over this repository."""

    def test_no_call_in_the_tracked_surface_is_bare(self) -> None:
        # Every offender, not the first few: the reader of this failure is
        # about to go and fix them, and `unittest` truncates by default.
        self.maxDiff = None
        self.assertEqual(
            undeclared(), [],
            "each of these calls git's index lister without saying what "
            "shape it expects back. Add the option that fixes it -- "
            f"{', '.join(FORM_OPTIONS)} -- or, if plain output is what the "
            f"site is testing, a comment reading `{SUBJECT}-form: plain -- "
            "<why>` on that line or the one above it.")

    def test_the_scan_reaches_this_repository(self) -> None:
        """A live check pointed at nothing reports success forever.

        Floors rather than the current numbers: this fails when the walk
        collapses, and stays quiet when a call site is added or removed.
        """

        found, unreadable = scan()
        self.assertEqual(unreadable, [], "files the walk could not read")
        self.assertGreaterEqual(len(found), SITE_FLOOR, found)
        self.assertGreaterEqual(len({site.path for site in found}), FILE_FLOOR)


class TheRecogniserTellsCallsFromProse(unittest.TestCase):
    """The half that decides what is a site. Both errors are expensive.

    Missing a call leaves the hole this file exists to close. Claiming one in
    prose fails the suite over a sentence, and the repository's comments and
    docstrings name this command constantly -- so the cases below are the
    exact spellings that appear in it.
    """

    def found(self, text: str) -> list[int]:
        return [number for number, _ in calls(text)]

    def test_an_argv_element_is_a_call(self) -> None:
        self.assertEqual(self.found(f'["git", "{SUBJECT}", "-z"]'), [1])
        self.assertEqual(self.found(f"self.git('{SUBJECT}', '--', path)"), [1])

    def test_a_shell_word_after_git_is_a_call(self) -> None:
        for line in (f"git {SUBJECT} --deduplicate -- bin",
                     f"if ! git {SUBJECT} -z -- '*.sh' >\"$list\"; then",
                     f"LINT := $(shell git {SUBJECT} --deduplicate -- bin)",
                     f"run: git {SUBJECT} -z | xargs -0 shellcheck"):
            with self.subTest(line=line):
                self.assertEqual(self.found(line), [1])

    def test_a_code_span_in_prose_is_not_a_call(self) -> None:
        for line in (f"# plain `{SUBJECT}` prints it once per stage",
                     f"    Enumerated from `git {SUBJECT}`, never from a list.",
                     f'    """Track `paths` and return `git {SUBJECT} -- spec`."""',
                     f"# No `git add` here, so `{SUBJECT}` does not see it"):
            with self.subTest(line=line):
                self.assertEqual(self.found(line), [])

    def test_an_error_message_naming_the_command_is_not_a_call(self) -> None:
        """Both shell gates print one, and neither of them runs anything.

        A word follows the subcommand instead of an argument, which is what
        separates a sentence about the command from the command.
        """

        for line in (f'  "error: git {SUBJECT} failed; cannot enumerate." >&2',
                     f"printf 'error: git {SUBJECT} failed.\\n' >&2",
                     f"enumerate it -- git grep -nI -- {SUBJECT} -- tests bin"):
            with self.subTest(line=line):
                self.assertEqual(self.found(line), [])

    def test_the_markers_own_name_is_not_a_call(self) -> None:
        """Otherwise the escape hatch would need an escape hatch."""

        self.assertEqual(self.found(f"# {SUBJECT}-form: plain -- git repeats it here"), [])

    def test_a_program_whose_name_ends_in_git_is_not_this_command(self) -> None:
        for line in (f"mygit {SUBJECT} -z", f"/usr/bin/nogit {SUBJECT} -z"):
            with self.subTest(line=line):
                self.assertEqual(self.found(line), [])


class TheDeclarationHasToSaySomething(unittest.TestCase):
    """The other half: what counts as having declared a form."""

    def declared(self, *lines: str) -> bool:
        return declares_form(list(lines), len(lines))

    def test_an_option_on_the_call_line_declares_the_form(self) -> None:
        for option in FORM_OPTIONS:
            with self.subTest(option=option):
                self.assertTrue(self.declared(f'["git", "{SUBJECT}", "{option}"]'))

    def test_an_option_on_another_line_does_not_reach(self) -> None:
        self.assertFalse(self.declared('    "--deduplicate",',
                                       f'    ["git", "{SUBJECT}"],'))

    def test_an_option_like_word_is_not_an_option(self) -> None:
        for near in ("--deduplicated", "x--others", "-under", "--stages"):
            with self.subTest(near=near):
                self.assertFalse(self.declared(f'["git", "{SUBJECT}", "{near}"]'))

    def test_a_plain_marker_with_a_reason_declares_the_form(self) -> None:
        self.assertTrue(self.declared(
            f'    ["git", "{SUBJECT}", "-z"],  # {SUBJECT}-form: plain -- '
            "the repeated path is the subject here"))

    def test_the_marker_reaches_one_line_down_and_no_further(self) -> None:
        marker = f"    raw = run(  # {SUBJECT}-form: plain -- git repeats the path here"
        call = f'        ["git", "{SUBJECT}", "-z"],'
        self.assertTrue(self.declared(marker, call))
        self.assertFalse(self.declared(marker, "        cwd=root,", call))

    def test_a_marker_with_no_reason_declares_nothing(self) -> None:
        """The toll. Without it the marker is a bare comment a new bare call
        copies, which is the hand-written exemption list in a new costume."""

        for empty in (f"# {SUBJECT}-form: plain", f"# {SUBJECT}-form: plain --",
                      f"# {SUBJECT}-form: plain -- ", f"# {SUBJECT}-form: plain -- why"):
            with self.subTest(marker=empty):
                self.assertFalse(self.declared(f'["git", "{SUBJECT}"]  {empty}'))

    def test_a_bare_call_declares_nothing(self) -> None:
        self.assertFalse(self.declared(f'["git", "{SUBJECT}"]'))
        self.assertFalse(self.declared(f'["git", "{SUBJECT}", "--", "f.py"]'))


class TheGuardAgainstTheGuard(unittest.TestCase):
    """A bare call landing in a tracked file must be named, in a real tree.

    The class above pins the two predicates on strings. This runs the whole
    path -- index, walk, report -- against a repository built for it, because
    that is the thing that has to work the day somebody adds a file.
    """

    def repository(self, **files: str) -> pathlib.Path:
        raw = tempfile.TemporaryDirectory()
        self.addCleanup(raw.cleanup)
        root = pathlib.Path(raw.name).resolve()
        for name, text in files.items():
            (root / name).write_text(text, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True,
                       capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True,
                       capture_output=True)
        return root

    def test_a_new_bare_call_is_named_with_its_path_and_line(self) -> None:
        root = self.repository(
            **{"tool.py": f'x = 1\nrun(["git", "{SUBJECT}", "--", "f"])\n'})
        self.assertEqual(undeclared(root), [f'tool.py:2: run(["git", "{SUBJECT}", "--", "f"])'])

    def test_the_same_call_with_the_option_is_not_named(self) -> None:
        root = self.repository(
            **{"tool.py": f'run(["git", "{SUBJECT}", "--deduplicate"])\n'})
        self.assertEqual(undeclared(root), [])

    def test_a_bare_call_in_a_page_is_not_named(self) -> None:
        """Prose is out of scope, and the scope is the suffix, not a path."""

        root = self.repository(**{
            "NOTES.md": f"Run: git {SUBJECT} -- bin\n",
            "tool.py": f'run(["git", "{SUBJECT}", "--deduplicate"])\n'})
        self.assertEqual(surface(root), ["tool.py"],
                         "the page was tracked and had to be dropped by "
                         "suffix, not missing from the index altogether")
        self.assertEqual(undeclared(root), [])

    def test_a_file_the_walk_cannot_read_is_reported_not_skipped(self) -> None:
        """Saying nothing about what was not scanned is how a walk shrinks.

        There is no such file in this repository today, which is exactly why
        the case is built rather than waited for: the day one lands, the scan
        must say it covered less, not report the same green it always did.
        """

        root = self.repository(**{"tool.py": "x = 1\n"})
        # Undecodable bytes that would be a bare call if they were text, so
        # the walk cannot both fail to read the file and report it clean.
        # Spelled through `SUBJECT` for the reason given at the top: written
        # out, this line would be a bare call in a tracked file, and the guard
        # would be right to say so -- it did, when it was.
        (root / "blob.bin").write_bytes(
            b"\xff\xfe\x00 git " + SUBJECT.encode() + b" -- bin\n")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True,
                       capture_output=True)
        found, unreadable = scan(root)
        self.assertEqual(found, [], "the unreadable bytes must not be parsed")
        self.assertEqual([entry.split(":", 1)[0] for entry in unreadable],
                         ["blob.bin"])

    def test_an_untracked_file_is_not_scanned(self) -> None:
        root = self.repository(**{"tool.py": "x = 1\n"})
        (root / "scratch.py").write_text(f'run(["git", "{SUBJECT}"])\n',
                                         encoding="utf-8")
        self.assertEqual(undeclared(root), [])


if __name__ == "__main__":
    unittest.main()
