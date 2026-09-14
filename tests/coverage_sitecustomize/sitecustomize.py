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

"A file the patterns name" is decided generously: a pattern matches any path
that ends in it, where coverage anchors a relative pattern at the working
directory, and a file matches through its absolute path as written and through
its real path, where coverage looks only at the real path. So among children
this module is loaded into, coverage starts in every one where it would record
anything, and in some where it records nothing. One trigger is watched: every
code object handed to ``exec`` -- which is how a script named on the command
line, an import, ``runpy``, ``python -m`` and a ``SourceFileLoader`` run a
module body -- seen through the ``exec`` audit event, which fires before the
module's frame exists, so the tracer is in place for its first line. A symlink
to a measured file, or a directory symlink on its path, still matches.

When that first measured body runs on a thread other than the only one, the
start also reaches the threads that already exist, as the eager start did by
running before any of them: coverage's per-thread installer is set on every
thread with ``sys._settraceallthreads`` (what ``threading.settrace_all_threads``
calls), and each thread builds its own tracer at its next call.

What is not measured -- children this module is never loaded into:

- ``python -I``, ``-E`` or ``-S``: the first two ignore ``PYTHONPATH``, the
  third skips ``site`` and with it every ``sitecustomize``;
- a child whose environment drops this directory from ``PYTHONPATH`` or drops
  ``SD_COVERAGE_PROCESS_START``.

The eager start measured the ``-I`` and ``-E`` cases through coverage's own
``.pth`` file, and a child without ``PYTHONPATH`` that kept
``COVERAGE_PROCESS_START``. So a process under the lazy start refuses to launch
a gate-measured file under ``-I``, ``-E`` or ``-S``: it watches the
``subprocess.Popen``, ``os.exec`` and ``os.posix_spawn`` audit events and
raises, which fails the test that did it. "Gate-measured" is anchored where the
gate combines, at the directory holding the coverage config, so a copy of the
installer in a temporary tree is not refused. The watch sees argument lists,
a shell command line and a measured file's own ``#!`` line; it does not see a
launch from a non-Python parent, nor ``-m`` naming a measured module.

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

#: Interpreter flags that keep this module from loading in the child.
UNMEASURED_FLAGS = frozenset("IES")
#: Audit events naming a process about to be launched, and where its argv sits.
LAUNCH_EVENTS = {"subprocess.Popen": 1, "os.exec": 1, "os.posix_spawn": 1}


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
    _trace_existing_threads(coverage)


def _trace_existing_threads(coverage):
    """Reach the threads that were running before this start.

    `Collector.start` traces the calling thread and, through
    `threading.settrace`, threads started later. Started at interpreter start,
    as coverage's `.pth` does, that is every thread; started from a worker
    thread it misses the main thread and every other live one. Anything this
    cannot find leaves those threads untraced, which lowers the gate rather
    than passing it.
    """
    if len(sys._current_frames()) < 2:
        return
    collector = getattr(coverage.Coverage.current(), "_collector", None)
    install = getattr(collector, "_installation_trace", None)
    set_all = getattr(sys, "_settraceallthreads", None)
    if not (getattr(getattr(collector, "core", None), "systrace", False)
            and callable(install) and callable(set_all)):
        # sys.monitoring cores trace every thread already.
        return
    # This thread included: its tracer is replaced by a fresh one at its next
    # call, which is the module body about to run. No measured frame is on its
    # stack yet, because this start is the first measured `exec`.
    set_all(install)


def _include_patterns(config_file):
    """The `[run] include` globs as written, or None when only an eager start is safe."""
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
    return patterns or None


def _loose(patterns):
    # A relative pattern matches any path that ends in it; see the docstring.
    # A pattern is kept as written too, so one that already starts with a
    # wildcard matches at least what coverage matches.
    return [form for pattern in patterns
            for form in ((pattern,) if pattern.startswith("/") else (pattern, "*/" + pattern))]


def _anchored(patterns, root):
    # Where the gate reads: a relative pattern at the config's directory.
    return [pattern if pattern.startswith(("/", "*", "?")) else os.path.join(root, pattern)
            for pattern in patterns]


