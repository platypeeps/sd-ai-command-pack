"""Every test run gets a temp dir of its own, inside the one it was started with (sd:3032).

A gate start reaps day-old leftovers from the temp dir, so a suite that starts a gate outside the gate reaped the
operator's real `$TMPDIR`, and the reaper's stderr line broke `test_rule_registry` leg d's `-v` verdicts. Set here,
`TMPDIR` reaches every module this package loads and every child they start; a child that imports the package
nests its own. A killed run leaves its folder behind; its name holds the run's pid, so `OWNED` in `bin/sd_gate_cache.py`
removes it once that pid is gone, never while the run lives.
"""

import atexit
import os
import shutil
import sys
import tempfile

os.environ["TMPDIR"] = tempfile.mkdtemp(prefix=f"sd-tests-{os.getpid()}-")
tempfile.tempdir = None
atexit.register(shutil.rmtree, os.environ["TMPDIR"], ignore_errors=True)

# `sd_db` is this checkout's `lib/` and nothing is installed (sd:3280). On the path here and in
# `PYTHONPATH`, so a module that imports it at the top, and a child's `sitecustomize` shim, read the
# commit under test; `bin/` entrypoints put `lib/` first themselves.
LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)
if LIB not in os.environ.get("PYTHONPATH", "").split(os.pathsep):
    os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, (LIB, os.environ.get("PYTHONPATH"))))
