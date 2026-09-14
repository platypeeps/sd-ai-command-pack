"""Hold the launch check in tests/coverage_sitecustomize to what bash does.

`test_coverage_sitecustomize` pins rows the check must refuse or leave alone,
each decided by hand. This module asks bash. Every shape in `SHAPES` runs as
`bash -c LINE` in a fresh directory laid out as `LAYOUT`, with shims for
`python`, `python3` and `python3.N` first on `PATH`. A shim logs `pwd -P` and
its arguments and exits, so no interpreter starts and the real
`bin/sd_install.py` is never reached: the directory's own `bin/sd_install.py`
is an empty file. bash refuses a shape when a logged launch carries `-I`, `-E`
or `-S` and its script resolves to that file. The check refuses it when
`_refuse_unmeasured_launch` raises for the same argv and directory, decided
before bash runs, since a shape may write files.

Where the two differ, the shape must be in `LIMITS`, under a passage of the
sitecustomize docstring that says why, quoted as it stands there. A shape in
`LIMITS` that the two decide alike fails as well, so the list holds the
check's real limits and nothing it has outgrown. The table leaves out shapes
whose answer depends on the platform rather than the check (`env` options BSD
and GNU spell differently, `timeout`, `/usr/bin/time`, `xargs` with no input)
and a function that calls itself without end, which bash never finishes.

The comparison needs bash 4 or later (`coproc`, `|&` and `;;&` are bash 4)
and is skipped, saying so, without one. Set `SD_LAUNCH_CHECK_BASELINE` to
another revision's sitecustomize.py to print how it and this one fare against
bash: the four outcomes, and each shape the baseline gets right and this one
wrong.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from fnmatch import fnmatchcase
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECK = REPO_ROOT / "tests/coverage_sitecustomize/sitecustomize.py"

#: The directory each shape runs in, as the paths under it.
LAYOUT = ("bin", "sub/deep", "other", "dir with space", "ww/ww")

#: Logs where it ran and its arguments, separated by US and ended by RS.
SHIM = """#!/bin/sh
printf '%s\\037' "$(pwd -P)" "$@" >> "$SD_LAUNCH_LOG"
printf '\\036' >> "$SD_LAUNCH_LOG"
"""

SHIM_NAMES = ("python", "python3", *(f"python3.{minor}" for minor in range(30)))

#: Nine calls deep, one more than `SHELL_REPLAYS` reads.
NINE_DEEP = "f1() { cd sub; }; " + "".join(f"f{k}() {{ f{k - 1}; }}; " for k in range(2, 10)) + "f9; "

# Why a shape is decided otherwise than bash decides it: each reason is a
# passage of the sitecustomize docstring, quoted as it stands there.
WRAPPER = "a wrapper other than ``env``"
STANDARD_INPUT = "the commands a shell reads from anywhere but its ``-c`` string"
HERE_DOCUMENT = "a here-document's body, which it reads as commands"
POSITIONAL = "a script the shell gets from ``\"$@\"`` or ``$1``"
DOUBLE_QUOTED = "a command inside double quotes"
COPROC = "a command after ``coproc``"
CALLED_ELSEWHERE = "a call to a function defined anywhere but the same line"
TOO_DEEP = "a call more than ``SHELL_REPLAYS`` calls deep"
TOO_MANY_CALLS = "every call after the first ``SHELL_CALLS`` in one line"
QUOTED_ASSIGNMENT = "a quoted word that reads as an assignment"
CUT_SHORT = "a ``return``, an ``unset -f`` or ``FUNCNEST`` cutting a function short"
LAUNCH_IN_BODY = "a launch written in a function body"
BRANCH = "which branch the shell takes"
PARTLY_QUOTED = "a pattern in a word part of which is quoted"
NAMED_LIKE_PYTHON = "whether a program named like an interpreter is one"
CARRIAGE_RETURN = "a carriage return, which the shell keeps in its word"
FAILED_CD = "a ``cd`` or ``pushd`` that fails"
SECOND_CALL = "A second call to the same body, under its own name or another, keeps the directory"

#: Each shape the check decides otherwise than bash, under the passage of the
#: sitecustomize docstring that says why.
LIMITS = {
    "exec python -I bin/sd_install.py": WRAPPER,
    "exec -a x python -I bin/sd_install.py": WRAPPER,
    "command python -I bin/sd_install.py": WRAPPER,
    "nice python -I bin/sd_install.py": WRAPPER,
    "nice python -S bin/sd_install.py": WRAPPER,
    "nohup python -I bin/sd_install.py": WRAPPER,
    "echo bin/sd_install.py | xargs python -I": WRAPPER,
    "f() { builtin cd sub; }; f; python -I ../bin/sd_install.py": WRAPPER,
    "sh <<< 'python -I bin/sd_install.py'": STANDARD_INPUT,
    "echo 'python -I bin/sd_install.py' | sh": STANDARD_INPUT,
    "echo 'python -I bin/sd_install.py' > s.sh; . ./s.sh": STANDARD_INPUT,
    "cat >/dev/null <<EOF\npython -I bin/sd_install.py\nEOF": HERE_DOCUMENT,
    "cat >/dev/null <<EOF\nit's\nEOF\npython -I bin/sd_install.py": HERE_DOCUMENT,
    "sh -c 'python -I \"$@\"' sh bin/sd_install.py": POSITIONAL,
    "p=python; $p -I bin/sd_install.py": POSITIONAL,
    "x=\"$(python -I bin/sd_install.py)\"": DOUBLE_QUOTED,
    "echo $'it\\'s'; python -I bin/sd_install.py": DOUBLE_QUOTED,
    "coproc python -I bin/sd_install.py; wait": COPROC,
    "f() { cd sub; }; x=f; $x; python -I ../bin/sd_install.py": CALLED_ELSEWHERE,
    "f() { cd sub; }; eval f; python -I ../bin/sd_install.py": CALLED_ELSEWHERE,
    "f() { cd sub; }; export -f f; bash -c 'f; python -I ../bin/sd_install.py'": CALLED_ELSEWHERE,
    NINE_DEEP + "python -I ../bin/sd_install.py": TOO_DEEP,
    NINE_DEEP + "python -I bin/sd_install.py": TOO_DEEP,
    "n() { :; }; " + "n; " * 256 + "f() { cd sub; }; f; python -I ../bin/sd_install.py": TOO_MANY_CALLS,
    "n() { :; }; " + "n; " * 256 + "f() { cd sub; }; f; python -I bin/sd_install.py": TOO_MANY_CALLS,
    "f() { cd sub; }; 'x=1' f; python -I bin/sd_install.py": QUOTED_ASSIGNMENT,
    "FUNCNEST=2; f() { cd sub; f; }; f; python -I ../bin/sd_install.py": CUT_SHORT,
    "f() { cd sub; }; unset -f f; f; python -I bin/sd_install.py": CUT_SHORT,
    "f() { return; cd sub; }; f; python -I bin/sd_install.py": CUT_SHORT,
    "f() { python -I bin/sd_install.py; }; true": LAUNCH_IN_BODY,
    "( f() { python -I bin/sd_install.py; } ); true": LAUNCH_IN_BODY,
    "cd sub || cd other; python -I ../bin/sd_install.py": BRANCH,
    "case x in y) cd sub;; *) cd other;; esac; python -I ../bin/sd_install.py": BRANCH,
    "true || python -I bin/sd_install.py": BRANCH,
    "python -I bin/sd_inst*\".py\"": PARTLY_QUOTED,
    "python-config -I bin/sd_install.py": NAMED_LIKE_PYTHON,
    "/some/where/python -S bin/sd_install.py": NAMED_LIKE_PYTHON,
    "python -I bin/sd_install.py\r\n": CARRIAGE_RETURN,
    "cd nonexist; python -I bin/sd_install.py": FAILED_CD,
    "pushd nonexist; python -I bin/sd_install.py": FAILED_CD,
    "cd sub; cd sub; python -I ../../bin/sd_install.py": FAILED_CD,
    ("sub/deep", "f() { cd ..; }; f; f; python -I bin/sd_install.py"): SECOND_CALL,
    ("sub/deep", "f() { cd ..; }; f; f; python -I ../bin/sd_install.py"): SECOND_CALL,
    "f() { cd ww; }; f; f; python -I ../../bin/sd_install.py": SECOND_CALL,
    "f() { cd ww; }; f; f; python -I ../bin/sd_install.py": SECOND_CALL,
    "f() { cd sub; }; g() { f; cd ..; }; g; f; python -I bin/sd_install.py": SECOND_CALL,
    "f() { cd sub; }; f; cd ..; f; python -I bin/sd_install.py": SECOND_CALL,
}

#: Every shape, as its line or as (the directory it runs in, its line).
SHAPES = (
    # The launches the review of #929 (sd:764) tried.
    "exec python -I bin/sd_install.py",
    "command python -I bin/sd_install.py",
    "nice python -S bin/sd_install.py",
    "time python -E bin/sd_install.py",
    "echo bin/sd_install.py | xargs python -I",
    "python3.13 -IS bin/sd_install.py",
    "python -X importtime -I bin/sd_install.py",
    "python -Ximporttime -I bin/sd_install.py",
    "python -W ignore -E bin/sd_install.py",
    "python -I -X dev bin/sd_install.py",
    "python -IX dev bin/sd_install.py",
    "python --check-hash-based-pycs never -I bin/sd_install.py",
    "python -u -I bin/sd_install.py",
    "/usr/bin/env python3 -E bin/sd_install.py",
    "bash -lc 'python -I bin/sd_install.py'",
    "sh -ec 'python -I bin/sd_install.py'",
    "bash -c -e 'python -I bin/sd_install.py'",
    "bash -o pipefail -c 'python -I bin/sd_install.py'",
    "echo 'a;b'; python -I 'bin/sd_install.py'",
    "echo a\\; python -I bin/sd_install.py",
    "echo a\\;b; python -I bin/sd_install.py",
    "echo \"x; python -I bin/sd_install.py\"",
    "x=$(python -I bin/sd_install.py)",
    "echo $(python -I bin/sd_install.py)",
    "x=`python -I bin/sd_install.py`",
    "if python -I bin/sd_install.py; then true; fi",
    "! python -I bin/sd_install.py",
    "{ python -I bin/sd_install.py; }",
    "while python -I bin/sd_install.py; do break; done",
    "cd 'dir with space' && python -I ../bin/sd_install.py",
    "cd \"dir with space\" && python -I ../bin/sd_install.py",
    "pushd sub >/dev/null && python -I ../bin/sd_install.py",
    "cd sub; python -I ../bin/sd_install.py",
    "cd sub && python -I bin/sd_install.py",
    ("sub", "python -I ../bin/sd_install.py"),
    "env -u FOO python -I bin/sd_install.py",
    "env -uFOO python -I bin/sd_install.py",
    "env '-Spython3 -I' bin/sd_install.py",
    "sh -c 'python -I \"$@\"' sh bin/sd_install.py",
    "python -I bin/sd_install.py",
    "python -I bin/sd_install.py 2>&1",
    "&>/dev/null python -I bin/sd_install.py",
    "python -I bin/sd_install.py &",
    "case x in x) python -I bin/sd_install.py;; esac",
    "true # python -I bin/sd_install.py",
    "if true; then python -I bin/sd_install.py; fi",
    "echo python -I bin/sd_install.py",
    "bash --norc -c 'python -I bin/sd_install.py'",
    "bash -x -c 'python -I bin/sd_install.py'",
    "bash +e -c 'python -I bin/sd_install.py'",
    "bin/sd_install.py",
    "python bin/sd_install.py",
    "python3 -I copy/bin/sd_install.py",
    "grep -e python -E bin/sd_install.py",
    "rg python -S bin/sd_install.py",
    "bash -c true 'python -I bin/sd_install.py'",
    "cd sub && python -I ../bin/sd_install.py",
    "git grep -n python -E bin/sd_install.py",
    "echo x > python -I bin/sd_install.py",
    "A=python; echo $A -I bin/sd_install.py",
    "cat <<< 'python -I bin/sd_install.py'",
    "printf '%s\\n' python -I bin/sd_install.py",
    "[ -x python ] || echo python -I bin/sd_install.py",
    "for p in python -I bin/sd_install.py; do echo $p; done",
    "echo a | python -I -c 'import sys' bin/sd_install.py",
    "python -m pytest -I bin/sd_install.py",
    "python-config -I bin/sd_install.py",
    # The review of #933: wrappers, quoting, blocks, the `pushd` stack.
    "{ python -S bin/sd_install.py; }",
    "pushd sub && python -I ../bin/sd_install.py",
    "true # x; python -I bin/sd_install.py",
    "sh <<EOF\npython -I bin/sd_install.py\nEOF",
    "bash -s <<'EOF'\npython -I bin/sd_install.py\nEOF",
    "sh <<< 'python -I bin/sd_install.py'",
    "echo 'python -I bin/sd_install.py' | sh",
    "sh -s",
    "builtin python -I bin/sd_install.py",
    "nohup python -I bin/sd_install.py",
    "nice python -I bin/sd_install.py",
    "exec -a x python -I bin/sd_install.py",
    "case x in y) true;; x) python -I bin/sd_install.py;; esac",
    "case x in (x) python -I bin/sd_install.py;; esac",
    "case x in x) cd sub;; esac; python -I ../bin/sd_install.py",
    "true && ! python -I bin/sd_install.py",
    "false || if python -I bin/sd_install.py; then :; fi",
    "if true; then true && python -I bin/sd_install.py; fi",
    "! ! python -I bin/sd_install.py",
    "time -p -- python -I bin/sd_install.py",
    "time -- python -I bin/sd_install.py",
    "time time python -I bin/sd_install.py",
    "! time -p python -I bin/sd_install.py",
    "time ! python -I bin/sd_install.py",
    "x=$( (python -I bin/sd_install.py) )",
    "echo $((1+2)); cd sub; python -I ../bin/sd_install.py",
    "( (cd sub) ); python -I ../bin/sd_install.py",
    "{ cd sub; }; python -I ../bin/sd_install.py",
    "{ cd sub; } & wait; python -I ../bin/sd_install.py",
    "f() { cd sub; }; python -I ../bin/sd_install.py",
    "f() { python -I bin/sd_install.py; }; f",
    "(pushd sub); python -I bin/sd_install.py",
    "x=$(pushd sub); python -I bin/sd_install.py",
    "python -I \\\nbin/sd_install.py",
    "true && \\\npython -I bin/sd_install.py",
    "cd sub && \\\npython -I ../bin/sd_install.py",
    "true\r\npython -I bin/sd_install.py",
    "python -I bin/sd_install.py\r\n",
    "\tif\tpython\t-I\tbin/sd_install.py;\tthen\t:;\tfi",
    "\"if\" python -I bin/sd_install.py",
    "echo if python -I bin/sd_install.py",
    "cat do; python -I bin/sd_install.py",
    "./do python -I bin/sd_install.py",
    "echo { python -I bin/sd_install.py",
    "time=1 python -I bin/sd_install.py",
    "echo ';' python -I bin/sd_install.py",
    "find . -maxdepth 0 -exec true {} \\; python -I bin/sd_install.py",
    "echo '('; cd sub; python -I ../bin/sd_install.py",
    "(cd sub; echo ')'; python -I ../bin/sd_install.py)",
    "cat >/dev/null <<EOF\npython -I bin/sd_install.py\nEOF",
    "cat >/dev/null <<EOF\nit's\nEOF\npython -I bin/sd_install.py",
    "cat >/dev/null <<EOF\n# x\nEOF\npython -I bin/sd_install.py",
    "echo $'it\\'s'; python -I bin/sd_install.py",
    "cd sub && true & wait; python -I ../bin/sd_install.py",
    "if cd sub; then :; fi | cat; python -I ../bin/sd_install.py",
    "while cd sub; do break; done & wait; python -I ../bin/sd_install.py",
    "{ cd sub; } | cat; python -I ../bin/sd_install.py",
    "a=(x y); python -I bin/sd_install.py",
    "a+=(python -I bin/sd_install.py)",
    "a=( $(echo x) ); python -I bin/sd_install.py",
    "a=(')' x); python -I bin/sd_install.py",
    "f() { local a=(python -I bin/sd_install.py); }; f",
    "declare -a a=(python -I bin/sd_install.py)",
    "a=(sub); cd sub; python -I ../bin/sd_install.py",
    "cd sub; cd -; python -I bin/sd_install.py",
    "cd sub; cd -; python -I ../bin/sd_install.py",
    "cd nonexist; python -I bin/sd_install.py",
    "pushd nonexist; python -I bin/sd_install.py",
    "pushd sub; pushd; python -I bin/sd_install.py",
    "pushd sub; pushd +1; python -I bin/sd_install.py",
    "pushd sub; pushd ../other; popd +1; popd; python -I bin/sd_install.py",
    "pushd sub; pushd ../other; popd +0; python -I ../bin/sd_install.py",
    "pushd -n sub; popd; python -I ../bin/sd_install.py",
    "pushd sub; pushd ../other; popd; popd; python -I bin/sd_install.py",
    "popd; python -I bin/sd_install.py",
    "pushd sub & wait; python -I bin/sd_install.py",
    "pushd sub; cd ..; popd; python -I bin/sd_install.py",
    "pushd sub; (popd); python -I ../bin/sd_install.py",
    "pushd sub; x=`popd`; python -I ../bin/sd_install.py",
    "pushd sub >/dev/null; python -I ../bin/sd_install.py",
    "cd ~; python -I bin/sd_install.py",
    "echo a#b; python -I bin/sd_install.py",
    "x=ab; echo ${#x}; python -I bin/sd_install.py",
    "echo $#; python -I bin/sd_install.py",
    "echo '# x'; python -I bin/sd_install.py",
    "echo \"# it's\"; python -I bin/sd_install.py",
    "echo \\# it; python -I bin/sd_install.py",
    "echo \\# it\\'s; python -I bin/sd_install.py",
    "true |# x\ncat; python -I bin/sd_install.py",
    "# use `x`\npython -I bin/sd_install.py",
    "(# x\npython -I bin/sd_install.py)",
    "true;# x\npython -I bin/sd_install.py",
    "a=#x; python -I bin/sd_install.py",
    "x=1; echo ${x}#y; python -I bin/sd_install.py",
    "true # it's\npython -I bin/sd_install.py",
    "true &>/dev/null; python -I bin/sd_install.py",
    "true >&2; python -I bin/sd_install.py",
    "true &>>log; python -I bin/sd_install.py",
    "cd sub |& cat; python -I ../bin/sd_install.py",
    "env -u X python -I bin/sd_install.py",
    "env -uX python -I bin/sd_install.py",
    "python -XI bin/sd_install.py",
    "python -Wd -I bin/sd_install.py",
    "python -I -- bin/sd_install.py",
    "python -I bin/sd_inst*.py",
    "python -I -c pass bin/sd_install.py",
    "bash -c -- 'python -I bin/sd_install.py'",
    "bash -c \"sh -c 'python -I bin/sd_install.py'\"",
    "x=\"$(python -I bin/sd_install.py)\"",
    "cat <(python -I bin/sd_install.py)",
    "(cd sub; cat <(true); python -I ../bin/sd_install.py)",
    "(cd sub; case x in x) python -I ../bin/sd_install.py;; esac)",
    "function f { python -I bin/sd_install.py; }; f",
    "coproc python -I bin/sd_install.py; wait",
    "select x in a; do python -I bin/sd_install.py; break; done <<< 1",
    "for ((i=0;i<1;i++)); do python -I bin/sd_install.py; done",
    "[[ -e bin/sd_install.py ]] && python -I bin/sd_install.py",
    "p=python; $p -I bin/sd_install.py",
    "eval 'python -I bin/sd_install.py'",
    "echo 'python -I bin/sd_install.py' > s.sh; . ./s.sh",
    # sd:791's first probe: the N-1 to N-4 families of #933's review.
    "pushd sub; pushd ../other; pushd; python -I ../bin/sd_install.py",
    "pushd sub; pushd ../other; pushd +1; python -I bin/sd_install.py",
    "pushd sub; pushd +0; python -I ../bin/sd_install.py",
    "pushd sub; pushd ../other; pushd -0; python -I ../bin/sd_install.py",
    "pushd sub; pushd +9; python -I ../bin/sd_install.py",
    "pushd sub; pushd ../other; popd -0; python -I ../bin/sd_install.py",
    "pushd sub; pushd ../other; popd -n; python -I ../bin/sd_install.py",
    "pushd -n sub; python -I bin/sd_install.py",
    "pushd; python -I bin/sd_install.py",
    "pushd -- sub; python -I ../bin/sd_install.py",
    "pushd sub other; python -I bin/sd_install.py",
    "function f() { python -I bin/sd_install.py; }; f",
    "f() ( python -I bin/sd_install.py ); f",
    "'while' python -I bin/sd_install.py",
    "'cd' sub && python -I ../bin/sd_install.py",
    "cd sub && python -I ../bin/sd_install.py & wait",
    "{ cd sub; python -I ../bin/sd_install.py; }",
    "if true; then cd sub; fi; python -I ../bin/sd_install.py",
    "for f in x; do cd sub; done; python -I ../bin/sd_install.py",
    "for python in x; do true; done; python -I bin/sd_install.py",
    "case x in x) cd sub;; esac | cat; python -I ../bin/sd_install.py",
    "if true; then { cd sub; }; fi; python -I ../bin/sd_install.py",
    "cd sub | true && python -I bin/sd_install.py",
    "echo a\\\nb; python -I bin/sd_install.py",
    "cd sub &&\npython -I ../bin/sd_install.py",
    "echo x |\ncat; python -I bin/sd_install.py",
    "eval python -I bin/sd_install.py",
    "eval echo python -I bin/sd_install.py",
    "time -p python -I bin/sd_install.py",
    "cd -; python -I bin/sd_install.py",
    "cd sub; cd -; cd -; python -I ../bin/sd_install.py",
    "python -I bin/sd_instal?.py",
    "python -I 'bin/sd_inst*.py'",
    "python -I bin/nothing*.py",
    "cd s*b && python -I ../bin/sd_install.py",
    "[ -e x ] || python -I bin/sd_install.py",
    "python -I bin/sd_install.py; echo 'oops",
    "python -I bin/sd_install.py\necho 'oops",
    "echo 'oops\npython -I bin/sd_install.py",
    "case x in esac; python -I bin/sd_install.py",
    "echo x > >(python -I bin/sd_install.py); wait",
    "true >| log; python -I bin/sd_install.py",
    "a=(python -I bin/sd_install.py)",
    "a=(\npython -I bin/sd_install.py\n)",
    "a=(x); python -I bin/sd_install.py",
    "a=( $(python -I bin/sd_install.py) )",
    "x=`pwd`; cd sub; python -I ../bin/sd_install.py",
    "echo \\'; true # it's\npython -I bin/sd_install.py",
    "d=sub; cd $d; python -I ../bin/sd_install.py",
    # sd:791's first probe, continued.
    "true | cd sub; python -I ../bin/sd_install.py",
    "pushd sub; pushd deep; popd +1; python -I ../bin/sd_install.py",
    "pushd sub; pushd deep; popd -n; python -I ../bin/sd_install.py",
    "pushd sub; pushd; python -I ../bin/sd_install.py",
    "pushd -n sub; python -I ../bin/sd_install.py",
    "python -I bin/sd_install.py\necho 'unclosed",
    # review-941: B-1 to B-4 and N-1 to N-6.
    "f() { cd sub; }; f; python -I bin/sd_install.py",
    "f() { cd sub; }; f; python -I ../bin/sd_install.py",
    "{ f() { cd sub; }; }; f; python -I bin/sd_install.py",
    "{ f() { cd sub; }; }; f; python -I ../bin/sd_install.py",
    "function f() { cd sub; }; f; python -I bin/sd_install.py",
    "function f() { cd sub; }; f; python -I ../bin/sd_install.py",
    "function f { cd sub; }; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; python -I bin/sd_install.py",
    "f() { cd sub; }; f; f; python -I ../../bin/sd_install.py",
    "f() { cd sub; }; f python -I bin/sd_install.py; true",
    "f() ( cd sub ); f; python -I bin/sd_install.py",
    "f() { cd sub; }; f | cat; python -I bin/sd_install.py",
    "pushd sub; pushd -n; python -I bin/sd_install.py",
    "pushd sub; pushd -n; python -I ../bin/sd_install.py",
    "echo \\b#c; python -I bin/sd_install.py",
    "echo a\\#b; python -I bin/sd_install.py",
    "pushd sub; pushd deep; popd +1; popd; python -I bin/sd_install.py",
    "pushd sub; pushd deep; popd -n; popd; python -I bin/sd_install.py",
    "pushd sub; pushd deep; popd +1; python -I ../../bin/sd_install.py",
    "pushd sub; pushd deep; popd -n; python -I ../../bin/sd_install.py",
    # review-941, continued: functions and their calls.
    "cd sub; cd sub; python -I ../../bin/sd_install.py",
    "f() { cd sub; }; f; f; python -I ../bin/sd_install.py",
    "f() { cd ..; }; f; f; python -I bin/sd_install.py",
    "f() { cd sub; }; f; f; python -I deep/../../bin/sd_install.py",
    "f() { cd sub; }; g() { cd deep; }; f; g; python -I ../../bin/sd_install.py",
    "f() { cd sub; }; f; f; f; python -I ../bin/sd_install.py",
    # review-941, continued: branches, patterns, failing `cd`.
    "cd sub || cd other; python -I ../bin/sd_install.py",
    "case x in y) cd sub;; *) cd other;; esac; python -I ../bin/sd_install.py",
    "true || python -I bin/sd_install.py",
    "python -I bin/sd_inst*\".py\"",
    "(case x in x) cd sub;;& y) :;; esac; python -I ../bin/sd_install.py)",
    # The first verification of #941 (V-1 to V-4), and calls through other functions.
    "f() { cd sub; }; g() { f; }; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; g() { f; }; f; python -I bin/sd_install.py",
    "function f { cd sub; }; g() { f; }; f; python -I ../bin/sd_install.py",
    "function f { cd sub; }; g() { f; }; f; python -I bin/sd_install.py",
    "function f() { cd sub; }; g() { f; }; f; python -I ../bin/sd_install.py",
    "function f() { cd sub; }; g() { f; }; f; python -I bin/sd_install.py",
    "f() { cd sub; }; g() { echo f; }; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; g() { echo f; }; f; python -I bin/sd_install.py",
    "f() { cd sub; }; g() { f; }; g; python -I ../bin/sd_install.py",
    "f() { cd sub; }; g() { f; }; g; python -I bin/sd_install.py",
    "f() { cd sub; }; g() { f; }; h() { g; }; h; python -I ../bin/sd_install.py",
    "f() { cd sub; }; (f); f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; (f); f; python -I bin/sd_install.py",
    "f() { cd sub; }; f | cat; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; f | cat; f; python -I bin/sd_install.py",
    "f() { cd sub; }; f & wait; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; f & wait; f; python -I bin/sd_install.py",
    "( f() { cd sub; } ); f; python -I bin/sd_install.py",
    "( f() { cd sub; } ); f; python -I ../bin/sd_install.py",
    "f() { cd sub; } | cat; f; python -I bin/sd_install.py",
    "f() { cd sub; } & wait; f; python -I bin/sd_install.py",
    "`f() { cd sub; }`; f; python -I bin/sd_install.py",
    "f() { cd sub; }; x=f; $x; python -I ../bin/sd_install.py",
    "f() { cd sub; }; \"f\"; python -I ../bin/sd_install.py",
    "f() { cd sub; }; \"f\"; python -I bin/sd_install.py",
    "f() { cd sub; }; \\f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; f() { cd other; }; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; f() { cd other; }; f; python -I bin/sd_install.py",
    "g() { f() { cd sub; }; }; g; f; python -I ../bin/sd_install.py",
    "g() { f() { cd sub; }; }; f; python -I bin/sd_install.py",
    "f() { cd sub; }; (f; python -I ../bin/sd_install.py)",
    "f() { cd sub; }; { f; python -I ../bin/sd_install.py; }",
    "f() { cd sub; }; cd sub; f; python -I ../../../bin/sd_install.py",
    "f() { cd sub; }; f x y; python -I ../bin/sd_install.py",
    "f() { cd sub; }; f; (f); python -I ../bin/sd_install.py",
    "f() { python -I bin/sd_install.py; }; true",
    "( f() { python -I bin/sd_install.py; } ); true",
    "f() { cd sub; }; g() { f; f; }; g; python -I ../bin/sd_install.py",
    "f() { cd sub; }; g() { f; f; }; g; python -I bin/sd_install.py",
    "f() { cd sub; }; g() { f; }; g | cat; python -I bin/sd_install.py",
    "f() { cd sub; }; g() { f; }; g & wait; python -I bin/sd_install.py",
    "f() { cd sub; }; g() { f; cd deep; }; g | cat; python -I bin/sd_install.py",
    "f() { cd sub; }; g() { f; cd deep; }; g; g; python -I ../../bin/sd_install.py",
    "echo \\'; python -I bin/sd_install.py # it's",
    # W-1: a second call that really moves again.
    ("sub/deep", "f() { cd ..; }; f; f; python -I bin/sd_install.py"),
    ("sub/deep", "f() { cd ..; }; f; f; python -I ../bin/sd_install.py"),
    "f() { cd ww; }; f; f; python -I ../../bin/sd_install.py",
    "f() { cd ww; }; f; f; python -I ../bin/sd_install.py",
    # The second verification of #941: its 74 shapes.
    "f() { cd sub; }; x=1 f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; x=1 f; python -I bin/sd_install.py",
    "f() { cd sub; }; >/dev/null f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; 2>/dev/null f; python -I bin/sd_install.py",
    "f() { cd sub; }; f; f() { cd deep; }; f; python -I ../../bin/sd_install.py",
    "f() { cd sub; }; f; f() { cd deep; }; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; f; f() { cd ..; }; f; python -I bin/sd_install.py",
    "n() { :; }; n; n; n; n; n; n; n; n; f() { cd sub; }; f; python -I ../bin/sd_install.py",
    "n() { :; }; n; n; n; n; n; n; n; n; f() { cd sub; }; f; python -I bin/sd_install.py",
    "f() { cd sub; }; g() { :; }; g; g; g; g; g; g; g; g; f; python -I bin/sd_install.py",
    "f() { cd sub; }; if f; then python -I ../bin/sd_install.py; fi",
    "f() { cd sub; }; if true; then f; fi; python -I bin/sd_install.py",
    "f() { cd sub; }; while f; do python -I ../bin/sd_install.py; break; done",
    "f() { cd sub; }; case x in x) f;; esac; python -I ../bin/sd_install.py",
    "f() { cd sub; }; f && python -I bin/sd_install.py",
    "f() { cd sub; }; true && f || true; python -I ../bin/sd_install.py",
    "f() { cd sub; }; if true; then f; fi | cat; python -I bin/sd_install.py",
    "f() { pushd sub; }; f; python -I ../bin/sd_install.py",
    "f() { pushd sub; }; f; popd; python -I bin/sd_install.py",
    "f() { popd; }; pushd sub; f; python -I bin/sd_install.py",
    "f() { popd; }; pushd sub; f; python -I ../bin/sd_install.py",
    "f() { pushd sub; }; (f); popd; python -I bin/sd_install.py",
    "f() { cd sub; } | cat; f; python -I ../bin/sd_install.py",
    "x=$(f() { cd sub; }); f; python -I ../bin/sd_install.py",
    "true && ( g() { cd sub; }; g ); python -I bin/sd_install.py",
    "{ f() { cd sub; }; } & wait; f; python -I ../bin/sd_install.py",
    "function f { cd sub; }; f | cat; f; python -I ../bin/sd_install.py",
    "function f { pushd sub; }; f; python -I bin/sd_install.py",
    "f() ( cd sub ); f; python -I ../bin/sd_install.py",
    "f() ( cd sub ); { cd sub; }; python -I ../bin/sd_install.py",
    "f() ( cd sub ); if true; then cd sub; fi; python -I ../bin/sd_install.py",
    "f() ( :; ); g() { cd sub; }; g; python -I ../bin/sd_install.py",
    "f() { cd sub; }; command f; python -I bin/sd_install.py",
    "f() { cd sub; }; command f; python -I ../bin/sd_install.py",
    "f() { builtin cd sub; }; f; python -I ../bin/sd_install.py",
    "cd() { :; }; cd sub; python -I bin/sd_install.py",
    "FUNCNEST=2; f() { cd sub; f; }; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; g() { f; }; h() { g; }; i() { h; }; i; python -I bin/sd_install.py",
    "g() { f() { cd sub; }; f; }; g; python -I ../bin/sd_install.py",
    "g() { f() { cd sub; }; }; g; g; f; python -I bin/sd_install.py",
    "g() { f() { cd sub; }; }; (g); f; python -I bin/sd_install.py",
    "g() { f() { cd sub; }; }; g | cat; f; python -I ../bin/sd_install.py",
    "f; f() { cd sub; }; python -I bin/sd_install.py",
    "g() { f; }; f() { cd sub; }; g; python -I ../bin/sd_install.py",
    "f()\n{\n  cd sub\n}\nf\npython -I ../bin/sd_install.py",
    "f() if true; then cd sub; fi; f; python -I ../bin/sd_install.py",
    "f() while true; do cd sub; break; done; f; python -I ../bin/sd_install.py",
    "f() if true; then cd sub; fi; python -I ../bin/sd_install.py",
    "f() { cd sub; }; unset -f f; f; python -I bin/sd_install.py",
    "f() { return; cd sub; }; f; python -I bin/sd_install.py",
    "f() { cd sub; }; g() { f; cd ..; }; g; f; python -I bin/sd_install.py",
    "f() { cd sub; }; f; cd ..; f; python -I bin/sd_install.py",
    "f() { cd sub; }; echo $(f); f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; echo `f`; python -I bin/sd_install.py",
    "f() { cd sub; }; eval f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; time f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; ! f; python -I bin/sd_install.py",
    "f() { cd sub; }; a=(f); python -I bin/sd_install.py",
    "f() { cd sub; }; for f in f; do f; done; python -I ../bin/sd_install.py",
    "f() { cd sub; }; bash -c f; python -I bin/sd_install.py",
    "f() { cd sub; }; export -f f; bash -c 'f; python -I ../bin/sd_install.py'",
    "f() { cd sub & }; f; python -I bin/sd_install.py",
    "f() { cd sub; } 2>/dev/null; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; f; f | cat; python -I ../bin/sd_install.py",
    "f() { cd sub; }; { f; } | cat; f; python -I ../bin/sd_install.py",
    "f(){ cd sub;}; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; case f in f) python -I ../bin/sd_install.py;; esac",
    "f() { cd sub; }; f && python -I ../bin/sd_install.py & wait",
    "f() { cd sub; }; g() { f; }; g; g; python -I bin/sd_install.py",
    "f() { cd sub; }; g() { f | cat; }; g; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; g() { (f); f; }; g; python -I ../bin/sd_install.py",
    "f() { cd sub; }; g() { f & wait; }; g; python -I bin/sd_install.py",
    "f() { cd sub; }; (f; f() { cd deep; }); f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; f; (f() { cd deep; }; f; python -I ../../bin/sd_install.py)",
    # This round: a call after an assignment or a redirection, a redefinition, the replay budget.
    "f() { cd sub; }; > f; python -I bin/sd_install.py",
    "f() { cd sub; }; echo > f; python -I bin/sd_install.py",
    "f() { cd sub; }; a=1 b=2 f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; x=1 2>&1 f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; x=1 2>&1 f; python -I bin/sd_install.py",
    "f() { cd sub; }; f >/dev/null; python -I ../bin/sd_install.py",
    "f() { cd sub; }; 'x=1' f; python -I bin/sd_install.py",
    "f() { cd sub; }; f; f() { cd sub; }; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; f; f() { cd sub; }; f; python -I ../../bin/sd_install.py",
    "f1() { cd sub; }; f2() { f1; }; f3() { f2; }; f4() { f3; }; f5() { f4; }; f6() { f5; }; f7() { f6; }; f8() { f7; }; f8; python -I ../bin/sd_install.py",
    "f1() { cd sub; }; f2() { f1; }; f3() { f2; }; f4() { f3; }; f5() { f4; }; f6() { f5; }; f7() { f6; }; f8() { f7; }; f8; python -I bin/sd_install.py",
    "f1() { cd sub; }; f2() { f1; }; f3() { f2; }; f4() { f3; }; f5() { f4; }; f6() { f5; }; f7() { f6; }; f8() { f7; }; f9() { f8; }; f9; python -I ../bin/sd_install.py",
    "f1() { cd sub; }; f2() { f1; }; f3() { f2; }; f4() { f3; }; f5() { f4; }; f6() { f5; }; f7() { f6; }; f8() { f7; }; f9() { f8; }; f9; python -I bin/sd_install.py",
    "n() { :; }; " + "n; " * 255 + "f() { cd sub; }; f; python -I ../bin/sd_install.py",
    "n() { :; }; " + "n; " * 256 + "f() { cd sub; }; f; python -I ../bin/sd_install.py",
    "n() { :; }; " + "n; " * 256 + "f() { cd sub; }; f; python -I bin/sd_install.py",
    "f() { cd sub; }; true | f; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; g() { { f; }; }; g; f; python -I ../bin/sd_install.py",
    "f() { cd sub; }; g() { cd sub; }; f; g; python -I ../bin/sd_install.py",
    "f() { cd sub; }; g() { cd sub; }; f; g; python -I ../../bin/sd_install.py",
    # The rows test_coverage_sitecustomize pins as not refused.
    "grep -e python -E bin/sd_install.py; true",
    "(cd sub && true); python -I ../bin/sd_install.py",
    "cd sub | true; python -I ../bin/sd_install.py",
    "cd sub & wait; python -I ../bin/sd_install.py",
    "pushd sub; popd; python -I ../bin/sd_install.py",
    "pushd sub; (pushd other); popd; python -I ../bin/sd_install.py",
    "f() { cd sub; }; f | cat; python -I ../bin/sd_install.py",
    # The rows test_coverage_sitecustomize pins as refused.
    "python3.13 -E bin/sd_install.py",
    "/some/where/python -S bin/sd_install.py",
    "env python -I bin/sd_install.py",
    "bash -ec 'true; FOO=1 python -E bin/sd_install.py' name arg",
    "echo hi | python -S bin/sd_install.py",
    "true\npython -I bin/sd_install.py",
    "sh -c 'python -I bin/sd_install.py'",
    ">log python -I bin/sd_install.py",
    "2> /dev/null FOO=1 python -E bin/sd_install.py",
    "2>&1 python -S bin/sd_install.py",
    "if true; then python -E bin/sd_install.py; fi",
    "if false; then true; elif python -S bin/sd_install.py; then true; fi",
    "if false; then true; else python -I bin/sd_install.py; fi",
    "until python -I bin/sd_install.py; do break; done",
    "for f in x; do python -I bin/sd_install.py; done",
    "time -p python -E bin/sd_install.py",
    "if cd sub; then python -I ../bin/sd_install.py; fi",
    "cd sub 2>/dev/null && python -I ../bin/sd_install.py",
    "cd sub >/dev/null && python -I ../bin/sd_install.py",
    "cd sub &>/dev/null && python -I ../bin/sd_install.py",
    "cd sub > /dev/null 2>&1; python -I ../bin/sd_install.py",
    "# it's here\npython -I bin/sd_install.py",
    "f() { cd sub; }; { { { { { { { { f; }; }; }; }; }; }; }; }; python -I ../bin/sd_install.py",
    "f() { cd sub; }; g() { { f; }; }; g | cat; python -I bin/sd_install.py",
)


def _shape(entry: str | tuple[str, str]) -> tuple[str, str]:
    """A table entry as (the directory under the root it runs in, the line)."""
    return entry if isinstance(entry, tuple) else ("", entry)


def _load(path: pathlib.Path):
    """The check at `path`, imported without starting coverage or adding its hook."""
    spec = importlib.util.spec_from_file_location(f"launch_check_{abs(hash(str(path)))}", path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ):
        for name in ("SD_COVERAGE_PROCESS_START", "COVERAGE_PROCESS_START", "COVERAGE_PROCESS_CONFIG"):
            os.environ.pop(name, None)
        spec.loader.exec_module(module)
    return module


def _bash() -> tuple[str | None, str]:
    """The bash on PATH and its major version, or None and why it cannot be used."""
    bash = shutil.which("bash")
    if bash is None:
        return None, "bash is not on PATH"
    result = subprocess.run([bash, "-c", "echo ${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}"],
                            capture_output=True, text=True, timeout=30, check=False)
    version = result.stdout.strip()
    if not version.split(".")[0].isdigit() or int(version.split(".")[0]) < 4:
        return None, f"{bash} is bash {version or 'of unknown version'}, and the table needs bash 4"
    return bash, version


def _skipped_script(words: list[str]) -> str | None:
    """The script a logged interpreter runs with `-I`, `-E` or `-S`, read as Python reads its options."""
    skipped, position = False, 0
    while position < len(words):
        word = words[position]
        if word == "--":
            position += 1
            break
        if word.startswith("--"):
            position += 2 if word == "--check-hash-based-pycs" else 1
            continue
        if word == "-" or not word.startswith("-"):
            break
        for offset, letter in enumerate(word[1:]):
            if letter in "cm":
                return None
            skipped = skipped or letter in "IES"
            if letter in "WX":
                # `-W` and `-X` take the rest of the word, or the next one.
                position += offset == len(word) - 2
                break
        position += 1
    return words[position] if skipped and position < len(words) else None


def _bash_refuses(bash: str, root: pathlib.Path, shape: tuple[str, str], log: pathlib.Path) -> bool:
    """Whether bash, running the shape, launches the root's installer with site skipped."""
    shims = root.parent.parent / "shims"
    environment = {"PATH": f"{shims}{os.pathsep}{os.environ.get('PATH', '')}",
                   "HOME": os.environ.get("HOME", str(root)), "LC_ALL": "C", "SD_LAUNCH_LOG": str(log)}
    subprocess.run([bash, "-c", shape[1]], cwd=root / shape[0], env=environment,
                   stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=False)
    installer = os.path.realpath(root / "bin/sd_install.py")
    for record in log.read_text(errors="replace").split("\x1e"):
        where, *words = record.split("\x1f")[:-1] or ["", ""]
        script = _skipped_script(words)
        if script is not None and os.path.realpath(os.path.join(where, script)) == installer:
            return True
    return False


