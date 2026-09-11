"""What `bin/` and `dashboard/` may not become, measured instead of asserted.

This replaces one check, not one file: `BIN_CAP` in `tests/test_loc_caps.py`,
which capped total lines under `bin/`. That file survives and still enforces
the `migrate-*` and dashboard ceilings; only the `bin/` total is retired here.

That cap was raised eighteen times in eleven days and lowered never, while
`bin/` grew from 8,000 lines to the 20,803 it was retired at -- so it never
once said no. It could not: every capability adds lines, and refusing the lines
means refusing the capability. A number that must be raised to let work proceed
is a record of growth wearing the costume of a limit.

Worse, it charged for prose. `bin/` measures 20,832 lines today -- already 29
past the figure it was retired at, from work that landed in the days between,
and nothing counts them now. Of those, 13,144 carry code and 7,688 are
docstring, comment or blank. House style puts
design reasoning in docstrings, so under a line cap explaining costs exactly
what implementing costs, and the one time the cap actually bound, what got
deleted was an explanation (`dashboard/` at 3,999 of 4,000, prose trimmed to
pay for code).

The checks here were chosen for one property: **they do not move when a feature
is added**. Adding a command adds functions; it does not make existing
functions branchier, or deeper, or duplicated. A ceiling on those can hold for
years without a raise, which is what separates a limit from a ledger. The
evidence that the distinction is real is in the shape of the growth itself --
between 2026-09-01 and 2026-09-11 `bin/` went 7,947 to 20,832 lines, but
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
import copy
import functools
import hashlib
import io
import itertools
import pathlib
import re
import subprocess
import tempfile
import textwrap
import tokenize
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

#: How much of a suffix-less entry point is read to find its shebang. A cap
#: so a binary is not read to its end; reaching it without a newline means the
#: line was not seen, which `_is_python_script` treats as "maybe", not "no".
SHEBANG_LIMIT = 4096

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
        if not _is_migration_tool(path)
    )


def _has_docstring(node: ast.AST) -> bool:
    """Whether `node.body[0]` is the docstring, by the rule Python itself uses."""

    body = getattr(node, "body", None)
    if not body:
        return False
    first = body[0]
    return (isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str))


def _is_migration_tool(path: pathlib.Path) -> bool:
    """`bin/migrate-*`, and only there, because that is what still has a cap.

    The exception is inherited from `MIGRATE_CAP`, which governs `bin/migrate-*`
    alone (`tests/test_loc_caps.py`). Keyed on the basename instead, it would
    also drop a future `dashboard/migrate-*.py` -- and drop it from `sources()`
    and from `expected` at once, so the corpus test would compare two sets that
    agree about a file neither of them holds. That is the fail-open shape this
    module exists to avoid, so the directory is part of the predicate.
    """

    return path.parent.name == "bin" and path.name.startswith("migrate-")


def _is_python_script(path: pathlib.Path) -> bool:
    """A `bin/` entry point has no suffix, so the shebang is what names it.

    The whole first line, not a fixed window: `#!/usr/bin/env -S python3 -X
    importtime` pushes the word past any short prefix, and a script that falls
    out of the corpus that way is ungoverned in silence. A line cap still
    applies so a binary cannot be read to its end.
    """

    try:
        with path.open("rb") as handle:
            first = handle.readline(SHEBANG_LIMIT)
    except OSError:
        # Included, not dropped. `sources()` and the corpus test ask this same
        # question, so answering "not Python" for a file nobody could open
        # removes it from both sides at once and the sets still match -- the
        # file vanishes and the fail-closed contract reports nothing. Saying
        # yes sends it to the parse, which records it in `BROKEN`.
        return True
    if first[:2] != b"#!":
        return False
    if b"python" in first:
        return True
    # The cap was reached with no newline, so this is a prefix and not the
    # line. "No python in the part I read" is not "not a Python script", and
    # answering no here would drop the file from `sources()` and `expected`
    # together -- the same silent vanishing `_is_migration_tool` guards
    # against. Hand it to the parse instead and let `BROKEN` speak.
    return len(first) == SHEBANG_LIMIT and not first.endswith(b"\n")


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
    for node in [*ast.walk(args), *_outside_nested_scopes(body)]:
        if isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.alias) and node.asname:
            names.add(node.asname)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            names.add(node.rest)
    return frozenset(names)


def _outside_nested_scopes(body: list[ast.stmt]) -> list[ast.AST]:
    """Every node in `body`, minus everything a nested scope binds.

    A nested scope's parameters are bound *inside it*, not in the function
    holding it. Collected into one flat set they leak: a body containing
    `lambda json: ...` marks `json` bound, and `Alpha` then renames the
    function's own free `json.dumps` too -- so two functions differing only in
    which module they call normalize to one digest and get reported as copies.
    That is a false positive, and this check's whole claim is that the copy
    fails while the original does not.

    Every binding scope, not just `lambda`. An earlier fix stopped at lambdas
    on the reasoning that `_strip_nested` had already blanked nested `def`
    bodies -- but it blanks the *body* and leaves the signature, so
    `def inner(json): ...` leaked `json` by exactly the route the lambda did.
    `Detectors` covers both spellings now, because fixing one vehicle for a
    bug and not the other is how this one survived a review round.

    The cost is a false negative in the other direction: a copy that renamed
    only a nested parameter no longer matches its original. Between the two,
    missing a copy is the safe failure and naming an innocent function a copy
    is not.
    """

    found: list[ast.AST] = []
    stack: list[ast.AST] = list(body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.Lambda,) + SCOPES):
            # The header still executes out here, and `_own` charges its
            # complexity to this function -- but a default or an annotation
            # binds nothing in this scope, so nothing in it belongs in the
            # bound set.
            continue
        found.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return found


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
        self.generic_visit(node)
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        return ast.copy_location(ast.Constant(value="K"), node)

    # Four bindings Python stores as plain strings rather than as `Name`
    # nodes. `_bound` collects them, so without these the name is renamed
    # everywhere it is *used* and left alone where it is *bound* -- one
    # function ends up with `except X as e: return v1`, and a copy that
    # renamed `e` still fails to match. Each is the binding half of a name
    # `_rename` already knows.

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ast.ExceptHandler:
        if node.name:
            node.name = self._rename(node.name)
        self.generic_visit(node)
        return node

    def visit_alias(self, node: ast.alias) -> ast.alias:
        if node.asname:
            node.asname = self._rename(node.asname)
        return node

    def visit_MatchAs(self, node: ast.MatchAs) -> ast.MatchAs:
        if node.name:
            node.name = self._rename(node.name)
        self.generic_visit(node)
        return node

    def visit_MatchStar(self, node: ast.MatchStar) -> ast.MatchStar:
        if node.name:
            node.name = self._rename(node.name)
        return node

    def visit_MatchMapping(self, node: ast.MatchMapping) -> ast.MatchMapping:
        if node.rest:
            node.rest = self._rename(node.rest)
        self.generic_visit(node)
        return node


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


def _strip_nested(body: list[ast.stmt]) -> list[ast.stmt]:
    """`body` with every nested scope's own body replaced by `pass`.

    `_own` stops at a nested scope because `_walk` measures it separately, and
    length and the clone digest have to agree with that or the file says two
    things. Rendering the whole body charged `make_handler` for the 105 lines
    of the `Handler` it builds, while `Handler.do_POST` was measured again at
    42 -- so adding a method to the nested class grew the outer function's
    score, and lifting code into a local helper could never shrink it.

    The `def` line and its decorators stay: those belong to this function.
    """

    owned = copy.deepcopy(body)
    for statement in owned:
        for node in ast.walk(statement):
            if isinstance(node, SCOPES):
                node.body = [ast.Pass()]
    return owned


def _header(node: ast.AST) -> list[ast.AST]:
    """The parts of a nested `def` or `class` the enclosing scope evaluates.

    Decorators, the argument list with its defaults and annotations, a return
    annotation, and a class's bases and keywords. Not the body, and not the
    name: those belong to the nested scope, which is measured separately.
    """

    parts: list[ast.AST] = list(node.decorator_list)
    if isinstance(node, ast.ClassDef):
        parts.extend(node.bases)
        parts.extend(node.keywords)
        return parts
    parts.extend(ast.iter_child_nodes(node.args))
    if node.returns is not None:
        parts.append(node.returns)
    return parts


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

    "Header" is every field evaluated at the `def` or `class` statement, which
    is more than the argument list: a return annotation and a class's bases and
    keywords run there too. Listing only decorators and `args` left
    `def inner() -> factory(flag)` and `class C(factory(flag))` uncharged to
    anybody, since a nested class gets no `Unit` of its own -- so a branch could
    be moved into a nested header to duck this ceiling.
    """

    # The body, not every child. A function's own decorators, defaults and
    # annotations run where the `def` sits -- in its *enclosing* scope, which
    # charges them through `_header` when it walks past this definition.
    # Starting from all children charged them here as well, so one `if` in a
    # nested default scored on both functions and the wrong one could be the
    # one pushed over the ceiling.
    stack: list[ast.AST] = list(getattr(function, "body", []))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, SCOPES):
            stack.extend(_header(node))
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


