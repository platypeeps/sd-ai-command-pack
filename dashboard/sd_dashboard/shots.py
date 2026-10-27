"""Screenshots of dashboard pages for the lead to review before enqueue (sd:6007).

`dashboard.sh shots --out DIR PAGE...` serves this checkout on a copy of the
database, so a capture writes nothing to the store, and has headless Chrome
draw each page dark and light, at desktop and phone width. It prints one PNG
path per line, for the pull-request body.

Chrome's command-line `--screenshot` cannot set the theme: theme.js reads it
from localStorage. So this drives Chrome over `--remote-debugging-pipe`, the
DevTools protocol as NUL-ended JSON on fds 3 and 4, with the standard library
alone. Chrome is the one `sd_research_publish.chrome()` finds; `CHROME`
names another.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import select
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import sd_db

from . import pack_module, server

#: Each page is drawn in every one of these: theme, width, height, phone.
VARIANTS = (("dark", 1440, 1000, False), ("dark", 375, 900, True),
            ("light", 1440, 1000, False), ("light", 375, 900, True))
#: Runs before theme.js on every document, so the page paints in that theme.
THEME = "localStorage.setItem('theme', '%s')"
#: The tallest shot, in CSS pixels: a long list stops here, not at 70,000.
TALLEST = 4000
#: How long a page has to reach network idle once its navigation starts.
SETTLE_SECONDS = 30
#: How long Chrome has to answer one DevTools call; apart from the settle wait, so a test can bound that alone.
ANSWER_SECONDS = 30


class ShotFailed(Exception):
    """A page that was not drawn, and why."""


def slug(page: str) -> str:
    """The file stem for `page`: `/tasks?x=1` is `tasks-x-1`, `/` is `root`."""
    return re.sub(r"[^A-Za-z0-9]+", "-", page).strip("-") or "root"


class Browser:
    """Headless Chrome on the DevTools pipe; one call at a time."""

    def __init__(self, chrome: str, profile: Path) -> None:
        chrome_reads, to_chrome = os.pipe()
        from_chrome, chrome_writes = os.pipe()
        # Chrome reads commands from fd 3 and writes replies to fd 4; the shell puts the pipe ends there.
        self.process = subprocess.Popen(
            ["/bin/sh", "-c", 'exec "$@" 3<&%d 4>&%d' % (chrome_reads, chrome_writes), "sh", chrome,
             "--headless=new", "--remote-debugging-pipe", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
             "--no-default-browser-check", "--user-data-dir=%s" % profile, "about:blank"],
            pass_fds=(chrome_reads, chrome_writes), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(chrome_reads)
        os.close(chrome_writes)
        self.writer = os.fdopen(to_chrome, "wb")
        self.reader = from_chrome
        self.buffer = b""
        self.events: list[dict] = []
        self.last = 0

    def read(self, deadline: float) -> dict:
        while b"\0" not in self.buffer:
            if not select.select([self.reader], [], [], max(0.0, deadline - time.monotonic()))[0]:
                raise TimeoutError
            chunk = os.read(self.reader, 65536)
            if not chunk:
                raise ShotFailed("Chrome closed the DevTools pipe (exit %s)" % self.process.poll())
            self.buffer += chunk
        message, self.buffer = self.buffer.split(b"\0", 1)
        return json.loads(message)

    def call(self, method: str, params: dict | None = None, session: str | None = None) -> dict:
        self.last += 1
        message = {"id": self.last, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        self.writer.write(json.dumps(message).encode() + b"\0")
        self.writer.flush()
        deadline = time.monotonic() + ANSWER_SECONDS
        while True:
            try:
                answer = self.read(deadline)
            except TimeoutError:
                raise ShotFailed("%s: no answer within %s s" % (method, ANSWER_SECONDS)) from None
            if answer.get("id") != self.last:
                self.events.append(answer)
                continue
            if "error" in answer:
                raise ShotFailed("%s: %s" % (method, answer["error"].get("message", answer["error"])))
            return answer.get("result", {})

    def settle(self, loader: str, label: str) -> None:
        """Wait for network idle of the load `loader` names; an earlier load's idle does not count."""
        deadline = time.monotonic() + SETTLE_SECONDS
        while True:
            event = self.events.pop(0) if self.events else None
            if event is None:
                try:
                    event = self.read(deadline)
                except TimeoutError:
                    raise ShotFailed("%s: no network idle within %s s" % (label, SETTLE_SECONDS)) from None
            params = event.get("params", {})
            if (event.get("method") == "Page.lifecycleEvent" and params.get("name") == "networkIdle"
                    and params.get("loaderId") == loader):
                return

    def close(self) -> None:
        try:
            self.call("Browser.close")
        except (ShotFailed, OSError, TimeoutError):
            pass
        try:
            self.writer.close()
        except OSError:
            pass
        os.close(self.reader)
        try:
            self.process.wait(10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def draw(browser: Browser, url: str, theme: str, width: int, height: int, phone: bool, label: str) -> bytes:
    """One page in one variant, as PNG bytes."""
    target = browser.call("Target.createTarget", {"url": "about:blank"})["targetId"]
    session = browser.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
    try:
        for method, params in (("Page.enable", {}), ("Page.setLifecycleEventsEnabled", {"enabled": True}),
                               ("Emulation.setDeviceMetricsOverride",
                                {"width": width, "height": height, "deviceScaleFactor": 2 if phone else 1,
                                 "mobile": phone}),
                               ("Emulation.setEmulatedMedia",
                                {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]}),
                               ("Page.addScriptToEvaluateOnNewDocument", {"source": THEME % theme})):
            browser.call(method, params, session)
        loaded = browser.call("Page.navigate", {"url": url}, session)
        if loaded.get("errorText"):
            raise ShotFailed("%s: %s" % (label, loaded["errorText"]))
        browser.settle(loaded.get("loaderId", ""), label)
        size = browser.call("Page.getLayoutMetrics", {}, session)["cssContentSize"]
        clip = {"x": 0, "y": 0, "width": width, "height": min(max(size["height"], height), TALLEST), "scale": 1}
        shot = browser.call("Page.captureScreenshot",
                            {"format": "png", "captureBeyondViewport": True, "clip": clip}, session)
    finally:
        browser.call("Target.closeTarget", {"targetId": target})
    data = base64.b64decode(shot.get("data", ""))
    if not data.startswith(b"\x89PNG"):
        raise ShotFailed("%s: Chrome sent no PNG" % label)
    return data


