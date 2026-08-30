#!/usr/bin/env python3
"""`sd-review setup-github`: install the opt-in routing lane in this repository.

This is the one surface in the review lane that writes. `bin/sd-review` reviews
and never posts -- `tests/test_sd_review_boundary.py` proves it structurally, by
reading that file's imports and call sites -- so the installer lives here, in its
own module, and the proof stays about the file it is a proof of.

What gets installed is a workflow that *reports*. It resolves the pull request's
diff, runs `route()` over the repository's policy, and prints the plan. It
requests no reviewer, posts no comment, and holds `contents: read`, so a pull
request cannot be made worse by it -- which is the whole reason a repository is
allowed to opt in at all.

Three refusals, each with a decision behind it:

  * `minimal` and `guest` repositories cannot install it (R10-D5), so a shared
    or upstream repository can never grow the framework's workflow.
  * A repository still carrying the sd-github-review footprint refuses without
    `--remove-legacy`: two routers in one repository is how a change gets
    reviewed twice and read once.
  * A pack checkout with uncommitted changes refuses to pin itself, because a
    pin is a promise that the bytes a consumer runs are the bytes reviewed here.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Callable, Mapping, Sequence, TextIO

_BIN = str(pathlib.Path(__file__).resolve().parent)
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

import sd_lib  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_REFUSED = 3

ACTION_REPOSITORY = "platypeeps/sd-ai-command-pack"
ACTION_SUBPATH = "actions/review-route"
# Pinned by digest with the tag beside it, because that is what this
# repository's own workflow security audit requires -- and a consumer inherits
# the file this writes.
CHECKOUT_ACTION = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
CHECKOUT_VERSION = "v7.0.1"
WORKFLOW_RELATIVE_PATH = pathlib.Path(".github") / "workflows" / "sd-review-route.yml"
# The footprint sd-github-review's installer left. `bin/migrate-trellis` removes
# the same three; this list exists so the installer can refuse over them rather
# than quietly add a second router beside the first.
LEGACY_ROUTER_PATHS = (
    ".github/workflows/ai-review-router.yml",
    ".github/workflows/sd-review.yml",
    ".github/sd-github-review.json",
)


class Refusal(Exception):
    """A precondition said no. Exit 3, and the message names what was wrong."""


class UsageError(Exception):
    """An invocation fault: exit 2, one sentence, no traceback."""


def pack_root() -> pathlib.Path:
    """The checkout this file is being run from."""

    return pathlib.Path(__file__).resolve().parent.parent


def resolve_pin(pack: pathlib.Path, given: str | None) -> str:
    """The commit a consumer's workflow will name, or a refusal.

    `git rev-parse HEAD` in a dirty checkout returns a commit that exists and a
    working tree that does not, which is a pin that lies. `--pin` is the escape
    hatch for naming a different commit, and is not second-guessed.
    """

    if given:
        return given
    head = sd_lib.git_output(["rev-parse", "HEAD"], pack)
    if not head:
        raise Refusal(f"cannot read the pack's HEAD commit in {pack}; pass --pin <sha>")
    if sd_lib.git_output(["status", "--porcelain"], pack):
        raise Refusal(
            f"the pack checkout at {pack} has uncommitted changes, so {head[:12]} does not "
            "describe what a consumer would run; commit them or pass --pin <sha>"
        )
    return head


def action_reference(pin: str | None) -> str:
    """How the workflow names the action.

    In the pack's own repository the action is a path in the same checkout, and
    a digest there would be a bootstrap that cannot close: the pull request
    installing the lane would pin a commit that exists only once it merges.
    Everywhere else the digest is the point -- which is also why the pin is
    resolved only when it will be written, so a dirty pack checkout cannot block
    a self-install that never names a commit.
    """

    if pin is None:
        return f"./{ACTION_SUBPATH}"
    return f"{ACTION_REPOSITORY}/{ACTION_SUBPATH}@{pin}"


def workflow_text(action_ref: str) -> str:
    """The workflow a consumer gets: one job, one action, read permission only."""

    return f"""\
# Installed by `sd-review setup-github`. Opt-in: nothing installs this file, and
# deleting it removes the lane.
#
# What it does: resolves this pull request's diff, runs `route()` over this
# repository's review policy -- `.github/sd-review.json` when that file exists,
# the built-in default when it does not -- and prints the resulting plan.
#
# What it does not do: it requests no reviewer, posts no comment, sets no label,
# and holds `contents: read` and nothing else, so it cannot affect this pull
# request's outcome. Asking a remote reviewer for a review is a separate change
# with its own decision record.
name: sd-review route

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

permissions:
  contents: read

jobs:
  route:
    name: route
    runs-on: ubuntu-latest
    steps:
      - name: Check out the pull request
        uses: {CHECKOUT_ACTION} # {CHECKOUT_VERSION}
        with:
          # `route()` measures the branch against its merge base, which a
          # shallow clone does not contain.
          fetch-depth: 0
          persist-credentials: false
      - name: Report the routing plan
        uses: {action_ref}
