"""A `path:line` citation still points at the thing the prose says it does.

A line number is invalidated by any insertion above its target, and nothing
watched them. Step 8-iv demonstrated the failure inside a single branch:
growing `bin/sd` from 1,553 lines to 2,006 moved `frontmatter()` from 1231 to
1248, the reader's `.strip('"')` from 1252 to 1276, and `status_filter` from
1350 to 1378. All three were correct on `main`, all three were wrong on the
branch that changed the file, and the branch that broke them was also the
branch editing the document that carried them.

The planning review rule -- `.claude/rules/sd-planning-adversarial-review.md`,
and the contract it points at -- already asks for this sweep, and it did catch
those three. But it only runs at a planning convergence boundary. A pure code
change that edits no `prd.md`, `design.md` or `implement.md` breaks citations
with nothing to notice; 8-iv was swept only because it happened to edit
`design.md` as well. This runs on every change instead.

**The rule is adjacency.** A citation that directly follows a backticked
symbol -- `` `status_filter` (`bin/sd:1378`) `` -- is a claim *about that
symbol*, and the symbol must appear at the cited line. A citation with prose
between it and the nearest backticked token is making some other claim, and is
skipped rather than guessed at: an earlier draft took the nearest symbol within
90 characters and mis-attributed `bin/sd-status:501-506`, which is an accurate
citation to a docstring that does not happen to repeat the key name. A gate
whose failures need interpreting teaches people to interpret failures away.

Skipped deliberately, each because the check would be wrong rather than
inconvenient:

* **Anything under `archive/`.** An archived record cites the code as it stood.
  `docs/work/archive/` cites `install.py` and `installer/*`, deleted at step 3e.
  Those citations are supposed to be stale; that is what an archive is.
* **A target that no longer exists.** Same reason, for live documents that
  reference sibling repositories (`sd-writing-pack/scripts/pack.py`) or files
  this rollout deleted.
* **An anchor that is a path rather than a symbol.** `` `tests/test_verb_inventory.py` ``
  before a citation says nothing checkable about a particular line.
* **A citation with no adjacent symbol at all**, such as the `bin/sd:323`
  pointer inside a dated, already-addressed incident record whose subject is a
  line that was then changed.
"""

from __future__ import annotations

import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# A backticked token, then only whitespace or an opening paren, then the
# citation. Anything else between them and this is not a claim about the token.
PAIR = re.compile(r"`([^`\n]+)`\s*\(?`([A-Za-z0-9_./-]+):(\d+)(?:-(\d+))?`")
SYMBOL = re.compile(r"^\.?[A-Za-z_][A-Za-z0-9_.]*(\(.*\))?$")
EXTENSION = re.compile(r"\.(md|py|js|json|sh|ya?ml|toml|txt|lock)$")

# The cited line is where the symbol is *introduced*; prose cites a `def` line
# and the reader looks at the lines under it. Wide enough to survive a
# signature wrapped across lines, narrow enough that a symbol used a hundred
# lines away cannot satisfy it.
WINDOW = 2


def is_symbol(token: str) -> bool:
    """A name a line can be checked against, as opposed to a path or a phrase."""

    return bool(SYMBOL.match(token)) and "/" not in token and not EXTENSION.search(token)


def is_inside_repo(target: pathlib.Path) -> bool:
    """A path this test is willing to open: a real file, inside the checkout."""

    try:
        resolved = target.resolve()
    except OSError:
        return False
    return resolved.is_file() and resolved.is_relative_to(REPO_ROOT.resolve())


def anchored_citations() -> list[tuple[pathlib.Path, str, pathlib.Path, int, int]]:
    """Every symbol-anchored citation in a live document, enumerated from disk."""

    found = []
    for doc in sorted(REPO_ROOT.glob("docs/**/*.md")):
        if "archive" in doc.parts:
            continue
        # Newlines flattened: a citation routinely wraps away from its symbol.
        flat = doc.read_text(encoding="utf-8").replace("\n", " ")
        for match in PAIR.finditer(flat):
            anchor, path, start = match.group(1), match.group(2), int(match.group(3))
            end = int(match.group(4) or match.group(3))
            target = REPO_ROOT / path
            # A citation is a string in a document, and this test reads the
            # file it names. `REPO_ROOT / path` yields the absolute path when
            # `path` is absolute, and follows `..` out of the tree, so an edit
            # to any document under `docs/` could make CI read a file of its
            # choosing. Citations that do not land inside the repository are
            # not citations, and are skipped rather than opened.
            if not is_symbol(anchor) or not is_inside_repo(target):
                continue
            found.append((doc, anchor, target, start, end))
    return found


