"""The library's own tests. `make test` runs each module as a shard (sd:3323).

One module: `python -m unittest tests.sd_db.test_cli` from the checkout.
"""

import os
import sys
import tempfile
from pathlib import Path

# A run with no destination writes to the USB disk (`sd_db.backup.DEFAULT_ROOT`).
# Relative, this root lands under each test's own home instead; assigned, not
# defaulted, so an operator's exported value never reaches a test either.
os.environ["SD_DB_BACKUP_ROOT"] = "Documents/sd-backups"

# A base row write renders the vault mirror under `$OBSIDIAN_VAULT` (sd:3976).
# Assigned to a folder that does not exist, so a test that names no vault of
# its own refuses to render rather than writing into the operator's vault.
os.environ["OBSIDIAN_VAULT"] = os.path.join(tempfile.gettempdir(), "sd-db-tests-name-their-own-vault")

# The suite tests this checkout's `lib/`, never a copy `make setup` installed
# into the virtualenv. On `PYTHONPATH` too, for the children it starts.
LIB = str(Path(__file__).resolve().parents[2] / "lib")
sys.path.insert(0, LIB)
os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, (LIB, os.environ.get("PYTHONPATH"))))