# Every statement that opens an indented block, because the measure is the
# indentation a reader has to hold, not the kind of statement that caused it.
# `match` and `except*` were missing here until 2026-09-11: both indent, so a
# real sixth level could sit inside a `case` or an `except*` arm and read as
# five. `match` is the load-bearing one -- `complexity` already charges for
# each `case`, so leaving it out of the depth measure made the two disagree
# about the same statement.
NESTS = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.TryStar,
         ast.AsyncFor, ast.AsyncWith, ast.Match)


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
        except (SyntaxError, OSError, UnicodeDecodeError) as failure:
            # Never `continue` without recording. Skipping the file would drop
            # every function in it from every ceiling at once, and the suite
            # would go green on a smaller corpus without saying so.
            #
            # `UnicodeDecodeError` is named because it is a `ValueError`, not
            # an `OSError` -- a tracked file with a non-UTF-8 encoding would
            # otherwise raise straight out of the walk, which fails the run but
            # as a traceback rather than as the one sentence this promises.
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
        # The docstring is the *first* statement and nothing else. Dropping
        # every bare string in the body instead let a function pad itself
        # under the length ceiling with literals -- and shrank its clone
        # digest by the same statements, so two functions could be made to
        # match by adding prose to one of them.
        body = node.body[1:] if _has_docstring(node) else list(node.body)
        found.extend(_walk(node, relative, prefix + (node.name,)))
        # A function whose only statement is a docstring still gets a unit.
        # Skipping it let `Handler.log_message` out of every check at once --
        # dead-code, duplicate and baseline alike -- and the corpus test could
        # not see the hole, because it proves the file was parsed, not that
        # every function in it was measured.
        owned = _strip_nested(body)
        nodes = sum(1 for statement in owned for _ in ast.walk(statement))
        # One `Alpha` for the whole body, never one per statement. Renaming
        # each statement in isolation restarts the counter, so `foo(x); bar(y)`
        # and `foo(x); bar(x)` both normalize to `v1(v2); v1(v2)` and two
        # unrelated functions collide. Numbering across the body is what makes
        # the digest mean "same shape, same data flow".
        rendered = ast.unparse(ast.Module(body=owned, type_ignores=[]))
        normalized = ast.dump(
            Alpha(_bound(node.args, owned)).visit(ast.parse(rendered)))
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
    "bin/sd_writing.py::run",  # 83
    "dashboard/plugins.py::bounded_run",  # 67
})

