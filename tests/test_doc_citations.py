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

import os
import pathlib
import re
import unittest
from unittest import mock

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


def contained(root: pathlib.Path, documents) -> list[pathlib.Path]:
    """The documents this test will open: real files inside `root`, archives out.

    `is_inside_repo` guards the file a citation *names*. This guards the file
    the citation is *in*, which nothing was watching. `glob` returns a symlink
    as readily as a regular file and `read_text` follows it, so a tracked
    `docs/current.md -> /etc/passwd` would have CI read a file of the
    document tree's choosing -- the same hole, entered from the other side.

    Resolved before the containment test, because an unresolved path compares
    as relative to the root while pointing anywhere at all.
    """
    base = root.resolve()
    kept = []
    for doc in documents:
        if "archive" in doc.parts:
            continue
        try:
            resolved = doc.resolve()
        except OSError:
            continue
        if resolved.is_file() and resolved.is_relative_to(base):
            kept.append(doc)
    return kept


def anchored_citations() -> list[tuple[pathlib.Path, str, pathlib.Path, int, int]]:
    """Every symbol-anchored citation in a live document, enumerated from disk."""

    found = []
    for doc in contained(REPO_ROOT, sorted(REPO_ROOT.glob("docs/**/*.md"))):
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


#: Living documents that sit above `docs/`. `CONTRIBUTING.md` is where the
#: convention itself is written down, example included, so a corpus that skips
#: it would let the one citation every reader copies rot first and unnoticed.
ROOT_DOCUMENTS = ("CONTRIBUTING.md",)


def stable_source_citations(root: pathlib.Path) -> list[tuple[pathlib.Path, str, str]]:
    """Explicit source:path::symbol locators; existing pytest node IDs are untouched."""
    documents = sorted(root.glob("docs/**/*.md"))
    documents += [root / name for name in ROOT_DOCUMENTS if (root / name).is_file()]
    found = []
    for doc in contained(root, documents):
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

    # Module level, then one level into each class. A test method is a
    # declaration a document cites by name as readily as a function is, and
    # `TestCase` puts every one of them inside a class. Not deeper: a name
    # defined inside a function body is a local, and a citation to one is a
    # claim about an implementation detail that has no stable identity.
    bodies = [tree.body]
    bodies += [node.body for node in tree.body if isinstance(node, ast.ClassDef)]
    declarations = 0
    for body in bodies:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                declarations += node.name == symbol
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                declarations += sum(
                    isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store)
                    and name.id == symbol
                    for target in targets for name in ast.walk(target)
                )
    if declarations != 1:
        return (f"{path}::{symbol}: expected one declaration at module or class "
                f"level, found {declarations}")
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

    def test_root_documents_are_scanned_beside_the_docs_tree(self) -> None:
        """`CONTRIBUTING.md` states the convention, so its own example must resolve.

        Scoping the corpus to `docs/**` would leave the citation every reader
        copies as the only one nothing checks.
        """

        docs = self.root / "docs"
        docs.mkdir()
        (docs / "current.md").write_text("`source:bin/tool::render`\n", encoding="utf-8")
        contributing = self.root / "CONTRIBUTING.md"
        contributing.write_text("prefer `source:bin/tool::render`\n", encoding="utf-8")
        self.assertIn(
            (contributing, "bin/tool", "render"), stable_source_citations(self.root)
        )
        contributing.write_text("prefer `source:bin/tool::deleted`\n", encoding="utf-8")
        self.assertIn(
            "found 0",
            source_declaration_error(self.root, "bin/tool", "deleted") or "",
        )

    def test_a_symlinked_document_is_never_read(self) -> None:
        """The document is an input too, not only the file its citation names.

        `glob` returns a symlink as readily as a file and `read_text` follows
        it, so without this a tracked `docs/current.md` could point anywhere
        and have CI read it. Asserted on both walks, because both glob the
        same tree.
        """

        docs = self.root / "docs"
        docs.mkdir()
        outside = self.root.parent / f"outside-{os.getpid()}.md"
        outside.write_text(
            "`source:bin/tool::render` and `render` (`bin/tool:1`)\n", encoding="utf-8"
        )
        self.addCleanup(outside.unlink)
        (docs / "escape.md").symlink_to(outside)
        (docs / "real.md").write_text("`source:bin/tool::render`\n", encoding="utf-8")

        collected = stable_source_citations(self.root)
        self.assertEqual([doc for doc, _, _ in collected], [docs / "real.md"])
        self.assertEqual(contained(self.root, [docs / "escape.md"]), [])

        with mock.patch.dict(globals(), {"REPO_ROOT": self.root}):
            self.assertEqual(anchored_citations(), [])

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


