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
from pathlib import Path, PurePosixPath
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sd_ai_command_pack_fleet_lib import (  # noqa: E402
    FleetConfigError,
    PayloadSource,
    fleet_manifest_digest,
    manifest_version,
    parse_fleet_consumers,
    payload_digest,
    validate_candidate_ledger,
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


def git_bytes(*args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ReleaseTagError(
            f"command failed to start: git {' '.join(args)}: {exc}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode(
            "utf-8", errors="replace"
        ).strip()
        suffix = f": {detail}" if detail else ""
        raise ReleaseTagError(
            f"command failed ({result.returncode}): git {' '.join(args)}{suffix}"
        )
    return result.stdout


def resolve_commit(ref: str) -> str:
    return git_text("rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def json_object_at_commit(commit_sha: str, path: str, label: str) -> dict:
    try:
        payload = json.loads(
            git_bytes("show", f"{commit_sha}:{path}").decode("utf-8")
        )
    except UnicodeError as exc:
        raise ReleaseTagError(
            f"{label} is not valid UTF-8 at {commit_sha}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ReleaseTagError(
            f"{label} is not valid JSON at {commit_sha}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ReleaseTagError(f"{label} is not an object at {commit_sha}")
    return payload


def git_tree_entries(commit_sha: str) -> dict[bytes, tuple[str, str, str]]:
    entries: dict[bytes, tuple[str, str, str]] = {}
    tree = git_bytes("ls-tree", "-r", "-t", "-z", commit_sha)
    for record in tree.split(b"\0"):
        if not record:
            continue
        metadata, separator, path = record.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise ReleaseTagError(f"malformed git tree entry at {commit_sha}")
        try:
            mode, object_type, object_id = (
                field.decode("ascii", errors="strict") for field in fields
            )
        except UnicodeError as exc:
            raise ReleaseTagError(
                f"malformed git tree metadata at {commit_sha}: {exc}"
            ) from exc
        entries[path] = (mode, object_type, object_id)
    return entries


def normalize_tree_path(path: PurePosixPath, source: str) -> str:
    if path.is_absolute():
        raise ReleaseTagError(
            f"pack manifest source resolves outside the repository at commit: {source}"
        )
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ReleaseTagError(
                    "pack manifest source resolves outside the repository at commit: "
                    f"{source}"
                )
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        raise ReleaseTagError(
            f"pack manifest source does not resolve to a file at commit: {source}"
        )
    return PurePosixPath(*parts).as_posix()


def payload_source_at_commit(
    commit_sha: str,
    source: str,
    entries: dict[bytes, tuple[str, str, str]],
) -> PayloadSource:
    current = normalize_tree_path(PurePosixPath(source), source)
    visited: set[str] = set()

    while current not in visited:
        visited.add(current)
        parts = PurePosixPath(current).parts
        for index in range(1, len(parts) + 1):
            prefix = PurePosixPath(*parts[:index]).as_posix()
            entry = entries.get(prefix.encode("utf-8"))
            if entry is None:
                raise ReleaseTagError(
                    f"pack manifest source is absent at {commit_sha}: {source}"
                )
            mode, object_type, object_id = entry
            if mode == "120000":
                if object_type != "blob":
                    raise ReleaseTagError(
                        f"pack manifest source has an invalid symlink at {commit_sha}: "
                        f"{source}"
                    )
                target_bytes = git_bytes("cat-file", "blob", object_id)
                try:
                    target = target_bytes.decode("utf-8", errors="strict")
                except UnicodeError as exc:
                    raise ReleaseTagError(
                        "pack manifest source has a non-UTF-8 symlink target at "
                        f"{commit_sha}: {source}: {exc}"
                    ) from exc
                combined = PurePosixPath(*parts[: index - 1]) / PurePosixPath(target)
                if index < len(parts):
                    combined = combined.joinpath(*parts[index:])
                current = normalize_tree_path(combined, source)
                break
            if index < len(parts):
                if mode != "040000" or object_type != "tree":
                    raise ReleaseTagError(
                        "pack manifest source traverses a non-directory at "
                        f"{commit_sha}: {source}"
                    )
                continue
            if mode not in {"100644", "100755"} or object_type != "blob":
                raise ReleaseTagError(
                    f"pack manifest source is not a regular file at {commit_sha}: {source}"
                )
            return PayloadSource(
                content=git_bytes("cat-file", "blob", object_id),
                executable=mode == "100755",
            )

    raise ReleaseTagError(
        f"pack manifest source has a symlink cycle at {commit_sha}: {source}"
    )


def verify_candidate_ledger(commit_sha: str, manifest: dict, version: str) -> None:
    fleet_path = "docs/fleet/consumers.json"
    ledger_path = "docs/fleet/candidate-validation.json"
    fleet_bytes = git_bytes("show", f"{commit_sha}:{fleet_path}")
    try:
        fleet_manifest = json.loads(fleet_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseTagError(
            f"fleet manifest is not valid UTF-8 JSON at {commit_sha}: {exc}"
        ) from exc
    if not isinstance(fleet_manifest, dict):
        raise ReleaseTagError(f"fleet manifest is not an object at {commit_sha}")
    ledger = json_object_at_commit(commit_sha, ledger_path, "candidate ledger")

    tree_entries = git_tree_entries(commit_sha)

    def load_source(source: str) -> PayloadSource:
        return payload_source_at_commit(commit_sha, source, tree_entries)

    try:
        consumers = parse_fleet_consumers(
            fleet_manifest,
            f"fleet manifest {fleet_path}",
        )
        expected_payload = payload_digest(manifest, load_source)
        errors = validate_candidate_ledger(
            ledger,
            expected_version=version,
            expected_payload_digest=expected_payload,
            expected_fleet_digest=fleet_manifest_digest(fleet_bytes),
            consumers=consumers,
        )
    except FleetConfigError as exc:
        raise ReleaseTagError(
            f"candidate validation configuration is invalid: {exc}"
        ) from exc
    if errors:
        raise ReleaseTagError(
            "candidate ledger is not release-ready: " + "; ".join(errors)
        )


def release_tag_plan(base_ref: str, head_ref: str) -> ReleaseTagPlan | None:
    base_sha = resolve_commit(base_ref)
    head_sha = resolve_commit(head_ref)
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

    verify_candidate_ledger(head_sha, manifest, version)

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
