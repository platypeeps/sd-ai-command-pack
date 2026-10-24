"""The dashboard's own tests (sd:5987).

The dashboard runs and reads tools of the system checkout (`SYSTEM_TOOLS_ROOT`,
else `~/repos/system`). Many tests point `HOME` at a temporary folder, which
would move that default with it, so it is fixed here once, before any test runs.
"""

import os
from pathlib import Path

os.environ.setdefault("SYSTEM_TOOLS_ROOT", str(Path.home() / "repos/system"))
