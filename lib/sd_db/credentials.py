"""Credential presence and expiry, for Health's Credentials area (sd:2203).

`sd-db credentials` runs nightly (`local-cron-jobs/examples/
credentials-nightly.job`) in the environment cron gives a job, which has
sourced `~/.config/shell/env.sh`. It writes one `heartbeat` state row under
`HEARTBEAT_KEY`; the dashboard reads the latest and calls nothing (the
operator's ruling of 2026-10-03: no per-request GitHub call or env.sh read).

sd:6722 adds the logins that time out: each Google account workspace-mcp
holds (a refresh grant), each AWS profile that signs in (`aws sts
get-caller-identity`), StrongDM (`sdm status`) and Claude (`claude auth
status`). None can renew itself: each needs a browser consent, so a probe
that can be signed in names its `signin` -- what `signin()` would start, read
again from disk when the operator presses Sign in. `check(only=...)` runs
one family again and keeps the rest of the last heartbeat.

**A value never leaves its probe.** A token is read from the environment,
put in one request header, and dropped. Nothing here writes, prints, logs or
hashes it: the row holds presence, what a status code means, an expiry date,
MCP server names and states, and reasons written here -- never a response
body, a tool's output, or an error's own words.
"""

from __future__ import annotations

import configparser
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .writes import record_state

HEARTBEAT_KEY = "credentials:nightly"
#: Seconds per probe; `claude mcp list` starts every server it checks.
TIMEOUT = 20
MCP_TIMEOUT = 120
GITHUB_USER = "https://api.github.com/user"
#: `claude mcp list`: `<name>: <command or url> - ✓ Connected`. The target is dropped.
_MCP_LINE = re.compile(r"^(?P<name>\S.*?): .* - (?P<mark>[✓✗!⚠])\s*(?P<text>.*)$")
_MCP_STATES = {"✓": "connected", "✗": "failed"}


class _NoRedirect(HTTPRedirectHandler):
    """Follows no redirect: urllib would resend the Authorization header to wherever a 3xx points."""

    def redirect_request(self, *args, **kwargs):
        return None


def _get(url: str, token: str) -> tuple[int, dict[str, str]]:
    """The status and lower-cased headers of a GET carrying `token`; never the body. A redirect is its 3xx status."""
    request = Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "sd-db-credentials"})
    try:
        with build_opener(_NoRedirect).open(request, timeout=TIMEOUT) as reply:  # nosec B310 - fixed or operator-set origin
            return reply.status, {key.lower(): value for key, value in reply.headers.items()}
    except HTTPError as error:
        return error.code, {}


def _post(url: str, form: dict[str, str]) -> int:
    """The status of a form POST; never the body, and no redirect is followed."""
    request = Request(url, data=urlencode(form).encode(), headers={"User-Agent": "sd-db-credentials"})
    try:
        with build_opener(_NoRedirect).open(request, timeout=TIMEOUT) as reply:  # nosec B310 - the token store's own token_uri
            return reply.status
    except HTTPError as error:
        return error.code


def _run(argv: list[str], timeout: int) -> tuple[int, str]:
    """Exit code and stdout; stderr is dropped unread, since `gh` names its token source there."""
    done = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True, timeout=timeout, check=False)
    return done.returncode, done.stdout