#: **Which skills must qualify the citation: all of them, and none is named.**
#:
#: The rule has no exception list because the reason is structural rather than
#: per-skill. A skill is installed to the platform home and read with the
#: reader's cwd in whatever checkout encloses it (R10-D6); nothing makes that
#: checkout this one. `sd-research-repo` is read from a research repo,
#: `sd-plan`/`sd-review`/`sd-ship` from whatever repository is being developed.
#: So a rule path any of them cites resolves against a checkout that need not
#: have the file. No skill is exempt, so no skill has to be remembered, and
#: both ends of this scan are walked from the filesystem: the documents from
#: `skills/`, the paths that matter from `.claude/rules/`.
#:
#: The predecessor hardcoded `FOREIGN_SKILL = "skills/sd-research-repo"`, which
#: was narrower than the defect it was written for -- four skills carried the
#: citation and one was watched.
SKILLS_DIR = "skills"

#: **Which paths are in scope: the pack's authored rules, enumerated.**
#:
#: Not "every path that happens to resolve in this checkout", which was the
#: predecessor's test and is wrong the moment it leaves one skill. Run broadly
#: it flags `.github/sd-review.json`, `.github/workflows/sd-review-route.yml`
#: and `.github/sd-status.json` -- per-repository configuration that the
#: *reader's* checkout is supposed to carry, which `bin/sd_setup_github.py`
#: writes there. Those are correct unqualified, and rewriting them to name the
#: pack would be the worse bug.
#:
#: What makes `.claude/rules/` different is that it is the one surface the pack
#: authors, tells the reader to go and *read* for authoritative content, and
#: cannot put in the reader's checkout:
#:
#:   * it is not installed -- `bin/sd_install.py` carries zero `.claude/rules`
#:     references, so it cannot be fanned out;
#:   * it cannot be shipped as a copy either -- the caps table is allowed
#:     exactly two copies and `tests/test_workflow_policy.py::ReviewTable`
#:     enforces that, so a third beside a skill fails the gate;
#:   * and resolving it against the wrong checkout is silent. The reader finds
#:     no file, reads no cap, and the review pass proceeds as if it had one.
#:     Confirmed absent in all seven research repos on this machine.
#:
#: So the invariant is the only one left: the prose names the checkout that
#: holds it. The rule files themselves are globbed, not listed, so a rule added
#: next to this one is covered on the day it is written.
RULES_DIR = ".claude/rules"

#: A backticked path with a directory separator. Only those make a claim about
#: some checkout's layout; a bare `CLAUDE.md` or `research.conf.py` is a name
#: the research-repo standard defines and not a pointer into this repository.
#: The leading `\.?` is load-bearing and was missing in the first draft: every
#: path this check exists for begins `.claude/`, so without it the scan matched
#: nothing and the live test passed over the defect it was written to catch.
BACKTICKED_PATH = re.compile(r"`(\.?[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|py|json|toml|ya?ml|sh))`")
#: Word-bounded, and that is the whole point. An unbounded `pack` is satisfied
#: by "the package documentation", "the packaging notes" or "unpack the brief",
#: so an unqualified citation with any of those within the window read as
#: qualified and the scan passed it -- verified against all three before this
#: was tightened. A guard with a false negative is worse than no guard, because
#: the class then looks clean. The boundary still matches what the prose
#: actually says: `pack`, `pack's`, and the `pack` in `sd-ai-command-pack`,
#: whose preceding `-` is a non-word character.
QUALIFIER = re.compile(r"\bpack\b", re.IGNORECASE)

