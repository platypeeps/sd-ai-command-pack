#!/usr/bin/env python3
"""Verify exact-commit release identity for tagging and fleet rollout."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sd_ai_command_pack_fleet_lib import (  # noqa: E402
    FleetConfigError,
    PayloadSource,
    filesystem_payload_digest,
    fleet_manifest_digest,
    load_fleet_consumers,
    load_json_object,
    manifest_version,
    parse_fleet_consumers,
    payload_digest,
    validate_candidate_ledger,
)

GIT_TIMEOUT_SECONDS = 60


class ReleaseIdentityError(RuntimeError):
    """Raised when a source checkout does not identify a published release."""


@dataclass(frozen=True)
class ReleaseIdentity:
    status: str
    version: str
    tag: str
    commit_sha: str
    payload_digest: str

    def as_json(self) -> dict[str, str]:
        return {
            "status": self.status,
            "version": self.version,
            "tag": self.tag,
            "commit": self.commit_sha,
            "payloadDigest": self.payload_digest,
        }


def run_git(
    repo: Path,
    args: Sequence[str],
    *,
    accepted_returncodes: set[int] | None = None,
    text: bool = False,
) -> subprocess.CompletedProcess:
    accepted = accepted_returncodes or {0}
    command = ["git", *args]
    try:
        result = subprocess.run(
            command,
            cwd=repo,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReleaseIdentityError(
            f"git command failed to start or timed out: {' '.join(command)}: {exc}"
        ) from exc
    if result.returncode not in accepted:
        raw_detail = result.stderr or result.stdout
        if isinstance(raw_detail, bytes):
            detail = raw_detail.decode("utf-8", errors="replace").strip()
        else:
            detail = raw_detail.strip()
        suffix = f": {detail}" if detail else ""
        raise ReleaseIdentityError(
            f"git command failed ({result.returncode}): {' '.join(command)}{suffix}"
        )
    return result


def git_text(repo: Path, *args: str) -> str:
    return run_git(repo, args, text=True).stdout


def git_bytes(repo: Path, *args: str) -> bytes:
    return run_git(repo, args).stdout


def resolve_commit(repo: Path, ref: str) -> str:
    return git_text(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def json_object_at_commit(
    repo: Path,
    commit_sha: str,
    path: str,
    label: str,
) -> dict:
    try:
        payload = json.loads(
            git_bytes(repo, "show", f"{commit_sha}:{path}").decode("utf-8")
        )
    except UnicodeError as exc:
        raise ReleaseIdentityError(
            f"{label} is not valid UTF-8 at {commit_sha}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ReleaseIdentityError(
            f"{label} is not valid JSON at {commit_sha}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ReleaseIdentityError(f"{label} is not an object at {commit_sha}")
    return payload


def git_tree_entries(
    repo: Path,
    commit_sha: str,
) -> dict[bytes, tuple[str, str, str]]:
    entries: dict[bytes, tuple[str, str, str]] = {}
    tree = git_bytes(repo, "ls-tree", "-r", "-t", "-z", commit_sha)
    for record in tree.split(b"\0"):
        if not record:
            continue
        metadata, separator, path = record.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise ReleaseIdentityError(f"malformed git tree entry at {commit_sha}")
        try:
            mode, object_type, object_id = (
                field.decode("ascii", errors="strict") for field in fields
            )
        except UnicodeError as exc:
            raise ReleaseIdentityError(
                f"malformed git tree metadata at {commit_sha}: {exc}"
            ) from exc
        entries[path] = (mode, object_type, object_id)
    return entries


def normalize_tree_path(path: PurePosixPath, source: str) -> str:
    if path.is_absolute():
        raise ReleaseIdentityError(
            f"pack manifest source resolves outside the repository at commit: {source}"
        )
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ReleaseIdentityError(
                    "pack manifest source resolves outside the repository at commit: "
                    f"{source}"
                )
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        raise ReleaseIdentityError(
            f"pack manifest source does not resolve to a file at commit: {source}"
        )
    return PurePosixPath(*parts).as_posix()


def payload_source_at_commit(
    repo: Path,
    commit_sha: str,
    source: str,
    entries: Mapping[bytes, tuple[str, str, str]],
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
                raise ReleaseIdentityError(
                    f"pack manifest source is absent at {commit_sha}: {source}"
                )
            mode, object_type, object_id = entry
            if mode == "120000":
                if object_type != "blob":
                    raise ReleaseIdentityError(
                        f"pack manifest source has an invalid symlink at {commit_sha}: "
                        f"{source}"
                    )
                target_bytes = git_bytes(repo, "cat-file", "blob", object_id)
                try:
                    target = target_bytes.decode("utf-8", errors="strict")
                except UnicodeError as exc:
                    raise ReleaseIdentityError(
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
                    raise ReleaseIdentityError(
                        "pack manifest source traverses a non-directory at "
                        f"{commit_sha}: {source}"
                    )
                continue
            if mode not in {"100644", "100755"} or object_type != "blob":
                raise ReleaseIdentityError(
                    f"pack manifest source is not a regular file at {commit_sha}: {source}"
                )
            return PayloadSource(
                content=git_bytes(repo, "cat-file", "blob", object_id),
                executable=mode == "100755",
            )

    raise ReleaseIdentityError(
        f"pack manifest source has a symlink cycle at {commit_sha}: {source}"
    )


def payload_digest_at_commit(
    repo: Path,
    commit_sha: str,
    manifest: Mapping[str, object],
) -> str:
    entries = git_tree_entries(repo, commit_sha)

    def load_source(source: str) -> PayloadSource:
        return payload_source_at_commit(repo, commit_sha, source, entries)

    try:
        return payload_digest(manifest, load_source)
    except FleetConfigError as exc:
        raise ReleaseIdentityError(f"release payload is invalid: {exc}") from exc


def verify_candidate_ledger_at_commit(
    repo: Path,
    commit_sha: str,
    manifest: Mapping[str, object],
    version: str,
) -> None:
    fleet_path = "docs/fleet/consumers.json"
    ledger_path = "docs/fleet/candidate-validation.json"
    fleet_bytes = git_bytes(repo, "show", f"{commit_sha}:{fleet_path}")
    try:
        fleet_manifest = json.loads(fleet_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseIdentityError(
            f"fleet manifest is not valid UTF-8 JSON at {commit_sha}: {exc}"
        ) from exc
    if not isinstance(fleet_manifest, dict):
        raise ReleaseIdentityError(f"fleet manifest is not an object at {commit_sha}")
    ledger = json_object_at_commit(
        repo,
        commit_sha,
        ledger_path,
        "candidate ledger",
    )

    try:
        consumers = parse_fleet_consumers(
            fleet_manifest,
            f"fleet manifest {fleet_path}",
        )
        expected_payload = payload_digest_at_commit(repo, commit_sha, manifest)
        errors = validate_candidate_ledger(
            ledger,
            expected_version=version,
            expected_payload_digest=expected_payload,
            expected_fleet_digest=fleet_manifest_digest(fleet_bytes),
            consumers=consumers,
        )
    except FleetConfigError as exc:
        raise ReleaseIdentityError(
            f"candidate validation configuration is invalid: {exc}"
        ) from exc
    if errors:
        raise ReleaseIdentityError(
            "candidate ledger is not release-ready: " + "; ".join(errors)
        )


def _remote_tag_object(repo: Path, remote: str, tag: str) -> str:
    ref = f"refs/tags/{tag}"
    output = git_text(repo, "ls-remote", "--refs", "--", remote, ref)
    matches: list[str] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1] == ref:
            matches.append(fields[0])
    if not matches:
        raise ReleaseIdentityError(
            f"release tag {tag} is missing from remote {remote}; publish the release before fleet refresh"
        )
    if len(matches) != 1:
        raise ReleaseIdentityError(
            f"remote {remote} returned duplicate identities for release tag {tag}"
        )
    return matches[0]


def _current_candidate_errors(
    manifest_path: Path,
    fleet_path: Path,
    ledger_path: Path,
    *,
    version: str,
    payload: str,
) -> list[str]:
    try:
        fleet_bytes = fleet_path.read_bytes()
        consumers = load_fleet_consumers(fleet_path)
        ledger = load_json_object(ledger_path, "candidate ledger")
    except (OSError, FleetConfigError) as exc:
        return [str(exc)]
    return validate_candidate_ledger(
        ledger,
        expected_version=version,
        expected_payload_digest=payload,
        expected_fleet_digest=fleet_manifest_digest(fleet_bytes),
        consumers=consumers,
    )


def verify_release_identity(
    repo: Path,
    *,
    manifest_path: Path,
    fleet_path: Path,
    ledger_path: Path,
    remote: str = "origin",
) -> ReleaseIdentity:
    repo = repo.resolve()
    try:
        manifest = load_json_object(manifest_path, "pack manifest")
        version = manifest_version(manifest)
        current_payload = filesystem_payload_digest(manifest_path)
    except FleetConfigError as exc:
        raise ReleaseIdentityError(str(exc)) from exc

    tag = f"v{version}"
    ref = f"refs/tags/{tag}"
    try:
        local_tag_object = git_text(repo, "rev-parse", "--verify", ref).strip()
        tag_commit = resolve_commit(repo, ref)
    except ReleaseIdentityError as exc:
        raise ReleaseIdentityError(
            f"local release tag {ref} is missing; fetch tags from {remote} and rerun"
        ) from exc

    remote_tag_object = _remote_tag_object(repo, remote, tag)
    if local_tag_object != remote_tag_object:
        raise ReleaseIdentityError(
            f"release tag {tag} was rewritten or does not match {remote}: "
            f"local {local_tag_object}, remote {remote_tag_object}"
        )

    ancestry = run_git(
        repo,
        ["merge-base", "--is-ancestor", tag_commit, "HEAD"],
        accepted_returncodes={0, 1},
    ).returncode
    if ancestry != 0:
        raise ReleaseIdentityError(
            f"release tag {tag} commit {tag_commit} is not an ancestor of the current checkout"
        )

    tagged_manifest = json_object_at_commit(repo, tag_commit, "manifest.json", "pack manifest")
    try:
        tagged_version = manifest_version(tagged_manifest, f"pack manifest at {tag}")
    except FleetConfigError as exc:
        raise ReleaseIdentityError(str(exc)) from exc
    if tagged_version != version:
        raise ReleaseIdentityError(
            f"tag {tag} contains pack version {tagged_version!r}; expected {version!r}"
        )

    tagged_payload = payload_digest_at_commit(repo, tag_commit, tagged_manifest)
    if tagged_payload != current_payload:
        raise ReleaseIdentityError(
            f"tag {tag} payload does not match the current checkout: "
            f"tag {tagged_payload}, current {current_payload}"
        )

    try:
        verify_candidate_ledger_at_commit(
            repo,
            tag_commit,
            tagged_manifest,
            tagged_version,
        )
    except ReleaseIdentityError as exc:
        raise ReleaseIdentityError(f"tagged {exc}") from exc

    current_errors = _current_candidate_errors(
        manifest_path,
        fleet_path,
        ledger_path,
        version=version,
        payload=current_payload,
    )
    if current_errors:
        raise ReleaseIdentityError(
            "current candidate ledger is not release-ready: "
            + "; ".join(current_errors)
        )

    return ReleaseIdentity(
        status="verified",
        version=version,
        tag=tag,
        commit_sha=tag_commit,
        payload_digest=current_payload,
    )
