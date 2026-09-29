"""The `sd-review` command `sd-ship` dispatches: what a reviewer is asked to do.

A `verdict` file in the review binding (sd:1834): it fixes the scope and the
challenge stance, so a change here changes what a new review would be asked
and moves every stored receipt. The rest of `sd_ship_review.py` is gate code
and runs live against the stored report.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any


def review_argv(bin_dir: pathlib.Path, database: pathlib.Path, args: Any, base: str | None) -> list[str]:
    """The sd-review command both stages run: `--explain` first, then the pass."""
    argv = [sys.executable, str(bin_dir / "sd-review"), "--scope", "branch", "--challenge", "--json", "--database", str(database)]
    requested = getattr(args, "provider", None)
    if requested is not None:
        argv += ["--provider", requested]
    if getattr(args, "reuse_check", False):
        argv.append("--reuse-check")
    if getattr(args, "review_timeout", None):
        # sd:1475. sd-review sizes its timing plan, and so this watchdog, from it.
        argv += ["--timeout", str(args.review_timeout)]
    if base:
        argv += ["--base", base]
    return argv
