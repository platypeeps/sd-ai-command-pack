"""What `bin/` and `dashboard/` may not become, measured instead of asserted.

This replaces `tests/test_loc_caps.py`, which capped total lines per directory.
That cap was raised eighteen times in eleven days and lowered never, while
`bin/` grew from 8,000 lines to 20,803 -- so it never once said no. It could
not: every capability adds lines, and refusing the lines means refusing the
capability. A number that must be raised to let work proceed is a record of
growth wearing the costume of a limit.

Worse, it charged for prose. Of 20,806 lines in `bin/`, 12,414 are code and
8,392 are docstring, comment or blank. House style puts design reasoning in
docstrings, so under a line cap explaining costs exactly what implementing
costs, and the one time the cap actually bound, what got deleted was an
explanation (`dashboard/` at 3,999 of 4,000, prose trimmed to pay for code).

The checks here were chosen for one property: **they do not move when a feature
is added**. Adding a command adds functions; it does not make existing
functions branchier, or deeper, or duplicated. A ceiling on those can hold for
years without a raise, which is what separates a limit from a ledger. The
evidence that the distinction is real is in the shape of the growth itself --
between 2026-09-01 and 2026-09-11 `bin/` went 7,947 to 20,803 lines, but
top-level definitions went 273 to 618. Nearly all of that 2.6x is more
functions, not fatter ones, and no check here fires on it.

Each ceiling carries a baseline of the functions that already exceed it. The
baseline may only shrink: `test_every_baseline_entry_still_earns_its_place`
fails when an entry stops exceeding, so a function that gets fixed must be
removed from the list. New code has no such exemption. That is the opposite of
the cap's ratchet, which could only rise.
"""

import ast
import collections
import functools
import hashlib
import itertools
import pathlib
import re
import subprocess
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Ceilings. Each is a per-function measure, not a per-directory total, because
#: a total is what made the old cap grow with the work it was meant to govern.
#:
#: The numbers come from the corpus's own distribution, which is the derivation
#: the old cap never had -- it was set equal to the measurement every time, so
#: it always bound at exactly zero and always had to move. These sit near the
#: 95th percentile instead: high enough that ordinary code never sees them, low
#: enough that the tail has to argue.
#:
#:   complexity   median 5,  p95 18, p99 34, max 97  -> 20, and 30 are baselined
#:   length       median 8,  p95 38, p99 75, max 138 -> 50, and 16 are baselined
#:   depth        median 1,  p95 3,  p99 4,  max 5   -> 5,  and none are
#:
#: Depth is the one ceiling that equals the corpus maximum, which is the shape
#: the old cap had and the reason it never said no. It is kept anyway, because
#: five levels of indentation is a limit that stands on its own argument rather
#: than on this repository's current state -- the agreement is a coincidence,
#: and if a sixth level ever arrives it should have to be defended.
COMPLEXITY_CEILING = 20
LENGTH_CEILING = 50
DEPTH_CEILING = 5

#: Below this many AST nodes a function is too small for duplication to mean
#: anything: two three-line wrappers that agree are not a copy-paste problem.
CLONE_FLOOR = 25

#: How many public functions the dead-code check cannot speak for, because
#: another function in the corpus carries the same name. Downward only.
AMBIGUOUS_CEILING = 155


def tracked(*pathspecs: str) -> list[pathlib.Path]:
    """Tracked files matching `pathspecs`, as the index reports them.

    The index rather than the directory, so a stray `__pycache__` entry or an
    untracked scratch file cannot join the measurement.
    """

    output = subprocess.run(
        ["git", "ls-files", "-z", "--", *pathspecs],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / name for name in output.split("\0") if name]


