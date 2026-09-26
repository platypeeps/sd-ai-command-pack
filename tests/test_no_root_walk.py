"""No test builds its corpus by walking the repository root.

sd:1404. Every root-level corpus in this suite comes from `git ls-files`, so a
local run cannot see what the index does not hold: a `.venv` symlink in a
borrowing worktree (sd:1020), scratch output, coverage sidecars, agent working
files. A test that rglobs the root instead sees all of them, and the failure
it produces is a local red that CI cannot reproduce. Until this file, that
property was a convention established by a grep; nothing failed when the next
walker landed.

**What counts as a walk.** A call to `rglob`, `glob`, `iterdir` or `walk` on
a receiver that is the root; `os.walk`, `os.listdir` or `os.scandir` given the
root; and `glob.glob`/`glob.iglob` given `root_dir=` the root, or a pattern
whose first component under the root is a wildcard.

**What counts as the root.** Not a name. `REPO_ROOT.rglob` is the spelling a
token match catches, and the spelling nobody needs help with. The receiver is
evaluated instead: `Path(__file__)` climbed to the checkout by `.parent`,
`.parents[n]` or `os.path.dirname`, through `resolve()`, `str()` and the like,
and through every binding that carries it -- a local alias (`root =
REPO_ROOT`, then `root.rglob`), a chain of them, a class attribute set on
`self` or `cls`, a parameter default, a parameter that a call in the same
module passes the root to, and a name imported from a sibling module in
`tests/`. A path built from the root (`REPO_ROOT / "skills"`) is a different
tree and is not a walk of the root.

**Which modules.** The `.py` files the index holds directly under `tests/`,
from `git ls-files`, for the same reason: an untracked scratch module is not
the suite. Depths above the checkout collapse to one value, so a loop that
climbs by rebinding a name settles.

**What this does not do**, stated rather than left to be discovered. Bindings
are read without flow: a name bound to the root anywhere in its scope is the
root everywhere in it, which over-reports and never under-reports. It does not
follow a root through a container, a return value, or a call into another
module. It does not see a walk that a subprocess makes (`find`, `ls`). A
reviewer stands behind those.

**The ratchet.** `KNOWN_ROOT_WALKS` holds the sites that walked the root when
this landed, each with its reason. It only shrinks: a site not in it fails,
and an entry that no longer matches a site fails too, so the list cannot rot
into an allowance for whatever replaces it.
"""

# This module reads every module in `tests/`, so no changed-files fast path
# may narrow it away. `.github/scripts/select-tests.py` greps for the line below.
# select-tests: always-run

from __future__ import annotations

import ast
import pathlib
import subprocess
import tempfile
import textwrap
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TESTS.parent

#: How many directory levels a module in `tests/` sits below the checkout.
#: `Path(__file__)` is the file; its first parent is `tests/`, its second the root.
ROOT_DEPTH = 2
#: Every depth above the checkout. A climb never descends, so no depth past
#: `ROOT_DEPTH` can come back to it; collapsing them keeps the domain finite,
#: and a loop that rebinds `root = root.parent` settles instead of growing.
ABOVE = ROOT_DEPTH + 1

#: Methods that list a directory when called on a path.
WALK_METHODS = frozenset({"rglob", "glob", "iterdir", "walk"})
#: `os` functions that list the directory in their first argument.
OS_WALKS = frozenset({"walk", "listdir", "scandir"})
#: Calls that return their path argument's location unchanged.
SAME_PLACE = frozenset({"Path", "PurePath", "PosixPath", "str", "fspath",
                        "abspath", "realpath", "normpath", "expanduser"})
SAME_PLACE_METHODS = frozenset({"resolve", "absolute", "expanduser"})
WILDCARD = frozenset("*?[")

#: `module: source` of each walk of the root that predates the gate, with why.
#: Only shrinks. Do not add to it; fix the new site instead.
KNOWN_ROOT_WALKS: dict[str, str] = {
    'test_doc_citations.py: root.rglob("*.md")':
        "corpus()'s fallback when `git ls-files` cannot run; the grep that "
        "measured sd:1404 missed it, because the root arrives as `root or REPO_ROOT`.",
}


