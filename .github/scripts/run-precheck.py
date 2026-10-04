#!/usr/bin/env python3
"""Run the always-run test modules, each on its own, and name every one that fails.

`make precheck` runs `lint` and then this (sd:2604). `sd-check` runs
`make precheck` before it waits for a gate slot, so a mypy error or a broken
whole-tree module fails in about a minute instead of after the slot wait and
the full suite. On 2026-10-03 and 10-04 at least five full gates of 15 to 25
minutes each failed on exactly that.

The modules are not listed here. They are the ones `select-tests.py` reads as
the always-run set, off the `# select-tests: always-run` line each carries, so
a module joins the precheck the way it joins the changed-files fast path: by
declaring itself. No module carrying the line means the set has drifted, and
that fails rather than passing on nothing.

Each module runs in its own `python -m unittest` process, so a failure is
attributed to its module by name. The output of a failing module is printed
whole, then one last line names every module that failed. The full suite runs
these modules again, under coverage; this run measures nothing.
"""

from __future__ import annotations

import concurrent.futures
import importlib.util
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
SELECTOR = ROOT / ".github/scripts/select-tests.py"


def always_run_modules(root: pathlib.Path) -> list[str]:
    """The always-run set, as `select-tests.py` reads it off the tree."""

    spec = importlib.util.spec_from_file_location("select_tests", SELECTOR)
    assert spec is not None and spec.loader is not None
    selector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selector)
    return sorted(selector.always_run(selector.test_modules(root)))


def run_module(name: str) -> tuple[str, int, float, str]:
    started = time.monotonic()
    # No test reaches the real Jev; run-tests.sh says why (sd:2136).
    environment = {**os.environ, "JEV_ENABLED": "0"}
    result = subprocess.run([sys.executable, "-m", "unittest", name], cwd=ROOT, env=environment,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, check=False)
    return name, result.returncode, time.monotonic() - started, result.stdout


def main() -> int:
    modules = always_run_modules(ROOT)
    if not modules:
        print("precheck failed: no test module carries the always-run line, so the set has drifted")
        return 1
    workers = max(1, (os.cpu_count() or 2) // 2)
    failed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for name, code, seconds, output in sorted(pool.map(run_module, modules)):
            print(f"precheck: {name} {'pass' if code == 0 else 'FAIL'} ({seconds:.1f}s)")
            if code:
                failed.append(name)
                print(output.rstrip())
    if failed:
        print(f"precheck failed: {', '.join(failed)}")
        return 1
    print(f"precheck: {len(modules)} always-run modules pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