@functools.cache
def sources() -> tuple[pathlib.Path, ...]:
    """Every Python file the checks govern: `bin/` and `dashboard/`.

    `migrate-*` is excluded on the same reasoning the old cap used -- those
    tools are deleted rather than kept, and holding deleted code to a standard
    it will never have to meet again is ceremony. The test is `startswith`, not
    a substring: as a substring, any new file with `migrate-` somewhere in its
    basename would leave the corpus, and nothing would have to be argued for.

    `tests/` is outside the corpus, and that is a real gap rather than a
    principle: a long test method is a worse read than a long function, not a
    better one. It is left out because test files legitimately hold near-copies
    of each other by the dozen -- that is what a table of cases looks like
    spelled out -- and the duplicate check would report every one of them.
    Governing tests needs a different clone rule, not this one relaxed.
    """

    return tuple(
        path for path in tracked("bin", "dashboard")
        if path.suffix == ".py" or _is_python_script(path)
        if not path.name.startswith("migrate-")
    )


def _is_python_script(path: pathlib.Path) -> bool:
    """A `bin/` entry point has no suffix, so the shebang is what names it.

    The whole first line, not a fixed window: `#!/usr/bin/env -S python3 -X
    importtime` pushes the word past any short prefix, and a script that falls
    out of the corpus that way is ungoverned in silence. A line cap still
    applies so a binary cannot be read to its end.
    """

    try:
        with path.open("rb") as handle:
            first = handle.readline(4096)
    except OSError:
        return False
    return first[:2] == b"#!" and b"python" in first


def _bound(args: ast.arguments, body: list[ast.stmt]) -> frozenset[str]:
    """Names this function binds: parameters, assignment targets, `as` names.

    Everything else a function mentions is free -- a module, a global, another
    function -- and those names are part of what the code *does*, not of how it
    happens to spell its locals.

    `args` is passed separately because parameters live on the signature, not
    in the body. Reading the body alone left every parameter free, so a copy
    that renamed its parameters stopped matching its original -- which is the
    one case the renaming exists to catch.
    """

    names = set()
    for statement in [*ast.walk(args), *body]:
        for node in ast.walk(statement):
            if isinstance(node, ast.arg):
                names.add(node.arg)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                names.add(node.id)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                names.add(node.name)
    return frozenset(names)


class Alpha(ast.NodeTransformer):
    """Rename a function's own locals to `v1, v2, ...` and blank constants.

    Without this a clone detector finds only literal copy-paste. With it, a
    copy whose variables were renamed on arrival -- which is what copy-paste
    between two scripts actually looks like -- still matches.

    One instance must normalize one whole function body. The counter carries
    the data flow: reusing a name gives back the number it got the first time,
    so two functions match only if they reuse their names in the same places.

    **Only bound names are renamed.** Renaming free ones too made
    `json.dumps(x)` and `yaml.dumps(x)` the same expression, so two functions
    differing only in which module they called were reported as copies.

    What this still cannot do, stated plainly rather than left to be
    discovered: the digest is an exact ordered statement sequence, so
    inserting one statement or swapping two defeats it, and constants are
    blanked, so two functions alike but for their literals match. It finds
    verbatim and renamed copies. It is not a similarity measure, and a low
    count here is not evidence that nothing was copied.
    """

    def __init__(self, bound: frozenset[str]) -> None:
        self.bound = bound
        self.names: dict[str, str] = {}

    def _rename(self, name: str) -> str:
        if name not in self.bound:
            return name
        if name not in self.names:
            self.names[name] = f"v{len(self.names) + 1}"
        return self.names[name]

    def visit_Name(self, node: ast.Name) -> ast.Name:
        return ast.copy_location(
            ast.Name(id=self._rename(node.id), ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.arg = self._rename(node.arg)
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        return ast.copy_location(ast.Constant(value="K"), node)


def _elif_chain(node: ast.If) -> list[ast.If]:
    """The `elif` arms hanging off one `if`, which are not nesting.

    Python builds `elif` as an `If` inside the previous one's `orelse`, so a
    flat thirteen-way dispatch reads to a naive walker as thirteen levels of
    nesting. Measured that way `bin/sd_writing.py`'s `run()` scores depth 15
    while indenting to 5. Punishing a flat dispatch chain would be the same
    mistake as the old cap punishing docstrings: the measure would fire on the
    readable thing.

    `elif` and `else:` followed by an indented `if` build the identical tree,
    and only the column separates them -- an `elif` arm starts where its parent
    `if` starts, a nested one starts further in. Without that test, code that
    really does indent can hide inside `else:` blocks and the depth ceiling
    never sees it. This is the one place the measure reads position rather
    than structure, because here position is the difference.
    """

    arms = []
    while (len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If)
           and node.orelse[0].col_offset == node.col_offset):
        node = node.orelse[0]
        arms.append(node)
    return arms


#: A nested scope answers for its own shape under its own name, so no measure
#: walks into one's body. `Lambda` is deliberately absent: `_walk` makes no
#: unit from a lambda, so stopping here too would leave its branches counted by
#: nobody -- `sorted(rows, key=lambda r: r.a if r.b else r.c)` would score 1.
#: A lambda is part of the expression that contains it.
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _own(function: ast.AST):
    """Nodes belonging to this function, stopping at each nested scope's body.

    A closure factory would otherwise carry every branch of the function it
    returns, and `_walk` already measures that one under its own name. Counting
    it twice makes the outer unfixable: simplifying `make_handler` cannot clear
    a score that belongs to `make_handler.Handler.do_POST`.

    A nested definition's decorators, default arguments and annotations are
    lexically the *outer* function's -- they run when the `def` is reached, not
    when the nested function is called -- so the walk descends into those and
    stops only at the body.
    """

    stack = list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, SCOPES):
            stack.extend(node.decorator_list)
            if not isinstance(node, ast.ClassDef):
                stack.extend(ast.iter_child_nodes(node.args))
        else:
            stack.extend(ast.iter_child_nodes(node))


