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
redirections and ``env`` with its options (``-C`` followed, ``-S`` split, a
value attached or in the next word), and the first word of each command in a
shell's ``-c`` string -- ``#`` comments cut, split at ``;``, ``&``, ``|``,
parentheses, backticks and newlines, past a reserved word (``!``, ``{``,
``if``, ``then``, ``elif``, ``else``, ``while``, ``until``, ``do``, ``time``),
following a ``cd``, ``pushd`` or ``popd`` that is not in a pipeline, the
background or a subshell, past its redirections, and nested shells -- plus a
measured file's own ``#!`` line. A ``python`` word elsewhere is another
program's argument, a bash array's ``a=(...)`` words are values, and a shell's
words after its ``-c`` string are positional arguments, so none is refused.

It does not see:

- a launch from a non-Python parent, or ``-m`` naming a measured module;
- a wrapper other than ``env`` (``exec``, ``command``, ``nice``, ``nohup``,
  ``xargs``, ``/usr/bin/time``): its options differ per wrapper;
- a script the shell gets from ``"$@"`` or ``$1``, a program or a ``cd``
  directory a variable names: positional arguments and variables are not
  expanded, by design;
- a command inside double quotes (``"$(python -I ...)"``, ``"`...`"``) or in a
  process substitution (``<(...)``, ``>(...)``): quoted text is one word;
- a command after ``function f {`` or ``coproc``: only the reserved words
  above are skipped.

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
#: What ends one shell command and starts the next, `(`, `)` and backticks included.
SHELL_SEPARATORS = ";&|()`\n"
#: Shell reserved words a command can follow. Not `for`, `case` or `select`,
#: whose next word is a name or a value rather than a program.
SHELL_RESERVED = frozenset(("!", "{", "if", "then", "elif", "else", "while", "until", "do", "time"))
#: Short `env` options that take a value, attached or in the next word.
ENV_VALUE_LETTERS = "CSuPLU"
#: Long `env` options that take a value, after `=` or in the next word.
ENV_VALUE_OPTIONS = frozenset(("--chdir", "--split-string", "--unset"))


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
    # this thread gets its own tracer back. A thread that had none keeps the
    # installer, which builds its tracer at the next call.
    here = sys.gettrace()
    set_all(install)
    if here is not None:
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
            position += 1 + (option == "--check-hash-based-pycs")
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


def _redirection(words):
    """How many leading words a redirection takes: `>log` one, `> log` two, `2>&1` as `2>`, `&`, `1` three."""
    redirect = words[0].lstrip("0123456789") if words else ""
    if redirect[:1] not in ("<", ">"):
        return 0
    bare = not redirect.strip("<>&")
    return 1 + bare + (bare and words[1:2] == ["&"])


def _unwrapped(words, cwd):
    """The program a command runs and where: past assignments, redirections, and `env` with its options."""
    while words:
        name, equals, _ = words[0].partition("=")
        redirection = _redirection(words)
        if equals and name.isidentifier():
            words = words[1:]
        elif redirection:
            words = words[redirection:]
        elif os.path.basename(words[0]) == "env":
            words, cwd = _past_env_options(words[1:], cwd)
        else:
            break
    return words, cwd


def _past_env_options(words, cwd):
    """The words after `env`'s options, `-S` strings split in, and the directory `-C` names."""
    while words:
        word, letter, value = words[0], "", ""
        if word == "--":
            return words[1:], cwd
        if word.startswith("--"):
            name, equals, value = word.partition("=")
            words = words[1:]
            if name in ENV_VALUE_OPTIONS:
                letter = {"--chdir": "C", "--split-string": "S"}.get(name, "u")
                if not equals and words:
                    value, words = words[0], words[1:]
        elif word.startswith("-"):
            # A cluster such as `-iC sub` or `-Csub`: the first letter that
            # takes a value takes the rest of the word, or the next word.
            words = words[1:]
            letters = word[1:]
            offset = next((index for index, flag in enumerate(letters) if flag in ENV_VALUE_LETTERS), None)
            if offset is not None:
                letter, value = letters[offset], letters[offset + 1:]
                if not value and words:
                    value, words = words[0], words[1:]
        elif "=" in word:
            words = words[1:]
        else:
            break
        if letter == "C":
            cwd = os.path.join(cwd or "", value)
        elif letter == "S":
            import shlex

            try:
                words = shlex.split(value) + words
            except ValueError:
                return [], cwd
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


def _prepared(line):
    """A shell line with each `#` comment cut to its newline, and `&>` written ` >`.

    A quote or `;` in a comment is not the line's. `&>file` redirects, where a
    lone `&` would end the command and put it in the background.
    """
    kept, quote, boundary, position = [], "", True, 0
    while position < len(line):
        char = line[position]
        if char == "\\" and quote != "'":
            kept.append(line[position:position + 2])
            position += 2
            boundary = False
            continue
        if char == "#" and boundary and not quote:
            end = line.find("\n", position)
            position = len(line) if end < 0 else end
            continue
        if char in "'\"" and quote in ("", char):
            quote = "" if quote else char
        elif (char == "&" and not quote and line[position + 1:position + 2] == ">"
              and not "".join(kept[-1:]).endswith(("&", "|", "<", ">"))):
            char = " "
        kept.append(char)
        position += 1
        boundary = not quote and char in " \t\r" + SHELL_SEPARATORS
    return "".join(kept)


def _opens_array(word):
    # `a=(` or `a+=(`: the words up to the matching `)` are values.
    name, equals, value = word.partition("=")
    return bool(equals) and not value and name.removesuffix("+").isidentifier()


def _shell_commands(line, cwd):
    """Each simple command of a shell line, with the directory a `cd` before it left."""
    import shlex

    lexer = shlex.shlex(_prepared(line), posix=True, punctuation_chars=SHELL_SEPARATORS)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        words = list(lexer) + [";"]
    except ValueError:
        return []
    # `nested` holds, for each open `(`, backtick or array, which of the three
    # it is, and the directory and `pushd` stack before it: a subshell's
    # `cd`, `pushd` and `popd` change neither.
    commands, current, nested, pushed, before = [], [], [], [], ";"
    for index, word in enumerate(words):
        previous = words[index - 1] if index else ""
        # The `&` of a `2>&1` redirect is not a separator.
        if not word or word.strip(SHELL_SEPARATORS) or previous.endswith(("<", ">")):
            if nested and nested[-1][1] == "=":
                continue
            # A reserved word at command position is not the program.
            if current or not (word in SHELL_RESERVED or (word == "-p" and previous == "time")):
                current.append(word)
            continue
        flushed = False
        for mark in word:
            in_array = bool(nested) and nested[-1][1] == "="
            if mark == "(" and not in_array and current and _opens_array(current[-1]):
                nested.append((cwd, "=", pushed[:]))
                continue
            if not in_array and not flushed:
                flushed = True
                if current:
                    commands.append((current, cwd))
                    # A `cd` in a pipeline or in the background runs in a subshell.
                    if not any(sign in (before, word) for sign in ("|", "|&", "&")):
                        cwd = _after_cd(current, cwd, pushed)
                    current = []
                before = word
            if mark in "(`" and not (mark == "`" and nested and nested[-1][1] == "`"):
                nested.append((cwd, mark, pushed[:]))
            elif mark in ")`" and nested:
                cwd, _, pushed = nested.pop()
    return commands


def _after_cd(words, cwd, pushed):
    """The directory after a `cd`, `pushd` or `popd`; `pushed` is the `pushd` stack so far."""
    kept = []
    while words:
        taken = _redirection(words)
        if not taken:
            kept.append(words[0])
        words = words[taken or 1:]
    if not kept or kept[0] not in ("cd", "pushd", "popd"):
        return cwd
    targets = [word for word in kept[1:] if word not in ("-L", "-P", "--")]
    if kept[0] == "popd":
        return pushed.pop() if pushed and not targets else cwd
    if not targets:
        return os.path.expanduser("~") if kept[0] == "cd" else cwd
    if len(targets) > 1 or targets[0] == "-" or (kept[0] == "pushd" and targets[0][:1] in "+-"):
        return cwd
    if kept[0] == "pushd":
        pushed.append(cwd)
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
