"""A fake of the system checkout's `herdr_wrap.py` for the dashboard's tests (sd:6044).

`active_sessions` reads `session_name` and `herdr_env`; `herdr.sh launch` runs `launch`: a workspace at the
directory, claude started in its root pane, then the prompt, each through the `herdr` on PATH.
"""

import json
import os
import shutil
import subprocess
import sys


class Fail(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def session_name():
    return os.environ.get("HERDR_SESSION") or "sd"


def herdr_env(session):
    env = dict(os.environ, HERDR_SESSION=session)
    env.pop("HERDR_SOCKET_PATH", None)
    return env


def herdr(session, *args):
    done = subprocess.run(["herdr", *args], env=herdr_env(session), capture_output=True, text=True, check=False)
    return done.returncode, done.stdout, done.stderr


def herdr_json(session, *args):
    code, out, err = herdr(session, *args)
    for stream in (out, err):
        try:
            return json.loads(stream)
        except ValueError:
            continue
    raise Fail(f"herdr {' '.join(args)}: exit {code}, no JSON answer")


def launch(session, directory, label, prompt):
    if shutil.which("herdr") is None:
        raise Fail("herdr is not installed; install it, then run herdr.sh start", 3)
    listed = herdr_json(session, "session", "list", "--json").get("sessions", [])
    if not any(entry.get("name") == session and entry.get("running") for entry in listed):
        raise Fail(f"session {session} is not running; run herdr.sh start first")
    created = herdr_json(session, "workspace", "create", "--cwd", directory, "--label", label, "--no-focus")
    pane = None if created.get("error") else created.get("result", {}).get("root_pane", {}).get("pane_id")
    if not pane:
        raise Fail(f"workspace create failed: {created.get('error') or 'no root_pane in the answer'}")
    name = "sd-" + pane.replace(":", "-")
    started = herdr_json(session, "agent", "start", name, "--kind", "claude", "--pane", pane)
    if started.get("error"):
        raise Fail(f"{pane}: claude did not start: {started['error']}; the workspace is left at its shell prompt")
    code, out, err = herdr(session, "agent", "prompt", name, prompt)
    if code != 0:
        raise Fail(f"{pane}: claude started, but the prompt was not sent: {err.strip() or out.strip()}")
    print(f"launched {pane}: claude in {directory}")


def main(argv):
    if len(argv) != 4 or argv[0] != "launch":
        print("herdr_wrap.py: the fake runs only launch <directory> <label> <prompt>", file=sys.stderr)
        return 2
    try:
        launch(session_name(), *argv[1:])
    except Fail as problem:
        print(f"herdr.sh launch: {problem}", file=sys.stderr)
        return problem.code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