class Module:
    """The bindings of one module in `tests/`, and the walks of the root in it.

    A value is the set of directory depths an expression can take, counted as
    levels above the module's own file; `ROOT_DEPTH` in the set means it can be
    the checkout. A set rather than one answer is what lets a name bound twice
    keep both.
    """

    def __init__(self, path: pathlib.Path, loader: "Loader") -> None:
        self.path = path
        self.loader = loader
        self.tree = ast.parse(path.read_text(encoding="utf-8"))
        self.source = path.read_text(encoding="utf-8")
        # scope node -> name -> expressions bound to it
        self.bindings: dict[ast.AST, dict[str, list[ast.AST]]] = {}
        # class name -> attribute -> expressions bound to it
        self.attributes: dict[str, dict[str, list[ast.AST]]] = {}
        self.bases: dict[str, list[str]] = {}
        self.parent: dict[ast.AST, ast.AST] = {}
        self.imported: dict[str, tuple[str, str]] = {}
        self.module_aliases: dict[str, str] = {}
        self.values: dict[tuple[int, str], frozenset[int]] = {}
        self._index()
        self._settle()

    # -- collection -----------------------------------------------------

    def _index(self) -> None:
        for node in ast.walk(self.tree):
            for child in ast.iter_child_nodes(node):
                self.parent[child] = node
        functions = {}
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.setdefault(node.name, []).append(node)
                self._bind_defaults(node)
            elif isinstance(node, ast.ClassDef):
                self.bases[node.name] = [b.id for b in node.bases if isinstance(b, ast.Name)]
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                self._bind_assignment(node)
            elif isinstance(node, ast.ImportFrom):
                self._bind_import_from(node)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.module_aliases[alias.asname or alias.name] = alias.name
        # A parameter a call in this module passes the root to.
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                for function in functions.get(node.func.id, ()):
                    self._bind_call(function, node)

    def _scope(self, node: ast.AST) -> ast.AST:
        """The function or module whose names `node` reads and binds."""
        current = self.parent.get(node)
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                                    ast.Module, ast.ClassDef)):
                return current
            current = self.parent.get(current)
        return self.tree

    def _enclosing_class(self, node: ast.AST) -> str | None:
        current = self.parent.get(node)
        while current is not None:
            if isinstance(current, ast.ClassDef):
                return current.name
            current = self.parent.get(current)
        return None

    def _bind(self, scope: ast.AST, name: str, value: ast.AST) -> None:
        self.bindings.setdefault(scope, {}).setdefault(name, []).append(value)

    def _bind_attribute(self, owner: str, name: str, value: ast.AST) -> None:
        self.attributes.setdefault(owner, {}).setdefault(name, []).append(value)

    def _bind_target(self, target: ast.AST, value: ast.AST, anchor: ast.AST) -> None:
        if isinstance(target, ast.Name):
            scope = self._scope(anchor)
            self._bind(scope, target.id, value)
            if isinstance(scope, ast.ClassDef):
                self._bind_attribute(scope.name, target.id, value)
        elif (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
              and target.value.id in ("self", "cls")):
            owner = self._enclosing_class(anchor)
            if owner is not None:
                self._bind_attribute(owner, target.attr, value)
        elif (isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List))
              and len(target.elts) == len(value.elts)):
            for inner, part in zip(target.elts, value.elts, strict=True):
                self._bind_target(inner, part, anchor)

    def _bind_assignment(self, node: ast.AST) -> None:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                self._bind_target(target, node.value, node)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            self._bind_target(node.target, node.value, node)
        elif isinstance(node, ast.NamedExpr):
            self._bind_target(node.target, node.value, node)

    def _bind_defaults(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        args = function.args
        positional = [*args.posonlyargs, *args.args]
        for arg, default in zip(positional[len(positional) - len(args.defaults):], args.defaults, strict=True):
            self._bind(function, arg.arg, default)
        for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
            if default is not None:
                self._bind(function, arg.arg, default)

    def _bind_call(self, function: ast.FunctionDef | ast.AsyncFunctionDef, call: ast.Call) -> None:
        params = [a.arg for a in (*function.args.posonlyargs, *function.args.args)]
        for param, value in zip(params, call.args, strict=False):
            if not isinstance(value, ast.Starred):
                self._bind(function, param, value)
        known = set(params) | {a.arg for a in function.args.kwonlyargs}
        for keyword in call.keywords:
            if keyword.arg in known:
                self._bind(function, keyword.arg, keyword.value)

    def _bind_import_from(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if node.level == 1 or module.startswith("tests."):
            stem = module.rsplit(".", 1)[-1] if module else ""
            for alias in node.names:
                if stem:
                    self.imported[alias.asname or alias.name] = (stem, alias.name)
                else:
                    self.module_aliases[alias.asname or alias.name] = f"tests.{alias.name}"

    # -- evaluation -----------------------------------------------------

    def _settle(self) -> None:
        """Evaluate every binding until no value grows: aliases chain.

        Values only grow, and each is a subset of `0..ABOVE`, so this ends."""
        while True:
            before = dict(self.values)
            for scope, names in self.bindings.items():
                for name, exprs in names.items():
                    self.values[(id(scope), name)] = frozenset().union(
                        *(self.value(e) for e in exprs))
            for owner, names in self.attributes.items():
                for name, exprs in names.items():
                    self.values[(-1, f"{owner}.{name}")] = frozenset().union(
                        *(self.value(e) for e in exprs))
            if self.values == before:
                return

    def _name(self, name: str, anchor: ast.AST) -> frozenset[int]:
        scope = self._scope(anchor)
        while True:
            if name in self.bindings.get(scope, {}):
                return self.values.get((id(scope), name), frozenset())
            if scope is self.tree:
                break
            scope = self._scope(scope)
            # Python does not read a class body's names from a method.
            while isinstance(scope, ast.ClassDef):
                scope = self._scope(scope)
        if name == "__file__":
            return frozenset({0})
        if name in self.imported:
            stem, attr = self.imported[name]
            return self.loader.exported(stem, attr)
        return frozenset()

    def _attribute(self, owner: str, name: str, seen: frozenset[str] = frozenset()) -> frozenset[int]:
        if owner in seen:
            return frozenset()
        found = self.values.get((-1, f"{owner}.{name}"))
        if found is not None:
            return found
        return frozenset().union(*(self._attribute(base, name, seen | {owner})
                                   for base in self.bases.get(owner, ())))

    def value(self, node: ast.AST) -> frozenset[int]:
        if isinstance(node, ast.BoolOp):  # `root = root or REPO_ROOT`
            return frozenset().union(*(self.value(v) for v in node.values))
        if isinstance(node, ast.IfExp):
            return self.value(node.body) | self.value(node.orelse)
        if isinstance(node, ast.Name):
            return self._name(node.id, node)
        if isinstance(node, ast.Attribute):
            base = node.value
            if node.attr == "parent":
                return _climb(self.value(base), 1)
            if isinstance(base, ast.Name) and base.id in ("self", "cls"):
                owner = self._enclosing_class(node)
                return self._attribute(owner, node.attr) if owner else frozenset()
            if isinstance(base, ast.Name) and base.id in self.module_aliases:
                stem = self.module_aliases[base.id]
                if stem.startswith("tests."):
                    return self.loader.exported(stem.rsplit(".", 1)[-1], node.attr)
            return frozenset()
        if isinstance(node, ast.Subscript):
            if (isinstance(node.value, ast.Attribute) and node.value.attr == "parents"
                    and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int)):
                return _climb(self.value(node.value.value), node.slice.value + 1)
            return frozenset()
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if isinstance(func, ast.Attribute) and name in SAME_PLACE_METHODS and not node.args:
                return self.value(func.value)
            if name == "dirname" and len(node.args) == 1:
                return _climb(self.value(node.args[0]), 1)
            if name in SAME_PLACE and len(node.args) == 1:
                return self.value(node.args[0])
            if name == "join" and len(node.args) == 1:
                return self.value(node.args[0])
        return frozenset()

    def is_root(self, node: ast.AST) -> bool:
        return ROOT_DEPTH in self.value(node)

    # -- walks ----------------------------------------------------------

    def _pattern_walks_root(self, node: ast.AST) -> bool:
        """A glob pattern whose first component under the root is a wildcard."""
        if isinstance(node, ast.Call) and len(node.args) == 1:
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in SAME_PLACE:
                return self._pattern_walks_root(node.args[0])
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "join" and node.args:
            head, rest = node.args[0], node.args[1:]
            return self.is_root(head) and bool(rest) and _wild_first(rest[0])
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return self.is_root(node.left) and _wild_first(node.right)
        if isinstance(node, ast.JoinedStr) and len(node.values) >= 2:
            head, rest = node.values[0], node.values[1]
            return (isinstance(head, ast.FormattedValue) and self.is_root(head.value)
                    and isinstance(rest, ast.Constant) and isinstance(rest.value, str)
                    and _wild_first(ast.Constant(rest.value.lstrip("/"))))
        return False

    def walks(self) -> list[ast.Call]:
        found = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            func = node.func
            owner = func.value
            if isinstance(owner, ast.Name) and owner.id == "os":
                if func.attr in OS_WALKS and node.args and self.is_root(node.args[0]):
                    found.append(node)
                continue
            if isinstance(owner, ast.Name) and owner.id == "glob" and func.attr in ("glob", "iglob"):
                root_dir = next((k.value for k in node.keywords if k.arg == "root_dir"), None)
                if ((root_dir is not None and self.is_root(root_dir))
                        or (node.args and self._pattern_walks_root(node.args[0]))):
                    found.append(node)
                continue
            if func.attr not in WALK_METHODS:
                continue
            if self.is_root(owner):
                args = node.args
            elif node.args and _names_path_class(owner) and self.is_root(node.args[0]):
                # `Path.rglob(REPO_ROOT, "*")`: the unbound spelling.
                args = node.args[1:]
            else:
                continue
            if func.attr == "glob" and args and not _wild_first(args[0]):
                # `REPO_ROOT.glob("skills/*/SKILL.md")` lists `skills/`, a
                # derived tree; `rglob` matches at any depth, so it has no such case.
                continue
            found.append(node)
        return found

    def report(self) -> list[str]:
        rel = self.path.name
        return [f"{rel}:{call.lineno}: {ast.get_source_segment(self.source, call)}"
                for call in sorted(self.walks(), key=lambda c: (c.lineno, c.col_offset))]


def _climb(depths: frozenset[int], levels: int) -> frozenset[int]:
    return frozenset(min(d + levels, ABOVE) for d in depths)


def _wild_first(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        first = node.value.split("/", 1)[0]
        return bool(WILDCARD & set(first))
    return False


def _names_path_class(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in ("Path", "PurePath", "PosixPath")
    return isinstance(node, ast.Attribute) and node.attr in ("Path", "PurePath", "PosixPath")


class Loader:
    """Parses the modules of one `tests/` directory once each, on demand.

    The corpus is `paths` when given, which is how a fixture directory outside
    any checkout is read; otherwise it is what the index holds directly under
    `tests/`, so an untracked scratch module never enters it.
    """

    def __init__(self, tests: pathlib.Path, paths: list[pathlib.Path] | None = None) -> None:
        self.tests = tests
        self.paths = paths
        self.modules: dict[str, Module | None] = {}

    def module(self, stem: str) -> Module | None:
        if stem not in self.modules:
            self.modules[stem] = None  # an import cycle reads as unknown
            path = self.tests / f"{stem}.py"
            self.modules[stem] = Module(path, self) if path.is_file() else None
        return self.modules[stem]

    def exported(self, stem: str, name: str) -> frozenset[int]:
        module = self.module(stem)
        if module is None:
            return frozenset()
        return module.values.get((id(module.tree), name), frozenset())

    def root_walks(self) -> list[str]:
        found = []
        paths = self.paths if self.paths is not None else tracked_modules(self.tests)
        for path in sorted(paths):
            module = self.module(path.stem)
            if module is not None:
                found.extend(module.report())
        return found


def tracked_modules(tests: pathlib.Path) -> list[pathlib.Path]:
    """The `.py` files the index holds directly under `tests/`."""
    listed = subprocess.run(
        ["git", "-C", str(tests.parent), "ls-files", "-z", "--deduplicate", "--",
         f":(glob){tests.name}/*.py"],
        check=True, capture_output=True, text=True).stdout
    return [tests.parent / rel for rel in listed.split("\0") if rel]


def site_key(line: str) -> str:
    """`module: source`, without the line number, so an edit above a known
    site does not read as a new one."""
    location, _, source = line.partition(": ")
    return f"{location.split(':', 1)[0]}: {source}"


class NoRootWalkTests(unittest.TestCase):
    def test_no_test_module_walks_the_repository_root(self) -> None:
        found = Loader(TESTS).root_walks()
        new = [line for line in found if site_key(line) not in KNOWN_ROOT_WALKS]
        self.assertEqual(new, [], "these walk the repository root; list the corpus "
                         "with `git ls-files` instead:\n" + "\n".join(new))

    def test_the_known_sites_still_exist(self) -> None:
        """The ratchet only shrinks: a fixed site leaves the list with it."""
        keys = {site_key(line) for line in Loader(TESTS).root_walks()}
        stale = sorted(set(KNOWN_ROOT_WALKS) - keys)
        self.assertEqual(stale, [], "remove these from KNOWN_ROOT_WALKS:\n" + "\n".join(stale))


class DetectorTests(unittest.TestCase):
    """The gate against a fixture `tests/` directory, so a detector that sees
    nothing cannot pass the gate above over a suite full of walkers."""

    def walks(self, source: str, header: bool = True, **siblings: str) -> list[str]:
        text = (textwrap.dedent(self.HEADER) if header else "") + textwrap.dedent(source)
        with tempfile.TemporaryDirectory() as tmp:
            tests = pathlib.Path(tmp) / "tests"
            tests.mkdir()
            (tests / "test_fixture.py").write_text(text)
            for stem, text in siblings.items():
                (tests / f"{stem}.py").write_text(textwrap.dedent(text))
            # `tests/` is a derived path, not the root: listing it is the point.
            return [line for line in Loader(tests, sorted(tests.glob("*.py"))).root_walks()
                    if line.startswith("test_fixture.py:")]

    HEADER = """\
        import glob, os, pathlib
        from pathlib import Path
        REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
    """

    def test_the_aliased_spelling_is_a_walk(self) -> None:
        """The shape sd:1404's decision note requires: bind first, walk through
        the alias. A token match on `REPO_ROOT.rglob` passes this over."""
        found = self.walks("""\
        def corpus():
            root = REPO_ROOT
            return sorted(root.rglob("*.py"))
        """)
        self.assertEqual(found, ['test_fixture.py:6: root.rglob("*.py")'])

    def test_each_spelling_of_the_root_and_of_a_walk_is_found(self) -> None:
        found = self.walks("""\
        ROOT = Path(__file__).resolve().parent.parent
        HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        a = b = REPO_ROOT
        c = a
        REPO_ROOT.rglob("*")
        ROOT.iterdir()
        c.glob("**/*.md")
        os.walk(HERE)
        os.listdir(str(ROOT))
        glob.glob(os.path.join(HERE, "**", "*.py"), recursive=True)
        glob.glob("*.md", root_dir=REPO_ROOT)
        glob.glob(f"{REPO_ROOT}/*.md")
        Path.rglob(REPO_ROOT, "*")
        Path.glob(REPO_ROOT, "*.md")
        REPO_ROOT.rglob("docs/*.md")
        """)
        self.assertEqual(len(found), 11, "\n".join(found))

    def test_a_fixture_attribute_a_default_and_a_parameter_carry_the_root(self) -> None:
        found = self.walks("""\
        import unittest
        class Base(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                cls.tree = REPO_ROOT
            def setUp(self):
                self.root = REPO_ROOT
        class Child(Base):
            def test_one(self):
                list(self.root.rglob("*"))
            def test_two(self):
                list(self.tree.iterdir())
        def listed(where=REPO_ROOT):
            return list(where.rglob("*"))
        def either(top=None):
            top = top or REPO_ROOT
            return list(top.iterdir())
        def digest(top):
            return list(top.rglob("*"))
        digest(REPO_ROOT)
        """)
        self.assertEqual(len(found), 5, "\n".join(found))

    def test_a_root_imported_from_a_sibling_is_the_root(self) -> None:
        found = self.walks("""\
            from tests.governed import REPO_ROOT as TOP
            from . import helpers
            TOP.rglob("*")
            helpers.ROOT.iterdir()
            """, header=False,
            governed="import pathlib\nREPO_ROOT = pathlib.Path(__file__).resolve().parents[1]\n",
            helpers="from pathlib import Path\nTESTS = Path(__file__).parent\nROOT = TESTS.parent\n")
        self.assertEqual(len(found), 2, "\n".join(found))

    def test_a_derived_tree_or_another_directory_is_not_a_walk(self) -> None:
        """`REPO_ROOT / "skills"` is its own tree. `tests/` is one level short
        of the root, and a temporary fixture is not the checkout at all."""
        found = self.walks("""\
        import tempfile
        TESTS = Path(__file__).resolve().parent
        (REPO_ROOT / "skills").rglob("SKILL.md")
        REPO_ROOT.glob("skills/*/SKILL.md")
        Path.glob(REPO_ROOT, "skills/*.md")
        TESTS.glob("test_*.py")
        os.walk(os.path.join(REPO_ROOT, "docs"))
        glob.glob(os.path.join(REPO_ROOT, "docs", "*.md"))
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            root.rglob("*")
        def digest(top):
            return list(top.rglob("*"))
        digest(pathlib.Path("/tmp"))
        """)
        self.assertEqual(found, [])

    def test_a_loop_that_climbs_settles(self) -> None:
        """A rebinding loop adds a level on every pass of the evaluator. Depths
        above the checkout collapse to one value, so the passes end; without
        flow the name can be the root, so its walk is reported."""
        found = self.walks("""\
        root = Path(__file__).resolve()
        while not (root / ".git").exists():
            root = root.parent
        root.rglob("*")
        """)
        self.assertEqual(found, ['test_fixture.py:7: root.rglob("*")'])

    def test_a_known_site_is_keyed_without_its_line_number(self) -> None:
        self.assertEqual(site_key('test_x.py:12: root.rglob("*: x")'),
                         'test_x.py: root.rglob("*: x")')


class CorpusTests(unittest.TestCase):
    """The modules read are the ones the index holds under `tests/`."""

    WALKER = "import pathlib\nROOT = pathlib.Path(__file__).resolve().parents[1]\nROOT.rglob('*')\n"

    def test_an_untracked_or_nested_module_is_not_in_the_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp)
            tests = repo / "tests"
            (tests / "fixtures").mkdir(parents=True)
            for name in ("test_tracked.py", "test_scratch.py", "fixtures/test_deep.py"):
                (tests / name).write_text(self.WALKER)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "tests/test_tracked.py",
                            "tests/fixtures/test_deep.py"], check=True)
            found = [site_key(line) for line in Loader(tests).root_walks()]
        self.assertEqual(found, ["test_tracked.py: ROOT.rglob('*')"])


if __name__ == "__main__":
    unittest.main()
