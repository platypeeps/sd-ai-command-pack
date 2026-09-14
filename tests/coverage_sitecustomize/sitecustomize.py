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
value attached or in the next word), the first word of each command in a
shell's ``-c`` string or in an ``eval``'s arguments, and nested shells -- plus
a measured file's own ``#!`` line.

A shell line is read like this. Each ``#`` comment is cut, a backslash before
a newline joins the two lines, and what a quote or a backslash covers is marked
as text: a quoted ``if`` is a program and a quoted ``;`` is an argument. A
quote left open ends its line, which is what the shell does with it. The line
splits at ``;``, ``&``, ``&&``, ``|``, ``||``, parentheses, backticks and
newlines, and each command is read past a reserved word (``!``, ``if``,
``then``, ``elif``, ``else``, ``while``, ``until``, ``do``, and ``time`` with
its ``-p`` and ``--``) and past its redirections, with its patterns expanded
where it runs.

Where each command runs is followed too. A ``cd``, ``pushd`` or ``popd`` moves
the directory and the ``pushd`` stack: a bare ``pushd`` swaps the top two
entries, ``+N`` and ``-N`` rotate it, ``-n`` leaves the directory where it is,
``popd +N`` drops an entry, and ``cd -`` goes back. A subshell, a backtick
and a ``<(...)`` put the directory back where they found it, and so does a
pipeline, while a ``&`` puts back the whole list it backgrounded: the shell
runs each of those in a child of its own. A function definition puts it back
as well, its body not having run yet, and a call to a function defined on the
same line reads that body again, where the caller stands, assignments and
redirections before its name included. Which functions are defined, and which
have been called, is part of that state, so a definition or a call inside a
subshell, a pipeline or a ``&`` goes back with it, as it does in the shell. A
second call to the same body, under its own name or another, keeps the
directory, which is a choice rather than the shell's rule: the relative ``cd``
that moved once usually fails the next time, but ``f() { cd ..; }`` called
twice really moves twice, and so does ``f() { cd sub; }`` where ``sub/sub``
exists. After ``f; f`` there the check stands one directory short, so it
misses a launch that runs and refuses a line that launches nothing. A compound
command (``{ }``, ``if``, ``while``, ``until``, ``for``, ``select``, ``case``)
is one command to the pipeline around it, and a ``)`` that closes a ``case``
pattern closes no subshell. A ``python`` word elsewhere is another program's argument,
a bash array's ``a=(...)`` words are values, a ``for``'s are names, and a
shell's words after its ``-c`` string are positional arguments, so none of
those is refused.

It does not see:

- a launch from a non-Python parent, or ``-m`` naming a measured module;
- a wrapper other than ``env`` (``exec``, ``command``, ``builtin``, ``nice``,
  ``nohup``, ``xargs``, ``/usr/bin/time``): its options differ per wrapper;
- the commands a shell reads from anywhere but its ``-c`` string: a script
  file, and a here-document, a here-string or a pipe on its standard input,
  which the launch does not carry; nor the commands ``.`` or ``source`` reads
  from a file, which may not exist yet when the launch is read;
- a here-document's body, which it reads as commands rather than as the data
  it is: text there that looks like a launch fails the test that wrote it, and
  a quote there left open ends the line, hiding a launch after the body;
- a script the shell gets from ``"$@"`` or ``$1``, a program or a ``cd``
  directory a variable or a ``$(...)`` names: positional arguments, variables
  and substitutions are not expanded, by design;
- a command inside double quotes (``"$(python -I ...)"``, ``"`...`"``) or an
  ANSI-C ``$'...'`` string: quoted text is one word;
- a command after ``coproc``: only the words above are skipped;
- a ``cd`` in an ``eval``: the line it is read as ends with it;
- a call to a function defined anywhere but the same line, named by a
  variable or a substitution, or made through ``eval`` or another shell;
- a call more than ``SHELL_REPLAYS`` calls deep, which is where a function
  that calls itself stops being read, and every call after the first
  ``SHELL_CALLS`` in one line, a bound on the work one line can cost;
- a quoted word that reads as an assignment (``'x=1' f``): it is taken for
  one, so the word after it is read as the command's name;
- a ``return``, an ``unset -f`` or ``FUNCNEST`` cutting a function short: a
  call reads the whole body, and a definition stands until another replaces it;
- a launch written in a function body, which is read where the body is
  defined: that is a refusal rather than a miss, even when nothing calls the
  function;
- which branch the shell takes: every arm of a ``&&``, a ``||`` and a ``case``
  is read in order, so a ``cd`` in an arm the shell skips is followed, and a
  launch in one is refused;