class DocCitationTests(unittest.TestCase):
    def test_every_anchored_citation_names_its_symbol_at_the_cited_line(self) -> None:
        stale = []
        for doc, anchor, target, start, end in anchored_citations():
            lines = target.read_text(encoding="utf-8").splitlines()
            window = "\n".join(lines[max(0, start - 1 - WINDOW):end + WINDOW])
            if anchor.rstrip("()") not in window:
                stale.append(
                    f"{doc.relative_to(REPO_ROOT)}: `{anchor}` is not at"
                    f" {target.relative_to(REPO_ROOT)}:{start}")
        self.assertEqual(stale, [], "\n".join(stale))

    def test_the_scan_reaches_the_documents(self) -> None:
        """The control, and deliberately not a threshold on what it found.

        A `PAIR` that matched nothing -- a tightened regex, a moved document
        tree -- would make the test above pass over any number of stale
        citations without comparing a single one. But asserting *how many*
        citations exist makes the control fail whenever the prose is
        reorganised, while the invariant still holds. So this asserts the tree
        was reached and at least one citation was compared; that `PAIR` itself
        works is proved by fixture in the test below rather than by counting.
        """

        live = [d for d in REPO_ROOT.glob("docs/**/*.md") if "archive" not in d.parts]
        self.assertNotEqual(live, [], "the document tree was not reached at all")
        self.assertTrue(anchored_citations() or stable_source_citations(REPO_ROOT), "no citation was compared")

    def test_a_citation_cannot_send_this_test_outside_the_checkout(self) -> None:
        """A citation is a string in a document, and this test opens what it names.

        `REPO_ROOT / path` returns the absolute path when `path` is absolute
        and follows `..` out of the tree, so without this an edit to any
        document under `docs/` could make CI read a file of its choosing.
        """

        self.assertFalse(is_inside_repo(pathlib.Path("/etc/passwd")))
        self.assertFalse(is_inside_repo(REPO_ROOT / ".." / ".." / "etc" / "passwd"))
        self.assertFalse(is_inside_repo(REPO_ROOT / "no-such-file-here.md"))
        self.assertTrue(is_inside_repo(REPO_ROOT / "bin" / "sd"))

    def test_prose_between_a_symbol_and_a_citation_breaks_the_anchor(self) -> None:
        """The rule is adjacency, and adjacency has to actually be required.

        Without this, a `PAIR` that tolerated arbitrary text between the two
        would reintroduce the mis-attribution the docstring describes, and the
        gate would start reporting accurate citations as stale.
        """

        self.assertTrue(PAIR.search("`status_filter` (`bin/sd:1378`)"))
        self.assertIsNone(PAIR.search("`status_filter` is reported by `bin/sd:1378`"))


# An explicit declaration locator carries no line claim. Keep the existing
# path:line rule above strict; only this spelling survives line movement.
STABLE_SOURCE = re.compile(r"`source:([A-Za-z0-9_./-]+)::([A-Za-z_][A-Za-z0-9_]*)`")


def stable_source_citations(root: pathlib.Path) -> list[tuple[pathlib.Path, str, str]]:
    """Explicit source:path::symbol locators; existing pytest node IDs are untouched."""
    found = []
    for doc in sorted(root.glob("docs/**/*.md")):
        if "archive" not in doc.parts:
            found.extend((doc, path, symbol) for path, symbol in
                         STABLE_SOURCE.findall(doc.read_text(encoding="utf-8")))
    return found


def source_declaration_error(root: pathlib.Path, path: str, symbol: str) -> str | None:
    """Resolve a Python top-level declaration without reading outside the checkout.

    Functions, classes and assigned names are declarations; comments, strings
    and call sites cannot keep a deleted definition's citation passing. This
    also handles extensionless Python entrypoints such as bin/sd-docs-lint.
    """
    import ast

    try:
        target = (root / path).resolve()
        if not target.is_relative_to(root.resolve()):
            return None  # Preserve the line rule's containment exclusion.
        if not target.is_file():
            return f"{path}: target is missing"
        tree = ast.parse(target.read_text(encoding="utf-8"), filename=path)
    except (OSError, UnicodeError, SyntaxError) as error:
        return f"{path}: cannot read a Python source declaration: {error}"

    declarations = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            declarations += node.name == symbol
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            declarations += sum(
                isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store) and name.id == symbol
                for target in targets for name in ast.walk(target)
            )
    if declarations != 1:
        return f"{path}::{symbol}: expected one top-level declaration, found {declarations}"
    return None


class StableSourceCitationTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.target = self.root / "bin" / "tool"
        self.target.parent.mkdir()
        self.target.write_text("def render():\n    pass\n", encoding="utf-8")

    def test_inserted_lines_do_not_break_a_declaration_locator(self) -> None:
        self.assertIsNone(source_declaration_error(self.root, "bin/tool", "render"))
        self.target.write_text("# inserted\n" * 100 + self.target.read_text(), encoding="utf-8")
        self.assertIsNone(source_declaration_error(self.root, "bin/tool", "render"))

    def test_deleted_renamed_or_comment_only_symbols_fail(self) -> None:
        for source in (
            "", "def renamed():\n    pass\n", "# def render():\ntext = 'render'\n", "render()\n"
        ):
            with self.subTest(source=source):
                self.target.write_text(source, encoding="utf-8")
                self.assertIn(
                    "found 0", source_declaration_error(self.root, "bin/tool", "render") or ""
                )

    def test_duplicate_declarations_fail_as_ambiguous(self) -> None:
        self.target.write_text(self.target.read_text() * 2, encoding="utf-8")
        self.assertIn(
            "found 2", source_declaration_error(self.root, "bin/tool", "render") or ""
        )

    def test_constants_and_classes_are_declarations(self) -> None:
        self.target.write_text("LIMIT = 2\nLABEL: str = 'name'\nclass Reader:\n    pass\n")
        for symbol in ("LIMIT", "LABEL", "Reader"):
            with self.subTest(symbol=symbol):
                self.assertIsNone(source_declaration_error(self.root, "bin/tool", symbol))

    def test_missing_inside_target_fails(self) -> None:
        self.assertIn(
            "target is missing",
            source_declaration_error(self.root, "bin/missing", "render") or "",
        )

    def test_outside_targets_are_never_opened(self) -> None:
        from unittest import mock

        link = self.root / "escape"
        link.symlink_to(self.root.parent / "outside.py")
        with mock.patch.object(pathlib.Path, "read_text", side_effect=AssertionError("opened")):
            for path in (str(self.root.parent / "outside.py"), "../outside.py", "escape"):
                with self.subTest(path=path):
                    self.assertIsNone(source_declaration_error(self.root, path, "render"))

    def test_only_explicit_locators_are_scanned_and_archives_stay_excluded(self) -> None:
        docs = self.root / "docs"
        archive = docs / "archive"
        archive.mkdir(parents=True)
        (docs / "current.md").write_text(
            "`render` (`source:bin/tool::render`) and `gh` (`GH_RECORDER`)\n"
            "`render` (`bin/tool:1`) and `tests/missing.py::test_historical`\n", encoding="utf-8"
        )
        (archive / "old.md").write_text("`source:bin/missing::gone`\n", encoding="utf-8")
        self.assertEqual(
            stable_source_citations(self.root), [(docs / "current.md", "bin/tool", "render")]
        )

    def test_existing_line_citations_still_reject_line_movement(self) -> None:
        from unittest import mock

        docs = self.root / "docs"
        docs.mkdir()
        (docs / "current.md").write_text("`render` (`bin/tool:1`)\n", encoding="utf-8")
        self.target.write_text("# inserted\n" * 100 + self.target.read_text(), encoding="utf-8")
        with mock.patch.dict(globals(), {"REPO_ROOT": self.root}):
            with self.assertRaisesRegex(AssertionError, "is not at"):
                DocCitationTests().test_every_anchored_citation_names_its_symbol_at_the_cited_line()

    def test_scan_control_accepts_a_corpus_using_only_stable_locators(self) -> None:
        from unittest import mock

        docs = self.root / "docs"
        docs.mkdir()
        (docs / "current.md").write_text("`source:bin/tool::render`\n", encoding="utf-8")
        with mock.patch.dict(globals(), {"REPO_ROOT": self.root}):
            self.assertEqual(anchored_citations(), [])
            DocCitationTests().test_the_scan_reaches_the_documents()

    def test_every_explicit_source_locator_resolves_in_the_live_corpus(self) -> None:
        citations = stable_source_citations(REPO_ROOT)
        failures = []
        for doc, path, symbol in citations:
            problem = source_declaration_error(REPO_ROOT, path, symbol)
            if problem:
                failures.append(f"{doc.relative_to(REPO_ROOT)}: {problem}")
        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