DEEP: frozenset[str] = frozenset()

#: Names the dead-code check must not flag, because something other than a
#: call site reaches them. `html.parser.HTMLParser` dispatches to its
#: `handle_*` methods by name from inside the base class, so no caller appears
#: anywhere. This is the whole exemption list; it is not a place to put a
#: function nobody could find a caller for.
DYNAMIC = frozenset({
    "dashboard/markup.py::Filter.handle_comment",
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

    @classmethod
    def setUpClass(cls):
        """Refuse to measure at all if the corpus could not be read.

        `test_the_corpus_is_complete` states the full comparison, but it
        cannot be the thing that runs first: `unittest` sorts methods
        alphabetically, so `test_every_baseline_entry_still_earns_its_place`
        and every `test_no_*` check run ahead of anything named `test_the_*`.
        A file that would not parse therefore produced a partial `units()`,
        and the ceilings reported their own confusing failures against it
        before the check that could name the unreadable path ever ran.

        Ordering by renaming the method would work until somebody renamed it
        back. This runs before every method in the class by construction.
        """

        units()
        if BROKEN:
            raise unittest.SkipTest(
                "the corpus could not be read, so no ceiling below means "
                f"anything: {BROKEN}")

    def test_the_corpus_is_complete(self):
        """The measurement must fail loudly rather than pass on a smaller corpus.

        A check whose enumeration quietly matches less than it should reports
        success forever, and that is the one failure mode a ceiling cannot
        survive. `setUpClass` above holds the ordering-safe half of this.

        The comparison is against a fresh `git ls-files`, not against a
        remembered count. A floor like "more than twenty files" would let the
        corpus lose half its contents and still pass, which is the same
        mistake as trusting a number somebody wrote down.
        """

        found = units()
        self.assertEqual(BROKEN, [], "files the walk could not read or parse")
        # Through `_is_migration_tool`, never a second spelling of it. This
        # line read `path.name.startswith("migrate-")` until 2026-09-11, while
        # `sources()` had already been narrowed to `bin/` -- so a future
        # `dashboard/migrate-*.py` would be in the corpus and absent from the
        # set the corpus is checked against, and this test would fail for a
        # file that belongs. One predicate, one place.
        expected = {
            path for path in tracked("bin", "dashboard")
            if not _is_migration_tool(path)
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
        Only letting one grow past the ceiling above does. The number is not
        repeated here, because a second copy of it is the drift this module
        exists to argue against.
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
        # Whole identifiers, not substrings. Counting substrings made 77 names
        # permanently unreportable because a longer name contained them --
        # `add` inside `add_row`, `check` inside `check_url` -- so the check
        # could never fire on them at all. `.github` and `.claude` are in the
        # pathspec because a function reached only from a workflow or a hook
        # is referenced, not dead.
        seen = _references()
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
        # Exactly, not at most. The docstring calls this downward-only, and
        # `assertLessEqual` did not enforce that half: a cleanup that renamed
        # a duplicate could shrink the population while the constant stayed at
        # its old value forever, which is the stale-record shape
        # `test_every_baseline_entry_still_earns_its_place` exists to stop for
        # the other baselines. Equality makes the record move with the thing
        # it records, in the same change.
        self.assertEqual(len(blind), AMBIGUOUS_CEILING, _explain(
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
def _references() -> collections.Counter:
    """How often each identifier is written across the repository.

    Python files are tokenised and their strings and comments dropped, so a
    function's own docstring is not evidence that something reaches it: an
    orphan whose docstring opens with its own name counted twice and passed.
    Prose files are counted whole, because naming a tool in a skill doc *is* a
    reference to it.
    A file that will not tokenise falls back to the plain scan rather than
    contributing nothing.

    This module is excluded from both. Listing a name in `DYNAMIC` would
    otherwise be a second occurrence of it, so the act of exempting a function
    would also be the evidence that it needed no exemption -- and deleting the
    entry would not bring the failure back.
    """

    me = pathlib.Path(__file__).resolve()
    words = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    seen: collections.Counter = collections.Counter()
    for path in tracked("bin", "dashboard", "tests", "skills", "docs",
                        ".github", ".claude", "*.md"):
        if path == me:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # The corpus walk already records an unreadable tracked file in
            # BROKEN, and `test_the_corpus_is_complete` names it with its
            # path. Raising here instead would lose that diagnostic: this
            # test sorts first, so a bare OSError would abort the run before
            # the check that explains what is wrong ever gets to speak.
            continue
        if path.suffix != ".py" and not _is_python_script(path):
            seen.update(words.findall(text))
            continue
        try:
            seen.update(
                token.string for token in tokenize.generate_tokens(
                    io.StringIO(text).readline)
                if token.type == tokenize.NAME)
        except (tokenize.TokenError, SyntaxError, IndentationError):
            seen.update(words.findall(text))
    return seen


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


def measure(source: str) -> dict[str, Unit]:
    """Every function in `source`, measured by the production walk.

    Through `_walk` rather than beside it. A fixture that re-derived span or
    digest would be a second copy of the pipeline, and the first thing a second
    copy does is stop agreeing with the first -- which is the failure this
    module exists to argue against, so it is not one to commit here.
    """

    return {
        unit.key.split("::", 1)[1]: unit
        for unit in _walk(ast.parse(textwrap.dedent(source)), "<fixture>", ())
    }


class Detectors(unittest.TestCase):
    """That each measure answers the question it claims, on known inputs.

    Every test above this point runs the detectors over the corpus as it
    stands, and the corpus passes. That proves nothing about the detectors: a
    measure that returned zero for everything would pass all eight, because
    zero is under every ceiling. These are the cases that separate a working
    check from a check that cannot fail -- each one a shape that slipped
    through a real review round of this file.
    """

    def test_an_elif_chain_is_one_level_and_a_nested_if_is_not(self):
        # Python builds `elif` as an `If` in the previous one's `orelse`, so a
        # flat dispatch reads to a naive walker as one level per arm.
        chain = measure("""
            def f(x):
                if x == 1:
                    return 'a'
                elif x == 2:
                    return 'b'
                elif x == 3:
                    return 'c'
            """)["f"]
        nested = measure("""
            def f(x):
                if x == 1:
                    return 'a'
                else:
                    if x == 2:
                        return 'b'
                    else:
                        if x == 3:
                            return 'c'
            """)["f"]
        self.assertEqual(chain.nest, 1, "an elif chain is one indented block")
        self.assertEqual(nested.nest, 3, "else-nested ifs are three")
        # Both are three decisions, though. Depth and complexity disagree about
        # this pair on purpose: one measures indentation, the other branches.
        self.assertEqual(chain.score, nested.score)

    def test_match_and_except_star_are_counted_as_indentation(self):
        for label, source in (
            ("match", """
                def f(x):
                    match x:
                        case 1:
                            if x:
                                return 1
                """),
            ("except*", """
                def f(x):
                    try:
                        return 1
                    except* OSError:
                        if x:
                            return 2
                """),
        ):
            with self.subTest(block=label):
                self.assertEqual(measure(source)["f"].nest, 2, label)

    def test_a_lambda_parameter_does_not_bind_an_outer_free_name(self):
        # Each function shadows the very module it calls, and they call
        # different ones. If a lambda's parameter enters the enclosing bound
        # set, `Alpha` renames `json` in the first and `yaml` in the second to
        # the same slot, the two collapse to one digest, and two unrelated
        # functions are reported as copies of each other.
        #
        # Shadowing matters: with `lambda json:` in both and the call sites
        # differing, the digests differ whether or not the bug is present, so
        # that pairing cannot tell the two implementations apart.
        first = measure("""
            def f(rows):
                pick = lambda json: json
                return json.dumps(rows)
            """)["f"]
        second = measure("""
            def f(rows):
                pick = lambda yaml: yaml
                return yaml.dumps(rows)
            """)["f"]
        self.assertNotEqual(first.digest, second.digest)

    def test_a_nested_def_parameter_does_not_bind_an_outer_free_name(self):
        # The same leak as the lambda case, through a different door. The
        # first fix stopped at `lambda` because `_strip_nested` had already
        # blanked nested `def` bodies -- but it blanks the body and leaves the
        # signature, so the parameter was still there to be collected. Both
        # spellings are covered now, and neither may be dropped without this
        # going red.
        first = measure("""
            def f(rows):
                def inner(json):
                    return json
                return json.dumps(rows)
            """)["f"]
        second = measure("""
            def f(rows):
                def inner(yaml):
                    return yaml
                return yaml.dumps(rows)
            """)["f"]
        self.assertNotEqual(first.digest, second.digest)

    def test_a_nested_default_is_charged_once(self):
        # It executes once, where the `def` sits. `_own` starting from every
        # child of the function charged it to the nested function as well, so
        # a branchy default scored on two units and either one could be the
        # one pushed over the ceiling.
        units_by_name = measure("""
            def f(flag):
                def inner(x=(1 if flag else 2)):
                    return x
                return inner
            """)
        self.assertEqual(units_by_name["f"].score, 2, "the enclosing scope")
        self.assertEqual(units_by_name["f.inner"].score, 1, "not the nested one")

    def test_a_renamed_local_is_still_the_same_function(self):
        # The whole point of the digest: a copy-paste that renamed its locals
        # has to stay visible. Each pair below binds through a different AST
        # field, and each field was missed at some point.
        pairs = {
            "parameter": ("def f(alpha):\n    return alpha + 1\n",
                          "def f(beta):\n    return beta + 1\n"),
            "except-as": ("def f(p):\n    try:\n        return open(p)\n"
                          "    except OSError as first:\n        return first\n",
                          "def f(p):\n    try:\n        return open(p)\n"
                          "    except OSError as second:\n        return second\n"),
            "import-as": ("def f():\n    import json as codec\n"
                          "    return codec.dumps({})\n",
                          "def f():\n    import json as writer\n"
                          "    return writer.dumps({})\n"),
            "match-as": ("def f(x):\n    match x:\n        case [1, *rest]:\n"
                         "            return rest\n",
                         "def f(x):\n    match x:\n        case [1, *tail]:\n"
                         "            return tail\n"),
        }
        for field, (left, right) in pairs.items():
            with self.subTest(binding=field):
                self.assertEqual(measure(left)["f"].digest,
                                 measure(right)["f"].digest)

    def test_a_different_free_name_is_a_different_function(self):
        # The other half of the same rule. A digest that ignored free names
        # would call every two-line wrapper in the repository a clone.
        self.assertNotEqual(
            measure("def f(x):\n    return alpha(x)\n")["f"].digest,
            measure("def f(x):\n    return beta(x)\n")["f"].digest)

    def test_only_the_first_statement_is_a_docstring(self):
        # Bare literals after the docstring are statements. Dropping them all
        # let a function pad itself under the length ceiling with prose.
        padded = measure("""
            def f(x):
                \"\"\"doc\"\"\"
                y = x + 1
                'pad'
                'pad'
                'pad'
                return y
            """)["f"]
        self.assertEqual(padded.span, 5)

    def test_a_nested_header_is_charged_to_the_enclosing_function(self):
        # A nested `def` runs its decorators, defaults, annotations and a
        # class's bases where the `def` sits -- so a branch moved there is the
        # outer function's, and must not become nobody's.
        for label, source in (
            ("return annotation", """
                def f(flag):
                    def inner() -> (int if flag else str):
                        return 1
                    return inner
                """),
            ("class base", """
                def f(flag):
                    class C(Alpha if flag else Beta):
                        pass
                    return C
                """),
            ("default argument", """
                def f(flag):
                    def inner(x=(1 if flag else 2)):
                        return x
                    return inner
                """),
        ):
            with self.subTest(header=label):
                self.assertEqual(measure(source)["f"].score, 2, label)

    def test_a_nested_body_is_not_charged_to_the_enclosing_function(self):
        # The complement. Otherwise simplifying a factory cannot clear a score
        # that belongs to the function it returns.
        outer = measure("""
            def f(rows):
                def inner(x):
                    if x:
                        if x > 1:
                            return 1
                    return 0
                return inner
            """)
        self.assertEqual(outer["f"].score, 1)
        self.assertEqual(outer["f"].nest, 0)
        self.assertEqual(outer["f.inner"].score, 3)

    def test_the_migration_exception_is_scoped_to_bin(self):
        self.assertTrue(_is_migration_tool(REPO_ROOT / "bin/migrate-rows"))
        self.assertFalse(
            _is_migration_tool(REPO_ROOT / "dashboard/migrate-store.py"))
        self.assertFalse(_is_migration_tool(REPO_ROOT / "bin/sd_lib.py"))

    def test_an_overlong_shebang_stays_in_the_corpus(self):
        # Fail closed. A file whose first line outran the read window used to
        # be classified "not Python" and leave every check in silence.
        with tempfile.TemporaryDirectory() as home:
            probe = pathlib.Path(home) / "entrypoint"
            probe.write_bytes(
                b"#!/usr/bin/env -S " + b"x" * SHEBANG_LIMIT + b" python3\n")
            self.assertTrue(_is_python_script(probe))
            plain = pathlib.Path(home) / "notes"
            plain.write_bytes(b"just text\n")
            self.assertFalse(_is_python_script(plain))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
