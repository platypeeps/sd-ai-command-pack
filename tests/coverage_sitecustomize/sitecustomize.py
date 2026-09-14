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
installer in a temporary tree is not refused. The watch reads a program only
at command position: an argument list's first word, past assignments,
redirections and ``env`` with its options (``-C`` followed), and the first
word of each command in a shell's ``-c`` string -- split at ``;``, ``&``,
``|``, parentheses and newlines, following a ``cd`` that is not in a pipeline,
the background or a subshell, and nested shells -- plus a measured file's own
``#!`` line. A ``python`` word
elsewhere is another program's argument, and a shell's words after its ``-c``
string are positional arguments, so neither is refused. It does not see a
launch from a non-Python parent, ``-m`` naming a measured module, a wrapper
other than ``env`` (``exec``, ``nohup``, ``xargs``), or a ``cd`` whose
directory a variable names.

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
#: Programs whose non-option arguments are read as a command line.
SHELLS = frozenset(("sh", "bash", "dash", "zsh", "ksh"))
#: What ends one shell command and starts the next, `(` and `)` included.
SHELL_SEPARATORS = ";&|()\n"


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
    # `_settraceallthreads` sets this thread too, over the tracer the start just
    # gave it: that tracer would be orphaned, a second one built at the next
    # call, and PyTracer warns at exit that its trace function changed. So
    # this thread gets its own tracer back.
    here = sys.gettrace()
    set_all(install)
    sys.settrace(here)


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
    """The measured script an interpreter command line runs with site skipped, if any.

    Only the program itself is an interpreter: a `python` word further along
    is some other program's argument.
    """
    if not tokens or not os.path.basename(tokens[0]).startswith("python"):
        return None
    position = 1
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


def _unwrapped(words, cwd):
    """The program a command runs and where: past assignments, redirections, and `env` with its options."""
    while words:
        name, equals, _ = words[0].partition("=")
        redirect = words[0].lstrip("0123456789")
        if equals and name.isidentifier():
            words = words[1:]
        elif redirect[:1] in ("<", ">"):
            # `>log`, or `>` and `2>&` with the target in the next word.
            bare = not redirect.strip("<>&")
            words = words[1 + bare + (bare and words[1:2] == ["&"]):]
        elif os.path.basename(words[0]) == "env":
            words = words[1:]
            while words:
                word = words[0]
                if word == "--":
                    words = words[1:]
                    break
                if word in ("-S", "--split-string") and len(words) > 1:
                    import shlex

                    try:
                        words = shlex.split(words[1]) + words[2:]
                    except ValueError:
                        return [], cwd
                elif word in ("-C", "--chdir") and len(words) > 1:
                    cwd = os.path.join(cwd or "", words[1])
                    words = words[2:]
                elif word.startswith("--chdir="):
                    cwd = os.path.join(cwd or "", word.partition("=")[2])
                    words = words[1:]
                elif word in ("-u", "--unset", "-P") and len(words) > 1:
                    words = words[2:]
                elif word.startswith("-") or "=" in word:
                    words = words[1:]
                else:
                    break
        else:
            break
    return words, cwd


def _shell_line(words):
    """The `-c` string of a shell's argv, or None; the words after it are positional."""
    reads_line = False
    position = 1
    while position < len(words):
        word = words[position]
        if word in ("--", "-"):
            position += 1
            break
        if word.startswith("--"):
            position += 1 + (word in ("--rcfile", "--init-file"))
            continue
        if word[:1] not in ("-", "+"):
            break
        reads_line = reads_line or (word[0] == "-" and "c" in word)
        # `-o name` and bash's `-O name` take the next word.
        position += 1 + ("o" in word or "O" in word)
    if reads_line and position < len(words):
        return words[position]
    return None


def _shell_commands(line, cwd):
    """Each simple command of a shell line, with the directory a `cd` before it left."""
    import shlex

    lexer = shlex.shlex(line, posix=True, punctuation_chars=SHELL_SEPARATORS)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        words = list(lexer)
    except ValueError:
        return []
    commands, current, subshells, previous, before = [], [], [], "", ";"
    for word in words + [";"]:
        # The `&` of a `2>&1` redirect is not a separator.
        if word and not word.strip(SHELL_SEPARATORS) and not previous.endswith(("<", ">")):
            if current:
                commands.append((current, cwd))
                # A `cd` in a pipeline or in the background runs in a subshell.
                if not any(mark in (before, word) for mark in ("|", "|&", "&")):
                    cwd = _after_cd(current, cwd)
                current = []
            before = word
            for mark in word:
                if mark == "(":
                    subshells.append(cwd)
                elif mark == ")" and subshells:
                    cwd = subshells.pop()
        else:
            current.append(word)
        previous = word
    return commands


def _after_cd(words, cwd):
    if words[0] != "cd":
        return cwd
    targets = [word for word in words[1:] if word not in ("-L", "-P", "--")]
    if not targets:
        return os.path.expanduser("~")
    if len(targets) > 1 or targets[0] == "-":
        return cwd
    return os.path.join(cwd or "", targets[0])


def _programs(words, cwd, depth=0):
    """Each argv a launch runs at command position: its own, then its shell lines' commands."""
    words, cwd = _unwrapped(words, cwd)
    if not words:
        return
    yield words, cwd
    if depth < 4 and os.path.basename(words[0]) in SHELLS:
        line = _shell_line(words)
        if line is not None:
            for command, where in _shell_commands(line, cwd):
                yield from _programs(command, where, depth + 1)


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
    # A shell's `-c` string is a command line of its own. Only a shell's, and
    # only that string: a space in another program's argument, `python -c`
    # source included, is not parsed as one, nor are a shell's positional
    # arguments after the string.
    for tokens, where in _programs(command, cwd):
        found = _unmeasured_script(tokens, measured, where)
        if found is None and measured(tokens[0], where):
            # The file itself is the program: its `#!` line picks the flags.
            interpreter, there = _unwrapped(_shebang(tokens[0], where) + tokens, where)
            found = _unmeasured_script(interpreter, measured, there)
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