- a pattern in a word part of which is quoted (``bin/sd_inst*".py"``): one
  quote stops the whole word expanding;
- whether a program named like an interpreter is one: any program whose name
  starts with ``python`` is taken for one, ``python-config`` and a path nothing
  is at included, which is a refusal rather than a miss;
- a carriage return, which the shell keeps in its word and this reads as a
  space: a launch at the end of a CRLF line is refused, though the shell looks
  for a script whose name ends in one;
- a ``cd`` or ``pushd`` that fails, and a ``cd -`` before any ``cd`` in the
  line: whether a directory exists is settled when the shell runs, which is
  after this reads the launch -- an earlier command may make it -- and the
  directory ``cd -`` goes back to first comes from ``OLDPWD``.

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
#: Shell operators of more than one character, longest first: `;;&` before `;;`.
SHELL_OPERATORS = (";;&", ";;", ";&", "&&", "||", "|&")
#: Shell reserved words a command can follow. Not `for`, `case` or `select`,
#: whose next word is a name or a value rather than a program.
SHELL_RESERVED = frozenset(("!", "if", "then", "elif", "else", "while", "until", "do", "time"))
#: Reserved words that end the list before them rather than opening a block.
SHELL_BRANCHES = frozenset(("then", "else", "elif", "do"))
#: Compound commands and the word that closes each. What one runs is its own
#: list: a `|` or a `&` on the block puts the whole of it in a subshell.
SHELL_BLOCKS = {"{": "}", "if": "fi", "while": "done", "until": "done", "for": "done",
                "select": "done", "case": "esac"}
#: Stands in for the directory a `cd -` goes to before any `cd` in the line:
#: the shell reads it from `OLDPWD`, which the launch does not carry.
ELSEWHERE = object()
#: Marks a word a quote or a backslash covered: a quoted `if` is a program, and
#: a quoted `;` is that program's argument rather than the shell's separator.
QUOTED = "\0"
#: How deep calls inside function bodies are read through, and how many calls one line is.
SHELL_REPLAYS = 8
SHELL_CALLS = 256
#: Short `env` options that take a value, attached or in the next word.
ENV_VALUE_LETTERS = "aCSuPLU"
#: Long `env` options that take a value, after `=` or in the next word.
ENV_VALUE_OPTIONS = frozenset(("--argv0", "--chdir", "--split-string", "--unset"))


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
    """A shell line ready to lex: comments cut, continuations joined, quoted text marked.

    A quote or `;` in a comment is not the line's, so each `#` comment is cut to
    its newline. `&>file` redirects, where a lone `&` would end the command and
    put it in the background, so it is written ` >`. A `\\` before a newline
    joins the two lines, as the shell does before it reads any word. Each
    quote and each backslash escape leaves a `QUOTED` mark in the word it
    covers; `_shell_tokens` reads the marks and drops them.

    A quote left open swallows the rest of its line, which is what the shell
    does with it: the line does not parse, so nothing on it runs, while the
    lines before it have run already.
    """
    kept, quote, boundary, position, opened = [], "", True, 0, 0
    while position < len(line):
        char, following = line[position], line[position + 1:position + 2]
        if char == "\\" and quote != "'" and following == "\n":
            position += 2
            continue
        if char == "\\" and quote != "'":
            kept.append(QUOTED + line[position:position + 2])
            position += 2
            boundary = False
            continue
        if char == "#" and boundary and not quote:
            end = line.find("\n", position)
            position = len(line) if end < 0 else end
            continue
        if char in "'\"" and quote in ("", char):
            if not quote:
                opened = len(kept)
                kept.append(QUOTED)
            quote = "" if quote else char
        elif (char == "&" and not quote and following == ">"
              and not "".join(kept[-1:]).endswith(("&", "|", "<", ">"))):
            char = " "
        kept.append(char)
        position += 1
        boundary = not quote and char in " \t\r" + SHELL_SEPARATORS
    if quote:
        del kept[opened:]
        while kept and "\n" not in kept[-1]:
            kept.pop()
    return "".join(kept)


