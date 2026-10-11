"""The library's own tests. `make test` runs each module as a shard (sd:3323).

One module: `python -m unittest tests.sd_db.test_cli` from the checkout.
"""

import os
import sys
from pathlib import Path

# A run with no destination writes to the USB disk (`sd_db.backup.DEFAULT_ROOT`).
# Relative, this root lands under each test's own home instead; assigned, not
# defaulted, so an operator's exported value never reaches a test either.
os.environ["SD_DB_BACKUP_ROOT"] = "Documents/sd-backups"

# The suite tests this checkout's `lib/`, never a copy `make setup` installed
# into the virtualenv. On `PYTHONPATH` too, for the children it starts.
LIB = str(Path(__file__).resolve().parents[2] / "lib")
sys.path.insert(0, LIB)
os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, (LIB, os.environ.get("PYTHONPATH"))))
