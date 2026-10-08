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
import tempfile

os.environ["TMPDIR"] = tempfile.mkdtemp(prefix=f"sd-tests-{os.getpid()}-")
tempfile.tempdir = None
atexit.register(shutil.rmtree, os.environ["TMPDIR"], ignore_errors=True)