def _expiry(value: str | None) -> str | None:
    """GitHub's `2026-12-01 00:00:00 UTC` as ISO UTC, or None."""
    if not value:
        return None
    try:
        moment = datetime.strptime(value.strip().replace(" UTC", " +0000"), "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return None
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _token_probe(probe: dict[str, Any], token: str | None, url: str | None, get) -> dict[str, Any]:
    """`present`, then `valid` from one GET: True on 200, False on 401, else a reason.

    Both endpoints answer 401 to a bad token. A 403 is a rate limit or a block, so it is unknown, not rejected.
    """
    probe["present"] = bool(token)
    if not token or not url:
        return probe
    try:
        status, headers = get(url, token)
    except (OSError, ValueError) as error:
        probe["reason"] = f"not reached: {type(error).__name__}"
        return probe
    probe["valid"] = True if status == 200 else False if status == 401 else None
    if probe["valid"] is None:
        probe["reason"] = f"answered HTTP {status}"
    probe["headers"] = headers
    return probe


def github_pat(env, get) -> dict[str, Any]:
    probe = _token_probe({"id": "github_pat", "name": "GitHub PAT (GITHUB_PERSONAL_ACCESS_TOKEN)"},
                         env.get("GITHUB_PERSONAL_ACCESS_TOKEN"), GITHUB_USER, get)
    headers = probe.pop("headers", {})
    if probe.get("valid"):
        raw = headers.get("github-authentication-token-expiration")
        probe["expires"] = _expiry(raw)
        if raw and probe["expires"] is None:
            probe["reason"] = "expiry header not understood"
    return probe


def ha_token(env, get) -> dict[str, Any]:
    url = (env.get("HA_URL") or "").rstrip("/")
    probe = _token_probe({"id": "ha_token", "name": "Home Assistant token (HA_TOKEN)"},
                         env.get("HA_TOKEN"), f"{url}/api/" if url else None, get)
    probe.pop("headers", None)
    if probe["present"] and not url:
        probe["reason"] = "HA_URL unset, so the token was not tested"
    return probe


def gh_cli(run) -> dict[str, Any]:
    probe: dict[str, Any] = {"id": "gh", "name": "gh CLI sign-in (gh auth status)"}
    try:
        code, _ = run(["gh", "auth", "status", "--hostname", "github.com"], TIMEOUT)
    except (OSError, subprocess.SubprocessError) as error:
        probe["reason"] = f"gh auth status did not run: {type(error).__name__}"
        return probe
    probe["signed_in"] = code == 0
    return probe


def mcp_servers(run) -> dict[str, Any]:
    probe: dict[str, Any] = {"id": "mcp", "name": "MCP servers (claude mcp list)"}
    try:
        code, out = run(["claude", "mcp", "list"], MCP_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as error:
        probe["reason"] = f"claude mcp list did not run: {type(error).__name__}"
        return probe
    servers = []
    for line in out.splitlines():
        match = _MCP_LINE.match(line.strip())
        if match:
            text = match["text"].lower()
            state = _MCP_STATES.get(match["mark"]) or ("needs_auth" if "auth" in text else "other")
            servers.append({"name": match["name"], "status": state})
    if code != 0 or not servers:
        probe["reason"] = f"claude mcp list exited {code}" if code else "claude mcp list named no server"
        return probe
    probe["servers"] = servers
    return probe


def _home(env) -> Path | None:
    return Path(env["HOME"]) if env.get("HOME") else None


def _google_files(env) -> list[Path]:
    """workspace-mcp's token files, one per account, in its own folder (`GOOGLE_MCP_CREDENTIALS_DIR` moves it)."""
    home = _home(env)
    folder = Path(env["GOOGLE_MCP_CREDENTIALS_DIR"]) if env.get("GOOGLE_MCP_CREDENTIALS_DIR") else \
        home / ".google_workspace_mcp" / "credentials" if home else None
    return sorted(folder.glob("*@*.json")) if folder is not None and folder.is_dir() else []


def google(env, post) -> list[dict[str, Any]]:
    """One probe per account in workspace-mcp's token store: a refresh grant is accepted (200) or refused (400, 401).

    The access token's own expiry is an hour and says nothing; the refresh token's is not in the file (Google drops it
    after 7 days while the OAuth app is in Testing), so the grant is the only answer."""
    probes = []
    for path in _google_files(env):
        account = path.stem
        probe: dict[str, Any] = {"id": f"google:{account}", "name": f"Google login ({account})",
                                 "signin": f"workspace-mcp start_google_auth for {account}"}
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stored = None
        fields = ("client_id", "client_secret", "refresh_token", "token_uri")
        if not isinstance(stored, dict) or any(not isinstance(stored.get(key, ""), str) for key in fields):
            probes.append({**probe, "reason": "token file unreadable"})
            continue
        form = {key: stored.get(key) for key in fields[:3]}
        probe["present"] = bool(all(form.values()) and stored.get("token_uri"))
        if probe["present"]:
            try:
                status = post(stored["token_uri"], {**form, "grant_type": "refresh_token"})
            except (OSError, ValueError) as error:
                probe["reason"] = f"not reached: {type(error).__name__}"
            else:
                probe["valid"] = True if status == 200 else False if status in (400, 401) else None
                if probe["valid"] is None:
                    probe["reason"] = f"answered HTTP {status}"
        probes.append(probe)
    return probes


def aws_profiles(env) -> dict[str, str]:
    """Each profile in `~/.aws/config` that signs in, and the line that signs it in."""
    home = _home(env)
    path = Path(env["AWS_CONFIG_FILE"]) if env.get("AWS_CONFIG_FILE") else home / ".aws" / "config" if home else None
    config = configparser.ConfigParser(interpolation=None)
    try:
        if path is None or not config.read(path, encoding="utf-8"):
            return {}
    except (configparser.Error, OSError):
        return {}
    found = {}
    for section in config.sections():
        name = "default" if section == "default" else section.removeprefix("profile ").strip()
        if section != "default" and not section.startswith("profile "):
            continue
        keys = config[section]
        if "login_session" in keys:
            found[name] = f"aws login --profile {name}"
        elif "sso_session" in keys or "sso_start_url" in keys:
            found[name] = f"aws sso login --profile {name}"
    return found


def aws(env, run) -> list[dict[str, Any]]:
    probes = []
    for name, line in aws_profiles(env).items():
        probe: dict[str, Any] = {"id": f"aws:{name}", "name": f"AWS profile ({name})", "signin": line}
        probes.append(_signed_in(probe, run, ["aws", "sts", "get-caller-identity", "--profile", name]))
    return probes


def _signed_in(probe: dict[str, Any], run, argv: list[str], *, out_ok=None, signed_out=None) -> dict[str, Any]:
    """`signed_in` from a status command's exit (and `out_ok(stdout)` when given); `signed_out` names an exit that means out."""
    try:
        code, out = run(argv, TIMEOUT)
    except (OSError, subprocess.SubprocessError) as error:
        probe["reason"] = f"{' '.join(argv[:3])} did not run: {type(error).__name__}"
        return probe
    if signed_out is not None and code not in (0, signed_out):
        probe["reason"] = f"{' '.join(argv[:2])} exited {code}"
        return probe
    probe["signed_in"] = code == 0 and (out_ok is None or out_ok(out))
    return probe


def _claude_logged_in(out: str) -> bool:
    try:
        return json.loads(out).get("loggedIn") is True
    except (ValueError, AttributeError):
        return False


def sdm(run) -> list[dict[str, Any]]:
    # `sdm status` exits 9 when signed out (sdm-login); any other failure is not an answer.
    return [_signed_in({"id": "sdm", "name": "StrongDM login (sdm status)", "signin": "sdm-login"}, run,
                       ["sdm", "status"], signed_out=9)]


def claude(run) -> list[dict[str, Any]]:
    return [_signed_in({"id": "claude", "name": "Claude login (claude auth status)", "signin": "claude auth login"}, run,
                       ["claude", "auth", "status"], out_ok=_claude_logged_in)]


#: Each probe family, by the part of its probes' ids before any `:`, in the heartbeat's order.
FAMILIES = ("github_pat", "gh", "ha_token", "mcp", "google", "aws", "sdm", "claude")


def _families(env, get, run, post) -> dict[str, Any]:
    """The probe of each of `FAMILIES`."""
    return {"github_pat": lambda: [github_pat(env, get)], "gh": lambda: [gh_cli(run)],
            "ha_token": lambda: [ha_token(env, get)], "mcp": lambda: [mcp_servers(run)],
            "google": lambda: google(env, post), "aws": lambda: aws(env, run),
            "sdm": lambda: sdm(run), "claude": lambda: claude(run)}


def check(connection, *, env, get=None, run=None, post=None, now: str | None = None,
          only: str | None = None) -> dict[str, Any]:
    """Run every probe, or `only` the family of one probe id, and record the heartbeat; the body it wrote.

    With `only`, the last heartbeat's other probes are kept as they were. `get`, `run` and `post` default to
    `_get`, `_run` and `_post`, looked up at call time so a test can replace them."""
    get, run, post = get or _get, run or _run, post or _post
    families = _families(env, get, run, post)
    if only is None:
        body = {"probes": [probe for make in families.values() for probe in make()]}
    else:
        family = only.split(":")[0]
        if family not in families:
            raise ValueError(f"{only} is not a credential probe")
        found = read(connection)
        kept = found[1]["probes"] if found else []
        mine = lambda probe: isinstance(probe, dict) and str(probe.get("id", "")).split(":")[0] == family  # noqa: E731
        at = next((index for index, probe in enumerate(kept) if mine(probe)), len(kept))
        others = [probe for probe in kept if not mine(probe)]
        body = {"probes": others[:at] + families[family]() + others[at:]}
    stamp = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record_state(connection, "heartbeat", key=HEARTBEAT_KEY, timestamp=stamp, body=body)
    return body


def signin(probe_id: str, env) -> str | None:
    """What Sign in starts for one probe, read from disk now; None when that probe cannot be signed in here.

    A shell login is typed as `! <line>` into a claude session, so the browser consent and the result show in its pane;
    Google's consent URL comes from workspace-mcp's own tool."""
    family, _, name = probe_id.partition(":")
    if family == "google":
        if any(path.stem == name for path in _google_files(env)):
            return (f"Sign workspace-mcp in to Google again for {name}: call its start_google_auth tool with "
                    f"user_google_email={name}, give me the URL, and check the login when I have consented.")
        return None
    line = aws_profiles(env).get(name) if family == "aws" else \
        {"sdm": "sdm-login", "claude": "claude auth login"}.get(family) if not name else None
    return f"! {line}" if line else None


def read(connection) -> tuple[str, dict[str, Any]] | None:
    """The latest heartbeat as `(timestamp, body)`, or None; a body with no probe list is a ValueError."""
    row = connection.execute("SELECT timestamp, body FROM state WHERE kind = 'heartbeat' AND key = ? "
                             "ORDER BY id DESC LIMIT 1", (HEARTBEAT_KEY,)).fetchone()
    if row is None:
        return None
    body = json.loads(row["body"] or "{}")
    if not isinstance(body, dict) or not isinstance(body.get("probes"), list):
        raise ValueError("the credentials heartbeat has no probe list")
    return row["timestamp"], body


def describe(probe: dict[str, Any]) -> str:
    """One line per probe for the verb's output: facts, no value."""
    facts = [f"{key} {probe[key]}" for key in ("present", "valid", "signed_in", "expires") if key in probe]
    if "servers" in probe:
        facts.append(f"{sum(s['status'] == 'connected' for s in probe['servers'])} of "
                     f"{len(probe['servers'])} servers connected")
    if probe.get("reason"):
        facts.append(probe["reason"])
    return f"{probe['id']}: {', '.join(facts) or 'nothing read'}"