def complexity(function: ast.AST) -> int:
    """Decision points a reader has to hold at once, this function's own only.

    Every `elif` arm counts. An earlier draft discounted them, on the reasoning
    that a flat dispatch chain reads as one decision -- but that handed anyone
    a way to clear this check by rewriting three sequential `if`s as `elif`s,
    which changes the score and nothing else. A branch is a branch. The flat-
    chain argument is true about *indentation*, and that is where it is applied:
    `depth` discounts the arms, `complexity` does not.
    """

    score = 1
    for node in _own(function):
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While,
                             ast.ExceptHandler, ast.Assert, ast.IfExp,
                             ast.match_case)):
            score += 1
        elif isinstance(node, ast.BoolOp):
            score += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            score += 1 + len(node.ifs)
    return score


NESTS = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncFor, ast.AsyncWith)


def depth(node: ast.AST, level: int = 0) -> int:
    """Deepest indented block, with `elif` arms held at their visual level."""

    deepest = level
    arms = set()
    if isinstance(node, ast.If):
        arms = {id(arm) for arm in _elif_chain(node)}
    for child in ast.iter_child_nodes(node):
        if isinstance(child, SCOPES):
            continue
        inner = level + 1 if isinstance(child, NESTS) else level
        if id(child) in arms:
            inner = level
        deepest = max(deepest, depth(child, inner))
    return deepest


Unit = collections.namedtuple("Unit", "key path name line span nodes digest score nest")


@functools.cache
def units() -> tuple[Unit, ...]:
    """Every function in the governed corpus, measured once.

    Cached because six tests read it and the corpus cannot change mid-run.
    Measuring inside the walk rather than re-parsing per check is what keeps
    the whole module under a second; a health check nobody waits for is a
    health check that gets commented out.
    """

    found = []
    for path in sources():
        relative = path.relative_to(REPO_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError) as failure:
            # Never `continue`. Skipping the file would drop every function in
            # it from every ceiling at once, and the suite would go green on a
            # smaller corpus without saying so.
            BROKEN.append(f"{relative}: {failure}")
            continue
        PARSED.add(relative)
        found.extend(_walk(tree, relative, ()))
    return tuple(found)


#: Files the walk could not read or parse, and files it did.
#: `test_the_corpus_is_complete` compares both against the index.
BROKEN: list[str] = []
PARSED: set[str] = set()