def _matches(filename, patterns, fnmatchcase, cwd=None):
    # `fnmatchcase` is passed in, imported before the hook exists: an import
    # from inside the hook is an `exec` event that re-enters it.
    if isinstance(filename, os.PathLike):
        filename = os.fspath(filename)
    if isinstance(filename, bytes):
        filename = os.fsdecode(filename)
    if not isinstance(filename, str) or not filename or filename.startswith("<"):
        return False
    if cwd is not None:
        filename = os.path.join(os.fsdecode(os.fspath(cwd)), filename)
    # A loader handed a relative path compiles it under that name; a launcher
    # can be a symlink to the file, or reach it through a symlinked directory.
    candidates = {os.path.abspath(filename), os.path.realpath(filename)}
    return any(fnmatchcase(candidate, pattern) for candidate in candidates for pattern in patterns)


def _unmeasured_script(tokens, measured, cwd):
    """The measured script an interpreter command line runs with site skipped, if any."""
    for index, token in enumerate(tokens):
        if not os.path.basename(token).startswith("python"):
            continue
        position = index + 1
        skipped = False
        while position < len(tokens):
            option = tokens[position]
            if option == "--":
                position += 1
                break
            if option.startswith("--"):
                position += 1
                continue
            if option == "-" or not option.startswith("-"):
                break
            letters = option[1:]
            for offset, letter in enumerate(letters):
                skipped = skipped or letter in UNMEASURED_FLAGS
                if letter in "cm":
                    # Code or a module name follows, not a file.
                    return None
                if letter in "WX":
                    position += offset == len(letters) - 1
                    break
            position += 1
        if skipped and position < len(tokens) and measured(tokens[position], cwd):
            return tokens[position]
    return None


def _shebang(path, cwd):
    try:
        with open(os.path.join(cwd or "", path), "rb") as handle:
            line = handle.readline(512)
    except (OSError, ValueError):
        return []
    if not line.startswith(b"#!"):
        return []
    import shlex

    try:
        return shlex.split(os.fsdecode(line[2:]).strip())
    except ValueError:
        return []


def _refuse_unmeasured_launch(event, arguments, measured):
    if len(arguments) <= LAUNCH_EVENTS[event]:
        return
    argv = arguments[LAUNCH_EVENTS[event]]
    cwd = arguments[2] if event == "subprocess.Popen" and len(arguments) > 2 else None
    if cwd is not None:
        cwd = os.fsdecode(os.fspath(cwd))
    if isinstance(argv, (str, bytes, os.PathLike)):
        argv = [argv]
    try:
        command = [os.fsdecode(os.fspath(token)) for token in argv]
    except TypeError:
        return
    commands = [command]
    for token in command:
        if " " in token:
            # A shell's `-c` line.
            import shlex

            try:
                commands.append(shlex.split(token))
            except ValueError:
                pass
    for tokens in commands:
        found = _unmeasured_script(tokens, measured, cwd)
        if found is None and tokens and measured(tokens[0], cwd):
            # The file itself is the program: its `#!` line picks the flags.
            found = _unmeasured_script(_shebang(tokens[0], cwd) + tokens, measured, cwd)
        if found is not None:
            raise RuntimeError(
                f"sitecustomize: {found} would run with -I, -E or -S, which skip the coverage "
                "start, so the installer gate would not see its lines; run it without those flags"
            )


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

    loose = _loose(patterns)
    anchored = _anchored(patterns, os.path.dirname(os.path.realpath(config_file)))

    def gate_measured(filename, cwd):
        return _matches(filename, anchored, fnmatchcase, cwd)

    state = {"done": False}

    def hook(event, arguments):
        if event == "exec":
            if state["done"]:
                return
            code = arguments[0] if arguments else None
            if _matches(getattr(code, "co_filename", None), loose, fnmatchcase):
                # Set first: starting coverage imports it, and those imports
                # are `exec` events of their own.
                state["done"] = True
                _start(config_file)
        elif event in LAUNCH_EVENTS:
            _refuse_unmeasured_launch(event, arguments, gate_measured)

    sys.addaudithook(hook)


_install()