def _check_refuses(check, root: pathlib.Path, shape: tuple[str, str]) -> bool:
    """Whether the check refuses `bash -c LINE` launched from the shape's directory."""
    patterns = check._anchored(["bin/sd_install.py"], str(root))

    def measured(filename, cwd):
        return check._matches(filename, patterns, fnmatchcase, cwd)

    argv = ["bash", "-c", shape[1]]
    try:
        check._refuse_unmeasured_launch("subprocess.Popen", (argv[0], argv, str(root / shape[0]), None), measured)
    except RuntimeError:
        return True
    return False


def _decided(bash: str, checks: list, scratch: pathlib.Path, index: int,
             shape: tuple[str, str]) -> tuple[bool, list[bool]]:
    """bash's verdict on one shape, and each check's, in a directory of its own."""
    root = scratch / str(index) / "root"
    for path in LAYOUT:
        (root / path).mkdir(parents=True)
    (root / "bin/sd_install.py").touch()
    (root / "bin/other.py").touch()
    # The checks read the directory first: a shape may write files into it.
    verdicts = [_check_refuses(check, root, shape) for check in checks]
    log = root.parent / "launches"
    log.touch()
    return _bash_refuses(bash, root, shape, log), verdicts


def _baseline_report(shapes: list[tuple[str, str]], results: list[tuple[bool, list[bool]]]) -> str:
    """The four outcomes of the baseline and this check against bash, and what the baseline has over it."""
    outcomes = {"both right": 0, "baseline wrong, this right": 0,
                "baseline right, this wrong": 0, "both wrong": 0}
    regressions = []
    for shape, (truth, (this, baseline)) in zip(shapes, results, strict=True):
        key = {(True, True): "both right", (False, True): "baseline wrong, this right",
               (True, False): "baseline right, this wrong", (False, False): "both wrong"}
        outcome = key[(baseline == truth, this == truth)]
        outcomes[outcome] += 1
        if outcome == "baseline right, this wrong":
            text = repr(shape) if len(repr(shape)) <= 160 else f"{repr(shape)[:90]} ... {repr(shape)[-60:]}"
            regressions.append(f"  {text} bash refuses: {truth}; {LIMITS.get(_entry(shape), 'NOT LISTED')}")
    counts = ", ".join(f"{name} {count}" for name, count in outcomes.items())
    return "\n".join([f"against the baseline: {counts}", *regressions])


