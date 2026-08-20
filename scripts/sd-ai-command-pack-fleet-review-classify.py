#!/usr/bin/env python3
"""Classify whether a fleet refresh needs a new remote implementation review."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]
RELEASE_SCRIPT_DIR = ROOT / ".github/scripts"
for import_root in (ROOT, RELEASE_SCRIPT_DIR):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from release_identity import (  # noqa: E402
    ReleaseIdentity,
    ReleaseIdentityError,
    resolve_commit,
    run_git,
    verify_release_identity,
)
from sd_ai_command_pack_fleet_lib import (  # noqa: E402
    FleetConfigError,
    FleetConsumer,
    load_fleet_consumers,
)

SCHEMA_VERSION = 1
INSPECTION_TIMEOUT_SECONDS = 180
DEFAULT_FLEET_MANIFEST = ROOT / "docs/fleet/consumers.json"
DEFAULT_PACK_MANIFEST = ROOT / "manifest.json"
DEFAULT_CANDIDATE_LEDGER = ROOT / "docs/fleet/candidate-validation.json"
INSTALLED_TARGETS = Path(".sd-ai-command-pack/installed-targets.txt")
PACK_MANIFEST = Path(".sd-ai-command-pack/manifest.json")
PROVENANCE = Path(".sd-ai-command-pack/provenance.json")
RECEIPT_PATHS = frozenset(
    {
        INSTALLED_TARGETS.as_posix(),
        PACK_MANIFEST.as_posix(),
        PROVENANCE.as_posix(),
    }
)
FULL_COMMIT_RE = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")


class FleetReviewClassificationError(RuntimeError):
    """Raised when integration-only eligibility cannot be proven."""


@dataclass(frozen=True)
class FleetReviewClassification:
    eligible: bool
    consumer: str
    repository: str
    base_commit: str | None
    head_commit: str | None
    release_identity: dict[str, str] | None
    installed_version: str | None
    installed_platforms: tuple[str, ...]
    changed_paths: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    disallowed_paths: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def classification(self) -> str:
        return "integration-only" if self.eligible else "remote-review-required"

    def as_json(self) -> dict[str, object]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "eligible": self.eligible,
            "classification": self.classification,
            "consumer": self.consumer,
            "repository": self.repository,
            "baseCommit": self.base_commit,
            "headCommit": self.head_commit,
            "releaseIdentity": self.release_identity,
            "installedVersion": self.installed_version,
            "installedPlatforms": list(self.installed_platforms),
            "changedPaths": list(self.changed_paths),
            "allowedPaths": list(self.allowed_paths),
            "disallowedPaths": list(self.disallowed_paths),
            "reasons": list(self.reasons),
        }


ReleaseVerifier = Callable[..., ReleaseIdentity]
InspectionRunner = Callable[[Path], dict[str, object]]


def _bounded_detail(value: str, *, limit: int = 2000) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _git_bytes(
    repo: Path,
    *args: str,
    accepted_returncodes: set[int] | None = None,
) -> bytes:
    try:
        return run_git(
            repo,
            args,
            accepted_returncodes=accepted_returncodes,
        ).stdout
    except ReleaseIdentityError as exc:
        raise FleetReviewClassificationError(str(exc)) from exc


def _safe_repo_path(value: str) -> bool:
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return bool(value) and not (
        value == "."
        or "\\" in value
        or posix.as_posix() != value
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ".." in posix.parts
        or ".." in windows.parts
    )


def parse_installed_targets(content: str, label: str) -> frozenset[str]:
    entries: list[str] = []
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        if not _safe_repo_path(value):
            raise FleetReviewClassificationError(
                f"{label} has unsafe entry on line {line_number}: {value!r}"
            )
        entries.append(value)
    if not entries:
        raise FleetReviewClassificationError(f"{label} contains no installed targets")
    if len(entries) != len(set(entries)):
        raise FleetReviewClassificationError(f"{label} contains duplicate entries")
    return frozenset(entries)


def installed_targets_at_commit(repo: Path, commit_sha: str) -> frozenset[str]:
    raw = _git_bytes(repo, "show", f"{commit_sha}:{INSTALLED_TARGETS.as_posix()}")
    try:
        content = raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise FleetReviewClassificationError(
            f"base installed-targets receipt is not valid UTF-8 at {commit_sha}: {exc}"
        ) from exc
    return parse_installed_targets(content, "base installed-targets receipt")


def current_installed_targets(repo: Path) -> frozenset[str]:
    path = repo / INSTALLED_TARGETS
    if path.is_symlink() or not path.is_file():
        raise FleetReviewClassificationError(
            f"current installed-targets receipt is missing or invalid: {path}"
        )
    try:
        content = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise FleetReviewClassificationError(
            f"cannot read current installed-targets receipt {path}: {exc}"
        ) from exc
    return parse_installed_targets(content, "current installed-targets receipt")


def _decode_git_paths(raw: bytes, label: str) -> tuple[str, ...]:
    paths: list[str] = []
    for encoded in raw.split(b"\0"):
        if not encoded:
            continue
        try:
            value = encoded.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise FleetReviewClassificationError(
                f"{label} contains a non-UTF-8 path: {exc}"
            ) from exc
        if not _safe_repo_path(value):
            raise FleetReviewClassificationError(
                f"{label} contains an unsafe path: {value!r}"
            )
        paths.append(value)
    return tuple(sorted(set(paths)))


def changed_paths(repo: Path, base_commit: str, head_commit: str) -> tuple[str, ...]:
    raw = _git_bytes(
        repo,
        "diff",
        "--name-only",
        "-z",
        "--no-renames",
        base_commit,
        head_commit,
        "--",
    )
    return _decode_git_paths(raw, "consumer refresh diff")


def run_install_inspection(repo: Path) -> dict[str, object]:
    command = [
        sys.executable,
        str(ROOT / "install.py"),
        str(repo),
        "--check",
        "--json",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=INSPECTION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FleetReviewClassificationError(
            f"installer inspection failed to start or timed out: {exc}"
        ) from exc
    if result.returncode != 0:
        detail = _bounded_detail(result.stderr or result.stdout)
        suffix = f": {detail}" if detail else ""
        raise FleetReviewClassificationError(
            f"installer --check --json exited {result.returncode}{suffix}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FleetReviewClassificationError(
            f"installer inspection did not return valid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise FleetReviewClassificationError(
            "installer inspection JSON must contain an object"
        )
    return payload


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise FleetReviewClassificationError(f"{label} must be an object")
    return value


def validate_inspection(
    payload: Mapping[str, object],
    *,
    repo: Path,
    release_version: str,
    expected_platforms: tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    if payload.get("state") != "current":
        raise FleetReviewClassificationError(
            f"installer inspection state is {payload.get('state')!r}, expected 'current'"
        )
    if payload.get("sourceVersion") != release_version:
        raise FleetReviewClassificationError(
            "installer inspection source version does not match the verified release"
        )
    installed_version = payload.get("installedVersion")
    if installed_version != release_version:
        raise FleetReviewClassificationError(
            "installed provenance version does not match the verified release"
        )
    target = payload.get("target")
    if not isinstance(target, str) or Path(target).resolve() != repo:
        raise FleetReviewClassificationError(
            "installer inspection target does not match the consumer repository"
        )
    change_count = payload.get("changeCount")
    if isinstance(change_count, bool) or change_count != 0:
        raise FleetReviewClassificationError(
            f"installer inspection reports {change_count!r} planned changes"
        )
    platform_payload = _mapping(payload.get("platforms"), "inspection platforms")
    installed_platforms_value = platform_payload.get("installed")
    if not isinstance(installed_platforms_value, list) or not all(
        isinstance(item, str) for item in installed_platforms_value
    ):
        raise FleetReviewClassificationError(
            "inspection installed platforms must be a string array"
        )
    installed_platforms = tuple(sorted(set(installed_platforms_value)))
    if installed_platforms != tuple(sorted(expected_platforms)):
        raise FleetReviewClassificationError(
            "installed platforms do not match the fleet manifest: "
            f"installed {', '.join(installed_platforms) or 'none'}, expected "
            f"{', '.join(sorted(expected_platforms)) or 'none'}"
        )
    audit = _mapping(payload.get("audit"), "inspection audit")
    if not (
        audit.get("requested") is True
        and audit.get("status") == "passed"
        and audit.get("exitCode") == 0
    ):
        raise FleetReviewClassificationError(
            "exact install audit did not pass during installer inspection"
        )
    return installed_version, installed_platforms


def _find_consumer(consumers: Sequence[FleetConsumer], name: str) -> FleetConsumer:
    matches = [consumer for consumer in consumers if consumer.name == name]
    if len(matches) != 1:
        raise FleetReviewClassificationError(
            f"fleet consumer {name!r} is not uniquely configured"
        )
    return matches[0]


def classify_review(
    *,
    consumer_name: str,
    repo: Path,
    base_commit: str,
    remote: str = "origin",
    manifest_path: Path = DEFAULT_PACK_MANIFEST,
    fleet_path: Path = DEFAULT_FLEET_MANIFEST,
    ledger_path: Path = DEFAULT_CANDIDATE_LEDGER,
    release_verifier: ReleaseVerifier = verify_release_identity,
    inspection_runner: InspectionRunner = run_install_inspection,
) -> FleetReviewClassification:
    resolved_repo = repo.expanduser().resolve()
    resolved_base: str | None = None
    head_commit: str | None = None
    release_json: dict[str, str] | None = None
    installed_version: str | None = None
    installed_platforms: tuple[str, ...] = ()
    diff_paths: tuple[str, ...] = ()
    allowed: tuple[str, ...] = ()
    disallowed: tuple[str, ...] = ()
    reasons: list[str] = []

    try:
        source_repo = manifest_path.expanduser().resolve().parent
        release = release_verifier(
            source_repo,
            manifest_path=manifest_path,
            fleet_path=fleet_path,
            ledger_path=ledger_path,
            remote=remote,
        )
        release_json = release.as_json()

        consumers = load_fleet_consumers(fleet_path)
        consumer = _find_consumer(consumers, consumer_name)
        configured_repo = Path(consumer.path_hint).expanduser().resolve()
        if configured_repo != resolved_repo:
            raise FleetReviewClassificationError(
                f"consumer path does not match fleet manifest: {resolved_repo} != {configured_repo}"
            )

        if not FULL_COMMIT_RE.fullmatch(base_commit):
            raise FleetReviewClassificationError(
                "base commit must be a full 40- or 64-character hexadecimal object ID"
            )
        try:
            resolved_base = resolve_commit(resolved_repo, base_commit)
            head_commit = resolve_commit(resolved_repo, "HEAD")
        except ReleaseIdentityError as exc:
            raise FleetReviewClassificationError(str(exc)) from exc
        if resolved_base.casefold() != base_commit.casefold():
            raise FleetReviewClassificationError(
                f"base commit resolved unexpectedly: {base_commit} -> {resolved_base}"
            )

        dirty = _git_bytes(
            resolved_repo,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        )
        if dirty:
            raise FleetReviewClassificationError(
                "consumer working tree is not clean at classification time"
            )
        ancestry = run_git(
            resolved_repo,
            ["merge-base", "--is-ancestor", resolved_base, head_commit],
            accepted_returncodes={0, 1},
        ).returncode
        if ancestry != 0:
            raise FleetReviewClassificationError(
                f"base commit {resolved_base} is not an ancestor of {head_commit}"
            )

        inspection = inspection_runner(resolved_repo)
        installed_version, installed_platforms = validate_inspection(
            inspection,
            repo=resolved_repo,
            release_version=release.version,
            expected_platforms=consumer.platforms,
        )

        base_targets = installed_targets_at_commit(resolved_repo, resolved_base)
        current_targets = current_installed_targets(resolved_repo)
        allowed_set = base_targets | current_targets | RECEIPT_PATHS
        allowed = tuple(sorted(allowed_set))
        diff_paths = changed_paths(resolved_repo, resolved_base, head_commit)
        if not diff_paths:
            raise FleetReviewClassificationError(
                "consumer branch has no committed refresh changes"
            )
        disallowed = tuple(sorted(set(diff_paths) - allowed_set))
        if disallowed:
            raise FleetReviewClassificationError(
                "consumer-owned or unclassified paths changed: "
                + ", ".join(disallowed)
            )
    except (
        FleetReviewClassificationError,
        FleetConfigError,
        ReleaseIdentityError,
        OSError,
    ) as exc:
        reasons.append(_bounded_detail(str(exc)))

    return FleetReviewClassification(
        eligible=not reasons,
        consumer=consumer_name,
        repository=str(resolved_repo),
        base_commit=resolved_base,
        head_commit=head_commit,
        release_identity=release_json,
        installed_version=installed_version,
        installed_platforms=installed_platforms,
        changed_paths=diff_paths,
        allowed_paths=allowed,
        disallowed_paths=disallowed,
        reasons=tuple(reasons),
    )


def render_human(result: FleetReviewClassification) -> str:
    lines = [
        f"fleet review classification: {result.classification}",
        f"consumer: {result.consumer}",
        f"repository: {result.repository}",
        f"base: {result.base_commit or 'unverified'}",
        f"head: {result.head_commit or 'unverified'}",
        f"changed paths: {len(result.changed_paths)}",
    ]
    if result.release_identity is not None:
        lines.append(
            "release: "
            f"{result.release_identity['tag']} at {result.release_identity['commit']}"
        )
    if result.disallowed_paths:
        lines.append("disallowed paths:")
        lines.extend(f"- {path}" for path in result.disallowed_paths)
    if result.reasons:
        lines.append("reasons:")
        lines.extend(f"- {reason}" for reason in result.reasons)
    else:
        lines.append("reasons: none")
    return "\n".join(lines)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prove a fleet consumer branch is a pure installer-managed refresh "
            "eligible for integration-only review."
        )
    )
    parser.add_argument("--consumer", required=True, help="fleet consumer name")
    parser.add_argument("--repo", required=True, type=Path, help="consumer checkout")
    parser.add_argument(
        "--base-commit",
        required=True,
        help="exact consumer commit captured before the refresh branch",
    )
    parser.add_argument(
        "--remote",
        default="origin",
        help="pack release remote; defaults to origin",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_PACK_MANIFEST)
    parser.add_argument("--fleet", type=Path, default=DEFAULT_FLEET_MANIFEST)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_CANDIDATE_LEDGER)
    parser.add_argument("--json", action="store_true", help="print JSON")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    result = classify_review(
        consumer_name=args.consumer,
        repo=args.repo,
        base_commit=args.base_commit,
        remote=args.remote,
        manifest_path=args.manifest,
        fleet_path=args.fleet,
        ledger_path=args.ledger,
    )
    if args.json:
        print(json.dumps(result.as_json(), indent=2, sort_keys=True))
    else:
        print(render_human(result))
    return 0 if result.eligible else 1


if __name__ == "__main__":
    raise SystemExit(main())