def _shell_tokens(line):
    """A shell line as `(text, operator, quoted)` triples, `QUOTED` marks read and dropped."""
    import shlex

    lexer = shlex.shlex(_prepared(line), posix=True, punctuation_chars=SHELL_SEPARATORS)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        raw = list(lexer)
    except ValueError:
        return []
    tokens = []
    for index, token in enumerate(raw):
        previous = raw[index - 1] if index else ""
        operator = bool(token) and not token.strip(SHELL_SEPARATORS)
        if operator and previous.endswith(("<", ">")) and not token.startswith("("):
            # The `&` of `2>&1` and the `|` of `>|file` belong to the redirection,
            # where the `(` of `<(...)` opens a command of its own.
            operator = False
        if not operator:
            tokens.append((token.replace(QUOTED, ""), False, QUOTED in token))
            continue
        while token:
            # `;;&` is one operator, `&&|` is `&&` and then `|`.
            head = next((form for form in SHELL_OPERATORS if token.startswith(form)), token[0])
            tokens.append((head, True, False))
            token = token[len(head):]
    return tokens


def _expanded(words, cwd):
    """A command's words, each unquoted pattern replaced by the paths it matches.

    A pattern that matches nothing stays as written, which is what the shell
    does with it unless `nullglob` is set.
    """
    if not any(not quoted and set(text) & set("*?[") for text, quoted in words):
        return [text for text, _ in words]
    import glob

    expanded = []
    for text, quoted in words:
        matched = []
        if not quoted and set(text) & set("*?["):
            try:
                matched = sorted(glob.glob(text, root_dir=cwd))
            except (OSError, ValueError):
                matched = []
        expanded.extend(matched or [text])
    return expanded


def _opens_array(word):
    # `a=(` or `a+=(`: the words up to the matching `)` are values.
    name, equals, value = word.partition("=")
    return bool(equals) and not value and name.removesuffix("+").isidentifier()


def _frame(kind, state):
    """One open subshell, block or array, and what a `|` or `&` on it restores.

    `saved` is the state at its opening word, put back when what it holds runs
    in a subshell of its own; `pipe` and `list` are the states its current
    pipeline and its current and-or list began in; `case` tracks where a
    `case` is (its subject, its `in`, a pattern or an arm) and `header` a
    `for` or `select` whose words are names rather than a command. A function
    body names the function in `defines` and where its tokens begin in `start`,
    so a call can read them again.
    """
    return {"kind": kind, "saved": state, "pipe": None, "list": None, "piped": False,
            "case": "", "header": False, "scoped": False, "defines": "", "start": 0,
            "replay": False}


def _begin(frame, state):
    """Mark where this pipeline and this and-or list started, for a `|` or `&` to put back."""
    for edge in ("pipe", "list"):
        if frame[edge] is None:
            frame[edge] = state


def _ends_pipeline(frame, state):
    """The state after a pipeline: each command of one with a `|` ran in a subshell."""
    if frame["piped"] and frame["pipe"] is not None:
        state = frame["pipe"]
    frame["pipe"] = None
    frame["piped"] = False
    return state


def _closed(frames, state):
    """Pop one frame: a subshell, a backtick, a `<(...)` or a function body puts its state back."""
    frame = frames.pop()
    return frame["saved"] if frame["scoped"] else state


def _unwound(frames, state, kind):
    """Pop through the nearest frame of `kind`, or nothing when there is none open."""
    if not any(frame["kind"] == kind for frame in frames[1:]):
        return state
    while frames[-1]["kind"] != kind:
        state = _closed(frames, state)
    return _closed(frames, state)


def _recorded(commands, current, state, follows):
    """Record a command and, when it has ended, follow a `cd`, `pushd` or `popd` in it."""
    if not current:
        return state
    words = _expanded(current, state[0])
    commands.append((words, state[0]))
    return _after_cd(words, state) if follows else state


def _defines_function(current, tokens, index):
    """`f ()` at command position: a definition, whose body runs where its caller stands."""
    return (len(current) == 1 and not current[0][1] and not set(current[0][0]) & set("=$")
            and tokens[index:index + 1] == [(")", True, False)])


def _prefixed(current):
    """Whether a command so far is only assignments and redirections, so its next word is its name."""
    words = [text for text, _ in current]
    while words:
        name, equals, _ = words[0].partition("=")
        taken = _redirection(words) or (1 if equals and name.isidentifier() else 0)
        if not taken or taken > len(words):
            # A word the next one completes, as `>` does its file, is no prefix.
            return False
        words = words[taken:]
    return True


def _defined(state, name, body):
    """The state a definition leaves: the shell that ran it knows one more function.

    The functions live in the state, so a subshell, a pipeline or a `&` loses
    the ones defined inside it when its state goes back, as the shell does.
    """
    return (*state[:3], {**state[3], name: body}, state[4])


