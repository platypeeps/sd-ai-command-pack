#!/usr/bin/env python3
"""Create the manifest version tag for a validated release commit."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_identity import (  # noqa: E402
    ReleaseIdentityError,
    resolve_commit,
    verify_candidate_ledger_at_commit,
)
from sd_ai_command_pack_fleet_lib import (  # noqa: E402
    FleetConfigError,
    manifest_version,
)

SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ReleaseTagError(RuntimeError):
    """Raised when a release tag cannot be planned or created safely."""


@dataclass(frozen=True)
class ReleaseTagPlan:
    tag: str
    commit_sha: str


def run_command(
    command: Sequence[str],
    *,
    accepted_returncodes: set[int] | None = None,
) -> subprocess.CompletedProcess[str]:
    accepted = accepted_returncodes or {0}
    try:
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise ReleaseTagError(f"command failed to start: {' '.join(command)}: {exc}") from exc
    if result.returncode not in accepted:
        detail = (result.stderr or result.stdout).strip()
        suffix = f": {detail}" if detail else ""
        raise ReleaseTagError(
            f"command failed ({result.returncode}): {' '.join(command)}{suffix}"
        )
    return result


def git_text(*args: str) -> str:
    return run_command(["git", *args]).stdout


def release_tag_plan(base_ref: str, head_ref: str) -> ReleaseTagPlan | None:
    repo = Path.cwd()
    try:
        base_sha = resolve_commit(repo, base_ref)
        head_sha = resolve_commit(repo, head_ref)
    except ReleaseIdentityError as exc:
        raise ReleaseTagError(str(exc)) from exc
    changed = run_command(
        ["git", "diff", "--quiet", base_sha, head_sha, "--", "manifest.json"],
        accepted_returncodes={0, 1},
    ).returncode
    if changed == 0:
        return None

    manifest_text = git_text("show", f"{head_sha}:manifest.json")
    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        raise ReleaseTagError(f"manifest.json is not valid JSON at {head_sha}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ReleaseTagError(f"manifest.json is not an object at {head_sha}")
    try:
        version = manifest_version(manifest)
    except FleetConfigError as exc:
        raise ReleaseTagError(str(exc)) from exc
    if not SEMVER_RE.fullmatch(version):
        raise ReleaseTagError(
            f"manifest.json version at {head_sha} is not a supported semantic version: "
            f"{version!r}"
        )

    changelog = git_text("show", f"{head_sha}:CHANGELOG.md")
    top_release_heading = next(
        (line.strip() for line in changelog.splitlines() if line.startswith("## ")),
        None,
    )
    expected_heading = re.compile(
        rf"^## {re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}$"
    )
    if not top_release_heading or not expected_heading.fullmatch(top_release_heading):
        found = repr(top_release_heading) if top_release_heading else "no release heading"
        raise ReleaseTagError(
            f"manifest version {version!r} requires the top CHANGELOG.md release "
            f"heading '## {version} - YYYY-MM-DD'; found {found}"
        )

    try:
        verify_candidate_ledger_at_commit(repo, head_sha, manifest, version)
    except ReleaseIdentityError as exc:
        raise ReleaseTagError(str(exc)) from exc

    return ReleaseTagPlan(tag=f"v{version}", commit_sha=head_sha)


def create_or_verify_tag(plan: ReleaseTagPlan, repository: str) -> None:
    if not REPOSITORY_RE.fullmatch(repository):
        raise ReleaseTagError(f"invalid GitHub repository slug: {repository!r}")

    ref_name = f"refs/tags/{plan.tag}"
    refs_text = run_command(
        [
            "gh",
            "api",
            f"repos/{repository}/git/matching-refs/tags/{plan.tag}",
        ]
    ).stdout
    try:
        refs = json.loads(refs_text)
    except json.JSONDecodeError as exc:
        raise ReleaseTagError(f"GitHub returned invalid tag-ref JSON: {exc}") from exc
    if not isinstance(refs, list):
        raise ReleaseTagError("GitHub tag-ref response was not a list")

    exact_refs = [
        item for item in refs if isinstance(item, dict) and item.get("ref") == ref_name
    ]
    if len(exact_refs) > 1:
        raise ReleaseTagError(f"GitHub returned duplicate refs for {ref_name}")
    if exact_refs:
        target = exact_refs[0].get("object", {})
        if not isinstance(target, dict):
            raise ReleaseTagError(f"GitHub returned an invalid target for {ref_name}")
        target_type = target.get("type")
        target_sha = target.get("sha")
        if target_type == "commit" and target_sha == plan.commit_sha:
            print(f"release tag: {plan.tag} already points at {plan.commit_sha}")
            return
        raise ReleaseTagError(
            f"release tag {plan.tag} already exists at {target_type or 'unknown'} "
            f"{target_sha or 'unknown'}, expected commit {plan.commit_sha}"
        )

    run_command(
        [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{repository}/git/refs",
            "-f",
            f"ref={ref_name}",
            "-f",
            f"sha={plan.commit_sha}",
        ]
    )
    print(f"release tag: created {plan.tag} at {plan.commit_sha}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create an idempotent v<manifest-version> tag when manifest.json "
            "changed and CHANGELOG.md has the matching top release heading."
        )
    )
    parser.add_argument("--base", default="HEAD^", help="Base commit for the release diff")
    parser.add_argument("--head", default="HEAD", help="Release commit to tag")
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="GitHub owner/repository slug (defaults to GITHUB_REPOSITORY)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the planned tag without calling GitHub",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        plan = release_tag_plan(args.base, args.head)
        if plan is None:
            print("release tag: manifest version unchanged; no tag needed")
            return 0
        if args.dry_run:
            print(f"release tag dry-run: would create {plan.tag} at {plan.commit_sha}")
            return 0
        if not args.repository:
            raise ReleaseTagError(
                "--repository or GITHUB_REPOSITORY is required unless --dry-run is used"
            )
        create_or_verify_tag(plan, args.repository)
    except ReleaseTagError as exc:
        print(f"release tag error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
