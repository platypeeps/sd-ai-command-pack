"""The dashboard's own tests (sd:5987).

The dashboard runs and reads tools of the system checkout (`SYSTEM_TOOLS_ROOT`, else `~/repos/system`). Here that is
`fake_system`, one small fake per tool, set once before any test runs, so the suite passes on a machine with no system
checkout and never runs a real one (sd:6044). The system checkout tests its own tools and documents.
"""

import os
from pathlib import Path

os.environ["SYSTEM_TOOLS_ROOT"] = str(Path(__file__).resolve().parent / "fake_system")
