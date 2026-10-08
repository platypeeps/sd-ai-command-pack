"""Every test run gets a temp dir of its own, inside the one it was started with (sd:3032).

A gate start reaps day-old leftovers from the temp dir, so a suite that starts a gate outside the gate reaped the
operator's real `$TMPDIR`, and the reaper's stderr line broke `test_rule_registry` leg d's `-v` verdicts. Set here,
`TMPDIR` reaches every module this package loads and every child they start; a child that imports the package
nests its own. A killed run leaves its folder behind; `LEFT_BEHIND` in `bin/sd_gate_cache.py` names the prefix.
"""

import atexit
import os
import shutil
import tempfile

os.environ["TMPDIR"] = tempfile.mkdtemp(prefix="sd-tests-")
tempfile.tempdir = None
atexit.register(shutil.rmtree, os.environ["TMPDIR"], ignore_errors=True)