def _walk(scope: ast.AST, relative: str, prefix: tuple[str, ...]) -> list[Unit]:
    """Functions under one scope, named by the classes that enclose them.

    The enclosing class is part of the name because five pairs in this
    repository share a bare one -- two `close`, two `refuse`, two `sandboxed`.
    A baseline keyed on the bare name would exempt both members of every pair,
    which is the quiet kind of hole a baseline must not have.
    """

    found = []
    for node in ast.iter_child_nodes(scope):
        if isinstance(node, ast.ClassDef):
            found.extend(_walk(node, relative, prefix + (node.name,)))
            continue
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.extend(_walk(node, relative, prefix))
            continue
        name = ".".join(prefix + (node.name,))
        body = [
            statement for statement in node.body
            if not (isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str))
        ]
        found.extend(_walk(node, relative, prefix + (node.name,)))
        if not body:
            continue
        nodes = sum(1 for statement in body for _ in ast.walk(statement))
        # One `Alpha` for the whole body, never one per statement. Renaming
        # each statement in isolation restarts the counter, so `foo(x); bar(y)`
        # and `foo(x); bar(x)` both normalize to `v1(v2); v1(v2)` and two
        # unrelated functions collide. Numbering across the body is what makes
        # the digest mean "same shape, same data flow".
        rendered = ast.unparse(ast.Module(body=body, type_ignores=[]))
        normalized = ast.dump(
            Alpha(_bound(node.args, body)).visit(ast.parse(rendered)))
        found.append(Unit(
            key=f"{relative}::{name}",
            path=relative,
            name=node.name,
            line=node.lineno,
            span=len(rendered.splitlines()),
            nodes=nodes,
            digest=hashlib.sha1(normalized.encode()).hexdigest(),
            score=complexity(node),
            nest=depth(node),
        ))
    return found


#: Functions that already exceed a ceiling, and may leave this list but never
#: join it. Each entry is `path::name`. A new violation fails its check; an
#: entry that stops violating fails `test_every_baseline_entry_still_earns_its_place`,
#: so the list cannot quietly outlive the debt it records.
COMPLEX = frozenset({
    "bin/sd-review::parse_findings",  # 22
    "bin/sd-review::render",  # 34
    "bin/sd-review::resolve_subject",  # 26
    "bin/sd-review::review",  # 97
    "bin/sd-review::run_provider",  # 40
    "bin/sd-ship::Ship.merge",  # 25
    "bin/sd-ship::Ship.prepare",  # 53
    "bin/sd-ship::Ship.review",  # 45
    "bin/sd-ship::Ship.review_inputs",  # 44
    "bin/sd-ship::commit_paths",  # 21
    "bin/sd-status::_work_rows",  # 31
    "bin/sd::store_add",  # 28
    "bin/sd::store_set",  # 25
    "bin/sd::validate_kind",  # 28
    "bin/sd_install.py::cmd_user",  # 24
    "bin/sd_install.py::main",  # 27
    "bin/sd_install.py::remove_hook",  # 25
    "bin/sd_lib.py::remote_permits_full",  # 27
    "bin/sd_registry.py::_provider",  # 34
    "bin/sd_registry.py::parse",  # 26
    "bin/sd_registry.py::url_response",  # 26
    "bin/sd_research_pins.py::report",  # 25
    "bin/sd_ship_dispositions.py::context",  # 22
    "bin/sd_ship_dispositions.py::validate",  # 27
    "bin/sd_ship_remote.py::GitHub.ready",  # 29
    "bin/sd_work.py::run",  # 29
    "bin/sd_writing.py::register",  # 22
    "bin/sd_writing.py::run",  # 37
    "dashboard/plugins.py::bounded_run",  # 23
    "dashboard/server.py::make_handler.Handler.do_POST",  # 26
})

