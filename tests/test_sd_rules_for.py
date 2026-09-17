"""`bin/sd-rules --for <path>`: the authoring tier, read off the registry.

The registry's three tiers are three call sites of one table, and this is the
first one: before a file is written, the author asks which live rules are in
scope for it and gets back each row's id, subject and the section that teaches
it. Nothing here is a fourth copy of a rule -- the verb iterates
`sd_rules.RULES` and prints what it finds, so a row added to the table is
answered the day it lands.

**The scope rule is the documentation gate's, not a new one.** A row's `scope`
is `code`, `prose` or `both`, and a path is prose when it is markdown, `.md`
or `.markdown` in any case, which is exactly how `points_into_code` in
`tests/test_doc_citations.py` decides whether a citation target is a page.
`test_the_scope_rule_is_the_doc_citation_gates` binds the two so they cannot
drift apart: a suffix one of them starts treating differently fails here.

**The table is patched, not listed.** The live table carried only `code` rows
when this module landed (#997); `R13-D1` to `R13-D3` gave it `prose` rows on
2026-09-16 (#1015), and `TheLiveTable` reads both branches off it as it
stands. No live row is `both` on 2026-09-16, and the order and the block
shape are questions about rows chosen for the purpose, so those are put to a
fixture table swapped in under `mock.patch`; the script must read
`sd_rules.RULES` at call time for that to work, which is also what keeps it
from holding a copy.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from types import ModuleType
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_rules  # noqa: E402 - the table the verb reads

# The scope rule's source, borrowed rather than restated.
from tests.test_doc_citations import points_into_code  # noqa: E402

SCRIPT = REPO_ROOT / "bin" / "sd-rules"


def load_rules_for() -> ModuleType:
    """Import the executable, which has no `.py` suffix to import by name.

    Registered in `sys.modules` before it is executed, the way
    `tests/test_sd_size_report.py` loads its command, and handed back from
    there on a second call rather than executed twice.
    """

    if "sd_rules_for" in sys.modules:
        return sys.modules["sd_rules_for"]
    spec = importlib.util.spec_from_loader(
        "sd_rules_for",
        importlib.machinery.SourceFileLoader("sd_rules_for", str(SCRIPT)),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def row(identifier: str, scope: str, state: str = sd_rules.LIVE) -> sd_rules.Rule:
    return sd_rules.Rule(
        id=identifier,
        subject=f"the subject of {identifier}",
        checker=None if state == sd_rules.REPEALED else "bin/sd_lib.py::repo_root",
        proof=None if state == sd_rules.REPEALED else "a proof",
        scope=scope,
        teaches=f"skills/sd-check/SKILL.md#{identifier} section",
        state=state,
    )


#: A table with every branch the matcher has: one row per scope and a repealed
#: row that must never print. The ids are ones that resolve today -- rows of
#: the registry or definitions in live prose -- because leg c of
#: `tests/test_rule_registry.py` reads every id written in this file as a
#: citation, and a made-up id here would be a dangling one there.
FIXTURE = (
    row("R10-D6", "code"),
    row("R11-D31", "prose"),
    row("R10-D5", "both"),
    row("R11-D32", "both", state=sd_rules.REPEALED),
)


def rule_id(round_number: int, decision: int) -> str:
    """An id assembled rather than written, for the ordering case.

    The numeric-order test needs ids whose text order differs from their
    numeric order, and no resolving id pair does. Assembling them keeps the
    census honest: an id written out here would be read as a citation.
    """

    return f"R{round_number}-D{decision}"


def run(argv: list[str], cwd: pathlib.Path | None = None) -> tuple[int, str, str]:
    """The command through its own `run_rules_for`, with the streams captured."""

    out, err = io.StringIO(), io.StringIO()
    code = load_rules_for().run_rules_for(argv, out=out, err=err, cwd=cwd)
    return code, out.getvalue(), err.getvalue()


def ids_in(text: str) -> list[str]:
    """The rule ids that open a block, in the order printed."""

    return [line.split()[0] for line in text.splitlines()
            if line and not line.startswith(" ") and sd_rules.RULE_ID.match(line)]


class TheCommandExists(unittest.TestCase):
    def test_the_command_is_in_bin(self) -> None:
        self.assertTrue(SCRIPT.is_file(), f"{SCRIPT} is not a file")


class ScopeMatching(unittest.TestCase):
    """Which rows a path draws, on the fixture table."""

    def setUp(self) -> None:
        patcher = mock.patch.object(sd_rules, "RULES", FIXTURE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_markdown_path_draws_the_prose_and_both_rows(self) -> None:
        code, out, _ = run(["--for", "docs/anything.md"], cwd=REPO_ROOT)
        self.assertEqual(code, 0)
        self.assertEqual(ids_in(out), ["R10-D5", "R11-D31"])

    def test_a_python_path_draws_the_code_and_both_rows(self) -> None:
        code, out, _ = run(["--for", "bin/sd_lib.py"], cwd=REPO_ROOT)
        self.assertEqual(code, 0)
        self.assertEqual(ids_in(out), ["R10-D5", "R10-D6"])

    def test_a_suffixless_command_is_code(self) -> None:
        # `bin/sd-review` is a Python file with no `.py`, and the first
        # checker the registry could not name lived in one.
        _, out, _ = run(["--for", "bin/sd-review"], cwd=REPO_ROOT)
        self.assertEqual(ids_in(out), ["R10-D5", "R10-D6"])

    def test_markdown_is_matched_in_any_case_and_either_spelling(self) -> None:
        for name in ("NOTES.MD", "docs/page.markdown", "docs/Page.Markdown"):
            with self.subTest(path=name):
                _, out, _ = run(["--for", name], cwd=REPO_ROOT)
                self.assertEqual(ids_in(out), ["R10-D5", "R11-D31"])

    def test_a_repealed_row_never_prints(self) -> None:
        for name in ("docs/page.md", "bin/tool.py"):
            with self.subTest(path=name):
                _, out, _ = run(["--for", name], cwd=REPO_ROOT)
                self.assertNotIn("R11-D32", out)

    def test_a_file_not_yet_written_is_still_answered(self) -> None:
        # The file being written is the one that may not exist yet; its name
        # is what the scope is read from.
        code, out, _ = run(["--for", "docs/not-written-yet.md"], cwd=REPO_ROOT)
        self.assertEqual(code, 0)
        self.assertEqual(ids_in(out), ["R10-D5", "R11-D31"])

    def test_no_row_in_scope_says_so_and_exits_zero(self) -> None:
        with mock.patch.object(sd_rules, "RULES", (row("R10-D6", "code"),)):
            code, out, err = run(["--for", "docs/page.md"], cwd=REPO_ROOT)
        self.assertEqual(code, 0)
        self.assertEqual(out, "no rule in scope for docs/page.md\n")
        self.assertEqual(err, "")


class TheBlock(unittest.TestCase):
    """What one row prints: id, subject, teaching section, in that order."""

    def setUp(self) -> None:
        patcher = mock.patch.object(sd_rules, "RULES", FIXTURE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_each_block_carries_id_subject_and_the_teaching_section(self) -> None:
        _, out, _ = run(["--for", "bin/sd_lib.py"], cwd=REPO_ROOT)
        blocks = [block for block in out.split("\n\n") if block.strip()]
        self.assertEqual(len(blocks), 2, out)
        for block, identifier in zip(blocks, ["R10-D5", "R10-D6"], strict=True):
            with self.subTest(rule=identifier):
                lines = block.splitlines()
                self.assertTrue(lines[0].startswith(identifier), lines[0])
                self.assertIn(f"the subject of {identifier}", block)
                self.assertIn(f"skills/sd-check/SKILL.md#{identifier} section",
                              block)

    def test_the_teaching_section_is_the_row_field_verbatim(self) -> None:
        # The section is the row's `teaches` field and nothing derived from it:
        # a heading with spaces and backticks, as `R10-D4`'s has, prints whole.
        section = "skills/sd-review/SKILL.md#The `codex-json` entry (heading)"
        fixture = (sd_rules.Rule("R10-D6", "s", "bin/sd_lib.py::repo_root",
                                 "p", "code", section),)
        with mock.patch.object(sd_rules, "RULES", fixture):
            _, out, _ = run(["--for", "bin/x.py"], cwd=REPO_ROOT)
        self.assertIn(section, out)

    def test_the_order_is_by_id_numerically(self) -> None:
        # Decision 10 sorts before decision 4 as text; the verb orders by the
        # numbers in the id so the listing reads the way the rounds ran.
        ids = [rule_id(11, 10), rule_id(11, 4), rule_id(11, 9), rule_id(2, 1)]
        fixture = tuple(row(identifier, "code") for identifier in ids)
        with mock.patch.object(sd_rules, "RULES", fixture):
            _, out, _ = run(["--for", "bin/x.py"], cwd=REPO_ROOT)
        self.assertEqual(ids_in(out), [ids[3], ids[1], ids[2], ids[0]])
        self.assertNotEqual(ids_in(out), sorted(ids), "text order would pass")

    def test_json_carries_the_same_rows_in_the_same_order(self) -> None:
        _, text, _ = run(["--for", "bin/sd_lib.py"], cwd=REPO_ROOT)
        code, out, _ = run(["--for", "bin/sd_lib.py", "--json"], cwd=REPO_ROOT)
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertEqual([r["id"] for r in rows], ids_in(text))
        self.assertEqual(sorted(rows[0]), ["id", "scope", "subject", "teaches"])
        self.assertEqual(rows[0]["teaches"], "skills/sd-check/SKILL.md#R10-D5 section")

    def test_json_with_no_row_in_scope_is_an_empty_list(self) -> None:
        with mock.patch.object(sd_rules, "RULES", (row("R10-D6", "code"),)):
            code, out, _ = run(["--for", "docs/page.md", "--json"], cwd=REPO_ROOT)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])


class BadPaths(unittest.TestCase):
    """Exit 2, one sentence on stderr, nothing on stdout."""

    def assert_refused(self, argv: list[str], cwd: pathlib.Path, fragment: str) -> None:
        code, out, err = run(argv, cwd=cwd)
        self.assertEqual(code, 2, err)
        self.assertEqual(out, "")
        self.assertIn(fragment, err)
        self.assertEqual(len(err.strip().splitlines()), 1, err)

    def test_a_directory_is_refused(self) -> None:
        self.assert_refused(["--for", "bin"], REPO_ROOT, "is a directory")

    def test_a_path_outside_the_repository_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as elsewhere:
            self.assert_refused(["--for", str(pathlib.Path(elsewhere) / "x.md")],
                                REPO_ROOT, "outside")

    def test_outside_a_repository_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as elsewhere:
            self.assert_refused(["--for", "x.md"], pathlib.Path(elsewhere),
                                "not inside a git repository")

    def test_a_path_that_walks_out_of_the_repository_is_refused(self) -> None:
        self.assert_refused(["--for", "../outside.md"], REPO_ROOT, "outside")

    def test_a_path_the_platform_cannot_resolve_is_refused_not_raised(self) -> None:
        # Review finding on #997: `Path.resolve()` raises `ValueError` on an
        # embedded NUL, and the documented answer to a bad path is exit 2
        # with one sentence, never a traceback.
        self.assert_refused(["--for", "docs/a\0b.md"], REPO_ROOT,
                            "cannot be resolved")


class TheLiveTable(unittest.TestCase):
    """Against `sd_rules.RULES` as it stands: enumerated, never listed."""

    def expected(self, path: str) -> list[str]:
        wanted = "code" if points_into_code(path) else "prose"
        return sorted(
            (r.id for r in sd_rules.RULES
             if r.state == sd_rules.LIVE and r.scope in (wanted, "both")),
            key=load_rules_for().rule_order)

    def test_a_code_path_draws_every_live_code_row(self) -> None:
        _, out, _ = run(["--for", "bin/sd_lib.py"], cwd=REPO_ROOT)
        self.assertEqual(ids_in(out), self.expected("bin/sd_lib.py"))
        self.assertTrue(ids_in(out), "the live table has no code row to print")

    def test_a_prose_path_draws_every_live_prose_row(self) -> None:
        code, out, _ = run(["--for", "README.md"], cwd=REPO_ROOT)
        self.assertEqual(code, 0)
        expected = self.expected("README.md")
        if expected:
            self.assertEqual(ids_in(out), expected)
        else:
            self.assertEqual(out, "no rule in scope for README.md\n")

    def test_the_scope_rule_is_the_doc_citation_gates(self) -> None:
        # The one place the two rules could disagree is the suffix table, so
        # every shape either one distinguishes is put to both.
        module = load_rules_for()
        for path in ("a.md", "A.MD", "a.markdown", "a.Markdown", "a.py",
                     "bin/sd-review", "a.md.py", "a.py.md", "a.js", "md",
                     "a.mdx", "a.txt", "docs/x/y.md", "a.json"):
            with self.subTest(path=path):
                self.assertEqual(module.path_scope(path) == "code",
                                 points_into_code(path))

    def test_the_command_runs_as_a_process(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--for", "bin/sd_lib.py"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(ids_in(result.stdout), self.expected("bin/sd_lib.py"))


if __name__ == "__main__":
    unittest.main()
