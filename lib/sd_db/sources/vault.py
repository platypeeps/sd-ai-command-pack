"""What the vault's `item` rows and the registered plugins share: `SOURCE`, the plugin list and the vault root.

The vault import is gone (sd:4627): every plugin keeps its rows in the
database (`store.driver: db`), and the vault holds only one HTML page per base.
Rows the import landed keep `source` `vault`, so `SOURCE` stays the name that
finds them. What remains is how the readers of those rows find the plugins and
the vault root.

**The plugin declares what a row is (sd:1425).** Each manifest's `workflow`
block names the kinds kept as rows, maps every ladder word of each to one of
the six item statuses, and may name the field that holds a due date. The
library asks the installed pack for them through `sd plugin list --json`, and
trusts only what that command has validated: a second validator here would be a
copy of the pack's rules in another repository.

**`fields` drops `NOT_FIELDS`:** `status`, which is `stage`, and `mirror-hash`,
which belonged to the retired note mirror (sd:5133).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .. import pack
from . import MigrationRefused

#: `source` of the rows the vault import landed.
SOURCE = "vault"

#: Where the vault is. `$OBSIDIAN_VAULT`, else a default under `~/Documents`.
DEFAULT_VAULT = "~/Documents/Obsidian Vault"

#: How long `sd plugin list --json` may take. The pack bounds each root's read
#: at five seconds, so this is far past any healthy answer.
LIST_SECONDS = 120

DUE = re.compile(r"\d{4}-\d{2}-\d{2}")

#: Frontmatter keys a row keeps elsewhere: `status` is `stage`, `mirror-hash` was the note mirror's.
NOT_FIELDS = frozenset({"status", "mirror-hash"})


def vault_root(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    return Path(os.path.expanduser(env.get("OBSIDIAN_VAULT") or DEFAULT_VAULT))


def plugin_entries(*, home: Path | str, environ: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """The registered plugins, as the installed pack's `sd plugin list --json` reports them.

    Run with this interpreter, as the design says: the pack's `bin/sd` needs
    nothing the library's own interpreter lacks.
    """
    env = dict(os.environ if environ is None else environ)
    found = pack.installed(home=home, environ=env)
    if found.checkout is None:
        raise MigrationRefused(f"the plugins are read through the pack, and {found.why}")
    command = found.checkout / "bin" / "sd"
    if not command.is_file():
        raise MigrationRefused(f"the plugins are read through the pack, and {command} does not exist")
    try:
        done = subprocess.run([sys.executable, str(command), "plugin", "list", "--json"],
                              capture_output=True, text=True, env=env, timeout=LIST_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        raise MigrationRefused(f"`{command} plugin list --json` did not answer in {LIST_SECONDS}s") from None
    if done.returncode != 0:
        first = (done.stderr.strip().splitlines() or ["no stderr"])[0]
        raise MigrationRefused(f"`{command} plugin list --json` exited {done.returncode}: {first}")
    try:
        entries = json.loads(done.stdout)
    except ValueError:
        entries = None
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise MigrationRefused(f"`{command} plugin list --json` printed what is not JSON entries")
    return entries


def store_root(store: dict[str, Any], prefix: str, environ: dict[str, str] | None = None) -> Path:
    """The folder a plugin's `store.root` names: `$OBSIDIAN_VAULT` through `vault_root`, else its variable."""
    variable = str(store["root"])[1:]
    if variable == "OBSIDIAN_VAULT":
        return vault_root(environ)
    env = os.environ if environ is None else environ
    if env.get(variable):
        return Path(os.path.expanduser(env[variable]))
    raise MigrationRefused(f"plugin {prefix} keeps its notes under ${variable}, which is not set")
