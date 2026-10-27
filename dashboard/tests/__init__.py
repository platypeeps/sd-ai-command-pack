"""The dashboard's own tests (sd:5987).

The dashboard runs and reads tools of the system checkout (`SYSTEM_TOOLS_ROOT`, else `~/repos/system`). Here that is
`fake_system`, one small fake per tool, set once before any test runs, so the suite passes on a machine with no system
checkout and never runs a real one (sd:6044). The system checkout tests its own tools and documents.

Git reads no global or system config here (sd:6386), the variables `tests/clean_env.py` names as `GIT_ISOLATION`. They
are written out, not imported: `dashboard.sh test` loads this package as `tests`, where that module does not exist.

`HOME` and the XDG roots point into a temp folder (sd:6403): the database and `hub.json` resolve under `$HOME`, and
a test that opened the default database read the live one, on a satellite the hub's over the tailnet.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

os.environ["SYSTEM_TOOLS_ROOT"] = str(Path(__file__).resolve().parent / "fake_system")
os.environ.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})

_home = tempfile.mkdtemp(prefix=f"sd-dashboard-tests-{os.getpid()}-")
atexit.register(shutil.rmtree, _home, ignore_errors=True)
for _name, _relative in (("HOME", "home"), ("XDG_CONFIG_HOME", "home/.config"),
                         ("XDG_DATA_HOME", "home/.local/share"), ("XDG_STATE_HOME", "home/.local/state")):
    os.environ[_name] = os.path.join(_home, _relative)
    os.makedirs(os.environ[_name], exist_ok=True)
