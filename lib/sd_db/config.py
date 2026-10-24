"""Where this machine's private config lives.

The installed twin of the checkout's `lib/system_tools_config.py`: an
installed package cannot import `lib/`, so it carries the same resolution
rule here. Private, per-machine values live in

    ${SYSTEM_TOOLS_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/system}/<tool>/

one subfolder per tool, named after the folder minus `local-`
(`repo-sync`, `cron-jobs`). The repository keeps only the `.example` files.

The dashboard reads its config here since it moved into the pack (sd:5987),
so `shared`, `label_prefix`, `obsidian_vault` and `setting` are here as the
checkout's twin has them, and `system_checkout` names that checkout.
"""

from __future__ import annotations

import os
import re
import socket
from collections.abc import Mapping
from pathlib import Path


def root(environ: dict[str, str] | None = None) -> Path:
    """The config root. It may not exist."""
    env = os.environ if environ is None else environ
    named = env.get("SYSTEM_TOOLS_CONFIG")
    if named:
        return Path(os.path.expanduser(named))
    base = env.get("XDG_CONFIG_HOME") or os.path.join(env.get("HOME") or os.path.expanduser("~"), ".config")
    return Path(os.path.expanduser(base)) / "system"


def system_checkout(environ: dict[str, str] | None = None) -> Path:
    """The system checkout, which holds the machine tools (`local-cron-jobs`
    and the rest): `$SYSTEM_TOOLS_ROOT`, else `~/repos/system`, as
    `operations.Cron` reads it. It may not exist."""
    env = os.environ if environ is None else environ
    named = env.get("SYSTEM_TOOLS_ROOT") or os.path.join(env.get("HOME") or os.path.expanduser("~"), "repos/system")
    return Path(os.path.expanduser(named))


def shared(name: str, environ: dict[str, str] | None = None) -> str:
    """A name every tool shares, kept once in <config>/shared.env (sd:3990).

    `st_shared` in config.sh. A variable that is set wins, an empty one too;
    else the file; else `""`. A tool's own .env still overrides the file where
    `st_source_env` loads it into the environment.
    """
    env = os.environ if environ is None else environ
    if name in env:
        return env[name]
    return _read_env_file(root(environ) / "shared.env", env).get(name, "")


def label_prefix(environ: dict[str, str] | None = None) -> str:
    """The launchd label prefix of every job and agent; `st_label_prefix` in config.sh."""
    return shared("SYSTEM_TOOLS_LABEL_PREFIX", environ) or "local.system-tools"


def obsidian_vault(environ: dict[str, str] | None = None) -> Path:
    """The Obsidian vault of every tool that reads one; `st_obsidian_vault` in config.sh."""
    env = os.environ if environ is None else environ
    home = env.get("HOME") or os.path.expanduser("~")
    named = shared("OBSIDIAN_VAULT", environ) or "~/Documents/Obsidian Vault"
    return Path(home + named[1:] if named == "~" or named.startswith("~/") else named)


def config_dir(tool: str, environ: dict[str, str] | None = None) -> Path:
    """The tool's config directory. It may not exist."""
    return root(environ) / tool


def missing(what: str, tool: str, file: str, folder: str | None = None,
            environ: dict[str, str] | None = None) -> str:
    """The standard remedy for a missing value or file, as one message."""
    folder = folder or f"local-{tool}"
    return (f"{what} is not set. Export it, or copy {folder}/{file}.example to "
            f"{config_dir(tool, environ) / file} and fill it in.")


_HOME = re.compile(r"\$\{HOME\}|\$HOME(?![A-Za-z0-9_])")


def read_env(tool: str, environ: dict[str, str] | None = None) -> dict[str, str]:
    """`KEY=value` lines from <config>/<tool>/.env; `{}` when it is absent.

    Blank lines, comments and an `export ` prefix are allowed; one layer of
    matching quotes is removed. `$HOME`, `${HOME}` and a leading `~/` expand
    as they do when `st_source_env` sources the file, except inside single
    quotes; no other variable expands (sd:1868).
    """
    env = os.environ if environ is None else environ
    return _read_env_file(config_dir(tool, environ) / ".env", env)


def _read_env_file(path: Path, env: Mapping[str, str]) -> dict[str, str]:
    home = env.get("HOME") or os.path.expanduser("~")
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep or not key.strip().isidentifier():
            continue
        value = value.strip()
        quote = value[0] if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"" else ""
        if quote:
            value = value[1:-1]
        if quote != "'":
            value = _HOME.sub(lambda _: home, value)
            if not quote and (value == "~" or value.startswith("~/")):
                value = home + value[1:]
        values[key.strip()] = value
    return values


def setting(name: str, saved: dict[str, str], environ: dict[str, str] | None = None) -> str | None:
    """`name` as `st_source_env` leaves it: exported, an empty value too, else
    from `saved` (a `read_env` result); None when neither has it (sd:3964)."""
    env = os.environ if environ is None else environ
    return env[name] if name in env else saved.get(name)


def cron_job_dirs(environ: dict[str, str] | None = None) -> list[Path]:
    """Where `cron-jobs.sh` finds a job file, in its lookup order.

    Each `CRON_JOBS_EXTRA_DIRS` entry (colon-separated) first, then this
    host's `<config>/cron-jobs/jobs/<host>`, then the shared
    `<config>/cron-jobs/jobs`; the first directory holding `<job>.job` defines
    it. `<host>` is `CRON_JOBS_HOST`, else the short host name, lower-cased;
    other hosts' folders are never listed. Both variables come from the
    environment, an exported empty value too, else from
    `<config>/cron-jobs/.env`, as `st_source_env` leaves them (sd:3970).
    Change this, its twin in the checkout's `lib/system_tools_config.py` and `job_dirs` in
    `local-cron-jobs/cron-jobs.sh` together.
    """
    env = os.environ if environ is None else environ
    saved = read_env("cron-jobs", env)
    def setting(name: str) -> str | None:
        return env[name] if name in env else saved.get(name)

    extra = setting("CRON_JOBS_EXTRA_DIRS") or ""
    host = (setting("CRON_JOBS_HOST") or socket.gethostname().split(".")[0]).lower()
    jobs = config_dir("cron-jobs", env) / "jobs"
    return ([Path(os.path.expanduser(d)) for d in extra.split(":") if d]
            + ([jobs / host] if host else []) + [jobs])