"""


def setup_github(
    root: pathlib.Path,
    args: argparse.Namespace,
    *,
    load_policy: Callable[[pathlib.Path], tuple[Mapping[str, Any], str]],
    backends: Sequence[Any],
) -> dict[str, Any]:
    """Install the routing lane in this repository, or refuse and say why.

    `load_policy` and `backends` are the seam `bin/sd-review` names: the
    installer reads the policy through the same validator a review does, so a
    policy this refuses to install against is one no review would have run
    against either.
    """

    repo_mode = sd_lib.mode(root)
    if repo_mode != "full":
        raise Refusal(
            f"this repository is in {repo_mode} mode; only a full-mode repository installs "
            "the routing lane (R10-D5)"
        )

    legacy = [rel for rel in LEGACY_ROUTER_PATHS if (root / rel).exists()]
    if legacy and not args.remove_legacy:
        raise Refusal(
            "the sd-github-review footprint is still here: "
            + ", ".join(legacy)
            + "; rerun with --remove-legacy to remove it, or remove it first -- two routers "
            "in one repository is how a change gets reviewed twice and read once"
        )

    policy, policy_source = load_policy(root)
    pack = pack_root()
    pin = None if root == pack else resolve_pin(pack, args.pin)
    target = root / WORKFLOW_RELATIVE_PATH
    text = workflow_text(action_reference(pin))
    existing = target.read_text(encoding="utf-8") if target.is_file() else None

    result: dict[str, Any] = {
        "repo": str(root),
        "mode": repo_mode,
        "policy_source": policy_source,
        "authors": list(policy["authors"]),
        "github_backends": [row.name for row in backends if row.lane == "github"],
        "workflow": str(WORKFLOW_RELATIVE_PATH),
        "action": action_reference(pin),
        "pin": pin,
        "legacy_found": legacy,
        "legacy_removed": [],
        "dry_run": bool(args.dry_run),
        "status": "installed",
    }

    if existing is not None and existing != text and not args.force:
        raise Refusal(
            f"{WORKFLOW_RELATIVE_PATH} exists and differs from what this build writes; "
            "rerun with --force to replace it"
        )
    if existing == text:
        result["status"] = "unchanged"

    if args.dry_run:
        result["status"] = "dry_run"
        result["would_write"] = text
        return result

    for rel in legacy:
        (root / rel).unlink()
        result["legacy_removed"].append(rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return result


def render(result: Mapping[str, Any], stream: TextIO) -> None:
    write = stream.write
    write(f"sd-review setup-github: {result['repo']}\n")
    write(f"  mode        {result['mode']}\n")
    write(f"  policy      {result['policy_source']}\n")
    authors = ", ".join(result["authors"]) or "(none listed; rule 5 hard-fails for nobody)"
    write(f"  authors     {authors}\n")
    write(f"  workflow    {result['workflow']}\n")
    write(f"  action      {result['action']}\n")
    if result["legacy_found"]:
        state = "removed" if result["legacy_removed"] else "still present"
        write(f"  legacy      {', '.join(result['legacy_found'])} ({state})\n")
    write(
        f"  not asked   {', '.join(result['github_backends'])} "
        "(this lane reports a plan; it requests nobody)\n"
    )
    write(f"\nsd-review setup-github: {result['status']}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sd-review setup-github",
        description=(
            "Install the opt-in routing workflow in this repository. It reports the "
            "routing plan on a pull request and requests no reviewer."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="print what would be written, write nothing")
    parser.add_argument("--json", action="store_true", help="emit one machine-readable object")
    parser.add_argument("--force", action="store_true", help="replace an existing workflow that differs")
    parser.add_argument(
        "--remove-legacy",
        action="store_true",
        help="delete the sd-github-review router files this lane replaces",
    )
    parser.add_argument(
        "--pin",
        metavar="SHA",
        default=None,
        help="pin the action to this commit instead of the pack checkout's HEAD",
    )
    return parser


def main(
    argv: list[str],
    *,
    load_policy: Callable[[pathlib.Path], tuple[Mapping[str, Any], str]],
    backends: Sequence[Any],
) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = sd_lib.repo_root(None)
        if root is None:
            raise UsageError(f"{pathlib.Path.cwd()} is not inside a git repository")
        result = setup_github(root, args, load_policy=load_policy, backends=backends)
    except (UsageError, sd_lib.ConfigError, OSError) as error:
        print(f"sd-review setup-github: error: {error}", file=sys.stderr)
        return EXIT_USAGE
    except Refusal as error:
        print(f"sd-review setup-github: refused: {error}", file=sys.stderr)
        return EXIT_REFUSED

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        render(result, sys.stdout)
    return EXIT_OK