def _calls(state, body):
    """The state a call leaves: this body has moved the directory here once.

    The mark is the body's, not the name's: a new body under an old name has
    not run, and the same body under another name has.
    """
    return (*state[:4], state[4] | {tuple(body)})


def _shell_commands(line, cwd):
    """Each simple command of a shell line, with the directory a `cd` before it left."""
    tokens = _shell_tokens(line)
    tokens.append((";", True, False))
    # The state is the directory, the one `cd -` goes back to, the `pushd`
    # stack, the functions defined here as the tokens of their bodies, and the
    # bodies already called. `frames` holds it as each subshell, block and array
    # was opened, so what a child defines or calls goes back with it.
    state = (cwd, ELSEWHERE, (), {}, frozenset())
    previous, pending, named, calls, index, deeper = ("", True), "", "", 0, 0, False
    commands, current, frames = [], [], [_frame("", state)]
    while index < len(tokens):
        text, operator, quoted = tokens[index]
        index += 1
        frame = frames[-1]
        if not operator:
            if frame["kind"] == "=" or frame["header"] and text not in SHELL_BRANCHES:
                # An array's words are values, a `for`'s are names.
                pass
            elif frame["case"] in ("subject", "in"):
                frame["case"] = "in" if frame["case"] == "subject" else "pattern"
            elif frame["case"] == "pattern":
                if text == "esac" and not quoted:
                    state = _closed(frames, state)
            elif (text in state[3] and _prefixed(current) and calls < SHELL_CALLS
                  and sum(entry["replay"] for entry in frames) < SHELL_REPLAYS
                  and tokens[index:index + 1] != [("(", True, False)]
                  and not any(entry["defines"] for entry in frames)):
                # A call reads the body again, where the caller stands, as one
                # command to the pipeline around it -- which is what a call is.
                # Assignments and redirections before the name leave it a call.
                # A body being defined is not running, so a name in one is not
                # a call, and a name a `()` follows is a definition of its own.
                # A second call to the same body keeps the directory, as a
                # definition does: a modelling choice the docstring names, not
                # the shell's rule. The `:` that ends the replay takes the
                # call's own words, which are the body's arguments.
                calls += 1
                body = state[3][text]
                named, pending, current = "", "body" if tuple(body) in state[4] else "", []
                # The pipeline and the list this call is in began before it,
                # so what they put back is the state without the call in it.
                _begin(frame, state)
                state = _calls(state, body)
                tokens[index:index] = [("{", False, False), *body, (";", True, False),
                                       ("}", False, False), (":", False, False)]
                # The `{` opened next is this call's, one call deeper.
                deeper = True
            elif current or quoted:
                _begin(frame, state)
                current.append((text, quoted))
            elif pending == "name":
                named, pending = text, "body"
            elif text == SHELL_BLOCKS.get(frame["kind"]):
                body = tokens[frame["start"]:index - 1] if frame["defines"] else None
                state = _closed(frames, state)
                if body is not None:
                    state = _defined(state, frame["defines"], body)
            elif text in SHELL_BRANCHES:
                frame["header"] = False
                state = _ends_pipeline(frame, state)
                frame["list"] = None
            elif text == "function":
                pending = "name"
            elif text in SHELL_BLOCKS:
                _begin(frame, state)
                frames.append(_frame(text, state))
                frames[-1]["header"] = text in ("for", "select")
                frames[-1]["case"] = "subject" if text == "case" else ""
                frames[-1]["scoped"] = pending == "body"
                frames[-1]["defines"] = named if pending == "body" else ""
                frames[-1]["start"] = index
                frames[-1]["replay"] = deeper
                pending, deeper = "", False
            elif not (text in SHELL_RESERVED or (text in ("-p", "--") and previous[0] in ("time", "-p"))):
                pending = ""
                _begin(frame, state)
                current.append((text, quoted))
        elif frame["kind"] == "=":
            if text == "(":
                frames.append(_frame("(", state))
                frames[-1]["scoped"] = True
            elif text == ")":
                frames.pop()
        elif frame["case"] == "pattern" and text != ")":
            pass
        elif text == "(":
            if _defines_function(current, tokens, index):
                named, current, pending, index = current[0][0], [], "body", index + 1
            elif current and _opens_array(current[-1][0]):
                _begin(frame, state)
                frames.append(_frame("=", state))
            else:
                # `$(`, `<(` or a subshell: what it runs is a command line, and
                # the command it sits in has not ended, so no `cd` is followed.
                state = _recorded(commands, current, state, False)
                current = []
                _begin(frame, state)
                frames.append(_frame("(", state))
                frames[-1]["scoped"] = True
        elif text == ")":
            if frame["case"] == "pattern":
                frame["case"] = "body"
            else:
                state = _recorded(commands, current, state, True)
                current = []
                state = _unwound(frames, state, "(")
        elif text == "`":
            closes = any(entry["kind"] == "`" for entry in frames[1:])
            state = _recorded(commands, current, state, closes)
            current = []
            if closes:
                state = _unwound(frames, state, "`")
            else:
                _begin(frame, state)
                frames.append(_frame("`", state))
                frames[-1]["scoped"] = True
        elif not (text == "\n" and previous[1] and previous[0] in ("&&", "||", "|", "|&")):
            state = _recorded(commands, current, state, True)
            current = []
            if text in ("|", "|&"):
                frame["piped"] = True
                state = frame["pipe"] if frame["pipe"] is not None else state
            elif text in ("&&", "||"):
                state = _ends_pipeline(frame, state)
            else:
                state = _ends_pipeline(frame, state)
                if text == "&" and frame["list"] is not None:
                    # The whole list ran in the background, in a subshell.
                    state = frame["list"]
                frame["list"] = None
                if text.startswith(";;") or text == ";&":
                    frame["case"] = "pattern" if frame["case"] else ""
        previous = (text, operator)
    return commands