def capture(chrome: str, base: str, pages: list[str], out: Path) -> list[Path]:
    """Draw every page in every variant into `out`; the files, in that order.

    All or nothing: a page that fails raises before any file lands, so no
    partial set passes for a review.
    """
    drawn: list[tuple[Path, bytes]] = []
    with tempfile.TemporaryDirectory() as scratch:
        browser = Browser(chrome, Path(scratch) / "profile")
        try:
            for page in pages:
                for theme, width, height, phone in VARIANTS:
                    label = "%s %s %d" % (page, theme, width)
                    data = draw(browser, base + page, theme, width, height, phone, label)
                    drawn.append((out / ("%s-%s-%d.png" % (slug(page), theme, width)), data))
        finally:
            browser.close()
    out.mkdir(parents=True, exist_ok=True)
    for path, data in drawn:
        partial = path.with_name(path.name + ".partial")
        partial.write_bytes(data)
        os.replace(partial, path)
    return [path for path, _ in drawn]


def chrome() -> str:
    """`CHROME` when set, else the Chrome `sd_research_publish` draws diagrams with; "" when none."""
    if "CHROME" in os.environ:
        named = os.environ["CHROME"]
        return named if os.access(named, os.X_OK) else ""
    return pack_module("sd_research_publish").chrome()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dashboard.sh shots",
                                     description="Draw dashboard pages dark and light, at desktop and phone width.")
    parser.add_argument("--out", type=Path, required=True, help="folder for the PNGs")
    parser.add_argument("--database", type=Path, default=None,
                        help="the store to copy (default: this machine's sd.db)")
    parser.add_argument("pages", nargs="+", metavar="PAGE", help="a page address, such as /tasks")
    arguments = parser.parse_args(argv)
    for page in arguments.pages:
        if not page.startswith("/"):
            parser.error("%s: a page is an address that starts with /" % page)
    browser = chrome()
    if not browser:
        print("shots: no Chrome found; set CHROME to its binary", file=sys.stderr)
        return 1
    if arguments.database is None:
        arguments.database = sd_db.database.local_path()
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "sd.db"
        try:
            # A read-only open: a missing store is an error here, not a new empty one drawn as empty pages.
            source = sd_db.connect(arguments.database, write=False)
            try:
                if not isinstance(source, sqlite3.Connection):
                    raise OSError("it is the hub's; run shots on the hub")
                target = sd_db.connect(copy, create=True)
                try:
                    source.backup(target)
                finally:
                    target.close()
            finally:
                source.close()
        except (OSError, sqlite3.Error, sd_db.SdDbError) as problem:
            print("shots: cannot copy %s: %s" % (arguments.database, problem), file=sys.stderr)
            return 1
        port = free_port()
        served = server.build(copy, port=port)
        thread = threading.Thread(target=served.serve_forever, daemon=True, name="sd-shots")
        thread.start()
        base = "http://127.0.0.1:%d" % port
        try:
            for page in arguments.pages:
                try:
                    with urllib.request.urlopen(base + page, timeout=SETTLE_SECONDS) as answer:
                        status = answer.status
                except urllib.error.HTTPError as refused:
                    status = refused.code
                except OSError as problem:
                    print("shots: %s did not answer: %s" % (page, problem), file=sys.stderr)
                    return 1
                if status != 200:
                    print("shots: %s answered %d" % (page, status), file=sys.stderr)
                    return 1
            files = capture(browser, base, arguments.pages, arguments.out)
        except ShotFailed as problem:
            print("shots: %s" % problem, file=sys.stderr)
            return 1
        finally:
            served.shutdown()
            served.server_close()
    for file in files:
        sys.stdout.write("%s\n" % file)
    return 0


if __name__ == "__main__":  # pragma: no cover - the entrypoint
    raise SystemExit(main())