#: Enough to reach back over "live in the sd-ai-command-pack checkout's" and a
#: line wrap, and short enough that the word has to be about this citation.
#:
#: Read on *both* sides of the citation, which the first version did not.
#: English puts the qualification either way round -- "the cap is in the
#: sd-ai-command-pack checkout's `<path>`" and "`<path>` ... that file lives
#: only in the sd-ai-command-pack checkout" are the same statement -- and a
#: guard that accepts one word order and not the other enforces a house style
#: instead of the invariant. Both forms are live in `skills/` today.
QUALIFIER_WINDOW = 100


def skill_documents(root: pathlib.Path) -> list[pathlib.Path]:
    """Every authored `*.md` under `skills/`, walked from the filesystem.

    Enumeration, not a roster. A skill that acquires a pack-path citation next
    month is covered the day it is written, with nobody updating anything --
    which is the property the hardcoded predecessor did not have.
    """

    return contained(root, sorted((root / SKILLS_DIR).rglob("*.md")))


def pack_rule_paths(root: pathlib.Path) -> set[str]:
    """The pack's authored rule files, as the paths a skill would cite them by.

    Globbed, so the scope grows with the directory rather than with anyone's
    memory of what is in it.
    """

    rules = root / RULES_DIR
    return {
        str(rule.relative_to(root))
        for rule in contained(root, sorted(rules.rglob("*.md")))
    }


def rule_path_citations(root: pathlib.Path) -> list[tuple[pathlib.Path, str, bool]]:
    """Every citation of a pack rule file from any skill, and whether the prose
    beside it names the checkout that holds it.

    Enumerated from disk on both axes: the documents come from walking
    `skills/`, and what counts as a rule path comes from walking
    `.claude/rules/`. Neither is a list anybody maintains.
    """

    rule_paths = pack_rule_paths(root)
    found: list[tuple[pathlib.Path, str, bool]] = []
    for doc in skill_documents(root):
        # Newlines flattened: the qualifier routinely wraps away from the path.
        flat = doc.read_text(encoding="utf-8").replace("\n", " ")
        for match in BACKTICKED_PATH.finditer(flat):
            cited = match.group(1)
            if cited not in rule_paths:
                continue
            # The citation itself is excluded from the window on purpose: a
            # cited path with `pack` as a segment would otherwise qualify
            # itself, which is a citation vouching for its own resolution.
            before = flat[max(0, match.start() - QUALIFIER_WINDOW):match.start()]
            after = flat[match.end():match.end() + QUALIFIER_WINDOW]
            found.append((doc, cited, bool(QUALIFIER.search(before) or QUALIFIER.search(after))))
    return found


def unqualified_rule_paths(root: pathlib.Path) -> list[str]:
    """The failures, as `<document>: <path>` lines."""

    return [
        f"{doc.relative_to(root)}: `{cited}` lives only in this pack, cited to a reader"
        " standing in some other checkout without naming the pack"
        for doc, cited, qualified in rule_path_citations(root)
        if not qualified
    ]