def _stack_entry(target, size):
    """Which `pushd` stack entry a `+N` or `-N` names: -1 for none, None when it is a directory."""
    if not target or target[0] not in "+-" or not target[1:].isdigit():
        return None
    offset = int(target[1:])
    index = offset if target[0] == "+" else size - 1 - offset
    return index if 0 <= index < size else -1


def _after_cd(words, state):
    """The state after a `cd`, `pushd` or `popd`: the directory, where `cd -` goes, the stack.

    The stack is the `pushd` one, its last entry the top, which is what `popd`
    returns to; the directory itself is the stack's first entry, as `dirs`
    prints it. A bare `pushd` swaps the top two entries, `+N` and `-N` rotate
    it and `-n` leaves the directory where it is.
    """
    kept = []
    while words:
        taken = _redirection(words)
        if not taken:
            kept.append(words[0])
        words = words[taken or 1:]
    if not kept or kept[0] not in ("cd", "pushd", "popd"):
        return state
    cwd, back, stack = state[:3]
    name, arguments, moves = kept[0], list(kept[1:]), True
    while arguments:
        option = arguments[0]
        if not option.startswith("-") or option == "-" or option[1:].isdigit():
            break
        del arguments[0]
        if option == "--":
            break
        moves = moves and not (name != "cd" and "n" in option)
    if len(arguments) > 1:
        # `cd a b` and `pushd a b` are errors: the directory does not change.
        return state
    target = arguments[0] if arguments else ""
    if name == "cd":
        if target == "-" and back is ELSEWHERE:
            # Before any `cd` in this line, `OLDPWD` comes from the environment.
            return state
        there = back if target == "-" else (os.path.join(cwd or "", target) if target
                                           else os.path.expanduser("~"))
        return (there, cwd, stack, *state[3:])
    entries = [cwd, *reversed(stack)]
    index = _stack_entry(target, len(entries))
    if index == -1:
        return state
    if name == "pushd":
        if not target:
            if not moves or len(entries) < 2:
                return state
            entries = [entries[1], entries[0], *entries[2:]]
        elif index is not None:
            if not moves:
                return state
            entries = entries[index:] + entries[:index]
        elif moves:
            entries = [os.path.join(cwd or "", target), *entries]
        else:
            return (cwd, back, stack + (os.path.join(cwd or "", target),), *state[3:])
    else:
        if index is None and target or len(entries) < 2:
            return state
        spot = index or 0
        # `popd` leaves the top entry and moves to the next; `popd -n` drops
        # that next entry instead and stays where it is.
        gone = spot if spot or moves else 1
        if gone >= len(entries):
            return state
        entries = entries[:gone] + entries[gone + 1:]
    there = entries[0]
    return (there, cwd if there != cwd else back, tuple(reversed(entries[1:])), *state[3:])


def _programs(words, cwd, depth=0):
    """Each argv a launch runs at command position: its own, then its shell lines' commands."""
    words, cwd = _unwrapped(words, cwd)
    if not words:
        return
    yield words, cwd
    if depth >= 4:
        return
    if words[0] == "eval":
        # `eval` reads its arguments, joined, as a line of their own.
        line = " ".join(words[1:])
    elif os.path.basename(words[0]) in SHELLS:
        line = _shell_line(words)
    else:
        return
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