LONG = frozenset({
    "bin/sd-review::render",  # 78
    "bin/sd-review::review",  # 138
    "bin/sd-review::run_provider",  # 69
    "bin/sd-ship::Ship.merge",  # 55
    "bin/sd-ship::Ship.prepare",  # 80
    "bin/sd-ship::Ship.review",  # 75
    "bin/sd::build_parser",  # 135
    "bin/sd::store_set",  # 57
    "bin/sd_install.py::cmd_user",  # 64
    "bin/sd_install.py::main",  # 63
    "bin/sd_work.py::register",  # 58
    "bin/sd_work.py::run",  # 54
    "bin/sd_writing.py::register",  # 57
    "bin/sd_writing.py::run",  # 86
    "dashboard/plugins.py::bounded_run",  # 91
    "dashboard/server.py::make_handler",  # 105
})

DEEP: frozenset[str] = frozenset()

#: Names the dead-code check must not flag, because something other than a
#: call site reaches them. `html.parser.HTMLParser` dispatches to its
#: `handle_*` methods by name from inside the base class, so no caller appears
#: anywhere. This is the whole exemption list; it is not a place to put a
#: function nobody could find a caller for.
DYNAMIC = frozenset({
    "dashboard/markup.py::Filter.handle_data",
    "dashboard/markup.py::Filter.handle_endtag",
    "dashboard/markup.py::Filter.handle_startendtag",
})

#: Duplicate function pairs already in the tree, each as a sorted 2-tuple.
CLONES = frozenset({
    ("bin/sd-handoff-restore::canonical_remote",
     "bin/sd-handoff::canonical_remote"),
    ("bin/sd-handoff-restore::git",
     "bin/sd-handoff::git"),
    ("bin/sd-handoff-restore::git",
     "bin/sd-skill-use::git"),
    ("bin/sd-handoff-restore::state_home",
     "bin/sd-handoff::state_home"),
    ("bin/sd-handoff::git",
     "bin/sd-skill-use::git"),
})