def _entry(shape: tuple[str, str]) -> str | tuple[str, str]:
    """A shape as the table writes it."""
    return shape if shape[0] else shape[1]


class LaunchCheckAgainstBash(unittest.TestCase):
    def test_the_table_holds_each_shape_once_and_lists_only_its_own_shapes(self) -> None:
        shapes = [_shape(entry) for entry in SHAPES]
        self.assertEqual(len(shapes), len(set(shapes)), "a shape is in SHAPES twice")
        self.assertEqual(sorted(map(str, set(map(_shape, LIMITS)) - set(shapes))), [],
                         "LIMITS names a shape SHAPES does not hold")
        documented = " ".join((_load(CHECK).__doc__ or "").split())
        self.assertEqual(sorted({reason for reason in LIMITS.values() if reason not in documented}), [],
                         "a reason in LIMITS is not a passage of the sitecustomize docstring")

    def test_the_check_decides_each_shape_as_bash_runs_it_or_names_the_limit(self) -> None:
        bash, version = _bash()
        if bash is None:
            print(f"launch check against bash: SKIPPED, {version}", file=sys.stderr)
            self.skipTest(version)
        checks = [_load(CHECK)]
        baseline = os.environ.get("SD_LAUNCH_CHECK_BASELINE")
        if baseline:
            checks.append(_load(pathlib.Path(baseline)))
        scratch_directory = tempfile.TemporaryDirectory()
        self.addCleanup(scratch_directory.cleanup)
        scratch = pathlib.Path(scratch_directory.name).resolve()
        (scratch / "shims").mkdir()
        for name in SHIM_NAMES:
            (scratch / "shims" / name).write_text(SHIM)
            (scratch / "shims" / name).chmod(0o755)
        shapes = [_shape(entry) for entry in SHAPES]
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(_decided, [bash] * len(shapes), [checks] * len(shapes),
                                    [scratch] * len(shapes), range(len(shapes)), shapes))
        wrong = {_entry(shape) for shape, (truth, verdicts) in zip(shapes, results, strict=True)
                 if verdicts[0] != truth}
        print(f"launch check against bash {version}: {len(shapes)} shapes, {len(shapes) - len(wrong)} "
              f"decided as bash runs them, {len(wrong)} documented limits, "
              f"{time.monotonic() - started:.1f}s", file=sys.stderr)
        if baseline:
            print(_baseline_report(shapes, results), file=sys.stderr)
        self.assertEqual(sorted(map(str, wrong - set(LIMITS))), [],
                         "the check decides these otherwise than bash, and LIMITS does not name them")
        self.assertEqual(sorted(map(str, set(LIMITS) - wrong)), [],
                         "LIMITS names these, and the check now decides them as bash does")