class ForeignCheckoutCitationTests(unittest.TestCase):
    def test_no_rule_path_is_cited_as_if_the_reader_s_checkout_had_it(self) -> None:
        problems = unqualified_rule_paths(REPO_ROOT)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_the_scan_reaches_the_skills(self) -> None:
        """The control, and it is not a formality.

        The first draft's regex rejected a leading dot, so it matched none of
        the `.claude/...` paths this check exists for and the test above passed
        on the unfixed tree. Asserting that the skills were globbed is not
        enough; both ends of the walk have to have produced something and a
        citation has to have been classified.
        """

        self.assertNotEqual(skill_documents(REPO_ROOT), [], "no skill document was walked")
        self.assertNotEqual(pack_rule_paths(REPO_ROOT), set(), "no rule file was walked")
        self.assertNotEqual(rule_path_citations(REPO_ROOT), [], "no rule citation was classified")

    def test_the_walk_covers_every_skill_and_not_a_named_one(self) -> None:
        """The generalisation, asserted rather than assumed.

        The predecessor hardcoded `skills/sd-research-repo` and so watched one
        skill while four carried the citation. Two things are checked. Every
        directory holding a `SKILL.md` is reached by the walk -- computed from
        disk on both sides, so adding a skill cannot quietly fall outside it.
        And the citations actually classified come from more than one skill,
        which a walk that had silently collapsed back to a single directory
        could not satisfy.
        """

        authored = {
            skill.parent for skill in (REPO_ROOT / SKILLS_DIR).rglob("SKILL.md")
        }
        self.assertGreater(len(authored), 1, "the skills tree did not enumerate")
        walked = {doc.parent for doc in skill_documents(REPO_ROOT)}
        self.assertEqual(authored - walked, set(), "a skill directory was not walked")

        cited_by = {doc.relative_to(REPO_ROOT).parts[1] for doc, _, _ in rule_path_citations(REPO_ROOT)}
        self.assertGreater(len(cited_by), 1, f"only one skill was scanned: {sorted(cited_by)}")

    def fixture(self) -> pathlib.Path:
        """A checkout with the cap file and an empty `skills/` tree."""

        import tempfile

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = pathlib.Path(temporary.name)
        (root / SKILLS_DIR).mkdir()
        (root / ".claude" / "rules").mkdir(parents=True)
        (root / ".claude" / "rules" / "caps.md").write_text("| Cap |\n", encoding="utf-8")
        return root

    def test_an_unqualified_pack_path_is_caught_and_a_qualified_one_is_not(self) -> None:
        """The guard against the guard: the defect this class exists for.

        Both halves matter. Without the first the check can never fail; without
        the second it fails on every correctly-written citation and gets
        deleted the next time someone needs the build green.
        """

        root = self.fixture()
        skill = root / SKILLS_DIR / "sd-example"
        (skill / "references").mkdir(parents=True)

        document = skill / "SKILL.md"
        document.write_text("its cap is in\n`.claude/rules/caps.md`.\n", encoding="utf-8")
        self.assertEqual(len(unqualified_rule_paths(root)), 1)

        document.write_text(
            "its cap is in the pack's\n`.claude/rules/caps.md`.\n", encoding="utf-8")
        self.assertEqual(unqualified_rule_paths(root), [])

    def test_any_skill_is_watched_and_the_failure_names_the_one_at_fault(self) -> None:
        """The generalisation, at fixture scale.

        Three skills, none of them the one the predecessor hardcoded, and only
        the middle one unqualified. A guard scoped to a named skill reports
        nothing here; this one reports exactly the offender, by name. The two
        well-written neighbours are the other direction -- a guard that fires
        on correct prose is worse than the bug, because it gets deleted.
        """

        root = self.fixture()
        for name, prose in (
            ("sd-alpha", "its cap is in the sd-ai-command-pack checkout's"),
            ("sd-beta", "its cap is in"),
            ("sd-gamma", "read the caps in the pack's"),
        ):
            skill = root / SKILLS_DIR / name
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                f"{prose}\n`.claude/rules/caps.md`.\n", encoding="utf-8")

        problems = unqualified_rule_paths(root)
        self.assertEqual(len(problems), 1, "\n".join(problems))
        self.assertIn(f"{SKILLS_DIR}/sd-beta/SKILL.md", problems[0])

    def test_the_qualifier_counts_on_either_side_of_the_citation(self) -> None:
        """The word order is prose, not the invariant.

        "the pack's `<path>`" and "`<path>` ... that file lives only in the
        sd-ai-command-pack checkout" say the same thing, and both are live in
        `skills/` today. A window that reads only backwards passes the first
        and fails the second, which makes the guard a style rule. The third
        case is the one that must still fail: a mention far enough away to be
        about something else does not qualify anything.
        """

        root = self.fixture()
        skill = root / SKILLS_DIR / "sd-example"
        skill.mkdir()
        document = skill / "SKILL.md"

        document.write_text(
            "the cap is on that row in\n`.claude/rules/caps.md`.\nThat file lives only in"
            " the sd-ai-command-pack checkout.\n", encoding="utf-8")
        self.assertEqual(unqualified_rule_paths(root), [])

        document.write_text(
            "the cap is on that row in\n`.claude/rules/caps.md`.\n"
            f"{'Read it before promoting the item. ' * 6}It ships with the pack.\n",
            encoding="utf-8")
        self.assertEqual(len(unqualified_rule_paths(root)), 1)

    def test_a_word_containing_pack_does_not_qualify_a_citation(self) -> None:
        """The false negative from the other side, and the reason for `\\b`.

        The first version matched `pack` as a bare substring, so "the package
        documentation", "the packaging notes" and "unpack the brief" all read
        as naming this pack and let an unqualified citation through. Each of
        the three was confirmed to slip through before the boundary was added.
        A guard that cannot fail is worse than no guard: the class it watches
        then looks clean.

        The second half is the one that matters as much -- the boundary must
        still accept what the prose really says, or the guard fires on every
        correct citation and gets deleted the next time the build is red.
        """

        root = self.fixture()
        skill = root / SKILLS_DIR / "sd-example"
        skill.mkdir()
        document = skill / "SKILL.md"

        for decoy in (
            "the package documentation says the cap is in",
            "see the packaging notes; the cap is in",
            "unpack the brief first. The cap is in",
            "the cap is in",
        ):
            with self.subTest(lead=decoy):
                document.write_text(f"{decoy}\n`.claude/rules/caps.md`.\n", encoding="utf-8")
                self.assertEqual(len(unqualified_rule_paths(root)), 1)

        for real in (
            "the cap is in the sd-ai-command-pack checkout's",
            "the caps live in the pack's",
            "read it in the pack at",
        ):
            with self.subTest(lead=real):
                document.write_text(f"{real}\n`.claude/rules/caps.md`.\n", encoding="utf-8")
                self.assertEqual(unqualified_rule_paths(root), [])

    def test_paths_that_are_not_pack_rules_are_left_alone(self) -> None:
        """The scope, and why it is the rules directory rather than everything.

        Each of these is correct *because* it resolves against the reader's
        checkout, and rewriting it to name the pack would be the worse bug this
        test exists to prevent:

        * `references/x.md` ships beside the installed skill.
        * `.github/sd-review.json` and `.github/workflows/sd-review-route.yml`
          are per-repository configuration written into the reader's checkout
          by `bin/sd_setup_github.py`; the reader's copy is the one that
          governs. A draft of this class that flagged every path resolving in
          this checkout reported all three, plus `.github/sd-status.json`.
        * a path this checkout does not have is naming another repository,
          which is what the prose beside it says.
        """

        root = self.fixture()
        skill = root / SKILLS_DIR / "sd-example"
        skill.mkdir()
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / ".github" / "sd-review.json").write_text("{}\n", encoding="utf-8")
        (root / ".github" / "workflows" / "route.yml").write_text("on: push\n", encoding="utf-8")
        (skill / "SKILL.md").write_text(
            "read `references/conventions.md`, the repository's `.github/sd-review.json`,"
            " the route in `.github/workflows/route.yml`, and"
            " `local-adversarial-gate/core.md`\n",
            encoding="utf-8")
        self.assertEqual(unqualified_rule_paths(root), [])


if __name__ == "__main__":
    unittest.main()