class CodeHealth(unittest.TestCase):
    """Per-function ceilings, none of which move when a feature is added."""

    def test_the_corpus_is_complete(self):
        """The measurement must fail loudly rather than pass on a smaller corpus.

        A check whose enumeration quietly matches less than it should reports
        success forever, and that is the one failure mode a ceiling cannot
        survive -- so it is asserted before any ceiling is.

        The comparison is against a fresh `git ls-files`, not against a
        remembered count. A floor like "more than twenty files" would let the
        corpus lose half its contents and still pass, which is the same
        mistake as trusting a number somebody wrote down.
        """

        found = units()
        self.assertEqual(BROKEN, [], "files the walk could not read or parse")
        expected = {
            path for path in tracked("bin", "dashboard")
            if not path.name.startswith("migrate-")
            if path.suffix == ".py" or _is_python_script(path)
        }
        self.assertEqual(set(sources()), expected,
                         "the corpus does not match what the index holds")
        self.assertEqual(
            PARSED, {path.relative_to(REPO_ROOT).as_posix() for path in expected},
            "the walk did not parse every file the index holds")
        self.assertEqual(len(found), len({unit.key for unit in found}),
                         "two functions share one key; a baseline entry would "
                         "exempt both of them")

    def test_no_function_is_branchier_than_the_ceiling(self):
        """Cyclomatic complexity, which counts paths a reader must hold at once."""

        over = sorted(
            (unit.key, unit.score, _where(unit))
            for unit in units()
            if unit.key not in COMPLEX and unit.score > COMPLEXITY_CEILING
        )
        self.assertEqual(over, [], _explain(
            "branchier than", COMPLEXITY_CEILING, over,
            "Split the decision out of the work, or dispatch through a table."))

    def test_no_function_is_longer_than_the_ceiling(self):
        """Statements, counted as `ast.unparse` renders them, one per line.

        Not physical lines. Physical lines are a formatting fact: semicolons,
        `if x: return` on one line, and joined call arguments all shrink a
        function without changing a thing inside it, which is a way to pass
        this check by reflowing. Unparsing puts one statement on one line and
        cannot be compressed, so the number measures the function.

        The docstring is not counted, which is the whole break from the old
        cap: explaining is free here, and only the code is charged. Unlike
        that cap this is per function, so writing a new one costs nothing.
        Only letting one grow past 80 statements does.
        """

        over = sorted(
            (unit.key, unit.span, _where(unit)) for unit in units()
            if unit.key not in LONG and unit.span > LENGTH_CEILING
        )
        self.assertEqual(over, [], _explain(
            "longer than", LENGTH_CEILING, over,
            "Name the middle of it and move that out."))

    def test_no_function_nests_deeper_than_the_ceiling(self):
        """Indented blocks, with a flat `elif` ladder held at one level."""

        over = sorted(
            (unit.key, unit.nest, _where(unit)) for unit in units()
            if unit.key not in DEEP and unit.nest > DEPTH_CEILING
        )
        self.assertEqual(over, [], _explain(
            "deeper than", DEPTH_CEILING, over,
            "Return early, or lift the inner block into its own function."))

    def test_no_two_functions_are_the_same_function(self):
        """Structural duplicates, after renaming locals and blanking constants.

        This is the check the line cap was reaching for and could not make.
        Copy-paste raises the total, so a cap punished it -- but it punished
        an original of the same length identically, and the only way to obey
        was to delete something else. Here the copy fails and the original
        does not.
        """

        by_digest = collections.defaultdict(list)
        where = {}
        for unit in units():
            if unit.nodes >= CLONE_FLOOR:
                by_digest[unit.digest].append(unit.key)
                where[unit.key] = _where(unit)
        pairs = sorted(
            tuple(sorted(pair))
            for keys in by_digest.values()
            for pair in itertools.combinations(sorted(keys), 2)
        )
        new = [pair for pair in pairs if pair not in CLONES]
        self.assertEqual(new, [], _explain(
            "a structural duplicate of", None,
            [(left, right, f"{where[left]} and {where[right]}") for left, right in new],
            "One of the two should call the other, or both should call a third."))

    def test_no_public_function_is_unreferenced(self):
        """Dead code, which is slop that already passed review.

        A name defined in the corpus and written nowhere else in the repo is
        either unused or reached dynamically; the second is rare enough here
        that saying so in a `DYNAMIC` entry is cheap.

        **This check only sees names that are unique in the corpus.** The
        evidence is a text count, and a text count cannot tell one `main` from
        the twenty other `main` definitions here -- their shared count never
        falls to one, so a dead one among them hides behind its live namesakes.
        Rather than let that pass for coverage, the ambiguous names are
        excluded outright and counted by `test_the_shared_name_blind_spot_only_shrinks`,
        so the gap has a number instead of being discovered later.
        """

        # Keyed on the full key, never on the bare name. Keyed on the name,
        # 111 of the 621 public functions here overwrite each other -- `main`
        # twenty-one ways, `run` thirteen -- and a dead one hides behind any
        # live namesake. That is the same hole `_walk` exists to close.
        defined = {
            unit.key: unit.name for unit in units()
            if not unit.name.startswith("_") and unit.key not in DYNAMIC
            and unit.name not in _ambiguous()
        }
        # This file is excluded from the haystack on purpose. Listing a name
        # in `DYNAMIC` above would otherwise be a second occurrence of it, so
        # the act of exempting a function would also be the evidence that it
        # needed no exemption -- and removing the entry would not bring the
        # failure back.
        haystack = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in tracked("bin", "dashboard", "tests", "skills", "docs",
                                ".github", ".claude", "*.md")
            if path != pathlib.Path(__file__).resolve()
        )
        # Whole identifiers, not substrings. Counting substrings made 77 names
        # permanently unreportable because a longer name contained them --
        # `add` inside `add_row`, `check` inside `check_url` -- so the check
        # could never fire on them at all. `.github` and `.claude` are in the
        # pathspec because a function reached only from a workflow or a hook
        # is referenced, not dead.
        seen = collections.Counter(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", haystack))
        located = {unit.key: _where(unit) for unit in units()}
        dead = sorted(key for key, name in defined.items() if seen[name] <= 1)
        self.assertEqual(dead, [], _explain(
            "written nowhere but", None,
            [(key, "its own def", located[key]) for key in dead],
            "Delete it, or add it to DYNAMIC with the dispatcher that reaches it."))

    def test_the_shared_name_blind_spot_only_shrinks(self):
        """How much of the corpus the dead-code check cannot speak for.

        Its predicate is a text count over a bare name, so a function whose
        name another function also carries is outside its reach. That is a real
        limit, and an unstated limit is worse than a small one -- so it is
        measured here and held to a ceiling that may only come down, the same
        rule the baselines follow. Giving a function a name nothing else in
        `bin/` and `dashboard/` uses is what shrinks it.
        """

        blind = sorted(
            unit.key for unit in units()
            if not unit.name.startswith("_") and unit.name in _ambiguous()
        )
        self.assertLessEqual(len(blind), AMBIGUOUS_CEILING, _explain(
            "unreachable by the dead-code check, against a ceiling of",
            AMBIGUOUS_CEILING,
            [(key, "shares its name", key.split("::")[0]) for key in blind],
            "Lower AMBIGUOUS_CEILING to the new count in the same change."))

    def test_every_baseline_entry_still_earns_its_place(self):
        """The baselines may only shrink.

        This is the inversion of the cap's ratchet. `BIN_CAP` could only rise,
        so every raise was legal and the number tracked the code. These lists
        can only fall: fix a function and the test fails until its entry is
        deleted, which makes removal the cheap path and addition the argued
        one.
        """

        found = {unit.key: unit for unit in units()}
        stale = []
        for baseline, label, exceeds in (
            (COMPLEX, "complexity", lambda unit: unit.score > COMPLEXITY_CEILING),
            (LONG, "length", lambda unit: unit.span > LENGTH_CEILING),
            (DEEP, "depth", lambda unit: unit.nest > DEPTH_CEILING),
        ):
            for key in sorted(baseline):
                unit = found.get(key)
                if unit is None:
                    stale.append(f"{key} no longer exists; drop it from {label}")
                elif not exceeds(unit):
                    stale.append(f"{key} is now under the {label} ceiling")
        for left, right in sorted(CLONES):
            one, other = found.get(left), found.get(right)
            if one is None or other is None:
                stale.append(f"{left} or {right} no longer exists; drop the pair")
            elif min(one.nodes, other.nodes) < CLONE_FLOOR:
                # The clone test stops generating this pair below the floor, so
                # without this the entry would outlive the duplication forever.
                stale.append(f"{left} and {right} are too small to count now")
            elif one.digest != other.digest:
                stale.append(f"{left} and {right} are no longer the same function")
        for key in sorted(DYNAMIC):
            if key not in found:
                stale.append(f"{key} no longer exists; drop it from DYNAMIC")
        self.assertEqual(stale, [], "\n".join(
            ["Fixed debt is still listed as debt. Delete these entries:", *stale]))


@functools.cache
def _ambiguous() -> frozenset[str]:
    """Public names carried by more than one function in the corpus."""

    seen = collections.Counter(
        unit.name for unit in units() if not unit.name.startswith("_"))
    return frozenset(name for name, count in seen.items() if count > 1)


def _where(unit: Unit) -> str:
    """`path:line`, so the reader can open the function the failure names."""

    return f"{unit.path}:{unit.line}"


def _explain(verb, ceiling, over, remedy: str) -> str:
    """The failure message, which has to say what to do, not just what is wrong.

    The first column of each row is the baseline key verbatim, so accepting a
    violation is a copy rather than a reconstruction. The last is `path:line`.
    """

    limit = f" the ceiling of {ceiling}" if ceiling is not None else ""
    listing = "\n".join(
        f"  {item[0]}: {item[1]}  ({item[2]})" for item in over)
    return (
        f"{len(over)} function(s) became {verb}{limit}:\n{listing}\n"
        f"{remedy} This is not a cap to raise: the ceiling has held across "
        f"every feature added so far, so a new violation is a shape problem "
        f"in the new code, not a budget that ran out. If the shape is genuinely "
        f"right, add the entry to the baseline in the same change, with the "
        f"reason in the commit message."
    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
