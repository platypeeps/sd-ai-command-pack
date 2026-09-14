"""
Start coverage in installer subprocesses when the test runner requests it.

Python imports this special ``sitecustomize`` module automatically when this
directory is on ``sys.path``. The test harness adds it to ``PYTHONPATH`` for
subprocesses so coverage can collect data from installed scripts.

Coverage starts only in a process that runs a file the ``[run] include``
patterns name, and it starts before that file's first line does. Until this
was lazy every Python child of the suite -- each ``git`` and ``gh`` shim a test
puts on ``PATH``, each ``sd-review`` a ``prepare`` launches -- imported
coverage, installed a tracer and wrote a data file at exit, although the
include list is the installer and nothing those children run. Measured on one
``tests/test_sd_ship.py`` case: 12.8s with the eager start, 6.5s with no
subprocess coverage at all, and the bare import alone is 40ms a launch.

"A file the patterns name" is decided generously, so the lazy start can only
start coverage more often than coverage itself would record anything, never
less often: a pattern matches any path that ends in it, where coverage anchors
a relative pattern at the working directory. Two ways in are watched:

- the script named on the command line (``python .github/scripts/x.py``),
  checked here at startup;
- every code object handed to ``exec`` -- which is how an import, ``runpy``,
  ``python -m`` and a ``SourceFileLoader`` run a module body -- seen through
  the ``exec`` audit event, which fires before the module's frame exists, so
  the tracer is in place for its first line.

A process that is already measured -- the ``coverage run`` shard itself -- is
left alone, as ``coverage.process_startup`` would leave it. A configuration
this cannot read, or one that measures by ``source`` rather than ``include``,
falls back to starting coverage at once, which is what this file always did.
The installer gate at 100% is what proves nothing was lost: a line that ran
unmeasured fails it.
"""
import os
import sys

#: What `run-tests.sh` exports: the config file, for a start that waits.
LAZY = "SD_COVERAGE_PROCESS_START"
#: coverage.py's own variable. Its `.pth` file (7.7 and later) starts coverage
#: in every interpreter that sees it, before this module is imported, which is
#: why the harness does not export it.
STANDARD = "COVERAGE_PROCESS_START"

COVERAGE_UNAVAILABLE_MESSAGE = (
    "sitecustomize: coverage.py not found or is too old, subprocess coverage will not be collected."
)


def _start(config_file=None):
    try:
        import coverage
    except ImportError:
        print(COVERAGE_UNAVAILABLE_MESSAGE, file=sys.stderr)
        return
    process_startup = getattr(coverage, "process_startup", None)
    if not callable(process_startup):
        print(COVERAGE_UNAVAILABLE_MESSAGE, file=sys.stderr)
        return
    current = getattr(getattr(coverage, "Coverage", None), "current", None)
    if callable(current) and current() is not None:
        return
    if config_file is None:
        process_startup()
        return
    # `process_startup` reads the standard variable. It is set for that call
    # only: left in the environment, every child of this process would start
    # coverage eagerly through coverage's own `.pth` file.
    os.environ[STANDARD] = config_file
    try:
        process_startup()
    finally:
        del os.environ[STANDARD]


def _include_patterns(config_file):
    """The `[run] include` globs, or None when only an eager start is safe."""
    import configparser

    parser = configparser.RawConfigParser()
    try:
        if not parser.read(config_file):
            return None
    except (configparser.Error, OSError, UnicodeError):
        return None
    if not parser.has_section("run"):
        return None
    for eager in ("source", "source_pkgs", "source_dirs", "plugins", "patch"):
        if parser.has_option("run", eager):
            return None
    if not parser.has_option("run", "include"):
        return None
    patterns = [line.strip() for line in parser.get("run", "include").replace(",", "\n").splitlines()]
    patterns = [pattern for pattern in patterns if pattern]
    if not patterns:
        return None
    # A relative pattern matches any path that ends in it; see the docstring.
    # A pattern is kept as written too, so one that already starts with a
    # wildcard matches at least what coverage matches.
    return [form for pattern in patterns
            for form in ((pattern,) if pattern.startswith("/") else (pattern, "*/" + pattern))]


def _install():
    if os.environ.get(STANDARD) is not None or os.environ.get("COVERAGE_PROCESS_CONFIG") is not None:
        # Asked for the eager start: coverage's `.pth` has usually done it
        # already, and `process_startup` returns at once when it has.
        _start()
        return
    config_file = os.environ.get(LAZY)
    if not config_file:
        return
    import importlib.util

    if importlib.util.find_spec("coverage") is None:
        print(COVERAGE_UNAVAILABLE_MESSAGE, file=sys.stderr)
        return
    patterns = _include_patterns(config_file)
    if patterns is None:
        _start(config_file)
        return
    from fnmatch import fnmatchcase

    def measured(filename):
        if not isinstance(filename, str) or filename.startswith("<"):
            return False
        # A loader handed a relative path compiles it under that name.
        filename = os.path.abspath(filename)
        return any(fnmatchcase(filename, pattern) for pattern in patterns)

    for argument in getattr(sys, "orig_argv", sys.argv)[1:]:
        if measured(argument):
            _start(config_file)
            return

    state = {"done": False}

    def hook(event, arguments):
        if state["done"] or event != "exec":
            return
        code = arguments[0] if arguments else None
        if measured(getattr(code, "co_filename", None)):
            # Set first: starting coverage imports it, and those imports are
            # `exec` events of their own.
            state["done"] = True
            _start(config_file)

    sys.addaudithook(hook)


_install()
