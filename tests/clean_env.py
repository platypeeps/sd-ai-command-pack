"""One clean environment for a test that starts a child process.

Two modules each kept their own copy: `test_commit_msg_hook` dropped `GIT_*`,
`test_changed_files_fast_path` dropped the runner and coverage variables. A
child that inherits `GIT_DIR`, the operator's global git config or `$HOME`
reads the live checkout instead of its fixture, so the helper is one and every
test that needs it imports it.
"""

from __future__ import annotations

import functools
import os
import tempfile

#: Variables that steer a run under test; each is set by a gate, a CI runner or `make`,
#: or, for `SD_AGENT_SESSION`, by `bin/sd-session-beat` in a teammate's Bash call.
DROPPED = {"SD_SKIP_HOOKS", "SD_COVERAGE_PROCESS_START", "PYTHONPATH", "CI", "GITHUB_ACTIONS",
           "TEST_CHANGED_FILES", "CHANGED", "MAKEFLAGS", "MFLAGS", "MAKELEVEL", "SD_AGENT_SESSION"}

#: Git reads no global or system config under test (sd:6386): a satellite's global `fetch.prune=true` failed a
#: fixture's fetch. `tests/__init__.py` sets these for the whole test process, so a test that commits gives git
#: its identity by env or in the fixture's local config.
GIT_ISOLATION = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


@functools.cache
def home() -> str:
    """A folder for `HOME` and `XDG_CONFIG_HOME`; `tests/__init__.py` removes its parent at exit."""

    return tempfile.mkdtemp(prefix="clean-home-")


def clean_environment(**extra: str) -> dict[str, str]:
    """This process's environment without anything that would steer the run under test."""

    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("GIT_", "COVERAGE_", "SD_COVERAGE_")) and key not in DROPPED}
    environment.update({**GIT_ISOLATION, "HOME": home(), "XDG_CONFIG_HOME": home(),
                        "TEST_WORKERS": "4", "PYTHONDONTWRITEBYTECODE": "1", **extra})
    return environment
